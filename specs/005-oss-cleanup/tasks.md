# Tasks: OSS Storage Cleanup

**Input**: Design documents from `/specs/005-oss-cleanup/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Manual testing via scripts (no formal test framework in this project)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/storage/` for storage module, `scripts/` for test scripts, `config/` for configuration
- **Migrations**: `migrations/` at repository root

---

## Phase 1: Setup

**Purpose**: Create test script for OSS delete API and database migration

- [ ] T001 [P] Create TOS delete API test script in scripts/test_tos_delete.py
- [ ] T002 [P] Create database migration for oss_deleted field in migrations/002_add_oss_deleted.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T003 Add oss_deleted field to RecordingSegment model in src/storage/models.py
- [ ] T004 Run migration to add oss_deleted column to database
- [ ] T005 Add cleanup configuration fields to config/config.ini ([OSS设置] section)

**Checkpoint**: Foundation ready - model updated, migration applied, config ready

---

## Phase 3: User Story 1 - Automatic Storage Cleanup on Upload (Priority: P1) 🎯 MVP

**Goal**: System automatically checks and cleans up old recordings from OSS when storage exceeds threshold after each upload

**Independent Test**: Configure low threshold (100MB), upload several recordings, verify oldest sessions deleted when threshold exceeded

### Implementation for User Story 1

- [ ] T006 [P] [US1] Add get_total_oss_storage() method to RecordingRepository in src/storage/repository.py
- [ ] T007 [P] [US1] Create CleanupResult and StorageStats dataclasses in src/storage/cleanup.py
- [ ] T008 [US1] Create StorageCleanup class skeleton with constructor and threading.Lock in src/storage/cleanup.py
- [ ] T009 [US1] Implement get_storage_stats() method in StorageCleanup class in src/storage/cleanup.py
- [ ] T010 [US1] Implement trigger_cleanup() method with mutex locking in src/storage/cleanup.py
- [ ] T011 [US1] Add cleanup callback hook to UploadWorker._process_task() in src/storage/upload_queue.py
- [ ] T012 [US1] Integrate StorageCleanup into RecordingManager.from_config() in src/storage/manager.py
- [ ] T013 [US1] Add cleanup property to RecordingManager in src/storage/manager.py
- [ ] T014 [US1] Wire up cleanup trigger in manager's upload completion handler in src/storage/manager.py

**Checkpoint**: At this point, automatic cleanup triggers on each upload with mutex protection

---

## Phase 4: User Story 2 - Session-Based Cleanup Granularity (Priority: P1)

**Goal**: Cleanup deletes entire recording sessions (all segments) rather than individual segments, in FIFO order

**Independent Test**: Create multiple sessions with multiple segments, trigger cleanup, verify all segments of deleted sessions removed while other sessions remain complete

### Implementation for User Story 2

- [ ] T015 [P] [US2] Add get_oldest_completed_sessions() method to RecordingRepository in src/storage/repository.py
- [ ] T016 [P] [US2] Add get_session_segments_for_cleanup() method to RecordingRepository in src/storage/repository.py
- [ ] T017 [P] [US2] Add mark_segments_oss_deleted() method to RecordingRepository in src/storage/repository.py
- [ ] T018 [US2] Implement _delete_session() private method in StorageCleanup class in src/storage/cleanup.py
- [ ] T019 [US2] Implement _perform_cleanup() method with FIFO session selection in src/storage/cleanup.py
- [ ] T020 [US2] Handle active session protection (ended_at IS NULL) in cleanup logic in src/storage/cleanup.py

**Checkpoint**: At this point, cleanup deletes entire sessions in FIFO order, protects active recordings

---

## Phase 5: User Story 3 - Cleanup Configuration (Priority: P2)

**Goal**: Configurable storage threshold for cleanup, with enable/disable flag

**Independent Test**: Modify config values, verify cleanup respects new threshold settings and enable/disable flag

### Implementation for User Story 3

- [ ] T021 [US3] Parse cleanup_enabled from config in RecordingManager.from_config() in src/storage/manager.py
- [ ] T022 [US3] Parse cleanup_threshold_gb from config and convert to bytes in src/storage/manager.py
- [ ] T023 [US3] Handle threshold=0 as disabled in StorageCleanup.trigger_cleanup() in src/storage/cleanup.py
- [ ] T024 [US3] Add default values (disabled, 0GB) for missing config settings in src/storage/manager.py

**Checkpoint**: At this point, cleanup is fully configurable via config.ini

---

## Phase 6: User Story 4 - Cleanup Logging and Visibility (Priority: P3)

**Goal**: Comprehensive logging of cleanup activities for audit and troubleshooting

**Independent Test**: Trigger cleanup, verify log entries show sessions deleted, space freed, current storage, and any errors

### Implementation for User Story 4

- [ ] T025 [P] [US4] Add cleanup trigger logging (current storage, threshold) in src/storage/cleanup.py
- [ ] T026 [P] [US4] Add session deletion logging (session_id, anchor_name, started_at) in src/storage/cleanup.py
- [ ] T027 [P] [US4] Add segment deletion logging (segment_id, oss_path, mp4_oss_path) in src/storage/cleanup.py
- [ ] T028 [P] [US4] Add error logging for OSS deletion failures in src/storage/cleanup.py
- [ ] T029 [US4] Add cleanup summary logging (sessions deleted, bytes freed, duration) in src/storage/cleanup.py

**Checkpoint**: All cleanup operations have complete audit trail in logs

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final verification and edge case handling

- [ ] T030 Handle orphaned records (OSS files already deleted) gracefully in src/storage/cleanup.py
- [ ] T031 Export StorageCleanup, CleanupResult, StorageStats from src/storage/__init__.py
- [ ] T032 Run test_tos_delete.py to verify OSS delete API works
- [ ] T033 Manual end-to-end test: configure low threshold, trigger uploads, verify cleanup behavior

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on T001, T002 completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational phase completion
- **User Story 2 (Phase 4)**: Depends on User Story 1 core (T008-T010)
- **User Story 3 (Phase 5)**: Depends on Foundational phase completion (can parallel with US1/US2)
- **User Story 4 (Phase 6)**: Can be done in parallel with US1/US2 after Foundational
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Core cleanup mechanism - foundational for US2
- **User Story 2 (P1)**: Session-based deletion - builds on US1's trigger mechanism
- **User Story 3 (P2)**: Configuration - can parallel with US1/US2, integrates at manager level
- **User Story 4 (P3)**: Logging - can be added incrementally to cleanup methods

### Within Each User Story

- Repository methods before cleanup class methods
- Core mechanism before edge case handling
- Integration last (manager, upload_queue)

### Parallel Opportunities

**Setup Phase**:
- T001, T002 can run in parallel (different files)

**Foundational Phase**:
- T003, T005 can run in parallel (different files)
- T004 depends on T003 (migration needs model update)

**User Story 1**:
- T006, T007 can run in parallel (repository.py vs cleanup.py)
- T011, T012-T014 sequential (upload_queue.py then manager.py)

**User Story 2**:
- T015, T016, T017 can run in parallel (all repository methods)
- T018-T020 sequential (cleanup.py methods)

**User Story 3**:
- T021-T024 sequential (all in manager.py)

**User Story 4**:
- T025, T026, T027, T028 can run in parallel (different logging points)
- T029 depends on others (summary at end)

---

## Parallel Example: User Story 2

```bash
# Launch all repository methods for User Story 2 together:
Task: "Add get_oldest_completed_sessions() method in src/storage/repository.py"
Task: "Add get_session_segments_for_cleanup() method in src/storage/repository.py"
Task: "Add mark_segments_oss_deleted() method in src/storage/repository.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (test script + migration)
2. Complete Phase 2: Foundational (model + config)
3. Complete Phase 3: User Story 1 (basic cleanup trigger)
4. **STOP and VALIDATE**: Test automatic cleanup triggers on upload
5. Can operate in production with hard-coded session selection

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Basic cleanup works → Deploy MVP
3. Add User Story 2 → FIFO session deletion → Deploy
4. Add User Story 3 → Configurable threshold → Deploy
5. Add User Story 4 → Full logging → Deploy final version

### Recommended Execution Order

1. T001, T002 (parallel) - Setup
2. T003, T005 (parallel) - Foundational
3. T004 - Run migration
4. T006, T007 (parallel) - US1 foundations
5. T008-T014 (sequential) - US1 core
6. T015-T017 (parallel) - US2 repository
7. T018-T020 (sequential) - US2 cleanup
8. T021-T024 (sequential) - US3 config
9. T025-T029 (mostly parallel) - US4 logging
10. T030-T033 (sequential) - Polish

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Manual testing via scripts - no pytest framework
- Verify TOS delete API works before relying on cleanup (T032)
- Commit after each task or logical group
- Stop at any checkpoint to validate independently
