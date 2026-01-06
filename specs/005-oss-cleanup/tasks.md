# Tasks: OSS Storage Cleanup

**Input**: Design documents from `/specs/005-oss-cleanup/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Manual testing via scripts (no formal test framework)

**Organization**: Tasks grouped by user story for independent implementation and testing

**Key Design Decision**: **Hard Delete** - After deleting OSS files, database records (segments + session) are also deleted. No new database fields needed.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps to user story (US1, US2, US3, US4)
- All tasks include exact file paths

## Path Conventions

- `src/storage/` - Storage module
- `scripts/` - Test scripts
- `config/` - Configuration files
- **No migrations needed** - Hard delete approach requires no schema changes

---

## Phase 1: Setup

**Purpose**: Create test script for OSS delete API validation

- [x] T001 Create TOS delete API test script (upload + delete test file) in scripts/test_tos_delete.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Configuration that MUST be complete before user story implementation

- [x] T002 Add cleanup configuration fields (`启用OSS存储清理(是/否)`, `OSS存储清理阈值(GB)`) to config/config.ini under [OSS设置] section

**Checkpoint**: Config ready, no database changes needed

---

## Phase 3: User Story 1 - Automatic Storage Cleanup on Upload (Priority: P1) 🎯 MVP

**Goal**: Trigger cleanup check after each upload, with mutex protection for thread safety

**Independent Test**: Configure 100MB threshold, upload recordings, verify cleanup triggers when exceeded

### Implementation for User Story 1

- [x] T003 [P] [US1] Add get_total_oss_storage() method (SUM file_size WHERE upload_status=COMPLETED AND oss_path IS NOT NULL) in src/storage/repository.py
- [x] T004 [P] [US1] Create CleanupResult dataclass (triggered, sessions_deleted, bytes_freed, errors, duration_seconds) in src/storage/cleanup.py
- [x] T005 [P] [US1] Create StorageStats dataclass (total_bytes, threshold_bytes, over_threshold, sessions_count) in src/storage/cleanup.py
- [x] T006 [US1] Create StorageCleanup class with constructor (repository, tos_uploader, threshold_bytes, enabled) and threading.Lock in src/storage/cleanup.py
- [x] T007 [US1] Implement get_storage_stats() method in StorageCleanup class in src/storage/cleanup.py
- [x] T008 [US1] Implement trigger_cleanup() method with mutex lock (acquire, check threshold, cleanup if needed, release) in src/storage/cleanup.py
- [x] T009 [US1] Add cleanup callback hook (_cleanup_callback) to UploadWorker after successful upload in src/storage/upload_queue.py
- [x] T010 [US1] Parse cleanup config (enabled, threshold_gb) in RecordingManager.from_config() in src/storage/manager.py
- [x] T011 [US1] Create StorageCleanup instance in RecordingManager.__init__() when enabled in src/storage/manager.py
- [x] T012 [US1] Add cleanup property to RecordingManager in src/storage/manager.py
- [x] T013 [US1] Wire cleanup.trigger_cleanup() to upload completion handler in src/storage/manager.py

**Checkpoint**: Cleanup triggers on upload with mutex protection

---

## Phase 4: User Story 2 - Session-Based Cleanup with Hard Delete (Priority: P1)

**Goal**: Delete entire sessions (OSS files + DB records) in FIFO order, protect active sessions

**Independent Test**: Create multi-segment sessions, trigger cleanup, verify OSS files AND database records deleted for oldest sessions

### Implementation for User Story 2

- [x] T014 [P] [US2] Add get_oldest_completed_sessions(limit) method (ORDER BY started_at ASC, ended_at IS NOT NULL) in src/storage/repository.py
- [x] T015 [P] [US2] Add get_session_segments_for_cleanup(session_id) method (oss_path IS NOT NULL) in src/storage/repository.py
- [x] T016 [P] [US2] Add delete_session_with_segments(session_id) method (DELETE segments then DELETE session) in src/storage/repository.py
- [x] T017 [US2] Implement _delete_oss_files_for_segment() helper (delete oss_path, delete mp4_oss_path if exists) in src/storage/cleanup.py
- [x] T018 [US2] Implement _delete_session() method: 1) get segments, 2) delete OSS files, 3) delete DB records via repository in src/storage/cleanup.py
- [x] T019 [US2] Implement _perform_cleanup() method: loop oldest sessions until storage < threshold in src/storage/cleanup.py
- [x] T020 [US2] Add active session protection filter (ended_at IS NOT NULL) to get_oldest_completed_sessions() in src/storage/repository.py

**Checkpoint**: Sessions deleted with OSS files AND database records in FIFO order

---

## Phase 5: User Story 3 - Cleanup Configuration (Priority: P2)

**Goal**: Configurable threshold with enable/disable flag, sensible defaults

**Independent Test**: Change config values, verify cleanup behavior respects settings

### Implementation for User Story 3

- [x] T021 [US3] Add default value handling for missing cleanup config (disabled by default, 0GB threshold) in src/storage/manager.py
- [x] T022 [US3] Handle threshold=0 as cleanup disabled in StorageCleanup.trigger_cleanup() in src/storage/cleanup.py
- [x] T023 [US3] Convert threshold_gb to threshold_bytes (GB * 1024^3) in RecordingManager.from_config() in src/storage/manager.py
- [x] T024 [US3] Skip cleanup instantiation when disabled in RecordingManager in src/storage/manager.py

**Checkpoint**: Cleanup fully configurable via config.ini

---

## Phase 6: User Story 4 - Cleanup Logging and Visibility (Priority: P3)

**Goal**: Comprehensive logging for audit trail and troubleshooting

**Independent Test**: Trigger cleanup, verify logs show sessions deleted, bytes freed, errors

### Implementation for User Story 4

- [x] T025 [P] [US4] Add cleanup trigger log (current storage, threshold) at start of trigger_cleanup() in src/storage/cleanup.py
- [x] T026 [P] [US4] Add session deletion log (session_id, anchor_name, started_at) in _delete_session() in src/storage/cleanup.py
- [x] T027 [P] [US4] Add segment file deletion log (segment_id, oss_path, mp4_oss_path) in _delete_oss_files_for_segment() in src/storage/cleanup.py
- [x] T028 [P] [US4] Add OSS deletion error log (file path, error message) with error collection in src/storage/cleanup.py
- [x] T029 [P] [US4] Add database record deletion log (session_id, segment_count deleted) in _delete_session() in src/storage/cleanup.py
- [x] T030 [US4] Add cleanup summary log (sessions deleted, bytes freed, duration) at end of trigger_cleanup() in src/storage/cleanup.py

**Checkpoint**: Complete audit trail in logs for all cleanup operations

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, error handling, and verification

- [x] T031 Handle orphaned records gracefully (OSS files already deleted) - treat as success, still delete DB records in src/storage/cleanup.py
- [x] T032 Export StorageCleanup, CleanupResult, StorageStats from src/storage/__init__.py
- [ ] T033 Run scripts/test_tos_delete.py to verify OSS delete API works (MANUAL: requires TOS credentials)
- [ ] T034 Manual end-to-end test: low threshold → uploads → verify oldest sessions deleted (OSS + DB) (MANUAL: requires running system)

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)      ──┐
                       ├──► Phase 3 (US1) ──► Phase 4 (US2) ──┐
Phase 2 (Foundation) ──┘                                      │
                       ├──► Phase 5 (US3) ────────────────────┼──► Phase 7 (Polish)
                       └──► Phase 6 (US4) ────────────────────┘
```

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|------------|-------------------|
| US1 (Core Trigger) | Foundation | - |
| US2 (Session Delete) | US1 (T006-T008) | US3, US4 |
| US3 (Config) | Foundation | US1, US2, US4 |
| US4 (Logging) | Foundation | US1, US2, US3 |

### Parallel Opportunities

**Phase 1+2**: T001, T002 (different files)

**User Story 1**: T003, T004, T005 (repository.py vs cleanup.py)

**User Story 2**: T014, T015, T016 (all repository methods)

**User Story 4**: T025, T026, T027, T028, T029 (different logging points)

---

## Implementation Strategy

### MVP First (US1 Only)

1. T001, T002 (parallel) - Setup + Config
2. T003-T013 - Core cleanup trigger with mutex
3. **VALIDATE**: Verify cleanup triggers on upload

### Incremental Delivery

| Increment | Tasks | Deliverable |
|-----------|-------|-------------|
| MVP | T001-T013 | Cleanup triggers on upload |
| +US2 | T014-T020 | Session hard delete (OSS + DB) |
| +US3 | T021-T024 | Configurable threshold |
| +US4 | T025-T030 | Full logging |
| Polish | T031-T034 | Production ready |

### Recommended Execution Order

```
1. T001, T002 (parallel)     - Setup + Foundation
2. T003, T004, T005 (parallel) - US1 dataclasses + repository
3. T006-T013 (sequential)    - US1 cleanup class + integration
4. T014, T015, T016 (parallel) - US2 repository methods
5. T017-T020 (sequential)    - US2 session deletion logic
6. T021-T024 (sequential)    - US3 config handling
7. T025-T030 (mostly parallel) - US4 logging
8. T031-T034 (sequential)    - Polish + verification
```

---

## Key Implementation Notes

### Hard Delete Flow (US2 Core)

```
For each session to delete:
  1. Get segments with oss_path != NULL
  2. For each segment:
     - Delete oss_path from OSS (log errors, continue)
     - Delete mp4_oss_path from OSS if exists (log errors, continue)
  3. Delete all segment records from DB
  4. Delete session record from DB
  5. Commit transaction
```

### Thread Safety (US1 Core)

```python
def trigger_cleanup(self) -> CleanupResult:
    with self._cleanup_lock:  # Blocks other cleanup calls
        # Re-check storage after acquiring lock (FR-011)
        stats = self.get_storage_stats()
        if not stats.over_threshold:
            return CleanupResult(triggered=False, ...)
        return self._perform_cleanup()
```

### Active Session Protection

```sql
-- Only select completed sessions for cleanup
WHERE session.ended_at IS NOT NULL
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Tasks** | 34 |
| **Setup + Foundation** | 2 |
| **US1 (Core Trigger)** | 11 |
| **US2 (Session Delete)** | 7 |
| **US3 (Config)** | 4 |
| **US4 (Logging)** | 6 |
| **Polish** | 4 |
| **Parallel Opportunities** | 5 groups |
| **Database Migration** | None needed |
