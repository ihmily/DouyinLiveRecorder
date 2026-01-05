# Implementation Plan: VOD Player Frontend with Seekable Playback

**Branch**: `002-vod-player-frontend` | **Date**: 2026-01-06 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-vod-player-frontend/spec.md`

## Summary

Implement a VOD playback system with two main components:

1. **Recording Pipeline Enhancement**: Modify existing upload workflow to convert TS → Fast Start MP4 locally before OSS upload, using composable pipeline stages (CSP/DAG pattern)
2. **VOD Frontend Application**: Web-based UI for browsing recordings (Platform → Anchor → Session → Segments) and playing videos with instant seek via presigned URLs

## Technical Context

**Language/Version**: Python 3.10+ (backend), TypeScript (frontend)
**Primary Dependencies**:
- Backend: FastAPI, SQLAlchemy (existing), TOS SDK (existing), FFmpeg
- Frontend: Vue 3, Video.js, Element Plus
**Storage**: SQLite/PostgreSQL (existing DB), TOS/Volcano Engine Object Storage (existing bucket)
**Testing**: pytest (backend), Vitest (frontend)
**Target Platform**: Linux server (backend), Modern browsers (frontend)
**Project Type**: Web application (backend + frontend)
**Performance Goals**:
- Seek response < 1 second (SC-001)
- Playback start < 3 seconds (SC-002)
- Navigation tree < 2 seconds for 1000+ sessions (SC-006)
- 50 concurrent playback sessions (SC-007)
**Constraints**:
- Zero server bandwidth for video streaming (direct TOS access)
- FFmpeg must be available locally
- Presigned URL validity configurable (default 1 hour)
**Scale/Scope**: 10,000+ recordings, 50 concurrent viewers

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Recording Reliability** | ✅ PASS | Pipeline adds MP4 conversion step but preserves TS as fallback on failure |
| **II. Platform Abstraction** | ✅ PASS | VOD system is decoupled from platform-specific recording logic |
| **III. Configuration Simplicity** | ✅ PASS | VOD settings added to existing config.ini pattern |
| **IV. Async-First Architecture** | ✅ PASS | FastAPI async endpoints, background conversion worker |
| **V. Observable Operations** | ✅ PASS | Conversion status tracked in DB, logged with timestamps |

**Gate Result**: PASS - No violations. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/002-vod-player-frontend/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
# Recording pipeline enhancement (integrates with existing src/storage/)
src/
├── storage/
│   ├── pipeline.py          # NEW: CSP/DAG pipeline orchestration
│   ├── stages/              # NEW: Pipeline stage implementations
│   │   ├── __init__.py
│   │   ├── convert.py       # TS → MP4 conversion stage
│   │   └── upload.py        # OSS upload stage (refactored from existing)
│   ├── manager.py           # MODIFY: Integrate pipeline
│   └── models.py            # MODIFY: Add mp4_oss_path, mp4_status, duration

# VOD application (new separate directory)
vod-player/
├── Makefile                 # One-command dev/build/deploy workflows
├── docker-compose.yml       # Container orchestration
├── nginx.conf               # Production reverse proxy config
├── backend/
│   ├── main.py              # FastAPI application
│   ├── config.py            # Configuration (reads existing config.ini)
│   ├── schemas.py           # Pydantic response schemas
│   ├── requirements.txt     # Python dependencies
│   ├── Dockerfile           # Backend container
│   ├── routers/
│   │   └── api.py           # REST API endpoints
│   ├── services/
│   │   └── tos_sign.py      # Presigned URL generation
│   └── tests/
│       └── test_api.py
├── frontend/
│   ├── src/
│   │   ├── views/
│   │   │   ├── Home.vue     # Tree navigation
│   │   │   └── Player.vue   # Video player page
│   │   ├── components/
│   │   │   ├── SessionTree.vue
│   │   │   └── VideoPlayer.vue
│   │   ├── api/
│   │   │   └── index.ts     # API client
│   │   └── router/
│   │       └── index.ts     # Vue router
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile           # Frontend container
```

**Structure Decision**: Web application pattern with separate backend/frontend. Recording pipeline changes integrate into existing `src/storage/` module to minimize disruption.

## Development Workflow

### Prerequisites

- **uv** - Python package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Node.js 18+** - For frontend development
- **FFmpeg** - For video conversion

### Quick Start (via Makefile)

```bash
cd vod-player

make check      # Verify prerequisites (uv, Node, FFmpeg)
make install    # Install dependencies (uv sync + npm install)
make migrate    # Run database migration
make dev        # Start backend + frontend
```

### Available Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all dependencies |
| `make dev` | Start both backend and frontend |
| `make dev-backend` | Start backend only (port 8000) |
| `make dev-frontend` | Start frontend only (port 5173) |
| `make build` | Build frontend for production |
| `make docker-up` | Start with Docker Compose |
| `make health` | Check service health |

### URLs

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs

## Complexity Tracking

No violations requiring justification.
