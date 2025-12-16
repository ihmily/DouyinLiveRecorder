# -*- coding: utf-8 -*-
"""
Background upload queue with worker thread.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
import os
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from .database import DatabaseManager
from .repository import RecordingRepository
from .models import UploadStatus, RecordingSegment
from .tos_uploader import TOSUploader


@dataclass(order=True)
class UploadTask:
    """Upload task item."""
    priority: int = field(compare=True)  # Lower = higher priority
    segment_id: int = field(compare=False)
    local_path: str = field(compare=False)
    platform: str = field(compare=False)
    anchor_name: str = field(compare=False)
    filename: str = field(compare=False)


class UploadWorker:
    """
    Background worker that processes upload tasks.
    Implements retry logic and failure handling.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        tos_uploader: TOSUploader,
        max_retries: int = 3,
        retry_delay: int = 60,
        delete_after_upload: bool = True,
        on_upload_complete: Callable[[RecordingSegment, str], None] | None = None,
        on_upload_failed: Callable[[RecordingSegment, str], None] | None = None
    ):
        """
        Initialize upload worker.

        Args:
            db_manager: Database manager instance
            tos_uploader: TOS uploader instance
            max_retries: Maximum retry attempts
            retry_delay: Delay between retry checks (seconds)
            delete_after_upload: Delete local file after successful upload
            on_upload_complete: Callback when upload completes
            on_upload_failed: Callback when upload fails permanently
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
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.delete_after_upload = delete_after_upload
        self.on_upload_complete = on_upload_complete
        self.on_upload_failed = on_upload_failed

        self.task_queue: queue.PriorityQueue[UploadTask] = queue.PriorityQueue()
        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._retry_thread: threading.Thread | None = None
        self._is_running = False

    def start(self) -> None:
        """Start the background worker thread."""
        if self._is_running:
            self.logger.warning("Upload worker already running")
            return

        self._stop_event.clear()

        # Start main worker thread
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="UploadWorker",
            daemon=True
        )
        self._worker_thread.start()

        # Start retry check thread
        self._retry_thread = threading.Thread(
            target=self._retry_loop,
            name="UploadRetryWorker",
            daemon=True
        )
        self._retry_thread.start()

        self._is_running = True
        self.logger.debug("Upload worker started")

    def stop(self, wait: bool = True, timeout: float = 30.0) -> None:
        """Stop the worker thread."""
        self._stop_event.set()
        if wait:
            if self._worker_thread and self._worker_thread.is_alive():
                self._worker_thread.join(timeout=timeout)
            if self._retry_thread and self._retry_thread.is_alive():
                self._retry_thread.join(timeout=timeout)
        self._is_running = False
        self.logger.debug("Upload worker stopped")

    def enqueue(self, task: UploadTask) -> None:
        """Add task to upload queue."""
        self.task_queue.put(task)
        self.logger.debug(f"Task enqueued: segment_id={task.segment_id}, file={task.filename}")

    @property
    def queue_size(self) -> int:
        """Get current queue size."""
        return self.task_queue.qsize()

    def _worker_loop(self) -> None:
        """Main worker loop."""
        while not self._stop_event.is_set():
            try:
                # Non-blocking get with timeout
                try:
                    task = self.task_queue.get(timeout=5.0)
                except queue.Empty:
                    continue

                self._process_task(task)
                self.task_queue.task_done()

            except Exception as e:
                self.logger.error(f"Worker loop error: {e}")
                time.sleep(5)

    def _retry_loop(self) -> None:
        """Periodically check for failed tasks to retry."""
        while not self._stop_event.is_set():
            try:
                # Wait for retry delay
                for _ in range(self.retry_delay):
                    if self._stop_event.is_set():
                        return
                    time.sleep(1)

                self._retry_failed_tasks()

            except Exception as e:
                self.logger.error(f"Retry loop error: {e}")
                time.sleep(10)

    def _process_task(self, task: UploadTask) -> None:
        """Process a single upload task."""
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            segment = repo.get_segment_by_id(task.segment_id)

            if not segment:
                self.logger.warning(f"Segment not found: {task.segment_id}")
                return

            # Check if file exists
            if not os.path.exists(task.local_path):
                self.logger.warning(f"Local file not found: {task.local_path}")
                repo.update_upload_status(
                    task.segment_id,
                    UploadStatus.SKIPPED,
                    error_message="Local file not found"
                )
                return

            # Mark as uploading
            repo.update_upload_status(task.segment_id, UploadStatus.UPLOADING)
            session.commit()

        # Generate OSS key (outside session context)
        oss_key = self.tos_uploader.generate_oss_key(
            platform=task.platform,
            anchor_name=task.anchor_name,
            filename=task.filename
        )

        # Attempt upload
        success, result = self.tos_uploader.upload_file(
            local_path=task.local_path,
            oss_key=oss_key
        )

        # Update database with result
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            segment = repo.get_segment_by_id(task.segment_id)

            if success:
                repo.update_upload_status(
                    task.segment_id,
                    UploadStatus.COMPLETED,
                    oss_path=result,
                    oss_bucket=self.tos_uploader.bucket
                )
                self.logger.info(f"Upload completed: {task.filename} -> {result}")

                # Delete local file if configured
                if self.delete_after_upload:
                    try:
                        os.remove(task.local_path)
                        repo.mark_local_deleted(task.segment_id)
                        self.logger.debug(f"Local file deleted: {task.local_path}")
                    except OSError as e:
                        self.logger.warning(f"Failed to delete local file: {e}")

                # Callback
                if self.on_upload_complete and segment:
                    try:
                        self.on_upload_complete(segment, result)
                    except Exception as e:
                        self.logger.error(f"Upload complete callback error: {e}")
            else:
                # Check retry count
                current_retries = segment.upload_retry_count if segment else 0
                if current_retries >= self.max_retries - 1:
                    repo.update_upload_status(
                        task.segment_id,
                        UploadStatus.FAILED,
                        error_message=result
                    )
                    self.logger.error(
                        f"Upload permanently failed after {self.max_retries} retries: {task.filename}"
                    )

                    if self.on_upload_failed and segment:
                        try:
                            self.on_upload_failed(segment, result)
                        except Exception as e:
                            self.logger.error(f"Upload failed callback error: {e}")
                else:
                    repo.update_upload_status(
                        task.segment_id,
                        UploadStatus.FAILED,
                        error_message=result
                    )
                    self.logger.warning(
                        f"Upload failed (retry {current_retries + 1}/{self.max_retries}): {task.filename}"
                    )

    def _retry_failed_tasks(self) -> None:
        """Re-queue failed tasks for retry."""
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            failed_segments = repo.get_failed_uploads(max_retries=self.max_retries)

            for segment in failed_segments:
                # Get parent session for metadata
                rec_session = repo.get_session_by_id(segment.session_id)
                if rec_session:
                    task = UploadTask(
                        priority=1,  # Lower priority for retries
                        segment_id=segment.id,
                        local_path=segment.local_file_path,
                        platform=rec_session.platform,
                        anchor_name=rec_session.anchor_name,
                        filename=segment.file_name
                    )
                    self.enqueue(task)

                    # Mark as pending to prevent duplicate retries
                    segment.upload_status = UploadStatus.PENDING

            if failed_segments:
                self.logger.debug(f"Re-queued {len(failed_segments)} failed tasks for retry")
