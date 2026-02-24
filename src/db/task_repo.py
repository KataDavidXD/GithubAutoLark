"""Repository for the ``tasks`` table — full CRUD with ACID transactions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database
from src.models.task import Task, TaskStatus


class TaskRepository:
    """Single-Responsibility repository for task persistence."""

    def __init__(self, db: Database):
        self._db = db

    # -- Create ----------------------------------------------------------------

    def create(self, task: Task) -> Task:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO tasks
                   (task_id, title, body, status, priority, source,
                    assignee_member_id, labels, target_table)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.title, task.body,
                    task.status.value, task.priority.value, task.source.value,
                    task.assignee_member_id, task.labels_json(),
                    task.target_table,
                ),
            )
        return task

    # -- Read ------------------------------------------------------------------

    def get_by_id(self, task_id: str) -> Optional[Task]:
        row = self._db.fetchone("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        return Task.from_row(row) if row else None

    def get_by_assignee(self, member_id: str, status: Optional[TaskStatus] = None) -> list[Task]:
        if status:
            rows = self._db.fetchall(
                "SELECT * FROM tasks WHERE assignee_member_id = ? AND status = ?",
                (member_id, status.value),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM tasks WHERE assignee_member_id = ?",
                (member_id,),
            )
        return [Task.from_row(r) for r in rows]

    # -- List / Filter ---------------------------------------------------------

    def list_all(
        self,
        status: Optional[TaskStatus] = None,
        assignee_member_id: Optional[str] = None,
        target_table: Optional[str] = None,
    ) -> list[Task]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status.value)
        if assignee_member_id:
            clauses.append("assignee_member_id = ?")
            params.append(assignee_member_id)
        if target_table:
            clauses.append("target_table = ?")
            params.append(target_table)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"SELECT * FROM tasks{where} ORDER BY created_at DESC", tuple(params)
        )
        return [Task.from_row(r) for r in rows]

    # -- Update ----------------------------------------------------------------

    def update(self, task_id: str, **fields: Any) -> Optional[Task]:
        if not fields:
            return self.get_by_id(task_id)

        allowed = {
            "title", "body", "status", "priority", "source",
            "assignee_member_id", "labels", "target_table",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return self.get_by_id(task_id)

        set_parts = [f"{k} = ?" for k in filtered]
        set_parts.append("updated_at = ?")
        values = list(filtered.values())
        values.append(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        values.append(task_id)

        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE tasks SET {', '.join(set_parts)} WHERE task_id = ?",
                tuple(values),
            )
        return self.get_by_id(task_id)

    # -- Delete ----------------------------------------------------------------

    def delete(self, task_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
        return cursor.rowcount > 0
