# Quickstart: Docker Compose One-Click Deployment

**Feature Branch**: `006-docker-compose-deploy`
**Date**: 2026-01-07

## Prerequisites

- Docker Engine 20.10+ installed
- Docker Compose V2 installed (`docker compose` command available)
- At least 2GB RAM available for containers
- Ports 80, 5173, 8000 available (or configure alternatives)

## Quick Start (Development Mode)

```bash
# Clone and enter project
git clone https://github.com/your-repo/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# Start all services (development mode)
docker compose up -d

# View logs
docker compose logs -f

# Access services
# - Frontend: http://localhost:5173
# - Backend API: http://localhost:8000
# - API docs: http://localhost:8000/docs
```

## Quick Start (Production Mode)

```bash
# Start with production profile (nginx + static frontend)
docker compose --profile production up -d

# Access via nginx (single entry point)
# - All services: http://localhost
# - API: http://localhost/api/
```

## Configuration

### 1. Add Live Room URLs

Edit `config/URL_config.ini` to add streams to monitor:

```ini
# One URL per line
https://live.douyin.com/123456789
https://www.tiktok.com/@username/live

# Use quality prefix for specific streams
超清,https://live.douyin.com/987654321
```

Changes take effect on next monitoring cycle (default: 5 minutes).

### 2. Configure OSS Upload (Optional)

Edit `config/tos_credentials.ini`:

```ini
[credentials]
access_key = your_access_key
secret_key = your_secret_key
endpoint = https://tos-cn-beijing.volces.com
bucket = your-bucket-name
```

### 3. Adjust Recording Settings

Edit `config/config.ini` to change:
- Recording quality (原画/超清/高清/标清)
- Output format (ts/mkv/flv/mp4)
- Save path structure
- Notification settings

## Directory Structure

After first run, the project has this structure:

```
DouyinLiveRecorder/
├── docker-compose.yml    # Main orchestration file
├── config/               # Configuration (editable)
│   ├── config.ini
│   ├── URL_config.ini
│   └── tos_credentials.ini
├── data/                 # Database
│   └── recordings.db
├── downloads/            # Recorded videos
│   └── [streamer]/[date]/
└── logs/                 # Service logs
    ├── recorder/
    ├── backend/
    └── frontend/
```

## Common Operations

### View Service Status

```bash
docker compose ps
```

### Restart a Single Service

```bash
docker compose restart recorder
docker compose restart backend
docker compose restart frontend
```

### Stop All Services

```bash
docker compose down
```

### Update to Latest Version

```bash
docker compose pull
docker compose up -d
```

### View Real-time Logs

```bash
# All services
docker compose logs -f

# Single service
docker compose logs -f recorder
```

## Port Configuration

Create a `.env` file to customize ports:

```bash
# .env
BACKEND_PORT=8080
FRONTEND_DEV_PORT=3000
NGINX_PORT=8080
```

## Troubleshooting

### Services won't start

1. Check port availability:
   ```bash
   lsof -i :80 -i :5173 -i :8000
   ```

2. Check Docker resources:
   ```bash
   docker system df
   docker system prune  # If disk space is low
   ```

### Database errors

1. Check if data directory is writable:
   ```bash
   touch data/test && rm data/test
   ```

2. Check recorder logs:
   ```bash
   docker compose logs recorder | grep -i error
   ```

### Configuration not loading

1. Verify config files exist:
   ```bash
   ls -la config/
   ```

2. Check config file syntax (INI format)

3. Restart services after major config changes:
   ```bash
   docker compose restart
   ```

## Next Steps

1. Add live room URLs to `config/URL_config.ini`
2. Configure notifications in `config/config.ini` (optional)
3. Set up OSS for cloud backup (optional)
4. Monitor recordings via the VOD player frontend
