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
                    assignee_member_id, labels, target_table, due_date, progress)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task.task_id, task.title, task.body,
                    task.status.value, task.priority.value, task.source.value,
                    task.assignee_member_id, task.labels_json(),
                    task.target_table, task.due_date, task.progress,
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
        due_before: Optional[str] = None,
        overdue_only: bool = False,
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
        if due_before:
            clauses.append("due_date IS NOT NULL AND due_date <= ?")
            params.append(due_before)
        if overdue_only:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            clauses.append("due_date IS NOT NULL AND due_date < ? AND status != 'Done'")
            params.append(now)

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"SELECT * FROM tasks{where} ORDER BY due_date ASC NULLS LAST, created_at DESC", tuple(params)
        )
        return [Task.from_row(r) for r in rows]
    
    def get_overdue(self) -> list[Task]:
        """Get all overdue tasks (past due_date and not Done)."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rows = self._db.fetchall(
            """SELECT * FROM tasks 
               WHERE due_date IS NOT NULL AND due_date < ? AND status != 'Done'
               ORDER BY due_date ASC""",
            (now,),
        )
        return [Task.from_row(r) for r in rows]
    
    def get_by_progress_range(self, min_progress: int = 0, max_progress: int = 100) -> list[Task]:
        """Get tasks within a progress range."""
        rows = self._db.fetchall(
            """SELECT * FROM tasks 
               WHERE progress >= ? AND progress <= ?
               ORDER BY progress DESC, created_at DESC""",
            (min_progress, max_progress),
        )
        return [Task.from_row(r) for r in rows]

    # -- Update ----------------------------------------------------------------

    def update(self, task_id: str, **fields: Any) -> Optional[Task]:
        import json
        if not fields:
            return self.get_by_id(task_id)

        allowed = {
            "title", "body", "status", "priority", "source",
            "assignee_member_id", "labels", "target_table", "due_date", "progress",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return self.get_by_id(task_id)

        # Convert labels list to JSON string
        if "labels" in filtered and isinstance(filtered["labels"], list):
            filtered["labels"] = json.dumps(filtered["labels"])

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
