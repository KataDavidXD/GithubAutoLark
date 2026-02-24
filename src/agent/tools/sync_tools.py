"""Tool functions for the Sync agent."""

from __future__ import annotations

from typing import Any, Optional

from src.db.database import Database
from src.db.outbox_repo import OutboxRepository
from src.db.sync_log_repo import SyncLogRepository
from src.sync.engine import SyncEngine


class SyncTools:
    """Stateful tool collection for sync operations."""

    def __init__(self, db: Database, github_service: Any = None, lark_service: Any = None):
        self._db = db
        self._outbox = OutboxRepository(db)
        self._sync_log = SyncLogRepository(db)
        self._engine = SyncEngine(db, github_service=github_service, lark_service=lark_service)

    def sync_pending(self) -> str:
        """Process all pending outbox events."""
        try:
            count = self._engine.process_batch(limit=50)
            return f"Processed {count} pending sync event(s)."
        except Exception as e:
            return f"Error processing sync: {e}"

    def sync_status(self) -> str:
        """Show current sync status — pending events, recent log entries."""
        pending = self._outbox.get_pending(limit=100)
        recent_logs = self._sync_log.recent(limit=10)

        lines = [f"Pending events: {len(pending)}"]
        for evt in pending[:10]:
            lines.append(f"  [{evt['event_type']}] {evt['status']} (attempts: {evt['attempts']})")

        lines.append(f"\nRecent sync log ({len(recent_logs)} entries):")
        for log in recent_logs:
            lines.append(
                f"  [{log['direction']}] {log['subject']} {log['subject_id'] or ''} "
                f"-> {log['status']}: {log.get('message', '')}"
            )

        return "\n".join(lines)

    def retry_failed(self) -> str:
        """Retry failed outbox events."""
        retried = self._outbox.retry_failed(limit=50)
        return f"Moved {len(retried)} failed event(s) back to pending."
