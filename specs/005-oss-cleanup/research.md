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

**Decision**: Add `oss_deleted` boolean field to `RecordingSegment` model; set to True after successful OSS deletion

**Rationale**:
- Preserves audit trail of what was recorded and when
- Allows future analysis of recording history
- Segments excluded from storage calculation once `oss_deleted = True`
- Existing `local_file_deleted` pattern provides precedent

**Model Change**:
```python
class RecordingSegment(Base):
    # ... existing fields ...
    oss_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
```

**Alternatives Considered**:
- Hard delete records: Loses history, can't answer "what was recorded last month?"
- Separate cleanup history table: Over-engineering for current requirements
- Only update `oss_path` to NULL: Less explicit than dedicated boolean flag

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

## Summary of Decisions

| Decision Area | Choice | Key Reason |
|---------------|--------|------------|
| Mutex Pattern | `threading.Lock()` | Standard Python, blocking by default |
| Storage Calculation | SQL SUM on file_size | Efficient, DB is source of truth |
| Session Selection | Order by started_at ASC | True FIFO, protects active sessions |
| OSS Deletion | Per-segment delete_object() | Exists in codebase, idempotent |
| DB Record Update | Add oss_deleted boolean | Preserves audit trail |
| Configuration | `[OSS设置]` section, GB unit | Follows existing patterns |
| Integration Point | UploadWorker callback | Synchronous, blocking per spec |
