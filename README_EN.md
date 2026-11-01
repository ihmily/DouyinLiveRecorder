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

> Total of **51** platforms (Continuously adding platforms). Platform data-fetching functions are in `src/spider.py`, and stream-URL parsing is in `src/stream.py`.

**Danmaku recording support (5 platforms)**: Douyin Live | Douyu Live | Huya Live | Bilibili Live | TwitchTV

**Actual quality re-sampling and degradation alerts (7 platforms)**: Douyin | TikTok | Kuaishou | Huya | Douyu | Bilibili | NetEase CC

## 📁 Project Structure

```
DouyinLiveRecorder/
├── config/                     # config.ini (main) + URL_config.ini (room list)
├── assets/app.ico              # application icon (GUI tray / Web favicon / packaged artifacts)
├── src/
│   ├── entry & scheduling: __init__ · spider · stream · stream_select · scheduler · room
│   ├── infrastructure: utils · logger · proxy · ttwid · http_config · async_http · sync_http
│   ├── config & installers: config_io · config_bool · config_read · node_install · ffmpeg_*
│   ├── recording post-processing: ffmpeg_proc · video_postprocess · notify · recorder_status
│   ├── Web: web_api · web_models · web_config · web_tray
│   ├── GUI: gui_qt/ (app · main_window · theme · widgets · tray · settings_dialog · pages) + ui_*
│   ├── danmaku: base · collector · danmaku_monitor · srt_writer · ws_client · platforms/ · proto/
│   └── javascript/             # 5 signing scripts
├── web/                        # index.html · app.js · motion.js · style.css
├── i18n/                       # zh_CN po/mo (1206 keys + header = 1207 entries) · en_US.json · en_GB.json · zh_TW.yaml
├── typings/                    # third-party type stubs
├── downloads/ · logs/ · backup_config/  # runtime output (git-ignored)
├── scripts/                    # run_gates · check_* · compile_po · sync_metadata · smoke_test · sync_version
├── tests/                      # pytest cases + frontend/*.mjs
├── docs/                       # agent-reference · changelog · worklog
├── main.py / gui.py / web.py   # CLI / GUI / Web entry points
├── i18n.py · msg_push.py · build_exe.py
├── requirements.txt · pyproject.toml · uv.lock
├── Dockerfile · docker-compose.yaml · .dockerignore · .gitignore · .gitattributes
├── index.html · StopRecording.vbs
└── README.md · README_EN.md · CODE_WIKI.md · CODE_WIKI_EN.md · AGENTS.md
```

> The full per-file tree is in [`CODE_WIKI_EN.md`](CODE_WIKI_EN.md) → "Directory Structure".

## ⚙️ Configuration

### Basic config (config/config.ini)

> A duplicated key inside one section no longer voids the whole file: it reads as the last value written and logs one warning naming section / key / line (via the `src/config_read.py` tolerant-read layer, since 2026-10-17).

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
# Panel icon path: written after uploading via "Import Icon" in the panel's top bar (the copy
# lives under config/icons/). Also serves the browser tab icon (GET /favicon.ico) and the Windows
# tray icon. Leave empty to use the built-in assets/app.ico
web_tray_icon =
```

> `web_host` is `127.0.0.1` in the repo's default config (localhost access only). For Docker or LAN/public access, change it to `0.0.0.0`, and be sure to also enable `web_auth_enable` and set `web_password`.

### GUI interface config (config/config.ini)

```ini
[GUI]
# UI theme: light | dark | high_contrast (leave empty to follow the system appearance; the sidebar menu writes it back)
gui_theme =
# UI scale: 85 | 100 | 115 | 130 | 150 (leave empty to auto-select from the usable screen area; the menu applies and writes it back)
gui_scale =
# UI font family: leave empty for the system default (Microsoft YaHei UI)
gui_font =
# Custom font file path: written by "Import Font…"; the copy lives under config/fonts/
gui_font_file =
# Custom tray / window icon path: written by "Import Icon…"; the copy lives under config/icons/
# Leave empty to use the built-in icon assets/app.ico (16/24/32/48/64/128/256)
gui_tray_icon =
```

> Font notes: the preset families in the dropdown are filtered by whether they are **installed on this machine**,
> so no entry can silently fall back. "Import Font…" accepts `.ttf` / `.otf` / `.ttc` (SFNT containers);
> `.woff2` / `.woff` are web delivery formats that Qt cannot load directly on Windows — convert them
> to ttf/otf first. The log terminal and URL editor stay on the monospace font regardless of this setting.
>
> Icon notes: "Import Icon…" in the sidebar accepts `.ico` only — Windows picks the frame per scenario from
> that container (16px for the tray, 256px for large icons in Explorer); a single-size PNG either gets
> upscaled into a blur or is not recognised at all. The file must contain 16×16 (missing it makes the system
> squeeze a large frame down, smearing the ring) and should contain 256×256 (missing it only warns). The copy
> lands in `config/icons/` and the config stores that copy's path, so deleting the original does not lose the
> icon; any load failure falls back silently to the built-in icon (then to the drawn one) and never blocks startup.

### Live room config (config/URL_config.ini)

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
- This is **deliberately a different name** from `image: y123ao6/douyin-live-recorder:latest` in `docker-compose.yaml` (the `gui` service uses its own `:latest-gui`, see ‘Switch run mode’ below):
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

> ℹ️ The image ships in two dependency shapes: the default one used by `recorder` / `web` **does not**
> install the GUI window layer (PySide6 measures 647.56MB unpacked on this host, and both services keep a
> complete import chain without it, so it would only add weight). `--profile gui` builds **a second image
> under its own tag** (`...:latest-gui`) with `--build-arg INSTALL_GUI=true` plus the Qt runtime libraries,
> so the first GUI run costs one extra build and never replaces the image recorder / web are using.

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

> Same table as "Environment variable config" above (`TZ` / `PYTHONUNBUFFERED` / `PYTHONDONTWRITEBYTECODE` / `PYTHONIOENCODING` / `TERM`); compose injects from that table, so it is not repeated here.

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

> **Five-tool quality gate**: this project uses `mypy` (src + tests) / `basedpyright` (local supplement) / `pytest` (0 warnings) / `black --check` / `isort --check-only` jointly as a quality gate; all-green in CI is a prerequisite for merging. Pass counts and coverage follow the most recent gate output.

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
- Lower the loop monitoring frequency (the default 60-second loop is already conservative; you may increase it as appropriate)
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

### v4.6.0 (2026-10-18 ~ 2026-10-31) — tkinter GUI stack removed entirely (PySide6 is the only window implementation) / unified ICO icon support (GUI tray, Web tray and page, packaged artifacts) / Web system tray moved to PySide6 and GUI log wrap following the window width / five full code-review rounds with remediation (per-hop SSRF re-checks, dangerous config keys, outbound read caps) / line-ending pinning and date-free regression-lock test filenames / metadata reconciliation and CI tool bumps / repo-wide comment slimming

> This release (v4.6.0, 2026-10-18 ~ 10-31) is a "tech-stack convergence + security and quality close-out" cycle: ① **the GUI stack now lives entirely on PySide6** - `gui.py` shrinks from a 5,022-line legacy window implementation to a 54-line thin entry point, and the tkinter stack, the legacy pystray tray and `src/ui_kit.py` / `src/ui_motion.py` are all gone; ② **unified ICO icon support**, one source of truth across the GUI tray, the Web tray and page, and the packaged artifacts; ③ **the Web system tray moves from pystray to PySide6**, with the Qt event loop taking over the main thread; ④ **five full code-review rounds with remediation** (10-18 / 10-19 / 10-21 / 10-29 / 10-30) covering per-hop SSRF re-checks, credential masking, dangerous config keys, outbound read caps and coverage machine checks; ⑤ **repository-shape close-out** - `.gitattributes` line-ending pinning, date-free regression-lock test filenames, and metadata / doc reconciliation. **There are breaking changes (GUI stack and dependency surface)** - see the dedicated section below. Full root-cause analysis and verification are in [CODE_WIKI.md](CODE_WIKI.md).

**✨ New Features / Improvements**
- **Unified ICO icon support (GUI tray / Web tray and page / packaged artifacts share one source)**: new `assets/app.ico` (seven steps: 16/24/32/48/64/128/256; frames up to 64 use BMP, 128 and above use PNG) and `src/ui_icons.py`; the single effective-icon exit `ui_icons.current_icon_path()` (imported copy > bundled icon > `None`) is shared by the tray, the panel and the favicon, along with one validation rule set and one set of machine codes. The GUI sidebar gains "Import icon..." (extension prefilter -> validation -> copy into `config/icons/` -> write back to config -> apply immediately), loaded at startup from `[GUI] gui_tray_icon`.
- **Web panel icon import and tab icon**: `POST /api/icon` uses base64 JSON rather than multipart (decode first, validate second, write last), so a bad file leaves no garbage copy under `config/icons/`; `GET /favicon.ico` needs no authentication (tab requests carry no Bearer) and returns 404 rather than an empty 200 when no icon is usable (an empty 200 gets cached by the browser as a broken icon); the frontend `uploadIcon()` prefilters at 512KB and appends a timestamp on success to bust the cache. New config key `[Web] web_tray_icon`.
- **Application icon in packaged artifacts**: `build_exe.py` gains `icon_spec_value()` / `icon_datas_entries()` / `_copy_app_icon()` - `EXE(icon=)` decides the resources of the exe file itself (Explorer / taskbar) while `datas` serves runtime reads (Qt window icon / tray / favicon), and the two roots are intentionally redundant.
- **Web system tray moved from pystray to PySide6 (QSystemTrayIcon + QMenu)**: the main thread goes to `run_event_loop()` and uvicorn is driven from a daemon thread; the return value of `start()` is the degradation contract (`False` means the caller keeps `asyncio.run(server.serve())` on the main thread); the exit chain gains `setQuitOnLastWindowClosed(False)`, a 200 ms watchdog `QTimer` and `aboutToQuit` setting `should_exit`; the menu has four items (Show console / Hide console / Open Web UI / Quit); the icon is drawn by `QPainter`, so a frozen build no longer depends on an icon file being bundled.
- **GUI tray menu gains "Hide main window" / "Settings"**: `bind_actions` grows from 2 callbacks to 4 (the order is the top-to-bottom menu order) and `retranslate()` covers all four; the Settings dialog still opens on its own while the main window sits in the tray.
- **GUI run-log wrap follows the window width**: `src/gui_qt/widgets.py::TerminalText` switches its wrap mode from `NoWrap` to `WidgetWidth`, so Qt re-wraps existing blocks on resize (offscreen measurement: a long line wraps into 24 lines in a 240px viewport and reflows to 5 lines at 1500px).
- **The four i18n catalogs stay in sync**: the Web tray tooltip's bare f-string now goes through `i18n.tr` and has entered the catalogs (one new entry per catalog, key set 1205 -> 1206, `zh_CN.mo` rebuilt at 1,207 entries); the new entries added by this cycle's batches (13 / 17 / 15 review items, 17 icon entries, the termination entry and 2 new entries) were registered in all four catalogs in the same batch, with `.mo` rebuilt alongside.

**🐛 Fixes**
- **The new Qt GUI's recording output path was completely disconnected (the only critical finding)**: repo-wide, `linesReceived` on `recorder.py` was never `emit`ted and `drain()` had zero production callers, so no recording output reached the GUI at all. The fix keeps the queue and adds a wake-up signal: the dead signal becomes `outputReady`, the main-thread `_pump_recorder_queue` drains in one go and hands over batches, and `(session_id,)` sentinels are de-duplicated per session across "manual stop ended" and "natural EOF". A new `reclaim_after_natural_end` lets only the main thread clear `_process` on natural EOF, which also fixes the unbounded `_read_queue` growth.
- **Security surface (across review rounds)**: host matching now uses label boundaries (`evilweibo.com` is no longer admitted as a substring of `weibo.com`); message push and `sync_req` gained **per-hop** redirect re-checks plus landing gates; internal-address detection moved to structured `ipaddress` checks (integer / octal / IPv4-mapped / CGNAT covered); the Bilibili danmaku host rejects `?` / `#` / `@` / `\`; `--snapshot` switched to a positive allowlist; the node installer's SHA256 baseline read and unreachable official documents both became fail-closed.
- **Credential masking**: `mask_credentials` covers the ini line shape, the short key names `sig` / `jwt`, JSON numbers, Chinese credential keys and the percent-encoded query-string shape; message push strips basic-auth userinfo from the netloc and 8 exception-text sites go through `_mask_exc_text`; Bilibili buvid3 is logged as a "prefix + length" fingerprint; proxy URLs percent-encode user / password with `quote(safe="")`; backup masking gained the two plaintext channels "no ini section" and "atomic-write failure fallback".
- **Web panel and config write-back**: `web/index.html` drops the stray `</body></html>` left at the top of the file (the panel no longer falls into quirks mode); `read_web_config` / `read_quality_options` / `read_config_safe` all go through the tolerant parser (a duplicated option in one section no longer makes the auth middleware return 500 on every request); `PUT /api/rooms/quality` and `toggle_room` now use "write then re-parse" verdicts (indented comment lines no longer report a fake success); `web_tray_icon` joins `_DANGEROUS_CONFIG_KEYS` and the favicon read side re-validates size and the ICO magic number (closing the write side of the unauthenticated arbitrary-file-read chain).
- **Recording chain**: the recording Popen's `stdin` goes back from `DEVNULL` to `PIPE` (otherwise `proc.stdin is None` and the whole "write q" graceful exit is unreachable); the `start()` failure rollback pops `_room_seq_in_use` (sequence numbers are no longer burned and the registry no longer grows without bound); the AcFun sort key is folded in (entries without a bitrate sort to the tail instead of turning the whole round into "not live"); Bilibili's `url_info` host / extra go through `_dig_str` (an explicit null no longer raises a swallowed TypeError); `ffmpeg -version` and `taskkill` gained timeouts, and the stderr temp file from a failed recording is closed and discarded in place.
- **Config and data integrity**: a newly created `URL_config.ini` goes through `atomic_write_text` (0600, same rule as config.ini); the masked config backup is rewritten line by line (the "keep comments and section structure" promise now actually holds); `update_file` no longer writes on a miss and `backup_file` no longer advances the MD5 baseline on failure; the three pure reads in `sync_metadata`, `check_workflow_constants` and `check_annotations` gained unreadable-input fallbacks (rc=2) instead of masquerading as "code fails the gate" with rc=1 and a raw traceback.
- **Packaging and release chain**: macOS ffmpeg source endpoints (evermeet Download API) were removed upstream with a blanket 410, so they now pin **versioned direct links** `ffmpeg-9.0.2.zip` / `ffprobe-9.0.2.zip` and same-name `.sig` signature files (both the URL and the signed object are immutable); the official-hash document chains gained a 2 MiB read cap; `smoke_web`'s loopback coverage window now spans the whole probe loop; egg-info `SOURCES.txt` lost 13 leftover entries for deleted files.
- **Signature-script pinning**: `liveme.js` was restored byte-exactly from the historical blob (the mismatch came from a conflict commit that reverted a cleanup commit wholesale, while `.gitattributes` pins `-text` for `src/javascript/*.js`), after which all five signature scripts match their SHA256 pins; new `TestJsPinTable::test_pinned_bytes_match_the_table` compares bytes against the table file by file.
- **DNS failure attribution**: new `DNS_UNRESOLVABLE_REASON_PREFIX`; a transient resolution failure is no longer reported as a "possibly tampered stream address" (it still fails closed).

**⚠️ Breaking Changes / Behavior Changes**
- **The tkinter GUI stack is removed entirely and PySide6 is the only window implementation**: `gui.py` loses `LiveRecorderGUI` / `AdvancedSettingsWindow` / `_legacy_main()` and the tkinter crash dialog; `src/ui_kit.py` and `src/ui_motion.py` are deleted, and `src/ui_theme.py` / `src/ui_fonts.py` / `src/ui_i18n.py` / `src/ui_scale.py` keep only what Qt still uses. **There is no tkinter fallback path any more**, and 11 tkinter-only test files were deleted in the same batch.
- **`config.ini` loses the `[GUI] gui_motion` key** (it only served the legacy motion layer); old configs that keep the key no longer have it read.
- **Runtime dependencies 21 -> 18**: `pystray` / `Pillow` / `python-multipart` leave `[project.dependencies]`, `.[gui]` and `requirements.txt`; both trays are now Qt + `QPainter` drawing, so `.[gui]` holds only `PySide6>=6.12.0`. After upgrading, these three packages are no longer installed with the project.
- **The Web entry's main-thread ownership is inverted**: the pystray version ran "uvicorn on the main thread + tray on a daemon thread", while the Qt version must run "the Qt event loop on the main thread + uvicorn on a daemon thread"; when `start()` returns `False` (not Windows / PySide6 missing / tray unavailable) the caller falls back to the original main-thread shape.
- **`.gitattributes` line-ending pinning takes effect**: `* text=auto eol=lf` (LF in the repository, LF on checkout), `*.bat` / `*.cmd` pinned to CRLF, `*.sh` pinned to LF, `src/javascript/*.js` byte-frozen with `-text`; 119 tracked text files were normalized to LF, and older clones may keep their previous shape until re-checked out.
- **macOS release-chain ffmpeg no longer follows the upstream rolling alias**: with versioned immutable links, an upstream release no longer flows through automatically, so bumping means updating both archive versions by hand and re-checking signatures.
- **Write-side security tightened in the panel**: `web_tray_icon` can no longer be written through the Web config (the `/api/icon` upload path writes config directly and is unaffected); `GET /favicon.ico` returns 404 for non-ICO content; sensitivity checks gain the "API link" key and the "push config" section.

**📦 Dependency Changes**
- **Runtime dependencies 21 -> 19 (10-20) -> 18 (same day)**: pystray / Pillow went with the retiring legacy tkinter tray, and python-multipart went because the repo has no `.form()` / `UploadFile` call site; `uv lock` re-resolved and also removed the platform-specific transitive packages `pyobjc-core` / `pyobjc-framework-cocoa` / `pyobjc-framework-quartz` (macOS) and `python-xlib` (Linux), with egg-info rebuilt programmatically.
- **The extras surface converges**: `.[gui]` shrinks from three entries to `PySide6>=6.12.0`; dev 7 and build 1 are unchanged.
- **CI tool versions moved to the latest PyPI releases**: in `ci.yml`, `mypy_version` 2.4.0 -> 2.4.1 and `pytest_version` 9.1.1 -> 9.2.0 (black 26.10.1 / isort 9.0.2 were verified as already latest, so the two mirror revs in `.pre-commit-config.yaml` needed no change); after the bump all four values equal the local `.venv` installs. **No real CI run was executed** - the new constants only count as CI-verified after the next push really installs them on GitHub Actions.
- **Metadata parity**: `requirements.txt` <-> `pyproject.toml` package-name sets are 18 <-> 18; the CODE_WIKI dependency tables drop pystray / Pillow / python-multipart (21 -> 18 rows); `uv.lock` is already 4.6.0 with the same 18 entries, so `uv lock` was deliberately skipped to avoid unrelated re-resolution.

**🛠️ Repo Maintenance & Docs**
- **Five full code-review rounds with item-by-item remediation**: of the 10-18 report's 85 findings, 83 landed (`L-27` / `L-28` handed back); the 10-19 report's 5 critical items were all fixed plus Medium 30/48 and Minor 25/81; two 10-21 batches closed 15 critical items plus 1 partial and Medium 28 + about 55; the 10-29 report graded Critical 7 / Medium 35 / Minor 14; the 10-30 report was remediated as P0 5 + P1 8 + P2 3 plus the locatable L items; the reports live under `docs/worklog/CODE_REVIEW_*.md`.
- **Line-ending pinning lands**: a 21-line `.gitattributes` is added and 119 tracked text-file blobs are normalized from CRLF to LF (zero AST-level content change); the byte-freeze rule for `src/javascript/*.js` is recorded in the attribute file so a cross-platform checkout cannot flip the pin table.
- **Regression-lock test filenames lose their date segment**: 17 files renamed with `git mv` and 72 files of references synced (production comments, CI, AGENTS / README / CODE_WIKI in both languages and docs), leaving zero `regression_2026` hits repo-wide (the rename map inside the changelog entry itself is the only exception).
- **New gates and machine checks**: R9 (`test_*.py` collecting zero cases) / R10 (a thread-exit assertion is required after every join, zero tolerance), `test_outbound_read_caps.py` (httpx read-cap ledger), `test_exception_log_masking.py` (exception-text masking ratchet), `test_pep758_except_form.py` (PEP 758 shape lock) and `test_ci_pytest_env_parity.py` (every job that runs pytest must install `requirements.txt`); the coverage thresholds for `spider` / `proxy` go 50 -> 60 with a new machine check for "registered threshold below the global floor without a debt-table entry".
- **Dead code and falsified comments cleared**: the dead module `src/ab_sign.py`, 51 dead `platform = "未知平台"` assignments in `main.py`, 18 unused imports, 38 unread locals and two zero-reference functions are gone; 11 comment / contract statements were corrected (skip reasons, segment_video, the motion.js degradation direction, and so on).
- **Repo-wide comment slimming (zero behavior change)**: 133 code files lose a net 263 comment lines (+798 / -1,061); the equivalence proof covers Python AST, JS / CSS / HTML comment-stripped line sequences (288 files compared, 286 OK), zero BOM / encoding / line-ending drift, zero lost measured readings, the 13% comment-density floor and the survival of all 13 tracked topics.
- **Doc parity**: `AGENTS.md`, `docs/agent-reference/project-structure.md`, `measured-evidence.md` and the bilingual CODE_WIKI / README move with the changes; `check_skill_agents_consistency.py`'s "directory -> table" check is promoted from WARN / rc=0 to FAIL / rc=1.

**🧪 Tests & Verification**
- Per-batch final readings (all taken after the last edit of the batch): on 10-18 the full `pytest` was 4568 passed / 14 skipped / 0 warnings with 83.80% coverage (69 modules) and `run_gates.py` 10/10; on 10-22, 4977 passed / 16 skipped with 83.84% coverage; on 10-31 the batches read 5049 / 5053 / 5054 passed (84.47% coverage / 69 modules), after the tkinter removal 4786 passed / 16 skipped with 84.65% coverage (67 modules), and the metadata-parity batch was 10/10 gates with 4764 passed.
- `basedpyright` reported 0 errors / 0 warnings in every batch; `mypy` was 0 errors on the host plus `--platform linux` and `--platform win32`; `black` / `isort` / `check_annotations.py` / `compile_po.py --check` / `check_version.py` / `check_runtime_pins.py` were all green.
- ICO real build: `python build_exe.py --smoke --no-runtime --no-zip` succeeded (2 m 35 s), all three CLI / Web / GUI smokes passed, all 7 frames were found inside each of the three exes (10.68MB / 11.00MB / 11.10MB), and `assets/app.ico` landed both in the release root and in `_internal/assets/`.
- tkinter removal: product code contains no `import tkinter` / `from tkinter`; `import gui` still succeeds with `PySide6` unavailable (`sys.modules['PySide6']=None`); an offscreen `MainWindow` builds (5 pages) and `python gui.py` runs 6 s offscreen without crashing.
- Handed-back live / end-to-end items: the `liveme.js` fix is recorded as `SKIP(no network / no live LiveMe room)`; the `CODE_REVIEW_2026-10-30` remediation's real-URL platform parsing, packaging-chain real-device run and panel end-to-end run were not executed and are handed back per DoD step 2; the full download plus `gpg --verify` against the new macOS endpoints needs a first run on the macOS runner.

### v4.5.0 (2026-10-02 ~ 2026-10-17) — GUI window layer migrated to PySide6 (Qt6) and UI modernization phases 4-6 closed out / mobile and short-link platforms added (b23.tv / m.douyu.com / hy.fan / Xiaohongshu normalization) / Linux arm64 ffmpeg plus multi-arch GHCR images / startup bytecode-cache purge and the release-chain online pin-source layer / tolerant config.ini duplicate-key reader and three rounds of i18n machine checks / full-workspace code review and two metadata reconciliation passes

> Full entry in the [archive volume](docs/changelog/release-notes-history-en.md) (imported: v4.5.0 / v4.4.0 / v4.3.0).

### v4.4.0 (2026-09-29 ~ 2026-10-01) — Web panel migrated from FastAPI to Starlette (fastapi/pydantic removed, 24 route contracts preserved verbatim) / Web frontend motion layer & mobile adaptation / GUI theme layer (phase 3) and adaptive label wrapping eradicating the DPI freeze / root cure for the douyin HEVC-origin-room "no usable source" deadlock & h265 candidates admitted by save format / two full code-review rounds with P0 fixes (standalone SSRF triple guard, ffmpeg command log masking, etc.) / i18n blind-spot backfill / dependency & doc reconciliations

> Full entry in the [archive volume](docs/changelog/release-notes-history-en.md) (imported: v4.5.0 / v4.4.0 / v4.3.0).

### v4.3.0 (2026-09-16 ~ 2026-09-27) — P0 fix for 100% recording failure on ffmpeg master builds (`-thread_queue_size` narrowed upstream to an output-only option) / boolean config parsing unified (`true/false` silently broke 8 settings and blocked 9 overseas platforms) / two full code-review rounds (62 + 106 graded fixes) / supply-chain hardening (official hashes first + GPG verification + Lanzou fallback removed) / four release-chain faults fixed (**the lite package shipped to users briefly never existed**) / Apple Silicon ffmpeg PATH yield policy / per-room log correlation field & `/health` probe endpoint / build artifact size −21.6% / coverage 73.28% → 82.03% (dedicated push) and 83.91% (final, 09-27)

> Full entry in the [archive volume](docs/changelog/release-notes-history-en.md) (imported: v4.5.0 / v4.4.0 / v4.3.0).

### Earlier entries (archived)

Historical release notes have been moved verbatim to [release-notes-history-en.md](docs/changelog/release-notes-history-en.md): v4.0.0 ~ v4.0.9.4 (17 entries) on 2026-09-28, v4.2.0 / v4.1.0 (2 entries) on 2026-10-18, and v4.5.0 / v4.4.0 / v4.3.0 (3 entries) on 2026-10-31; that volume also restores the trailing `…` / mid-sentence cuts left by the previous trimming pass against the `.workbuddy/docold` baseline (exact rule in its header).
The root document keeps only the current v4.6.0 summary plus this pointer; the full history lives in the archive volume.

## 💬 For questions or requests, please open an Issue. Stars and Forks are welcome

[![Star History Chart](https://api.star-history.com/svg?repos=y123ao6/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#y123ao6/DouyinLiveRecorder&Timeline)
