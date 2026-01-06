# Internal API Contracts: OSS Storage Cleanup

**Feature**: 005-oss-cleanup
**Date**: 2026-01-06

> Note: This feature does not expose external APIs. These are internal Python interfaces.

## StorageCleanup Class

### Constructor

```python
class StorageCleanup:
    def __init__(
        self,
        repository: RecordingRepository,
        tos_uploader: TOSUploader,
        threshold_bytes: int,
        enabled: bool = True
    )
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `repository` | RecordingRepository | Data access layer for database operations |
| `tos_uploader` | TOSUploader | OSS client for file deletion |
| `threshold_bytes` | int | Storage threshold in bytes (0 disables cleanup) |
| `enabled` | bool | Whether cleanup is enabled |

### Methods

#### trigger_cleanup

Triggers cleanup check. Blocks until cleanup completes (or determines no cleanup needed).

```python
def trigger_cleanup(self) -> CleanupResult
```

**Returns**: `CleanupResult` dataclass

**Thread Safety**: Uses internal mutex. Multiple concurrent calls will queue and execute sequentially.

**Behavior**:
1. Acquire mutex (blocks if another cleanup in progress)
2. Calculate current storage usage
3. If below threshold: release mutex, return
4. Select oldest completed sessions until target freed
5. Delete each session's files from OSS
6. Update database records
7. Release mutex, return result

#### get_storage_stats

Returns current storage statistics without triggering cleanup.

```python
def get_storage_stats(self) -> StorageStats
```

**Returns**: `StorageStats` dataclass

---

## Data Classes

### CleanupResult

```python
@dataclass
class CleanupResult:
    triggered: bool          # Whether cleanup was needed
    sessions_deleted: int    # Number of sessions deleted
    bytes_freed: int         # Total bytes freed
    errors: list[str]        # Any errors encountered
    duration_seconds: float  # Time taken
```

### StorageStats

```python
@dataclass
class StorageStats:
    total_bytes: int         # Current OSS storage usage
    threshold_bytes: int     # Configured threshold
    over_threshold: bool     # Whether storage exceeds threshold
    sessions_count: int      # Number of completed sessions
```

---

## RecordingRepository Extensions

### New Methods

#### get_total_oss_storage

```python
def get_total_oss_storage(self) -> int
```

**Returns**: Total bytes of uploaded segments (excluding deleted)

**Query Logic**:
- Sum `file_size` where `upload_status = COMPLETED`
- And `oss_path IS NOT NULL`

#### get_oldest_completed_sessions

```python
def get_oldest_completed_sessions(self, limit: int = 10) -> list[tuple[RecordingSession, int]]
```

**Parameters**:
- `limit`: Maximum sessions to return

**Returns**: List of (session, total_size_bytes) tuples, ordered by `started_at` ASC

**Query Logic**:
- Filter: `ended_at IS NOT NULL` (completed only)
- Filter: Has at least one segment with `oss_path IS NOT NULL`
- Group by session, sum segment file sizes
- Order by `started_at` ascending

#### get_session_segments_for_cleanup

```python
def get_session_segments_for_cleanup(self, session_id: int) -> list[RecordingSegment]
```

**Returns**: All segments for a session that have files to delete from OSS

**Filter**: `oss_path IS NOT NULL`

#### delete_session_with_segments

```python
def delete_session_with_segments(self, session_id: int) -> None
```

**Parameters**:
- `session_id`: ID of the session to delete

**Action**: Delete all segment records for the session, then delete the session record itself

**Note**: This is a hard delete - records are permanently removed from the database

---

## TOSUploader (Existing, No Changes)

The existing `delete_object` method is sufficient:

```python
def delete_object(self, oss_key: str, bucket: str = None) -> bool
```

**Parameters**:
- `oss_key`: Object key to delete
- `bucket`: Optional bucket override (uses default if not specified)

**Returns**: `True` if successful, `False` if error

**Idempotency**: Deleting non-existent object returns success

---

## RecordingManager Extensions

### New Property

#### cleanup

```python
@property
def cleanup(self) -> StorageCleanup | None
```

**Returns**: StorageCleanup instance if enabled, None otherwise

### Updated Factory Method

```python
@classmethod
def from_config(
    cls,
    config_file: str,
    tos_config_file: str,
    database_url: str = None
) -> RecordingManager
```

**New Config Parsing**:
- Read `启用OSS存储清理(是/否)` → `cleanup_enabled`
- Read `OSS存储清理阈值(GB)` → `cleanup_threshold_gb`
- Convert GB to bytes: `threshold_bytes = cleanup_threshold_gb * 1024^3`

### Integration Hook

The `on_upload_complete` callback triggers cleanup:

```python
def _on_upload_complete(self, segment_id: int) -> None:
    # ... existing logic ...
    if self._cleanup:
        result = self._cleanup.trigger_cleanup()
        if result.triggered:
            logger.info(f"Cleanup freed {result.bytes_freed} bytes")
```

---

## Error Handling

### Cleanup Errors

| Error Type | Handling |
|------------|----------|
| OSS deletion fails | Log error, continue with other segments, include in `CleanupResult.errors` |
| Database error | Log error, abort current session cleanup, continue with next session |
| Lock acquisition timeout | N/A (uses blocking lock, will wait indefinitely) |

### Logging Format

```
INFO  | OSS cleanup triggered: current={current_bytes}, threshold={threshold_bytes}
INFO  | Deleting session {session_id} ({anchor_name}, started {started_at})
INFO  | Deleted segment {segment_id}: {oss_path}
INFO  | Deleted segment {segment_id} MP4: {mp4_oss_path}
ERROR | Failed to delete {oss_path}: {error_message}
INFO  | OSS cleanup complete: {sessions_deleted} sessions, {bytes_freed} bytes freed in {duration}s
```
