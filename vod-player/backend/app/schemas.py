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


# === Video Segment Aggregation Schemas (004-video-segment-aggregation) ===

class AggregatedSegment(BaseModel):
    """Segment with computed timeline offsets for aggregated playback."""
    segment_id: int = Field(..., description="Database segment ID", example=101)
    segment_index: int = Field(..., description="Original segment index (0-based)", example=0)
    duration: float = Field(..., description="Segment duration in seconds", example=600.0)
    start_offset: float = Field(..., description="Cumulative start position in session timeline", example=0.0)
    end_offset: float = Field(..., description="Cumulative end position (start_offset + duration)", example=600.0)


class AggregatedSession(BaseModel):
    """Session with computed timeline data for seamless multi-segment playback."""
    session_id: int = Field(..., description="Database session ID", example=13)
    anchor_name: str = Field(..., description="Streamer/anchor name", example="Seven(国服老虎)")
    platform: str = Field(..., description="Platform name", example="抖音直播")
    live_title: Optional[str] = Field(None, description="Original stream title", example="王者荣耀直播")
    session_timestamp: str = Field(..., description="Session start time formatted for URL", example="2026-01-06_14-01-37")
    started_at: datetime = Field(..., description="ISO format start time")
    ended_at: Optional[datetime] = Field(None, description="ISO format end time")
    total_duration: float = Field(..., description="Total playable duration in seconds (converted segments only)", example=3600.5)
    converted_segment_count: int = Field(..., description="Number of segments with mp4_status=COMPLETED", example=6)
    total_segment_count: int = Field(..., description="Total segment count (for progress display)", example=7)
    segments: List[AggregatedSegment] = Field(..., description="Ordered list of playable segments with offsets")


class BatchPlaybackUrlsRequest(BaseModel):
    """Request for batch fetching playback URLs."""
    segment_ids: List[int] = Field(..., max_length=5, description="List of segment IDs (max 5)", example=[101, 102, 103])


class BatchPlaybackUrls(BaseModel):
    """Response with multiple presigned playback URLs."""
    urls: dict[str, PlaybackUrl] = Field(..., description="Map of segment_id to PlaybackUrl")
    failed: List[int] = Field(default_factory=list, description="Segment IDs that could not be fetched (not ready)")
