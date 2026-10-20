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
- [Changelog](#changelog)

## Document Statistics and Index

> This section is summarized from a statistical analysis of **all `*.md` files in the workspace** (first generated on 2026-08-09; re-checked on 2026-09-20; recomputed on 2026-09-27 alongside the doc size pass, and again on 2026-09-28 with the version sync and the changelog split-and-archive).
> **Counts must be recomputable**: the numbers below came from the command written right here, measured 2026-09-28 — a figure that cannot be recomputed counts as stale:
> `python -c "import pathlib; sk={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache'}; p=[x for x in pathlib.Path('.').rglob('*.md') if not (set(x.parts) & sk)]; print(len(p))"`

### Statistics Overview

Excluding `.git/`/`.venv/`/`node_modules/`, the workspace contains **106** Markdown files (recomputed 2026-09-28 with the changelog split; +5 over the same-day reading of 101: the four new `docs/changelog/` archive volumes plus one harness session report), grouped by source and maintenance method into seven categories:

| Category | Path | Count | Nature | Manually Maintained |
| --- | --- | --- | --- | --- |
| Project root docs (source of truth) | `AGENTS.md` + `README` / `CODE_WIKI` CN-EN pairs | 5 | Source of truth (CN/EN document pairs) | Yes |
| Architecture reference sub-docs | `docs/agent-reference/**` | 6 | **Purely reference material moved out** of the root docs: directory tree, one-off measured readings, session learnings, lock-classification policy, and the changelog file inventories | Yes |
| One-off review reports | `docs/worklog/*.md` | 9 | Historical review / diagnosis / proposal output: `CODE_REVIEW_2026-09-17` (AGENTS conventions review), `-09-18`, `-09-20`, `-09-21`, `-09-22`, `-09-22_1`, `-09-22_2`, plus `DIAGNOSIS_2026-09-23_*` and `PROPOSAL_2026-09-22_*`; these used to sit at the repo root and are archived here | No (archived) |
| Changelog archives | `docs/changelog/**` | 4 | **Added 2026-09-28**: the historical entry volumes that the root documents' changelogs roll over per release window (`README` / `CODE_WIKI`, two volumes per language); entries are kept verbatim and the volumes are append-only | Yes |
| Local tool-generated docs | `.qoder/**` | 1 | The 302 AI-generated English architecture/knowledge files under `.qoder/repowiki/**` were confirmed absent at the 2026-09-20 re-check; the single remaining file is a harness practice session report | No (auto-generated) |
| Workspace memory | `.workbuddy/**` | 66 | Local agent's daily work logs (53 files under `memory/`) + the `docold/`/`docnew/`/`docopt/` snapshots of earlier doc passes (4 each) + one quality report | No (cache) |
| Historical memory | `.codebuddy/memory/**` | 14 | Legacy agent memory (deprecated) | No (cache) |
| CI sidecars | `.github/**/*.md` | 1 | Notes shipped with workflows / issue templates | Yes |

**Conclusion**: the hand-maintained documents that should act as the source for changes are the **5** root docs (`AGENTS.md` plus the `README` / `CODE_WIKI` CN-EN pairs), the `docs/agent-reference/` sub-docs, and the rolling archive volumes under `docs/changelog/`; the reports under `docs/worklog/` are historical artifacts, `.workbuddy/` is project-level persistent data that must not be deleted, and everything else is AI-generated derivative documentation or a local cache that must not be merged into this document, to avoid introducing content that is out of sync with the code. (Snapshot first generated on 2026-08-09; root-doc count updated to 5 on 2026-08-28 as the CN/EN pairs were completed; refreshed on 2026-09-20: total 324 -> 285, the `.qoder/repowiki/**` directory no longer exists, and a row for the 2 review reports was added. **Since 2026-09-27 this section carries a command-plus-timestamp discipline**: the old 285 shipped without a recompute command and can no longer be reproduced. Measured 101 on 2026-09-27, 106 on 2026-09-28 after the changelog split.)

### Root Document Index

| File | Role | Main Content |
| --- | --- | --- |
| `AGENTS.md` | Coding agent conventions | Single source of truth for version (`pyproject.toml`), code style (black / isort / mypy), project structure, dependency/test/build commands, key conventions |
| `README.md` | User/developer guide | Features, supported platforms (51), quick start, configuration, usage, Docker deployment, development guide, FAQ, changelog |
| `CODE_WIKI.md` | Project architecture doc (Chinese) | Module details, dependencies, design patterns, troubleshooting, contributing guide, changelog |
| `README_EN.md` | User/developer guide (English) | English counterpart of `README.md` (added 2026-08-24, structure aligned with the Chinese version) |
| `CODE_WIKI_EN.md` | Project architecture doc (English) | English counterpart of this document (added 2026-08-24, entries correspond one-to-one with the Chinese version) |

> The five documents are complementary: when changing platform support or configuration items, both `README.md` and the wiki must be updated in sync; engineering conventions follow `AGENTS.md`; `README_EN.md` / `CODE_WIKI_EN.md` are updated in sync with their Chinese counterparts.

### Reference Sub-Document Index (`docs/agent-reference/`)

> This is where purely reference material moved out of the root docs lands. The rule for what may move lives at the top of `AGENTS.md`: constraints stay in the root file, supporting readings and listings move out.

| File | Content | Moved from |
| --- | --- | --- |
| `project-structure.md` | Full directory tree | `AGENTS.md` "Project Structure" |
| `measured-evidence.md` | One-off measured readings (probe speed-up / keepalive / Huya tier sampling / Douyu clamping / release-chain bundle sizes) | long reading blocks at the end of `AGENTS.md` pitfall entries |
| `session-learnings.md` | Session learnings (step 6 of the Definition of Done) | `.workbuddy/memory/*.md` |
| `lock-classification.md` | Re-entrancy classification of locks | `AGENTS.md` "Known pitfalls" |
| `changelog-file-inventories.md` | **Added 2026-09-27**: verbatim text of the 41 "Files involved (classified by module)" inventories from the Chinese changelog; the original spots keep their section heading plus a one-line pointer | `CODE_WIKI.md` changelog |
| `changelog-file-inventories-en.md` | English counterpart of the row above (32 inventory blocks), pointed to from `CODE_WIKI_EN.md` | `CODE_WIKI_EN.md` changelog |

### Changelog Archive Index (`docs/changelog/`)

> **Added 2026-09-28.** This directory has a different job from `docs/agent-reference/`: that one holds purely reference passages lifted out of the root docs, this one holds whole historical changelog entries rolled out of the release window.
> Rotation rule: the root documents keep only the **current release window** (this file) or the **three most recent releases** (`README`); everything older moves to the volume below. When a new entry is written to a root document, the oldest entry that falls out of the window is appended to the matching archive volume.
> The volumes are **append-only**: entry bodies stay verbatim; the only change is the per-line restoration of the trailing `…` / mid-sentence cuts left by the earlier trimming pass, matched against the `.workbuddy/docold` baseline (each volume's header states the exact rule).

| File | Content | Moved from |
| --- | --- | --- |
| `code-wiki-history-en.md` | The 193 historical entries of this document's changelog (2026-05-17 ~ 2026-10-17; 20 v4.4.0 + 9 v4.3.0-dev entries moved in on 2026-10-18) | `CODE_WIKI_EN.md` "Changelog" |
| `code-wiki-history-zh.md` | Chinese counterpart of the entries above (193, one-to-one) | `CODE_WIKI.md` "更新日志" |
| `release-notes-history-en.md` | The 17 earlier release notes of `README_EN.md` (v4.0.0 ~ v4.0.9.4, 2024-07-13 ~ 2026-09-06) | `README_EN.md` "Changelog" |
| `release-notes-history-zh.md` | Chinese counterpart of the rows above (17) | `README.md` "更新日志" |

## Project Overview

### Project Basic Information

- **Project Name**: DouyinLiveRecorder (Douyin Live Recorder)
- **Version**: 4.5.0
- **Author**: y123ao6
- **License**: MIT
- **Project URL**: [GitHub](https://github.com/y123ao6/DouyinLiveRecorder)

### Features

- ✅ Supports 60+ live streaming platforms (Douyin, TikTok, YouTube, Kuaishou, Huya, Douyu, Bilibili, Xiaohongshu, etc.)
- ✅ Continuously monitors live status; auto-records when a stream starts and auto-stops when it ends
- ✅ Multiple output video formats: TS, MKV, FLV, MP4, MP3, M4A
- ✅ Three run modes: CLI + GUI + Web management panel
- ✅ Multi-platform message push: DingTalk, WeChat, email, Telegram, Bark, NTFY, PushPlus
- ✅ Docker containerized deployment
- ✅ Internationalization support (Chinese/English)
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
| asyncio + httpx | Asynchronous network requests |
| asyncio | Async decorator support |
| FFmpeg | Video recording and transcoding |
| Node.js + exejs/PyExecJS | Run JavaScript signing algorithms (exejs preferred, PyExecJS fallback) |
| Loguru | Structured logging |
| PySide6 (Qt6) + pystray + Pillow | GUI and system tray (the window layer is `src/gui_qt/` since 2026-10-17; the Web entry tray `src/web_tray.py` also uses QSystemTrayIcon since 2026-10-20; the tkinter.ttk implementation is kept during the migration and still uses pystray + Pillow) |
| Starlette + uvicorn | Web management panel backend |
| HTML + CSS + JavaScript | Web management panel frontend |
| Docker | Containerized deployment |
| gettext (msgfmt) | Internationalization translation compilation |
| mypy | Static type checking (`--strict` mode, `disallow_untyped_defs = true`) |
| pyflakes | Static code checking |
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
├── config/                              # 配置文件目录
│   ├── config.ini                      # 主配置文件
│   └── URL_config.ini                  # 直播间地址列表
├── src/                                 # 核心源码包
│   ├── __init__.py                     # 包初始化 + Node.js 环境配置 + 弹幕注册表/工厂（get_danmaku_class / get_danmaku_collector）
│   ├── spider.py                       # 直播数据爬虫（60+ 平台）
│   ├── stream.py                       # 直播流地址解析（含画质回采）
│   ├── room.py                         # 直播间信息解析
│   ├── utils.py                        # 工具函数库
│   ├── logger.py                       # Loguru 日志配置
│   ├── proxy.py                        # 代理检测
│   ├── node_install.py                # Node.js 自动安装/初始化
│   ├── ffmpeg_master_download.py       # FFmpeg master-build downloader (per-platform/arch fetch + verification, challenge-page aware, TOFU)
│   ├── ffmpeg_linux_download.py        # Linux 运行期 ffmpeg 直下（月末不可变标签 + 双趟拷贝，缺件时 dest 零改动）
│   ├── ttwid.py                        # 抖音访客 ttwid 获取
│   ├── web_api.py                      # Web 管理面板 Starlette 应用
│   ├── web_models.py                   # Web 请求体校验层（纯标准库 dataclass + parse，替代 pydantic）
│   ├── web_config.py                   # Web 面板配置读写（不依赖 Web 框架）
│   ├── web_tray.py                     # Web 模式系统托盘（Windows 最小化到托盘）
│   ├── ui_theme.py                     # GUI 主题层（语义 token + 多主题 + ttk 注册 + 持久化 + 对比度机检）
│   ├── ui_kit.py                       # GUI 控件工厂（ttk 变体样式映射 + Treeview 增量表格 + 过渡动效原语）
│   ├── ui_scale.py                     # GUI 度量层（语义字号 token + 间距栅格 + 全局缩放档位 + 小屏降档）
│   ├── ui_motion.py                    # GUI 动效层（off/subtle/full 三档 + 插值原语 + 系统「关闭动画」感知）
│   ├── ui_i18n.py                      # GUI 静态标签 i18n 接线（T() 标记 + 语言切换整窗回填 + Qt/Tk 两种应用模式）
│   ├── ui_fonts.py                     # GUI 自选字体（Tk 族名解析判据 + 私有字体加载 + config/fonts/ 副本）
│   ├── gui_qt/                         # GUI 窗口层（PySide6/Qt6：app·theme·widgets·main_window·tray·settings_dialog·recorder·监控 + pages 五页）
│   ├── http_config.py                  # HTTP 客户端共享运行时配置（SSL 验证开关）
│   ├── async_http.py                   # 异步 HTTP 客户端 (httpx)
│   ├── sync_http.py                    # 同步 HTTP 客户端
│   ├── javascript/                     # JavaScript 签名脚本
│   │   ├── crypto-js.min.js            # 加密库
│   │   ├── x-bogus.js                  # 抖音 X-Bogus 签名
│   │   ├── haixiu.js                   # 嗨秀签名
│   │   ├── liveme.js                   # LiveMe 签名
│   │   └── migu.js                     # 咪咕签名
│   ├── ffmpeg_install.py                # FFmpeg 安装脚本
│   ├── ffmpeg_proc.py                   # FFmpeg 进程注册/注销/终止/清理（抽离自 main.py）
│   ├── video_postprocess.py             # 视频后处理：分段/转码/字幕（抽离自 main.py）
│   ├── stream_select.py                 # 流地址选择/校验/画质码/抖音限速（抽离自 main.py）
│   ├── notify.py                        # Push/script/success-failure counting/concurrency adjustment (extracted from main.py)
│   ├── scheduler.py                     # Concurrency scheduling hub (adaptive capacity + per-platform circuit breaker + runtime-resizable semaphore)
│   ├── recorder_status.py               # Recording status snapshot and display (extracted from main.py)
│   ├── config_io.py                     # 配置读写/安全数值转换/备份（抽离自 main.py）
│   ├── config_bool.py                   # Boolean config parsing (是/否 equals true/false/1/0/yes/no; dependency-free module)
│   ├── config_read.py                   # Tolerant config read (a duplicated key folds to the last value and is reported; added 2026-10-17)
│   ├── base.py                          # 弹幕基类与数据结构（DanmakuBase / DanmakuMessage / DanmakuMessageType）
│   ├── collector.py                     # 弹幕采集器（线程化包装 DanmakuBase，落 SRT + 上报监控枢纽）
│   ├── cookie_cache.py                  # 按 URL 的访客 Cookie 进程内缓存（防并发重复请求触发风控）
│   ├── danmaku_monitor.py               # 弹幕监控枢纽（进程单例，内存快照 + JSONL 边车）
│   ├── srt_writer.py                    # SRT 字幕分段写入（时间轴对齐 ffmpeg segment）
│   ├── ws_client.py                     # 弹幕 WebSocket 传输层（各平台弹幕共用，proxy=None 直连）
│   ├── log_archive.py                   # 运行日志归档（停止录制流程收尾：四日志按时间戳改名）
│   ├── startup_cleanup.py              # 启动期陈旧字节码缓存清理（白名单根 + 源码内容哈希哨兵）
│   ├── platforms/                       # 各平台弹幕客户端：Douyin/Douyu/Huya/Bilibili/Twitch + 私有签名 _tars/_xbogus
│   └── proto/                           # 抖音弹幕 protobuf（douyin.proto + 生成的 douyin_pb2）
├── web/                                 # Web 管理面板前端
│   ├── index.html                      # 单页应用入口
│   ├── app.js                          # 前端逻辑（API 调用、SSE、渲染）
│   ├── motion.js                       # 前端动效引擎（零依赖 IIFE：入场/视差/粒子/降级）
│   └── style.css                       # 样式表（主题、响应式、动效 token）
├── i18n/                                # 国际化翻译目录（多语言多格式）
│   ├── zh_CN/LC_MESSAGES/
│   │   ├── zh_CN.po                   # 简体中文翻译源（gettext）
│   │   └── zh_CN.mo                   # 编译后的翻译（运行时必需，随仓库/镜像分发）
│   ├── en_US.json                     # 英语（美国）目录（JSON 格式）
│   ├── en_GB.json                     # 英语（英国）目录（JSON 格式）
│   └── zh_TW.yaml                     # 繁体中文目录（YAML 格式）
├── typings/                             # 第三方库类型存根（仅静态检查用）
├── ffmpeg/                              # FFmpeg 二进制目录（Windows，git 忽略 exe）
├── node/                                # Node.js 二进制目录（Windows，git 忽略）
├── main.py                              # 命令行入口
├── gui.py                               # GUI 图形界面入口（委托 src/gui_qt/，PySide6 窗口层；tkinter 实现迁移期保留）
├── web.py                               # Web 管理面板入口
├── i18n.py                              # 国际化实现（print 翻译包装）
├── msg_push.py                          # 消息推送模块
├── index.html                           # 独立 M3U8/FLV 播放器页面
├── StopRecording.vbs                    # Windows 停止录制脚本
├── build_exe.py                         # PyInstaller 打包脚本（CLI/GUI/Web 三入口）
├── DouyinLiveRecorder.spec              # 由 build_exe.py 自动生成（.gitignore 已忽略）
├── requirements.txt                     # Python 依赖列表
├── uv.lock                              # uv dependency lock file (committed to the repo; image/CI use pip + requirements.txt, do not consume it)
├── pyproject.toml                      # Python 项目配置（版本号/工具配置/覆盖率门禁单一事实源）
├── scripts/                             # 辅助脚本
│   ├── check_version.py                # 版本号一致性校验（CI static job 调用）
│   ├── check_annotations.py            # Annotation-convention & AST-equivalence checker (no docstrings / density floor / --baseline equivalence compare, invoked by the CI static job)
│   ├── check_coverage.py               # Per-module coverage gate (invoked by the CI test job, thresholds in MODULE_THRESHOLDS)
│   ├── compile_po.py                   # gettext catalog compiler (.po → .mo; --check zero-side-effect sync check, invoked by the CI static job)
│   ├── extract_i18n_strings.py         # i18n pending-translation string extractor (AST scan + four-catalog comparison, maintenance-time tool)
│   └── sync_version.py                 # 版本号同步脚本（pyproject → 各文档）
├── Dockerfile                          # Docker 构建文件（多阶段）
├── docker-compose.yaml                 # Docker Compose（recorder/web/gui 三服务）
├── .dockerignore                       # Docker 构建上下文排除文件
├── .gitignore                          # Git 排除文件
├── README.md                           # 项目说明（中文版，中英成对）
├── tests/                               # 单元测试目录（asyncio_mode=auto，覆盖率 source=src）
│   ├── conftest.py                     # Pytest 配置与 fixtures
│   ├── test_stream.py                  # stream.py 核心路径测试（工具函数 + 平台流解析）
│   ├── test_async_http.py              # async_http.py 核心路径测试（客户端管理 + 请求）
│   ├── test_sync_http.py               # sync_http.py 同步客户端测试
│   ├── test_room.py                    # room.py 直播间解析测试
│   ├── test_spider.py                  # spider.py 爬虫测试
│   ├── test_spider_platform.py         # spider.py 多平台分发测试
│   ├── test_utils.py                   # utils.py 工具函数测试
│   ├── test_douyin_url_resolution.py   # 抖音 URL 分发逻辑测试
│   ├── test_ttwid.py                   # 抖音 ttwid 共享缓存测试
│   ├── test_proxy.py                   # 代理检测测试
│   ├── test_concurrency.py             # 线程安全并发测试
│   ├── test_i18n.py                    # i18n 翻译加载/环境变量独立性/po-mo 同步回归测试
│   ├── test_anchor_rename.py           # 主播名自动同步测试（config_io.update_anchor_name + main.rename_anchor_directory）
│   ├── test_scheduler.py               # Scheduler tests (ResizableSemaphore / PlatformBreaker / ConcurrencyScheduler, 16 cases)
│   ├── test_record_failure_feedback.py # Recording failure feedback tests (success/fast-fail backoff/slow-fail/missing -i/capacity fallback/direct-download failure & success sampling, 7 cases)
│   ├── test_stream_select.py           # Stream selection and probe backoff marking tests
│   ├── test_cookie_cache.py            # Visitor Cookie cache tests
│   ├── test_danmaku_monitor.py         # Danmaku monitoring hub tests
│   ├── test_http_config.py             # HTTP configuration tests
│   ├── test_config_io_readonly.py      # Config readonly/language key migration tests
│   ├── test_config_io_backup.py        # Config backup tests
│   ├── test_bilibili_danmaku_info.py   # Bilibili danmaku info fetch tests
│   ├── test_huya_danmaku.py            # Huya danmaku tests
│   ├── test_concurrency_rate_limit.py  # Douyin rate-limit concurrency test
│   ├── test_node_install.py            # Node.js auto-installer offline tests (added 2026-09-21)
│   ├── test_web_tray.py                # Web console system-tray offline tests (added 2026-09-21)
│   ├── test_platform_danmaku_offline.py # Douyu/Bilibili/Twitch danmaku frame codec offline tests (added 2026-09-21)
│   ├── test_config_io_update_file.py   # Config write-side tests (update_file / anchor name / backup redaction) (added 2026-09-21)
│   └── test_video_postprocess_paths.py # Video post-processing branch and exception-classification tests (added 2026-09-21)
├── .github/                             # GitHub Actions workflow directory
│   ├── ISSUE_TEMPLATE/                 # Issue templates (Bug report / Feature request)
│   ├── PULL_REQUEST_TEMPLATE.md         # PR template
│   ├── actions/
│   │   └── retry/                      # Composite action: linear-backoff retry wrapper for network install commands (shared by ci.yml / build-release.yml)
│   └── workflows/
│       ├── ci.yml                      # CI static verification (setup/static/typecheck/test/concurrency/integration/build-verify/summary)
│       ├── build-release.yml           # Four-platform build (incl. linux aarch64; lite + full dual artifact) + auto-publish Release
│       └── issue-translator.yml        # Issue auto-translation workflow (CN↔EN)
├── .coveragerc-concurrency             # Concurrency test coverage config (used by CI concurrency-test job, no global threshold)
├── CODE_WIKI.md                        # This architecture document (Chinese)
├── CODE_WIKI_EN.md                     # This architecture document (English)
├── README_EN.md                        # Project README (English)
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

### 9. GUI Module (`gui.py`)

> **Since 2026-10-17 the window layer has moved to PySide6**: this section describes the tkinter implementation kept during the migration period (`_legacy_main()`); the current window implementation lives in `src/gui_qt/` (`app.py` assembly / `theme.py` design tokens & QSS / `widgets.py` Card·Toast·DataTable / `main_window.py` main window / `pages/` five pages / `recorder.py`·`danmaku_monitor.py` controllers), with the visual source of truth in `docs/gui-redesign/index.html` — see the same-day entry in the changelog.

**Responsibility**: Provide a modern graphical user interface.

**Design features**:

- **High-contrast color system**: meets the WCAG AA accessibility standard
- **DPI-aware fonts**: adaptive resolution scaling
- **System tray**: minimize to tray
- **Modern components**: card-based design, gradient banner, status indicators

**Main components**:

- `Colors` - color constant class
- `DpiFont` - DPI-aware font system
- `SystemTray` - system tray management
- `CardFrame` - card container
- `GradientBanner` - gradient banner
- `StatusIndicator` - status indicator
- `ModernTextWidget` - modern text widget

**Navigation pages**:

- 📊 Console - recording status overview, start/stop control
- 🎯 Quality Monitor - detect in real time whether each room's actual quality matches the setting
- 📝 URL Config - live room address management
- 📋 Run Logs - subprocess log viewer

**Quality Monitor page** (`_build_quality_page`):

- Obtains quality info by parsing the stdout log of the main.py subprocess
- Parses the loguru log prefix (`|` + `-` separators) to extract the message content
- Downgrade alert match: `{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})`
- Recording status match: `{name}[{quality}] 正在录制中 {duration}`
- Statistics cards: recording / quality normal / quality downgraded counts
- Downgraded rows are highlighted with a red background; normal rows show "✓ Same"
- Thread safety: `_quality_lock` protects shared data; UI updates run only on the main thread
- Timeout cleanup: recording markers not updated for 30 seconds are auto-cleared

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
- **Session lifecycle management (2026-09-02)**: the thread-local `requests.Session` is registered through a module-level `WeakSet` (entries are reclaimed automatically once a thread dies, GC is never blocked); `atexit` registers `close_all_sessions()` to shut down every still-live connection pool gracefully at process exit (80+ rooms running for a long time); `close_session()` additionally lets a room thread release its own Session explicitly on the exit path, and the next `_session()` call rebuilds it automatically
- **Opener construction shape (after F-12; this subsection recalibrated 2026-09-24)**: only `_opener_secure` (proxy disabled, certificate verification kept) is pre-built at module level; the non-verifying `SSLContext` and its opener are always built **lazily on demand** (`_get_insecure_context()` / `_get_insecure_opener()`) — the 2026-09-12 review item 6.7 pointed out that a non-verifying context existing at import time equals a silent process-wide downgrade surface, so reverting to module-level residency is forbidden
- **`ssl_verify` per-call override (F-12)**: `sync_req(..., ssl_verify=None/True/False)` is decided by `_resolve_ssl_verify()` (`None` = follow the `http_config.ssl_verify` global switch; an explicit value wins for that call), and the same decision must be **passed through both the urllib and the requests (proxy) paths** — credential-carrying call sites can force verification instead of being dragged down by the global switch
- **Public accessor for the thread-level Session (MIN-08)**: `session()` serves call sites that must read the status code / response headers and therefore cannot use `sync_req` (whose failure contract collapses everything into an empty string) while still reusing the same connection pool; the patch target remains `_session` (test convention)
- **Response body caps (SEV-2226 follow-up, 2026-09-23)**: on the proxy-free urllib path both caps are required — `_read_capped()` limits the compressed/raw body read (`_MAX_RESPONSE_BYTES`, 8 MiB) and `_gunzip_capped()` decompresses in chunks while limiting the produced bytes (`_MAX_DECOMPRESSED_BYTES`, 32 MiB); exceeding a cap raises `ValueError`, which the existing failure branch logs masked and turns into an empty string. **The proxy branch's `response.text` is gzip-decoded by requests itself and is still NOT covered by these caps** (known residual gap, see the source comment)
- **Current status (SEV-2226 forensics, 2026-09-23)**: this module **currently has no production importer at all** (`src/spider.py` uses the httpx async surface via `from .async_http import async_req`; the former caller `src/weverse_auth.py` was deleted on 2026-09-23); keeping or removing it is left to the maintainer — the module still carries the F-12 invariant and the `tests/test_sync_http.py` regression lock on it

### 13. Web Management Panel (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`)

**Responsibility**: Provide a Web interface to remotely manage the recorder, including dashboard, live room management, config editing, and log viewing.

**Architecture**:

- `web.py` - entry: a daemon thread runs `main.main()`, the main thread runs uvicorn; supports a hidden background run mode
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

**API routes**:

| Route | Method | Function |
| --- | --- | --- |
| `/api/login` | POST | Password login, returns Token |
| `/api/status` | GET | Get recording status (includes `actual_quality`) |
| `/health` | GET | Liveness endpoint (`{"status": "ok", "version"}`, always public / not gated by auth; for CI smoke / LB health checks) |
| `/api/rooms` | GET/POST | Live room list query / add |
| `/api/rooms/{url}` | PUT/DELETE | Edit / delete a live room |
| `/api/rooms/toggle` | POST | Enable / disable a live room |
| `/api/recording/toggle` | POST | Recording master switch (start/stop recording; stopping triggers runtime log archiving) |
| `/api/config` | GET/PUT | Read / modify config |
| `/api/logs/stream` | GET | SSE real-time log push |

**Frontend features** (`web/`):

- `index.html` - single-page application entry (dashboard / rooms / config three views)
- `app.js` - frontend logic (Token auth, API calls, SSE log stream, status rendering)
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
    # 自动捕获并记录异常（支持同步和异步函数）
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
| pystray | >=0.19.5 | System tray (GUI entry `gui.py`; the Web tray uses QSystemTrayIcon since 2026-10-20) |
| Pillow | >=12.3.0 | Image processing (tray icon generation) |
| starlette | >=1.3.1 | ASGI framework (`src/web_api.py` migrated from FastAPI to depend on Starlette directly in phase 2; lower bound 0.49.1 → 1.0.1 → 1.3.1, see the CVE/PYSEC notes) |
| uvicorn[standard] | >=0.51.0 | ASGI server |
| python-multipart | >=0.0.32 | Form/file upload parsing |
| websockets | >=14.0 | Danmaku WebSocket client (`src/ws_client.py`; `additional_headers` is a 14.0+ API) |
| protobuf | >=6.33.5,<8 | Douyin danmaku protocol decoding (`src/proto/douyin_pb2.py`; the `<8` cap is a gencode compatibility guard) |
| brotli | >=1.2.0 | Bilibili danmaku decompression (protover=3) |
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
| language | Interface language (blank follows system language; values support zh_cn/zh_CN/en/en_US/en_GB/zh_TW etc., normalized via resolve_language; falls back to en_US if unrecognized or the language file is missing; Web/GUI can switch instantly and write back to this key) | (empty) |
| 是否跳过代理检测(是/否) | Whether to skip proxy detection | Yes |
| 是否启用https录制 | Combined switch (merges the former "whether to force https recording" and "whether to disable SSL certificate verification (yes/no)"): enabled = https pull + skip cert verification; disabled = http pull + default cert verification (https-only overseas platforms stay as-is) | No |
| 禁用SSL证书验证的平台(逗号分隔) | Platform-level cert-verification exemption list: **only takes effect when certificate verification is required** (i.e. http recording mode, where TLS cert verification is on by default since FFmpeg 9.0) — platforms in the list skip cert verification (for platforms with abnormal certs like Huya/Bilibili); in https recording mode cert verification is already skipped globally, making the list redundant. At startup, missing required platforms are auto-appended (Huya Live, Bilibili Live — only appended, user-entered items are never removed) | 虎牙直播,B站直播 |
| 是否启用日志文件(是/否) | Whether to write logs to a file | Yes |
| 直播保存路径(不填则默认) | Recording file save path | (empty, defaults to current directory) |
| 保存文件夹是否以作者区分 | Whether to categorize by anchor name | Yes |
| 是否自动更新主播名(是/否) | Auto-sync on anchor rename: updates the anchor-name field in URL_config.ini, and renames the recording folder and its recording files (including danmaku/subtitle and other same-prefix artifacts) previously named with the old anchor name; triggered only when that room is not currently recording, so in-progress recordings are unaffected; if disabled, the manually entered name is kept unchanged | Yes |
| 视频保存格式ts | mkv | flv | mp4 | mp3 audio | m4a audio | ts/mkv/flv/mp4/mp3/m4a | ts |
| 原画 | Ultra HD | HD | SD | Smooth | Default quality | Original |
| 是否使用代理ip(是/否) | Whether to enable proxy | No |
| 代理地址 | Proxy server address; supports protocol prefixes (`http://` / `https://` / `socks://` etc.); a bare address (`ip:port`) automatically gets the `http://` prefix prepended | (empty) |
| 同一时间访问网络的线程数 | Concurrency (number of threads accessing the network at the same time) | 3 |
| 循环时间(秒) | Live status check interval | 120 |
| 分段录制是否开启 | Whether to segment recordings | Yes |
| 是否启用HLS采集(是/否) | Whether to prefer HLS (m3u8) source collection; falls back to FLV when disabled or the source is unavailable | Yes |
| HLS采集排除平台(逗号分隔) | HLS capture exclusion list: listed platforms **ignore the "whether to enable HLS capture" setting and always use FLV capture** (equivalent to disabling HLS capture for that platform only — the whole HLS candidate group is removed with no fallback, and the h265-FLV → HLS switch is disabled as well); platforms outside the list are unaffected and keep HLS priority. Platform names must match exactly (e.g. 斗鱼直播); both Chinese and English commas are supported; hot-reloaded every main-loop iteration | (empty, excludes nothing) |
| 视频分段时间(秒) | Segment duration | 1800 |
| 使用代理录制的平台(逗号分隔) | Matches live room URLs by domain substring; a hit routes through the proxy (requires "whether to use proxy ip" enabled first) | tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit |
| 额外使用代理录制的平台 | Append additional proxy-routed platforms (comma-separated) beyond the table above; the proxy address falls back to a value other than "proxy address" | (empty) |
| 是否录制弹幕(是/否) | Whether to write danmaku to SRT subtitle files | No |
| 是否弹幕监控(是/否) | Independent danmaku monitor switch: the GUI "Danmaku Monitor" page / Web "Danmaku Monitor" tab shows the danmaku stream and stats in real time; decoupled from "whether to record danmaku" — monitor-only does not write SRT; when both are on, the same danmaku connection is reused | No |
| 弹幕录制平台(逗号分隔) | Platforms that currently support danmaku recording (names must match exactly): Douyu Live, Bilibili Live, Huya Live, Douyin Live, TwitchTV (see the danmaku registry in `src/__init__.py`) | 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV |
| 弹幕分片时长(秒) | Danmaku SRT shard duration (requires segmented recording enabled) | 1800 |

#### [Push Configuration] section

| Config Item | Description | Default |
| --- | --- | --- |
| 直播状态推送渠道 | Optional channels: WeChat | DingTalk | Telegram | Email | Bark | NTFY | PushPlus (multi-select) | (empty) |
| 钉钉推送接口链接 | DingTalk Webhook | (empty) |
| 微信推送接口链接 | Server酱 URL | (empty) |
| bark推送接口链接 | Bark API | (empty) |
| bark推送中断级别 | Bark interruption level, options: critical (important reminder) / active (default) / timeSensitive (time-sensitive) / passive (silent) | active |
| tgapi令牌 | Telegram Bot Token | (empty) |
| tg聊天id | Chat ID | (empty) |
| smtp邮件服务器 | SMTP server | (empty) |
| 是否使用SMTP服务SSL加密(是/否) | Whether to enable SMTP SSL encryption (blank is treated as "Yes"); when enabled the port is typically 465 | Yes |
| ntfy推送地址 | NTFY service address | (empty) |
| pushplus推送token | PushPlus Token | (empty) |
| 只推送通知不录制(是/否) | Whether to notify only without recording | No |

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

### Live Room Configuration File (`config/URL_config.ini`)

**Format**:

```ini
# 基础格式
https://live.douyin.com/745964462470

# 指定画质（画质,直播间地址）
超清，https://live.douyin.com/745964462470

# 指定画质和主播名（画质,直播间地址,主播:名称）
高清，https://live.bilibili.com/123456，主播: B站主播

# 注释直播间（在地址前加 #）
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
# 阶段 1: builder
# - 仅安装 build-essential（编译无二进制轮子的依赖）
# - 创建 Python 虚拟环境 /opt/venv 并安装 requirements.txt
#   （Node.js 只在运行时需要，builder 阶段不安装）
# - INSTALL_GUI=false（默认）时按行首包名剔除 PySide6 后再装：镜像只跑 main.py / web.py，
#   两者在屏蔽 PySide6 后导入链完整；过滤只发生在镜像侧，requirements.txt 仍保留该依赖

# 阶段 2: runtime
# - 精简基础镜像 + apt 安装 ffmpeg / nodejs(24 LTS) / tzdata / procps
#   （仅 INSTALL_GUI=true 时追加 Qt 运行库 libegl1/libgl1/…，与 builder 的过滤同开关）
# - 从 builder 复制 /opt/venv 虚拟环境
# - 非 root 用户 recorder(uid=1000) 运行
# - HEALTHCHECK 兼容 main.py 与 web.py 两种模式（pgrep）
# - ENTRYPOINT ["python", "main.py"]，EXPOSE 8000（Web 模式用）
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

- `datas`: `src/javascript` (JS signing scripts), `i18n` (translations), `web` (frontend static assets), all located via `__file__`, automatically collected into `_internal/` by PyInstaller.
- `config/` does not go into `_internal`; it is copied beside the exe by `copy_external_binaries()` (see the directory convention).
- `hiddenimports`: `i18n`, `src.async_http` (dynamically imported by main.py via `__import__`), `h2` (httpx[http2] lazy load); `a_web` additionally `collect_submodules('uvicorn')` (protocol modules imported by string).
- `excludes`: CLI excludes GUI/Web libraries (tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette); GUI excludes Web libraries; Web excludes GUI libraries (tkinter/customtkinter/pystray; **since 2026-10-20 `PySide6` is no longer excluded** — the Web tray moved to QSystemTrayIcon); all three entries additionally exclude `brotlicffi` (fixes the post-packaging error of the `brotlicffi` module missing the `error` attribute; httpx auto-falls back when no brotli is present).

**Version number**: Parsed from the `version` field of `pyproject.toml` (single source of truth), used for zip naming; falls back to `0.0.0` on parse failure. `main.py` also reads the version dynamically from `pyproject.toml` at runtime (prefers `importlib.metadata`, falls back to parsing the file directly).

### 2. Directory Structure Convention (packaging artifact)

After adopting `onedir + contents_directory='_internal'`, PyInstaller collects dependencies and `__file__`-located resources into `_internal/` beside the exe; runtime resources located via `sys.argv[0]`/`sys.executable` are copied beside the exe by the packaging script after `COLLECT`. Final artifact structure:

```
dist/DouyinLiveRecorder/
├── DouyinLiveRecorder.exe          # CLI 录制核心
├── DouyinLiveRecorder-GUI.exe      # 图形界面
├── DouyinLiveRecorder-Web.exe      # Web 管理面板
├── config/                          # 配置目录（exe 同级，运行时直接读写）
├── ffmpeg/                          # FFmpeg 运行时（exe 同级，Windows 内置）
├── node/                            # Node.js 运行时（exe 同级，Windows 内置）
├── logs/                            # 日志目录（运行时默认创建于 exe 同级）
├── downloads/                       # 默认下载目录（config.ini 未指定时位于 exe 同级）
├── backup_config/                   # 配置备份目录（exe 同级）
└── _internal/                       # 依赖包 + src/ 及打包资源统一管理
    ├── (Crypto/ PIL/ certifi/ h2/ watchfiles/ websockets/ yaml/ + 运行库 .dll)
    ├── src/            src/javascript/
    ├── i18n/
    └── web/
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
| `static` | py3.14 | `black --check .` + `isort --check .` + `python scripts/check_version.py` (version single-source-of-truth check) + `python scripts/compile_po.py --check` (i18n po/mo sync check, zero side effects) + `python scripts/check_annotations.py` (annotation conventions: no docstrings / density floor / module headers, zero side effects) |
| `typecheck` | py3.14 | Install requirements + pinned mypy, then run `mypy` (scope comes entirely from `pyproject.toml [tool.mypy].files`; the minimum supported version is still used so conclusions hold for the oldest interpreter) |
| `test` | py3.14 | `pytest --cov=src --cov-report=term-missing` (global `fail_under=50` gate, `fail-fast: false`); on the minimum version additionally runs the `scripts/check_coverage.py` per-module gate + coverage.xml upload + optional Codecov |
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
pip install pyinstaller          # install the packager
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
- Type checking: `mypy` (already with `disallow_untyped_defs = true`, fully passes `--strict` mode)
- Type checking (enhanced, local): `basedpyright` is configured in `pyproject.toml` under `[tool.basedpyright]` (standard mode, excludes `typings/`/`node/`/`ffmpeg/` etc., `venvPath` points to the workbuddy managed venv); CI still uses `mypy` as the standard (basedpyright is not a CI check item, and re-specifying venvPath is needed when switching machines)
- Comment standard: Module/function descriptions uniformly use `#` line comments, **do not use triple-quote `"""` docstrings**; multi-line descriptions start each line with `#` (functional multi-line string literals excepted, e.g. templates/SQL, which should use single quotes + line concatenation instead of `"""`)

### Testing and Coverage

- Run tests: `pytest` (`asyncio_mode = "auto"`, async cases need no explicit marker); currently 3690 passed / 14 skipped, total coverage 85% (from coverage.json)
- Coverage config is centralized in `pyproject.toml`: `source = ["src"]`, global gate `fail_under = 50`
- High-frequency-change core modules have independent coverage gates (recorded in `pyproject.toml` comments, checked in CI via `--cov-fail-under` or a script):

| Module | Gate | Current Coverage |
| --- | --- | --- |
| `spider.py` | ≥50% | 50% |
| `stream.py` | ≥70% | 70% |
| `utils.py` | ≥80% | 82% |
| `ttwid.py` | ≥85% | 85% |
| `proxy.py` | ≥50% | 51% |

- Concurrency-specific tests (`test_concurrency.py` / `test_concurrency_rate_limit.py`) use the dedicated config `.coveragerc-concurrency` (no global threshold), verifying the correctness of `threading.Lock` de-duplication and Douyin rate limiting under multi-threaded environments

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

> Scope: baseline `72d1664` (the HEAD when this session started) -> the current worktree (readings taken 2026-10-17 23:00), covering **committed** (`553b036`), **uncommitted** and **index-only** changes. **No files were deleted**; the only removals are the six orphan entries in the i18n catalogs (section 1), and no configuration key was removed.
>
> Concurrent work package: `src/config_read.py` and `tests/test_config_read.py` (both untracked) plus the changes in `main.py`, `src/gui_qt/{settings_dialog,widgets,danmaku}.py`, `src/ui_{motion,scale,theme}.py` and `tests/test_config_io.py` are **not this agent's work** and are excluded from the tables below; the template they just added, `config.ini 存在重复配置项，已按最后一次取值读取: {detail}`, was briefly unregistered, which made `tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` red for a while (it was then the only missing entry) - that package owns the fix and has since committed the registration.
>
> Legend: [breaking] changes an outward contract, image content or installed artefact; [configuration] touches config keys or defaults; [dependency] touches dependencies or version constants; [string contract] changes text that other code may compare literally.

### 1. Localization catalogs (i18n)

- **Modified** · `i18n/zh_CN/LC_MESSAGES/zh_CN.po`, `i18n/en_US.json`, `i18n/en_GB.json`, `i18n/zh_TW.yaml` — Added 5 Qt sidebar navigation msgids (two-space form, passed to `tr()` by name so the extractor cannot see them); the four-catalog key count went 1110 -> 1115
- **Modified** · The same four catalogs — [string contract] Added 16 raise-site Chinese message msgids (`main.py` 7 / `src/spider.py` 3 / `src/web_models.py` 6); key count 1115 -> 1131
- **Modified** · The same four catalogs — Added 1 font-copy failure log template msgid with the placeholders `{name}`/`{target}`/`{type_name}`/`{err}`; key count 1131 -> 1132
- **Modified** · `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` — Recompiled by `scripts/compile_po.py`: 1133 entries / 149 505 bytes (header empty msgid included, N == keys + 1); the four key sets are item-for-item equal; the `.po` header date is now 2026-10-17
- **Modified** · The same four catalogs — **Retracted 6 orphan bare-text keys** (`停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志`): historical entries left without call sites once the GUI layer moved to icon-bearing keys; an AST sweep over every string constant in the repo found no consumer (`停止录制` occurs only as a **value** inside `web/app.js`'s own embedded catalog, unrelated to the backend keys). Four-catalog key count 1132 -> 1126, `.mo` recompiled to 1127 entries / 149 231 bytes
- **Note** · `开始录制` (kept in all four catalogs) — Same bare-key shape but **not retracted**: `tests/test_i18n.py::test_load_translations_priority` and `::test_set_language_hot_swaps_translator` use it as the sample msgid that proves the `.mo`-over-JSON/YAML load priority and hot switching, so removing it would redden two mechanism tests. The coupling is now recorded in the `AGENTS.md` blind-spot list

### 2. GUI window layer (`src/gui_qt/`)

- **Modified** · `src/gui_qt/main_window.py`, `src/gui_qt/pages/dashboard.py`, `src/gui_qt/pages/config.py`, `src/gui_qt/pages/runlog.py` — The construction label and the `T()` registered key of 9 buttons were unified on **one existing icon-bearing catalog key** (three-space form), fixing the fault where startup back-fill and every `retranslate_all()` knocked the icon back to bare text; no new catalog entries
- **Added** · The same 4 files — Added rationale comments at the paired sites that the construction label and the registered key must be the same msgid: the full statement stays in `main_window.py`, the other three files carry a one-line pointer (no second fact source)

### 3. GUI font module (`src/ui_fonts.py`)

- **Modified** · `src/ui_fonts.py::install_font_file` — [dependency] `except Exception: return None` now emits `logger.warning(i18n.tr("复制字体文件失败: {name} -> {target} - {type_name}: {err}", name=src.name, target=str(target), type_name=type(e).__name__, err=e))` first, so the four causes that look identical in the UI (file locked / read-only directory / disk full / source removed mid-copy) become attributable. The module gained `import i18n` and `from src.logger import logger`
- **Modified** · `src/ui_fonts.py::_safe_filename`, `src/ui_fonts.py::_WIN_RESERVED_NAMES` — [configuration] Added Windows reserved device-name cleaning (`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`: whole base name, case-insensitive, `_` prefix, idempotent; `COM10` deliberately excluded). The rationale is portability across builds and APIs - measured on this host (Windows 10.0.26300) `CON.ttf`/`AUX.ttf` in fact land as ordinary files; the cleaned name is persisted into `gui_font_file` and read back on the next start

### 4. Recording chain and platform parsing (`main.py` / `src/spider.py`)

- **Modified** · `main.py` (`_hy_fan_path_segment`, `_b23_tv_path_segment` and the two short-link resolvers, 12 sites) — [string contract] Chinese raise messages now call `i18n.tr(...)` at the production point: these messages used to be interpolated as the `{reason}` argument of an already-translated log template, so the template looked up while the message never did, which makes the production point the only place a catalog entry has meaning. Success paths untouched
- **Modified** · `src/spider.py` (TTingLive sign-in, TwitCasting, Weibo, 3 sites) — [string contract] The TTingLive sign-in failure sentence is now wrapped in `tr()`; the TwitCasting/Weibo f-strings were rewritten into a constant template + the named argument `{masked_url}` (masking still evaluated by the caller), matching the existing Douyu shape
- **Note** · The 9 messages of `src/spider.py::XhsUrlError` — Deliberately **not** wrapped in `tr()` and **not** registered: both `except XhsUrlError` handlers in `src/spider.py` and `main._resolve_xhslink_com` read only `e.code`, the message never displays, so registering it would only add dead entries. Pinned by the allowlist set equality in `tests/test_i18n_raise_site_tr.py`

### 5. Web panel backend (`src/web_models.py`)

- **Modified** · `src/web_models.py` (`_as_str`/`_as_opt_str`/`_as_bool`/`_as_str_list`/`_require_dict`, 6 sites) — [string contract] The 422 validation messages now go through `tr()`, f-strings rewritten into a constant template + the named argument `field=` (invariant 1: the template must be a literal and placeholders must be bare identifiers)
- **Modified** · the import block of `src/web_models.py` — [dependency] Added `import i18n` (that module's "zero dependency" meant no pydantic/fastapi; `i18n` depends only on stdlib + loguru and never points back at `web_*`, so there is no cycle). The panel reads error text from the `detail` **key** and never matched the wording, so the frontend contract is unaffected

### 6. Container and deployment (`Dockerfile` / `docker-compose.yaml`)

- **Modified** · `Dockerfile` (one `ARG INSTALL_GUI=false` per stage) — [breaking] [configuration] The image's GUI dependency is now gated by one switch: stage 1 filters PySide6 out of the requirements list by default, stage 2 installs the Qt runtime libraries (`libEGL`/`libGL`/glib/fontconfig/xkbcommon, etc.) only when the switch is true. Default false keeps the whole wheel out of images that only run `main.py`/`web.py`
- **Modified** · `docker-compose.yaml` (the `gui` service) — [configuration] The `gui` service now passes `INSTALL_GUI: "true"` explicitly and uses its own tag `:latest-gui` - when services with different build configs share one image name, whichever builds later overwrites the tag the other is using
- **Note** · `.github/workflows/docker-publish.yml` — The release chain must **not** pass true, keeping published images slim (that file was not changed this round and is recorded here as the other half of the constraint)

### 7. CI and gate toolchain (`ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json`)

- **Modified** · `.github/workflows/ci.yml` — [dependency] `black_version` 26.5.1 -> 26.10.1 to match the installed build; before the bump both versions ran a full `black --check` and reached identical verdicts (that is the actual criterion) - raising the constant removes a version gap, it is not evidence that CI ran
- **Modified** · `.pre-commit-config.yaml` — [dependency] black mirror rev 25.9.0 -> 26.10.1 and isort 6.1.0 -> 9.0.2 so the local venv, the CI pin and the commit hooks share one version; both revs were confirmed via the GitHub API and `pre-commit validate-config` passes, but cloning is blocked by this host's proxy, so "the hooks actually install and run" remains unverified
- **Added** · `pyrightconfig.json` — [configuration] Configuration shared by the IDE language server and the `pyright` CLI: include equals `[tool.mypy].files` item for item, exclude covers both the mypy and basedpyright lists, and typeCheckingMode/pythonVersion/venv match `[tool.basedpyright]`. Running `pyright` with no paths now reproduces the IDE surface; Pylance itself cannot be shell-driven under its license, so this is the real fix for "IDE findings must be checkable"

### 8. Package metadata and derived artefacts (`pyproject.toml` / `egg-info` / `coverage.json`)

- **Modified** · `pyproject.toml` (`packages` under `[tool.setuptools]`) — [breaking] [dependency] Added `src.gui_qt` and `src.gui_qt.pages`: explicit `packages` does not discover recursively, so omitting them leaves both sub-packages out of `pip install .` and the `douyin-recorder-gui` entry dies with `ModuleNotFoundError` at the first import
- **Modified** · `DouyinLiveRecorder.egg-info/SOURCES.txt` — [dependency] Derived artefact rebuilt after the entry above (`python scripts/sync_metadata.py`). `uv.lock` and egg-info are derived consumers of pyproject and must never be hand-edited for version fields; `sync_metadata.py --check` re-verified consistency
- **Modified** · `coverage.json` — Regenerated by `pytest --cov=src --cov-report=json`: total coverage 83.02% -> 83.04%; `scripts/check_coverage.py` reports all 68 modules meeting their threshold (`src/proto/douyin_pb2.py` stays an explicit protoc-generated exemption)

### 9. Configuration baseline (`config/config.ini`)

- **Modified** · `config/config.ini` (committed part) — [configuration] Default keys completed and reconciled against the `README.md`/`README_EN.md` configuration blocks and the code fallbacks. This file is the **tracked redacted baseline template**; `.gitignore` does not apply to it, so real cookies / proxies / panel passwords filled in locally must never be committed
- **Pending action** · `config/config.ini` (a line that exists only in the index) — [breaking] [configuration] The staged copy contains a duplicated key inside one section - `是否启动时清理陈旧字节码缓存(是/否)` on both line 5 and line 44 of `[录制设置]` - which makes `RawConfigParser()` (default `strict=True`) raise `DuplicateOptionError` on the next `read()`, i.e. the baseline config becomes unreadable. The worktree was restored to match HEAD; **the index copy was left untouched** and the cleanup `git restore --staged config/config.ini` is handed back to the maintainer. The writer-side root cause is not located (one read + write-back run changes nothing, `config_parser.write()` emits the key exactly once, and a full `run_gates.py` re-run did not reproduce it either), so this round claims no fix; the hazard and its reproduction test are recorded in `AGENTS.md`

### 10. Tests (`tests/`)

- **Added** · `tests/test_i18n_catalog_coverage.py` (3 cases) — Turns i18n blind spot 4 from manual registration into a machine check: msgid candidates passed to `tr()`/`T()` by name must be present in all four catalogs, the four key sets must be item-for-item equal, and unresolvable call sites are governed by allowlist set equality (a new one reddens it, and a resolved one left in the list reddens it too)
- **Added** · `tests/test_i18n_raise_site_tr.py` (2 cases) — Blind spot 5: unwrapped Chinese raise sites are governed by allowlist set equality (10 entries today), wrapped msgids must appear in all four catalogs, and anchors guard against a vacuous pass when the parse returns nothing
- **Added** · `tests/test_gui_qt_label_parity.py` (2 cases) — An AST pass builds tables of construction labels and registered keys and compares them per widget attribute, plus an emoji-pair floor (9) and a catalog-membership check on the registered key; behavioural evidence comes from building real offscreen widgets and reading `text()`
- **Added** · `tests/test_dockerfile_image_gui_arg.py` (5 cases) — Structural locks for the image GUI switch: `ARG` declared before use (split per Docker stage since ARGs do not cross stages), the filter expression really selects PySide6 with no collateral matches, the two compose services use different tags, the release workflow must not pass true, plus a self-check of the criterion itself
- **Added** · `tests/test_pyright_config_parity.py` (5 cases) — Pins the parity between `pyrightconfig.json` and `[tool.mypy].files` / the basedpyright lists (include equal item for item, exclude covering both lists, matching strictness/version/venv, reverse witness on the three root entries) and forbids treating Pylance as gate evidence
- **Modified** · `tests/test_ui_fonts.py` (21 -> 23 cases) — The Windows-only red case fixed on the test side: a `:` in the fixture name resolves to an alternate data stream of a file called `font` (`exists()` true, `shutil.copy2` raising WinError 3), so the character-cleaning half moved into a pure-function case and the filesystem case uses a name both platforms can create that still needs cleaning; two more cases cover reserved device names and "a failure must write one warning line naming the exception type"
- **Note** · The full `pytest` run — 4345 passed / 14 skipped / 0 failed with an empty warnings summary. The total grew by 12 over the previous round: +4 are the two new locks' cases and **+8 come from `tests/test_test_hygiene.py`'s four checks parametrized over the files in `tests/`**, each now visiting the two new files - a collection-surface change, not new assertions

### 11. Documentation and knowledge assets (`AGENTS.md` / `CODE_WIKI*` / `README*` / `docs/agent-reference/`)

- **Modified** · `AGENTS.md` — Four registrations added: i18n blind spot 5 (raise-site messages must be wrapped at the production point), clause 7 that a Qt construction label and its `T()` key must be the same msgid, the fourth custom-font hard constraint (failure must log a warning + reserved device name cleaning), and missing-key write-back must stay idempotent; plus a new convention that code references use anchors rather than `file:line`
- **Modified** · `AGENTS.md` — Six factual corrections: design tokens 26 -> **25** keys x 3 themes, `record_danmaku_args` 52 -> **60** assignments, three dead `file:line` references replaced by anchors (`main.py:3595`, `Dockerfile:112`, `src/ffmpeg_install.py:583`), and black/mypy file counts no longer cited as constants (the two measures are never equal)
- **Modified** · `AGENTS.md`, `docs/agent-reference/measured-evidence.md` — Trimming used relocation and merging instead of deletion: five groups of one-off measured readings moved verbatim into the reference document (19 341 -> 24 042 B) leaving constraint plus pointer behind; two bullets sharing one heading were re-titled to their real subjects, DoD step 5 became a pointer, and two `[历史注]` clauses were compressed to single lines. Root file 157 364 -> 158 266 B (net growth, because two durable conventions were added in the same round)
- **Modified** · `README.md`, `README_EN.md` — [configuration] Configuration-block defaults reconciled item-for-item against `config/config.ini` and the code fallbacks; version entries kept in one-to-one bilingual correspondence
- **Modified** · `docs/agent-reference/project-structure.md`, `docs/agent-reference/session-learnings.md` — The directory tree synced with the new modules and test files; lessons appended (the ADS fixture, the reserved-name measurement, the case-count attribution, the offscreen probe exit shape, measuring redundancy before editing, anchors over line numbers, and duplicate keys under `strict=True`)
- **Added** · `CODE_WIKI.md`, `CODE_WIKI_EN.md` — This module-classified change overview section (identical bilingual structure, matching entry counts, one-to-one correspondence), plus the per-batch changelog entries appended alongside each change and kept in one-to-one bilingual correspondence
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
> **Rolling archive**: this section keeps only the current release window; older entries live verbatim in [`docs/changelog/code-wiki-history-en.md`](docs/changelog/code-wiki-history-en.md) (rule stated in the "Changelog Archive Index" above).

### v4.6.0-dev (2026-10-20) — Repo-wide dependency and dead-code audit: python-multipart dropped, the dead module src/ab_sign.py deleted, 18 unused imports cleared

- **User instruction**: verify every package declared in the dependency manifests is actually referenced and list the unused ones; find retired dead code (functions/classes/methods/variables/exports with no caller, module files with no referencing entry point, large commented-out blocks, unreachable branches); pay special attention to dynamic imports, reflection, string-built paths, config-file references, aliases and build-script references so live code is not deleted by mistake; produce a "location + type + evidence" list for confirmation before deleting; then verify the build and the tests.
- **Audit method (measured locally)**: 91 production `.py` files (6 at root + 15 in `scripts/` + 70 in `src/`), 162 test `.py` files, and 18 non-Python consumption surfaces (js/mjs/html/yml/spec/toml/vbs/css/ini). Symbol reachability is decided by **raw-text identifier counts whose surface includes comments and string literals** — so indirect references such as `getattr(x, "name")`, registry literals, i18n msgids and config keys all count as "referenced". The criterion is deliberately conservative (prefer false negatives over deleting something live). **Two categories came back empty**: statements unreachable after `return`/`raise`/`break`/`continue` — 0; constant-false guards (`if False` / `while False`) — 0.
- **Unused dependency (1 dropped, 19 → 18)**: `python-multipart>=0.0.32` leaves `[project.dependencies]` and `requirements.txt`; `scripts/sync_metadata.py` regenerated `uv.lock` and the egg-info, and the package-name-set equality lock between the two manifests stays green. Evidence: the interface its declared reason refers to ("the Web API receives config uploads") does not exist — there is no `.form()` / `UploadFile` call site anywhere, and `web/` has no `FormData` / `<input type=file>` / `enctype`. Starlette only imports it inside `Request.form()`, so unlike genuinely executed optional extras such as `h2` / `socksio` the same retention argument does not apply. **Deliberately not judged unused**: `h2`, `socksio`, `urllib3` (transport-layer runtime deps with CVE floors) and `PyExecJS` (the fallback for `exejs`).
- **Dead module (1 deleted)**: `src/ab_sign.py` (Douyin A-Bogus signing, ~550 lines) together with `tests/test_ab_sign.py` (348 lines). Evidence: `git log --all -S "from .ab_sign import"` returns **zero hits across the entire history** — it was never wired into `src/__init__.py`; the header comment in `tests/test_ab_sign.py` claiming that `from .ab_sign import ab_sign` in `src/__init__.py` rebinds the package attribute to a same-named function is **stale and false**, so the `import_module("src.ab_sign")` workaround written because of it was unnecessary too. Three registrations invalidated by the deletion were cleared in the same batch: `MODULE_THRESHOLDS["src/ab_sign.py"]=95` in `scripts/check_coverage.py` (keeping it would make the per-module gate fail with "module not found", rc=1), the per-module-gate comment in `ci.yml`, and the fixture in `tests/test_check_coverage.py` that used it as "a definitely hand-written module" to build a false-exemption case (repointed to `src/proxy.py`; the criterion is unchanged).
- **Dead functions (2 deleted)**: `ConcurrencyScheduler.breaker_state()` / `breaker_states()` (zero callers, zero tests); `from typing import Any` became an orphan as a result and was removed in the same batch.
- **Unused imports (18 names across 9 files)**: the whole line `from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi` in `main.py` (pushes actually go through `push_message`, imported elsewhere in the same file, and no test monkeypatches `main.<channel>`) plus `backup_file`; `find_room_url_by_anchor_name` in `gui.py` (the function itself is alive in `src/web_config.py` and tested — only gui.py's import was dead); `src/ffmpeg_install.py::zipfile`, `src/ffmpeg_proc.py::types`, `src/node_install.py::hashlib`, `src/stream_select.py::cast`, `src/gui_qt/main_window.py::{Callable,Palette}`, `src/gui_qt/settings_dialog.py::{Callable,QWidget}`, `src/gui_qt/widgets.py::RADIUS_XL`. In every case the criterion is "the name occurs exactly once in the file's raw text (the import line itself)", which also covers string-form annotations. A further 49 `from __future__ import annotations` hits are scanner **false positives** (a compiler directive, not a bindable name) and are not counted.
- **Dead symbols (5 deleted + 1 wired instead)**: deleted `scripts/smoke_test.py::_YELLOW`, `src/gui_qt/widgets.py::build_grid()` (plus the `QGridLayout` import it orphaned) and `StatusDot.is_animating()`, `src/gui_qt/shared.py::QUALITY_NON_DISPLAY_FIELDS` (a duplicate left over from the tkinter→Qt migration: the live one is `gui.py::_QUALITY_NON_DISPLAY_FIELDS`, and `src/gui_qt/pages/quality.py` has no "skip rebuild when unchanged" comparison at all), and `src/ui_fonts.py::DEFAULT_FAMILY_FALLBACK`. **`src/ui_motion.py::ROW_HIGHLIGHT_FRAMES` was wired up rather than deleted**: the row-highlight call site in `gui.py` passed the literal `frames=5` while importing its sibling `ROW_HIGHLIGHT_MS` from the same module — deleting the constant would cement a magic number and contradict the module's own "decay steps and total duration" comment, so the constant is now imported and used (same value 5, zero behaviour change).
- **Commented-out code (4 lines deleted)**: two proxy-address debug `print` lines in `main.py`, one uptime `print` in `src/recorder_status.py`, one superseded Weibo endpoint in `src/spider.py`. Roughly 53 lines in three groups were **deliberately kept**: the `__main__` manual-debug harness in `msg_push.py` (F-24: it is commented out precisely because running the file fired a real public push), the credential-redaction archives in `src/javascript/liveme.js` and `haixiu.js` (L-24 / MIN-N39), and the danmaku DEBUG noise in `src/collector.py` marked "commented out on request".
- **Four categories judged non-deletable after the audit (including three corrections to the audit list's own premises)**: ① `spider.get_huajiao_sn` — its body carries an explicit MID-2223 (2026-09-23) rationale for "not choosing option ① (deleting the function)", it is registered in `tests/test_spider_hardening.py::OVERSEAS_MIGRATED_FUNCTIONS` (a bidirectional lock), and it is the only branch in spider.py that writes back to `URL_config.ini`; ② `spider.get_kuaishou_stream_data2` — self-described as a "backup interface" and given an L-09 regression lock on 2026-10-19 (the day before), so deleting it would erase a one-day-old lock; ③ `room.get_xbogus` + `src/javascript/x-bogus.js` — deleting the function would leave that vendored script with no executor, and "the set of `.js` files == the keyset of `utils._JS_SHA256_EXPECTED`" is a bidirectional equality lock; ④ `src/sync_http.py` (AGENTS.md explicitly retains it) and the legacy tkinter stack in `gui.py` (~5210 of 5278 lines; `main()` is a 5-line Qt delegate, but 10 `tests/test_gui_*.py` files pin it via AST text locks and subprocess `import gui` — `_legacy_main()` itself has zero callers, not even from tests).
- **Orphan files (4 deleted)**: `typings/pystray/__init__.pyi` (removed with pystray; AGENTS.md already stated `typings/` should contain only `execjs/`), `docs/qgraphflow/` (2 generated session artifacts, ~786 KB, fetched only by its sibling `index.html`, linked from no document), `docs/agent-reference/better-harness-evidence-collection.md` (AGENTS.md links four other files in that directory, never this one), and `.zcodeignore` (zero references repo-wide, content a verbatim clone of `.gitignore`; `docs/worklog/CODE_REVIEW_2026-10-04.md` had already recorded that neither ignore file has a rule for it). **Judged not orphans**: the root `index.html` (both README languages document it as a standalone M3U8 player tool page, even though it is not in the exe's `datas`), `coverage.json` (a tracked generated artifact that is the source of the documented coverage readings; the `.gitignore` entry is inert for tracked files, the same pattern as `config/config.ini`), and `DouyinLiveRecorder.spec` (gitignored, regenerated by every build).
- **One self-inflicted deletion in this round was rolled back**: `src/web_tray.py::SW_SHOW` was removed as "unused", but it is pinned by `tests/test_web_tray.py::test_module_constants_match_win32_api`, which asserts the whole family of Win32 magic numbers matches the API (the lock exists precisely because a transcription error produces a visual bug with no exception). It has been restored with a comment explaining why it is not removed as unused; the full `pytest` run went from 1 failed / 4589 passed back to all green.
- **The `saved_buttons()` comment was corrected to state the truth, per AGENTS.md key convention #12**: it claimed the accessor exists "for tests to assert button availability (the stop flow disables the control buttons)", but the Qt window layer's stop flow only disables the dashboard's start/stop buttons and never touches this page's — an assertion written to that comment would necessarily fail, which is why the accessor had zero callers. `tests/test_gui_qt_units.py::test_config_page_saved_buttons_exposes_both_control_buttons` now locks the contract that **does** exist (returns the page's own two button objects in (reload, save) order, both enabled at construction). Mutation check (swapping the returned order) turned it red on the spot and was reverted byte-for-byte.
- **Documentation kept in sync**: the AGENTS.md dependency section (21 → 18 entries, `.[gui]` three → one, "three GUI packages" → one, python-multipart removed from the security-floor sentence), a historical note about the pystray stub deletion in the typings section, and the macOS dual-main-thread entry marked as a cause archive pointing at the current Qt conclusion; the directory trees in both README languages drop `ab_sign.py` and `typings/pystray/`; both CODE_WIKI languages drop the four structural references to `ab_sign.py` (directory tree, test tree, the whole `### Signing Algorithm` section, the dependency tree) and its coverage-table row. The sentence "`pystray` / `Pillow` stay" inside README's v4.5.0 historical entry was **deliberately left alone** — it was true when written and is superseded by the new same-day entries.

### v4.6.0-dev (2026-10-20) — GUI tray gains "Hide main window" / "Settings"; the legacy pystray tray is retired and pystray/Pillow leave the dependency list

- **User instruction**: migrate the GUI system tray to PySide6 (`QSystemTrayIcon` / `QMenu` / `QAction`), keep the icon, tooltip, menu items and single/double-click behaviour, align the signal-slot style, and list the touched files with their key changes.
- **Premise corrected (measured, not inferred)**: this repo **never used PyQt** — searching all `*.py` for `pyqtSignal|PyQt5|PyQt6|from PyQt|import PyQt` and for PyQt's legacy `exec_` event-loop spelling yields **zero hits**, so "rename `pyqtSignal` to `Signal`, `exec_` to `exec`" has nothing to migrate. The tray on the shipping path **was already PySide6**: `gui.py::main()` forwards to `src.gui_qt.app.main()`, and `MainWindow._setup_tray()` mounts `src/gui_qt/tray.py::TrayIcon`; the Web tray (`src/web_tray.py`) had moved to `QSystemTrayIcon` earlier the same day.
- **The real gap was in the menu**: the Qt tray menu only had Show main window / Status (disabled) / Quit, missing the Hide entry that the old pystray menu had (Show / Minimise to tray / Exit) and offering no tray-level Settings. This round adds `hide_action` (bound to `MainWindow.minimize_to_tray`) and `settings_action` (bound to `open_advanced_settings`); `bind_actions` grows from 2 to 4 callbacks (order = top-to-bottom action-item order) and `retranslate()` refreshes all four labels.
- **Settings needs no window restore first (measured offscreen)**: `AdvancedSettingsDialog` is a `QDialog`, so with the parent hidden `show()` still yields `isVisible()==True` and `isWindow()==True`. It pops up independently while the main window sits in the tray, so there is no need to raise the main window.
- **The legacy pystray tray was retired, not ported**: `gui.py::SystemTray` (pystray + a Pillow-painted icon, including the macOS `run_detached()` main-thread workaround) is deleted as a whole (10,363 bytes). **Why not convert it to PySide6**: on that path Tk's `mainloop` owns the main thread and Qt's GUI thread must be the main thread too — the header of `src/web_tray.py` records a measured **segfault** (exit code 139, not catchable from Python) when `QApplication` is built on a worker thread. On macOS both Tcl/Tk and AppKit demand the main thread, which is exactly what `run_detached()` was working around. Adding a second toolkit to a Tk process would turn "works on macOS" into "crashes on macOS". The legacy Tk path therefore no longer ships a tray: `minimize_to_tray` always iconifies to the taskbar (keeping the warning log), the status-bar tray slot always reads "not running", and the `sys.platform` fork in `_legacy_main` — whose only reason for existing was the tray threading model — collapses into a single `mainloop()`.
- **Dependency removal**: `pystray` and `Pillow` leave `[project.dependencies]`, `[project.optional-dependencies].gui` and `requirements.txt` (21 → 19 entries). Re-running `uv lock` also drops their platform-specific transitive deps `pyobjc-core` / `pyobjc-framework-cocoa` / `pyobjc-framework-quartz` (macOS) and `python-xlib` (Linux); egg-info was rebuilt programmatically (`requires.txt` down to 19). The four-way package-name-set locks (`requirements.txt` ↔ `pyproject [project.dependencies]` ↔ egg-info ↔ `uv.lock`) are all green. In `build_exe.py` the `PIL.*` / `pystray` excludes stay as a **defensive guard** (both packages are still installed in the build venv, and `test_bloat_excludes_still_cover_the_measured_bloat` pins `PIL._avif` / `PIL._imagingft` as the size baseline); only the falsified comments were corrected.
- **i18n**: 2 new msgids (hide main window / settings) registered across all four catalogs (`zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`); `scripts/compile_po.py` recompiled the `.mo` (`--check` confirms sync at 1152 entries).
- **Verification**: new `tests/test_gui_qt_units.py::test_tray_menu_action_items_are_wired_and_fire_in_menu_order` constructs `TrayIcon` directly instead of going through `_setup_tray()` (which sets `tray` to `None` when `isSystemTrayAvailable()` is false, degenerating the case into a no-op run), triggers every action to assert callbacks and ordering, and asserts single/double click map to Show while right click (`Context`) does not fire twice. Mutation check (disconnecting `settings_action`) turned it red on the spot and was reverted byte-for-byte. The old lock `test_language_change_triggers_tray_menu_rebuild` was deleted with the legacy tray; its invariant (tray labels must follow a language switch) is taken over by the four tray assertions in `test_static_labels_and_derived_title_follow_language_switch`.

### v4.6.0-dev (2026-10-20) — Web system tray migrated from pystray to PySide6 (QSystemTrayIcon + QMenu); the Qt event loop now owns the main thread

- **User instruction**: migrate the Web entry tray (`src/web_tray.py`) from pystray to PySide6, keep behaviour identical (icon, menu, clean exit), handle the threading integration, and document icon assets plus packaged-path handling.
- **The threading model had to be inverted (measured locally, not inferred)**: the pystray version ran uvicorn on the main thread with the tray icon on a daemon thread. With Qt, `QApplication` **can only be created on the main thread** — executing `QApplication(sys.argv)` on a worker thread segfaulted (process exit code 139, nothing catchable in Python), matching Qt's "the GUI thread is the main thread" rule. So the main thread now goes to `run_event_loop()` and uvicorn runs on a daemon thread via `web.py::_serve_forever` (uvicorn 0.54's `capture_signals()` skips registration off the main thread instead of raising `ValueError`).
- **`start()` returns a contract**: `True` = the tray owns the main thread (the caller must move uvicorn off it and then run the event loop); `False` = degraded (non-Windows / PySide6 missing / `isSystemTrayAvailable()` false), and the caller keeps `asyncio.run(server.serve())` on the main thread.
- **Three things the exit chain cannot drop**: ① `setQuitOnLastWindowClosed(False)` (no QWidget exists here, otherwise the loop exits early); ② the watchdog `QTimer` (200 ms) quits only once the server thread has ended, and it is also the only landing point for Ctrl+C while the loop blocks (signals are taken over by `web.py::_install_sigint_shutdown`; a second Ctrl+C calls `request_quit()`); ③ `aboutToQuit` re-asserts `server.should_exit`, otherwise `serve()` never returns and web.py's `finally` cleanup (post-process pool / ffmpeg / HTTP pools) is never reached.
- **Menu**: Show console / Hide console / Open web panel / Exit. `_web_url()` normalises `0.0.0.0` and IPv6 literals into a browser-openable address; single and double click restore the console, right click opens the context menu.
- **Icon assets and packaged paths**: the default icon is painted with `QPainter` (no Pillow), so a frozen build reads neither `sys._MEIPASS` nor exe-relative paths — the "icon file missing from the bundle" failure mode does not exist. An optional external icon is probed by `_resource_roots()`: `sys._MEIPASS` → exe directory → repo root. On the packaging side `build_exe.py` drops `PySide6` from `a_web`'s `excludes` (the Web exe previously excluded both pystray and PySide6, so the tray in released builds was dead).
- **i18n**: 1 msgid renamed (`[web] 托盘不可用（缺少 pystray/Pillow）：{e}` → PySide6) plus 4 new ones (show/hide console, open web panel, browser-open failure); all four catalogs kept in sync and the `.mo` recompiled.
- **Verification**: `tests/test_web_tray.py` was rewritten from pystray stubs to Qt fakes (43 passed) and `tests/test_web_qt_tray_wiring.py` added (3 wiring locks); `mypy` (incl. `--platform linux` / `--platform win32`), `black`/`isort` and `check_annotations.py` are green. Two live smoke runs: ① real `web.py` start — tray enabled plus `Uvicorn running on http://127.0.0.1:8000`; ② in-process real Qt + real uvicorn — `HTTP GET / → 200`, and after the tray "exit" action `serve()` returned gracefully, the loop exited within 1.82 s and `stop()` removed the icon.

### v4.6.0-dev (2026-10-19) — 2026-10-19 review batch: all five severe issues fixed plus medium/low-severity convergence

- **Instruction**: extract every issue from `CODE_REVIEW_2026-10-19.md`, locate and fix each one without refactoring beyond the review scope; explain rather than guess on ambiguous items; run the gates afterwards and report.
- **Severe (5/5 fixed)**:
  · **S-01** `scripts/agent_hook_guard.py`: the `tail` predicate in `_protected_hit` now accepts a boundary-character set (quotes/whitespace/closing brackets/end-of-string) instead of only path separators; `_RECURSIVE_FORCE_RE` gained split `-r -f` and long-option forms; the verb table gained `ri`/`os.removedirs`/`Clear-*`; `_BARE_WIDE_TOKENS` de-duplicated. Deformed corpora are pinned in `run_self_test()` (dict → list of tuples so one rule can carry several cases) and in `tests/test_agent_hook_guard.py`.
  · **S-02** `src/config_io.py::_redact_ini_secrets`: switched to `tolerant_config_parser` (strict=False), removing the real-world fail-open where a duplicate key in a section raised `DuplicateOptionError` and returned unredacted text; a parse failure now logs an explicit warning.
  · **S-03** `src/gui_qt/main_window.py::_finalize_quit`: `QApplication.instance().quit()` added at the end (with `setQuitOnLastWindowClosed(False)`, `close()` alone never returns from the event loop, leaving a zombie process).
  · **S-04** `src/stream_select.py`: a security rejection on a body-derived hop now raises the internal control-flow exception `_DerivedHopRejected` (same pattern as `RedirectHopRejected`); `_validate_stream_url` gained a `security_rejected` out-param and `select_source_url` consults it before the `record_url` reuse branch — neither "last-resort release" nor "same-address reuse" can flip an internal target back to reachable. Two regression locks added.
  · **S-05** `main.py::_interruptible_sleep` now returns whether it was interrupted, and both `continue` branches add a fixed `time.sleep(3)` when interrupted, removing the zero-delay busy loop in Web mode with an empty URL list.
- **Medium (30/48 fixed, rest handed back)**: M-01, M-03, M-06, M-08, M-09, M-10, M-11, M-12, M-13, M-14, M-15, M-16, M-17, M-18, M-21, M-22, M-23, M-24, M-27, M-28, M-29, M-30, M-31, M-32, M-33, M-34, M-35 (details mirrored from the Chinese entry).
- **Low (25/81 fixed; the report section heading says "55 items" but numbering runs to L-81 — numbering is authoritative)**: L-01~L-15, L-24~L-28, L-47, L-48, L-54, L-55, L-77 (details mirrored from the Chinese entry).
- **i18n**: 13 new msgids registered in all four catalogs (`zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`); `scripts/extract_i18n_strings.py` reports 0 missing; `scripts/compile_po.py` regenerated the `.mo` (1146 entries).
- **Verification**: all ten `scripts/run_gates.py` steps green (black / isort / mypy on three platforms / annotation check / coverage / full pytest with 0 warnings).
- **Not completed / handed back**: see the "remaining items" table in the same-round summary reply; reasons fall into three classes — needs a design decision, needs real-device / cross-platform verification, or is a cross-module refactor beyond the review scope.

### v4.6.0-dev (2026-10-18) — Review follow-up: dead-code removal + the three §7.11 mechanized gates (R9/R10 plus two new lock files)

- **Instruction**: delete `L-27`/`L-28` dead code, delete `scripts/patch_i18n_2026_09_12.py`, and land the report's §7.11 mechanized-gate suggestions. The first two were items handed back last round under "do not delete existing dead code"; the user has now decided.
- **Dead code (re-verified before deleting, not taken on trust)**: four lines removed from `web/style.css` — `.dm-time` (:405), `.dm-empty` (:411) and `--sidebar` in both theme blocks (:16/:35). The check is "find the producer in reverse", not "find no forward reference": `grep -o "dm-[a-zA-Z]*" web/app.js` shows the JS actually emits seven classes (`dm-dropped`/`dm-gift`/`dm-line`/`dm-room`/`dm-sc`/`dm-status`/`dm-user`) and **no** `dm-time`/`dm-empty`; the sibling `.dm-dropped` does have a producer so it was deliberately kept. `var(--sidebar)` has zero hits repo-wide. `tests/frontend/test_quality_ui.mjs` only mentions style.css in prose, so all 91 frontend cases still pass. One **reverse gap** recorded but untouched (adding CSS is out of scope): JS emits `.dm-status` while CSS defines no rule for it.
- **Deleting `scripts/patch_i18n_2026_09_12.py` was blocked by the project's own hook**: `git rm` triggered **R-CLEAN-SCOPE** in `scripts/agent_hook_guard.py` (protected directory `scripts/`, the machine-checked form of AGENTS.md's "wrap-up cleanup" rule). The documented escalation is "hand back for user confirmation", and the rule deliberately has no escape hatch. Following "do not bypass safety checks", the hook was not weakened and no alternative deletion route was used (a `python -c os.remove` workaround is exactly how such a guard gets dismantled); the deletion is handed back with the command. References were checked first: apart from local tool artefacts (`.qoder/`, `.qoder-credits/`, `.workbuddy/doc*`) and historical snapshots, no active source file, `AGENTS.md`, `pyproject`, `.pre-commit-config.yaml` or workflow references it, so removal breaks no link.
- **The three §7.11 gates (all implemented as pytest structural locks — no new gate command)**. The reason for not extending the `AGENTS.md` "format commands" block: that block is `run_gates.py`'s single source of truth, so one more line means syncing four places (doc / pre-commit / run_gates / its regression lock) and pushing a second-scale AST check into the serial gate chain; as `tests/` locks the CI `test` job covers them automatically, they run under plain `pytest`, and failures name the offending site.
  · **`tests/test_outbound_read_caps.py`** — reads `(file, function)` pairs of **httpx-only** read methods (`aread`/`aiter_bytes`/`aiter_raw`/`aiter_lines`/`iter_bytes`/`iter_raw`/`iter_lines`; exactly 3 sites measured) as a two-way set equality, so a new site must be registered with "cap shape + why acceptable". It also locks that the managed functions really reference a cap constant (guarding "function name kept, limit removed") and that `sync_http` has no unmanaged `.read` while its 400 branch goes through `_read_capped`. `.read`/`.text`/`.json` are deliberately **not** scanned repo-wide: 53 measured `.read` sites are mostly file reads, which would drown the real signal; the sync side uses a module-scoped rule instead.
  · **`tests/test_exception_log_masking.py`** — only functions whose body really performs an outbound action are scanned, and exception kwargs are collected from the **whole logger subtree**, because this repo writes `logger.warning(i18n.tr(template, e=e))` so `e=` hangs on the inner `tr()` (checking only the logger's own keywords finds nothing — the first false green found while diagnosing M-05). A **shrink-only ratchet** rather than zero tolerance: measurement gives 23 functions / 34 kwargs, and a permanently red board is read by nobody and protects nothing (the M-26 lesson). Each entry is labelled credential-bearing vs download-source, with the 11 credential-bearing ones listed as the burn-down queue.
  · **`tests/test_pep758_except_form.py`** — ① every repo `.py` must parse under the running interpreter (pinning the recurring "3.13 mis-reports the unparenthesized form" trap); ② the count of unparenthesized multi-exception handlers must not fall below baseline (mass parenthesizing is invisible to both `ast.dump` and `black --check`, i.e. blind spot ① of the annotation checker, turned into a lock); ③ assert `except A, B as e:` is still a SyntaxError on the target version — that form can never be a lint rule (it dies at parse time), so the lock's value is that a future runtime allowing it turns this red and forces the convention to be re-examined. Classification uses AST positions plus `ast.get_source_segment` (measured on 3.14.8: the parenthesized segment text carries the leading `(`, the bare one does not), making it immune to comments and strings.
  · **`tests/test_test_hygiene.py` gains R9 and R10** — R9 rejects `test_*.py` files that collect zero cases (the MT-02 shape) with a two-way-equal exception table, currently 6 entries (4 dual-mode collectors + 2 douyu manual probes, the latter flagged for conversion); detection is AST-based because really running `--collect-only` imports every module through the autouse fixtures that pull in the whole runtime dependency set. R10 requires an exit assertion after every thread join (the LT-01…04/MT-04 shape) with **zero tolerance and no exception table** — all 18 legacy violations were fixed in this batch (5 joins that had no `timeout=` gained one, turning a deadlock from "hangs the session" into "fails fast"); the rule is function-scoped, and thread detection is intentionally conservative so `"\n".join(lines)` and `queue.Queue.join()` are never flagged.
- **Two self-inflicted defects, both caught by the reverse witnesses in the same run**: ① the R9 classifier double-counted methods inside `Test*` classes (`ast.walk` hits both class and method) — the `classed` reverse witness failed with 2 ≠ 1 and it was rewritten with a parent map; ② the PEP 758 baseline was first taken from a rough line regex (60), and the mutation "remove one unparenthesized site" **stayed green** — the AST classifier's real number is 61, so 61→60 still satisfied the stale baseline: a ratchet whose baseline does not come from its own classifier ships a built-in slack. Fixed to 61 with the re-compute command recorded in the comment.
- **Falsified sentences corrected in place** (AGENTS.md's own exception rule): the "live collector" item claimed `--collect-only -q` must return in seconds **and collect ≥ 1**; measurement shows only `test_twitch_live_collector.py` yields ≥1 while the other four report `no tests collected` — the guard's real target is collection-time side effects, not the count, so the sentence now says "returns in seconds" with a dated `[2026-10-18 证伪改正]` note. Also the hygiene file's header still said "six rules (R1–R4 + R6 + R7)" although R8 had existed for weeks; it now reads "nine rules (R1–R4 + R6–R10)" with a history note.
- **Verification**: the four new locks plus the revised hygiene file = **664 cases green**; all eight mutations turned red and were restored byte-exact in the same round (cap constant removed / 400 branch back to full read / new unregistered read site / new unmasked kwargs / masked without shrinking the table / one mass-parenthesizing edit / a synthetic zero-collection file / a removed exit assertion), with 664 passing again after restore; `black`/`isort`/`mypy`/`check_annotations.py` (251 files, 0 dangling names) green. Full-suite readings follow in the next entry's wrap-up.
- **Not executed / handed back**: ① the `patch_i18n_2026_09_12.py` deletion must be run by the user as `git rm scripts/patch_i18n_2026_09_12.py` (the hook blocks agent-side deletions under `scripts/` by design); ② burning down the 11 credential-bearing sites in the masking ratchet; ③ converting the two douyu manual probes into offline collected cases.



- **Counting caveat first**: the report's summary table claims 86 findings (1 critical + 37 medium + 48 minor), but its body enumerates only **85** — section 5.1 is headed "production code (24 items)" yet lists `M-01…M-23` (one item never written up; the report contradicts its own statistics, it is not a gap on our side). This round processed the **85 enumerated** items: 83 landed, 2 (`L-27`/`L-28`, dead frontend CSS) were handed back to the user because `AGENTS.md` prescribes "do not delete existing dead code — report it instead". Every item was re-verified against the source first; **3 report conclusions were disproved** (below).
- **S-01 (the only critical finding — the new Qt GUI's recording output path was completely disconnected)**: repo-wide, `linesReceived` on `recorder.py` was never `emit`ted and `drain()` had zero production callers (only `tests/test_gui_qt_units.py` called it directly, which is exactly what masked the break). Final shape keeps the queue and adds a wake-up signal instead of emitting straight from the reader thread: the dead signal becomes `outputReady`, `_push` emits after "enqueue → set flag" so the ordering can never lose a batch, and the main-thread `_pump_recorder_queue` drains in one go — batches to the original `_on_lines_received` (quality `parse_line` keeps its input), `(session_id,)` EOF sentinels to `_on_recorder_ended`, de-duplicated across the two channels (manual stop's `ended` signal and natural EOF) and still guarded by `_quitting`/`is_stopping`/late-session checks. A new `reclaim_after_natural_end` lets only the main thread clear `_process` on EOF, preserving the window where `_stopping`/`stop_async` need the handle, and also fixes the unbounded `_read_queue` growth. Rationale for the choice: the existing `drain()` contract in `test_gui_qt_units.py`, where `_READ_BATCH_SIZE` throttling lands, and avoiding a permanently idling poll. `M-11` (cross-thread `QTimer.start()` from the danmaku tail thread) shares the root and now goes through `logQueued.emit()` → main-thread `_ensure_log_timer_running`. Locks: new `tests/test_regression_2026_10_18_gui_output_chain.py` (6) and `tests/test_gui_qt_settings_dialog.py` (2); four mutations (drop the emit / skip reclaim / restore direct `start()` / drop the mtime pre-set) each turn red.
- **Three disproved recommendations**: ① `M-09`'s "install the new handles first, then rename" — measured on this host, `os.rename` raises `PermissionError [WinError 32]` while the process still holds the append handle, which is precisely why the original order exists. Replaced instead with a bounded in-memory `_ConsoleBridge` that takes over the standard streams + `rebind_console_sink()` synchronously, then closes the old handle, renames, installs the new handle and merges the buffered window output into the file. ② `LT-09`'s "compare the value before and after import" — `import i18n` at the top of that file already runs the module body, so a baseline taken afterwards absorbs the very pollution under test (measured: still 2 passed, i.e. a second false green); final form clears `LANG`/`LC_*` with `delenv` first, then re-executes the real module body in a throwaway namespace. ③ `L-35`'s claim that "the foreground shell exits immediately" is wrong (the old line is a synchronous call), but `$$` does point at the wrong process (measured: pid file held 6241 = the bash script while the real node was 60400; `stop-server.sh` reported "stopped" yet the service still answered 200) — fixed by writing the real child pid (`$!`) and keeping the blocking `wait`.
- **Response-body read caps (M-03/M-04/L-11)**: the sync 400 branch now reuses the module's `_read_capped` (that branch never decompresses the error body, so a single cap is the correct scope — adding a decompression tier would change the pass-through contract). On the async hot path the cap is enforced **inside the single response hook built by `_build_client`** (httpx fires it after headers are received and before `aread()`), where `_bounded_response_read` aggregates via `aiter_bytes()` — reusing httpx's own decode pipeline instead of rewriting it — raises on overflow, and otherwise materialises and back-fills `response._content` so the later `aread()` short-circuits. The call surface, return contract and exception exits are byte-for-byte unchanged, and no second hook is created (`test_regression_2026_09_29_wp_b_netguard` asserts exactly one). 8 MB / 32 MB match the sync side but are **stored separately rather than imported** (the sync module documents zero production importers, plus the evidence-gathering anchors), with `test_caps_match_the_sync_side_baseline` pinning the parity. The four probe sites now use `_bounded_probe_get`, keeping the HEAD → Range GET verdicts identical.
- **Data integrity (M-06/M-07/M-08/M-10/L-12/L-13/L-14)**: `update_file` gained a `matched` flag (no hit → no write, return `old_str`, consistent with `delete_line`'s SEV-05 contract; all call sites grepped — none relied on the fake success); `backup_file` returns `bool` and a failure no longer advances the MD5 baseline (retried next round); `utils.read_ini_value`/`update_config` moved onto `config_read.tolerant_config_parser` — **only via a function-level deferred import**, since a top-level import cycles through `web_config`, with an AST lock on that shape — and `preserve_case=False` keeps the existing case-insensitive matching, while the write-back product is asserted to still parse under a **strict** parser; both TOFU baseline reads now also catch `UnicodeDecodeError` (master and `ffmpeg_install` comments name each other, same shape as the Linux sibling); `ffmpeg_official_temp.zip` cleanup grew from the report's "two exits" to the four actually present, collapsed into one `finally` unlink; the yum probe exception branch now sets `is_RHS = False`, and the pre-existing case `test_yum_probe_crash_keeps_rhs_semantics` — which pinned the defect itself — was renamed and rewritten per "changing a lock's type means changing the test".
- **Credentials and masking (M-05/L-08/L-10/L-21/L-24)**: the singleflight failure log now passes `e=` through `mask_credentials` (the report's extra claim that `{type_name}` was missing is a false positive — it was already there), backed by a value-disappears behaviour lock plus an AST structural lock for future call sites; Bilibili buvid3 is logged as a `_buvid_log_form` "4-char prefix + length" fingerprint (both debug sites keep their attribution value via the exit string, the whole value never lands in rotating logs); proxy URLs percent-encode user/password with `quote(safe="")` (`_split_host_port` never unquotes ⇒ the fields are literal by contract; eight measured values decode byte-identically, while `safe="%"` would wrongly treat a literal `%40` as an escape); `is_sensitive_item` compares section names through a new `_SENSITIVE_SECTIONS_FOLDED` `casefold()` view (the allowlist itself unchanged, tightening backup copies and the write-side guard too); `liveme.js` comment samples replaced with `<REDACTED>` and `haixiu.js`' four `eval("<static constant name>")` sites replaced by direct references (each verified to be a same-scope `var` literal). Both JS files were driven through the production execjs entry point, HEAD vs modified, returning identical key sets and signature values → non-behavioural changes, so `utils._JS_SHA256_EXPECTED` was re-pinned for those two slots (raw-byte SHA256; the superseded values remain as history).
- **GUI stability (M-12/M-13/M-14/M-15/M-16/L-02)**: the URL-config conflict check gained an `_url_conflict_asked` guard **before** the `_url_last_mtime` pre-set (ordering matters: otherwise a write during the dialog is silently consumed) with an unconditional `finally` reset; the settings dialog stops `_watch_timer` in `hideEvent` and restarts in `showEvent` (stopping beats instance reuse — a fresh instance is when disk re-reads and the two MID-55 baselines are rebuilt, and `hide` is the common terminus of all four close paths); `TerminalText` now holds its own `_highlighter`, `apply_highlighter` attaches once and later only calls `set_palette` + `rehighlight()`; `status_title`/`status_sub` leave the retranslate registry per "runtime labels are not registered", with `_repopulate_static_texts` re-driving `_set_running_ui` (one fewer dual source of truth than the report's "keep registered + re-fill later"); nav buttons, brand_sub, statistics headers, empty states and refresh buttons all go through `T()` + `set_text` with the constructed label and the registered msgid from the same source (zero new emoji-keyed entries), and quality/danmaku each add `retranslate_runtime()` that clears row caches to force a full repaint; the legacy tkinter exit path gained a PID-reuse defence (`OpenProcess` + `QueryFullProcessImageNameW`, skipping the whole-tree kill only when the image name is **provably** different; every inconclusive case falls back to the original unconditional kill).
- **Frontend (M-17/M-18/M-19)**: `data-i18n="loading"` removed from `#config-container` (`applyTranslations` is a generic "scan `[data-i18n]`, overwrite textContent" routine; adding an exception table to it would fail silently on any omission — and the other four dynamic containers keep their attributes on children that `innerHTML` replaces, so they are not affected); the three on-demand loaders reuse the existing `makePollChain` generation mechanism (`halt()` + `isCurrent()`) on both the success and the catch path, so a stale generation's network error cannot mark the newest load as failed; the danmaku room dropdown rebuilds only when the option string actually differs from the last write (comparing the previously written string rather than reading the DOM, since real-browser normalisation would make the comparison permanently unequal). All new cases went into the existing `tests/frontend/test_quality_ui.mjs` (83 → 91), so **no new `.mjs`** and no `ci.yml` node-id change.
- **Test validity (MT-01…13 / LT-01…13)**: every stdlib-body patch converged onto a shim or a `sys.modules` entry plus a reverse witness (`asyncio`, `smtplib`, `os.rename`, `ctypes`, `os._exit`); the tautological security lock MT-03 now asserts on fragments that really occur in the command plus a sentinel unique to it, with a mutation ("make the guard echo the command") proving the old assertion was indeed always true; the empty file MT-02 was rebuilt after `test_bili_e2e.py` into 3 offline collection-type chained cases (the live path stays behind `if __name__ == "__main__"` with all four dual-mode template constraints satisfied; no whole-module skip); MT-08's heartbeat timeout runs on a controllable virtual clock (all three thresholds unchanged, three anti-idle guards, file runtime 4.44s → 0.53s); MT-05's collection-time `DLR_GUI_PARENT` pollution moved into a session-scoped fixture using `MonkeyPatch.context()` for a true delete plus an AST self-lock; MT-06/MT-07 replaced fixed sleeps with the file's own deadline polling and an explicit `assert hub.flush()`; every `join()` now asserts `not is_alive()`; LT-07's module-level `sys.path.insert` is now inserted/returned per case by value; LT-13 gates `GOLDEN_REGEN=1` on "case set complete" before writing (measured: without the gate the baseline JSON was overwritten by a single snapshot, keys 38 → 2).
- **Scripts and dev tooling (M-21/M-22/M-23/L-29/L-30/L-31/L-32/L-33/L-34)**: `patch_i18n_2026_09_12.py` now derives `ROOT` from `Path(__file__).resolve().parent.parent` and returns `int(res.returncode)`, launching `compile_po` via `sys.executable` instead of by name; `check_annotations.py`'s home-directory guard was narrowed to "the home itself and its direct children" plus an explicit pass for workspace subdirectories strictly under `cwd` — placed before the system-roots check, because on Windows `C:\Users` is also in that list; `check_runtime_pins.py` probes all required private attributes up front and `sys.exit(2)`s on absence (both `check()` and `--emit-env`; matrix key order untouched); gate commands in `run_gates.py` moved to `build_gate_argv()` with `shell=False`, falling back to the shell form only for shell metacharacters or `.bat`/`.cmd`; `smoke_test.py` validates `expect_contains` element types at the single `load_config` checkpoint and returns **rc=2** for malformed config (never downgraded to 0 or a warning); the companion `server.cjs` got per-file try/catch around `statSync`/`readFileSync`, request- and server-level error handlers, an Origin check on the WebSocket upgrade (compared against the actual listening port; a missing Origin still passes for non-browser local clients), and a shutdown that destroys all clients plus `closeAllConnections()` before `server.close`.
- **Cross-package regression fixed along the way**: `utils.run_node_script_async` moved from `subprocess.run` to a self-managed `Popen + communicate(timeout=)` with process-tree reclamation (POSIX `start_new_session` + `killpg`, Windows `taskkill /T /F`, cross-referencing `src/notify.py`'s contract), so `tests/test_spider_fixes.py::TestMigu`'s stub moved from `run` to `Popen` (a class with `__class_getitem__`) — which also removed a case that was falsely green while spawning a real node process and real network traffic. The hang was reproduced on this host: with the old shape a detached grandchild holding the pipe kept `subprocess.run(timeout=2)` blocked for 20 s; the new shape raises `TimeoutError @2.01s` and `tasklist node.exe` drops from 2 to 0.
- **New i18n keys (5; all four catalogs plus the regenerated `.mo` are in sync — `zh_CN.mo` measured at 1133 entries)**: two for web_console truncation, one for the PID-reuse skip, one for node child-tree reclamation failure, one for "backup failed → do not advance the baseline".
- **Verification** (wrap-up on 2026-10-18, every run made after the last code edit of the batch): `scripts/run_gates.py` **10/10 PASS, rc=0** (black 251 files unchanged / isort / `mypy` without arguments — 250 files Success / `mypy --platform linux` Success / `mypy --platform win32` Success / `check_annotations.py` / `compile_po.py --check` (`.mo` in sync with `.po`, 1133 entries) / `check_version.py` / `check_runtime_pins.py` / `check_skill_agents_consistency.py` all 5 entries consistent); full `pytest --cov=src` **4568 passed / 14 skipped / 0 warnings (9 m 52 s, rc=0)**; `scripts/check_coverage.py` **all 69 modules above threshold, total coverage 83.80%**; `node --test tests/frontend/*.mjs` **91/91 pass, 0 fail**; `basedpyright` **0 errors / 0 warnings / 0 notes**; `tests/test_test_hygiene.py` 635 passed (no mutation-marker residue repo-wide). The first full-suite pass caught exactly 1 failure (a cross-test thread race in the L-18 case); the readings above are after that fix. **End-to-end live verification (DoD step 2) was not executed** — this sandbox has no external network and no live room, while `M-04`/`L-08`/`L-09`/`L-11` sit on the platform-parsing and source-selection path. **Handed back to the user**: in a networked environment run `python tests/test_douyin_live_collector.py <masked URL> 60` and `python tests/test_bili_live_collector.py <masked URL> 60` (covering the new read caps and the buvid fingerprint logs), plus one real Windows pass of "Start recording → let the stream end naturally → start again" to confirm all three impacts of S-01 are gone; the `build-release` / `ci.yml` sides need a manual pipeline run to confirm.
- **Doc parity**: the "`src/utils.py`×2" entry in `AGENTS.md`'s "parsers not yet migrated to the tolerant read layer" list is now implemented (corrected separately below); `.agents/skills/dlr-dev-playbook/scripts/` behaviour changes did not require touching `references/visual-companion.md` (only L-35's pid semantics, which do not conflict with it).



- **Symptom**: in the macOS build job of `build-release` (runner `macos-latest` → runtime key `macos-arm64`) node v24.22.0 installed fine, then two consecutive `[build][error] full package self-check: no non-empty ffmpeg / ffprobe executable found in …/dist/DouyinLiveRecorder/ffmpeg` lines, followed by `[build][FATAL] full package is missing usable runtime components, build terminated (the release path does not allow missing pieces)`, exit code 1. The missing pieces were only named at the pre-packaging self-check because one swallowed `[build] ffmpeg download failed: …` warning sits above them.
- **Root cause (measured)**: both macOS entries of `build_exe._FFMPEG_DOWNLOAD_URLS` and all four signature URLs of `_RUNTIME_GPG_SIGNATURES` pointed at evermeet's Download API (`getrelease/zip`, `getrelease/ffprobe/zip`, `/sig` appended). Upstream **removed that API entirely**: `https://evermeet.ca/ffmpeg/getrelease/zip`, after redirecting to `evermeet.cx`, returns **410** / `application/json` / 86 B — `{"status":"error","message":"API endpoint removed due to exorbitant abuse","code":410}` — and `…/zip/sig` likewise. The page's own "APIs → Download API" section now reads `This endpoint has been removed due to exorbitant abuse.`. `urllib`'s `HTTPError` is an `Exception` subclass, so `_download_ffmpeg`'s `except Exception` collapsed it into one warning line → `ffmpeg/` stayed an empty directory → the artefact self-check hard-failed. The fail-closed chain worked as designed: no truncated zip was produced and `release-guard` reclaims the empty Release.
- **Fix**: the macOS artefacts now come from the **versioned direct links** the page lists — `_FFMPEG_DOWNLOAD_URLS` for both keys → `https://evermeet.ca/ffmpeg/ffmpeg-9.0.2.zip`; the ffprobe entry of `_EXTRA_EXECUTABLE_URLS` → `…/ffprobe-9.0.2.zip`; the four `_RUNTIME_GPG_SIGNATURES` entries → **artifact name + `.sig`** (measured `…/ffmpeg-9.0.2.zip.sig` → 200 / `application/pgp-signature` / 594 B, redirect landing at `e.deolaha.ca:4242/pub/ffmpeg/ffmpeg-9.0.2.zip.sig`, i.e. the **same object** measured through the old alias on 2026-09-26, so the pinned primary key fingerprint `20F6EA3E0CFD6B4C53447A73476C4B611A660874` did not have to be re-taken). The egress host is unchanged (`evermeet.ca`), so `_ALLOWED_HOSTS` stays; `tests/test_ffmpeg_install.py::DOWNLOAD_SOURCES` covers the runtime-install side, which does not overlap with the release chain, and was likewise left alone.
- **The signature tier got stricter as a side effect**: the old alias rolled forward, so `OFFICIAL_SIGNATURE_PIN` could only pin *who signed*, never *which version*. With versioned links both the URL and the signed object are immutable — structurally the same contract as the Linux month-end autobuild tag, with the same price: upstream releases do not flow through automatically, and bumping means updating both artefact versions by hand and re-checking the signature. The "rolling alias" limitation noted inside `_download_file` was falsified, so its text was corrected in place with a dated historical note.
- **Regression locks**: new `tests/test_build_exe.py::test_macos_ffmpeg_urls_point_at_immutable_artifacts` (bans the `getrelease` shape, requires the versioned-link shape, both architectures equal per slot, and the two archives on the same version); `…::test_macos_arm64_resolves_to_the_same_evermeet_build_as_x64` now asserts the versioned tail; `…::test_gpg_config_shape_and_source_consistency` and `…::test_macos_ffprobe_signature_entry_matches_its_artifact_url` moved their isomorphism test from `artifact + "/sig"` to `artifact + ".sig"`; the darwin end-to-end case `…::test_macos_ffmpeg_branch_fetches_both_archives_and_verifies` now derives its stub payload keys **from the production source tables** instead of re-writing URL literals (two copies of the same fact drift apart).
- **Four mutation checks** (in-memory backup → rewrite → run → byte-exact restore, verified via `read_bytes()`): ① reverting both macOS slots to the `getrelease` alias → 5 failed (new lock + the two isomorphism locks + the tail lock + the darwin end-to-end lock); ② offsetting only the ffmpeg signature URL version → 2 failed; ③ bumping only the ffprobe archive → 1 failed (version-parity test); ④ pinning the two architectures to different versions → 4 failed.
- **Verification**: `pytest tests/test_build_exe.py` → 125 passed; `scripts/check_runtime_pins.py` structure check green. **Not executed**: the full archive download plus a real `gpg --verify` — evermeet's origin `e.deolaha.ca:4242` kept answering **429** (a 30 B `text/plain` error body) to this machine, and the 26 MB archive crawled at ~45 KB/s before being cut. That is a local network boundary, not a code regression. The defence in that shape was checked: `_download_file` (no retries) writes the 429 body in as the archive, the signature tier then feeds non-zip bytes to verification → `_hard_fail`/exception → the release path terminates, so it cannot ship silently. "Download in full and verify against the new endpoint" can only be proven by the first macOS runner run. **Handed back to the user**: trigger `build-release` once manually and confirm `[build] ffmpeg (evermeet.ca release) official signature verified (ffmpeg), measured SHA256=…` appears, with the matching ffprobe line.
- **Doc parity**: `AGENTS.md`'s "release-chain runtime binaries must be fail-closed pinned (SEV-10)" gained the macOS endpoint-shape constraint, and "adding/removing a release ffmpeg source means changing three places together" now names the two extra macOS registration points (`_EXTRA_EXECUTABLE_URLS` and `_RUNTIME_GPG_SIGNATURES`); `.agents/skills/runtime-pin-verification/SKILL.md` gained a "macOS source endpoint constraints" section; the probe commands and readings live in `docs/agent-reference/measured-evidence.md` under "2026-10-18 re-measurement · evermeet macOS source endpoint removed".

### v4.5.0-dev (2026-10-18) — CI fix: the vbs-behavior-test job installed only pytest, so all 11 cases errored in setup (ModuleNotFoundError: No module named 'distro')

- **Symptom**: on a manual CI run the `vbs-behavior-test` job (windows-latest) went red — all 11 cases of `tests/test_stop_recording_vbs.py` errored during setup with `src/node_install.py:10: import distro` on top of the stack; one warning `Unknown config option: asyncio_mode` (pytest-asyncio missing) came along.
- **Root cause (not the test file)**: the test file itself imports only the standard library plus pytest; the failure comes from three **autouse** fixtures in `tests/conftest.py` — `_clean_credential_caches` (`from src import spider` -> `src/__init__.py` -> `src/node_install.py` top-level `import distro`), `_hermetic_danmaku_hub` (`import src.danmaku_monitor`, same src import chain), `_pin_identity_translation` (`import i18n` -> top-level `from loguru import logger`). Running *any* pytest case in this repo therefore requires the **whole requirements.txt**, regardless of what the test file imports; the same holds for running a single src-independent file.
- **Fix (align the environment, do not add a skip channel to the fixtures)**: the job now installs `requirements.txt pytest pytest-asyncio` through `.github/actions/retry`, and `timeout-minutes` goes 10 -> 20 (PySide6-sized wheels take minutes). The alternative — making fixtures silently no-op when the module is not loaded — would reopen the MIN-2264 class of fake green (fixtures silently ineffective, pollution cases degrading into "passes alone, fails in the suite") and was rejected. The cost is acceptable: this workflow is manual-trigger only, and build-release.yml's Windows build job already installs the same list on the same runner image.
- **Regression lock (new `tests/test_ci_pytest_env_parity.py`, 7 cases)**: every job that mentions pytest (running or installing it) must also `pip install -r requirements.txt`. Pinned both ways — the known pytest jobs (`test` / `concurrency-test` / `vbs-behavior-test`) must be detected, while `setup` / `static` / `deps-audit` / `integration-verify` / `build-verify` must not (setup only echoes `pytest_version=9.1.1`). The detector reads only `run` and `with.command` and strips bash comment lines: otherwise the `# pytest ...` comment block in the setup constants step would count "mentions pytest" as "runs pytest" and dilute the verdict.
- **Two mutation checks**: (1) dropping `-r requirements.txt` from that job's command turns the main verdict red and names `vbs-behavior-test`; (2) relaxing the detector to a bare substring turns the setup false-positive case red. Both restored byte-for-byte (compared against backup), re-run 7 passed.
- **Verification**: `pytest tests/test_ci_pytest_env_parity.py + test_ci_retry_action.py + test_ci_frontend_registration.py + test_stop_recording_vbs.py` **35 passed / 0 warning**; `mypy` (no path args) Success over 247 files; `black --check`, `isort --check-only` and `scripts/check_annotations.py` all rc=0; `ci.yml` still pure CRLF after the edit (991 CRLF, 0 bare LF).
- **End-to-end live verification (DoD step 2)**: not applicable — a pure CI engineering change touching neither the recording pipeline nor source selection nor ffmpeg arguments. **Handed back to the maintainer**: commit, push, then trigger CI manually once to confirm `vbs-behavior-test` turns green.

### v4.5.0-dev (2026-10-18) — runtime pins re-pinned to upstream node v24.22.0: root cause and handling of the four-platform release-chain failure

- **Symptom**: four platforms (`windows-x64` / `linux-x64` / `linux-arm64` / `macos-arm64`) aborted simultaneously with `[build][FATAL] node-v24.22.0-*.zip|tar.gz SHA256 mismatch`, while the expected values were still the five `v24.21.0` hashes.
- **Root cause (not an integrity alarm)**: `_download_nodejs` takes the **first `lts` entry** of `https://nodejs.org/dist/index.json`; after upstream published `v24.22.0` (Krypton) on 2026-10-14 that entry replaced `v24.21.0`, so the artifact name switched to `node-v24.22.0-*` while the table still held the previous version's values. This is exactly the human gate documented in the `_PINNED_RUNTIME_SHA256` comment ("the moment upstream ships a new LTS this block mismatches"), not a compromised build machine.
- **Where the values came from (official channel, not self-computed)**: `https://nodejs.org/dist/v24.22.0/SHASUMS256.txt` cross-checked line by line against the cleartext body of the same version's `SHASUMS256.txt.asc` — **all 34 lines identical** (same rule as 2026-09-22, **signature not verified**; the slot's `fingerprint` in `_PIN_SOURCE_TABLE` is still empty, so the online layer does not adopt it). The resulting five values match all four "actual" hashes reported by CI **digit for digit**, independently confirming "the values are right, only the version drifted".
- **Change**: the node × 5 slots in `build_exe._PINNED_RUNTIME_SHA256` now carry the official `v24.22.0` values (`macos-x64` did not fail in this matrix, but shares the same source, so it was updated in the same pass — otherwise only the next mac build would go red); the slot comments' version and source URL were corrected, and the 2026-09-22 readings are kept as history.
- **Rejected handling**: (1) never backfill the hashes CI reported (that would freeze "the build machine is compromised" as the baseline); (2) never hard-code a version for "latest LTS" in `_download_nodejs`, which would disable version-drift detection entirely.
- **Verification**: `check_runtime_pins.py --strict` rc=0 (all 5 runtime keys green, the four macOS slots still on the signed mode); `pytest tests/test_build_exe.py` **124 passed**, 0 warnings; end-to-end download of `node-v24.22.0-win-x64.zip` (37,733,703 B) hashes to `f9683a19…`, digit-for-digit equal to the pinned value. The remote release chain still needs a re-run to confirm (cannot be run locally).

### v4.5.0-dev (2026-10-18) — SR-06 closed: `.agents/skills/` is now git-tracked (28 files committed) + new `tests/test_skill_agents_consistency.py` (12 regression locks), so the CI required check no longer fails deterministically on a clean checkout

- **Root cause**: `.gitignore` excluded the whole `.agents/` directory and `.agents/skills/` was never tracked (`git ls-files .agents` empty), so `scripts/check_skill_agents_consistency.py` treated "directory missing" as rc=2 (the gate itself is broken); that gate is one of the `needs` of the required check `ci-summary`, so every remote CI run went fully red (finding SR-06 in `docs/worklog/CODE_REVIEW_2026-10-04.md`, confirmed red against the remote API). The maintainer's machine has the directory, so local runs were permanently green while clean checkouts were permanently red.
- **Why tracking rather than "skip when missing" (confirmed with the user before acting)**: the skip route would make this required check **never actually execute** on CI - turning "permanently red" into "permanently idle", which contradicts this repo's rule that failure signals must not be downgraded. Tracking makes the judgement run for real at every merge boundary.
- **The pattern must be "exclude contents + re-include the subdirectory"**: `.agents/*` plus `!.agents/skills/`. With a directory-level `.agents/`, git stops descending into it and the re-inclusion is void - measured locally: after reverting to `.agents/`, `git status --untracked-files=all .agents` dropped from **28 entries to 0** (exactly the original SR-06 state). `test_gitignore_reincludes_skills_dir_but_not_sibling_dirs` pins this; the literal `.agents/` must not reappear.
- **`.dockerignore` still excludes `.agents/` entirely**: the image does not need the skills; that is unrelated to tracking, and AGENTS.md now states the split explicitly.
- **New `.agents/skills/.gitattributes` pins `*.sh text eol=lf`**: the repo has `core.autocrlf=true`, which turns LF into CRLF on Windows checkout, so the shebang of `start-server.sh` / `stop-server.sh` would become `bash\r` and `/usr/bin/env` would fail to find that interpreter under Git Bash. The attribute file applies only inside that subtree and leaves every other `.sh` untouched; `git check-attr` reports `text: set` / `eol: lf` for both, and the shebang in the index reads `bash\n`.
- **12 regression locks** (new `tests/test_skill_agents_consistency.py`): missing directory -> rc 2 / missing AGENTS.md -> rc 2 / table entry pointing at a missing directory -> rc 1 / directory without `SKILL.md` -> rc 1 / frontmatter name != directory name -> rc 1 / no AGENTS.md constraint-source declaration -> rc 1 / reference to a non-existent AGENTS.md section -> rc 1 / external tool skill exempt / consistent case -> rc 0 / unregistered directory at least emits a WARN / ignore-pattern lock / the real repository face self-checks. **The core is the two-tier split**: "directory missing = the gate itself is broken (2)" and "entry points at the wrong place = consistency failure (1)" must never swallow each other.
- **Deliberately left open**: the "directory exists but is unregistered" direction currently only produces a warning with rc 0 (already listed as a gap in section 3.2 of the same review). The new case pins only "the WARN is visible", **not the exit code** - locking rc 0 today would freeze a known defect into a contract.
- **Two mutations**: M1 reverting the pattern to a directory-level `.agents/` reddens `test_gitignore_reincludes_skills_dir_but_not_sibling_dirs` (and git's visible file count drops 28 -> 0); M2 changing the script's "directory missing" branch from rc 2 to rc 0 reddens `test_missing_skills_dir_is_rc2_not_silent_pass`. Both were restored byte-for-byte (`git diff --stat scripts/check_skill_agents_consistency.py` empty) and the repo-wide `MUTATION-` sweep returns 0.
- **Verification**: `pytest tests/test_skill_agents_consistency.py + test_pre_commit_config.py + test_run_gates.py + test_agent_hook_guard.py` gives **105 passed / 1 skipped** (12 passed from the new file, zero warnings); `python scripts/check_skill_agents_consistency.py` exits 0 (5 skill entries consistent); `black` reformatted the new test file and re-checks unchanged, `isort --check-only` rc=0, `mypy` reports 0 issues on both files; `scripts/check_annotations.py` rc=0. `scripts/check_skill_agents_consistency.py` itself is **unchanged** and still pure CRLF (269), while the new test file and `.gitignore` stay pure LF and AGENTS.md stays pure CRLF (548 -> 550).
- **Live end-to-end verification (DoD step 2)**: not applicable - engineering assets and gate wiring only, no recording chain / source selection / ffmpeg parameter is touched. **Hand-back action**: this entry needs to be committed and pushed, then the remote `CI` `static` job re-checked as red -> green.

### v4.5.0-dev (2026-10-18) — the four root documents synced to the real state + slimmed: v4.4.0 and earlier rolled into the archive, the v4.5.0 release notes compressed, `src/config_read.py` added to every tree

- **Measured before acting**: baselines were `README.md` 125,120 B / `README_EN.md` 142,725 B / `CODE_WIKI.md` 480,656 B / `CODE_WIKI_EN.md` 542,868 B. Measured redundancy: 3 / 6 / 4 / 6 fully duplicated long sentences, 0 / 0 / 2 / 2 consecutive blank lines, zero useless formatting markers (rules / empty bold / `<br>`). The real bulk is the **changelog** (31.8% / 55.6% / 42.2% of each file).
- **Synced to the real state (from the worktree changes)**: all four directory trees gained `src/config_read.py` (the tolerant-read layer added on 2026-10-17); both READMEs gained a one-line note under the basic-config section stating the real behavior - a duplicated key inside one section no longer voids the file, it reads as the last value and logs one warning naming section / key / line.
- **Three slimming moves**: ① rolling archive - per the root documents' own stated policy, the 29 v4.4.0 + v4.3.0-dev entries of `CODE_WIKI` and the 2 v4.2.0 / v4.1.0 entries of both READMEs were moved **verbatim** into the matching `docs/changelog/` volumes (written to the archive first, then verified line by line, and only then deleted from the root; `code-wiki-history` volumes went 164 -> 193 entries, `release-notes-history` volumes 17 -> 19, with both index tables corrected); ② the 37 bullets of the v4.5.0 entry in both READMEs were compressed (Chinese 18,928 -> 12,733 B, English 22,333 -> 15,228 B) with every criterion, reading and live-device conclusion preserved, the detail still living in the matching entries of this file; ③ the duplicated environment-variable table between "Configuration" and "Docker Deployment" in both READMEs was reduced to a pointer, and 2 consecutive blank lines each were merged in CODE_WIKI both languages.
- **Pitfall worth reusing**: `pathlib.Path.read_text()` performs **universal newline translation** (`\r\n` -> `\n`), so reading a pure-CRLF document with it and writing it back silently turns the whole file into LF - both READMEs lost their CRLF this way mid-round (CRLF down to 53, bare LF 1,165 / 1,182) and were repaired by re-reading via `read_bytes()` and normalising. Batch edits to these four documents must always go through byte-level `\r\n`.
- **Re-checked**: all four documents remain pure CRLF (0 bare LF); both READMEs align on 14 level-2 headings and 3 release entries, CODE_WIKI both languages on 16 level-2 headings and 35 changelog entries one-to-one; the three doc locks `test_run_gates.py` + `test_regression_2026_09_22_gates.py` + `test_check_annotations.py` give 74 passed / 1 skipped; `check_version.py` PASS.


### v4.5.0-dev (2026-10-18) — version-doc sync: the 4.5.0-dev changelog in CODE_WIKI distilled into the bilingual v4.5.0 README entry (`README.md` / `README_EN.md`)

- **How it was distilled**: the 34 `v4.5.0-dev` entries in the `CODE_WIKI.md` changelog (2026-10-02 ~ 10-17) were sorted into the six subsections the README release entries already use - 9 under New Features / Improvements, 9 under Fixes, 5 under Breaking Changes / Behavior Changes, 4 under Dependency Changes, 5 under Repo Maintenance & Docs and 5 under Tests & Verification; the two languages match section by section in count, heading and order, all inherited from the v4.4.0 entry.
- **Version numbering (executed after the conflict was handed back)**: the instruction read "4.5.0-dev -> 4.4.0, written into README's 4.5.0 entry", which collides with the fact that README already carries a released v4.4.0 entry (2026-09-29 ~ 10-01). After confirmation it was executed as **a new `### v4.5.0 (2026-10-02 ~ 2026-10-17)` entry inserted above v4.4.0**, leaving the existing v4.4.0 entry untouched.
- **Distilled, not embellished**: the body is taken strictly from the CODE_WIKI source - the size (153.21MB / 359 files), coverage (83.10% / 69 modules) and live readings (Huya 660000 / Bilibili 545068 / b23.tv 22747736, etc.) are all numbers already present in the log, with no conclusion added that the log does not contain. The net effect of removing `customtkinter` and adding `PySide6` is stated as its two log readings actually say - "20 -> 21 entries" (20 after the removal, 21 after PySide6) - rather than collapsed into a vague "21".
- **Verification**: both files remain pure CRLF (`README.md` 1221 / `README_EN.md` 1238 CRLF, 0 bare LF); `scripts/check_version.py` PASS and `scripts/sync_metadata.py --check` OK re-run green.

### v4.5.0-dev (2026-10-17) — metadata parity re-scan: 15 target files checked against `pyproject.toml` as the fact source, three documentation drifts fixed (`README.md` / `README_EN.md` / `CODE_WIKI_EN.md`)

- **Fact source values**: `version = 4.5.0` / `requires-python = ">=3.14"` / 21 runtime dependencies / extras dev 7, gui 3, build 1 / three console scripts `douyin-recorder{,-gui,-web}` / 5 `packages` (including `src.gui_qt` and `src.gui_qt.pages`).
- **Machine gates re-verified green first** (so this round only fixes wording, never values): `scripts/check_version.py` PASS, `scripts/sync_metadata.py --check` OK, `requirements.txt` 21 vs pyproject 21 with both set differences empty, `PKG-INFO` runtime `Requires-Dist` equal spec for spec over 21 entries, `uv.lock` root package at 4.5.0 with the same 21 dependencies, `.coveragerc-concurrency` omit 24 vs 24 and `exclude_also` 4 vs 4, and `egg-info/SOURCES.txt` already carrying `src/gui_qt` plus `src/gui_qt/pages`.
- **Three actual edits**: (1) the `README_EN.md` structure tree still annotated `web_api.py` as "FastAPI app" - `fastapi` was removed in v4.4.0 phase 2, so it now reads `Starlette app`, which is what the Chinese side already said at the same position; (2) the `src/ui_fonts.py` entry heading in `CODE_WIKI_EN.md` had been rendered twice, one copy with no body, leaving the EN changelog at 63 entries against the Chinese 62 - the empty copy is deleted and both sides return to 62 vs 62; (3) both README structure trees gained `src/gui_qt/` (`app.py` / `main_window.py` / `theme.py` / `pages/`) - the package is declared by `[tool.setuptools].packages` and `gui.py:main()` delegates to it, so its absence left the GUI entry point with no documented landing place.
- **Carried along (not pyproject-derived, changed after confirmation)**: the `zh_CN.po` key counts in both README trees (780/781) were stale and now read 1127 keys / 1128 entries including the header (1127 keys per catalog, `.mo` N = keys + 1).
- **Unchanged**: `AGENTS.md`, `requirements.txt`, `Dockerfile`, `docker-compose.yaml`, `.gitignore`, `.dockerignore`, `.coveragerc-concurrency`, `config/config.ini`, `DouyinLiveRecorder.egg-info`, `uv.lock` and `build_exe.py` - eleven files checked item by item with no drift.
- **Verification**: after the edits all four documents remain pure CRLF (`README.md` 1168 / `README_EN.md` 1185 / `CODE_WIKI.md` 3010 / `CODE_WIKI_EN.md` 3111 CRLF, 0 bare LF); `check_version.py` and `sync_metadata.py --check` re-run green.

### v4.5.0-dev (2026-10-17) — a duplicated config.ini option no longer voids the whole file: new `src/config_read.py` tolerant-read layer + a Qt monospace family factory (attribution and fix for the three warnings in the user's log)

- **Trigger (user pasted a runtime log)**: in `D:\LiveRecorder\config\config.ini` the option `是否启动时清理陈旧字节码缓存(是/否)` appeared **twice inside `[录制设置]`** - line 5 and line 44, byte-for-byte identical (line-wise diff). configparser defaults to `strict=True`, so the next read raises `DuplicateOptionError` and **not a single key survives the read**: ① `main.py`'s unguarded module-level read makes the recording core die during `import main` (on site, `logs/` contained only `gui.log`, no `streamget.log`); ② the GUI status bar emitted "failed to read config.ini, using defaults" every 10 s.
- **Changes**: ① new `src/config_read.py` (stdlib + i18n + logger only, so the GUI can import it without walking the `config_io` → `main` engine-lock chain): `tolerant_config_parser(preserve_case=)` (`strict=False` + `interpolation=None`, optional identity `optionxform` reproducing the GUI-local closure it replaces), `find_duplicate_options(text)` (mirrors configparser's own reading rules - full-line comments, section headers, both `=` and `:` delimiters, case-insensitive option names), `warn_duplicate_options(path)` (one warning per path+mtime naming section / option / line numbers; the memory set is capped at 32 entries and cleared rather than silently dropping reports). ② Ten read sites wired: `main.py`'s module-level `config` and `_hot_reload_config`; `src/gui_qt/main_window.py`'s `_dynamic_status_info` (together with the now-redundant local closure and the `import configparser` it orphaned) and `_read_config_value`; the preference readers in `src/ui_theme.py` / `src/ui_scale.py` / `src/ui_motion.py`; two sites in `src/ui_fonts.py` (with their in-function `import configparser`). ③ Qt monospace fonts: new `src/gui_qt/widgets.py::fixed_font(point_size=None)` returns the first candidate family actually installed (`_FIXED_FONT_CANDIDATES`), falling back to `QFontDatabase.systemFont(FixedFont)` when none is present; replaced four occurrences of `QFont("Consolas, Menlo, Courier New, monospace")` (`widgets.TerminalText`, `settings_dialog`, `pages/config`, `pages/danmaku`) and removed, in `pages/danmaku.py`, both the "built-then-discarded" `mono` object and the hard-coded `setFontFamily("Consolas")`.
- **Attribution of the two Qt warnings (measured, not inferred)**: `QFont`'s family slot takes a **single** family name. On a machine with Consolas the old string happened to resolve (`QFontInfo` reads back `Consolas`); on the reporter's machine Qt fell through its legacy alias table to `Terminal` because of `styleHint=Monospace` (measured enum value 7 here, matching `styleHint=7` in the user's log), which produced `CreateFontFaceFromHDC() failed ... Family="Terminal"` plus the immediately following `QFont::setPointSize: Point size <= 0 (-1)`. After the fix, constructing a real `TerminalText` under the Windows platform plugin captured **0** Qt messages.
- **End-to-end real-machine verification**: this change touches the config-read layer and the GUI font layer, not the recording chain / source selection / ffmpeg args / platform parsing, so DoD step 2 is exempt by its own rule. Live-side evidence instead: after deleting line 44 from `D:\LiveRecorder\config\config.ini` (pre-change backup kept as `config.ini.bak-dup`; the diff is exactly one line) the strict parser reads the file, `[录制设置]` yields 42 keys, and the duplicated option count returns to 1.
- **Regression locks and mutations**: new `tests/test_config_read.py` (11 cases); `TestMissingKeyWritebackIdempotency` in `tests/test_config_io.py` (2 cases); 3 `fixed_font` cases in `tests/test_gui_qt_units.py` (stubbing `QFontDatabase.families` / `systemFont` so nothing depends on the host font table). Five mutations, all restoring files byte-for-byte: M1 `strict=False→True` → 2 failed; M2 removing the dedupe guard → 1 failed; M3 reverting `main` to `RawConfigParser()` → 1 failed; M4 turning the write-back into an append-style write → 1 failed (**this one only reddened after hardening** - counting occurrences of the key alone cannot catch a whole section being appended twice, hence the added "the write-back product must still be fully readable by a strict parser" criterion); M5 making `fixed_font` return the comma string → 2 failed.
- **i18n**: one new log-template msgid, `config.ini 存在重复配置项，已按最后一次取值读取: {detail}`, registered in all four catalogs and `zh_CN.mo` recompiled (1128 entries).
- **Boundaries left open (handed back)**: ① the repo's **index copy** of `config/config.ini` still holds the duplicated-option version (`git status` shows `MM`) - committing it would ship a self-breaking baseline template, so the user needs to run `git restore --staged config/config.ini`; ② the remaining strict parsers were deliberately left out of this round: `src/web_config.py`×3, `src/utils.py`×2, `gui.py`×2, `build_exe.py`×2, `src/web_api.py`, `src/ttwid.py`, `src/logger.py`, and the twin copy `scripts/douyin_live_recorder_standalone.py` - under a duplicated key they degrade silently through their own `except` clauses and are not crash sites; ③ `D:\LiveRecorder` on the user's machine is an independent source copy, so this fix only takes effect there once the files are synced.
- **Verification**: `scripts/run_gates.py` **10/10 green, rc=0** (black 246 files unchanged; bare `mypy` 245 source files plus the `--platform linux` / `--platform win32` re-runs; `check_annotations.py`; `compile_po --check` in sync at 1128 entries; `check_version` / `check_runtime_pins` / `check_skill_agents_consistency` all OK; the embedded full `pytest` run **4365 passed / 14 skipped / 0 failed with an empty warnings summary**); `pytest --cov=src` total coverage **83.10%** and `scripts/check_coverage.py` **all 69 modules meet threshold** (`src/config_read.py`: 49 statements / 1 miss = **98%**); `basedpyright` **0 errors / 0 warnings / 0 notes**. Line-ending forms re-measured unchanged after editing (still pure CRLF for `main.py`, `src/gui_qt/main_window.py`, `src/ui_theme|ui_scale|ui_motion.py`, `tests/test_gui_qt_units.py`; still pure LF for `src/config_read.py`, `src/gui_qt/widgets.py`, `src/ui_fonts.py`, `src/gui_qt/pages/config.py`, `tests/test_config_read.py`, `tests/test_config_io.py`). All five mutations (M1-M5) reddened their locks and every file was restored byte-for-byte; a closing `grep -rn MUTATION-` sweep returned nothing. `run_gates.py` was re-run once more after these documentation entries as the final-state evidence.
- **AGENTS.md**: the "缺键补写必须幂等" entry now also states the tolerance layer and names the regression locks.

### v4.5.0-dev (2026-10-17) — two `src/ui_fonts.py` defects fixed: font copy failures no longer log nothing, and copy targets are cleaned of Windows reserved device names (1 new log-template msgid, catalogs 1131 -> 1132 keys; `tests/test_ui_fonts.py` 21 -> 23 cases)

> Both items came off the handed-back list; single-file production fix, recording chain untouched.
- **(1) exception collapsed into `None` with zero log lines**: `except Exception: return None` in `install_font_file` now emits `logger.warning(i18n.tr("复制字体文件失败: {name} -> {target} - {type_name}: {err}", …))` before returning `None`. The attribution matters because the caller can only show a **category-level** message (`main_window.py:599/606` carry no OSError detail), so a locked file, a read-only target, a full disk and a source removed mid-copy all look identical in the UI. Following the existing rule that exception logs must name the type and context, `{type_name}` is passed alongside `{err}` - on Windows some exceptions stringify to the empty string, and `{err}` alone would print a blank line. The template is an ordinary literal-first-arg form (no extractor blind spot) and was registered in all four catalogs with `.mo` recompiled. `src/ui_fonts.py` gained `import i18n` and `from src.logger import logger`.
- **(2) `_safe_filename` ignored Windows reserved device names**: added `_WIN_RESERVED_NAMES` (`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`); the base name before the first dot is compared case-insensitively and prefixed with `_` on a hit (idempotent: `_CON.ttf` stays as is). `COM10`/`LPT10` are deliberately not reserved (MSDN stops at 1..9) and `console.ttf`/`NULx.ttf`/`myCON.ttf` only look alike. The cleaned name is what gets persisted into `gui_font_file` and read back on the next start, i.e. a path distributed across machines.
  **The rationale was rewritten against measurement**: the first draft claimed copying to `CON.ttf` raises OSError or produces an unopenable file, and this host disproved it directly - on Windows 10.0.26300 both `CON.ttf` and `AUX.ttf` are created as ordinary files via Python `open()` **and** via `cmd` redirection (`iterdir()` lists them, `getsize` = 8), while writing `AUX.ttf` through the `\\?\` extended prefix instead raises `OSError [Errno 22] Invalid argument`. Same name, different meaning depending on API path and Windows build - which is the actual reason to normalize. Comments and the test note now say "portability defense + measured record" and must not say "this host cannot write it".
- **Real-machine verification (GUI surface, not the recording chain)**: importing the actual system font `C:\Windows\Fonts\cambria.ttc` landed as `app\config\fonts\cambria.ttc`, `exists()` true, **1 792 664 bytes**; the failure surface (source pointed at a non-existent subpath) returned `None` and wrote exactly one warning line `复制字体文件失败: nofile.ttf -> …\config\fonts\nofile.ttf - FileNotFoundError: [WinError 2] 系统找不到指定的文件。` - type name and target path included, which is precisely the information the fix used to drop.
- **Regression locks and mutations**: `tests/test_ui_fonts.py::TestInstallAndRegister::test_install_font_file_logs_copy_failure_with_reason` (shutil replaced through a module-namespace shim, `logger.add(level="WARNING")` capture with `logger.remove` in `finally`) and `…::test_safe_filename_prefixes_windows_reserved_device_names` (6 reserved names + idempotency + 5 boundary names that must not change). All five mutations behaved as expected: A1 removing the warning reddens the log lock and leaves the reserved-name lock green; A2 removing the reserved-name branch does the reverse; A3 loosening the comparison into substring matching reddens the boundary case (proving the `console.ttf` assertion actually bites). Every mutation restored byte-for-byte.
- **AGENTS.md**: the "custom font" entry grew from three to **four** hard constraints, adding ④ (failure must log a warning + reserved-name cleaning, with the measured boundary spelled out so nobody re-writes it as "this host cannot write it").

**Verification**: `run_gates.py` **10/10 green rc=0** (black 244 files unchanged, bare mypy 243 source files plus both platform targets, `compile_po --check` in sync at 1133 entries); full `pytest --cov` **4345 passed / 14 skipped / 0 failed / 0 warnings**, total coverage **83.02% -> 83.04%** (the two new cases reach failure branches nothing had executed before), `check_coverage.py` 68 modules pass; basedpyright **0/0/0**; bare `pyright` **0/0/0**; the four catalogs' key sets remain item-for-item equal (1132 keys each) and `.mo` is 1133 entries / 149 505 bytes (N == keys + 1); line-ending forms of `src/ui_fonts.py` and the edited test file re-measured unchanged (each still pure CRLF / pure LF).

### v4.5.0-dev (2026-10-17) — 6 orphan bare-text keys retracted from the i18n catalogs (four catalogs 1132 -> 1126 keys) + a new module-classified change overview section in CODE_WIKI (`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` / `AGENTS.md` / `CODE_WIKI*.md`)

- **Every consumer was disproved before retracting anything** (no blanket "no production call site" rule): an AST sweep over **all string constants** in `main.py`/`gui.py`/`web.py`/`i18n.py`/`msg_push.py`/`src/`/`scripts/`/`tests/`/`web/` - not just the first argument of `T()`/`tr()` - left 5 keys with zero consumers, `停止录制` appearing only as a **value** in `web/app.js`'s own embedded catalog (unrelated to the backend keys), and `开始录制` with 12 consumers, all inside `tests/test_i18n.py`, where `test_load_translations_priority` and `test_set_language_hot_swaps_translator` use it as the sample msgid proving the `.mo`-over-JSON/YAML load priority and hot switching. **So six went, one stayed**: `停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志` were deleted and `开始录制` kept. That coupling is now written into the AGENTS.md blind-spot list so the next pass does not delete it as an orphan.
- **Each catalogue file needed its own removal shape, with syntax validated before writing**: the `.po` loses its `msgid`+`msgstr` block plus the following blank line; the two JSON files need line removal **and** comma normalisation inside the entry region only (no comma on the last entry, commas elsewhere - deleting the final entry would otherwise leave the previous line without its comma and make the JSON illegal), verified by `json.loads` before writing, asserting "keys == original keys - 6" and that the retained `开始录制` value was untouched; `zh_TW.yaml` mixes single- and double-quoted keys (body uses `'key': 'value'`, the tail uses `"key": "value"`), so matching only double quotes would have deleted 2 of 6 - an assertion caught it on the spot (2 != 6). Immediate reading after the retraction: 1126 keys per catalog with item-for-item equal key sets, `.mo` at 1127 entries / 149 231 bytes (N == keys + 1), and `extract_i18n_strings.py`'s "suspected redundant" list fell from 247 to 241; the concurrent package then registered its own template, so the current state is 1127 keys per catalog and `.mo` N=1128 / 149 399 bytes.
- **New module-classified change overview section in CODE_WIKI** (one section per language, placed before the changelog with a matching TOC anchor): 11 module subsections, each entry recording type / paths / description plus [breaking] [configuration] [dependency] [string contract] tags. The scope line states the baseline `72d1664` (HEAD at session start) -> current worktree, covering committed (`553b036`, committed by someone else mid-session), uncommitted and index-only changes; no files were deleted, the only removals being those six catalogue entries. **Both languages render from one shared data table**, with built-in self-checks: matching subsection counts, per-section entry counts and numbering order, no CJK left in the English text outside code spans, and no `TODO`/placeholder/ellipsis - and the checks did catch two of my own defects (the English tags once rendered in Chinese as `[依赖]`, and an ellipsis left inside a code sample); both are fixed.
- **A concurrent work package is not this agent's and was excluded honestly**: `src/config_read.py` and `tests/test_config_read.py` (both untracked) plus edits to `main.py`, `src/gui_qt/{settings_dialog,widgets,danmaku}.py`, `src/ui_{motion,scale,theme}.py` and `tests/test_config_io.py` landed while this round ran. The template it adds, `config.ini 存在重复配置项，已按最后一次取值读取: {detail}`, **was briefly unregistered**, which made `tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` red for a while (it was then the extractor's only reported miss). This agent did not file it on their behalf, since the wording may still change and a pre-filled entry would just become another orphan; that package registered it itself afterwards, and the re-check reports 0 missing.

**Verification**: after the retraction `scripts/compile_po.py --check` reports `.mo` in sync with `.po` (1127 entries); the locks relevant to this agent's work - `tests/test_i18n.py`, `test_i18n_catalog_coverage.py`, `test_ui_fonts.py`, `test_gui_qt_label_parity.py` - give **67 passed**; all four catalogues re-measured unchanged in line ending and BOM (pure CRLF, no BOM). The one transient red point belonged to the concurrent package's then-unregistered template and was unrelated to this retraction; that package has since registered it.

### v4.5.0-dev (2026-10-17) — AGENTS.md re-verified and trimmed: 6 claims corrected against measurement, 3 `file:line` references turned into anchors, one-off readings relocated (`AGENTS.md` / `docs/agent-reference/measured-evidence.md`)

> The request was "scan the workspace, sync AGENTS.md to the changes, then slim it". One fact reframes the first half: **a commit landed mid-session (`553b036`, 22:13:55, not made by this agent)** that already contains everything done earlier in the session, so the measured change set since HEAD is a single file - `config/config.ini` +1 line - and that line is corrupt.
- **The duplicated key in `config/config.ini` (measured, restored)**: `是否启动时清理陈旧字节码缓存(是/否)` appeared on both line 5 and line 44, inside `[录制设置]`. The consequence is not cosmetic: the repo parses config with `configparser.RawConfigParser()` (default `strict=True`), and reading the file raised `DuplicateOptionError: ... option '...' in section '录制设置' already exists` - i.e. the tracked baseline had become unreadable. The duplicate line was removed and the worktree re-verified equal to HEAD. **The writer-side root cause is NOT located and no claim of a fix is made here**: running `read_config_bool` against a present key writes nothing, and `config_parser.write()` emits the key exactly once, so the shape is "two writers holding different snapshots", not "the append path always duplicates". A full `run_gates.py` re-run afterwards did not reproduce it either (key count still 1), which is consistent with a race rather than a deterministic path. The staged copy in the index was left untouched (whether to run `git restore --staged config/config.ini` is the user's call). The hazard itself is now recorded in AGENTS.md's config section.
- **Claims audit: 69 machine checks, 6 corrections.** The script compares pyproject/requirements, symbol existence, collected case counts, and path/anchor existence. Corrections: (1) design tokens **26 -> 25 keys x 3 themes** (AST count over `_LIGHT`/`_DARK`/`_HIGH_CONTRAST`, identical key sets); (2) `ctx.record_danmaku_args` assignments **52 -> 60** (`grep -c 'record_danmaku_args = ' main.py`); (3)(4)(5) three `file:line` references had all gone stale and are now anchors - the danmaku call site `main.py:3595` (really `comment_end = check_subprocess(...)` at 3952), `Dockerfile:112` `COPY . ./` (really `COPY --chown=recorder:recorder . ./` at 149, the literal itself had changed too), and `src/ffmpeg_install.py:583` (really 594); (6) counts that move with the number of files (black `239/242 files`, mypy `241 source files`) are no longer cited as constants - black counts scanned files, mypy counts Python modules, and the two are never equal. Two apparent drifts were disproved on the spot: `MAX_FRAMES=12`/`MONO_SCALE_FACTOR=0.9` exist with `Final[...]` annotations (my regex missed them), and the "8 cells" in `tests/test_ci_retry_action.py` means the 8 entries of `_BEHAVIOUR_CASES`; its collected count of 12 is 8 behaviour + 4 structure locks.
- **Two new durable conventions added** (registration, not trimming): code references should use anchors (symbol or unique statement fragment) rather than `file:line`, because one audit round alone turned up three dead coordinates; and missing-key write-back must stay idempotent, with a reproduction test (run read + write-back twice over the same file and assert the key still occurs once).
- **Trimming used relocation and merging, not deletion**, matching the "与根文件的分工" section of the reference doc: five groups of one-off readings moved verbatim into `docs/agent-reference/measured-evidence.md` (19 341 -> 24 042 B) leaving constraint + pointer behind (right-edge-fit pixel readings, the `sync_http` reuse gain, PySide6/`Qt6WebEngineCore`/`QT_BLOAT_FILES` sizes, gate file counts, the version-alignment timeline and the exclude-anchoring before/after readings). Four merges/compressions: two bullets that shared one heading were re-titled to their actual subjects (the `Tkinter after` self-renewing chain and the stop/exit single-flight gate - a migration-era copy-paste of the heading, not duplicated content), DoD step 5 now points at the cleanup section, two `[历史注]` clauses became single lines, and the falsified collector one-liner lost its duplicated code. **Size reported straight: root file 157 364 -> 158 266 B (+902)**, because this round added two constraints while the trims only moved readings out. The remaining candidates (the MID-63 incident chain, the Starlette ⑥⑦ verification note, the `.superpowers` registration history) are all "why" content - squeezing them further would delete judgement text, so they are handed back as levers with their cost instead of being cut.
- **Redundancy measured before editing**: 547 lines / 93 696 characters, 0 trailing-whitespace lines, 0 multi-blank runs, only 6 exactly duplicated lines and all of them structural (``` , ```bash , >), and just 3 pairs of >120-character bullets above 0.45 similarity - one is the Black/isort "取值" sub-heading (false positive), one was DoD step 5 vs the cleanup section (now a pointer), one was the 3.14 breaking-change list vs the concurrency section's `get_event_loop()` detail (now registered in one place). Re-measured after trimming: duplicate bold openings are back to zero apart from the structural "取值", and 2 high-similarity pairs remain, both justified.

**Verification**: `run_gates.py` **10/10 green rc=0** (black 244 files unchanged, bare mypy 243 source files plus both platform targets, `compile_po --check` in sync at 1133 entries, its embedded pytest **4345 passed** with an empty warnings summary); AGENTS.md's three real readers checked separately - the gate bash block `scripts/run_gates.py` parses was not touched, `scripts/check_skill_agents_consistency.py` rc=0, and `tests/test_agent_hook_guard.py + test_run_gates.py + test_regression_2026_09_22_gates.py + test_ci_frontend_registration.py` give **118 passed / 1 skipped**; both edited docs re-measured as pure CRLF (bare-LF 0). Being a documentation-only change, DoD exemptions apply: gates + doc parity + log + scratch cleanup, with the live end-to-end step not applicable.

### v4.5.0-dev (2026-10-17) — approved i18n items B+C: 9 Qt button icons restored (existing keys reused, zero new entries) + 21 Chinese raise messages wired to `tr()` at the production point (16 new msgids, catalogs 1115 -> 1131 keys) (`src/gui_qt/main_window.py` / `src/gui_qt/pages/{dashboard,config,runlog}.py` / `main.py` / `src/spider.py` / `src/web_models.py` / four catalogs + `zh_CN.mo` / new `tests/test_i18n_raise_site_tr.py`, `tests/test_gui_qt_label_parity.py`)

> Only the two items the user approved landed here (item A, the catalog-coverage lock, was done earlier the same day).
- **B root cause, all 9 buttons**: `action_button("📥  最小化到托盘")` followed by `set_text(btn, T("最小化到托盘"))` - `set_text` applies and registers immediately, so the icon-bearing construction label is overwritten by the bare registered key at startup and on every `retranslate_all()`. Neither line looks wrong alone. Fix: both places use the **same msgid**, taken from the **existing Tk three-space keys** (`▶   开始录制` etc.), so the catalogs gained **nothing**. Sites: sidebar 2 (`main_window.py:256-259`), dashboard 4 (`:76-79`, `:104-107`), config 2 (`:55-58`), runlog 1 (`:50-51`). Behavioural evidence via offscreen real widgets: 7 page buttons + 2 sidebar buttons read through `text()` still carry their icons after `retranslate_all()` in `zh_CN`/`en_US`/`zh_TW` (e.g. `▶   Start Recording`, `🗑   清空日誌`). Also measured: `MainWindow` runs its own language detection, so a probe must pin the language before reading labels (same rule as AGENTS.md's existing pitfall ⑤).
- **C criterion was "does this message ever get displayed", not "is it Chinese"**: 21 sites (`main.py` 12 / `src/spider.py` 3 / `src/web_models.py` 6; 16 unique msgids) now build their message through `i18n.tr()` at the raise point. The reason is that these messages are interpolated as the `{reason}` argument of a log template that **is already** translated - the template looks up, the message never does, so registering the bare text would only add dead entries. Three f-string sites were rewritten into the constant-template + named-argument form required by invariant ① (`无法从链接中解析 TwitCasting 主播 ID: {masked_url}`, the Weibo twin, and five `字段 {field} 必须是…` templates); `src/web_models.py` therefore gained `import i18n` (i18n depends only on stdlib + loguru and never points back at `web_*`, so no cycle). `extract_i18n_strings.py` reports **0 missing**; the four key sets are item-for-item equal (1131 keys each); `.mo` recompiled to 1132 entries / 149 357 bytes (header empty msgid included, N == keys + 1). Runtime check on the real functions, per language: `Path is empty, room ID missing`, `欄位 web_auth_enable 必須是布林值`, `房間號含非法字元`, with `{field}` filled by the caller.
  10 messages deliberately left unregistered and pinned by **set equality** of the allowlist: the nine `XhsUrlError` texts (both `except XhsUrlError` handlers and `main._resolve_xhslink_com` read only `e.code`; the message never displays) plus one sentence that is English apart from the single Chinese character 原 - translating it would mean re-translating English. The three Douyu sites in `src/spider.py` were already `i18n.tr()`-shaped and untouched.
- **Two new locks + 13 mutations**: `tests/test_i18n_raise_site_tr.py` (allowlist set equality for unwrapped sites, four-catalog coverage for the wrapped ones, anchors against a vacuous pass) and `tests/test_gui_qt_label_parity.py` (AST equality of construction label vs registered key, an emoji-pair floor, catalog membership). Twelve of the thirteen mutations matched their expectation; **the thirteenth was my expectation being wrong, not the lock**: for E2b (same key, icons stripped throughout) I wrote "green", and it turned red on the `assert 8 >= 9` emoji-floor branch - exactly where it should bite. Every mutation restored byte-for-byte. Case-count accounting: full `pytest` 4331 -> **4343**, of which +4 are the new locks and **+8 come from `tests/test_test_hygiene.py`'s four checks that are parametrized over the files in `tests/`**, each now visiting the two new files (a collection-surface change, not new assertions).
- **End-to-end on real rooms (DoD step 2, one per affected platform)**: `python tests/test_huya_live_collector.py https://www.huya.com/660000 20` -> **PASS, 2 danmaku / 206-byte SRT**; `python tests/test_bili_live_collector.py https://live.bilibili.com/545068 20` -> **PASS, 33 danmaku / 2 642-byte SRT** (the two `.srt` files were this run's artifacts and are removed per the cleanup rule). The changed `main.py` sites live in the hy.fan/b23.tv short-link error branches and the `src/spider.py` sites in malformed-link branches for TwitCasting/Weibo/TTingLive, so real rooms exercise the success paths that these branches do not overlap; the incremental run establishes that the import and parse chains were not knocked askew.
- **Two AGENTS.md writebacks**: key convention #14 gains "blind spot ⑤ (raise-site messages)" with its admission test, and the "GUI static labels go through the `T()` registry" pitfall gains clause ⑦ (a Qt construction label and its `T()` key must be the same msgid). **Handed back**: after B, seven bare keys (`开始录制`, `停止录制`, `重新读取`, `保存 URL 配置`, `打开下载目录`, `高级设置`, `清空日志`) have no call site left (AST-confirmed; `最小化到托盘` and `彻底退出` are still used by `gui.py:782` and `src/gui_qt/tray.py`). Orphan entries trigger no gate failure and cleanup was not in scope for this batch - whether to retract them from the catalogs is the maintainer's call.

**Verification**: `run_gates.py` **10/10 green** (bare mypy 241 source files, black 242 files unchanged, both platform targets, `compile_po --check` in sync at 1132 entries); full `pytest --cov` **4343 passed / 14 skipped / 0 failed / 0 warnings**, total coverage **83.02% (unchanged from the previous round)**, `check_coverage.py` 68 modules pass; basedpyright **0 errors / 0 warnings / 0 notes**; bare `pyright` **0 errors / 0 warnings / 0 informations**; `extract_i18n_strings.py` 0 missing; line-ending form re-measured per catalog file (`.po`, both `.json`, `.yaml`: pure CRLF, no BOM, bare-LF count still 0 after appending); `git status` free of scratch files and the `MUTATION-` sweep empty. Stated boundary: for these 16 strings `en_GB` equals `en_US` - none contains an `-ise/-ize`, `canceled/cancelled` or `catalog/catalogue` divergence, and inventing one would break the catalogs' existing practice of splitting sides only on real differences (22 divergent entries exist today).

### v4.5.0-dev (2026-10-17) — test-side fix for the Windows-only red case, three-way tool-version convergence, `pyrightconfig.json` to make IDE findings reproducible, coverage re-run (`tests/test_ui_fonts.py` / `.github/workflows/ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json` / `tests/test_pyright_config_parity.py`)

> This batch lands the four items the previous report handed back: (1) fix the only failing case touching tests only, (2) resolve the three-way black/isort version drift, (3) run coverage, (4) resolve "Pylance cannot be evidence". No production logic changed.
- **(1) root cause and fix for `test_filename_is_sanitized` (tests/ only)**: the `:` in the fixture name `font:with|weird*chars?.ttf` makes Windows resolve it as an **alternate data stream** of a file called `font` - measured: `iterdir()` lists only `font`, `exists()/is_file()` are true because the stream can be stat'ed, but `shutil.copy2` raises `FileNotFoundError [WinError 3]`, which `src/ui_fonts.py` collapses into `return None`. Hence red on this host, green on Linux CI. The fix splits the two concerns: **the illegal-character half moves to a pure-function case** (calls `_safe_filename` directly, no filesystem, identical semantics on both platforms), while the fs case uses a name both platforms can create but that still needs cleaning (`"  my font  (v2) ..ttf"`), plus a new case for empty/dot-only names falling back to `custom_font.ttf`. `src/ui_fonts.py` untouched. Mutation check: turning `_safe_filename` into an identity function reddens three cases at once (3 failed), restored byte-for-byte.
- **(2) convergence**: the venv runs black 26.10.1 / isort 9.0.2, CI pinned `black_version` at 26.5.1, and the two .pre-commit mirror revs were a third set (25.9.0 / 6.1.0). CI `black_version` → 26.10.1 and both revs → 26.10.1 / 9.0.2 so that venv, CI pin and commit hooks share one value. **Before the bump, `black --check` was run in full under both 26.5.1 and 26.10.1** (26.5.1 unpacked into a temp dir, venv untouched); both report `242 files would be left unchanged` (the count taken after removing a scratch directory mistakenly created inside the repo), so the bump removes a version gap without changing any verdict. Both new revs were confirmed to exist via the GitHub API (`refs/tags/26.10.1`, `refs/tags/9.0.2`, HTTP 200) and `pre-commit validate-config` passes; cloning the hook repos is blocked by this host's proxy, so "the hooks actually install and run" remains unverified here.
- **(3) coverage re-run**: `pytest -q --cov=src --cov-report=json` → **4331 passed / 14 skipped / 0 failed**, total coverage **82.68% → 83.02%**; `scripts/check_coverage.py` → **all 68 modules meet their threshold** (`src/proto/douyin_pb2.py` stays an explicit exemption as protoc output). Six module-level moves: `gui_qt/pages/quality.py` 61.62→84.00, `gui_qt/pages/danmaku.py` 55.11→71.75, `gui_qt/widgets.py` 80.81→87.38, `gui_qt/main_window.py` 64.34→65.07 up; `src/proxy.py` 92.02→84.66 and `src/web_api.py` 84.32→83.90 down - the new cases widen the import closure so lines previously hit incidentally are no longer covered: **a measurement-surface change, not a regression**, and both stay far above their thresholds.
- **(4) making Pylance checkable**: first a shortcut was disproven - Pylance *is* installed here (`.vscode/extensions/ms-python.vscode-pylance-2026.4.101`, and its `dist/server.bundle.js` does start under node), but its license text permits use only inside Visual Studio products, so **no** tool that shells out to that bundle is written here, and AGENTS.md now pins that prohibition. The root cause was then fixed instead: IDE and CLI shared no configuration (this repo had neither `[tool.pyright]` nor `pyrightconfig.json`, so bare pyright used its own default surface), which made IDE squiggles inherently unreproducible. `pyrightconfig.json` now exists: include equals `[tool.mypy].files` item for item, exclude covers both the mypy and basedpyright lists, and typeCheckingMode/pythonVersion/venv match `[tool.basedpyright]` - so **running `pyright` with no path arguments now reproduces the IDE surface**, measured 0 errors / 0 warnings. The parity is machine-checked by `tests/test_pyright_config_parity.py` (5 cases); five mutations each redden it (drop a root entry from include, set typeCheckingMode=off, drop an exclude entry, point venv at a wrong name), config restored byte-for-byte. Two measured details are recorded in the config comments: pyright accepts **only known top-level keys** (a `"//"` key triggers `Config contains unrecognized setting`, so the explanation lives in JSONC line comments) and `$schema` is likewise unrecognised (it printed noise on every run, so it moved into the comments too).
- **Two AGENTS.md updates follow**: the "when can local gates be extrapolated" bullet gains the convergence reading (keeping the original rule that raising a constant is not the same as CI having run it), and the "what pyright and Pylance are" bullet is rewritten against the new fact - it used to say this repo has no pyright config and reproduction requires explicit paths; per AGENTS.md's own rule, a falsified statement in that file is edited in place rather than layered.

**Verification**: `run_gates.py` **10/10 green** (bare mypy 241 source files, black 242 files unchanged, plus both platform targets; `compile_po --check` in sync at 1116 entries); full `pytest --cov` **4331 passed / 14 skipped / 0 failed / 0 warnings**; basedpyright **0 errors / 0 warnings / 0 notes**; bare `pyright` on the new config **0 errors / 0 warnings / 0 informations**; `check_coverage.py` 68 modules pass; `test_ui_fonts.py` 21 passed (was 20 + 1 failed), `test_pyright_config_parity.py` 5 passed, `test_pre_commit_config.py` and `test_run_gates.py` pass; the `MUTATION-` sweep is empty twice, and `src/ui_fonts.py` / `pyrightconfig.json` were asserted byte-identical after restore. Standing boundaries unchanged: no Docker daemon here, and pre-commit cannot clone its hook repos through this host's proxy.

### v4.5.0-dev (2026-10-17) — Metadata parity sync (A1-A8 + B1) + images no longer carry GUI dependencies by default (single `INSTALL_GUI` switch) (`AGENTS.md` / `CODE_WIKI*` / `README*` / `Dockerfile` / `docker-compose.yaml` / `config/config.ini` / `docs/agent-reference/project-structure.md` / new `tests/test_dockerfile_image_gui_arg.py`)

> Baseline: every working-tree change since HEAD `72d1664` (including the Qt session's uncommitted `pyproject.toml` packages and `egg-info/SOURCES.txt`). Fact source `pyproject.toml`: version 4.5.0 / requires-python >=3.14 / 21 runtime dependencies (with `PySide6>=6.12.0`) / extras dev 7, gui 3, build 1 / three console scripts / 5 packages.
- **Machine gates re-verified green first** (so this batch only fixes wording, never values): `check_version.py` PASS, `sync_metadata.py --check` OK, requirements.txt 21 ↔ pyproject 21 sets equal, uv.lock package version 4.5.0 with the same 21 dependencies, `PKG-INFO` runtime `Requires-Dist` equal spec for spec (protobuf's `<8,>=6.33.5` is setuptools normalisation), `.coveragerc-concurrency` omit 24↔24 and exclude_also 4↔4, the 19 shared ignore-list names present in both ignore files, compose's three services ↔ the three entry points, and `python_build=3.14` / `node_version=24` equal across both workflows.
- **A1-A3 (three stale statements in AGENTS.md' dependency section)**: runtime count 20 → **21** (re-check date moved to 2026-10-17, attributing the addition to the window-layer migration), `.[gui]` from "pystray/Pillow" to "PySide6/pystray/Pillow, three entries", and "GUI two-package floors" → **three packages** adding `PySide6>=6.12.0` (the historical note is appended, never rewritten, per 修改注释只增不改).
- **A4-A8 (CODE_WIKI, both languages)**: tech-stack row `tkinter.ttk + pystray + Pillow` → `PySide6 (Qt6) + pystray + Pillow` (the tkinter implementation marked as migration-period retention); the Python dependency table gains a `PySide6 >=6.12.0` row — and on the CN side this also fixes a **broken table row** (PyExecJS and pystray were squeezed onto one physical line, which renders as a malformed row and left CN one row short of EN); both files now have 21 rows with an identical pipe count per row. The tree annotation for `gui.py` now points at `src/gui_qt/`, and the src subtree gains `gui_qt/` plus `ui_i18n.py`/`ui_fonts.py`/`ffmpeg_linux_download.py`/`startup_cleanup.py` (same text in both files, matching the block).
- **B1 (baseline template gains two keys)**: `gui_font` / `gui_font_file` were documented in both READMEs and are read by `src/ui_fonts.py`, yet absent from the tracked `config/config.ini` template — added, because AGENTS.md requires template defaults, code fallbacks and README config blocks to reconcile item by item. This file is **BOM + pure LF** (not CRLF), so it was written in its own form and re-measured. Verdict: the three `[GUI]` key sets are now pairwise equal.
- **C1 (externalised tree reference)**: `docs/agent-reference/project-structure.md` gains the five GUI-layer modules, `gui_qt/`, `startup_cleanup.py` and the two ffmpeg downloaders, and loses the `weverse_auth.py` entry (module deleted 2026-09-23). That file has **mixed** line endings (CRLF-dominant with 17 bare LF), so it was edited with anchored byte-level inserts rather than a whole-file split/join, which would have silently converted those 17 lines. Re-checked: no missing and no ghost entries against the real src inventory, in either tree.
- **Slim images (the only behavioural change here)**: added `ARG INSTALL_GUI=false` — in stage 1 a false value filters `pyside6` out by leading package name before `pip install`, and stage 2 only installs the Qt runtime libraries when true (libegl1/libgl1/libglib2.0-0/libfontconfig1/libxkbcommon*/libdbus-1-3/libxcb-*). Measured, not guessed: PySide6 unpacks to **647.56MB** in the local venv, and with an import blocker installed for PySide6 both `import main` and `import web` still succeed (`gui.py` defers the window layer into `main()`, so it does not touch it at import time either). **The manifests are untouched**: the filter lives entirely on the image side, so the requirements ↔ pyproject equality lock is unaffected (measured: 21 → 20 entries, only pyside6 removed, no collateral, and the two surviving lines are pure comments that pip ignores). The compose `gui` service now passes `INSTALL_GUI: "true"` and uses **its own tag** `:latest-gui` (services with different build configs sharing one image name overwrite the tag each is using); `docker-publish.yml` never passes it, so published images stay slim.
- **New lock `tests/test_dockerfile_image_gui_arg.py` (5 cases)**: (1) every stage referencing `$INSTALL_GUI` declares it before use (ARG does not cross stages; same family as MIN-14) — `_stages` drops the comment-only header bucket, otherwise the stage number in the diagnostic is off by one (measured: it reported 阶段3) — plus a predicate self-check case feeding synthetic sources to prove both "use before declaration" and "no declaration at all" are caught; (2) the default must be false, the filter must be the "grep-out + temp manifest" shape, and PySide6 must still be in requirements.txt **and** pyproject; (3) compose's gui service opts in and uses a different tag from recorder; (4) the publishing workflow must not contain `INSTALL_GUI=true`.
- **Not done and the boundary (must not be read as verified)**: this host has **no Docker daemon**, so "the slimmed image actually runs" and "the GUI=true branch really opens a window" are both **untested in a container**. Substitutes performed: all 6 RUN payloads pass `sh -n` and `bash -n`; the branches were traced with pip replaced by `echo` (`true` → whole manifest, `false`/`TRUE`/empty → temp manifest, i.e. the match is case-sensitive on exactly `true`); compose file passes `yaml.safe_load`. In-container verification is handed back to an environment with Docker.

**Verification**: `run_gates.py` 10/10 green (bare mypy 240 files plus both platform targets, `compile_po --check`, `check_skill_agents_consistency`); the new lock's 5 cases plus `test_docker_publish_workflow`, `test_config_io_backup`, `test_web_config`, `test_i18n_catalog_coverage` and `test_regression_2026_09_22_gates` pass with no warnings; `pytest -q` overall reading is recorded at the end of this round. All six mutations reddened exactly as predicted (stage-2 declaration moved after use / stage-1 default flipped to true / the filter replaced by `cat` / gui loses the flag / gui falls back to the shared tag / the publishing workflow gains a true build-arg), the four touched files were restored byte-for-byte inside a finally block, and the `MUTATION-` sweep came back empty twice.

### v4.5.0-dev (2026-10-17) — i18n blind spot (4) becomes machine-checked: new `tests/test_i18n_catalog_coverage.py` (three locks + mutation proof)

- **Why**: the same day's four-catalog sync showed blind spot (4) had no defence at all - `scripts/extract_i18n_strings.py` and invariant (3) only read the **literal first argument** of `tr()`/`T()`, so `i18n.tr(msgid)` (msgid from a tuple table), `tr(THEME_LABELS[k])` and `T(title)` (a loop variable) are invisible; the Qt sidebar is exactly that shape, which made "catalog entry missing" indistinguishable from "all good" (the extractor keeps reporting 0 missing - a false green).
- **Three locks**: (5-A) msgid candidates resolved from by-name call sites must be present in **all four catalogs**; (5-B) call sites that cannot be resolved are judged by **set equality against an allowlist** (stronger than a count ceiling: a new one reddens, and a retired one that is not removed also reddens) - currently only `src/ui_i18n.py:34`; (5-C) the four key sets are equal item for item (keeping the established "drop the empty header msgid from .po" convention). (5-A) carries two anchor assertions (`found` non-empty, and a nav msgid containing 「控制台」 must be resolved) so "the resolver caught nothing" cannot pass as green.
- **Resolver scope**: the scan surface reuses the extractor's `SCAN_FILES` instead of creating a second list (copying a list is this repo's recurring drift source). Name-to-candidates resolution accepts four binding shapes: module-level UPPER_CASE constants merged across files (for imported tables such as `THEME_LABELS`), same-file local assignments, `for page_id, msgid in ((...))` taken **positionally** (a wrong offset would pull ids like `dashboard` in as text and produce false reds), and formal-parameter positions; lowercase names are never merged across files so same-named locals cannot feed each other. `_INDEX_PASSES=3` iterations converge the two-level chain `_pattern_from_template -> _sentinel_text`.
- **Performance**: the first version walked the tree again per function inside `_binding_index`, measured at 35s per pass; collecting the call nodes once brought it to ~6s, and the three cases share one `functools.lru_cache`d parse (file total 6.5s).
- **Mutation verification** (four mutants, one per bite point, all behaved as predicted with byte-exact restore): M1 replace one nav key in en_US with an equal-length marker key -> (5-A) and (5-C) both red; M2 delete a by-name msgid from zh_TW -> both red; **M3 change `📊  控制台` in source to a form absent from every catalog -> only (5-A) red while (5-C) stays green** (key sets remain equal when all four sides miss it - precisely why (5-A) must exist on its own); M4 turn `tr(self.msgid)` into a literal -> (5-B) red because the allowlist went stale.
- **Deliberately not done**: no production code changed; the 15 Chinese (about 9 distinct) raise-site messages in `main.py`/`src/spider.py`/`src/web_models.py` still bypass `tr()` - registering them only makes sense once they are wired - left for a separate round.

**Verification**: `pytest tests/test_i18n_catalog_coverage.py -q` 3 passed; `test_test_hygiene + test_i18n_migration + this file` 604 passed; `run_gates.py` 10/10 green (bare mypy 239 files, `compile_po --check` in sync at 1116 entries); full `pytest -q` 4303 passed / 14 skipped / 1 failed, the single red still being `tests/test_ui_fonts.py::TestInstallAndRegister::test_filename_is_sanitized` (filename containing `:` resolves to an NTFS alternate data stream on this host; unrelated to i18n).

### v4.5.0-dev (2026-10-17) — i18n four-catalog sync: +5 sidebar nav msgids reached via by-name tr(), key count 1110 -> 1115 (`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`)

- **Scan surface**: `scripts/extract_i18n_strings.py` as the baseline (0 missing over its SCAN_FILES), plus an independent full AST sweep of the 74 runtime `.py` files (5 root entry points + `src/**`, excluding `.venv`/`node`/`ffmpeg`/`__pycache__`/`tests`/`scripts`/`build_exe.py`), walking all four blind spots of AGENTS.md rule 14: (1) every `color_obj.print_colored` literal is already registered; (2) `messagebox.show*` and the Qt text positions (`setText`/`setWindowTitle`/`setToolTip`/`addButton`/`addItem`/`setHorizontalHeaderLabels`) hold no unregistered literals - the only survivors are the brand name `DouyinLiveRecorder`, the decorative `☰`/`🌓` and `'-'`; (3) in `msg_push.py` only the two sample strings inside `__main__` are unregistered; (4) all 15 by-name `tr()`/`T()` call sites were dereferenced (`_THEME_LABELS`/`_MOTION_LABELS`/`STATUS_TPL_*`/`_INSECURE_BIND_ENV_TAIL`/dashboard grid titles) and every value hits the catalog.
- **The single real gap is blind spot (4) showing up as a form drift**: `src/gui_qt/main_window.py:238-242` keeps the sidebar msgids in a tuple and passes them by name (`i18n.tr(msgid)`); Qt uses the **two-space** form while the catalogs only had the **three-space** Tk-legacy form - so under en_US/en_GB/zh_TW the sidebar and the derived page title (`:380`'s `text().split("  ")[-1]`) silently fell back to the Simplified source text. Each catalog gained 5 entries and `.mo` was recompiled.
- **Keeping both forms is deliberate, not duplication**: `gui.py:2110-2114` (`_legacy_main()`, pinned by nine `tests/test_gui_*.py` AST/subprocess locks) still uses the three-space form. The first attempt renamed the keys as "source changed"; the extractor immediately reported 5 missing, so the rename was **reverted in favour of coexistence** - renaming would have broken the Tk sidebar instead. Tooling lesson: a non-ASCII pattern containing consecutive spaces is silently missed by Git Bash `grep`, so orphan verdicts must come from AST constant comparison.
- **Two classes deliberately left alone**: (1) `build_exe.py`'s `[build]` logs (47 strings, developer-facing build output, outside the i18n scan surface); (2) 9 constructor literals such as `action_button("📥  最小化到托盘")` - the next line `set_text(..., T("最小化到托盘"))` overwrites them, so they are neither displayed nor looked up, and registering them would create dead entries. **Code-side follow-up**: the emoji prefix is therefore actually lost on Qt buttons.
- **Panel-visible text that is not routed through `tr()` (registering it would create dead entries, so not registered)**: the ValueError texts of `src/web_config.py::_check_url_target` and `_INTERNAL_TARGET_HINT` (injected as an f-string argument, never looked up), the type errors of `src/web_models.py` (surfaced verbatim through `HTTPException(422, str(exc))`), and 115 raise-site literals in total (`src/spider.py` 87 / `main.py` 12 / 16 elsewhere). Covering them requires wiring `tr()` at the production point first - a code change, outside catalog-sync scope.
- **Frontend and scripts**: `web/app.js` keeps its own four embedded dictionaries (127 keys x 4 languages; panel dotted keys never enter the backend catalogs) - read-only check found them mutually equal, no drift; `StopRecording.vbs` (UTF-16 LE) contains only process-name identifiers, no user-facing text.

**Verification**: `extract_i18n_strings.py` reports 0 missing and no inconsistency line; all four catalogs hold 1115 keys each with identical key sets; `python scripts/compile_po.py` produced `.mo` (1116 entries including the empty header msgid, 147,743 bytes), `--check` reports in-sync, and `gettext.GNUTranslations` reads back 1116 entries; the local GNU `msgfmt --check` exits 0 and its msgid set matches the committed artifact entry for entry (only the header metadata string differs in form). The real nav path `tr(msgid)` -> `split("  ")[-1]` was replayed in-process: en_US yields `📊  Console` / `Console`, zh_TW yields `🎯  畫質監控` / `畫質監控`; no GUI window was launched. `python scripts/run_gates.py` **10/10 green**; `pytest -q` **4303 passed / 14 skipped / 1 failed**, the single red being `tests/test_ui_fonts.py::TestInstallAndRegister::test_filename_is_sanitized`, unrelated to i18n (that case builds a filename containing `:` which `shutil.copy2` cannot handle on this host; neither `test_ui_fonts.py` nor `src/ui_fonts.py` references `i18n`, so it is a Windows-only defect Linux CI never surfaces). Line-ending form was re-measured per file and stays as before (pure CRLF, no BOM); the two date fields in the `.po` header were advanced to 2026-10-17. Live end-to-end verification (DoD step 2): not applicable - no recording-chain / source-selection / ffmpeg / platform-resolver change, not executed.

### v4.5.0-dev (2026-10-17) — GUI window layer migrated to PySide6: 1:1 landing of the prototype visual language + Qt dead-weight pruning in the packaging chain (`src/gui_qt/` / `gui.py` / `build_exe.py`)

> Work-package source: `docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md` (approved by the user on 2026-10-17, "no objection, proceed"). Scope: new `src/gui_qt/` (16 files, 4,189 lines: `app` / `theme` / `shared` / `widgets` / `main_window` / `tray` / `settings_dialog` / `danmaku_monitor` / `quality_monitor` / `recorder` + `pages/` five pages), `gui.py`'s `main()` now delegates to `src.gui_qt.app.main()` (the former tkinter implementation renamed `_legacy_main()`, kept during the migration period); `src/ui_i18n.py` gains the `"qt"` mode and `set_text()`; `build_exe.py` wires in PySide6 collection and adds the `QT_BLOAT_FILES` prune list; `PySide6` double-written into `pyproject.toml` / `requirements.txt`; new `tests/test_gui_qt_{theme,window,units}.py` with 42 cases total; 47 keys added to each of the four i18n catalogues and `.mo` recompiled (1,111 entries).

- **Why migrate instead of staying on ttk**: the prototype's 18/24px rounded cards, three-tier soft shadows and spring motion cannot be implemented natively in ttk (the clam theme has no radii, no per-widget alpha), and Canvas self-drawing does not participate in the layout system's size negotiation; QSS + `QGraphicsDropShadowEffect` reproduce the design 1:1, and `QTableView` / `QTextEdit` ship with virtualization and `maximumBlockCount`, so high-throughput log/danmaku pages need no hand-rolled render throttling. User decision (2026-10-17): migrate to PySide6, restoration scope = full visual language + empty-state guidance / Toast / card hover states.
- **The controller/UI decoupling is this migration's net win**: `recorder` (child-process lifecycle), `danmaku_monitor` (tail sidecar JSONL), `shared` (config arbitration) and `settings_dialog` contain no Qt layout code and unit-test under `QT_QPA_PLATFORM=offscreen` — the old predicament where much of the tk logic could only be verified in a real window is gone.
- **The threading model switches wholesale**: the old `_ui_event_queue + post_ui` pump + 5 `after`-id guards → Qt Signal/Slot (cross-thread Queued connections) + `QTimer`. The stdout reader thread returns to the main thread via a Signal; periodic chains (status 3s / danmaku 1s) hang on `QTimer`, callbacks still wrapped in try/except + 30s rate-limited logging (the old "exception → silence" failure shape is explicitly consumed).
- **The design-token single source of truth is `theme.py`**: the HTML `:root` CSS variables → a Python token table (26 keys × 3 themes) → `build_stylesheet()` computes QSS at runtime and applies it with one whole-window `setStyleSheet`; a theme switch regenerates from tokens without rebuilding the widget tree. QSS only honours objectName selectors (`QFrame#card`) — a bare `QFrame` also hits `QTableView`'s embedded frame.
- **Races are ported item by item, not rewritten** (none of the old traps dropped): the late session_id callback, the `_stopping` reset in `finally` and ahead of the session check, and stop/quit sharing the single-flight gate `_stop_child_once()` (console attachment is process-global state; a duplicate attach takes pytest's stdout down with it).
- **Two packaging gates, neither optional**: ① the spec adds **no collect calls whatsoever** — `collect_all('PySide6')` would drag the whole 647MB wheel (including the 194MB Qt6WebEngineCore) into the bundle; collection is left to PyInstaller's own `hook-PySide6.py` (collects per actually-imported Qt module), with `'PySide6'` excluded only on the CLI/Web Analyses; ② the hook's output **must then be pruned**: the hook collects plugins wholesale per plugin-type directory and plugin link dependencies cascade in — `imageformats` wholesale brings `qpdf.dll` (dragging Qt6Pdf, 4.41MB), `platforminputcontexts` wholesale brings `qtvirtualkeyboardplugin.dll` (dragging the VirtualKeyboard→Quick→Qml quintet, ~14.3MB), and `collect_extra_binaries` unconditionally collects the Mesa software GL `opengl32sw.dll`, 19.68MB. `excludes` cannot reach hook-collected DLLs, so they must be deleted by filename after COLLECT: `build_exe.QT_BLOAT_FILES`, 11 items / 39.25MB, with the same admission criterion as `BLOAT_EXCLUDES` (**provable present in the bundle + unreachable at runtime**), backed by a link-dependency scan of every dll/pyd under `_internal/PySide6/` (zero reverse references, no unresolved imports after deletion) plus a 9s live run of the frozen GUI exe. Post-prune reading: 91.81MB → 192.46MB → **153.21MB / 359 files** (+61.4MB over the stage-5 baseline, inside the proposal's accepted +50~70MB band); details and criteria in `docs/agent-reference/measured-evidence.md`; 2 new regression locks in `tests/test_build_exe.py` (prune entries may not traverse paths / must stay inside the PySide6 dir; only listed files are deleted).
- **Four real problems the tests and gates caught** (all surfaced after the code was written, all fixed): ① `main_window._dynamic_status_info`'s `interval` was unbound when config.ini lacks the `[录制设置]` section (caught by basedpyright `reportPossiblyUnbound`) — fall back to the default before entering try; ② `app.py` resolved `app_root` one level too high for source runs (landing on the project root's parent, misplacing config/ — caught by an assembly test); ③ `pages/logs.py` collided with the bare name `logs` in `[tool.mypy].exclude` and was silently skipped by no-arg mypy (caught by `test_mypy_exclude_never_shadows_source_files`) → renamed to `runlog.py`; ④ a Qt widget's Python wrapper survives C++-side destruction, so `retranslate_all()` must catch `RuntimeError` or one dead entry crashes the whole retranslate pass (caught by `tests/test_ui_i18n.py`'s global-count assertion).
- **i18n**: 47 runtime templates registered in all four catalogues in the same batch (zh_CN.po appended and `.mo` recompiled at 1,111 entries; en_US/en_GB JSON and zh_TW YAML appended as text to preserve existing key order); `src/ui_i18n.py` gains the `"qt"` mode (`setText`) and the `set_text()` entry point. Stubbing subprocess in `tests/test_gui_qt_units.py` must use a `types.SimpleNamespace(**vars(mod))` shallow-copy shim — the R1 lock in `test_test_hygiene` treats `setattr(subprocess, "run", ...)` as a process-wide rewrite.
- **Migration-period coexistence and retirement plan**: the tkinter implementation at the top of `gui.py` is kept (nine `tests/test_gui_*.py` files pin it via AST static locks / subprocess), which is why Tcl/Tk's 5.28MB is still in the bundle; the legacy version retires after verification (git history allows rollback).

**Verification**: `python scripts/run_gates.py` all green 10/10 (black / isort / mypy ×3 platforms on 238 files / check_annotations / compile_po 1,111 entries / check_version / check_runtime_pins / consistency; built-in pytest fallback **4,301 passed with an empty warnings summary**); `scripts/check_coverage.py` **all 68 modules pass** (82.68% total; every `src/gui_qt` module ≥55%, lowest `pages/danmaku.py` 55.1%); basedpyright 0 errors on `src/gui_qt` and the new test files; `scripts/report_bundle_size.py` measured **153.21 MB / 359 files**, toolchain leak "none"; a real build plus offscreen screenshots (light/dark themes × 5 pages + the 85% scale step) show intact layout (the offscreen platform has no CJK font fallback, so glyphs render as boxes — a platform limitation, not a styling defect); the frozen GUI exe ran for 9s alive with a normal window title. End-to-end visual confirmation is handed back to the user: run `python gui.py` and eyeball theme/scale/language switching.

| GUI PySide6 migration | New `src/gui_qt/` (16 files, 4,189 lines), `tests/test_gui_qt_theme.py` (8 cases), `tests/test_gui_qt_window.py` (9 cases), `tests/test_gui_qt_units.py` (25 cases), `docs/gui-redesign/` (design prototype), `docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md`; changed `gui.py` (`main()` delegation + `_legacy_main`), `src/ui_i18n.py` (qt mode + RuntimeError tolerance), `build_exe.py` (spec comments + `QT_BLOAT_FILES` + `prune_qt_bloat()`), `pyproject.toml` / `requirements.txt` (+PySide6 double-write), the four i18n catalogues +47 keys each with `.mo` recompiled, `tests/test_build_exe.py` (+2 prune locks); generated `uv.lock` / `DouyinLiveRecorder.egg-info` regenerated via `sync_metadata.py`; docs `AGENTS.md` ×3, this entry (zh/en), `measured-evidence.md` +size readings. One-off scripts: 3 (i18n backfill / dependency scan / offscreen screenshots, all outside the repo and cleaned up) |

### v4.5.0-dev (2026-10-17) — GUI visual language restyle: brand blue → warm terracotta + warm-neutral palette (`src/ui_theme.py` / `gui.py`)

> Scope: pure presentation-layer recolor, zero functional change. THEMES `light`/`dark` in `src/ui_theme.py` swap 16 slot values (surface_alt / border / text / text_muted / primary / primary_hover / disabled_bg / disabled_fg, 8 per theme); the `Colors` brand and neutral groups in `gui.py` are updated in the same batch (PRIMARY / PRIMARY_HOVER / PRIMARY_SOFT_* / BG_* / CARD_* / SIDEBAR_* / BORDER_* / TEXT_* / MUTED_*). Deliberately untouched: the `high_contrast` theme (an accessibility theme does not follow brand restyles), the `TERMINAL_*` palette (theme-independent by design), the success / danger / warning / on_primary / surface slots (semantic colors locked by the contrast contract), and every font/spacing token in `src/ui_scale.py` (already semantic since stage 6 — nothing to adjust).

- **Design source**: the warm-neutral base + terracotta accent defined by the `docs/gui-redesign/index.html` prototype; the restyle lands only the colors onto the existing theme layer — widget structure, layout, type scale and spacing tokens remain the stage 4-6 system.
- **Why the primary is not the prototype's #C96442**: CONTRAST_REQUIREMENTS forces `on_primary` (white label) vs primary ≥ 4.5 (body-text AA), and #C96442 measures 3.90; the same hue deepened to #B5573A reaches 4.78. The dark theme takes #B85A3F (4.59) — there the primary must also sit ≥3.0 against both surfaces, leaving a narrow luminance window of ~0.13-0.18 that both the lighter #D97757 (3.12 vs white) and darker siblings would breach.
- **Why the dark-theme hover goes darker, not lighter**: `on_primary` vs `primary_hover` carries the same 4.5 contract, and brightening the hover in dark mode falls below it (#C96A4A measures 3.72), so the darker #A8502F is used; the light theme goes the opposite direction with #9C4A2C.
- **Borders cannot take a "nice light gray"**: the contract forces border vs surface / surface_alt ≥ 3.0 (WCAG 1.4.11 non-text), so the light-theme border lands at the warm gray #7A766F — the machine-checked floor between "perceivable border" and "restrained palette".
- **`gui.Colors` and `ui_theme.THEMES` are two same-value landing spots**: brand-color changes must be made in pairs (this entry followed that rule); the neutral group in `Colors` is a brand-statement declaration, while actual widget painting goes through the ui_theme slots.

**Verification**: `python scripts/run_gates.py` all green 10/10 (black / isort / mypy ×3 platforms / check_annotations / basedpyright 0 errors; pytest 4245 passed with 0 warnings); `tests/test_ui_theme.py` 35 passed (all contrast machine checks); `scripts/check_coverage.py` passes for all 51 modules (84.27%); both edited files re-verified as pure CRLF (LF-only count 0); headless smoke: all three themes register and switch via `ThemeManager.apply` (dlr-light@100 / dlr-dark@100 / dlr-high_contrast@100). End-to-end visual confirmation is handed back to the user: launch the GUI and eyeball the light/dark themes.

### v4.5.0-dev (2026-10-17) — GUI right-border clipping fix + selectable UI font (`src/ui_fonts.py` / `gui.py` / `src/ui_kit.py`)

> Scope: `gui.py` gains `_raise_width_to_fit_content` / `_settled_reqwidth` / `Fonts.bind_family` / `Fonts.set_family` / `_activate_saved_font` / `_apply_font_family` / `_refresh_font_menu_values` / `_on_font_change` / `_on_import_font`; three long hint labels now carry an initial `wraplength` and the URL-config hint is wired to `_bind_adaptive_wraplength`; new `src/ui_fonts.py` (SFNT name-table parsing + GDI private font registration + preference IO); `EditorText` / `terminal_text` in `src/ui_kit.py` gain `width=1` and `spacing1/spacing3`; new `tests/test_gui_right_edge_fit.py` and `tests/test_ui_fonts.py`, the wiring-count lock in `tests/test_gui_wrap_hints.py` moves 4 → 5, and 16 keys land in all four i18n catalogues.

- **Root cause of the clipped right border is two-layered**: (1) three long hint labels start with `wraplength=0` (i.e. no wrapping, so a single line of 725–820 px counts as requested width) and two `tk.Text` widgets in `ui_kit` keep the default 80-character width, pushing `root.winfo_reqwidth()` to **1248 > geometry 1120**; (2) Tk grid **clips** a slave whose requested width exceeds its allocation instead of shrinking it, and the deficit is cut off the content column's right edge — the card's right border plus its 20 px margin disappear exactly as the user's screenshot shows (left border present, right border gone).
- **Why `minsize` was not simply raised to the requested width**: that locks the minimum window width at the requested width (measured 1389 px here) and the user can never resize narrower — a usability regression. The implementation does three things instead: raise the **initial geometry** to kill the first-frame deficit, temporarily shrink the geometry to the scale tier's minimum width to read the content's **shrink floor** (measured 1108–1151 px, varies with language/content) and raise only `minsize` to that floor, and clamp everything to `SCREEN_FILL_CEILING` so small screens stay operable.
- **The requested width must be read after it settles**: Treeview column widths are recomputed in the `<Configure>` callback, and `update_idletasks()` does not process Configure events — reading with idle tasks alone returns the stale large-window value (measured 300+ px off), which is why `_settled_reqwidth()` exists. It converges after four iterations and repeated calls do not ratchet the width upward.
- **Selectable fonts: why availability must not be judged by `tkfont.families()`** (the biggest trap here; the measured finding lives in the comment on `ui_fonts.family_resolves`): `AddFontResourceExW(FR_PRIVATE)` succeeds and Tk does lay out glyphs for that family name, but **`families()` never lists it** (Tk enumerates only registry-installed fonts), while a *missing* font makes Tk **fall back silently** with neither an error nor a listing. So "present in `families()`" is neither necessary nor sufficient; the only reliable discriminator between "really loaded" and "silent fallback" is letting Tk resolve the name and comparing it against the fallback produced by a deliberately nonexistent family. Verified by rewriting every `nameID=1` record of a system font copy to one marker name: `Font(marker).actual()["family"]` did return the patched name.
- **Why `woff2` is rejected outright**: Tk obtains fonts through GDI on Windows, which accepts only SFNT containers (`.ttf`/`.otf`/`.ttc`); woff2 is a web delivery format and pulling in a decompression dependency for one GUI dropdown is not worth it, so the import gate refuses it with "convert to ttf/otf first" rather than accepting the file and silently doing nothing.
- **The switch happens in one `configure`, no widget tree rebuild**: `Fonts.set_family()` mutates the cached proportional font objects in place (`family=`) — Tk fonts are named shared resources and widgets hold the name, not a snapshot — so log contents, unsaved edits in the URL editor and both monitor tables survive untouched; `_apply_font_family` then runs `restyle_fonts`, one `update_idletasks` per page, and re-runs `_raise_width_to_fit_content` / `_raise_minsize_to_fit_sidebar` so the post-switch width change is absorbed in the same sync instead of drifting back into the right-border clipping path. The monospace chain (`mono_*`) is deliberately left alone — the log terminal and URL editor are read with character alignment.
- **Display consistency**: sizes and line spacing still come from the single source of truth `src/ui_scale.TYPE_SCALE` (this change only adds 2 px of vertical breathing room to `tk.Text`, since CJK has no descender room and the default leading packs lines together); anti-aliasing is decided by system ClearType, not by anything in Fontconfig; mixed CJK/Latin rendering relies on Windows per-glyph fallback, which is why the preset list prefers families that are present locally and ship CJK coverage.

**Verification**: `python scripts/run_gates.py` fully green (black/isort/mypy on three platforms/check_annotations/basedpyright); `pytest tests/test_gui_right_edge_fit.py tests/test_ui_fonts.py tests/test_gui_wrap_hints.py tests/test_ui_kit.py tests/test_ui_scale.py tests/test_i18n.py tests/test_gui_language_retranslate.py -q` → passed with 0 warnings; on the real machine (1366×768 at 133 % DPI) the geometry probe moved from "reqw 1248 > width 1120 (clipping)" to "reqw 1108 ≤ width 1389, minsize width 1108, zero card right-edge overhang at every width tried".

### v4.5.0-dev (2026-10-17) — release-chain runtime pinning gains an "online source" layer: off by default, and online values are adoptable only when the manifest carries independent authentication

> Scope: `build_exe.py` gains a "runtime pin online sources" section (three-state switch + trust tiers + source table + cache + application entry point), the `--pin-source` CLI flag, wiring into `_pinned_slots()`, version/filename capture in `_download_nodejs`, and a `strict` keyword plus a `bool` return on `_verify_gpg_artifact`; `tests/test_build_exe.py` gains 17 cases and folds `api.github.com` into the source-host allowlist. **Not a single value in `_PINNED_RUNTIME_SHA256` changed**, and the default behaviour is byte-for-byte identical to before this layer existed.

- **Why the hardcoded hashes were not simply replaced by a runtime fetch**: that table is an out-of-band baseline a maintainer copied from an official channel at a point in time, and its strength comes precisely from being **channel-independent**. A runtime fetch puts the expected value and the artifact on the same channel — gyan.dev's `.sha256` document is served by the same server as the archive, and `api.github.com`'s digest lives on the same github.com as the download — so an attacker who swaps the archive swaps the manifest with it, and "fetch manifest → use as expected → compare artifact" passes tautologically. Hence the layer is **off by default** and classifies sources as `signed` / `advisory` instead of trusting them uniformly.
- **Three-state switch (off / verify / adopt)**: `off` (the default) issues no network request at all; `verify` fetches and **only compares against the in-tree table** — a match confirms the table is still current, a mismatch exits with `SystemExit` on the release path and prints the online value for back-filling, and it **never writes** — writing it would skip the "human back-fills the table" gate, which is also the trigger for re-confirming the version generation, the size budget and the smoke run; `adopt` is the only mode that promotes an online value into a verdict. The environment variable is `DLR_RUNTIME_PIN_SOURCE`; an unrecognised value (e.g. the misspelling `verfiy`) warns and falls back to `off` rather than being guessed into another mode.
- **The gate for `adopt` is "the manifest carries independent authentication", not "the manifest was reachable"**: only `trust=signed` slots (a detached GPG signature published alongside it **plus** a pinned 40-hex primary-key fingerprint) whose **manifest itself verifies** may be adopted. Verification reuses the very same `_verify_gpg_artifact` used for artifacts (one judgement only: `GOODSIG`+`VALIDSIG` and the signing key belongs to the pinned-fingerprint key); `strict=False` merely changes the outcome to "do not adopt" instead of "abort the build" — the real fail-closed gate stays at artifact download time. `advisory` slots and "signed but no pinned fingerprint" are always refused and fall back to the in-tree value.
- **`strict` changes how failure is handled, never the judgement**: the original semantics already had two classes — "signature unreachable / gpg unavailable" logs and skips on the local path but aborts on the release path, while "fingerprint not in the ring / BADSIG / no VALIDSIG" aborts on both. Those two classes are now factored into `_skip_or_fail` / `_hard_fail` with the judgements and message wording preserved verbatim (`test_gpg_tool_or_sig_missing_never_passes_silently` and `test_gpg_rejects_every_untrustworthy_shape` had no assertion changed).
- **One shape gate only**: an online value must pass `_SHA256_PATTERN` (64 lowercase hex) before it can be adopted; empty bodies, HTML error pages, short values, non-hex values and GitHub's `sha256:` digest prefix all converge on that single check. Anything unparseable is treated as "not fetched", and failures are **not cached** — one timeout must not pin an entire build's online cross-check to "unreachable".
- **Cache and refresh cadence**: an in-process `(runtime key, slot) -> (timestamp, value)` map with a 24h default TTL (`DLR_PIN_CACHE_TTL`, `0` = refetch every time) and a 30s default fetch timeout (`DLR_PIN_FETCH_TIMEOUT`; manifests are a few KB and should not inherit the 180s artifact-download budget). A build is far shorter than 24h, so in practice it only de-duplicates repeated asks for the same slot within one process. A cross-process disk cache was **deliberately not added**: it would leave an unreviewed state file behind and open a path for "a stale value treated as freshly fetched".
- **The node manifest URL must be built from the version actually resolved this run**: the download point is the newest LTS picked from `nodejs.org/dist/index.json`, which can differ on every build. `_download_nodejs` therefore writes the version and filename into `_NODE_RESOLVED_VERSION` / `_NODE_RESOLVED_FILENAME` before calling `_download_file`, and the source table uses `{version}` / `{filename}` placeholders; when the version is not yet resolved the layer **skips explicitly** instead of building a URL that is permanently 404 — the latter would point the error at "upstream is down" and hide the real cause.
- **Deliberately left unfilled**: the node slot's `fingerprint` in `_PIN_SOURCE_TABLE` is still an empty string, so that slot **cannot be adopted** (an intentional fail-closed state). It only becomes live under `adopt` once the full 40-hex primary-key fingerprint of the Node.js release key is filled in. The two macOS slots (evermeet publishes no hashes) have no source entry and keep the official-signature tier; neither `verify` nor `adopt` touches them.
- **Gate readings (re-run after the change)**: `black --check` reports both touched files unchanged; `isort --check-only` rc=0; `mypy` with no path arguments rc=0; `scripts/check_annotations.py` rc=0; `scripts/check_runtime_pins.py` rc=0 and `--strict` rc=0; `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` **142 passed** (125 before, 17 added). Both touched files re-verified as pure CRLF (LF-only count 0).
- **Live verification (DoD step 2)**: **not run** — the default `off` path is behaviour-neutral, while the non-default paths (`--pin-source verify/adopt`) need outbound access to nodejs.org / gyan.dev / api.github.com plus a local gpg install; all 17 new cases are fully offline with stubs. Handed back to the user: after filling in the Node.js release-key fingerprint, run `python build_exe.py --pin-source verify --no-zip --no-runtime` locally once and review the log.

### v4.5.0-dev (2026-10-04) — GUI modernization stage 6: type-scale rework + global UI scaling + transition motion (`src/ui_scale.py` / `src/ui_motion.py`)

> Scope: new `src/ui_scale.py` (semantic type-scale tokens + spacing grid + scale presets + small-screen downgrade + persistence) and `src/ui_motion.py` (off/subtle/full levels + interpolation primitives + system "animations off" detection + persistence); `src/ui_theme.py` derives ttk padding / rowheight / table fonts from a `ScaleProfile` and encodes the scale segment in the ttk theme name; `src/ui_kit.py` adds the scale segment to the font-derived-style cache key, adds `restyle_fonts` re-pointing plus the `slide_in` / `scale_in_window` / `blend` transition primitives, and makes `DataTable.sync` return the changed rows so the caller can flash them; `gui.py` makes `Fonts` token-driven with in-place resizing, reflows the four sidebar preferences into a 2x2 grid, adds the scale/motion menus and their callbacks, and scales the window and sidebar geometry with the level while clamping to the screen; `config/config.ini` gains two documented keys; each of the four catalogs gains 14 entries and `zh_CN.mo` is recompiled (1048 entries).

- **Why the type scale was reworked**: stage 5 used 12/13/15/20/26 logical px, and **12 vs 13 differ by a single pixel**, so "caption" and "body" were visually indistinguishable — exactly why the sidebar status text and nav items in the user screenshots read as one flat tier. The new scale guarantees at least 1.5pt between adjacent tiers and never less than 10pt for captions: caption 10 / label 11 / body 12 / heading 14 / stat 16 / title 19 / display 28 (point values at 100%). Table/list text is now explicitly named `label` and statistics get their own `stat` tier (previously both reused `body`/`title`, so numbers in a table carried the same weight as body text and scanning had no anchor).
- **Scaling changes only size, never information density**: row height, padding and sidebar width scale linearly, but column counts, card structure and nav item count are untouched. Otherwise "make the UI bigger" would degenerate into "re-arrange the information architecture".
- **Instant effect with no loss of runtime state (what makes this stage possible)**: a `tkfont.Font` is a **named shared resource** and a widget's `-font` refers to the name, not a snapshot, so `Fonts.rescale_all` only calls `configure(size=...)` on the cached Font objects and every referencing widget repaints — **the widget tree is never rebuilt**. Rebuilding would wipe the log contents, unsaved URL-editor text and both monitor tables (the same class of incident as stage 4's "destroy + rebuild every refresh" table flicker). Monospace fonts likewise changed from tuples to Font objects (a tuple is a snapshot and does not follow rescaling).
- **DPI and scaling are two different things**: DPI adaptation is handled natively by Tk's `tk scaling` plus negative point sizes (already true since stage 5, unchanged here); what this stage adds is the **low-resolution screen** dimension — `auto_scale_for_screen` downgrades one notch for small screens (the stricter of the two dimensions wins, so both 1366x768 and 1920x700 downgrade), and `window_size` clamps all four window values to 94% of the screen so a 150% level cannot open a window larger than the display. When the screen size cannot be read it skips the clamp rather than crashing.
- **Point sizes do not scale linearly**: a point is already a DPI-independent physical quantity, so multiplying by the user factor again would push 150% body text to 18pt (~24px @96dpi) and blow apart every row height and card. Hence the gentle `factor ** 0.6` gain (1.30x at 150%, 0.90x at 85%) — users clearly perceive bigger/smaller while the layout survives. Monospace gets an extra 0.9 factor (wider monospace characters drastically reduce how many columns fit per line).
- **The ttk theme name must carry the scale segment**: `theme_create` raises TclError on a second call with the same name and Tk has no "update a registered theme" API. Reusing `dlr-light` after a scale change would keep the old padding/rowheight, so the name becomes `dlr-light@115`. Stale theme names left in `theme_names()` are harmless (Tk does not reclaim them).
- **`restyle_fonts` is mandatory after a scale change**: a `font_style` derived style **copies** the base variant's configure (including padding) at creation time, so after a scale change existing buttons still point at the stale derived style — visible as "the font grew but the button padding did not", most obvious at 85% (buttons look oversized relative to their text; found by reviewing real screenshots). `restyle_fonts` walks the widget tree and re-points every font-bearing button at a style derived from the new theme.
- **Tk capability boundaries (stated honestly rather than faked)**: ttk/clam has no rounded corners and no per-widget alpha. Cards therefore keep a 1px border (which is the flat style anyway) and "rounded corners" only apply to the Canvas-drawn status dot and pill; page switches and dialogs use **offset + size interpolation** (slide-in / scale-to-place) with **no fake fade** — faking one would require screenshot overlays, which are both slow and ugly.
- **Three motion levels, accessibility first**: `off` / `subtle` / `full`, defaulting to `subtle`. The system "show animations" switch (Windows `SPI_GETCLIENTAREAANIMATION`, macOS `reduceMotion`) **takes priority over** the user's in-app choice and forces `off`; the sidebar menu then visibly drops to "Off" and a log line explains why, because "I selected it and nothing happened" would almost certainly be reported as a bug. The `off` level **schedules no `after` and lands the terminal state synchronously** (otherwise widgets stick mid-transition), and immediately stops the in-flight status-dot breathing chain (the only thing in this window that keeps repainting while the UI is otherwise idle).
- **Hard frame cap**: `MAX_FRAMES=12` is taken as the minimum against the caller-supplied frame count, and the `subtle` level halves it again. This is the machine-checkable form of "smooth but restrained" and stops a user picking `full` from saturating the main thread.
- **Flash on changed table rows**: `DataTable.sync` now returns the rows that actually changed (inserted plus value/tag changes) and gui tags them `flash`, blending the background back to normal frame by frame. **The final frame must explicitly remove the tag**: although its colour already equals the normal background, leaving the tag in place makes the next `sync` see "one extra tag" as a change, retriggering the flash and creating a "flashes every refresh" self-exciting loop. The highlight colour is a blend of `primary` and `surface_alt` rather than `success`/`danger`, because good/bad is already expressed by the `downgraded` / `disconnected` tags and reusing semantic colours would conflate two meanings.
- **Sidebar bottom reflowed to 2x2 (a layout defect surfaced by real screenshots)**: stage 5 stacked four full-width "label + dropdown" rows (~344px); adding scale and motion as more rows pushed it to ~470px, and at 85% (window height 629px, sidebar required height 662px) the "Exit Completely" button was pushed outside the window — users saw "only a red sliver of the exit button". The 2x2 layout brings the bottom back to ~200px. `_raise_minsize_to_fit_sidebar` additionally folds the sidebar's **measured** `winfo_reqheight` into the minsize floor (a hardcoded constant inevitably misses some "level x language x translation line count" combination) while still capping it at the current window height so the window stays draggable on screens that are too small.
- **Page slide-in must not end with a bare `place_forget` (a real bug found on screen)**: `place_forget` removes the widget from **every** geometry manager, so a grid-managed page ends up in no manager at all and simply disappears from the window. The correct approach captures the original `grid_info`/`pack_info` before the transition and restores it (after `place_forget`) on the final frame.
- **i18n**: 14 new strings (`界面缩放` / `动效强度` / `自动` / `关闭` / `轻微` / `完整` / `{percent}%`, six parameterised log templates, and the "system animations are off" notice) registered across all four catalogs with `zh_CN.mo` recompiled (1034 → 1048). `en_US.json` / `en_GB.json` are patched by **textual append** rather than a `json.dumps(sort_keys=True)` rewrite: the existing key order comes from the extractor's locale-aware sort and rewriting would produce a ~1000-line meaningless diff (the gate checks the key set, not the order).
- **Tests and mutation verification**: new `tests/test_ui_scale.py` (44 cases: preset set/clamping/type-scale monotonicity/permanently-negative point sizes/window clamping/auto downgrade/parse tolerance/persistence round-trip with comment preservation) and `tests/test_ui_motion.py` (38 cases: frame plan excludes the final frame/frame cap/accessibility priority/controller/`blend` endpoint exactness/persistence); `tests/test_ui_theme.py` had 2 assertions updated (scale segment in the theme name) plus a new re-registration case. **Four mutations verified**: `a11y_priority` (removing system priority) turns `test_system_off_overrides_user_choice` red; `include_final` (frame list includes the final frame) turns `test_plan_excludes_final_frame` red; `frame_cap_all` (removing the frame cap) turns `test_frames_capped_by_max` + `test_subtle_is_shorter_than_full` red; `off_all_three` (removing all three redundant guards on the `off` path: the table value, the short-circuit and `total <= 1`) turns `test_off_returns_empty` + `test_off_runs_terminal_state_synchronously` red. The fourth is what makes the first three meaningful: single-point mutations are masked by the **redundant guards** inside `frame_plan` (removing one still leaves another covering it), so only removing all three proves the invariant itself is tested rather than being a false green.
- **Gate readings**: `pytest` (no coverage) **4184 passed / 16 skipped / 0 failed**; `check_coverage.py` **all 50 modules meet their threshold** (new modules `src/ui_scale.py` 96.1%, `src/ui_motion.py` 80.9%; `src/ui_theme.py` 85.0%, `src/ui_kit.py` 55.4%); `mypy` without path arguments **215 source files / no issues**; `black --check` 216 files unchanged; `isort --check-only` rc=0; `compile_po.py --check` rc=0 (1048 entries). In `run_gates.py`, `check_skill_agents_consistency.py` returns rc=2 (this worktree has no `.agents/skills` directory — a "did not run" rather than a code failure, unrelated to this change); the other 10 items are green. The `--cov` run shows 17 failures plus an `INTERNALERROR`, caused by the harness `sitecustomize.py` safe-delete bulk guard spawning node from a background thread and hitting `WinError 6` (invalid handle) — an environment interception, not a code regression; the same suite without coverage is fully green for comparison.
- **End-to-end verification (DoD step 2)**: **performed**. A real window cycled through 4 themes / 5 scales / 4 motion levels / all five pages / the close dialog / the advanced-settings window with no exceptions (`ALL_OK`), and screenshots at 85% / 100% / 150% were reviewed by hand. The "button padding does not follow", "sidebar bottom overflows" and "page disappears after slide-in" defects were all found in that step rather than by reading code.

### v4.5.0-dev (2026-10-04) — CI tool-version constants aligned with the local install: `isort_version` 9.0.1 → 9.0.2 (removing the last version gap that blocked extrapolating "local gates green" to CI)

> Scope: one line plus three comment lines in `.github/workflows/ci.yml`'s setup-job `consts` block, the matching amendment in `AGENTS.md` "Formatting commands" (the extrapolation-precondition entry), and this entry (CN/EN in sync). `[tool.isort]` was **not** touched, no dependency declaration in `pyproject.toml`/`requirements.txt` changed, and no `.py` source or test file was modified.

- **Why the CI constant was raised rather than the local install lowered**: the local `.venv` carries isort 9.0.2 (`importlib.metadata.version('isort')`), while CI pinned 9.0.1 — one patch apart. Under the "Formatting commands" rule that single gap forced the isort verdict to be labelled "local calibration, not CI-verified". Local 9.0.2 already returns `rc=0` over all 212 files with no silent-skip, so raising CI to the installed version moves the constant toward the configuration actually measured here. Lowering the local venv to 9.0.1 would require reinstalling a package, which the "Risk control (pre-flight)" section routes back to the user. Approved by the user (2026-10-04).
- **One declaration point covers both consumers**: `isort_version` is emitted once (`echo "isort_version=…"`); the lint job and the test job each read `${{ needs.setup.outputs.isort_version }}`, so no second copy needed a matching edit. All four values now match the local install: black 26.5.1 / isort 9.0.2 / mypy 2.4.0 / pytest 9.1.1.
- **Raising a constant only removes the version gap — it is not evidence that CI actually ran**: every reading in this entry comes from this Windows/GBK host. The ubuntu side stays covered by the existing MID-63 defences (`env: PYTHONUTF8: "1"` plus the silent-skip backstop step), not by extrapolation from this change.
- **`uv.lock` intentionally stays at 9.0.1**: CI installs isort with `pip install "isort==<constant>"`, **not** via `uv sync`. The 9.0.1 entry in `uv.lock` is merely what `isort>=5.12.0` (dev extra) resolved to at the last lock and is not coupled to this constant. Since `pyproject.toml` was not modified, the `sync_metadata.py --check` surface (static job plus the metadata regression locks) is unchanged and no `uv lock` recompute was needed.
- **Gate readings (re-run after the edit, so the green run post-dates the last file change)**: `black --check` **212 files unchanged / rc=0**; `isort --check-only --diff` **rc=0, empty diff, no `Unable to parse file`** (`Skipped 17 files` is the expected `extend_skip` set); `mypy` with no path arguments **211 source files / no issues**, `--platform linux` and `--platform win32` each 0, all three additionally re-run with a fresh `--cache-dir` to rule out a stale-cache false green; `basedpyright` **0 errors / 0 warnings** (`filesAnalyzed=212`); `pyright` given the same explicit path set as `[tool.mypy].files` **0/0/0** (its bare default scope differs from the gate and is reference only); `pytest` **4095 passed / 14 skipped / 0 failed / empty warnings summary**; `check_coverage.py` **all 48 modules at threshold (84.89%)**; `scripts/run_gates.py` **10/10 PASS**. The 14 skips are all platform/privilege-gated, not regressions: 6 from the parametrized `test_spider_hardening.py:198` (platforms with no documented offline shape), 3 symlink tests needing a Windows privilege (`WinError 1314`), 2 depending on `os.chmod` permission bits (Windows exposes only the read-only bit), 1 expecting case-sensitive environment variables, 1 expecting SIGKILL self-termination (POSIX-only), and 1 asserting a missing `h2` import (installed here).
- **Live verification (DoD step 2)**: **not run** — nothing in this change touches the recording chain / source selection / ffmpeg arguments / platform resolvers (a workflow constant and documentation only), so the step's precondition is not met. Nothing handed back to the user.

### v4.5.0-dev (2026-10-04) — GUI static labels wired to i18n: `src/ui_i18n.py` (T marker + retranslation registry) + whole-window refill on language switch + web_api error details

> Scope: new `src/ui_i18n.py` (static-label marker `T()`, registry `register`/`retranslate_all`, window title `apply_title`); `src/ui_kit.py` factories (Label/Button/DataTable headings) accept Translatable; `gui.py` static labels wired point by point + language-switch hook retranslates + sentinel values reset to their `tr()` form + tray menu rebuild; `gui.py` runtime strings (`_log`/`_set_hint`/`_warn_chain`/table cells/danmaku stream) and `src/web_api.py` error details all rendered through `i18n_module.tr`; each of the four catalogs +169 entries and `zh_CN.mo` recompiled (1034 entries). Stable machine-code details (`unauthorized`/`rate_limited`/`host_not_allowed`/`insecure_bind_disabled`), config keys, regexes and the security blacklist are deliberately left untranslated.

- **Why a registry instead of destroy-and-rebuild**: static labels (buttons/card titles/headings/window titles) are fixed at widget-creation time; a language hot-switch previously only affected text looked up through `tr()` afterwards. Under Tk, destroying and rebuilding the window would lose runtime state (log contents, URL editor contents, monitor tables) and would make the `after` job handles attached to it raise `TclError` en masse. The mechanism is therefore isomorphic to Qt's `retranslateUi`: register `(weak widget ref, application mode, marker)` and refill on switch — zero state loss, and Toplevel open/close does not leak (weak refs; dead entries are pruned during the refill pass).
- **Single factory wiring point**: `ui_kit.Label/Button`'s `text=` and the second element of `DataTable` columns rows (the heading) accept `str | ui_i18n.Translatable` — passing `T("…")` renders through the catalog at build time and registers under the `text` / `heading:<col>` mode; a plain `str` passes through untouched (dynamically concatenated text does not participate in retranslation). `apply_title(win, T("…"))` covers window titles (Tk titles are a method, not a `configure` option). There are exactly three dispatch modes — `text` / `title` / `heading:<col>` — and mis-dispatch fails silently (title is not a valid configure option, so the resulting `TclError` gets swallowed).
- **Four language-switch behaviours (each pinned by a regression lock)**: `_on_language_change` calls `retranslate_all()` to refill the registry; the sentinel values (`默认画质`/`全部房间`) are reset to their `i18n.tr(...)` form (same rule as key convention #13 — both sides of every comparison use the `tr()` form); dynamic surfaces (status bar/quality table/danmaku table/filter menu/tray menu) are rebuilt or re-rendered; `language` is written back to config.ini. Retranslation failure and the config write-back live in independent `try` blocks (a crash in retranslation must not swallow the persistence step). At startup, `_setup_ui` performs one extra `retranslate_all()`: the few labels built before `set_language` inside `_build_sidebar` (brand, theme menu initial value) are fixed in the import-default language, and the refill keeps the whole window consistent (measured: with the host detecting en_US the brand label used to mix Chinese and English).
- **Runtime-string wiring shape**: constant first arguments of `_log`/`_set_hint`/`_warn_chain` are wrapped in `tr()`; every f-string/concatenation with placeholders is rewritten as `i18n_module.tr(constant template, **kw)` (placeholders are plain identifiers and must match kwargs exactly — machine-checked by migration invariant #2). Table cells (`✓ 同等`/`⚠ 降级`/`已连接`/`已断开`) and danmaku-stream text (`[礼物] `, `（+N 条已省略）`, `暂无弹幕数据`) are translated at the point of production. Module constants passed to `tr()` by name (e.g. `_INSECURE_BIND_ENV_TAIL`) are invisible to the extractor and were registered in the four catalogs by hand.
- **web_api error text**: display details of `HTTPException(status, detail)` and the `message` field of `JSONResponse` all go through `i18n_module.tr`; `_insecure_bind_detail` became a composite template (`bind`/`context`/`action`/`tail`, all four looked up at call time) so the 403 text follows the language switch while preserving the SEV-N03 semantics of reporting the actual listening address. Stable machine-code details are untouched (the front end reads `detail` in `apiError` and toasts it verbatim; translating them would break the contract).
- **Extraction surface extended**: `scripts/extract_i18n_strings.py` and `tests/test_i18n_migration.py` now both recognise `T(...)` (new `T_CALLER_IDS`), so static-label entries are covered by the "catalog coverage complete" machine check (invariant #3); the probe test `test_extractor_sees_T_marker_templates` guards against "the extractor cannot see them, therefore it is always green".
- **Tests and verification**: new `tests/test_ui_i18n.py` (5 cases: render/refill/dead-reference pruning/same-slot replacement/three-mode dispatch) and `tests/test_gui_language_retranslate.py` (3 cases: retranslate + sentinels, tray rebuild, retranslation failure does not block persistence); `tests/test_ui_kit.py` +1 (factory Translatable integration, real window); `tests/test_web_api.py` +5 (login/files/rooms details go through tr, the four-segment composite template, the middleware's machine-code detail untranslated + message translated); `tests/test_i18n_migration.py` +1 (extractor T probe). **All five mutations turned red and were restored byte-for-byte**: factory register removed (`MUTATION-I18NUIKIT`), language-hook retranslate removed (`MUTATION-I18NTRT`), web_api detail reverted to a bare literal (`MUTATION-I18NWEB`), extractor T support removed (`MUTATION-I18NSCAN`), sentinel reverted to a bare literal (`MUTATION-I18NSENT` — the anchor must be the two-line block inside the hook: a single-line anchor also matches the same assignment in `__init__`, which the stub instance skips, so the mutation silently has no effect; hit in practice). Incidental fix: the subprocess probe in `tests/test_gui_wrap_hints.py` used to match four labels by simplified-Chinese source prefixes; once static labels go through i18n the host language decides the rendered text, so the probe now pins the language after construction with `set_language("zh_CN")` + `retranslate_all()` (the same path a user takes when switching back to Simplified Chinese).
- **Gate readings**: `run_gates.py` **10/10 green** (built-in pytest fallback 4095 passed / 0 warnings); full `pytest --cov` **4095 passed / 14 skipped / 0 warnings**; `check_coverage.py` **all 48 modules meet their thresholds** (84.89%, including the new `src/ui_i18n.py`); `mypy` 0 issues; `basedpyright` **0/0/0**.

| GUI i18n wiring | New `src/ui_i18n.py` (~100 lines), `tests/test_ui_i18n.py` (5 cases), `tests/test_gui_language_retranslate.py` (3 cases); changed `gui.py` (54 T()/apply_title sites on static labels + ~60 tr sites on runtime strings + language hook + sentinels + tray `_build_menu`/`rebuild_menu` + `_setup_ui` refill + widened factory-helper parameter types), `src/ui_kit.py` (Label/Button/DataTable accept Translatable), `src/web_api.py` (27 detail/message sites + module-level `import i18n`), `scripts/extract_i18n_strings.py` (T scanning), `tests/test_ui_kit.py`/`tests/test_web_api.py`/`tests/test_i18n_migration.py`/`tests/test_gui_wrap_hints.py` (regression locks and probe language pinning), four catalogs +169 entries each and `zh_CN.mo` recompiled (1034 entries); docs `AGENTS.md` (new convention/known-pitfall entries) and this entry (CN/EN in sync). 5 one-off scripts (wiring/inventory/translation writer/mutation verification, all under `%TEMP%`, cleaned up) |

### v4.5.0-dev (2026-10-04) — Xiaohongshu live-link normalization: `/livestream/<room id>` / dynamic path / `xhslink` short link / share params all wired in

> Work-package source: `docs/worklog/PROPOSAL_2026-10-04_xhs-live-link-normalization.md` (approved). Scope: new pure parsing entry `src/spider.py::parse_xhs_live_url`, wiring into the existing `get_xhs_stream_url` pipeline and `main._resolve_xhslink_com` dispatch, URL-config normalization switched to the same verdict, four-language i18n sync, plus `tests/test_xhs_live_links.py`. No new platform registration — the existing `PLATFORM_HOST` / `_PLATFORM_RESOLVERS` / `start_record` chain is reused as-is.

- **Single parsing entry (pure function, zero network)**: `parse_xhs_live_url(url) -> dict[str, str]` returns `kind` / `normalized_url` / `room_id` / `user_id` and covers four shapes at once — standard live `https://www.xiaohongshu.com/livestream/<numeric room id>`, dynamic-segment live `/livestream/<dynamic>/<numeric id>`, share short link `https://xhslink.com/o/<code>`, and author profile `/user/profile/<id>` (historical monitoring entry preserved). Verdict order is fixed: scheme → userinfo → port → exact host → path. Only `www.xiaohongshu.com` and `xhslink.com` are accepted (suffix spoofing, trailing dots, userinfo spoofing and domain words appearing in the path are all rejected); only http/https, and the normalized output is always https. Default ports are accepted and stripped from the normalized URL. Room ids are **ASCII digits** (`[0-9]+`, not `\d+`, which would admit full-width digits); dynamic segments / short codes / profile ids are narrowed to `[A-Za-z0-9_-]+` so dot segments (`.`, `..`, `%2e%2e`) never reach the normalized URL. The dynamic segment is **preserved verbatim** rather than folded into the standard path.
- **Query allowlist**: only `host_id`, `xsec_token` and `xsec_source` are rebuilt in a fixed order; `timestamp` / `share_source` / `share_id`, the fragment and all unknown parameters are dropped. Live evidence (2026-10-04): the user-supplied short link finally lands on `/livestream/<dynamic>/<numeric id>` whose query actually carries `host_id` / `share_id` / `share_source` / `source` / `timestamp` / `xsec_source` / `xsec_token` — the two auth-related ones must be preserved, the rest exist only for share attribution.
- **Machine-checkable error categories**: `XhsUrlError` carries a stable `code` (`host` / `non_live_path` / `room_id` / `short_path` / `scheme` / `userinfo` / `port` / `format`), and the message **never echoes the raw URL, query token or path** (so `xsec_token` cannot land in logs in clear text; callers that do log the URL still go through `utils.mask_credentials()`). A `/livestream` prefix whose room segment is invalid always maps to `room_id` ("room id missing or non-numeric"), fully separated from "not a live room or author profile".
- **Wired into the stream pipeline**: `get_xhs_stream_url` now runs the shared parser before building any credentialed request, so an invalid link returns its `error` category and **issues no request at all**; short links resolve the redirect first (keeping SEV-2214's two gates: domain-family allowlist plus `web_config._host_internal_reason` internal-address check), then the landing page goes through the same parser again — a note/search landing page fails with its category and no credentialed request is sent to that landing page. The return value gained two stable fields, `room_id` and `normalized_url`.
- **Offline rounds can now create a job (the real defect fixed here)**: the anchor name is read from `liveStream.roomData.hostInfo.nickName` — live probing confirms that field still exists when `liveStatus="end"` (not started / already ended), whereas the old code only pulled `host_nickname` out of `roomInfo.deeplink` in the live state. Before this, a standard `/livestream/<id>` link produced **no** `anchor_name` on **every** waiting round, so `start_record` judged it "URL content fetch failed" and retried forever — the symptom being "configured the link but never sees the stream-start notice". When the nickname is still unavailable, `小红书_<room_id>` serves as a stable monitoring name (the old path requested `/user/profile/None` for a wasted round).
- **Dispatch and config write-back**: `main._resolve_xhslink_com` reads `port_info["error"]` → logs an `i18n.tr` warning and sets `ctx.unrecognized` (no longer idling as if the anchor simply hadn't started), and reads `normalized_url` → writes it back to URL_config.ini through the existing `new_record_url` channel, so later rounds use the long link directly and skip a short-link redirect per round. The `new_record_url` comment changed from "Shopee-only" to "the canonical URL to be written back after parsing". During URL-config reading, `www.xiaohongshu.com` long links now go through the shared parser (the old `re.search("&host_id=…")` only matched when `host_id` was preceded by `&`, so the first-parameter form never normalized, and it stripped the auth parameters too); short links are deliberately **not** normalized at admission time (resolving them needs a network request, and one blip would rewrite the user's config). Four msgids added per language directory and `zh_CN.mo` recompiled.
- **Tests and verification**: new `tests/test_xhs_live_links.py` (75 cases) covering the four shapes, the query allowlist, scheme/port/userinfo/dot-segment/full-width-digit counter-examples, error categories and redaction, short-link security boundaries, dispatch write-back, an i18n template static lock, and a **record-start integration case** that drives `start_record`: the offline round registers a monitoring job, the live round actually spawns `check_subprocess` with the XHS stream URL as its input. The fabricated URLs in the existing `TestXhsHardening` / `TestXhsRedirectCredentialContainment` (`/live/livestream/x123`, `https://www.xiaohongshu.com/live/123`) were switched to the real `/livestream/<numeric id>` shape. Two security invariants were **mutation-verified** (both turned red and were restored byte-for-byte): the room-id category verdict (`MUTATION-XHSROOMID`) and the query allowlist (`MUTATION-XHSQ`). Gate readings: `run_gates.py` **10/10 green** (built-in pytest fallback 4072 passed / 0 warnings); full `pytest --cov` **4072 passed / 14 skipped / 0 warnings**; `check_coverage.py` **all 47 modules meet threshold** (84.79%); `mypy` 0 issues; `basedpyright` **0/0/0**.
- **Live verification (DoD step 2, parsing side)**: `[2026-10-04] Xiaohongshu | https://www.xiaohongshu.com/livestream/570480456678837366 | called get_xhs_stream_url directly | OK (room id and anchor name resolved; the room reported liveStatus=end at that moment, so no stream URL was fetched) | —`; the short link, the dynamic-path link and the full share-parameter link all resolve to the same room. **Not done**: capturing a real stream (requires a currently live room — handed back to the user).

| Xiaohongshu link normalization | New `src/spider.py::parse_xhs_live_url` + `XhsUrlError` (~120 lines); changed `src/spider.py::get_xhs_stream_url` (shared parser entry + short-link landing re-validation + hostInfo nickname + room-id fallback + `room_id`/`normalized_url` return fields), `main.py::_resolve_xhslink_com` (error-category warning + canonical URL write-back), the URL-config reading block in `main.py` (XHS normalization via the shared parser), `i18n` four directories +4 entries each and recompiled `.mo` (865 entries); new `tests/test_xhs_live_links.py` (75 cases); adjusted `tests/test_spider_hardening.py` (URL and expected switched to the real shape), `tests/test_regression_2026_09_22_spider.py` (short-link/landing URLs switched to the real shape); docs `AGENTS.md` +1 entry, this entry (synced in both languages), `docs/worklog/PROPOSAL_2026-10-04_xhs-live-link-normalization.md`. Throwaway scripts: 0 |

### v4.5.0-dev (2026-10-03) — UI stage 5 wrap-up: customtkinter dependency fully removed + packaging chain cleanup + size baseline + xvfb normalization

> Work-package source: `PROPOSAL_2026-09-29_ui-modernization.md` §6 stage 5 + work-log §2.5; green-lit 2026-10-03. Scope: dependency removal (gui.py CTk residue replacement / requirements / pyproject / typings stubs / build_exe collection), `--smoke` three-entry smoke, bundle-size re-measure (filling the stage-0 baseline), xvfb evaluation and adoption.

- **gui.py de-CTk (compatibility contract preserved)**: `root = tk.Tk()`, both `CTkToplevel`→`tk.Toplevel` (bg follows theme tokens; **system-following titlebar is a registered cosmetic boundary** — self-drawn dark titlebars need extra dwmapi work, not in this batch); `CTkFont`→`tkfont.Font` with **negative point sizes** (CTk size semantics = logical px at 100% DPI, 1pt = 4/3 px@100%, converted by 3/4 for per-size equivalence and automatic cross-DPI scaling via `tk scaling`; positive pixel sizes don't scale and run small at high DPI — forbidden), `Fonts.mono()` tuple converted to `-8` points; `_THEME_CTK_MODE`/`_ctk_mode_to_theme` retired, "Follow System" now uses `ui_theme.detect_system_appearance()` (win32 registry `AppsUseLightTheme` / darwin `defaults read` / other platforms fall back to light; any failure returns light and never blocks startup); new `_apply_root_chrome()` colors the root background from tokens (inheriting CTk root's appearance-mode duty).
- **Dependency removal, three places in one batch**: `requirements.txt`, `pyproject.toml` (runtime list + `.[gui]` extra), `typings/customtkinter/` stub directory deleted (README trees in both languages synced); `uv.lock`/`DouyinLiveRecorder.egg-info` regenerated via `sync_metadata.py` (the two-sided package-name-set regression lock compares dynamically — no lock edits needed). The customtkinter package inside the venv is **not uninstalled** (bulk uninstalls belong to the user's terminal, per the risk-control red line) — with zero imports it affects neither gates nor the bundle.
- **build_exe.py**: removed `collect_data_files('customtkinter')` (nothing left to collect); the `'customtkinter'` entries in excludes are **kept** under the same defensive rationale as fastapi (guarding against venv residue seeping into the bundle).
- **Packaging and size (stage-0 baseline filled)**: `build_exe.py --smoke --no-zip --no-runtime` — all three entries (CLI/Web/GUI) smoked green (GUI ran in a real window for 8s without FATAL_MARKERS), `_internal/` verified item-by-item to contain **zero CTk entries**; `report_bundle_size.py` reading **91.81 MB / 224 files** (biggest: exe bodies 32.28, numpy 26.29, python314.dll 6.48, libcrypto 5.74, Tcl/Tk 5.28), toolchain-leak check clean — the reading and its history are recorded in `docs/agent-reference/measured-evidence.md`.
- **xvfb normalization (evaluated, then adopted)**: the test job's apt step now installs xvfb and `Run pytest with coverage` is wrapped in `xvfb-run -a` — real-Tk integration tests (wrap_hints real-window/stress, ui_theme TestApplyTtk, ui_kit cell editor) change from skip to actually executing in CI; per the MID-2264 anti-skip pattern a "Tk can open a display" fallback step was added (a broken xvfb turns red immediately, preventing the real-window cases from silently disappearing). Rationale: stages 4/5 proved these tests catch two real bugs invisible headlessly (ttk without widget-level `-font`, CTk configure silently ignoring cnf dicts).
- **Gate readings (after the final revision)**: `run_gates.py` **10/10 green** (built-in pytest fallback 3993 passed / 0 warnings); full `pytest --cov` **3993 passed / 14 skipped / 0 warnings** (all 14 skips are platform-conditional; real-window cases run 0-skip on this machine); `check_coverage.py` **all 47 modules meet threshold** (84.70%); `mypy` **207 files, 0 issues**; `basedpyright` **0/0/0**.
- **Docs**: AGENTS.md four entries updated (typings stubs now one, `.[gui]` two packages, GUI two-package floors, wraplength pitfall re-based on ttk); this file and CODE_WIKI_EN carry the same entry; work log §0/§2.5/§4 settled.
- **DoD step 2 (real machine)**: the GUI side is covered by the frozen-build smoke (GUI exe ran 8s in a real window) + real-window regression locks; the recording chain is untouched in this batch. CI first-run verification (xvfb test job / mypy 2.4.0 consts) is handed to the next push's CI run.

| UI stage 5 wrap-up | Changed `gui.py` (root/Toplevel/Fonts/theme callbacks de-CTk + `_apply_root_chrome`), `src/ui_theme.py` (+`detect_system_appearance`), `src/ui_kit.py` (header comment), `requirements.txt`/`pyproject.toml` (customtkinter removed ×2 places), `build_exe.py` (-collect_data_files), `typings/customtkinter/` (deleted), `README.md`/`README_EN.md` (tree -1 line), `.github/workflows/ci.yml` (xvfb three steps), `tests/test_gui_wrap_hints.py` (real-window branches to native widgets + tk scaling storm source), `tests/test_test_hygiene.py` (name list -1), `tests/test_danmaku_monitor.py`/`tests/test_regression_2026-09-22_gui.py` (importorskip reasons); artifacts `uv.lock`/`DouyinLiveRecorder.egg-info` regenerated via `sync_metadata.py`; docs `AGENTS.md` ×4, this entry (both languages), `measured-evidence.md` +size reading, work log settled. Zero one-off scripts (packaging used the existing entry point) |

### v4.5.0-dev (2026-10-03) — UI stage 4 GUI widget layer: CTk → ttk page-by-page replacement + `src/ui_kit.py` factory + Treeview incremental tables + single "UI Theme" entry

> Work-package source: `PROPOSAL_2026-09-29_ui-modernization.md` §3.3/§5.3 (approved spec), work-log §2.4 backlog; green-lit 2026-10-03. Scope: new `src/ui_kit.py` + six gui.py surfaces (dashboard / quality / danmaku / URL config / logs / advanced settings) + sidebar replacement; unify the "Appearance Mode / UI Theme" menus; tables moved to Treeview, verified for "no flicker, no missed clicks". Compatibility contract preserved verbatim: `LiveRecorderGUI` / `SystemTray` / `AdvancedSettingsWindow` / `Colors` / `Fonts` / `_quality_alert_expired` symbols and signatures unchanged, `import gui` stays headless-safe, recording chain / web_config / scheduler untouched.

- **Architecture (colors never enter the factories)**: `src/ui_kit.py` (~430 lines) provides six CTk-compatible factories — `Frame` / `Label` / `Button` / `Menu` / `EditorText` / `terminal_text` — plus the `DataTable` table wrapper; **all colors derive from ttk variant styles registered by ui_theme from tokens** (`Card.TFrame` / `Alt.TFrame` / `Primary.TFrame` / `Muted.TLabel` / `Success.TButton` / `Ghost.TButton` / `Nav.TButton` / `NavActive.TButton` etc.), theme switching redraws via the global ttk style, callers pick a style with the `variant=` string and must not write colors directly; `Colors.TERMINAL_*` is the sole exception (deliberately theme-invariant terminal palette, applied via `terminal_text()` on tk widgets). ui_theme grew in the same batch: `_shade()` derives hover colors from base slots, Treeview `rowheight=32`, Combobox popdown colored via the option DB, contrast contract +3 pairs (`primary/surface_alt`, `on_primary/success`, `on_primary/danger`, all 4.5).
- **Two mechanism rulings settled empirically** (probe scripts deleted; conclusions固化 in comments and test anchors): ① **ttk wraplength is raw device pixels** (Tk 9.0 probe: reqwidth constant at a given wraplength across `tk scaling` ×2) — `_compute_wraplength` dropped the CTk-era scaling division (old anchor 1584@1.5→1050 and new anchor 1584→1576 are visually equivalent at 150% DPI), `ScalingTracker` retired; ② **ttk.Button has no widget-level `-font`** (TclError) — `font_style()` derives a cached style per (variant style + font) and **explicitly copies** the base variant's static config and state map (the multi-segment configure/map fallback across dot segments proved unreliable in probing).
- **DataTable row-level incremental updates**: `sync(keys, values, tags)` differentiates by key via `insert/delete/item/move` — untouched rows are never touched, moves happen only on order drift (row objects are never rebuilt), structurally eliminating the flicker and missed clicks of the old `CTkScrollableFrame` destroy+rebuild cycle; row keys are business keys directly (space-bearing "序号N 主播名", safe through tkinter's parameterized calls). Each row's quality switcher is a readonly Combobox floated over the cell bbox (the official tkinter editable-cell recipe): click opens it, initial value = that row's current quality (`_quality_row_setq` cached at sync), selection flows into the existing `_on_room_quality_change` (unsaved-edits arbitration and reverse-lookup write-back fully reused), and `.set()` not firing the callback matches CTkOptionMenu semantics. The old `_add_quality_header_row` / `_add_quality_data_row` / `_add_danmaku_header_row` / `_add_danmaku_data_row` methods are deleted — headers now come from Treeview headings; row coloring (downgraded red / disconnected grey) goes through tags configured from tokens by `_sync_table_tags()` — Treeview tags are row-level, the old per-cell coloring is inexpressible, and the ✓/⚠ glyphs keep the state semantics; empty-state placeholders became single instances toggled by grid stacking (no per-cycle rebuild).
- **Menu unification**: the sidebar "Appearance Mode" menu (follow-system/light/dark, legacy hardcoded Chinese) is removed; "UI Theme" is the single light-dark/contrast entry — it gains a "跟随系统" (Follow System) option (i18n four catalogs +1 entry, .mo recompiled at 861): resolves light/dark from the current system appearance and **writes an empty `[GUI] gui_theme` value** (`load_theme_preference` treats empty as "unset" → next launch keeps following the system); the three explicit themes persist on selection. `_on_theme_change` absorbed the follow-system branch; root/Toplevel remain CTk and `_THEME_CTK_MODE` keeps driving window chrome (dependency removal belongs to stage 5); `_sync_theme_extras()` recolors the three kinds of tk widgets after a theme switch (Canvas dots tokenized, both tables' row tags, both editors).
- **Real-machine verification (DoD step 2, executed in real windows)**: a one-off driver (deleted) on this desktop — full GUI construction, five-page switching (`_current_page` checked per page + nav active state landing on the font-derived style), quality table injected with two rows (downgraded row carries the `downgraded` tag, placeholder hidden), **the full cell-editor chain: click opens → initial "原画" → commit "高清" → URL_config copy written as "高清,URL,主播A" → log "画质已切换"**, danmaku disconnected tag, dark theme persisted (config copy), editor fg following tokens, follow-system writing an empty value, empty-state placeholder toggling back. The real-window regression locks (`tests/test_gui_wrap_hints.py` narrow-container wrapping + DPI-flip stress) run 0-skip green on the new GUI; the stress collection face covers ttk.Label + CTkLabel (coexistence period).
- **Gate readings (after the final revision)**: `run_gates.py` **10/10 green** (built-in pytest fallback 3993 passed / 0 warnings); full `pytest --cov` **3993 passed / 14 skipped / 0 warnings** (net +12 cases: 11 in `tests/test_ui_kit.py` — the six sync-incremental cells + spaced key + structure lock + real-window cell editor/derived style — plus the new wrap_hints anchors); `check_coverage.py` **all 47 modules meet threshold** (ui_kit included, total coverage 84.90%); `mypy` **207 files, 0 issues** (new files in the scan face); `basedpyright` **0/0/0**. **Mutation validation**: reverting `DataTable.sync` to "delete all + rebuild" turned the five incremental locks red immediately → byte-identical restore → green again (`MUTATION-UDDT`, driver in `%TEMP%`, deleted).
- **Docs and config sync**: AGENTS.md "Known pitfalls · GUI" +1 entry (the three ttk adaptation traps: wraplength device pixels, Button without widget-level font, CTk configure silently ignoring cnf dicts); this file and CODE_WIKI_EN carry the same entry; work log `PROPOSAL_2026-09-29_ui-modernization-work.md` §2.4 settled. **Not in this batch** (stage 5 scope): customtkinter dependency removal and `build_exe.py` data-collection cleanup, bundle-size re-measure, xvfb CI evaluation.

| UI stage 4 widget layer | Added `src/ui_kit.py` (~430 lines) + `tests/test_ui_kit.py` (11 cases); changed `gui.py` (six pages + sidebar + theme callbacks + wraplength formula), `src/ui_theme.py` (+15 variant styles + 3 contract pairs + option DB + _shade), `tests/test_gui_wrap_hints.py` (new anchors + single-instance placeholder locks + stress collection face), `tests/test_gui_tail_robustness.py` (stubs moved to the DataTable interface), `i18n` four catalogs +1 entry each and `zh_CN.mo` recompiled (861 entries); docs `AGENTS.md` +1 entry, this entry (both languages), work log settled. Two one-off scripts (real-window smoke driver + mutation-validation driver) lived in `%TEMP%` and were deleted at cleanup |

### v4.5.0-dev (2026-10-03) — `[tool.mypy].exclude` directory anchoring: bare `"ffmpeg"`/`"node"` substring false-matches fixed; 12 previously blind files enter the no-path mypy gate for the first time

> Work-package source: `PROPOSAL_2026-10-03_linux-arm64-ffmpeg-rulings.md` §二.5 (R-8, one of the two deferred "convenience fix" packages originally awaiting maintainer sign-off; green-lit 2026-10-03). mypy's `exclude` matches with `re.search` against the "relative path + forward-slash normalisation, trailing `/` appended for directories" form as a **substring**, so a bare directory name silently excludes every source file whose module name merely contains that word; the same-named exclusions of black (directory segments only) / isort (by name) / basedpyright (directory globs) never had this failure mode.

- **What was fixed**: in `pyproject.toml [tool.mypy].exclude`, `"node"` → `"(^|/)node/"` and `"ffmpeg"` → `"(^|/)ffmpeg/"` (directory-segment anchoring, cross-platform equivalent — mypy normalises paths to forward slashes), plus a list comment stating "new exclusion entries must always use the anchored form". A file-by-file enumeration confirmed the repaired surface: bare `"ffmpeg"` shadowed `src/ffmpeg_*` ×4 + `tests/test_ffmpeg_*` ×6 — **10** files; bare `"node"` shadowed `src/node_install.py` + `tests/test_node_install.py` — **2** files (the node shadowing is a new finding this round; the original AGENTS.md entry did not record it). The remaining bare entries (`downloads` / `recordings` / `logs` / `backup_config` / `typings` etc.) were fully enumerated and collide with no `.py`/`.pyi` path, so they stay as-is to keep the diff minimal.
- **The 8 legacy errors newly exposed (all in test doubles; zero errors on the src/ side)**: ① four `__exit__` methods that always return False but were annotated `-> bool`, triggering mypy `[exit-return]` — changed to `-> None` (identical falsy semantics, behaviour byte-for-byte equivalent, exceptions still propagate): `_Resp`/`_Bar` in `tests/test_ffmpeg_install.py` and `_FakeResponse`/`_DummyTqdm` in `tests/test_node_install.py`; ② four lambdas consuming `list.append`'s return value (`LIST.append(x) or False` / `(calls.append(url), resp)[1]` shapes), triggering `[func-returns-value]` — rewritten as nested defs (`*args: Any, **kwargs: Any` per the forwarding-stub annotation rule), behaviour exactly equivalent.
- **Regression lock (new safety invariant — mutation validation mandatory)**: `tests/test_run_gates.py::test_mypy_exclude_never_shadows_source_files` — parses the `[tool.mypy].files` scan face from pyproject (206 `.py`/`.pyi` files) and asserts **no exclude pattern may substring-match any source file inside that face** (a semantic lock: the `^ffmpeg/` vs `(^|/)ffmpeg/` wording difference is deliberately not pinned). It carries three anti-false-green witnesses (excludes ≥10 entries, scan face ≥200 files, and the files from both formerly blind families must be present in the enumerated set). **Mutation validation PASS**: reverting pyproject to bare `"ffmpeg"` (carrying a `MUTATION-MYPYEXCL` marker) → the test reports 1 failed; byte-identical restore (asserting `read_bytes()==original`) → 1 passed again; the driver script lived in `%TEMP%` and was deleted at cleanup.
- **Gate readings (executed after the final revision)**: no-path `mypy` 193→**205 source files** (+12, exactly the enumerated set) with 0 issues — run twice, once with the local venv's **mypy 2.4.0** and once with the CI-pinned **2.3.1** (installed into a temp directory via `pip install --target` as a cross-check; the project venv untouched), both fully green, closing the version-gap review required by the "local gate extrapolation" rule; `run_gates.py` **10/10 green** (38.2s, also paying off the arm64 batch's outstanding "run_gates not re-run end-to-end" item); `pytest` **3979 passed / 14 skipped / 0 warnings**; `check_coverage.py` **all 46 modules meet threshold** (total coverage 85.02%); `basedpyright` **0 errors / 0 warnings / 0 notes**. black / isort unchanged on every edited file.
- **Docs**: the AGENTS.md "Known pitfalls · type checking" entry was rewritten as the hard rule "runtime-binary directory entries must use the directory-segment anchored form `(^|/)<name>/`; bare names are forbidden" (with a `[历史注]` preserving the pre-fix 189/190 source-files readings and the retired "explicit-path mypy + basedpyright" compensation); this entry (both languages).
- **DoD step 2 exemption**: this batch only touches type-gate configuration and the annotation/shape of test doubles — no runtime behaviour of the recording chain / source selection / ffmpeg arguments / platform resolvers is involved.

| mypy exclude directory anchoring | Changed `pyproject.toml` (2 exclude entries + comment), `tests/test_ffmpeg_install.py` (5 double fixes), `tests/test_node_install.py` (3 double fixes), `tests/test_run_gates.py` (+1 semantic lock), `AGENTS.md` (1 entry rewritten); this entry (both languages). One one-off script (mutation-validation driver) lived outside the repo in `%TEMP%` and was deleted at cleanup |

### v4.5.0-dev (2026-10-03) — Bilibili mobile share links (`b23.tv`) wired in: direct numeric normalisation + short-code 302 resolution (in-process cache), reusing the desktop pipeline

> User stance: add support for `https://b23.tv/ZyQrgYf`, covering four input shapes — room id straight after the path, with a trailing slash, with a query string, and the `http://` form. Once the room id is extracted, **reuse the existing Bilibili pipeline** (stream URL retrieval, quality selection, recording and saving) so mobile links behave exactly like live.bilibili.com links, without re-implementing anything; return a clear error for unrecognisable links, links without a room id, or invalid room ids.

- **Root cause and requirement-3 conclusion**: `b23.tv` is Bilibili's mobile share domain with two link classes — pure-numeric paths (`b23.tv/22747736`, the path segment is the room id) and alphanumeric short codes (`b23.tv/ZyQrgYf`, a 302 redirect to `https://live.bilibili.com/22747736?share_...`, verified 2026-10-03). Before this change both classes were commented out as "unknown link" during URL-config reading (`b23.tv` was not in `PLATFORM_HOST`). **The existing pipeline depends only on the numeric room id, not on any desktop page**: `_resolve_live_bilibili_com` → `spider.get_bilibili_room_info` (`room_init?id=` / `Master/info?uid=` / `getH5InfoByRoom?room_id=`) / `stream.get_bilibili_stream_url` (`playUrl`) / `get_bilibili_danmaku_info` (`getDanmuInfo`) are all APIs independent of the input link form — once a mobile link is normalised to `live.bilibili.com/<room id>` the whole chain is reused and **no additional request fields are needed**; short-code resolution adds a single `GET https://b23.tv/<code>` (redirect followed, only the landing-path segment parsed, landing page content never fetched), with per-hop SSRF re-checks already handled by the async_http response hooks.
- **Implementation (same pattern as the hy.fan Huya mobile short links landed the same day)**: a b23.tv platform section was added to `main.py` (after `_resolve_live_bilibili_com`, before the dispatch table, per the F-01c layout convention) — `_b23_tv_path_segment` (single path segment; empty path / multi-level path / illegal characters / full-width digits raise a ValueError carrying the reason), `_bilibili_room_id_from_landing` (host must equal `live.bilibili.com` exactly or be a `.live.bilibili.com` suffix; accepts both `/<room id>` and the mobile `/h5/<room id>` forms and requires pure digits — live.bilibili.com has no alphanumeric room ids; video pages / self-referential short links / hyphen-joined domains all yield an empty string), `_resolve_b23_tv_room_segment` (`async_req(redirect_url=True)`, failures converted to a ValueError carrying the reason), `_resolve_b23_tv` (numeric segments normalise with zero network; short codes go through the `_B23_TV_ROOM_CACHE` in-process cache and only miss a request on cache miss; failures `logger.error` (template via i18n.tr, URL via `mask_credentials`) + `ctx.unrecognized` for deferred retry by the room thread), then delegates to `_resolve_live_bilibili_com` for the ctx fields — no duplicated assignment. `PLATFORM_HOST` registers `"b23.tv"`, and the dispatch table gains `(_match_host("b23.tv/"), _resolve_b23_tv)` after the Bilibili entry (MID-04 contract: every whitelist host must be hit by some resolver fragment). The room thread's `record_host` stays `b23.tv`: the per-host circuit-breaker bucket keeps "short-code resolution failures" counted separately from desktop stream failures (same rationale as `_resolve_hy_fan`). Like hy.fan, config lines are **deliberately not rewritten at the admission layer** (redirect resolution depends on the network; doing it in the main-loop admission would amplify one transient network failure into "config line commented out/rewritten").
- **Untouched**: `spider.get_bilibili_room_info` / `get_bilibili_danmaku_info`, `stream.get_bilibili_stream_url`, danmaku collection (`src/platforms/bilibili.py`), `CLEAN_URL_HOST_LIST`, `src/web_config.py` (the web panel's `parse_url_config` / `normalize_url` let b23.tv links through as-is; normalisation happens uniformly on the recording side) — all zero changes; the same-day `hy.fan` / `m.douyu.com` parallel work packages were not touched either.
- **Verification**: `pytest tests/test_b23_tv_dispatch.py tests/test_platform_dispatch.py tests/test_hy_fan_dispatch.py` **80 passed** (22 new cases: 21 in `tests/test_b23_tv_dispatch.py` — the four-form normalisation root contract (spider receives the `live.bilibili.com` link, not the raw b23 address), short-code resolution + second-round cache hit (one resolution request across two rounds), resolution failure / unexpected exception treated as unrecognised with zero spider calls, valid / invalid path segments (including full-width digits), landing-page domain and shape boundaries (video pages / self-referential short links / hyphen-joined domains / alphanumeric segments rejected) + 1 `_DISPATCH_CASES` entry in `test_platform_dispatch.py`); `compile_po.py --check` **860 entries in sync**; black / isort unchanged on the edited files. **Mutation validation 4/4 red** (M-B23-1 strip the path-segment character whitelist / M-B23-2 strip the multi-level-path rejection / M-B23-3 strip the landing-page pure-digit requirement / M-B23-4 strip the normalisation write-back root contract; each "line-level rewrite (changed line carries a `MUTATION-` marker) → real tests turn red → byte-identical restore asserted", with the two lines textually identical to hy.fan disambiguated by nearby anchor lines; zero leftovers).
- **Real-machine verification (DoD step 2, executed)**: network reachable and the target room live. ① The DoD-named script `tests/test_bili_live_collector.py https://b23.tv/22747736 25` → **PASS** (`VERIFICATION_RESULT: {"platform": "bilibili", "status": "PASS", "messages": 18, "srt_bytes": 1402}` — the b23.tv link fed the danmaku pipeline directly, real messages written to SRT); ② real-network direct calls to `_resolve_platform_stream`: the short code `https://b23.tv/ZyQrgYf` resolved via a real 302 to room 22747736 (`anchor=不死鸟总监`, `is_live=True`, `title=新游戏 战争机器：E-DAY`, `actual_quality=OD`, danmaku params `room_id`/`token`/`buvid`/`host_list` all present), and all four numeric forms matched the short-code results item by item; invalid forms `https://b23.tv/` and `https://b23.tv/a/b` → returned None with error logs naming the reason ("路径为空，缺少房间号" / "路径含多级目录，不是标准房间链接").
- **Docs**: `README.md` / `README_EN.md` each gained one Bilibili link-forms paragraph under "Supported platforms" (short-code 302 resolution and in-process cache); this entry (both languages).

| Bilibili mobile share links (b23.tv) | Changed `main.py` (+b23.tv platform section: 4 functions and a cache, `PLATFORM_HOST` +1 host, dispatch table +1 entry), `i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` +2 entries each and `zh_CN.mo` recompiled (860 entries), new `tests/test_b23_tv_dispatch.py` (21 cases), `tests/test_platform_dispatch.py` (+1 dispatch case); docs `README.md` / `README_EN.md` +1 paragraph each, this entry (both languages). Two one-off scripts (mutation validation + real-machine driver) lived outside the repo in `%TEMP%` and were deleted at cleanup |

### v4.5.0-dev (2026-10-03) — Douyu mobile links (`m.douyu.com`) wired in: admission whitelist + shared dispatch entry + normalised room-id extraction (trailing slash / query string / http scheme)

> User stance: add support for `https://m.douyu.com/8751648`, covering four input shapes — room id straight after the path, with a trailing slash, with a query string, and the `http://` form. Once the room id is extracted, **reuse the existing Douyu pipeline** (stream URL retrieval, quality selection, recording and saving) instead of re-implementing it; return a clear error for unrecognisable links, links without a room id, or invalid room ids. Two stances were settled during design: ① non-numeric room ids (alphanumeric / vanity ids) **keep** the existing mobile-page resolution, and only error when no numeric id can be resolved; ② when the path already holds digits, **keep the current behaviour** and still fetch the mobile page (no "digits means skip the fetch" fast path).

- **Actual state on take-over (evidence first)**: mobile links were blocked at **two** places. ① `PLATFORM_HOST` only listed `www.douyu.com`, and admission matches the **exact host** (`url_host in PLATFORM_HOST`), so `https://m.douyu.com/8751648` was rejected while reading the URL config — "本行包含未知链接.此条跳过" — and commented out. ② The dispatch table only had `_match_host("www.douyu.com/")`, so even if admitted the link would fall into `_resolve_unrecognized` and spin forever (same failure shape as SEV-2203: never records, never counts a `record_error`, still occupies a monitoring slot). Missing either one makes the feature unusable.
- **Reuse verdict (answer to "can the existing pipeline be reused?")**: **yes — no new endpoint or field is needed.** The three endpoints in the chain (`https://www.douyu.com/betard/{rid}`, `https://www.douyu.com/lapi/live/getH5PlayV1/{rid}`, `https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption`) **only accept a numeric rid**, and the `Referer` is always built as `https://www.douyu.com/{rid}` regardless of the source domain; the page used for id resolution, `https://m.douyu.com/{candidate}`, is a mobile page in the first place (measured: `https://m.douyu.com/8751648` returns `vike_pageContext` with `rid=8751648`). Real-device evidence is under "Verification".
- **Normalised room-id extraction (`src/spider.py`)**: two unit-testable helpers, `extract_douyu_rid_param()` and `extract_douyu_room_id()`, replace the two whole-string regexes. Each old regex had a boundary hole: `rid=(.*?)(?=&|$)` was not anchored on the parameter boundary (`?xyzrid=123` could be picked up as the room id); `douyu.com/(.*?)(?=\?|$)` swept the trailing slash and any extra path segment into the id (`/8751648/` → `"8751648/"`, `/topic/x` → `"topic/x"`), so the `betard` request got no `room` and the user only saw a misleading "room does not exist". With `urlsplit`, the scheme, trailing slash, query and fragment are all stripped at parse level, so http/https and www/m share one rule; a scheme-less input gets `https://` prepended by the same rule admission uses (otherwise the first non-empty segment would be the host name).
- **Error messages**: no room id in the path → `斗鱼链接缺少房间号: {masked_url}`; a URL so malformed that `urlsplit` raises → `斗鱼链接无法解析房间号: {masked_url}`; a non-numeric resolved id → `斗鱼房间号还原结果非数字: candidate={candidate} rid={rid}` (`betard` / `getH5PlayV1` only accept numeric ids; the old code concatenated a non-numeric id into the URL and failed silently). All three are constant `i18n.tr` templates, and the link goes through `utils.mask_credentials` before reaching the text; four catalogues gained 3 entries each and `zh_CN.mo` was recompiled (**856 entries** = 855 keys + 1 empty header msgid, `compile_po.py --check` in sync). Also: the `rid` query parameter only counts when **its value is purely numeric** — `?rid=abc` falls back to the first path segment (the old code concatenated it straight into betard).
- **Entry wiring (`main.py`)**: `PLATFORM_HOST` gains `m.douyu.com`; the Douyu dispatch entry becomes `(_match_host("www.douyu.com/", "m.douyu.com/"), _resolve_douyu_com)` — **the same handler**, no new branch. `_match_host` already compares against the `scheme://host/` normalisation of `urlsplit` (M-03 rule), so a trap address such as `https://example.com/m.douyu.com/8751648` is not routed to Douyu (covered by a regression lock).
- **Parallel writer (not this batch, worth noting)**: while this batch was editing, another work package inserted the Huya mobile short-link `hy.fan` into `main.py` (entry placed after `_resolve_huya_com` and before `_resolve_douyu_com`, with `hy.fan` registered in `PLATFORM_HOST` in the same batch). That insertion moved the Douyu entry from index 4 to 5, turning `tests/test_platform_dispatch.py::test_resolver_table_priority_head` red — this batch synced that order lock to the **actual** order (first six entries: `…_resolve_huya_com` → `_resolve_hy_fan` → `_resolve_douyu_com`) and added a note that inserting an entry shifts every later index. The `hy.fan` implementation and its tests were not touched by this batch.
- **Untouched**: the stream/quality chain (`stream.get_douyu_stream_url` / `spider.get_douyu_stream_data` / `get_token_js`), the danmaku chain (`src/platforms/douyu.py`) and `CLEAN_URL_HOST_LIST` (Douyu was never in it) — zero changes. The twin copy `scripts/douyin_live_recorder_standalone.py` was **checked and deliberately not back-ported**: it matches platforms with `douyu\.com` (already covering the m subdomain), derives the room id via `url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]` (already handling trailing slash and query), and already raises an explicit "斗鱼房间号必须是纯数字" error — none of this batch's defects exist there.
- **Verification**: `pytest tests/test_douyu_url_resolution.py tests/test_platform_dispatch.py -q` **66 passed / 0 warnings**; `black --check` on the 4 changed files unchanged, `isort --check-only` no reordering; bare `mypy` **192 source files, 0 issues**; `compile_po.py --check` 856 entries in sync. **Two mutation checks** (each: rewrite with a `MUTATION-` marker → run the real cases → restore and confirm sha256 `f92a15b7…1a72` matches): ① removing `if not rid.isdigit():` turned `test_non_numeric_resolved_rid_raises` red (`DID NOT RAISE ValueError`); ② changing `return segments[0]` to `"/".join(segments)` (back to the old whole-path rule) did **not** turn red on the first pass — the cases only covered single-segment paths, a genuine test gap — so a multi-segment case `https://m.douyu.com/8751648/extra` was added and the mutation then turned red (`assert '8751648/extra' == '8751648'`). Full run: `pytest --cov=src` **3977 passed / 14 skipped / 0 failed, empty warnings summary** (691.7s); `scripts/check_coverage.py` **PASSED: All 46 module(s) meet coverage threshold** (`src/spider.py` 75.2%); `scripts/run_gates.py` **10/10 PASS** (black 205 files unchanged / isort / three mypy passes over 192 files with 0 issues / check_annotations 202 files with 0 dangling references / compile_po --check / check_version / check_runtime_pins / check_skill_agents). Note on sequencing: the **first** `run_gates.py` run of this batch (04:0x) reported its pytest fallback as rc=1 while the parallel session was still writing `main.py` (its `hy.fan` work was mid-flight); that run only recorded the return code, so no failure list exists. After the parallel session finished, the full suite re-ran green — the first red is attributed to in-flight edits but was **not** individually evidenced.
- **Real-device verification (DoD step 2, executed)**: external network reachable from this machine. ① All four shapes (`https://m.douyu.com/8751648`, `https://m.douyu.com/8751648/`, `http://m.douyu.com/8751648?rid=8751648`, `https://www.douyu.com/8751648`) resolve identically: `anchor_name=有鬼yougui` (that room was offline at the time, `is_live=false`). ② A live room was then used for the full chain, `https://m.douyu.com/5526219` (南波儿大魔王丶, `is_live=true`, `room_id=5526219`, title "王者前十冲第一!"): `stream.get_douyu_stream_url` returned `flv_url` / `m3u8_url` / `record_url` (`huosa.douyucdn2.cn/live/5526219r…_4000.flv?wsAuth=…`) plus `quality` / `actual_quality` — **proof that mobile links ride the same stream-retrieval chain as www links**.
- **Documentation same-source**: `README.md` / `README_EN.md` each gained one line on the supported Douyu link shapes under "Supported Platforms" (per convention `-dev` entries do not enter the README changelog; they are distilled from CODE_WIKI at release time); this entry in both languages.

| Douyu mobile link support | Changed: `src/spider.py` (+2 extraction helpers, 2 old regexes replaced, +1 guard at the resolution exit), `main.py` (+1 whitelist host, +1 dispatch fragment), `i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` (+3 entries each, `zh_CN.mo` recompiled), new `tests/test_douyu_url_resolution.py` (27 cases), `tests/test_platform_dispatch.py` (+2 dispatch cases, +1 admission/counter-example lock, order lock synced to the actual order). Docs: `README.md` / `README_EN.md` +1 line each, this entry in both languages. No throwaway scripts (verification ran through `python -c` and in-memory mutation only, with output written outside the repo to `%TEMP%`) |

### v4.5.0-dev (2026-10-03) — Huya mobile share links (`hy.fan`) wired in: admission whitelist + new dispatch resolver + short-code 301 redirect resolution (standard / trailing slash / query string / http scheme)

> User stance: add support for `https://hy.fan/` (example `https://hy.fan/JbmwoV`), covering four input shapes — room id straight after the path, with a trailing slash, with a query string, and the `http://` form. Once the room id is extracted, **reuse the existing Huya pipeline** (stream URL retrieval, quality selection, recording and saving) so mobile links behave exactly like existing www.huya.com links, without re-implementing anything; return a clear error for unrecognisable links, links without a room id, or invalid room ids. Answer to requirement 3 (does the existing flow depend on desktop pages/APIs): **it does, but no additional request URLs or fields are needed** — the desktop chain (page-inline `stream:` object / `mp.huya.com` mini-program API) only understands the `www.huya.com/<room id>` form, so this batch normalises first at the parsing layer and then delegates; the desktop side is unchanged.

- **Measured short-link behaviour (evidence gathered before design, 2026-10-03)**: `https://hy.fan/JbmwoV` is a **301 → `https://www.huya.com/30764624?source=android&shareid=…&hyaction=live…`** — the short code is not a room id and must be resolved by following the redirect; a purely numeric path segment (`hy.fan/30764624`) and the short-code form resolve to the same room. `hy.fan` had zero references in the repo before: it was not in `PLATFORM_HOST`, so such links were commented out as "unknown link" during URL-config reading (the same failure shape the Douyu batch logged under SEV-2203; either missing piece makes the feature unusable).
- **Wiring (`main.py`)**: `PLATFORM_HOST` gains `hy.fan`; the dispatch table gains `(_match_host("hy.fan/"), _resolve_hy_fan)`, placed after `_resolve_huya_com` (their match fragments never overlap, no shadowing; the `test_resolver_table_priority_head` order lock was synced to the actual six-entry order by the Douyu batch — see the Douyu entry's "parallel writer" note; this batch did not touch that lock).
- **Normalisation and reuse (requirements 1 and 2)**: `_hy_fan_path_segment` extracts the single path segment (empty path / multi-level path / illegal characters — full-width digits rejected via the `isascii` tightening — raise a `ValueError` carrying the reason); purely numeric segments normalise to `https://www.huya.com/<segment>` with zero network (covering all four forms); non-numeric segments are treated as short codes → `_resolve_hy_fan_room_segment` goes through `async_req(redirect_url=True)` (the same contract as xhslink.com short-link resolution: success returns the final landing URL, failure returns an empty string, narrowed via `isinstance` + non-empty) → `_huya_room_segment_from_landing` requires the landing host to equal `huya.com` exactly or be a `.`-suffix of it, with a single ASCII alphanumeric path segment (self-referential short-link domains / hyphen-joined domains like `evil-huya.com` / multi-segment paths all yield an empty string) → only success writes `_HY_FAN_ROOM_CACHE` (in-process cache: the short-link-to-room mapping is stable, idempotent writes, GIL-atomic, bounded by the number of config lines, so monitoring rounds never re-issue the 301). After normalisation it delegates to `_resolve_huya_com` to write the four ctx fields — stream retrieval, quality, danmaku and recording ride the same chain as desktop links; if the landing page is a streamer's custom alphanumeric profile id, the existing app-path ProfileRoom reverse lookup handles it, no second implementation.
- **Error messages (requirement 1)**: `虎牙移动端链接缺少有效房间号，本轮跳过: {record_url} - {reason}` (reasons: URL 无法解析 / 路径为空，缺少房间号 / 路径含多级目录，不是标准房间链接 / 房间号含非法字符) and `虎牙移动端短链解析失败，本轮跳过: {record_url} - {reason}` (reasons: 未获取到跳转地址 / 跳转地址不是虎牙直播间 / `{type_name}: {err}`). Both are `i18n.tr` constant templates with URLs passed through `utils.mask_credentials`; +2 entries in each of the four language catalogues and `zh_CN.mo` recompiled.
- **Known boundary (deliberately not fixed; not a production path)**: when `tests/test_huya_live_collector.py` feeds the URL **directly** to `spider.get_huya_app_stream_url` (bypassing main.py's parsing layer), the short-code form fails at the ProfileRoom reverse lookup (with the app UA the 301 landing page regex does not match → `Please use "https://www.huya.com/+room_number"`) and the script exits as `SKIP`. In the production chain the resolver normalises first and spider only ever receives numeric room links — spider does not know about hy.fan, so `src/spider.py` stays untouched; the `scripts/douyin_live_recorder_standalone.py` twin copy shares this boundary and was not back-ported.
- **Untouched**: `src/spider.py` / `src/stream.py` / danmaku collection (`src/platforms/huya.py`) / `CLEAN_URL_HOST_LIST` (queries are dropped during normalisation, no need to join the cleaning list) — all zero changes; `record_host` stays `hy.fan`: the per-host circuit-breaker bucket keeps "short-code resolution failures" counted separately from desktop stream failures (same rationale as `_resolve_b23_tv`), so it is not rewritten to `www.huya.com`.
- **Verification**: new `tests/test_hy_fan_dispatch.py` — **21 cases** all green with 0 warnings (the four-form normalisation root contract — spider receives `https://www.huya.com/30764624`, not the raw hy.fan address; short-code resolution + second-round cache hit issuing exactly one request; resolution failure / non-ValueError exceptions treated as unrecognised with zero spider calls; landing-page domain family and shape boundaries); **mutation validation 1/1 red** (breaking the normalisation write-back turned 6 cases red, byte-identical restore asserted, `MUTATION-hyfan1` zero leftovers); no-arg `mypy` **192 source files 0 issues**; `basedpyright` **0 errors / 0 warnings**; coverage gate — all 46 modules meet their thresholds (total 84.90%).
- **Real-machine verification (DoD step 2, executed, readings 2026-10-03 04:22-04:24)**: external network reachable and the target room live. ① Real-network direct call to `main._resolve_platform_stream("https://hy.fan/JbmwoV", None, "原画")` → `platform=虎牙直播`, `anchor_name=Horcus`, `is_live=True`, `flv_url` 250 B / `m3u8_url` 251 B (signed CDN direct links on `hs.flv.huya.com` / `hs.hls.huya.com`), danmaku triple `{ayyuid: 35184700893343, topSid: 1239543859098, subSid: 1239543859098}`; ② `https://hy.fan/30764624` (numeric form) resolved identically item by item (proving the short-code and numeric forms point to the same room over the same chain); ③ `python tests/test_huya_live_collector.py https://www.huya.com/30764624 20` (the normalised link through the existing app path + collector) → **WARN** (`VERIFICATION_RESULT: {"platform": "huya", "status": "WARN", "messages": 0, "srt_bytes": 0}` — connected normally, no danmaku in that window); ④ feeding the raw short link to the collector directly is the "known boundary" above → `SKIP(the room_offline marker actually denotes the failed reverse lookup)`. Hand-back: no danmaku in that window — for byte-level SRT readings, re-run with the normalised link during an active-danmaku window.
- **Documentation same-source**: `README.md` / `README_EN.md` each gained one Huya link-formats paragraph under "Supported platforms" (per convention `-dev` entries do not enter the README changelog; they are distilled from CODE_WIKI at release time); this entry in both languages.

| Huya mobile share links (hy.fan) | Changed `main.py` (+hy.fan platform section: 4 functions and 1 cache, `PLATFORM_HOST` +1 host, dispatch table +1 entry, `src.async_http` import +1 name), `i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` (+2 entries each, `zh_CN.mo` recompiled; the 860-entry reading includes the same-day b23.tv parallel batch), new `tests/test_hy_fan_dispatch.py` (21 cases); docs `README.md` / `README_EN.md` +1 paragraph each, this entry in both languages. Mutation validation ran as a `python - <<PY` in-memory byte backup / rewrite / restore — zero throwaway scripts written to disk |

### v4.5.0-dev (2026-10-03) — Linux arm64 (aarch64) ffmpeg support landed in three segments: four-platform release matrix + runtime official direct-download module + GHCR multi-arch image publishing

> User framing: the three scope items (release chain produces an arm64 package / runtime Linux-native download / Docker image available on arm64) were approved item by item on 2026-10-02; integrity stance chosen as "official hash first, TOFU only as an explicit downgrade"; implementation landing chosen as option A (a new `src/ffmpeg_linux_download.py`); `docker-compose.yaml`'s image name **not changed**; image publishing triggers only on `v*` tags. Spec: `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`, plan: `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg-plan.md`.

- **Why (establishing what already existed)**: Linux arm64 **fetching and pinning were already in place** (`build_exe._FFMPEG_DOWNLOAD_URLS` carries the month-end-tag `linuxarm64-gpl-9.0.tar.xz`, `_PINNED_RUNTIME_SHA256` has both `linux-arm64` slots, `RELEASE_RUNTIME_KEYS` includes the key, archives are walked recursively by file name). What was missing were three other things: **who builds it** (the release matrix only had `windows-latest`/`ubuntu-latest`/`macos-latest`, so the arm64 package never appeared in a Release); **whether the runtime can obtain a verified native binary on its own** (`install_ffmpeg_linux()` had only `yum`→`apt`, both requiring root and a distro repository that ships ffmpeg; `ffmpeg_master_download.py` is Windows-only); and **whether an arm64 image layer actually gets published** (the `Dockerfile` installs ffmpeg via apt so it is architecturally native by construction, but the repository had no image-publishing workflow at all).
- **S1 release matrix (now four platforms)**: `.github/workflows/build-release.yml`'s `matrix.include` gained `- os: ubuntu-24.04-arm` + `platform: linux-arm64`, **inserted after `ubuntu-latest`** (the position is the contract: `check_runtime_pins._runtime_matrix_keys()` returns keys in `os:` line order and `tests/test_check_runtime_pins.py::test_workflow_matrix_and_test_constant_stay_in_sync` asserts element-wise equality with `_MATRIX_KEYS`, not a set comparison). Both Linux steps moved from `if: matrix.platform == 'linux'` to the family test `startsWith(matrix.platform, 'linux')`, and the negated one had to be written **quoted** as `if: "!startsWith(matrix.platform, 'linux')"` (YAML reads a leading `!` as a tag directive; unquoted it reproduces a `ParserError`). `Verify artifact completeness` went from `-lt 6` to `-lt 8` (4 platforms × (lite+full)), and the platform-count wording that described the release matrix was corrected to the live count: the header/section comments of `.github/workflows/build-release.yml` and `build_exe.py:425` were updated in the S1 commit, while the 2026-10-03 documentation round additionally corrected the Release body template at `build-release.yml:567` (user-visible), the two `AGENTS.md` entries 「打包与冒烟测试语义」 and 「release-guard」, the directory-tree comments and the CI/CD chapter in both language versions of this document, and the tree in `docs/agent-reference/project-structure.md`. Wording that denotes the **OS-family count of 3** (`linux-x64` and `linux-arm64` share one `.tar.xz` build and the `-version` probe), as well as dated historical readings, stays untouched. The single fact source for the four-platform / 8-zip reality is the `AGENTS.md` 「CI / workflow 约定」 entry 「发布矩阵为四平台」; every other place only references it. `scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY` gained `"ubuntu-24.04-arm": "linux-arm64"` — **the single registration point**; an unregistered runner label goes to `sys.exit(2)` and kills the release in the prepare job before any build runs. `tests/test_check_runtime_pins.py`'s `_MATRIX_KEYS` now holds the four keys. The artefact is named `DouyinLiveRecorder-v<version>-linux-aarch64-{lite,full}.zip` — the architecture segment is the literal value of `platform.machine().lower()`, i.e. `aarch64`, **not** `arm64`.
- **S2 runtime Linux-native direct download**: new `src/ffmpeg_linux_download.py` (476 lines, LF-only) + `tests/test_ffmpeg_linux_download.py` (**46 cases**, measured `46 tests collected`). The adjudication surface is the four-cell truth table of spec §4.1: digest obtained and matching → install; obtained but mismatching → refuse, delete the archive, error-level log telling a human to cross-check; not obtainable + `FFMPEG_MASTER_ALLOWED` false (default) → refuse; not obtainable + switch true → TOFU (compare against a baseline if one exists, otherwise record the first one and install, warning level). Three invariants: the default path must always be verified; a baseline present but unreadable means refuse (the SEV-2222 tightening, no regression to a warning); shape before hash (check it really is a tar.xz, then hash, then extract). Implementation points: `_linux_arch()` treats only `arm64`/`aarch64` as ARM and conservatively falls back to `linux64`; `_api_release_url()` **derives** repo and tag by parsing the download URL back (no second URL constant, so the "download from the new tag, fetch the digest from the old one" half-state cannot exist); the digest must pass `^[0-9a-f]{64}$` and the code deliberately does **not** `.lower()` it (an upper-case payload counts as "not obtainable" = fail-closed); `_install_binaries()` runs in **two passes** (locate both `ffmpeg` and `ffprobe` recursively first and return immediately if one is missing — the destination side sees zero changes; only when both are found does it mkdir + copy + restore the executable bit), regression lock `TestBinaryLayoutDiscovery::test_missing_companion_leaves_no_half_install`; `extractall(filter="data")` is passed explicitly (MI-26); the top-level entry **always returns False on failure and never raises**. The TOFU baseline file name embeds the asset name (`_ffmpeg_linux.<asset_stem>.tar.xz.sha256`), so changing tag changes the baseline. The downgrade switch is **passed in** by `install_ffmpeg_linux()` as `master_allowed=_master_source_allowed()` — the new module must not read the environment variable itself, because `ffmpeg_install` already imports it and importing back would form a cycle. The wiring sits at the **unified exit at the end of `install_ffmpeg_linux()`** (package managers stay first: apt/yum natively provide arm64 and carry the distro's own signature chain). In the same round the "non-zero `apt update` returns False inside the apt block" early exit was removed and `apt install` folded into an `else:` branch — on non-root Debian/Ubuntu arm64 machines `apt update` failing is the norm, and exactly those machines are this module's target population, so the early exit left them a path that never reaches the fallback. `tests/test_ffmpeg_install.py`: `DOWNLOAD_SOURCES` gained `api.github.com` = `官方哈希` (official hash) and `DOWNLOAD_MODULES` gained `src.ffmpeg_linux_download` (AGENTS "关键约定" #10 — missing either registration reddens the lock), while **`github.com` stays `TOFU`** (the master-latest route still exists; the two entries must not be merged); six new behavioural locks for the wiring/order/arguments (including "a successful package manager must not reach the direct download" and "`FFMPEG_MASTER_ALLOWED=1` really arrives at the fallback"), bringing that file to **116 cases** (baseline 110 → 114 → 116). The four i18n catalogs each gained the same 20 templates and `.mo` was recompiled (`compile_po.py --check` reads 853 entries = 852 keys + 1 empty header msgid, 2026-10-02).
- **S3 GHCR multi-arch image**: new `.github/workflows/docker-publish.yml` (210 lines, LF-only) + structural lock `tests/test_docker_publish_workflow.py` (**12 locks**). Stance: triggers only on `push: tags: ["v*"]`; `prepare` derives the image name from `GITHUB_REPOSITORY_OWNER` and **lower-cases** it (GHCR forces a lower-case namespace); `docker-build-amd64`(`ubuntu-latest`) and `docker-build-arm64`(`ubuntu-24.04-arm`) are **two native runners each producing one layer**, pushing only per-architecture temporary tags `:vX.Y.Z-amd64`/`-arm64`, each with an explicit `provenance: false` (when it is omitted the action composes `--attest` from the repository visibility, and a public repository lands on `mode=max`, mixing non-runnable entries into the published manifest); both build jobs **promote `steps.build.outputs.digest` to job-level `outputs:`**, and `docker-manifest` uses `docker buildx imagetools create` to merge **the two digests** (not the per-architecture tags) into `latest` plus the version tag in one command. **Single-job QEMU cross-builds are deliberately rejected** (the image build runs apt + the full pip install, which under emulation is whole-layer work); credentials are only the automatic `GITHUB_TOKEN`, with top-level `permissions: contents: read` and `packages: write` granted per-job only where images are pushed; `cancel-in-progress: false`; zero in-job install steps (a structural lock pins that, so there is no `.github/actions/retry` application point here). Third-party actions use floating major-version refs — the trigger source is a maintainer-pushed `v*` tag, i.e. trusted input, the same MIN-17 dividing line.
- **Live evidence (`api.github.com` equals the release pins byte for byte)**: `api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27`'s `assets[].digest` compared against `build_exe._PINNED_RUNTIME_SHA256` — linux64 `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz` = 126,600,656 B / `sha256:182c1b509720e939bb47bfb47dc29cc0c298640401128e3dce8627d10707eb5a`, linuxarm64 `...-linuxarm64-gpl-9.0.tar.xz` = 108,761,296 B / `sha256:e2dd447c8a47849c5812d87e54a47b20ae0f3603d38989440f4a5fe1af8755b1`; both architectures read `api digest == release pin: True` (readings: first recorded 2026-09-27 in `docs/agent-reference/measured-evidence.md`, re-verified byte-identical on **2026-10-02** by this plan). Stance reminder: that channel is **same-origin consistency checking, not source authentication** (same platform as the artefact but a different service, on par with gyan.dev's `.sha256` documents, the MIN-2258 wording) — neither comments nor logs may call it an "authenticated source".
- **Left alone**: `install_ffmpeg_windows` / `install_ffmpeg_mac` / `_windows_arch` / `download_ffmpeg_official` not touched by one line (zero change on the Windows side); `docker-compose.yaml` and the `Dockerfile` untouched (compose's `image: ihmily/douyin-live-recorder:latest` and the GHCR name being **different is deliberate division of labour** — compose goes through `pull_policy: build`, MIN-18 unchanged); `build_exe._ALLOWED_HOSTS` untouched (`github.com` is already there, and the runtime-side `api.github.com` belongs to the separate `DOWNLOAD_SOURCES` lock — they do not substitute for each other); `[tool.mypy].exclude` in `pyproject.toml` **not changed** (see the next bullet); the `scripts/douyin_live_recorder_standalone.py` twin copy was **checked and deliberately not backfilled** — `grep -n "install_ffmpeg\|download_ffmpeg"` yields zero hits, that copy contains no ffmpeg installation chain at all, only the same-named `should_prepend_bundled_ffmpeg_dir` PATH-yield predicate whose semantics were not touched.
- **Known defect (compensated for in this round, left as its own work package)**: the bare `"ffmpeg"` entry in `[tool.mypy].exclude` is a **path-substring** regex, so `src/ffmpeg_*` and `tests/test_ffmpeg_*` are invisible to the "mypy without path arguments" gate — measured: the no-argument run reported `189 source files` both before and after the two new files were added (only an explicit run over them reports `checked 2 source files`), and the next day adding `tests/test_docker_publish_workflow.py`, whose name lacks `ffmpeg`, moved the same command to `190 source files`. This round's typing verdict therefore rests on "explicit per-file `mypy` (the two new files report `Success: no issues found in 2 source files`; the sibling legacy file `tests/test_ffmpeg_install.py` carries 5 pre-existing errors — `exit-return` ×2 (`:436`/`:458`) + `func-returns-value` ×3 (`:514`/`:737`/`:739`), all five inside that test file, while `src/ffmpeg_install.py` on its own reports `Success: no issues found in 1 source file`; 0 from the code added in this round) + `basedpyright` (no path arguments: `0 errors, 0 warnings, 0 notes`; over the two new files: `filesAnalyzed: 2`, `errorCount: 0`)" — **"mypy is green" must not be cited as gate evidence for these files**. Changing the exclude form is a separate work package pending the maintainer; the rule is now written back into `AGENTS.md` "已知坑 · 类型检查、注释与静态门禁".
- **Verification** (each unit ran its own scoped commands, all after that unit's last edit; the full gate suite is executed by the closing unit, so this bullet is **not** a claim that the full gates are green): `pytest tests/test_ffmpeg_linux_download.py -q -W error` → **46 passed / 0 warnings**; `pytest tests/test_ffmpeg_install.py -q -W error` → **116 passed / 0 warnings**; `pytest tests/test_docker_publish_workflow.py -q -W error` → **12 passed / 0 warnings**; neighbouring files unaffected — `test_ffmpeg_linux_download + test_build_exe + test_test_hygiene` = **682 passed** (46 + 105 + 531, and `tests/test_test_hygiene.py`'s R8 repo-wide mutation-marker scan doubles as a disk-level reverse witness); `pytest tests/test_check_runtime_pins.py -q` → 20 passed; `check_runtime_pins.py` in both structural and `--strict` mode rc=0, printing the matrix `windows-x64, linux-x64, linux-arm64, macos-arm64`; `PYTHONUTF8=1 python scripts/check_annotations.py` all passed (2026-10-03 reading: 213 Python files, 0 dangling symbol references); `compile_po.py --check` in sync at 853 entries and `extract_i18n_strings.py` reporting 0 missing with no `[不一致]` lines; both YAML files parse through `yaml.safe_load` (four matrix entries, the three `if:` expressions, and the docker workflow's four job names). **Mutation evidence per unit** (Task 1 once: flipping `linux-arm64/ffmpeg` back to the placeholder made `--strict` rc=1 and put that key into the failure set — the reverse witness that it is now inside the gate; Unit A 11 markers, every one reddening at least one case; Unit B 2 in the first round + 3 in the fix round; Unit 6 3 + 5), all executed as "back up bytes in memory → rewrite (changed lines tagged `MUTATION-`) → run real cases → restore in `finally` asserting `read_bytes()` equality", zero residue. The single marker that survived locally was Unit A's extra `M-A1-CHMPOFF` (deleting `target.chmod(...)`, the executable-bit restore): on Windows tar member modes all report `0o666` and a set `S_IXUSR` never reads back, so that cell collapses to an existence assertion on non-POSIX hosts and **the executable-bit judgement is carried by Linux CI** — it is not written up as locked.
- **Not executed + handed back (DoD step 2)**: `SKIP(this machine is Windows x86_64 — it can neither produce nor run arm64 artefacts)`. ① The two arm64 real-machine branches need an aarch64 container (e.g. `arm64v8/debian:trixie` without ffmpeg): one keeps apt but runs as non-root (`apt update` rc≈100 → expect `Failed to update package lists using apt` → official direct download → installed and verified → True), the other hides yum and apt. ② Whether `ubuntu-24.04-arm` counts against this account's free quota can only be decided by a first run (GitHub publishes no pricing statement for it); the fallback (keep linux-arm64 in the matrix but enable it only under `workflow_dispatch`) **requires separate approval**. ③ Setting the GHCR package visibility to public is a one-off manual action that `GITHUB_TOKEN` will not perform, so anonymous `docker pull ghcr.io/<owner>/douyin-live-recorder:latest` is unverified before the first push. ④ This change **does not touch the recording chain / source selection / ffmpeg arguments / platform resolvers**, so the collector scripts (`tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py`) have no attributable increment and no "verified on real devices" claim is made.
- **Documentation same-source**: five entries written back to `AGENTS.md` — two in "CI / workflow 约定" (four-platform matrix with the single runner-label registration point; the multi-arch image stance), two in "已知坑 · 构建产物、依赖与运行时基线" (the two physical URL copies plus the `api.github.com` wording; the two non-revertable implementation shapes), one in "已知坑 · 类型检查、注释与静态门禁" (the mypy exclude substring blindness); `README.md`/`README_EN.md` gained the linux-aarch64 artefact list and the GHCR pull instruction (the compose wording kept verbatim); this entry (kept in sync across both languages); and the rollback paragraph of the spec corrected against the implementation (next bullet). The 2026-10-03 review-fix round (Unit 7 Fix round 1) closed out, in the same batch: the remaining stale locations listed in the S1 bullet (the two `AGENTS.md` platform-count phrasings now reference the 「发布矩阵为四平台」 entry instead of restating it; the directory-tree comments and the CI/CD matrix enumeration + zip count in both language versions of this document; the tree in `docs/agent-reference/project-structure.md`; the user-visible Release body template at `build-release.yml:567`, text only; the exhaustive auto-install enumeration in `README.md`/`README_EN.md` plus scoping "the only automatic route" to Windows); two factual errors this entry had itself introduced (the artefact platform segment is attributed to `build_exe.make_zip()` reading `sys.platform` through the `{"win32": "windows", "darwin": "macos"}` mapping rather than `platform.system()`, and the 5 pre-existing mypy errors are attributed to `tests/test_ffmpeg_install.py` instead of `src/ffmpeg_install.py`); and the spec's S1 rollback wording, which now names the entry by its `os` label instead of a serial position.

- **Spec rollback paragraph corrected (falsified by the implementation)**: `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md` used to say "S2 rollback = delete the new module + remove that one call in `install_ffmpeg_linux()`". The wiring round (2026-10-03) also deleted the early `return False` on `apt update` failure and folded `apt install` into an `else:` block, so removing only the call would leave a behavioural difference ("update failed still falls through to the unified exit"). An equivalent rollback must restore that nesting too; the text was corrected in place with a dated `[历史注]` line.

| Linux arm64 ffmpeg support | New: `src/ffmpeg_linux_download.py` (476 lines), `tests/test_ffmpeg_linux_download.py` (46 cases), `.github/workflows/docker-publish.yml` (210 lines), `tests/test_docker_publish_workflow.py` (12 locks). Changed: `.github/workflows/build-release.yml` (matrix / `if:` conditions / `-lt 8` / comment counts), `scripts/check_runtime_pins.py` (runner mapping + comments), `build_exe.py` (comment wording only), `src/ffmpeg_install.py` (import, fallback at the unified exit, `apt update` early exit turned into an `else:` block), `tests/test_ffmpeg_install.py` (two registries + 6 wiring locks, 116 cases in total), `tests/test_check_runtime_pins.py` (four `_MATRIX_KEYS` + a genuinely unregistered runner sample), `i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` (+20 entries each, `zh_CN.mo` recompiled). Docs: `AGENTS.md` +5 entries, `README.md`/`README_EN.md` artefact and image stances, this entry in both languages, and the rollback section of `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md` corrected. This unit produced no throwaway scripts |

### v4.5.0-dev (2026-10-02) — `CODE_REVIEW_2026-10-02` remediation finished: L-04/L-05 closed + three gate reds and three runtime defects introduced by the remediation itself corrected

> User framing: read `docs/worklog/CODE_REVIEW_2026-10-02.md`, extract every finding, locate the file and code position for each, and fix them one by one; follow the existing style, no refactoring beyond review scope; where an item is vague or unlocatable, state why instead of guessing; finish by running the project's build / test / static checks and report solved items, changed files, verification results and items still needing a human.

- **State on arrival (evidence before edits)**: **63 of the findings had already landed in a previous session** (source carries `（2026-10-02）` attribution comments, `tests/` carries the matching regression locks) but was never committed and the closing gates had never completed — `run_gates.py` stopped on the first command (black wanted 4 files reformatted) and the remaining 9 never ran. This session therefore centred on "verify each item truly landed" rather than re-applying it.
- **Report count corrected (measured before writing docs)**: the report header and the §3.2 matrix say "17 medium / 66 total", yet §5 enumerates M-01…M-18 = **18** items — the matrix's "tools / config / notification infrastructure" row omits M-01 (row says 3, is actually 4). Item-by-item count: 2 critical + 18 medium + 47 minor = **67**.
- **The two report items closed here**: ① **L-04** — `main.py`'s `platform_cookie` mapping was missing the two forced-direct-download platforms (`only_flv_platform_list = ["shopee", "花椒直播"]`): both `[Cookie] shopee_cookie` / `huajiao_cookie` are already read in main.py and passed to the resolvers, yet absent from the mapping, so one user cookie took two different routes — "resolve" versus "probe / ffmpeg record headers / direct download". Measured size of the gap: **50 declared `*_cookie` globals, 23 in the mapping, 27 missing**. Only the two platforms named by the report were added; the other 25 were **deliberately left out** — whether each platform needs a logged-in state to fetch a stream has not been confirmed by live packet capture, and adding them blindly changes the outbound request headers of 25 platforms. Regression lock `tests/test_platform_dispatch.py::test_forced_direct_download_platforms_carry_cookie` (AST invariant lock: both direct-download platforms must be present and bound to a `*_cookie` variable rather than an empty-string literal, with a reverse witness that reddens if the mapping disappears entirely). ② **L-05** closing step — the three dead module-level globals `pre_max_request` / `record_danmaku_args` / `seen_urls` had their declarations removed last round, but `main.py` still held `seen_urls = _seen_urls`; since `main()`'s `global` list does not contain `seen_urls`, that line only bound a function-local nobody reads. Removed it and corrected the adjacent "four collections swapped" count — falsified by the removal — to three.
- **Defects introduced by the remediation itself (4, none of them report items)**: ① `src/spider.py`'s L-10 log addition was written as `except Exception:` while referencing `type(e)` / `{e}` — reaching that branch raised `NameError`, turning "add a debug line" into a throw site; changed to `except Exception as e:` (reported by all three mypy passes — the only runtime defect this round caught by the type checker). ② `main.py`'s M-02 handed `url_data` (`tuple[str, str, str]`) to `mask_credentials`, which only accepts `str` and is entirely `re.sub` inside → `TypeError` escaping through the "content fetch failed, retrying" print; now `mask_credentials(str(url_data))`, leaving the template and the catalog msgid's `{url_data}` placeholder untouched. ③ `gui.py`'s L-39 moved `_log_queue_has_data = False` from "after a successful render" up to "as soon as the queue is drained", which fixed the permanent idle spin when only the sentinel was taken but punched through the M-15 lock "a raise mid-render must not kill the chain" (`test_log_flush_chain_rearms_when_render_raises` went red). L-39's unconditional clear is kept; the except branch of `_schedule_log_flush` now restores `has_data=True` so the `finally` rearms as before and the chain goes dormant naturally on the next empty drain (one extra idle tick, no renewed spin). ④ `src/spider.py`'s M-05 was changed to bare truthiness `if is_private` following the report's suggestion, and its comment's claim that this is "semantically correct for `"0"`/0/False" **is false** — `bool("0")` is True, so a public room whose API returns the string `"0"` was judged private and errored out every round. Now on the repo-wide parser `parse_config_bool(is_private, False)` (bool short-circuit / non-zero int / `"0"`·`"false"`·`"否"` tokens normalized; unrecognized values pass as not-private); the falsified conclusion was corrected in place with a one-line `[历史注]` per the comment conventions. Regression lock `tests/test_spider_platforms.py::TestPopkontvIsPrivateParsing` (10-cell bool/int/string matrix).
- **Two further gate reds**: after L-13 deleted `get_live_room_id`, `src/room.py`'s trailing `__main__` demo block was changed to `print("return sec_user_id:", sec_uid)` — a literal inside the i18n extraction surface but absent from the catalogs, so `test_runtime_templates_covered_by_catalog` was permanently red. Following the existing precedent (`return web_rid:` carries all four catalog entries) one entry was added to `zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` and `.mo` recompiled (833 entries = 832 keys + 1 empty header msgid; `compile_po.py --check` in sync). `tests/test_regression_2026_09_22_gui.py`'s `assert len(runs) == 4` was a stale count after L-40 removed two unreachable fallback filters — a hard-coded count expresses no judgement and merely tracks every legitimate add/remove, so it became "non-empty reverse witness + per-call `capture_output` / no-text-mode assertions".
- **Left alone**: the behavioural side of M-10 (whether `_is_same_origin` should trust `Sec-Fetch-Site`) — the report explicitly hands that to the maintainer as "fix behaviour or fix docs", and the previous session already took the docs route (`web_config.py` comment corrected + `web.py` warning text extended with that constraint); not widened here. The "待确认" items still need live capture: L-30's request-body ceiling value, L-44's TOFU stance, M-05's real field type. The three structural proposals in §8.3 (matrix-driven masking tests, machine-checked standalone backfill list, aligning "memory is bounded" claims with implementation) are new design and out of this batch. The stray untracked file `markdown-DX-TNHnc.js` that §2.3 recommends deleting **is already in the git index**; deleting it is the user's call — see "Residuals".
- **Verification** (readings taken 18:0x-18:4x, after this batch's last code edit; everything after that was documentation only, which no gate or test consumes): `python scripts/run_gates.py` - **all 10 commands PASS** (black actually re-formatted the 4 batch files first, then re-checked; isort; `mypy` with no arguments over 189 files at 0 issues plus `--platform linux` and `--platform win32` - all three clean; `check_annotations.py` over 203 Python files with 0 dangling symbol references, which is exactly what catches the call site left behind by L-05's global removal; `compile_po.py --check` in sync at 833 entries; `check_version.py`; `check_runtime_pins.py`; `check_skill_agents_consistency.py` consistent across 5 Skills - the suite's summary line for that last command had not flushed, so it was re-run standalone at `rc=0`). **Closing reading: `run_gates.py --keep-going` printed "all gates green: 10/10 passed (173.9s)" and its trailing pytest fallback also passed - "[PASS] pytest 3841 passed and empty warnings summary (408.2s)" - so the script overall exits 0.** An earlier run in the same tree had that fallback fail because `pytest` returned 1 (overall rc=1); it was never one of the 10 gate commands turning red, and the fallback going green afterwards is itself evidence that those subprocess failures were ordering/handle noise rather than code. Tool versions were not re-verified against the `ci.yml` consts (this machine's `python` is the user-level 3.14 core, not `.venv`), so 'local green' is not CI same-version green. Coverage: following the existing practice, `COVERAGE_FILE` was pointed at `%TEMP%` for `pytest --cov=src` (no `--cov-report=json`, so the tracked `coverage.json` and the doc readings are not rewritten by this run), then `python scripts/check_coverage.py` -> **PASSED: All 46 module(s) meet coverage threshold** (rc=0). Full `pytest --cov=src`: before this batch's fixes **24 failed / 3792 passed / 15 skipped**, after them **30 failed / 3786 passed / 15 skipped** (both totalling 3831), closing run **21 failed / 3818 passed / 15 skipped** (total 3854; the +23 belongs entirely to the parallel work package, see Residual 3). The three *deterministic* reds from before the fixes (i18n catalog coverage, gui log-flush chain, gui run-count lock) are gone from the closing failure list (`grep -c` reading 0); the remaining failures fall only in the six subprocess-family files `test_build_exe` / `test_ci_retry_action` / `test_notify` / `test_notify_script_guard` / `test_regression_2026_09_22_standalone` / `test_stop_recording_vbs`, and the basis for calling them environmental is that each of those files is **green when run alone** (build_exe 105 / ci_retry_action 12 / notify 4 / notify_script_guard 18 / stop_recording_vbs 11 / regression_2026_09_22_standalone 49 / run_gates 43 / regression_2026_09_22_gates 27) while every traceback stops in `subprocess._make_inheritable` with `WinError 6/50` (handle inheritance) - not one is an assertion failure. Redirecting stdin for the shell (`< /dev/null`, `< some-file`) was measured and does **not** remove them. Two mutation verifications, both via "back up bytes in memory -> rewrite -> run -> restore in `finally` and assert `read_bytes()` equality": the bare-truthiness form reddened the two string cells of `TestPopkontvIsPrivateParsing` (2 failed / 8 passed); deleting the `shopee` mapping key reddened the L-04 lock (1 failed). Restore witnesses True, zero `MUTATION-` residue repo-wide. Line-ending form: all 11 changed files re-measured - `main.py` / `gui.py` / `src/spider.py` stayed pure CRLF; the two test files had 44/18 stray lone-LF lines from heredoc appends (AGENTS blind spot #3, invisible to both black and AST comparison), normalized back to their original form and re-measured at lone-LF = 0; `core.autocrlf=true` explains why 'index stores LF / worktree is CRLF' is not a contradiction.
- **Not executed + handed back (DoD step 2)**: the incremental real-URL end-to-end run was **not executed**. Outbound network is reachable here (measured: `live.douyin.com` resolves and answers HTTP 200), but L-04 (shopee / huajiao direct download), M-05 (popkontv private rooms) added in this session and SR-01 (internal addresses inside playlist bodies) landed last round all need a **live room plus platform accounts** to produce a meaningful verdict, and `config/URL_config.ini` is the user's real room list — running `python main.py` immediately starts real recordings and writes outside the repo, an action requiring authorization. Please run these by hand when a live room exists and append the result to this entry: `python tests/test_douyu_live_collector.py <masked URL> 60` (douyu/huya cover HLS segment probing and the `codec=h265` chain) and `python tests/test_huya_live_collector.py <masked URL> 60`. There is **no** collector script in the repo for shopee / huajiao / popkontv; either add one following the four template constraints in "测试编写强制约定" (dual-mode script rules), or apply L-04's own verification method — compare request headers by packet capture to see whether `Cookie` reaches the probe and ffmpeg. Definition of Done steps 1→6 must not be declared complete on this basis.
- **Residuals (handed back; the agent must not delete these)**: ① `markdown-DX-TNHnc.js` — judged in report §2.3 a VSCode Markdown syntax asset dropped into the repo root by mistake and recommended for deletion in §8.3, but it is **staged in git** (status `A`); removing something the index already intends to track is the user's decision, so it is only listed here. ② Orphan catalog msgid `"return web_rid:"` — without references after L-13 deleted its only user (one entry in each of the four catalogs); AGENTS' "i18n 扫描盲区" note says orphans never turn a gate red and need manual review, and deleting it would also change the key counts already cited in CODE_WIKI/README, so it awaits the user's call. ③ **This working tree has a concurrent writer (not this session, not this batch)**: while closing out, another work package was implementing a "native Linux ffmpeg installer" in the same tree — untracked new files `src/ffmpeg_linux_download.py` and `tests/test_ffmpeg_linux_download.py` (19 cases), plus edits to `src/ffmpeg_install.py` / `tests/test_ffmpeg_install.py` (worktree 21 lines ahead of the index). The **+23 total-test drift (3831 → 3854) belongs entirely to that parallel batch** (19 + 4); this batch never touched those files. **[历史注]** the first version of this note recorded those two mtime changes as "a same-bytes rewrite, cause unknown" — that was my own evidence-gathering error: `git diff HEAD -- <untracked file>` is always empty for a file absent from HEAD, and I read "no diff" as "content unchanged". Lesson: to decide whether content was rewritten, use the tracked state from `git status --short` (`??` = untracked) plus `git ls-files --others --exclude-standard`, never an empty `git diff` alone. Knock-on effect: `check_annotations.py` reddens because that parallel new file `tests/test_ffmpeg_linux_download.py` has comment density 11.0% below the 13.0% threshold (not fixed here — editing it would clobber the other worker), and the coverage gate refused to grade the first run (rc=2, stale data, because `src/` gained a newer mtime). Therefore this batch's "gates green" reading **describes the moment after this batch's last edit**; the merge boundary remains CI's call.

| Remediation close-out | 11 files changed in this batch: `main.py` (L-04's two direct-download platform keys + L-05's dead assignment removal + M-02's argument shape), `gui.py` (has_data reset at the L-39 / M-15 seam), `src/spider.py` (L-10 `as e` + M-05 `parse_config_bool` + one import), `tests/test_spider_platforms.py` +1 class / 10 cases, `tests/test_platform_dispatch.py` +1 helper +1 lock, `tests/test_regression_2026_09_22_gui.py` count lock turned into a reverse witness, one entry each added to `i18n/zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` with `zh_CN.mo` recompiled (833 entries), and this entry (kept in sync across both languages). No throwaway scripts left behind (verification ran through heredocs and in-memory mutations; gate/test logs live outside the repo in `%TEMP%`/`/tmp`); runtime artefacts such as `logs/.pyc_stamp` stay untouched per the red line |

### v4.5.0-dev (2026-10-02) — New startup purge of stale bytecode caches: `src/startup_cleanup.py` (version + content-hash sentinel, whitelisted scan roots, switch defaults to on)

> User framing: add "clean `__pycache__` automatically before startup". During design review four candidate trigger strategies were on the table; the user picked "version-sentinel triggered, purge only once, plus a configuration switch that defaults to on", and approved landing items 1→8 as designed.

- **Why**: the source-run distribution upgrades by unpacking a zip over the existing folder, and copy tools routinely preserve source mtimes; when a changed module happens to keep the same byte length, CPython's (mtime, size) timestamp invalidation concludes the cache is still fresh and **silently keeps loading the old .pyc** (the symptom is "code changed but the old logic still runs", and neither the gates nor the logs point at the cache layer). Meanwhile "delete the whole tree on every launch" was measured locally at 345 ms of full recompilation per launch (51 files in that set), and the CLI / GUI recorder child / Web entry all share the same `src/` caches, each deleting what the others just rebuilt — so the trigger narrows to "the sources or the version actually changed".
- **Changes**: ① New `src/startup_cleanup.py`: scan roots come from a **positive whitelist** (the program folder's own top level plus every directory directly containing `.py` under `src/` — measured at 4 hits on this machine), and only `.pyc`/`.pyo` inside `__pycache__/` under those roots are reclaimed (files handled one by one, then the directory; anything else inside stays untouched and is reported — better to leave a directory behind than to reach for content we do not recognize). The baseline is `sha256(relative path + file bytes)` paired with the version string, stored in `logs/.pyc_stamp` as `version|hash`; it is written atomically via a same-directory temp file plus `os.replace`, deliberately **not** reusing `src.config_io._atomic_write_text` so the GUI process is never wired into the `main.file_update_lock` recording-engine lock family. `_IS_FROZEN` and a switched-off run both do zero I/O (no walk, no hashing, no baseline touch). A missing or unreadable baseline means "freshness cannot be proven" and costs one purge round; a failed baseline write still purges and warns (degrading to the same semantics as a user deleting caches by hand) rather than silently disabling the feature. ② `main.py` wires the call right after `utils.remove_duplicate_lines(url_config_file)` (+7 lines = 1 import, 1 blank, 2 lines of placement rationale, 3 lines of call): at that point `src.*` is fully imported, so the current launch is unaffected, and the single call site covers all three entries — CLI, the recorder child spawned by the GUI, and Web. ③ Three config surfaces stay equal: the switch key `是否启动时清理陈旧字节码缓存(是/否)` is read through `read_config_bool` (default on), `config/config.ini` gains 1 line (its UTF-8 BOM and whole-file CRLF preserved), `README.md` +3 lines and `README_EN.md` +4 lines in the config block. ④ Five new `tr()` templates were added to `zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml` and `scripts/compile_po.py` regenerated `.mo` (key sets across the four catalogs agree at 831↔831; the `.mo` header reports 832 = key count + the empty header msgid). ⑤ `AGENTS.md` "Key conventions" gains item 15, pinning "whitelisted roots" and "content hash, never mtime" as hard constraints together with their mutation-verification evidence.
- **Deliberately untouched**: `build_exe.py`'s pre-packaging bytecode removal and `RUNTIME_ARTIFACT_DIR_NAMES` (the sentinel lives inside `logs/`, already excluded by three surfaces, so no fourth exclusion convention is introduced); `tests/`, `scripts/`, `.venv/`, `node/`, `ffmpeg/`, `downloads/`, `logs/` stay out of reclamation scope; `scripts/douyin_live_recorder_standalone.py` is **deliberately not re-synced** — checked against the five mandatory twin-sync categories (sync_http opener whitelist / `-protocol_whitelist` / ffmpeg termination chain / `config_bool` boolean semantics / MID-49 signature encoding) and this change belongs to none, and as a single-file distribution its own bytecode lands in `scripts/__pycache__`, outside the whitelist anyway.
- **Verification**: TDD ran RED first (`ModuleNotFoundError: No module named 'src.startup_cleanup'`), then `tests/test_startup_cleanup.py` — 9 passed / 0 warnings. All three mutations were caught: ① turning the scan roots into a full recursive walk from the program folder → `test_purges_only_whitelisted_roots` turns red (**the first version of this case was a false green**: the out-of-scope locations held no `.py`, so a recursive walk could not reach them either; only splitting them into "has `.py` but is not a whitelisted root" and "inside the whitelist tree but holds no `.py`" pinned both rules); ② degrading the content hash to (size, mtime) → `test_same_size_same_mtime_content_change_is_detected` turns red; ③ dropping the "directory must contain `.py`" rule → same case as ① turns red. Each mutation ran as "in-memory byte backup → rewrite → run → restore in `finally` and assert `read_bytes()` equality"; all three reported byte-identical restore and zero `MUTATION-` residue. Function-level run against the real repository tree: run1 triggered, reclaimed 4 directories freeing 1,758,820 B in 12.9 ms while every cache under `.venv`/`tests`/`scripts` survived; run2 with sources and version unchanged → `triggered=False`, zero action, 7.8 ms; run3 with the switch off → 0.0 ms, zero I/O. Full `pytest --cov=src`: **3803 passed / 14 skipped / 3 failed** — all three failures belong to the in-flight worktree WIP (two `gui.py` AST structural pins, plus `src/room.py:261`'s leftover debug print reddening the i18n catalog-coverage gate); neither file was touched by this batch. `src/startup_cleanup.py` coverage is 88% (111 statements / 13 missed), above `GLOBAL_FLOOR=50%` for unregistered modules. `run_gates.py --keep-going`: six gates PASS (isort / check_annotations / compile_po --check / check_version / check_runtime_pins / check_skill_agents_consistency); black and all three mypy runs FAIL entirely on the WIP — black's four files are `main.py`/`src/spider.py`/`tests/test_web_api.py`/`scripts/douyin_live_recorder_standalone.py`, where `main.py` already had 4 hunks before this batch and still has 4 afterwards with none touching the added lines; mypy reports the same 3 errors on all three platform runs, none in this batch's files. The two new files pass black + isort + mypy individually and are pure LF with no mixed line endings.
- **Not executed (honest boundary)**: DoD step 2's real three-entry startup run was **not executed** — this machine's `config/URL_config.ini` holds the user's real room list, so running `python main.py` / GUI / Web would immediately start actual recordings and outbound requests, an effect that needs the user's authorization. This batch touches no recording chain / source selection / ffmpeg arguments / platform parsing, so step 2 is exempt by definition and the real-tree two-round plus switch three-round measurements above stand in. **Handed back to the user**: after the next normal start, finding one line in `logs/PlayURL.log` — "源码或版本已变化，已清理 N 个字节码缓存目录（释放 X KB）" — is the evidence the wiring is live (the message is INFO level, and per `src/logger.py`'s level split it goes to `PlayURL.log`, not `streamget.log`; this batch already captured two such lines there, most recently `2026-10-02 14:50:24.920`).
- **Residue (handed back; the agent must not delete it)**: `logs/.pyc_stamp` written by the feature during verification (current value prefixed `v4.5.0-realcheck-2`) is still on disk. It sits in a runtime-artifact directory, and per the "Risk control · cleanup scope" red line plus the project hook's R-CLEAN-SCOPE rule the agent may not dispose of it (the attempt was blocked on the spot, as measured). Leaving it costs one extra cache-reclaim round at the next start (one-off, harmless); to zero it immediately, please handle the file yourself.

- **Local test-surface noise (found while gathering evidence for this batch, not introduced by it)**: the full-suite failure count swings between 3 and 24 across identical commands, and the cause is **import order**, not code. The six files `tests/test_ci_retry_action.py`/`test_build_exe.py`/`test_notify.py`/`test_notify_script_guard.py`/`test_stop_recording_vbs.py`/`test_regression_2026_09_22_standalone.py` fail a fixed 20 cases when run alone, yet drop to **0 failures** as soon as any test file that has already imported the `src` side is placed before them — the control experiment used `tests/test_config_bool.py`, which this batch never touched (261 passed), alongside this batch's own new file (208 passed), and both produced the same shape, so this red cannot be charged to this batch. `WinError 6` (child processes inheriting a closed stdin) appears 23 times in the failure output, matching the same-family environment pit already recorded in `docs/agent-reference/session-learnings.md`. Left as a separate follow-up: those six files should carry their own import precondition or pass an explicit `stdin=` to their children.

| Runtime and startup chain | New `src/startup_cleanup.py` (111 statements) and `tests/test_startup_cleanup.py` (9 cases); `main.py` +7 lines of wiring; `config/config.ini` +1 key; `README.md` +3 / `README_EN.md` +4 lines; `AGENTS.md` key conventions +1 item; i18n four catalogs +5 entries each with `.mo` recompiled; `docs/agent-reference/session-learnings.md` +3 entries; this entry (zh/en in sync). No throwaway scripts left behind — all verification ran inline via `python -c` and heredocs; the single residue is described above |

### v4.5.0-dev (2026-10-02) — The "register every new front-end `.mjs` in CI" rule gains a repo-side completeness lock: new `tests/test_ci_frontend_registration.py` (two-way set difference + self-hosted pin)

> User scope: turn the existing rule into a lock that ships with the repository and holds for every contributor and for CI itself, converged onto one deterministic comparison (enumerate `tests/frontend/*.mjs`, diff against the entries named by the ci.yml "Gate frontend tests not skipped" step, fail when the difference is non-empty); reuse the existing two-file convention and the existing pinning style (the list↔config two-way pin of `tests/test_pre_commit_config.py`), add no second gate list and do not touch the `python_build`/`node_version` constants.

- **Root cause**: the rule only had two carriers — the prose bullet in `AGENTS.md`"Testing" and the PostToolUse rule P-MJS-REGISTER in `scripts/agent_hook_guard.py`. The latter lives in the local `.qoder/` tool directory (`AGENTS.md`"Project-level Hooks / Commands": not distributed with the repository, must never enter the image), so it says nothing about other contributors or about CI itself: someone without the Hook can re-import the M-28 shape (wrapper written, list not updated, the regression locks of that file never executed in a normal CI run) and CI stays green.
- **Changes**: (1) new `tests/test_ci_frontend_registration.py` (5 cases): precondition guards (the step exists exactly once, node-ids are parseable from it, the directory enumeration is non-empty, the mapping mechanism yields something — all against "a green light that scans nothing"), forward difference (every `.mjs` must be referenced by some **registered** wrapper), reverse difference (a registered wrapper exists, the named test function is really defined, the referenced `.mjs` is still on disk), a self-hosted pin (this lock's own entry must be in the list) and a gate self-check (a minimal synthetic repository under `tmp_path`, only the three path globals of this module swapped, proving both differences really report). The wrapper↔case mapping is taken from the path constants in the wrapper's AST, not from a same-stem coincidence — two of the four existing wrappers sit in `tests/` and are named differently from their `.mjs`, so copying the Hook's same-stem criterion would flag those legitimate shapes red. (2) the node-id list of that ci.yml step gains `tests/test_ci_frontend_registration.py::test_every_frontend_mjs_is_registered`, with four provenance comment lines appended above the step (append-only). (3) one sentence added to the `AGENTS.md`"Testing" bullet: completeness is machine-checked by that case, and the local Hook is only an immediate-feedback channel that cannot replace it.
- **Untouched**: the `python_build`/`node_version` constants, the step's "any skip is red" criterion and every other job, the `tests/frontend/*.mjs` cases themselves, the Hook's P-MJS-REGISTER rule (kept as write-time feedback), and the gate command list (`run_gates.py` still parses `AGENTS.md`, no parallel list added).
- **Verification**: directory side probe — dropping an unregistered `tests/frontend/tmp_probe_unregistered.mjs` turned only `test_every_frontend_mjs_is_registered` red, naming that file verbatim (1 failed / 4 passed), and 5 passed again after deleting it; list-side mutation ran in the "back up in memory → rewrite → run → restore by bytes and assert equality" single-process form — removing this lock's entry from the list turned `test_lock_itself_runs_inside_the_frontend_gate` red with `RESTORED_BYTE_IDENTICAL: True`. The new file is clean under black / isort / mypy (single-file run) with pure CRLF endings. The black/mypy failures of the full `run_gates.py` run all land on work-in-progress in the working tree (`main.py`/`src/spider.py`/`tests/test_web_api.py`/`scripts/douyin_live_recorder_standalone.py`); the full pytest run reports 3782 passed / 14 skipped / 11 failed, those 11 being the WIP above (the i18n template `return sec_user_id:` and the gui `_schedule_log_flush`) plus this machine's bash entry being disabled by the WSL service (0x80070422) — none of them points at this batch. This batch does not touch the recording chain, source selection or ffmpeg arguments, so DoD step 2 (real-device verification) is waived.

| Docs & gates | This batch is a test-asset + CI-list change: one new `tests/*.py`, `ci.yml` +1 id line and +4 comment lines, one sentence in `AGENTS.md`, plus this entry (CN/EN synchronised); the probe and the one-off verification script are both deleted, zero residue |

### v4.5.0-dev (2026-10-02) — CI typecheck gate completes the platform double-run: add `mypy --platform win32`, win32 target participates in type checking at the merge boundary for the first time (pure CI / gate change, zero runtime change)

> User scope: close the declared "double-run" gate onto the merge boundary — inside the typecheck job, add one win32-target run symmetric to the existing linux-target run, same `[tool.mypy].files` range, equally without path arguments; do not narrow the check scope, do not add a parallel list, do not touch the pytest/node constants.

- **Root cause**: `AGENTS.md`"Formatting commands (the single gate baseline)" has long declared the mypy platform double-run (bare run + `mypy --platform linux`), but the CI typecheck job ran only one bare `mypy`, which on the ubuntu runner defaults to the linux target — so win32-gated branches (`ctypes.windll`, `subprocess.STARTUPINFO`, etc. inside `if sys.platform == "win32":`) were only incidentally checked on a Windows dev box and never verified at the merge boundary, an inspection-surface gap of "local green, CI cannot judge win32".
- **Changes**: (1) split the `ci.yml` typecheck job into two steps — `Run mypy (linux target)` (bare `mypy`, = linux on ubuntu) plus a new symmetric `Run mypy (win32 target)` (`mypy --platform win32`), same range, both without path arguments, the job-level `if` filter condition unchanged. (2) add a third line `mypy --platform win32` to the `AGENTS.md` gate bash block (symmetric to `--platform linux`) so `run_gates.py` covers both linux and win32 on any host; sync the mypy section's "platform-symbol gated double-run" bullet and the run_gates explanatory bullet, keeping a single adjudication basis with no second source of truth.
- **Untouched**: pytest / node constants, the `ci-summary` needs list and its `failure/cancelled` criterion, and the check scope (`[tool.mypy].files`) — `typecheck` is still depended on as a single whole job by `ci-summary`, and when path-filtered out (including the new step) it skips as a unit and is treated as passing, semantics unchanged.
- **Validation**: locally with mypy 2.3.1 (matching the CI consts pin) over the full `[tool.mypy].files` 186 files, three passes — bare `mypy` (win32 host), `--platform linux`, `--platform win32` — produced **byte-identical line-by-line output** (`Compare-Object` empty), proving the win32 target agrees with linux on the judgement surface and conflicts with no existing `# type: ignore` (no "required on one platform, unnecessary on the other" ignore). The 3 errors present in all three passes come from in-flight WIP in the working tree (`main.py`/`src/spider.py`), identical across platforms and platform-independent, out of this batch's scope. `run_gates.py --list` resolves the full list including `mypy --platform win32`; `ci.yml` YAML validity + `ci-summary.needs` containing `typecheck` re-verified; regression locks `tests/test_pre_commit_config.py` (7 passed) and `tests/test_run_gates.py` (42 passed / 1 skipped) unaffected. This batch does not touch the recording chain / source selection / ffmpeg parameters, so DoD step 2 real-machine validation is waived.

| Docs & gates | This batch is a pure CI / gate config change: `ci.yml` typecheck job + `AGENTS.md` gate block and two explanatory bullets + this entry (bilingual sync), zero `.py`/frontend asset changes; no one-off scripts left behind |

### v4.5.0-dev (2026-10-02) — workspace-wide code review (producing `docs/worklog/CODE_REVIEW_2026-10-02.md`): 8 work packages of per-file deep review + Mimosa deep-scan triage, 2 critical / 17 medium / 47 minor

> User brief: comprehensively review all source code in this workspace (Python/JavaScript/Node.js etc., excluding node_modules, dist, build), focusing on code quality, potential defects, security vulnerabilities and logic errors; record findings per file and classify them by severity into a formal report.

- **Report**: [`docs/worklog/CODE_REVIEW_2026-10-02.md`](CODE_REVIEW_2026-10-02.md) (review-record wildcard already excluded via `.dockerignore`, not shipped in the image). Eight parallel deep-review work packages covered main.py / gui.py / spider.py / source-selection & HTTP / danmaku / web front+back / infra / build & install chain / the standalone twin / test-risk patterns; all 66 findings carry line numbers and fix suggestions.
- **Two critical items (both line-level verified; "defense wiring/backfill gaps", not "missing defenses")**: SR-01 `_probe_hls_segment` in `stream_select.py` keeps a candidate "reachable" (`return True`) even when a playlist-body-derived address fails the internal-network gate (contradicting the WP-J comment in the same function), letting an internal target reach ffmpeg via a hijacked playlist; SR-02 the standalone probe opener whitelist includes `HTTPRedirectHandler` with no per-hop re-check — the mainline hop-guard added 2026-09-30 was never backfilled to the standalone distribution.
- **Reproduced by execution**: `mask_credentials` passes Bilibili `SESSDATA`/`bili_jct` and Douyin `sessionid_ss`/`sid_tt` through unchanged (M-01, a new instance of the key-agreement-#11 family); `httpx.InvalidURL` inherits directly from `Exception` (M-06 exception-set gap holds).
- **Cross evidence**: `basedpyright` 0 error / 0 warning / 0 notes; Mimosa deep scan (`scan-2026-10-01T18-57-00.175Z-21bb8f2f1ff5`, 40 raw alerts) triaged to **0 newly confirmed vulnerabilities** and 3 informational (run_gates `shell=True` on repo-controlled input, Haixiu/LiveMe platform anonymous tokens, 1 dependency advisory match); tests/ spot-check found no MUTATION residue, no real-shaped credentials, no over-broad mocks.
- **Follow-ups**: Chapter 8 of the report — five P0 items (two critical + two credential-masking + the node startup-crash guard), P1 in batches, P2 opportunistically; three structural suggestions (matrix-driven masking-key tests / standalone backfill checklist machine-check / align "memory-bounded" claims with implementations).

| Docs & gates | Docs-only batch: added `docs/worklog/CODE_REVIEW_2026-10-02.md` + this entry (CN/EN synced), zero code changes; exempt per DoD: step 1 gates N/A (no `.py`/frontend asset changes), step 2 live verification N/A (no recording-chain/source-selection/ffmpeg-argument changes), steps 3/5 N/A (no regression-lock changes, no one-off scripts produced) |

### v4.5.0-dev (2026-10-02) — Harness assets added: project-level hook body `scripts/agent_hook_guard.py` + `/dlr-dod` command entry

- **Trigger**: the better-harness review found that AGENTS.md's high-frequency manual flows were backed only by prose, with no lifecycle owner, so every session had to remember each judgement on its own. The user asked to "create project-level hooks or commands assets for the high-frequency manual flows in AGENTS.md", with acceptance defined as "at least one asset exists + its trigger conditions match the AGENTS.md constraints". (This invocation carried no `better-harness-fix-output` machine callback, so no fix record was written into a historical findings.json.)
- **Changes**: (1) New `scripts/agent_hook_guard.py`: reads one Qoder hook event as JSON from stdin and blocks with exit code 2. `PreToolUse` (Bash) rules — `R-PIP-BULK` (bulk venv dependency reinstall; only `--force-reinstall` and `--ignore-installed`+`-r` are blocked, the documented single-package repair path stays allowed), `R-CLEAN-SCOPE` (a delete statement whose target reaches a runtime artifact directory or `scripts/`; `-notmatch`/`-Exclude` exclusion clauses are not treated as targets; statements split on `&&`/`||`/`;`/newline while a pipeline stays one statement), `R-WIPE-SCOPE` (recursive/wildcard deletes with no `-Include`/`-name` filter, plus `git clean -f*`). `PostToolUse` (Write/Edit) rules — `P-MUTATION` (mutation-verification marker left in code: invisible to black / mypy / the annotation checker), `P-LINE-ENDING` (a `.py` carrying both CRLF and lone LF, the fingerprint of a silently flipped whole-file rewrite), `P-MJS-REGISTER` (a `tests/frontend/*.mjs` missing from the ci.yml node-id list, the M-28 class). Denial messages give only the short rule id and the matched directory name, never the command verbatim; script errors and unrecognised event shapes fail open.
- **Changes (cont.)**: (2) Wiring: `.qoder/settings.json` registers `hooks.PreToolUse` (matcher covering Bash) and `hooks.PostToolUse` (matcher covering Write|Edit|SearchReplace) on that script; new `.qoder/commands/dlr-dod.md` (`/dlr-dod`) is only the Definition of Done 1->6 entrypoint, delegating to `scripts/run_gates.py` and `scripts/check_coverage.py` and copying no gate parameters. Both live under `.qoder/`, which `.gitignore`/`.dockerignore` already exclude, so they ship neither with the repository nor in the image. (3) A new "Project-level Hooks / Commands (lifecycle assets)" table plus two rules follow the "Project-level Skills" chapter in `AGENTS.md`. (4) New `tests/test_agent_hook_guard.py` with 33 cases: behaviour locks (both block and allow faces), the consistency lock (protected directory set == the AGENTS.md "runtime artifact directories" enumeration), the CLI contract (stdin JSON -> rc 2/0, unknown events fail open), the asset-wiring lock (skips when `.qoder/` is absent instead of pretending to be a repository gate), and four in-memory mutation proofs (no disk writes, no markers left behind).
- **Side fix**: `scripts/check_skill_agents_consistency.py` (an untracked script from an earlier session, already gate #9) kept `black --check .` permanently red; it was reformatted to the black style, with `ast.dump` sha256 identical before and after (`ea18a7f57727710e`) and no logic change.
- **Verification**: all 9 commands of `python scripts/run_gates.py` reported [PASS] (including `mypy` without arguments over 186 files with 0 issues, `mypy --platform linux`, `check_annotations.py`, and `check_skill_agents_consistency.py` agreeing on 5 Skill rows); `pytest tests/test_agent_hook_guard.py tests/test_test_hygiene.py` gave 552 passed / 0 warnings (the R8 repository scan had caught the mutation-marker literal inside this script's own comments, rewritten per the self-reference avoidance rule); live hook evidence: bulk reinstall command blocked with rc=2, both AGENTS.md cleanup commands and `python scripts/run_gates.py` allowed with rc=0, `--self-test` rc=0 over six sample shapes; every edited file stayed pure CRLF. **The full `pytest` run is not reliable in this agent shell**: the same command yielded 22 then 17 failures across two runs, and moving the two new files out of the repository still produced 9 failures from the same set. Causes are child processes inheriting an already closed stdin (`OSError WinError 6`) and `bash` resolving to a Windows stub (`0x80070422`) — environment limits, not code regressions; the pytest warnings-summary fallback at the end of `run_gates.py` therefore reported rc=1 and cannot be used as a conclusion. This change touches no recording chain / source selection / ffmpeg parameter, so DoD step 2 (live platform verification) is exempt.

### v4.5.0-dev (2026-10-02) — v4.4.0 documentation finalized: 20 headings in both wikis renamed v4.4.0-dev → v4.4.0 + five backfills into the README v4.4.0 entries

- **Trigger**: the user's "version-doc sync" task: summarize the complete 4.4.0-dev changelog in CODE_WIKI by four categories, write it into the README v4.4.0 entries, and unify the version number 4.4.0-dev to 4.4.0. Both READMEs already had a v4.4.0 entry (added 2026-10-01, when the -dev headings were deliberately left unchanged); this batch is the explicit reversal of that decision plus the entry backfill.
- **Changes**: ① the 20 `### v4.4.0-dev` headings in `CODE_WIKI.md` / `CODE_WIKI_EN.md` unified to `### v4.4.0` (a verbatim replacement of the version segment only; dates and bodies untouched; v4.3.0-dev/v4.5.0-dev are out of scope). ② The v4.4.0 entries in `README.md` / `README_EN.md`, compared item by item, gained five backfills: the title and summary extended from "three things" to "four" to include the HEVC deadlock root cure; a new first bullet in 🐛 Fixes for the douyin HEVC-origin-room "no usable source" deadlock (three-rule-stacking root cause + the `flv_url_list` fallback + `E2E_RESULT: CURED`); a new ✨ bullet for h265 candidates admitted by save format + the zero-source observability warning; a new 📦 bullet for the urllib3 floor 2.7.0 → 2.8.0 (CVE-2026-97687/97688/97689); a new 🛠️ bullet for the two test-side fixes (the singleflight Linux CI false-reds' POSIX stub and the `test_notify` wall-clock margin derived from production constants) plus the "three gate-wording corrections" folded into the AGENTS bullet. ③ Reading corrections: pytest 3690 → **3721** (final state, 10-01), overall coverage 85% → **84.9%** (per coverage.json), the i18n key count 808 annotated with the "final 809", and a new 🧪 bullet for the three-state live PASS on the 10-01 HEVC-origin room.
- **Verification**: all four files keep pure CRLF (both READMEs +5 lines each, LF-only still 0); repo-wide grep for `4.4.0-dev` residue is 0; the bilingual entries stay section-by-section symmetric (✨/🐛/⚠️/📦/🛠️/🧪) with 5 new bullets each; documentation-only change with no gate consuming README/CODE_WIKI bodies, so per DoD exemption only the affected gate surface runs (none).

### v4.5.0-dev (2026-10-02) — recompute four signature-script pin-table entries: trailing-byte drift from pre-commit's end-of-file-fixer

- **Trigger**: after the user ran pre-commit, `end-of-file-fixer` appended a trailing newline to each of `src/javascript/{crypto-js.min.js, x-bogus.js, haixiu.js, liveme.js}` — `utils._check_js_hash` hashes **raw bytes** (rb) and compares against the pin table, so the tail-byte change mismatched all four entries: by default every execution of these scripts logs a "hash mismatch" warning (x-bogus.js is the douyin signing chain), and with `DLR_JS_STRICT_HASH=1` execution is refused outright; migu.js already ended with a newline, was left untouched, and still matches. The three JsPinTable tests in `test_utils.py` only lock the key set / file existence / bidirectional directory-table equality and never compare actual hashes — a fully green pytest cannot catch this drift (a fourth blind-spot class beyond the known three).
- **Change**: the user picked **recompute** among the three options (revert files / exclude in the hook / recompute the table); `src/utils.py::_JS_SHA256_EXPECTED` updated for all four entries against current raw bytes, with a dated recompute note (old values archived in truncated form; migu.js untouched). The hook is idempotent from here on (files now end with a newline), so recomputing is the stable end state rather than a temporary cover-up.
- **Verification**: hashing all 5 on-disk scripts against the live table matches everywhere; `pytest tests/test_utils.py` 81 passed / 1 skipped; targeted black check unchanged; a repo-wide grep for the old hash prefixes only hits the historical note in utils.py; `src/utils.py` line-ending form unchanged (pure CRLF).

### v4.5.0-dev (2026-10-02) — version bump 4.4.0 → 4.5.0 + pre-commit added to dev extras: workspace-wide metadata sync and derived-artifact regeneration

- **Trigger**: two source-of-truth changes in `pyproject.toml`: `[project].version` 4.4.0 → 4.5.0; `[project.optional-dependencies].dev` gains `pre-commit>=3.6.0` (paired with the root `.pre-commit-config.yaml`, the pre-commit hook definition).
- **Sync surface**: `AGENTS.md` version line + the "dev/build/GUI dependency" enumeration (six → seven entries); `docker-compose.yaml` header `.env` example `APP_VERSION=4.4.0` → `4.5.0` and the Web service comment "FastAPI/uvicorn" → "Starlette/uvicorn" (fastapi was removed in the v4.4.0 phase-2 migration; the comment kept the stale fact); `requirements.txt` header comment's .dev enumeration gains pre-commit; `.dockerignore` adds the bare pattern `.pre-commit-config.yaml` (dev-tool config, kept out of the image like scripts/); the header version lines of `CODE_WIKI.md`/`CODE_WIKI_EN.md`. **README (both languages) unchanged**: the dev install line is already the canonical `pip install .[dev]` form (points at the extra itself without enumerating packages, so dev-group additions cause no drift), and the v4.4.0 changelog entries are historical records; runtime dependencies remain 21 (pre-commit is a dev extra, not in requirements.txt).
- **Artifacts**: `uv.lock` and `DouyinLiveRecorder.egg-info` regenerated via `python scripts/sync_metadata.py`, no hand edits: uv.lock root 4.5.0 + dev extra gains pre-commit 4.6.2 (current resolution, satisfies the >=3.6.0 floor) plus 7 transitive packages (cfgv 3.5.0 / distlib 0.4.3 / filelock 4.0.8 / identify 2.6.20 / nodeenv 1.11.0 / python-discovery 1.6.1 / virtualenv 21.14.2), with zero changes to existing pins; egg-info PKG-INFO, besides version and the dev extra, also absorbed the current README long-description (empty `language =`, loop interval 60, HLS-exclusion example 虎牙, https-recording/danmaku example values, etc. — README had been edited earlier while the old PKG-INFO was never regenerated; `sync_metadata --check` only compares version and the dependency list, not the long description, so the previous reconciliation could not see it).
- **Verification**: `sync_metadata.py --check` OK (uv.lock / egg-info both 4.5.0); `check_version.py` PASS (all dynamic consumers OK: main / web_api / Dockerfile); `pytest tests/test_regression_2026_09_22_gates.py` 27 passed; `git diff` review confirms uv.lock changes are only the root version + new package nodes, no drift in existing pins.

> **Rolling archive**: v4.4.0 and every earlier entry has been moved as a whole into [docs/changelog/code-wiki-history-en.md](docs/changelog/code-wiki-history-en.md); this section keeps only the current release cycle.
