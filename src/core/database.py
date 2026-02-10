"""
Database connection and operations
"""
import sqlite3
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import logging

from src.config import settings

logger = logging.getLogger(__name__)


class Database:
    """Database manager for SQLite operations"""
    
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self._ensure_database()
    
    def _ensure_database(self):
        """Create database and tables if they don't exist"""
        if not self.db_path.exists():
            logger.info(f"Creating new database at {self.db_path}")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize_schema()
        else:
            logger.info(f"Using existing database at {self.db_path}")
    
    def _initialize_schema(self):
        """Initialize database schema from SQL file"""
        schema_path = settings.BASE_DIR / "database_schema.sql"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")
        
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema_sql = f.read()
        
        with self.get_connection() as conn:
            conn.executescript(schema_sql)
            conn.commit()
        
        logger.info("Database schema initialized successfully")
    
    @contextmanager
    def get_connection(self):
        """Get database connection with context manager"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row  # Enable column access by name
        conn.execute("PRAGMA foreign_keys = ON")  # Enable foreign keys
        try:
            yield conn
        finally:
            conn.close()
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Execute SELECT query and return results as list of dicts"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def execute_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Execute SELECT query and return single result"""
        results = self.execute_query(query, params)
        return results[0] if results else None
    
    def execute_write(self, query: str, params: tuple = ()) -> int:
        """Execute INSERT/UPDATE/DELETE query and return affected row count or last insert ID"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            # Return last insert ID for INSERT, row count for UPDATE/DELETE
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute multiple INSERT/UPDATE queries"""
        with self.get_connection() as conn:
            cursor = conn.executemany(query, params_list)
            conn.commit()
            return cursor.rowcount


# Global database instance
db = Database()
