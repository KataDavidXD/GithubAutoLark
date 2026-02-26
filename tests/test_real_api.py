"""
Real API integration tests for GitHub and Lark.
Run with: pytest tests/test_real_api.py --real-api -v

These tests create and clean up actual resources. Ensure:
1. .env is configured with valid credentials
2. You have write permissions to the target repo/bitable
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from datetime import datetime

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.lark_table_repo import LarkTableRepository
from src.services.github_service import GitHubService
from src.services.lark_service import LarkService
from src.models.member import Member, MemberRole
from src.models.lark_table_registry import LarkTableConfig
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools


@pytest.fixture(scope="module")
def real_db(tmp_path_factory):
    """Create a test database for real API tests."""
    db_path = tmp_path_factory.mktemp("data") / "test_real.db"
    db = Database(path=db_path)
    db.init()
    return db


@pytest.fixture(scope="module")
def github_service():
    """Create real GitHub service."""
    token = os.getenv("GITHUB_TOKEN")
    repo = os.getenv("GITHUB_REPO")
    
    if not token or not repo:
        pytest.skip("GITHUB_TOKEN and GITHUB_REPO required")
    
    return GitHubService()


@pytest.fixture(scope="module")
def lark_service():
    """Create real Lark service."""
    app_id = os.getenv("LARK_APP_ID")
    app_secret = os.getenv("LARK_APP_SECRET")
    
    if not app_id or not app_secret:
        pytest.skip("LARK_APP_ID and LARK_APP_SECRET required")
    
    svc = LarkService()
    svc.use_direct_api = True
    return svc


@pytest.fixture(scope="module")
def test_table_config(real_db):
    """Register test table configuration from env."""
    app_token = os.getenv("LARK_APP_TOKEN")
    table_id = os.getenv("LARK_TASKS_TABLE_ID")
    
    if not app_token or not table_id:
        pytest.skip("LARK_APP_TOKEN and LARK_TASKS_TABLE_ID required")
    
    repo = LarkTableRepository(real_db)
    config = LarkTableConfig(
        app_token=app_token,
        table_id=table_id,
        table_name="Integration Test Table",
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


@pytest.fixture(scope="module")
def test_member(real_db):
    """Create a test member."""
    repo = MemberRepository(real_db)
    member = Member(
        name="Test User",
        email="test@example.com",
        github_username=os.getenv("GITHUB_TEST_USER", ""),
        lark_open_id=os.getenv("LARK_TEST_USER_ID", ""),
        team="Integration Test",
        role=MemberRole.DEVELOPER,
    )
    repo.create(member)
    return member


@pytest.mark.real_api
class TestGitHubRealAPI:
    """Real GitHub API integration tests."""
    
    def test_create_and_close_issue(self, real_db, github_service, test_member):
        """Create a real GitHub issue and then close it."""
        tools = GitHubTools(real_db, github_service)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"[Integration Test] Auto-created {timestamp}"
        
        result = tools.create_issue(
            title=title,
            body="This is an automated integration test. Will be closed shortly.",
            labels=["test", "automated"],
        )
        
        assert "Issue #" in result
        issue_number = int(result.split("#")[1].split()[0])
        
        time.sleep(1)
        
        get_result = tools.get_issue(issue_number)
        assert title in get_result
        assert "open" in get_result.lower()
        
        close_result = tools.close_issue(issue_number)
        assert "closed" in close_result.lower()
    
    def test_list_open_issues(self, real_db, github_service):
        """List real open issues."""
        tools = GitHubTools(real_db, github_service)
        result = tools.list_issues(state="open")
        
        assert "issue" in result.lower()
    
    def test_create_issue_with_assignee(self, real_db, github_service, test_member):
        """Create issue with assignee (if configured)."""
        if not test_member.github_username:
            pytest.skip("GITHUB_TEST_USER not configured")
        
        tools = GitHubTools(real_db, github_service)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = tools.create_issue(
            title=f"[Assignee Test] {timestamp}",
            body="Testing assignee resolution",
            assignee=test_member.email,
        )
        
        if "Assigned" in result:
            assert test_member.github_username in result
        
        if "#" in result:
            issue_number = int(result.split("#")[1].split()[0])
            tools.close_issue(issue_number)


@pytest.mark.real_api
class TestLarkRealAPI:
    """Real Lark API integration tests."""
    
    def test_create_record(self, real_db, lark_service, test_table_config):
        """Create a real Lark record."""
        tools = LarkTools(real_db, lark_service)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        title = f"[Integration Test] {timestamp}"
        
        result = tools.create_record(
            title=title,
            status="To Do",
            body="Automated integration test record",
        )
        
        assert "Record" in result
        assert "created" in result.lower()
    
    def test_list_records(self, real_db, lark_service, test_table_config):
        """List records from real Lark table."""
        tools = LarkTools(real_db, lark_service)
        result = tools.list_records()
        
        assert "record" in result.lower() or "No records" in result
    
    def test_list_tables(self, real_db, test_table_config):
        """List registered tables."""
        tools = LarkTools(real_db)
        result = tools.list_tables()
        
        assert "Integration Test Table" in result


@pytest.mark.real_api
class TestBidirectionalSyncReal:
    """Test bidirectional sync with real APIs."""
    
    def test_github_to_lark_queue(self, real_db, github_service, lark_service, test_table_config):
        """Create GitHub issue and queue for Lark sync."""
        tools = GitHubTools(real_db, github_service, lark_service)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = tools.create_issue(
            title=f"[Sync Test] {timestamp}",
            body="This issue should sync to Lark",
            send_to_lark=True,
        )
        
        assert "Issue #" in result
        assert "Queued for Lark sync" in result
        
        if "#" in result:
            issue_number = int(result.split("#")[1].split()[0])
            tools.close_issue(issue_number)
    
    def test_lark_to_github_queue(self, real_db, lark_service, github_service, test_table_config):
        """Create Lark record and queue for GitHub sync."""
        tools = LarkTools(real_db, lark_service, github_service)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = tools.create_record(
            title=f"[Sync Test] {timestamp}",
            status="To Do",
            send_to_github=True,
        )
        
        assert "Record" in result
        assert "Queued for GitHub sync" in result


@pytest.mark.real_api
class TestMappingIntegrity:
    """Test that mappings are correctly maintained."""
    
    def test_task_mapping_on_github_create(self, real_db, github_service):
        """Verify task and mapping created on GitHub issue creation."""
        tools = GitHubTools(real_db, github_service)
        
        initial_tasks = len(TaskRepository(real_db).list_all())
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        result = tools.create_issue(
            title=f"[Mapping Test] {timestamp}",
            body="Testing mapping creation",
        )
        
        assert "Issue #" in result
        
        final_tasks = len(TaskRepository(real_db).list_all())
        assert final_tasks == initial_tasks + 1
        
        issue_number = int(result.split("#")[1].split()[0])
        mapping = MappingRepository(real_db).get_by_github_issue(issue_number)
        assert mapping is not None
        
        tools.close_issue(issue_number)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--real-api"])
