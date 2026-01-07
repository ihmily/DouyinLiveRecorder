# Data Model: Docker Compose One-Click Deployment

**Feature Branch**: `006-docker-compose-deploy`
**Date**: 2026-01-07

## Overview

This feature is infrastructure-focused and introduces no new data entities. The existing data model remains unchanged:

- **recordings.db** (SQLite): Existing database storing recording metadata
- **config.ini**: Application configuration (recording quality, proxy, notifications)
- **URL_config.ini**: List of live room URLs to monitor
- **tos_credentials.ini**: OSS/TOS credentials for cloud upload

## Volume Mapping Specification

The following defines how data moves between host and containers:

### Configuration Volume

| Attribute | Value |
|-----------|-------|
| **Host Path** | `./config` |
| **Container Paths** | `/app/config` (recorder), `/config` (backend) |
| **Mount Mode** | Read-only (ro) |
| **Contents** | config.ini, URL_config.ini, tos_credentials.ini |
| **Ownership** | Host user (editable externally) |

### Data Volume

| Attribute | Value |
|-----------|-------|
| **Host Path** | `./data` |
| **Container Paths** | `/app/data` (recorder), `/data` (backend) |
| **Mount Mode** | Read-write (rw) |
| **Contents** | recordings.db |
| **Ownership** | Container process (SQLite manages file) |

### Downloads Volume

| Attribute | Value |
|-----------|-------|
| **Host Path** | `./downloads` |
| **Container Path** | `/app/downloads` (recorder only) |
| **Mount Mode** | Read-write (rw) |
| **Contents** | Recorded video files organized by streamer/date |
| **Ownership** | Container process (FFmpeg writes files) |

### Logs Volume

| Attribute | Value |
|-----------|-------|
| **Host Path** | `./logs` |
| **Container Paths** | `/app/logs` (all services) |
| **Mount Mode** | Read-write (rw) |
| **Contents** | recorder/, backend/, frontend/ subdirectories |
| **Ownership** | Container processes |

## File Lifecycle

### First Run Behavior

1. If `./config` is empty or missing config files:
   - Recorder entrypoint copies default templates
   - `config.ini.example` → `config.ini`
   - `URL_config.ini.example` → `URL_config.ini`
   - `tos_credentials.ini.example` → `tos_credentials.ini`

2. If `./data` is empty:
   - Recorder creates `recordings.db` on first recording
   - Backend waits for database to exist (health check)

3. Directories `./downloads` and `./logs` are created automatically by Docker if missing

### Upgrade Behavior

- Volume data persists across container rebuilds
- Database migrations run automatically on recorder startup
- Configuration files are never overwritten (user modifications preserved)

## No API Changes

This feature adds no new API endpoints or modifies existing contracts. The backend API remains unchanged:
- GET /api/recordings - List recordings (reads from recordings.db)
- GET /api/stream/{id} - Get signed stream URL (uses tos_credentials.ini)

See existing contracts in `specs/002-vod-player-frontend/contracts/` for API documentation.
