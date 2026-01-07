# Implementation Plan: Docker Compose One-Click Deployment

**Branch**: `006-docker-compose-deploy` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-docker-compose-deploy/spec.md`

## Summary

Unify the three system components (recorder, backend API, frontend player) into a single docker-compose.yml at the project root. All persistent data (config, database, downloads, logs) is mounted from host directories as Docker volumes, enabling external access and management without entering containers. The system starts with a single `docker compose up` command and supports both development and production profiles.

## Technical Context

**Language/Version**: Python 3.11 (recorder, backend), TypeScript 5.x (frontend), Docker Compose 3.8+
**Primary Dependencies**: Docker, Docker Compose, nginx (production profile)
**Storage**: SQLite (data/recordings.db), host filesystem (config, downloads, logs)
**Testing**: Manual verification via `docker compose up` and service health checks
**Target Platform**: Linux server (primary), macOS, Windows with WSL2
**Project Type**: Multi-container application (3 services)
**Performance Goals**: All services healthy within 2 minutes of startup
**Constraints**: Host directories must be writable, ports 80/5173/8000 available
**Scale/Scope**: Single-node deployment, 1-100 concurrent streams

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Compliance Notes |
|-----------|--------|------------------|
| I. Recording Reliability | ✅ PASS | Volume mounts ensure recordings persist; ts format recommendation documented |
| II. Platform Abstraction | ✅ PASS | No changes to platform integration; docker-compose is orchestration only |
| III. Configuration Simplicity | ✅ PASS | Config files remain on host, editable without Docker knowledge |
| IV. Async-First Architecture | ✅ PASS | No changes to application code; container orchestration is external |
| V. Observable Operations | ✅ PASS | Logs mounted to host directory for external access |

**Container Support Standards (from Constitution)**:
- ✅ Docker builds include all runtime dependencies (existing Dockerfiles)
- ✅ Volume mounts for config/ and downloads/ documented and implemented
- ✅ Container interruption warnings addressed via ts format recommendation

## Project Structure

### Documentation (this feature)

```text
specs/006-docker-compose-deploy/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (minimal - infrastructure feature)
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (N/A - no API changes)
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
# Root-level docker-compose.yml (NEW - main deliverable)
docker-compose.yml       # Unified orchestration file (replaces existing)

# Existing structure (unchanged)
main.py                  # Recorder entry point
Dockerfile               # Recorder container (exists)

vod-player/
├── backend/
│   ├── Dockerfile       # Backend container (exists)
│   └── app/             # FastAPI application
├── frontend/
│   ├── Dockerfile       # Frontend container (exists)
│   └── src/             # Vite/TypeScript application
└── nginx.conf           # Production reverse proxy (exists)

# Host-mounted directories (created on first run if needed)
config/                  # Configuration files (mounted read-only to recorder/backend)
├── config.ini
├── URL_config.ini
└── tos_credentials.ini

data/                    # Database (mounted read-write to recorder/backend)
└── recordings.db

downloads/               # Recorded videos (mounted read-write to recorder)
└── [streamer]/[date]/

logs/                    # Runtime logs (mounted read-write to all services)
├── recorder/
├── backend/
└── frontend/
```

**Structure Decision**: The project already has separate Dockerfiles for each component. The new root-level docker-compose.yml orchestrates these existing containers with proper volume mounts and dependencies. No structural changes to application code are needed.

## Complexity Tracking

No constitution violations requiring justification. The implementation adds only orchestration configuration without modifying core application logic.
