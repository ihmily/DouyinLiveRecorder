# -*- coding: utf-8 -*-
"""
Pydantic schemas for VOD Player API responses.

Based on OpenAPI spec from contracts/openapi.yaml.
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class Platform(BaseModel):
    """Platform with recording statistics."""
    name: str = Field(..., example="抖音直播")
    anchor_count: int = Field(..., example=15)
    session_count: int = Field(..., example=120)


class Anchor(BaseModel):
    """Anchor (streamer) with session statistics."""
    name: str = Field(..., example="主播A")
    session_count: int = Field(..., example=25)
    last_live: Optional[datetime] = Field(None, example="2026-01-05T20:30:00Z")


class SessionSummary(BaseModel):
    """Summary of a recording session for list views."""
    id: int = Field(..., example=123)
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration: Optional[float] = Field(None, description="Total duration in seconds", example=9000)
    segment_count: int = Field(..., example=5)
    total_size: Optional[int] = Field(None, description="Total size in bytes", example=5368709120)


class SessionListResponse(BaseModel):
    """Paginated list of recording sessions."""
    total: int = Field(..., example=50)
    page: int = Field(1, example=1)
    limit: int = Field(20, example=20)
    items: List[SessionSummary]


class SegmentInfo(BaseModel):
    """Information about a recording segment."""
    id: int = Field(..., example=456)
    index: int = Field(..., description="Segment number (0-based)", example=0)
    duration: Optional[float] = Field(None, description="Duration in seconds", example=1800.5)
    size: Optional[int] = Field(None, description="File size in bytes", example=1073741824)
    mp4_status: str = Field(..., description="Conversion status", example="completed")


class SessionDetail(BaseModel):
    """Detailed session information with segments."""
    id: int
    platform: str
    anchor_name: str
    live_title: Optional[str] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    total_duration: Optional[float] = Field(None, description="Sum of all segment durations")
    segments: List[SegmentInfo]


class PlaybackUrl(BaseModel):
    """Presigned playback URL with metadata."""
    url: str = Field(..., description="Presigned TOS URL")
    expires_at: datetime = Field(..., description="URL expiration time")
    duration: Optional[float] = Field(None, description="Video duration in seconds")
    title: str = Field(..., description="Display title for player", example="主播A - 2026-01-05 14:00 - 分段1")


class ErrorResponse(BaseModel):
    """Error response."""
    detail: str = Field(..., example="Segment MP4 not ready, status: processing")
