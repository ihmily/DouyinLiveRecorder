# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DouyinLiveRecorder is a multi-platform live stream recording tool built with Python. It supports 40+ streaming platforms (Douyin, TikTok, Kuaishou, Huya, Douyu, Bilibili, YouTube, Twitch, etc.) and uses FFmpeg for recording. The tool monitors live rooms and automatically records when streams go live.

## Commands

### Run the Application
```bash
# With Python directly
python main.py

# With uv (recommended)
uv run main.py
```

### Install Dependencies
```bash
# Using pip
pip install -r requirements.txt

# Using uv (recommended)
uv sync
```

### Test Platform Stream Fetching
```bash
# Edit demo.py to set the platform, then run:
python demo.py
```

## Architecture

### Core Components

- **`main.py`**: Entry point. Handles the main recording loop, configuration loading, thread management, and FFmpeg subprocess orchestration. Monitors `config/URL_config.ini` for live room URLs and spawns recording threads.

- **`src/spider.py`**: Platform-specific stream data fetchers. Contains async functions like `get_douyin_app_stream_data()`, `get_tiktok_stream_data()`, `get_bilibili_stream_data()`, etc. Each function fetches live status and stream URLs for its platform.

- **`src/stream.py`**: Stream URL processors. Takes raw stream data from spider functions and extracts the actual recording URLs (m3u8/flv) based on quality settings.

- **`src/room.py`**: Room/user ID resolution. Handles URL parsing, short link expansion, and extraction of room IDs and user IDs from various URL formats.

- **`src/ab_sign.py`**: Douyin signature generation (a_bogus algorithm) for API authentication.

- **`src/http_clients/`**: HTTP client wrappers for both sync (`sync_http.py`) and async (`async_http.py`) requests using httpx.

- **`msg_push.py`**: Notification handlers for live status updates. Supports DingTalk, WeChat, Telegram, email, Bark, ntfy, and pushplus.

- **`demo.py`**: Test harness for individual platform stream fetching. Maps platform names to spider functions for easy testing.

### Configuration Files

- **`config/config.ini`**: Main configuration (recording quality, proxy settings, save paths, notification settings, platform cookies)
- **`config/URL_config.ini`**: List of live room URLs to monitor (one per line)

### Key Patterns

- Stream fetching functions are **async** (use `asyncio.run()` when testing)
- Platform detection uses URL pattern matching in `main.py`
- Recording uses FFmpeg subprocess with configurable output format (ts/mkv/flv/mp4)
- The `trace_error_decorator` in `src/utils.py` provides standardized error logging

## Dependencies

- Python >= 3.10
- FFmpeg (must be installed separately on Linux/macOS)
- Node.js (for JavaScript-based signature algorithms, auto-checked on startup)
- Key packages: httpx, loguru, pycryptodome, PyExecJS

## Runtime Configuration (Git-ignored)

The following files and directories are **not tracked by git** but required at runtime:

### Required Configuration Files

1. **TOS Credentials** (required only if using OSS upload feature):
   ```bash
   cp config/tos_credentials.ini.example config/tos_credentials.ini
   # Edit with your Volcano Engine TOS credentials:
   # - endpoint, s3_endpoint, region
   # - bucket name
   # - access_key, secret_key
   ```

### Optional Configuration Files

1. **Environment Variables** (optional, for customizing Docker deployment):
   ```bash
   cp .env.example .env
   ```
   Docker Compose auto-reads `.env` and uses these variables (all have defaults):
   | Variable | Default | Purpose |
   |----------|---------|---------|
   | `BACKEND_PORT` | 8000 | Backend API port |
   | `FRONTEND_DEV_PORT` | 5173 | Vite dev server port |
   | `NGINX_PORT` | 80 | Production nginx port |
   | `TZ` | Asia/Shanghai | Container timezone |

   **Note**: If you're fine with defaults, you don't need to create `.env` at all.

### Runtime Directories (auto-created)

| Directory | Purpose |
|-----------|---------|
| `data/` | SQLite database (`recordings.db`) |
| `logs/` | Application logs (recorder, backend, frontend, nginx) |
| `downloads/` | Recorded video files |
| `backup_config/` | Configuration backups |

### Configuration Files (tracked)

| File | Purpose |
|------|---------|
| `config/config.ini` | Main settings: quality, proxy, save paths, cookies, OSS/VOD settings |
| `config/URL_config.ini` | Live room URLs to monitor (one per line, format: `URL,主播: name`) |

## Docker Deployment

### Quick Start
```bash
# Development mode (with Vite hot-reload)
docker compose --profile dev up -d

# Production mode (with nginx)
docker compose --profile production up -d

# Or use Makefile shortcuts
make up        # Development
make up-prod   # Production
```

### Services
| Service | Description | Port |
|---------|-------------|------|
| `recorder` | Live stream monitoring & FFmpeg recording | - |
| `backend` | FastAPI VOD API (metadata, signed URLs) | 8000 |
| `frontend-dev` | Vite dev server (dev profile only) | 5173 |
| `nginx` | Production reverse proxy (production profile only) | 80 |

### Volume Mounts
```
./config     -> /app/config    (recorder config)
./data       -> /app/data      (shared SQLite database)
./downloads  -> /app/downloads (recorded files)
./logs       -> /app/logs      (service logs)
```

## Database

- **Default**: SQLite at `data/recordings.db` (auto-created on first recording)
- **Alternative**: PostgreSQL/MySQL via `数据库URL` setting in `config/config.ini`
  - Example: `postgresql://user:pass@localhost/dbname`
  - Example: `mysql+pymysql://user:pass@localhost/dbname`
- Managed by SQLAlchemy 2.0+

## VOD Player

The `vod-player/` directory contains a web-based video player for recorded streams:

- **Backend** (`vod-player/backend/`): FastAPI service providing recording metadata and TOS-signed playback URLs
- **Frontend** (`vod-player/frontend/`): Vue 3 + TypeScript SPA with Video.js player

Configuration in `config/config.ini`:
```ini
[VOD设置]
启用VOD(是/否) = 是
签名有效期 = 3600
服务端口 = 8000
```

## Platform Support

Adding a new platform requires:
1. Add stream fetching function in `src/spider.py`
2. Add stream URL processor in `src/stream.py` (if needed)
3. Add URL pattern matching in `main.py`
4. Add cookie field in `config/config.ini` (if needed)
5. Add test entry in `demo.py`

## Technology Stack

| Component | Technology |
|-----------|------------|
| Recorder | Python 3.11, FFmpeg, httpx, loguru |
| Backend API | FastAPI, SQLAlchemy 2.0+, Pydantic |
| Frontend | Vue 3, TypeScript 5.x, Video.js |
| Cloud Storage | Volcano Engine TOS (`tos` SDK) |
| Database | SQLite (default), PostgreSQL/MySQL (optional) |
| Deployment | Docker Compose, nginx |
