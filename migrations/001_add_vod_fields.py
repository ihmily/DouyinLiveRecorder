# -*- coding: utf-8 -*-
"""
Migration: Add VOD playback fields to recording_segments table.

Run: python migrations/001_add_vod_fields.py

Author: DouyinLiveRecorder
Date: 2026-01-06
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from src.storage.database import DatabaseManager


def check_column_exists(session, table: str, column: str) -> bool:
    """Check if a column exists in the table."""
    result = session.execute(text(f"PRAGMA table_info({table})"))
    columns = [row[1] for row in result.fetchall()]
    return column in columns


def upgrade():
    """Add VOD fields to recording_segments table."""
    db = DatabaseManager.get_instance()

    with db.get_session() as session:
        # Check and add mp4_oss_path column
        if not check_column_exists(session, 'recording_segments', 'mp4_oss_path'):
            session.execute(text(
                "ALTER TABLE recording_segments ADD COLUMN mp4_oss_path TEXT"
            ))
            print("Added column: mp4_oss_path")

        # Check and add mp4_status column
        if not check_column_exists(session, 'recording_segments', 'mp4_status'):
            session.execute(text(
                "ALTER TABLE recording_segments ADD COLUMN mp4_status VARCHAR(20) DEFAULT 'pending'"
            ))
            print("Added column: mp4_status")

        # Check and add duration column
        if not check_column_exists(session, 'recording_segments', 'duration'):
            session.execute(text(
                "ALTER TABLE recording_segments ADD COLUMN duration FLOAT"
            ))
            print("Added column: duration")

        # Create index on mp4_status for conversion queue
        try:
            session.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_recording_segments_mp4_status ON recording_segments (mp4_status)"
            ))
            print("Created index: ix_recording_segments_mp4_status")
        except Exception as e:
            print(f"Index may already exist: {e}")

        session.commit()
        print("Migration completed successfully!")


def downgrade():
    """Remove VOD fields (SQLite doesn't support DROP COLUMN easily)."""
    print("Downgrade not supported for SQLite. Recreate database if needed.")


if __name__ == "__main__":
    upgrade()
