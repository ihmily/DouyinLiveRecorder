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
| `code-wiki-history-en.md` | The 164 historical entries of this document's changelog (2026-05-17 ~ 2026-09-24) | `CODE_WIKI_EN.md` "Changelog" |
| `code-wiki-history-zh.md` | Chinese counterpart of the entries above (164, one-to-one) | `CODE_WIKI.md` "更新日志" |
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
| tkinter.ttk + pystray + Pillow | GUI and system tray |
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
│   ├── ab_sign.py                      # 抖音签名算法 (A-Bogus)
│   ├── node_install.py                # Node.js 自动安装/初始化
│   ├── ffmpeg_master_download.py       # FFmpeg master-build downloader (per-platform/arch fetch + verification, challenge-page aware, TOFU)
│   ├── ttwid.py                        # 抖音访客 ttwid 获取
│   ├── web_api.py                      # Web 管理面板 Starlette 应用
│   ├── web_models.py                   # Web 请求体校验层（纯标准库 dataclass + parse，替代 pydantic）
│   ├── web_config.py                   # Web 面板配置读写（不依赖 Web 框架）
│   ├── web_tray.py                     # Web 模式系统托盘（Windows 最小化到托盘）
│   ├── ui_theme.py                     # GUI 主题层（语义 token + 多主题 + ttk 注册 + 持久化 + 对比度机检）
│   ├── ui_kit.py                       # GUI 控件工厂（ttk 变体样式映射 + Treeview 增量表格 + 过渡动效原语）
│   ├── ui_scale.py                     # GUI 度量层（语义字号 token + 间距栅格 + 全局缩放档位 + 小屏降档）
│   ├── ui_motion.py                    # GUI 动效层（off/subtle/full 三档 + 插值原语 + 系统「关闭动画」感知）
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
│   ├── base.py                          # 弹幕基类与数据结构（DanmakuBase / DanmakuMessage / DanmakuMessageType）
│   ├── collector.py                     # 弹幕采集器（线程化包装 DanmakuBase，落 SRT + 上报监控枢纽）
│   ├── cookie_cache.py                  # 按 URL 的访客 Cookie 进程内缓存（防并发重复请求触发风控）
│   ├── danmaku_monitor.py               # 弹幕监控枢纽（进程单例，内存快照 + JSONL 边车）
│   ├── srt_writer.py                    # SRT 字幕分段写入（时间轴对齐 ffmpeg segment）
│   ├── ws_client.py                     # 弹幕 WebSocket 传输层（各平台弹幕共用，proxy=None 直连）
│   ├── log_archive.py                   # 运行日志归档（停止录制流程收尾：四日志按时间戳改名）
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
├── gui.py                               # GUI 图形界面入口（tkinter.ttk + src/ui_kit）
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
│   ├── test_ab_sign.py                 # A-Bogus 签名算法测试
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

### Signing Algorithm (`src/ab_sign.py`)

Douyin's A-Bogus signing algorithm, including:

- SM3 hash
- RC4 encryption
- Complex parameter obfuscation

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
| pystray | >=0.19.5 | System tray (GUI / Web tray mode) |
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
│   ├── src/ab_sign.py
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

# 阶段 2: runtime
# - 精简基础镜像 + apt 安装 ffmpeg / nodejs(24 LTS) / tzdata / procps
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
- `excludes`: CLI excludes GUI/Web libraries (tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette); GUI excludes Web libraries; Web excludes GUI libraries; all three entries additionally exclude `brotlicffi` (fixes the post-packaging error of the `brotlicffi` module missing the `error` attribute; httpx auto-falls back when no brotli is present).

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
| `ab_sign.py` | ≥95% | 99% |
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

### v4.4.0 (2026-10-01) — admit h265 candidates by save format (TS/MKV/MP4 can stream-copy HEVC) + zero-source observability for the silent HLS config drop

- **Trigger**: the two deferred candidate improvements from the same-day previous entry (origin-HEVC-room deadlock root cure); the user approved both ("relax + observe").
- **Change**: ① `src/stream_select.py` adds `_h265_copy_format_supported()` — it reads main's hot-reloaded global `video_save_type` and decides whether the configured container can stream-copy HEVC: TS(mpegts)/MKV(matroska)/MP4 muxers support it (the same fact as main.py forcing record_save_type=TS when an h265 address gets selected); FLV (HEVC-in-FLV is an Enhanced-FLV extension, unsupported by the repo's stance), MP3/M4A audio-only formats (no video track), out-of-domain/missing values all conservatively count as unsupported. The h265 filter narrows from "drop unconditionally" to "drop only when stream copy is unsupported", so TS users now get the h265 origin FLV primary candidate into the regular sequence for probing; the falsified blanket wording "h265 cannot be copy-recorded" in the `_is_h265` and sequence-construction comments is corrected in place with a dated history note per the comment convention. ② `main.py`'s h265→TS forcing block gains the same-predicate guard: when the save format is already TS/MKV/MP4 it no longer takes over nor logs "use TS format instead" (otherwise TS users would get one misleading warning per round); FLV/audio formats keep the original forcing semantics. ③ Before the no-source conclusion, a new observability warning fires when m3u8 candidates were dropped as a whole by the HLS config (global switch / exclusion list) AND the round ends with no usable source — naming the cause, the candidate count and the recovery switches; this was the only "zero-log" source-selection cause (the 2026-10-01 deadlock-room blind spot: with an FLV fallback present the early-exit warning never fired and the sequence showed no trace of the m3u8); it stays silent on rounds where a source is found. All four i18n catalogs register the 1 new msgid (zh_CN.po tail section + bumped PO-Revision-Date; en/en_GB corner brackets to double quotes; zh_TW terminology aligned 採集/清單/丟棄) and zh_CN.mo is recompiled (810 records = 809 keys + header).
- **Regression locks**: `tests/test_stream_select.py` gains the h265×save-format dual matrix (TS/ts/MKV/MP4 admit and select the h265 primary first; FLV/MP3/M4A音频/webm/empty drop it onto the h264 fallback, both asserting zero probes on h265), the `_h265_copy_format_supported` decision matrix (11 cells incl. case/whitespace/out-of-domain/None/int) plus the missing-global conservative fallback, and 2 observability cases (the warning fires exactly once on the failing round and never on a healthy round); `tests/test_main_fixes.py`'s two h265 source-selection cases pin the save format explicitly with history notes as the semantics narrow; `test_excluded_platform_h265_flv_not_switched_to_hls` pins FLV the same way. Mutation verification: inverting the predicate (MUTATION-H265RELAX) turned 24 cases red, force-disabling the observability condition (MUTATION-HLSOBS) turned the positive case red; both restored byte-exact with zero marker residue.
- **Verification**: `pytest --cov=src` 3720 passed / 14 skipped / 1 failed — `tests/test_notify.py::test_run_script_timeout_kills_process` hit the 4.0s assertion margin at 4.04s; attributed at the time to "session-sandbox environment state", **an attribution the user's normal-PowerShell rerun later disproved** (see the correction below).
- **Follow-up correction (2026-10-02 00:41, after the user-terminal reproduction)**: the same case still failed in the user's normal terminal (elapsed=4.01s) → a control experiment re-characterized it: `proc.kill()` (direct Popen kill) 0.01s, PowerShell `Stop-Process` 0.71s, `taskkill /?` 0.10s, while `taskkill /F /PID` terminating a real process takes a steady **2.5~3.1s** (rc=0, CPU at 6%) — what is slow is taskkill.exe's own implementation path (WMI signature), not the process-termination action and even less this repo's code; the 1s test timeout plus ~3s taskkill lands exactly on the hand-tuned 4.0s margin. Fix: the case's wall-clock bound is now **derived from the production constants** (`_SCRIPT_TIMEOUT_SECONDS + _TREE_KILL_TIMEOUT_SECONDS + 2.0`, ≈8s) — taskkill consuming its own full 5s budget no longer false-alarms, while "unbounded blocking / tree-kill over budget / hung pipe reaping" still trips the bound red; the original "does not occupy the calling thread after timeout" intent is unchanged, and the per-behavior locks remain in `tests/test_notify_script_guard.py`. The machine-state root cause (why taskkill/WMI takes ~3s) is an OS-layer matter outside this repo's scope. Lesson: a test's time margin should be derived from the tested path's production constants, never hand-tuned — a hand-picked value silently assumes "external tools in their healthy state", which both false-alarms and defies attribution when machine state shifts.
- **Verification (final, after correction)**: `pytest --cov=src` **3721 passed / 14 skipped / 0 warnings**, `check_coverage.py` all 44 modules meet threshold, basedpyright 0 error / 0 warning, `compile_po --check` in sync, `run_gates.py` all 8 gates green. Live verification (live HEVC-origin room 127453393722 央视网快看, inline source-selection script): HLS off + ts → **the h265 FLV primary was admitted and selected** (codec=h265, probe passed for real); HLS off + FLV → fell onto the h264 origin fallback (codec=h264); HLS off + FLV with the fallback stripped → None with the new observability warning fired for real (English catalog form with recovery switches and the anchor name) → all three states PASS.

### v4.4.0 (2026-10-01) — root cure for the douyin HEVC-origin-room "no usable source this round" deadlock: keep the replaced h264 origin FLV in `flv_url_list` when substituting hevc

- **Trigger**: user's running-instance log — two douyin origin-quality rooms (H131-好几百个八 / newly added 大山摩旅中国) logged `h265 codec candidate cannot be recorded with stream copy, skipping` → `选源结论: platform=抖音直播 本轮无可用源` → skipped recording every round while the streamers were live; the status line's cumulative error count stayed 0 (source-selection failure rounds do not feed error samples, so the status line alone looks healthy).
- **Root cause**: three individually-correct rules composing a deadlock. ① `src/stream.py::get_douyin_stream_url` replaces the h264 FLV with the h265 FLV as the **only** FLV candidate when the origin tier is requested (quality_index==0) and the API publishes `hevc_flv_url` (triggered only when m3u8 is not h265); ② `select_source_url` drops every `codec=h265` candidate before probing (h265 never enters the regular candidate sequence; only the record_url last-resort channel can carry it); ③ with HLS collection disabled in the running instance, the h264 m3u8 group is dropped **silently** (the "HLS not enabled" warning fires only when there is no FLV/record_url fallback), and record_url (douyin = `m3u8_url or flv_url`) is disabled in tandem because it is an `.m3u8` — leaving zero usable candidates after the h265 filter. Log-reading evidence: "h265 warning → source conclusion" within the same millisecond = zero probes emitted after filtering; absence of the `record_url has h265 codec` English warning = record_url was the m3u8 (i.e. the m3u8 existed every round rather than being absent).
- **Change**: `src/stream.py::get_douyin_stream_url` now stores the replaced h264 origin URL into `flv_url_list` (new result key; `select_source_url`'s existing consumption point appends it after the primary candidate) before the hevc substitution — with HLS enabled the m3u8 still leads; with HLS off/unreachable the h264 FLV takes over. Defensive filtering: an `flv_pull_url` entry identical to the hevc URL, or one already carrying the `codec=h265` marker (per the pinning convention that parameter belongs on hevc_flv_url only), is not collected — it would be filtered out anyway and only add warning noise. The `record_url` contract is unchanged. The other two candidate improvements (a warning when the silent HLS drop leaves zero usable candidates, relaxing the h265 filter by save format) were intentionally not done in this round, pending the user's decision.
- **Regression locks**: `tests/test_stream.py::TestGetDouyinStreamUrl` gains 6 cases (substitution keeps the h264 fallback, the fallback survives the m3u8-probe-failure downgrade, non-origin requests do not substitute, hevc-only with no flv_pull_url keeps the fallback empty, byte-identical URL is not duplicated, an h265-marked entry is not collected); `tests/test_stream_select.py` gains 2 cases (with HLS off the h264 fallback from `flv_url_list` is selected and the h265 primary never gets probed; the control case — h265-only without a fallback — stays None probe-free). Mutation verification: removing the append (marker MUTATION-H265FB) turned both stream-side locks red; byte-exact restore returned them green.
- **Verification**: `run_gates.py` all 8 gates green (embedded full pytest 3698 passed / 0 warnings); after `pytest --cov=src` 3698 passed / 14 skipped, `check_coverage.py` all 44 modules meet threshold; basedpyright 0 error / 0 warning. Live verification (inline script reusing `tests/test_douyin_live_collector.py`'s web path and 3-level cookie fallback):
  `[2026-10-01] douyin | https://live.douyin.com/127453393722 (央视网快看) | inline source-selection script (web path) | PASS | status=2, h265 primary + h264 fallback, SELECT hls_off → h264 FLV`
  The room happened to be a live HEVC-origin room (same shape as the user's deadlocked rooms): the API published an h265 FLV primary (`pull-f3.douyinliving.com/…codec=h265`, one filter warning per select run) plus the retained h264 origin FLV fallback (`pull-flv-f1.douyinliving.com/…codec=h264`); with HLS on the m3u8(h264) was selected (priority unchanged), with HLS **off the h264 FLV fallback was selected** (pre-fix this shape was always "no usable source this round") → `E2E_RESULT: CURED`. Also tried 656722643531 (大山摩旅中国) and 699394970561, both `SKIP(room offline)`; confirming the HLS switch state on the user's running instance is handed back to the user.

### v4.4.0 (2026-10-01) — fix 4 false-red results of test_gui_stop_exit_singleflight on Linux CI: missing stub for the POSIX signal branch

- **Trigger**: CI `test` job (ubuntu) 4 failed / 3679 passed — all four scenarios of `tests/test_gui_stop_exit_singleflight.py` observed 0 console attaches (`attaches: []`) against the "exactly one attach" assertion, and scenario A's `reuse_logged` was False at the same time; locally on Windows the full suite is green.
- **Root cause**: `gui._send_stop_signal_and_wait` branches by platform — win32 calls `_send_ctrl_break_to_child` (the original stub point), POSIX calls `os.kill(proc.pid, SIGINT)`. The subprocess script stubbed only the win32 side, so the accounting spy never fires on Linux; knock-on effect: the stop chain loses its 0.35s simulated duration and finishes instantly, so after scenario A's `sleep(0.05)` the in-flight thread has already ended and `_current_stop_worker()` returns None — the "reuse the in-flight stop thread" criterion falls through too. The CI readings (empty attaches / wait_calls=1 / reuse_logged False) match the single cause "missing stub" exactly; not a concurrency defect.
- **Changes** (test file only, no production code): the subprocess script now installs, on non-win32, a namespace shim per the AGENTS "stdlib stand-ins go through the tested module's namespace" rule — `gui.os` replaced by a `SimpleNamespace(**vars(os))` copy with only `kill` overridden by the same accounting spy (restored in finally); `make_attach_spy` gained a `sig=None` parameter to accept the `os.kill(pid, sig)` call shape; scenario D swaps both sides' spies to the 0.05s short-duration version; the header comment's falsified "single external side-effect point" statement was corrected with a dated history note. AGENTS "Mandatory test-writing conventions" gained an entry: stub points must cover every branch of a platform-branched path.
- **Verification**: Windows full `pytest --cov=src` 3690 passed / 14 skipped / 0 warnings, `check_coverage.py` all 44 modules pass; `run_gates.py` all 8 gates green; basedpyright 0 errors / 0 warnings. Locally reproduced the POSIX path by faking `sys.platform="linux"` — all 25 criteria of the four scenarios pass (technique: change `sys.platform` **after** `import gui`; changing it before import makes loguru's `enqueue=True` initialize multiprocessing the posix way, hitting `No module named '_posixsubprocess'` on Windows). Mutation verification: with the single-flight gate removed (reuse decision and `_console_stop_lock` torn out), 3 behavioral locks + 1 structural lock all went red, and `gui.py` was restored byte-identical. Live verification exempt (test-only change, no recording pipeline involved).

### v4.4.0 (2026-10-01) — deps-audit "floor re-check" catches three new CVEs in urllib3 2.7.0; declared floor raised to 2.8.0

- **Trigger**: the `Audit declared floors against OSV (no resolution)` step of the CI `deps-audit` job failed with rc=1 — when every floor is pinned as `==` and audited one by one, `urllib3==2.7.0` reports three advisories, CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689, all fixed in 2.8.0; the old floor itself sits inside the affected band (same pattern as the starlette / protobuf / h2 floor re-checks; resolution mode is blind to this shape).
- **Changes**: `urllib3>=2.7.0` → `>=2.8.0` in `requirements.txt` and `pyproject.toml [project.dependencies]` (still 21 entries, package-name sets unchanged on both sides); the requirements.txt comment gained a dated re-check record following the h2 precedent; `python scripts/sync_metadata.py` regenerated `uv.lock` (locked version 2.7.0 → 2.8.0, specifier in sync) and `DouyinLiveRecorder.egg-info/requires.txt`. The local venv already had 2.8.0 installed, so raising the floor changes neither the resolved set nor the installed environment.
- **Verification**: re-ran both audit steps locally with the exact CI logic — resolution mode and the `==`-pinned `--no-deps` floor mode both returned `No known vulnerabilities found` (rc=0, 21 floors); `run_gates.py` all 8 gates green (with the embedded full pytest 3690 passed / 0 warnings fallback); after `pytest --cov=src` (3690 passed / 14 skipped), `check_coverage.py` passes on all 44 modules; basedpyright 0 errors / 0 warnings. No production-code changes; live verification not applicable (exempt).
- **Docs**: the `AGENTS.md` "Dependency Management · Security floors" entry and the `urllib3` row of both dependency tables updated in the same batch.

### v4.4.0 (2026-10-01) — Session changes archived by module: AGENTS.md fidelity-preserving slim-down (−1,818 B / −21 lines, 19 places) + stop-hook red-line wording hardening; no production-code changes and no file additions/removals in this session

- **Scope statement**: every change in this session landed in repo conventions and user docs — **no new features, no production-code changes (`src/` / root entry points / `build_exe.py` / `scripts/`), no files added or removed**; the "deletions" are only redundant text inside AGENTS.md (table below). Zero runtime-behavior impact, hence no live-verification item.
- **Per-module change list**:

| Module | File | Type | Change |
| --- | --- | --- | --- |
| Repo conventions | `AGENTS.md` | modified | Fidelity-preserving slim-down in 19 places: 2 redundant removals (the mypy pointer bullet in the gate-command section, the duplicated PowerShell cleanup command embedded in the safe-delete bullet); 4 merge groups (comment conventions "why + three layers", the two ConcurrencyScheduler bullets in the scheduler hub, cleanup "scope + pre-check", Python-version ↔ known-pitfall PEP 758 dedup); 8 compressions of superseded archaeology/stale readings (the 21-dependency recheck chain, superseded lower-bound ranges, stale regression-test counts, the danmaku-wiring `[historical note]`, the old gate-bullet paraphrase, M-28 counts, the rate-limit rewrite note, etc.); 5 wording tightenings (M-26, wraplength, the Web-backend tail note, skipif, config-key audit). The gate-command bash block and every `##`/`###`/`####` heading stayed byte-identical; all 37 "回归锁" (regression-lock) references and measured readings preserved verbatim. 110,287 → 108,364 bytes (−1,818 B), 519 → 498 lines, pure CRLF kept |
| Repo conventions | `AGENTS.md` (CI/workflow · config-key audit bullet) | modified | Mimosa stop-hook disposition: the bullet was flagged by the scanner as a "sensitive file + external send" combination; assessed as a false positive (the line is a prohibitive red line against leakage, and the audit target is key names in a sanitized template, not credential values), then hardened per the suggestion to "**禁止**把真实凭据写入提交或以任何形式外传" — i.e. committing or externally transmitting real credentials in any form is prohibited (red line: see 风险控制（前置）·凭据与敏感配置红线). Semantics unchanged, prohibitive intent made explicit (108,364 → 108,469 bytes) |
| User docs | `README.md` / `README_EN.md` | modified | The "Install dev dependencies" pip line `pip install pytest pytest-asyncio black isort mypy` (5 packages, missing `pytest-cov`; an environment set up this way cannot run the coverage gate) → `pip install .[dev]` (single-sourced from the six entries of `[project.optional-dependencies].dev`, matching AGENTS.md dependency management); details in the previous same-day entry (metadata reconciliation) |
| Changelog | `CODE_WIKI.md` / `CODE_WIKI_EN.md` | modified | The two same-day entries (metadata reconciliation + this one) registered in both CN/EN |

- **Verification**: `run_gates.py --list` parses all 8 gate commands from the slimmed AGENTS.md in the original order; `tests/test_run_gates.py`+`tests/test_regression_2026_09_22_gates.py`+`tests/test_check_annotations.py` = **73 passed / 1 skipped** (matching the 2026-09-30 baseline); `tests/test_regression_2026_09_22_gates.py` (including the "parse gate list from AGENTS.md" source lock) re-run alone = **27 passed**; heading diff HEAD vs new version = **ALL HEADINGS IDENTICAL**; EOL audit: every file touched in this batch stays pure CRLF (AGENTS.md 498 lines, both READMEs 1049/1050 lines, both CODE_WIKIs in the same form).

### v4.4.0 (2026-10-01) — Metadata reconciliation (15 files vs `pyproject.toml`): a single drift in the README dev-dependency instructions, zero changes elsewhere

- **Scope**: `AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` / `config/config.ini` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `README.md` / `README_EN.md` / `DouyinLiveRecorder.egg-info` / `build_exe.py` / `uv.lock`, checked against `pyproject.toml` as the single source of truth: version 4.4.0, project name & three entry points, Python >= 3.14, the 21 runtime dependencies and floors, image / service names, port 8000 and the four mounted directories, and `build_exe.py` packaging parameters.
- **Only change**: the "Install dev dependencies" pip line in `README.md` / `README_EN.md` — `pip install pytest pytest-asyncio black isort mypy` (5 packages, missing `pytest-cov`; an environment set up this way cannot run the coverage gate `pytest --cov=src`) — replaced with the canonical `pip install .[dev]` (single-sourced from the six entries of `[project.optional-dependencies].dev`, matching the `AGENTS.md` dependency-management convention; future extras changes no longer need doc edits).
- **Evidence**: `sync_metadata.py --check` OK (uv.lock / egg-info both 4.4.0), `check_version.py` PASS; egg-info `Requires-Dist` matches the 21 runtime deps plus dev/gui/build extras item by item (setuptools normalizes the `protobuf` spec to `<8,>=6.33.5` — ordering is not a drift), no fastapi/pydantic residue in `uv.lock`; `.coveragerc-concurrency` omit (23) + `exclude_also` (4) identical to pyproject entry by entry; the README edit is a single-line replacement and both files remain pure CRLF.
- Documentation-only change: no recording-chain involvement, no live-verification item; per DoD exemption only the affected gate surface was run.

### v4.4.0 (2026-09-30) — i18n blind-spot backfill batch: tr-ified user-visible text in extractor blind spots ①②③ + 16 entries registered across all four catalogs + zh_CN.mo recompiled

**Call-site tr conversion (lookup before interpolation, eliminating "entry exists in the catalog but can never be matched at runtime")**

- **print_colored (blind spot ①)**: two sites in `main.py` (download interrupted / thread exiting) and two in `src/notify.py` (push failure / removed from recording list) — f-strings passed straight in are now pre-formatted via `i18n.tr(constant template, **kw)` (same shape as MIN-2233).
- **messagebox (blind spot ②)**: 10 sites in `gui.py` — 6 error bodies tr-ified (load/save config file failed, failed to start recording, failed to write URL_config.ini, room URL not found) plus 7 titles tr-ified (Error ×4 call sites, Failed to switch quality ×2, Success, Configuration file changed ×2, GUI startup failed), aligning with the MIN-2247 rule "titles and bodies both go through tr".
- **Push text (blind spot ③)**: the push-title fallback `直播间状态更新通知` in `src/notify.py` goes through tr; the SMTP CRLF guard in `msg_push.py` now raises `tr("{kind} 含换行符，禁止用于邮件头", kind=tr(kind))` (the 4 kind labels are translated at the call sites); 6 push-failure `errmsg` fallbacks (`未知错误`) go through tr.

**Four-catalog registration (16 new msgids)**: zh_CN identity (new section at the po tail + updated header dates); en_US/en_GB share the same English text (「」converted to double quotes); zh_TW traditional with terminology aligned to existing entries (配置文件→設定檔, 线程→線程, 消息→訊息, 注释→註釋). zh_TW also had **7 duplicated theme-section keys removed** (values identical; `界面主题` and 6 more were registered twice as a whole block; the earlier copy dropped) — all four catalogs are strictly key-set equal again (808 keys).

**Regression lock**: `tests/test_i18n_migration.py` gains invariant ④ `test_no_valuable_fstring_in_print_colored_or_messagebox` — repo-wide scan banning interpolated f-strings in blind-spot argument positions + predicate self-check (tr pre-formatting / constants / dynamic non-template args must not be flagged); mutation-verified: reverting one site to an f-string turns the test red, then restored byte-for-byte with no residue.

**Verification**

- Gates: `run_gates.py` 8/8 green; full pytest 3690 passed / 14 skipped / 0 warnings; `check_coverage.py` all 44 modules meet thresholds (84.76%); basedpyright 0 error / 0 warning; `compile_po.py --check` .po/.mo in sync (.mo header N=809, i.e. 808 keys + 1).
- i18n chain end-to-end: hot-switched through all four languages with `set_language`; all 16 new entries match via `.mo` (zh_CN) / JSON (en) / YAML (zh_TW), including a bilingual check of the SMTP-guard exception text (en_US/zh_TW). This batch only touches message plumbing — no recording-chain / source-selection / ffmpeg-argument / platform-resolver behaviour — so no live-room verification is required.

### v4.4.0 (2026-09-30) — P0 fix batch: landed `CODE_REVIEW_2026-09-30.md` Critical 2 + P0 six-pack (each with a regression lock)

> Executed per the report's chapter 8 "P0 (fix immediately)"; P1 (install chain / HTTP bounds / test-line restoration) and P2 remain for later batches.

**Critical (standalone twin drift)**

- **S-01**: `scripts/douyin_live_recorder_standalone.py` gains three defenses — ① `_build_opener` rebuilt as an explicit handler whitelist (no longer via `build_opener`; file/ftp/data handlers no longer registered; isomorphic to the mainline `sync_http` design, keeping `UnknownHandler` as the uniform rejection gate for non-whitelisted schemes); ② new `_untrusted_stream_target_reason` (scheme whitelist + IP literals incl. inet_aton shorthand `2130706433`/`0x7f000001`/`0177.0.0.1`/`127.1` + IPv4-mapped + CGNAT + internal-purpose hostnames, zero-DNS offline judgement, the offline subset of mainline `web_config._internal_ip_reason`), wired into the `validate_stream_url` entry (hard reject even for last_resort — "warn-and-allow the last candidate" targets CDN-rejection false kills only) and `select_source_url` candidate filtering (per-candidate logged for attribution); ③ `-protocol_whitelist` added to both ffmpeg command definition sites (verbatim-equal to `main.py:3472`, placed before `-i`).
- **S-02**: ffmpeg command log masking — `run_ffmpeg` now routes the log line through `_mask_ffmpeg_cmd_for_log` before writing `logs/ffmpeg.log` (`-headers` value replaced with a `<headers:N chars>` placeholder, `-i` value via `strip_query` keeping the path); platform cookies and anti-leech tokens no longer land in plaintext (the log is append-only, unrotated).

**Medium (P0 group)**

- **M-01**: `notify.remove_room_from_running` no longer skips cleanup when `exit_recording=True` (a disk-full pause is not process exit; cleanup is idempotent under `record_state_lock`, and one extra call during real exit is harmless) — rooms that exited during the pause no longer stay in `running_list`, so the relaunch condition holds again once space recovers and the recovery log matches reality.
- **M-02**: `gui._save_text_to_file` delegates to `src.utils.atomic_write_text` (the repo's single hardened implementation: flush+fsync + preserving the target's original mode before replace; utils does not import main, avoiding the config_io side effect), removing the SEV-2211-family gap where each GUI save restored a 0600 tightening back to umask permissions on POSIX; failure semantics unchanged (False re-raised as OSError for the error dialog).
- **M-06**: the web password strip convention unified across three sites — write side strips before hashing, login compares stripped, legacy-plaintext upgrade hashes the stripped form; setting a password with leading/trailing spaces no longer locks every subsequent reauth into permanent 403 (panel-level self-lockout of the auth config).
- **M-07**: `web_config.update_config_line` drops the unquoted-value `" #"`/`" ;"` inline-comment fallback heuristic (the reader-side configparser never enabled inline_comment_prefixes, so a ` #` inside the old value is part of the value; splicing it back silently corrupts the new value); quoted values still take comments only **after the closing quote** (F-23 semantics kept, `key = "a #b"` no longer re-polluted by the fallback).
- **M-17**: `utils._SECRET_HEADER_RE` camel branch loses its permanently-dead guard (mutually exclusive with `(?<=[a-z])` at the same position, branch never matched) — header-form camelCase compound keys (`myToken:`/`sessionKey:` etc.) are masked again; two guardrails recorded: the plain branch must NOT gain a quote exclusion (the shell command form `--header "Authorization: Bearer X"` has a quote right before the key; excluding it re-opens the leak — the whole `tests/test_notify_script_guard.py` group proves it), and the old "guard prevents https: masking" claim is falsified under the current key list (no key can match `https:`).
- **M-18**: `utils.replace_url` switched to segment-exact matching — the matcher moved down to `utils.rewrite_line_by_segment` (`config_io._rewrite_line_by_match` is now a thin delegating wrapper, one implementation kills the twin drift), so prefix-overlapping sibling room lines (`…/l/123456` vs `…/l/1234567`) are no longer whole-line corrupted by HuyaLive's dead-URL auto-commenting.

**Verification**

- `[2026-09-30] Huya | https://www.huya.com/660002 | scripts/douyin_live_recorder_standalone.py --dry-run | PASS | real live room parsed as "王者荣耀赛事", all candidates passed the new guard, probe 403 retry recovered→tx line 200, stream URL selected (incremental verification of S-01's three defenses + S-02)`.
- Gates: `run_gates.py` 8/8 green; full pytest 3689 passed / 14 skipped / 0 warnings; `check_coverage.py` all 44 modules above threshold; basedpyright 0 error / 0 warning. The M-18 regression lock was mutation-verified (red under the old substring implementation, byte-exact restore, line-ending shapes untouched).
- Regression locks: `tests/test_regression_2026_09_22_standalone.py` (TestUntrustedStreamTargetGuard / TestWhitelistOpener / TestFfmpegCommandHardening / TestFfmpegCommandLogMasking), `tests/test_regression_2026_09_22_utils.py` (header-form camelCase compound keys + quoted header), `tests/test_web_api.py::TestPasswordManagement::test_password_with_surrounding_whitespace_not_self_locking`, `tests/test_web_config.py::TestUpdateConfigLine::test_hash_in_value_reads_back_as_new_value`, `tests/test_utils.py::TestReplaceUrl::test_prefix_overlapping_sibling_line_untouched`, `tests/test_regression_2026_09_22_main.py::TestDiskFullPauseCleanupStillRuns`, `tests/test_gui_save_atomic.py`.

### v4.4.0 (2026-09-30) — Full-workspace code review (producing `CODE_REVIEW_2026-09-30.md`): 18 per-file deep-audit batches plus Mimosa deep-scan cross evidence — Critical 2 / Medium 51 / Minor 160

> User's brief: comprehensively review all source code in the workspace (Python/JavaScript/Node.js/HTML/CSS/CI, excluding third-party dependency directories such as node_modules and build artefacts such as dist/build), focusing on code quality, latent defects, security vulnerabilities and logic errors; record findings per file and classify them by severity into a formal report. The report landed as [`CODE_REVIEW_2026-09-30.md`](CODE_REVIEW_2026-09-30.md) in the repository root.

| Item | Content |
| --- | --- |
| Method and coverage | 18 independent deep-audit batches grouped by module (12 production + 6 test), each reading every assigned file line by line, each carrying an "established-conventions anti-false-positive list plus per-area anchor points"; coverage ≈42,000 lines of production code (`main.py` 5,465 / `gui.py` 4,526 / `src/spider.py` 7,100 / Web layer 3,439 / source-selection & scheduler 3,498 / danmaku chain 2,743 / HTTP infrastructure 2,084 / tooling 3,524 / install & post-process 2,600 / front-end & signing JS 4,805 / build-gate CI ≈8,000 / standalone 2,261) and ≈56,200 lines of tests (124 `tests/*.py` files + 8 `tests/frontend` files); excluded `typings/`, `src/proto/douyin_pb2.py` (protoc-generated) and `src/javascript/crypto-js.min.js` (tamper special-check only: full-file pattern scan shows no network egress / dynamic construction / system-capability calls — judged to be an unmodified standard crypto-js 4.x build). Before the report was written, the lead reviewer re-verified the 2 Critical and 5 representative Medium findings at line level; all confirmed |
| The 2 Critical findings (both in `scripts/douyin_live_recorder_standalone.py`, twin drift) | ① SSRF + local-file-read chain in the probe/record path (`:180-187/:746-756/:1456-1494`): default `build_opener` ships FileHandler + platform candidates accepted without protocol/internal-host checks + the ffmpeg command lacks `-protocol_whitelist` (the mainline has it at `main.py:3466`) — three layers stack into a complete chain where `file://` and `169.254.169.254` reach "probe → accept → ffmpeg records to disk"; ② the full ffmpeg command (including the Cookie header and token-bearing stream URLs) is written verbatim per round into `logs/ffmpeg.log` with no rotation (`:1543/:1552`), in direct conflict with the "no credentials to disk" red line |
| Distribution and representatives of the 51 Medium findings | Production 37: standalone 4 (MID-49 Douyu POST not back-ported, probe exceptions carry full URLs, GBK config crashes at startup, Windows terminate() hard-kills and truncates mp4); install chain 6 (TOFU baseline unread → fail-open, new zip recorded without archive-shape validation, version string unvalidated, direct unzip into the app root, import-time concurrent `check_node` install race, `check_node` exceptions can crash `import src`); tooling 4 (`_SECRET_HEADER_RE` camel branch has two mutually exclusive lookbehinds and can never match — camelCase compound keys in header form are not masked; `replace_url` substring fallback silently comments out sibling rooms with overlapping ID prefixes; logger dual-sink partial-failure leak; `run_node_script_async` lacks the wait_for double budget and can hang a room thread forever); Web 3 (no request-body size limit, three inconsistent password-strip call sites can permanently self-lock auth config, inline-comment preservation silently corrupts values containing ` #`); HTTP 4 (sync_http same-scheme internal-redirect gap / unbounded HTTPError body / data-vs-json branch divergence; async_http hop guard does a synchronous getaddrinfo inside the event loop); danmaku 3 (singleflight failure log unmasked, in-flight registrations never reaped on waiter timeout, SRT open failures are silent and both existing alert chains miss); source selection 2 (`_PRIVATE_HOST_PATTERN` literal-only gap; room.py bare AsyncClient follows redirects); spider 2 (LangLive/Inke/JD still require both FLV+HLS, MID-2212 family residue; xhs session sid forwarded across redirects); main 1 (after a disk-full pause recovers, `running_list` residue permanently blocks all rooms from relaunching); GUI 1 (`_save_text_to_file` weakened atomic write restores 0600 on POSIX — SEV-2211 family); build/CI 6 (softprops/action-gh-release and dorny/paths-filter floating refs × highest permissions, check_annotations home-dir guard direction inverted, smoke tests never drain the PIPE / never assert liveness, one-off script ROOT hardcoded); front-end 1 (switching language wipes the rendered config form). Tests 14: always-true assertions (`test_http_config:153`, `test_proxy:149`), stubs landing on process-wide module bodies (configparser/ctypes/time.sleep/httpx/loguru), three front-end wrappers missing the node-side skipped check (`{skip:true}` goes green end-to-end), sandbox without sessionStorage leaves the `_tokenStore` main path at zero coverage, MID-2253/2238 text locks escapeable |
| Machine-scan cross evidence (Mimosa) | scanId `scan-2026-09-30T02-25-56.161Z-3255898c38d0`, seal `sha256:5350da9801cb…d78a1`, depth deep, evidence boundary static_only, status **inconclusive** (198/198 files parsed, threatModel incomplete, validation phase investigated=0 — all 41 findings are unvalidated static hits): HIGH command-injection 3 / hardcoded-credentials 3 / path-traversal 11 / SSRF 7, plus LOW weak-randomness 17. Human triage: 0 findings constitute an exploitable vulnerability unseen by the manual audit (2 corroborate manual findings — the unvalidated node version string and the sync_http internal-redirect gap; the rest are pattern false positives or by-design public client identifiers); the scan's selection did not cover standalone — the two Critical findings came out of the manual audit |
| Report structure and actions | The report contains overview / scope / statistics matrix / item-by-item detail for the 2 Critical and 51 Medium findings (problem + impact analysis + fix suggestion) / 160 Minor findings as per-area tables / the machine-scan triage table / P0–P2 fix priorities / process recommendations (a proposed "twin back-port" hard rule, adding configparser to the R1 list and registering the ctypes stub in `_SANCTIONED`, a standalone back-port alignment project) / conclusions; 10+ findings are marked "to be confirmed" and need real-device or environment-specific reproduction before final grading |
| Documentation and gates | Documentation-only batch: new `CODE_REVIEW_2026-09-30.md` in the repo root (`.dockerignore` already carries the `CODE_REVIEW_*.md` wildcard, so it never enters the image) plus this entry (CN/EN synchronised); zero code changes. DoD waivers: step 1 gates not applicable (no `.py`/front-end asset changes), step 2 real-device verification not applicable (no recording-chain / source-selection / ffmpeg-argument changes), steps 3/5 not applicable (no regression-lock changes, no one-off scripts produced) |
| Handed back to the user | The five P0 fix queues are in report chapter 8 (standalone twin back-port, the masking dead branch, Web auth self-lock and config-value corruption, `replace_url` collateral damage and the disk-recovery relaunch, GUI atomic write); the standalone back-port alignment deserves its own dedicated project |

### v4.4.0 (2026-09-30) — `AGENTS.md` reconciled with workspace state (7 fact corrections) plus information-preserving slimming only, after measuring redundancy: net +529 bytes this batch (slimming operations −170 B, fact sync +699 B)

> User's brief: scan the workspace → identify adds/modifies/deletes since the last commit via `git status`/`git diff` → write the affected `AGENTS.md` configuration back → then slim the file.
> Workspace as measured: `git status --porcelain` shows exactly 5 `M` entries (`AGENTS.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `docs/agent-reference/session-learnings.md` / `pyproject.toml`),
> **0 additions, 0 deletions, 0 untracked** (`filter.lfs.*` is configured and does not suppress status collection); reconciliation baseline is HEAD `046bb73`.
> This round's `pyproject.toml` change touches only the **attribution comments** of two `[tool.pytest.ini_options].filterwarnings` entries with zero value changes, so `AGENTS.md` needed no follow-on (runtime dependencies verified at 21 on both sides, identical name sets to `requirements.txt`).

| Item | Content |
| --- | --- |
| 7 fact corrections (each with a measurable basis) | ① "dev / build / GUI dependencies": `.[dev]` expanded from "pytest/black/isort/mypy" to the **six** entries actually declared (`pytest-asyncio` and `pytest-cov` were missing); ② `tests/test_scheduler.py` "16 tests" → **29** and `tests/test_record_failure_feedback.py` "5 tests" → **8** (`pytest --collect-only -q`); ③ the symbol `_allow_sleep` quoted in the pitfalls section **does not exist** — `src/scheduler.py` defines module-level `_sleep` (:531) and `_now()` (:525); ④ "6 `check_subprocess(...)` call sites" → **1** (`main.py:3595`; after the F-01 convergence each platform branch only fills `ctx.record_danmaku_args`, now 52 assignments by `grep -c`); ⑤ `_loads_dict` "about 40 call sites" → **103** (`grep -c '_loads_dict(' src/spider.py` = 104 lines including 1 definition); ⑥ in the bundle-size section, `pydantic_core` 4.93 MB and "≈24 MB total" were falsified by `046bb73` removing fastapi/pydantic and there is no local `dist/` to re-measure, so the readings moved out and the root file keeps only the "three fixed costs" constraint; ⑦ readings re-verified as **correct** and left untouched: `BARE_JSON_LOADS_CEILING = 1`, the 8-cell real-bash behaviour grid in `tests/test_ci_retry_action.py`, the 9-cell `test_twin_agrees_on_every_criterion_combination` matrix, 24 web_api routes, `_FFMPEG_FAST_FAIL_SECONDS = 20.0`, `_PROBE_LEASE_SECONDS = 60.0`, `_PROBE_BACKOFF_PLATFORMS`/`_FLV_FIRST_PLATFORMS = ("虎牙直播",)`, the ci.yml consts (black 26.5.1 / isort 9.0.1 / mypy 2.3.1 / pytest 9.1.1 / Python 3.14 / Node 24), actions v7, `release-guard`, rules R7/R8, the two metadata regression locks, the `\r?\n\r?\n` anchor in `MIN-2241`, and the 5 locks in `test_motion.mjs` |
| Redundancy measured before editing | Sizes are **raw file bytes in CRLF form**: HEAD `046bb73` 515 lines / 107,227 B → at the start of this session 517 lines / 109,009 B (including the previous batch's three uncommitted gate-wording entries) → at the end of this batch **518 lines / 109,538 B**. Measured split of the two operation groups: slimming **−170 B** (merging the two `PYTHONUTF8` entries −39 B; merging "`main.py` subprocess" with `FakePopen` **+33 B** — the merge added the causal framing "`__class_getitem__` cannot be omitted", so it grew and is reported as such; merging the two live-collector entries −175 B; relocating the bundle-size readings −137 B from the root file; the two new pointer definitions +148 B), and the fact sync **+699 B** (the 7 measured readings plus their `[历史注]` lines). Machine counts: trailing whitespace **0** lines, verbatim duplicate lines **1** (the same `Where-Object` clause legitimately appearing in both the PowerShell and POSIX cleanup snippets), repeated bold lead-ins **0**, blank runs **8** (all ≤3 lines), and of the 113 bullets longer than 200 characters **0** share >50% of their 25-char shingles with `CODE_WIKI.md`+`CODE_WIKI_EN.md`, **0** bullet pairs share >40% with each other. **Conclusion: there is no "redundant repeated wording" left to delete** — roughly 41% of the file's bytes are the regression-lock and constraint register, i.e. the source of truth itself. Any further size cut can only come from compressing correction archaeology or relocating more readings, both of which change the information's form rather than remove duplication and therefore need the user's go-ahead |
| The only information-preserving moves available | Merged same-topic bullets in **3 places**: the "`PYTHONUTF8=1` + fail-on-warning" entry and the "parent-process forwarding / `errors=\"replace\"`" entry became one (MID-63, "re-implemented in 6 places", `run_gates.ensure_utf8_streams()`, `_guard_stdio_encoding_policy` and `gui._install_crash_sink()` all retained); "patch `main.py`'s subprocess" merged with "`FakePopen` must define `__class_getitem__`"; and the dual-mode collector's two-step `int(sys.argv)` guard merged with "the body must sit inside `__main__`" — the four template constraints are now numbered ①②③④ with the three readings (20.55 s / exit code 5 / 4 errors during collection) kept verbatim |
| Relocation + broken-pointer repair | The per-file MB readings and the `pydantic_core` falsification history moved into a new section "产物体积大头读数" (bundle-size readings) of `docs/agent-reference/measured-evidence.md`, whose own admission rule (no imperative constraint may appear in a relocated sentence) was checked. Also fixed **two sub-docs the root file had lost sight of**: `measured-evidence.md` and `lock-classification.md` had long been relocated out but carried no pointer in `AGENTS.md` (only `project-structure.md` was still linked); each now has a reference-style link (`[体积读数]`, `[锁分类快照]`) |
| Zero-loss proof | Compared class by class against HEAD, with `measured-evidence.md` counted as retained: `test_*` identifiers **69 → 69 (0 lost)**, MID/SEV/MIN/CVE/PYSEC/GHSA labels **19 → 19 (0 lost)**, `UPPER_SNAKE` constants **77 → 77 (0 lost)**. The 5 backtick spans that disappeared are all rewrites of the same thing: `_now`→`_now()`, `libcrypto/libssl`→`libcrypto`/`libssl`, `record_danmaku_args`→`ctx.record_danmaku_args`, `basedpyright tests/` (the wrong baseline the previous batch already removed), and `__main__` folded into the full `if __name__ == "__main__": main()` form |
| Gates | `python scripts/run_gates.py` → **8/8 green (41.1 s)** plus its trailing backstop **3653 passed with an empty warnings summary (194.5 s)**, exit code 0; `run_gates.py --list` still parses **8** commands with the first one byte-identical to `python -m black --check --diff --line-length 120 --target-version py314 .` (section heading, fence and the line-start `PYTHONUTF8=1` prefix all untouched); the three document locks `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = **73 passed / 1 skipped / 0 warnings (36.57 s)**; `AGENTS.md` line endings **CRLF 518 / bare LF 0**, `measured-evidence.md` still pure CRLF, `session-learnings.md` still pure LF. One side effect recorded: after the full gate run (including its trailing pytest) `git status --porcelain` also listed the **tracked** `config/config.ini` — a blank line before `[GUI]` had been swallowed by a config write-back path. That is a test artefact, not an intended change of this batch; restoring a tracked file is the user's call, so it was left as-is and logged as N-4 |
| Not re-run, and why | `scripts/check_coverage.py` and `basedpyright` were **not** re-run this batch: zero `.py` or front-end asset changes (`.md` only), so their same-day readings stand (44 modules above threshold / 191 files with 0 errors and 0 warnings). Additionally `check_coverage.py` needs coverage data from `pytest --cov=src`, while `run_gates.py`'s backstop runs pytest without `--cov`, so re-running it now would only produce a false "no data, rc=2" signal |
| Real-device verification | **Not executed**: this batch touches no recording chain / source selection / ffmpeg arguments / platform parsing, so DoD step 2 is waived; only steps 1 (affected parts) / 4 / 6 were performed |
| Still for the user to decide (numbered) | **N-1** three stale comments still say "FastAPI": `.github/workflows/ci.yml:6`, `.github/workflows/ci.yml:606`, `docker-compose.yaml:100` — fastapi left the tree in `046bb73` and the panel is Starlette-driven; comment-only, left alone to stay inside the "change `AGENTS.md`" mandate. **N-2** `scripts/compile_po.py:136-137` calls `reconfigure(encoding="utf-8")` **without `errors`**, contradicting this repository's own rule that every `reconfigure` states `errors` (omitting it resets the handler to `strict` — the MID-63 failure family); landing a fix needs a regression lock, so the maintenance script was not touched. **N-3** the two derived-metadata questions carried in from the previous batch remain open: whether `src/proto/douyin_pb2.pyi` belongs in `[tool.setuptools.package-data]`, and whether the `.[dev]` lower bounds should be raised to the CI-pinned versions |

### v4.4.0 (2026-09-30) — Full quality-gate re-audit (191 source files / 3653 tests): code side clean, three `AGENTS.md` gate-wording corrections

> The user asked for a complete code-quality and test run over all Python code in the workspace. Result: **black / isort / mypy (host plus `--platform linux`) / basedpyright / pyright / pytest / per-module coverage — all seven green, zero production-code changes**; the only repository change this round is three gate-wording entries in `AGENTS.md`.

| Item | Content |
| --- | --- |
| Gate readings | `python scripts/run_gates.py` → 8/8 PASS (45.3 s) plus its trailing pytest backstop "3653 passed, warnings summary empty" (190.5 s), cross-checked against a standalone `pytest --cov=src -q` run (3653 passed / 14 skipped); `scripts/check_coverage.py` → all 44 modules above threshold (84.69% total; `src/proto/douyin_pb2.py` at 8.7% is the explicitly exempted protoc artefact); `basedpyright` with no path → 191 files, 0 errors / 0 warnings (the older `basedpyright tests/` form, 126 files, also 0/0); `pyright` 1.1.414 with the explicit `[tool.mypy].files` path set → 191 files, 0/0, and a bare `pyright` → 205 files (the extra 14 are `typings/` stubs) also 0/0 |
| `AGENTS.md` correction 1 | "Testing → quality gates (must be kept)" used to say "the three black/isort/mypy commands with paths replaced by `tests/`", which contradicts this file's own "`mypy` takes no path arguments" rule — passing paths overrides `[tool.mypy].files` and shrinks coverage. It now points at the "Formatting commands (sole gate baseline)" section; the pass criteria (0 warnings / all green / 0 errors 0 warnings) are unchanged verbatim |
| `AGENTS.md` correction 2 | The "basedpyright (local supplementary gate, not run in CI)" section now states where `pyright` and Pylance belong: `pyright` is only the engine underneath basedpyright and is **not a third gate**; Pylance has no command-line entry, so "Pylance was checked" may never be presented as gate evidence; this repository has no `[tool.pyright]` section, so a bare `pyright` scan is wider than the `[tool.basedpyright]` exclusion set |
| `AGENTS.md` addition | The gate section gains a transferability precondition: local black/isort/mypy/pytest versions must equal the pinned `ci.yml` consts, otherwise the report must be labelled "local readings, not verified against the CI toolchain version". Measured divergence, one item: **local isort 9.0.2 versus the CI pin of 9.0.1** (black 26.5.1 / mypy 2.3.1 / pytest 9.1.1 all match). Workflow constants were not touched and venv dependencies were not reinstalled (the latter is a user-channel action per "Risk controls (preface)") |
| Attribution of the 14 skips | All are environment-shape limits, not failures: Windows semantics 4 (`tests/test_proxy.py:199`, `tests/test_regression_2026_09_22_utils.py:178`, `tests/test_utils.py:574`, `tests/test_run_gates.py:218`); missing symlink privilege 3 (`tests/test_ffmpeg_path_preference.py:262`, `tests/test_web_api.py:2137`/`:2157`, WinError 1314); local `h2` present so the missing-dependency construction branch is unreachable 1 (`tests/test_regression_2026_09_22_net.py:681`); platform has no documented offline shape 6 (`tests/test_spider_hardening.py:198`) |
| Live end-to-end verification | **Not executed**: zero code changes this round (documentation only), so the Definition of Done exemption keeps steps 1/4/6; the recording chain was not touched |
| Doc-lock self-check | After editing `AGENTS.md`, the three document locks that read it were re-run — `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped; the "Formatting commands" bash block still parses with the same command count (new bullets sit outside the fence); `AGENTS.md` line endings re-measured as CRLF 517 / bare LF 0, the same shape as HEAD |

### v4.4.0 (2026-09-30) — `pyproject.toml` reconciled against workspace changes (dependencies / derived metadata / package list / exclusion list): no value changes, only the attribution in two `filterwarnings` comments corrected

**Context**: re-audited under the "scan the workspace → identify adds/mods/deletes since the last commit → write back the affected `pyproject.toml` configuration" brief. The working tree was clean against `HEAD`, so the reconciliation baseline became the unpushed `046bb73` (the batch that dropped fastapi / pydantic).

| Item | Evidence (measured locally) | Outcome |
| --- | --- | --- |
| Runtime dependency set | `pyproject [project.dependencies]` = 21 entries ↔ `requirements.txt` = 21 after stripping inline comments; `tests/test_regression_2026_09_22_gates.py` 27 passed | Already synced by `046bb73`; no change |
| Derived artefacts | `python scripts/sync_metadata.py --check` | OK: `uv.lock` carries no fastapi/pydantic node any more, egg-info version and requirements both match |
| Third-party imports with no declaration | AST walk over all 243 `.py` files in the repo collecting top-level import roots (script fed via stdin, nothing written to disk) | No gap in product code; `fastapi`/`pydantic` survive only inside the `.workbuddy/tmp/` stale backup snapshot, a directory already excluded by every tool's exclusion list |
| Package list | `src/` still has exactly `platforms` / `proto` as sub-packages; all 6 root `.py` files are listed in `py-modules` and `[tool.mypy].files`; this batch's new files land in `src/`, `tests/`, `web/`, `docs/worklog/` | `packages` / `py-modules` / `package-data` all need no change |
| Exclusion-list single-sourcing | black / isort / mypy / coverage / basedpyright omit entries match `.coveragerc-concurrency` item by item; no new `.py`-bearing asset directory under `tests/`, `docs/`, `web/` | No change |

**Actual change (comments only)**: the two `[tool.pytest.ini_options].filterwarnings` attributions corrected —

- Entry 1 is **load-bearing**: running `tests/test_web_api.py` with `-W default::UserWarning` puts exactly one line in the warnings summary, emitted by `starlette/testclient.py` itself (category `StarletteDeprecationWarning`, a `UserWarning` subclass). The old comment blamed "an internal import inside fastapi's testclient", which `046bb73` falsified.
- Entry 2 **does not fire on the installed combination** (starlette 1.7.0 + anyio 4.15.1): with `-W always::DeprecationWarning` (a command-line `-W` overrides the ini filter) `test_web_api.py` + `test_web_api_routes.py` give 163 passed and an empty summary, because all three starlette references now go through `anyio.from_thread.BlockingPortal`. Kept rather than deleted — the shape across the declared `starlette>=1.3.1` lower-bound range was not verified locally.

**Gates**: `check_version.py` PASS, `sync_metadata.py --check` OK, `pytest tests/test_regression_2026_09_22_gates.py tests/test_web_api.py` = 190 passed / 2 skipped / 0 warnings; TOML parses and the whole file stays within 120 columns.
**Live end-to-end verification**: **not executed** — this batch touches no recording chain / source selection / ffmpeg arguments / platform resolver, so the Definition of Done step-2 exemption applies.
**Deliberately left for the user**: (1) `src/proto/douyin_pb2.pyi` (present since 2026-08-18) is not listed in `[tool.setuptools.package-data]`; whether wheels include it was **not** measured (no installed distribution and no `.whl` on this machine to inspect) and needs a real build to decide. (2) `[project.optional-dependencies].dev` floors (pytest>=7.0.0 / mypy>=1.5.0 / pytest-asyncio>=0.21.0) sit far below the pinned `ci.yml` consts (pytest 9.1.1 / mypy 2.3.1 / black 26.5.1); raising them to CI parity is undecided.

**Same-day follow-up (separately approved by the user)**: `AGENTS.md` "Dependency management" read "23 entries", a figure falsified by `046bb73` (the fastapi/pydantic removal). It was initially left alone because the file was under parallel edit; once the user issued the explicit instruction it was corrected to "21 entries, re-checked 2026-09-30: 23→21 after the stage-2 removal", with the earlier 2026-09-26 21→23 reading recast as an explicit "superseded by that removal" historical note rather than deleted (constant names and dates kept verbatim). Re-measured after the edit: `AGENTS.md` line-ending shape unchanged at CRLF 517 / bare LF 0, and the three document locks that parse it — `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped / 0 warnings (the "Formatting commands" bash block still parses with the same command count; this edit sits outside the fence).

### v4.4.0 (2026-09-30) — Three hand-back items from the review report landed (1-A sync-probe internal guard / 2-A retry exit-code buckets / 3-A live-script template gate) plus a new machine check against unrestored mutations

> The previous batch left three items for the user to decide. All three were approved and landed as
> 1-A / 2-A / 3-A. During the work an actual incident was found and turned into a machine check (new rule R8).

**1. 1-A — internal-target guard for the synchronous probe (`src/stream_select.py`, `src/async_http.py`)**

The previous batch only wired the per-hop re-check into the asynchronous side, and I described the gap as
"the synchronous probe has the same shape but is un-wired (per-hop level)". Re-reading the code
**corrects that premise**: the only call site of the internal-target judgement in the whole repository was
`async_http.get_response_status`, so the synchronous probe had **no internal/loopback/cloud-metadata check even for
the initial URL** — it only had the `_is_recordable_url` scheme-shape whitelist, which blocks `file://`/`concat:`
but not `http://127.0.0.1:6379`. A hijacked platform API returning an internal stream address was enough to hit it.

| Item | Content |
| --- | --- |
| Single factory | Both self-built `httpx.Client` sites now go through `_probe_client()`, which attaches the synchronous response hook (`build_sync_hop_guard`); the judgement reuses the one implementation in `async_http` — **no second copy in stream_select** |
| Import cycle | The hook factory is imported **inside the function**, following the technique documented at `async_http.py:518-521` (this module has a module-level `import main`, so a module-level outgoing edge would change initialisation order) |
| Initial check | `_validate_stream_url` runs `internal_stream_target_reason` before the first request; it deliberately does not reuse the variant that carries a scheme whitelist, because the protocol dimension is already gated by `_is_recordable_url` — the two guards do not substitute for each other |
| Exception convergence | `RedirectHopRejected` (extending `httpx.HTTPError`, not `RuntimeError`) becomes the same `False` as "this candidate failed validation" inside `_validate_stream_url` and **never escapes**; the "treat the list as reachable" fallbacks in `_confirm_get_ok` / `_probe_hls_segment` must `raise` — otherwise the last candidate returns `True` and hands an internal address to `ffmpeg -i` |
| Not regressed | Probe client scope stays single-selection, no `(proxy, verify)` module-level cache, keepalive not disabled, `utils.handle_proxy_addr` normalisation not moved |
| Locks | `tests/test_sync_probe_internal_guard.py` (includes AST structure locks: one construction site, `event_hooks` argument must come from the synchronous factory, both call sites pass the initial check); the asynchronous lock file stays green |

**2. 2-A — the retry composite action supports exit-code buckets (`.github/actions/retry/action.yml`, `.github/workflows/ci.yml`)**

| Item | Content |
| --- | --- |
| New optional input | `fail_fast_codes`, `required: false`, `default: ""`; **when unset the behaviour of existing call sites is unchanged verbatim** (backoff arithmetic, both message texts, final `exit 1`) |
| Hit semantics | The branch sits **before** the backoff `sleep`, prints `::error:: … configuration-class error … retrying is pointless` and `exit "$rc"` keeping the original code; it must never exit 0 nor degrade to a warning (that would be a false green) |
| Parsing | `IFS=", "` + `set -f` + `case ''|*[!0-9]*`: space/comma mixes parse, illegal entries are ignored with a `::warning::`, and matching uses a space-padded string so a list containing `2` does not match rc=12; strictly POSIX, no bash-only associative arrays |
| Wiring | Only the web smoke call site passes `"2"`, closing M-32(2)'s "a broken config must not be retried" |
| Premise corrected | The work order said "10 call sites"; measurement found **16** (11 in ci.yml, 5 in build-release.yml) — earlier batches had already migrated more install steps into this action. The structure lock therefore pins 16 as a lower bound (only-decrease semantics) and asserts "regex count == YAML structural count" so a drift in the `uses` form cannot silently disable AGENTS' own grep gate |
| Locks | `tests/test_ci_retry_action.py`: 4 structural locks + 8 real-`bash` behaviour cells (they run the production script extracted from `action.yml`, no copy, so deleting the production branch must redden); when bash is missing the test **fails explicitly instead of skipping** |

**3. 3-A — live-script template gate R7 (`tests/test_test_hygiene.py` + the five `test_*_live_collector.py`)**

Four AST criteria, each named individually: ① an `__main__` guard that really calls `main()`; ② no module-level
collection-time side effects (only imports / constant assignment / the sanctioned `sys.path` injection are allowed);
③ the argv numeric guard; ④ output-directory cleanup must filter by platform prefix and check the entry type first.
The reverse witness was extended as required: each criterion is fed its worst-case form (must redden) and a compliant
source (must not false-positive), plus four new cases that mutate the real scripts and demand that only the
corresponding criterion reddens.

**4. Two documented premises that turned out to be wrong**

1. **AGENTS' own argv-guard sample was falsified by measurement**: the documented one-liner
   `SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else N` breaks under
   `pytest a.py b.py`, where `sys.argv[2]` is the **next test file's path** — it carries no `-` prefix, passes the
   non-option test, and `int(path)` raises ValueError, erroring that module's collection outright
   (measured: 4 errors during collection). All five scripts now use the two-step form
   `_SECONDS_RAW = …` → `int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else N`; R7③ machine-checks it and the AGENTS
   entry body was corrected (falsified statements get rewritten in place).
2. **The report's finding about blind directory clearing was real**: `test_bili_live_collector.py` /
   `test_huya_live_collector.py` used `for f in os.listdir(base_dir): os.remove(...)` (no prefix filter, no type
   check), which throws when a subdirectory is present and deletes other platforms' artefacts under parallel runs.
   Now filtered by platform prefix + `isfile`, keeping the original intent of starting from a clean directory.
3. **AGENTS' "the retry action is rc-agnostic, rc=2 cannot actually stop early (pending decision)" was closed by 2-A**
   and the entry body was updated accordingly.

**5. The incident and the new machine check R8 (guarding against unrestored mutations)**

A parallel work package mutated the HLS segment branch in `src/stream_select.py` to prove a lock was not fake
(removing `except RedirectHopRejected: raise`), hit its turn limit, and left `pass  # MUTATION-M4c …` **in the
production file**. The consequence is not a missing comment: `seg_resp` was left unassigned → `UnboundLocalError`
swallowed by the outer `except Exception` as a "probe error" → the last candidate returned `True` →
**an internal address was handed to `ffmpeg -i`**. This shape is invisible to black / mypy / the annotation checker
(syntactically valid, type-clean, and it even adds comments); only a test that actually executes that branch catches
it — which is exactly what the new synchronous-probe case did.

R8 now scans source files repository-wide and reddens if a `MUTATION-` marker survives; three hard constraints were
written back into AGENTS' "mandatory test-writing conventions" (in-memory backup + byte-exact restore in `finally`;
markers must be left during the mutation; when taking over an interrupted work package, the first step is to scan for
residue rather than assume the implementation is complete). The guard protects itself three ways: the marker literal
is built by concatenation (otherwise the gate would flag its own source), it asserts the traversal covers >200 files
(a wrong scan root would otherwise spin silently), and the reverse witness covers all three legs.

**6. Verification**

| Item | Reading |
| --- | --- |
| 1-A real outbound probe | Public HLS (walking the playlist **and the segment-probe branch** that held the residue) `test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` → **True** (no false rejection); `http://127.0.0.1:6379/`, `http://169.254.169.254/latest/meta-data/`, `http://10.0.0.5/live.m3u8`, `http://100.64.0.1/live.m3u8` → all **False**; internal target with `last_resort=True` → **False** (the last candidate is not handed an internal address); `file:///etc/passwd` → **False** (shape whitelist intact) |
| Real "public → internal" redirect chain | **SKIP(no usable public redirector)**: httpbingo.org returns 403 to this host and no public endpoint 302s into a private address; covered via `httpx.MockTransport`, no fabricated readings |
| 2-A | `pytest tests/test_ci_retry_action.py` alone → **12 passed / 0 warnings** (4 structural + 8 real-bash cells); end-to-end wiring check with the real ci.yml `with` values and the GitHub-filled default → `runs=1 / rc=2 / 0.23s` (a real backoff with `backoff=5` would take ≥5s); three mutation runs: delete branch `4 failed, 8 passed`, `default` → `"2"` `1 failed, 11 passed`, branch moved after `sleep` `4 failed, 8 passed`; all restored byte-identical |
| 3-A / R8 | `pytest tests/test_test_hygiene.py` → **507 passed**; R8's disk path proven with a one-shot probe file: adding `tests/_tmp_r8_probe.py` (containing a marker) → `AssertionError: tests/_tmp_r8_probe.py:7`, removing it → green; probe deleted |
| Live recording chain | Douyin room `live.douyin.com/699394970561` → SKIP(room offline at run time); the affected path is the source-selection validator, whose real outbound evidence is the row above |
| Full gates | `python scripts/run_gates.py` 8/8 green with an empty pytest warnings summary (readings in the delivery reply) |

**7. Still open**

- The `inputs → env` expansion happens on the GitHub runner; locally we only proved the script behaves correctly once
  the default is filled the GitHub way. After merging, check that the first failing web-smoke log shows
  `exit code 2 is a configuration error … not retried`.
- The five `build-release.yml` call sites deliberately do not pass `fail_fast_codes` (they install via choco/apt/brew/pip,
  where no "configuration-class" exit code exists; passing one would only weaken retry on network flakiness). A
  structure lock pins "nobody passes it" instead of letting that drift.
- The hook still fires after the hop's response has been received (what is closed is "no further following and no
  leakage", not "no connection"); intercepting before connect would need a request hook (two checks and two
  `getaddrinfo` calls per hop), and the DNS-rebinding window is not closed at this layer — all recorded as residual
  risk in the source comments and here.
- The previous batch's eyeball items and live gaps are unchanged (M-14/M-16/M-18/M-22 visual checks, M-11 needs an
  outbound route for TikTok, no live Douyu room at the time, `basedpyright` not installed locally).

### v4.4.0 (2026-09-29) — Fix batch for the full-repository review report CODE_REVIEW_2026-09-29_2 (P0+P1+P2, 31 numbered items)

> Implemented per `docs/worklog/CODE_REVIEW_2026-09-29_2.md`, within the scope the user approved: P0+P1+P2
> (31 numbered IDs / 33 distinct issues). Deliberately out of this batch: minor items 43-47 (front-end a11y),
> the P3 items M-6 (tighten the VBS match surface) / M-7 (migu wasm SRI) / M-20 (frozen-bundle i18n measurement),
> and every item the report flagged "to be confirmed". Every fix ships with a regression lock; security
> invariants additionally got mutation verification.

**1. Security hardening (S-1, M-1 ~ M-5)**

| ID | Where | What |
| --- | --- | --- |
| S-1 | `src/spider.py:140-174`, `112-121`, `6183-6254` | The Shopee short-link landing page now passes the **same two gates** that XHS SEV-2214 introduced: host-family allowlist (via `urlparse().hostname`, exact-or-`.`-suffix, userinfo rejected) plus `web_config._host_internal_reason` for internal/loopback/cloud-metadata targets. An untrusted landing page is discarded, the user-entered URL is kept and the Cookie header is stripped. The constructed `api_host` is re-checked against the allowlist (so a poisoned `host_suffix` cannot leak), and `_shopee_host_suffix` moved from raw string splitting to hostname parsing |
| M-1 | `src/async_http.py:87`, `460`, `532-588`, `679` | **Per-hop** redirect re-validation for the probe and every `async_req` branch: one `event_hooks` response hook wired at the single `_build_client` site re-runs `_internal_stream_target_reason` on each hop's landing URL, stopping the chain and returning the existing "unreachable" semantics. The DNS-rebinding window is registered as residual risk (judgement results are deliberately not cached) |
| M-2 | `src/sync_http.py:56-140`, `309`, `375` | `sync_req` gains a scheme allowlist (reusing `utils.is_safe_http_url` rather than a second implementation) and its opener is built from an explicit protocol whitelist that no longer registers FileHandler/FTPHandler/DataHandler; the abroad branch, which uses the process-global `urlopen`, gets a post-landing re-check |
| M-3 | `src/spider.py:716-720`, `911`, `1126`, `1289`, `1848`, `3324`, `3490`, `4279`, `4512`, `5137` and more | Raw URLs entering `raise`/log calls now pass `utils.mask_credentials` first (the primary case was the PandaTV/WinkTV private-room `pwd` landing in rotated logs; Douyin / TwitCasting / Weibo closed on the same standard) |
| M-4 | `src/spider.py:3908-3920` | `login_popkontv` — the only production httpx request in the file that bypasses `async_req` — masks the exception text and adds `type_name`, so proxy `user:pass@` cannot reach the logs |
| M-5 | `src/notify.py:92-98`, `113-155`, `173-187`, `203-205` | All four post-record custom-script failure branches mask the command text; the second `communicate()` after a timeout is now bounded; process-tree reclamation uses `start_new_session` + `killpg` on POSIX and `taskkill /T /F` on Windows (argv list, never shell=True), degrading to the original `kill` on any failure |

**2. Recording and resolver correctness (M-8 ~ M-13)**

| ID | Where | What |
| --- | --- | --- |
| M-8 | `src/spider.py:207-324` | The module-global fast path for the Kuaishou `did` and Bilibili `buvid3` caches now compares the proxy context, so a fingerprint obtained via proxy A is no longer reused by rooms on proxy B (mirrors the already-fixed ttwid MIN-2220). Lock types and the cross-await semantics untouched |
| M-9 | `src/spider.py:723`, `914`, `1173`, `1370`, `1610`, `3200` | Remaining `anchor_name`-can-be-None sites unified on `_dig_str` / `isinstance(v, str)`, eliminating the `clean_name(None)` crash that used to knock out the whole parsing round |
| M-10 | `src/spider.py:4325-4331` | The TwitCasting restricted-room login fallback now also catches `ValueError` (PEP 758 parenthes-free form); the promised "parse failure → login retry" path was previously unreachable |
| M-11 | `src/stream.py:654-691` | TikTok quality selection no longer writes the FLV-clamped index back into the shared variable: the original requested index is kept and FLV/HLS are clamped independently against their own list lengths (same standard as the Douyin branch in the same file); the fallback base was fixed in the same pass. HLS-only rooms asking for the lowest tier no longer silently pull the top tier without a downgrade warning |
| M-12 | `main.py:4950-4959` | The danmaku platform list becomes a list comprehension with `strip()` and empty-item filtering, matching the HLS exclusion list in the same function; `"斗鱼直播, B站直播"` no longer never matches |
| M-13 | `src/platforms/bilibili.py:55-159` | A `_report_close` gate was added to Bilibili host rotation: while candidates remain untried the event is an intermediate state (routed through `_on_reconnect` for tracing), and only exhaustion or the `_stopped` terminal state reports — exactly once. `_hosts_left` is zeroed when rotation ends, otherwise real disconnects mid-session get swallowed. Not pushed down into WsClient, the `backup_url` primary/backup rotation was not merged, and `src/ws_client.py` is untouched |

**3. Web / i18n / front-end (M-18, M-19, M-21 ~ M-23, M-26)**

| ID | Where | What |
| --- | --- | --- |
| M-18 | `web.py:199-239`, `258-262` | The "authentication disabled must not bind beyond loopback" gate was moved **above** `_enter_background_mode`, so the refusal text is no longer swallowed by the stdio redirect; the falsified "refuse = zero-side-effect exit" comment was corrected per the AGENTS exception clause and compressed into a one-line dated note |
| M-19 | `i18n.py:399-414` | Both `tr()` except layers now include `AttributeError, TypeError` (measured: `{x.y}` with `x=None` raises AttributeError, `{x:d}` raises TypeError), honouring the "never raises" promise; `translated_print` was reviewed and has no equivalent gap (it never calls `.format`) |
| M-21 | `web/app.js:753-870` | All three polling chains (SSE / log / danmaku) renew through one shared `makePollChain()` generation token: both `halt()` and `begin()` advance the generation, so an in-flight callback whose generation is stale is dropped and never re-schedules orphaned timer chains |
| M-22 | `web/app.js:1498-1560`, `web/index.html:176-190`, `web/style.css` | The auth re-verification password is collected in a `type="password"` modal instead of `window.prompt`'s cleartext; all four exits funnel through `_settleReauth()` which clears the input node immediately; `reauth_password` is attached only to the two authentication keys' PUTs and no longer rides along on every other config key of the same save pass |
| M-23 | `web/app.js:1107-1117` | The collapsed-danmaku counter `m.dropped` now goes through `esc()`, restoring this file's "every concatenation path is escaped" invariant |
| M-26 | `tests/frontend/test_regression_2026_09_22_gates.mjs` | Removed two `doesNotMatch` text locks pinned to outdated source literals (the backend does enforce re-verification and the literal drifted, so the assertions passed vacuously and contradicted the new Python-side contract); replaced with a positive behavioural lock on "the authentication-key path really collects and sends `reauth_password`". Test count 32 → 36 |

**4. GUI robustness (M-14 ~ M-17, M-24, M-31)**

| ID | Where | What |
| --- | --- | --- |
| M-14 | `gui.py:1110-1360`, `3627`, `3684` | The quality-monitoring match patterns are now derived from **`i18n.tr()` results using the same msgid as the producer** (escaped then assembled) and recomputed lazily per language; hard-coded Simplified-Chinese constants removed. The one `src/recorder_status.py` literal that is **not** run through `tr()` continues to match verbatim, with the reason stated in the comment. The `#DLRQ` structured status protocol was **deliberately not introduced** — AGENTS key convention #13 lists it as a pending-approval long-term plan. A self-audit during wrap-up also fixed a defect this batch introduced itself: the per-language cache now only commits after re-verifying the language code is unchanged — the build reads `tr()` six times while the recording thread and the UI thread can switch language concurrently, so an unconditional write would freeze a **mixed-language** pattern set in place (lock: `test_mid_build_language_switch_is_not_cached`) |
| M-15 | around `gui.py:1466`, `3519`, `3667`, `3132` plus `gui.py:1599-1612` | The renewal `after()` of the self-renewing chains moved into `try/finally` so it is re-armed unconditionally; external numeric fields such as `ts` go through one shared tolerance helper (a `null` record can no longer break the timer chain). Wrap-up added the **fourth chain of the same family**, `_pump_ui_events` (the UI event pump): its renewal sat on the last statement while the preceding "activate the log flush chain on demand" can raise during a window-destroy race — a broken pump means queued `post_ui` callbacks such as `_on_recording_stopped`/`_finalize_quit` never run (the window cannot be closed). The `_CHAINS` structural lock was extended to name all four |
| M-16 | `gui.py:3226-3352`, `4175-4189` | New single-flight entry `_stop_child_once` shared by "stop recording" and "quit": quitting reuses an in-flight stop thread instead of a second concurrent console attach/detach sequence (console attachment is process-global state); both registration and deregistration sit on unconditional paths |
| M-17 | `gui.py:3801-3844` | The tail thread's try/except was pushed down to **each event** (bad record → continue), so one malformed event no longer discards the intact events that follow it in the same chunk; the outermost handler now leaves a rate-limited warning |
| M-24 | `tests/test_danmaku_monitor.py:562-599` | The tail test sets **the Event it actually passed in** and adds `assert not t.is_alive()` — "it stops after rotation" is verified for the first time (previously the daemon thread lingered until process exit) |
| M-31 | `tests/test_gui_monitor.py:79-85`, `tests/test_danmaku_monitor.py:429` | The child process gets `PYTHONUTF8`/`PYTHONIOENCODING` explicitly; `import gui` moved out of collection time into the test body with an autouse fixture restoring `DLR_GUI_PARENT` in pairs (`patch.dict(os.environ)` forbidden) |

**5. Test system and maintenance scripts (S-2, M-25, M-27 ~ M-30, M-32)**

| ID | Where | What |
| --- | --- | --- |
| S-2 | `tests/test_twitch_live_collector.py:42`, `109`, structural lock `118-190` | The whole body moved into `def main()` + `if __name__ == "__main__": main()`, making it homogeneous with the four sibling live scripts. Evidence: `pytest --collect-only` went from **20.55 s / no tests collected / exit code 5** to **0.81 s / 1 test collected**; the collection-time live connection, `sleep 20`, `tests/_out_live` purge and session-killing `sys.exit(1)` are all gone |
| M-25 | `tests/test_huya_danmaku.py:121` | The bare assignment `spider.async_req = fake` replaced by `monkeypatch.setattr` (the old form never restored and used an incomplete signature, poisoning the whole pytest session) |
| M-27 | `tests/test_config_io_backup.py:20-26`, `tests/test_log_archive.py:114`, `tests/test_anchor_rename.py:15-20` | Patches of process-global `os.remove`/`os.rename` now go through a `SimpleNamespace(**vars(os))` shim installed on the module under test's own `os` reference (loguru and other background threads are no longer affected during the window) |
| M-28 | `tests/frontend/test_motion.py` (new), `.github/workflows/ci.yml` | The five `test_motion.mjs` cases gained a Python wrapper and were added to the CI "Gate frontend tests not skipped" node-id list (`node --test <file>` only runs the named file and never discovers its siblings, so those degradation/cleanup locks never executed in normal CI). This batch also registers WP-G's new `tests/frontend/test_auth_reauth.py::test_auth_reauth` in the same list |
| M-29 | `tests/test_machine_validation_fixes.py` | The heartbeat-timeout case now records the **timestamp and origin** of every `close()` and attributes per entry point, asserting the first close happens at the timeout point and before the deliberate stop (the old `len(close_called) >= 1` was blind to deleting the timeout branch); the "all three call sites timed out" aggregate count in the same file was tightened to per-entry attribution |
| M-30 | `tests/test_notify.py:27`, `63`, `74` | Child-process commands use `sys.executable` instead of the literal `python` (images that ship only `python3` always failed these, while the local Windows box was always green) |
| M-32 | `scripts/sync_metadata.py:112-158`, `scripts/smoke_test.py:87-192`, `214-218` | (1) `shutil.which` early return plus `OSError` catching: with uv missing the WARN branch is reachable and the egg-info rebuild still runs (the read-only `--check` path spawns no subprocess, pinned by a tripwire case). (2) `load_config` is the single validation point and malformed headers/checks shapes exit rc=2 (previously `.items()` raised AttributeError → rc=1, breaking the contract `_ci_web_smoke.sh` uses to tell "panel failure, retryable" from "config problem") |

**6. i18n catalogue synchronisation (new strings from S-1/M-4)**

- Four new msgids (three Shopee gate messages + the popkontv exception carrying `type_name`) were added to all four catalogues
  (`zh_CN.po`, `en_US.json`, `en_GB.json`, `zh_TW.yaml`) and the `.mo` was regenerated; the collision-avoidance intermediate
  `_i18n_pending_wpa.json` was deleted after the central merge, per AGENTS key convention #14.
- Entry counts under both accepted measures (read locally on 2026-09-29, not estimated): JSON key count **791**;
  `.mo` header N **792** (the header's empty msgid is counted, so N = key count + 1). Command used:
  `python -c "import struct;print(struct.unpack('<6I', open('i18n/zh_CN/LC_MESSAGES/zh_CN.mo','rb').read(24))[2])"`;
  `python scripts/compile_po.py --check` self-reports the same 792 (.po/.mo in sync);
  `python scripts/extract_i18n_strings.py` reports 0 missing.

**7. Verification (real devices, per AGENTS Definition of Done step 2)**

| Date | Platform | Room address (masked) | Script | Result | Readable evidence |
| --- | --- | --- | --- | --- | --- |
| 2026-09-29 | Douyin | live.douyin.com/699394970561 | `tests/test_douyin_live_collector.py` | PASS | 59 messages / SRT 4518 bytes |
| 2026-09-29 | Bilibili | live.bilibili.com/21452505 | `tests/test_bili_live_collector.py` | PASS | 9 messages / SRT 678 bytes, no "fake close" under the `_report_close` gate |
| 2026-09-29 | Huya | www.huya.com/660000 | `tests/test_huya_live_collector.py` | WARN | 0 messages, connection healthy, no danmaku in that window (SRT produced) |
| 2026-09-29 | Twitch | twitch.tv/forsen | `tests/test_twitch_live_collector.py` | WARN | 0 messages; the guarded script still runs standalone (live evidence for S-2) |
| 2026-09-29 | Shopee | shp.ee/**** (invalid short link) | in-process probe `spider.get_shopee_stream_url` | live interception evidence | The landing-derived `api_host=https://live.shopee.ee` was blocked by the family allowlist gate with a warning and returned as not live — real outbound evidence for S-1 |
| 2026-09-29 | Douyu | www.douyu.com/1, /23059, /9235411 | `tests/test_douyu_live_collector.py` | SKIP(room offline) | Anchor names still resolved correctly ("斗鱼官方视频号", "注意前方猪妖"), so the resolver chain is intact; re-run when a room is live |
| 2026-09-29 | TikTok | www.tiktok.com/@tiktok | in-process probe | SKIP(no outbound route) | `ConnectTimeout` plus the built-in guest-cookie expiry warning; M-11 needs the user to re-run a real room with quality set to the lowest tier and confirm `logs/PlayURL.log` picks a non-first m3u8 |

**8. Residual gaps and actions handed back to the user**

- **GUI eyeball checks**: headless verification does not replace observation for M-14/M-15/M-16/M-17 — switch to English, restart recording, and confirm the quality page still shows recording lines / downgrade warnings / empty-state clearing; for M-22 confirm the password modal masks input and that the field is cleared on cancel.
- **M-18**: the refusal text now reaches un-redirected stdout/stderr plus one warning, but double-clicking `python web.py` on a desktop still destroys the console window when `sys.exit(1)` runs; eliminating the "flash" entirely is a product decision (pause or banner before refusing).
- **Three boundaries of the per-hop re-check (M-1)**: the synchronous probe in `src/stream_select.py` builds its own `httpx.Client` and does not go through `_build_client`, so that shape is still un-wired; the response hook fires only after that hop's response headers arrived (what is closed is "no further following and no leakage", not "no connection"); the DNS-rebinding window cannot be eliminated at this layer.
- **The retry action is rc-agnostic**: `.github/actions/retry` retries on any non-zero exit code alike, so M-32(2)'s "rc=2 means a config problem, stop immediately" is currently only visible in the step log; at job level 1 and 2 remain indistinguishable — decide whether the retry action should gain an exit-code bucket input.
- **Proposed new gate not implemented**: templating/lint checks for the live scripts (mandatory `__main__` guard, platform-prefixed cleanup) were kept as a recommendation, not added unilaterally.
- **P3 / to-be-confirmed items untouched**: M-6, M-7, M-20 and the minor items flagged as needing measurement.

### v4.4.0 (2026-09-29) — GUI freeze fix: adaptive wraplength reworked to true debounce + hysteresis, eliminating the event-storm oscillation during DPI rescale

> Observed by the user: text flickering at high frequency → some UI elements rendered incompletely → the whole window freezing unresponsive. The root cause is the **previous fix (adaptive wraplength) writing synchronously inside `<Configure>`**, oscillating with CTk's DPI-rescale machinery. The trigger is dragging the window to a monitor with a different scale factor (or a system DPI change) — the same mechanism as the dev-time stress probe hang, through two different entrances.

**1. Root-cause chain (all empirically verified)**

1. CTk's DPI-change handling runs `ScalingTracker.update_scaling_callbacks_* → widget _set_scaling → _draw → _update_dimensions_event → update_idletasks` — a **mutually recursive pump** (nested frames visible deep in ctk_scrollbar.py).
2. During rescale the internal label's width swings violently (probe measured 350↔1566 device px; at identical widths the wraplength got chased into `334→1038→190→858→…`).
3. The old binding called `label.configure(wraplength=…)` synchronously on every Configure — each write re-invalidates geometry into the same idle queue, which then never drains: **`update()`/mainloop never returns = freeze**; the high-frequency relayout = flicker; starved paints = missing elements.
4. Decisive control: under the same 10-flip DPI stress (via `set_widget_scaling`, the same callback chain as `check_dpi_scaling`) — with the binding active the loop never drained (killed at 120s = freeze reproduced); with the binding no-op'd the run **completed in 9.2s**.

**2. Fix (gui.py)**

| Item | Content |
| --- | --- |
| True debounce | `<Configure>` only resets a timer (`after_cancel` + `after(120ms)`); while the storm lasts **not a single write** happens — structurally impossible to feed geometry invalidation back into the recursion. Deliberately not "throttle to one write per 120ms" (a mid-storm write can re-ignite the recursion via the scrollbar threshold) |
| Hysteresis | `_wrap_should_apply(current, new, scale_changed)` pure function: skip when `|new−current| ≤ max(12, 2%)` and the scale is unchanged. The ±~11-logical-px wobble of a scrollbar appearing/disappearing is absorbed; first apply (current==0) and any scale change (the conversion basis moved) always apply |
| Race guard | `_run` is TclError-guarded throughout — the danmaku/quality placeholders are rebuilt every 2s, so a debounced callback can race destruction |
| Startup shaping | if a real width already exists at bind time (winfo_width>1) apply once synchronously so the first frame wraps; later changes go through the debounce |

**3. Verification**

- Stress regression lock (`tests/test_gui_wrap_hints.py::TestRealWindowWrap::test_dpi_flip_stress_*`, real window, skips headless): full GUI build + 8 DPI flips must drain the event loop (the pre-fix equivalent times out) with ≤24 wraplength writes per label (measured ~1 per flip).
- End-to-end real-window final check (1120×740, 150% system scaling): all four long hints unclipped; after simulated 1.2↔1.0 DPI flips everything converges to the correct wrapping with zero freezing.
- 5 headless pure-function cases for the hysteresis + AST source locks for debounce/guards; `run_gates.py` 8/8, pytest 3308 passed / 0 warnings, basedpyright 0/0/0.

**4. Known micro-edge**

- For ~120ms after startup a long hint may render one unwrapped frame before the first debounced settle — an imperceptible trade for structurally safe zero writes during storms.

### v4.4.0 (2026-09-29) — GUI text-clipping fix: adaptive wrapping for long hints (`_bind_adaptive_wraplength`), eliminating symmetric pack clipping on both sides

> Observed on user screenshots (150% DPI, default 1120×740 window): the console hint "启动后将调用 main.py…" lost half of its first and last characters, and the danmaku empty-state hint was clipped at the right edge. The root cause is one family: **when a label's requested width exceeds the width its parent allocates, Tk pack centers it (default anchor=center) and clips symmetrically on both sides**; the quality page's fixed `wraplength=1000` is a variant of the same failure under narrow windows (right-edge clip). A repo-wide sweep found 5 sites of the same shape — all fixed together.

**1. Changes by module**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Adaptive wrapping | Added | `gui.py` | `_compute_wraplength(width_device_px, scale, margin)` pure function (device px → logical: CTk scales wraplength by `_widget_scaling` on configure (`ctk_label.py`), while `<Configure>` reports device pixels, so divide by `ScalingTracker.get_widget_scaling`; floor 120 prevents wraplength→0 from silently re-enabling clipping); `_bind_adaptive_wraplength(label)` binds the label's **own** window width (requires `pack(fill=tk.X)`: window width is packer-allocated, decoupled from the label's request — no wraplength→request→width feedback loop; sets an initial value from the current width because a re-pack with unchanged geometry fires no Configure); `ScalingTracker` imported from its definition path `customtkinter.windows.widgets.scaling.scaling_tracker` (the top-level namespace does not export it — reportAttributeAccessIssue) |
| Wiring | Modified | `gui.py` | console hint now `pack(fill=tk.X, expand=True)` + binding; quality hint drops fixed `wraplength=1000` for the binding; the quality/danmaku empty-state labels consolidated into `_make_quality_placeholder` / `_make_danmaku_placeholder` factories (parameter `tk.Misc` — CTk 6.0's CTkScrollableFrame is not a CTkFrame subclass), shared by initial build and every refresh rebuild; duplicate copies of the copy reduced from 4 to 1 each |
| Tests | Added | `tests/test_gui_wrap_hints.py` | three layers: subprocess unit tests of the pure function (conversion anchors 1584@1.5→1050 pinned, 120 floor, zero/negative scale, monotonicity); AST source locks (helper defined once with exactly 4 wiring points, each placeholder copy appears exactly once, no constant wraplength kwargs anywhere, factories must keep fill=tk.X + binding, both build and refresh paths must call the factories); a real-window case (fill=X label wraps without clipping in a narrow container, wraplength grows when widened; skips without a display — the only skip surface) |

**2. Root causes & design points**

1. **Why half-characters missing on both sides**: pack's default anchor=center centers an oversized child in its (too narrow) parcel, so the overflow is clipped equally left and right — "启" half-missing at the left and "制" half-missing at the right is the fingerprint of requested > allocated width.
2. **Why binding the label's own width is safe**: under `fill=tk.X` the window width is entirely packer-allocated; changing wraplength only changes the requested height, never the window width, so oscillation is structurally impossible. Binding the parent's width would instead require subtracting sibling widgets (the button row) — more fragile.
3. **The real-window case deliberately avoids `set_widget_scaling`**: a manual scaling override fights CTk's system-DPI tracking during real window mapping (measured event storm → `update()` never returns). The system's own DPI already exercises the conversion for real, and the formula is pinned by the pure-function anchors.
4. **Two CTk 6.0.0 facts** (verified from source): `configure(wraplength=...)` multiplies by `_widget_scaling` internally while `cget("wraplength")` returns the logical value; `CTkScrollableFrame`'s MRO does not contain `CTkFrame` (they share only the `CTkBaseClass` ancestor).

**3. Verification**

- End-to-end measurement (this Windows machine, 150% system scaling, full `LiveRecorderGUI` built in a subprocess at the screenshot's 1120×740): before the fix the console hint measured reqwidth 768 > actual ~520 (symmetric clip) and the danmaku hint 1564 > 1538; after the fix all four long hints (console hint / danmaku placeholder / quality placeholder / quality hint) satisfy "requested ≤ allocated with wraplength active" (540≥519, 1196≥1092, 1196≥540, 1230≥986), the console hint wrapping onto two lines.
- `run_gates.py` 8/8 green; full pytest 3300 passed / 14 skipped / 0 warnings; coverage all 44 modules above threshold; basedpyright 0 errors / 0 warnings / 0 notes; the real-window case passed three consecutive runs in ~8s each.
- Regression locks: `tests/test_gui_wrap_hints.py` (10 cases); mutation check — removing either factory's `_bind_adaptive_wraplength` call or dropping fill=tk.X turns the AST locks red immediately.

### v4.4.0 (2026-09-29) — GUI theme layer (Phase 3): 3 semantic-token themes + runtime switching + `[GUI] gui_theme` persistence + WCAG contrast machine-checks

> Module-level overview of this change. Phase 3 (UI modernization · GUI theme layer) adds `src/ui_theme.py`
> (zero display dependency, safe to import headless); the `gui.py` sidebar gains a "UI Theme" menu
> (Light / Dark / High contrast) whose choice is written back to `config.ini [GUI] gui_theme` and registered
> as a ttk theme (`dlr-<id>`, clam base). The `Colors` / `Fonts` facades and every existing symbol signature
> are unchanged.

**1. Changes by module (added / modified + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Theme engine | Added | `src/ui_theme.py` | 13 semantic slots (proposal §5.2's twelve + `on_primary`: in dark/high-contrast themes the primary button is a bright-blue fill whose label needs a near-black foreground — `surface` doubling as button text fails on dark); `THEMES` with three sets (light / dark / high_contrast); `contrast_ratio` per WCAG relative luminance; `CONTRAST_REQUIREMENTS` contract (body text 4.5 / non-text & disabled 3.0); `ThemeManager` (idempotent select/apply, guard against duplicate `theme_create`); `load/save_theme_preference` via `update_or_append_config_line` (creates missing section/key, preserves comments, atomic write) — deliberately not `config_io.read_config_value`, whose write-back holds `main.file_update_lock` (recorder lock system) |
| GUI wiring | Modified | `gui.py` | imports `src.ui_theme`; `__init__` reads `[GUI] gui_theme` — an explicit preference syncs the CTk appearance mode to the theme's family, otherwise follow the system appearance (pre-upgrade behavior kept); sidebar "UI Theme" `CTkOptionMenu` (i18n display names) + `_on_theme_change` (select → apply → persist → appearance mapping → appearance-menu display sync → `_sync_canvas_bg`); `_THEME_CTK_MODE` / `_THEME_LABELS` module constants; `Colors`/`Fonts`/`LiveRecorderGUI`/`SystemTray`/`AdvancedSettingsWindow`/`_quality_alert_expired` symbols and signatures untouched |
| Template & docs | Modified | `config/config.ini`, `README.md` | template gains `[GUI] gui_theme =` (empty = follow appearance); README config block documents the GUI section |
| i18n | Synced | `zh_CN.po`(+`.mo`), `en_US.json`, `en_GB.json`, `zh_TW.yaml` | 7 new entries: UI theme label, three theme names, switch success and two write-failure messages (`{theme}`/`{type_name}`/`{err}` placeholders). Four-catalog key-set equality holds (i18n test locks green); `web/app.js` needs no sync — the theme menu is GUI-only copy with no web surface |
| Tests | Added | `tests/test_ui_theme.py` | 34 cases: contrast-math anchors (black/white 21:1, white-on-#4F6DF5 pinned at 4.34), registry integrity (every slot, strict #RRGGBB), contrast contract parameterized across all pairs × themes, persistence (missing/invalid/round-trip/comment preservation/single-line on repeated save), switch idempotency (same-id short-circuit + byte-identical config), ttk-settings pure-data assertions + real-Tk integration (skips without a display — the only such case) |

**2. Root causes & design points**

1. **Contrast first**: all three themes' tokens were iterated to compliance (body 4.5 / non-text 3.0) with a scratch script before the values were baked into the module; light's `primary` is `#4358E8` (brand hue, deepened) — the original `#4F6DF5` measures 4.34:1 with a white label, below AA. The scratch script is deleted; `tests/test_ui_theme.py` keeps regressing the numbers.
2. **The cost of 3:1 borders**: WCAG 1.4.11 non-text contrast pushes light's border to `#848DA0` (darker than common light borders) — the machine-checked contract wins over visual habit.
3. **Visible effect boundary of Phase 3**: CTk widget colors are taken over by tokens in Phase 4 (ui_kit); for now a theme switch maps to the CTk appearance mode (high_contrast → dark) plus ttk element colors (effective once Phase-4 widgets land). The "Appearance mode" menu stays (it owns system-follow); Phase 4 unifies the two controls.
4. **Idempotency in three places**: `select` short-circuits on the same id (no redundant config writes), `save` keeps a single line on repeated saves (update before append), `apply` guards duplicate registration (`theme_create` raises TclError on an existing theme name).

**3. Verification**

- `pytest tests/test_ui_theme.py` → 34 passed (locally including 3 real-Tk integration cases; on headless CI those 3 skip while the other 31 run).
- Real-window smoke (this Windows machine, full `LiveRecorderGUI` built in a subprocess): with no preference the theme follows the system appearance to `light`; menu display names localized correctly; a simulated click on "High contrast" flipped `theme_manager.theme_id == "high_contrast"`, wrote `[GUI] gui_theme` into a temp copy, switched ttk to `dlr-high_contrast`, mapped CTk to Dark, and synced the appearance menu's display to "深色"; the real `config.ini` was never written (write path redirected).
- `python scripts/run_gates.py` → 8/8 green; full pytest 3286 passed / 14 skipped / 0 warnings; coverage 84.07% (all 44 modules above threshold); basedpyright 0 errors / 0 warnings / 0 notes; `import gui` headless-import succeeds (compatibility contract).

**4. Known edges & hand-back**

- The real-Tk integration cases skip on headless CI (no X server on ubuntu runners); to run them in CI regularly, add xvfb to the test job (deferred to Phase 5 evaluation).
- Coexisting "Appearance mode" and "UI Theme" menus are a Phase-3 transitional shape (the former owns CTk light/dark incl. system-follow, the latter owns token themes plus persistence); they get unified during the Phase-4 widget replacement.

### v4.4.0 (2026-09-29) — Web backend FastAPI → Starlette migration: self-built route adapter + zero-dependency validation layer; all 24 route contracts and security invariants preserved verbatim

> Module-level overview of this change. Phase 2 (UI modernization · framework replacement) migrates the Web admin panel backend
> from FastAPI to Starlette directly: removes the `fastapi` / `pydantic` dependencies, adds `src/web_models.py`
> (a pure-stdlib dataclass validation layer) and the `_route` adapter inside `src/web_api.py` (replicating FastAPI's
> model-argument parsing / Query clamping / dict→JSON serialization / sync-endpoint threadpool dispatch). All 24 route
> handlers are untouched; business logic and every security invariant (MID-*/SEV-*) are preserved verbatim. New
> `tests/test_web_api_routes.py` dynamically asserts the route contract, replacing the static baseline
> `web_api_routes_baseline.json` that tripped the sensitive-content gate.

**1. Changes by module (added / modified / deleted + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Web backend framework | Migration (dependency removal) | `src/web_api.py` | `FastAPI()` → `Starlette()`; the 24 `@app.post/get/...` decorators replaced with `@_route(app, [METHOD], path)`; 5 `Query(...)` params de-decorated to plain defaults; `cast(FastAPI, request.app)` → `cast(Starlette, ...)`; auth middleware rewired as `app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)` [corrected 2026-09-29 runtime verification]: the initial draft wrongly claimed `@app.middleware("http")` was Starlette-native and kept verbatim — Starlette has no such decorator method and the import would raise AttributeError (mypy attr-defined agrees); FastAPI's decorator is exactly `add_middleware(BaseHTTPMiddleware, dispatch=...)` underneath; additionally a JSON `HTTPException` handler is registered (Starlette's built-in handler replies with a PlainTextResponse, dropping the `{"detail": ...}` error contract) |
| Request model validation | Added (zero-dependency) | `src/web_models.py` | 9 dataclasses (LoginRequest / RoomCreate / RoomUpdate / RoomToggle / RoomQualityUpdate / QualityOptionsUpdate / RecordingToggle / ConfigUpdate / LanguageUpdate) use a `.parse(data)` classmethod instead of pydantic `BaseModel`; missing field / wrong type → ValueError; bool accepts only real Python bool; extra fields ignored |
| Route adapter layer | Added | `src/web_api.py` | `_route` decorator factory: `inspect.signature`-driven classification (model arg / Query arg / request); JSON body parsed via `_read_json_body`, invalid body → 422; Query clamped by `_QUERY_DEFAULTS` default and bounds; sync `def` endpoints dispatched via `run_in_threadpool` (matches FastAPI, avoids blocking the event loop); non-Response returns wrapped in JSONResponse |
| Tests | Migration + added | `tests/test_web_api.py`, `tests/test_web_config_locks.py`, `tests/test_danmaku_monitor.py`, `tests/test_regression_2026_09_22_web_g.py`, `tests/test_web_api_routes.py` | 5 `TestClient` imports switched to `starlette.testclient`; new dynamic route-contract test asserts the exact set of 24 route method/path pairs + the `/web` mount; deleted `tests/web_api_routes_baseline.json` |
| Dependency manifests | Synced deletion | `requirements.txt`, `pyproject.toml` | Removed `fastapi>=0.140.0` and `pydantic>=2.13.4`; kept `starlette>=1.3.1` / `uvicorn` / `python-multipart`; name-set equality verified by `tests/test_regression_2026_09_22_gates.py` |

**2. Root-cause details**

1. **Performance & size**: FastAPI pulls in pydantic + pydantic_core, one of the Web panel's major size contributors; driving Starlette directly drops both, shrinking the bundle and startup overhead (size pending local re-measure with `scripts/report_bundle_size.py`).
2. **Wiring semantics preserved**: Starlette, unlike FastAPI, does not auto-dispatch `def` sync endpoints to a threadpool nor auto-parse JSON bodies; missing either blocks the event loop or changes 422 behavior — the `_route` adapter restores each equivalent behavior, leaving handler bodies untouched.
3. **422 contract deviation (known)**: the old field-level pydantic 422 `detail` is now a string `detail` (`str(ValueError)`); the frontend `apiError()` only reads the `detail` text, so behavior stays compatible.

**3. Verification (2026-09-29 runtime re-run, venv restored)**

- `python scripts/run_gates.py` → **8/8 green** (black / isort / mypy / annotation conventions / compile_po / check_version / check_runtime_pins / pytest backstop).
- `pytest` → **3248 passed, 14 skipped, 0 failed, empty warnings summary**; with `--cov=src`, `scripts/check_coverage.py` reports all 43 modules above threshold (total coverage 83.98%); `basedpyright` 0 errors / 0 warnings / 0 notes.
- `pytest tests/test_web_api.py tests/test_web_api_routes.py -q` → 165 passed, 2 skipped, 0 warnings.
- Runtime verification caught and fixed two wiring errors the earlier static-only pass could not see:
  1. `@app.middleware("http")` raises AttributeError at import time on Starlette (P0, panel unusable) → replaced with `add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)`;
  2. `raise HTTPException` inside endpoints came back with a plain-text body under Starlette's built-in handler — the `{"detail": ...}` JSON contract drifted (a batch of security tests went red) → registered a FastAPI-equivalent JSON handler (headers passthrough keeps Retry-After usage).
- Companion fixes: `scripts/check_version.py`'s web_api version check retargeted from `FastAPI(version=)` to the importlib.metadata dynamic-read shape (MIN-2262 fail-closed semantics kept; all three branches mutation-verified); the MID-2241 field-scan anchor in `tests/frontend/test_regression_2026_09_22_gates.mjs` moved to `src/web_models.py` and the endpoint-slice anchor to `@_route(app, ["GET"], "/api/language")`; the `/health` version assertion in `test_web_api.py` now reads the same-source `_APP_VERSION`; `uv.lock`/`egg-info` regenerated via `sync_metadata.py` (requires.txt free of fastapi/pydantic).

**4. Not verified & hand-back (closed)**

- ~~Gate green and runtime verification~~: done (see "3. Verification").
- Still handed to a later phase: the bundle-size re-measure `python scripts/report_bundle_size.py dist/DouyinLiveRecorder` requires one `build_exe.py` run first (local `dist/` is empty; a phase-5 closing item). Note the local venv still has fastapi/pydantic leftovers from the removed manifest (`pip install -r requirements.txt` does not uninstall removed packages); gates and tests are unaffected, but the user should run `pip uninstall fastapi pydantic` in a normal terminal before the bundle re-measure to keep the environment in sync with the manifest.

**5. Breaking changes**

- Removed the `fastapi` / `pydantic` runtime dependencies; `src/web_models` models are read via `.parse()` instead of the pydantic API (internal use, no impact on external plugins). All other routes, request/response shapes, security headers, and the auth middleware behave unchanged.

### v4.4.0 (2026-09-29) — Web front-end motion layer (Phase 1): scroll reveal / parallax particles / reduced-motion degradation, zero dependencies and zero build

> Module-level overview: Phase 1 (UI modernization · front-end motion) adds `web/motion.js` (223 lines, zero-dependency IIFE mounting `window.__dlrMotion`), adds the `<canvas id="bg-canvas">` background layer and script reference to `web/index.html`, and adds motion tokens plus full `prefers-reduced-motion` coverage to `web/style.css`. **Motion only adds classes, never wrapper elements** — the `tbody.innerHTML` fragment assertions in `tests/frontend/*.mjs` regression locks are unaffected; dynamically rendered table rows do not participate in the reveal animation.

**1. Changes by module (added / modified + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Motion engine | Added | `web/motion.js` | single rAF loop, IntersectionObserver reveal (threshold 0.15, rootMargin `0px 0px -8% 0px`, stagger `min(index*40, 240)ms`, one-shot unobserve on hit), DPR capped at 2, pauses on `document.hidden`, full degradation under `prefers-reduced-motion: reduce`, `destroy()` leaves no timers; particle count `clamp(18, floor(viewport area/22000), 64)`, halved when viewport <768px or `hardwareConcurrency ≤ 4` |
| Page wiring | Modified | `web/index.html` | `<canvas id="bg-canvas" aria-hidden="true">` as the first child of `<body>` (pointer-events:none, z-index -1); `<script src="/web/motion.js">` appended at the end (defer, non-blocking) |
| Motion styles | Modified | `web/style.css` | `#bg-canvas` fixed layer, `.reveal`/`.is-revealed` transitions, `:focus-visible` ring, full `@media (prefers-reduced-motion: reduce)` coverage (motion section ≈ lines 508–547); transitions only touch transform/opacity/border-color/box-shadow, never layout properties |
| Tests | Added | `tests/frontend/test_motion.mjs` | 5 cases (node:test + node:vm sandbox driving motion.js: degradation gate / reveal / particle parameters / hidden pause / destroy cleanup), zero npm dependencies |

**2. Verification & known deviation**

- `node --test tests/frontend/*.mjs` → **65/65 green** (existing regression locks + 5 new); `tbody.innerHTML` fragment assertions intact.
- **Known deviation**: motion.js measures 9449 bytes (≈9.2KB), about 15% over the ≤8KB performance budget in proposal §5.1 — defer loading, single rAF and read/write separation all hold; the size deviation is deferred to Phase 5 evaluation (minify or split; no functional impact).

### v4.4.0 (2026-09-29) — Web panel mobile fix: two-row top bar + safe-area / `dvh` adaptation + in-panel table scrolling, removing clipping and horizontal page scroll on iPhone 16 Pro Max and Pixel 10

> This section is the **module-level overview** of this change (module table + root-cause detail + verification
> readings). Only the Web frontend static assets are touched (`web/index.html` + `web/style.css`); the Python side
> is unchanged and **nothing was deleted** - no rule, element or file was removed, existing comments are all
> preserved under the "add only, never rewrite" convention, and this round only adds rules and rewrites existing
> declarations.

**1. Changes classified by module (added / modified / removed + file paths)**

| Module | Nature of change | Main files | Key change / judgement |
| --- | --- | --- | --- |
| Web page skeleton | Modified, 1 place | `web/index.html` | viewport meta gains `viewport-fit=cover` - without it `env(safe-area-inset-*)` is always 0, so safe-area adaptation cannot take effect at all |
| Web styles: top bar | Modified (layout constraints rewritten) | `web/style.css` | `height:56px` -> `min-height:56px`; padding on all four sides becomes `max(20px, env(safe-area-inset-*))`; `.tabs` gains `min-width:0`; under the <=768px breakpoint it wraps into two rows (row 1: brand + language/theme, row 2: tabs on a full-width horizontal scroller) |
| Web styles: main content | Modified + added | `web/style.css` | `.view` left/right padding routed through the safe-area insets; `body` gains `min-height:100dvh` (the original `100vh` stays as fallback) and `text-size-adjust:100%` against landscape font inflation |
| Web styles: data tables | Added | `web/style.css` | Under the <=768px breakpoint `.panel{overflow-x:auto}` plus `min-width:540px` for the dashboard / danmaku / files tables - headers are no longer squeezed into vertical single-character columns, they scroll inside the panel instead |
| Web styles: control bar / toolbars / toast | Modified | `web/style.css` | `.recording-control`, `.danmaku-toolbar` and `.file-header` gain `flex-wrap:wrap`; `.toast` positioning becomes `max(24px, env(safe-area-inset-bottom/right))`; `.inline-form input[type="text"]` becomes a shrinkable `flex:1 1 160px; min-width:0` |
| Web frontend logic and tests | **Untouched** | `web/app.js`, `tests/frontend/*.mjs` | CSS/HTML-only change with no JS behavioural surface; the existing frontend suite needs no new case (no new DOM contract) |
| Python side (recording chain / Web backend / config / i18n) | **Untouched** | none | No `.py` file, dependency list, config file or catalog was touched this round |

**2. Root-cause detail (numbered; each comes from comparing the two device screenshots against the stylesheet)**

1. **Top-bar overflow (the main cause, present on both devices)**: `.topbar` had a fixed `height:56px` and a single
   non-wrapping flex row while `.brand` also carried `white-space:nowrap`, so the minimum content width of
   "brand + five tabs + language select + theme button" exceeded both viewports. The flex children were squeezed -
   in the screenshots "仪表盘" broke into vertical characters and the right-hand theme button was clipped off screen -
   and the whole top bar overflowed, producing page-level horizontal scrolling. Fix: row 2 of the module table.
2. **Missing safe-area adaptation**: no `viewport-fit=cover` in the viewport meta and no `env(safe-area-inset-*)`
   anywhere in the styles, so the Dynamic Island, the rounded corners and the Home Indicator obscured top-bar content
   and the bottom-right toast, and landscape clipped both sides.
3. **`100vh` viewport height**: `body{min-height:100vh}` does not follow the dynamic viewport when the mobile address
   bar collapses or expands, which shows up as the bottom being covered by the browser toolbar or the layout jumping;
   replaced with `100dvh` (old browsers fall back to the `100vh` line above it).
4. **No scroll fallback for the dashboard "now recording" table**: a five-column auto layout breaks out of `.panel`
   at min-content width on narrow screens, so the "设置画质 / 实际画质" headers collapse into vertical characters and
   row heights diverge. Fix is in-panel scrolling plus a minimum width, which **coexists** with the existing
   `table-layout:fixed` scheme of `#rooms-view` - the latter's scope is still strictly `#rooms-view` and its comment
   constraint (3) was not relaxed.
5. **Control bar / toolbars do not wrap**: the state text plus two buttons in `.recording-control`, and the heading
   plus filter select in `.danmaku-toolbar`, squeezed each other on narrow screens; `flex-wrap:wrap` makes them wrap
   instead of compress, keeping touch targets intact.

**3. Verification**

- `node --test tests/frontend/*.mjs` -> **60 passed / 0 failed** (the 60 existing cases including the MIN-2241 root
  `index.html` integrity / crossorigin lock and the frontend `parseConfigBool` consistency lock; no case added or removed).
- Line-ending check (measured after the change): `web/style.css` CRLF=0 / LF-only=506 (still pure LF),
  `web/index.html` CRLF=175 / LF-only=0 (still pure CRLF) - on both files the side that was 0 is still 0 afterwards,
  with no opposite-form lines mixed in.
- The Python side is unchanged, so this round did not run the `pytest` / mypy / black / isort gate set;
  `scripts/check_annotations.py` does not apply (no Python file touched).

**4. Not measured and handed back (honest boundary)**

- Live-device verification column: `SKIP(no physical device / no remote debugging channel)`. The two viewport
  readings (iPhone 16 Pro Max 440x956 CSS px at DPR 3; Pixel 10 about 412 CSS px wide at DPR ~2.6) come from device
  specifications and the screenshots; no Safari/Chrome remote debugging or on-device re-screenshot was performed here.
- Hand-back action: after a hard refresh (Ctrl+F5) confirm four points on a real device or device emulator - the two-row
  top bar is fully visible and the tabs scroll horizontally, the page as a whole has no horizontal scrollbar, the
  Dynamic Island / Home Indicator do not cover the top bar or the toast, and the three data tables can be scrolled
  horizontally inside their panel to see every column.
- Step 2 of the Definition of Done (live-device verification) does not apply to a CSS-only frontend change (no
  recording chain / source selection / ffmpeg arguments / platform resolver involved), but the four points above must be
  confirmed on a real device by the user before this change counts as closed.

### v4.3.0-dev (2026-09-27) — Today's changes classified by module: four release-chain fixes + findings 4/5/6 + the four-doc size pass + the AGENTS.md trim + metadata and consistency sync

> This section is the **module-level overview** of everything changed on 2026-09-27 (summary table plus the readings that
> justify each verdict). The path-level detail follows today's documentation policy and lives where the other 73
> historical inventories live; the four same-day detail entries (three release-chain faults, findings 4/5/6 plus the doc
> size pass, and the `AGENTS.md` trim) sit below and cross-verify this one.

| Module | Nature of change | Main files | Key reading / judgement |
| --- | --- | --- | --- |
| Packaging and release chain | `make_zip` naming and guards modified, Linux ffmpeg source and eight pins corrected; **added** `_clean_stale_release_zips` / `_drop_stale_release_zips` / `_assert_dual_zips_are_two_files` plus the `--dual` vs `--no-zip` exclusion | `build_exe.py` | No function or download source deleted; artifact names are `DouyinLiveRecorder-v4.3.0-windows-amd64-{lite,full}.zip` |
| CI and release workflow | **Added** the `release-guard` job and the `Verify dist contains both lite & full zips` step | `.github/workflows/build-release.yml` | `gh release delete` keeps tags by default; `fail_on_unmatched_files: true` not relaxed; the 08:14 edit by another actor was untouched here (logged) |
| Tests | **Added** 9 cases (10 assertion units), reworked `_stub_build_steps`, corrected two comments | `tests/test_build_exe.py` | Single file 100 -> **105 passed**; four mutations each reddened only their own lock; `DIST_DIR` repointed to `tmp_path` so tests cannot delete real artifacts |
| Root conventions | `make_zip` item gained judgements (4) and (5) plus the nine lock names; protobuf range corrected to `>=6.33.5,<8`; volume pass | `AGENTS.md` | 97,034 -> **95,715 B** (-1.4%); token audit: 0 lost among `test_` names, CVE codes and `UPPER_SNAKE` identifiers |
| CN/EN wikis | **Added** four detail entries plus this overview; 73 inventories relocated; 109 (zh) / 181 (EN) truncated table cells restored; statistics and index sections rewritten; step 4 of "Packaging and Release" corrected | `CODE_WIKI.md`, `CODE_WIKI_EN.md` | `^### v` 169 -> **173 = 173**; dangling-code-span paragraphs 26/18 -> **0**; both files pure CRLF |
| User-facing docs | **Version-entry sync in a later step the same day** (09-26 ~ 09-27 changes folded into the `v4.3.0` entry, the date range extended to 09-27, and the stale test readings plus the "permanently red on this host" note corrected) | `README.md` (104,040 -> 109,648 B), `README_EN.md` (123,017 -> 129,644 B) | All five subsections match one-to-one in count (🐛 9 / ✨ 12 / ⚠️ 9 / 🛠️ 7 / 🧪 4) and order; `^### v` 20 = 20; both files still pure CRLF. They genuinely needed no update during the consistency audit; this step **adds** content and still does not compress the README changelog |
| Reference sub-docs and local records | **Added** two inventory appendices; session learnings and work log appended | `docs/agent-reference/changelog-file-inventories.md` (130,064 -> 139,024 B), `-en.md` (98,458 -> 107,897 B), `session-learnings.md`, `.workbuddy/memory/2026-09-27.md` | 41 (zh) / 32 (EN) historical inventories plus this block; every pointer resolves; 0 orphaned table headers |
| Build-artifact metadata | **Rebuilt** egg-info, fixing two real drifts | `DouyinLiveRecorder.egg-info/` (gitignored + dockerignored) | `PKG-INFO`'s `Requires-Dist: h2` `>=4.3.0` -> `>=4.4.1`; embedded README gained the v4.3.0 section; the other four files byte-identical |
| Dependencies / versions / ignore lists / config / i18n | **One comment repair only; the rest verified as needing no update** | `requirements.txt` (inline comment completed), `pyproject.toml`, `Dockerfile`, `docker-compose.yaml`, `.gitignore`, `.dockerignore`, `.coveragerc-concurrency`, `config/config.ini`, the four catalogs | The `websockets>=14.0` inline comment was cut at "…14.0+ API," (a trailing comment cannot continue onto the next line, so this was a real truncation); completed against the matching `pyproject.toml` comment as "12/13.x makes `connect()` raise TypeError immediately and the reconnect loop swallows it, so danmaku never connects". **No specifier changed**: 23 vs 23 package-name sets still equal, `tests/test_regression_2026_09_22_gates.py` 25 passed, the file stays pure LF. Everything else: `python 3.14` / `node 24` identical across workflows; tool pins match what is installed; no gaps in the four exclude sets; `config.ini` has 6 sections / 143 keys and today added no key; four catalogs equal at 780 keys, `.mo` in sync at 781 entries, extractor reports 0 missing |

- **Consistency readings (measured this round, all recomputable)**: `grep -c '^### v' CODE_WIKI.md CODE_WIKI_EN.md` -> 173 = 173;
  `importlib.metadata.version('DouyinLiveRecorder')` -> 4.3.0; `scripts/check_version.py` PASS;
  `scripts/compile_po.py --check` in sync at 781 entries; `scripts/extract_i18n_strings.py` 0 missing;
  `pytest tests/test_i18n.py -k "keyset or sync or catalogs"` -> 6 passed;
  `pytest tests/test_proto_runtime_compat.py tests/test_i18n.py` -> 43 passed.
- **Deliberately not done (honest boundary)**: no dependency added to `requirements.txt` or `pyproject.toml` (nothing required one);
  `config/config.ini` not written (it holds credentials, is ignored, and no new key was needed); `README*.md` untouched per the
  user's 09-27 decision; `docs/agent-reference/session-learnings.md` remains the only LF-only file in that directory
  (finding 7, out of scope this round).

> The path-level inventory was moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-27) — Today's changes classified by module: four release-chain fixes + findings 4/5/6 + the four-doc size pass + the AGENTS.md trim + metadata and consistency sync | section: Today's change inventory by module (added / modified / removed + file paths)).

### v4.3.0-dev (2026-09-27) — `AGENTS.md` size pass: three real duplications removed and relocated readings turned into pointers; measured conclusion is that the root file is already at its constraint-density floor

- **Motivation**: the user asked to shrink `AGENTS.md` while keeping every core instruction and key constraint.
  Measure the redundancy classes first, then choose the method.
- **What the measurement showed**: the relocatable one-off readings had already been relocated correctly.
  `BtbN 126,600,656 B / 108,761,296 B`, `johnvansickle 41,888,096 B`, `autobuild-2024-10-31`, the `latest`
  republish at 2026-09-26T13:22:38Z, the ~two-week retention of daily `autobuild-*` tags (only
  `09-13~09-26`, 15 entries) and `api.github.com` `assets[].digest` all exist **verbatim** in
  `docs/agent-reference/measured-evidence.md` under "Runtime upstream integrity artifacts", yet `AGENTS.md`
  copied them again. Those numbers in the SEV-10 item and in the "three places to change per source" item are now
  pointers to that section, with an explicit note that the root file no longer duplicates values.
- **Three genuine duplications removed** (the file's own "no second source of truth" rule): (1) key convention 14
  and the 已知坑/i18n extractor-blindspot item overlapped - merged into 14 (absorbing the four catalog filenames and
  the "reports 0 missing, falsely green" consequence) and deleted the latter; (2) the version line in "Project
  overview" restated key convention 1 wholesale - compressed to a pointer; (3) two routing bullets in "Risk control"
  re-quoted the command and the forbidden directory list owned by their detail sections - kept only the judgement
  plus the pointer (the command `pip install --ignore-installed --no-deps -r requirements.txt` and the
  `downloads/`/`logs/`/`backup_config/` prohibition are still word-for-word in "CI / workflow conventions" and
  "temp-script cleanup"). The two same-cause items about parent-process `PYTHONUTF8` and
  `reconfigure(errors="replace")` in "Gate commands" were merged into one.
- **Reading**: `AGENTS.md` 97,034 -> **95,715 B** (-1,319, -1.4%), 496 lines, pure CRLF (LF-only count 0).
- **Why only 1.4% (a conclusion for later sessions)**: the file has **224 top-level items averaging 383 B**
  (command: `python -c "import pathlib,re; t=pathlib.Path('AGENTS.md').read_text(encoding='utf-8'); top=[x for x in t.splitlines() if re.match(r'^([-*] |[0-9]+[.] )', x)]; print(len(top), sum(len(x.encode()) for x in top)//len(top))"`),
  and item by item each one is an incompressible payload of judgement + constant name + test name + error code.
  Preservation audit: of the 997 code spans in the original, only 15 no longer appear in their old form, and each was
  checked: (a) 9 were `::test_...` fragments rewritten as "file name once, then bare test names" - all **55 test
  identifiers still present**; (b) 6 were readings that live on in the wiki / measured-evidence. Loss counts for
  `test_` identifiers, CVE/PYSEC/GHSA and MIN/SEV/MID codes, and `UPPER_SNAKE` constants and environment variables
  are all **0** (only three byte readings now exist solely in measured-evidence, by design). So under the current
  architecture the volume is near its floor; going materially lower requires an architecture change (move 已知坑
  detail into per-topic sub-docs, leaving the root file as index plus hard rules), which contradicts the file's own
  opening rule that "已知坑 constraint sentences stay in the root file" and therefore **needs the user's approval**;
  not attempted in this pass.
- **Verification**: `scripts/run_gates.py --list` still parses 8 gates (the parser reads the fenced bash block of the
  "Gate commands" section, which this pass did not touch);
  `pytest tests/test_run_gates.py tests/test_regression_2026_09_22_gates.py` -> **67 passed / 1 skipped**, including
  the three source locks ("first command must be the verbatim black gate line", "the `PYTHONUTF8=1` prefix must
  parse into env", "renaming the section must return an empty list"). Line-ending form unchanged. Docs-only change,
  so step 2 of the Definition of Done (live-device verification) does not apply.

### v4.3.0-dev (2026-09-27) — Fourth release-chain hardening: `--dual` now validates both return paths after packaging and prunes stale `dist/` zips before packaging; four docs slimmed by relocating 73 historical file inventories and restoring `…`-truncated table cells

- **Motivation**: the closing review of the previous entry produced findings 1-8; the user approved the already-fixed
  1/2/3 and asked for 4/5/6 plus a documentation size pass. (4) `make_zip`'s return value was discarded with `_ =`
  in the `--dual` branch, so nothing locally checked that the two variants really differ and both exist on disk, and
  `dist/` was never cleaned, so leftovers got swept in by `path: dist/*.zip`; (5) the artifact-name example still read
  `windows-x64` (Windows actually yields `amd64`; `x64` only exists as the runtime key after `_NODE_ARCH_MAP`
  normalization); (6) "both pre-existing tests assert *only* `zip_path.is_file()`" was imprecise -
  `test_make_zip_aborts_when_archive_still_contains_logs` asserts the `SystemExit` text.
- **Changes (`build_exe.py`, three)**: (1) `_assert_dual_zips_are_two_files(lite_zip, full_zip)` - identical names
  raise `SystemExit` (`zipfile` `"w"` truncates in place without an error, and a single-call guard cannot see two
  calls landing on one file), and a missing variant raises `SystemExit` too; (2)
  `_clean_stale_release_zips()` + `_drop_stale_release_zips()` - delete only `{APP_NAME}-v*.zip`, only when a zip is
  actually being produced, and print the removed list (silent deletion is as bad as not deleting); the `--no-zip`
  path never cleans. The call must sit **before the first** zip: inside `make_zip` the second call would delete the
  first one's artifact. (3) The non-`--dual` path keeps `make_zip`'s return value and prints the real artifact name.
- **Same-family corrections**: the truncation-incident comment in `tests/test_build_exe.py` rewritten to the true
  artifact name plus the precise per-test judgement; step 4 of "Packaging and Release" claimed "smoke tests run on
  the lite version", which the MID-2254 ordering change already disproved - it now says smoke runs after **both**
  zips against the release directory that holds the runtimes, and records the pruning plus the post-hoc check; the
  same line carried a stale exception name (`ChallengePageError` was removed on 2026-09-23 under MIN-2267; only
  `IntegrityError` / `NetworkError` remain) and a `…` that cut a code span in half.
- **Regression locks (5 new cases in `tests/test_build_exe.py`, all mutation-verified)**:
  `test_dual_build_aborts_when_both_variants_land_on_one_zip`,
  `test_dual_build_aborts_when_a_variant_zip_is_missing`,
  `test_dual_build_prunes_stale_zips_before_first_zip`,
  `test_no_zip_build_keeps_existing_dist_zips` (inverse lock: no packaging means no deletion),
  `test_clean_stale_release_zips_only_touches_own_artifacts` (includes the "missing `dist/` is a no-op" case and
  idempotency). `_stub_build_steps`'s `make_zip` stub now **returns a name derived from `suffix` and really writes
  the file**: the old constant `stub.zip` would turn all three `--dual` cases falsely red once the new check landed;
  `DIST_DIR` is also redirected to `tmp_path`, otherwise the tests would delete the user's real `dist/` artifacts.
  Mutation readings: cleaner made a no-op -> 2 red; `--dual` wiring removed -> 1 red; whole post-hoc check disabled
  -> 1 red; existence check only disabled -> 1 red. Each mutation reddened exactly its own lock, and
  `build_exe.py` came back byte-identical to its backup.
- **Doc size pass (policy: relocate, never delete)**: measured first, and the redundancy the request assumed was
  mostly not there - 0 trailing-whitespace lines, 0 multi-blank runs, and only 1 README line duplicated verbatim from
  `CODE_WIKI`; all the weight is body text. What genuinely moved is 73 historical "Files involved (classified by
  module)" inventories (41 zh blocks / 32 EN blocks) into
  `docs/agent-reference/changelog-file-inventories.md` / `-en.md`, each original spot keeping its section heading plus
  a one-line "entry | section" pointer. The pass also repaired a silent information loss from the 2026-09-25
  compression: 109 (zh) / 181 (EN) table cells truncated with `…` were restored from `.workbuddy/docold` by unique
  prefix match (+18,439 B / +33,117 B; 2 ambiguous matches were deliberately skipped).
  Readings (**before this entry was written**; `README*` are byte-identical to the originals):
  `CODE_WIKI.md` 638,616 -> 552,368 B (-86,248, -13.5%), `CODE_WIKI_EN.md` 692,281 -> 649,906 B (-42,375, -6.1%),
  `README.md` 104,040 B and `README_EN.md` 123,017 B unchanged; new appendices 130,064 B / 98,458 B.
  Confirmed scope: the README changelog is user-facing release notes and is not compressed.
- **Self-proof (recomputable)**: `grep -c '^### v'` is still **170 = 170**; a line-by-line reconciliation shows every
  non-empty original line still lives either in its document or in the appendix (only the 109/181 restored table rows
  vanished in their truncated form); all 41/32 pointers resolve to an existing file **and** to a real
  "entry + section" pair inside it; 0 orphaned table headers; dangling-code-span paragraphs dropped from 26 (zh) /
  18 (EN) to 0; every relocated block ends at a heading or a 验证/Impact/Conclusion-class label, so no table header
  was separated from its body; all four documents plus both appendices are pure CRLF (LF-only count 0).
- **Doc drift fixed on the way**: the "Document Statistics and Index" section claimed **285** Markdown files with no
  command attached, which cannot be recomputed; it now carries the command plus today's reading (**100**), the review
  reports are listed at their real home `docs/worklog/` (9 files), and a `docs/agent-reference/` row plus a new
  "Reference Sub-Document Index" section were added. Nine Chinese comment lines inside EN fenced command blocks were
  translated. Known and left undone: 162 Chinese lines remain inside EN code fences (the architecture diagram and the
  directory tree labels); that is translation work, not size redundancy, and is deferred to its own pass.
- **Verification**: `scripts/run_gates.py` 8/8 rc=0 (incl. `check_annotations.py` PASS at 23.8% mean comment density,
  `compile_po.py --check` in sync at 781 entries, `check_version.py`, `check_runtime_pins.py` fully pinned);
  its built-in full-suite fallback **3240 passed with an empty warnings summary** (up from 3235 = the 5 cases added
  here); `pytest --cov=src` -> 3240 passed / 14 skipped, total coverage **83.91%**, and `scripts/check_coverage.py`
  **PASSED: all 42 modules meet their threshold** (`src/proto/douyin_pb2.py` explicitly exempt);
  `basedpyright` (no path) 0 errors / 0 warnings / 0 notes; `mypy` (no path) Success; black and isort report both
  touched files unchanged; `python -m pytest tests/test_build_exe.py` alone -> **105 passed** (was 100).
- **Not measured / handed back**: (1) `python build_exe.py --smoke --dual` was **not** run locally (full PyInstaller
  build plus ~300MB upstream download), so the real "prune, then both zips land in `dist/`" path is still confirmed
  by CI's `Verify dist contains both lite & full zips` on its first run; (2) this is a docs-only change with no
  recording-chain / source-selection / ffmpeg-argument / platform-parsing touch point, so step 2 of the Definition of
  Done does not apply; (3) restored cells reflect the `.workbuddy/docold` snapshot (pre-2026-09-25), so any wording
  changed before that snapshot comes back in its snapshot form; (4) to reject the relocation, delete this entry's two
  artifacts: the two appendix files plus the 73 pointer lines.

### v4.3.0-dev (2026-09-27) — Third release-chain fault: `make_zip` truncated the artifact name via `Path.with_suffix(".zip")`, so lite was overwritten in place by full

- **Symptom**: this `Build & Release` run **passed** the pin verification and
  `Build executables + smoke test`, then reddened on the next step
  `Verify dist contains both lite & full zips`: `Found 0 lite zip(s) and 0 full zip(s)`,
  `Error: Expected both *-lite.zip and *-full.zip in dist/, but missing one or both.`, while
  `Full listing:` shows exactly one file, `dist/DouyinLiveRecorder-v4.3.zip` at 160,298,993 B.
  So the artifact **did exist** — what had vanished from both variant names were the `-lite`/`-full`
  segments together with `-<os>-<arch>`. Same family as the two earlier reds
  (`Pattern 'dist/*-lite.zip' does not match any files`), different cause, and one step further along.
- **Root cause**: `build_exe.make_zip()` built `zip_base = DIST_DIR / f"{APP_NAME}-v{version}-{os}-{arch}{suffix}"`
  and then `zip_path = zip_base.with_suffix(".zip")`. `Path.with_suffix` splits the extension at the
  **last dot**, and the version itself contains dots: measured locally on the real per-platform names —
  `Path('DouyinLiveRecorder-v4.3.0-windows-amd64-lite').suffix == '.0-windows-amd64-lite'`, so
  `with_suffix('.zip')` yields `DouyinLiveRecorder-v4.3.zip` (`-full` resolves to the **same** name, and so
  does `linux-x86_64`). Both `make_zip` calls of `--dual` therefore wrote one and the same path: the second
  (full) truncated and rewrote the first (lite) through zipfile's `"w"` mode, leaving full's content on disk
  under a name carrying neither variant nor platform.
- **Why it stayed invisible**: neither pre-existing `make_zip` test says anything about the **name** (one
  only asserts `zip_path.is_file()`, the other only the `SystemExit` text) — name drift is completely
  invisible to "does a file exist". The only name-aware judgement in the repo is the CI `dist/*-lite.zip`
  glob, so only a real `--dual` run could redden. The non-`--dual` path (`ci.yml` build-verify uses
  `--no-zip`) never exposed the missing platform segment either.
- **Fix (three parts, all in `build_exe.py`)**: (1) `.zip` is now concatenated inside the same f-string,
  keeping naming a single definition point, with a comment recording why `with_suffix` is banned;
  (2) a new structural invariant — the composed `zip_path.parent` must still be `DIST_DIR`, otherwise
  `SystemExit` (when `version`/`suffix` contain a path separator the f-string produces a **sub-path** and
  the artifact silently lands outside `dist/`; on Windows pathlib treats `\` as a separator too);
  (3) `--dual` and `--no-zip` are now mutually exclusive and fail fast — the `--dual` branch never reads
  `no_zip`, so `--dual --no-zip` used to **silently ignore** the flag the user explicitly typed and emit
  both large zips anyway (a contradictory combination must either error out or honour it, not half-run).
- **Regression locks (`tests/test_build_exe.py`, four functions / five cases, all mutation-verified)**:
  `test_make_zip_name_keeps_dotted_version_and_variant_suffix` (structural regex: full `v4.3.0` +
  `<os>-<arch>` + `-lite`/`-full` + `.zip`; the real Windows name looks like
  `DouyinLiveRecorder-v4.3.0-windows-amd64-lite.zip`),
  `test_dual_suffixes_do_not_collide_on_one_zip` (two `make_zip` calls must yield two distinct files),
  `test_make_zip_refuses_name_containing_path_separator` (runs **both** argument positions — `version` and
  `suffix` — with `'/'` rather than `os.sep` so the refusal branch really executes on both platforms),
  `test_dual_and_no_zip_are_mutually_exclusive` (asserts `order == []`, locking "the judgement precedes
  every build step").
  Mutation readings: reverting the implementation to `with_suffix(".zip")` reddened the first two while the
  pre-existing `make_zip` tests stayed green (disproving the old assertion standard); forcing the two new
  guards to `if False:` reddened the last two — the guard-(2) one via `FileNotFoundError`, which proves its
  assertions are actually reached.
- **Verification**: `pytest tests/test_build_exe.py` **100 passed**; `basedpyright build_exe.py tests/test_build_exe.py`
  0 errors / 0 warnings / 0 notes; `mypy` (no path arguments) Success over 158 files;
  `black --check` / `isort --check-only` report both files unchanged; `check_annotations.py` passes;
  line-ending form of every touched file unchanged (`build_exe.py` and `AGENTS.md` pure CRLF,
  `tests/test_build_exe.py` pure LF).
- **Not measured / handed back**: (1) `python build_exe.py --smoke --dual` was **not** run locally (it needs a
  full PyInstaller build plus ~300 MB of upstream downloads), so "lite + full both present in dist/" can only
  be confirmed by the first CI run of `Verify dist contains both lite & full zips`; (2) the failed Release
  record is reclaimed by `release-guard` (`needs.build.result != 'success'`) and the tag is kept, so a
  re-run republishes; (3) any historical asset named `DouyinLiveRecorder-v<major>.<minor>.zip` is a product
  of this defect — its lite half was never actually distributed, and a re-run is what yields correctly
  named per-platform variants.

### v4.3.0-dev (2026-09-27) — Release-chain fix: Linux ffmpeg pins now point at an immutable month-end release tag, plus a `release-guard` job that rewinds the empty Release left behind by a failed build

- **Background**: a tag-triggered `Build & Release` run died in the Linux build job's ffmpeg download step with
  `[build][FATAL] _ffmpeg_temp.tar.xz SHA256 不匹配（期望 87de0900…，实际 0cfb2146…），已终止构建`, and the
  very next step (`softprops/action-gh-release`) then reported
  `⚠️ Pattern 'dist/*-lite.zip' does not match any files` (`fail_on_unmatched_files: true`). The second message
  is a **downstream symptom** of "dist/ has no artefacts", not a separate fault — turning
  `fail_on_unmatched_files` off would erase the only visible signal.
- **Root cause**: both Linux slots of `_FFMPEG_DOWNLOAD_URLS` pointed at BtbN's
  `releases/download/latest/...`. `latest` is a **rolling alias**: the same asset name is re-uploaded over and
  over, so its digest keeps changing — tag `latest` was republished at `2026-09-26T13:22:38Z`, which invalidated
  the pin value `87de0900…` taken earlier the same day; the arm64 pin `30774c8f…` was stale too (now `f2fe35e9…`).
- **Chosen route (per the user: "switch to an immutable month-end tag")**: both slots now pin the **month-end**
  autobuild tag `autobuild-2026-08-31-13-27` (assets
  `ffmpeg-n9.0.1-11-ge47273f4d9-linux{64,arm64}-gpl-9.0.tar.xz`), with pin values taken from
  `api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/<tag>` → `assets[].digest`
  (linux64 `182c1b50…`, linuxarm64 `e2dd447c…`). Why month-end specifically: the repo holds only **38 releases**;
  daily `autobuild-*` tags survive only about two weeks (only 09-13…09-26, 15 of them, were left), so pinning a
  daily tag is planting a guaranteed 404, while month-end tags reach back to `autobuild-2024-10-31` — the only
  combination where both URL and digest are immutable. Cost: the bundled ffmpeg lags `latest` (n9.0.2) and now
  sits at n9.0.1-11-ge47273f4d9; upgrading means editing the tag **and** the pin by hand, which is exactly the
  SEV-10 manual gate — deliberately not replaced by auto-fetching the current hash.
- **Second item, the guardrail**: `build-release.yml` gains a `release-guard` job
  (`needs: [prepare, build]`, `if: always() && release path && needs.build.result != 'success'`) that runs
  `gh release delete` on the empty/partial Release pre-created by `release-create` (tag is **kept**) and emits a
  `::warning::`. Why: `release-create` deliberately pre-allocates the Release before build to avoid three build
  jobs racing to create it, but when a build fails the finalizing `release` job is skipped by `needs: build`, so
  an empty Release stays in the repo with zero downloadable assets.
- **Files touched**: `build_exe.py` (two URLs + two pin cells + three comment/maintenance corrections);
  `tests/test_build_exe.py` (new `test_linux_ffmpeg_urls_pin_an_immutable_release_tag`: forbids
  `/releases/download/latest/`, forbids the `n9.0-latest-` asset-name form, requires one shared tag across both
  arches); `.github/workflows/build-release.yml` (new `release-guard` job only — matrix/cache/build/upload logic
  untouched); `AGENTS.md` (SEV-10 entry gains the "month-end tag" rule and its regression lock; a new
  empty-Release guardrail bullet under CI/workflow conventions; volume readings refreshed);
  `docs/agent-reference/measured-evidence.md` (2026-09-27 re-measurement table).
- **Measured (2026-09-27)**: `releases/latest` → linux64 150,999,836 B / `0cfb2146…`, linuxarm64 127,395,868 B /
  `f2fe35e9…` (neither equals the old pins); `releases?per_page=100` → 38 releases total; month-end tag assets →
  linux64 126,600,656 B / `182c1b50…`, linuxarm64 108,761,296 B / `e2dd447c…` (a `checksums.sha256` asset is
  also published, usable as a second cross-check); gyan.dev Windows `.sha256` still `60f46726…` (no drift);
  nodejs.org's first `lts` entry still `v24.21.0` (no drift). A prefix fetch confirmed the month-end asset is a
  valid xz (magic `fd377a585a00`) whose top-level directory is
  `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0/`.
- **Verification**: `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` → **115 passed**; full
  `pytest` → 3229 passed / 14 skipped with an empty warnings summary (the single failure,
  `test_web_config.py::TestFormatUrlLine::test_normal_line`, is the sandbox failing to resolve
  `live.douyin.com`; re-run alone it is **1 passed**, unrelated to this change); `mypy` (no args) → Success over
  158 files; `basedpyright tests/test_build_exe.py` → 0 errors / 0 warnings / 0 notes; `black --check` and
  `isort --check-only` unchanged; `check_annotations.py` passes; `check_runtime_pins.py --strict` still rc=0;
  `yaml.safe_load` on the workflow parses with jobs in the order prepare / release-create / build /
  release-guard / release. Line endings unchanged (`build_exe.py`, `AGENTS.md`, `CODE_WIKI*.md`,
  `measured-evidence.md` stay pure CRLF; the test file and the workflow stay pure LF).
- **Not yet verified / handed back**: ① `github.com` direct links are reset on this box (prefix fetch → http=000,
  full fetch died at 5.4 MB), so "download from the new URL and compare against the pin" can only be confirmed by
  the first GitHub runner run; ② `bin/ffmpeg` / `bin/ffprobe` inside the month-end archive were not directly
  confirmed by this prefix (5.4 MB only covered `doc/`) — we rely on the 09-26 measurement for the same asset
  family; if they are missing, `_extract_linux_ffmpeg_binaries()` raises `SystemExit` rather than degrading to a
  silent empty package; ③ Linux full-package size changes with the new tag (126,600,656 B / 108,761,296 B) and
  must be re-checked against CI artefacts via `scripts/report_bundle_size.py` before touching any platform
  threshold.

### v4.3.0-dev (2026-09-27) — Second release-chain fault fixed: eight slots of `_PINNED_RUNTIME_SHA256` had been rewritten to the official-signature marker; hashes re-pinned from the official channels

- **Symptom**: the pasted log only carried the last two lines `Run softprops/action-gh-release@v3` /
  `⚠️ Pattern 'dist/*-lite.zip' does not match any files`. It is read the same way as the entry above
  (`fail_on_unmatched_files: true` is the only visible signal of a missing artefact and must stay on).
  Re-computing locally exposed a **second fault in the current working tree that fires even earlier**:
  eight slot values in `build_exe.py`'s `_PINNED_RUNTIME_SHA256` had been replaced wholesale with
  `OFFICIAL_SIGNATURE_PIN` (file mtime 07:58, i.e. after the 01:45 wrap-up of the previous entry), which
  moves the break point of the release chain from the build job forward to the prepare job.
- **Root cause**: the signature mode only applies to slots whose upstream really publishes no hash *and*
  which are registered in `_RUNTIME_GPG_SIGNATURES` with a signature URL plus the full 40-hex primary
  fingerprint — in this repo that is only the four macOS ffmpeg/ffprobe slots. The five node slots
  (nodejs.org `SHASUMS256.txt`), `windows-x64/ffmpeg` (gyan.dev `.sha256`) and the two Linux ffmpeg slots
  (BtbN `assets[].digest`) all have officially published values; once turned into the marker,
  `_is_signature_satisfied` returns False because the slot is unregistered → all three disjuncts of
  `_slot_is_gated` are False. Two consequences: `scripts/check_runtime_pins.py --strict` returned **rc=1**
  (the prepare job's fail-closed step goes red) and
  `tests/test_build_exe.py::test_table_never_declares_signature_mode_without_satisfaction` **failed** —
  that lock exists precisely to catch this rewrite.
- **Action**: all eight values re-derived from the **official channels** named in the AGENTS.md /
  `build_exe.py` maintenance notes, never from locally downloaded self-computed digests:
  `curl -sS https://nodejs.org/dist/v24.21.0/SHASUMS256.txt` (win-x64 `.zip`, linux/macos `.tar.gz` — the
  five asset names `_download_nodejs` actually fetches);
  `curl -sSL https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256` → `60f46726…47ba`
  (no drift);
  `curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27`
  → linux64 `182c1b50…` / linuxarm64 `e2dd447c…` (byte-identical to what measured-evidence.md records; a
  month-end tag's digest is immutable); plus confirmation that the first `lts` entry of `dist/index.json`
  is still `v24.21.0` (Krypton). The macOS ffmpeg/ffprobe slots keep the signature mode untouched.
- **Scope**: `build_exe.py` only (8 pin values + one `[2026-09-27 restore]` note above the table + a
  per-node-line source asset name). Logic, the URL table, the predicates, tests and workflows untouched.
- **Verification**: before the change `check_runtime_pins.py --strict` was **rc=1** and
  `test_table_never_declares_signature_mode_without_satisfaction` FAILED (8 offenders named per slot);
  afterwards both `--strict` and the structural mode return **rc=0**, `pytest tests/test_build_exe.py`
  **95 passed**, `python scripts/run_gates.py` **8/8 green rc=0**, full `pytest` **3230 passed /
  14 skipped** with an empty warnings summary, `basedpyright build_exe.py` 0 errors / 0 warnings / 0 notes,
  and `black --check` / `isort --check-only` / `py_compile` pass. End-of-line shape unchanged (build_exe.py
  pure CRLF: 1686 CRLF / 0 bare LF).
- **Not measured / handed back**: ① "download in full and compare against the pinned value" still only
  runs on a GitHub runner first — `github.com` direct links are reset on this machine, only
  `api.github.com`, `nodejs.org` and `gyan.dev` are reachable; ② during this session `build-release.yml`
  was modified **concurrently** at 08:14 (a new `Verify dist contains both lite & full zips` step and
  `| tee build_exe.log` on the build command). That file is neither changed nor reviewed by this entry;
  under `pipefail` the `tee` does not swallow `SystemExit`, but its author should confirm before releasing.

### v4.3.0-dev (2026-09-26) — Release-chain integrity gate gains an "official signature" mode and Linux ffmpeg moves to BtbN: `build-release.yml` prepare goes from rc=1 to rc=0 without loosening SEV-10's fail-closed semantics

- **Background**: the prepare job failed at `Verify runtime binary SHA256 pins (fail-closed)` with
  `Error: Process completed with exit code 1.`, and the log body is literally the output of
  `scripts/check_runtime_pins.py --strict`: two in-matrix slots (`linux-x64/ffmpeg`, `macos-arm64/ffmpeg`) still
  carry the placeholder marker. Located precisely at `.github/workflows/build-release.yml:141-149`; rc=1 comes from
  the `--strict` branch of the checker. This is not a defect — the gate stopped the release exactly as designed
  (both the `build_exe.py` pin-table comment and the `AGENTS.md` SEV-10 entry say: if upstream publishes no hash,
  the release chain stays red).
- **Why deleting the gate was not the fix**: the pin table does not live in the workflow (source of truth is
  `build_exe._PINNED_RUNTIME_SHA256`; the YAML only passes values through via `DLR_RUNTIME_SHA256`). And
  `require_pinned_hashes()` is auto-true under `GITHUB_ACTIONS=true`, so removing the prepare step would only move
  the same failure into the three build jobs (each after a full pip install, still aborting before any download) —
  zero artefacts either way.
- **Chosen route (per the user's "grade integrity criteria by what each upstream actually publishes")**: class ①
  "release-time runtime binaries" gains a second satisfaction mode **behind the single predicate**
  `build_exe._slot_is_gated()` — the **official signature mode**: table value = `OFFICIAL_SIGNATURE_PIN`, and the
  slot must actually be registered in `_RUNTIME_GPG_SIGNATURES` with a 40-hex fingerprint. The marker alone never
  grants passage (same anti-"easier-to-fill marker = free pass" wall as the 4th class `SOURCE_BUILD_PROVENANCE`).
  macOS's two slots take this mode (evermeet publishes `/sig`, no hash); the Linux slots moved to BtbN's n9.0-series
  assets, pinning the `assets[].digest` SHA256 published by `api.github.com`, so no MD5 downgrade mode was needed.
- **SEV-2221 fixed on the way**: `_download_file()`'s pre-download gate only accepted `_is_pinned()`, while the
  signature check sat after the download inside the "hash already matched" branch — so a placeholder-valued macOS
  slot never reached the download and the P-2 verification had **never executed** on the real build path. The gate
  now accepts both modes, and a signature-mode slot **must** pass verification after download (BADSIG / signer not
  in the pinned key's primary-or-subkey set / missing gpg or unreachable signature on the release path all
  `SystemExit`); the observed SHA256 is logged as the audit trail for the rolling alias.
- **Scope**: `build_exe.py` (new constant + predicates, `_download_file` dispatch, `_unpinned_action` naming the
  exact reason a signature declaration is unsatisfied, the two Linux rows of `_FFMPEG_DOWNLOAD_URLS`, four pin-table
  cells, and Linux extraction pulled out into the layout-agnostic `_extract_linux_ffmpeg_binaries()`);
  `scripts/check_runtime_pins.py` (per-mode `[NOTE]` announcement, judgement still delegated);
  `tests/test_build_exe.py` (+12 cases: signature-mode truth table, case-insensitive marker, fingerprint shape gate,
  table/registration stay-in-sync invariant, the SEV-2221 reachability lock, abort-on-bad-signature and
  abort-when-gpg-missing, unregistered marker must not download, both archive layouts plus abort-on-missing-binary;
  `_ALLOWED_HOSTS` gains `github.com` and drops `johnvansickle.com`; `_FakeResponse` gains `headers` and drains per
  read); `tests/test_check_runtime_pins.py` (`_fake_module` exposes the new symbols + 2 routing cases);
  `.github/workflows/build-release.yml` — **comments only** (4 spots: the `DLR_RUNTIME_SHA256` legend, the prepare
  step explanation, the source-host list, and the gnupg step noting verification is now the sole criterion);
  matrix / caching / build / upload / release logic untouched. Plus `AGENTS.md` and
  `docs/agent-reference/measured-evidence.md` (every retrieval command and reading from this round).
- **Measured (2026-09-26)**: `evermeet.ca/ffmpeg/getrelease/zip/sig` → 200 / `application/pgp-signature` / 594 B
  binary OpenPGP packet, landing on `e.deolaha.ca:4242/pub/ffmpeg/ffmpeg-9.0.2.zip.sig`; keyserver lookup of
  `0x476C4B611A660874` → 200, UID `static FFmpeg binaries (signing key)`, server-echoed fingerprint equal to the
  pinned value (**a second, independent channel** — this closes R-2's "fingerprint never corroborated");
  `johnvansickle ...amd64-static.tar.xz.md5` → 200 with the same value as 2026-09-22, `.sha256` → 404; BtbN
  `linux64-gpl-9.0` = 150,998,508 B / `linuxarm64-gpl-9.0` = 127,417,700 B, and a ranged prefix fetch + `tar -tJf`
  confirms the binaries sit at `bin/ffmpeg` and `bin/ffprobe`.
- **Verification**: `scripts/run_gates.py` 8/8 green; full `pytest` **3220 passed, empty warnings summary**;
  `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` → 105 passed; `check_runtime_pins.py --strict`
  went rc=1 → **rc=0**, announcing the two macOS slots as "signature mode" rather than "pinned"; all five mutations
  reddened (gate omits the new mode / SEV-2221 reverted / marker alone satisfies / `bin/` layout hardcoded /
  missing binary no longer aborts).
- **Not yet verified, handed back**: ① the direct `github.com/.../releases/download/...` link resets on this box, so
  "download in full and compare against the pin" can only be proven by the first GitHub runner run; ② evermeet
  verification on the real build path executes for the first time in the macOS CI job (the keyserver probe shows
  `--recv-keys` will resolve, but no local gpg run happened); ③ the Linux full zip grows sharply with the source
  switch, and `report_bundle_size.py` could not be run locally (no Linux, blocked direct link) — re-check the size
  gate from CI artefacts before adjusting any threshold. A rolling alias pins *who signed*, not *which version*: a
  new evermeet build flows through without reddening the gate. That is this mode's inherent boundary; the logged
  observed SHA256 is what makes it auditable afterwards.

### v4.3.0-dev (2026-09-26) — CI typecheck gate: install a pinned pytest and fix the `[return]` false positive in `tests/test_proto_runtime_compat.py`, removing the "green locally, red in CI" coverage drift (CI / test-only change, zero runtime impact)

- **Background**: the CI `typecheck` job reported `tests/test_proto_runtime_compat.py:33: error: Missing return statement  [return]` (checked 159 files), while a local `mypy` run was fully green on 158 files and could not reproduce it at all.
- **Root cause**: that job installs only `requirements.txt + mypy` — **no pytest** — so `import pytest` resolves to `Any`, the `NoReturn` annotation of `pytest.fail()` is lost, and mypy concludes that `_declared_protobuf_specifier() -> str` may fall off the end. This is an environment difference, not a code defect; the same cause also meant that every `pytest.*` in `tests/` (fixtures / `MonkeyPatch` / `raises`) was previously **unchecked** — the gate was effectively half-blind. Local reproduction: `mypy --no-site-packages` (hides installed packages and reproduces the exact error; the 5 extra `no-any-return` reports in that mode are over-stripping noise).
- **Nature of change**: CI workflow + one test helper + `AGENTS.md` only. `src/`, `main.py`, `gui.py`, `web.py`, `web/app.js`, `requirements.txt` / `pyproject.toml` untouched; no dependency added or removed (pytest is installed only inside the typecheck job, never into the runtime list).

**Files touched (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-26) — CI typecheck gate: install a pinned pytest and fix the `[return]` false positive in `tests/test_proto_runtime_compat.py`, removing the "green locally, red in CI" coverage drift (CI / test-only change, zero runtime impact) | section: Files touched (grouped by module)).

**Verification**: `mypy` (no args) and `mypy --platform linux` both succeed on 158 files (local pytest is 9.1.1, the same version CI now pins); under `mypy --no-site-packages` the original `[return]` is gone and only the 5 stripping-noise reports remain; `basedpyright tests/test_proto_runtime_compat.py` reports 0 errors / 0 warnings / 0 notes; `black --check` unchanged; `pytest tests/test_proto_runtime_compat.py` → 4 passed; `yaml.safe_load` parses `ci.yml` with the expected outputs / steps; line endings of the edited files are unchanged (`ci.yml` pure LF; `AGENTS.md` and the test file pure CRLF).

**Leftover observation**: that CI run reported `checked 159 source files` while the local count under `[tool.mypy].files` is 158 `.py` files — one unaccounted file (likely an extra file on the commit of that run), unrelated to this fix.

### v4.3.0-dev (2026-09-26) — Repo metadata & doc sync: aligned the dependency tables / structure trees / egg-info / ignore lists and cleaned up leftover records of the deleted `weverse_auth` module (metadata & docs only, zero runtime code change)

- **Background**: a full-repo read-through cross-checking the four shared-source families (version / dependencies / structure trees / ignore lists) surfaced several stale spots: the `CODE_WIKI*.md` dependency tables still listed only 16 entries with `starlette` lower bound `>=0.49.1`; the structure trees still listed `src/weverse_auth.py` and `tests/test_weverse_auth.py`, both deleted on 2026-09-23; `DouyinLiveRecorder.egg-info/requires.txt` was missing `h2`/`socksio` (added 2026-09-23); `AGENTS.md` still said "21 runtime dependencies".
- **Nature of change**: docs / metadata / ignore lists only, plus a regenerated `egg-info`. `src/`, `main.py`, `gui.py`, `web.py` and `web/app.js` untouched; the runtime dependency set is unchanged (23 entries on each side, identical package-name sets).

**Files touched (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-26) — Repo metadata & doc sync: aligned the dependency tables / structure trees / egg-info / ignore lists and cleaned up leftover records of the deleted `weverse_auth` module (metadata & docs only, zero runtime code change) | section: Files touched (grouped by module)).

**Verification**: `scripts/check_version.py` rc=0 (`pyproject.toml` is the single source of truth; all four consumers read it dynamically); `scripts/check_runtime_pins.py` rc=0; `pytest tests/test_regression_2026_09_22_gates.py tests/test_build_exe.py` all green (including the "requirements.txt and pyproject package-name sets are equal" lock); `pytest tests/test_i18n.py tests/test_i18n_migration.py tests/test_i18n_tr.py tests/test_frontend_*.py` 56 passed; `node --test tests/frontend/*.mjs` green.

**Handed back to the user (needs a decision)**: `config/config.ini` currently has `禁用SSL证书验证的平台(逗号分隔) = 虎牙直播,B站直播,抖音直播`, while the code's enforced set `main.SSL_DISABLE_REQUIRED_PLATFORMS` contains only `虎牙直播` / `B站直播` and the README default is the same two. The extra `抖音直播` entry is a legacy exemption that disables certificate verification for Douyin streams; whether to remove it is left to the user — this pass did not touch a security-relevant toggle on its own.

### Earlier entries (archived)

164 day-by-day development entries from 2026-05-17 to 2026-09-24 were moved verbatim to [code-wiki-history-en.md](docs/changelog/code-wiki-history-en.md) on 2026-09-28; that volume also restores the short `…` / mid-sentence tails left by the previous trimming pass against the `.workbuddy/docold` baseline (exact rule in its header).
Reason: the changelog alone took 72.9% of this file's characters (472,669 of 648,535). The root document now keeps only the current release window plus this pointer, which is what makes the rest of the document readable.
