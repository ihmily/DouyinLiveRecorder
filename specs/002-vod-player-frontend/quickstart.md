# Quickstart: VOD Player Frontend

**Feature**: 002-vod-player-frontend
**Date**: 2026-01-06

## Prerequisites

- **uv** (Python package manager) - `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Python 3.10+
- Node.js 18+
- FFmpeg installed and in PATH
- Existing DouyinLiveRecorder setup with recordings
- TOS bucket with uploaded recordings

## Quick Start (One Command)

```bash
cd vod-player

# Check prerequisites
make check

# Install all dependencies
make install

# Run database migration
make migrate

# Start both backend and frontend
make dev
```

**That's it!** Open http://localhost:5173 in your browser.

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Available Make Commands

```bash
make help            # Show all available commands
make install         # Install all dependencies (backend + frontend)
make dev             # Start both servers in parallel
make dev-backend     # Start backend only
make dev-frontend    # Start frontend only
make build           # Build frontend for production
make docker-up       # Start with Docker Compose
make health          # Check if services are running
```

## Manual Setup (Alternative)

If you prefer not to use the Makefile:

### 1. Apply Database Migration

```bash
cd /path/to/DouyinLiveRecorder

# Run migration script
python migrations/001_add_vod_fields.py

# Or create tables directly
python -c "
from src.storage.database import DatabaseManager
from src.storage.models import Base
db = DatabaseManager.get_instance()
Base.metadata.create_all(db.engine)
"
```

### 2. Start VOD Backend

```bash
cd vod-player/backend

# Install dependencies with uv
uv sync

# Start development server
uv run uvicorn main:app --reload --port 8000
```

### 3. Start VOD Frontend

```bash
cd vod-player/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

## Configuration

### Backend Configuration

The VOD backend reads from existing `config/config.ini`:

```ini
[VOD设置]
# URL签名有效期（秒）
签名有效期=3600

# 是否启用VOD功能
启用VOD=是

# VOD后端服务端口
服务端口=8000
```

TOS credentials from existing `config/tos_credentials.ini`.

### Environment Variables (Optional)

```bash
# Override database URL
DATABASE_URL=sqlite:///data/recordings.db

# Override TOS settings
TOS_ACCESS_KEY=your_ak
TOS_SECRET_KEY=your_sk
TOS_ENDPOINT=tos-cn-beijing.volces.com
TOS_REGION=cn-beijing
TOS_BUCKET=your-bucket
```

## Verify Installation

### Quick Health Check

```bash
make health
```

### Manual Verification

```bash
# 1. Check API
curl http://localhost:8000/api/platforms

# 2. Check Playback URL (replace 1 with actual segment ID)
curl http://localhost:8000/api/segments/1/play

# 3. Test Video Seek
# Open frontend, navigate to a recording, play video, drag progress bar
```

## Production Deployment

### Option 1: Docker Compose (Recommended)

```bash
cd vod-player

# Build and start
make docker-build
make docker-up

# Or directly
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
make docker-down
```

### Option 2: Manual Deployment

```bash
# Build frontend
make build

# Start backend with production settings
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# Serve frontend/dist with Nginx
```

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name vod.example.com;

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Troubleshooting

### Segments show "pending" status

MP4 conversion hasn't run yet. Check:
1. FFmpeg is installed: `ffmpeg -version`
2. Recording pipeline includes conversion stage
3. Check logs for conversion errors

### Playback URL returns 403

Presigned URL expired or TOS credentials invalid. Check:
1. TOS credentials in config
2. System clock is synchronized
3. URL validity period in config

### Video doesn't seek instantly

MP4 missing faststart flag. Re-convert with:
```bash
ffmpeg -i input.ts -c copy -movflags faststart output.mp4
```

### Backend won't start

Check dependencies:
```bash
cd vod-player/backend
uv sync
```

### Frontend won't start

Check Node.js version and dependencies:
```bash
node --version  # Should be 18+
cd vod-player/frontend
rm -rf node_modules
npm install
```
