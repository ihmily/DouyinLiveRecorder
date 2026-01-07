# Research: Docker Compose One-Click Deployment

**Feature Branch**: `006-docker-compose-deploy`
**Date**: 2026-01-07

## Research Areas

### 1. Docker Compose File Placement

**Question**: Should we replace the existing docker-compose.yaml at root or create a separate file?

**Decision**: Replace the existing `docker-compose.yaml` with an enhanced version

**Rationale**:
- The existing file only defines the recorder service
- Users expect `docker compose up` to work from project root
- A single file is simpler than managing multiple compose files
- The existing file structure (using `./config`, `./logs`, `./downloads` mounts) is already correct

**Alternatives Considered**:
- Separate `docker-compose.full.yml` - Rejected: adds complexity, users may use wrong file
- Keep existing, add `docker-compose.override.yml` - Rejected: harder to understand for new users

### 2. Service Dependency Order

**Question**: How should services depend on each other?

**Decision**: Recorder → Backend → Frontend/Nginx (with health checks)

**Rationale**:
- Recorder must start first to initialize database (recordings.db)
- Backend needs database to exist before starting (depends on recorder being healthy)
- Frontend/Nginx can connect to backend once API is ready
- Health checks ensure proper startup sequencing, not just container start

**Implementation**:
```yaml
recorder:
  healthcheck:
    test: ["CMD", "test", "-f", "/app/data/recordings.db"]
    interval: 10s
    timeout: 5s
    retries: 5

backend:
  depends_on:
    recorder:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 10s
    timeout: 5s
    retries: 5

frontend:
  depends_on:
    backend:
      condition: service_healthy
```

### 3. Volume Mount Best Practices

**Question**: Should we use named volumes or bind mounts for host directories?

**Decision**: Use bind mounts (host path mapping)

**Rationale**:
- User explicitly requested "外部可以access和管理这些文件" (external access and management)
- Bind mounts make files directly accessible in host filesystem
- Named volumes hide data in Docker's internal storage
- Config files need to be editable without Docker commands

**Volume Configuration**:
| Host Path | Container Path | Mode | Used By |
|-----------|----------------|------|---------|
| ./config | /app/config | ro | recorder |
| ./config | /config | ro | backend |
| ./data | /app/data | rw | recorder, backend |
| ./downloads | /app/downloads | rw | recorder |
| ./logs | /app/logs | rw | all services |

### 4. Environment Variable Strategy

**Question**: How should we pass configuration to containers?

**Decision**: Use environment variables for paths, read actual config from mounted files

**Rationale**:
- Existing code reads config from files (config.ini, tos_credentials.ini)
- Environment variables set paths to these files
- No code changes needed in application layer
- Users manage config via familiar INI file editing

**Environment Variables**:
```yaml
recorder:
  environment:
    - TZ=Asia/Shanghai

backend:
  environment:
    - DATABASE_URL=sqlite:///data/recordings.db
    - CONFIG_PATH=/config/config.ini
    - TOS_CREDENTIALS_PATH=/config/tos_credentials.ini
```

### 5. Development vs Production Profiles

**Question**: How should we support different deployment modes?

**Decision**: Use Docker Compose profiles

**Rationale**:
- Profiles are the standard Docker Compose way to handle optional services
- Production adds nginx for static file serving and API proxy
- Development runs frontend dev server with hot reload
- Default (no profile) runs development mode for easier local testing

**Profile Structure**:
```yaml
services:
  frontend-dev:
    # Development mode with hot reload
    profiles: ["dev"]

  nginx:
    # Production mode with static files
    profiles: ["production"]
```

### 6. Default Configuration Handling

**Question**: How should the system handle first-time startup with empty config?

**Decision**: Copy example config files during container startup if missing

**Rationale**:
- The project already has example files (e.g., `tos_credentials.ini.example`)
- Entrypoint script can check and copy if needed
- Avoids failing on first run
- Users can then edit the copied defaults

**Implementation Approach**:
- Create `scripts/docker-entrypoint.sh` for recorder service
- Script checks if config files exist, copies examples if not
- Then runs main.py

### 7. Log Directory Structure

**Question**: Should logs be separated by service or combined?

**Decision**: Separate subdirectories per service

**Rationale**:
- Easier to find logs for specific service
- Prevents filename collisions
- Allows different rotation policies per service
- Structure: `logs/recorder/`, `logs/backend/`, `logs/frontend/`

**Implementation**:
- Each service writes to its own subdirectory
- Log paths configured via environment or app config

### 8. Port Configuration

**Question**: Should ports be configurable or fixed?

**Decision**: Use environment variables with sensible defaults

**Rationale**:
- Users may have port conflicts on their hosts
- .env file pattern is standard for Docker Compose
- Defaults work out-of-box for most users

**Port Defaults**:
| Service | Default Port | Environment Variable |
|---------|--------------|---------------------|
| Backend API | 8000 | BACKEND_PORT |
| Frontend Dev | 5173 | FRONTEND_DEV_PORT |
| Nginx (prod) | 80 | NGINX_PORT |

## Summary of Decisions

1. **Single docker-compose.yml at root** - replaces existing minimal file
2. **Health-check based dependencies** - ensures proper startup order
3. **Bind mounts for all persistent data** - enables external file access
4. **Environment variables for paths only** - config remains in files
5. **Docker Compose profiles** - separates dev and production modes
6. **Entrypoint script for defaults** - copies example configs on first run
7. **Per-service log directories** - organized under ./logs/
8. **Configurable ports via .env** - with sensible defaults
