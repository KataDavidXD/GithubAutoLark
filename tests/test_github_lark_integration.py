"""
Comprehensive integration tests for GitHub-Lark task synchronization.
Tests cover: assignee handling, due dates, progress tracking, bidirectional sync.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import Mock, patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole
from src.models.task import Task, TaskStatus, TaskSource
from src.models.mapping import Mapping
from src.models.lark_table_registry import LarkTableConfig
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools


@pytest.fixture
def test_db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    db = Database(path=db_path)
    db.init()
    return db


@pytest.fixture
def sample_members(test_db):
    """Create sample members for testing."""
    repo = MemberRepository(test_db)
    
    members = [
        Member(
            name="Alice Chen",
            email="alice@example.com",
            github_username="alicechen",
            lark_open_id="ou_alice123",
            team="MAS Engine",
            role=MemberRole.MANAGER,
        ),
        Member(
            name="Bob Wang",
            email="bob@example.com",
            github_username="bobwang",
            lark_open_id="ou_bob456",
            team="MAS Engine",
            role=MemberRole.DEVELOPER,
        ),
        Member(
            name="Carol Li",
            email="carol@example.com",
            github_username="carolli",
            lark_open_id="ou_carol789",
            team="Agent Optimization",
            role=MemberRole.DEVELOPER,
        ),
    ]
    
    for m in members:
        repo.create(m)
    
    return members


@pytest.fixture
def mock_github_service():
    """Create a mock GitHub service."""
    mock = Mock()
    mock.repo_slug = "test-org/test-repo"
    mock.create_issue = Mock(return_value={
        "number": 42,
        "title": "Test Issue",
        "html_url": "https://github.com/test-org/test-repo/issues/42",
    })
    mock.get_issue = Mock(return_value={
        "number": 42,
        "title": "Test Issue",
        "state": "open",
        "body": "Test body",
        "assignees": [{"login": "alicechen"}],
        "labels": [{"name": "bug"}],
        "html_url": "https://github.com/test-org/test-repo/issues/42",
    })
    mock.update_issue = Mock(return_value={"number": 42})
    mock.list_issues = Mock(return_value=[
        {"number": 1, "title": "Issue 1", "state": "open", "assignees": [], "labels": []},
        {"number": 2, "title": "Issue 2", "state": "open", "assignees": [{"login": "bobwang"}], "labels": []},
    ])
    mock.close_issue = Mock(return_value={"number": 42, "state": "closed"})
    return mock


@pytest.fixture
def mock_lark_service():
    """Create a mock Lark service."""
    mock = Mock()
    mock.create_record = Mock(return_value={
        "record": {"record_id": "rec_test123456"},
    })
    mock.get_record = Mock(return_value={
        "record_id": "rec_test123456",
        "fields": {
            "Task Name": "Test Task",
            "Status": "To Do",
            "Description": "Test description",
        },
    })
    mock.update_record = Mock(return_value={"record_id": "rec_test123456"})
    mock.search_records = Mock(return_value=[
        {"record_id": "rec_001", "fields": {"Task Name": "Task 1", "Status": "To Do"}},
        {"record_id": "rec_002", "fields": {"Task Name": "Task 2", "Status": "In Progress"}},
    ])
    return mock


@pytest.fixture
def table_config(test_db):
    """Register a test table configuration."""
    repo = LarkTableRepository(test_db)
    config = LarkTableConfig(
        app_token="test_app_token",
        table_id="test_table_id",
        table_name="Test Tasks",
        is_default=True,
        field_mapping={
            "title_field": "Task Name",
            "status_field": "Status",
            "body_field": "Description",
            "assignee_field": "Assignee",
        },
    )
    repo.register(config)
    return config


class TestAssigneeResolution:
    """Test assignee lookup and resolution across platforms."""
    
    def test_resolve_by_email(self, test_db, sample_members, mock_github_service):
        """Resolve assignee by email address."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.create_issue(
            title="Bug fix",
            body="Fix the login issue",
            assignee="alice@example.com",
        )
        
        assert "Issue #42" in result
        assert "Assigned to alicechen" in result
        mock_github_service.create_issue.assert_called_once()
        call_args = mock_github_service.create_issue.call_args
        assert call_args.kwargs.get("assignees") == ["alicechen"]
    
    def test_resolve_by_name(self, test_db, sample_members, mock_github_service):
        """Resolve assignee by name."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.create_issue(
            title="Feature request",
            body="Add dark mode",
            assignee="Bob Wang",
        )
        
        assert "Issue #42" in result
        mock_github_service.create_issue.assert_called_once()
        call_args = mock_github_service.create_issue.call_args
        assert call_args.kwargs.get("assignees") == ["bobwang"]
    
    def test_resolve_by_github_username(self, test_db, sample_members, mock_github_service):
        """Resolve assignee by GitHub username."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.create_issue(
            title="Test issue",
            body="",
            assignee="carolli",
        )
        
        mock_github_service.create_issue.assert_called_once()
        call_args = mock_github_service.create_issue.call_args
        assert call_args.kwargs.get("assignees") == ["carolli"]
    
    def test_resolve_lark_assignee(self, test_db, sample_members, mock_lark_service, table_config):
        """Resolve assignee for Lark records using open_id."""
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.create_record(
            title="Lark Task",
            assignee="alice@example.com",
            status="To Do",
        )
        
        assert "Record 'Lark Task' created" in result
        mock_lark_service.create_record.assert_called_once()
    
    def test_unknown_assignee_no_crash(self, test_db, sample_members, mock_github_service):
        """Creating issue with unknown assignee should not crash."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.create_issue(
            title="Test",
            body="",
            assignee="unknown_person@nowhere.com",
        )
        
        assert "Issue #42" in result
        call_args = mock_github_service.create_issue.call_args
        assert call_args.kwargs.get("assignees") is None


class TestBidirectionalSync:
    """Test synchronization between GitHub and Lark."""
    
    def test_github_to_lark_sync(self, test_db, sample_members, mock_github_service, mock_lark_service, table_config):
        """Creating GitHub issue should queue Lark sync when requested."""
        tools = GitHubTools(test_db, mock_github_service, mock_lark_service)
        result = tools.create_issue(
            title="Sync Test Issue",
            body="This should sync to Lark",
            assignee="alice@example.com",
            send_to_lark=True,
        )
        
        assert "Queued for Lark sync" in result
        
        from src.db.outbox_repo import OutboxRepository
        outbox = OutboxRepository(test_db)
        pending = outbox.get_pending()
        assert len(pending) == 1
        assert pending[0]["event_type"] == "convert_issue_to_lark"
    
    def test_lark_to_github_sync(self, test_db, sample_members, mock_lark_service, mock_github_service, table_config):
        """Creating Lark record should queue GitHub sync when requested."""
        tools = LarkTools(test_db, mock_lark_service, mock_github_service)
        result = tools.create_record(
            title="Sync Test Record",
            assignee="bob@example.com",
            send_to_github=True,
        )
        
        assert "Queued for GitHub sync" in result
        
        from src.db.outbox_repo import OutboxRepository
        outbox = OutboxRepository(test_db)
        pending = outbox.get_pending()
        assert len(pending) == 1
        assert pending[0]["event_type"] == "convert_record_to_github"
    
    def test_mapping_created_on_github_issue(self, test_db, sample_members, mock_github_service):
        """Creating issue should create a task-issue mapping."""
        tools = GitHubTools(test_db, mock_github_service)
        tools.create_issue(title="Mapping Test", body="")
        
        mapping_repo = MappingRepository(test_db)
        task_repo = TaskRepository(test_db)
        
        tasks = task_repo.list_all()
        assert len(tasks) == 1
        
        mapping = mapping_repo.get_by_github_issue(42)
        assert mapping is not None
        assert mapping.github_repo == "test-org/test-repo"
    
    def test_mapping_created_on_lark_record(self, test_db, sample_members, mock_lark_service, table_config):
        """Creating Lark record should create a task-record mapping."""
        tools = LarkTools(test_db, mock_lark_service)
        tools.create_record(title="Mapping Test", status="To Do")
        
        mapping_repo = MappingRepository(test_db)
        task_repo = TaskRepository(test_db)
        
        tasks = task_repo.list_all()
        assert len(tasks) == 1
        
        mapping = mapping_repo.get_by_lark_record("rec_test123456")
        assert mapping is not None


class TestIssueAndRecordCRUD:
    """Test create, read, update operations."""
    
    def test_get_github_issue(self, test_db, mock_github_service):
        """Get GitHub issue details."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.get_issue(42)
        
        assert "Issue #42" in result
        assert "Test Issue" in result
        assert "alicechen" in result
    
    def test_update_github_issue(self, test_db, sample_members, mock_github_service):
        """Update GitHub issue."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.update_issue(
            issue_number=42,
            title="Updated Title",
            state="closed",
            assignee="bob@example.com",
        )
        
        assert "Issue #42 updated" in result
        mock_github_service.update_issue.assert_called_once()
        call_args = mock_github_service.update_issue.call_args
        assert call_args.kwargs.get("assignees") == ["bobwang"]
    
    def test_list_github_issues_with_filter(self, test_db, sample_members, mock_github_service):
        """List GitHub issues with filters."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.list_issues(state="open")
        
        assert "2 issue(s)" in result
        assert "#1" in result
        assert "#2" in result
    
    def test_close_github_issue(self, test_db, mock_github_service):
        """Close a GitHub issue."""
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.close_issue(42)
        
        assert "Issue #42 closed" in result
        mock_github_service.close_issue.assert_called_once_with(42)
    
    def test_get_lark_record(self, test_db, mock_lark_service, table_config):
        """Get Lark record details."""
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.get_record("rec_test123456")
        
        assert "rec_test123456" in result
        assert "Task Name" in result
    
    def test_update_lark_record(self, test_db, mock_lark_service, table_config):
        """Update Lark record fields."""
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.update_record(
            record_id="rec_test123456",
            Status="Done",
        )
        
        assert "updated" in result
        mock_lark_service.update_record.assert_called_once()
    
    def test_list_lark_records(self, test_db, mock_lark_service, table_config):
        """List Lark records."""
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.list_records()
        
        assert "2 record(s)" in result
        assert "Task 1" in result
        assert "Task 2" in result


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def test_github_service_not_configured(self, test_db):
        """Handle missing GitHub service gracefully."""
        tools = GitHubTools(test_db, github_service=None)
        result = tools.create_issue(title="Test", body="")
        
        assert "Error: GitHub service not configured" in result
    
    def test_lark_service_not_configured(self, test_db):
        """Handle missing Lark service gracefully."""
        tools = LarkTools(test_db, lark_service=None)
        result = tools.create_record(title="Test", status="To Do")
        
        assert "Error: Lark service not configured" in result
    
    def test_github_api_error(self, test_db, mock_github_service):
        """Handle GitHub API errors."""
        mock_github_service.create_issue.side_effect = Exception("API rate limit exceeded")
        
        tools = GitHubTools(test_db, mock_github_service)
        result = tools.create_issue(title="Test", body="")
        
        assert "Error creating issue" in result
        assert "rate limit" in result
    
    def test_lark_api_error(self, test_db, mock_lark_service, table_config):
        """Handle Lark API errors."""
        mock_lark_service.create_record.side_effect = Exception("Permission denied")
        
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.create_record(title="Test", status="To Do")
        
        assert "Error creating record" in result


class TestTableRegistry:
    """Test Lark table registry operations."""
    
    def test_register_table(self, test_db):
        """Register a new Lark table."""
        tools = LarkTools(test_db)
        result = tools.register_table(
            table_name="New Project",
            app_token="app_123",
            table_id="tbl_456",
            is_default=False,
        )
        
        assert "Table 'New Project' registered" in result
    
    def test_list_tables(self, test_db, table_config):
        """List registered tables."""
        tools = LarkTools(test_db)
        result = tools.list_tables()
        
        assert "Test Tasks" in result
        assert "[DEFAULT]" in result
    
    def test_resolve_table_by_name(self, test_db, mock_lark_service, table_config):
        """Create record in specific table by name."""
        tools = LarkTools(test_db, mock_lark_service)
        result = tools.create_record(
            title="Specific Table Task",
            table_name="Test Tasks",
            status="To Do",
        )
        
        assert "Record 'Specific Table Task' created in table 'Test Tasks'" in result


class TestMemberRepository:
    """Test member lookup functionality."""
    
    def test_find_by_name_partial(self, test_db, sample_members):
        """Find members by partial name match."""
        repo = MemberRepository(test_db)
        results = repo.find_by_name("Alice")
        
        assert len(results) == 1
        assert results[0].name == "Alice Chen"
    
    def test_find_by_team(self, test_db, sample_members):
        """Find members by team."""
        repo = MemberRepository(test_db)
        results = repo.list_all(team="MAS Engine")
        
        assert len(results) == 2
        names = [m.name for m in results]
        assert "Alice Chen" in names
        assert "Bob Wang" in names
    
    def test_get_by_github(self, test_db, sample_members):
        """Get member by GitHub username."""
        repo = MemberRepository(test_db)
        member = repo.get_by_github("carolli")
        
        assert member is not None
        assert member.name == "Carol Li"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
