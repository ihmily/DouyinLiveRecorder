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

#### wait_for_completion

Waits for any in-progress cleanup to complete. Used during graceful shutdown.

```python
def wait_for_completion(self, timeout: float = 60.0) -> bool
```

**Parameters**:
- `timeout`: Maximum seconds to wait (default 60.0)

**Returns**: `True` if cleanup completed (or wasn't running), `False` if timeout expired

**Behavior**:
1. Attempt to acquire cleanup mutex with timeout
2. If acquired: cleanup is idle, release immediately, return True
3. If timeout: cleanup still running, return False

**Usage**: Called from `RecordingManager.stop()` during graceful shutdown

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

### Updated stop Method (Graceful Shutdown)

```python
def stop(self, graceful: bool = True) -> None:
    """
    Stop background services.

    Args:
        graceful: If True, drain upload queue before stopping (default True)
    """
    if self._upload_worker:
        if graceful:
            # Phase 1: Drain queue first (uploads will trigger cleanup)
            self.logger.info("正在等待上传队列完成...")
            self._upload_worker.drain_and_stop(timeout=120.0)
        else:
            # Immediate stop (for forced shutdown)
            self._upload_worker.stop()

    # Phase 2: Wait for any final cleanup to complete
    if self._cleanup:
        self.logger.info("等待清理任务完成...")
        if self._cleanup.wait_for_completion(timeout=60.0):
            self.logger.info("清理任务已完成")
        else:
            self.logger.warning("清理任务超时，继续退出流程")

    self.logger.info("Recording manager stopped")
```

**Shutdown Sequence** (graceful=True):
1. Drain upload queue (120s timeout) - process all pending uploads
2. Wait for cleanup completion (60s timeout) - final cleanup after last upload
3. Log completion

**What Gets Completed vs Interrupted**:
| Component | Behavior |
|-----------|----------|
| FFmpeg recording | INTERRUPTED (by main.py signal handler) |
| Pending uploads | COMPLETED (drain queue) |
| Cleanup tasks | COMPLETED (wait for lock) |

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

## UploadWorker Extensions

### New Method: drain_and_stop

```python
def drain_and_stop(self, timeout: float = 120.0) -> bool:
    """
    Stop accepting new tasks and wait for queue to drain.

    Args:
        timeout: Maximum seconds to wait for queue drain (default 120.0)

    Returns:
        True if queue drained successfully, False if timeout expired
    """
```

**Behavior**:
1. Set `_draining = True` to reject new enqueue calls
2. Wait for `queue_size == 0` with timeout
3. Set `_stop_event` to signal worker threads
4. Join worker threads (10s timeout each)
5. Return whether drain completed

**Thread Safety**: Safe to call from signal handler context

### Modified Method: enqueue

```python
def enqueue(self, task: UploadTask) -> bool:
    """
    Add task to upload queue.

    Returns:
        True if enqueued, False if worker is draining/stopped
    """
    if self._draining or not self._is_running:
        self.logger.warning(f"拒绝入队: worker正在关闭, segment_id={task.segment_id}")
        return False
    self.task_queue.put(task)
    return True
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
