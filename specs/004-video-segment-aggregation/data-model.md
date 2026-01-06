# Data Model: Video Segment Aggregation

**Feature**: 004-video-segment-aggregation
**Date**: 2026-01-06

## Overview

This feature extends the existing data model with computed/virtual entities for aggregated playback. No database schema changes are required - all aggregation is computed at runtime from existing `RecordingSession` and `RecordingSegment` tables.

---

## Existing Entities (No Changes)

### RecordingSession

| Field | Type | Description |
|-------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| anchor_name | String | Streamer/anchor name |
| platform | String | Platform name (e.g., "抖音直播") |
| live_room_url | String | Original room URL |
| live_title | String (nullable) | Stream title |
| started_at | DateTime | Session start time |
| ended_at | DateTime (nullable) | Session end time |
| record_quality | String | Recording quality setting |
| is_split | Boolean | Whether split recording was enabled |
| segment_count | Integer | Total segment count |
| created_at | DateTime | Record creation time |
| updated_at | DateTime | Last update time |

### RecordingSegment

| Field | Type | Description |
|-------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| session_id | Integer (FK) | Reference to RecordingSession |
| segment_index | Integer | 0-based position in sequence |
| local_file_path | String | Full path to file |
| file_name | String | Filename only |
| file_format | String | ts/mp4/flv/mkv |
| file_size | Integer (nullable) | Bytes |
| duration | Float (nullable) | Seconds (from MP4 metadata) |
| mp4_status | Enum | pending/processing/completed/failed |
| mp4_oss_path | String (nullable) | OSS path for converted MP4 |
| oss_bucket | String (nullable) | TOS bucket name |
| recorded_at | DateTime | When segment was recorded |
| created_at | DateTime | Record creation time |
| updated_at | DateTime | Last update time |

---

## New Computed Entities (Runtime Only)

### AggregatedSession

Computed from RecordingSession + filtered RecordingSegment list.

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| session_id | Integer | RecordingSession.id | Original session ID |
| anchor_name | String | RecordingSession.anchor_name | Streamer name |
| platform | String | RecordingSession.platform | Platform name |
| live_title | String | RecordingSession.live_title | Stream title |
| session_timestamp | String | Computed | Format: YYYY-MM-DD_HH-MM-SS from started_at |
| total_duration | Float | Computed | Sum of converted segment durations |
| converted_segment_count | Integer | Computed | Count where mp4_status = COMPLETED |
| total_segment_count | Integer | RecordingSession.segment_count | All segments (for progress indicator) |
| segments | AggregatedSegment[] | Computed | Ordered list with offsets |

**Computation Logic**:
```python
def compute_aggregated_session(session: RecordingSession, segments: List[RecordingSegment]) -> AggregatedSession:
    converted = [s for s in segments if s.mp4_status == 'completed' and s.duration]
    converted.sort(key=lambda s: s.segment_index)

    total_duration = sum(s.duration for s in converted)

    aggregated_segments = []
    offset = 0.0
    for seg in converted:
        aggregated_segments.append(AggregatedSegment(
            segment_id=seg.id,
            segment_index=seg.segment_index,
            duration=seg.duration,
            start_offset=offset,
            end_offset=offset + seg.duration
        ))
        offset += seg.duration

    return AggregatedSession(
        session_id=session.id,
        anchor_name=session.anchor_name,
        platform=session.platform,
        live_title=session.live_title,
        session_timestamp=session.started_at.strftime('%Y-%m-%d_%H-%M-%S'),
        total_duration=total_duration,
        converted_segment_count=len(converted),
        total_segment_count=session.segment_count,
        segments=aggregated_segments
    )
```

### AggregatedSegment

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| segment_id | Integer | RecordingSegment.id | Database ID |
| segment_index | Integer | RecordingSegment.segment_index | Original index |
| duration | Float | RecordingSegment.duration | Segment duration (seconds) |
| start_offset | Float | Computed | Cumulative start position |
| end_offset | Float | Computed | Cumulative end position |

### SegmentTimeline (Frontend Only)

Used for seek calculations and progress bar rendering.

```typescript
interface SegmentTimeline {
  sessionId: number;
  anchorName: string;
  sessionTimestamp: string;
  totalDuration: number;
  segments: TimelineSegment[];
}

interface TimelineSegment {
  segmentId: number;
  segmentIndex: number;
  duration: number;
  startOffset: number;  // seconds from session start
  endOffset: number;    // startOffset + duration
}
```

### PlaybackState (localStorage)

Persisted in browser for resume functionality.

```typescript
interface PlaybackState {
  sessionKey: string;       // "{anchor_name}_{session_timestamp}"
  position: number;         // Cumulative position in seconds
  currentSegmentId: number; // Active segment ID
  savedAt: number;          // Unix timestamp (ms)
}
```

**Storage Key**: `vod_position_{sessionKey}`

**Validation Rules**:
- `position` must be >= 0 and <= totalDuration
- `currentSegmentId` must exist in session
- `savedAt` must be within 30 days (configurable expiry)

---

## State Transitions

### Segment Playback States

```
[Not Started] → [Loading] → [Playing] → [Ended]
                    ↓           ↓
                [Error]    [Paused]
                              ↓
                          [Seeking] → [Playing]
```

### Aggregated Session States

```
[Idle] → [Loading Session] → [Ready]
                ↓               ↓
           [Error]      [Playing Segment N]
                              ↓
                        [Transitioning to N+1]
                              ↓
                        [Playing Segment N+1]
                              ↓
                        [Session Complete]
```

---

## Relationships

```
RecordingSession (1) ──────────────< RecordingSegment (N)
       │                                    │
       │ computed                           │ filtered (mp4_status = completed)
       ↓                                    ↓
AggregatedSession (1) ─────────────< AggregatedSegment (N)
       │
       │ stored in browser
       ↓
PlaybackState (1)
```

---

## Data Volume Considerations

| Entity | Expected Count | Notes |
|--------|---------------|-------|
| RecordingSession | 100-1000 | Per month, depends on usage |
| RecordingSegment | 500-5000 | ~5-10 segments per session |
| AggregatedSession | 1 | Per active player view |
| PlaybackState | 10-50 | Per browser, with 30-day expiry |

No performance concerns - aggregation is done on small datasets (typically < 20 segments per session).
