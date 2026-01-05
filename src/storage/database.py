# -*- coding: utf-8 -*-
"""
Database engine and session management.
Supports SQLite (default), PostgreSQL, MySQL via SQLAlchemy.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
import os
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base

# Default SQLite database path
DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "recordings.db"
)


class DatabaseManager:
    """Manages database connections and sessions."""

    _instance: "DatabaseManager | None" = None

    def __init__(self, database_url: str | None = None):
        """
        Initialize database manager.

        Args:
            database_url: SQLAlchemy database URL. Defaults to SQLite.
                Examples:
                - sqlite:///path/to/db.sqlite
                - postgresql://user:pass@localhost/dbname
                - mysql+pymysql://user:pass@localhost/dbname
        """
        # Import logger here to avoid circular import
        try:
            from ..logger import logger
            self.logger = logger
        except ImportError:
            import logging
            self.logger = logging.getLogger(__name__)

        if database_url is None or database_url.strip() == "":
            # Ensure data directory exists
            os.makedirs(os.path.dirname(DEFAULT_DB_PATH), exist_ok=True)
            database_url = f"sqlite:///{DEFAULT_DB_PATH}"

        self.database_url = database_url

        # Create engine with appropriate settings
        engine_kwargs = {
            "echo": False,  # Set True for SQL debugging
            "pool_pre_ping": True,  # Check connection health
        }

        # SQLite specific settings
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}

        self.engine = create_engine(database_url, **engine_kwargs)

        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False
        )

        # Create tables if not exist
        Base.metadata.create_all(self.engine)

        # Log initialization (hide credentials)
        safe_url = database_url.split('@')[-1] if '@' in database_url else database_url
        self.logger.debug(f"Database initialized: {safe_url}")

    @classmethod
    def get_instance(cls, database_url: str | None = None) -> "DatabaseManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls(database_url)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (for testing)."""
        if cls._instance is not None:
            cls._instance.engine.dispose()
            cls._instance = None

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Context manager for database sessions with auto-commit/rollback."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            session.close()

    def get_new_session(self) -> Session:
        """Get a new session (caller must manage lifecycle)."""
        return self.SessionLocal()

    def close(self) -> None:
        """Close database connections."""
        self.engine.dispose()
        self.logger.debug("Database connections closed")
