# Implementation Plan: Docker Compose One-Click Deployment

**Branch**: `006-docker-compose-deploy` | **Date**: 2026-01-07 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-docker-compose-deploy/spec.md`

## Summary

Unify the three system components (recorder, backend API, frontend player) into a single docker-compose.yml at the project root. All persistent data (config, database, downloads, logs) is mounted from host directories as Docker volumes, enabling external access and management without entering containers. The system starts with a single `docker compose up` command and supports both development and production profiles.

**Additional Requirement (2026-01-07)**: Add runtime prerequisite validation that checks TOS credentials (access_key, secret_key) on startup and performs a basic API connectivity test (read/write) before the system begins recording operations.

## Technical Context

**Language/Version**: Python 3.11 (recorder, backend), TypeScript 5.x (frontend), Docker Compose 3.8+
**Primary Dependencies**: Docker, Docker Compose, nginx (production profile), `tos` SDK (TOS validation)
**Storage**: SQLite (data/recordings.db), host filesystem (config, downloads, logs), TOS (cloud upload)
**Testing**: Manual verification via `docker compose up` and service health checks
**Target Platform**: Linux server (primary), macOS, Windows with WSL2
**Project Type**: Multi-container application (3 services)
**Performance Goals**: All services healthy within 2 minutes of startup; TOS validation within 10 seconds
**Constraints**: Host directories must be writable, ports 80/5173/8000 available
**Scale/Scope**: Single-node deployment, 1-100 concurrent streams

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Compliance Notes |
|-----------|--------|------------------|
| I. Recording Reliability | ✅ PASS | Volume mounts ensure recordings persist; TOS validation prevents silent upload failures |
| II. Platform Abstraction | ✅ PASS | No changes to platform integration; docker-compose is orchestration only |
| III. Configuration Simplicity | ✅ PASS | Config files remain on host, editable without Docker knowledge; TOS validation uses existing tos_credentials.ini |
| IV. Async-First Architecture | ✅ PASS | No changes to application code; container orchestration is external |
| V. Observable Operations | ✅ PASS | Logs mounted to host directory; TOS validation logs clear status messages |

**Container Support Standards (from Constitution)**:
- ✅ Docker builds include all runtime dependencies (existing Dockerfiles)
- ✅ Volume mounts for config/ and downloads/ documented and implemented
- ✅ Container interruption warnings addressed via ts format recommendation

**Development Workflow (from Constitution)**:
- ✅ Configuration parsing fails fast with clear error messages - TOS validation aligns with this principle

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

# Prerequisite check script (NEW)
scripts/
└── check-prerequisites.sh   # TOS validation entrypoint wrapper

# Existing structure (unchanged except for entrypoint)
main.py                  # Recorder entry point
Dockerfile               # Recorder container (updated for entrypoint)

vod-player/
├── backend/
│   ├── Dockerfile       # Backend container (exists)
│   └── app/             # FastAPI application
├── frontend/
│   ├── Dockerfile       # Frontend container (exists)
│   └── src/             # Vite/TypeScript application
└── nginx.conf           # Production reverse proxy (exists)

# TOS validation module (NEW or integrated into existing)
src/
└── tos_validator.py     # TOS credential and connectivity validation

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

**Structure Decision**: The project already has separate Dockerfiles for each component. The new root-level docker-compose.yml orchestrates these existing containers with proper volume mounts and dependencies. A new `src/tos_validator.py` module handles TOS credential validation on startup.

## Complexity Tracking

No constitution violations requiring justification. The implementation adds orchestration configuration and startup validation without modifying core recording logic.

## TOS Validation Design

### Validation Flow

```
Container Start
      │
      ▼
┌─────────────────────────────┐
│ Check tos_credentials.ini   │
│ - access_key present?       │
│ - secret_key present?       │
│ - endpoint configured?      │
│ - bucket configured?        │
└─────────────────────────────┘
      │
      ▼ (credentials present)
┌─────────────────────────────┐
│ TOS Connectivity Test       │
│ 1. HeadBucket (check access)│
│ 2. PutObject (test write)   │
│ 3. GetObject (test read)    │
│ 4. DeleteObject (cleanup)   │
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Log Result                  │
│ - Success: "TOS verified"   │
│ - Auth fail: error + disable│
│ - Network: warning + retry  │
└─────────────────────────────┘
      │
      ▼
┌─────────────────────────────┐
│ Continue to main.py         │
│ (OSS enabled or disabled)   │
└─────────────────────────────┘
```

### Validation Outcomes

| Scenario | Log Message | Behavior |
|----------|-------------|----------|
| Credentials missing | "TOS credentials not configured - OSS upload disabled" | Continue, OSS disabled |
| Credentials invalid | "TOS authentication failed: [error]" | Continue, OSS disabled |
| Bucket not found | "TOS bucket not found: [bucket]" | Continue, OSS disabled |
| Network unreachable | "TOS endpoint unreachable - will retry periodically" | Continue, retry in background |
| All tests pass | "TOS connectivity verified - OSS upload enabled" | Continue, OSS enabled |
