"""Repository for the ``outbox`` table — event queue for eventual consistency."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.db.database import Database


class OutboxRepository:
    """Single-Responsibility repository for outbox event persistence."""

    def __init__(self, db: Database):
        self._db = db

    def enqueue(self, event_type: str, payload: dict[str, Any], max_attempts: int = 5) -> str:
        event_id = str(uuid.uuid4())
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO outbox
                   (event_id, event_type, payload_json, max_attempts)
                   VALUES (?, ?, ?, ?)""",
                (event_id, event_type, json.dumps(payload), max_attempts),
            )
        return event_id

    def get_pending(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._db.fetchall(
            "SELECT * FROM outbox WHERE status = 'pending' ORDER BY created_at LIMIT ?",
            (limit,),
        )

    def mark_processing(self, event_id: str) -> None:
        self._set_status(event_id, "processing")

    def mark_sent(self, event_id: str) -> None:
        self._set_status(event_id, "sent")

    def mark_failed(self, event_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                """UPDATE outbox SET
                       status = 'failed', attempts = attempts + 1,
                       last_error = ?, updated_at = ?
                   WHERE event_id = ?""",
                (error, now, event_id),
            )

    def mark_dead(self, event_id: str, error: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                """UPDATE outbox SET
                       status = 'dead', attempts = attempts + 1,
                       last_error = ?, updated_at = ?
                   WHERE event_id = ?""",
                (error, now, event_id),
            )

    def retry_failed(self, limit: int = 10) -> list[dict[str, Any]]:
        """Move eligible *failed* events back to *pending*."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                """UPDATE outbox SET status = 'pending', updated_at = ?
                   WHERE status = 'failed' AND attempts < max_attempts""",
                (now,),
            )
        return self.get_pending(limit)

    # -- internal --------------------------------------------------------------

    def _set_status(self, event_id: str, status: str) -> None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE outbox SET status = ?, updated_at = ? WHERE event_id = ?",
                (status, now, event_id),
            )
