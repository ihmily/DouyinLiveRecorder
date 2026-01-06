# Data Model: OSS Storage Cleanup

**Feature**: 005-oss-cleanup
**Date**: 2026-01-06

## Entity Changes

### No Schema Changes Required

**Approach**: Hard delete records after OSS cleanup (no new fields needed)

When a session is cleaned up:
1. Delete OSS files (TS and MP4)
2. Delete all `RecordingSegment` records for the session
3. Delete the `RecordingSession` record

**Rationale**:
- Simpler implementation - no database migration required
- Database stays clean - only contains active/valid data
- Storage calculation remains simple (sum all existing records)

### Existing Entities (No Modifications)

#### RecordingSession

The `RecordingSession` entity already has all required fields:
- `started_at`: Used for FIFO ordering
- `ended_at`: Used to identify completed (deletable) vs active (protected) sessions

#### RecordingSegment

The `RecordingSegment` entity already has all required fields:
- `file_size`: Used for storage calculation
- `oss_path`: Used to identify files to delete
- `mp4_oss_path`: Used to identify MP4 files to delete
- `upload_status`: Used to filter completed uploads

### Query Views (Logical)

#### TotalOSSStorage

Aggregate view for calculating total storage used in OSS.

**Definition**:
```
SUM(file_size) WHERE upload_status = 'COMPLETED'
                 AND oss_path IS NOT NULL
```

**Returns**: Integer (bytes)

**Note**: Since we hard delete records, no need to filter by deletion status.

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
GROUP BY session.id
ORDER BY session.started_at ASC
```

**Returns**: List of (RecordingSession, total_size) tuples

## State Transitions

### Segment Lifecycle

```
┌─────────┐    ┌───────────┐    ┌───────────┐    ┌───────────┐
│ PENDING │───▶│ UPLOADING │───▶│ COMPLETED │───▶│ [DELETED] │
└─────────┘    └───────────┘    └───────────┘    └───────────┘
                    │                                   │
                    ▼                                   │
               ┌────────┐                               │
               │ FAILED │                               │
               └────────┘                               │
```

**Note**: `[DELETED]` means the record is removed from the database entirely.

**Transition: COMPLETED → [DELETED]**
- Trigger: Storage cleanup selects session for deletion
- Action: Delete OSS files, then delete database records
- Result: No record remains in database

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
                    │   [REMOVED]    │◄──── Record deleted from DB
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
| Session must have OSS files | At least one segment with `oss_path IS NOT NULL` |

## Data Integrity Constraints

### Cascade Behavior

When a session is cleaned up:
- All segment records are deleted from database
- Session record is deleted from database
- OSS files are permanently deleted

### Deletion Order

To maintain referential integrity:
1. Delete OSS files first (can be retried if failed)
2. Delete segment records
3. Delete session record
4. Commit transaction

### Atomicity

Cleanup of a single session should be atomic:
- OSS deletion: Best effort, log errors, continue
- Database deletion: All records deleted in single transaction
- On partial OSS failure: Still delete records (files may be orphaned, but that's acceptable)

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
