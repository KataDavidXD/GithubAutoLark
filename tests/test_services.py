"""Unit tests for the service layer and sync module.

External APIs (GitHub, Lark) are mocked.  DB tests use real temp SQLite.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.outbox_repo import OutboxRepository
from src.db.lark_table_repo import LarkTableRepository
from src.db.sync_log_repo import SyncLogRepository
from src.models.member import Member, MemberRole, LarkTableAssignment
from src.models.task import Task, TaskStatus, TaskPriority, TaskSource
from src.models.mapping import Mapping
from src.models.lark_table_registry import LarkTableConfig
from src.services.member_service import MemberService, MemberWorkSummary
from src.sync.status_mapper import (
    lark_status_to_github_state,
    github_state_to_lark_status,
    normalise_status,
)
from src.sync.field_mapper import (
    github_issue_to_lark_fields,
    lark_record_to_github_fields,
    build_lark_record_fields,
)
from src.sync.engine import SyncEngine


def _make_db() -> Database:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(path=Path(tmp.name))
    db.init()
    return db


# ===========================================================================
# 1. Status Mapper (pure functions)
# ===========================================================================

class TestStatusMapper(unittest.TestCase):
    def test_lark_done_to_github_closed(self):
        state, reason = lark_status_to_github_state("Done")
        self.assertEqual(state, "closed")
        self.assertEqual(reason, "completed")

    def test_lark_todo_to_github_open(self):
        state, reason = lark_status_to_github_state("To Do")
        self.assertEqual(state, "open")
        self.assertIsNone(reason)

    def test_lark_inprogress_to_github_open(self):
        state, reason = lark_status_to_github_state("In Progress")
        self.assertEqual(state, "open")

    def test_github_closed_to_lark_done(self):
        self.assertEqual(github_state_to_lark_status("closed"), "Done")

    def test_github_open_preserves_inprogress(self):
        self.assertEqual(
            github_state_to_lark_status("open", "In Progress"), "In Progress"
        )

    def test_github_open_default_todo(self):
        self.assertEqual(github_state_to_lark_status("open"), "To Do")

    def test_normalise_variants(self):
        self.assertEqual(normalise_status("todo"), "To Do")
        self.assertEqual(normalise_status("in progress"), "In Progress")
        self.assertEqual(normalise_status("DONE"), "Done")
        self.assertEqual(normalise_status("wip"), "In Progress")
        self.assertEqual(normalise_status("completed"), "Done")
        self.assertEqual(normalise_status("garbage"), "To Do")


# ===========================================================================
# 2. Field Mapper
# ===========================================================================

class TestFieldMapper(unittest.TestCase):
    def test_github_issue_to_lark(self):
        issue = {
            "title": "[AUTO][abc12345] Fix auth",
            "body": "Details here",
            "state": "open",
            "number": 42,
        }
        fields = github_issue_to_lark_fields(issue, assignee_open_id="ou_abc")
        self.assertEqual(fields["Task Name"], "Fix auth")
        self.assertEqual(fields["Status"], "To Do")
        self.assertEqual(fields["Assignee"], [{"id": "ou_abc"}])
        self.assertEqual(fields["GitHub Issue"], 42)

    def test_lark_record_to_github(self):
        record = {
            "record_id": "rec_123",
            "fields": {
                "Task Name": "Design mockup",
                "Status": "In Progress",
                "Description": "Full mockup",
            },
        }
        result = lark_record_to_github_fields(
            record, task_id="abcd1234-5678", assignee_github_username="alice-gh"
        )
        self.assertIn("[AUTO][abcd1234]", result["title"])
        self.assertIn("Design mockup", result["title"])
        self.assertEqual(result["state"], "open")
        self.assertEqual(result["assignees"], ["alice-gh"])

    def test_build_lark_record_fields(self):
        fields = build_lark_record_fields(
            title="New Task",
            status="In Progress",
            assignee_open_id="ou_123",
            github_issue_number=7,
        )
        self.assertEqual(fields["Task Name"], "New Task")
        self.assertEqual(fields["Status"], "In Progress")
        self.assertEqual(fields["Assignee"], [{"id": "ou_123"}])
        self.assertEqual(fields["GitHub Issue"], 7)

    def test_custom_field_mapping(self):
        cfg = LarkTableConfig(
            app_token="app1", table_id="tbl1", table_name="Custom",
            field_mapping={
                "title_field": "Custom Title",
                "status_field": "Custom Status",
                "assignee_field": "Owner",
                "github_issue_field": "GH#",
                "last_sync_field": "Synced",
                "description_field": "Notes",
            },
        )
        fields = build_lark_record_fields(
            title="Task", status="Done", body="notes", table_cfg=cfg
        )
        self.assertIn("Custom Title", fields)
        self.assertIn("Custom Status", fields)
        self.assertEqual(fields["Custom Title"], "Task")
        self.assertEqual(fields["Notes"], "notes")


# ===========================================================================
# 3. Member Service
# ===========================================================================

class TestMemberService(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_lark = MagicMock()
        self.mock_github = MagicMock()
        self.svc = MemberService(
            db=self.db,
            lark_service=self.mock_lark,
            github_service=self.mock_github,
        )
        # Register a table for assign_table tests
        table_repo = LarkTableRepository(self.db)
        self.table_cfg = LarkTableConfig(
            app_token="app1", table_id="tbl1", table_name="Frontend Tasks",
        )
        table_repo.register(self.table_cfg)

    def tearDown(self):
        self.db.close()

    def test_create_member_resolves_lark_id(self):
        self.mock_lark.get_user_id_by_email.return_value = "ou_alice"
        m = self.svc.create_member("Alice", "alice@co.com", role="developer")
        self.assertEqual(m.lark_open_id, "ou_alice")
        self.mock_lark.get_user_id_by_email.assert_called_once_with("alice@co.com")

    def test_create_member_without_lark(self):
        svc = MemberService(db=self.db)
        m = svc.create_member("Bob", "bob@co.com")
        self.assertIsNone(m.lark_open_id)
        self.assertEqual(m.role, MemberRole.MEMBER)

    def test_get_member_by_email(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        found = self.svc.get_member("alice@co.com")
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Alice")

    def test_get_member_by_name(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice Chen", "alice@co.com")
        found = self.svc.get_member("Alice Chen")
        self.assertIsNotNone(found)

    def test_list_members_filter(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "a@co.com", role="developer", team="fe")
        self.svc.create_member("Bob", "b@co.com", role="qa", team="qa")
        devs = self.svc.list_members(role="developer")
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0].name, "Alice")

    def test_update_member(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        updated = self.svc.update_member("alice@co.com", role="manager")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.role, MemberRole.MANAGER)

    def test_deactivate_member(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        result = self.svc.deactivate_member("alice@co.com")
        self.assertEqual(result.status.value, "inactive")

    def test_assign_table(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        result = self.svc.assign_table("alice@co.com", "Frontend Tasks")
        self.assertIsNotNone(result)
        self.assertEqual(len(result.lark_tables), 1)
        self.assertEqual(result.lark_tables[0].table_name, "Frontend Tasks")

    def test_assign_table_idempotent(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        self.svc.assign_table("alice@co.com", "Frontend Tasks")
        result = self.svc.assign_table("alice@co.com", "Frontend Tasks")
        self.assertEqual(len(result.lark_tables), 1)

    def test_assign_table_not_found(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        with self.assertRaises(ValueError):
            self.svc.assign_table("alice@co.com", "Nonexistent Table")

    def test_get_member_work(self):
        self.mock_lark.get_user_id_by_email.return_value = "ou_alice"
        m = self.svc.create_member(
            "Alice", "alice@co.com", github_username="alice-gh"
        )

        self.mock_github.list_issues_by_assignee.return_value = [
            {"number": 1, "title": "Issue 1", "state": "open"},
        ]
        self.mock_lark.search_records_by_assignee.return_value = [
            {"record_id": "rec1", "fields": {"Task Name": "Task 1"}},
        ]

        # Assign table so search works
        self.svc.assign_table("alice@co.com", "Frontend Tasks")

        work = self.svc.get_member_work("alice@co.com")
        self.assertIsNotNone(work)
        self.assertEqual(len(work.github_issues), 1)
        self.assertEqual(len(work.lark_records), 1)
        self.assertIn("Alice", work.to_text())

    def test_resolve_lark_ids(self):
        self.mock_lark.get_user_id_by_email.return_value = None
        self.svc.create_member("Alice", "alice@co.com")
        self.svc.create_member("Bob", "bob@co.com")

        self.mock_lark.get_user_ids_by_emails.return_value = {
            "alice@co.com": "ou_alice",
            "bob@co.com": "ou_bob",
        }

        resolved = self.svc.resolve_lark_ids()
        self.assertEqual(resolved["alice@co.com"], "ou_alice")

        alice = self.svc.get_member("alice@co.com")
        self.assertEqual(alice.lark_open_id, "ou_alice")


# ===========================================================================
# 4. Sync Engine
# ===========================================================================

class TestSyncEngine(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.mock_github = MagicMock()
        self.mock_lark = MagicMock()
        self.engine = SyncEngine(
            db=self.db,
            github_service=self.mock_github,
            lark_service=self.mock_lark,
        )
        self.member_repo = MemberRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.mapping_repo = MappingRepository(self.db)
        self.outbox_repo = OutboxRepository(self.db)
        self.table_repo = LarkTableRepository(self.db)

        # Seed a member and table
        self.member = Member(name="Alice", email="alice@co.com")
        self.member_repo.create(self.member)

        self.table_cfg = LarkTableConfig(
            app_token="app1", table_id="tbl1", table_name="Tasks", is_default=True
        )
        self.table_repo.register(self.table_cfg)

    def tearDown(self):
        self.db.close()

    def test_github_create(self):
        task = Task(title="Test task", assignee_member_id=self.member.member_id)
        self.task_repo.create(task)

        self.mock_github.create_issue.return_value = {"number": 55}
        self.mock_github.repo_slug = "owner/repo"

        self.outbox_repo.enqueue("sync_github_create", {
            "task_id": task.task_id, "labels": ["auto"],
        })

        processed = self.engine.process_batch()
        self.assertEqual(processed, 1)
        self.mock_github.create_issue.assert_called_once()

        mapping = self.mapping_repo.get_by_github_issue(55)
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.task_id, task.task_id)

    def test_lark_create(self):
        task = Task(title="Lark task", assignee_member_id=self.member.member_id)
        self.task_repo.create(task)

        self.mock_lark.create_record.return_value = {
            "record": {"record_id": "rec_new"}
        }

        self.outbox_repo.enqueue("sync_lark_create", {"task_id": task.task_id})

        processed = self.engine.process_batch()
        self.assertEqual(processed, 1)
        self.mock_lark.create_record.assert_called_once()

        mapping = self.mapping_repo.get_by_lark_record("rec_new")
        self.assertIsNotNone(mapping)

    def test_github_update(self):
        task = Task(title="Updated", status=TaskStatus.DONE,
                    assignee_member_id=self.member.member_id)
        self.task_repo.create(task)
        self.mapping_repo.upsert_for_task(task.task_id, github_issue_number=10)

        self.mock_github.update_issue.return_value = {"number": 10}

        self.outbox_repo.enqueue("sync_github_update", {"task_id": task.task_id})
        processed = self.engine.process_batch()
        self.assertEqual(processed, 1)

        call_args = self.mock_github.update_issue.call_args
        self.assertEqual(call_args[0][0], 10)
        self.assertEqual(call_args[1]["state"], "closed")

    def test_failed_event_retried(self):
        task = Task(title="Fail task", assignee_member_id=self.member.member_id)
        self.task_repo.create(task)

        self.mock_github.create_issue.side_effect = RuntimeError("API down")
        self.mock_github.repo_slug = "owner/repo"

        self.outbox_repo.enqueue("sync_github_create", {
            "task_id": task.task_id, "labels": ["auto"],
        })

        processed = self.engine.process_batch()
        self.assertEqual(processed, 0)

        row = self.db.fetchone("SELECT * FROM outbox WHERE status = 'failed'")
        self.assertIsNotNone(row)
        self.assertEqual(row["attempts"], 1)

    def test_unknown_event_type(self):
        self.outbox_repo.enqueue("unknown_event", {"data": "x"})
        processed = self.engine.process_batch()
        self.assertEqual(processed, 0)

    def test_convert_issue_to_lark(self):
        task = Task(title="Convert me", assignee_member_id=self.member.member_id)
        self.task_repo.create(task)
        self.mapping_repo.upsert_for_task(task.task_id, github_issue_number=20)

        self.mock_github.get_issue.return_value = {
            "title": "Convert me", "body": "Body", "state": "open", "number": 20,
        }
        self.mock_lark.create_record.return_value = {
            "record": {"record_id": "rec_converted"}
        }

        self.outbox_repo.enqueue("convert_issue_to_lark", {
            "issue_number": 20,
            "task_id": task.task_id,
            "target_table": "Tasks",
        })

        processed = self.engine.process_batch()
        self.assertEqual(processed, 1)

        mapping = self.mapping_repo.get_by_lark_record("rec_converted")
        self.assertIsNotNone(mapping)


if __name__ == "__main__":
    unittest.main()
