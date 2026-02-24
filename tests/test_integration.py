"""Integration tests — end-to-end flows through the full agent system.

Simulates real user command sequences with mocked external APIs.
Verifies ACID transactions, outbox consistency, and cross-agent flows.
"""

from __future__ import annotations

import json
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
from src.db.sync_log_repo import SyncLogRepository
from src.models.member import Member, MemberRole
from src.models.task import Task, TaskStatus
from src.models.lark_table_registry import LarkTableConfig
from src.agent.graph import run_command
from src.sync.engine import SyncEngine


def _make_db() -> Database:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(path=Path(tmp.name))
    db.init()
    return db


class IntegrationTestBase(unittest.TestCase):
    """Base class with common setup for integration tests."""

    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_github.repo_slug = "owner/repo"
        self.mock_lark = MagicMock()
        self.mock_lark.get_user_id_by_email.return_value = None

        # Seed tables
        self.table_repo = LarkTableRepository(self.db)
        self.default_table = LarkTableConfig(
            app_token="app1", table_id="tbl_default",
            table_name="Default Tasks", is_default=True,
        )
        self.table_repo.register(self.default_table)
        self.backend_table = LarkTableConfig(
            app_token="app1", table_id="tbl_backend",
            table_name="Backend Tasks",
        )
        self.table_repo.register(self.backend_table)

    def tearDown(self):
        self.db.close()

    def _run(self, command: str) -> str:
        return run_command(
            command, db=self.db,
            github_service=self.mock_github,
            lark_service=self.mock_lark,
        )


# ===========================================================================
# UC-1: Full member lifecycle
# ===========================================================================

class TestMemberLifecycle(IntegrationTestBase):

    def test_create_show_update_deactivate(self):
        result = self._run("Add member Alice alice@co.com as developer")
        self.assertIn("created", result)

        result = self._run("Show member Alice")
        self.assertIn("Alice", result)
        self.assertIn("developer", result)

        result = self._run("Update member Alice role to manager")
        self.assertIn("updated", result)

        result = self._run("Show member Alice")
        self.assertIn("manager", result)

        result = self._run("Remove member Alice")
        self.assertIn("deactivated", result)

    def test_list_members_by_role(self):
        self._run("Add member Alice alice@co.com as developer")
        self._run("Add member Bob bob@co.com as qa")
        self._run("Add member Carol carol@co.com as developer")

        result = self._run("List members")
        self.assertIn("3 member(s)", result)


# ===========================================================================
# UC-2: GitHub issue lifecycle with Lark sync
# ===========================================================================

class TestGitHubIssueLarkSync(IntegrationTestBase):

    def test_create_issue_and_sync_to_lark(self):
        self._run("Add member Alice alice@co.com as developer")

        self.mock_github.create_issue.return_value = {"number": 42}
        result = self._run("Create issue 'Fix auth bug' assigned to Alice label:bug")
        self.assertIn("#42", result)

        # Verify local task and mapping were created
        task_repo = TaskRepository(self.db)
        tasks = task_repo.list_all()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].title, "Fix auth bug")

        mapping_repo = MappingRepository(self.db)
        mapping = mapping_repo.get_by_github_issue(42)
        self.assertIsNotNone(mapping)

    def test_send_issue_to_lark_via_outbox(self):
        self._run("Add member Alice alice@co.com as developer")
        self.mock_github.create_issue.return_value = {"number": 55}

        result = self._run("Send issue #55 to lark table Backend Tasks")
        self.assertIn("queued", result)

        # Verify outbox event was created
        outbox = OutboxRepository(self.db)
        pending = outbox.get_pending()
        self.assertTrue(len(pending) >= 1)
        event = pending[0]
        self.assertEqual(event["event_type"], "convert_issue_to_lark")
        payload = json.loads(event["payload_json"])
        self.assertEqual(payload["issue_number"], 55)

    def test_full_sync_pipeline(self):
        """Create issue → outbox → sync engine processes → mapping updated."""
        self._run("Add member Alice alice@co.com as developer")
        self.mock_github.create_issue.return_value = {"number": 60}

        self._run("Create issue 'Backend refactor' label:feature")

        # Queue sync to Lark
        task_repo = TaskRepository(self.db)
        tasks = task_repo.list_all()
        task_id = tasks[0].task_id

        outbox = OutboxRepository(self.db)
        outbox.enqueue("sync_lark_create", {"task_id": task_id})

        # Run sync engine
        self.mock_lark.create_record.return_value = {
            "record": {"record_id": "rec_synced_001"}
        }
        engine = SyncEngine(
            self.db, github_service=self.mock_github, lark_service=self.mock_lark
        )
        processed = engine.process_batch()
        self.assertEqual(processed, 1)

        # Verify mapping now includes Lark record
        mapping_repo = MappingRepository(self.db)
        mapping = mapping_repo.get_by_lark_record("rec_synced_001")
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.task_id, task_id)


# ===========================================================================
# UC-3: Lark table management
# ===========================================================================

class TestLarkTableManagement(IntegrationTestBase):

    def test_list_tables(self):
        result = self._run("List tables")
        self.assertIn("Default Tasks", result)
        self.assertIn("Backend Tasks", result)
        self.assertIn("2", result)

    def test_create_record_in_table(self):
        self.mock_lark.create_record.return_value = {
            "record": {"record_id": "rec_new_001"}
        }
        result = self._run("Create record 'Design mockup' in table Default Tasks")
        self.assertIn("created", result)

        # Verify local tracking
        task_repo = TaskRepository(self.db)
        tasks = task_repo.list_all()
        self.assertEqual(len(tasks), 1)

    def test_send_record_to_github(self):
        result = self._run("Send record rec_abc123 to github")
        self.assertIn("queued", result)

        outbox = OutboxRepository(self.db)
        pending = outbox.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_type"], "convert_record_to_github")


# ===========================================================================
# UC-4: Cross-platform sync status
# ===========================================================================

class TestSyncOperations(IntegrationTestBase):

    def test_sync_status_command(self):
        result = self._run("Sync status")
        self.assertIn("Pending events: 0", result)

    def test_sync_pending_command(self):
        result = self._run("Sync pending")
        self.assertIn("0 pending", result)

    def test_retry_failed_command(self):
        outbox = OutboxRepository(self.db)
        eid = outbox.enqueue("sync_github_create", {"task_id": "dummy"})
        outbox.mark_failed(eid, "test error")

        result = self._run("Retry failed")
        self.assertIn("1 failed", result)


# ===========================================================================
# UC-5: ACID consistency under failure
# ===========================================================================

class TestACIDConsistency(IntegrationTestBase):

    def test_github_api_failure_leaves_outbox_intact(self):
        """If GitHub API fails during sync, outbox event is marked failed, not lost."""
        self._run("Add member Alice alice@co.com as developer")

        task = Task(title="Fail task")
        TaskRepository(self.db).create(task)

        outbox = OutboxRepository(self.db)
        outbox.enqueue("sync_github_create", {
            "task_id": task.task_id, "labels": ["auto"]
        })

        self.mock_github.create_issue.side_effect = RuntimeError("API down")
        engine = SyncEngine(
            self.db, github_service=self.mock_github, lark_service=self.mock_lark
        )
        processed = engine.process_batch()
        self.assertEqual(processed, 0)

        # Event should be 'failed', not lost
        row = self.db.fetchone("SELECT * FROM outbox WHERE status = 'failed'")
        self.assertIsNotNone(row)

    def test_dead_letter_after_max_attempts(self):
        """After max_attempts, event is moved to dead-letter."""
        task = Task(title="Dead task")
        TaskRepository(self.db).create(task)

        outbox = OutboxRepository(self.db)
        eid = outbox.enqueue("sync_github_create", {
            "task_id": task.task_id, "labels": ["auto"]
        }, max_attempts=1)

        self.mock_github.create_issue.side_effect = RuntimeError("Permanent failure")
        engine = SyncEngine(
            self.db, github_service=self.mock_github, lark_service=self.mock_lark
        )
        engine.process_batch()

        row = self.db.fetchone("SELECT * FROM outbox WHERE event_id = ?", (eid,))
        self.assertEqual(row["status"], "dead")


# ===========================================================================
# UC-6: Unknown commands handled gracefully
# ===========================================================================

class TestGracefulErrorHandling(IntegrationTestBase):

    def test_unknown_command(self):
        result = self._run("fly me to the moon")
        self.assertIn("couldn't understand", result)
        self.assertIn("Available commands", result)

    def test_missing_member(self):
        result = self._run("Show member NonExistent")
        self.assertIn("not found", result)


if __name__ == "__main__":
    unittest.main()
