# Tasks: Video Segment Aggregation

**Input**: Design documents from `/specs/004-video-segment-aggregation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in specification. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `vod-player/backend/app/`
- **Frontend**: `vod-player/frontend/src/`

---

## Phase 1: Setup

**Purpose**: Project structure verification and new file scaffolding

- [x] T001 Verify existing project structure matches plan.md layout
- [x] T002 [P] Create backend services directory if not exists at vod-player/backend/app/services/
- [x] T003 [P] Create frontend stores directory at vod-player/frontend/src/stores/
- [x] T004 [P] Create frontend services directory at vod-player/frontend/src/services/

---

## Phase 2: Foundational (Backend API + Schemas)

**Purpose**: Core backend infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No frontend work can begin until this phase is complete

- [x] T005 Add AggregatedSession and AggregatedSegment schemas in vod-player/backend/app/schemas.py
- [x] T006 Add BatchPlaybackUrls schema in vod-player/backend/app/schemas.py
- [x] T007 Create aggregation service with compute_aggregated_session() in vod-player/backend/app/services/aggregation.py
- [x] T008 Add GET /sessions/{session_id}/aggregated endpoint in vod-player/backend/app/routers/api.py
- [x] T009 Add GET /sessions/by-path/{anchor_name}/{session_timestamp} endpoint in vod-player/backend/app/routers/api.py
- [x] T010 Add POST /segments/batch-urls endpoint for pre-fetching in vod-player/backend/app/routers/api.py

**Checkpoint**: Backend API ready - frontend implementation can now begin

---

## Phase 3: User Story 1 - Play Session as Continuous Video (Priority: P1) 🎯 MVP

**Goal**: Enable seamless continuous playback across all segments without user intervention

**Independent Test**: Play a multi-segment session and verify it plays from segment 0 through the last segment continuously without stopping

### Implementation for User Story 1

- [x] T011 [US1] Create timeline.ts service with SegmentTimeline interface and buildTimeline() function in vod-player/frontend/src/services/timeline.ts
- [x] T012 [US1] Add findSegmentForPosition() function to calculate segment + offset from unified position in vod-player/frontend/src/services/timeline.ts
- [x] T013 [US1] Create api.ts additions for getAggregatedSession() and batchGetPlayUrls() in vod-player/frontend/src/api/index.ts
- [x] T014 [US1] Create AggregatedPlayer.vue component with canvas overlay for seamless transitions in vod-player/frontend/src/components/AggregatedPlayer.vue
- [x] T015 [US1] Implement segment pre-fetching logic (5-second threshold) in AggregatedPlayer.vue
- [x] T016 [US1] Implement automatic segment advancement on 'ended' event in AggregatedPlayer.vue
- [x] T017 [US1] Add unified progress bar showing total duration in AggregatedPlayer.vue
- [x] T018 [US1] Integrate AggregatedPlayer into Player.vue replacing single-segment player in vod-player/frontend/src/views/Player.vue

**Checkpoint**: User Story 1 complete - continuous playback works without seeking

---

## Phase 4: User Story 2 - Seek Across Segments (Priority: P2)

**Goal**: Enable seeking to any position in the unified timeline, loading correct segment automatically

**Independent Test**: Seek to positions across different segments and verify correct segment loads at correct offset

### Implementation for User Story 2

- [x] T019 [US2] Add handleUnifiedSeek() method to AggregatedPlayer.vue that maps position to segment in vod-player/frontend/src/components/AggregatedPlayer.vue
- [x] T020 [US2] Implement segment switching on seek (load new segment if different from current) in AggregatedPlayer.vue
- [x] T021 [US2] Add progress bar click handler for seeking in AggregatedPlayer.vue
- [x] T022 [US2] Update time display to show unified position (not segment position) in AggregatedPlayer.vue

**Checkpoint**: User Story 2 complete - seeking works across entire session

---

## Phase 5: User Story 3 - Session Duration Display (Priority: P3)

**Goal**: Display total session duration (sum of converted segments) in session lists

**Independent Test**: View session list and verify displayed duration matches sum of segment durations

### Implementation for User Story 3

- [x] T023 [US3] Update SessionTree.vue to display total_duration from aggregated endpoint in vod-player/frontend/src/components/SessionTree.vue
- [x] T024 [US3] Add formatDuration() utility for HH:MM:SS display in vod-player/frontend/src/services/timeline.ts
- [x] T025 [US3] Update Home.vue session preview to show aggregated duration in vod-player/frontend/src/views/Home.vue

**Checkpoint**: User Story 3 complete - durations display correctly

---

## Phase 6: User Story 4 - Segment-Level Navigation (Priority: P4)

**Goal**: Optional segment markers and list for jumping to specific segments

**Independent Test**: Click segment markers and verify playback jumps to correct segment start

### Implementation for User Story 4

- [x] T026 [US4] Add segment markers to progress bar (thin vertical lines at boundaries) in AggregatedPlayer.vue
- [x] T027 [US4] Add collapsible segment list sidebar showing segment index and duration in AggregatedPlayer.vue
- [x] T028 [US4] Implement click-to-jump on segment list items in AggregatedPlayer.vue

**Checkpoint**: User Story 4 complete - segment navigation available

---

## Phase 7: User Story 5 - Resume Playback Position (Priority: P3)

**Goal**: Persist and restore playback position using browser localStorage

**Independent Test**: Play session to 50%, close browser, reopen same URL, verify playback resumes at 50%

### Implementation for User Story 5

- [x] T029 [US5] Create playback.ts store with PlaybackState interface in vod-player/frontend/src/stores/playback.ts
- [x] T030 [US5] Implement savePosition() with 5-second throttle in vod-player/frontend/src/stores/playback.ts
- [x] T031 [US5] Implement loadPosition() with validation (position <= duration, 30-day expiry) in vod-player/frontend/src/stores/playback.ts
- [x] T032 [US5] Implement clearPosition() for completed videos in vod-player/frontend/src/stores/playback.ts
- [x] T033 [US5] Integrate playback store with AggregatedPlayer - save on timeupdate, load on mount in AggregatedPlayer.vue
- [x] T034 [US5] Handle edge case: saved position exceeds available duration (reset to 0) in AggregatedPlayer.vue

**Checkpoint**: User Story 5 complete - playback position persists

---

## Phase 8: User Story 6 - Shareable Human-Readable URLs (Priority: P3)

**Goal**: Use URLs with anchor name and timestamp instead of numeric session IDs

**Independent Test**: Navigate to session, verify URL shows /{anchor_name}/{timestamp} format

### Implementation for User Story 6

- [x] T035 [US6] Add new route /:anchorName/:sessionTimestamp in vod-player/frontend/src/router/index.ts
- [x] T036 [US6] Update Player.vue to accept route params and call getSessionByPath() in vod-player/frontend/src/views/Player.vue
- [x] T037 [US6] Add getSessionByPath() API call in vod-player/frontend/src/api/index.ts
- [x] T038 [US6] Update SessionTree navigation to use new URL format in vod-player/frontend/src/components/SessionTree.vue
- [x] T039 [US6] Handle URL encoding/decoding for Chinese anchor names in router in vod-player/frontend/src/router/index.ts

**Checkpoint**: User Story 6 complete - human-readable URLs work

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Edge cases, error handling, and final integration

- [x] T040 [P] Add error handling for missing/corrupted segments (skip and notify) in AggregatedPlayer.vue
- [x] T041 [P] Add loading states during segment transitions in AggregatedPlayer.vue
- [x] T042 Handle single-segment sessions (bypass aggregation logic) in AggregatedPlayer.vue
- [ ] T043 Add auto-update when new segments finish converting (poll or websocket) in AggregatedPlayer.vue (DEFERRED - future enhancement)
- [x] T044 Update existing /player/:sessionId route to redirect to new URL format in vod-player/frontend/src/router/index.ts
- [ ] T045 Run quickstart.md validation scenarios (manual testing)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1 (P1): Can start after Phase 2
  - US2 (P2): Depends on US1 (extends AggregatedPlayer with seek)
  - US3 (P3): Can start after Phase 2 (independent of US1/US2)
  - US4 (P4): Depends on US1 (adds to AggregatedPlayer)
  - US5 (P3): Depends on US1 (integrates with AggregatedPlayer)
  - US6 (P3): Can start after Phase 2 (routing is independent)
- **Polish (Phase 9)**: Depends on US1 being complete

### User Story Dependencies

```
Phase 2: Foundational
     │
     ├──────────────────────────────────────┐
     │                                      │
     ▼                                      ▼
US1 (P1): Continuous Playback         US3 (P3): Duration Display
     │                                 US6 (P3): Human-Readable URLs
     │                                      (independent)
     ├──────────────────┐
     │                  │
     ▼                  ▼
US2 (P2): Seeking   US4 (P4): Segment Nav
                    US5 (P3): Resume Position
```

### Parallel Opportunities

**Within Phase 1 (Setup)**:
```
T002, T003, T004 can run in parallel
```

**Within Phase 2 (Foundational)**:
```
T005, T006 can run in parallel (different parts of schemas.py)
T008, T009, T010 can run in parallel after T007 (different endpoints)
```

**After Phase 2 completes**:
```
US1, US3, US6 can start in parallel (different files)
```

---

## Parallel Example: Starting After Foundational

```bash
# After Phase 2 completes, launch these in parallel:

# Team member A: User Story 1 (core playback)
Task: "Create timeline.ts service" in vod-player/frontend/src/services/timeline.ts
Task: "Create AggregatedPlayer.vue" in vod-player/frontend/src/components/AggregatedPlayer.vue

# Team member B: User Story 3 (duration display - independent)
Task: "Update SessionTree.vue" in vod-player/frontend/src/components/SessionTree.vue
Task: "Update Home.vue" in vod-player/frontend/src/views/Home.vue

# Team member C: User Story 6 (URLs - independent)
Task: "Add new route" in vod-player/frontend/src/router/index.ts
Task: "Add getSessionByPath() API" in vod-player/frontend/src/api/index.ts
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (backend API)
3. Complete Phase 3: User Story 1 (continuous playback)
4. **STOP and VALIDATE**: Test continuous playback independently
5. Deploy/demo if ready - this delivers core value

### Incremental Delivery

1. Setup + Foundational → Backend ready
2. Add User Story 1 → Continuous playback works → **MVP!**
3. Add User Story 2 → Seeking works → Better UX
4. Add User Story 3 + 6 (parallel) → Duration display + URLs → Polish
5. Add User Story 4 + 5 → Segment nav + Resume → Full feature
6. Polish phase → Error handling, edge cases

### Recommended Order for Solo Developer

1. T001-T004 (Setup)
2. T005-T010 (Foundational)
3. T011-T018 (US1: Continuous Playback) ← **MVP milestone**
4. T019-T022 (US2: Seeking)
5. T029-T034 (US5: Resume Position)
6. T035-T039 (US6: URLs)
7. T023-T025 (US3: Duration)
8. T026-T028 (US4: Segment Nav)
9. T040-T045 (Polish)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Backend (Phase 2) must complete before ANY frontend work
- US1 is the MVP - delivers core value alone
