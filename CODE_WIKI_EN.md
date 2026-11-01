# DouyinLiveRecorder Project Architecture Document

English&nbsp;&nbsp;|&nbsp;&nbsp;[**简体中文**](CODE_WIKI.md)

## Table of Contents

- [Document Statistics and Index](#document-statistics-and-index)
- [Project Overview](#project-overview)
  - [Project Basic Information](#project-basic-information)
  - [Features](#features)
  - [Supported Platforms](#supported-platforms)
  - [Quality Code Reference](#quality-code-reference)
  - [Tech Stack](#tech-stack)
- [System Architecture](#system-architecture)
- [Directory Structure](#directory-structure)
- [Core Module Details](#core-module-details)
- [Key Classes and Functions](#key-classes-and-functions)
- [Dependencies](#dependencies)
- [Configuration File Reference](#configuration-file-reference)
- [How to Run](#how-to-run)
- [Packaging and Release](#packaging-and-release)
- [Design Patterns](#design-patterns)
- [Troubleshooting](#troubleshooting)
- [Contributing Guide](#contributing-guide)
- [Change Overview by Module (2026-10-17)](#change-overview-by-module-2026-10-17)
- [Change Overview by Module (2026-10-29)](#change-overview-by-module-2026-10-29)
- [Changelog](#changelog)

## Document Statistics and Index

> This section is a document map, not a source of truth. Counts are recomputed with the command below (measured 2026-10-31: **220** Markdown files, excluding `.git/`, `.venv/`, `node_modules/`, `__pycache__/`, `.mypy_cache/`, `.pytest_cache/`).
> `python -c "import pathlib; sk={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache'}; p=[x for x in pathlib.Path('.').rglob('*.md') if not (set(x.parts) & sk)]; print(len(p))"`

### Statistics Overview

The hand-maintained sources are the **5** root documents (`AGENTS.md` plus the CN/EN `README` / `CODE_WIKI` pairs), the **6** reference sub-documents under `docs/agent-reference/`, and the **4** archive volumes under `docs/changelog/`. `docs/worklog/` holds historical review artifacts; `.workbuddy/`, `.qoder/` and `.codebuddy/` are local tool data and are not change sources.

### Root Document Index

| File | Role | Main Content |
| --- | --- | --- |
| `AGENTS.md` | Coding agent conventions | Version source of truth, code style, project structure, dependency/test/build commands, key conventions |
| `README.md` | User/developer guide | Features, platforms, quick start, configuration, usage, Docker, development guide, FAQ, changelog |
| `CODE_WIKI.md` | Project architecture doc (Chinese) | Module details, dependencies, configuration, packaging/release, design patterns, troubleshooting, contributing, changelog index |
| `README_EN.md` | User/developer guide (English) | English counterpart of `README.md` |
| `CODE_WIKI_EN.md` | Project architecture doc (English) | English counterpart of this document; entries correspond one-to-one |

### Reference Sub-Document Index (`docs/agent-reference/`)

| File | Content |
| --- | --- |
| `project-structure.md` | Full directory tree |
| `measured-evidence.md` | One-off measured readings |
| `session-learnings.md` | Session learnings |
| `lock-classification.md` | Lock re-entrancy classification |
| `changelog-file-inventories.md` / `-en.md` | Changelog file-inventory archives (CN/EN) |

### Changelog Archive Index (`docs/changelog/`)

| File | Content |
| --- | --- |
| `code-wiki-history-zh.md` / `-en.md` | CODE_WIKI changelog history (including the current release window imported on 2026-10-31) |
| `release-notes-history-zh.md` / `-en.md` | README release-note history (including v4.5.0 / v4.4.0 / v4.3.0 imported on 2026-10-31) |

> Rotation rule: the root documents keep only the current release-window summary/index; detailed entries are moved verbatim into this directory. Archive volumes are append-only.

## Project Overview

### Project Basic Information

- **Project Name**: DouyinLiveRecorder (Douyin Live Recorder)
- **Description**: A live-stream recorder for 60+ platforms (Douyin, TikTok, YouTube, Kuaishou, etc.), with looped recording, multi-room recording and message push
- **Version**: 4.7.0 (single source of truth: `pyproject.toml`)
- **Python**: >=3.14
- **Author / License**: y123ao6 / MIT
- **Entry points**: `douyin-recorder` → `main:main`; `douyin-recorder-gui` → `gui:main`; `douyin-recorder-web` → `web:main`
- **Project URL**: [GitHub](https://github.com/y123ao6/DouyinLiveRecorder)

### Features

- ✅ Supports 60+ live streaming platforms (Douyin, TikTok, YouTube, Kuaishou, Huya, Douyu, Bilibili, Xiaohongshu, etc.)
- ✅ Continuously monitors live status; auto-records when a stream starts and auto-stops when it ends
- ✅ Multiple output video formats: TS, MKV, FLV, MP4, MP3, M4A
- ✅ Three run modes: CLI + GUI + Web management panel
- ✅ Multi-platform message push: DingTalk, WeChat, email, Telegram, Bark, NTFY, PushPlus
- ✅ Docker containerized deployment
- ✅ Internationalization support (Simplified Chinese / English (US) / English (UK) / Traditional Chinese)
- ✅ Flexible configuration: quality selection, segmented recording, custom save paths, etc.
- ✅ Actual quality feedback and downgrade alerting (supports Douyin, TikTok, Kuaishou, Huya, Douyu, Bilibili, NetEase CC)
- ✅ Web security: Token authentication, path traversal protection, sensitive config masking

### Supported Platforms

Summarized from `README.md`; currently **51** platforms are listed (README advertises 60+ externally, including platforms still being added):

**Domestic sites (37)**: Douyin | Kuaishou | Huya | Douyu | YY | Bilibili | Xiaohongshu | bigo | blued | NetEase CC | Qiandu Rebo | Maoer FM | Look Live | TwitCasting | Baidu | Weibo | Kugou | Huajiao | Liuxing | Acfun | Changliao | Inke | Yinbo | Zhihu | Haixiu | VV Planet | 17Live | Lang Live | Piaopiao | 6Rooms | Lehai | Huamao | Taobao | JD | Migu | Lianjie | Laixiu

**Overseas sites (14)**: TikTok | SOOP (formerly AfreecaTV) | PandaTV | WinkTV | TTingLive (formerly Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | YouTube | Faceit | Picarto

> Each platform's stream-parsing function lives in `src/stream.py`, and its data-fetching function lives in `src/spider.py`; for adding a new platform see "Contributing Guide → Adding New Platform Support".

### Quality Code Reference

Recording quality is expressed by codes; the corresponding Chinese names and descriptions are as follows (the config item `原画|超清|高清|标清|流畅` maps to this table):

| Quality Code | Chinese Name | Description |
| --- | --- | --- |
| OD | 原画 (Original) | Original Definition, highest quality |
| BD | 蓝光 (Blu-ray) | Blu-ray, ultra high definition |
| UHD | 超清 (Ultra HD) | Ultra HD |
| HD | 高清 (HD) | High Definition |
| SD | 标清 (SD) | Standard Definition |
| LD | 流畅 (Smooth) | Low Definition, lowest quality |

Platforms that support actual quality feedback and downgrade alerting: Douyin, TikTok, Kuaishou, Huya, Douyu, Bilibili, NetEase CC. When the quality actually delivered by the platform is lower than the configured quality, an alert is automatically raised and flagged.

### Tech Stack

| Technology | Purpose |
| --- | --- |
| Python 3.14+ | Core programming language |
| asyncio + httpx | Asynchronous network requests and async decorators |
| FFmpeg | Video recording and transcoding |
| Node.js + exejs/PyExecJS | Run JavaScript signing algorithms (exejs preferred, PyExecJS fallback) |
| Loguru | Structured logging |
| PySide6 (Qt6) | GUI and system tray (the window layer is `src/gui_qt/`; both the GUI and Web entry trays use QSystemTrayIcon (since 2026-10-20); the tkinter/ttk implementation was fully removed on 2026-10-31) |
| Starlette + uvicorn | Web management panel backend |
| HTML + CSS + JavaScript | Web management panel frontend |
| Docker | Containerized deployment |
| gettext (msgfmt) | Internationalization translation compilation |
| mypy | Static type checking (`disallow_untyped_defs = true`; CI gate, run for the host, linux and win32 targets) |
| basedpyright | Local strictness supplement (not run in CI) |
| websockets | Danmaku (live comments) WebSocket transport layer (`src/ws_client.py`, shared across platforms) |
| protobuf | Douyin danmaku protocol decoding (`src/proto/douyin_pb2`, protoc-generated module) |
| brotli | Bilibili danmaku decompression (protover=3 requires brotli decompression) |

## System Architecture

### Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
├──────────────────┬──────────────────────┬───────────────────────┤
│ 命令行 (main.py) │ GUI 图形界面 (gui.py)│ Web 面板 (web.py)     │
│                  │                      │ └ src/web_api.py      │
│                  │                      │ └ web/ (前端静态资源)  │
└──────────────────┴──────────────────────┴───────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        核心业务层                                │
├──────────────────────┬─────────────────────┬────────────────────┤
│  直播间管理 (room.py)│  数据爬虫 (spider.py)│  流解析 (stream.py)│
├──────────────────────┴─────────────────────┴────────────────────┤
│                    FFmpeg 录制进程管理                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                        基础设施层                                │
├──────────────────────┬─────────────────────┬────────────────────┤
│  日志 (logger.py)  │  工具 (utils.py)  │  代理 (proxy.py) │
├──────────────────────┴─────────────────────┴────────────────────┤
│                    配置管理 + 消息推送 (msg_push.py)             │
└─────────────────────────────────────────────────────────────────┘
```

### Workflow

1. **Configuration parsing phase**
   - Read the `config/config.ini` main configuration
   - Read the `config/URL_config.ini` live room list
   - Initialize the Node.js environment and FFmpeg path
2. **Live detection phase**
   - Use async tasks to concurrently detect multiple live rooms
   - Platform-specific API calls and signing algorithms
   - Dynamically adjust concurrency to avoid rate limiting
3. **Stream address acquisition phase**
   - Call each platform's live stream API
   - Select different qualities based on configuration (Original/Ultra HD/HD/SD/Smooth)
   - Feed back the quality actually delivered by the platform (`actual_quality`) and available tiers (`available_qualities`)
   - Validate stream address availability
4. **Recording execution phase**
   - Launch the FFmpeg subprocess
   - Monitor recording status in real time
   - Record the actual quality; output an alert log when quality is downgraded
   - Support segmented recording
   - Support transcoding to MP4
5. **Status notification phase**
   - Triggered by live-start/live-end events
   - Call the configured message push channels
   - Write logs

## Directory Structure

```
DouyinLiveRecorder/
├── config/                              # config.ini + URL_config.ini
├── assets/app.ico                       # application icon (GUI tray, Web favicon, packaged artifacts)
├── src/
│   ├── __init__.py                      # package init + Node.js env + danmaku registry/factory
│   ├── spider.py · stream.py · stream_select.py · scheduler.py
│   ├── room.py · utils.py · logger.py · proxy.py · ttwid.py
│   ├── node_install.py · ffmpeg_install.py · ffmpeg_master_download.py
│   ├── ffmpeg_linux_download.py · ffmpeg_proc.py · video_postprocess.py
│   ├── notify.py · recorder_status.py · config_io.py · config_bool.py · config_read.py
│   ├── cookie_cache.py · log_archive.py · startup_cleanup.py
│   ├── http_config.py · async_http.py · sync_http.py
│   ├── web_api.py · web_models.py · web_config.py · web_tray.py
│   ├── ui_theme.py · ui_scale.py · ui_i18n.py · ui_fonts.py · ui_icons.py
│   ├── gui_qt/                          # app · main_window · theme · widgets · tray · settings_dialog
│   │   ├── recorder.py · danmaku_monitor.py · quality_monitor.py · shared.py
│   │   └── pages/                       # dashboard · quality · config · runlog · danmaku
│   ├── base.py · collector.py · danmaku_monitor.py · srt_writer.py · ws_client.py
│   ├── platforms/                       # douyin · douyu · huya · bilibili · twitch · _tars · _xbogus
│   ├── proto/                           # douyin.proto · douyin_pb2.py · douyin_pb2.pyi
│   └── javascript/                      # crypto-js.min.js · x-bogus.js · haixiu.js · liveme.js · migu.js
├── web/                                 # index.html · app.js · motion.js · style.css
├── i18n/                                # zh_CN/LC_MESSAGES/{po,mo} · en_US.json · en_GB.json · zh_TW.yaml
├── scripts/                             # run_gates · check_* · compile_po · sync_metadata · smoke_test · sync_version
├── tests/                               # conftest.py · test_*.py · frontend/*.mjs
├── docs/                                # agent-reference/ · changelog/ · worklog/
├── .github/                             # workflows/{ci,build-release,docker-publish,issue-translator}.yml · actions/retry
├── main.py · gui.py · web.py            # CLI / GUI / Web entry points
├── i18n.py · msg_push.py · build_exe.py
├── requirements.txt · pyproject.toml · uv.lock
├── Dockerfile · docker-compose.yaml · .dockerignore · .gitignore
├── .gitattributes · .pre-commit-config.yaml · pyrightconfig.json · .coveragerc-concurrency
├── index.html · StopRecording.vbs
└── README.md · README_EN.md · CODE_WIKI.md · CODE_WIKI_EN.md · AGENTS.md
```

## Core Module Details

### 1. Main Program Module (`main.py`)

**Responsibility**: The command center of the entire recorder, responsible for workflow orchestration.

**Core functions**:

- Configuration file reading and parsing
- Live room URL list parsing
- Concurrency control and task scheduling
- FFmpeg process management
- Error retry and dynamic tuning
- Message push triggering
- Exit signal handling

**Key state variables**:

```python
recording: set              # 正在录制的直播间集合
monitoring: int             # 正在监控的直播间数
running_list: list          # 正在运行的 URL 列表
error_count: int            # 当前错误计数
error_window: list          # 错误时间窗口（用于动态调优）
url_tuples_list: list       # 解析后的 URL 配置列表 [(quality, url, anchor_name)...]
recording_time_list: dict   # 录制时间与画质记录 {name: [start_time, quality_zh, actual_quality_zh]}
```

**Main flow functions**:

- `main()` - entry function
- `read_config()` - read configuration
- `check_url_config()` - check URL configuration
- `start_recording()` - start recording (parses `actual_quality`, outputs an alert on downgrade)
- `stop_recording()` - stop recording
- `check_live_status()` - detect live status
- `display_info()` - terminal status display (compatible with old and new `recording_time_list` formats)
- `get_status()` - return recording status dict (includes the `actual_quality` field, used by the Web API)
- `select_source_url()` - selects between m3u8/FLV sources, falling back to FLV when HLS source validation fails (polling with `delay_default=120s`); a new `proxy_addr` parameter is passed through to the three validation calls to avoid misjudging proxy-required platforms like TikTok as unreachable on direct validation; computes the "last-resort candidate" (when FLV has no `record_url` fallback, or `record_url` is always present) and passes it to the validator as `last_resort` — even a stable rejection only warns and passes through, leaving the final decision to ffmpeg's actual stream pull; **HLS capture exclusion list** (`main.hls_collection_exclude_platforms`, config key "HLS采集排除平台(逗号分隔)"): listed platforms ignore the "whether to enable HLS capture" setting and always use FLV capture (equivalent to disabling HLS capture for that platform only — the whole HLS candidate group is removed with no fallback; when only HLS sources remain with no fallback, it warns and gives up the round, with recovery guidance pointing to removing the platform from the exclusion list); platforms outside the list behave unchanged
- `_validate_stream_url()` - stream address validation: the content-type check now also accepts `mpegurl`; when HEAD is rejected, for `.m3u8` sources (including **404**) it adds a `Range: bytes=0-0` GET probe — Douyin CDN's m3u8 often returns 4xx to HEAD, which used to be misjudged as unreachable and always fell back to FLV; a new `verify` parameter follows the global SSL switch (consistent with async validation); all failure paths now log a warning (URL + exception type/status code/content-type) instead of silently swallowing the exception; the GET re-check (`_confirm_get_ok`) retries once verbatim (0.8s interval) when receiving 401/403 before convicting — CDNs such as Douyu hw/Huya al occasionally return 403 to millisecond-level back-to-back probes (HEAD→GET) (in practice the same URL returns 200 after a brief retry, and ffmpeg's single GET works normally); the retry distinguishes "intermittent rate limiting" from "stable rejection", and the historically false-green Huya scenario that still returns 403 after retry is correctly rejected

**Refactoring (2026-08-16)**: The following responsibilities have been extracted into `src/` submodules, re-exported by `main.py` to preserve `main.<name>` namespace compatibility (zero changes to `web.py`/`gui.py`/`web_api.py`/tests):

- FFmpeg process management → `src/ffmpeg_proc.py` (process register/unregister/terminate/cleanup)
- Video post-processing (segment/transcode/subtitle) → `src/video_postprocess.py`
- Stream address selection/validation/quality-code/Douyin rate-limit → `src/stream_select.py` (`select_source_url`/`_validate_stream_url`/`get_quality_code`/`_douyin_rate_limit`, etc.)
- Push/script/success-failure counting/concurrency adjustment → `src/notify.py` (`push_message`/`record_error`/`record_success`/`adjust_max_request`/`clear_record_info`, etc.)
- Recording status snapshot/display → `src/recorder_status.py` (`get_status`/`display_info`)
- Config read/write/safe numeric conversion/backup → `src/config_io.py` (`update_file`/`delete_line`/`read_config_value`/`_safe_int`/`_safe_float`/`backup_file`/`backup_file_start`)

Modules deeply coupled to main's globals uniformly use a runtime `import main` to lazily access globals, avoiding parameter bloat at call sites during startup; a `__main__` guard is added at the top of `main.py` to prevent a submodule's `import main` from re-executing the entire file when running `python main.py`.

**Room recording thread closure fix (2026-08-16)**: When adding a new live room, a daemon thread is spawned for each URL to run `start_record`. The original implementation used "default-argument binding of loop variables" (`def _room_thread_target(_key=thread_key, _args=args)`) to avoid the closure late-binding trap, and `_args: tuple[Any, ...]` used an explicit `Any` that the project's basedpyright globally disallows. After the fix:

- `_args` is concretized to `tuple[tuple[str, str, str], int]` (`url_tuple` is `tuple[str, str, str]`, consistent with the `start_record(url_data, count_variable)` signature);
- the current loop value is explicitly bound at thread creation via `threading.Thread(target=..., args=(thread_key, args))`, removing the default-argument hack for clearer and more maintainable semantics;
- the thread still cleans up on exit with `finally: create_var.pop(_key, None)`, preventing unbounded growth of the `create_var` dict.

**Danmaku recording integration (finalized wiring on 2026-08-16)**: Each platform branch of `start_record` collects `record_danmaku_args` (reset to `None` each round) → all 6 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` calls are wired up → `get_danmaku_collector(platform, args, base_filename, segment_seconds)` creates the collector. The collector calls `stop()` outside the `while process.poll() is None` loop (`DanmakuCollector.stop()` has `_stop_called` to prevent re-entry, idempotent). Segmented filename convention: the ffmpeg video segment template is unified to `_%03d` (FLV aligned from `_%02d`; audio still uses `_%02d` but has no danmaku), SRT shards use `{seg:03d}` (`_000.srt` pairs with `_000.ts`); `check_subprocess` also strips the `_%02d`/`_%03d` placeholders. When Douyin has an empty cookie, `DouyinDanmaku.start()` dynamically fetches it via `await get_ttwid()` inside the coroutine (the collection thread has its own event loop, so it can `await` directly; process-level cache). "Danmaku shard duration (seconds)" goes through `_safe_float(..., 1800.0)`. The danmaku platform registry is `get_danmaku_class` in `src/__init__.py` (Douyu Live / Bilibili Live / Huya Live / Douyin Live / TwitchTV).

**Room log correlation field binding (2026-09-20)**: `start_record`, being the room-thread body, calls `set_room_context(f"序号{count_variable}")` at the **thread entry** (otherwise the logs that precede `record_name` — exit flag / commented-out exit / resolution failure / breaker back-off — could not be attributed to a room), and upgrades the value to the full room name after each round assigns `record_name = f"序号{count_variable} {anchor_name}"`. How the field reaches the log line, and which threads do or do not carry it, is documented in "6. Logging Module" and the `AGENTS.md` "Known pitfalls" entry.

### 2. Spider Module (`src/spider.py`)

**Responsibility**: Responsible for fetching live room data from each major streaming platform.

**Supported platforms**:

Domestic: Douyin, Kuaishou, Huya, Douyu, YY, Bilibili, Xiaohongshu, bigo, blued, NetEase CC, Qiandu Rebo, Maoer FM, Look Live, TwitCasting, Baidu, Weibo, Kugou, Huajiao, Liuxing, Acfun, Changliao, Inke, Yinbo, Zhihu, Haixiu, VV Planet, 17Live, Lang Live, Piaopiao, 6Rooms, Lehai, Huamao, Taobao, JD, Migu, Lianjie, Laixiu

Overseas: TikTok, SOOP (formerly AfreecaTV), PandaTV, WinkTV, TTingLive (formerly Flextv), PopkonTV, TwitchTV, LiveMe, ShowRoom, CHZZK, Shopee, YouTube, Faceit, Picarto

**Key functions**:

- `get_douyin_web_stream_data()` - fetch Douyin Web-end live data (prefers the `web/enter` API, silently retries once on failure, then falls back to HTML scraping)
- `get_douyin_app_stream_data()` - fetch Douyin App-end live data (fallback; contains built-in URL dispatch logic, see "Douyin URL Dispatch" below)
- `get_tiktok_stream_data()` - fetch TikTok live data
- `get_youtube_stream_data()` - fetch YouTube live data
- `get_bilibili_stream_data()` - fetch Bilibili live stream data (returns a dict containing url/current_qn/accept_qn)
- `get_play_url_list()` - fetch clarity options from the M3U8 playlist
- `get_params()` - extract parameters from URL

**Douyin URL dispatch logic** (`get_douyin_app_stream_data`, optimized on 2026-08-01):

| URL Form | Handling Path |
| --- | --- |
| `live.douyin.com/<room number or Douyin ID>` | Directly calls `get_douyin_web_stream_data` (the `web/enter` API accepts Douyin IDs, no redirect resolution needed) |
| `www.douyin.com/user/<sec_uid>` (web homepage) | Skips the doomed-to-fail `get_sec_user_id` probe and uses `resolve_from_homepage()`: `get_unique_id()` resolves the Douyin ID → assembles `live.douyin.com/<Douyin ID>` → directly calls the web endpoint |
| `v.douyin.com/<short link>` (App short link, may point to a live room or homepage) | First `get_sec_user_id()` to follow the redirect; on `UnsupportedUrlError` falls back to `resolve_from_homepage()` |

- `resolve_from_homepage()` directly calls `get_douyin_web_stream_data` (web API preferred, with built-in HTML fallback), no longer routing through the old HTML-first scraping path (about 1MB page), and **explicitly passes through proxy_addr / cookies** (the old implementation did not, causing proxy and Cookie config to silently fail on the homepage path)
- The `web/enter` API call is wrapped as `_try_web_api()` + `for attempt in range(2)`: on first failure (e.g. transient risk-control `status_code=10002`) → `await asyncio.sleep(0.5)` to buffer → silent retry; on retry success returns directly, skipping the HTML fallback; only when both attempts fail is a WARNING logged and HTML fallback used (HTML scraping for the HEVC original is common behavior across all web-end paths and is unchanged)

**Implementation characteristics**:

- Uses the async HTTP client (`httpx`)
- Platform-specific signing algorithms
- Proxy support
- Cookie support
- Error retry mechanism
- The Bilibili spider returns a dict structure (containing `current_qn`/`accept_qn` metadata) for the stream module to feed back the actual quality

### 3. Live Stream Parsing Module (`src/stream.py`)

**Responsibility**: Parse live stream addresses, support multiple quality selection, and feed back the quality actually delivered by the platform.

**Quality mapping**:

```python
QUALITY_MAPPING = {"OD": 0, "BD": 1, "UHD": 2, "HD": 3, "SD": 4, "LD": 5}
QUALITY_MAPPING_BIT = {
    'OD': 99999, 'BD': 4000, 'UHD': 2000, 'HD': 1000, 'SD': 800, 'LD': 600
}
QUALITY_LEVEL = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}  # 等级值越大画质越低
QUALITY_CODE_TO_ZH = {"OD": "原画", "BD": "蓝光", "UHD": "超清", "HD": "高清", "SD": "标清", "LD": "流畅"}
NETEASE_QUALITY_MAP = {"blueray": "OD", "ultra": "UHD", "high": "HD", "standard": "SD"}
```

**Quality utility functions**:

- `bitrate_to_quality(bitrate)` - reverse-lookup the quality code from bitrate (0/unknown falls back to OD)
- `code_to_zh(code)` - convert quality code to Chinese name
- `is_downgrade(requested, actual)` - determine whether a downgrade occurred (actual level value > requested)
- `get_quality_index()` - parse the quality parameter and return an index
- `_pad_list()` - pad a list to a specified minimum length (some platforms now use explicit truncation instead)

**Per-platform stream address parsing functions**:

| Function | Platform | Actual-quality feedback method |
| --- | --- | --- |
| `get_douyin_stream_url()` | Douyin | Extract quality label from keys of `flv_pull_url` / `hls_pull_url_map` |
| `get_tiktok_stream_url()` | TikTok | Reverse-lookup via `bitrate_to_quality()` from the `vbitrate` field |
| `get_kuaishou_stream_url()` | Kuaishou | Reverse-lookup from the `bitrate` field of `flv_url_list` |
| `get_huya_stream_url()` | Huya | Map from the `exsphd` ratio value, handle downgrade selection |
| `get_douyu_stream_url()` | Douyu | Reverse-map from the platform-delivered `rate` field |
| `get_bilibili_stream_url()` | Bilibili | Reverse-map `current_qn` returned by spider into a quality code |
| `get_netease_stream_url()` | NetEase CC | Map from quality name (blueray/ultra/high) via `NETEASE_QUALITY_MAP` |

**Return value structure** (unified across platforms):

```python
{
    "is_live": True,
    "anchor_name": "主播名",
    "title": "直播标题",
    "quality": "UHD",              # 用户设置的画质
    "actual_quality": "UHD",       # 平台实际下发的画质
    "available_qualities": ["OD", "UHD", "HD"],  # 平台可用的画质档位
    "m3u8_url": "http://...",
    "flv_url": "http://...",
    "record_url": "http://...",
}
```

**Implementation characteristics**:

- Bandwidth-sorted clarity selection
- Automatic downgrade strategy (auto-downgrade when preferred quality is unavailable)
- FLV and M3U8 dual-protocol support
- Status code validation
- Explicit truncation replacing `_pad_list`'s silent padding, avoiding out-of-bounds
- Quality downgrade detection (`is_downgrade`), used by main.py for alerting
- Douyu FLV→m3u8 same-token HLS candidate: when `rtmp_live` ends with `.flv`, `get_douyu_stream_url` changes the path `.flv` to `.m3u8` (query string preserved as-is) and attaches it as `m3u8_url` — Douyu's wsAuth token works for both FLV and HLS (verified: hw CDN returns 200 + `application/vnd.apple.mpegurl`, two-level m3u8); when HLS collection is enabled it is validated and preferred via `select_source_url`, falling back to FLV when unreachable; HLS pulls segment-by-segment without maintaining a long connection, mitigating the repeated segmentation caused by the visitor-state FLV long connection being cut by the CDN after about 70 seconds

### 4. Live Room Info Module (`src/room.py`)

**Responsibility**: Parse live room URLs, extract room ID, anchor info, Douyin ID, etc.

**Key functions**:

- `get_sec_user_id()` - get the room ID and the user's sec_user_id
- `get_unique_id()` - get the Douyin ID (includes a 30-minute TTL sec_uid→Douyin-ID process-level cache, aligned with `ttwid.py`'s `threading.Lock` cross-thread/cross-asyncio-loop deduplication pattern)
- `is_user_homepage_url()` - determine whether a URL is in the "web anchor homepage" form (`douyin.com/user/<sec_uid>`; `v.douyin.com` short links do not belong to this category); used as a zero-request fast path — the sec_user_id is directly in the path, no request needed to follow a redirect
- `extract_sec_user_id()` - explicitly regex-extract sec_user_id from the URL
- `get_live_room_id()` - get the live room web ID
- `get_xbogus()` - generate the X-Bogus signature

**Exception handling**:

- `UnsupportedUrlError` - unsupported URL format exception

**Key constants and interfaces**:

- `DESKTOP_UA` - desktop Chrome UA. Interfaces such as `iesdouyin.com/web/api/v2/user/info/` will be silently rate-limited (HTTP 200 + empty body) if an old mobile UA is used; the desktop UA must be used
- Homepage parsing uses the JSON interface `https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid=<sec_uid>` (take `unique_id`, fall back to `short_id` if empty) — the old `iesdouyin.com/share/user/<sec_uid>` page is now a JS anti-scraping shell page, and HTML regex is unreliable

### 5. Utility Module (`src/utils.py`)

**Responsibility**: Provide general-purpose utility functions.

**Main utilities**:

| Utility Function | Description |
| --- | --- |
| `Color` class | Terminal color output constants |
| `trace_error_decorator()` | Error tracing decorator |
| `check_md5()` | Compute file MD5 |
| `dict_to_cookie_str()` | Convert cookie dict to string |
| `read_config_value()` | Read configuration file value |
| `update_config()` | Update configuration file |
| `remove_emojis()` | Remove emoji from text |
| `remove_duplicate_lines()` | Remove duplicate lines from a file |
| `handle_proxy_addr()` | Normalize proxy address format |
| `generate_random_string()` | Generate a random string |

### 6. Logging Module (`src/logger.py`)

**Responsibility**: Configure structured logging based on Loguru.

**Log output**:

- **Console**: colorized log output (`custom_format`, no room column)
- **`logs/streamget.log`**: DEBUG level (excluding INFO), line layout `time | level | room | module:function:line - message`
- **`logs/PlayURL.log`**: INFO level (live stream addresses only), line layout `time | room | message`
- **`logs/gui.log`**: written only by the GUI parent process (exclusive handle), carries no room column — the GUI process does not record, so the column would always be empty

**Room correlation field `extra[room]` (added 2026-09-20)**:

- Every line emitted by a room thread carries a stable correlation column, used to cut a single room's chain out of the interleaved multi-room log file (extraction command and boundaries: the identically named `AGENTS.md` "Known pitfalls" entry)
- Implementation: `ROOM_FIELD` plus `set_room_context()` / `get_room_context()` reading and writing a `ContextVar`, pushed into `record["extra"]` by the global patcher registered via `logger.configure(extra={ROOM_FIELD: ""}, patcher=_room_patcher)` **in the calling thread** (hence no cross-talk under `enqueue=True`); an explicit call-site `bind(room=...)` outranks the thread-level fallback
- The room thread binds `序号N` at the `main.py::start_record` entry and upgrades it to the full `record_name` once the anchor name resolves; `set_room_context("")` unbinds
- **The `extra` default must not be removed**: without it, formatting an unbound record raises `KeyError: 'room'`, loguru swallows it, prints `Logging error in Loguru Handler` to stderr for every line and drops the line; regression lock `tests/test_logger_room_context.py`
- Only the identifier was added: log levels, the two INFO/other `filter` buckets, `rotation` and `retention` are unchanged

**Log file switch**:

- Controlled via `是否启用日志文件(是/否)` in `config/config.ini`
- Enabled by default, preserving backward compatibility
- `logger.py` reads the configuration directly at initialization (not dependent on main.py execution order)

**Log rotation**: auto-rotates at 300 KB, keeping 1 backup

### 7. Message Push Module (`msg_push.py`)

**Responsibility**: Support multiple message push channels.

**Supported channels**:

| Channel | Function | Description |
| --- | --- | --- |
| DingTalk | `dingtalk()` | Group bot push |
| WeChat | `xizhi()` | Server酱 / WeChat |
| Telegram | `tg_bot()` | Bot message |
| Email | `send_email()` | SMTP protocol |
| Bark | `bark()` | iOS notification |
| NTFY | `ntfy()` | Open-source push service |
| PushPlus | `pushplus()` | WeChat push platform |

### 8. Internationalization Module (`i18n.py`)

**Responsibility**: A gettext-based multilingual support system that automatically translates `print` output from the project source code.

**Implementation mechanism**:

- `translated_print` wraps `builtins.print`, automatically translating output whose caller comes from the project root (`src/` package and top-level scripts like `main.py`); `main.py` unconditionally installs `builtins.print = translated_print` at import time (installed under any language — zh_CN/zh_TW translate English constant strings into Chinese, en_US/en_GB translate Chinese strings into English, unknown strings are returned identically)
- Supports both source-run and PyInstaller-packaged path detection (`_internal/i18n` vs `i18n/`)
- **Multi-format catalog loading (since 2026-08)**: `i18n.py` probes in order gettext `.mo` → `<lang>.json` → `<lang>.yaml`; all three formats are flat "original → translation" mappings with consistent behavior; `PyYAML` is a runtime dependency (only YAML format support is lost if missing). `_load_yaml_catalog()` catches `yaml.YAMLError` (not an OSError/ValueError subclass) — a corrupted yaml catalog returns None and degrades to the next format instead of letting `set_language` raise (web language-switch endpoint 500)
- **Hot language switch**: `set_language(lang)` normalizes (via the `normalize_language` alias table: `zh_cn`/`zh-CN`/`en`/`en-US`/`zh-Hant`/`zh_CN.UTF-8` and other spellings all work) then hot-swaps the `_tr` translation function without restarting the process. Three switch entry points: Web panel (`GET/PUT /api/language`, writes back to config + hot switch + redraws frontend `data-i18n` text; on `PUT`, a missing `language` config key now falls back to appending it at the end of its section instead of an unconditional 500), GUI (sidebar "Language" menu), CLI main loop (re-syncs per round from config)
- Default language: Simplified Chinese (zh_CN); supported languages: zh_CN / en_US / en_GB / zh_TW

**Translation files**:

| File | Description | Entries |
| --- | --- | --- |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` | Simplified Chinese translation source (gettext, editable) | 496 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | Compiled binary translation (the only file gettext reads at runtime, distributed with repo/image) | 496 |
| `i18n/en_US.json` | US English catalog (JSON format, English source identical + Chinese source translated to English) | 496 |
| `i18n/en_GB.json` | UK English catalog (JSON format, British spelling: minimise/unrecognised, etc.) | 496 |
| `i18n/zh_TW.yaml` | Traditional Chinese catalog (YAML format, simplified→traditional character conversion + Taiwan usage adaptation) | 496 |

**Maintenance workflow**: After modifying `.po` you must run `python scripts/compile_po.py` to recompile and commit the `.mo` together, otherwise translation changes will not take effect; `python scripts/compile_po.py --check` (CI `static` job) blocks when the two are out of sync — internally `write_mo()` is **pure in-memory output with no disk write**, so `--check` has zero side effects and genuinely compares against the committed `.mo` on disk; only non-check mode writes the file. The CI path filter (paths-filter) treats `i18n/**` as a trigger condition: translation-only changes also run this gate. **The key sets of all four language catalogs must be consistent** (enforced by `tests/test_i18n.py::test_catalogs_share_same_keyset`) — when adding a new msgid you must update all four catalogs. To extract and compare pending-translation strings, run `python scripts/extract_i18n_strings.py` (AST-scans runtime code for print constant strings + logger f-string template drafts and compares against the four catalogs; f-string template normalization conventions: format/conversion specifiers dropped, double quotes inside expressions converted to single quotes; pure-placeholder templates (e.g. `{color}{text}`) and the gettext header empty msgid are filtered out, producing no noise).

**Translation coverage** (after the full 2026-08-27 replenishment, covering all runtime constant strings and logger template drafts):

- `src/spider.py` — per-platform live data fetch/login/risk-control messages (including the Bilibili buvid auth chain)
- `main.py` — main program general messages, recording chain, quality downgrade, anchor-name sync, disk space
- `gui.py` — GUI interface messages (widget text, process management, tray, exit confirmation)
- `src/scheduler.py` — concurrency mode switching and capacity-adjustment broadcasts
- `src/stream_select.py` — the full stream-URL validation message set (probe backoff, GET recheck, last-resort pass-through)
- `src/collector.py` / `src/danmaku_monitor.py` — danmaku capture and monitoring
- `src/async_http.py` / `src/sync_http.py` / `src/cookie_cache.py` — HTTP clients and cookie cache
- `msg_push.py` — seven-channel push-failure branches (WeChat/DingTalk/TG/Bark/ntfy/PushPlus/email)
- `src/ffmpeg_install.py` / `src/node_install.py` — ffmpeg/Node.js auto installation
- `src/config_io.py` / `src/utils.py` — config read/write, backup, disk space
- `src/notify.py` — custom script execution errors
- `web.py` / `src/web_tray.py` — web panel startup and tray
- `src/room.py` / `src/recorder_status.py` / `src/ttwid.py` / `src/ffmpeg_proc.py` / `src/platforms/bilibili.py` / `src/platforms/douyin.py` / `build_exe.py` — remaining runtime messages

> Note: What actually participates in translation lookup at runtime is the constant English string output by `print()`; `logger.*` output and f-string-interpolated text do not go through lookup, and the related entries in the catalogs are kept only as ready-made translation drafts for later log i18n integration.

### 9. GUI Module (`gui.py` + `src/gui_qt/`)

**Responsibility**: Provide the PySide6/Qt6 desktop UI. `gui.py` is only a thin entry (parent-process marker `DLR_GUI_PARENT`, lazy delegation of `main()` to `src.gui_qt.app.main()`, and a crash fallback for windowed runs); the tkinter implementation was fully removed on 2026-10-31.

**Window layer** (`src/gui_qt/`):

- `app.py` assembles the QApplication and event loop; `main_window.py` hosts the main window and sidebar; `theme.py` holds design tokens (25 keys × 3 themes) and QSS; `widgets.py` provides Card / Toast / DataTable / TerminalText.
- `pages/` contains five pages: dashboard, quality, config, runlog and danmaku.
- `recorder.py` / `danmaku_monitor.py` are controllers; `tray.py` is the system tray; `settings_dialog.py` is the settings dialog; `shared.py` holds shared state.
- Threading: Qt Signal/Slot + QTimer; controller code contains no Qt layout code and can be unit-tested offscreen with `QT_QPA_PLATFORM=offscreen`.
- Quality monitor: consumes `actual_quality` and downgrade alerts from the recording subprocess log, counts recording / normal / downgraded rows, and clears markers not updated for 30 seconds.

### 10. Async HTTP Client (`src/async_http.py`)

**Responsibility**: Wrap httpx to provide a unified async HTTP interface.

**Features**:

- Proxy support
- Timeout setting
- Auto retry
- Status code checking
- HTTP/2 support
- **Connection pool reuse**: reuse AsyncClient by (proxy, verify, http2) dimensions, leveraging the keepalive connection pool
- **Event loop detection**: cache and record the event loop reference at each client's creation; automatically rebuild the client when `asyncio.run()` causes a loop change, avoiding the `'NoneType' object has no attribute 'send'` error
- **Module-level lock rebuilt with the event loop** (fixed 2026-08-12): the `_client_lock` protecting `_client_cache` reads/writes was a module-level singleton `asyncio.Lock()`; after it lazily bound to the first room's `asyncio.run()` loop, subsequent rooms each started a new loop via `asyncio.run()` and `await`ing it again triggered `RuntimeError: ... is bound to a different event loop`; that exception was swallowed by `async_req` and returned an empty string, which `spider.py` misjudged as "risk-control empty response" and cascaded into HTML fallback failure. Now `_get_client_lock()` caches a `(lock, loop)` tuple and automatically rebuilds the lock when the current loop changes, consistent with `_client_cache`'s "client + loop" mechanism, eliminating cross-loop lock errors at the source
- **Typed exception logs** (consolidated 2026-08-12): all `except Exception as e: logger.debug(e)` inside `async_req` and `_close_all_clients` now include `type(e).__name__` (with URL when necessary), eliminating the blank-log problem on Windows when an exception's `str()` is empty and impossible to locate
- **SSL verification**: uniformly controlled by the global config `src/http_config.py`, enabled by default
- **No more scheduled close of stale cross-loop clients** (fixed 2026-09-04): when evicting a stale AsyncClient created on another event loop, **no** `aclose()` coroutine is ever created (running / stopped / closed old loops are all treated the same); the reference is dropped and GC handles cleanup. The old implementation scheduled via `run_coroutine_threadsafe` without waiting — when the old loop sat inside the `asyncio.run` teardown window (stopped but not yet closed) the callback never executed, and GC reported "coroutine ... aclose was never awaited" with randomly fluctuating counts (1~2 flaky occurrences, escaping via unraisableexception); the "is_running gate + wait for future" variant was empirically still incurable (during teardown a scheduled task may be created yet never stepped — `Task was destroyed but it is pending` — and a never-resolving future amplifies the race into multi-second blocking); awaiting directly on the current loop would operate a transport bound to the old loop. Regression locks: `tests/test_async_http_lock.py::test_cross_loop_running_old_loop_skips_close` / `test_cross_loop_stopped_old_loop_skips_close`
- **Connection pool cleanup**: release all reused AsyncClients on process exit via atexit / signal handlers
- **`get_response_status()` m3u8 fault tolerance** (enhanced 2026-08-05): when HEAD validation fails, if the URL ends with `.m3u8` it adds a lightweight `Range: bytes=0-0` GET probe (all non-2xx including **404** trigger the probe; returns 200/206 → reachable); behavior for non-m3u8 sources (FLV/record_url) is unchanged. Exception logs include URL + `type(e).__name__` (e.g. `ConnectTimeout` / `TimeoutError`), avoiding blank messages when Windows `socket.timeout`'s `str()` is empty; probe failures log `status_code` / `content-type` for troubleshooting

**Imported by**:

- `src/spider.py` - `async_req()`
- `src/stream.py` - `get_response_status()`

### 11. HTTP Client Configuration (`src/http_config.py`)

**Responsibility**: Provide shared runtime configuration for HTTP clients.

**Features**:

- Global SSL certificate verification switch (`ssl_verify`), enabled by default (True, security first); integrated into "whether to enable https recording" — enabled = https pull + disable cert verification, disabled = http pull + default strict verification (hot-synced by main.py each round)
- Provides `set_ssl_verify()` / `set_https_recording()` functions, set at startup from the main config and each round in the main loop
- Platform-level SSL override (`ssl_verify_platform_overrides`): kept for compatibility; integration does not change actual behavior
- Async / sync HTTP clients read this config when issuing requests

### 12. Sync HTTP Client (`src/sync_http.py`)

**Responsibility**: Wrap requests and urllib to provide a synchronous HTTP interface.

**Features**:

- Proxy support
- Timeout setting
- Cookie support
- Redirect tracking
- **SSL verification**: uniformly controlled by the global config `src/http_config.py`, and overridable **per single call** via the `ssl_verify` parameter (see below)
- **Session lifecycle management (2026-09-02; updated in the 2026-10-20 cleanup round)**: the thread-local `requests.Session` is registered through a module-level `WeakSet` (entries are reclaimed automatically once a thread dies, GC is never blocked); `atexit` registers `close_all_sessions()` to shut down every still-live connection pool gracefully at process exit (80+ rooms running for a long time). The former `close_session()` was removed — it had zero callers repo-wide; process-exit shutdown is centralized in `close_all_sessions()`, and `_session()` rebuilds on demand for later requests
- **Opener construction shape (after F-12; this subsection recalibrated 2026-09-24)**: only `_opener_secure` (proxy disabled, certificate verification kept) is pre-built at module level; the non-verifying `SSLContext` and its opener are always built **lazily on demand** (`_get_insecure_context()` / `_get_insecure_opener()`) — the 2026-09-12 review item 6.7 pointed out that a non-verifying context existing at import time equals a silent process-wide downgrade surface, so reverting to module-level residency is forbidden
- **`ssl_verify` per-call override (F-12)**: `sync_req(..., ssl_verify=None/True/False)` is decided by `_resolve_ssl_verify()` (`None` = follow the `http_config.ssl_verify` global switch; an explicit value wins for that call), and the same decision must be **passed through both the urllib and the requests (proxy) paths** — credential-carrying call sites can force verification instead of being dragged down by the global switch
- **Public accessor for the thread-level Session (MIN-08)**: `session()` serves call sites that must read the status code / response headers and therefore cannot use `sync_req` (whose failure contract collapses everything into an empty string) while still reusing the same connection pool; the patch target remains `_session` (test convention)
- **Response body caps (SEV-2226 follow-up, 2026-09-23)**: on the proxy-free urllib path both caps are required — `_read_capped()` limits the compressed/raw body read (`_MAX_RESPONSE_BYTES`, 8 MiB) and `_gunzip_capped()` decompresses in chunks while limiting the produced bytes (`_MAX_DECOMPRESSED_BYTES`, 32 MiB); exceeding a cap raises `ValueError`, which the existing failure branch logs masked and turns into an empty string. **The proxy branch's `response.text` is gzip-decoded by requests itself and is still NOT covered by these caps** (known residual gap, see the source comment)
- **Current status (SEV-2226 forensics, 2026-09-23)**: this module **currently has no production importer at all** (`src/spider.py` uses the httpx async surface via `from .async_http import async_req`; the former caller `src/weverse_auth.py` was deleted on 2026-09-23); keeping or removing it is left to the maintainer — the module still carries the F-12 invariant and the `tests/test_sync_http.py` regression lock on it

### 13. Web Management Panel (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`)

**Responsibility**: Provide a Web interface to remotely manage the recorder, including dashboard, live room management, config editing, and log viewing.

**Architecture**:

- `web.py` - entry: the recording engine runs in a daemon thread; by default uvicorn runs on the main thread. On Windows with the Qt tray enabled, the main thread is handed to `QApplication` and uvicorn moves to a daemon thread; when tray `start()` returns `False`, it silently falls back to the main-thread shape
- `src/web_api.py` - Starlette app: authentication (Token), REST API routes, SSE push, static asset mounting
- `src/web_config.py` - config read/write (does not depend on Web framework, convenient for unit tests)
- `web/` - frontend static assets (single-page application)

**Background run mode** (`web_show_console = false`):

- `_enter_background_mode()` is called before starting the recording engine
- On Windows, `ctypes` calls `GetConsoleWindow()` + `ShowWindow(hwnd, SW_HIDE)` to hide the console window
- stdout/stderr redirected to `logs/web_console.log` (line-buffered, written in real time)
- The program runs fully in the background and is managed via the Web panel
- Restore console: set `web_show_console = true` and restart

**Console encoding / `ctypes` robustness (fixed 2026-08-16)**:

- kernel32 / user32 `WinDLL` handles are cached as module-level singletons (`_KERNEL32` / `_USER32`), avoiding repeated DLL loads when `_fix_encoding()` and `_enter_background_mode()` are called multiple times; on load failure they remain `None` and subsequent calls auto-retry
- Completed `restype` declarations: `SetConsoleOutputCP` / `SetConsoleCP` return `BOOL` (explicit `restype = ctypes.c_int`), `ShowWindow` returns `BOOL`, consistent with the existing `GetConsoleWindow.restype = c_void_p`, eliminating implicit reliance on ctypes' default return type
- In `_enter_background_mode()`, `GetConsoleWindow()` already returns `c_void_p`; removed the redundant `cast(ctypes.c_void_p, ...)`, directly checking for null then `ShowWindow(hwnd, 0)`
- **Tray-module alignment (2026-09-02)**: `src/web_tray.py`'s console-window restyling (`_patch_console_window`) and tray restore (`_on_show`) switched to the same `WinDLL` + explicit `argtypes`/`restype` conventions (HWND/HMENU declared as `c_void_p`, fixing 64-bit handles being truncated by ctypes' default `c_int` — which could redirect window operations to a wrong address), with module-level `_KERNEL32`/`_USER32` singleton caching; the second parameter of `SetWindowPos` (insert-after window) is accordingly narrowed to `c_void_p | None`

**API routes (grouped; the full list lives in `src/web_api.py`)**:

| Group | Routes |
| --- | --- |
| Auth | `POST /api/login`, `POST /api/logout`, `GET /api/auth/status` |
| Status / liveness | `GET /api/status`, `GET /api/status/stream` (SSE), `GET /health` |
| Recording | `POST /api/recording/toggle` |
| Rooms | `GET/POST/PUT/DELETE /api/rooms`, `POST /api/rooms/toggle`, `PUT /api/rooms/quality`, `GET/PUT /api/rooms/qualities` |
| Config / language | `GET/PUT /api/config`, `GET/PUT /api/language` |
| Files / logs / danmaku | `GET /api/files`, `GET /api/files/download`, `GET /api/logs`, `GET /api/danmaku` |
| Icon | `POST /api/icon`, `GET /favicon.ico` |

**Frontend features** (`web/`):

- `index.html` - single-page application entry (views live in `web/index.html`)
- `app.js` - frontend logic (Token auth, API calls, SSE log stream, status rendering)
- `motion.js` - zero-dependency motion engine (entrance / parallax / particles / degradation)
- `style.css` - stylesheet (light/dark theme, responsive layout, downgrade highlight)
- **Mobile adaptation conventions (2026-09-29)**: the viewport in `index.html` carries `viewport-fit=cover`; top and
  side padding always goes through `env(safe-area-inset-*)` (Dynamic Island and Home Indicator clearance) and page
  height uses `100dvh` (with `100vh` kept only as a fallback); under the <=768px breakpoint the top bar splits into two
  rows (row 1: brand + language/theme, row 2: tabs on a full-width horizontal scroller) and data tables scroll
  horizontally inside `.panel` (minimum width `540px`). New panels, columns or interactive controls must follow these
  three rules (relative units + wrappable flex + safe area); the constraints and verification readings live in the
  2026-09-29 entry of the Changelog.

**Recording table display**:

- Name / configured quality / actual quality / start time / recorded duration
- When actual quality differs from configured quality, shown in red (`.quality-down` style)

**Security mechanisms**:

- After a password change, all existing Tokens are automatically revoked, forcing re-login
- Outputs a security warning when listening on `0.0.0.0` without authentication enabled
- File download path validation (`_is_within` prevents directory traversal)
- Sensitive config items (Cookie / account password / web_password) are masked as `***` in API responses
- **Unauthenticated dangerous-config write protection**: when `web_auth_enable = false`, `PUT /api/config` is forbidden from overwriting dangerous keys in [Recorder] and [Push] (such as "run custom script after recording" `run_script`); only [Web] and whitelisted keys are allowed, blocking the unauthenticated RCE chain
- **INI injection protection**: config values and live room names filter `\n`/`\r` to prevent injecting arbitrary new lines / new sections into `config.ini` / `URL_config.ini`
- **Login brute-force rate limiting**: after `/api/login` fails consecutively up to a threshold (default 5 times / 5 minutes), it locks for a period (default 10 minutes), defending against online password brute-forcing
- **Push log masking**: `_mask_url()` in `msg_push.py` masks tokens / secrets in the query of webhook URLs in failure logs, preventing credential leakage via logs

### 14. Danmaku Collection Subsystem (`src/platforms/` + `src/collector.py` + related modules)

**Responsibility and architecture overview**: Provides live danmaku (bullet-chat) collection synchronized with video recording, sharded by half-hour — danmaku is written to SRT subtitle files and can also be viewed independently via "Danmaku Monitor" (monitor only, no disk write). The danmaku module was ported from `dart_simple_live`, originally located in `src/danmaku/`, then migrated to the `src/` root along with the directory flattening (base class `src/base.py`, collector `src/collector.py`, monitor `src/danmaku_monitor.py`, transport `src/ws_client.py`, cache `src/cookie_cache.py`, subtitles `src/srt_writer.py`, `src/proto/`, and per-platform implementations `src/platforms/`).

**Decoupled from stream parsing**: The danmaku subsystem and `src/spider.py` (video stream address parsing) are **two parallel abstractions**. `spider.py` is responsible for parsing video stream addresses; the danmaku client is decoupled via the registry/factory in `src/__init__.py`; `spider.py` does not import `src/platforms` at all. Only Bilibili danmaku lazily calls back `spider.invalidate_bili_buvid_cache()` when AUTH is rejected.

**Lifecycle wiring** (starts and stops together with recording):

- Each platform branch of `main.start_record` collects `record_danmaku_args` (reset to `None` each round);
- All 6 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` calls are wired up;
- The factory `src/__init__.py:get_danmaku_collector(platform, danmaku_args, base_filename, segment_seconds, only_fans, room_name, write_srt)` picks the danmaku class by platform and constructs a `DanmakuCollector`; returns `None` when the platform is unsupported or `danmaku_args` is empty;
- `DanmakuCollector` calls `stop()` outside the `while process.poll() is None` loop; `DanmakuCollector.stop()` has `_stop_called` to prevent re-entry (idempotent).

**Platform registry** (`src/__init__.py:get_danmaku_class`, platform names consistent with `main.py` identifiers):

| Platform ID | Danmaku Class (`src/platforms/`) |
| --- | --- |
| Douyu Live | `DouyuDanmaku` |
| Bilibili Live | `BilibiliDanmaku` |
| Huya Live | `HuyaDanmaku` |
| Douyin Live | `DouyinDanmaku` |
| TwitchTV | `TwitchDanmaku` |

**Key files**:

- **Base class and data structures (`src/base.py`)**: `DanmakuBase(ABC)` defines the unified contract — class attribute `heartbeat_interval=45.0`; constructor `__init__(on_message, on_close, on_ready)` saves callbacks and sets `_stopped=False`; four abstract methods `async start(args)` / `async stop()` / `async heartbeat()` / `decode_message(data: bytes|str)`, helper `_emit(msg)` pushes up via `on_message`. `DanmakuMessageType(Enum)` (`CHAT/GIFT/ONLINE/SUPER_CHAT`); `DanmakuMessage` dataclass (`type/user_name/message/data/color/timestamp_ms`, `timestamp_ms` injected by the collector).
- **Danmaku collector (`src/collector.py`)**: `DanmakuCollector` wraps the async danmaku client into a threaded synchronous collector. Constructor params include `danmaku_cls / danmaku_args / base_filename / segment_seconds / only_fans / room_name / platform_name / write_srt` (`write_srt=False` means monitor-only, no disk write); `start()` anchors the SRT timeline and spawns a daemon thread `_run()` (new `asyncio.new_event_loop()`, instantiates the danmaku class, `run_until_complete(danmaku.start(args))`); `_on_message` reports all types to the monitor hub `hub.room_message(...)`, and only `CHAT` with non-empty username/content is written to SRT; `stop(timeout=8.0)` is idempotent, with a `message_count` property. Depends on `src.base` / `src.danmaku_monitor` / `src.srt_writer`.
- **Per-platform danmaku clients (`src/platforms/`)**: five `DanmakuBase` subclasses + two private signing/codec utilities.
| File | Class | WebSocket Endpoint | Key Protocol/Logic |
| --- | --- | --- | --- |
| `douyin.py` | `DouyinDanmaku` | `wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/` | gzip-decode `PushFrame.payload`→`Response` (protobuf); `danmaku_signature` (`_xbogus`) generates `signature`; when Cookie missing `await get_ttwid()`; `backup_url` changes `lq`→`lf` |
| `douyu.py` | `DouyuDanmaku` | `wss://danmuproxy.douyu.com:8506` | Little-endian binary frame + STT text protocol; `_dispatch` handles `chatmsg` (filters fans by `if==1`) and emits CHAT; heartbeat sends `mrkl` |
| `huya.py` | `HuyaDanmaku` | `wss://cdnws.api.huya.com` | Tars binary protocol (`_tars`); `_make_join_data()` writes `WSRegisterReq`; `cmdType==7`→`_decode_chat` (HYMessage) |
| `bilibili.py` | `BilibiliDanmaku` | `wss://{host}/sub` (iterates `host_list`) | 16-byte big-endian frame header; `protover=2` zlib / `=3` brotli decompression; `operation==8` AUTH_REPLY checks `code==0`, on failure/timeout via `_reject_auth()` + `spider.invalidate_bili_buvid_cache()`; `_auth_watchdog`(8s) fallback |
| `twitch.py` | `TwitchDanmaku` | `wss://irc-ws.chat.twitch.tv` | Pure IRC; anonymous `justinfan{random}` connection; `PING`→`PONG`, regex-parse PRIVMSG to emit CHAT; proxy via `handle_proxy_addr` or system proxy |
| `_tars.py` | (private) Tars codec | — | Huya uses a minimal Tars: `TarsInputStream` / `TarsOutputStream`, header byte high 4 bits tag, low 4 bits type |
| `_xbogus.py` | (private) X-Bogus signature | — | Used by Douyin danmaku: `generate_xbogus` (RC4 + custom base64), `danmaku_signature(room_id, unique_id)` |
- **Danmaku monitor hub (`src/danmaku_monitor.py`)**: `DanmakuMonitorHub` (process singleton, lazily created via `get_hub()`) aggregates danmaku events from each room — `room_started/room_connected/room_closed/room_stopped/room_message`; in-memory snapshot `snapshot(since=0)` for the Web API to consume, and writes a JSONL sidecar `logs/danmaku_monitor.jsonl` (5MB rotation). All methods swallow exceptions; includes a 10s×6-bucket rate window and ≤10 messages/sec sampling fold.
- **SRT subtitle writer (`src/srt_writer.py`)**: `SrtWriter` shards by `segment_seconds` to `{base}_{seg:03d}.srt` (single-file mode `{base}.srt`); the timeline is based on `time.monotonic()` and aligned with ffmpeg's `segment -reset_timestamps` PTS; `write()` holds a `threading.Lock` to write entries and flush.
- **WebSocket transport layer (`src/ws_client.py`)**: `WsClient` is the async WS client shared by all platform danmaku. `connect()` explicitly sets `proxy=None` (danmaku connects directly, not following the system proxy, avoiding the SOCKS-requires-python-socks error); `ping_interval=None` (each platform has its own heartbeat); `max_size=None`, `asyncio.Lock` serializes sending; supports `on_message/on_ready/on_heartbeat/on_close/on_reconnect` callbacks and a `max_reconnect` reconnect policy.
- **Visitor Cookie cache (`src/cookie_cache.py`)**: the only in-process "dynamically fetch visitor cookie by URL" cache, avoiding risk-control triggers from concurrent duplicate requests across multiple rooms. `fetch_cookies(url, proxy, *, ttl=30min, fetcher=None)` uses a lock-free fast path + singleflight deduplication (rewritten 2026-09-02: `threading.Lock` only guards the synchronous reads/writes of the cache dict and the in-flight registry — **never awaiting while holding the lock**; under the old RLock-across-await scheme, same-loop coroutines could all re-enter the lock, voiding mutual exclusion; same-loop waiters reuse a future, cross-loop delivery goes through `loop.call_soon_threadsafe` (futures are not thread-safe); if the fetching coroutine is cancelled it immediately delivers an empty result to waiters, and waiters carry a timeout fallback to prevent hanging forever); `get_cookie_str` / `invalidate` / `clear`.
- **Douyin danmaku protocol (`src/proto/`)**: `douyin.proto` (Proto3) defines `Response/Message/ChatMessage/GiftMessage/...`; `douyin_pb2.py` is protoc-generated (DO NOT EDIT), `douyin_pb2.pyi` is a pyright-based type stub. Douyin danmaku parsing chain: `PushFrame.payload` (gzip → `Response`) → `Message.payload` → `ChatMessage`.

### 15. Concurrency Scheduling Hub (`src/scheduler.py`)

**Responsibility**: Uniformly manages global network concurrency capacity, per-platform (host) isolated circuit breaker degradation, and supports both adaptive speed adjustment and fixed concurrency modes with runtime-resizable semaphores.

**Core Classes**:

- **`ResizableSemaphore`**: A runtime-resizable semaphore implementing the context manager protocol. Supports `set_value(n)` for runtime capacity adjustments — on increase, wakes the corresponding number of waiters; on decrease, only lowers the upper bound without forcibly reclaiming held slots. `__init__` / `set_value` allow a capacity of 0 (paused state). Eliminates the race condition of the old "destroy-and-recreate semaphore" approach.

- **`PlatformBreaker`**: A per-key (host) isolated circuit breaker implementing a `closed → open → half-open` three-state state machine. When the continuous failure sample ratio exceeds the threshold, it opens (skips probing and enters cooldown); after cooldown, a **single** probe is released; probe success restores closed, probe failure re-opens. Used to isolate and degrade single-platform jitter, preventing cascading global failures. **The probe carries a lease (`_PROBE_LEASE_SECONDS = 60s`, since 2026-08-27)**: if no sample is reported after the lease expires (not-live waiting rounds, `disable_record`, room-thread exit — paths that never trigger `record`), `allow()` re-grants the probe for self-healing — without the lease, the `_probing` flag never resets and the host stays permanently circuit-broken until process restart.

- **`ConcurrencyScheduler`**: The scheduling hub, integrating adaptive capacity, platform circuit breaker, and recording concurrency limit capabilities.
  - **Network concurrency capacity** = `max(configured lower bound, min(upper bound, ceil(active count / scale factor)))`; when the error rate is extremely high, capacity is gently reduced but never below the safe lower bound (default min=1 / max=128)
  - **Adaptive mode** (default, `Max simultaneous recordings (0=unlimited)` = 0): capacity dynamically scales with active task count, error feedback drives gentle backpressure
  - **Fixed concurrency mode** (`Max simultaneous recordings (0=unlimited)` ≠ 0): ignores the adaptive governor and error backpressure; network capacity is fixed to "Network thread count" (minimum 1 slot, hot-updates take effect immediately)
  - **Recording concurrency soft limit**: controls the simultaneous ffmpeg recording count via `recording_semaphore`, default 0 means unlimited
  - `adjust_loop` daemon recalculates capacity every 5 seconds, replacing the old one-way suppression `adjust_max_request`

**Key Functions**:

- `host_of(url)`: Extracts the hostname from the URL (cut at the first `/`, `?`, or `#`; lowercased, port kept) as the circuit breaker key; empty strings or parse errors uniformly map to `"unknown"` (unrelated broken URLs share one breaker key — a coarse-grained fallback)
- `allow(key)`: Pre-checks whether the specified host is circuit-broken; returns False when the caller should skip this round of probing; the half-open state carries a probe lease (see `PlatformBreaker`)
- `record_error(key)` / `record_success(key)`: Records success/failure samples per host, driving circuit breaker state transitions

**Wiring Points** (fixed locations, does not modify 50+ platform dispatch functions):

- `notify.record_error/record_success` adds a `key` parameter, delegates to `scheduler`
- `start_record` entry performs `scheduler.allow(record_host)` circuit breaker pre-check before platform dispatch
- The parse-success branch of `start_record` (non-empty `anchor_name`) reports `record_success(record_host)` — the half-open probe relies on this round's result to close the loop, so other rooms on the same host no longer starve while the probe room is in a long recording
- `check_subprocess` recording loop is governed by `recording_semaphore`
- `main()` initializes the scheduler in the first round; `semaphore` / `recording_semaphore` point to its attributes

**Thread Safety** (hardened 2026-08-27): the config fields (mode/configured limit/active count/error window) are read and written concurrently by the main thread and the `adjust_loop` daemon; `_compute_capacity()` snapshots all mutable inputs under a single lock, and `set_configured_limit()` / `set_dynamic_mode()` write inside the lock (idempotence check + write atomic). `Lock` is non-reentrant, so all setters call `recompute()` only after releasing the lock — no nested lock holding anywhere in the chain.

**Configuration Items**:

| Config Item | Description | Default |
| --- | --- | --- |
| Max simultaneous recordings (0=unlimited) | 0=unlimited (also serves as concurrency mode switch: 0=adaptive speed, non-zero=fixed concurrency) | 0 |
| Network thread count | In adaptive mode, one of the capacity lower bounds; in fixed mode, the fixed concurrency limit value | 3 |

**Tests**: `tests/test_scheduler.py` has 16 test cases covering semaphore resizing, circuit breaker state machine (including probe-lease timeout self-healing), adaptive capacity scaling/lower bound, fixed concurrency mode, per-key isolation, recording concurrency soft limit, etc.

## Key Classes and Functions

### Configuration File Management (`src/utils.py`)

```python
def read_config_value(file_path: Path, section: str, key: str) -> str | None
def update_config(file_path: Path, section: str, key: str, new_value: str) -> None
```

### Error Handling Decorator

```python
@trace_error_decorator
async def some_function():
    # Automatically capture and log exceptions (sync and async functions)
    pass
```

**Implementation characteristics**:

- Detects function type via `asyncio.iscoroutinefunction()`
- Async functions use `async wrapper` to correctly `await` and catch exceptions
- Uniformly returns `{}` empty dict, compatible with the caller's `.get()` usage
- `execjs.ProgramError` handled separately (Node.js environment issue)

### Dynamic Concurrency Adjustment

`main.py` implements an error-rate-based dynamic concurrency adjustment mechanism to avoid being rate-limited by platforms.

### Concurrency Scheduler (`src/scheduler.py`)

```python
# Runtime-resizable semaphore
class ResizableSemaphore:
    def set_value(self, n: int) -> None: ...
    def acquire(self) -> None: ...
    def release(self) -> None: ...

# Per-platform circuit breaker
class PlatformBreaker:
    def allow(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_failure(self) -> None: ...

# Scheduling hub
class ConcurrencyScheduler:
    network_semaphore: ResizableSemaphore
    recording_semaphore: ResizableSemaphore
    def set_dynamic_mode(self, enabled: bool) -> None: ...
    def set_recording_limit(self, limit: int) -> None: ...
    def allow(self, key: str) -> bool: ...
    def record_error(self, key: str) -> None: ...
    def record_success(self, key: str) -> None: ...

# Helper function
def host_of(url: str) -> str: ...
```

## Dependencies

### Python Dependencies (`requirements.txt`, kept consistent with `pyproject.toml [project.dependencies]`)

| Package | Version Requirement | Purpose |
| --- | --- | --- |
| requests | >=2.34.2 | Synchronous HTTP requests (now only the ffmpeg / node install-download scripts; platform parsing uses the httpx async surface) |
| urllib3 | >=2.8.0 | Transport layer (under requests; declared explicitly to prevent resolution fallback into the CVE-2026-44431 / 97687-97689 ranges) |
| httpx[http2] | >=0.28.1 | Async HTTP client (with HTTP/2; `src/async_http.py` fetches stream URLs concurrently) |
| h2 | >=4.4.1 | Runtime dependency of httpx `http2=True` (`import h2` inside `Client.__init__`) |
| socksio | >=1.0.0 | Runtime dependency of httpx SOCKS proxy (`socks5`/`socks5h`, `import socksio` in the transport layer) |
| loguru | >=0.7.3 | Structured logging (wrapped by `src/logger.py`) |
| pycryptodome | >=3.23.0 | Cryptographic algorithms (SM3, RC4, AES) |
| distro | >=1.9.0 | Linux distribution detection |
| tqdm | >=4.69.0 | Download progress bar |
| exejs | >=1.0.1 | JavaScript execution engine (active-maintained successor to PyExecJS, preferred) |
| PyExecJS | >=1.5.1 | JS execution engine fallback compatibility (used when exejs is not installed) |
| PySide6 | >=6.12.0 | GUI window layer (`src/gui_qt/`, QSS token themes + Qt widgets) + Web entry system tray (`src/web_tray.py`, migrated from pystray on 2026-10-20; the 6.12 floor is the measured minimum that supports Python 3.14.8) |
| starlette | >=1.3.1 | ASGI framework (`src/web_api.py` migrated from FastAPI to depend on Starlette directly in phase 2; lower bound 0.49.1 → 1.0.1 → 1.3.1, see the CVE/PYSEC notes) |
| uvicorn[standard] | >=0.51.0 | ASGI server |
| websockets | >=14.0 | Danmaku WebSocket client (`src/ws_client.py`; `additional_headers` is a 14.0+ API) |
| protobuf | >=6.33.5,<8 | Douyin danmaku protocol decoding (`src/proto/douyin_pb2.py`; the `<8` cap is a gencode compatibility guard) |
| brotli | >=1.2.1 | Bilibili danmaku decompression (protover=3) |
| PyYAML | >=6.0.3 | YAML translation catalog support (`i18n/zh_TW.yaml`) |

> Note 1: [Historical note] this section used to record that "Weverse platform authentication is implemented by
> `src/weverse_auth.py` calling the API directly via requests, and no longer depends on the pip `weverse` package".
> That module (together with `tests/test_weverse_auth.py`) was removed entirely on 2026-09-23; the conclusion is kept
> for reference only: the pip `weverse` package pulls in the deprecated pycrypto==2.6.1 (uncompilable on Python 3.10+),
> so it must **never** be added to the dependency list.
>
> Note 2: Executable packaging requires PyInstaller, an optional build-time dependency: `pip install .[build]`
>
> (corresponding to `pyproject.toml`'s `[project.optional-dependencies] build`).

### External Dependencies

| Dependency | Purpose | Installation |
| --- | --- | --- |
| FFmpeg | Video recording and transcoding | Built-in on Windows (`ffmpeg/`), manual install on Linux/macOS; installed via apt inside Docker |
| Node.js | Run JavaScript signing algorithms | Auto-installed on Windows (`node/`), needs a package manager on Linux; Node 24 installed via apt inside Docker |

### Module Dependency Graph

```
main.py
├── src/spider.py
│   ├── src/room.py
│   ├── src/async_http.py
│   │   └── src/http_config.py
│   ├── src/http_config.py
│   └── src/utils.py
├── src/stream.py
│   ├── src/spider.py
│   └── src/async_http.py
├── src/scheduler.py (concurrency scheduling hub)
│   ├── ResizableSemaphore (runtime-resizable semaphore)
│   ├── PlatformBreaker (per-platform circuit breaker)
│   └── ConcurrencyScheduler (scheduling hub)
├── src/notify.py (record_error/record_success delegates to scheduler)
├── src/http_config.py
├── src/async_http.py
├── src/utils.py
│   └── src/logger.py
├── msg_push.py
└── src/ffmpeg_install.py

src/__init__.py (弹幕注册表/工厂)
├── get_danmaku_collector() → src/collector.py
│   └── DanmakuCollector
│       ├── src/base.DanmakuBase (契约)
│       ├── src/platforms/<X>Danmaku (各平台实现)
│       │   ├── src/ws_client.WsClient (传输，proxy=None 直连)
│       │   ├── src/cookie_cache.fetch_cookies (访客 cookie)
│       │   ├── src/proto.douyin_pb2 (抖音解码)
│       │   └── src/ttwid.get_ttwid (抖音动态 ttwid)
│       ├── src/srt_writer.SrtWriter (落 SRT)
│       └── src/danmaku_monitor.get_hub() (监控枢纽，进程单例)

web.py
├── src/web_api.py
│   ├── src/web_config.py
│   └── main.py (get_status 等函数)
└── web/ (静态资源)
```

## Configuration File Reference

### Main Configuration File (`config/config.ini`)

#### [Recording Settings] section

| Config Item | Description | Default |
| --- | --- | --- |
| language | UI language: zh_CN / en_US / en_GB / zh_TW; blank follows the system language | (empty) |
| 是否跳过代理检测(是/否) | Skip proxy detection at startup | Yes |
| 是否启用日志文件(是/否) | Write runtime logs to `logs/` | Yes |
| 是否启动时清理陈旧字节码缓存(是/否) | Purge stale `__pycache__` once when the version or source hash changes | Yes |
| 直播保存路径(不填则默认) | Recording output path; blank uses `downloads/` | (empty) |
| 是否自动更新主播名(是/否) | Sync `URL_config.ini` and rename folders/files after an anchor rename | Yes |
| 保存文件夹是否以作者区分 | Create a per-anchor subdirectory | Yes |
| 保存文件夹是否以时间区分 | Create a time-based subdirectory | No |
| 保存文件夹是否以标题区分 | Create a title-based subdirectory | No |
| 保存文件名是否包含标题 | Include the live title in the filename | No |
| 是否去除名称中的表情符号 | Strip emoji from anchor names / titles | Yes |
| 视频保存格式ts\|mkv\|flv\|mp4\|mp3音频\|m4a音频 | Output container/format | ts |
| 原画\|超清\|高清\|标清\|流畅 | Default recording quality | 原画 |
| 自定义画质选项(逗号分隔) | Quality subset offered by GUI/Web; blank uses the full built-in set | (empty) |
| 是否使用代理ip(是/否) | Enable the recording proxy | No |
| 代理地址 | Proxy address; a bare `ip:port` gets `http://` | (empty) |
| 同一时间访问网络的线程数 | Network concurrency | 3 |
| 最大同时录制数(0为不限制) | Global recording concurrency cap; 0 = unlimited | 0 |
| 循环时间(秒) | Live-status poll interval; runtime floor is 30 seconds | 60 |
| 排队读取网址时间(秒) | Delay between room URL dispatches | 0 |
| 是否显示循环秒数 | Show the polling countdown | No |
| 是否显示直播源地址 | Log the resolved stream URL | No |
| 分段录制是否开启 | Enable time-based segmentation | Yes |
| 是否启用HLS采集(是/否) | Prefer HLS; fall back to non-HLS candidates when disabled/unreachable | Yes |
| HLS采集排除平台(逗号分隔) | Platforms forced to FLV; blank excludes none | 虎牙直播 |
| 是否启用https录制 | Use HTTPS and skip certificate verification; disabled = HTTP + default verification | Yes |
| 禁用SSL证书验证的平台(逗号分隔) | Per-platform certificate exemptions; required Huya/Bilibili entries are appended at startup | 虎牙直播,B站直播 |
| 录制空间剩余阈值(gb) | Stop new recordings below this free-space threshold | 1.0 |
| 视频分段时间(秒) | Segment duration | 1800 |
| 录制完成后自动转为mp4格式 | Remux to MP4 after recording | No |
| mp4格式重新编码为h264 | Re-encode MP4 to H.264 during post-processing | No |
| 追加格式后删除原文件 | Delete the source file after successful post-processing | Yes |
| 生成时间字幕文件 | Generate a timed subtitle file | No |
| 是否录制完成后执行自定义脚本 | Run a user command after recording | No |
| 自定义脚本执行命令 | Command / script body | (empty) |
| 使用代理录制的平台(逗号分隔) | Route matching domains through the proxy | tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit |
| 额外使用代理录制的平台(逗号分隔) | Additional proxy-routed platforms | (empty) |
| 是否录制弹幕(是/否) | Write danmaku to SRT subtitles | Yes |
| 是否弹幕监控(是/否) | Real-time danmaku view without writing SRT | Yes |
| 弹幕分片时长(秒) | Danmaku SRT shard duration | 1800 |
| 弹幕录制平台(逗号分隔) | Danmaku platform allowlist | 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV |
| 单次录制时长上限(秒,0为不限制) | Maximum duration of one ffmpeg recording; 0 = unlimited | 0 |

#### [Push Configuration] section

| Config Item | Description | Default |
| --- | --- | --- |
| 直播状态推送渠道 | WeChat / DingTalk / Telegram / Email / Bark / NTFY / PushPlus; multi-select | (empty) |
| 钉钉推送接口链接 | DingTalk webhook | (empty) |
| 钉钉通知@对象(填手机号) | Mention a phone number | (empty) |
| 钉钉通知@全体(是/否) | Mention everyone | No |
| 微信推送接口链接 | ServerChan URL | (empty) |
| bark推送接口链接 | Bark API | (empty) |
| bark推送中断级别 | critical / active / timeSensitive / passive | active |
| bark推送铃声 | Bark ringtone | bell |
| tgapi令牌 | Telegram bot token | (empty) |
| tg聊天id(个人或者群组id) | Chat ID | (empty) |
| smtp邮件服务器 | SMTP server | (empty) |
| 是否使用smtp服务ssl加密(是/否) | Enable SMTP SSL; blank is treated as yes | Yes |
| smtp邮件服务器端口 | SMTP port | (empty) |
| 邮箱登录账号 | Login account | (empty) |
| 发件人密码(授权码) | Authorization code | (empty) |
| 发件人邮箱 | From address | (empty) |
| 发件人显示昵称 | From display name | (empty) |
| 收件人邮箱 | To address | (empty) |
| ntfy推送地址 | NTFY service URL | (empty) |
| ntfy推送标签 | NTFY tag | tada |
| ntfy推送邮箱 | NTFY email | (empty) |
| pushplus推送token | PushPlus token | (empty) |
| 自定义推送标题 | Push title | 直播间状态更新通知 |
| 自定义开播推送内容 | Live-start message template | (empty) |
| 自定义关播推送内容 | Live-end message template | (empty) |
| 只推送通知不录制(是/否) | Notify only, do not record | No |
| 直播推送检测频率(秒) | Push check interval | 1800 |
| 开播推送开启(是/否) | Live-start notifications | Yes |
| 关播推送开启(是/否) | Live-end notifications | No |

#### [Cookie] section

Cookie configuration for each platform (required for recording some platforms). Special keys:

| Config Item | Description | Default |
| --- | --- | --- |
| 抖音cookie | Required for recording Douyin; must at least contain ttwid, blank triggers risk control | (empty) |
| ttwid | Can pin a Douyin ttwid (enter `ttwid=xxx` or just the value); blank auto-fetches, but a filled value takes priority over auto-fetch (`src/ttwid.py`) | (empty) |

#### [Authorization] section

Token configuration for special platforms

#### [Account Password] section

Account/password configuration for some platforms

#### [Web] section

Web management panel configuration (specific to `web.py` mode)

| Config Item | Description | Default |
| --- | --- | --- |
| web_host | Listen address (set to 0.0.0.0 inside Docker) | 127.0.0.1 |
| web_port | Listen port | 8000 |
| web_auth_enable | Whether to enable password authentication. When disabled, the API forbids overwriting dangerous [Recorder]/[Push] config (such as custom scripts), but still allows modifying [Web] settings | false |
| web_password | Login password (required when auth is enabled, stored hashed with PBKDF2-HMAC-SHA256) | (empty) |
| web_token_expiry | Token validity period (seconds) | 86400 |
| web_show_console | Whether to show the console window (false = hidden background run) | true |
| web_minimize_to_tray | Minimize console to system tray (Windows only; close button disabled, exit via tray icon "Exit Program") | true |
| web_trusted_proxy | Trusted proxy list for reverse-proxy scenarios (comma-separated direct IPs, e.g. 127.0.0.1): only direct peers in the list are trusted for `X-Forwarded-For` real-client-IP resolution (prevents forged headers from bypassing login rate limiting); blank = always use the direct peer address. Do not fill when unauthenticated and exposed to the public internet | (empty) |
| web_allowed_hosts | Extra registered domain allowlist (comma-separated; supports `*.example.com` suffix matching) on top of the hosts the server allows automatically. See `src/web_config.py::is_host_allowed` for the Host rule: **IP literals** and **dot-less single-label names** pass implicitly (DNS rebinding needs at least a multi-label registered domain), while **multi-label domains** must be registered explicitly or they are rejected with 400; `web_host` bound to `0.0.0.0`/`::` is not added to the allowlist (a wildcard bind address is not a valid Host value). So this only needs filling when `web_host` is a wildcard bind and the panel is reached via a **domain name** — not for direct-IP access or the default `127.0.0.1` setup | (empty) |
| web_tray_icon | Panel icon path (`.ico`); used for the browser tab and the Web system tray; blank uses `assets/app.ico` | (empty) |

#### [GUI] section

| Config Item | Description | Default |
| --- | --- | --- |
| gui_theme | Theme: light / dark / high_contrast; blank follows the system appearance | (empty) |
| gui_scale | Scale: 85 / 100 / 115 / 130 / 150; blank selects a preset from the available screen area | (empty) |
| gui_font | Font family; blank uses the system default (Microsoft YaHei UI) | (empty) |
| gui_font_file | Custom font file path (copy stored under `config/fonts/`) | (empty) |
| gui_tray_icon | Custom icon path (copy stored under `config/icons/`); blank uses `assets/app.ico` | (empty) |

### Live Room Configuration File (`config/URL_config.ini`)

**Format**:

```ini
# Basic format
https://live.douyin.com/745964462470

# Specify quality (quality, room URL)
超清，https://live.douyin.com/745964462470

# Specify quality and anchor name (quality, room URL, anchor: name)
高清，https://live.bilibili.com/123456，主播: B站主播

# Comment out a room (prefix the URL with #)
# https://live.douyin.com/123456789
```

**Automatic anchor-name update**: After enabling `[Recording Settings] 是否自动更新主播名(是/否)` in `config.ini` (enabled by default), whenever a polling round resolves that a platform's latest anchor name differs from the currently used name, it automatically:

1. Renames the folder previously named with the old anchor name in the save directory (`{save path}/{platform}/{old anchor name}`, merging item-by-item if the target already exists);
2. Synchronously renames all recording files prefixed with the old anchor name inside the folder (including date/title subdirs) (`{old anchor name}_*`) and same-prefix artifacts like danmaku SRT/timed subtitles, and also renames title directories ending with `_{old anchor name}` (`{title}_{old anchor name}`);
3. Updates the anchor-name field of the corresponding line in `URL_config.ini` (exact URL match of that line, preserving the quality segment, the `#` comment prefix and line-ending style, normalizing full-width colons to half-width, idempotent).

**Triggering and safety**:

- The trigger point is after each round's live-data parsing and before recording startup; at this moment the room's thread is necessarily not recording (during recording it is blocked inside the ffmpeg daemon), so the rename will not touch files being written, and in-progress recordings are unaffected.
- Skip conditions: `platform == "自定义录制直播"` (its anchor name contains a per-round random UUID and should not repeatedly trigger renaming), or the platform returns an invalid name such as "blank nickname".
- Sync order: **filesystem first, then config file**; the round's used name is switched only when both succeed. On any failure (e.g. config file locked by an editor, directory rename failed) the old name is kept and retried on the next polling round (completed directory renames are idempotent and will not repeat).
- An individual file occupied by a background transcode/player that fails to rename only warns and skips, without blocking the whole; other files are processed normally and backfilled next round; meanwhile stale recording-status entries (under `recording` / `recording_time_list`) of the old name are cleaned up to avoid the monitor page hanging onto the old name long-term.
- Config writes hold `file_update_lock`, mutually exclusive with the recording thread's `update_file` / Web API writes, avoiding half-written states.

Disabling this option keeps the manually entered name unchanged.

## How to Run

### Method 1: Run from Source

#### Prerequisites

- Python 3.14+
- FFmpeg
- Node.js

#### Install Dependencies

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

#### CLI Mode

```bash
python main.py
```

#### GUI Mode

```bash
python gui.py
```

#### Web Management Panel Mode

```bash
python web.py
# 默认监听 http://localhost:8000
```

### Method 2: Run with Docker

#### Dockerfile Multi-stage Build Notes (base image `python:3.14-slim-bookworm`)

```dockerfile
# Stage 1: builder
# - Install only build-essential (for dependencies without binary wheels)
# - Create the Python virtualenv /opt/venv and install requirements.txt
#   (Node.js is needed only at runtime, so it is not installed in the builder stage)
# - With INSTALL_GUI=false (default), filter PySide6 out by leading package name before install:
#   the image only runs main.py / web.py, whose import chains stay intact without PySide6;
#   the filter applies only to the image, and requirements.txt still keeps the dependency

# Stage 2: runtime
# - Slim base image + apt installs ffmpeg / nodejs (24 LTS) / tzdata / procps
#   (Qt runtime libraries libegl1/libgl1/… are added only when INSTALL_GUI=true, the same switch as the builder filter)
# - Copy /opt/venv from the builder
# - Run as the non-root user recorder (uid=1000)
# - HEALTHCHECK compatible with both main.py and web.py (pgrep)
# - ENTRYPOINT ["python", "main.py"], EXPOSE 8000 (for Web mode)
```

**`.dockerignore` key points** (after the 2026-08-28 sync):

- Exclude platform binaries (`ffmpeg/`, `node/`, installed via apt in the container), `config/*.ini` (mounted at runtime), `typings/`, `build_exe.py`, the root `index.html` (a standalone M3U8 player page; the panel uses `web/`), and other desktop/build-specific files;
  [2026-09-21 revision: this line previously listed `gui_legacy.py`, deleted in v4.1.0-dev / 2026-09-10 and absent from `.dockerignore` — the 4th stale MIN-15 reference, corrected in place]
- **Keep `i18n/**/*.mo` compiled translation files and `i18n/*.json`, `i18n/*.yaml` multilingual catalogs** — they are required at runtime (gettext / JSON / YAML, the three translation catalog formats) and the Dockerfile will not recompile/regenerate them; only the `.po` sources and compile scripts are excluded;
- Exclude local tool / AI-assistant generated directories (`.mimosa/`, `.qoder/`, `.agents/`, `.pnpm-store/`, `.dsh-validation/`, `.ego-browser-test/`, `.plugin-src/`, `pytest-cache-files-*/`, etc., maintained in sync with `.gitignore`);
- Exclude content the image does not consume at runtime: `uv.lock` (the image uses pip + requirements.txt), `scripts/` (maintenance scripts, zero references from the runtime chain), `tests/`, docs such as `AGENTS.md` / `README_EN.md` / `CODE_WIKI_EN.md`, and `.coveragerc-concurrency` (CI-specific).

#### Using Docker Compose (recommended)

The `docker-compose.yaml` at the repo root defines three services (sharing one image, reusing config via YAML anchors):

| Service | Entry | Start Command | Port |
| --- | --- | --- | --- |
| `recorder` (default) | `python main.py` | `docker compose up -d` | None (pure CLI) |
| `web` (profile) | `python web.py` | `docker compose --profile web up -d` | `127.0.0.1:8000:8000` |
| `gui` (profile) | `python gui.py` | `docker compose --profile gui up -d` | None (requires X11) |

Shared mount volumes: `./config`, `./downloads`, `./logs`, `./backup_config`.

> ⚠️ **Web mode required reading**: `web.py` listens on `127.0.0.1:8000` by default; inside the container you must set `web_host = 0.0.0.0` in the `[Web]` section of `config/config.ini` for the host port mapping to be reachable;
>
> at the same time it is strongly recommended to enable `web_auth_enable = true` and configure a password.

## Packaging and Release

This project provides one-click executable packaging (`build_exe.py`) and cross-platform automated build/release (`GitHub Actions`), unifying the **CLI / GUI / Web three entry points** into distributable release directories.

### 1. Packaging Script `build_exe.py`

PyInstaller `onedir` mode + `contents_directory='_internal'`, dynamically generates the `.spec` file and then calls PyInstaller to build **three entries sharing dependencies**:

| Artifact (beside the exe) | Entry | Mode |
| --- | --- | --- |
| `DouyinLiveRecorder(.exe)` | `main.py` | Console (CLI recording core) |
| `DouyinLiveRecorder-GUI(.exe)` | `gui.py` | No console window (GUI) |
| `DouyinLiveRecorder-Web(.exe)` | `web.py` | Console (Web management panel, listens on `0.0.0.0:8000`) |

The three entries share one `COLLECT`; after dependency de-duplication the size is about 1/3 of independent packaging.

**Usage**:

```bash
python build_exe.py              # build and produce the zip artifact
python build_exe.py --smoke      # additionally run smoke tests after building (recommended for CI)
python build_exe.py --no-zip     # build only, no zip
python build_exe.py --no-runtime # skip bundling ffmpeg/node (downloaded at runtime instead, smaller artifact)
python build_exe.py --dual       # emit both zips: lite (no runtime) and full (ffmpeg+node bundled)
```

**Data files and hidden imports**:

- `datas`: `src/javascript` (JS signing scripts), `i18n` (translations), `web` (frontend static assets) and `assets/app.ico`, all located via `__file__`, automatically collected into `_internal/` by PyInstaller.
- `config/` does not go into `_internal`; it is copied beside the exe by `copy_external_binaries()` (see the directory convention).
- `hiddenimports`: `i18n`, `src.async_http` (dynamically imported by main.py via `__import__`), `h2` (httpx[http2] lazy load); `a_web` additionally `collect_submodules('uvicorn')` (protocol modules imported by string).
- `excludes`: CLI excludes GUI/Web libraries (tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette); GUI excludes Web libraries; Web excludes GUI libraries (tkinter/customtkinter/pystray; **since 2026-10-20 `PySide6` is no longer excluded** — the Web tray moved to QSystemTrayIcon); all three entries additionally exclude `brotlicffi` (fixes the post-packaging error of the `brotlicffi` module missing the `error` attribute; httpx auto-falls back when no brotli is present).

**Version number**: Parsed from the `version` field of `pyproject.toml` (single source of truth), used for zip naming; falls back to `0.0.0` on parse failure. `main.py` also reads the version dynamically from `pyproject.toml` at runtime (prefers `importlib.metadata`, falls back to parsing the file directly).

### 2. Directory Structure Convention (packaging artifact)

After adopting `onedir + contents_directory='_internal'`, PyInstaller collects dependencies and `__file__`-located resources into `_internal/` beside the exe; runtime resources located via `sys.argv[0]`/`sys.executable` are copied beside the exe by the packaging script after `COLLECT`. Final artifact structure:

```
dist/DouyinLiveRecorder/
├── DouyinLiveRecorder.exe          # CLI recording core
├── DouyinLiveRecorder-GUI.exe      # GUI
├── DouyinLiveRecorder-Web.exe      # Web management panel
├── config/                          # config directory (beside the exe, read/write at runtime)
├── assets/                          # application icon (assets/app.ico)
├── ffmpeg/                          # FFmpeg runtime (beside the exe; bundled on Windows)
├── node/                            # Node.js runtime (beside the exe; bundled on Windows)
├── logs/                            # log directory (created beside the exe by default)
├── downloads/                       # default download directory (beside the exe when config.ini leaves the path blank)
├── backup_config/                   # config backup directory (beside the exe)
└── _internal/                       # Python dependencies + src/ + packaged resources
    ├── (Crypto/ PySide6/ certifi/ h2/ watchfiles/ websockets/ yaml/ + runtime .dll)
    ├── src/            src/javascript/
    ├── i18n/
    ├── web/
    └── assets/
```

**Key conventions (mandatory)**:

- `node/`, `ffmpeg/`, `config/` stay **beside the exe** (not in `_internal/`).
- `src/` and all Python dependency packages are uniformly collected into `_internal/`.
- Writable runtime directories `logs/`, `downloads/` (when not specified via `直播保存路径(不填则默认)` in `config.ini`), `backup_config/` are all created by default in the **exe's sibling directory**.

### 3. Path Convergence Mechanism `_app_root()`

The project has a "dual-track path" problem: `main.py`/`src/ffmpeg_install.py`/`src/__init__.py` etc. locate runtime resources via `sys.argv[0]`/`sys.executable`; `src/logger.py`, `i18n.py`, `src/web_api.py` etc. locate packaged resources via `__file__`. After freezing, the former points to the exe's sibling directory (release root), the latter to `_internal/`.

To unify convergence, `src/logger._app_root()` was added (same name as the inline function in `main.py`):

```python
def _app_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.realpath(sys.executable))  # = exe 同级
    return os.path.split(os.path.realpath(sys.argv[0]))[0]
```

- `main.py`'s `script_path`, `src/__init__.py`, `src/node_install.py`, `src/ffmpeg_install.py`'s `execute_dir` all converge to the exe's sibling directory, so `config/ffmpeg/node` are located correctly.
- `src/logger.py`'s `script_path` is changed to `_app_root()`, so `logs/`, `backup_config/` land beside the exe.
- `gui.py` adds `self.app_root`: when frozen, if `script_dir` is `_internal` it falls back one level to the release root, from which config/downloads are located; the CLI subprocess is launched via the sibling `DouyinLiveRecorder.exe` (see below).
- `i18n.py` supports dual-path detection of `_internal/i18n` and `i18n/`.

### 4. Frozen Build Adaptation Notes

- **GUI subprocess launch (critical fix)**: After `gui.py` is frozen, `sys.executable` points to the GUI itself; the original `[sys.executable, main.py]` would recursively launch the GUI infinitely. Changed to directly call the sibling `DouyinLiveRecorder.exe` when frozen; source-run stays as before.
- **GUI subprocess pythonw compatibility (2026-08-09)**: In source mode, if the GUI is started via `pythonw.exe`, `sys.executable` points to pythonw (GUI subsystem, no console); the original `[sys.executable, main.py]` would also run the recording core under pythonw — `CREATE_NEW_CONSOLE` is ineffective on it, `AttachConsole(pid)` is guaranteed to fail, CTRL_BREAK can never be delivered, and stopping can only hard-kill (orphaning ffmpeg). Now when the interpreter basename starts with `pythonw`, it switches to launching the recording core with the sibling `python.exe` (console subsystem); the packaged version (CLI exe `console=True`) is unaffected.
- **GUI graceful stop on recording (2026-08-09)**: When `_send_ctrl_break_to_child` fails, instead of only `proc.terminate()` (`TerminateProcess` hard-kill, orphaning ffmpeg and `wait()` succeeding immediately bypassing whole-tree cleanup), it now uses `taskkill /F /T /PID` for whole-tree termination; logs distinguish "graceful exit" from "hard-kill path" by path, no longer falsely reporting ffmpeg as cleaned up.
- **Chinese UTF-8 encoding (critical fix)**: After freezing, the subprocess stdout is a pipe and Python falls back to GBK for output, while the GUI reads the pipe as UTF-8 → Chinese mojibake (e.g. `自动获取 Cookie ttwid 成功` becomes garbled). Added `_fix_encoding()` at the top of `main.py`/`gui.py`/`web.py`: on Windows `sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace')` + `ctypes.windll.kernel32.SetConsoleOutputCP(65001)/SetConsoleCP(65001)`; on non-Windows only reconfigure. stream gets `None`/`hasattr` guards (stdout of a windowed exe may be `None`). `web.py`'s original `reconfigure(errors='replace')` is upgraded to also set `encoding='utf-8'`.

### 5. Smoke Tests

`build_exe.py --smoke` automatically runs three verifications after packaging (CI recommended to enable):

- **CLI**: Launch for a few seconds, confirm it enters the monitoring loop and outputs no `Traceback`/`ImportError`/`ModuleNotFoundError`.
- **Web**: HTTP liveness probe `http://127.0.0.1:8000/`, returns 200 means the panel is usable; also verifies the built-in ffmpeg is hit (no download triggered).
- **GUI**: Launch for 8 seconds to confirm the process survives without crashing (auto-skipped when no display environment `DISPLAY` is set).

Before smoke testing, a commented URL is written to the exe-level `config/URL_config.ini` to avoid the CLI blocking on `input()` because the URL list is empty.

### 6. GitHub Actions CI Static Verification (`ci.yml`)

Workflow file: `.github/workflows/ci.yml`, runs on push to main / PR, ensuring code style, type safety, and functional correctness pass verification before merge (structure after the 2026-08-28 optimization).

**Unified strategy**:

- The `setup` job centrally declares **shared constants** (Python version matrix / Node version / pinned black / isort / mypy versions) and performs path filtering; constants are exported to job outputs for reference by all jobs and `strategy.matrix` (matrix cannot reference the env context), serving as the workflow's single source of truth;
- **actions major versions unified at v7** (`checkout` / `setup-python` / `setup-node` / `upload-artifact`), fully consistent with build-release.yml;
- **Network-install retries uniformly go through the `.github/actions/retry` composite action** (linear backoff ×3; `command` / `label` / `attempts` / `backoff` parameterizable) — 9 pip / apt call sites; the retry strategy is maintained in action.yml alone, and re-inlining retry loops inside jobs is forbidden;
- **apt hardening flags** (aligned with the Linux build of build-release.yml): `DEBIAN_FRONTEND=noninteractive` + `Acquire::Retries=3` + `--no-install-recommends`;
- Every job sets an explicit `timeout-minutes`; a new push to the same branch/PR cancels stale runs via `cancel-in-progress: true` (fast feedback, deliberately different from the non-cancellable release pipeline);
- pip caching uniformly keyed by `hash(requirements.txt + pyproject.toml)` (no lock file participates in installation).

**Path filtering**: the `setup` job uses `dorny/paths-filter@v4` to detect changed file categories; a match runs all downstream jobs. Trigger list: Python source (`src/**`, root entry points `main.py`/`gui.py`/`web.py`/`i18n.py`/`msg_push.py`/`build_exe.py`), `tests/**`, `scripts/**`, dependency manifests (`requirements.txt` / `pyproject.toml` / `.coveragerc-concurrency`), **`i18n/**`**, **`web/**`**, **`Dockerfile` / `docker-compose.yaml`**, and the workflow and composite actions (**`.github/workflows/**` / `.github/actions/**`**). Only **pure documentation (`*.md`) changes do not trigger**. **`i18n/**` is a trigger condition** — translation-only changes also run the static job's compile_po --check sync gate; **`web/**` is likewise a trigger** (added 2026-09-20) — `web/app.js`'s `parseConfigBool + CONFIG_*_TOKENS` and `src/config_bool.py` form a cross-language boolean-parsing invariant (AGENTS.md "Unified parsing of boolean config values"), so a change on either side must run the `tests/frontend/test_quality_ui.mjs` regression lock via the test job (the old "pure frontend web/ does not trigger" claim has been falsified; see the matching changelog entry).

**Parallel jobs** (all gated by `needs: setup`):

| Job | Environment | Content |
| --- | --- | --- |
| `static` | py3.14 | `black --check` + `isort --check` + `check_version.py` + `check_workflow_constants.py` + `check_runtime_pins.py` + `compile_po.py --check` + `check_annotations.py` + `check_skill_agents_consistency.py` + `sync_metadata.py --check` |
| `typecheck` | py3.14 | Install requirements + pinned mypy/pytest, then run `mypy` (linux target) and `mypy --platform win32`; scope comes entirely from `pyproject.toml [tool.mypy].files` |
| `test` | py3.14 | `pytest --cov=src --cov-report=term-missing` (global `fail_under=60` gate, `fail-fast: false`) + the `scripts/check_coverage.py` per-module gate (runs once on the minimum version) + coverage.xml upload + optional Codecov |
| `concurrency-test` | py3.14 | Concurrency-specific: under `COVERAGE_RCFILE=.coveragerc-concurrency` runs `test_concurrency_rate_limit.py` + `test_concurrency.py` + `test_async_http_lock.py` (dedicated config sets no global threshold) |
| `integration-verify` | py3.14 + Node 24 | apt install ffmpeg; verify the ffmpeg/node binaries are discoverable, and call `check_ffmpeg_installed()` / `check_nodejs_installed()` to verify detection logic |
| `build-verify` | py3.14 packaging interpreter | `build_exe.py --smoke --no-runtime --no-zip` (lite packaging + CLI/Web/GUI three-entry smoke, on Linux via `xvfb-run -a`); release-grade full packaging is left to build-release.yml |
| `ci-summary` | — | The only required check: aggregates the results of all upstream jobs (skipped counts as passed — path-filter skips never leave branch protection permanently pending) |

### 7. GitHub Actions Automated Build and Release (`build-release.yml`)

Workflow file: `.github/workflows/build-release.yml` (job name `Build (${{ matrix.os }})`).

**Trigger methods**:

- Manual trigger (`workflow_dispatch`, optional `create_release` input): by default only builds and uploads artifacts; checking the input also creates a Release.
- Push a `v*` tag (e.g. `v4.0.9.1`): build + automatically create a GitHub Release with artifacts attached (`permissions: contents: write`, granted only to the build / release jobs).

**Build matrix**: `windows-latest` / `ubuntu-latest` / `ubuntu-24.04-arm` / `macos-latest`, Python 3.14 (`fail-fast: false`; same value as ci.yml's build-verify packaging interpreter, guaranteeing "the packaging environment validated by CI == the one actually released").

**Steps**:

1. `prepare` job: extracts the version from pyproject.toml via tomllib and validates tag consistency (a mistagged release fails immediately); runs `check_version.py` to confirm all consumers read the version dynamically.
2. `release-create` job: on the release path **pre-creates** the Release record (a singleton job eliminating the race where multi-platform build jobs concurrently create the same Release; no files attached); on the manual release path it also creates the lightweight tag (a Release must be attached to a tag).
3. build job (matrix): each platform installs ffmpeg via its system package manager for smoke testing — Windows `choco`, Linux `apt` (plus `xvfb`; GUI smoke needs a virtual display), macOS `brew` (`brew trust aws/tap` as a separate idempotent step, `HOMEBREW_*` variables exported inline in the command); **all network-install commands are wrapped by the `.github/actions/retry` composite action** (linear backoff ×3; system package managers back off 15s, pip 10s); dependencies via `pip install -r requirements.txt` + `pip install ".[build]"`.
4. `python build_exe.py --smoke --dual` (on Linux wrapped with `xvfb-run -a`): PyInstaller runs only once. Before any packaging, stale `DouyinLiveRecorder-v*.zip` leftovers under `dist/` are pruned (otherwise `path: dist/*.zip` sweeps last run's artifacts into this run's attachment set). It then produces the **lite** zip (no ffmpeg/node, auto-downloaded at runtime) → downloads the runtimes → produces the **full** zip (built-in runtime, ~300MB). The two `make_zip` **return paths** must differ and both must exist on disk, otherwise the build exits with `SystemExit` right there. Smoke runs after **both** zips (MID-2254) against the release directory that already holds the runtimes — not against the lite build.
5. Artifact publishing: on the release path (tag / manual with create_release) the build job uploads zips **directly to the Release** via `softprops/action-gh-release@v3` (explicit `tag_name` pointing at the same Release as release-create; GitHub supports concurrent uploads of distinct assets to the same Release); the build-only path uses `upload-artifact@v7` (`compression-level: 0` to skip re-compression, retained 30 days for manual retrieval).
6. `release` job (release path): `gh release download` pulls the published assets back to verify completeness (4 platforms × (lite+full) = 8 zips; any shortfall fails instead of publishing an incomplete Release), generates `SHA256SUMS.txt`, and finally via `softprops/action-gh-release@v3` attaches the checksums and writes the release notes (`generate_release_notes: true`).

**Artifact naming**: `DouyinLiveRecorder-v{version}-{os}-{arch}-{lite|full}.zip` (e.g. `DouyinLiveRecorder-v4.0.9.1-windows-amd64-full.zip`).

### 8. Local Packaging Steps

```bash
pip install .[build]              # install the packager (PyInstaller)
python build_exe.py --smoke      # build + smoke test
python build_exe.py --smoke --dual  # same shape as CI: lite + full artifacts
# output: dist/DouyinLiveRecorder/ release directory + dist/DouyinLiveRecorder-vX.Y.Z-*.zip
```

Note: This repo is a local copy; the workflows only run after being pushed to the GitHub repository. The lite artifact (and CI Linux/macOS artifacts) does not include `ffmpeg`/`node`; they are auto-downloaded on first run.

## Design Patterns

### 1. Adapter Pattern

Each live platform's API is uniformly adapted to the same calling interface, implemented in `spider.py` and `stream.py`.

### 2. Decorator Pattern

`trace_error_decorator` is used for error tracing, implemented in `utils.py`.

### 3. Strategy Pattern

Different message push channels (DingTalk, WeChat, Telegram, etc.) are implemented as independent functions, selected at runtime based on configuration.

### 4. Singleton Pattern

Log configuration is implemented as a singleton via module import side effects, in `src/logger.py`.

### 5. Template Method Pattern

Each platform's recording flow follows the same template: detect → fetch stream → record → push.

### 6. Factory + Registry Pattern

The danmaku subsystem uses the `get_danmaku_class(platform)` registry in `src/__init__.py` (Chinese platform name → danmaku class) together with the `get_danmaku_collector(...)` factory to uniformly create each platform's collector; `main.py` obtains the collector by platform identifier without knowing the concrete platform implementation. To add a new danmaku platform you only need to register it in the registry and implement the four abstract methods `start/stop/heartbeat/decode_message` of `DanmakuBase`, with zero intrusion to callers.

## Troubleshooting

### Issue 1: Prompt says FFmpeg is missing

**Solution**:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
Built-in, no installation needed
```

### Issue 2: Prompt says Node.js is missing

**Solution**:

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
sudo apt-get install -y nodejs

# macOS
brew install node

# Windows
The program auto-downloads and installs it
```

### Issue 3: Douyin risk control prevents data fetching

**Risk-control characteristics (measured)**:

- The risk-control signal is **HTTP 200 + empty response body**, not 4xx. When troubleshooting a parse failure, first check `len(response.text)`; if it is 0 it basically means UA/Cookie was rejected
- The old mobile UA will be silently rate-limited (always reproducible on `iesdouyin.com` interfaces); you must use the desktop Chrome UA (`room.DESKTOP_UA`)
- `iesdouyin.com/share/user/<sec_uid>` is now a JS anti-scraping shell page with no `unique_id` inside, so any HTML regex is unreliable
- The `web/enter` interface occasionally returns `status_code=10002 unknown error`, a transient soft rejection (risk control / missing msToken / rate limiting); the code already does a silent retry once, which is normal fault tolerance and does not mean the room is unavailable

**Solution**:

- Update Cookie
- Lower the polling frequency
- Change IP
- Update UA (use `room.DESKTOP_UA` desktop Chrome UA)
- If the log shows `10002` and then the HTML fallback succeeds, it is a normal path and needs no action

### Issue 4: HLS validation failure with blank logs / always falling back to FLV

**Symptom** (appears continuously in logs, with no troubleshooting info at all):

```
get_response_status 校验失败（判定为不可达）:      ← 消息是空的
HLS URL validation failed, falling back to FLV    ← 原因完全不可见
```

**Root cause** (three layers, all fixed on 2026-08-05):

- The exception log only printed `{e}`, and on Windows `socket.timeout` / `TimeoutError`'s `str()` returns an **empty string**, so a timeout exception prints blank
- `main.py::_validate_stream_url` used `except Exception: return False` to swallow all failure reasons, giving no clue on fallback
- The m3u8 source HEAD probe only covered `400/401/403/405`, **404 was directly judged unreachable**; and `select_source_url` → the validation call **did not pass through the proxy**, so overseas platforms like TikTok would time out on direct validation and be misjudged

**After the fix**: exception logs include URL + exception type; all failure paths log a warning (including status_code / content-type); m3u8 HEAD non-2xx (including 404) always adds a Range GET probe; `select_source_url` passes through `proxy_addr`. After re-running, the log directly gives the real cause (e.g. `ConnectTimeout`, `HEAD=404, Range-GET=403`); if still unreachable it is an environment issue such as the CDN domain being blocked or the stream URL having expired, not a code misjudgment.

### Issue 5: Danmaku connection fails "connecting through a SOCKS proxy requires python-socks" (system proxy conflict)

**Symptom** (Bilibili and all platforms reusing `WsClient` have their danmaku connection dropped, visible in logs):

```
[弹幕采集]BilibiliDanmaku 连接关闭: connecting through a SOCKS proxy requires python-socks
```

**Two pre-fixed sub-issues** (both real defects, but not the final root cause):

- **Short room_id not converted to real room_id**: `get_bilibili_danmaku_info` used to directly request getDanmuInfo with the URL short number (e.g. `live.bilibili.com/462`); the token returned by Bilibili did not match the real room, so no danmaku was received after join; now it first calls `room/v1/Room/room_init` to convert the short number to the real room_id (462 → 763679) before proceeding (`src/spider.py`).
- **Heartbeat coroutine was never awaited**: `BilibiliDanmaku.heartbeat` is `async def`, but `WsClient._heartbeat_loop` used to call `self._on_heartbeat()` directly without awaiting; Bilibili's long connection was dropped by the server after tens of seconds without a heartbeat; now it checks `inspect.isawaitable(result)` and then `await result` (`src/ws_client.py`).

**Root cause (system proxy "ghost")**: `websockets.connect(proxy=True)` by default **auto-detects and follows the proxy**, obtaining proxy config via `urllib.request.getproxies()`; on macOS this call does not only read shell environment variables but directly reads the system-level proxy in **system network settings** (System Preferences → Network → Proxies). If a proxy tool (Clash-like) wrote HTTP/HTTPS/SOCKS three-layer proxies into system settings (e.g. `socks5://127.0.0.1:7890`), `env | grep -i proxy` finds nothing (`scutil --proxy` can read it), but websockets follows that SOCKS proxy — and the SOCKS protocol requires the `python-socks` library, which raises the above error when not installed. Video pulling goes through ffmpeg/its own headers and does not pass through websockets, so recording is unaffected by the proxy; standalone test scripts behave intermittently depending on the run environment/system proxy state.

**Fix (danmaku direct connection)**: `src/ws_client.py`'s `connect()` explicitly passes `proxy=None`, so the danmaku WS connects directly to the server, unaware of the system proxy and environment variables like `ALL_PROXY`:

```python
async with websockets.connect(
    url,
    additional_headers=self._headers,
    open_timeout=self.connect_timeout,
    ping_interval=None,   # 各平台自带心跳, 关闭库默认 ping
    max_size=None,
    ssl=self._ssl_context,
    proxy=None,           # 弹幕连接直连, 不跟随系统代理
) as ws:
```

This fix uniformly takes effect for **all platforms** (Bilibili/Douyu/Huya/Douyin/Twitch, etc.) danmaku connections (all reuse `WsClient`).

**Decision basis**: The danmaku channel is inherently a domestic direct connection and does not need an outbound proxy, consistent with the overall direct-connection semantics of "recording with proxy disabled"; minimizes dependencies (no new `python-socks`); does not touch system settings; explicit declaration is better than implicit detection (avoids re-stepping on the pit if a library upgrade changes default behavior). If an individual overseas platform's danmaku genuinely needs a proxy, a later optional `proxy` parameter can be added to `WsClient` to pass through on demand, without global following.

**Verification**: Fully run `main.py` with no proxy; danmaku is correctly written to disk as SRT; `mypy src/ws_client.py` / `py_compile` pass. When troubleshooting danmaku anomalies, first look at `logs/streamget.log` (DEBUG records collector thread start / connection ready / first danmaku received / connection close reason).

### Issue 6: Douyin/Douyu and other platforms show "live streaming" but never record (no error, no file)

**Symptom**: During `py web.py` (or `python main.py`), Douyin and Douyu rooms print "live streaming…" every monitoring cycle, but "preparing to start video recording" never appears, and no recording file is produced; on the same config, Huya and Bilibili record normally. The log has no error, warning, or hint, and the status panel always shows "live streaming".

**Scope**: All platforms where `get_record_headers()` returns `None` (measured: Douyin, Douyu). These platforms share the characteristic of having no dedicated recording request-header rules (Referer/Origin) and no corresponding Cookie configured.

**Root cause (historic structural bug)**: In `main.py`'s `run()`, the `if headers:` after `headers = get_record_headers(platform, ...)` wrongly wrapped the **entire recording chain** that follows — tls_verify/proxy insertion, recording-status registration, all TS/FLV/MP4/MKV recording branches, `check_subprocess` launching ffmpeg, and `record_success` cycle counting (about 490 lines). Any platform where `get_record_headers` returns `None` (`_RECORD_HEADER_RULES` has no Referer/Origin configured and no Cookie) had its entire recording block **silently skipped**: no print, no error, no recording, just idling every cycle. Platforms with dedicated recording headers (Huya/Bilibili) happened to be unaffected, making the problem look like "an individual platform parse issue" rather than a global structural one.

**Fix**:

1. **Indentation-level correction (main.py)**: Inside the `if headers:` block only the `-headers` insertion (4 lines) is kept; tls_verify insertion, proxy insertion, recording-status registration, all recording branches, and cycle counting are **shifted left 4 spaces as a whole**, escaping the conditional nesting and executing unconditionally.
2. **Validator UA alignment (src/stream_select.py)**: Added the `MOBILE_UA` constant (identical character-for-character to `main.py`'s ffmpeg command default UA); `_validate_stream_url` sends a mobile UA for platforms without a desktop UA — Douyu's hwa CDN occasionally returns 403 to non-browser-UA GETs, so the validator and recorder must use exactly the same UA (method GET + header Referer/Cookie + UA, a trinity).

**Troubleshooting tip**: The entry condition of a long recording chain must precisely correspond to the "whether to record" semantics; "skip the whole block when the condition is false" is the most dangerous failure mode (no exception thrown, no log printed). When all code-path analysis says "there should be a log" but there isn't, the shortest path to locate is to temporarily instrument and print the real `real_url` after `select_source_url` returns, and cross-check the block boundaries against the indentation level by drawing a diagram.

## Contributing Guide

### Code Standards

- Formatting: `black .`
- Import sorting: `isort .`
- Type checking: `mypy` (`disallow_untyped_defs = true`; CI gate, run for the host, linux and win32 targets)
- Type checking (enhanced, local): `basedpyright` is configured in `pyproject.toml` under `[tool.basedpyright]` (standard mode, excludes `typings/`/`node/`/`ffmpeg/` etc.; `venvPath` / `venv` point to the workspace `.venv`); CI still uses `mypy` as the standard.
- Comment standard: Module/function descriptions uniformly use `#` line comments, **do not use triple-quote `"""` docstrings**; multi-line descriptions start each line with `#` (functional multi-line string literals excepted, e.g. templates/SQL, which should use single quotes + line concatenation instead of `"""`)

### Testing and Coverage

- Run tests: `pytest` (`asyncio_mode = "auto"`; async cases need no explicit marker).
- Coverage gate: global `fail_under = 60`; the single source of per-module thresholds is `MODULE_THRESHOLDS` in `scripts/check_coverage.py` (spider / proxy ≥60, stream ≥70, utils ≥80, ttwid ≥85). Unregistered modules are judged against the global floor.
- Concurrency-specific tests: `test_concurrency.py` / `test_concurrency_rate_limit.py` use `.coveragerc-concurrency` (no global threshold).
- Pass counts and coverage readings follow the most recent gate output; this document does not freeze volatile numbers.

#### Web/API Smoke Test Tool (`scripts/smoke_test.py`)

A general, zero-dependency (pure standard library) Web/API smoke test tool for quickly verifying the reachability and core responses of **running HTTP interfaces** such as the Web management panel.

- Config-driven: JSON describes check items (`url` / `method` / `expected_status` / `timeout` / `headers` / `body` / `expect_contains` / `expect_json`)
- `base_url` prefix concatenation, no need to write the full address for each interface
- Three outputs: console (colored), JSON report, HTML report
- Any check failure exits with non-zero code, convenient for CI integration
- **Wired into CI**: the default case `scripts/smoke_web.json` probes the Web panel `/` and `/health` (the latter a public liveness endpoint provided by `src/web_api.py`); the `test` job in `.github/workflows/ci.yml` starts `python web.py` in a controlled way after pytest, does readiness-wait + assertions via `scripts/_ci_web_smoke.sh` (through `.github/actions/retry`), keeps `logs/web-smoke-*` artifacts and turns the job red on failure — covering the "can the panel process really bind and respond" path that TestClient cannot reach

Usage:

```bash
# 检查本机 Web 管理面板（默认 127.0.0.1:8000，示例见 scripts/smoke_web.json）
python scripts/smoke_test.py -c scripts/smoke_web.json

# 生成 HTML 报告
python scripts/smoke_test.py -c scripts/smoke_web.json -r smoke_report.html -f html
```

> Unlike `build_exe.py --smoke` (packaging-artifact smoke test, see Section 5 above), this tool does lightweight liveness probing against **running HTTP interfaces**; the two are complementary.

### Adding New Platform Support

1. Add a platform data-fetching function in `src/spider.py`
2. Add a stream-address parsing function in `src/stream.py`, whose return value includes the `actual_quality` and `available_qualities` fields
3. Add platform identification logic in `main.py`
4. Update `README.md` and this document

## Change Overview by Module (2026-10-17)

> This round covered i18n catalogue additions, Qt sidebar labels, GUI font safety, recording-chain raise messages through `tr()`, Web 422 validation text, the Docker GUI switch, CI tool bumps, package metadata/tree parity and new regression locks. The per-module file list and verification readings are in the 2026-10-17 entries of [`docs/changelog/code-wiki-history-en.md`](docs/changelog/code-wiki-history-en.md); no files or config keys were removed.

## Change Overview by Module (2026-10-29)

> This round added `.gitattributes` and normalized the line endings of 119 tracked text files from CRLF to LF; `src/javascript/*.js` stays byte-frozen via `-text`. AST/byte-level content is unchanged and no config key or dependency changed. The full file list, conflict-repair process and verification readings are in the 2026-10-29 entries of [`docs/changelog/code-wiki-history-en.md`](docs/changelog/code-wiki-history-en.md).

## Changelog

> **Live-verification retention convention** (same source as `AGENTS.md` DoD step 2): for changes
> affecting the recording chain / source selection / ffmpeg arguments / platform resolvers, write the
> real-device verification conclusion in the "Verification" subsection of the corresponding changelog
> entry here, synchronised in both CN/EN files.
> Format: `[YYYY-MM-DD] platform | masked URL | script | result | message count`.
> When verification cannot run, write `SKIP(reason)` in the result column
> (e.g. `SKIP(no network)` / `SKIP(room offline)`) and note the hand-back action;
> completion (DoD steps 1–6) must not be claimed until the user re-runs and fills in readable counts.
> Scripts also emit a `VERIFICATION_RESULT: {"platform":..., "status":..., ...}` structured line when run directly.
> Scripts: `tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py`
> (`python file.py <URL> [seconds]`; requires a live room + network; manual channel by default).
> **Rolling archive**: the detailed entries of the current release window were moved verbatim to [`docs/changelog/code-wiki-history-en.md`](docs/changelog/code-wiki-history-en.md) on 2026-10-31; this section keeps the heading index and release summary (rule stated in the "Changelog Archive Index" above).

> **Section index**: the verbatim bodies below were moved to the [archive volume](docs/changelog/code-wiki-history-en.md) ("Imported: current release window") on 2026-10-31; this section keeps only the heading index. Search the archive by the original heading text.
>
> **v4.6.0 summary (2026-10-18 ~ 2026-10-31)**: (1) GUI stack consolidated on PySide6; the legacy tkinter/pystray implementations plus `src/ui_kit.py` / `src/ui_motion.py` were removed; (2) unified ICO icon support across the GUI tray, Web tray/page and packaged artifacts; (3) Web tray migrated to Qt and the run log wraps to the viewport; (4) five repo-wide review rounds (per-hop SSRF re-checks, dangerous config keys, outbound read caps, credential masking); (5) EOL pinning, regression-test de-dating, metadata parity, CI tool bumps and repo-wide comment slimming.

### v4.7.0 (2026-11-01) — ffmpeg dynamic criteria on three slots: windows/linux now take the build-day official manifest values (advisory explicitly acknowledged via ADVISORY_ADOPT_ACK), linux resolves the download URL alongside the newest month-end tag, static table demoted to the fallback baseline

### v4.7.0 (2026-11-01) — Release-path dynamic pinning: the node slot now takes the GPG-verified official SHASUMS as its criterion (--pin-source adopt), upstream LTS promotions no longer break the release

### v4.7.0 (2026-11-01) — Runtime pins re-pinned to upstream node v26.13.0: Node 26 LTS promotion moved the first-lts pointer, node SHA256 mismatched on all four platforms

### v4.7.0 (2026-11-01) — setuptools build floor 68.0 → 84.1.0 + uv.lock pin 84.0.0 → 84.2.1: hardening after read-only triage of the external path-escape advisory (GHSA-xmj3-9gf7-h52w)

### v4.7.0 (2026-11-01) — Release credential-check (SEV-2213) false positive fixed: per-key comparison narrowed to "same key position", removing the root cause of the v4.6.0 four-platform release build failure

### v4.7.0 (2026-11-01) — Three platform-sensitive tests made platform-agnostic for CI Linux + the missing POSIX graceful-stop flag fixed in recorder.py

### v4.7.0 (2026-11-01) — brotli declared floor 1.2.0 → 1.2.1: CI deps-audit floor recheck caught the old floor itself inside the PYSEC-2026-4322 affected range

### v4.6.0 (2026-10-31) — Four root documents resynced with reality and rolled into the archive: changelog bodies moved verbatim into `docs/changelog/`, root docs keep only the heading index and release summary

### v4.6.0 (2026-10-31) — AGENTS.md aligned with repo state and wording compressed (docs only)

### v4.6.0 (2026-10-31) — Version-doc sync: the 4.6.0-dev changelog of CODE_WIKI summarized into four categories for the bilingual README v4.6.0 entry, version labels unified to 4.6.0

### v4.6.0 (2026-10-31) — i18n catalogue sync: Web tray tooltip added to all four locales

### v4.6.0 (2026-10-31) — Metadata parity: 15 target files re-checked against `pyproject.toml` as the single source of truth; CODE_WIKI dependency tables and the egg-info artifacts corrected

### v4.6.0 (2026-10-31) — CI tool pins moved to the latest PyPI releases: mypy 2.4.0 → 2.4.1, pytest 9.1.1 → 9.2.0

### v4.6.0 (2026-10-31) — Complete removal of the tkinter GUI stack (PySide6 is the only window implementation)

### v4.6.0 (2026-10-31) — GUI run-log window: word wrap follows viewport width

### v4.6.0 (2026-10-31) — Repo-wide comment-only slimming and consistency pass (zero behavior change)

### v4.6.0 (2026-10-31) — CODE_REVIEW_2026-10-30 remediation: five P0 + eight P1 + three P2 + locatable L items

### v4.6.0 (2026-10-30) — Remediation of the scattered CODE_REVIEW_2026-10-29 findings (15 unnumbered/pending items)

### v4.6.0 (2026-10-29) — Remediation of CODE_REVIEW_2026-10-29: S-03/S-04/S-06/S-07, M-01/M-04/M-05/M-13/M-17/M-26/M-34/M-35

### v4.6.0 (2026-10-29) — Repo-wide static code review (produces `docs/worklog/CODE_REVIEW_2026-10-29.md`) + `liveme.js` pin-mismatch fix and a byte-parity lock

### v4.6.0 (2026-10-29) — Regression-lock test filenames lose their date segment: 17 files renamed, references synced repo-wide

### v4.6.0 (2026-10-29) — Line-ending pinning lands: `.gitattributes` added and 119 tracked text files normalized to LF

### v4.6.0 (2026-10-22) — Unified ICO icon support: GUI tray / Web tray and page / packaged artifacts share one source of truth

### v4.6.0 (2026-10-21) — Remediation round 2: sibling leftovers and interrupted work packages closed; gates and tests fully green

### v4.6.0 (2026-10-21) — Code-review remediation: all 16 critical items closed, predicate families unified

### v4.6.0 (2026-10-20) — Comment slimming across nine recording-path modules: archaeology removed, duplication folded, logic untouched

### v4.6.0 (2026-10-20) — Comment slimming across ten runtime modules: archaeology removed, duplication folded, logic untouched

### v4.6.0 (2026-10-20) — Second repo-wide cleanup: unused imports, write-only variables, two zero-reference functions and 38 unread locals cleared; TAG_NORMAL and motion tokens wired

### v4.6.0 (2026-10-20) — Repo-wide dependency and dead-code audit: python-multipart dropped, the dead module src/ab_sign.py deleted, 18 unused imports cleared

### v4.6.0 (2026-10-20) — GUI tray gains "Hide main window" / "Settings"; the legacy pystray tray is retired and pystray/Pillow leave the dependency list

### v4.6.0 (2026-10-20) — Web system tray migrated from pystray to PySide6 (QSystemTrayIcon + QMenu); the Qt event loop now owns the main thread

### v4.6.0 (2026-10-19) — 2026-10-19 review batch: all five severe issues fixed plus medium/low-severity convergence

### v4.6.0 (2026-10-18) — Review follow-up: dead-code removal + the three §7.11 mechanized gates (R9/R10 plus two new lock files)

### v4.5.0-dev (2026-10-18) — CI fix: the vbs-behavior-test job installed only pytest, so all 11 cases errored in setup (ModuleNotFoundError: No module named 'distro')

### v4.5.0-dev (2026-10-18) — runtime pins re-pinned to upstream node v24.22.0: root cause and handling of the four-platform release-chain failure

### v4.5.0-dev (2026-10-18) — SR-06 closed: `.agents/skills/` is now git-tracked (28 files committed) + new `tests/test_skill_agents_consistency.py` (12 regression locks), so the CI required check no longer fails deterministically on a clean checkout

### v4.5.0-dev (2026-10-18) — the four root documents synced to the real state + slimmed: v4.4.0 and earlier rolled into the archive, the v4.5.0 release notes compressed, `src/config_read.py` added to every tree

### v4.5.0-dev (2026-10-18) — version-doc sync: the 4.5.0-dev changelog in CODE_WIKI distilled into the bilingual v4.5.0 README entry (`README.md` / `README_EN.md`)

### v4.5.0-dev (2026-10-17) — metadata parity re-scan: 15 target files checked against `pyproject.toml` as the fact source, three documentation drifts fixed (`README.md` / `README_EN.md` / `CODE_WIKI_EN.md`)

### v4.5.0-dev (2026-10-17) — a duplicated config.ini option no longer voids the whole file: new `src/config_read.py` tolerant-read layer + a Qt monospace family factory (attribution and fix for the three warnings in the user's log)

### v4.5.0-dev (2026-10-17) — two `src/ui_fonts.py` defects fixed: font copy failures no longer log nothing, and copy targets are cleaned of Windows reserved device names (1 new log-template msgid, catalogs 1131 -> 1132 keys; `tests/test_ui_fonts.py` 21 -> 23 cases)

### v4.5.0-dev (2026-10-17) — 6 orphan bare-text keys retracted from the i18n catalogs (four catalogs 1132 -> 1126 keys) + a new module-classified change overview section in CODE_WIKI (`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` / `AGENTS.md` / `CODE_WIKI*.md`)

### v4.5.0-dev (2026-10-17) — AGENTS.md re-verified and trimmed: 6 claims corrected against measurement, 3 `file:line` references turned into anchors, one-off readings relocated (`AGENTS.md` / `docs/agent-reference/measured-evidence.md`)

### v4.5.0-dev (2026-10-17) — approved i18n items B+C: 9 Qt button icons restored (existing keys reused, zero new entries) + 21 Chinese raise messages wired to `tr()` at the production point (16 new msgids, catalogs 1115 -> 1131 keys) (`src/gui_qt/main_window.py` / `src/gui_qt/pages/{dashboard,config,runlog}.py` / `main.py` / `src/spider.py` / `src/web_models.py` / four catalogs + `zh_CN.mo` / new `tests/test_i18n_raise_site_tr.py`, `tests/test_gui_qt_label_parity.py`)

### v4.5.0-dev (2026-10-17) — test-side fix for the Windows-only red case, three-way tool-version convergence, `pyrightconfig.json` to make IDE findings reproducible, coverage re-run (`tests/test_ui_fonts.py` / `.github/workflows/ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json` / `tests/test_pyright_config_parity.py`)

### v4.5.0-dev (2026-10-17) — Metadata parity sync (A1-A8 + B1) + images no longer carry GUI dependencies by default (single `INSTALL_GUI` switch) (`AGENTS.md` / `CODE_WIKI*` / `README*` / `Dockerfile` / `docker-compose.yaml` / `config/config.ini` / `docs/agent-reference/project-structure.md` / new `tests/test_dockerfile_image_gui_arg.py`)

### v4.5.0-dev (2026-10-17) — i18n blind spot (4) becomes machine-checked: new `tests/test_i18n_catalog_coverage.py` (three locks + mutation proof)

### v4.5.0-dev (2026-10-17) — i18n four-catalog sync: +5 sidebar nav msgids reached via by-name tr(), key count 1110 -> 1115 (`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`)

### v4.5.0-dev (2026-10-17) — GUI window layer migrated to PySide6: 1:1 landing of the prototype visual language + Qt dead-weight pruning in the packaging chain (`src/gui_qt/` / `gui.py` / `build_exe.py`)

### v4.5.0-dev (2026-10-17) — GUI visual language restyle: brand blue → warm terracotta + warm-neutral palette (`src/ui_theme.py` / `gui.py`)

### v4.5.0-dev (2026-10-17) — GUI right-border clipping fix + selectable UI font (`src/ui_fonts.py` / `gui.py` / `src/ui_kit.py`)

### v4.5.0-dev (2026-10-17) — release-chain runtime pinning gains an "online source" layer: off by default, and online values are adoptable only when the manifest carries independent authentication

### v4.5.0-dev (2026-10-04) — GUI modernization stage 6: type-scale rework + global UI scaling + transition motion (`src/ui_scale.py` / `src/ui_motion.py`)

### v4.5.0-dev (2026-10-04) — CI tool-version constants aligned with the local install: `isort_version` 9.0.1 → 9.0.2 (removing the last version gap that blocked extrapolating "local gates green" to CI)

### v4.5.0-dev (2026-10-04) — GUI static labels wired to i18n: `src/ui_i18n.py` (T marker + retranslation registry) + whole-window refill on language switch + web_api error details

### v4.5.0-dev (2026-10-04) — Xiaohongshu live-link normalization: `/livestream/<room id>` / dynamic path / `xhslink` short link / share params all wired in

### v4.5.0-dev (2026-10-03) — UI stage 5 wrap-up: customtkinter dependency fully removed + packaging chain cleanup + size baseline + xvfb normalization

### v4.5.0-dev (2026-10-03) — UI stage 4 GUI widget layer: CTk → ttk page-by-page replacement + `src/ui_kit.py` factory + Treeview incremental tables + single "UI Theme" entry

### v4.5.0-dev (2026-10-03) — `[tool.mypy].exclude` directory anchoring: bare `"ffmpeg"`/`"node"` substring false-matches fixed; 12 previously blind files enter the no-path mypy gate for the first time

### v4.5.0-dev (2026-10-03) — Bilibili mobile share links (`b23.tv`) wired in: direct numeric normalisation + short-code 302 resolution (in-process cache), reusing the desktop pipeline

### v4.5.0-dev (2026-10-03) — Douyu mobile links (`m.douyu.com`) wired in: admission whitelist + shared dispatch entry + normalised room-id extraction (trailing slash / query string / http scheme)

### v4.5.0-dev (2026-10-03) — Huya mobile share links (`hy.fan`) wired in: admission whitelist + new dispatch resolver + short-code 301 redirect resolution (standard / trailing slash / query string / http scheme)

### v4.5.0-dev (2026-10-03) — Linux arm64 (aarch64) ffmpeg support landed in three segments: four-platform release matrix + runtime official direct-download module + GHCR multi-arch image publishing

### v4.5.0-dev (2026-10-02) — `CODE_REVIEW_2026-10-02` remediation finished: L-04/L-05 closed + three gate reds and three runtime defects introduced by the remediation itself corrected

### v4.5.0-dev (2026-10-02) — New startup purge of stale bytecode caches: `src/startup_cleanup.py` (version + content-hash sentinel, whitelisted scan roots, switch defaults to on)

### v4.5.0-dev (2026-10-02) — The "register every new front-end `.mjs` in CI" rule gains a repo-side completeness lock: new `tests/test_ci_frontend_registration.py` (two-way set difference + self-hosted pin)

### v4.5.0-dev (2026-10-02) — CI typecheck gate completes the platform double-run: add `mypy --platform win32`, win32 target participates in type checking at the merge boundary for the first time (pure CI / gate change, zero runtime change)

### v4.5.0-dev (2026-10-02) — workspace-wide code review (producing `docs/worklog/CODE_REVIEW_2026-10-02.md`): 8 work packages of per-file deep review + Mimosa deep-scan triage, 2 critical / 17 medium / 47 minor

### v4.5.0-dev (2026-10-02) — Harness assets added: project-level hook body `scripts/agent_hook_guard.py` + `/dlr-dod` command entry

### v4.5.0-dev (2026-10-02) — v4.4.0 documentation finalized: 20 headings in both wikis renamed v4.4.0-dev → v4.4.0 + five backfills into the README v4.4.0 entries

### v4.5.0-dev (2026-10-02) — recompute four signature-script pin-table entries: trailing-byte drift from pre-commit's end-of-file-fixer

### v4.5.0-dev (2026-10-02) — version bump 4.4.0 → 4.5.0 + pre-commit added to dev extras: workspace-wide metadata sync and derived-artifact regeneration
