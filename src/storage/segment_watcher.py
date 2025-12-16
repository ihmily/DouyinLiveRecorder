# -*- coding: utf-8 -*-
"""
Real-time segment file watcher.

Monitors a directory for new segment files created by FFmpeg during recording.
Triggers callbacks when new segments are detected, enabling real-time processing.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    from ..logger import logger
except ImportError:
    from loguru import logger


@dataclass
class SegmentInfo:
    """Information about a detected segment."""
    path: str
    filename: str
    index: int
    size: int
    created_at: float


class SegmentWatcher:
    """
    Real-time watcher for FFmpeg segment files.

    Monitors a directory for new segment files matching a pattern and
    triggers callbacks when stable segments are detected.

    Usage:
        def on_segment(info: SegmentInfo):
            print(f"New segment: {info.filename}")

        watcher = SegmentWatcher(
            watch_dir="/path/to/recordings",
            filename_prefix="anchor_2025-12-16_14-30-00",
            file_extension=".ts",
            on_segment_created=on_segment
        )
        watcher.start()

        # ... FFmpeg recording ...

        watcher.stop()
        segments = watcher.get_all_segments()
    """

    # Pattern to extract segment index from filename
    # Matches: prefix_000.ts, prefix_001.ts, etc.
    SEGMENT_INDEX_PATTERN = re.compile(r'_(\d{3,})\.(\w+)$')

    def __init__(
        self,
        watch_dir: str,
        filename_prefix: str,
        file_extension: str,
        on_segment_created: Optional[Callable[[SegmentInfo], None]] = None,
        poll_interval: float = 2.0,
        stable_time: float = 1.0
    ):
        """
        Initialize segment watcher.

        Args:
            watch_dir: Directory to monitor
            filename_prefix: Prefix of segment filenames (before _XXX.ext)
            file_extension: File extension including dot (.ts, .mp4)
            on_segment_created: Callback when new stable segment detected
            poll_interval: Seconds between directory scans
            stable_time: Seconds a file must be unchanged to be considered stable
        """
        self.watch_dir = watch_dir
        self.filename_prefix = filename_prefix
        self.file_extension = file_extension.lower()
        self.on_segment_created = on_segment_created
        self.poll_interval = poll_interval
        self.stable_time = stable_time

        # Internal state
        self._segments: dict[str, SegmentInfo] = {}  # path -> SegmentInfo
        self._pending: dict[str, tuple[int, float]] = {}  # path -> (size, last_modified)
        self._stop_event = threading.Event()
        self._watcher_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the watcher thread."""
        if self._watcher_thread is not None:
            return

        self._stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._watch_loop,
            name=f"SegmentWatcher-{self.filename_prefix[:20]}",
            daemon=True
        )
        self._watcher_thread.start()
        logger.debug(f"SegmentWatcher started: {self.watch_dir}/{self.filename_prefix}*{self.file_extension}")

    def stop(self, timeout: float = 5.0) -> None:
        """
        Stop the watcher thread.

        Args:
            timeout: Maximum seconds to wait for thread to finish
        """
        self._stop_event.set()
        if self._watcher_thread is not None:
            self._watcher_thread.join(timeout=timeout)
            self._watcher_thread = None

        # Final scan to catch any remaining segments
        self._scan_directory(final=True)
        logger.debug(f"SegmentWatcher stopped: found {len(self._segments)} segments")

    def get_all_segments(self) -> list[SegmentInfo]:
        """Get all detected segments sorted by index."""
        with self._lock:
            return sorted(self._segments.values(), key=lambda s: s.index)

    def get_segment_count(self) -> int:
        """Get current segment count."""
        with self._lock:
            return len(self._segments)

    @property
    def is_running(self) -> bool:
        """Check if watcher is running."""
        return self._watcher_thread is not None and self._watcher_thread.is_alive()

    def _watch_loop(self) -> None:
        """Main watcher loop."""
        while not self._stop_event.is_set():
            try:
                self._scan_directory()
            except Exception as e:
                logger.error(f"SegmentWatcher scan error: {e}")

            # Sleep with early exit support
            for _ in range(int(self.poll_interval * 10)):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

    def _scan_directory(self, final: bool = False) -> None:
        """Scan directory for new segments."""
        if not os.path.exists(self.watch_dir):
            return

        current_time = time.time()

        try:
            files = os.listdir(self.watch_dir)
        except OSError:
            return

        for filename in files:
            # Check if filename matches our pattern
            if not filename.startswith(self.filename_prefix):
                continue
            if not filename.lower().endswith(self.file_extension):
                continue

            filepath = os.path.join(self.watch_dir, filename)

            # Skip if already processed
            with self._lock:
                if filepath in self._segments:
                    continue

            # Get file info
            try:
                stat = os.stat(filepath)
                file_size = stat.st_size
                file_mtime = stat.st_mtime
            except OSError:
                continue

            # Skip empty files
            if file_size == 0:
                continue

            # Extract segment index
            match = self.SEGMENT_INDEX_PATTERN.search(filename)
            if not match:
                continue

            segment_index = int(match.group(1))

            # Check stability (file size unchanged for stable_time seconds)
            if filepath in self._pending:
                prev_size, prev_time = self._pending[filepath]
                if file_size == prev_size:
                    # Size unchanged - check if stable enough
                    if current_time - prev_time >= self.stable_time or final:
                        # Segment is stable, process it
                        self._process_segment(filepath, filename, segment_index, file_size, file_mtime)
                        del self._pending[filepath]
                else:
                    # Size changed, update pending
                    self._pending[filepath] = (file_size, current_time)
            else:
                # New file, add to pending
                self._pending[filepath] = (file_size, current_time)

    def _process_segment(
        self,
        filepath: str,
        filename: str,
        index: int,
        size: int,
        mtime: float
    ) -> None:
        """Process a stable segment."""
        segment_info = SegmentInfo(
            path=filepath,
            filename=filename,
            index=index,
            size=size,
            created_at=mtime
        )

        with self._lock:
            self._segments[filepath] = segment_info

        logger.debug(f"Segment detected: {filename} (index={index}, size={size/1024/1024:.1f}MB)")

        # Trigger callback
        if self.on_segment_created:
            try:
                self.on_segment_created(segment_info)
            except Exception as e:
                logger.error(f"Segment callback error: {e}")
