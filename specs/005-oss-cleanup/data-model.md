# Data Model: OSS Storage Cleanup

**Feature**: 005-oss-cleanup
**Date**: 2026-01-06

## Entity Changes

### Modified Entity: RecordingSegment

**Current State**: Tracks individual video segments with upload status and file paths.

**Change**: Add `oss_deleted` field to track OSS deletion status.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `oss_deleted` | Boolean | False | Whether segment files have been deleted from OSS |

**Rationale**: Preserves audit trail while excluding deleted segments from storage calculations.

**Migration Required**: Yes - add column with default False

```sql
ALTER TABLE recording_segments ADD COLUMN oss_deleted BOOLEAN DEFAULT FALSE;
```

### No Changes: RecordingSession

The `RecordingSession` entity already has all required fields:
- `started_at`: Used for FIFO ordering
- `ended_at`: Used to identify completed (deletable) vs active (protected) sessions

### Query Views (Logical)

#### TotalOSSStorage

Aggregate view for calculating total storage used in OSS.

**Definition**:
```
SUM(file_size) WHERE upload_status = 'COMPLETED'
                 AND oss_path IS NOT NULL
                 AND oss_deleted = FALSE
```

**Returns**: Integer (bytes)

#### OldestCompletedSessions

Sessions eligible for cleanup, ordered by age.

**Definition**:
```
SELECT session.*, SUM(segment.file_size) as total_size
FROM recording_sessions session
JOIN recording_segments segment ON segment.session_id = session.id
WHERE session.ended_at IS NOT NULL
  AND segment.upload_status = 'COMPLETED'
  AND segment.oss_path IS NOT NULL
  AND segment.oss_deleted = FALSE
GROUP BY session.id
ORDER BY session.started_at ASC
```

**Returns**: List of (RecordingSession, total_size) tuples

## State Transitions

### Segment Lifecycle (Updated)

```
                                    ┌─────────────────┐
                                    │                 │
                                    ▼                 │
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│ PENDING │───▶│ UPLOADING │───▶│ COMPLETED │───▶│  DELETED  │
└─────────┘    └───────────┘    └───────────┘    └───────────┘
                    │                                   │
                    │                                   │
                    ▼                                   │
               ┌────────┐                               │
               │ FAILED │◀──────────────────────────────┘
               └────────┘        (OSS delete failure)
```

**New State**: `DELETED` (represented by `oss_deleted = True`)

**Transition: COMPLETED → DELETED**
- Trigger: Storage cleanup selects session for deletion
- Action: Delete files from OSS, set `oss_deleted = True`
- Reversible: No (files are permanently deleted from OSS)

### Session Cleanup Eligibility

```
                    ┌────────────────┐
                    │ Session Created │
                    │ (started_at set)│
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │    ACTIVE      │◄──── Protected from cleanup
                    │ (ended_at=NULL)│
                    └────────┬───────┘
                             │ Recording ends
                             ▼
                    ┌────────────────┐
                    │   COMPLETED    │◄──── Eligible for cleanup
                    │ (ended_at set) │
                    └────────┬───────┘
                             │ Storage exceeds threshold
                             ▼
                    ┌────────────────┐
                    │    CLEANED     │◄──── All segments oss_deleted=True
                    │                │
                    └────────────────┘
```

## Validation Rules

### Storage Threshold Configuration

| Rule | Validation |
|------|------------|
| Threshold value | Must be non-negative number (0 disables cleanup) |
| Unit | GB (converted to bytes internally) |
| Range | 0 to 10000 GB (practical limit) |

### Cleanup Eligibility

| Rule | Condition |
|------|-----------|
| Session must be completed | `ended_at IS NOT NULL` |
| Session must have uploaded segments | At least one segment with `upload_status = COMPLETED` |
| Segments not already deleted | `oss_deleted = FALSE` |

## Data Integrity Constraints

### Cascade Behavior

When a session's segments are cleaned up:
- Session record remains (for audit trail)
- All segment records remain with `oss_deleted = True`
- OSS files are permanently deleted

### Atomicity

Cleanup of a single session should be atomic:
- Either all segments are marked `oss_deleted = True`, or none
- On partial OSS deletion failure: log error, mark successful deletions, continue with next session
- Database transaction commits only after all OSS deletions for a session complete

## Configuration Schema

### New Config Fields in `[OSS设置]`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `启用OSS存储清理(是/否)` | Boolean (是/否) | 否 | Enable/disable automatic cleanup |
| `OSS存储清理阈值(GB)` | Float | 0 | Storage threshold in GB (0 = disabled) |

**Example**:
```ini
[OSS设置]
启用OSS上传(是/否) = 是
上传后删除本地文件(是/否) = 是
上传失败重试次数 = 3
数据库URL =
启用OSS存储清理(是/否) = 是
OSS存储清理阈值(GB) = 50
```
