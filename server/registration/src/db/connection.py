"""Database connection management"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseConnection:
    """SQLite database connection wrapper"""
    
    def __init__(self, db_path: str = None):
        """Initialize database connection"""
        if db_path is None:
            # Use default path in workspace
            db_path = str(Path(__file__).parent.parent.parent.parent.parent / ".data" / "cowater.db")
        
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._ensure_directory()
        self._connect()
    
    def _ensure_directory(self):
        """Ensure database directory exists"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Database directory: {db_dir}")
    
    def _connect(self):
        """Establish database connection"""
        try:
            self.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=10.0
            )
            # Enable foreign key support
            self.conn.execute("PRAGMA foreign_keys = ON")
            # Set row factory for dict-like access
            self.conn.row_factory = sqlite3.Row
            logger.info(f"✅ Connected to SQLite: {self.db_path}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to SQLite: {e}")
            raise
    
    def get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        if self.conn is None:
            self._connect()
        return self.conn
    
    def execute(self, query: str, params: tuple = None):
        """Execute query and return cursor"""
        cursor = self.conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        return cursor
    
    def execute_one(self, query: str, params: tuple = None):
        """Execute query and return single row"""
        cursor = self.execute(query, params)
        return cursor.fetchone()
    
    def execute_all(self, query: str, params: tuple = None):
        """Execute query and return all rows"""
        cursor = self.execute(query, params)
        return cursor.fetchall()
    
    def commit(self):
        """Commit transaction"""
        if self.conn:
            self.conn.commit()
    
    def rollback(self):
        """Rollback transaction"""
        if self.conn:
            self.conn.rollback()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
            self.conn = None
            logger.info("✅ Database connection closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()


# Global database instance
_db_instance: Optional[DatabaseConnection] = None


def get_db(db_path: str = None) -> DatabaseConnection:
    """Get or create global database instance"""
    global _db_instance
    
    if _db_instance is None:
        _db_instance = DatabaseConnection(db_path)
    
    return _db_instance


def close_db():
    """Close global database instance"""
    global _db_instance
    
    if _db_instance:
        _db_instance.close()
        _db_instance = None
