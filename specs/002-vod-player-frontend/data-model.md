# Data Model: VOD Player Frontend

**Feature**: 002-vod-player-frontend
**Date**: 2026-01-06

## Entity Relationship Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ┌─────────────────┐       ┌─────────────────────────────┐ │
│  │    Platform     │       │     RecordingSession        │ │
│  │  (virtual/query)│◄──────│                             │ │
│  └─────────────────┘       │  id (PK)                    │ │
│                            │  platform                   │ │
│  ┌─────────────────┐       │  anchor_name                │ │
│  │     Anchor      │◄──────│  live_room_url              │ │
│  │  (virtual/query)│       │  live_title                 │ │
│  └─────────────────┘       │  started_at                 │ │
│                            │  ended_at                   │ │
│                            │  record_quality             │ │
│                            │  is_split                   │ │
│                            │  segment_count              │ │
│                            └──────────────┬──────────────┘ │
│                                           │ 1:N            │
│                                           ▼                │
│                            ┌─────────────────────────────┐ │
│                            │    RecordingSegment         │ │
│                            │                             │ │
│                            │  id (PK)                    │ │
│                            │  session_id (FK)            │ │
│                            │  segment_index              │ │
│                            │  local_file_path            │ │
│                            │  file_name                  │ │
│                            │  file_format                │ │
│                            │  file_size                  │ │
│                            │  oss_path                   │ │
│                            │  oss_bucket                 │ │
│                            │  upload_status              │ │
│                            │  ─────────────────────────  │ │
│                            │  mp4_oss_path      [NEW]    │ │
│                            │  mp4_status        [NEW]    │ │
│                            │  duration          [NEW]    │ │
│                            └─────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Existing Entities (No Changes)

### RecordingSession

| Field | Type | Description |
|-------|------|-------------|
| id | Integer (PK) | Auto-increment primary key |
| platform | String(100) | Platform name (e.g., "抖音直播") |
| anchor_name | String(255) | Streamer name |
| live_room_url | Text | Original live room URL |
| live_title | String(500) | Live broadcast title |
| started_at | DateTime | Recording start time |
| ended_at | DateTime | Recording end time |
| record_quality | String(20) | Quality setting |
| is_split | Boolean | Whether split recording enabled |
| segment_count | Integer | Number of segments |
| created_at | DateTime | Record creation time |
| updated_at | DateTime | Last update time |

**Relationships**:
- Has many RecordingSegments (cascade delete)

### RecordingSegment (Extended)

| Field | Type | Description | Status |
|-------|------|-------------|--------|
| id | Integer (PK) | Auto-increment primary key | Existing |
| session_id | Integer (FK) | Reference to RecordingSession | Existing |
| segment_index | Integer | Segment number (0-based) | Existing |
| local_file_path | Text | Local file path | Existing |
| file_name | String(500) | File name | Existing |
| file_format | String(20) | Format (ts/mp4/flv/mkv) | Existing |
| file_size | BigInteger | File size in bytes | Existing |
| oss_path | Text | TS file path in TOS | Existing |
| oss_bucket | String(255) | TOS bucket name | Existing |
| upload_status | Enum | pending/uploading/completed/failed/skipped | Existing |
| upload_retry_count | Integer | Upload retry attempts | Existing |
| upload_error_message | Text | Last upload error | Existing |
| local_file_deleted | Boolean | Local file removed | Existing |
| recorded_at | DateTime | Recording timestamp | Existing |
| **mp4_oss_path** | Text | **MP4 file path in TOS** | **NEW** |
| **mp4_status** | String(20) | **pending/processing/completed/failed** | **NEW** |
| **duration** | Float | **Video duration in seconds** | **NEW** |

**Relationships**:
- Belongs to RecordingSession

## Virtual Entities (Query-Based)

### Platform

Not a database table. Derived from `SELECT DISTINCT platform FROM recording_sessions`.

**API Representation**:
```json
{
  "name": "抖音直播",
  "anchor_count": 15,
  "session_count": 120
}
```

### Anchor

Not a database table. Derived from `SELECT DISTINCT anchor_name, platform FROM recording_sessions`.

**API Representation**:
```json
{
  "name": "主播A",
  "platform": "抖音直播",
  "session_count": 25,
  "last_live": "2026-01-05T20:30:00"
}
```

## State Transitions

### mp4_status State Machine

```
          ┌──────────────────────────────────────────┐
          │                                          │
          ▼                                          │
    ┌─────────┐     start      ┌────────────┐       │
    │ pending │ ─────────────▶ │ processing │       │
    └─────────┘                └─────┬──────┘       │
          ▲                          │              │
          │                    ┌─────┴─────┐        │
          │                    │           │        │
          │               success      failure      │
          │                    │           │        │
          │                    ▼           ▼        │
          │             ┌───────────┐ ┌────────┐    │
          │             │ completed │ │ failed │────┘
          │             └───────────┘ └────────┘
          │                               │
          └───────────────────────────────┘
                     retry (manual)
```

**Transition Rules**:
- `pending` → `processing`: When conversion starts
- `processing` → `completed`: FFmpeg exits with code 0, MP4 uploaded
- `processing` → `failed`: FFmpeg fails or upload fails
- `failed` → `pending`: Manual retry trigger (future feature)

## Validation Rules

### RecordingSegment

| Field | Validation |
|-------|------------|
| mp4_oss_path | Required when mp4_status = "completed" |
| mp4_status | Must be one of: pending, processing, completed, failed |
| duration | Must be > 0 when mp4_status = "completed" |
| duration | Nullable when mp4_status != "completed" |

## Database Migration

```python
# alembic/versions/xxx_add_vod_fields.py

def upgrade():
    op.add_column('recording_segments',
        sa.Column('mp4_oss_path', sa.Text(), nullable=True))
    op.add_column('recording_segments',
        sa.Column('mp4_status', sa.String(20), server_default='pending'))
    op.add_column('recording_segments',
        sa.Column('duration', sa.Float(), nullable=True))

def downgrade():
    op.drop_column('recording_segments', 'mp4_oss_path')
    op.drop_column('recording_segments', 'mp4_status')
    op.drop_column('recording_segments', 'duration')
```

## Indexes

### Existing (No Changes)
- `recording_sessions.anchor_name` (for anchor lookup)
- `recording_sessions.platform` (for platform filtering)
- `recording_segments.session_id` (FK index)
- `recording_segments.upload_status` (for upload queue)

### New Indexes
- `recording_segments.mp4_status` (for conversion queue processing)

```python
Index('ix_recording_segments_mp4_status', RecordingSegment.mp4_status)
```
