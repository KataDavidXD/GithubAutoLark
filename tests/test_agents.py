"""Unit tests for the agent layer — supervisor routing, tools, and sub-agents.

External APIs are mocked; DB uses real temp SQLite.
LangGraph compilation is tested where available.
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

from src.agent.supervisor import (
    classify_intent_keywords,
    parse_command,
    route_by_intent,
    ask_clarification,
)
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
# 1. Intent Classification (keyword-based)
# ===========================================================================

class TestIntentClassification(unittest.TestCase):
    def test_member_create(self):
        intent, action, ent = classify_intent_keywords("Add member Alice alice@co.com as developer")
        self.assertEqual(intent, "member_management")
        self.assertEqual(action, "create")
        self.assertEqual(ent.get("email"), "alice@co.com")
        self.assertEqual(ent.get("role"), "developer")

    def test_member_show(self):
        intent, action, ent = classify_intent_keywords("Show member Alice")
        self.assertEqual(intent, "member_management")
        self.assertEqual(action, "read")
        self.assertEqual(ent.get("name"), "Alice")

    def test_member_list(self):
        intent, action, _ = classify_intent_keywords("List members by role developer")
        self.assertEqual(intent, "member_management")
        self.assertEqual(action, "list")

    def test_member_work(self):
        intent, action, ent = classify_intent_keywords("Show Alice's work")
        self.assertEqual(intent, "member_management")
        self.assertEqual(action, "read")
        self.assertEqual(ent.get("name"), "Alice")

    def test_github_create(self):
        intent, action, ent = classify_intent_keywords(
            "Create issue 'Fix login bug' assigned to Alice label:bug"
        )
        self.assertEqual(intent, "github_issues")
        self.assertEqual(action, "create")
        self.assertEqual(ent.get("title"), "Fix login bug")
        self.assertEqual(ent.get("assignee"), "Alice")

    def test_github_show(self):
        intent, action, ent = classify_intent_keywords("Show issue #42")
        self.assertEqual(intent, "github_issues")
        self.assertEqual(action, "read")
        self.assertEqual(ent.get("issue_number"), 42)

    def test_github_close(self):
        intent, action, ent = classify_intent_keywords("Close issue #10")
        self.assertEqual(intent, "github_issues")
        self.assertEqual(action, "close")
        self.assertEqual(ent.get("issue_number"), 10)

    def test_github_list(self):
        intent, action, _ = classify_intent_keywords("List issues by Alice")
        self.assertEqual(intent, "github_issues")
        self.assertEqual(action, "list")

    def test_github_send_to_lark(self):
        intent, action, ent = classify_intent_keywords(
            "Send issue #5 to lark table Backend Tasks"
        )
        self.assertEqual(intent, "github_issues")
        self.assertEqual(action, "convert")
        self.assertTrue(ent.get("send_to_lark"))

    def test_lark_create(self):
        intent, action, ent = classify_intent_keywords(
            "Create task in table Design 'Design mockup' assigned to Bob"
        )
        self.assertEqual(intent, "lark_tables")
        self.assertEqual(action, "create")
        self.assertEqual(ent.get("title"), "Design mockup")

    def test_lark_list_tables(self):
        intent, action, _ = classify_intent_keywords("List tables")
        self.assertEqual(intent, "lark_tables")
        self.assertEqual(action, "list")

    def test_lark_send_to_github(self):
        intent, action, ent = classify_intent_keywords("Send record rec_abc to github")
        self.assertEqual(intent, "lark_tables")
        self.assertEqual(action, "convert")
        self.assertEqual(ent.get("record_id"), "rec_abc")
        self.assertTrue(ent.get("send_to_github"))

    def test_sync_pending(self):
        intent, action, _ = classify_intent_keywords("Sync pending")
        self.assertEqual(intent, "cross_platform_sync")

    def test_sync_status(self):
        intent, action, _ = classify_intent_keywords("Sync status")
        self.assertEqual(intent, "cross_platform_sync")

    def test_unknown(self):
        intent, _, _ = classify_intent_keywords("Hello world")
        self.assertEqual(intent, "unknown")


# ===========================================================================
# 2. Supervisor Routing
# ===========================================================================

class TestSupervisorRouting(unittest.TestCase):
    def test_parse_command(self):
        state = {"user_command": "Add member Alice alice@co.com", "messages": []}
        result = parse_command(state)
        self.assertEqual(result["intent"], "member_management")

    def test_route_member(self):
        state = {"intent": "member_management"}
        self.assertEqual(route_by_intent(state), "member_agent")

    def test_route_github(self):
        state = {"intent": "github_issues"}
        self.assertEqual(route_by_intent(state), "github_agent")

    def test_route_lark(self):
        state = {"intent": "lark_tables"}
        self.assertEqual(route_by_intent(state), "lark_agent")

    def test_route_sync(self):
        state = {"intent": "cross_platform_sync"}
        self.assertEqual(route_by_intent(state), "sync_agent")

    def test_route_unknown(self):
        state = {"intent": "unknown"}
        self.assertEqual(route_by_intent(state), "ask_clarification")

    def test_ask_clarification(self):
        state = {"user_command": "do something weird"}
        result = ask_clarification(state)
        self.assertIn("couldn't understand", result["result"])


# ===========================================================================
# 3. Member Tools
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
# 4. GitHub Tools
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
# 5. Lark Tools
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
# 6. Sync Tools
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
# 7. LangGraph Integration (compile + run)
# ===========================================================================

class TestLangGraphIntegration(unittest.TestCase):
    """Test that the LangGraph graph compiles and runs end-to-end."""

    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_github.repo_slug = "owner/repo"
        self.mock_lark = MagicMock()

    def tearDown(self):
        self.db.close()

    def test_graph_compiles(self):
        try:
            from src.agent.graph import compile_graph
            app = compile_graph(self.db, self.mock_github, self.mock_lark)
            self.assertIsNotNone(app)
        except ImportError:
            self.skipTest("langgraph not installed")

    def test_run_member_command(self):
        try:
            from src.agent.graph import run_command
            self.mock_lark.get_user_id_by_email.return_value = None
            result = run_command(
                "Add member Alice alice@co.com as developer",
                db=self.db,
                github_service=self.mock_github,
                lark_service=self.mock_lark,
            )
            self.assertIn("alice@co.com", result)
            self.assertIn("created", result)
        except ImportError:
            self.skipTest("langgraph not installed")

    def test_run_unknown_command(self):
        try:
            from src.agent.graph import run_command
            result = run_command(
                "do something weird",
                db=self.db,
                github_service=self.mock_github,
                lark_service=self.mock_lark,
            )
            self.assertIn("couldn't understand", result)
        except ImportError:
            self.skipTest("langgraph not installed")

    def test_run_github_command(self):
        try:
            from src.agent.graph import run_command
            self.mock_github.create_issue.return_value = {"number": 77}
            result = run_command(
                "Create issue 'Fix auth module' label:feature",
                db=self.db,
                github_service=self.mock_github,
                lark_service=self.mock_lark,
            )
            self.assertIn("#77", result)
        except ImportError:
            self.skipTest("langgraph not installed")

    def test_run_sync_command(self):
        try:
            from src.agent.graph import run_command
            result = run_command(
                "Sync status",
                db=self.db,
                github_service=self.mock_github,
                lark_service=self.mock_lark,
            )
            self.assertIn("Pending events", result)
        except ImportError:
            self.skipTest("langgraph not installed")

    def test_run_list_tables_command(self):
        try:
            from src.agent.graph import run_command
            LarkTableRepository(self.db).register(LarkTableConfig(
                app_token="app1", table_id="tbl1", table_name="Frontend Tasks",
                is_default=True,
            ))
            result = run_command(
                "List tables",
                db=self.db,
                github_service=self.mock_github,
                lark_service=self.mock_lark,
            )
            self.assertIn("Frontend Tasks", result)
        except ImportError:
            self.skipTest("langgraph not installed")


if __name__ == "__main__":
    unittest.main()
