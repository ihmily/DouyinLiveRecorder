# -*- coding: utf-8 -*-
"""
Aggregation service for computing unified session timelines.

Implements timeline calculation for seamless multi-segment playback.
Part of feature: 004-video-segment-aggregation
"""
from typing import List, Optional
import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
sys.path.insert(0, project_root)

# Import storage modules directly (same pattern as api.py)
import importlib.util
def _import_module_direct(module_path: str, module_name: str):
    """Import a module directly by path, bypassing package __init__.py"""
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

_storage_models = _import_module_direct(
    os.path.join(project_root, "src", "storage", "models.py"),
    "src.storage.models_agg"
)

RecordingSession = _storage_models.RecordingSession
RecordingSegment = _storage_models.RecordingSegment
Mp4Status = _storage_models.Mp4Status

from app.schemas import AggregatedSession, AggregatedSegment


def compute_aggregated_session(
    session: RecordingSession,
    segments: Optional[List[RecordingSegment]] = None
) -> AggregatedSession:
    """
    Compute an aggregated session with timeline offsets for all converted segments.

    Only includes segments where:
    - mp4_status == COMPLETED
    - duration is not None

    Args:
        session: The RecordingSession database model
        segments: Optional list of segments (if not provided, uses session.segments)

    Returns:
        AggregatedSession with computed timeline offsets
    """
    if segments is None:
        segments = session.segments

    # Filter to only converted segments with valid duration
    converted = [
        s for s in segments
        if s.mp4_status == Mp4Status.COMPLETED and s.duration is not None
    ]

    # Sort by segment index to ensure correct order
    converted.sort(key=lambda s: s.segment_index)

    # Build aggregated segments with cumulative offsets
    aggregated_segments: List[AggregatedSegment] = []
    offset = 0.0

    for seg in converted:
        duration = seg.duration or 0.0
        aggregated_segments.append(AggregatedSegment(
            segment_id=seg.id,
            segment_index=seg.segment_index,
            duration=duration,
            start_offset=offset,
            end_offset=offset + duration
        ))
        offset += duration

    # Calculate total duration
    total_duration = offset

    # Format session timestamp for URL
    session_timestamp = session.started_at.strftime('%Y-%m-%d_%H-%M-%S')

    return AggregatedSession(
        session_id=session.id,
        anchor_name=session.anchor_name,
        platform=session.platform,
        live_title=session.live_title,
        session_timestamp=session_timestamp,
        started_at=session.started_at,
        ended_at=session.ended_at,
        total_duration=total_duration,
        converted_segment_count=len(converted),
        total_segment_count=len(segments) if segments else session.segment_count or 0,
        segments=aggregated_segments
    )


def find_segment_for_position(
    aggregated_session: AggregatedSession,
    position: float
) -> Optional[tuple[AggregatedSegment, float]]:
    """
    Find which segment contains a given unified timeline position.

    Args:
        aggregated_session: The aggregated session with timeline data
        position: Position in seconds from the start of the session

    Returns:
        Tuple of (AggregatedSegment, local_position_in_segment) or None if position is out of bounds
    """
    if position < 0 or position > aggregated_session.total_duration:
        return None

    for segment in aggregated_session.segments:
        if segment.start_offset <= position < segment.end_offset:
            local_position = position - segment.start_offset
            return (segment, local_position)

    # If we're exactly at the end, return the last segment at its end
    if aggregated_session.segments and position == aggregated_session.total_duration:
        last_segment = aggregated_session.segments[-1]
        return (last_segment, last_segment.duration)

    return None
