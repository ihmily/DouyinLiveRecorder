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

# Add project root to path (vod-player/backend/app/routers/api.py -> 5 levels up to DouyinLiveRecorder)
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
    SessionDetail, SegmentInfo, PlaybackUrl, ErrorResponse
)
from app.config import get_settings
from app.services.tos_sign import generate_presigned_url

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
