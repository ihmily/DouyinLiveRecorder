# Research: OSS Storage Cleanup

**Feature**: 005-oss-cleanup
**Date**: 2026-01-06

## Research Questions & Findings

### 1. Threading Mutex Pattern for Blocking Cleanup

**Question**: How to implement thread-safe blocking cleanup where only one cleanup runs at a time and others wait?

**Decision**: Use `threading.Lock()` with standard `acquire()` (blocking by default)

**Rationale**:
- Python's `threading.Lock` is a mutex that blocks by default when `acquire()` is called
- Multiple threads calling `acquire()` will queue up and wait
- Simple, well-understood pattern already used in the codebase
- Meets requirement FR-009 (only one cleanup at a time) and FR-010 (others block and wait)

**Alternatives Considered**:
- `threading.RLock()`: Reentrant lock - not needed since same thread won't call cleanup recursively
- `threading.Semaphore(1)`: Functionally identical to Lock for this use case, but Lock is more explicit
- `asyncio.Lock()`: Would require refactoring upload callbacks to async - unnecessary complexity

**Implementation Pattern**:
```python
class StorageCleanup:
    def __init__(self):
        self._cleanup_lock = threading.Lock()

    def trigger_cleanup_if_needed(self):
        with self._cleanup_lock:  # Blocks until lock acquired
            # Re-check storage after acquiring lock (FR-011)
            current_usage = self._get_total_storage()
            if current_usage > self.threshold:
                self._perform_cleanup()
```

---

### 2. Storage Calculation from Database

**Question**: How to efficiently calculate total OSS storage from database records?

**Decision**: SQL aggregation query on `RecordingSegment.file_size` for uploaded segments

**Rationale**:
- Database already stores `file_size` for each segment (BigInteger field)
- SQL `SUM()` is efficient even for thousands of segments
- Only count segments with `upload_status = COMPLETED` and valid `oss_path`
- Database is source of truth per spec assumptions

**Query Pattern**:
```python
def get_total_oss_storage(self, session) -> int:
    result = session.query(func.sum(RecordingSegment.file_size)).filter(
        RecordingSegment.upload_status == UploadStatus.COMPLETED,
        RecordingSegment.oss_path.isnot(None)
    ).scalar()
    return result or 0
```

**Alternatives Considered**:
- Listing objects directly from TOS: Slow, rate-limited, and may not match DB records
- Maintaining a running total counter: Risk of drift, complex to maintain atomicity
- Periodic full recalculation: Adds latency, but could be used for periodic reconciliation (future feature)

---

### 3. Session Selection for FIFO Cleanup

**Question**: How to select oldest completed sessions for cleanup?

**Decision**: Query sessions ordered by `started_at` ASC, excluding active sessions (where `ended_at IS NULL`)

**Rationale**:
- `started_at` timestamp is reliably set when recording begins (per spec assumption)
- Excluding `ended_at IS NULL` protects active recordings (FR-008)
- Ordering by `started_at` ensures true FIFO behavior (FR-004)
- Fetch sessions with their total size (sum of segment file_size) for efficient selection

**Query Pattern**:
```python
def get_oldest_completed_sessions_with_size(self, session, limit: int = 10):
    """Get oldest completed sessions with their total storage size."""
    return session.query(
        RecordingSession,
        func.sum(RecordingSegment.file_size).label('total_size')
    ).join(
        RecordingSegment
    ).filter(
        RecordingSession.ended_at.isnot(None),  # Only completed sessions
        RecordingSegment.upload_status == UploadStatus.COMPLETED,
        RecordingSegment.oss_path.isnot(None)
    ).group_by(
        RecordingSession.id
    ).order_by(
        RecordingSession.started_at.asc()
    ).limit(limit).all()
```

**Alternatives Considered**:
- Order by `ended_at`: Could cause issues if sessions end out of order (overlapping streams)
- Order by `created_at`: Not semantically correct - `started_at` represents recording time
- Delete by segment upload time: Would break session integrity (FR-005)

---

### 4. OSS Deletion Strategy

**Question**: How to delete session files from OSS reliably?

**Decision**: Use existing `TOSUploader.delete_object()` for each segment's `oss_path` and `mp4_oss_path`

**Rationale**:
- Method already exists in `src/storage/tos_uploader.py` (lines 214-222)
- TOS SDK deletion is idempotent (per spec assumption)
- Delete both TS (`oss_path`) and MP4 (`mp4_oss_path`) files (FR-006)
- Log each deletion for audit trail (FR-014)

**Deletion Flow**:
1. Get all segments for session
2. For each segment:
   - Delete `oss_path` (TS file) if exists
   - Delete `mp4_oss_path` (MP4 file) if exists
   - Update database record (set `oss_deleted = True` or remove record)
3. Log session deletion summary

**Error Handling**:
- Log errors but continue with other segments
- Don't block cleanup of other sessions on single failure
- Mark segments with deletion errors for retry

**Alternatives Considered**:
- Batch deletion API: TOS SDK may support batch delete, but single deletions are simpler and allow per-file error handling
- Soft delete (mark only): Would leave orphaned files in OSS, defeating storage management purpose
- Delete session record entirely: Considered, but keeping record with `oss_deleted=True` provides better audit trail

---

### 5. Database Record Update Strategy

**Question**: After OSS deletion, how to update database records?

**Decision**: Hard delete segment records from database after successful OSS deletion. Delete session record when all its segments are deleted.

**Rationale**:
- Simpler implementation - no schema migration needed
- Database stays clean - only contains active/valid data
- Storage calculation remains simple (sum all records)
- User preference: no need to preserve deleted recording history
- Cascade delete: when all segments of a session are deleted, delete the session too

**Deletion Flow**:
```python
def delete_session_completely(self, session_id: int) -> None:
    # Delete all segments for this session
    session.query(RecordingSegment).filter(
        RecordingSegment.session_id == session_id
    ).delete()
    # Delete the session itself
    session.query(RecordingSession).filter(
        RecordingSession.id == session_id
    ).delete()
    session.commit()
```

**Alternatives Considered**:
- Soft delete with `oss_deleted` boolean: Preserves history but adds complexity, user doesn't need it
- Separate cleanup history table: Over-engineering for current requirements
- Only update `oss_path` to NULL: Leaves orphaned records in database

---

### 6. Configuration Design

**Question**: How to configure cleanup threshold and enable/disable cleanup?

**Decision**: Add two settings to `[OSS设置]` section in `config/config.ini`

**Configuration**:
```ini
[OSS设置]
# ... existing settings ...
OSS存储清理阈值(GB) = 50
启用OSS存储清理(是/否) = 是
```

**Rationale**:
- Follows existing Chinese naming convention in config.ini
- GB is intuitive unit for storage thresholds
- Explicit enable/disable flag provides clear control
- Threshold of 0 also disables cleanup (FR-013)
- Default: disabled (0 or 否) to prevent accidental data deletion

**Parsing**:
```python
cleanup_enabled = config.get('OSS设置', '启用OSS存储清理(是/否)', fallback='否') == '是'
cleanup_threshold_gb = float(config.get('OSS设置', 'OSS存储清理阈值(GB)', fallback='0'))
cleanup_threshold_bytes = int(cleanup_threshold_gb * 1024 * 1024 * 1024)
```

**Alternatives Considered**:
- Separate config file: Inconsistent with existing patterns
- Bytes unit: Not user-friendly
- Percentage-based threshold: Requires knowing total bucket capacity, not always available

---

### 7. Integration Point: Upload Completion Hook

**Question**: Where to trigger cleanup after upload completes?

**Decision**: Add callback hook in `UploadWorker._process_task()` after successful upload

**Rationale**:
- Upload completion is the trigger point per FR-002
- `UploadWorker` already handles upload success/failure
- Hook called synchronously (blocking) to ensure cleanup runs before next upload check
- Hook receives segment_id to know which upload just completed

**Integration Point** (in `upload_queue.py`):
```python
def _process_task(self, task: UploadTask) -> bool:
    # ... existing upload logic ...
    if success:
        self._on_upload_success(task.segment_id)
        if self._cleanup_callback:
            self._cleanup_callback()  # Blocking cleanup hook
    return success
```

**Alternatives Considered**:
- Event-based async notification: Would require refactoring upload worker, adds complexity
- Polling-based cleanup: Less responsive, wastes resources
- Timer-based periodic cleanup: Doesn't meet "trigger on each upload" requirement

---

### 8. OSS Delete API Testing

**Question**: How to verify that the OSS delete API works correctly before relying on it for cleanup?

**Decision**: Create a dedicated test script `scripts/test_tos_delete.py` that uploads a test file and immediately deletes it.

**Rationale**:
- Validates TOS credentials and permissions for DELETE operations
- Follows existing testing pattern (`scripts/test_tos.py` for upload)
- Quick verification without affecting production data
- Can be run as part of deployment validation

**Test Script Design**:
```python
# scripts/test_tos_delete.py
"""
Test TOS delete API by uploading and deleting a test file.
Usage: python scripts/test_tos_delete.py
"""
import os
import sys
import configparser
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.storage.tos_uploader import TOSUploader
from loguru import logger

def test_upload_and_delete():
    """Test file upload followed by deletion."""
    # Load TOS credentials
    config = configparser.ConfigParser()
    config_path = 'config/tos_credentials.ini'
    config.read(config_path, encoding='utf-8-sig')

    # Initialize uploader
    uploader = TOSUploader(
        access_key=config.get('tos', 'access_key_id'),
        secret_key=config.get('tos', 'secret_access_key'),
        endpoint=config.get('tos', 'endpoint'),
        region=config.get('tos', 'region'),
        bucket=config.get('tos', 'bucket')
    )

    # Generate unique test key
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    test_key = f"_test_delete/{timestamp}_test.txt"
    test_content = f"Test file created at {timestamp}"

    logger.info(f"Step 1: Uploading test file to {test_key}")

    # Upload test file
    upload_success = uploader.put_object(test_key, test_content.encode('utf-8'))
    if not upload_success:
        logger.error("Upload failed!")
        return False
    logger.info("Upload successful")

    logger.info(f"Step 2: Deleting test file {test_key}")

    # Delete test file
    delete_success = uploader.delete_object(test_key)
    if not delete_success:
        logger.error("Delete failed!")
        return False
    logger.info("Delete successful")

    logger.info("✓ OSS delete API test passed!")
    return True

if __name__ == '__main__':
    success = test_upload_and_delete()
    sys.exit(0 if success else 1)
```

**Test Execution**:
```bash
python scripts/test_tos_delete.py
```

**Expected Output**:
```
INFO  | Step 1: Uploading test file to _test_delete/20260106_120000_test.txt
INFO  | Upload successful
INFO  | Step 2: Deleting test file _test_delete/20260106_120000_test.txt
INFO  | Delete successful
INFO  | ✓ OSS delete API test passed!
```

**Error Cases to Validate**:
1. **Missing credentials**: Script fails with clear error message
2. **Invalid bucket**: Script fails with TOS authentication error
3. **No delete permission**: Script fails at delete step (upload works)
4. **Network error**: Script handles and reports gracefully

**Alternatives Considered**:
- Unit test with mocking: Doesn't validate real TOS connectivity
- Integration into existing test_tos.py: Keeps delete testing separate for clarity
- pytest framework: Project doesn't use formal test framework yet

---

## Summary of Decisions

| Decision Area | Choice | Key Reason |
|---------------|--------|------------|
| Mutex Pattern | `threading.Lock()` | Standard Python, blocking by default |
| Storage Calculation | SQL SUM on file_size | Efficient, DB is source of truth |
| Session Selection | Order by started_at ASC | True FIFO, protects active sessions |
| OSS Deletion | Per-segment delete_object() | Exists in codebase, idempotent |
| DB Record Update | Hard delete records | Simpler, no migration needed |
| Configuration | `[OSS设置]` section, GB unit | Follows existing patterns |
| Integration Point | UploadWorker callback | Synchronous, blocking per spec |
| Delete API Testing | `scripts/test_tos_delete.py` | Validates TOS delete before production use |
