# -*- coding: utf-8 -*-
"""
High-level manager for recording file management.
This is the main interface for integration with main.py.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
import datetime
import os
import configparser
from .database import DatabaseManager
from .repository import RecordingRepository
from .models import RecordingSession, RecordingSegment, UploadStatus
from .tos_uploader import TOSUploader
from .upload_queue import UploadWorker, UploadTask


class RecordingManager:
    """
    High-level API for recording file management and OSS upload.

    Usage in main.py:
        from src.storage import RecordingManager

        # Initialize (once at startup)
        recording_manager = RecordingManager.from_config(config_file, tos_config_file)
        recording_manager.start()

        # On recording complete (in check_subprocess)
        recording_manager.on_recording_complete(
            record_name=record_name,
            save_file_path=save_file_path,
            save_type=save_type,
            platform=platform,
            anchor_name=anchor_name,
            live_room_url=record_url
        )
    """

    _instance: "RecordingManager | None" = None

    def __init__(
        self,
        db_manager: DatabaseManager,
        tos_uploader: TOSUploader | None = None,
        enable_upload: bool = True,
        delete_after_upload: bool = True,
        max_retries: int = 3
    ):
        """
        Initialize recording manager.

        Args:
            db_manager: Database manager instance
            tos_uploader: TOS uploader instance (optional)
            enable_upload: Whether to enable OSS upload
            delete_after_upload: Delete local file after upload
            max_retries: Maximum upload retry attempts
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
        self.enable_upload = enable_upload and tos_uploader is not None
        self.delete_after_upload = delete_after_upload
        self.max_retries = max_retries

        # Track active recording sessions
        self._active_sessions: dict[str, int] = {}  # record_name -> session_id

        # Upload worker (lazy initialized)
        self._upload_worker: UploadWorker | None = None

    @classmethod
    def from_config(
        cls,
        config_file: str,
        tos_config_file: str,
        database_url: str | None = None
    ) -> "RecordingManager":
        """
        Create manager from config files.

        Reads OSS settings from config.ini [OSS设置] section.

        Args:
            config_file: Path to config.ini
            tos_config_file: Path to tos_credentials.ini
            database_url: Override database URL (optional)

        Returns:
            RecordingManager instance
        """
        # Import logger
        try:
            from ..logger import logger
        except ImportError:
            import logging
            logger = logging.getLogger(__name__)

        config = configparser.RawConfigParser()
        config.read(config_file, encoding='utf-8-sig')

        # Read OSS settings with defaults
        enable_upload = False
        delete_after_upload = True
        max_retries = 3
        db_url = database_url

        if config.has_section('OSS设置'):
            enable_upload = config.get('OSS设置', '启用OSS上传(是/否)', fallback='否') == '是'
            delete_after_upload = config.get('OSS设置', '上传后删除本地文件(是/否)', fallback='是') == '是'
            max_retries = int(config.get('OSS设置', '上传失败重试次数', fallback='3'))
            if not db_url:
                db_url = config.get('OSS设置', '数据库URL', fallback='')
                if not db_url.strip():
                    db_url = None

        # Initialize database
        db_manager = DatabaseManager.get_instance(db_url)

        # Initialize TOS uploader if enabled
        tos_uploader = None
        if enable_upload and os.path.exists(tos_config_file):
            try:
                tos_uploader = TOSUploader(config_path=tos_config_file)
                # Verify bucket access
                if not tos_uploader.check_bucket_access():
                    logger.warning("TOS bucket access check failed, upload disabled")
                    tos_uploader = None
                    enable_upload = False
            except Exception as e:
                logger.error(f"Failed to initialize TOS uploader: {e}")
                enable_upload = False

        return cls(
            db_manager=db_manager,
            tos_uploader=tos_uploader,
            enable_upload=enable_upload,
            delete_after_upload=delete_after_upload,
            max_retries=max_retries
        )

    @classmethod
    def get_instance(cls) -> "RecordingManager | None":
        """Get singleton instance if initialized."""
        return cls._instance

    def start(self) -> None:
        """Start background services (upload worker)."""
        if self.enable_upload and self.tos_uploader:
            self._upload_worker = UploadWorker(
                db_manager=self.db_manager,
                tos_uploader=self.tos_uploader,
                max_retries=self.max_retries,
                delete_after_upload=self.delete_after_upload
            )
            self._upload_worker.start()
            self.logger.info("Recording manager started with OSS upload enabled")
        else:
            self.logger.info("Recording manager started (OSS upload disabled)")

        RecordingManager._instance = self

    def stop(self) -> None:
        """Stop background services."""
        if self._upload_worker:
            self._upload_worker.stop()
        self.logger.info("Recording manager stopped")

    def start_recording(
        self,
        record_name: str,
        anchor_name: str,
        platform: str,
        live_room_url: str,
        live_title: str | None = None,
        record_quality: str | None = None,
        is_split: bool = False
    ) -> int:
        """
        Create a new recording session.

        Args:
            record_name: Unique identifier (e.g., "序号X 主播名")
            anchor_name: Anchor name
            platform: Platform name (e.g., "抖音直播")
            live_room_url: Live room URL
            live_title: Live title (optional)
            record_quality: Recording quality (optional)
            is_split: Whether split recording is enabled

        Returns:
            session_id for tracking
        """
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            rec_session = repo.create_session(
                anchor_name=anchor_name,
                platform=platform,
                live_room_url=live_room_url,
                live_title=live_title,
                record_quality=record_quality,
                is_split=is_split
            )
            session_id = rec_session.id

        self._active_sessions[record_name] = session_id
        self.logger.debug(f"Recording session created: {anchor_name} -> session_id={session_id}")
        return session_id

    def on_segment_created(
        self,
        session_id: int,
        segment_path: str,
        segment_index: int,
        platform: str,
        anchor_name: str,
        save_type: str = "ts"
    ) -> int | None:
        """
        Called when a new segment file is detected during recording.

        This enables real-time processing of segments instead of waiting
        for the entire recording to complete.

        Args:
            session_id: Recording session ID
            segment_path: Full path to the segment file
            segment_index: Index of this segment (0, 1, 2, ...)
            platform: Platform name
            anchor_name: Anchor name
            save_type: Recording format (ts/mp4/flv/mkv)

        Returns:
            segment_id if successful, None otherwise
        """
        # Get file info
        file_name = os.path.basename(segment_path)
        file_size = None
        if os.path.exists(segment_path):
            try:
                file_size = os.path.getsize(segment_path)
            except OSError:
                pass

        # Add segment to database
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            segment = repo.add_segment(
                session_id=session_id,
                local_file_path=segment_path,
                file_name=file_name,
                file_format=save_type.lower(),
                file_size=file_size,
                segment_index=segment_index
            )
            segment_id = segment.id

            # Update session segment count
            repo.update_session_segment_count(session_id, segment_index + 1)

        create_time = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        size_mb = f"{file_size/1024/1024:.2f}MB" if file_size else "未知"
        self.logger.info(f"分段已写入数据库: {file_name} | 会话: {session_id} | 序号: {segment_index} | 大小: {size_mb} | 时间: {create_time}")

        # Queue for upload if enabled
        if self.enable_upload and self._upload_worker:
            from .upload_queue import UploadTask
            task = UploadTask(
                priority=0,
                segment_id=segment_id,
                local_path=segment_path,
                platform=platform,
                anchor_name=anchor_name,
                filename=file_name
            )
            self._upload_worker.enqueue(task)
            self.logger.info(f"分段已加入上传队列: {file_name} | segment_id: {segment_id}")
        else:
            self.logger.debug(f"分段未加入上传队列 (上传未启用): {file_name}")

        return segment_id

    def on_recording_complete(
        self,
        record_name: str,
        save_file_path: str,
        save_type: str,
        platform: str,
        anchor_name: str,
        live_room_url: str = "",
        live_title: str | None = None,
        segment_index: int = 0,
        session_id: int | None = None
    ) -> None:
        """
        Called when a recording file is complete.

        This should be called from check_subprocess() in main.py.

        Args:
            record_name: Unique identifier (e.g., "序号X 主播名")
            save_file_path: Local file path
            save_type: Recording format (TS/FLV/MP4/MKV)
            platform: Platform name
            anchor_name: Anchor name
            live_room_url: Live room URL
            live_title: Live title (optional)
            segment_index: Segment index for split recordings
            session_id: Session ID (optional, auto-created if not provided)
        """
        # Get or create session ID
        if session_id is None:
            session_id = self._active_sessions.get(record_name)

        if session_id is None:
            # Create session on-the-fly if not tracked (backward compatibility)
            session_id = self.start_recording(
                record_name=record_name,
                anchor_name=anchor_name,
                platform=platform,
                live_room_url=live_room_url,
                live_title=live_title,
                is_split=segment_index > 0
            )

        # Get file info
        file_name = os.path.basename(save_file_path)
        file_size = None
        if os.path.exists(save_file_path):
            try:
                file_size = os.path.getsize(save_file_path)
            except OSError:
                pass

        # Add segment to database
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            segment = repo.add_segment(
                session_id=session_id,
                local_file_path=save_file_path,
                file_name=file_name,
                file_format=save_type.lower(),
                file_size=file_size,
                segment_index=segment_index
            )
            segment_id = segment.id

        self.logger.debug(f"Recording segment added: {file_name} (segment_id={segment_id})")

        # Queue for upload if enabled
        if self.enable_upload and self._upload_worker:
            task = UploadTask(
                priority=0,  # Normal priority
                segment_id=segment_id,
                local_path=save_file_path,
                platform=platform,
                anchor_name=anchor_name,
                filename=file_name
            )
            self._upload_worker.enqueue(task)

    def end_recording(self, record_name: str, segment_count: int = 1) -> None:
        """
        Mark recording session as ended.

        Args:
            record_name: Unique identifier
            segment_count: Total number of segments
        """
        session_id = self._active_sessions.pop(record_name, None)
        if session_id:
            with self.db_manager.get_session() as session:
                repo = RecordingRepository(session)
                repo.end_session(session_id, segment_count)
            self.logger.debug(f"Recording session ended: {record_name}")

    def get_upload_stats(self) -> dict:
        """Get upload statistics."""
        with self.db_manager.get_session() as session:
            repo = RecordingRepository(session)
            return repo.get_upload_stats()

    @property
    def is_upload_enabled(self) -> bool:
        """Check if upload is enabled."""
        return self.enable_upload

    @property
    def pending_uploads(self) -> int:
        """Get number of pending uploads."""
        if self._upload_worker:
            return self._upload_worker.queue_size
        return 0
