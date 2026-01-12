# -*- coding: utf-8 -*-
"""
VOD Player API routes.

Implements endpoints for navigation and playback URL generation.
"""
import os
import sys
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy import func, distinct
from sqlalchemy.orm import Session

# Add project root to path
# In Docker: /src is mounted directly, so project_root = "/"
# In local dev: vod-player/backend/app/routers/api.py -> 5 levels up to DouyinLiveRecorder
if os.path.exists("/src/storage/models.py"):
    # Docker environment - src is mounted at /src
    project_root = "/"
else:
    # Local development
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, project_root)

# Import storage modules directly to avoid src/__init__.py initialization (requires distro, node check, etc.)
import importlib.util
def _import_module_direct(module_path: str, module_name: str):
    """Import a module directly by path, bypassing package __init__.py"""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Load storage modules without triggering src/__init__.py
_storage_models = _import_module_direct(
    os.path.join(project_root, "src", "storage", "models.py"),
    "src.storage.models"
)
_storage_database = _import_module_direct(
    os.path.join(project_root, "src", "storage", "database.py"),
    "src.storage.database"
)

DatabaseManager = _storage_database.DatabaseManager
RecordingSession = _storage_models.RecordingSession
RecordingSegment = _storage_models.RecordingSegment
Mp4Status = _storage_models.Mp4Status
from app.schemas import (
    Platform, Anchor, SessionSummary, SessionListResponse,
    SessionDetail, SegmentInfo, PlaybackUrl, ErrorResponse,
    AggregatedSession, BatchPlaybackUrls, BatchPlaybackUrlsRequest
)
from app.config import get_settings
from app.services.tos_sign import generate_presigned_url
from app.services.aggregation import compute_aggregated_session

router = APIRouter()


def get_db() -> Session:
    """Dependency to get database session."""
    db = DatabaseManager.get_instance()
    session = db.get_new_session()
    try:
        yield session
    finally:
        session.close()


# T014: GET /platforms - List all platforms
@router.get("/platforms", response_model=List[Platform], tags=["Navigation"])
async def list_platforms(db: Session = Depends(get_db)):
    """List all platforms with statistics."""
    # Query platforms with counts
    results = db.query(
        RecordingSession.platform,
        func.count(distinct(RecordingSession.anchor_name)).label("anchor_count"),
        func.count(RecordingSession.id).label("session_count")
    ).group_by(RecordingSession.platform).all()

    return [
        Platform(
            name=row.platform,
            anchor_count=row.anchor_count,
            session_count=row.session_count
        )
        for row in results
    ]


# T015: GET /platforms/{platform}/anchors - List anchors for a platform
@router.get("/platforms/{platform}/anchors", response_model=List[Anchor], tags=["Navigation"])
async def list_anchors(platform: str, db: Session = Depends(get_db)):
    """List anchors for a specific platform."""
    # Query anchors with session counts and last live time
    results = db.query(
        RecordingSession.anchor_name,
        func.count(RecordingSession.id).label("session_count"),
        func.max(RecordingSession.started_at).label("last_live")
    ).filter(
        RecordingSession.platform == platform
    ).group_by(
        RecordingSession.anchor_name
    ).order_by(
        func.max(RecordingSession.started_at).desc()
    ).all()

    return [
        Anchor(
            name=row.anchor_name,
            session_count=row.session_count,
            last_live=row.last_live
        )
        for row in results
    ]


# T016: GET /anchors/{anchor_name}/sessions - List sessions with pagination
@router.get("/anchors/{anchor_name}/sessions", response_model=SessionListResponse, tags=["Navigation"])
async def list_sessions(
    anchor_name: str,
    platform: Optional[str] = Query(None, description="Filter by platform"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """List recording sessions for an anchor with pagination."""
    # Base query
    query = db.query(RecordingSession).filter(
        RecordingSession.anchor_name == anchor_name
    )

    if platform:
        query = query.filter(RecordingSession.platform == platform)

    # Get total count
    total = query.count()

    # Get paginated results
    sessions = query.order_by(
        RecordingSession.started_at.desc()
    ).offset(
        (page - 1) * limit
    ).limit(limit).all()

    # Calculate total duration and size for each session
    items = []
    for session in sessions:
        total_duration = sum(
            seg.duration or 0 for seg in session.segments
            if seg.mp4_status == Mp4Status.COMPLETED
        )
        total_size = sum(seg.file_size or 0 for seg in session.segments)

        items.append(SessionSummary(
            id=session.id,
            started_at=session.started_at,
            ended_at=session.ended_at,
            duration=total_duration if total_duration > 0 else None,
            segment_count=len(session.segments),
            total_size=total_size if total_size > 0 else None
        ))

    return SessionListResponse(
        total=total,
        page=page,
        limit=limit,
        items=items
    )


# T017: GET /sessions/{session_id} - Get session details with segments
@router.get("/sessions/{session_id}", response_model=SessionDetail, tags=["Sessions"])
async def get_session(session_id: int, db: Session = Depends(get_db)):
    """Get session details with all segments."""
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Build segment list
    segments = [
        SegmentInfo(
            id=seg.id,
            index=seg.segment_index,
            duration=seg.duration,
            size=seg.file_size,
            mp4_status=seg.mp4_status.value if seg.mp4_status else "pending"
        )
        for seg in sorted(session.segments, key=lambda s: s.segment_index)
    ]

    # Calculate total duration
    total_duration = sum(
        seg.duration or 0 for seg in session.segments
        if seg.mp4_status == Mp4Status.COMPLETED
    )

    return SessionDetail(
        id=session.id,
        platform=session.platform,
        anchor_name=session.anchor_name,
        live_title=session.live_title,
        started_at=session.started_at,
        ended_at=session.ended_at,
        total_duration=total_duration if total_duration > 0 else None,
        segments=segments
    )


# T019: GET /segments/{segment_id}/play - Get presigned playback URL
@router.get(
    "/segments/{segment_id}/play",
    response_model=PlaybackUrl,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["Playback"]
)
async def get_play_url(segment_id: int, db: Session = Depends(get_db)):
    """Get presigned playback URL for a segment."""
    settings = get_settings()

    segment = db.query(RecordingSegment).filter(
        RecordingSegment.id == segment_id
    ).first()

    if not segment:
        raise HTTPException(status_code=404, detail="Segment not found")

    # Check if MP4 is ready
    if segment.mp4_status != Mp4Status.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Segment MP4 not ready, status: {segment.mp4_status.value if segment.mp4_status else 'unknown'}"
        )

    if not segment.mp4_oss_path:
        raise HTTPException(
            status_code=400,
            detail="Segment MP4 path not available"
        )

    # Generate presigned URL
    try:
        url = generate_presigned_url(
            bucket=segment.oss_bucket or settings.tos_bucket,
            key=segment.mp4_oss_path,
            expires=settings.url_expiration_seconds
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate playback URL: {str(e)}"
        )

    # Calculate expiration time
    expires_at = datetime.utcnow() + timedelta(seconds=settings.url_expiration_seconds)

    # Build title
    session = segment.session
    title = f"{session.anchor_name} - {session.started_at.strftime('%Y-%m-%d %H:%M')} - 分段{segment.segment_index + 1}"

    return PlaybackUrl(
        url=url,
        expires_at=expires_at,
        duration=segment.duration,
        title=title
    )


# === Video Segment Aggregation Endpoints (004-video-segment-aggregation) ===

# T008: GET /sessions/{session_id}/aggregated - Get aggregated session with timeline
@router.get(
    "/sessions/{session_id}/aggregated",
    response_model=AggregatedSession,
    responses={404: {"model": ErrorResponse}},
    tags=["Sessions"]
)
async def get_aggregated_session(session_id: int, db: Session = Depends(get_db)):
    """
    Get aggregated session with computed timeline offsets for all converted segments.

    Only segments with mp4_status=COMPLETED are included in the timeline.
    """
    session = db.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return compute_aggregated_session(session)


# T009: GET /sessions/by-path/{anchor_name}/{session_timestamp} - Lookup by human-readable path
@router.get(
    "/sessions/by-path/{anchor_name}/{session_timestamp}",
    response_model=AggregatedSession,
    responses={404: {"model": ErrorResponse}},
    tags=["Sessions"]
)
async def get_session_by_path(
    anchor_name: str,
    session_timestamp: str,
    db: Session = Depends(get_db)
):
    """
    Get aggregated session by anchor name and timestamp.

    Lookup session using human-readable URL components.
    The session_timestamp should be in format: YYYY-MM-DD_HH-MM-SS
    """
    # Parse the timestamp format from URL (YYYY-MM-DD_HH-MM-SS) to datetime
    try:
        from datetime import datetime as dt
        parsed_time = dt.strptime(session_timestamp, '%Y-%m-%d_%H-%M-%S')
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid timestamp format. Expected: YYYY-MM-DD_HH-MM-SS, got: {session_timestamp}"
        )

    # Find session matching anchor name and start time
    # Use time range to handle microseconds and minor timestamp differences
    time_window_start = parsed_time
    time_window_end = parsed_time + timedelta(seconds=1)

    session = db.query(RecordingSession).filter(
        RecordingSession.anchor_name == anchor_name,
        RecordingSession.started_at >= time_window_start,
        RecordingSession.started_at < time_window_end
    ).first()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return compute_aggregated_session(session)


# T010: POST /segments/batch-urls - Batch fetch presigned URLs
@router.post(
    "/segments/batch-urls",
    response_model=BatchPlaybackUrls,
    tags=["Playback"]
)
async def batch_get_play_urls(
    request: BatchPlaybackUrlsRequest,
    db: Session = Depends(get_db)
):
    """
    Batch fetch presigned playback URLs for multiple segments.

    Useful for pre-fetching next segment URLs during playback.
    Maximum 5 segment IDs per request.
    """
    settings = get_settings()

    urls = {}
    failed = []

    # Fetch all requested segments in one query
    segments = db.query(RecordingSegment).filter(
        RecordingSegment.id.in_(request.segment_ids)
    ).all()

    # Create a lookup map
    segment_map = {seg.id: seg for seg in segments}

    for segment_id in request.segment_ids:
        segment = segment_map.get(segment_id)

        if not segment:
            failed.append(segment_id)
            continue

        # Check if MP4 is ready
        if segment.mp4_status != Mp4Status.COMPLETED or not segment.mp4_oss_path:
            failed.append(segment_id)
            continue

        # Generate presigned URL
        try:
            url = generate_presigned_url(
                bucket=segment.oss_bucket or settings.tos_bucket,
                key=segment.mp4_oss_path,
                expires=settings.url_expiration_seconds
            )

            expires_at = datetime.utcnow() + timedelta(seconds=settings.url_expiration_seconds)

            # Build title
            session = segment.session
            title = f"{session.anchor_name} - {session.started_at.strftime('%Y-%m-%d %H:%M')} - 分段{segment.segment_index + 1}"

            urls[str(segment_id)] = PlaybackUrl(
                url=url,
                expires_at=expires_at,
                duration=segment.duration,
                title=title
            )
        except Exception:
            failed.append(segment_id)

    return BatchPlaybackUrls(urls=urls, failed=failed)
