# Quickstart: VOD Player Frontend

**Feature**: 002-vod-player-frontend
**Date**: 2026-01-06

## Prerequisites

- Python 3.10+
- Node.js 18+
- FFmpeg installed and in PATH
- Existing DouyinLiveRecorder setup with recordings
- TOS bucket with uploaded recordings

## Quick Start (Development)

### 1. Apply Database Migration

```bash
cd /path/to/DouyinLiveRecorder

# If using alembic
alembic upgrade head

# Or run migration manually (if not using alembic)
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

# Install dependencies
pip install fastapi uvicorn

# Start development server
uvicorn main:app --reload --port 8000
```

API available at: http://localhost:8000
OpenAPI docs at: http://localhost:8000/docs

### 3. Start VOD Frontend

```bash
cd vod-player/frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

Frontend available at: http://localhost:5173

## Configuration

### Backend Configuration

The VOD backend reads from existing `config/config.ini`:

```ini
[VOD设置]
# URL签名有效期（秒）
签名有效期=3600

# 是否启用VOD功能
启用VOD=是
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

### 1. Check API

```bash
curl http://localhost:8000/api/platforms
```

Expected: List of platforms with recordings.

### 2. Check Playback URL

```bash
# Get a segment ID from the API first
curl http://localhost:8000/api/segments/1/play
```

Expected: JSON with presigned URL.

### 3. Test Video Seek

Open frontend, navigate to a recording, play video, drag progress bar - should seek instantly.

## Production Deployment

### Docker Compose

```bash
cd vod-player
docker-compose up -d
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

## Next Steps

1. Run `/speckit.tasks` to generate implementation tasks
2. Start with Phase 1: Database migration
3. Implement pipeline stages
4. Build VOD API
5. Build frontend
