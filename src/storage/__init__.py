# -*- coding: utf-8 -*-
"""
Storage module for recording file management and OSS upload.

This module provides:
- Database models for recording sessions and segments
- SQLAlchemy-based data access layer
- TOS (Volcano Engine Object Storage) upload client
- Background upload queue with retry logic
- High-level manager for easy integration

Usage:
    from src.storage import RecordingManager

    # Initialize from config files
    manager = RecordingManager.from_config('config/config.ini', 'config/tos_credentials.ini')
    manager.start()

    # On recording complete
    manager.on_recording_complete(
        record_name="序号1 主播名",
        save_file_path="/path/to/file.ts",
        save_type="TS",
        platform="抖音直播",
        anchor_name="主播名",
        live_room_url="https://live.douyin.com/xxx"
    )

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
from .models import RecordingSession, RecordingSegment, UploadStatus, Base
from .database import DatabaseManager
from .repository import RecordingRepository
from .tos_uploader import TOSUploader
from .upload_queue import UploadWorker, UploadTask
from .manager import RecordingManager
from .segment_watcher import SegmentWatcher, SegmentInfo
from .cleanup import StorageCleanup, CleanupResult, StorageStats

__all__ = [
    # Models
    "RecordingSession",
    "RecordingSegment",
    "UploadStatus",
    "Base",
    # Database
    "DatabaseManager",
    # Repository
    "RecordingRepository",
    # TOS
    "TOSUploader",
    # Upload Queue
    "UploadWorker",
    "UploadTask",
    # Manager (main interface)
    "RecordingManager",
    # Segment Watcher
    "SegmentWatcher",
    "SegmentInfo",
    # Cleanup
    "StorageCleanup",
    "CleanupResult",
    "StorageStats",
]
