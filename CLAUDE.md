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

## Platform Support

Adding a new platform requires:
1. Add stream fetching function in `src/spider.py`
2. Add stream URL processor in `src/stream.py` (if needed)
3. Add URL pattern matching in `main.py`
4. Add cookie field in `config/config.ini` (if needed)
5. Add test entry in `demo.py`

## Active Technologies
- Python 3.10+ (backend), TypeScript (frontend) (002-vod-player-frontend)
- SQLite/PostgreSQL (existing DB), TOS (existing bucket) (002-vod-player-frontend)
- Python 3.10+ + FastAPI, TOS SDK (`tos` package), Pydantic (003-dual-oss-endpoint)
- SQLite (existing, no changes) (003-dual-oss-endpoint)
- Python 3.10+ (backend), TypeScript 5.3+ (frontend) (004-video-segment-aggregation)
- SQLite (existing recordings.db), localStorage (playback position) (004-video-segment-aggregation)
- Python >= 3.10 + SQLAlchemy 2.0+, tos (Volcano Engine TOS SDK), loguru, threading (005-oss-cleanup)
- SQLite (default, data/recordings.db), also supports PostgreSQL/MySQL via SQLAlchemy (005-oss-cleanup)
- Python >= 3.10 (existing project requirement) + SQLAlchemy 2.0+, `tos` (Volcano Engine TOS SDK), loguru, threading (005-oss-cleanup)
- Python 3.11 (recorder, backend), TypeScript 5.x (frontend), Docker Compose 3.8+ + Docker, Docker Compose, nginx (production profile) (006-docker-compose-deploy)
- SQLite (data/recordings.db), host filesystem (config, downloads, logs) (006-docker-compose-deploy)
- Python 3.11 (recorder, backend), TypeScript 5.x (frontend), Docker Compose 3.8+ + Docker, Docker Compose, nginx (production profile), `tos` SDK (TOS validation) (006-docker-compose-deploy)
- SQLite (data/recordings.db), host filesystem (config, downloads, logs), TOS (cloud upload) (006-docker-compose-deploy)

## Recent Changes
- 002-vod-player-frontend: Added Python 3.10+ (backend), TypeScript (frontend)
