"""Repository for the ``sync_log`` and ``sync_state`` tables."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database


class SyncLogRepository:
    """Audit-trail repository for sync operations."""

    def __init__(self, db: Database):
        self._db = db

    def log(
        self,
        direction: str,
        subject: str,
        subject_id: Optional[str],
        status: str,
        message: Optional[str] = None,
    ) -> str:
        log_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO sync_log
                   (id, direction, subject, subject_id, status, message)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (log_id, direction, subject, subject_id, status, message),
            )
        return log_id

    def get_by_subject(self, subject: str, subject_id: Optional[str] = None) -> list[dict[str, Any]]:
        if subject_id:
            return self._db.fetchall(
                "SELECT * FROM sync_log WHERE subject = ? AND subject_id = ? ORDER BY created_at DESC",
                (subject, subject_id),
            )
        return self._db.fetchall(
            "SELECT * FROM sync_log WHERE subject = ? ORDER BY created_at DESC",
            (subject,),
        )

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._db.fetchall(
            "SELECT * FROM sync_log ORDER BY created_at DESC LIMIT ?", (limit,)
        )


class SyncStateRepository:
    """Key-value store for sync cursors and state."""

    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str) -> Optional[str]:
        row = self._db.fetchone("SELECT value FROM sync_state WHERE key = ?", (key,))
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO sync_state (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE
                   SET value = excluded.value, updated_at = excluded.updated_at""",
                (key, value, now),
            )
