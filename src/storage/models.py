# -*- coding: utf-8 -*-
"""
Database models for recording file management.

Author: DouyinLiveRecorder
Date: 2025-12-16
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    Column, Integer, String, DateTime, BigInteger, Float,
    ForeignKey, Enum as SQLEnum, Text, Boolean
)
from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column

Base = declarative_base()


class UploadStatus(str, Enum):
    """Upload status enumeration."""
    PENDING = "pending"           # Waiting to upload
    UPLOADING = "uploading"       # Currently uploading
    COMPLETED = "completed"       # Upload successful
    FAILED = "failed"             # Upload failed (after retries)
    SKIPPED = "skipped"           # Skipped (e.g., file not found)


class Mp4Status(str, Enum):
    """MP4 conversion status enumeration for VOD playback."""
    PENDING = "pending"           # Waiting to convert
    PROCESSING = "processing"     # Currently converting
    COMPLETED = "completed"       # Conversion successful, MP4 uploaded
    FAILED = "failed"             # Conversion failed


class RecordingSession(Base):
    """
    Represents a single live recording session (one broadcast).
    A session can have multiple segments if split_video_by_time is enabled.
    """
    __tablename__ = "recording_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Anchor information
    anchor_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    live_room_url: Mapped[str] = mapped_column(Text, nullable=False)
    live_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Recording metadata
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    record_quality: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Session status
    is_split: Mapped[bool] = mapped_column(Boolean, default=False)
    segment_count: Mapped[int] = mapped_column(Integer, default=1)

    # Relationships
    segments: Mapped[List["RecordingSegment"]] = relationship(
        "RecordingSegment",
        back_populates="session",
        cascade="all, delete-orphan"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<RecordingSession(id={self.id}, anchor={self.anchor_name}, platform={self.platform})>"


class RecordingSegment(Base):
    """
    Represents a single recorded file segment.
    For non-split recordings, there will be one segment per session.
    For split recordings, multiple segments belong to one session.
    """
    __tablename__ = "recording_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Parent session reference
    session_id: Mapped[int] = mapped_column(Integer, ForeignKey("recording_sessions.id"), nullable=False, index=True)
    session: Mapped["RecordingSession"] = relationship("RecordingSession", back_populates="segments")

    # Segment identification
    segment_index: Mapped[int] = mapped_column(Integer, default=0)

    # File information
    local_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # OSS information
    oss_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    oss_bucket: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Upload status tracking
    upload_status: Mapped[UploadStatus] = mapped_column(
        SQLEnum(UploadStatus),
        default=UploadStatus.PENDING,
        index=True
    )
    upload_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    upload_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    upload_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    upload_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Local file status
    local_file_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # VOD playback fields (for MP4 conversion)
    mp4_oss_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mp4_status: Mapped[Mp4Status] = mapped_column(
        SQLEnum(Mp4Status),
        default=Mp4Status.PENDING,
        index=True
    )
    duration: Mapped[Optional[float]] = mapped_column(nullable=True)

    # Timestamps
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<RecordingSegment(id={self.id}, file={self.file_name}, status={self.upload_status})>"
