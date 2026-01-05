# Tasks: VOD Player Frontend with Seekable Playback

**Input**: Design documents from `/specs/002-vod-player-frontend/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: Not explicitly requested in spec - tests are EXCLUDED from this task list.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

Based on plan.md structure:
- **Recording pipeline**: `src/storage/` (existing module)
- **VOD backend**: `vod-player/backend/`
- **VOD frontend**: `vod-player/frontend/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure for both backend and frontend

- [x] T001 Create VOD application directory structure per plan.md at vod-player/
- [x] T002 [P] Initialize Python backend with FastAPI dependencies in vod-player/backend/
- [x] T003 [P] Initialize Vue 3 frontend with Vite in vod-player/frontend/
- [x] T004 [P] Create docker-compose.yml for development environment in vod-player/
- [x] T005 [P] Add VOD configuration section to config/config.ini

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T006 Add mp4_oss_path, mp4_status, duration fields to RecordingSegment model in src/storage/models.py
- [x] T007 Create Alembic migration for new VOD fields in alembic/versions/
- [x] T008 Create database configuration module for VOD backend in vod-player/backend/app/config.py
- [x] T009 [P] Setup FastAPI application with CORS and routing in vod-player/backend/app/main.py
- [x] T010 [P] Create base Pydantic schemas for API responses in vod-player/backend/app/schemas.py
- [x] T011 [P] Setup Vue 3 project with Element Plus and Video.js in vod-player/frontend/package.json
- [x] T012 [P] Configure Vite with proxy for backend API in vod-player/frontend/vite.config.ts
- [x] T013 Create API client module with axios in vod-player/frontend/src/api/index.ts

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Browse and Play Recordings (Priority: P1) 🎯 MVP

**Goal**: Users can browse recorded live streams by platform/anchor and play any recording with instant seek

**Independent Test**: Navigate through platform/anchor tree, select a recording session, click play, drag the progress bar to a random position - video should jump to that position within 1 second.

### Implementation for User Story 1

#### Backend - Navigation API

- [x] T014 [P] [US1] Implement GET /api/platforms endpoint in vod-player/backend/app/routers/api.py
- [x] T015 [P] [US1] Implement GET /api/platforms/{platform}/anchors endpoint in vod-player/backend/app/routers/api.py
- [x] T016 [P] [US1] Implement GET /api/anchors/{anchor_name}/sessions endpoint with pagination in vod-player/backend/app/routers/api.py
- [x] T017 [US1] Implement GET /api/sessions/{session_id} endpoint for session details in vod-player/backend/app/routers/api.py

#### Backend - Playback URL Generation

- [x] T018 [US1] Create TOS presigned URL service in vod-player/backend/app/services/tos_sign.py
- [x] T019 [US1] Implement GET /api/segments/{segment_id}/play endpoint in vod-player/backend/app/routers/api.py

#### Frontend - Navigation

- [x] T020 [US1] Create Vue router configuration in vod-player/frontend/src/router/index.ts
- [x] T021 [US1] Create SessionTree component for platform/anchor/session navigation in vod-player/frontend/src/components/SessionTree.vue
- [x] T022 [US1] Create Home view with tree navigation in vod-player/frontend/src/views/Home.vue

#### Frontend - Video Player

- [x] T023 [US1] Create VideoPlayer component with Video.js in vod-player/frontend/src/components/VideoPlayer.vue
- [x] T024 [US1] Create Player view page with segment selection in vod-player/frontend/src/views/Player.vue
- [x] T025 [US1] Implement seek functionality and progress bar handling in VideoPlayer component

**Checkpoint**: User Story 1 complete - browse and play with seek should be fully functional

---

## Phase 4: User Story 2 - Secure Time-Limited Access (Priority: P2)

**Goal**: Video URLs are time-limited and secure, preventing unauthorized access through leaked/bookmarked URLs

**Independent Test**: Request a play URL, wait for expiration time, attempt to access - should return access denied.

### Implementation for User Story 2

- [x] T026 [US2] Add configurable URL expiration to TOS presigned URL service in vod-player/backend/app/services/tos_sign.py
- [x] T027 [US2] Add expires_at field to playback URL response in vod-player/backend/app/routers/api.py
- [x] T028 [US2] Implement URL expiration handling in VideoPlayer component in vod-player/frontend/src/components/VideoPlayer.vue
- [x] T029 [US2] Add "Refresh URL" button for expired URL recovery in vod-player/frontend/src/views/Player.vue

**Checkpoint**: User Story 2 complete - secure time-limited URLs functional

---

## Phase 5: User Story 3 - Multi-Segment Session Playback (Priority: P2)

**Goal**: Users can easily navigate between segments and see which segment they're currently watching

**Independent Test**: Open a session with 5 segments, play segment 3, finish it, verify transition to segment 4.

### Implementation for User Story 3

- [x] T030 [US3] Display segment list with duration and status in Player view in vod-player/frontend/src/views/Player.vue
- [x] T031 [US3] Implement segment switching without page reload in vod-player/frontend/src/views/Player.vue
- [x] T032 [US3] Show "Processing" status for segments with mp4_status != completed in vod-player/frontend/src/views/Player.vue
- [x] T033 [US3] Add visual indicator for current segment in segment list in vod-player/frontend/src/views/Player.vue

**Checkpoint**: User Story 3 complete - multi-segment navigation functional

---

## Phase 6: User Story 4 - Format Conversion for Seek Support (Priority: P3)

**Goal**: Recorded TS files are automatically converted to seek-friendly MP4 format (fast start) before upload

**Independent Test**: Complete a recording, verify MP4 conversion runs locally, then MP4 is uploaded to storage with moov atom at file start.

### Implementation for User Story 4

#### Pipeline Infrastructure

- [x] T034 [US4] Create pipeline orchestration module with Stage protocol in src/storage/pipeline.py
- [x] T035 [US4] Create stages package with __init__.py in src/storage/stages/__init__.py

#### Conversion Stage

- [x] T036 [US4] Implement TS to MP4 conversion stage with FFmpeg faststart in src/storage/stages/convert.py
- [x] T037 [US4] Add duration extraction using FFprobe in src/storage/stages/convert.py

#### Upload Stage Refactor

- [x] T038 [US4] Refactor existing upload logic into upload stage in src/storage/stages/upload.py
- [x] T039 [US4] Update upload stage to handle MP4 path and update mp4_oss_path field in src/storage/stages/upload.py

#### Pipeline Integration

- [x] T040 [US4] Integrate pipeline into storage manager in src/storage/manager.py
- [x] T041 [US4] Update mp4_status transitions (pending → processing → completed/failed) in pipeline stages

#### Fallback Handling

- [x] T042 [US4] Implement TS upload fallback when MP4 conversion fails in src/storage/stages/convert.py
- [x] T043 [US4] Add error logging and status tracking for conversion failures

**Checkpoint**: User Story 4 complete - automated MP4 conversion pipeline functional

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T044 [P] Add error handling for TOS unavailability in VideoPlayer component
- [x] T045 [P] Add loading states and buffering indicator to VideoPlayer component
- [x] T046 [P] Handle edge case: seek beyond video duration (clamp to end)
- [x] T047 [P] Handle edge case: empty sessions with zero segments
- [x] T048 [P] Add pagination UI for sessions list in Home view
- [ ] T049 Run quickstart.md validation to verify end-to-end flow

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phases 3-6)**: All depend on Foundational phase completion
  - US1 (P1): Can start after Phase 2
  - US2 (P2): Can start after Phase 2, integrates with US1 playback
  - US3 (P2): Can start after Phase 2, integrates with US1 player
  - US4 (P3): Can start after Phase 2, independent backend work
- **Polish (Phase 7)**: Depends on US1 at minimum; polish tasks can start once related stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Foundation only - Core playback functionality
- **User Story 2 (P2)**: Foundation + US1 (uses playback infrastructure)
- **User Story 3 (P2)**: Foundation + US1 (uses player component)
- **User Story 4 (P3)**: Foundation only - Backend pipeline (independent of frontend)

### Within Each User Story

- Backend endpoints before frontend components that consume them
- Services before routers that use them
- Core implementation before edge case handling

### Parallel Opportunities

- T002, T003, T004, T005: All setup tasks can run in parallel
- T009, T010, T011, T012: Foundation frontend/backend can run in parallel
- T014, T015, T016: Navigation endpoints can run in parallel
- T020, T021, T022: Frontend navigation components (after backend endpoints ready)
- T034, T035: Pipeline infrastructure files can run in parallel
- US4 backend work can run in parallel with US2/US3 frontend work

---

## Parallel Example: User Story 1

```bash
# Launch backend navigation endpoints in parallel:
Task: T014 "Implement GET /api/platforms endpoint"
Task: T015 "Implement GET /api/platforms/{platform}/anchors endpoint"
Task: T016 "Implement GET /api/anchors/{anchor_name}/sessions endpoint"

# After backend ready, launch frontend components in parallel:
Task: T021 "Create SessionTree component"
Task: T023 "Create VideoPlayer component"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T013) - CRITICAL
3. Complete Phase 3: User Story 1 (T014-T025)
4. **STOP and VALIDATE**: Test browse + play + seek independently
5. Deploy/demo if ready - this is the MVP!

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 → Browse + Play with Seek (MVP!)
3. Add User Story 2 → Secure time-limited URLs
4. Add User Story 3 → Multi-segment navigation
5. Add User Story 4 → Automated MP4 conversion pipeline
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (frontend)
   - Developer B: User Story 1 (backend) → then US4 (pipeline)
   - Developer C: After US1 backend ready → US2 + US3
3. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- US4 (Pipeline) can be developed in parallel with frontend stories since it's backend-only
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
