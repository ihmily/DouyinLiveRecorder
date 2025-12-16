# -*- coding: utf-8 -*-
"""
Repository pattern for data access operations.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
from datetime import datetime
from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .models import RecordingSession, RecordingSegment, UploadStatus


class RecordingRepository:
    """Data access operations for recording records."""

    def __init__(self, session: Session):
        self.session = session

    # ============ Session Operations ============

    def create_session(
        self,
        anchor_name: str,
        platform: str,
        live_room_url: str,
        live_title: str | None = None,
        record_quality: str | None = None,
        is_split: bool = False
    ) -> RecordingSession:
        """Create a new recording session."""
        rec_session = RecordingSession(
            anchor_name=anchor_name,
            platform=platform,
            live_room_url=live_room_url,
            live_title=live_title,
            record_quality=record_quality,
            is_split=is_split,
            started_at=datetime.now()
        )
        self.session.add(rec_session)
        self.session.flush()  # Get ID without committing
        return rec_session

    def end_session(self, session_id: int, segment_count: int = 1) -> None:
        """Mark session as ended."""
        rec_session = self.session.query(RecordingSession).filter_by(id=session_id).first()
        if rec_session:
            rec_session.ended_at = datetime.now()
            rec_session.segment_count = segment_count

    def get_session_by_id(self, session_id: int) -> RecordingSession | None:
        """Get session by ID."""
        return self.session.query(RecordingSession).filter_by(id=session_id).first()

    def get_recent_sessions(
        self,
        anchor_name: str | None = None,
        platform: str | None = None,
        limit: int = 50
    ) -> List[RecordingSession]:
        """Get recent recording sessions with optional filters."""
        query = self.session.query(RecordingSession)
        if anchor_name:
            query = query.filter(RecordingSession.anchor_name == anchor_name)
        if platform:
            query = query.filter(RecordingSession.platform == platform)
        return query.order_by(RecordingSession.created_at.desc()).limit(limit).all()

    # ============ Segment Operations ============

    def add_segment(
        self,
        session_id: int,
        local_file_path: str,
        file_name: str,
        file_format: str,
        file_size: int | None = None,
        segment_index: int = 0
    ) -> RecordingSegment:
        """Add a recording segment."""
        segment = RecordingSegment(
            session_id=session_id,
            segment_index=segment_index,
            local_file_path=local_file_path,
            file_name=file_name,
            file_format=file_format,
            file_size=file_size,
            upload_status=UploadStatus.PENDING,
            recorded_at=datetime.now()
        )
        self.session.add(segment)
        self.session.flush()
        return segment

    def get_segment_by_id(self, segment_id: int) -> RecordingSegment | None:
        """Get segment by ID."""
        return self.session.query(RecordingSegment).filter_by(id=segment_id).first()

    def get_segments_by_session(self, session_id: int) -> List[RecordingSegment]:
        """Get all segments for a session."""
        return self.session.query(RecordingSegment).filter_by(
            session_id=session_id
        ).order_by(RecordingSegment.segment_index).all()

    def get_pending_uploads(self, limit: int = 10) -> List[RecordingSegment]:
        """Get segments pending upload."""
        return self.session.query(RecordingSegment).filter(
            RecordingSegment.upload_status == UploadStatus.PENDING
        ).order_by(RecordingSegment.created_at).limit(limit).all()

    def get_failed_uploads(self, max_retries: int = 3) -> List[RecordingSegment]:
        """Get failed uploads eligible for retry."""
        return self.session.query(RecordingSegment).filter(
            and_(
                RecordingSegment.upload_status == UploadStatus.FAILED,
                RecordingSegment.upload_retry_count < max_retries
            )
        ).all()

    def update_upload_status(
        self,
        segment_id: int,
        status: UploadStatus,
        oss_path: str | None = None,
        oss_bucket: str | None = None,
        error_message: str | None = None
    ) -> None:
        """Update segment upload status."""
        segment = self.session.query(RecordingSegment).filter_by(id=segment_id).first()
        if segment:
            segment.upload_status = status
            if status == UploadStatus.UPLOADING:
                segment.upload_started_at = datetime.now()
            elif status == UploadStatus.COMPLETED:
                segment.upload_completed_at = datetime.now()
                segment.oss_path = oss_path
                segment.oss_bucket = oss_bucket
            elif status == UploadStatus.FAILED:
                segment.upload_retry_count += 1
                segment.upload_error_message = error_message

    def mark_local_deleted(self, segment_id: int) -> None:
        """Mark local file as deleted."""
        segment = self.session.query(RecordingSegment).filter_by(id=segment_id).first()
        if segment:
            segment.local_file_deleted = True

    # ============ Statistics ============

    def get_upload_stats(self) -> dict:
        """Get upload statistics."""
        total = self.session.query(RecordingSegment).count()
        pending = self.session.query(RecordingSegment).filter_by(
            upload_status=UploadStatus.PENDING
        ).count()
        uploading = self.session.query(RecordingSegment).filter_by(
            upload_status=UploadStatus.UPLOADING
        ).count()
        completed = self.session.query(RecordingSegment).filter_by(
            upload_status=UploadStatus.COMPLETED
        ).count()
        failed = self.session.query(RecordingSegment).filter_by(
            upload_status=UploadStatus.FAILED
        ).count()

        return {
            "total": total,
            "pending": pending,
            "uploading": uploading,
            "completed": completed,
            "failed": failed
        }
