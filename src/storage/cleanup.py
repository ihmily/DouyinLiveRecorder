# -*- coding: utf-8 -*-
"""
OSS Storage Cleanup module.

Automatically cleans up old recordings from OSS when storage exceeds threshold.
Deletes entire sessions (all segments) in FIFO order by started_at.

Thread-safe: Uses mutex to ensure only one cleanup runs at a time.

Author: DouyinLiveRecorder
Date: 2026-01-06
"""
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .repository import RecordingRepository
    from .tos_uploader import TOSUploader
    from .database import DatabaseManager


@dataclass
class CleanupResult:
    """Result of a cleanup operation."""
    triggered: bool = False           # Whether cleanup was needed
    sessions_deleted: int = 0         # Number of sessions deleted
    bytes_freed: int = 0              # Total bytes freed
    errors: list[str] = field(default_factory=list)  # Any errors encountered
    duration_seconds: float = 0.0     # Time taken


@dataclass
class StorageStats:
    """Current storage statistics."""
    total_bytes: int = 0              # Current OSS storage usage
    threshold_bytes: int = 0          # Configured threshold
    over_threshold: bool = False      # Whether storage exceeds threshold
    sessions_count: int = 0           # Number of completed sessions


class StorageCleanup:
    """
    OSS storage cleanup manager.

    Triggers cleanup after each upload, deleting oldest completed sessions
    until storage falls below threshold. Thread-safe with mutex protection.
    """

    def __init__(
        self,
        db_manager: "DatabaseManager",
        tos_uploader: "TOSUploader",
        threshold_bytes: int,
        enabled: bool = True
    ):
        """
        Initialize cleanup manager.

        Args:
            db_manager: Database manager for data access
            tos_uploader: TOS client for file deletion
            threshold_bytes: Storage threshold in bytes (0 disables cleanup)
            enabled: Whether cleanup is enabled
        """
        # Import logger
        try:
            from ..logger import logger
            self.logger = logger
        except ImportError:
            import logging
            self.logger = logging.getLogger(__name__)

        self.db_manager = db_manager
        self.tos_uploader = tos_uploader
        self.threshold_bytes = threshold_bytes
        self.enabled = enabled and threshold_bytes > 0

        # Mutex for thread safety - blocks concurrent cleanup calls
        self._cleanup_lock = threading.Lock()

    def wait_for_completion(self, timeout: float = 60.0) -> bool:
        """
        Wait for any in-progress cleanup to complete.

        This method is used during graceful shutdown to ensure cleanup
        operations finish before the application exits.

        Args:
            timeout: Maximum seconds to wait (default 60.0)

        Returns:
            True if cleanup completed (or wasn't running), False if timeout expired
        """
        acquired = self._cleanup_lock.acquire(timeout=timeout)
        if acquired:
            self._cleanup_lock.release()
            return True
        self.logger.warning(f"Cleanup wait timeout after {timeout}s")
        return False

    def get_storage_stats(self) -> StorageStats:
        """
        Get current storage statistics without triggering cleanup.

        Returns:
            StorageStats with current usage info
        """
        from .repository import RecordingRepository

        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            total_bytes = repo.get_total_oss_storage()
            sessions_count = repo.get_completed_sessions_count()

        return StorageStats(
            total_bytes=total_bytes,
            threshold_bytes=self.threshold_bytes,
            over_threshold=total_bytes > self.threshold_bytes,
            sessions_count=sessions_count
        )

    def trigger_cleanup(self) -> CleanupResult:
        """
        Trigger cleanup check. Blocks until cleanup completes.

        Thread-safe: Multiple concurrent calls will queue and execute sequentially.
        After acquiring lock, re-checks storage in case another cleanup freed space.

        Returns:
            CleanupResult with details of what was cleaned
        """
        # Check if cleanup is disabled
        if not self.enabled or self.threshold_bytes <= 0:
            return CleanupResult(triggered=False)

        # Acquire mutex - blocks if another cleanup is in progress
        with self._cleanup_lock:
            start_time = time.time()

            # Re-check storage after acquiring lock (FR-011)
            # Another cleanup may have freed space while we were waiting
            stats = self.get_storage_stats()

            # Log cleanup trigger check
            self.logger.info(
                f"OSS cleanup check: current={stats.total_bytes / 1024**3:.2f}GB, "
                f"threshold={stats.threshold_bytes / 1024**3:.2f}GB"
            )

            if not stats.over_threshold:
                return CleanupResult(
                    triggered=False,
                    duration_seconds=time.time() - start_time
                )

            # Perform cleanup
            result = self._perform_cleanup(stats)
            result.duration_seconds = time.time() - start_time

            # Log summary
            self.logger.info(
                f"OSS cleanup complete: {result.sessions_deleted} sessions, "
                f"{result.bytes_freed / 1024**3:.2f}GB freed in {result.duration_seconds:.1f}s"
            )

            return result

    def _perform_cleanup(self, stats: StorageStats) -> CleanupResult:
        """
        Perform the actual cleanup operation.

        Deletes oldest completed sessions until storage falls below threshold.

        Args:
            stats: Current storage statistics

        Returns:
            CleanupResult with cleanup details
        """
        from .repository import RecordingRepository

        result = CleanupResult(triggered=True)
        current_bytes = stats.total_bytes
        target_bytes = self.threshold_bytes

        self.logger.info(
            f"OSS cleanup triggered: need to free {(current_bytes - target_bytes) / 1024**3:.2f}GB"
        )

        # Get oldest sessions to delete
        # Extract data within session context to avoid detached instance errors
        sessions_to_delete = []
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            oldest_sessions = repo.get_oldest_completed_sessions(limit=50)
            # Extract needed attributes while session is open
            for rec_session, session_size in oldest_sessions:
                sessions_to_delete.append({
                    'id': rec_session.id,
                    'anchor_name': rec_session.anchor_name,
                    'started_at': rec_session.started_at,
                    'size': session_size
                })

        # Delete sessions until we're under threshold
        for session_info in sessions_to_delete:
            if current_bytes <= target_bytes:
                break

            # Delete this session
            freed, errors = self._delete_session(
                session_info['id'],
                session_info  # Pass dict instead of ORM object
            )
            result.sessions_deleted += 1
            result.bytes_freed += freed
            result.errors.extend(errors)
            current_bytes -= freed

        return result

    def _delete_session(self, session_id: int, session_info: dict | None = None) -> tuple[int, list[str]]:
        """
        Delete a single session: OSS files first, then DB records.

        Args:
            session_id: Session ID to delete
            session_info: Optional dict with session info for logging
                          (keys: 'anchor_name', 'started_at')

        Returns:
            (bytes_freed, errors_list)
        """
        from .repository import RecordingRepository

        errors = []
        bytes_freed = 0

        # Log session deletion start
        if session_info:
            self.logger.info(
                f"Deleting session {session_id} ({session_info.get('anchor_name', 'unknown')}, "
                f"started {session_info.get('started_at', 'unknown')})"
            )

        # Get segments to delete
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            segments = repo.get_session_segments_for_cleanup(session_id)

            # Delete OSS files for each segment
            for segment in segments:
                freed, segment_errors = self._delete_oss_files_for_segment(segment)
                bytes_freed += freed
                errors.extend(segment_errors)

            # Delete database records (hard delete)
            segment_count = repo.delete_session_with_segments(session_id)
            session.commit()

            self.logger.info(
                f"Deleted session {session_id}: {segment_count} segment records removed from DB"
            )

        return bytes_freed, errors

    def _delete_oss_files_for_segment(self, segment) -> tuple[int, list[str]]:
        """
        Delete OSS files for a segment (TS and MP4).

        Args:
            segment: RecordingSegment object

        Returns:
            (bytes_freed, errors_list)
        """
        errors = []
        bytes_freed = segment.file_size or 0

        # Delete TS file (oss_path)
        if segment.oss_path:
            # Extract key from tos:// URL
            oss_key = self._extract_oss_key(segment.oss_path)
            if oss_key:
                success = self.tos_uploader.delete_object(oss_key)
                if success:
                    self.logger.info(f"Deleted segment {segment.id}: {oss_key}")
                else:
                    error = f"Failed to delete {oss_key}"
                    self.logger.error(error)
                    errors.append(error)

        # Delete MP4 file (mp4_oss_path) if exists
        if segment.mp4_oss_path:
            mp4_key = self._extract_oss_key(segment.mp4_oss_path)
            if mp4_key:
                success = self.tos_uploader.delete_object(mp4_key)
                if success:
                    self.logger.info(f"Deleted segment {segment.id} MP4: {mp4_key}")
                else:
                    error = f"Failed to delete MP4 {mp4_key}"
                    self.logger.error(error)
                    errors.append(error)

        return bytes_freed, errors

    @staticmethod
    def _extract_oss_key(oss_path: str) -> str | None:
        """
        Extract object key from tos:// URL.

        Args:
            oss_path: Full TOS path like "tos://bucket/key"

        Returns:
            Object key or None if invalid
        """
        if not oss_path:
            return None

        # Format: tos://bucket/key
        if oss_path.startswith("tos://"):
            parts = oss_path[6:].split("/", 1)
            if len(parts) == 2:
                return parts[1]

        return oss_path  # Assume it's already a key
