"""Unit tests for the agent layer — tool registry, tools, and plan execution.

External APIs are mocked; DB uses real temp SQLite.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.outbox_repo import OutboxRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole
from src.models.task import Task, TaskStatus
from src.models.mapping import Mapping
from src.models.lark_table_registry import LarkTableConfig

from src.agent.tool_registry import ToolRegistry
from src.agent.tools.member_tools import MemberTools
from src.agent.tools.github_tools import GitHubTools
from src.agent.tools.lark_tools import LarkTools
from src.agent.tools.sync_tools import SyncTools


def _make_db() -> Database:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(path=Path(tmp.name))
    db.init()
    return db


# ===========================================================================
# 1. Tool Registry
# ===========================================================================

class TestToolRegistry(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_github.repo_slug = "owner/repo"
        self.mock_lark = MagicMock()
        self.registry = ToolRegistry(self.db, self.mock_github, self.mock_lark)

    def tearDown(self):
        self.db.close()

    def test_unknown_tool(self):
        result = self.registry.execute("nonexistent", {})
        self.assertIn("Unknown tool", result)

    def test_list_members(self):
        result = self.registry.execute("list_members", {})
        self.assertIn("No members", result)

    def test_sync_status(self):
        result = self.registry.execute("sync_status", {})
        self.assertIn("Pending events", result)

    def test_param_error(self):
        result = self.registry.execute("get_issue", {"bad_param": 1})
        self.assertIn("error", result.lower())


# ===========================================================================
# 2. Member Tools
# ===========================================================================

class TestMemberTools(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_lark = MagicMock()
        self.mock_lark.get_user_id_by_email.return_value = None
        self.mock_github = MagicMock()
        self.tools = MemberTools(self.db, self.mock_lark, self.mock_github)

    def tearDown(self):
        self.db.close()

    def test_create_and_get(self):
        result = self.tools.create_member("Alice", "alice@co.com", role="developer")
        self.assertIn("created", result)

        info = self.tools.get_member("alice@co.com")
        self.assertIn("Alice", info)
        self.assertIn("developer", info)

    def test_list_members(self):
        self.tools.create_member("Alice", "a@co.com", role="developer")
        self.tools.create_member("Bob", "b@co.com", role="qa")
        result = self.tools.list_members()
        self.assertIn("2 member(s)", result)

    def test_deactivate(self):
        self.tools.create_member("Alice", "alice@co.com")
        result = self.tools.deactivate_member("alice@co.com")
        self.assertIn("deactivated", result)

    def test_get_nonexistent(self):
        result = self.tools.get_member("nobody@co.com")
        self.assertIn("not found", result)


# ===========================================================================
# 3. GitHub Tools
# ===========================================================================

class TestGitHubTools(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_github.repo_slug = "owner/repo"
        self.tools = GitHubTools(self.db, github_service=self.mock_github)

        MemberRepository(self.db).create(
            Member(name="Alice", email="alice@co.com", github_username="alice-gh")
        )

    def tearDown(self):
        self.db.close()

    def test_create_issue(self):
        self.mock_github.create_issue.return_value = {"number": 55}
        result = self.tools.create_issue(
            "Fix bug", body="Details", assignee="Alice", labels=["bug"]
        )
        self.assertIn("#55", result)
        self.mock_github.create_issue.assert_called_once()
        call_kw = self.mock_github.create_issue.call_args
        self.assertEqual(call_kw[1]["assignees"], ["alice-gh"])

    def test_create_issue_with_lark_sync(self):
        self.mock_github.create_issue.return_value = {"number": 56}
        result = self.tools.create_issue(
            "Auth module", send_to_lark=True, target_table="Backend"
        )
        self.assertIn("Lark sync", result)
        pending = OutboxRepository(self.db).get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_type"], "convert_issue_to_lark")

    def test_close_issue(self):
        self.mock_github.close_issue.return_value = {"number": 10}
        result = self.tools.close_issue(10)
        self.assertIn("closed", result)

    def test_list_issues(self):
        self.mock_github.list_issues.return_value = [
            {"number": 1, "title": "Issue 1", "state": "open", "assignees": [], "labels": []},
        ]
        result = self.tools.list_issues()
        self.assertIn("1 issue(s)", result)

    def test_send_to_lark(self):
        result = self.tools.send_issue_to_lark(42, "Frontend Tasks")
        self.assertIn("queued", result)

    def test_no_github_service(self):
        tools = GitHubTools(self.db)
        result = tools.create_issue("Test")
        self.assertIn("not configured", result)


# ===========================================================================
# 4. Lark Tools
# ===========================================================================

class TestLarkTools(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_lark = MagicMock()
        self.tools = LarkTools(self.db, lark_service=self.mock_lark)

        LarkTableRepository(self.db).register(LarkTableConfig(
            app_token="app1", table_id="tbl1", table_name="Tasks", is_default=True,
        ))

    def tearDown(self):
        self.db.close()

    def test_create_record(self):
        self.mock_lark.create_record.return_value = {
            "record": {"record_id": "rec_new_123"}
        }
        result = self.tools.create_record("My Task", table_name="Tasks")
        self.assertIn("created", result)
        self.mock_lark.create_record.assert_called_once()

    def test_list_tables(self):
        result = self.tools.list_tables()
        self.assertIn("Tasks", result)
        self.assertIn("1", result)

    def test_send_to_github(self):
        result = self.tools.send_record_to_github("rec_abc")
        self.assertIn("queued", result)

    def test_register_table(self):
        result = self.tools.register_table(
            "New Table", "app1", "tbl_new", is_default=False
        )
        self.assertIn("registered", result)

    def test_no_lark_service(self):
        tools = LarkTools(self.db)
        result = tools.create_record("Test")
        self.assertIn("not configured", result)


# ===========================================================================
# 5. Sync Tools
# ===========================================================================

class TestSyncTools(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_lark = MagicMock()
        self.tools = SyncTools(
            self.db, github_service=self.mock_github, lark_service=self.mock_lark
        )

    def tearDown(self):
        self.db.close()

    def test_sync_status(self):
        result = self.tools.sync_status()
        self.assertIn("Pending events: 0", result)

    def test_sync_pending_empty(self):
        result = self.tools.sync_pending()
        self.assertIn("0 pending", result)


# ===========================================================================
# 6. Plan Execution via chat()
# ===========================================================================

class TestPlanExecution(unittest.TestCase):
    """Test that the plan executor works with run_command (graph.py shim)."""

    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_github.repo_slug = "owner/repo"
        self.mock_lark = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_run_command_delegates_to_chat(self):
        from src.agent.graph import run_command
        self.mock_lark.get_user_id_by_email.return_value = None
        result = run_command(
            "list members",
            db=self.db,
            github_service=self.mock_github,
            lark_service=self.mock_lark,
        )
        # Should return something (either LLM result or fallback)
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
