"""Repository for the ``mappings`` table — full CRUD with ACID transactions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database
from src.models.mapping import Mapping, SyncStatus


class MappingRepository:
    """Single-Responsibility repository for task↔remote mapping persistence."""

    def __init__(self, db: Database):
        self._db = db

    # -- Create ----------------------------------------------------------------

    def create(self, mapping: Mapping) -> Mapping:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO mappings
                   (mapping_id, task_id, github_issue_number, github_repo,
                    lark_record_id, lark_app_token, lark_table_id,
                    field_mapping, sync_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    mapping.mapping_id, mapping.task_id,
                    mapping.github_issue_number, mapping.github_repo,
                    mapping.lark_record_id, mapping.lark_app_token,
                    mapping.lark_table_id, mapping.field_mapping_json(),
                    mapping.sync_status.value,
                ),
            )
        return mapping

    # -- Read ------------------------------------------------------------------

    def get_by_id(self, mapping_id: str) -> Optional[Mapping]:
        row = self._db.fetchone("SELECT * FROM mappings WHERE mapping_id = ?", (mapping_id,))
        return Mapping.from_row(row) if row else None

    def get_by_task(self, task_id: str) -> list[Mapping]:
        rows = self._db.fetchall("SELECT * FROM mappings WHERE task_id = ?", (task_id,))
        return [Mapping.from_row(r) for r in rows]

    def get_by_github_issue(self, issue_number: int, repo: Optional[str] = None) -> Optional[Mapping]:
        if repo:
            row = self._db.fetchone(
                "SELECT * FROM mappings WHERE github_issue_number = ? AND github_repo = ?",
                (issue_number, repo),
            )
        else:
            row = self._db.fetchone(
                "SELECT * FROM mappings WHERE github_issue_number = ?",
                (issue_number,),
            )
        return Mapping.from_row(row) if row else None

    def get_by_lark_record(self, record_id: str) -> Optional[Mapping]:
        row = self._db.fetchone(
            "SELECT * FROM mappings WHERE lark_record_id = ?", (record_id,)
        )
        return Mapping.from_row(row) if row else None

    # -- Update ----------------------------------------------------------------

    def update(self, mapping_id: str, **fields: Any) -> Optional[Mapping]:
        if not fields:
            return self.get_by_id(mapping_id)

        allowed = {
            "github_issue_number", "github_repo",
            "lark_record_id", "lark_app_token", "lark_table_id",
            "field_mapping", "sync_status",
        }
        filtered = {k: v for k, v in fields.items() if k in allowed}
        if not filtered:
            return self.get_by_id(mapping_id)

        set_parts = [f"{k} = ?" for k in filtered]
        set_parts.append("updated_at = ?")
        values = list(filtered.values())
        values.append(datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        values.append(mapping_id)

        with self._db.transaction() as conn:
            conn.execute(
                f"UPDATE mappings SET {', '.join(set_parts)} WHERE mapping_id = ?",
                tuple(values),
            )
        return self.get_by_id(mapping_id)

    def upsert_for_task(
        self,
        task_id: str,
        *,
        github_issue_number: Optional[int] = None,
        github_repo: Optional[str] = None,
        lark_record_id: Optional[str] = None,
        lark_app_token: Optional[str] = None,
        lark_table_id: Optional[str] = None,
    ) -> Mapping:
        """Create-or-update a mapping for *task_id*.

        If a mapping already exists for the task, merge non-None values.
        """
        existing = self.get_by_task(task_id)
        if existing:
            m = existing[0]
            updates: dict[str, Any] = {}
            if github_issue_number is not None:
                updates["github_issue_number"] = github_issue_number
            if github_repo is not None:
                updates["github_repo"] = github_repo
            if lark_record_id is not None:
                updates["lark_record_id"] = lark_record_id
            if lark_app_token is not None:
                updates["lark_app_token"] = lark_app_token
            if lark_table_id is not None:
                updates["lark_table_id"] = lark_table_id
            if updates:
                return self.update(m.mapping_id, **updates)  # type: ignore[return-value]
            return m

        new = Mapping(
            task_id=task_id,
            github_issue_number=github_issue_number,
            github_repo=github_repo,
            lark_record_id=lark_record_id,
            lark_app_token=lark_app_token,
            lark_table_id=lark_table_id,
        )
        return self.create(new)

    # -- Delete ----------------------------------------------------------------

    def delete(self, mapping_id: str) -> bool:
        with self._db.transaction() as conn:
            cursor = conn.execute("DELETE FROM mappings WHERE mapping_id = ?", (mapping_id,))
        return cursor.rowcount > 0
