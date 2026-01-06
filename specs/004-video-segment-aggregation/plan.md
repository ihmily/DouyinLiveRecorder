# Implementation Plan: Video Segment Aggregation

**Branch**: `004-video-segment-aggregation` | **Date**: 2026-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-video-segment-aggregation/spec.md`

## Summary

Enable seamless playback of multi-segment recording sessions as a single continuous video. Currently, users must manually click through each 10-minute segment; this feature aggregates all converted segments into a unified timeline with continuous playback, cross-segment seeking, playback position persistence, and human-readable URLs.

**Technical Approach**: Implement a virtual playlist system in the frontend that:
1. Calculates cumulative time offsets for each segment to create a unified timeline
2. Pre-fetches next segment URLs for seamless transitions
3. Maps seek positions to correct segment + offset combinations
4. Persists playback state in localStorage
5. Uses human-readable URL routing with anchor name and session timestamp

## Technical Context

**Language/Version**: Python 3.10+ (backend), TypeScript 5.3+ (frontend)
**Primary Dependencies**:
- Backend: FastAPI >= 0.109.0, SQLAlchemy >= 2.0.0, Pydantic >= 2.5.0, TOS SDK >= 2.6.0
- Frontend: Vue 3.4.0, Vue Router 4.2.0, Video.js 8.10.0, Element Plus 2.5.0, Axios 1.6.0
**Storage**: SQLite (existing recordings.db), localStorage (playback position)
**Testing**: pytest (backend), Vitest (frontend - to be configured)
**Target Platform**: Web browser (Chrome, Firefox, Safari, Edge)
**Project Type**: Web application (existing vod-player frontend + backend)
**Performance Goals**:
- Segment transitions < 2 seconds (SC-002)
- Seek operations < 3 seconds (SC-003)
- 95% seamless transitions (SC-005)
**Constraints**:
- Must work with existing TOS presigned URL system
- Must handle sessions with 12+ segments (2+ hours)
- Must exclude unconverted segments (mp4_status != COMPLETED)
**Scale/Scope**: Single user local deployment, typical session 1-20 segments

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Recording Reliability | ✅ PASS | Feature is read-only (VOD playback), does not affect recording |
| II. Platform Abstraction | ✅ PASS | No changes to spider.py or platform-specific code |
| III. Configuration Simplicity | ✅ PASS | No new config files; playback position stored in browser |
| IV. Async-First Architecture | ✅ PASS | Backend already async; frontend uses async/await |
| V. Observable Operations | ✅ PASS | Player events (ended, error) already logged; will add segment transition events |

**Gate Result**: PASS - No violations. Feature aligns with all constitution principles.

## Project Structure

### Documentation (this feature)

```text
specs/004-video-segment-aggregation/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── api-changes.yaml # OpenAPI spec for new/modified endpoints
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
vod-player/
├── backend/
│   └── app/
│       ├── routers/
│       │   └── api.py           # Modify: add aggregated session endpoint
│       ├── schemas.py           # Modify: add AggregatedSession schema
│       └── services/
│           └── aggregation.py   # NEW: timeline calculation service
└── frontend/
    ├── src/
    │   ├── components/
    │   │   ├── VideoPlayer.vue      # Modify: add playlist support
    │   │   └── AggregatedPlayer.vue # NEW: unified timeline player
    │   ├── views/
    │   │   └── Player.vue           # Modify: support new URL format
    │   ├── router/
    │   │   └── index.ts             # Modify: new route pattern
    │   ├── stores/
    │   │   └── playback.ts          # NEW: playback position persistence
    │   └── services/
    │       └── timeline.ts          # NEW: timeline calculation utilities
    └── tests/                       # NEW: add test directory
        └── unit/
            └── timeline.spec.ts
```

**Structure Decision**: Web application structure (Option 2) - extending existing vod-player/backend and vod-player/frontend directories.

## Complexity Tracking

> No constitution violations requiring justification.

N/A - All implementations follow existing patterns.
