# Contracts: Docker Compose One-Click Deployment

**Feature Branch**: `006-docker-compose-deploy`
**Date**: 2026-01-07

## No New Contracts

This feature is infrastructure-focused and introduces no new API endpoints or modifications to existing contracts.

### Existing Contracts

The system uses existing API contracts from:
- `specs/002-vod-player-frontend/contracts/` - VOD API endpoints

### Service Endpoints (Docker Compose)

The docker-compose.yml exposes these internal service endpoints:

| Service | Internal URL | External Port (Host) |
|---------|-------------|---------------------|
| Recorder | N/A (no API) | N/A |
| Backend | http://backend:8000 | ${BACKEND_PORT:-8000} |
| Frontend (dev) | http://frontend:5173 | ${FRONTEND_DEV_PORT:-5173} |
| Nginx (prod) | http://nginx:80 | ${NGINX_PORT:-80} |

### Health Check Endpoints

The following endpoints are used for health checks within Docker Compose:

| Service | Health Check Endpoint | Expected Response |
|---------|----------------------|-------------------|
| Backend | GET /health | 200 OK |
| Recorder | File check: /app/data/recordings.db exists | Exit 0 |

### Environment Variables

See `data-model.md` for the complete list of environment variables passed to services.
