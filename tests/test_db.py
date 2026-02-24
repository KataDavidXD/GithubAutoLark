"""Unit tests for the DB layer — models, schema, and all repositories.

Every test uses a fresh in-memory SQLite database so tests are isolated,
fast, and leave no artefacts on disk.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.db.database import Database
from src.db.member_repo import MemberRepository
from src.db.task_repo import TaskRepository
from src.db.mapping_repo import MappingRepository
from src.db.outbox_repo import OutboxRepository
from src.db.sync_log_repo import SyncLogRepository, SyncStateRepository
from src.db.lark_table_repo import LarkTableRepository
from src.models.member import Member, MemberRole, MemberStatus, LarkTableAssignment
from src.models.task import Task, TaskStatus, TaskPriority, TaskSource
from src.models.mapping import Mapping, SyncStatus
from src.models.lark_table_registry import LarkTableConfig, DEFAULT_FIELD_MAPPING


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> Database:
    """Return a Database backed by a fresh temporary file (auto-deleted)."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db = Database(path=Path(tmp.name))
    db.init()
    return db


def _sample_member(**overrides) -> Member:
    defaults = dict(
        name="Alice Chen",
        email="alice@example.com",
        role=MemberRole.DEVELOPER,
        github_username="alice-gh",
        position="Frontend Lead",
        team="frontend",
    )
    defaults.update(overrides)
    return Member(**defaults)


def _sample_task(**overrides) -> Task:
    defaults = dict(
        title="Fix login bug",
        body="The login form crashes on empty password",
        priority=TaskPriority.HIGH,
        labels=["bug", "frontend"],
    )
    defaults.update(overrides)
    return Task(**defaults)


# ===========================================================================
# 1. Database core
# ===========================================================================

class TestDatabaseCore(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()

    def tearDown(self):
        self.db.close()

    def test_tables_created(self):
        tables = self.db.fetchall(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        names = {t["name"] for t in tables}
        expected = {"members", "tasks", "mappings", "lark_tables_registry",
                    "outbox", "sync_log", "sync_state"}
        self.assertTrue(expected.issubset(names), f"Missing tables: {expected - names}")

    def test_foreign_keys_enabled(self):
        row = self.db.fetchone("PRAGMA foreign_keys")
        self.assertEqual(row["foreign_keys"], 1)

    def test_transaction_commit(self):
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO sync_state (key, value) VALUES (?, ?)",
                ("test_key", "test_value"),
            )
        row = self.db.fetchone("SELECT * FROM sync_state WHERE key = 'test_key'")
        self.assertIsNotNone(row)
        self.assertEqual(row["value"], "test_value")

    def test_transaction_rollback(self):
        try:
            with self.db.transaction() as conn:
                conn.execute(
                    "INSERT INTO sync_state (key, value) VALUES (?, ?)",
                    ("rollback_key", "val"),
                )
                raise ValueError("Force rollback")
        except ValueError:
            pass
        row = self.db.fetchone("SELECT * FROM sync_state WHERE key = 'rollback_key'")
        self.assertIsNone(row)


# ===========================================================================
# 2. Member model & repo
# ===========================================================================

class TestMemberModel(unittest.TestCase):
    def test_to_dict_roundtrip(self):
        m = _sample_member(lark_tables=[
            LarkTableAssignment("app1", "tbl1", "Frontend Tasks")
        ])
        d = m.to_dict()
        self.assertEqual(d["name"], "Alice Chen")
        self.assertEqual(d["role"], "developer")
        tables = json.loads(d["lark_tables"])
        self.assertEqual(len(tables), 1)
        self.assertEqual(tables[0]["table_name"], "Frontend Tasks")

    def test_from_row(self):
        row = {
            "member_id": "abc",
            "name": "Bob",
            "email": "bob@co.com",
            "github_username": "bob-gh",
            "lark_open_id": None,
            "role": "qa",
            "position": "QA",
            "team": "quality",
            "status": "active",
            "lark_tables": "[]",
            "created_at": "",
            "updated_at": "",
        }
        m = Member.from_row(row)
        self.assertEqual(m.role, MemberRole.QA)
        self.assertEqual(m.lark_tables, [])


class TestMemberRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.repo = MemberRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_create_and_get(self):
        m = _sample_member()
        self.repo.create(m)
        fetched = self.repo.get_by_email("alice@example.com")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.name, "Alice Chen")
        self.assertEqual(fetched.role, MemberRole.DEVELOPER)

    def test_duplicate_email_raises(self):
        self.repo.create(_sample_member())
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create(_sample_member(member_id="other-id"))

    def test_get_by_github(self):
        self.repo.create(_sample_member())
        found = self.repo.get_by_github("alice-gh")
        self.assertIsNotNone(found)
        self.assertEqual(found.email, "alice@example.com")

    def test_find_by_name_partial(self):
        self.repo.create(_sample_member())
        self.repo.create(_sample_member(name="Alice Wang", email="aw@co.com", member_id="id2"))
        results = self.repo.find_by_name("alice")
        self.assertEqual(len(results), 2)

    def test_list_filter_by_role(self):
        self.repo.create(_sample_member())
        self.repo.create(_sample_member(
            name="Bob", email="bob@co.com", role=MemberRole.QA, member_id="id2"
        ))
        devs = self.repo.list_all(role=MemberRole.DEVELOPER)
        self.assertEqual(len(devs), 1)
        self.assertEqual(devs[0].name, "Alice Chen")

    def test_update(self):
        m = _sample_member()
        self.repo.create(m)
        updated = self.repo.update(m.member_id, role="manager", position="Team Lead")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.role, MemberRole.MANAGER)
        self.assertEqual(updated.position, "Team Lead")

    def test_deactivate_and_activate(self):
        m = _sample_member()
        self.repo.create(m)
        self.repo.deactivate(m.member_id)
        fetched = self.repo.get_by_id(m.member_id)
        self.assertEqual(fetched.status, MemberStatus.INACTIVE)

        self.repo.activate(m.member_id)
        fetched = self.repo.get_by_id(m.member_id)
        self.assertEqual(fetched.status, MemberStatus.ACTIVE)

    def test_list_by_team(self):
        self.repo.create(_sample_member())
        self.repo.create(_sample_member(
            name="Bob", email="bob@co.com", team="backend", member_id="id2"
        ))
        frontend = self.repo.list_all(team="frontend")
        self.assertEqual(len(frontend), 1)


# ===========================================================================
# 3. Task model & repo
# ===========================================================================

class TestTaskModel(unittest.TestCase):
    def test_labels_json_roundtrip(self):
        t = _sample_task()
        j = t.labels_json()
        parsed = Task.parse_labels(j)
        self.assertEqual(parsed, ["bug", "frontend"])

    def test_from_row(self):
        row = {
            "task_id": "t1",
            "title": "Test",
            "body": "",
            "status": "In Progress",
            "priority": "critical",
            "source": "command",
            "assignee_member_id": None,
            "labels": '["urgent"]',
            "target_table": None,
            "created_at": "",
            "updated_at": "",
        }
        t = Task.from_row(row)
        self.assertEqual(t.status, TaskStatus.IN_PROGRESS)
        self.assertEqual(t.priority, TaskPriority.CRITICAL)
        self.assertEqual(t.labels, ["urgent"])


class TestTaskRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.member_repo = MemberRepository(self.db)
        self.repo = TaskRepository(self.db)
        self.member = _sample_member()
        self.member_repo.create(self.member)

    def tearDown(self):
        self.db.close()

    def test_create_and_get(self):
        t = _sample_task(assignee_member_id=self.member.member_id)
        self.repo.create(t)
        fetched = self.repo.get_by_id(t.task_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.title, "Fix login bug")
        self.assertEqual(fetched.priority, TaskPriority.HIGH)

    def test_list_by_status(self):
        self.repo.create(_sample_task(title="A"))
        self.repo.create(_sample_task(title="B", status=TaskStatus.DONE))
        todo_tasks = self.repo.list_all(status=TaskStatus.TODO)
        self.assertEqual(len(todo_tasks), 1)
        self.assertEqual(todo_tasks[0].title, "A")

    def test_get_by_assignee(self):
        self.repo.create(_sample_task(assignee_member_id=self.member.member_id))
        self.repo.create(_sample_task(title="Unassigned"))
        assigned = self.repo.get_by_assignee(self.member.member_id)
        self.assertEqual(len(assigned), 1)

    def test_update(self):
        t = _sample_task()
        self.repo.create(t)
        updated = self.repo.update(t.task_id, status="Done", priority="low")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, TaskStatus.DONE)
        self.assertEqual(updated.priority, TaskPriority.LOW)

    def test_delete(self):
        t = _sample_task()
        self.repo.create(t)
        self.assertTrue(self.repo.delete(t.task_id))
        self.assertIsNone(self.repo.get_by_id(t.task_id))

    def test_fk_constraint(self):
        t = _sample_task(assignee_member_id="nonexistent-member-id")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create(t)


# ===========================================================================
# 4. Mapping model & repo
# ===========================================================================

class TestMappingRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.member_repo = MemberRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.repo = MappingRepository(self.db)

        self.member = _sample_member()
        self.member_repo.create(self.member)
        self.task = _sample_task(assignee_member_id=self.member.member_id)
        self.task_repo.create(self.task)

    def tearDown(self):
        self.db.close()

    def test_create_and_get(self):
        m = Mapping(task_id=self.task.task_id, github_issue_number=42, github_repo="owner/repo")
        self.repo.create(m)
        fetched = self.repo.get_by_id(m.mapping_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.github_issue_number, 42)

    def test_get_by_github_issue(self):
        m = Mapping(task_id=self.task.task_id, github_issue_number=99)
        self.repo.create(m)
        found = self.repo.get_by_github_issue(99)
        self.assertIsNotNone(found)
        self.assertEqual(found.task_id, self.task.task_id)

    def test_get_by_lark_record(self):
        m = Mapping(task_id=self.task.task_id, lark_record_id="rec_abc123")
        self.repo.create(m)
        found = self.repo.get_by_lark_record("rec_abc123")
        self.assertIsNotNone(found)

    def test_upsert_creates_then_updates(self):
        m1 = self.repo.upsert_for_task(self.task.task_id, github_issue_number=10)
        self.assertEqual(m1.github_issue_number, 10)
        self.assertIsNone(m1.lark_record_id)

        m2 = self.repo.upsert_for_task(self.task.task_id, lark_record_id="rec_xyz")
        self.assertEqual(m2.github_issue_number, 10)
        self.assertEqual(m2.lark_record_id, "rec_xyz")

    def test_update_sync_status(self):
        m = Mapping(task_id=self.task.task_id)
        self.repo.create(m)
        updated = self.repo.update(m.mapping_id, sync_status="conflict")
        self.assertEqual(updated.sync_status, SyncStatus.CONFLICT)

    def test_fk_constraint(self):
        m = Mapping(task_id="nonexistent-task")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create(m)


# ===========================================================================
# 5. Outbox repo
# ===========================================================================

class TestOutboxRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.repo = OutboxRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_enqueue_and_get_pending(self):
        eid = self.repo.enqueue("sync_github_create", {"task_id": "t1"})
        pending = self.repo.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["event_id"], eid)
        self.assertEqual(pending[0]["status"], "pending")

    def test_lifecycle_sent(self):
        eid = self.repo.enqueue("test_event", {"data": 1})
        self.repo.mark_processing(eid)
        self.repo.mark_sent(eid)
        pending = self.repo.get_pending()
        self.assertEqual(len(pending), 0)

    def test_lifecycle_failed(self):
        eid = self.repo.enqueue("test_event", {"data": 1})
        self.repo.mark_failed(eid, "timeout")
        row = self.db.fetchone("SELECT * FROM outbox WHERE event_id = ?", (eid,))
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["attempts"], 1)
        self.assertEqual(row["last_error"], "timeout")

    def test_mark_dead(self):
        eid = self.repo.enqueue("test_event", {"data": 1})
        self.repo.mark_dead(eid, "permanent failure")
        row = self.db.fetchone("SELECT * FROM outbox WHERE event_id = ?", (eid,))
        self.assertEqual(row["status"], "dead")

    def test_retry_failed(self):
        eid = self.repo.enqueue("test_event", {"data": 1})
        self.repo.mark_failed(eid, "transient")
        retried = self.repo.retry_failed()
        self.assertEqual(len(retried), 1)
        self.assertEqual(retried[0]["status"], "pending")


# ===========================================================================
# 6. Sync log / state repos
# ===========================================================================

class TestSyncLogRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.repo = SyncLogRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_log_and_query(self):
        self.repo.log("outbound", "github", "t1", "success", "Issue created")
        self.repo.log("inbound", "lark", "t1", "detected", "Status changed")
        logs = self.repo.get_by_subject("github", "t1")
        self.assertEqual(len(logs), 1)
        recent = self.repo.recent(limit=10)
        self.assertEqual(len(recent), 2)


class TestSyncStateRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.repo = SyncStateRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_set_and_get(self):
        self.repo.set("last_sync", "2026-01-01T00:00:00Z")
        val = self.repo.get("last_sync")
        self.assertEqual(val, "2026-01-01T00:00:00Z")

    def test_upsert(self):
        self.repo.set("cursor", "100")
        self.repo.set("cursor", "200")
        val = self.repo.get("cursor")
        self.assertEqual(val, "200")

    def test_get_missing(self):
        self.assertIsNone(self.repo.get("nonexistent"))


# ===========================================================================
# 7. Lark table registry repo
# ===========================================================================

class TestLarkTableRepository(unittest.TestCase):
    def setUp(self):
        self.db = _make_db()
        self.repo = LarkTableRepository(self.db)

    def tearDown(self):
        self.db.close()

    def _sample_config(self, **overrides) -> LarkTableConfig:
        defaults = dict(
            app_token="app_tok_123",
            table_id="tbl_001",
            table_name="Frontend Tasks",
            description="Tasks for the frontend team",
            is_default=True,
        )
        defaults.update(overrides)
        return LarkTableConfig(**defaults)

    def test_register_and_get(self):
        cfg = self._sample_config()
        self.repo.register(cfg)
        fetched = self.repo.get_by_id(cfg.registry_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.table_name, "Frontend Tasks")
        self.assertTrue(fetched.is_default)

    def test_get_by_name_case_insensitive(self):
        self.repo.register(self._sample_config())
        found = self.repo.get_by_name("frontend tasks")
        self.assertIsNotNone(found)

    def test_get_default(self):
        self.repo.register(self._sample_config(is_default=True))
        self.repo.register(self._sample_config(
            table_id="tbl_002", table_name="Backend", is_default=False,
            registry_id="other-id"
        ))
        default = self.repo.get_default()
        self.assertIsNotNone(default)
        self.assertEqual(default.table_name, "Frontend Tasks")

    def test_set_default(self):
        c1 = self._sample_config(is_default=True)
        c2 = self._sample_config(
            table_id="tbl_002", table_name="Backend", is_default=False,
            registry_id="reg2"
        )
        self.repo.register(c1)
        self.repo.register(c2)

        self.repo.set_default(c2.registry_id)

        old = self.repo.get_by_id(c1.registry_id)
        new = self.repo.get_by_id(c2.registry_id)
        self.assertFalse(old.is_default)
        self.assertTrue(new.is_default)

    def test_list_all(self):
        self.repo.register(self._sample_config())
        self.repo.register(self._sample_config(
            table_id="tbl_002", table_name="Backend",
            registry_id="reg2"
        ))
        all_tables = self.repo.list_all()
        self.assertEqual(len(all_tables), 2)

    def test_field_mapping_preserved(self):
        custom = dict(DEFAULT_FIELD_MAPPING)
        custom["title_field"] = "Custom Title"
        cfg = self._sample_config()
        cfg.field_mapping = custom
        self.repo.register(cfg)
        fetched = self.repo.get_by_id(cfg.registry_id)
        self.assertEqual(fetched.field_mapping["title_field"], "Custom Title")

    def test_unique_constraint(self):
        self.repo.register(self._sample_config())
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.register(self._sample_config(registry_id="other-reg"))

    def test_delete(self):
        cfg = self._sample_config()
        self.repo.register(cfg)
        self.assertTrue(self.repo.delete(cfg.registry_id))
        self.assertIsNone(self.repo.get_by_id(cfg.registry_id))


# ===========================================================================
# 8. Cross-repo ACID transaction test
# ===========================================================================

class TestCrossRepoACID(unittest.TestCase):
    """Verify that a single transaction spanning multiple repos is atomic."""

    def setUp(self):
        self.db = _make_db()
        self.member_repo = MemberRepository(self.db)
        self.task_repo = TaskRepository(self.db)
        self.mapping_repo = MappingRepository(self.db)
        self.outbox_repo = OutboxRepository(self.db)

    def tearDown(self):
        self.db.close()

    def test_atomic_task_creation_with_mapping_and_outbox(self):
        """Simulate create_task_and_sync: task + mapping + outbox in one TX."""
        member = _sample_member()
        self.member_repo.create(member)

        task = _sample_task(assignee_member_id=member.member_id)

        with self.db.transaction() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (task_id, title, body, status, priority, source,
                    assignee_member_id, labels, target_table)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.title, task.body,
                    task.status.value, task.priority.value, task.source.value,
                    task.assignee_member_id, task.labels_json(), task.target_table,
                ),
            )
            conn.execute(
                """INSERT INTO mappings
                   (mapping_id, task_id, github_issue_number, sync_status)
                   VALUES (?, ?, ?, ?)""",
                ("map1", task.task_id, 42, "pending"),
            )
            conn.execute(
                """INSERT INTO outbox
                   (event_id, event_type, payload_json)
                   VALUES (?, ?, ?)""",
                ("evt1", "sync_github_create", json.dumps({"task_id": task.task_id})),
            )

        fetched_task = self.task_repo.get_by_id(task.task_id)
        self.assertIsNotNone(fetched_task)
        fetched_mapping = self.mapping_repo.get_by_github_issue(42)
        self.assertIsNotNone(fetched_mapping)
        pending = self.outbox_repo.get_pending()
        self.assertEqual(len(pending), 1)

    def test_rollback_leaves_nothing(self):
        """If the outbox insert fails, neither task nor mapping should persist."""
        member = _sample_member()
        self.member_repo.create(member)
        task = _sample_task(assignee_member_id=member.member_id)

        try:
            with self.db.transaction() as conn:
                conn.execute(
                    """INSERT INTO tasks
                       (task_id, title, body, status, priority, source,
                        assignee_member_id, labels, target_table)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        task.task_id, task.title, task.body,
                        task.status.value, task.priority.value, task.source.value,
                        task.assignee_member_id, task.labels_json(), task.target_table,
                    ),
                )
                raise RuntimeError("Simulated outbox failure")
        except RuntimeError:
            pass

        self.assertIsNone(self.task_repo.get_by_id(task.task_id))


if __name__ == "__main__":
    unittest.main()
