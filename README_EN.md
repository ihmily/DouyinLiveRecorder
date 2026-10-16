![video_spider](https://socialify.git.ci/y123ao6/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

English&nbsp;&nbsp;|&nbsp;&nbsp;[简体中文](README.md)

## 💡 Introduction

[![Python Version](https://img.shields.io/badge/python-v3.14%2B-blue?logo=python)](https://www.python.org/downloads/)
[![Node.js Version](https://img.shields.io/badge/node.js-LTS_v24%2B-blue?logo=node.js)](https://nodejs.org/en/download)
[![FFmpeg Version](https://img.shields.io/badge/ffmpeg-v9.0%2B-blue?logo=ffmpeg)](https://www.ffmpeg.org/download.html)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%7CLinux%7CmacOS-blue)](https://github.com/y123ao6/DouyinLiveRecorder)
[![GitHub issues](https://img.shields.io/github/issues/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/issues)
[![Latest Release](https://img.shields.io/github/v/release/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/y123ao6/DouyinLiveRecorder/total)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/stargazers)

A **lightweight** loop-monitoring live-stream recording tool that uses FFmpeg to record live sources from multiple platforms, supporting custom recording configuration and live-status notifications.

Upstream project: [ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder)

## ✨ Features

| Feature | Description |
| --- | --- |
| 🎯 **Multi-platform support** | Supports 51 platforms including Douyin, TikTok, YouTube, Kuaishou, Huya, Douyu, Bilibili, etc. (more being added) |
| 🔄 **Loop monitoring** | Automatically detects live status — starts recording when live and stops when offline |
| 🎬 **Multiple formats** | Supports TS, MKV, FLV, MP4, MP3, M4A and other output formats |
| 🖥️ **Three run modes** | CLI mode, GUI mode, and Web management panel mode |
| 📊 **Quality monitoring** | Real-time detection of each room's actual quality, with automatic alerts on quality degradation |
| 💬 **Danmaku recording** | Captures danmaku from Douyin / Douyu / Huya / Bilibili / TwitchTV, outputting SRT subtitles per segment, synced with video start/stop |
| 👀 **Danmaku monitoring** | Standalone real-time danmaku viewer (not persisted to disk); viewable in both GUI and Web panel |
| 🏷️ **Auto anchor-name update** | When an anchor renames, automatically syncs `URL_config.ini` and renames the recording directory and files |
| 📱 **Message push** | Supports DingTalk, WeChat, email, Telegram, Bark, NTFY, PushPlus, etc. |
| 🐳 **Docker support** | Supports Docker containerized deployment, ready to use out of the box |
| 🌐 **Internationalization** | Built-in Simplified Chinese / English (US) / English (UK) / Traditional Chinese, with restart-free hot switching in GUI and Web panel |
| ⚙️ **Flexible config** | Per-room customization of quality, format, segmented recording, etc., with hot-reload of config changes |
| 🔐 **Web security** | Token auth, login brute-force rate limiting, path-traversal protection, sensitive-config masking, unauthenticated write protection |

## 🚀 Quick Start

### Method 1: Download the release package (recommended for beginners)

1. Go to [Releases](https://github.com/y123ao6/DouyinLiveRecorder/releases) and download the latest released zip archive.
   Each platform ships two packages — **lite** (no bundled ffmpeg/node; the app tries to fetch them on first start)
   and **full** (runtime bundled). The **platform** segment of the attachment name is produced by
   `build_exe.make_zip()`, which reads `sys.platform` and normalizes it through
   `{"win32": "windows", "darwin": "macos"}` (anything else maps to `linux`); only the **architecture**
   segment is the literal value of `platform.machine().lower()`:

   | Target platform | Attachment name |
   | --- | --- |
   | Windows x64 | `DouyinLiveRecorder-v<version>-windows-amd64-lite.zip` / `-full.zip` |
   | Linux x86_64 | `DouyinLiveRecorder-v<version>-linux-x86_64-lite.zip` / `-full.zip` |
   | **Linux arm64** | `DouyinLiveRecorder-v<version>-linux-aarch64-lite.zip` / `-full.zip` |
   | macOS (Apple Silicon) | `DouyinLiveRecorder-v<version>-macos-arm64-lite.zip` / `-full.zip` |

   > The architecture segment for Linux arm64 reads **`aarch64`** — that is what `platform.machine().lower()` actually
   > returns on that architecture, **not** `arm64`; the package comes out of the four-platform release matrix
   > (`windows` / `linux` / `linux-arm64` / `macos`). On Linux a lite package is fetched in this order:
   > `yum` → `apt` → the official month-end build downloaded directly (verified against the asset digest published by
   > `api.github.com`); only when all of those fail does the app ask you to install ffmpeg manually.
2. After extracting, add live-room URLs to `URL_config.ini` inside the `config` folder
3. Run `DouyinLiveRecorder.exe` to start recording

### Method 2: Run from source (recommended for developers)

```bash
# Clone the project
git clone https://github.com/y123ao6/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# Install dependencies (uv is recommended)
uv sync

# Or use pip
pip install -r requirements.txt

# Run the program
python main.py        # CLI mode
python gui.py         # GUI mode
python web.py         # Web management panel mode
```

### Method 3: Run with Docker

```bash
# CLI recording mode (default, no port used)
docker compose up -d

# Web management panel mode (access via browser at http://localhost:8000)
# Note: you must first set web_host = 0.0.0.0 in the [Web] section of config/config.ini,
#       and it is recommended to enable web_auth_enable = true to set an access password
docker compose --profile web up -d

# Or build locally and start (APP_VERSION is read from pyproject.toml; without it the image LABEL version is baked in as an empty string)
docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" -t douyin-live-recorder .
docker run -d -v ./config:/app/config -v ./downloads:/app/downloads -v ./logs:/app/logs -v ./backup_config:/app/backup_config douyin-live-recorder
```

> Inside the container, FFmpeg and Node.js are provided by the image itself (installed via apt) — no need to mount the local `ffmpeg/`, `node/` directories;
> `config/`, `downloads/`, `logs/`, and `backup_config/` are persisted via volume mounts.
> If you would rather not build locally, a prebuilt multi-architecture image (`linux/amd64` + `linux/arm64`) is published
> on GHCR — see the "Pull the prebuilt multi-arch image (GHCR)" subsection of the "🐋 Docker Deployment" chapter below.

### Installing ffmpeg manually (Windows user guide)

On Windows the app downloads ffmpeg from the official gyan.dev source at startup — **that is the only
automatic route on Windows** (no mirror fallback is offered, because mirror artefacts have no official digest to check
against). If the automatic install fails (usually gyan.dev unreachable, a proxy/firewall blocking it, or a
SHA256 baseline mismatch), install it yourself in three steps:

1. **Download the official zip**: <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip>
   To verify it yourself, compare against the official digest document for that same zip,
   <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256> (this is exactly what the
   automatic installer checks).
2. **Take the `bin` folder out of the zip, put it in the app directory and rename it to `ffmpeg`**:

| How you run the app | Required final layout |
| --- | --- |
| Downloaded release package (exe) | `DouyinLiveRecorder\ffmpeg\ffmpeg.exe` |
| From source / single-file script | `<project root>\ffmpeg\ffmpeg.exe` |

   - **Do not** leave it as `ffmpeg\bin\ffmpeg.exe` — the app adds only the `ffmpeg\` directory itself to the
     lookup path and does not search sub-directories.
   - Put `ffprobe.exe` from the same folder in there too (the release-package self-check requires both
     ffmpeg and ffprobe to be present and runnable).
3. **Verify**: run `ffmpeg -version` inside that `ffmpeg\` directory — a version banner means it works.
   Restart the app; the install took effect once `logs\streamget.log` no longer reports "ffmpeg is not installed.".

Installing system-wide works equally well (`winget install Gyan.FFmpeg`, Chocolatey, or any build you trust) —
the app also looks the binary up on `PATH`.

**When the error is a SHA256 baseline rejection** (the log says to delete something matching
`_ffmpeg_official*.zip.sha256` and retry): delete those sidecar files **in the app directory** and restart.
The sidecar records the digest seen on first download, while the gyan.dev URL is a rolling address — once
upstream ships a new build the old baseline necessarily mismatches, and removing it lets the app re-record a
baseline for the new build. (Its strength equals the write permissions of that directory, so it is not an
independent trust root and does not replace the official digest document.)

> Scope: **full** release packages already bundle ffmpeg, so normally nothing has to be installed; **lite**
> packages and the single-file script do not, and need either the automatic install or the steps above.
> On macOS the automatic install uses Homebrew; on Linux the order is `yum` → `apt` → the official month-end
> build downloaded directly (verified against the asset digest published by `api.github.com`, which has to be
> reachable) — install manually through your distribution if all three routes fail. For the Apple Silicon choice
> between the bundled build and a native one, see the FAQ below.

## 🎈 Supported Platforms

**Domestic sites (37)**: Douyin | Kuaishou | Huya | Douyu | YY | Bilibili | Xiaohongshu | bigo | blued | NetEase CC | Qiandu Rebo | MaoerFM | Look Live | TwitCasting | Baidu | Weibo | Kugou | Huajiao | Liuxing | Acfun | Changliao | Inke | Yinbo | Zhihu | Haixiu | VV Planet | 17Live | LangLive | Piaopiao | 6Rooms | Lehai | Huamao | Taobao | JD | Migu | Lianjie | Laixiu

**Overseas sites (14)**: TikTok | SOOP (formerly AfreecaTV) | PandaTV | WinkTV | TTingLive (formerly Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | YouTube | Faceit | Picarto

**Douyu link formats (both domains share one recording pipeline)**: `https://www.douyu.com/8751648` | `https://m.douyu.com/8751648` (mobile). Trailing slashes (`.../8751648/`), query strings (`...?rid=8751648`, `...?dyshid=...`), the `http://` scheme and extra path segments are all accepted; alphanumeric room ids and share links are resolved back to the numeric room id before pulling the stream. A link with no room id, or an invalid one, produces an explicit error message (links are masked before they reach the logs).

**Bilibili link formats (both domains share one recording pipeline)**: `https://live.bilibili.com/22747736` | `https://b23.tv/22747736` (mobile share domain, numeric room id; trailing slashes, query strings and the `http://` scheme are all accepted). Alphanumeric short codes (e.g. `https://b23.tv/ZyQrgYf`) are resolved to the real room id by following the 302 redirect (results are cached in-process, no repeated requests) before pulling the stream; a landing page that is not a Bilibili live room, or a link with no room id / an invalid one, produces an explicit error message (links are masked before they reach the logs).

**Huya link formats (mobile share domain and desktop link share one recording pipeline)**: `https://www.huya.com/30764624` | `https://hy.fan/30764624` (mobile share domain, a purely numeric path segment is the room id; trailing slashes, query strings and the `http://` scheme are all accepted). Alphanumeric short codes (e.g. `https://hy.fan/JbmwoV`) are resolved to the real room id by following the 301 redirect (results are cached in-process, no repeated requests) and normalised to the desktop link before pulling the stream; a landing page that is not a Huya live room, or a link with no room id / an invalid one, produces an explicit error message (links are masked before they reach the logs).

> Total of **51** platforms (marketed as 60+, including platforms being added). Platform data-fetching functions are in `src/spider.py`, and stream-URL parsing is in `src/stream.py`.

**Danmaku recording support (5 platforms)**: Douyin Live | Douyu Live | Huya Live | Bilibili Live | TwitchTV

**Actual quality re-sampling and degradation alerts (7 platforms)**: Douyin | TikTok | Kuaishou | Huya | Douyu | Bilibili | NetEase CC

## 📁 Project Structure

```
DouyinLiveRecorder/
├── config/                     # config file directory
│   ├── config.ini             # main config file
│   └── URL_config.ini         # live room URL list
├── src/                        # core source package
│   ├── __init__.py             # package init + Node.js env config + danmaku platform registry/factory
│   ├── spider.py              # live stream URL parsing (60+ platforms, danmaku logic extracted)
│   ├── stream.py              # live stream recording orchestration (ffmpeg commands/segmentation/format)
│   ├── stream_select.py       # stream source selection / reachability check / probe backoff
│   ├── scheduler.py           # concurrency scheduler hub (adaptive capacity + per-platform circuit breaker)
│   ├── room.py                # live room info parsing
│   ├── utils.py               # utility function library
│   ├── logger.py              # Loguru logging config
│   ├── proxy.py               # proxy detection
│   ├── ab_sign.py             # Douyin A-Bogus signature
│   ├── ttwid.py               # Douyin visitor ttwid fetch/cache
│   ├── node_install.py        # Node.js auto-install/init
│   ├── ffmpeg_install.py      # FFmpeg install script
│   ├── ffmpeg_master_download.py  # FFmpeg master builds (per-platform fetch + verification)
│   ├── ffmpeg_proc.py         # ffmpeg subprocess management (extracted from main.py)
│   ├── video_postprocess.py   # post-recording processing (remux/transcode)
│   ├── notify.py              # live-status message push (extracted from main.py)
│   ├── recorder_status.py     # recording status tracking (extracted from main.py)
│   ├── config_io.py           # config read/write / value conversion / backup (extracted from main.py)
│   ├── config_bool.py         # boolean config parsing (是/否 equals true/false/1/0/yes/no; dependency-free)
│   ├── cookie_cache.py        # visitor Cookie process-level shared cache
│   ├── log_archive.py         # runtime log archiving (on recording stop: four logs renamed with timestamp)
│   ├── http_config.py          # HTTP client shared config (SSL verify toggle)
│   ├── async_http.py          # async HTTP client (httpx)
│   ├── sync_http.py           # sync HTTP client
│   ├── web_api.py             # Web management panel FastAPI app
│   ├── web_config.py          # Web panel config read/write
│   ├── web_tray.py            # Web-mode system tray (minimize to tray)
│   ├── base.py               # danmaku collector base class (DanmakuBase / DanmakuMessage)
│   ├── collector.py           # danmaku collector (thread bridge to main flow)
│   ├── danmaku_monitor.py     # danmaku monitor hub (DanmakuMonitorHub)
│   ├── srt_writer.py         # danmaku time subtitle (SRT) writer
│   ├── ws_client.py          # WebSocket transport layer (danmaku direct connect, proxy=None)
│   ├── platforms/            # danmaku platform implementations (factory-registered by platform id)
│   │   ├── douyin.py         # Douyin danmaku (protobuf + _tars heartbeat)
│   │   ├── douyu.py          # Douyu danmaku (STT protocol)
│   │   ├── huya.py           # Huya danmaku (WSP protocol)
│   │   ├── bilibili.py       # Bilibili danmaku (WebSocket)
│   │   ├── twitch.py         # Twitch danmaku (IRC/WS)
│   │   ├── _tars.py          # TARS private protocol codec
│   │   └── _xbogus.py        # X-Bogus signature
│   ├── proto/                # Douyin danmaku protobuf definitions
│   │   ├── douyin.proto      # protoc source definition
│   │   ├── douyin_pb2.py      # protoc-generated (DO NOT EDIT)
│   │   └── douyin_pb2.pyi     # type stub
│   └── javascript/            # JavaScript signature scripts
│       ├── crypto-js.min.js
│       ├── x-bogus.js
│       ├── haixiu.js
│       ├── liveme.js
│       └── migu.js
├── web/                        # Web management panel frontend
│   ├── index.html              # SPA entry
│   ├── app.js                  # frontend logic (API, SSE, rendering)
│   └── style.css               # stylesheet (theme, responsive)
├── typings/                    # third-party lib type stubs (for static checks)
│   ├── execjs/                 # PyExecJS stub
│   └── pystray/                # pystray stub
├── scripts/                    # engineering helper scripts
│   ├── smoke_test.py           # generic Web/API smoke test (zero-dep, config-driven)
│   ├── smoke_web.json          # smoke test sample cases (probe Web panel)
│   ├── compile_po.py           # .po → .mo compile and sync check (--check)
│   ├── check_coverage.py       # per-module coverage gate (used by CI)
│   ├── check_version.py        # version "single source of truth" dynamization check
│   └── sync_version.py         # version sync helper
├── downloads/                  # recording output dir (generated at runtime)
├── logs/                       # log dir (generated at runtime, includes danmaku_monitor.jsonl)
├── i18n/                       # i18n translation dirs (multilingual, multi-format)
│   ├── zh_CN/LC_MESSAGES/      # Simplified Chinese (gettext)
│   │   ├── zh_CN.po           # Chinese translation source (780 translation keys; 781 entries including the header)
│   │   └── zh_CN.mo           # compiled translation (required at runtime, shipped with repo)
│   ├── en_US.json              # English (US) (JSON catalog)
│   ├── en_GB.json              # English (UK) (British spelling variant)
│   └── zh_TW.yaml              # Traditional Chinese (YAML catalog, requires PyYAML)
├── ffmpeg/                     # FFmpeg dir (Windows)
├── node/                       # Node.js dir (Windows)
├── main.py                     # CLI entry
├── gui.py                      # GUI entry
├── web.py                      # Web management panel entry
├── index.html                  # M3U8 video player (standalone tool page)
├── msg_push.py                 # message push module
├── i18n.py                     # i18n implementation
├── build_exe.py                # PyInstaller packaging script (CLI/GUI/Web three entries)
├── requirements.txt            # Python dependencies
├── pyproject.toml             # Python project config
├── Dockerfile                  # Docker build file (multi-stage)
├── docker-compose.yaml         # Docker Compose (recorder/web/gui three services)
├── .dockerignore               # Docker build-context exclude
├── .gitignore                  # Git exclude
├── StopRecording.vbs           # Windows stop-recording script
├── CODE_WIKI.md                # project architecture doc
└── README.md                   # project README doc
```

## ⚙️ Configuration

### Basic config (config/config.ini)

```ini
[录制设置]
# UI language: zh_CN | en_US | en_GB | zh_TW (empty = follow system language; values such as zh_cn/zh-CN/en/en-GB/zh-Hant are also accepted and auto-normalized; falls back to en_US if the language file is missing)
language =
# Whether to skip proxy detection (yes/no)
是否跳过代理检测(是/否) = 是
# Whether to enable log files (yes/no)
是否启用日志文件(是/否) = 是
# Purge stale bytecode caches at startup: runs only when the version or source content changed
# (no-op otherwise). Scope is __pycache__ under the app folder and src/ only - never tests/,
# scripts/, downloads/ and similar directories
是否启动时清理陈旧字节码缓存(是/否) = 是
# Live save path (defaults to downloads/ if empty)
直播保存路径(不填则默认) =
# When the anchor renames, automatically update URL_config.ini and rename the recording directory/files (default: yes)
是否自动更新主播名(是/否) = 是
# Whether to separate save folders by author
保存文件夹是否以作者区分 = 是
# Whether to separate save folders by time
保存文件夹是否以时间区分 = 否
# Whether to separate save folders by title
保存文件夹是否以标题区分 = 否
# Whether to include the title in the save file name
保存文件名是否包含标题 = 否
# Whether to strip emoji from names
是否去除名称中的表情符号 = 是
# Video save format ts|mkv|flv|mp4|mp3 audio|m4a audio
视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频 = ts
# Recording quality 原画|超清|高清|标清|流畅
原画|超清|高清|标清|流畅 = 原画
# Custom quality options (comma-separated) — the user-selected quality subset; when empty or all entries are invalid it falls back to the engine's built-in full set (default: empty);
# the WEB-side add/remove and the GUI-side "switch quality" write back here; choosing a non-default quality writes "quality,live-room address" into config/URL_config.ini
自定义画质选项(逗号分隔) =
# Whether to use a proxy IP (yes/no)
是否使用代理ip(是/否) = 否
# Proxy address
代理地址 =
# Number of threads accessing the network at the same time
同一时间访问网络的线程数 = 3
# Max concurrent recordings — global concurrency cap, 0 means unlimited (default 0); changes take effect on the next check cycle
最大同时录制数(0为不限制) = 0
# Loop interval (seconds) — live-status check interval (default 60)
循环时间(秒) = 60
# Queue read URL time (seconds)
排队读取网址时间(秒) = 0
# Whether to show the loop countdown
是否显示循环秒数 = 否
# Whether to show the live source URL
是否显示直播源地址 = 否
# Whether segmented recording is enabled
分段录制是否开启 = 是
# Whether HLS capture is enabled (yes/no) — if disabled, only non-HLS candidates such as FLV are used
是否启用HLS采集(是/否) = 是
# HLS capture exclusion platforms (comma-separated) — listed platforms ignore the "是否启用HLS采集" setting and always use FLV capture
# (platform names must exactly match those shown in logs/config, e.g. 斗鱼直播,虎牙直播; leave empty to exclude nothing)
HLS采集排除平台(逗号分隔) = 虎牙直播
# Whether https recording is enabled — consolidates the former "是否强制启用https录制" and "是否禁用SSL证书验证(是/否)":
# enabled = stream pulled over https and SSL cert verification skipped; disabled = stream pulled over http and default cert verification restored
# (the value of the old key "是否强制启用https录制" is auto-migrated and inherited; https-only overseas platforms like TikTok/YouTube keep their original form when disabled)
是否启用https录制 = 是
# Platforms exempt from SSL cert verification (comma-separated) — only takes effect when "是否启用https录制 = 否" (http mode, cert verification required).
# Since FFmpeg 9.0, TLS cert verification is on by default; platforms with cert anomalies must be exempted here; required platforms are auto-appended at startup
# (Huya Live / Bilibili Live), with only appends and no removal of user-entered items
禁用SSL证书验证的平台(逗号分隔) = 虎牙直播,B站直播
# Recording free-space threshold (gb)
录制空间剩余阈值(gb) = 1.0
# Video segment duration (seconds) (default 1800)
视频分段时间(秒) = 1800
# Automatically convert to mp4 format after recording completes
录制完成后自动转为mp4格式 = 否
# Re-encode mp4 format to h264
mp4格式重新编码为h264 = 否
# Delete the original file after appending format
追加格式后删除原文件 = 是
# Generate a timestamp subtitle file
生成时间字幕文件 = 否
# Whether to run a custom script after recording completes
是否录制完成后执行自定义脚本 = 否
# Custom script execution command
自定义脚本执行命令 =
# Platforms recorded using a proxy (comma-separated)
使用代理录制的平台(逗号分隔) = tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit
# Additional platforms recorded using a proxy (comma-separated)
额外使用代理录制的平台(逗号分隔) =
# Whether to record danmaku (yes/no) — when enabled, danmaku is written to SRT subtitle files, synced with video start/stop
是否录制弹幕(是/否) = 是
# Whether danmaku monitoring is enabled (yes/no) — real-time danmaku viewing only, no SRT written (decoupled from danmaku recording, can be enabled separately)
是否弹幕监控(是/否) = 是
# Danmaku segment duration (seconds) — SRT segment granularity, recommended to match "视频分段时间(秒)"
弹幕分片时长(秒) = 1800
# Danmaku recording platforms (comma-separated) — the 5 currently supported platforms
弹幕录制平台(逗号分隔) = 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV
# Per-recording duration limit in seconds; 0 means unlimited
单次录制时长上限(秒,0为不限制) = 0
```

### Push config (config/config.ini)

```ini
[推送配置]
# Optional: 微信|钉钉|tg|邮箱|bark|ntfy|pushplus — multiple values allowed
直播状态推送渠道 =
钉钉推送接口链接 =
微信推送接口链接 =
bark推送接口链接 =
bark推送中断级别 = active
bark推送铃声 = bell
钉钉通知@对象(填手机号) =
钉钉通知@全体(是/否) = 否
tgapi令牌 =
tg聊天id(个人或者群组id) =
smtp邮件服务器 =
是否使用smtp服务ssl加密(是/否) = 是
smtp邮件服务器端口 =
邮箱登录账号 =
发件人密码(授权码) =
发件人邮箱 =
发件人显示昵称 =
收件人邮箱 =
ntfy推送地址 =
ntfy推送标签 = tada
ntfy推送邮箱 =
pushplus推送token =
自定义推送标题 = 直播间状态更新通知
自定义开播推送内容 =
自定义关播推送内容 =
只推送通知不录制(是/否) = 否
直播推送检测频率(秒) = 1800
开播推送开启(是/否) = 是
关播推送开启(是/否) = 否
```

### Cookie config (config/config.ini)

```ini
[Cookie]
# Required for recording Douyin: fill in a valid cookie copied from the browser at live.douyin.com (must at least include ttwid)
# Leaving it empty will auto-attempt to fetch a visitor ttwid (may trigger risk control; filling it in is recommended)
抖音cookie =
# Specify Douyin ttwid separately (left empty, it is fetched and process-level cached by src/ttwid.py)
ttwid =
快手cookie =
tiktok_cookie =
tiktok_guest_cookie =
虎牙cookie =
斗鱼cookie =
yy_cookie =
b站cookie =
小红书cookie =
# XHS (Xiaohongshu) app-side session sid carried in the xy-common-params header;
# left empty the built-in default is used (it may already have expired).
# Priority: environment variable XHS_SESSION_SID > this key > built-in default
xhs_session_sid =
bigo_cookie =
# ... a total of 51 platform cookie keys; see config.ini for the rest
```

> Visitor-type cookies (Douyin ttwid, Kuaishou did, etc.) are process-level shared-cached by `src/cookie_cache.py` keyed by "normalized URL + proxy" (default 30-minute TTL), so concurrent rooms do not repeatedly fetch and trigger risk control.

### Authorization config (config/config.ini)

```ini
[Authorization]
# Token obtained from PopkonTV after login (written back after auto-login with account/password)
popkontv_token =
```

### Account/password config (config/config.ini)

```ini
[账号密码]
sooplive账号 =
sooplive密码 =
flextv账号 =
flextv密码 =
popkontv账号 =
partner_code = P-00001
popkontv密码 =
twitcasting账号类型 = normal
twitcasting账号 =
twitcasting密码 =
```

### Web management panel config (config/config.ini)

```ini
[Web]
# Web management panel listen address (localhost-only by default; explicitly change to 0.0.0.0 for Docker/LAN access)
web_host = 127.0.0.1
# Web management panel port
web_port = 8000
# Whether password login is enabled (true/false)
web_auth_enable = false
# Access password (required when auth is enabled)
web_password =
# Token validity period (seconds)
web_token_expiry = 86400
# Whether to show the console window (when false, runs in background; logs written to logs/web_console.log)
web_show_console = true
# Minimize the console to the system tray (instead of the taskbar); Windows only;
# the close button is disabled — exit via the tray icon's "Exit program" menu
web_minimize_to_tray = true
# Trusted reverse-proxy sources (comma-separated). Left empty, X-Forwarded-For is not parsed;
# when behind Nginx/Caddy, fill in the proxy IP so login rate-limiting can obtain the real client IP
web_trusted_proxy =
# Allowed Host / Origin allowlist (comma-separated). Only needed when web_host is bound to
# 0.0.0.0/:: and the panel is reached via a domain name; any unlisted multi-label domain Host is
# rejected to block DNS rebinding (attacker.tld → 127.0.0.1)
web_allowed_hosts =
```

> `web_host` is `127.0.0.1` in the repo's default config (localhost access only). For Docker or LAN/public access, change it to `0.0.0.0`, and be sure to also enable `web_auth_enable` and set `web_password`.

### Live-room config (config/URL_config.ini)

Douyin supports the following 5 live-room / profile URL formats (formats for other platforms are shown in the per-platform examples below):

```
# 1) Web anchor live room (numeric room id)
https://live.douyin.com/745964462470

# 2) App anchor live room (share short link)
https://v.douyin.com/iQFeBnt/

# 3) Douyin-id concatenation (https://live.douyin.com/ + Douyin id, supports VR live recording)
https://live.douyin.com/yall1102

# 4) App anchor profile (share short link)
https://v.douyin.com/CeiU5cbX

# 5) Web anchor profile (user page address)
https://www.douyin.com/user/MS4wLjABAAAA3kr2yA4aRD-sjf9cx8xkOH8Di3RjktpKcAvqIetpsF0
```

> Notes:
> - Formats 1/3/5 use the web endpoint (support VR live); formats 2/4 use the app endpoint
> - Format 5 (web anchor profile `www.douyin.com/user/<sec_uid>`) directly extracts `sec_user_id` from the address and resolves the Douyin id, then records via the web endpoint as a live-room address — no app-endpoint probing needed
> - Short-link forms such as format 4 (app profile) first probe the live-room address; on failure they automatically fall back to Douyin-id resolution and then record via the web endpoint

```ini
# Specify quality (quality, live-room address)
超清，https://live.douyin.com/745964462470

# Specify quality and anchor name (quality, live-room address, anchor: name)
高清，https://live.bilibili.com/123456，主播: B站主播

# Comment out a live room (prefix the address with #)
# https://live.douyin.com/123456789
```

### Environment variable config

| Variable | Description | Example |
| --- | --- | --- |
| `PYTHONUNBUFFERED` | Output logs in real time | `1` |
| `PYTHONDONTWRITEBYTECODE` | Do not generate .pyc files | `1` |
| `PYTHONIOENCODING` | Python output encoding | `utf-8` |
| `TZ` | Timezone setting | `Asia/Shanghai` |
| `TERM` | Terminal type | `xterm-256color` |

## 🎬 Usage

### CLI mode

```bash
python main.py
```

### GUI mode

```bash
python gui.py
```

GUI features (5 sidebar pages):
- 📊 Console — recording-status overview, start/stop control
- 🎯 Quality monitoring — real-time check of whether each room's actual quality matches the setting
- 💬 Danmaku monitoring — real-time view of each room's danmaku stream, with filtering by room/type
- 📝 URL config — live-room address management
- 📋 Run logs — subprocess log viewer

The sidebar also provides an **Appearance** selector (light/dark/follow system) and a **Language** selector (Simplified Chinese / English (US) / English (UK) / Traditional Chinese); switching language takes effect immediately and is written back to `config.ini`, with no restart needed.

The system tray icon supports minimizing to the tray for background running.

### Web management panel mode

```bash
python web.py
```

After startup, open `http://localhost:8000` in a browser.

Features:
- **Dashboard**: real-time view of monitored/recording counts, error count, remaining disk, recording list, and log stream (SSE push)
- **Room management**: online CRUD of live-room addresses, enable/disable (auto hot-loaded into the recording main loop)
- **Config editor**: edit each config.ini item online (recording settings/push/Cookie, etc.); sensitive config items are masked
- **File browser**: browse the downloads directory and download recording files
- **Actual quality display**: the recording table shows "set quality / actual quality", highlighted in red on degradation
- **Danmaku viewer**: reads the danmaku monitor hub snapshot and shows each room's danmaku events in real time
- **Language switch**: top-bar language selector, instant four-language switching (writes back config and hot-switches in-process translations, no restart needed)

Main API routes (all require a Token, except when auth is disabled):

| Route | Method | Function |
| --- | --- | --- |
| `/api/login` | POST | Password login, returns Token |
| `/api/status` | GET | Recording status (incl. actual quality) |
| `/api/status/stream` | GET | Recording-status SSE stream |
| `/api/rooms` | GET/POST/PUT/DELETE | Live-room CRUD |
| `/api/rooms/toggle` | POST | Enable / disable a live room |
| `/api/config` | GET/PUT | Read / modify config |
| `/api/language` | GET/PUT | Query / switch UI language |
| `/api/files`, `/api/files/download` | GET | Recording file browse and download |
| `/api/logs`, `/api/logs/stream` | GET | Log query / SSE real-time push |
| `/api/danmaku` | GET | Danmaku monitor snapshot |

The Web mode shares the same recording engine and config file with CLI mode; CRUD of live-room addresses is auto hot-loaded by the recording main loop.

Background mode: set `web_show_console` to `false`; under Windows the console window is hidden, logs are written to `logs/web_console.log`, and the program runs fully in the background.

Under Windows the console defaults to "minimize to system tray" (`web_minimize_to_tray = true`): after clicking minimize the window disappears from the taskbar and collapses to the system tray; double-click the tray icon to restore; the title-bar close button is disabled — exit via the tray icon menu's "Exit program".

> ⚠️ **Security note**: the default bind is localhost-only (`127.0.0.1`) with authentication disabled. If Docker, LAN, or public access requires binding to `0.0.0.0`, enable `web_auth_enable` and set a strong password at the same time.

### Recommended recording formats

- **Long recordings**: `ts` is recommended — written in real time, resilient to corruption on power loss
- **Short recordings**: `mp4` or `mkv` is recommended — directly usable after recording completes
- **Audio-only recording**: `mp3` or `m4a` is recommended

### Quality notes

| Quality code | Chinese name | Description |
| --- | --- | --- |
| OD | 原画 | Original Definition, highest quality |
| BD | 蓝光 | Blu-ray, ultra-high definition |
| UHD | 超清 | Ultra HD |
| HD | 高清 | High Definition |
| SD | 标清 | Standard Definition |
| LD | 流畅 | Low Definition, lowest quality |

Supported platforms: Douyin, TikTok, Kuaishou, Huya, Douyu, Bilibili, NetEase CC. When a platform's actually delivered quality is lower than the configured quality, an automatic alert and flag are raised.

### Source selection (HLS/FLV)

The recording stream source is automatically selected between HLS (m3u8, pulled segment by segment) and FLV (a single long connection): by default HLS is preferred, falling back to FLV in order when validation fails, with `record_url` as the final fallback. It is controlled by two config items together:

| Config item | Effect |
| --- | --- |
| `是否启用HLS采集(是/否)` | Global switch: when enabled (default), the HLS source is preferred and falls back to FLV when unreachable or absent; when disabled, all platforms use only non-HLS candidates such as FLV |
| `HLS采集排除平台(逗号分隔)` | Platform-level exclusion list: listed platforms **ignore the global switch and always use FLV capture** (equivalent to disabling HLS capture for that platform only — HLS sources take no part in candidates or fallback) |

- **Use case**: you prefer HLS recording overall (HLS pulls segment by segment and is immune to a single long connection being cut off by the CDN), but an individual platform's HLS source is unstable or risk-controlled, and you want only that platform forced onto FLV — just add it to the exclusion list, without having to turn off the global HLS switch
- **Fill format**: platform names must **exactly match** what the logs/config file show (e.g. `斗鱼直播`, not `斗鱼`); separate multiple platforms with commas (Chinese or English commas both work), e.g. `斗鱼直播,虎牙直播`; leave empty (default) to exclude nothing — behavior stays identical to previous versions
- **Priority semantics**: the exclusion list takes precedence over the global switch — even with "是否启用HLS采集(是/否) = 是" (yes), a listed platform only uses FLV; platforms outside the list are completely unaffected and keep HLS priority per the global config
- **Boundary behavior**: if an excluded platform's parsed result contains only an HLS source with no FLV/record_url fallback, the round is abandoned with a warning (the log suggests "remove the platform from the exclusion list to restore HLS capture"); an h265-encoded FLV source no longer triggers a switch to HLS (the logic that auto-saves h265 FLV recordings as TS format is unaffected)
- **Hot reload**: the main loop re-reads the config every round — save your changes and the next monitoring round picks them up, no restart needed

### Danmaku recording and danmaku monitoring

The danmaku features are controlled by two **mutually decoupled** toggles, which can be enabled separately or together:

| Config item | Effect |
| --- | --- |
| `是否录制弹幕(是/否)` | Danmaku is written to SRT subtitle files, synced with video start/stop |
| `是否弹幕监控(是/否)` | Real-time danmaku viewing only, no SRT written (GUI "Danmaku monitoring" page / Web `/api/danmaku`) |
| `弹幕分片时长(秒)` | SRT segment granularity, recommended to match "视频分段时间(秒)" |
| `弹幕录制平台(逗号分隔)` | Whitelist of platforms with danmaku enabled |

- **Supported platforms (5)**: Douyin Live, Douyu Live, Huya Live, Bilibili Live, TwitchTV
- **Output files**: SRT corresponds one-to-one with video segments, named `{base name}_{segment index:03d}.srt` (e.g. `_000.srt` corresponds to `_000.ts`); when not segmented, `{base name}.srt`. The timeline is based on a monotonic clock, aligned with ffmpeg's `segment -reset_timestamps` PTS, and can be loaded directly by players
- **Danmaku direct connect**: the danmaku WebSocket explicitly does not follow the system proxy, avoiding immediate disconnection under a SOCKS proxy
- **Monitor sidecar log**: danmaku monitor events are also written to `logs/danmaku_monitor.jsonl` (5MB rotation)
- Douyin danmaku auto-fetches a visitor ttwid when the cookie is empty; Bilibili danmaku auto-fetches a real buvid (login cookie → spi endpoint → homepage Set-Cookie → random fallback)

### Auto anchor-name update

With `是否自动更新主播名(是/否)` enabled (default "yes"), whenever the latest anchor name is resolved each round and differs from the name recorded in `URL_config.ini`, the program automatically does two things:

1. **Rename the filesystem**: `{save path}/{platform}/{old anchor name}` → new anchor-name directory; recursively rename all recording artifacts (TS / FLV / SRT / subtitles) in the directory tree that start with `{old name}_`, and title directories ending with `_{old name}`; if the new-name directory already exists, items are merged and moved in one by one (compatible with an anchor reverting to a former name)
2. **Write back the config file**: precisely match by URL segment and replace only that line's anchor-name field, fully preserving the quality segment, the `#` comment prefix, and the line-ending style; the operation is idempotent

Safety constraints:

- The detection point is located "after live data is parsed, before recording starts", at which time the thread is necessarily not recording — naturally avoiding the ffmpeg file-occupancy window
- **Filesystem first, then config file; the name used this round is switched only after both succeed**; on any failure, the old name is kept and retried automatically on the next poll round
- When an individual file is occupied by background transcoding/a player, only a warning is skipped past — it does not block the whole process
- Custom stream addresses (whose anchor name contains a per-round random UUID) and nicknames that become blank after cleaning are automatically skipped
- Disabling this toggle keeps manual names unchanged

### Multi-language and UI switching

Four translation catalogs are built in, probed at load time in the order `gettext .mo → <lang>.json → <lang>.yaml`:

| Language code | Display name | Catalog file |
| --- | --- | --- |
| `zh_CN` | Simplified Chinese | `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` |
| `en_US` | English (US) | `i18n/en_US.json` |
| `en_GB` | English (UK) | `i18n/en_GB.json` |
| `zh_TW` | Traditional Chinese | `i18n/zh_TW.yaml` |

- The config key `language`: leave it empty to follow the system language; values such as `zh_cn` / `zh-CN` / `en` / `en-US` / `en-GB` / `zh-Hant` / `zh_CN.UTF-8` are accepted and auto-normalized to the canonical language code; unrecognized values or missing language files fall back to `en_US`
- **Hot switching**: switchable via three paths — the GUI sidebar language selector, the Web panel top-bar language selector, or directly editing `config.ini`; the CLI main loop checks for config changes each round and reloads translations immediately, **no process restart needed** (the running ffmpeg subprocess is unaffected)
- Translations no longer depend on the `LANG` / `LANGUAGE` environment variables (generally unset on Windows)
- `zh_TW.yaml` requires `PyYAML`; if missing, only that language is lost, other formats are unaffected

### Stop recording

- **Windows**: run `StopRecording.vbs` or press `Ctrl+C` in the terminal
- **Linux/macOS**: press `Ctrl+C` in the terminal
- **Docker**: run `docker-compose stop`

### Notes

1. To record overseas platforms such as TikTok or SOOP (formerly AfreecaTV), enable the proxy in the config
2. For long uptime, set a longer loop interval (e.g. 60 seconds) to avoid frequent requests getting your IP banned
3. Files are saved automatically after the live stream ends — no manual stop needed
4. If a recorded video file is corrupted, `ts` format recording is recommended
5. Recording Douyin requires a valid cookie (at least containing ttwid), otherwise risk control may be triggered
6. Some platforms need a Node.js environment to run JavaScript signature scripts, which is auto-installed under Windows

## 🐋 Docker Deployment

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed
- [Docker Compose](https://docs.docker.com/compose/install/) installed

### Quick start

```bash
# 1. Clone the project
git clone https://github.com/y123ao6/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# 2. Edit the config file
# Add live-room addresses in config/URL_config.ini

# 3. Start the container (default CLI recording mode)
docker compose up -d

# 4. View logs
docker compose logs -f
```

### Pull the prebuilt multi-arch image (GHCR)

The `.github/workflows/docker-publish.yml` workflow builds and pushes one layer per native runner (amd64 and arm64)
on every `v*` tag and then merges them by manifest digest — so **a single `docker pull` resolves to the layer matching
the host architecture**:

```bash
# Replace <owner> with the GitHub account that owns the image (GHCR namespaces are always lower-cased)
docker pull ghcr.io/<owner>/douyin-live-recorder:latest
docker run -d -v ./config:/app/config -v ./downloads:/app/downloads \
  -v ./logs:/app/logs -v ./backup_config:/app/backup_config \
  ghcr.io/<owner>/douyin-live-recorder:latest
```

- Tags: `latest` and `vX.Y.Z`; `latest` is produced only from a `v*` tag and cannot be overwritten by a manual run.
  The two per-architecture tags (`:vX.Y.Z-amd64` / `-arm64`) are intermediate products of the merge step and are not
  cleaned up automatically at the moment.
- Anonymous pulls require the GHCR package visibility to be **public** — a one-off manual action in the repository settings.
- This is **deliberately a different name** from `image: y123ao6/douyin-live-recorder:latest` in `docker-compose.yaml`:
  compose goes through `pull_policy: build` and builds in place (it does not pull a same-named registry image), so the
  "Quick start" instructions above stay as they are. Use the `docker run` line above for the GHCR image; on an arm64
  host the in-place compose build works just as well.

### Switch run mode

`docker-compose.yaml` has three built-in services (recorder / web / gui) that you switch via profile without editing the file:

```bash
# CLI recording mode (default, no port used)
docker compose up -d

# Web management panel mode (maps port 8000, access via browser at http://localhost:8000)
docker compose --profile web up -d

# GUI mode (requires an X11 display environment; run xhost +local: on the host first)
docker compose --profile gui up -d
```

> ⚠️ Web-mode note: `web.py` listens on `127.0.0.1` by default; inside the container you must set `web_host = 0.0.0.0` in the `[Web]` section of `config/config.ini` to access it from the host; it is also recommended to enable `web_auth_enable = true` and set `web_password`.

### Data mounts

```yaml
volumes:
  - ./config:/app/config:rw          # config directory (required)
  - ./downloads:/app/downloads:rw    # recording download directory (required)
  - ./logs:/app/logs:rw              # runtime log directory
  - ./backup_config:/app/backup_config:rw  # config backup directory
```

### Port mapping

Only the `web` service (Web management panel mode) maps ports; the `recorder` / `gui` services listen on no ports:

```yaml
ports:
  - "127.0.0.1:8000:8000"   # Web panel port (web profile only; exposed to the local host by default)
```

### Environment variables

| Variable | Description | Default |
| --- | --- | --- |
| `TZ` | Timezone | `Asia/Shanghai` |
| `PYTHONUNBUFFERED` | Real-time output | `1` |
| `PYTHONDONTWRITEBYTECODE` | Do not generate .pyc files | `1` |
| `PYTHONIOENCODING` | Python output encoding | `utf-8` |
| `TERM` | Terminal type | `xterm-256color` |

### Docker image features

- **Multi-stage build**: the builder stage installs dependencies into a virtualenv; the runtime stage is a slim image
- **Non-root user**: runs as the `recorder` user for improved security
- **Health check**: automatically detects whether the `main.py` or `web.py` process is alive
- **Resource limits**: defaults to 2 CPU / 2G memory (adjustable in docker-compose.yaml)
- **Log rotation**: single file 50MB, up to 3 retained
- **Built-in Node.js 24 LTS**: for running JavaScript signature scripts

## 🛠️ Development Guide

### Environment requirements

- Python >= 3.14
- FFmpeg (downloaded automatically from the official source on Windows at startup; on Linux the app tries
  `yum` → `apt` → the official month-end build, on macOS it uses Homebrew — the package-manager routes need
  root/administrator, so install manually when all of them fail)
- Node.js (downloaded and unpacked into the program directory automatically on Windows; on Linux the app uses
  `yum` (RHEL-family, requires EPEL) or `apt`, on macOS it uses Homebrew — the package-manager routes need
  root/administrator, so install manually when they fail)

### Install dev dependencies

```bash
# Use uv (recommended)
uv sync --dev

# Or use pip
pip install -r requirements.txt
pip install .[dev]
```

### Code conventions

```bash
# Format code (line-length = 120)
black .

# Sort imports
isort .

# Type check (CI uses mypy; no path argument, scope comes from pyproject.toml [tool.mypy].files)
mypy

# Type check (local enhancement, optional): basedpyright
# Configured in pyproject.toml under [tool.basedpyright], venvPath points to the workspace .venv (relative path, portable)
# First time: create and install deps: python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
basedpyright

# Run tests
pytest
```

> **Comment convention**: module/function docs uniformly use `#` line comments, not triple-quoted `"""` docstrings; functional multiline string literals (templates/SQL) use single quotes + line concatenation instead of `"""`.

> **Five-tool quality gate**: this project uses `mypy` (src + tests) / `basedpyright` (tests) / `pytest` (0 warnings) / `black --check .` / `isort --check-only .` jointly as a quality gate; all-green in CI is a prerequisite for merging. Current baseline: **974 passed / 2 skipped / 0 warnings**.

> **Test note**: `tests/test_web_api.py`'s symlink-related cases (`TestListFiles::test_broken_symlink_skipped` / `test_symlink_outside_skipped`) auto-`pytest.skip` in environments where real symlinks cannot be created (Windows without Developer Mode, some sandboxes) — this is normal and does not indicate a code defect.

### Project documentation

- [CODE_WIKI.md](CODE_WIKI.md) - project architecture doc (detailed module descriptions, dependencies, design patterns)

### Web/API smoke testing

The project ships a generic, zero-dependency Web/API smoke-test tool `scripts/smoke_test.py` (pure standard library, no third-party packages needed), which can do lightweight liveness probes against **running HTTP interfaces** such as the Web management panel.

```bash
# Check the local Web management panel (default 127.0.0.1:8000; sample config in scripts/smoke_web.json)
python scripts/smoke_test.py -c scripts/smoke_web.json

# Generate an HTML report
python scripts/smoke_test.py -c scripts/smoke_web.json -r smoke_report.html -f html
```

- Config-driven (JSON): `url` / `method` / `expected_status` / `timeout` / request headers / request body / response text that should be included / expected JSON fields
- Supports `base_url` prefix concatenation; console / JSON / HTML report formats; non-zero exit code on failure (can be wired into CI)
- Unlike `build_exe.py --smoke` (packaging-artifact smoke test), this tool probes **running HTTP interfaces** for liveness — the two complement each other
- The default case `scripts/smoke_web.json` probes the Web panel `/` (home page 200) and `/health` (`{"status": "ok"}`, a public liveness endpoint provided by `src/web_api.py`, not gated by `web_auth_enable`)
- **Wired into CI**: the `test` job in `.github/workflows/ci.yml` starts `python web.py` in a controlled way after pytest, then runs the `scripts/smoke_web.json` smoke test once it is ready (network flakiness handled via `.github/actions/retry`; on failure it keeps the `logs/web-smoke-*` artifacts and turns the job red), covering the "can the panel process really bind and respond" path that TestClient cannot

### Add a new platform

**Video recording platform:**

1. Add a platform stream-URL parsing function in `src/spider.py` (refer to existing platform implementations)
2. Add a stream-URL parsing function in `src/stream.py`, with the return value containing `actual_quality` and `available_qualities` fields
3. Add platform identification logic in `main.py` (the `PLATFORM_HOST` list and the recording branch)
4. Update `README.md` and `CODE_WIKI.md`

**Danmaku recording platform (if danmaku support is needed):**

1. Create `<platform>.py` under `src/platforms/`, inheriting `DanmakuBase` from `src/base.py`, implementing connect/auth/message parsing
2. Register it in the danmaku platform registry in `src/__init__.py` (platform name must match the `platform` id in `main.py`); decoupled creation via the `get_danmaku_class` / `get_danmaku_collector` factory
3. Add the platform branch at the danmaku-recording wiring in `main.py` (construct `record_danmaku_args` and pass it to `check_subprocess`)
4. Update `README.md` and `CODE_WIKI.md`

> Note: the danmaku subsystem and `src/spider.py` (video stream-URL parsing) are two parallel, decoupled abstractions; `spider.py` does not import `src/platforms`.

## ❓ FAQ

**Q: Recording shows "ffmpeg missing, cannot record"**

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# The program ships with ffmpeg, no install needed
```

**Q: Which ffmpeg is actually used on an Apple Silicon (M-series) Mac?**

The macOS ffmpeg bundled in the full release package is upstream's **x86_64 static build**
(ffmpeg.org only publishes "Static builds for macOS 64-bit" and **no arm64 build**), so on
Apple Silicon it runs through **Rosetta 2** translation. To keep it from shadowing a native
build the user installed themselves: when "macOS + arm64 + another ffmpeg already exists on the
system PATH" all hold, the program **prefers the system one** (e.g. what `brew install ffmpeg`
installs, a native arm64 build) and no longer prepends the bundled `ffmpeg/` directory to `PATH`.
In every other case (Intel Mac, Windows, Linux, no ffmpeg on the system, or the PATH hit turns
out to be the bundled copy itself) the previous behaviour is kept and the bundled build is used.
The single-file script `douyin_live_recorder_standalone.py` applies the same criteria; there it
shows up as `find_ffmpeg()` returning the system build's path instead of reordering `PATH`.

How to confirm which copy is in effect:

```bash
ffmpeg -version          # a Homebrew build carries --prefix=/opt/homebrew/... (native on Apple Silicon)
                          # the bundled evermeet static build has no such prefix
which ffmpeg              # points into the bundled ffmpeg/ directory => the bundled copy is in use
```

Or look for the "FFmpeg PATH priority" line in the debug log (written to `logs/streamget.log`
when `config.ini` has `是否启用日志文件 = 是`), which states explicitly whether the program is
"yielding to the native system ffmpeg <path>" or "still prepending the bundled directory <path>".

> Docker is unaffected by this policy: the image installs ffmpeg via apt, and on Apple Silicon
> the Linux arm64 container is built/run for the host architecture, so it is native already.

**Q: Shows "Node.js missing" or "execjs"-related errors**

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
sudo apt-get install -y nodejs

# macOS
brew install node

# Windows
# The program auto-downloads and installs into the node/ directory
```

**Q: Shows "IP banned, please change device or network"**

- Check whether the proxy is enabled
- Lower the loop monitoring frequency
- Wait a while and try again

**Q: Douyin risk control prevents data retrieval**

- Fill `config.ini`'s `[Cookie]` section with a valid cookie copied from the browser at `live.douyin.com` (must at least include `ttwid`)
- Lower the loop monitoring frequency (the default 120-second loop is already conservative; you may increase it as appropriate)
- Change IP or use a proxy
- Key troubleshooting points (verified conclusions):
  - The typical signal of Douyin risk control is **HTTP 200 + empty response body**, not a 4xx error code; seeing `web/enter` return `status_code=10002 / unknown error` then auto-falling back to HTML scraping is a **normal fault-tolerant path**, not a recording failure
  - Douyin API requests must use a **desktop User-Agent**; the old mobile UA is silently throttled (returns empty body)
  - For profile-type links (formats 4/5), fill in the complete address directly; the old `iesdouyin.com/share/user/` path has become an anti-scraping shell page — do not use it

**Q: HLS check log is blank and always falls back to FLV**

- Symptom: the log shows `get_response_status check failed (judged unreachable): ` (blank message) immediately followed by `HLS URL validation failed, falling back to FLV`, repeating
- Cause (fixed on 2026-08-05):
  - Under Windows, `socket.timeout` / `TimeoutError`'s `str()` is empty, causing exception logs to show blank — impossible to tell whether it was a timeout, connection refused, or a cert issue
  - The stream-URL check function used to silently swallow all exceptions (`except Exception: return False`), so when falling back to FLV there was no cause to inspect
  - The m3u8 source HEAD probe did not cover 404 (Douyin and other CDNs often return 404 for HEAD while GET pulls fine), and from HLS source selection to the check call the **proxy was not forwarded**, causing TikTok and other proxy-required platforms to time out on direct-connect checks and be misjudged unreachable
- Behavior after the fix: exception logs include the URL and exception type; all failure paths log detailed warnings (with status code / content-type); m3u8 HEAD non-2xx (**including 404**) always gets a `Range: bytes=0-0` GET probe; HLS source selection correctly forwards the proxy. If it still falls back after re-running, the log will directly give the real cause (e.g. `ConnectTimeout`, `HEAD=404, Range-GET=403`) — at that point it is usually an environmental issue such as the CDN domain being blocked or the anchor's stream URL expiring, not a code misjudgment

**Q: Recorded video file is corrupted**

- `ts` format recording is recommended
- Check that disk space is sufficient
- Check that the network is stable

**Q: How to push live-start notifications only, without recording?**

Set `只推送通知不录制(是/否) = 是` in the `[推送配置]` section of `config.ini`

**Q: Forgot the Web panel password?**

Directly edit the `web_password` item in `config/config.ini`; after changing it, restart `web.py`. After a password change, all existing Tokens are invalidated and require re-login.

## ❤️ Contributors

<a href="https://github.com/y123ao6/DouyinLiveRecorder/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=y123ao6/DouyinLiveRecorder" />
</a>

## 📄 License

This project is open-sourced under the [MIT License](LICENSE). Stars and Forks are welcome!

## ⏳ Changelog

### v4.4.0 (2026-09-29 ~ 2026-10-01) — Web panel migrated from FastAPI to Starlette (fastapi/pydantic removed, 24 route contracts preserved verbatim) / Web frontend motion layer & mobile adaptation / GUI theme layer (phase 3) and adaptive label wrapping eradicating the DPI freeze / root cure for the douyin HEVC-origin-room "no usable source" deadlock & h265 candidates admitted by save format / two full code-review rounds with P0 fixes (standalone SSRF triple guard, ffmpeg command log masking, etc.) / i18n blind-spot backfill / dependency & doc reconciliations

> This release (v4.4.0, 2026-09-29 ~ 10-01) is a "UI modernization + full review fixes" cycle. Four things matter most: ① **the Web panel backend moved from FastAPI to a Starlette-driven design** — a self-built route adapter plus a zero-dependency validation layer, with all 24 route contracts and every security invariant preserved verbatim, and runtime dependencies 23 → 21; ② **two full code-review rounds** (`CODE_REVIEW_2026-09-29_2` with all 31 numbered fixes landed + `CODE_REVIEW_2026-09-30` with Critical 2 / Medium 51 / Minor 160, P0 fixed) cleared a batch of silent-failure modes — the standalone edition's SSRF/local-file-read chain and ffmpeg commands writing credentials to disk in plaintext among them; ③ **the douyin HEVC-origin-room deadlock is cured** — live streamers whose rooms logged "no usable source this round" every round and never recorded (three individually-correct rules stacking: hevc substitution, the pre-probe h265 candidate drop, and the silent HLS-config drop) now record again; h265 candidates are admitted by save format (TS/MKV/MP4) and a zero-source observability warning was added; ④ **the GUI theme layer (phase 3)** and **the Web frontend motion layer (phase 1)** shipped, and adaptive label wrapping eradicated both-side clipping and the DPI-rescale freeze. **There are breaking changes (dependency surface)** — see the dedicated section below. Full root-cause analysis and verification are in [CODE_WIKI.md](CODE_WIKI.md).

**✨ New Features / Improvements**
- **GUI theme layer (phase 3)**: new `src/ui_theme.py` (zero display dependencies, safe to import headlessly) — 13 semantic token slots × three themes (light / dark / high contrast), a sidebar theme menu that switches at runtime and persists to `config.ini [GUI] gui_theme`; WCAG contrast checks (body text 4.5 / non-text & disabled 3.0) continuously enforced by `tests/test_ui_theme.py` (34 tests).
- **Web frontend motion layer (phase 1)**: new `web/motion.js` (zero-dependency IIFE exposing `window.__dlrMotion`) — scroll-in reveals (IntersectionObserver with stagger) / parallax particles (count adapts to viewport, halved on low-core devices) / full `prefers-reduced-motion` degradation / pause while the page is hidden / `destroy()` leaves no timers behind; wired via `web/index.html` + `web/style.css`; `tests/frontend/test_motion.mjs` 5 tests (node:test sandbox, zero npm dependencies).
- **Self-built Web adapter layer** (added with the migration): `src/web_models.py` (9 pure-stdlib dataclass request models replacing pydantic) + the `_route` adapter in `src/web_api.py` (JSON body parsing / Query clamping / threadpool dispatch for sync endpoints / JSONResponse wrapping), with the bodies of all 24 route handlers untouched.
- **The `retry` composite action gains a `fail_fast_codes` input (exit-code tiering)**: with it omitted, the behavior of all 16 existing call sites is byte-identical; the web smoke call site passes `"2"` so configuration-class errors fail immediately without entering backoff — never rewritten to 0 or downgraded to a warning just to make the pipeline green.
- **Two new test defenses**: R7, an AST gate over the real-device collector script template (`__main__` guard / zero collection-time side effects / two-step argv guard / platform-prefixed cleanup, with all 5 live_collector scripts hardened in the same batch); R8, a repo-wide scan for leftover `MUTATION-` markers (a mutation not reverted turns the gate red, with the three hard rules written back into AGENTS.md).
- **New dynamic route-contract lock** `tests/test_web_api_routes.py` (exact set of 24 method/path pairs + the `/web` mount), replacing the static baseline JSON that the secret-scanning gate blocked.
- **h265 candidates admitted by save format (TS/MKV/MP4 can stream-copy HEVC) + zero-source observability for the silent HLS drop**: `_h265_copy_format_supported()` reads main's hot-reloaded `video_save_type` and admits HEVC stream copy for TS/MKV/MP4 (the h265 primary candidate now enters the regular probe sequence) while FLV (HEVC-in-FLV is an Enhanced-FLV extension), MP3/M4A and out-of-domain values stay conservatively dropped; main.py's h265→TS forcing block gains the same-predicate guard (no takeover and no "use TS format instead" warning when the save format is already TS/MKV/MP4). When m3u8 candidates are dropped as a whole by the HLS config (global switch / exclusion list) and the round ends with no usable source, a new warning names the cause, the candidate count and the recovery switches — closing the only "zero-log" source-selection cause; healthy rounds that do select a source stay silent.

**🐛 Fixes**
- **Root cure for the douyin HEVC-origin-room "no usable source this round" deadlock**: streamers were live yet recording was skipped every round, with the status line's cumulative error count stuck at 0 (source-selection failures don't feed error samples, so the status line alone looks healthy). Three individually-correct rules stacked into the deadlock — at the origin tier with `hevc_flv_url` published, the h265 FLV **replaced** the h264 one as the only FLV candidate; `select_source_url` dropped every `codec=h265` candidate before probing; with HLS collection disabled the h264 m3u8 group was dropped silently and record_url (an `.m3u8`) was disabled in tandem — zero usable candidates after filtering. Fix: before the hevc substitution, the replaced h264 origin URL is stored into `flv_url_list` (the fallback takes over when HLS is off/unreachable; entries byte-identical to the hevc URL or already carrying the `codec=h265` marker are not collected). Live verification on a live HEVC-origin room: with HLS off the h264 FLV fallback was selected (this shape was always "no usable source" pre-fix) → `E2E_RESULT: CURED`.
- **Standalone-edition twin drift (Critical, 2 items)**: ① the probe/recording SSRF and local-file-read chain (default `build_opener` registering FileHandler + no protocol/internal-IP vetting of candidates + ffmpeg lacking `-protocol_whitelist` — three layers stacked so `file://` and cloud-metadata addresses could go from probe to allowed to recorded on disk) — fixed with an explicit handler whitelist, an `_untrusted_stream_target_reason` internal-IP check (covering abbreviated forms like `2130706433`/`0x7f000001`), and `-protocol_whitelist` at both command definition points; ② the full ffmpeg command (Cookie headers and token-bearing stream URLs included) was written round after round in plaintext to `logs/ffmpeg.log` — now masked via `_mask_ffmpeg_cmd_for_log` before writing.
- **P0 six-pack**: rooms that exit while paused on "disk full" no longer stay in `running_list` forever (the root cause of every room refusing to restart after space recovers); GUI config saving now does a real atomic write (no longer re-tightening 0600 to umask permissions on POSIX); Web password handling unified to strip in three places (passwords with leading/trailing spaces no longer self-lock authentication with 403); `update_config_line` drops the unquoted-value inline-comment fallback heuristic (config values containing ` #` are no longer silently polluted); camelCase credentials in header form (`myToken:`/`sessionKey:`) are masked again; `replace_url` switched to segment-exact matching (sibling room lines whose URLs share a prefix are no longer wrongly commented out by the "dead address auto-comment" path).
- **31 numbered fixes from the full review**: Shopee short-link landing pages get the double gate (domain-family whitelist + internal-IP check; untrusted → drop the redirect and strip cookies); per-hop internal-IP re-checking on async HTTP redirects; a scheme-whitelist opener for `sync_req` (file/ftp/data handlers no longer registered); raw URLs reaching logs on PandaTV/WinkTV and similar platforms are masked; Kuaishou did / Bilibili buvid device fingerprints no longer shared across proxy exits; an `anchor_name` of None no longer crashes the whole parsing round; the TikTok quality-selection defect where HLS-only rooms "requested smooth but pulled original" with no downgrade notice; Bilibili danmaku host rotation swallowing real disconnects as "fake closes"; the Web auth refusal message no longer swallowed by stdio redirection; `tr()` secondary exceptions no longer replacing the original one; the frontend reauth password moved to a masked dialog and generation tokens on the three polling chains preventing orphaned timer chains; GUI status-line matchers recomputed lazily per language, `after` self-rescheduling chains wrapped in `try/finally` against permanent breakage, a single-flight entry shared by "stop recording"/"quit", per-event fault tolerance in the tail thread; and the collection-time pollution from real-device scripts (real platform connections / output-dir wipes; `pytest --collect-only` 20.55 s → 0.81 s).
- **Sync-probe internal-IP closure**: the synchronous probe previously had no internal/loopback/cloud-metadata vetting of even the initial URL (the protocol-shape whitelist blocks `file://` but not `http://127.0.0.1:6379`) — a single `_probe_client()` factory + pre-request initial vetting + `RedirectHopRejected` convergence; verified with real egress: public HLS passes while `127.0.0.1:6379`/`169.254.169.254`/`10.0.0.5`/CGNAT are all rejected (including the last-resort candidate).
- **GUI label clipping on both sides and the DPI freeze (two batches, same root cause)**: `_bind_adaptive_wraplength` adaptive wrapping eradicates pack's symmetric clipping (5 occurrences fixed together); then the synchronous write inside `<Configure>` was replaced with "true debounce (settle only after the storm stays quiet for 120 ms) + hysteresis (skip writes when |Δ| ≤ max(12, 2%)) + TclError race guarding", eradicating the event-storm mutual pumping with CTk's DPI rescaling (whole-window freeze / flickering text / partially rendered elements).
- **Web panel mobile adaptation**: two-row top bar (fixed 56px → min-height + wrap at ≤768px), `viewport-fit=cover` + `env(safe-area-inset-*)` safe-area handling, `100dvh` dynamic viewport, and in-panel horizontal scrolling for the three data tables on narrow screens — eliminating the top-bar clipping and whole-page horizontal scrolling seen on iPhone 16 Pro Max / Pixel 10.
- **i18n blind-spot backfill**: user-visible text in the extractor's three blind spots (`print_colored` / `messagebox` / push bodies) all routed through `tr()`, 16 new entries registered across the four language catalogs and the `.mo` recompiled; zh_TW also deduplicated 7 duplicate keys, restoring strict key-set parity across the four catalogs (808 keys; one more entry registered on 10-01 for the h265 zero-source observability warning, 809 keys in the final state).

**⚠️ Breaking Changes / Behavior Changes**
- **The `fastapi` / `pydantic` runtime dependencies are removed** (details under "Dependency Changes" below): the panel's 24 routes, request/response shapes, security headers, and auth middleware behave identically; the internal request models are read via `.parse()`, with no API-surface change for external consumers. Only custom deployments importing these two packages outside the panel need adjusting.

**📦 Dependency Changes**
- **Runtime dependencies 23 → 21**: `fastapi>=0.140.0` and `pydantic>=2.13.4` removed; the package-name sets of `requirements.txt` and `pyproject.toml [project.dependencies]` are equal item by item (regression lock `tests/test_regression_2026_09_22_gates.py`), and `uv.lock` plus `DouyinLiveRecorder.egg-info` were rebuilt via `scripts/sync_metadata.py` (zero residue of either package).
- **`urllib3` declared floor 2.7.0 → 2.8.0**: the CI `deps-audit` "floor re-check" measured the old floor itself inside the affected band of CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689 (all fixed in 2.8.0); `requirements.txt` and `pyproject.toml [project.dependencies]` raised in sync (still 21 entries, package-name sets unchanged), with `uv.lock` and `DouyinLiveRecorder.egg-info` rebuilt via `sync_metadata.py`; the local venv already had 2.8.0 installed, so the resolved set is unchanged.
- **CI typecheck job now installs pinned `pytest==9.1.1`**: type checking over `tests/` is no longer half-blind (fixtures and the `NoReturn` of `pytest.fail()` are visible again).
- **Doc-level dependency-notation fix**: the dev-dependency pip line in both READMEs went from 5 packages (missing `pytest-cov`; an environment set up that way cannot run the coverage gate) to the canonical `pip install .[dev]` (pointing at the six entries of `[project.optional-dependencies].dev`).

**🛠️ Repo Maintenance & Docs**
- **Two full code-review rounds**: `docs/worklog/CODE_REVIEW_2026-09-29_2.md` (all 31 numbered items landed as P0+P1+P2) and the root-level `CODE_REVIEW_2026-09-30.md` (18 per-file deep-audit batches over ≈42,000 lines of production code + 56,200 lines of tests — Critical 2 / Medium 51 / Minor 160, with Mimosa deep-scan cross evidence); P0 is fixed, P1/P2 await later batches, and a dedicated "twin back-port" project is suggested for standalone.
- **Multiple reconciliations and a slim-down of `AGENTS.md`**: 7 fact syncs (stale readings of test counts / symbol names / call-site counts corrected) + a fidelity-preserving slim-down in 19 places (110,287 → 108,469 bytes; the gate-command bash block and every section heading byte-identical; the three doc locks unchanged at 73 passed / 1 skipped) plus three gate-wording corrections (quality gates now defer to the "Formatting commands (single gate baseline)" section; `pyright`/Pylance positioning clarified as non-gates; a new premise that local gate results extrapolate only when tool versions match the `ci.yml` pinned values); a stop-hook credential-risk flag was assessed as a false positive and the red-line wording made explicit per the suggestion.
- **Metadata reconciliation**: 15 files fully checked against `pyproject.toml` (version 4.4.0 / 21 dependencies / image & service names / ports & mounts / packaging parameters), with the only drift being the README dev-deps line above; the two `filterwarnings` comment attributions in `pyproject` were corrected from "fastapi testclient" to the `starlette.testclient` body.
- **Two test-side fixes (no production-code changes)**: the 4 false-reds of `test_gui_stop_exit_singleflight` on Linux CI came from the test double stubbing only the win32 signal branch (POSIX uses `os.kill`) — after adding the POSIX-side stub per the "stdlib stand-ins go through the tested module's namespace" rule, faking `sys.platform` locally reproduces the POSIX path with all 25 criteria of the four scenarios passing; and the wall-clock margin of the `test_notify` timeout case is now derived from the production constants (`taskkill /F /PID` measured at a steady 2.5~3.1s, so the 1s timeout plus ~3s landing exactly on the hand-tuned 4.0s margin is no longer a machine-state false alarm).

**🧪 Tests & Verification**
- Full `pytest` **3721 passed / 14 skipped / 0 failed / 0 warnings** (measured locally on 2026-10-01, final state; all 14 skips are platform-conditional: missing symlink privileges, Windows chmod read-only-bit semantics, the POSIX-shaped SIGKILL case, h2 installed so the missing-dependency branch is unreachable, etc.).
- Coverage: all 44 modules above threshold (84.9% overall, per coverage.json); basedpyright 0 errors / 0 warnings; `run_gates.py` 8/8 green.
- Live verification (09-29 ~ 09-30): Douyin PASS (59 messages / SRT 4,518 bytes), Bilibili PASS (9 / 678 bytes), Huya WARN (connected, no danmaku in that window), Twitch WARN, Douyu SKIP(room offline, parsing healthy), TikTok SKIP(no egress network); standalone `--dry-run` PASS on a real live Huya room (incremental verification of S-01/S-02); the public-HLS segment probe passes while all four classes of internal targets are rejected. Hand-back actions (GUI visual checks, Douyu/TikTok re-runs on live rooms, bundle-size re-measurement) are in [CODE_WIKI.md](CODE_WIKI.md).
- Live verification (10-01, a live douyin HEVC-origin room "央视网快看"): all three states PASS — HLS off + ts save format → the h265 FLV primary was admitted and selected (codec=h265 probed for real); HLS off + FLV → fell onto the h264 origin fallback (codec=h264); fallback stripped → None with the new zero-source observability warning fired for real.

### v4.3.0 (2026-09-16 ~ 2026-09-27) — P0 fix for 100% recording failure on ffmpeg master builds (`-thread_queue_size` narrowed upstream to an output-only option) / boolean config parsing unified (`true/false` silently broke 8 settings and blocked 9 overseas platforms) / two full code-review rounds (62 + 106 graded fixes) / supply-chain hardening (official hashes first + GPG verification + Lanzou fallback removed) / four release-chain faults fixed (**the lite package shipped to users briefly never existed**) / Apple Silicon ffmpeg PATH yield policy / per-room log correlation field & `/health` probe endpoint / build artifact size −21.6% / coverage 73.28% → 82.03% (dedicated push) and 83.91% (final, 09-27)

> This release (v4.3.0, 2026-09-16 ~ 09-27) is a convergence cycle focused on **correctness and supply-chain safety**. Four items matter most: ① **P0**: ffmpeg master builds narrowed `-thread_queue_size` to an output-only option, while we still placed it before `-i` — so on such a build **every single recording exited with `-22 (EINVAL)` and produced zero bytes**; ② **boolean config parsing unified**: writing `true/false` in `config.ini` used to be treated as invalid and **silently** fall back to a hardcoded default (no warning, no log), which measurably drifted the effective value of 8 settings — the worst one leaving 9 overseas platforms 100% unable to record; it is now unified so that `是/否`, `true/false`, `1/0`, `yes/no` and `on/off` are all equivalent; ③ **two full code-review rounds** (62 items on 09-19: 12 severe / 22 medium / 28 minor; 106 items from `CODE_REVIEW_2026-09-20` on 09-21: 10 severe / 70 medium / 26 minor) cleared a batch of silent-failure modes at once — SSRF, panel takeover, credentials written to disk in plaintext, danmaku thread livelock, and more; ④ **four release-chain faults** (09-26 ~ 09-27), the last of which is user-visible: `make_zip` finished with `Path.with_suffix(".zip")` while the version itself contains a dot, so lite and full resolved to the same attachment name and the second call truncated the first in place — **one Release ended up with a single attachment carrying neither platform nor variant label, and the lite build was never distributed at all**. **There are breaking changes** — see the dedicated section below. Full root-cause analysis and verification are in [CODE_WIKI.md](CODE_WIKI.md).

**🐛 Fixes**
- **P0: 100% recording failure on ffmpeg master builds**: `-thread_queue_size` was narrowed upstream to a muxer-only option; placed before `-i`, ffmpeg exits with `Option thread_queue_size … cannot be applied to input url … Error opening input files: Invalid argument` (return code -22). Unrelated to room / platform / CDN — on that build *every* recording fails.
- **P0: boolean config parsing unified**: the scattered parsers (previously `!= "否"`, `== "是"`, and the front-end `=== '是'`) are unified into `src/config_bool.py::parse_config_bool`; as a result `global_proxy` is no longer wrongly forced to False, restoring resolution for TikTok / SOOP / PandaTV / WinkTV / Flextv / PopkonTV / Twitch / LiveMe / Faceit and other overseas platforms.
- **Full code review, 62 items (09-19)**: GUI silent hang on empty config; one extra comma in a config line permanently skipping every room after it; missing bounds checks in Tars decoding causing a danmaku-thread livelock; Douyu danmaku silently filtered out (regression of an earlier fix); a hung ffmpeg permanently holding a concurrency slot; zero-byte output judged as success and cancelling circuit-breaker backoff; `config.ini` (with credentials) copied in plaintext into `backup_config/`; the Web panel being take-over-able or lockable through its own API; zero protocol validation on room URLs → blind SSRF; the masking blacklist missing every "credential embedded in the value" URL-type key; zero integrity verification in the install/packaging chain.
- **`CODE_REVIEW_2026-09-20` landed in full, 106 items (09-21)**: the concurrency semaphore treating "available permits" as capacity (the network concurrency cap effectively out of control); `PUT /api/rooms` bypassing room-entry validation; intranet blocking via a string-prefix blacklist (5 of 7 probe addresses passed); panel auth being hot-disabled by a single write request, with case variants bypassing the password hash / self-lock guard / token revocation; deleting a room on CRLF configs failing permanently while still reporting `{"ok": true}`; Shopee site-suffix parsing producing an illegal domain; fallback decorators mismatched with return contracts (failures disguised as "not live"); the recording watchdog using the wrong baseline for its "stalled" verdict (the real tolerance window was only 30 seconds); the `only_flv` branch missing `flv_url`, causing the time-subtitle thread to spin and write to disk in a loop; an empty runtime-binary hash pinning table in the release chain.
- **Release chain & supply chain**: macOS arm64 full packages **silently shipped without ffmpeg** (no such artifact upstream — the download point is fixed); the Windows runtime ffmpeg primary source verified healthy by measurement (gyan.dev ships a `.sha256` document that cross-confirms the release-time pin); official SHA256 pins backfilled for 6 of 10 slots.
- **Test hygiene (09-23)**: one cross-file patch leak (a missing `undo()`) let later tests in the same session issue real network requests, producing 11 "red in full run, green alone" false failures out of 13.
- **P0: build script polluting the test session (09-23)**: the bare `reconfigure` in `build_exe._ensure_utf8_streams()` broke pytest's fd capture, surfacing as a "GUI failed to start" dialog plus unrelated tests marked FAILED/ERROR (all nine CI jobs run ubuntu and stayed green — never reproduced).
- **Four release-chain faults (09-26 ~ 09-27, affecting shipped artifacts)**: (1) all eight slots of the pinning table had been turned into the "official signature" marker, so `check_runtime_pins.py --strict` exited rc=1 in the prepare job and releases never even reached the build (hashes re-pinned from the official channels); (2) the Linux bundled-ffmpeg pins came from BtbN's rolling `latest` alias, and upstream republishing the same asset name the same day changed its digest — the release turned red on the SHA256 check that very day (now pinned to the **immutable month-end release tag** `autobuild-2026-08-31-13-27`, where URL and digest are both frozen); (3) **the lite package was never actually distributed**: `make_zip` closed with `Path.with_suffix(".zip")` while the version `4.3.0` itself contains a dot, so `DouyinLiveRecorder-v4.3.0-windows-amd64-lite` and `-full` truncated to the same `DouyinLiveRecorder-v4.3.zip`, the second call truncating the first in place with no error — the Release kept one attachment with neither platform nor variant label; (4) when any platform build failed, the pre-created Release record stayed in the repository as an **empty Release**.
- **Metadata second-copy drift (09-27)**: `DouyinLiveRecorder.egg-info/PKG-INFO` still carried `Requires-Dist: h2` at the old floor `>=4.3.0` (the manifests had been raised to `>=4.4.1` but never propagated into the metadata), and its embedded README lacked the whole v4.3.0 changelog section; rebuilt and corrected.

**✨ New Features / Improvements**
- **Per-room log correlation field `extra[room]`**: `src/logger.py` gains `ROOM_FIELD` / `set_room_context()` / `get_room_context()` (internal `ContextVar` + patcher), so interleaved multi-room logs can be sliced per room.
- **Web panel `/health` probe endpoint**: `GET /health` returns `{"status": "ok", "version": …}`, and the built-in smoke tool `scripts/smoke_test.py` is wired into CI as a real HTTP probe.
- **W6: Apple Silicon ffmpeg PATH yield policy**: on darwin + arm64 with another native ffmpeg already on `PATH`, the bundled x86_64 build (which only runs through Rosetta translation) is no longer unconditionally prepended; yielding requires all five criteria to hold. Other platforms are unchanged, byte for byte.
- **Runtime binary integrity**: `build_exe.py` gains the `_PINNED_RUNTIME_SHA256` table plus `--require-pinned`, backed by `scripts/check_runtime_pins.py` (structure mode in the local gate / `--strict` in the release prepare job / `--emit-env` for CI injection); first-time runtime installs now prefer officially published hashes, and release builds add GPG verification plus a full-package self-check.
- **Build artifact size optimization (09-24)**: excluded runtime-unreachable modules (`PIL._avif`, `pydantic.v1.mypy` which drags in all of mypy, uvicorn's optional implementations, `i18n/*.po`, …) plus zip `compresslevel=9` — the lite artifact went from **82.77MB to 64.88MB (−21.6%)** and the zip from **54.84MB to 42.19MB (−23.1%)**, with a new measurement script `scripts/report_bundle_size.py`.
- **Five new gates**: `PYTHONUTF8=1` + "any warning fails" (kills the mode where isort silently skips files with Chinese comments under a GBK locale and still exits 0); a decorator-contract AST lock; a test-hygiene AST lock (R1–R4 / R6 "manual MonkeyPatch must pair with undo"); a front-end catalog consistency lock (`data-i18n*` keys compared one-by-one against the four embedded catalogs); a `deps-audit` job and hard failure when coverage data is missing.
- **Dynamic concurrency floor lowered**: `ConcurrencyScheduler`'s `min_capacity` default changed from 8 to 1.
- **Bundled-ffmpeg upstreams and satisfaction tiers (09-26 ~ 09-27)**: both Linux architectures moved to BtbN's GPL-complete assets, keyed per `<os>-<arch>` runtime key, with the source endpoint fixed to the immutable month-end tag; the two macOS slots use the **official GPG signature tier** (evermeet publishes no SHA256, so signature verification is that slot's only criterion, with the full 40-hex-digit master fingerprint pinned out of band). Hash pinning and signature verification are two non-interchangeable lines of defense.
- **`release-guard`: never publish an incomplete release (09-27)**: when a build is not fully green, the empty/partial pre-created Release is reclaimed with `gh release delete` (tags are kept by default, so a re-run republishes cleanly) and a `::warning::` is left behind; `fail_on_unmatched_files` on the upload step is deliberately not relaxed, because that error is the only visible signal of a missing artifact.
- **Two new checks around `--dual` artifacts (09-27)**: before packaging, stale `DouyinLiveRecorder-v*.zip` leftovers under `dist/` are pruned (so a reused build workspace cannot sweep last run's package into this run's attachment set); after packaging, the lite and full artifact paths must differ **and** both must exist on disk, otherwise the build aborts on the spot.
- **The CI typecheck job now installs a pinned `pytest==9.1.1` (09-26)**: it previously installed only `requirements.txt + mypy`, so every `pytest.*` reference under `tests/` was checked as `Any` — fixtures and the `NoReturn` of `pytest.fail()` were effectively invisible, leaving the gate half blind.
- **Documentation size pass (09-27, zero information deleted)**: 73 historical "Files involved (classified by module)" inventories were moved verbatim out of the `CODE_WIKI*.md` changelog into `docs/agent-reference/changelog-file-inventories{,-en}.md` (wiki body −12.3% zh / −5.0% EN), and 109 (zh) / 181 (EN) table cells that an earlier bulk compression had silently truncated with `…` were restored from the pre-compression snapshot. `README.md` / `README_EN.md` are deliberately left uncompressed — user-facing release notes are not degraded.

**⚠️ Breaking Changes / Behavior Changes**
- **Lanzou ffmpeg fallback removed on Windows at runtime**: automatic installation now has a single primary source (measurement showed that direct link serves a JS-challenge HTML page with all companion hash documents returning 404, i.e. unusable); when automatic installation fails, an explicit manual-install guide is emitted instead. **Windows users who relied on that fallback must place the binary themselves, following the "manual ffmpeg installation on Windows" section of this README.**
- **The bundled ffmpeg directory is no longer unconditionally prepended on Apple Silicon**: users who installed a native arm64 ffmpeg (e.g. via Homebrew) will now have recording subprocesses use that system copy instead (its version / build options may differ).
- **Dynamic concurrency floor 8 → 1**: the network concurrency allowance is no longer lifted to 8 under low load.
- **Boolean config semantics changed**: keys previously written as `true/false`, `1/0`, … were **silently ignored** (falling back to a default); after upgrading they take effect literally — if your config depended on the old wrong fallback value, the effective value changes. Please re-check the 8 affected settings after upgrading.
- **Runtime dependencies 20 → 23**: newly declared explicitly — `urllib3>=2.7.0` (CVE-2026-44431), `h2>=4.4.1` (PYSEC-2026-3628) and `socksio>=1.0.0` (httpx runtime deps for HTTP/2 and SOCKS); `starlette` lower bound `>=0.49.1` → **`>=1.3.1`** (CVE-2026-48710 plus PYSEC-2026-2280/2281/248/249); `protobuf` keeps its `<8` cap (gencode compatibility guardrail).
- **Build time**: the `build-release.yml` prepare job now blocks unpinned runtime binaries via `check_runtime_pins.py --strict`.
- **`build_exe.py --dual --no-zip` now fails fast**: the `--dual` branch never read `no_zip`, so an explicitly typed `--no-zip` was silently ignored while both large zips were still produced. Contradictory flag combinations now abort instead of letting one of the two flags do nothing.
- **Release attachments regain platform and variant labels — please use the new attachments**: after a re-publish, Windows / Linux / macOS attachments are named `DouyinLiveRecorder-v4.3.0-<os>-<arch>-lite.zip` and `-full.zip`. Any earlier attachment shaped like `DouyinLiveRecorder-v4.3.zip` (no platform segment, no variant segment) is a defective artifact of the bug above: its content was the full package, and the lite package did not exist.
- **Linux full packages grow substantially**: with the BtbN switch, the bundled ffmpeg asset (uncompressed) is about 126.6 MB for linux64 and 108.8 MB for linuxarm64, versus roughly 41.9 MB for the previous johnvansickle amd64 static build. Choose the `lite` package to keep the download small (binaries are then fetched on first run).

**🛠️ Repo Maintenance & Quality Gates**
- **Test coverage push (09-21)**: `src/` coverage **73.28% → 82.03%** (tests only, zero product-code changes), plus a layered allowlist (table empty by default, fails when it expires).
- **Four-language catalogs kept complete and verified**: 594 → **780 entries**, with all four catalogs matching key by key and no empty values; the `.mo` is recompiled whenever they change.
- **Metadata single-source sync**: `AGENTS.md` dependency count and lower-bound wording, the `CODE_WIKI*.md` dependency tables (16 → 23 entries), `DouyinLiveRecorder.egg-info` regenerated, `_probe_*.py` added to `.dockerignore`, and `[Cookie] ttwid` added to `config/config.ini`.
- **Type stubs & comment governance**: 7 `.pyi` files under `typings/execjs/` got complete annotations and two abstract-base stubs dropped `six` (switched to `metaclass=ABCMeta`); multiple repo-wide comment-refinement batches (including one 68-file round), and `scripts/check_annotations.py` gained a third blind spot (newline form).
- **Leftovers of deleted modules cleaned up**: `src/weverse_auth.py` / `tests/test_weverse_auth.py` (deleted 2026-09-23) were removed from structure trees and dependency notes, and their 3 orphan translations were dropped from the four catalogs.
- **Cross-file consistency sync (09-27)**: `requirements.txt` vs `pyproject.toml [project.dependencies]` — 23 vs 23 package-name sets equal, with all three extras groups matching; `python_build = 3.14` and `node_version = 24` identical in `ci.yml` and `build-release.yml`; the 14 local tool directories and 6 runtime artifact directories present without gaps across `.gitignore`, `.dockerignore`, every pyproject tool exclude and `.coveragerc-concurrency`. The only edit this round was completing the truncated inline comment on `websockets>=14.0` (no specifier changed).
- **`AGENTS.md` size pass (09-27)**: readings that already existed in `docs/agent-reference/measured-evidence.md` were replaced by pointers and three genuine duplications merged, taking the file from 97,034 to 95,715 B (-1.4%); a token-preservation audit proves no constraint was lost (0 losses among test names, error codes, and constant / environment-variable names).

**🧪 Tests & Verification**
- Full `pytest`: **3240 passed / 14 skipped / 0 failed** (two measured runs on 09-27, one of them with `--cov=src`). The case previously reported as permanently red on this Windows host, `test_symlinked_system_hit_inside_bundled_dir_keeps_prepending`, is now skipped explicitly by host capability (`symlink not permitted on this host`) and is counted among those 14 skips rather than being a failure.
- `black --check .` **169 files unchanged**; `isort --check-only .` no reordering; parameterless `mypy` **158 files, 0 issues** (`mypy --platform linux` likewise 0); `basedpyright` (standard) **0 errors / 0 warnings / 0 notes**.
- Coverage: total `src/` coverage **83.91%**, and `scripts/check_coverage.py` reports **all 42 modules meeting their thresholds** (`src/proto/douyin_pb2.py` is a protoc artifact and explicitly exempt).
- `node --test tests/frontend/*.mjs` green; `scripts/check_version.py` and `scripts/check_runtime_pins.py` both rc=0; `scripts/compile_po.py --check` reports `zh_CN.mo` in sync with the `.po` (781 entries).

### v4.2.0 (2026-09-12 ~ 2026-09-15) — full code-review fix (~120 items: security/concurrency/platform) + Douyu "SRT only, no video" root cause & HLS segment-layer false-green probe + source-selection hardening + start_record command-construction / platform-dispatch single-source-of-truth refactor + repo metadata sync & four-language catalog consistency fix + mypy gate expansion (scope pushed down to `[tool.mypy].files`) with 6 type-defect fixes + Linux CI read-only test fix

> This release (v4.2.0, 2026-09-12 ~ 09-15) is a comprehensive fix-and-hardening cycle spanning security, concurrency, and the platform layer plus quality gates. Core fixes: ① root-caused and fixed the "only danmaku SRT produced, no video file" issue on Douyu and similar platforms — the HLS playlist layer always returns 200, but the edge node serving the media segments returns 404 for all of them, so ffmpeg pulls zero media segments and produces zero bytes; the danmaku pipeline depends only on `room_id` and is decoupled from the video pipeline, so the SRT is still written. Added the HLS segment-layer probe `_probe_hls_segment` (decoupling "playlist 200" from "recordable") and three directions of source-selection hardening (config fallback / observability / same-origin FLV fallback). ② Collapsed the five inline ffmpeg `command=[]` lists in `start_record` into a single source of truth and replaced the 53-level `elif` chain in platform dispatch with a dispatch table, with zero behavioral difference (byte-level golden snapshots + item-by-item dispatch snapshots). ③ Closed `CODE_REVIEW_FIX_1` (F-01~F-25, 22 landed + 3 deferred) and the 09-12 full code review (~120 items: SHA256 pinning, atomic writes, zip-bomb protection, singleflight concurrency, Douyu packet-boundary / Bilibili watchdog / Shopee fixes). ④ Synced repo metadata (pyproject exclude dirs / .gitignore / .dockerignore / AGENTS.md) from a single source of truth, and fixed 21 entries in en_GB mistakenly filled with Traditional Chinese, re-aligning the four-language catalogs to 594 entries each. ⑤ The mypy gate scope was pushed down to a single source of truth in `pyproject.toml [tool.mypy].files` (`src/` → the whole codebase, including root entry points / `build_exe.py` / `scripts` / `tests`), fixing 6 long-escaping type defects — among them the `gui.py` UI finalization path after a subprocess exits naturally, which **always raised `NameError`** (apart from that finalization path there is no functional behavior change); also fixed a Linux-CI "read-only config" test that stopped working because atomic-write `os.replace` only checks the directory permission. **No breaking changes** (all runtime semantics preserved). See [CODE_WIKI.md](CODE_WIKI.md) for full root-cause analysis and verification.

**🐛 Fixes**
- **Douyu "SRT only, no video" root cause + HLS segment-layer false-green probe**: the HLS playlist layer always returns 200, but the media segments land on another edge node and all return 404 → ffmpeg pulls zero media segments and produces zero bytes; the danmaku pipeline depends only on `room_id` and is decoupled from the video pipeline, so the SRT is still written. Added `_probe_hls_segment()` (playlist GET → follow master variant → send `Range bytes=0-0` probe to the **last segment**; segment 4xx/5xx explicit rejection → unreachable "false green", 200/206 → reachable; conservatively pass when no segment can be parsed), wired into `_validate_stream_url` to decouple "playlist 200" from "recordable".
- **Source-selection hardening (config fallback / observability / same-origin candidate)**: `_hls_selection_config()` (reads `hls_collection_enabled`/`hls_collection_exclude_platforms` via `getattr(main, ..., default)`, defaults reachable, tolerates comma strings, no longer `AttributeError`-crashes on missing/type errors); `_same_origin_flv()` (matches by path before `?`, treats `.m3u8`↔`.flv` as equivalent, finds the same-token FLV as fallback when all HLS segments die); `_log_source_choice()` (single-line "source-selection conclusion" log covering fallback/hit/no-usable-source paths).
- **Full code review (09-12, ~120 items)**: H-1 SHA256 pinning (`ffmpeg_install`/`node_install` `_sha256_of_file`/`_check_or_record_zip_sha256`, Lanzou `FFMPEG_LANZOU_SHA256`); C-1 Web blacklist bypass (`req.key.strip()` + `_DANGEROUS_CONFIG_KEYS_FOLDED`); zip-bomb protection (single file 4GB / cumulative 8GB / 100x ratio); H-2 singleflight isolating locks held across `await` + GUI 6.2 fixes (SMTP header injection `_reject_smtp_newline`, session id, quality-table dedup); URL-scheme whitelist `is_safe_http_url`, JS/subprocess via `run_js_async`/`run_node_script_async`; C-2 Douyu packet boundary `offset+=full_len+4`; C-3 only_fans=False; H-4 Bilibili watchdog `spawn_danmaku_task(self._auth_watchdog(self._ws))`; H-5 Shopee clear-path finally `_not_record_prefix`; H-3 `websockets>=14.0`; H-6 atomic writes (`config_io._atomic_write_text` + `web_config._config_write_lock`); standalone two-stage termination (terminate→wait(3s)→kill); 6 ffmpeg paths add `record_finished=True` to trigger the 30s quick check; `data={}` treated as a valid body.
- **CODE_REVIEW_FIX_1 batch (F-01~F-25)**: main.py F-02 removed dead imports (`converts_m4a`/`segment_video` functions kept in `video_postprocess.py`), F-03 direct-download stream `finally` only cleans zero-byte residue; gui.py F-04~F-09 session-id closure / quality-table dedup / crash sink forbids `import src` / local atomic write (no `import src.config_io` to avoid triggering GUI-process main init); msg_push.py F-24 guarded ntfy real push; spider.py F-10 `_read_tiktok_guest_cookie` must be inserted above `@trace_error_decorator` (inserting code between "@decorator+def" hijacks the decorator), F-11 multi-arg print→logger concat, F-19 ab_sign random by default; web_config.py F-23 inline-comment quote priority + atomic write; utils.py F-16 `read_ini_value` no write-back + F-25 JS-signature-script hash pinning (`_JS_SHA256_EXPECTED`, 7 scripts, warn by default, `DLR_JS_STRICT_HASH=1` rejects).
- **F-13 Douyin signature kept unencoded**: cross-checked upstream `dart_simple_live` and confirmed it concatenates directly without `encodeComponent`, matching this repo byte-for-byte; blindly adding `quote()` would make this client the only fingerprint outlier on the whole network. Pinned the "concatenate as-is, no percent-encoding" contract with `tests/test_douyin_signature_encoding.py` (4 cases).
- **F-12 sync_http SSL scope narrowed**: `CERT_NONE` context and opener changed from import-time globals to lazy construction; added `sync_req(..., ssl_verify=None)` for per-request override (propagated through both urllib and requests paths). Corrected the original risk description — all `sync_req` call sites live in `src/spider.py`, and the production path has no `set_ssl_verify(False)`, so the CERT_NONE path is unreachable in production.
- **check_annotations violation fixed**: the triple-quoted docstring on `class _Cap:` in `tests/test_start_record_command_golden.py` was changed to a `#` line comment (conforming to the "no docstring" rule); also fixed a `main.py` monitor-only branch that wrongly wrote `main.recording_enabled` (module-level `main` is the entry function, not the module object, so it always raised `AttributeError`).
- **mypy gate expansion + 6 type-defect fixes (09-15)**: triggered by 3 errors from the CI typecheck, which revealed that the gate only covered `src/` — root entry points and `tests/` had never been checked. Fixed: `src/platforms/huya.py` gained the missing `import i18n` (the `except` branch called `i18n.tr()` without importing it, so a frame-parse exception raised `NameError` and masked the real cause); `src/async_http.py` `_get_client` now stores the reused instance directly inside the critical section so the type narrows; `src/spider.py` liveme `lm_s_sign` gained `str()` (`sign_data` is `dict[str, object]`); 3 in `gui.py` — added `from src.logger import child_process_env, logger`, `_has_unsaved_config_edits` now returns `bool(...)`, and the **UI finalization path after a subprocess exits naturally always raised `NameError`** (`session_id` in `_process_ended(session_id)` was undefined). The fix did not simply drop the parameter (that would lose the "discard late callbacks from an old session" protection): the log-queue end sentinel was changed from a bare `None` to `(session_id,)` carrying the session id, which the UI thread hands to `_process_ended` for validation.
- **Linux CI read-only test fix (09-15, tests & docs only)**: `test_read_config_value_missing_key_readonly_ok` used `cfg.chmod(0o444)` to make the file "unwritable", but the write-back in `read_config_value` had been changed to `_atomic_write_text` (temp file in the same dir + `os.replace`) — `os.replace` only checks the write permission of the **containing directory**, not the target file's permission bits (and root bypasses them entirely), so on Linux the write-back still succeeded; on Windows the read-only attribute makes `replace` fail outright, hence "passes locally on Windows, fails on Linux CI". Now `monkeypatch.setattr(config_io.os, "replace", _deny_replace)` raises `PermissionError` only for the target config path and passes everything else through, reproducing cross-platform the "write-back rejected → warning logged + default returned + original file untouched" fallback branch. `AGENTS.md` gained a rule that read-only tests must not rely on `chmod` alone, distinguishing the two write-back paths `config_io` (atomic) and `utils.update_config` (direct).

**✨ New Features / Improvements**
- **start_record command construction & platform dispatch single source of truth (F-01)**: the five inline `command=[]` lists were collapsed into module-level `_build_ffmpeg_output_args` / `_build_ffmpeg_input_args` / `_build_record_output_path` / `_ffmpeg_network_tuning`, with all container mapping going through `SEGMENT_FORMAT_BY_SUFFIX` (no raw literals); the 53-level `elif` chain in `_resolve_platform_stream` became the `_PLATFORM_RESOLVERS` dispatch table (one `_resolve_<host>()` per platform, sharing `_PlatformResolveContext`), so adding a platform = append a handler + one table entry. Also fixed two behavior drifts (TS non-segmented unconditionally converting to MP4; the "preparing to record" hint printing the non-segmented filename).
- **JS-signature-script hash pinning (F-25)**: `get_compiled_js` reads raw bytes and compares against the `_JS_SHA256_EXPECTED` baseline, warning by default and rejecting execution when `DLR_JS_STRICT_HASH=1`, closing the runtime surface for tampered signature scripts.
- **F-14 protobuf compatibility guardrail**: this environment has no protoc, so `douyin_pb2.py` is not regenerated (generated file is DO NOT EDIT); instead a CI-fronted `tests/test_proto_runtime_compat.py` asserts "declared range has an upper bound / runtime satisfies the range / runtime not older than gencode / importable and PushFrame round-trips", turning red immediately on 8.x and prompting a same-generation protoc regen first.
- **mypy gate scope pushed down to a single source of truth (09-15)**: `pyproject.toml [tool.mypy].files` is now pinned to `src` + root entry points (main / gui / web / i18n / msg_push) + `build_exe.py` + `scripts` + `tests`; the `ci.yml` typecheck changed from `mypy src/` to a **parameterless `mypy`**, so local and CI run the same command (explicit arguments override `files` and are only for narrowing during debugging — the gate verdict comes from the parameterless run). 15 drifted annotations in `tests/` were filled in as well (12 missing annotations in `test_start_record_command_golden.py`, generator-fixture return types `Iterator`→`Generator`, and `type: ignore` codes that must suppress both mypy `assignment` and basedpyright `method-assign`).

**🛠️ Repo Maintenance & Quality Gates**
- **pyproject exclude dirs single-source completion**: `logs`/`backup_config` were previously only in some tools — now completed across black `.exclude`, isort `extend_skip`, mypy `exclude`, basedpyright `exclude`, and coverage `omit`, all with a unified "runtime-product dirs (maintained with .gitignore/.dockerignore)" comment; `.coveragerc-concurrency`'s omit aligned to match.
- **.gitignore / .dockerignore globbing**: removed per-filename entries for now-missing files like `PERF_REVIEW_2026-08-28.md` in favor of three glob groups `PERF_REVIEW_*.md`/`CODE_REVIEW_*.md`/`DIAGNOSIS_*.md`; .dockerignore gained `*.jsonl`. AGENTS.md gained the `.gitignore`/`.dockerignore` entries and the `logs/`/`downloads/`/`backup_config/` runtime dirs plus the root doc `CODE_REVIEW_FIX_1.md`.
- **Four-language catalog consistency fix**: fixed 21 en_GB entries whose values were mistakenly Traditional Chinese (7 danmaku-parse errors + 14 ffmpeg/Node install SHA256 prompts), re-filled with British English per the "en_GB differs from en_US only in spelling" rule; verified all four catalogs `zh_CN(.mo)`/`en_US`/`en_GB`/`zh_TW` at **594 entries** each with zero key-set differences, no Chinese residue in en_US/en_GB, no untranslated entries in zh_TW; `zh_CN.mo` recompiled (595 entries), `scripts/compile_po.py --check` passes byte-level sync.
- **Repo metadata sync**: `AGENTS.md` / `docker-compose.yaml` example version `4.1.0`→`4.2.0`; `config/config.ini` gained `tiktok_guest_cookie = ` under `[Cookie]` (F-10 config-override slot); requirements.txt and pyproject dependencies verified identical line-by-line (incl. `protobuf>=6.31.1,<8` upper bound and `websockets>=14.0`).

**🧪 Tests & Verification**
- Full `pytest` **974 passed / 2 skipped / 0 failed** (climbing 909→929→944→974); frontend `node --test tests/frontend/*.mjs` 6 passed; `tests/test_stream_select.py` gained 15 cases (segment probe + hardening), `tests/test_platform_dispatch.py` 16 cases, `test_douyin_signature_encoding.py` 4 cases, golden-snapshot `test_start_record_command_golden.py` 20 cases.
- `black --check --line-length 120 --target-version py314 .` 134 files green; `isort --check-only` green; `scripts/check_annotations.py` 0 violations (avg density 22.1%); `scripts/compile_po.py --check` in sync; `scripts/extract_i18n_strings.py` 0 runtime-missing; `scripts/check_version.py` PASS; mypy/basedpyright 0 error on changed files.
- After the 09-15 gate expansion: parameterless `mypy` **115 files, 0 issues** (covering src + root entry points + `build_exe.py` + `scripts` + `tests`); `pytest -q` still **974 passed / 2 skipped**; `pytest tests/test_config_io_readonly.py` 15 passed (consistent with 976 collected in CI); Linux CI recovered from 1 failed / 975 passed to fully green.

### v4.1.0 (2026-09-10 ~ 2026-09-11) — P0 fixes for missing ffmpeg `-reconnect*` values and HLS infinite reconnect (live recording yields subtitles but no video) / 28 code-review fixes / 8 decision + 4 machine-validation items / migration of 242 parameterized logs to i18n.tr / Web-panel narrow-viewport fix / four-language catalog completion

> This release (v4.1.0, 2026-09-10 ~ 09-11) fixes two P0 defects in the recording pipeline: ① moving the ffmpeg `-reconnect*` options before `-i` dropped the boolean value `1`, so real recording failed at input open with exit code -22; ② `-reconnect_at_eof 1` with an HLS(m3u8) input reconnects **infinitely at the playlist layer**, so the hls demuxer never pulls a single media segment — live recording looked like "only the danmaku SRT was produced, no video file". Also shipped 28 code-review fixes, the remaining 8 production-decision + 4 machine-validation items (hls.js pinning / TLS split-stream / audio-container alignment / `gui_legacy.py` removal / danmaku SRT off-loaded off the event loop / i18n `tr()` API, etc.), a full migration of 242 parameterized logs from f-string to `i18n.tr`, the Web-panel narrow-viewport fix, and an eight-file metadata sync plus four-language catalog completion (521 → 539 → 544 keys). **No breaking changes** (all recording/danmaku/network/push runtime semantics preserved). See [CODE_WIKI.md](CODE_WIKI.md) for full root-cause analysis and verification.

**🐛 Fixes**
- **P0 missing ffmpeg `-reconnect*` values → recording fails at startup with -22 (EINVAL)**: when the 09-10 review refactor moved `-reconnect_delay_max 60 / -reconnect_streamed / -reconnect_at_eof` from after `-i` to before it, the boolean values `1` of the last two options were dropped, so ffmpeg parsed the next option name as the value (`Unable to parse ... as boolean`) and failed before the input opened; `-reconnect_delay_max 60` survived because it kept its value. Values were restored in `main.py`, and the `_FFMPEG_ERRNO_HINTS[-22]` hint text was extended (besides container/codec mismatch, "input option parsing failure" is now a recognized cause).
- **P0 disable `-reconnect_at_eof` for HLS(m3u8) inputs → live recording yields subtitles but no video**: the end of the HTTP response of an m3u8 playlist is itself an EOF, so the option makes the http layer reconnect infinitely right after the playlist is fully downloaded (measured signature: consecutive `Will reconnect at <size> in N second(s), error=End of file`, 1/3/7/15/31s backoff, no retry cap); the hls demuxer never leaves the "waiting for playlist" stage and never pulls a media segment — ffmpeg stays alive, video stays at zero bytes, with `-loglevel error` giving no error at all. **Affected rooms are exactly the HLS-first platforms such as Douyin/Douyu** (Huya uses FLV-first and was unaffected). Fix: m3u8 inputs drop the option pair at command construction (all three definition points in `main.py` and `scripts/douyin_live_recorder_standalone.py`), FLV inputs keep it (reconnect-at-EOF appends to the same file after a CDN long-connection drop). Control experiment: with `-t 10` bound the broken command still had not exited after 60s with zero bytes; removing the option recorded 9MB in 10s and exited 0.
- **28 code-review fixes (2026-09-10)**: `-reconnect*` established as "before `-i`, each option directly followed by its value"; the recording semaphore is acquired before `Popen` with the startup segment inside `try/finally` to prevent slot leaks; `process.wait(timeout=30)` gains a `kill()` fallback on timeout; danmaku-SRT text injection escaping (`_sanitize_srt_text`: `\n`→space, `-->`→`->`, blocking forged timeline rows); danmaku collector `stop()/_run()` handshake ordering plus a bounded `_shutdown` (preventing thread + SRT-handle double leaks); sensitive-config masking (`web_config.py` key regex + `web/app.js` password inputs + `utils.mask_credentials`); last-resort probe pass-through semantics aligned; `data={}` treated as a valid body; `src/ttwid.py` falls back to serial re-fetch on non-blocking failure; the coverage gate now fails when a module is not found.
- **Web-panel rooms-list narrow-viewport misalignment**: `table-layout: fixed` + single-line ellipsis on the URL/name columns (full URL visible on hover) + horizontal-scroll fallback at ≤768px, eliminating vertical header stacking, controls overflowing the card, and long-URL wrapping on narrow windows / high-DPI scaling.

**✨ New Features**
- **i18n `tr()` parameterized API + full migration of 242 sites**: `i18n.tr(template, **kw)` looks up first, then interpolates — fixing the root cause where f-string interpolation completed **before** the catalog lookup so placeholder keys could never match and translation silently fell back to the source text; 242 parameterized logs across 27 files were converted to `tr()`, and placeholders were unified in the four-language catalogs (key set 539 → 544).
- **Web API auth hardening**: middleware now injects `X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY`; new public endpoint `GET /api/auth/status` exposes whether authentication is required plus a warning message.
- **hls.js pinned to 1.7.2**: `index.html` pins `hls.js@latest` to a concrete version (jsdelivr CDN supply-chain risk mitigation, aligned with the existing flv.js pinning convention).

**🛠️ Repo Maintenance & Quality Gates**
- **Remaining 8 production-decision + 4 machine-validation items**: all 8 decisions implemented — hls.js pinning; `http_config` TLS verification split into pull-stream-specific vs control-plane-general paths; audio-only platforms' extension/container/codec alignment (`.m4a`+aac+ipod / `.ts`+aac+mpegts); notify scripts killed after a 300s timeout; Web auth model documented; `gui_legacy.py` deleted; danmaku SRT off-loaded off the event loop (`queue.SimpleQueue` + dedicated writer thread); i18n `tr()` API; the 4 machine-validation items conservatively implemented with stub tests (`spider._safe_loads` JSON-safe parsing + URL-scheme whitelist, `ws_client` heartbeat timeout fallback, `proxy` IPv6 literals, `video_postprocess` timeout classified per type).
- **Metadata sync**: `uv.lock` project version aligned to 4.1.0 (dependency graph of 73 packages untouched), `DouyinLiveRecorder.egg-info` regenerated, eight-file version/dependency drift check clean (`AGENTS.md` / `docker-compose.yaml` etc.), `scripts/check_version.py` PASS.
- **Four-language catalog completion**: new strings added via `extract_i18n_strings.py`; all four catalogs re-aligned (544 entries each); `zh_CN.mo` recompiled (545 entries incl. the header empty msgid, `--check` byte-level sync passes).

**🧪 Tests & Verification**
- Full `pytest` **907 passed / 2 skipped / 0 warnings** (climbing 870 → 899 → 902 → 907); `tests/test_ffmpeg_reconnect_args.py` gained a third invariant class (AST-asserting the m3u8 guard exists at every definition point in main.py + standalone).
- `scripts/extract_i18n_strings.py`: 0 missing, zero four-language key-set differences; `scripts/compile_po.py --check` in sync with `.po` (545 entries); `mypy` / `basedpyright` 0 error; `black --check` / `isort --check-only` / `scripts/check_annotations.py` / `scripts/check_version.py` all green.

### Earlier entries (archived)

17 release-note entries from 2024-07-13 to 2026-09-06 (v4.0.0 ~ v4.0.9.4) were moved verbatim to [release-notes-history-en.md](docs/changelog/release-notes-history-en.md) on 2026-09-28; that volume also restores the short `…` / mid-sentence tails left by the previous trimming pass against the `.workbuddy/docold` baseline (exact rule in its header).
Reason: the changelog alone took 36.6% of this file's characters (45,771 of 124,906). The root document now keeps only the most recent releases plus this pointer, which is what makes the rest of the document readable. [Corrected 2026-10-01: four releases since v4.4.0 was added (v4.4.0/v4.3.0/v4.2.0/v4.1.0); the original wording said three]

## 💬 For questions or requests, please open an Issue. Stars and Forks are welcome

[![Star History Chart](https://api.star-history.com/svg?repos=y123ao6/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#y123ao6/DouyinLiveRecorder&Timeline)
