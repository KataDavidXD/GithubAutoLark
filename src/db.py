"""
Database module - SQLite with ACID transactions.

Schema:
- employees: email -> open_id mapping
- tasks: local task records
- mappings: task_id -> github_issue_number / lark_record_id
- outbox: pending external API calls for eventual consistency
- sync_log: audit trail of sync operations
- sync_state: polling cursors and state
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional

from src.config import get_db_path


# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS employees (
    email TEXT PRIMARY KEY,
    lark_open_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ToDo',
    source TEXT DEFAULT 'manual',
    assignee_email TEXT,
    assignee_open_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mappings (
    task_id TEXT PRIMARY KEY,
    github_issue_number INTEGER,
    lark_record_id TEXT,
    lark_app_token TEXT,
    lark_table_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (task_id) REFERENCES tasks(task_id)
);

CREATE TABLE IF NOT EXISTS outbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_log (
    id TEXT PRIMARY KEY,
    direction TEXT NOT NULL,
    subject TEXT NOT NULL,
    subject_id TEXT,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outbox_status ON outbox(status);
CREATE INDEX IF NOT EXISTS idx_sync_log_subject ON sync_log(subject, subject_id);
"""


# ---------------------------------------------------------------------------
# Database Connection
# ---------------------------------------------------------------------------
@dataclass
class Database:
    """
    SQLite database wrapper with transaction support.
    
    Usage:
        db = Database()
        db.init()
        with db.transaction() as conn:
            conn.execute("INSERT INTO tasks ...")
    """
    
    path: Path
    _conn: Optional[sqlite3.Connection] = None
    
    def __init__(self, path: Optional[Path] = None):
        self.path = path or get_db_path()
    
    def _ensure_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
    
    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            # Enable foreign keys
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn
    
    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def init(self) -> None:
        """Initialize the database schema."""
        conn = self._get_connection()
        conn.executescript(_SCHEMA)
        conn.commit()
    
    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for ACID transactions.
        
        Commits on success, rolls back on exception.
        """
        conn = self._get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    
    # -------------------------------------------------------------------------
    # Employee Operations
    # -------------------------------------------------------------------------
    
    def upsert_employee(self, email: str, lark_open_id: Optional[str] = None) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO employees (email, lark_open_id, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    lark_open_id = COALESCE(excluded.lark_open_id, lark_open_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (email, lark_open_id),
            )
    
    def get_employee(self, email: str) -> Optional[dict[str, Any]]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM employees WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None
    
    # -------------------------------------------------------------------------
    # Task Operations
    # -------------------------------------------------------------------------
    
    def create_task(
        self,
        title: str,
        body: str = "",
        status: str = "ToDo",
        source: str = "manual",
        assignee_email: Optional[str] = None,
        assignee_open_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> str:
        """Create a new task and return its task_id."""
        tid = task_id or str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO tasks (task_id, title, body, status, source, assignee_email, assignee_open_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tid, title, body, status, source, assignee_email, assignee_open_id),
            )
        return tid
    
    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    
    def update_task(self, task_id: str, **fields) -> None:
        if not fields:
            return
        
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [task_id]
        
        with self.transaction() as conn:
            conn.execute(
                f"UPDATE tasks SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE task_id = ?",
                values,
            )
    
    def list_tasks(self, status: Optional[str] = None) -> list[dict[str, Any]]:
        conn = self._get_connection()
        if status:
            rows = conn.execute("SELECT * FROM tasks WHERE status = ?", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM tasks").fetchall()
        return [dict(r) for r in rows]
    
    # -------------------------------------------------------------------------
    # Mapping Operations
    # -------------------------------------------------------------------------
    
    def upsert_mapping(
        self,
        task_id: str,
        github_issue_number: Optional[int] = None,
        lark_record_id: Optional[str] = None,
        lark_app_token: Optional[str] = None,
        lark_table_id: Optional[str] = None,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO mappings (task_id, github_issue_number, lark_record_id, lark_app_token, lark_table_id, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(task_id) DO UPDATE SET
                    github_issue_number = COALESCE(excluded.github_issue_number, github_issue_number),
                    lark_record_id = COALESCE(excluded.lark_record_id, lark_record_id),
                    lark_app_token = COALESCE(excluded.lark_app_token, lark_app_token),
                    lark_table_id = COALESCE(excluded.lark_table_id, lark_table_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, github_issue_number, lark_record_id, lark_app_token, lark_table_id),
            )
    
    def get_mapping(self, task_id: str) -> Optional[dict[str, Any]]:
        conn = self._get_connection()
        row = conn.execute("SELECT * FROM mappings WHERE task_id = ?", (task_id,)).fetchone()
        return dict(row) if row else None
    
    def get_mapping_by_github_issue(self, issue_number: int) -> Optional[dict[str, Any]]:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM mappings WHERE github_issue_number = ?", (issue_number,)
        ).fetchone()
        return dict(row) if row else None
    
    def get_mapping_by_lark_record(self, record_id: str) -> Optional[dict[str, Any]]:
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM mappings WHERE lark_record_id = ?", (record_id,)
        ).fetchone()
        return dict(row) if row else None
    
    # -------------------------------------------------------------------------
    # Outbox Operations (for eventual consistency)
    # -------------------------------------------------------------------------
    
    def enqueue_event(self, event_type: str, payload: dict[str, Any]) -> str:
        """Add an event to the outbox."""
        event_id = str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO outbox (event_id, event_type, payload_json) VALUES (?, ?, ?)",
                (event_id, event_type, json.dumps(payload)),
            )
        return event_id
    
    def get_pending_events(self, limit: int = 10) -> list[dict[str, Any]]:
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM outbox WHERE status = 'pending' ORDER BY created_at LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    
    def mark_event_sent(self, event_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                "UPDATE outbox SET status = 'sent', updated_at = CURRENT_TIMESTAMP WHERE event_id = ?",
                (event_id,),
            )
    
    def mark_event_failed(self, event_id: str, error: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                UPDATE outbox SET 
                    status = 'failed',
                    attempts = attempts + 1,
                    last_error = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE event_id = ?
                """,
                (error, event_id),
            )
    
    # -------------------------------------------------------------------------
    # Sync Log Operations
    # -------------------------------------------------------------------------
    
    def log_sync(
        self,
        direction: str,
        subject: str,
        subject_id: Optional[str],
        status: str,
        message: Optional[str] = None,
    ) -> str:
        log_id = str(uuid.uuid4())
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO sync_log (id, direction, subject, subject_id, status, message) VALUES (?, ?, ?, ?, ?, ?)",
                (log_id, direction, subject, subject_id, status, message),
            )
        return log_id
    
    # -------------------------------------------------------------------------
    # Sync State Operations
    # -------------------------------------------------------------------------
    
    def get_state(self, key: str) -> Optional[str]:
        conn = self._get_connection()
        row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None
    
    def set_state(self, key: str, value: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT INTO sync_state (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, value),
            )


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------
_default_db: Optional[Database] = None


def get_db() -> Database:
    global _default_db
    if _default_db is None:
        _default_db = Database()
        _default_db.init()
    return _default_db


if __name__ == "__main__":
    print("Initializing database...")
    db = Database()
    db.init()
    print(f"Database created at: {db.path}")
    
    # Quick test
    task_id = db.create_task("Test task", body="Testing DB", status="ToDo", source="manual")
    print(f"Created task: {task_id}")
    
    task = db.get_task(task_id)
    print(f"Retrieved: {task}")
