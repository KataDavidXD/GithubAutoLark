"""Core database connection with ACID transaction support."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

from src.db.schema import SCHEMA_DDL


class Database:
    """
    SQLite database wrapper with explicit ACID transaction support.

    Implements the Unit-of-Work pattern: every mutation goes through
    ``transaction()``, which commits on success and rolls back on failure.
    """

    def __init__(self, path: Optional[Path | str] = None):
        from src.config import get_db_path
        if path is None:
            self.path: Path = get_db_path()
        elif isinstance(path, str):
            self.path = Path(path)
        else:
            self.path = path
        self._conn: Optional[sqlite3.Connection] = None

    # -- connection lifecycle --------------------------------------------------

    def _ensure_dir(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._ensure_dir()
            self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def init(self) -> None:
        """Create all tables (idempotent)."""
        conn = self.connection()
        conn.executescript(SCHEMA_DDL)
        conn.commit()

    # -- transaction helpers ---------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """ACID transaction: commits on success, rolls back on exception."""
        conn = self.connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # -- low-level query helpers -----------------------------------------------

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self.connection().execute(sql, params)

    def fetchone(self, sql: str, params: tuple = ()) -> Optional[dict[str, Any]]:
        row = self.connection().execute(sql, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        rows = self.connection().execute(sql, params).fetchall()
        return [dict(r) for r in rows]


# -- module singleton ----------------------------------------------------------

_default_db: Optional[Database] = None


def get_db(path: Optional[Path] = None) -> Database:
    """Return (and lazily initialise) the module-level Database singleton."""
    global _default_db
    if _default_db is None:
        _default_db = Database(path)
        _default_db.init()
    return _default_db


def reset_db() -> None:
    """Close and discard the singleton (useful in tests)."""
    global _default_db
    if _default_db is not None:
        _default_db.close()
        _default_db = None
