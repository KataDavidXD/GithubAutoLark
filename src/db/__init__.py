"""Database layer — SQLite with ACID transactions and repository pattern."""

from src.db.database import Database, get_db
from src.db.schema import SCHEMA_DDL

__all__ = ["Database", "get_db", "SCHEMA_DDL"]
