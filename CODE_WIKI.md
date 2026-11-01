# DouyinLiveRecorder 项目架构文档

简体中文  |  [**English**](CODE_WIKI_EN.md)

## 目录

- [文档统计与索引](#文档统计与索引)
- [项目概述](#项目概述)
  - [项目基本信息](#项目基本信息)
  - [功能特性](#功能特性)
  - [已支持平台](#已支持平台)
  - [画质代码对照](#画质代码对照)
  - [技术栈](#技术栈)
- [系统架构](#系统架构)
- [目录结构](#目录结构)
- [核心模块详解](#核心模块详解)
- [关键类与函数](#关键类与函数)
- [依赖关系](#依赖关系)
- [配置文件说明](#配置文件说明)
- [运行方式](#运行方式)
- [打包与发布](#打包与发布)
- [设计模式](#设计模式)
- [常见问题排查](#常见问题排查)
- [贡献指南](#贡献指南)
- [改动总览（按模块分类，2026-10-17）](#改动总览按模块分类2026-10-17)
- [改动总览（按模块分类，2026-10-29）](#改动总览按模块分类2026-10-29)
- [更新日志](#更新日志)

## 文档统计与索引

> 本节是文档地图，不是事实源。计数按下方命令实时复算（2026-10-31 实测 **220** 个 Markdown 文件；已排除 `.git/`、`.venv/`、`node_modules/`、`__pycache__/`、`.mypy_cache/`、`.pytest_cache/`）。
> `python -c "import pathlib; sk={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache'}; p=[x for x in pathlib.Path('.').rglob('*.md') if not (set(x.parts) & sk)]; print(len(p))"`

### 统计概览

人工维护的事实源为根目录 **5** 份（`AGENTS.md` + 中英成对的 `README` / `CODE_WIKI`）、`docs/agent-reference/` 的 **6** 份参考子文档、`docs/changelog/` 的 **4** 份归档卷；`docs/worklog/` 是历史审查产物，`.workbuddy/` / `.qoder/` / `.codebuddy/` 是本地工具数据，均不作为改动来源。

### 根文档索引

| 文件 | 角色 | 主要内容 |
| --- | --- | --- |
| `AGENTS.md` | 编码代理约定 | 版本号事实源、代码风格、项目结构、依赖/测试/构建命令、关键约定 |
| `README.md` | 用户/开发者说明 | 功能、平台、快速开始、配置、使用、Docker、开发指南、FAQ、更新日志 |
| `CODE_WIKI.md` | 项目架构文档（本文档） | 模块详解、依赖关系、配置、打包发布、设计模式、排查、贡献指南、更新日志索引 |
| `README_EN.md` | 用户/开发者说明（英文） | `README.md` 的英文对应版 |
| `CODE_WIKI_EN.md` | 项目架构文档（英文） | 本文档的英文对应版，条目一一对应 |

### 参考子文档索引（`docs/agent-reference/`）

| 文件 | 内容 |
| --- | --- |
| `project-structure.md` | 完整目录树 |
| `measured-evidence.md` | 一次性实测读数 |
| `session-learnings.md` | 会话经验双轨记录 |
| `lock-classification.md` | 锁的可重入性分类口径 |
| `changelog-file-inventories.md` / `-en.md` | 更新日志文件清单块归档（中英） |

### 变更日志归档索引（`docs/changelog/`）

| 文件 | 内容 |
| --- | --- |
| `code-wiki-history-zh.md` / `-en.md` | CODE_WIKI 更新日志历史条目（含 2026-10-31 迁入的当前发布周期条目） |
| `release-notes-history-zh.md` / `-en.md` | README 发布说明历史条目（含 2026-10-31 迁入的 v4.5.0 / v4.4.0 / v4.3.0） |

> 滚动规则：根文档只保留当前发布周期的概要/索引，详细条目逐字迁入本目录；归档卷只增不改。

## 项目概述

### 项目基本信息

- **项目名称**: DouyinLiveRecorder (抖音直播录制器)
- **描述**: 支持抖音、TikTok、YouTube、快手等 60+ 平台的直播录制工具，支持循环录制、多人录制、消息推送
- **版本**: 4.7.0（唯一事实源 `pyproject.toml`）
- **Python**: >=3.14
- **作者 / 开源协议**: y123ao6 / MIT
- **入口**: `douyin-recorder` → `main:main`；`douyin-recorder-gui` → `gui:main`；`douyin-recorder-web` → `web:main`
- **项目地址**: [GitHub](https://github.com/y123ao6/DouyinLiveRecorder)

### 功能特性

- ✅ 支持 60+ 个直播平台（抖音、TikTok、YouTube、快手、虎牙、斗鱼、B站、小红书等）
- ✅ 循环值守直播状态，开播自动录制，断播自动停止
- ✅ 多种视频格式输出：TS、MKV、FLV、MP4、MP3、M4A
- ✅ 命令行 + GUI + Web 管理面板三模式运行
- ✅ 多平台消息推送：钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus
- ✅ Docker 容器化部署
- ✅ 国际化支持（简体中文 / English (US) / English (UK) / 繁體中文）
- ✅ 灵活配置：画质选择、分段录制、自定义保存路径等
- ✅ 实际画质回采与降级告警（支持抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC）
- ✅ Web 安全：Token 认证、路径穿越防护、敏感配置脱敏

### 已支持平台

归纳自 `README.md`，当前已列出 **51** 个平台（README 对外标称 60+，含持续添加中的平台）：

**国内站点（37 个）**：抖音 | 快手 | 虎牙 | 斗鱼 | YY | B站 | 小红书 | bigo | blued | 网易CC | 千度热播 | 猫耳FM | Look直播 | TwitCasting | 百度 | 微博 | 酷狗 | 花椒 | 流星 | Acfun | 畅聊 | 映客 | 音播 | 知乎 | 嗨秀 | VV星球 | 17Live | 浪Live | 飘飘 | 六间房 | 乐嗨 | 花猫 | 淘宝 | 京东 | 咪咕 | 连接 | 来秀

**海外站点（14 个）**：TikTok | SOOP(原AfreecaTV) | PandaTV | WinkTV | TTingLive(原Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | YouTube | Faceit | Picarto

> 各平台流解析函数位于 `src/stream.py`、数据获取函数位于 `src/spider.py`；新增平台见「贡献指南 → 添加新平台支持」。

### 画质代码对照

录制画质以代码表示，对应中文名与说明如下（配置项 `原画|超清|高清|标清|流畅` 即映射到该表）：

| 画质代码 | 中文名 | 说明 |
| --- | --- | --- |
| OD | 原画 | Original Definition，最高画质 |
| BD | 蓝光 | Blu-ray，超高清 |
| UHD | 超清 | Ultra HD |
| HD | 高清 | High Definition |
| SD | 标清 | Standard Definition |
| LD | 流畅 | Low Definition，最低画质 |

支持实际画质回采与降级告警的平台：抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC。当平台实际下发画质低于设置画质时，自动告警并标记。

### 技术栈

| 技术 | 用途 |
| --- | --- |
| Python 3.14+ | 核心编程语言 |
| asyncio + httpx | 异步网络请求与异步装饰器 |
| FFmpeg | 视频录制与转码 |
| Node.js + exejs/PyExecJS | 运行 JavaScript 签名算法（exejs 优先，PyExecJS 回退） |
| Loguru | 结构化日志 |
| PySide6 (Qt6) | GUI 图形界面与系统托盘（窗口层为 `src/gui_qt/`；GUI 与 Web 两入口托盘均走 QSystemTrayIcon（2026-10-20 起）；tkinter/ttk 实现已于 2026-10-31 完全移除） |
| Starlette + uvicorn | Web 管理面板后端 |
| HTML + CSS + JavaScript | Web 管理面板前端 |
| Docker | 容器化部署 |
| gettext (msgfmt) | 国际化翻译编译 |
| mypy | 静态类型检查（`disallow_untyped_defs = true`；CI 门禁，本机 + linux + win32 三跑） |
| basedpyright | 本地严格度补充门禁（CI 不跑） |
| websockets | 弹幕 WebSocket 传输层（`src/ws_client.py`，各平台弹幕共用） |
| protobuf | 抖音弹幕协议解码（`src/proto/douyin_pb2`，protoc 生成模块） |
| brotli | B站弹幕解压（protover=3 需 brotli 解压） |

## 系统架构

### 整体架构图

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

### 工作流程

1. **配置解析阶段**
   - 读取 `config/config.ini` 主配置
   - 读取 `config/URL_config.ini` 直播间列表
   - 初始化 Node.js 环境和 FFmpeg 路径
2. **直播检测阶段**
   - 使用异步任务并发检测多个直播间
   - 各平台独立的 API 调用与签名算法
   - 动态调整并发数以避免限流
3. **流地址获取阶段**
   - 调用各平台的直播流 API
   - 根据配置选择不同画质（原画/超清/高清/标清/流畅）
   - 回采平台实际下发的画质（`actual_quality`）与可用档位（`available_qualities`）
   - 验证流地址可用性
4. **录制执行阶段**
   - 启动 FFmpeg 子进程
   - 实时监控录制状态
   - 记录实际画质，画质降级时输出告警日志
   - 支持分段录制
   - 支持转码为 MP4
5. **状态通知阶段**
   - 开播/关播事件触发
   - 调用配置的消息推送渠道
   - 记录日志

## 目录结构

```
DouyinLiveRecorder/
├── config/                              # 配置文件目录
│   ├── config.ini                      # 主配置文件
│   └── URL_config.ini                  # 直播间地址列表
├── assets/                              # 应用图标（app.ico）
├── src/                                 # 核心源码包
│   ├── __init__.py                     # 包初始化 + Node.js 环境配置 + 弹幕注册表/工厂（get_danmaku_class / get_danmaku_collector）
│   ├── spider.py                       # 直播数据爬虫（60+ 平台）
│   ├── stream.py                       # 直播流地址解析（含画质回采）
│   ├── room.py                         # 直播间信息解析
│   ├── utils.py                        # 工具函数库
│   ├── logger.py                       # Loguru 日志配置
│   ├── proxy.py                        # 代理检测
│   ├── node_install.py                # Node.js 自动安装/初始化
│   ├── ffmpeg_master_download.py       # FFmpeg master 构建下载器（按平台/架构拉取 + 校验，含挑战页识别与 TOFU）
│   ├── ffmpeg_linux_download.py        # Linux 运行期 ffmpeg 直下（月末不可变标签 + 双趟拷贝，缺件时 dest 零改动）
│   ├── ttwid.py                        # 抖音访客 ttwid 获取
│   ├── web_api.py                      # Web 管理面板 Starlette 应用
│   ├── web_models.py                   # Web 请求体校验层（纯标准库 dataclass + parse，替代 pydantic）
│   ├── web_config.py                   # Web 面板配置读写（不依赖 Web 框架）
│   ├── web_tray.py                     # Web 模式系统托盘（Windows 最小化到托盘）
│   ├── ui_theme.py                     # GUI 主题偏好层（主题 id 白名单 + 系统明暗探测 + config.ini 持久化）
│   ├── ui_scale.py                     # GUI 缩放档位层（可选档位 + 自动档 + config.ini 持久化）
│   ├── ui_i18n.py                      # GUI 静态标签 i18n 接线（T() 标记 + 语言切换整窗回填 + Qt setText）
│   ├── ui_fonts.py                     # GUI 自选字体（偏好读写 + config/fonts/ 副本 + 文件名清洗）
│   ├── ui_icons.py                     # 应用图标解析/校验（GUI 托盘、Web favicon、打包产物共用）
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
│   ├── notify.py                        # 推送/脚本/成功失败计数/并发调节（抽离自 main.py）
│   ├── scheduler.py                     # 并发调度中枢（自适应容量 + 按平台熔断 + 可运行时调容信号量）
│   ├── recorder_status.py               # 录制状态快照与展示（抽离自 main.py）
│   ├── config_io.py                     # 配置读写/安全数值转换/备份（抽离自 main.py）
│   ├── config_bool.py                   # 布尔配置解析（是/否 与 true/false/1/0/yes/no 等价，零依赖模块）
│   ├── config_read.py                   # 容错配置读取（同节重复键折叠为最后一次取值 + 点名告警，2026-10-17 新增）
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
├── gui.py                               # GUI 图形界面入口（薄入口：父进程标记 + PySide6 崩溃兜底 + 委托 src/gui_qt/）
├── web.py                               # Web 管理面板入口
├── i18n.py                              # 国际化实现（print 翻译包装）
├── msg_push.py                          # 消息推送模块
├── index.html                           # 独立 M3U8/FLV 播放器页面
├── StopRecording.vbs                    # Windows 停止录制脚本
├── build_exe.py                         # PyInstaller 打包脚本（CLI/GUI/Web 三入口）
├── DouyinLiveRecorder.spec              # 由 build_exe.py 自动生成（.gitignore 已忽略）
├── requirements.txt                     # Python 依赖列表
├── uv.lock                              # uv 依赖锁文件（随仓库分发；镜像/CI 走 pip + requirements.txt，不消费）
├── pyproject.toml                      # Python 项目配置（版本号/工具配置/覆盖率门禁单一事实源）
├── scripts/                             # 工程辅助脚本
│   ├── run_gates.py                    # 统一门禁编排（解析 AGENTS.md 命令块）
│   ├── check_version.py                # 版本号一致性校验
│   ├── check_workflow_constants.py     # CI/workflow 版本常量一致性
│   ├── check_runtime_pins.py           # 运行时钉定结构校验
│   ├── check_annotations.py            # 注释规范与 AST 等价性校验
│   ├── check_coverage.py               # 逐模块覆盖率门禁
│   ├── check_skill_agents_consistency.py
│   ├── compile_po.py                   # .po → .mo 编译与 --check 同步校验
│   ├── sync_metadata.py                # egg-info 等派生元数据重建
│   ├── extract_i18n_strings.py         # i18n 待翻译串提取
│   ├── smoke_test.py / smoke_web.json / _ci_web_smoke.sh
│   └── sync_version.py
├── Dockerfile                          # Docker 构建文件（多阶段）
├── docker-compose.yaml                 # Docker Compose（recorder/web/gui 三服务）
├── .dockerignore                       # Docker 构建上下文排除文件
├── .gitignore                          # Git 排除文件
├── .gitattributes                      # 行尾与二进制属性钉定
├── .pre-commit-config.yaml             # 提交期钩子配置
├── pyrightconfig.json                  # pyright/Pylance 与 mypy/basedpyright 同源配置
├── docs/                               # 参考文档、审查报告与更新日志归档
├── README.md                           # 项目说明（中文版，中英成对）
├── tests/                               # pytest 用例（asyncio_mode=auto；覆盖率 source=src）
│   ├── conftest.py                     # fixtures 与公共替身
│   ├── test_*.py                       # 单元/回归/平台离线/前端包装用例
│   └── frontend/*.mjs                  # Node 内置 node:test 用例
├── .github/                             # GitHub Actions 工作流目录
│   ├── ISSUE_TEMPLATE/                 # Issue 模板（Bug 报告 / 功能请求）
│   ├── PULL_REQUEST_TEMPLATE.md         # PR 模板
│   ├── actions/
│   │   └── retry/                      # 复合动作：网络安装命令线性退避重试包装（ci.yml / build-release.yml 共用）
│   └── workflows/
│       ├── ci.yml                      # CI 静态验证（setup/static/typecheck/test/concurrency/integration/build-verify/summary）
│       ├── build-release.yml           # 四平台构建（含 linux aarch64；lite + full 双产物）+ 自动发布 Release
│       └── issue-translator.yml        # Issue 自动翻译工作流（中英互译）
├── .coveragerc-concurrency             # 并发测试专用覆盖率配置（CI concurrency-test job 使用，不设全局阈值）
├── CODE_WIKI.md                        # 本架构文档（中文版）
├── CODE_WIKI_EN.md                     # 本架构文档（英文版）
├── README_EN.md                        # 项目说明（英文版）
└── ...
```

## 核心模块详解

### 1. 主程序模块 (`main.py`)

**职责**: 整个录制器的指挥中心，负责流程调度

**核心功能**:

- 配置文件读取与解析
- 直播间 URL 列表解析
- 并发控制与任务调度
- FFmpeg 进程管理
- 错误重试与动态调优
- 消息推送触发
- 退出信号处理

**关键状态变量**:

```python
recording: set              # 正在录制的直播间集合
monitoring: int             # 正在监控的直播间数
running_list: list          # 正在运行的 URL 列表
error_count: int            # 当前错误计数
error_window: list          # 错误时间窗口（用于动态调优）
url_tuples_list: list       # 解析后的 URL 配置列表 [(quality, url, anchor_name)...]
recording_time_list: dict   # 录制时间与画质记录 {name: [start_time, quality_zh, actual_quality_zh]}
```

**主流程函数**:

- `main()` - 入口函数
- `read_config()` - 读取配置
- `check_url_config()` - 检查 URL 配置
- `start_recording()` - 启动录制（解析 actual_quality，降级时输出告警）
- `stop_recording()` - 停止录制
- `check_live_status()` - 检测直播状态
- `display_info()` - 终端状态展示（兼容新旧 recording_time_list 格式）
- `get_status()` - 返回录制状态 dict（含 actual_quality 字段，供 Web API 使用）
- `select_source_url()` - 在 m3u8/FLV 源间选择，HLS 源校验失败时回退 FLV（`delay_default=120s` 轮询）；新增 `proxy_addr` 参数透传给三处校验调用，避免 TikTok 等需代理平台直连校验误判不可达；计算「末位候选」（FLV 无 record_url 备选时、record_url 恒为）并以 `last_resort` 传给校验器——稳定拒绝也仅告警放行、交由 ffmpeg 实际拉流定夺；**HLS 采集排除列表**（`main.hls_collection_exclude_platforms`，配置键「HLS采集排除平台(逗号分隔)」）：命中平台无视「是否启用HLS采集」配置、恒按 FLV 采集（等效于仅对该平台关闭 HLS 采集，HLS 候选整组剔除、不作回退；仅剩 HLS 源无回退时告警并放弃本轮，恢复指引指向移出排除列表），列表外平台行为不变
- `_validate_stream_url()` - 流地址校验：content-type 判定补充 `mpegurl`；HEAD 被拒时对 `.m3u8` 源（**含 404**）补 `Range: bytes=0-0` GET 探测——抖音 CDN 的 m3u8 常对 HEAD 返回 4xx，此前会被误判不可达而总回退 FLV；新增 `verify` 参数沿用全局 SSL 开关（与异步校验一致）；所有失败路径记录 warning（URL + 异常类型/状态码/content-type），不再静默吞异常；GET 复核（`_confirm_get_ok`）收到 401/403 先原样重试一次（间隔 0.8s）再定罪——斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针（HEAD→GET）偶发 403（实测同 URL 片刻后重试即 200、ffmpeg 单次 GET 正常），重试可区分「偶发限流」与「稳定拒绝」，历史虎牙假绿场景重试仍 403 依旧被正确否决

**重构（2026-08-16）**：下列职责已抽离至 `src/` 子模块，经 `main.py` re-export 保持 `main.<name>` 命名空间兼容（`web.py`/`gui.py`/`web_api.py`/测试零改动）：

- FFmpeg 进程管理 → `src/ffmpeg_proc.py`（进程注册/注销/终止/清理）
- 视频后处理（分段/转码/字幕）→ `src/video_postprocess.py`
- 流地址选择/校验/画质码/抖音限速 → `src/stream_select.py`（`select_source_url`/`_validate_stream_url`/`get_quality_code`/`_douyin_rate_limit` 等）
- 推送/脚本/成功失败计数/并发调节 → `src/notify.py`（`push_message`/`record_error`/`record_success`/`adjust_max_request`/`clear_record_info` 等）
- 录制状态快照/展示 → `src/recorder_status.py`（`get_status`/`display_info`）
- 配置读写/安全数值转换/备份 → `src/config_io.py`（`update_file`/`delete_line`/`read_config_value`/`_safe_int`/`_safe_float`/`backup_file`/`backup_file_start`）

深度耦合 main 全局的模块一律用运行时 `import main` 惰性访问全局，避免启动期传参膨胀调用点；`main.py` 顶部加 `__main__` 守卫规避 `python main.py` 时子模块 `import main` 触发整文件二次执行。

**房间录制线程闭包整改（2026-08-16）**：新增直播间时为每路 URL 起一个 daemon 线程运行 `start_record`。原实现用「默认参数绑定循环变量」（`def _room_thread_target(_key=thread_key, _args=args)`）规避闭包晚期绑定陷阱，且 `_args: tuple[Any, ...]` 使用了项目 basedpyright 全局禁用的显式 `Any`。整改后：

- `_args` 类型具体化为 `tuple[tuple[str, str, str], int]`（`url_tuple` 为 `tuple[str, str, str]`，与 `start_record(url_data, count_variable)` 签名一致）；
- 通过 `threading.Thread(target=..., args=(thread_key, args))` 在创建线程时显式绑定当前循环值，移除默认参数 hack，语义更清晰、更易维护；
- 线程退出仍 `finally: create_var.pop(_key, None)` 清理，防止 `create_var` 字典长期无界增长。

**弹幕录制集成（2026-08-16 接线定稿）**：`start_record` 各平台分支收集 `record_danmaku_args`（每轮重置 `None`）→ 6 处 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` 全部接线 → `get_danmaku_collector(platform, args, base_filename, segment_seconds)` 创建采集器。采集器在 `while process.poll() is None` 循环外 `stop()`（`DanmakuCollector.stop()` 有 `_stop_called` 防重入，幂等）。分段文件名约定：ffmpeg 视频分段模板统一 `_%03d`（FLV 已从 `_%02d` 对齐；音频仍 `_%02d` 但无弹幕），SRT 分片 `{seg:03d}`（`_000.srt` 对 `_000.ts`）；`check_subprocess` 同时剥离 `_%02d`/`_%03d` 占位符。抖音空 cookie 时 `DouyinDanmaku.start()` 协程内 `await get_ttwid()` 动态获取（采集线程独立事件循环，可直接 await；进程级缓存）。`弹幕分片时长(秒)` 走 `_safe_float(..., 1800.0)`。弹幕平台注册表见 `src/__init__.py` 的 `get_danmaku_class`（斗鱼直播/B站直播/虎牙直播/抖音直播/TwitchTV）。

**房间日志关联字段绑定（2026-09-20）**：`start_record` 作为房间线程主体，在**线程入口**即调 `set_room_context(f"序号{count_variable}")` 绑定日志关联字段（否则早于 `record_name` 的退出标志 / 注释退出 / 解析失败 / 熔断退避日志无法归属房间），并在每轮解析出主播名、`record_name = f"序号{count_variable} {anchor_name}"` 之后刷新为完整房间名。字段如何进入日志行、哪些线程带/不带该标记，见「6. 日志模块」与 `AGENTS.md`「已知坑」。

### 2. 爬虫模块 (`src/spider.py`)

**职责**: 负责从各大直播平台获取直播间数据

**支持平台**:

国内：抖音、快手、虎牙、斗鱼、YY、B站、小红书、bigo、blued、网易CC、千度热播、猫耳FM、Look直播、TwitCasting、百度、微博、酷狗、花椒、流星、Acfun、畅聊、映客、音播、知乎、嗨秀、VV星球、17Live、浪Live、飘飘、六间房、乐嗨、花猫、淘宝、京东、咪咕、连接、来秀

海外：TikTok、SOOP(原AfreecaTV)、PandaTV、WinkTV、TTingLive(原Flextv)、PopkonTV、TwitchTV、LiveMe、ShowRoom、CHZZK、Shopee、YouTube、Faceit、Picarto

**关键函数**:

- `get_douyin_web_stream_data()` - 获取抖音 Web 端直播数据（`web/enter` API 优先，失败静默重试 1 次，再回退 HTML 抓取）
- `get_douyin_app_stream_data()` - 获取抖音 App 端直播数据（备用方案，内置 URL 分发逻辑，见下方「抖音 URL 分发」）
- `get_tiktok_stream_data()` - 获取 TikTok 直播数据
- `get_youtube_stream_data()` - 获取 YouTube 直播数据
- `get_bilibili_stream_data()` - 获取 B站直播流数据（返回 dict，含 url/current_qn/accept_qn）
- `get_play_url_list()` - 获取 M3U8 播放列表中的清晰度选项
- `get_params()` - 从 URL 提取参数

**抖音 URL 分发逻辑**（`get_douyin_app_stream_data`，2026-08-01 优化后）：

| URL 形态 | 处理路径 |
| --- | --- |
| `live.douyin.com/<房间号或抖音号>` | 直调 `get_douyin_web_stream_data`（`web/enter` API 接受抖音号，无需重定向解析） |
| `www.douyin.com/user/<sec_uid>`（网页端主页） | 跳过必然失败的 `get_sec_user_id` 探测，走 `resolve_from_homepage()`：`get_unique_id()` 解析抖音号 → 拼接 `live.douyin.com/<抖音号>` → 直调网页端 |
| `v.douyin.com/<短链>`（App 短链，可能指向直播间或主页） | 先 `get_sec_user_id()` 跟随重定向；抛 `UnsupportedUrlError` 时回退 `resolve_from_homepage()` |

- `resolve_from_homepage()` 直调 `get_douyin_web_stream_data`（网页端 API 优先、内置 HTML 兜底），不再绕经旧版 HTML 优先抓取路径（约 1MB 页面），并**显式透传 proxy_addr / cookies**（旧实现未透传，导致代理与 Cookie 配置在主页路径静默失效）
- `web/enter` API 调用封装为 `_try_web_api()` + `for attempt in range(2)`：首次失败（如瞬时风控 `status_code=10002`）→ `await asyncio.sleep(0.5)` 缓冲 → 静默重试；重试成功直接返回、跳过 HTML 兜底；两次都失败才记 WARNING 并回退 HTML（取 HEVC 原画的 HTML 抓取是各网页端路径通用行为，保持不变）

**实现特点**:

- 使用异步 HTTP 客户端 (`httpx`)
- 各平台独立的签名算法
- 代理支持
- Cookie 支持
- 错误重试机制
- B站 spider 返回 dict 结构（含 `current_qn`/`accept_qn` 元信息），供 stream 模块回采实际画质

### 3. 直播流解析模块 (`src/stream.py`)

**职责**: 解析直播流地址，支持多种画质选择，回采平台实际下发的画质

**画质映射**:

```python
QUALITY_MAPPING = {"OD": 0, "BD": 1, "UHD": 2, "HD": 3, "SD": 4, "LD": 5}
QUALITY_MAPPING_BIT = {
    'OD': 99999, 'BD': 4000, 'UHD': 2000, 'HD': 1000, 'SD': 800, 'LD': 600
}
QUALITY_LEVEL = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}  # 等级值越大画质越低
QUALITY_CODE_TO_ZH = {"OD": "原画", "BD": "蓝光", "UHD": "超清", "HD": "高清", "SD": "标清", "LD": "流畅"}
NETEASE_QUALITY_MAP = {"blueray": "OD", "ultra": "UHD", "high": "HD", "standard": "SD"}
```

**画质工具函数**:

- `bitrate_to_quality(bitrate)` - 根据码率反查画质代码（0/未知回退 OD）
- `code_to_zh(code)` - 画质代码转中文名
- `is_downgrade(requested, actual)` - 判定是否降级（actual 等级值 > requested）
- `get_quality_index()` - 解析画质参数，返回索引
- `_pad_list()` - 填充列表到指定最小长度（部分平台已改用显式截断替代）

**各平台流地址解析函数**:

| 函数 | 平台 | 实际画质回采方式 |
| --- | --- | --- |
| `get_douyin_stream_url()` | 抖音 | 从 `flv_pull_url` / `hls_pull_url_map` 的 key 提取画质标签 |
| `get_tiktok_stream_url()` | TikTok | 从 `vbitrate` 字段通过 `bitrate_to_quality()` 反查 |
| `get_kuaishou_stream_url()` | 快手 | 从 `flv_url_list` 的 `bitrate` 字段反查 |
| `get_huya_stream_url()` | 虎牙 | 从 `exsphd` ratio 值映射，处理降级选择 |
| `get_douyu_stream_url()` | 斗鱼 | 从平台下发的 `rate` 字段反向映射 |
| `get_bilibili_stream_url()` | B站 | 从 spider 返回的 `current_qn` 反向映射为画质代码 |
| `get_netease_stream_url()` | 网易CC | 从画质名（blueray/ultra/high）通过 `NETEASE_QUALITY_MAP` 映射 |

**返回值结构**（各平台统一）:

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

**实现特点**:

- 按带宽排序的清晰度选择
- 自动降级策略（首选画质不可用时自动降级）
- FLV 与 M3U8 双协议支持
- 状态码验证
- 显式截断替代 `_pad_list` 静默填充，避免越界
- 画质降级检测（`is_downgrade`），供 main.py 告警使用
- 斗鱼 FLV→m3u8 同 token HLS 候选：`get_douyu_stream_url` 在 `rtmp_live` 以 `.flv` 结尾时，将路径 `.flv` 改 `.m3u8`（查询串原样保留）附为 `m3u8_url`——斗鱼 wsAuth token 对 FLV/HLS 通用（实测 hw CDN 200 + `application/vnd.apple.mpegurl`，两级 m3u8），HLS 采集开启时经 `select_source_url` 优先校验选用、不可达自动回退 FLV；HLS 逐段拉取不维持长连接，缓解游客态 FLV 长连接约 70 秒被 CDN 掐断导致的反复分段

### 4. 直播间信息模块 (`src/room.py`)

**职责**: 解析直播间 URL，提取房间 ID、主播信息、抖音号等

**关键函数**:

- `get_sec_user_id()` - 获取房间 ID 和用户 sec_user_id
- `get_unique_id()` - 获取抖音号（含 30 分钟 TTL 的 sec_uid→抖音号进程级缓存，对齐 `ttwid.py` 的 `threading.Lock` 跨线程/跨 asyncio 循环去重模式）
- `is_user_homepage_url()` - 判断 URL 是否为「网页端主播主页」形态（`douyin.com/user/<sec_uid>`，v.douyin.com 短链不属于此类）；用于零请求快速路径——sec_user_id 直接在路径中，无需发请求跟随重定向
- `extract_sec_user_id()` - 从 URL 中显式正则提取 sec_user_id
- `get_live_room_id()` - 获取直播间 web ID
- `get_xbogus()` - 生成 X-Bogus 签名

**异常处理**:

- `UnsupportedUrlError` - 不支持的 URL 格式异常

**关键常量与接口**:

- `DESKTOP_UA` - 桌面 Chrome UA。`iesdouyin.com/web/api/v2/user/info/` 等接口用旧移动端 UA 会被静默限流（HTTP 200 + 空 body），必须使用桌面 UA
- 主页解析走 `https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid=<sec_uid>` JSON 接口（取 `unique_id`，空则退 `short_id`）——旧 `iesdouyin.com/share/user/<sec_uid>` 页面已是 JS 反爬壳页，HTML 正则不可靠

### 5. 工具模块 (`src/utils.py`)

**职责**: 提供通用工具函数

**主要工具**:

| 工具函数 | 功能描述 |
| --- | --- |
| `Color` 类 | 终端彩色输出常量 |
| `trace_error_decorator()` | 错误追踪装饰器 |
| `check_md5()` | 计算文件 MD5 |
| `dict_to_cookie_str()` | cookie 字典转字符串 |
| `read_config_value()` | 读取配置文件值 |
| `update_config()` | 更新配置文件 |
| `remove_emojis()` | 移除文本中的表情符号 |
| `remove_duplicate_lines()` | 移除文件重复行 |
| `handle_proxy_addr()` | 处理代理地址格式 |
| `generate_random_string()` | 生成随机字符串 |

### 6. 日志模块 (`src/logger.py`)

**职责**: 基于 Loguru 配置结构化日志

**日志输出**:

- **控制台**: 彩色日志输出（`custom_format`，不含房间列）
- **`logs/streamget.log`**: DEBUG 级别（排除 INFO），行结构 `时间 | 级别 | 房间 | 模块:函数:行号 - 消息`
- **`logs/PlayURL.log`**: INFO 级别（仅直播流地址），行结构 `时间 | 房间 | 消息`
- **`logs/gui.log`**: 仅 GUI 父进程写（独占句柄），不带房间列——GUI 进程不执行录制，该列恒为空

**房间关联字段 `extra[room]`（2026-09-20 新增）**:

- 房间线程的全部日志行带一个稳定关联列，用于从多房间交织落盘的日志里切出单个房间的链路（切法与边界见 `AGENTS.md`「已知坑」同名条目）
- 实现：`ROOM_FIELD` + `set_room_context()` / `get_room_context()` 读写一个 `ContextVar`，由 `logger.configure(extra={ROOM_FIELD: ""}, patcher=_room_patcher)` 注册的全局 patcher 在**调用线程**内写进 `record["extra"]`（故 `enqueue=True` 不串味）；调用点显式 `bind(room=...)` 优先于线程级兜底
- 房间线程在 `main.py::start_record` 入口绑 `序号N`、解析出主播名后升级为完整 `record_name`；`set_room_context("")` 为解绑
- **`extra` 默认值不可删**：缺它时未绑定房间的日志格式化 `KeyError: 'room'`，loguru 不抛异常而是每条日志向 stderr 吐 `Logging error in Loguru Handler` 并丢弃该行；回归锁 `tests/test_logger_room_context.py`
- 只加关联标识：日志级别、INFO/其余两档 `filter`、`rotation`、`retention` 均未改动

**日志文件开关**:

- 通过 `config/config.ini` 的 `是否启用日志文件(是/否)` 控制
- 默认启用，保持向后兼容
- logger.py 在初始化时直接读取配置（不依赖 main.py 执行顺序）

**日志轮转**: 300 KB 自动轮转，保留 1 份

### 7. 消息推送模块 (`msg_push.py`)

**职责**: 支持多种消息推送渠道

**支持渠道**:

| 渠道 | 函数名 | 说明 |
| --- | --- | --- |
| 钉钉 | `dingtalk()` | 群机器人推送 |
| 微信 | `xizhi()` | Server酱 / WeChat |
| Telegram | `tg_bot()` | Bot 消息 |
| 邮件 | `send_email()` | SMTP 协议 |
| Bark | `bark()` | iOS 通知 |
| NTFY | `ntfy()` | 开源推送服务 |
| PushPlus | `pushplus()` | 微信推送平台 |

### 8. 国际化模块 (`i18n.py`)

**职责**: 基于 gettext 的多语言支持系统，自动翻译项目源码的 print 输出。

**实现机制**:

- `translated_print` 包装 `builtins.print`，自动翻译调用者来自项目根（`src/` 包及 `main.py` 等顶层脚本）的输出；`main.py` 导入时无条件安装 `builtins.print = translated_print`（任何语言下均安装——zh_CN/zh_TW 把英文常量串译为中文，en_US/en_GB 把中文串译为英文，未知串恒等返回）
- 支持源码运行和 PyInstaller 打包两种路径检测（`_internal/i18n` vs `i18n/`）
- **多格式目录加载（2026-08 起）**：`i18n.py` 按语言依次探测 gettext `.mo` → `<lang>.json` → `<lang>.yaml`，三种格式均为「原文 → 译文」扁平映射，行为一致；`PyYAML` 为运行时依赖（缺失时仅损失 YAML 格式支持）。`_load_yaml_catalog()` 捕获 `yaml.YAMLError`（非 OSError/ValueError 子类）——损坏的 yaml 目录返回 None 降级到下一格式，而非让 `set_language` 抛异常（Web 语言切换接口 500）
- **语言热切换**：`set_language(lang)` 归一化（`normalize_language` 别名表：zh_cn/zh-CN/en/en-US/zh-Hant/zh_CN.UTF-8 等写法均可）后热替换 `_tr` 翻译函数，无需重启进程。三个切换入口：Web 面板（`GET/PUT /api/language`，写回 config + 热切换 + 前端 `data-i18n` 文案重绘；`PUT` 在配置缺 `language` 键时降级为节末追加补建，不再恒 500）、GUI（侧边栏「语言 Language」菜单）、CLI 主循环（每轮按 config 重同步）
- 默认语言：简体中文（zh_CN）；受支持语言：zh_CN / en_US / en_GB / zh_TW

**翻译文件**:

| 文件 | 说明 | 条目数 |
| --- | --- | --- |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` | 简体中文翻译源文件（gettext，可编辑） | 496 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | 编译后的二进制翻译文件（gettext 运行时唯一读取，随仓库/镜像分发） | 496 |
| `i18n/en_US.json` | 英语（美国）目录（JSON 格式，英文源恒等 + 中文源译英） | 496 |
| `i18n/en_GB.json` | 英语（英国）目录（JSON 格式，英式拼写：minimise/unrecognised 等） | 496 |
| `i18n/zh_TW.yaml` | 繁体中文目录（YAML 格式，简→繁字符转换 + 台湾用语适配） | 496 |

**维护流程**: 修改 `.po` 后必须执行 `python scripts/compile_po.py` 重新编译并一并提交 `.mo`，否则翻译改动不会生效；`python scripts/compile_po.py --check`（CI `static` job）在两者不同步时拦截——其内部 `write_mo()` 为**纯内存产出不落盘**，`--check` 模式零副作用、真实比对磁盘上已提交的 `.mo`，仅非 check 模式才写盘。CI 路径过滤器（paths-filter）将 `i18n/**` 视为触发条件：纯翻译变更同样会运行该门禁。**四种语言的目录键集合必须一致**（`tests/test_i18n.py::test_catalogs_share_same_keyset` 强制校验）——新增 msgid 时需同步更新四个目录。新增待翻译串的提取与比对用 `python scripts/extract_i18n_strings.py`（AST 扫描运行时代码 print 常量串 + logger f-string 模板底稿并与四语目录比对；f-string 模板归一化约定：格式/转换符丢弃、表达式内双引号转单引号；纯占位符模板（如 `{color}{text}`）与 gettext 头部空 msgid 已过滤，不产生噪声）。

**翻译覆盖范围**（2026-08-27 全量补全后，覆盖运行时全部常量串与 logger 模板底稿）:

- `src/spider.py` — 各平台直播数据获取/登录/风控消息（含 B站 buvid 认证链路）
- `main.py` — 主程序通用消息、录制链、画质降级、主播名同步、磁盘空间
- `gui.py` — GUI 界面消息（控件文本、进程管理、托盘、退出确认）
- `src/scheduler.py` — 并发模式切换与容量调整播报
- `src/stream_select.py` — 流地址校验全套消息（探针退避、GET 复核、末位放行）
- `src/collector.py` / `src/danmaku_monitor.py` — 弹幕采集与监控
- `src/async_http.py` / `src/sync_http.py` / `src/cookie_cache.py` — HTTP 客户端与 cookie 缓存
- `msg_push.py` — 七渠道推送失败分支（微信/钉钉/TG/Bark/ntfy/PushPlus/邮件）
- `src/ffmpeg_install.py` / `src/node_install.py` — ffmpeg/Node.js 自动安装
- `src/config_io.py` / `src/utils.py` — 配置读写、备份、磁盘空间
- `src/notify.py` — 自定义脚本执行错误
- `web.py` / `src/web_tray.py` — Web 面板启动与托盘
- `src/room.py` / `src/recorder_status.py` / `src/ttwid.py` / `src/ffmpeg_proc.py` / `src/platforms/bilibili.py` / `src/platforms/douyin.py` / `build_exe.py` — 其余运行时消息

> 注：运行时真正参与翻译查找的是 `print()` 输出的常量英文串；`logger.*` 输出与 f-string 插值后的文本不经过查找，目录中相关条目仅作为后续日志接入 i18n 时的现成翻译底稿保留。

### 9. GUI 模块 (`gui.py` + `src/gui_qt/`)

**职责**: 提供 PySide6/Qt6 图形界面。`gui.py` 仅保留为薄入口（`DLR_GUI_PARENT` 父进程标记、`main()` 延迟委托 `src.gui_qt.app.main()`、窗口化运行崩溃兜底）；tkinter 实现已于 2026-10-31 完全移除。

**窗口层** (`src/gui_qt/`):

- `app.py` 装配 QApplication 与事件循环；`main_window.py` 主窗与侧边栏导航；`theme.py` 设计令牌（25 键 × 3 主题）与 QSS；`widgets.py` Card / Toast / DataTable / TerminalText。
- `pages/` 五页：dashboard（控制台）、quality（画质监控）、config（URL 配置）、runlog（运行日志）、danmaku（弹幕监控）。
- `recorder.py` / `danmaku_monitor.py` 控制器；`tray.py` 系统托盘；`settings_dialog.py` 设置对话框；`shared.py` 共享状态。
- 线程模型：Qt Signal/Slot + QTimer；控制器层无 Qt 布局代码，`QT_QPA_PLATFORM=offscreen` 可离屏单测。
- 画质监控：消费录制子进程日志中的 `actual_quality` 与降级告警，统计录制中 / 正常 / 降级计数，30 秒无更新自动清理。

### 10. 异步 HTTP 客户端 (`src/async_http.py`)

**职责**: 封装 httpx，提供统一的异步 HTTP 接口

**功能**:

- 代理支持
- 超时设置
- 自动重试
- 状态码检查
- HTTP/2 支持
- **连接池复用**: 按 (代理, verify, http2) 维度复用 AsyncClient，发挥 keepalive 连接池作用
- **事件循环检测**: 缓存记录每个 client 创建时的事件循环引用，检测到 `asyncio.run()` 导致循环变更时自动重建客户端，避免 `'NoneType' object has no attribute 'send'` 错误
- **模块级锁随事件循环重建**（2026-08-12 修复）: 保护 `_client_cache` 读写的 `_client_lock` 原是模块级单例 `asyncio.Lock()`，在首个 room 的 `asyncio.run()` 循环里惰性绑定后，后续 room 各自 `asyncio.run()` 起新循环再次 `await` 会触发 `RuntimeError: ... is bound to a different event loop`；该异常被 `async_req` 吞掉后返回空串，被 `spider.py` 误判成「风控空响应」并级联触发 HTML 兜底失败。现 `_get_client_lock()` 改为缓存 `(lock, loop)` 二元组，当前循环变更时自动重建锁，与 `_client_cache` 的「client + loop」机制一致，从源头消除跨循环锁错误
- **异常日志带类型**（2026-08-12 收口）: `async_req`、`_close_all_clients` 内所有 `except Exception as e: logger.debug(e)` 改为带 `type(e).__name__`（必要时含 URL），消除 Windows 下异常 `str()` 为空时打出空白日志、无法定位的问题
- **SSL 验证**: 由全局配置 `src/http_config.py` 统一控制，默认启用
- **跨循环旧客户端不再调度关闭**（2026-09-04 修复）: 淘汰他循环创建的旧 AsyncClient 时一律**不创建** `aclose()` 协程（旧循环运行中/已停止/已关闭同样对待），释放引用交由 GC 兜底。旧实现 `run_coroutine_threadsafe` 只调度不等待，旧循环处于 `asyncio.run` 收尾窗口（已停未关）时回调永不执行，GC 报 "coroutine ... aclose was never awaited" 且数量随机波动（1~2 条 flaky，经 unraisableexception 逸出）；「is_running 门控 + 等待 future」实测仍无法根治（收尾阶段任务可能已创建却永不步进 `Task was destroyed but it is pending`，future 永不完成还会把收尾竞态放大成秒级阻塞）；在当前循环直接 await 则会操作绑定旧循环的 transport。回归锁：`tests/test_async_http_lock.py::test_cross_loop_running_old_loop_skips_close` / `test_cross_loop_stopped_old_loop_skips_close`
- **连接池清理**: 进程退出时通过 atexit / 信号处理器释放所有复用的 AsyncClient
- **`get_response_status()` m3u8 容错**（2026-08-05 增强）: HEAD 校验失败时，若 URL 以 `.m3u8` 结尾则补一次 `Range: bytes=0-0` GET 轻量探测（**含 404 在内的所有非 2xx 均触发探测**，返回 200/206 即判可达）；非 m3u8 源（FLV/record_url）行为不变。异常日志带 URL + `type(e).__name__`（如 `ConnectTimeout` / `TimeoutError`），避免 Windows 下 `socket.timeout` 的 `str()` 为空时只输出空白消息；探测失败记录 `status_code` / `content-type` 便于排障

**被以下模块导入**:

- `src/spider.py` - `async_req()`
- `src/stream.py` - `get_response_status()`

### 11. HTTP 客户端配置 (`src/http_config.py`)

**职责**: 提供 HTTP 客户端共享运行时配置

**功能**:

- SSL 证书验证全局开关（`ssl_verify`），默认启用（True，安全优先）；已整合进「是否启用https录制」——开启=https 拉流 + 禁用证书验证，关闭=http 拉流 + 默认严格校验（由 main.py 每轮热同步）
- 提供 `set_ssl_verify()` / `set_https_recording()` 函数，由主配置启动时及主循环每轮设置
- 平台级 SSL 覆盖（`ssl_verify_platform_overrides`）：兼容保留，整合后不改变实际行为
- 异步 / 同步 HTTP 客户端在发起请求时读取此配置

### 12. 同步 HTTP 客户端 (`src/sync_http.py`)

**职责**: 封装 requests 和 urllib，提供同步 HTTP 接口

**功能**:

- 代理支持
- 超时设置
- Cookie 支持
- 重定向跟踪
- **SSL 验证**: 由全局配置 `src/http_config.py` 统一控制，并可经 `ssl_verify` 参数做**单次覆盖**（见下）
- **Session 生命周期管理（2026-09-02；2026-10-20 清理轮更新）**: thread-local `requests.Session` 经模块级 `WeakSet` 弱引用登记（线程销毁后条目自动回收、不阻止 GC）；`atexit` 注册 `close_all_sessions()` 在进程退出时统一优雅关闭全部存活连接池（80+ 房间长跑场景）。原 `close_session()` 已删除——全仓零调用方，进程退出统一收口由 `close_all_sessions()` 承担，下次请求时 `_session()` 会按需重建
- **Opener 构造形态（F-12 落地后，2026-09-24 校准本小节）**: 仅 `_opener_secure`（禁用代理 + 保留证书验证）在模块级预构建；不校验证书的 `SSLContext` 与 opener 一律**按需惰性构造**（`_get_insecure_context()` / `_get_insecure_opener()`）——2026-09-12 审查 6.7 指出「import 期即存在不校验上下文」等于给全进程开静默降级面，故禁止改回常驻
- **`ssl_verify` 单次覆盖（F-12）**: `sync_req(..., ssl_verify=None/True/False)` 由 `_resolve_ssl_verify()` 裁决（`None` = 跟随 `http_config.ssl_verify` 全局开关，显式传值以本次调用为准），且该次裁决必须**同时透传 urllib 与 requests(代理) 两条路径**，凭据类调用点可显式强制校验而不被全局降级拖下水
- **线程级 Session 公开出口（MIN-08）**: `session()` 供「必须拿状态码 / 响应头、无法走 `sync_req`（其失败契约是一律返回空串）」的调用点复用同一份连接池；打桩目标仍是 `_session`（测试约定）
- **响应体上限（SEV-2226 收尾，2026-09-23）**: 无代理 urllib 路径两道上限缺一不可——`_read_capped()` 限制压缩/原始响应体读入（`_MAX_RESPONSE_BYTES` 8 MiB）、`_gunzip_capped()` 分块解压并限制产出（`_MAX_DECOMPRESSED_BYTES` 32 MiB），超限抛 `ValueError` 由既有失败分支记脱敏日志并返回空串；**代理分支的 `response.text` 由 requests 自行解码 gzip，仍不受该上限保护**（已知残留缺口，见源码注释）
- **现状（SEV-2226 取证，2026-09-23）**: 本模块**当前无任何生产 importer**（`src/spider.py` 走 `from .async_http import async_req` 的 httpx 异步面；原调用方 `src/weverse_auth.py` 已于 2026-09-23 删除），去留待维护者决定；本体仍承载 F-12 不变量与 `tests/test_sync_http.py` 对该不变量的回归锁

### 13. Web 管理面板 (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`)

**职责**: 提供 Web 界面远程管理录制器，包括仪表盘、直播间管理、配置编辑、日志查看

**架构**:

- `web.py` - 入口：录制引擎跑守护线程；默认主线程跑 uvicorn，Windows 下启用 Qt 托盘时主线程交给 `QApplication`、uvicorn 改跑守护线程；托盘 `start()` 返回 `False` 时静默回退主线程形态
- `src/web_api.py` - Starlette 应用：认证（Token）、REST API 路由、SSE 推送、静态资源挂载
- `src/web_config.py` - 配置读写（不依赖 Web 框架，便于单测）
- `web/` - 前端静态资源（单页应用）

**后台运行模式** (`web_show_console = false`):

- `_enter_background_mode()` 在启动录制引擎前调用
- Windows 下通过 `ctypes` 调用 `GetConsoleWindow()` + `ShowWindow(hwnd, SW_HIDE)` 隐藏控制台窗口
- stdout/stderr 重定向到 `logs/web_console.log`（行缓冲，实时写入）
- 程序完全后台运行，通过 Web 面板管理
- 恢复控制台：设置 `web_show_console = true` 后重启

**控制台编码 / `ctypes` 健壮性（2026-08-16 整改）**:

- kernel32 / user32 的 `WinDLL` 句柄缓存为模块级单例（`_KERNEL32` / `_USER32`），避免 `_fix_encoding()` 与 `_enter_background_mode()` 多次调用时重复加载 DLL；加载失败时仍保持 `None`，后续调用自动重试
- 补全 `restype` 声明：`SetConsoleOutputCP` / `SetConsoleCP` 返回 `BOOL`（显式 `restype = ctypes.c_int`），`ShowWindow` 返回 `BOOL`，与既有的 `GetConsoleWindow.restype = c_void_p` 一致，消除对 ctypes 默认返回类型的隐式依赖
- `_enter_background_mode()` 中 `GetConsoleWindow()` 的返回值已为 `c_void_p`，移除多余 `cast(ctypes.c_void_p, ...)`，直接判空后 `ShowWindow(hwnd, 0)`

**API 路由（按功能分组，完整清单以 `src/web_api.py` 为准）**:

| 分组 | 路由 |
| --- | --- |
| 认证 | `POST /api/login`、`POST /api/logout`、`GET /api/auth/status` |
| 状态与探活 | `GET /api/status`、`GET /api/status/stream`（SSE）、`GET /health` |
| 录制 | `POST /api/recording/toggle` |
| 直播间 | `GET/POST/PUT/DELETE /api/rooms`、`POST /api/rooms/toggle`、`PUT /api/rooms/quality`、`GET/PUT /api/rooms/qualities` |
| 配置与语言 | `GET/PUT /api/config`、`GET/PUT /api/language` |
| 文件 / 日志 / 弹幕 | `GET /api/files`、`GET /api/files/download`、`GET /api/logs`、`GET /api/danmaku` |
| 图标 | `POST /api/icon`、`GET /favicon.ico` |

**前端功能** (`web/`):

- `index.html` - 单页应用入口（视图以 `web/index.html` 为准）
- `app.js` - 前端逻辑（Token 认证、API 调用、SSE 日志流、状态渲染）
- `motion.js` - 零依赖动效引擎（入场/视差/粒子/降级）
- `style.css` - 样式表（明暗主题、响应式布局、降级高亮）
- **移动端适配惯例（2026-09-29）**：`index.html` 的 viewport 带 `viewport-fit=cover`；顶部/左右留白一律用
  `env(safe-area-inset-*)`（灵动岛与 Home Indicator 避让）、页面高度用 `100dvh`（`100vh` 仅作回退）；
  ≤768px 断点下顶栏拆两行（第一行品牌 + 语言/主题，第二行标签页整行横向滚动）、数据表在 `.panel` 内横向滚动
  （保底 `min-width:540px`）。新增面板 / 新增列 / 新增交互控件时须沿用这三条例（相对单位 + 可换行 flex + 安全区），
  约束细则与验证读数见「更新日志」的 2026-09-29 条目。

**录制表格展示**:

- 名称 / 设置画质 / 实际画质 / 开始时间 / 已录时长
- 实际画质与设置画质不一致时标红显示（`.quality-down` 样式）

**安全机制**:

- 密码变更后自动吊销所有现有 Token，强制重新登录
- 监听 `0.0.0.0` 且未启用认证时输出安全告警
- 文件下载路径校验（`_is_within` 防目录穿越）
- 敏感配置项（Cookie / 账号密码 / web_password）API 返回时脱敏为 `***`
- **未认证危险配置写保护**：`web_auth_enable = false` 时，`PUT /api/config` 禁止改写 [Recorder] 与 [Push] 危险键（如「录制完成后执行自定义脚本」`run_script`），仅允许 [Web] 及白名单键，阻断未认证 RCE 链
- **INI 注入防护**：配置值与直播间名称过滤 `\n`/`\r`，防止向 `config.ini` / `URL_config.ini` 注入任意新行 / 新节
- **登录爆破限流**：`/api/login` 连续失败达阈值（默认 5 次 / 5 分钟）后锁定一段时间（默认 10 分钟），防御密码在线爆破
- **推送日志脱敏**：`msg_push.py` 的 `_mask_url()` 对失败日志中的 webhook URL 遮挡 query 内 token / secret，避免凭证经日志泄露

### 14. 弹幕采集子系统 (`src/platforms/` + `src/collector.py` + 关联模块)

**职责与架构总览**: 提供与视频录制同步、按半小时分片的直播弹幕（bullet-chat）采集能力——弹幕落为 SRT 字幕文件，并可经「弹幕监控」独立查看（仅监控不落盘）。弹幕模块自 `dart_simple_live` 移植，原位于 `src/danmaku/`，后随目录扁平化迁移至 `src/` 根（基类 `src/base.py`、采集器 `src/collector.py`、监控 `src/danmaku_monitor.py`、传输 `src/ws_client.py`、缓存 `src/cookie_cache.py`、字幕 `src/srt_writer.py`、`src/proto/`、各平台实现 `src/platforms/`）。

**与流解析解耦**: 弹幕子系统与 `src/spider.py`（视频流地址解析）是**平行的两套抽象**。`spider.py` 负责解析视频流地址，弹幕客户端经 `src/__init__.py` 的注册表/工厂解耦；`spider.py` 完全不 import `src/platforms`。仅 B站弹幕在 AUTH 被拒时会懒加载回调 `spider.invalidate_bili_buvid_cache()`。

**生命周期接线**（与录制同起同停）:

- `main.start_record` 各平台分支收集 `record_danmaku_args`（每轮重置 `None`）；
- 6 处 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` 全部接线；
- 由 `src/__init__.py:get_danmaku_collector(platform, danmaku_args, base_filename, segment_seconds, only_fans, room_name, write_srt)` 工厂按平台取弹幕类并构造 `DanmakuCollector`；平台不支持或 `danmaku_args` 为空时返回 `None`；
- `DanmakuCollector` 在 `while process.poll() is None` 循环外 `stop()`，`DanmakuCollector.stop()` 有 `_stop_called` 防重入（幂等）。

**平台注册表**（`src/__init__.py:get_danmaku_class`，平台名与 `main.py` 标识一致）:

| 平台标识 | 弹幕类（`src/platforms/`） |
| --- | --- |
| 斗鱼直播 | `DouyuDanmaku` |
| B站直播 | `BilibiliDanmaku` |
| 虎牙直播 | `HuyaDanmaku` |
| 抖音直播 | `DouyinDanmaku` |
| TwitchTV | `TwitchDanmaku` |

**关键文件**:

- **基类与数据结构 (`src/base.py`)**: `DanmakuBase(ABC)` 定义统一契约——类属性 `heartbeat_interval=45.0`；构造 `__init__(on_message, on_close, on_ready)` 保存回调并置 `_stopped=False`；四个抽象方法 `async start(args)` / `async stop()` / `async heartbeat()` / `decode_message(data: bytes|str)`，辅助 `_emit(msg)` 经 `on_message` 上抛。`DanmakuMessageType(Enum)`（`CHAT/GIFT/ONLINE/SUPER_CHAT`）；`DanmakuMessage` dataclass（`type/user_name/message/data/color/timestamp_ms`，`timestamp_ms` 由采集器注入）。
- **弹幕采集器 (`src/collector.py`)**: `DanmakuCollector` 把异步弹幕客户端包装为线程化的同步采集器。构造参数含 `danmaku_cls / danmaku_args / base_filename / segment_seconds / only_fans / room_name / platform_name / write_srt`（`write_srt=False` 为仅监控不落盘模式）；`start()` 锚定 SRT 时间轴并起 daemon 线程 `_run()`（新 `asyncio.new_event_loop()`，实例化弹幕类 `run_until_complete(danmaku.start(args))`）；`_on_message` 把全部类型上报监控枢纽 `hub.room_message(...)`，仅 `CHAT` 且用户名/内容非空才写 SRT；`stop(timeout=8.0)` 幂等，`message_count` 属性。依赖 `src.base` / `src.danmaku_monitor` / `src.srt_writer`。
- **各平台弹幕客户端 (`src/platforms/`)**: 五个 `DanmakuBase` 子类 + 两个私有签名/编解码工具。
| 文件 | 类 | WebSocket 端点 | 关键协议/逻辑 |
| --- | --- | --- | --- |
| `douyin.py` | `DouyinDanmaku` | `wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/` | gzip 解 `PushFrame.payload`→`Response`（protobuf）；`danmaku_signature`（`_xbogus`）生成 `signature`；Cookie 缺失 `await get_ttwid()`；`backup_url` 把 `lq`→`lf` |
| `douyu.py` | `DouyuDanmaku` | `wss://danmuproxy.douyu.com:8506` | 小端二进制帧 + STT 文本协议；`_dispatch` 处理 `chatmsg`（按 `if==1` 粉丝过滤）emit CHAT；心跳发 `mrkl` |
| `huya.py` | `HuyaDanmaku` | `wss://cdnws.api.huya.com` | Tars 二进制协议（`_tars`）；`_make_join_data()` 写 `WSRegisterReq`；`cmdType==7`→`_decode_chat`（HYMessage） |
| `bilibili.py` | `BilibiliDanmaku` | `wss://{host}/sub`（遍历 `host_list`） | 16B 大端帧头；`protover=2` zlib / `=3` brotli 解压；`operation==8` AUTH_REPLY 校验 `code==0`，失败/超时经 `_reject_auth()` + `spider.invalidate_bili_buvid_cache()`；`_auth_watchdog`(8s) 兜底 |
| `twitch.py` | `TwitchDanmaku` | `wss://irc-ws.chat.twitch.tv` | 纯 IRC；匿名 `justinfan{random}` 连接；`PING`→`PONG`，正则解析 PRIVMSG emit CHAT；代理经 `handle_proxy_addr` 或系统代理 |
| `_tars.py` | （私有）Tars 编解码器 | — | 虎牙用极简 Tars：`TarsInputStream` / `TarsOutputStream`，头字节高 4 位 tag、低 4 位 type |
| `_xbogus.py` | （私有）X-Bogus 签名 | — | 抖音弹幕用：`generate_xbogus`（RC4 + 自定义 base64）、`danmaku_signature(room_id, unique_id)` |
- **弹幕监控枢纽 (`src/danmaku_monitor.py`)**: `DanmakuMonitorHub`（进程单例，经 `get_hub()` 惰性创建）聚合各房间弹幕事件——`room_started/room_connected/room_closed/room_stopped/room_message`，内存快照 `snapshot(since=0)` 供 Web API 消费，并写 JSONL 边车 `logs/danmaku_monitor.jsonl`（5MB 轮转）。所有方法异常全吞；含 10s×6 桶速率窗与每秒 ≤10 条采样折叠。
- **SRT 字幕写入 (`src/srt_writer.py`)**: `SrtWriter` 按 `segment_seconds` 分片输出 `{base}_{seg:03d}.srt`（单文件模式 `{base}.srt`），时间轴以 `time.monotonic()` 为基准、与 ffmpeg `segment -reset_timestamps` PTS 对齐；`write()` 持 `threading.Lock` 写条目并 flush。
- **WebSocket 传输层 (`src/ws_client.py`)**: `WsClient` 各平台弹幕共用的异步 WS 客户端。`connect()` 显式 `proxy=None`（弹幕直连、不跟随系统代理，避免 SOCKS 需 python-socks 报错）；`ping_interval=None`（各平台自带心跳）；`max_size=None`、`asyncio.Lock` 串行发送；支持 `on_message/on_ready/on_heartbeat/on_close/on_reconnect` 回调与 `max_reconnect` 重连策略。
- **访客 Cookie 缓存 (`src/cookie_cache.py`)**: 进程内唯一「按网址动态获取访客 cookie」缓存，避免多 room 并发重复请求触发风控。`fetch_cookies(url, proxy, *, ttl=30min, fetcher=None)` 无锁快速路径 + singleflight 去重（2026-09-02 重写：`threading.Lock` 仅保护缓存字典与在途登记表的同步读写、**锁内绝无 await**——旧 RLock 跨 await 持有时同循环协程全部可重入、互斥失效；同循环等待者复用 future，跨循环经 `loop.call_soon_threadsafe` 交付（future 非线程安全）；拉取协程被取消时立即交付空结果，等待者带超时兜底防永久挂起）；`get_cookie_str` / `invalidate` / `clear`。
- **抖音弹幕协议 (`src/proto/`)**: `douyin.proto`（Proto3）定义 `Response/Message/ChatMessage/GiftMessage/...` 等；`douyin_pb2.py` 为 protoc 生成（DO NOT EDIT），`douyin_pb2.pyi` 为基于pyright 类型存根。抖音弹幕解析链路：`PushFrame.payload`（gzip 后 `Response`）→`Message.payload`→`ChatMessage`。

### 15. 并发调度中枢 (`src/scheduler.py`)

**职责**: 统一管理全局网络并发容量、按平台（host）隔离熔断降级、支持自适应调速与固定并发双模式的可运行时调容信号量系统。

**核心类**:

- **`ResizableSemaphore`**: 可运行时调容的信号量，实现上下文管理器协议。支持 `set_value(n)` 运行时增减容量——增大时唤醒相应数量的等待者，减小时仅降低上限、不强行回收已持有槽位。`__init__` / `set_value` 允许容量为 0（暂停态）。消除旧「销毁重建信号量」的竞态风险。
- **`PlatformBreaker`**: 按 key（host）隔离的熔断器，实现 `closed → open → half-open` 三态状态机。连续失败样本比例超阈值即 open（跳过探测并进入冷却），冷却后经**唯一**探针放行；探针成功恢复 closed、失败重新 open。用于将单平台抖动隔离降级，避免连锁拖垮全局。**探针带租约（`_PROBE_LEASE_SECONDS = 60s`，2026-08-27 起）**：探针被授予后超过租约仍未回报样本（主播未开播等待轮、`disable_record`、房间线程退出等不触发 `record` 的路径）时，`allow()` 重新授予探针实现自愈——无租约时 `_probing` 标志永不复位会导致该 host 永久熔断直到进程重启。
- **`ConcurrencyScheduler`**: 调度中枢，整合自适应容量、平台熔断、录制并发上限三大能力。
  - **网络并发容量** = `max(配置下限, min(上限, ceil(活跃数/缩放因子)))`；错误率极高时温和降容但永不低于安全下限（默认 min=1 / max=128）
  - **自适应模式**（默认，`最大同时录制数(0为不限制) = 0`）：容量随活跃任务数动态缩放，错误率反馈驱动温和背压
  - **固定并发模式**（`最大同时录制数(0为不限制) ≠ 0`）：忽略动态调速器与错误背压，网络容量恒为「同一时间访问网络的线程数」（最小 1 槽位，热更新即时生效）
  - **录制并发软上限**：通过 `recording_semaphore` 管控同时 ffmpeg 录制数，默认 0 为不限制
  - `adjust_loop` 守护循环每 5 秒重算容量，取代旧的单向压制 `adjust_max_request`

**关键函数**:

- `host_of(url)`: 从 URL 提取主机名（截到首个 `/`、`?`、`#` 为止，小写、保留端口）作为熔断 key；空串或解析异常统一归 `"unknown"`（互不相关的坏 URL 共享同一熔断 key，粗粒度兜底）
- `allow(key)`: 预检指定 host 是否已熔断，返回 False 时调用方应跳过本轮探测；half-open 态带探针租约（见 `PlatformBreaker`）
- `record_error(key)` / `record_success(key)`: 按 host 计入成功/失败样本，驱动熔断器状态迁移

**接线点**（固定几处，不改动 50+ 平台分派函数）:

- `notify.record_error/record_success` 增 `key` 形参，委托给 `scheduler`
- `start_record` 入口在平台分派前做 `scheduler.allow(record_host)` 熔断预检
- `start_record` 解析成功分支（`anchor_name` 非空）上报 `record_success(record_host)`——half-open 探针依赖本轮结果闭环，探针房间进入长时间录制期间同 host 其余房间不再饿死
- `check_subprocess` 的录制循环受 `recording_semaphore` 管控
- `main()` 首轮初始化调度器，`semaphore` / `recording_semaphore` 指向其属性

**线程安全**（2026-08-27 加固）: 配置字段（模式/配置上限/活跃数/错误窗口）由 main 主线程与 `adjust_loop` 守护线程并发读写，`_compute_capacity()` 单次加锁快照全部可变输入、`set_configured_limit()` / `set_dynamic_mode()` 锁内写入（幂等检查与写入原子）；`Lock` 不可重入，所有 setter 在锁释放后再调 `recompute()`，全链路无嵌套持锁。

**配置项**:

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| 最大同时录制数(0为不限制) | 0=不限制（同时兼作并发模式开关：0=动态调速，非0=固定并发） | 0 |
| 同一时间访问网络的线程数 | 动态模式下为容量下限之一；固定模式下为固定并发限制值 | 3 |

**测试**: `tests/test_scheduler.py` 共 16 用例，覆盖信号量调容、熔断器状态机（含探针租约超时自愈）、自适应容量缩放/下限、固定并发模式、按 key 隔离、录制并发软上限等。

## 关键类与函数

### 配置文件管理 (`src/utils.py`)

```python
def read_config_value(file_path: Path, section: str, key: str) -> str | None
def update_config(file_path: Path, section: str, key: str, new_value: str) -> None
```

### 错误处理装饰器

```python
@trace_error_decorator
async def some_function():
    # 自动捕获并记录异常（支持同步和异步函数）
    pass
```

**实现特点**:

- 使用 `asyncio.iscoroutinefunction()` 检测函数类型
- 异步函数使用 `async wrapper` 正确 `await` 并捕获异常
- 统一返回 `{}` 空字典，与调用方 `.get()` 用法兼容
- `execjs.ProgramError` 单独处理（Node.js 环境问题）

### 动态并发调整

`main.py` 中实现的基于错误率的动态并发数调整机制，避免被平台限流。

### 并发调度器 (`src/scheduler.py`)

```python
# 可运行时调容信号量
class ResizableSemaphore:
    def set_value(self, n: int) -> None: ...
    def acquire(self) -> None: ...
    def release(self) -> None: ...

# 按平台熔断器
class PlatformBreaker:
    def allow(self) -> bool: ...
    def record_success(self) -> None: ...
    def record_failure(self) -> None: ...

# 调度中枢
class ConcurrencyScheduler:
    network_semaphore: ResizableSemaphore
    recording_semaphore: ResizableSemaphore
    def set_dynamic_mode(self, enabled: bool) -> None: ...
    def set_recording_limit(self, limit: int) -> None: ...
    def allow(self, key: str) -> bool: ...
    def record_error(self, key: str) -> None: ...
    def record_success(self, key: str) -> None: ...

# 辅助函数
def host_of(url: str) -> str: ...
```

## 依赖关系

### Python 依赖 (`requirements.txt`，与 `pyproject.toml [project.dependencies]` 保持一致)

| 包名 | 版本要求 | 用途 |
| --- | --- | --- |
| requests | >=2.34.2 | 同步 HTTP 请求（现仅 ffmpeg / node 安装下载脚本使用；各平台解析走 httpx 异步面） |
| urllib3 | >=2.8.0 | 传输层（requests 之下；显式声明以防解析回退落入 CVE-2026-44431 / 97687-97689 区间） |
| httpx[http2] | >=0.28.1 | 异步 HTTP 客户端（含 HTTP/2，`src/async_http.py` 并发抓取流地址） |
| h2 | >=4.4.1 | httpx `http2=True` 的运行期依赖（`Client.__init__` 内 `import h2`） |
| socksio | >=1.0.0 | httpx SOCKS 代理（socks5/socks5h）的运行期依赖（传输层内 `import socksio`） |
| loguru | >=0.7.3 | 结构化日志（`src/logger.py` 统一封装） |
| pycryptodome | >=3.23.0 | 加密算法（SM3、RC4、AES） |
| distro | >=1.9.0 | Linux 发行版检测 |
| tqdm | >=4.69.0 | 下载进度条 |
| exejs | >=1.0.1 | JavaScript 执行引擎（PyExecJS 的活跃维护继任者，优先使用） |
| PyExecJS | >=1.5.1 | JS 执行引擎回退兼容（exejs 未安装时使用） |
| PySide6 | >=6.12.0 | GUI 窗口层（`src/gui_qt/`，QSS token 主题 + Qt 控件）+ Web 入口系统托盘（`src/web_tray.py`，2026-10-20 起由 pystray 迁来；下界 6.12 为本机实测支持 Python 3.14.8 的最小版） |
| starlette | >=1.3.1 | ASGI 框架（`src/web_api.py` 阶段2 由 FastAPI 迁移为直接依赖 Starlette 驱动；下限 0.49.1→1.0.1→1.3.1 见 CVE/PYSEC 说明） |
| uvicorn[standard] | >=0.51.0 | ASGI 服务器 |
| websockets | >=14.0 | 弹幕 WebSocket 客户端（`src/ws_client.py`；`additional_headers` 为 14.0+ API） |
| protobuf | >=6.33.5,<8 | 抖音弹幕协议解码（`src/proto/douyin_pb2.py`；上限 <8 为 gencode 兼容护栏） |
| brotli | >=1.2.1 | B站弹幕解压（protover=3） |
| PyYAML | >=6.0.3 | YAML 翻译目录支持（`i18n/zh_TW.yaml`） |

> 注 1：[历史注] 旧版此处记录「Weverse 平台认证由 `src/weverse_auth.py` 实现、不再依赖 pip 上的 `weverse` 包」。
> 该模块（连同 `tests/test_weverse_auth.py`）已于 2026-09-23 整体删除，结论仅作备查：pip 上的 `weverse`
> 包会拉入已废弃的 pycrypto==2.6.1（Python 3.10+ 无法编译），**任何时候都不要加入依赖清单**。
>
> 注 2：可执行文件打包需 PyInstaller，属于构建期可选依赖：`pip install .[build]`
>
> （对应 `pyproject.toml` 的 `[project.optional-dependencies] build`）。

### 外部依赖

| 依赖 | 用途 | 安装方式 |
| --- | --- | --- |
| FFmpeg | 视频录制与转码 | Windows 内置（`ffmpeg/`），Linux/macOS 手动安装；Docker 内 apt 安装 |
| Node.js | 运行 JavaScript 签名算法 | Windows 自动安装（`node/`），Linux 需包管理器安装；Docker 内 apt 安装 Node 24 |

### 模块依赖关系图

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
├── src/scheduler.py (并发调度中枢)
│   ├── ResizableSemaphore (可运行时调容信号量)
│   ├── PlatformBreaker (按平台熔断器)
│   └── ConcurrencyScheduler (调度中枢)
├── src/notify.py (record_error/record_success 委托调度器)
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

## 配置文件说明

### 主配置文件 (`config/config.ini`)

#### [录制设置] 节

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| language | 界面语言；留空跟随系统，支持常见语言别名并归一到 `zh_CN` / `en_US` / `en_GB` / `zh_TW` | （空） |
| 是否跳过代理检测(是/否) | 跳过启动时代理可用性检测 | 是 |
| 是否启用日志文件(是/否) | 将运行日志写入 `logs/` | 是 |
| 是否启动时清理陈旧字节码缓存(是/否) | 启动时按版本号/源码哈希清理一次陈旧 `__pycache__` | 是 |
| 直播保存路径(不填则默认) | 录制文件保存路径；留空使用 `downloads/` | （空） |
| 是否自动更新主播名(是/否) | 主播改名后同步 URL 配置与录制目录/文件 | 是 |
| 保存文件夹是否以作者区分 | 按主播名创建子目录 | 是 |
| 保存文件夹是否以时间区分 | 按时间创建子目录 | 否 |
| 保存文件夹是否以标题区分 | 按直播标题创建子目录 | 否 |
| 保存文件名是否包含标题 | 在录制文件名中加入直播标题 | 否 |
| 是否去除名称中的表情符号 | 清理主播名/标题中的 emoji | 是 |
| 视频保存格式ts\ | mkv\ | flv\ | mp4\ | mp3音频\ | m4a音频 | 录制输出格式 | ts |
| 原画\ | 超清\ | 高清\ | 标清\ | 流畅 | 默认录制画质 | 原画 |
| 自定义画质选项(逗号分隔) | GUI/Web 可选画质子集；留空使用内置全集 | （空） |
| 是否使用代理ip(是/否) | 是否启用录制代理 | 否 |
| 代理地址 | 代理服务器地址；裸 `ip:端口` 自动补 `http://` | （空） |
| 同一时间访问网络的线程数 | 网络请求并发数 | 3 |
| 最大同时录制数(0为不限制) | 全局录制并发上限 | 0 |
| 循环时间(秒) | 直播状态检测间隔；运行时下限钳制为 30 秒 | 60 |
| 排队读取网址时间(秒) | 逐条调度直播间 URL 的间隔 | 0 |
| 是否显示循环秒数 | 是否显示轮询倒计时 | 否 |
| 是否显示直播源地址 | 是否在日志中显示解析后的源地址 | 否 |
| 分段录制是否开启 | 是否按时长分段输出 | 是 |
| 是否启用HLS采集(是/否) | 优先使用 HLS；关闭或不可达时走非 HLS 候选 | 是 |
| HLS采集排除平台(逗号分隔) | 命中平台恒按 FLV 采集；留空不排除任何平台 | 虎牙直播 |
| 是否启用https录制 | 开启时使用 HTTPS 并跳过证书校验；关闭时恢复 HTTP/默认校验 | 是 |
| 禁用SSL证书验证的平台(逗号分隔) | 平台级证书校验豁免；启动时补齐虎牙/B站必需项 | 虎牙直播,B站直播 |
| 录制空间剩余阈值(gb) | 可用磁盘空间低于该值时停止新录制 | 1.0 |
| 视频分段时间(秒) | 视频分段时长 | 1800 |
| 录制完成后自动转为mp4格式 | 录制结束后自动转封装为 MP4 | 否 |
| mp4格式重新编码为h264 | MP4 后处理时重新编码为 H.264 | 否 |
| 追加格式后删除原文件 | 后处理成功后删除原始录制文件 | 是 |
| 生成时间字幕文件 | 生成时间轴字幕文件 | 否 |
| 是否录制完成后执行自定义脚本 | 录制完成后执行用户命令 | 否 |
| 自定义脚本执行命令 | 自定义脚本/命令内容 | （空） |
| 使用代理录制的平台(逗号分隔) | 按域名子串匹配并走代理 | tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit |
| 额外使用代理录制的平台(逗号分隔) | 在内置代理平台列表之外追加平台 | （空） |
| 是否录制弹幕(是/否) | 将弹幕落为 SRT 字幕 | 是 |
| 是否弹幕监控(是/否) | 实时查看弹幕但不要求落盘 | 是 |
| 弹幕分片时长(秒) | 弹幕 SRT 分片时长 | 1800 |
| 弹幕录制平台(逗号分隔) | 允许采集弹幕的平台白名单 | 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV |
| 单次录制时长上限(秒,0为不限制) | 单次 ffmpeg 录制的最长时长；0 表示不限制 | 0 |

#### [推送配置] 节

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| 直播状态推送渠道 | 微信 / 钉钉 / tg / 邮箱 / bark / ntfy / pushplus，可多选 | （空） |
| 钉钉推送接口链接 | 钉钉 Webhook | （空） |
| 钉钉通知@对象(填手机号) | @指定手机号 | （空） |
| 钉钉通知@全体(是/否) | 是否 @ 全体成员 | 否 |
| 微信推送接口链接 | Server酱 URL | （空） |
| bark推送接口链接 | Bark API | （空） |
| bark推送中断级别 | critical / active / timeSensitive / passive | active |
| bark推送铃声 | Bark 铃声 | bell |
| tgapi令牌 | Telegram Bot Token | （空） |
| tg聊天id(个人或者群组id) | 聊天 ID | （空） |
| smtp邮件服务器 | SMTP 服务器 | （空） |
| 是否使用smtp服务ssl加密(是/否) | 启用 SMTP SSL；留空视为「是」 | 是 |
| smtp邮件服务器端口 | SMTP 端口 | （空） |
| 邮箱登录账号 | 登录账号 | （空） |
| 发件人密码(授权码) | 授权码 | （空） |
| 发件人邮箱 | 发件人地址 | （空） |
| 发件人显示昵称 | 发件人昵称 | （空） |
| 收件人邮箱 | 收件人地址 | （空） |
| ntfy推送地址 | NTFY 服务地址 | （空） |
| ntfy推送标签 | NTFY 标签 | tada |
| ntfy推送邮箱 | NTFY 邮箱 | （空） |
| pushplus推送token | PushPlus Token | （空） |
| 自定义推送标题 | 推送标题 | 直播间状态更新通知 |
| 自定义开播推送内容 | 开播内容模板 | （空） |
| 自定义关播推送内容 | 关播内容模板 | （空） |
| 只推送通知不录制(是/否) | 仅通知不录制 | 否 |
| 直播推送检测频率(秒) | 推送检测间隔 | 1800 |
| 开播推送开启(是/否) | 开播通知开关 | 是 |
| 关播推送开启(是/否) | 关播通知开关 | 否 |

#### [Cookie] 节

各平台的 Cookie 配置（录制部分平台必填）。特殊键：

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| 抖音cookie | 录制抖音必填，至少包含 ttwid，留空将触发风控 | (空) |
| ttwid | 可单独固定抖音 ttwid（填 `ttwid=xxx` 或仅值均可）；留空则自动获取，填写后优先于自动获取（`src/ttwid.py`） | (空) |

#### [Authorization] 节

特殊平台的 Token 配置

#### [账号密码] 节

部分平台的账号密码配置

#### [Web] 节

Web 管理面板配置（`web.py` 模式专用）

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| web_host | 监听地址（Docker 内需设为 0.0.0.0） | 127.0.0.1 |
| web_port | 监听端口 | 8000 |
| web_auth_enable | 是否启用密码认证。关闭时 API 禁止改写 [Recorder]/[Push] 危险配置（如自定义脚本），但仍允许修改 [Web] 设置 | false |
| web_password | 登录密码（认证开启时必填，PBKDF2-HMAC-SHA256 哈希存储） | (空) |
| web_token_expiry | Token 有效期（秒） | 86400 |
| web_show_console | 是否显示控制台窗口（false 时后台隐藏运行） | true |
| web_minimize_to_tray | 控制台最小化到系统托盘（仅 Windows 生效；关闭按钮被禁用，退出请用托盘图标「退出程序」） | true |
| web_trusted_proxy | 反向代理场景下的可信代理列表（逗号分隔直连 IP，如 127.0.0.1）：仅列表内的直连对端才信任 `X-Forwarded-For` 解析真实客户端 IP（防伪造头绕过登录限流）；留空 = 一律使用直连对端地址。未启用认证且公网暴露时请勿填写 | (空) |
| web_allowed_hosts | 除服务端自动放行的 Host 之外，额外登记的域名白名单（逗号分隔，支持 `*.example.com` 后缀匹配）。Host 判定规则见 `src/web_config.py::is_host_allowed`：**IP 字面量**与**无点号单标签名**天然放行（DNS 重绑定至少要一个多级注册域名），**多级域名**必须显式登记否则 400 拒绝；`web_host` 绑到 `0.0.0.0`/`::` 时不入名单（通配符绑址本身不是合法 Host 值）。故仅当 `web_host` 为通配绑址且用**域名**访问面板时才需要填写；以 IP 直连或本机 `127.0.0.1` 默认场景无需填写 | (空) |
| web_tray_icon | 面板图标路径（`.ico`）；同时用于浏览器标签页与 Web 系统托盘；留空使用内置 `assets/app.ico` | (空) |

#### [GUI] 节

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| gui_theme | 主题：light / dark / high_contrast；留空跟随系统外观 | （空） |
| gui_scale | 缩放：85 / 100 / 115 / 130 / 150；留空按屏幕可用区自动选档 | （空） |
| gui_font | 字体族名；留空使用系统默认（Microsoft YaHei UI） | （空） |
| gui_font_file | 自定义字体文件路径（副本落 `config/fonts/`） | （空） |
| gui_tray_icon | 自定义图标路径（副本落 `config/icons/`）；留空使用 `assets/app.ico` | （空） |

### 直播间配置文件 (`config/URL_config.ini`)

**格式**:

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

**主播名自动更新**: 开启 `config.ini` 的 `[录制设置] 是否自动更新主播名(是/否)`（默认开启）后，每轮轮询解析到平台最新主播名与当前使用名不一致时，会自动完成：

1. 重命名保存目录中旧主播名命名的文件夹（`{保存路径}/{平台}/{旧主播名}`，目标已存在则逐项合并）；
2. 同步重命名文件夹内（含日期/标题子目录）所有以旧主播名为前缀的录制文件（`{旧主播名}_*`）及弹幕 SRT/时间字幕等同前缀产物，并把以 `_{旧主播名}` 结尾的标题目录（`{标题}_{旧主播名}`）一并改名；
3. 更新 `URL_config.ini` 对应行的主播名字段（按 URL 精确匹配该行，保留画质段、`#` 注释前缀与行尾换行风格，全角冒号统一半角，幂等）。

**触发与安全性**

- 触发点在每轮解析直播数据之后、录制启动之前，此刻该房间线程必然不在录制中（录制期间阻塞在 ffmpeg 守护里），因此改名不会触碰正在写入的文件，进行中的录制不受影响。
- 跳过条件：`platform == "自定义录制直播"`（其主播名含每轮随机 UUID，不应反复触发改名），或平台返回名为「空白昵称」等无效名。
- 同步顺序：**先改文件系统、后写配置文件**；两者全部成功才切换本轮使用名。任一失败（如配置文件被编辑器锁定、目录改名失败）保持旧名，下轮轮询自动重试（已完成的目录改名幂等，不会重复操作）。
- 被后台转码/播放器占用的个别文件改名失败仅告警跳过、不阻塞整体，其余文件照常处理，下轮补齐；同时清理旧名残留的录制状态条目（`recording` / `recording_time_list`），避免监控页长期挂旧名。
- 配置写入持 `file_update_lock`，与录制线程的 `update_file` / Web API 写入互斥，避免半写。

关闭该选项则保持手动填写的名称不变。

## 运行方式

### 方式 1: 源码运行

#### 前置要求

- Python 3.14+
- FFmpeg
- Node.js

#### 安装依赖

```bash
# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -r requirements.txt
```

#### 命令行模式

```bash
python main.py
```

#### GUI 图形界面模式

```bash
python gui.py
```

#### Web 管理面板模式

```bash
python web.py
# 默认监听 http://localhost:8000
```

### 方式 2: Docker 运行

#### Dockerfile 多阶段构建说明（基础镜像 `python:3.14-slim-bookworm`）

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

**`.dockerignore` 要点**（2026-08-28 同步后）：

- 排除平台二进制（`ffmpeg/`、`node/`，容器内 apt 安装）、`config/*.ini`（运行时挂载）、`typings/`、`build_exe.py`、根目录 `index.html`（独立的 M3U8 播放器页，面板用 `web/`）等桌面/构建专用文件；
  [2026-09-21 修订：本行原列 `gui_legacy.py`，该文件已于 v4.1.0-dev / 2026-09-10 删除且 `.dockerignore` 中无该条目，属 MIN-15 的第 4 处陈旧引用，就地清除]
- **保留 `i18n/**/*.mo` 编译翻译文件与 `i18n/*.json`、`i18n/*.yaml` 多语言目录** ——
  运行时必需（gettext / JSON / YAML 三种翻译目录格式）且 Dockerfile 不会重新编译/生成，
  仅排除 `.po` 源文件与编译脚本；
- 排除本地工具 / AI 助手生成目录（`.mimosa/`、`.qoder/`、`.agents/`、`.pnpm-store/`、`.dsh-validation/`、`.ego-browser-test/`、`.plugin-src/`、`pytest-cache-files-*/` 等，与 `.gitignore` 同源维护）；
- 排除镜像运行不消费的内容：`uv.lock`（镜像走 pip + requirements.txt）、`scripts/`（维护脚本，运行时链路零引用）、`tests/`、`AGENTS.md` / `README_EN.md` / `CODE_WIKI_EN.md` 等文档、`.coveragerc-concurrency`（CI 专用）。

#### 使用 docker compose (推荐)

仓库根目录的 `docker-compose.yaml` 已定义三个服务（共享同一镜像，通过 YAML 锚点复用配置）：

| 服务 | 入口 | 启动命令 | 端口 |
| --- | --- | --- | --- |
| `recorder`（默认） | `python main.py` | `docker compose up -d` | 无（纯 CLI） |
| `web`（profile） | `python web.py` | `docker compose --profile web up -d` | `127.0.0.1:8000:8000` |
| `gui`（profile） | `python gui.py` | `docker compose --profile gui up -d` | 无（需 X11） |

统一挂载卷：`./config`、`./downloads`、`./logs`、`./backup_config`。

> ⚠️ **Web 模式必读**：`web.py` 默认监听 `127.0.0.1:8000`，容器内必须在
>
> `config/config.ini` 的 `[Web]` 节设置 `web_host = 0.0.0.0`，宿主机端口映射才能访问；
>
> 同时强烈建议开启 `web_auth_enable = true` 并配置密码。

## 打包与发布

本项目提供一键式可执行文件打包（`build_exe.py`）与跨平台自动构建发布（`GitHub Actions`），将 **CLI / GUI / Web 三个入口**统一构建为可分发的发布目录。

### 1. 打包脚本 `build_exe.py`

PyInstaller `onedir` 模式 + `contents_directory='_internal'`，动态生成 `.spec` 文件后调用 PyInstaller 完成**三入口共享依赖**构建：

| 产物（exe 同级） | 入口 | 模式 |
| --- | --- | --- |
| `DouyinLiveRecorder(.exe)` | `main.py` | 控制台（CLI 录制核心） |
| `DouyinLiveRecorder-GUI(.exe)` | `gui.py` | 无控制台窗口（GUI） |
| `DouyinLiveRecorder-Web(.exe)` | `web.py` | 控制台（Web 管理面板，监听 `0.0.0.0:8000`） |

三个入口共用一个 `COLLECT`，依赖去重后体积约为独立打包的 1/3。

**用法**：

```bash
python build_exe.py              # 打包并生成 zip 产物
python build_exe.py --smoke      # 打包后额外运行冒烟测试（CI 推荐）
python build_exe.py --no-zip     # 仅打包不压缩
python build_exe.py --no-runtime # 跳过 ffmpeg/node 打包（交由用户运行时自动下载，减小体积）
python build_exe.py --dual       # 同时生成 lite（无运行时）与 full（下载并打包 ffmpeg+node）两个 zip
```

**数据文件与隐藏导入**：

- `datas`：`src/javascript`（JS 签名脚本）、`i18n`（翻译）、`web`（前端静态资源），均经 `__file__` 定位，PyInstaller 自动收进 `_internal/`。
- `config/` 不进 `_internal`，由 `copy_external_binaries()` 复制到 exe 同级（见目录规范）。
- `hiddenimports`：`i18n`、`src.async_http`（main.py 经 `__import__` 动态导入）、`h2`（httpx[http2] 懒加载）；`a_web` 额外 `collect_submodules('uvicorn')`（协议模块按字符串导入）。
- `excludes`：CLI 排除 GUI/Web 库（tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette）；GUI 排除 Web 库；Web 排除 GUI 库（tkinter/customtkinter/pystray；**2026-10-20 起不再排除 `PySide6`**——Web 托盘已迁 QSystemTrayIcon）；三个入口均额外排除 `brotlicffi`（修复打包后 brotlicffi 模块缺失 `error` 属性的报错，httpx 无 brotli 时自动回退）。

**版本号**：从 `pyproject.toml` 的 `version` 字段解析（单一事实源），用于 zip 命名，解析失败回退 `0.0.0`。`main.py` 运行时同样从 `pyproject.toml` 动态读取版本号（优先 `importlib.metadata`，回退直接解析文件）。

### 2. 目录结构规范（打包产物）

采用 `onedir + contents_directory='_internal'` 后，PyInstaller 把依赖与经 `__file__` 定位的资源收进 exe 同级的 `_internal/`；而经 `sys.argv[0]`/`sys.executable` 定位的运行时资源由打包脚本在 `COLLECT` 之后复制到 exe 同级。最终产物结构：

```
dist/DouyinLiveRecorder/
├── DouyinLiveRecorder.exe          # CLI 录制核心
├── DouyinLiveRecorder-GUI.exe      # 图形界面
├── DouyinLiveRecorder-Web.exe      # Web 管理面板
├── config/                          # 配置目录（exe 同级，运行时直接读写）
├── assets/                          # 应用图标（assets/app.ico）
├── ffmpeg/                          # FFmpeg 运行时（exe 同级，Windows 内置）
├── node/                            # Node.js 运行时（exe 同级，Windows 内置）
├── logs/                            # 日志目录（运行时默认创建于 exe 同级）
├── downloads/                       # 默认下载目录（config.ini 未指定时位于 exe 同级）
├── backup_config/                   # 配置备份目录（exe 同级）
└── _internal/                       # 依赖包 + src/ 及打包资源统一管理
    ├── (Crypto/ PySide6/ certifi/ h2/ watchfiles/ websockets/ yaml/ + 运行库 .dll)
    ├── src/            src/javascript/
    ├── i18n/
    ├── web/
    └── assets/
```

**关键约定（硬性）**：

- `node/`、`ffmpeg/`、`config/` 与 exe 保持**同级**（而非 `_internal/`）。
- `src/` 及全部 Python 依赖包统一收进 `_internal/`。
- 运行时可写目录 `logs/`、`downloads/`（未通过 `config.ini` 的 `直播保存路径(不填则默认)` 指定时）、`backup_config/` 均默认创建在 **exe 同级目录**。

### 3. 路径收敛机制 `_app_root()`

项目存在"双轨路径"：`main.py`/`src/ffmpeg_install.py`/`src/__init__.py` 等用 `sys.argv[0]`/`sys.executable` 定位运行时资源；`src/logger.py`、`i18n.py`、`src/web_api.py` 等用 `__file__` 定位打包资源。冻结后前者指向 exe 同级（发布根），后者指向 `_internal/`。

为统一收敛，新增 `src/logger._app_root()`（与 `main.py` 内联同名函数）：

```python
def _app_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.realpath(sys.executable))  # = exe 同级
    return os.path.split(os.path.realpath(sys.argv[0]))[0]
```

- `main.py` 的 `script_path`、`src/__init__.py`、`src/node_install.py`、`src/ffmpeg_install.py` 的 `execute_dir` 均收敛到 exe 同级，使 `config/ffmpeg/node` 正确定位。
- `src/logger.py` 的 `script_path` 改为 `_app_root()`，使 `logs/`、`backup_config/` 落在 exe 同级。
- `gui.py` 新增 `self.app_root`：冻结时若 `script_dir` 为 `_internal` 则回退一层到发布根，config/downloads 据此定位；CLI 子进程经同目录 `DouyinLiveRecorder.exe` 拉起（见下）。
- `i18n.py` 支持 `_internal/i18n` 与 `i18n/` 双路径检测。

### 4. 冻结版适配要点

- **GUI 子进程拉起（关键修复）**：`gui.py` 冻结后 `sys.executable` 指向 GUI 自身，原 `[sys.executable, main.py]` 会无限递归拉起 GUI。改为冻结时直接调用同目录的 `DouyinLiveRecorder.exe`，源码运行保持原样。
- **GUI 子进程 pythonw 兼容（2026-08-09）**：源码模式下若 GUI 经 `pythonw.exe` 启动，`sys.executable` 指向 pythonw（GUI 子系统、无控制台），原 `[sys.executable, main.py]` 会让录制核心也以 pythonw 运行——`CREATE_NEW_CONSOLE` 对其无效，`AttachConsole(pid)` 必失败、CTRL_BREAK 永远送不到、停止只能硬杀（ffmpeg 孤儿化）。现检测解释器 basename 以 `pythonw` 开头时改用同目录 `python.exe`（console 子系统）拉起录制核心；打包版（CLI exe `console=True`）不受影响。
- **GUI 停止录制优雅退出（2026-08-09）**：`_send_ctrl_break_to_child` 失败时不再只 `proc.terminate()`（`TerminateProcess` 硬杀、ffmpeg 孤儿化且 `wait()` 立即成功绕过整树清理），改为 `taskkill /F /T /PID` 整树终止；日志按路径区分"优雅退出"与"硬杀路径"，不再谎报 ffmpeg 已清理。
- **中文 UTF-8 编码（关键修复）**：冻结后子进程 stdout 为管道，Python 回退到 GBK 写输出，而 GUI 以 UTF-8 读取管道 → 中文乱码（如 `自动获取 Cookie ttwid 成功` 变成乱码）。在 `main.py`/`gui.py`/`web.py` 顶部加入 `_fix_encoding()`：Windows 下 `sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace')` + `ctypes.windll.kernel32.SetConsoleOutputCP(65001)/SetConsoleCP(65001)`；非 Windows 仅 reconfigure。stream 加 `None`/`hasattr` 保护（windowed exe 的 stdout 可能为 `None`）。`web.py` 原有 `reconfigure(errors='replace')` 升级为同时设 `encoding='utf-8'`。

### 5. 冒烟测试

`build_exe.py --smoke` 在打包后自动运行三项验证（CI 推荐开启）：

- **CLI**：启动数秒，确认进入监控循环且输出无 `Traceback`/`ImportError`/`ModuleNotFoundError`。
- **Web**：HTTP 探活 `http://127.0.0.1:8000/`，返回 200 视为面板可用；同时验证内置 ffmpeg 被命中（不触发下载）。
- **GUI**：启动 8 秒确认进程存活无崩溃（无显示环境 `DISPLAY` 未设置时自动跳过）。

冒烟前会向 exe 级 `config/URL_config.ini` 写入一条注释 URL，避免 CLI 因 URL 列表为空而阻塞在 `input()`。

### 6. GitHub Actions CI 静态验证（`ci.yml`）

工作流文件：`.github/workflows/ci.yml`，在 push 到 main / PR 时运行，确保代码风格、类型安全与功能正确性在合入前通过验证（2026-08-28 优化后结构如下）。

**统一策略**：

- `setup` job 集中声明**共享常量**（Python 版本矩阵 / Node 版本 / black / isort / mypy 固定版本号）并执行路径过滤，常量输出至 job outputs 供各 job 与 `strategy.matrix` 引用（matrix 无法引用 env 上下文），是全工作流的单一事实源；
- **actions 大版本统一 v7**（`checkout` / `setup-python` / `setup-node` / `upload-artifact`），与 build-release.yml 完全一致；
- **网络安装重试统一经 `.github/actions/retry` 复合动作**（线性退避 ×3；`command` / `label` / `attempts` / `backoff` 可参数化）——pip / apt 安装共 9 处调用，重试策略只在 action.yml 一处维护，禁止 job 内重新内联重试循环；
- **apt 强化参数**（对齐 build-release.yml 的 Linux 构建）：`DEBIAN_FRONTEND=noninteractive` + `Acquire::Retries=3` + `--no-install-recommends`；
- 每个 job 显式 `timeout-minutes`；同分支/PR 新推送 `cancel-in-progress: true` 取消旧运行（快速反馈，与发布流的不可取消策略有意区分）；
- pip 缓存统一以 `hash(requirements.txt + pyproject.toml)` 为 key（仓库无 lock 文件参与安装）。

**路径过滤**：`setup` job 使用 `dorny/paths-filter@v4` 检测变更文件类别，命中即运行全部下游 job。触发清单：Python 源码（`src/**`、根目录入口 `main.py`/`gui.py`/`web.py`/`i18n.py`/`msg_push.py`/`build_exe.py`）、`tests/**`、`scripts/**`、依赖清单（`requirements.txt` / `pyproject.toml` / `.coveragerc-concurrency`）、**`i18n/**`**、**`web/**`**、**`Dockerfile` / `docker-compose.yaml`**、工作流与复合动作（**`.github/workflows/**` / `.github/actions/**`**）。仅**纯文档（`*.md`）变更不触发**。**`i18n/**` 是触发条件**——纯翻译变更同样会跑 static job 的 compile_po --check 同步门禁；**`web/**` 亦是触发条件**（2026-09-20 补齐）——`web/app.js` 的 `parseConfigBool + CONFIG_*_TOKENS` 与 `src/config_bool.py` 是跨语言布尔口径不变量（AGENTS.md「布尔配置项统一解析口径」），改任一侧都须由 test job 跑 `tests/frontend/test_quality_ui.mjs` 回归锁（旧口径「纯前端 web/ 不触发」已被证伪，详见更新日志对应条目）。

**并行 jobs**（均 `needs: setup` 条件门控）：

| Job | 运行环境 | 内容 |
| --- | --- | --- |
| `static` | py3.14 | `black --check` + `isort --check` + `check_version.py` + `check_workflow_constants.py` + `check_runtime_pins.py` + `compile_po.py --check` + `check_annotations.py` + `check_skill_agents_consistency.py` + `sync_metadata.py --check` |
| `typecheck` | py3.14 | 安装 requirements + 固定版 mypy/pytest 后运行无参 `mypy`（linux 目标）与 `mypy --platform win32`；范围由 `pyproject.toml [tool.mypy].files` 定义 |
| `test` | py3.14 | `pytest --cov=src --cov-report=term-missing`（全局 `fail_under=60` 门禁，`fail-fast: false`）+ `scripts/check_coverage.py` 逐模块门禁（仅最低版本跑一次）+ coverage.xml 上传 + 可选 Codecov |
| `concurrency-test` | py3.14 | 并发专项：`COVERAGE_RCFILE=.coveragerc-concurrency` 下跑 `test_concurrency_rate_limit.py` + `test_concurrency.py` + `test_async_http_lock.py`（专用配置不设全局阈值） |
| `integration-verify` | py3.14 + Node 24 | apt 装 ffmpeg；验证 ffmpeg/node 二进制可发现，并调 `check_ffmpeg_installed()` / `check_nodejs_installed()` 验证探测逻辑 |
| `build-verify` | py3.14 打包解释器 | `build_exe.py --smoke --no-runtime --no-zip`（lite 打包 + CLI/Web/GUI 三入口冒烟，Linux 经 `xvfb-run -a`）；发布级完整打包留给 build-release.yml |
| `ci-summary` | — | 唯一 required check：汇总上游全部 job 结果（skipped 视为通过——路径过滤跳过不会让分支保护永久 pending） |

### 7. GitHub Actions 自动构建与发布（`build-release.yml`）

工作流文件：`.github/workflows/build-release.yml`（任务名 `Build (${{ matrix.os }})`）。

**触发方式**：

- 手动触发（`workflow_dispatch`，可选 `create_release` 输入）：默认仅构建并上传 artifact，勾选后亦创建 Release。
- 推送 `v*` 标签（如 `v4.0.9.1`）：构建 + 自动创建 GitHub Release 并附产物（`permissions: contents: write`，仅 build / release 相关 job 授予）。

**构建矩阵**：`windows-latest` / `ubuntu-latest` / `ubuntu-24.04-arm` / `macos-latest`，Python 3.14（`fail-fast: false`；与 ci.yml build-verify 的打包解释器同值，保证「CI 验证的打包环境 == 实际发布的打包环境」）。

**流程**：

1. `prepare` job：用 tomllib 从 pyproject.toml 提取版本号并校验 tag 一致（打错 tag 直接失败），跑 `check_version.py` 确认各消费方动态读取。
2. `release-create` job：发版路径下**预创建** Release 记录（单例 job，消除多平台 build 并发创建同一 Release 的竞态；不传 files）；手动发版路径在此补建轻量 tag（Release 必须挂在 tag 上）。
3. build job（矩阵）：各平台以系统包管理器装 ffmpeg 供冒烟——Windows `choco`、Linux `apt`（额外 `xvfb`，GUI 冒烟需虚拟显示）、macOS `brew`（`brew trust aws/tap` 为独立幂等步骤，`HOMEBREW_*` 变量在命令内 export）；**全部网络安装命令经 `.github/actions/retry` 复合动作包装**（线性退避 ×3，系统包管理器退避 15s、pip 10s）；依赖为 `pip install -r requirements.txt` + `pip install ".[build]"`。
4. `python build_exe.py --smoke --dual`（Linux 用 `xvfb-run -a` 包裹）：PyInstaller 只跑一次；出包前先清 `dist/` 内上一轮残留的 `DouyinLiveRecorder-v*.zip`（否则会被 `path: dist/*.zip` 连同本轮一起扫进附件），随后先产 **lite** zip（不含 ffmpeg/node，运行时自动下载）→ 下载运行时 → 再产 **full** zip（内置运行时，约 300MB）；两次 `make_zip` 的**返回路径**必须互不相同且都真实落件，否则当场 `SystemExit`。冒烟排在**两个** zip 之后（MID-2254），跑的是已装满运行时的发布目录——不是 lite 版本。
5. 产物发布：发版路径（tag / 手动勾选 create_release）由 build job 经 `softprops/action-gh-release@v3` 把 zip **直传 Release**（显式 `tag_name` 与 release-create 指向同一 Release，GitHub 支持同 Release 并发上传不同 asset）；仅构建路径走 `upload-artifact@v7`（`compression-level: 0` 跳过二次压缩，留存 30 天供人工取回）。
6. `release` job（发版路径）：`gh release download` 拉回已发布附件校验齐全（4 平台 ×（lite+full）= 8 个 zip，缺失即失败不发布残缺 Release），生成 `SHA256SUMS.txt`，最后经 `softprops/action-gh-release@v3` 补传校验和并写发版说明（`generate_release_notes: true`）。

**产物命名**：`DouyinLiveRecorder-v{version}-{os}-{arch}-{lite|full}.zip`（如 `DouyinLiveRecorder-v4.0.9.1-windows-amd64-full.zip`）。

### 8. 本地打包步骤

```bash
pip install .[build]              # 安装打包器（PyInstaller）
python build_exe.py --smoke      # 打包 + 冒烟测试
python build_exe.py --smoke --dual  # 与 CI 一致：lite + full 双产物
# 产物：dist/DouyinLiveRecorder/ 发布目录 + dist/DouyinLiveRecorder-vX.Y.Z-*.zip
```

注意：本仓库为本地副本，工作流需推送至 GitHub 仓库后才可运行。lite 产物（及 CI Linux/macOS 产物）不含 `ffmpeg`/`node`，首次运行会自动下载。

## 设计模式

### 1. 适配器模式 (Adapter Pattern)

各直播平台的 API 接口被统一适配为相同的调用接口，`spider.py` 和 `stream.py` 中实现。

### 2. 装饰器模式 (Decorator Pattern)

`trace_error_decorator` 用于错误追踪，`utils.py` 中实现。

### 3. 策略模式 (Strategy Pattern)

不同的消息推送渠道（钉钉、微信、TG 等）实现为独立函数，运行时根据配置选择。

### 4. 单例模式 (Singleton Pattern)

日志配置通过模块导入副作用实现单例，`src/logger.py` 中实现。

### 5. 模板方法模式 (Template Method Pattern)

各平台的录制流程遵循相同的模板：检测 → 获取流 → 录制 → 推送。

### 6. 工厂 / 注册表模式 (Factory + Registry Pattern)

弹幕子系统通过 `src/__init__.py` 的 `get_danmaku_class(platform)` 注册表（中文平台名 → 弹幕类）与 `get_danmaku_collector(...)` 工厂统一创建各平台采集器；`main.py` 按平台标识取采集器，无需感知具体平台实现。新增弹幕平台只需在注册表登记并实现 `DanmakuBase` 的 `start/stop/heartbeat/decode_message` 四个抽象方法，对调用方零侵入。

## 常见问题排查

### 问题 1: 提示缺少 FFmpeg

**解决**:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
程序已内置，无需安装
```

### 问题 2: 提示缺少 Node.js

**解决**:

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
sudo apt-get install -y nodejs

# macOS
brew install node

# Windows
程序会自动下载安装
```

### 问题 3: 抖音风控无法获取数据

**风控特征（实测）**:

- 风控信号是 **HTTP 200 + 空响应体**，不是 4xx。排查解析失败时先看 `len(response.text)`，为 0 基本就是 UA/Cookie 被拒
- 旧移动端 UA 会被静默限流（`iesdouyin.com` 接口必现），需使用桌面 Chrome UA（`room.DESKTOP_UA`）
- `iesdouyin.com/share/user/<sec_uid>` 已是 JS 反爬壳页，页面内无 `unique_id`，任何 HTML 正则都不可靠
- `web/enter` 接口偶发 `status_code=10002 unknown error` 属瞬时软拒绝（风控/缺 msToken/限流），代码已做静默重试 1 次，属正常容错，不代表房间不可用

**解决**:

- 更新 Cookie
- 降低循环监测频率
- 更换 IP
- 更新 UA（使用 `room.DESKTOP_UA` 桌面 Chrome UA）
- 若日志出现 `10002` 后 HTML 兜底成功，属正常链路，无需处理

### 问题 4: HLS 校验失败日志空白 / 总回退 FLV

**现象**（日志连续出现，且无任何可排障信息）：

```
get_response_status 校验失败（判定为不可达）:      ← 消息是空的
HLS URL validation failed, falling back to FLV    ← 原因完全不可见
```

**根因**（三层，均已修复于 2026-08-05）：

- 异常日志只打印 `{e}`，而 Windows 下 `socket.timeout` / `TimeoutError` 的 `str()` 返回**空字符串**，导致超时异常打出来是空白
- `main.py::_validate_stream_url` 用 `except Exception: return False` 把失败原因全部吞掉，回退时无任何线索
- m3u8 源 HEAD 探测只覆盖 `400/401/403/405`，**404 直接判不可达**；且 `select_source_url` → 校验调用**不透传代理**，TikTok 等境外平台直连校验必超时误判

**修复后**：异常日志带 URL + 异常类型；所有失败路径记录 warning（含 status_code / content-type）；m3u8 HEAD 非 2xx（含 404）一律补 Range GET 探测；`select_source_url` 透传 `proxy_addr`。重新运行后日志会直接给出真实原因（如 `ConnectTimeout`、`HEAD=404, Range-GET=403`）；若仍不可达则是 CDN 域名被墙或主播流地址已失效等环境问题，而非代码误判。

### 问题 5: 弹幕连接失败 "connecting through a SOCKS proxy requires python-socks"（系统代理冲突）

**现象**（B站及复用 `WsClient` 的所有平台弹幕连接断开，日志可见）：

```
[弹幕采集]BilibiliDanmaku 连接关闭: connecting through a SOCKS proxy requires python-socks
```

**前置两个已修复子问题**（均为真实缺陷，但非最终根因）：

- **短号 room_id 未转真实 room_id**：`get_bilibili_danmaku_info` 曾直接用 URL 短号（如 `live.bilibili.com/462`）请求 getDanmuInfo，B站返回的 token 与真实房间不匹配，join 后收不到弹幕；现先调 `room/v1/Room/room_init` 把短号转真实 room_id（462 → 763679）再走后续流程（`src/spider.py`）。
- **心跳协程从未被 await**：`BilibiliDanmaku.heartbeat` 是 `async def`，但 `WsClient._heartbeat_loop` 曾直接 `self._on_heartbeat()` 调用未 await，B站长连接几十秒无心跳被服务器断开；现检测 `inspect.isawaitable(result)` 后 `await result`（`src/ws_client.py`）。

**根因（系统代理"幽灵"）**：`websockets.connect(proxy=True)` 默认**自动探测并跟随代理**，经 `urllib.request.getproxies()` 获取代理配置；在 macOS 上该调用不只读 shell 环境变量，而是直接读**系统网络设置**（System Preferences → Network → Proxies）里的系统级代理。若代理工具（Clash 类）在系统设置写入了 HTTP/HTTPS/SOCKS 三层代理（如 `socks5://127.0.0.1:7890`），`env | grep -i proxy` 查不到（`scutil --proxy` 可读到），但 websockets 会跟随该 SOCKS 代理——而 SOCKS 协议需要 `python-socks` 库支持，未安装即报上述错误。视频拉流走 ffmpeg/自备 header，不经过 websockets，故录制不受代理影响；独立测试脚本因运行环境/系统代理状态不同而时好时坏。

**修复（弹幕直连）**：`src/ws_client.py` 的 `connect()` 显式传入 `proxy=None`，弹幕 WS 直连服务器、不感知系统代理与 `ALL_PROXY` 等环境变量：

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

该修复对**所有平台**（B站/斗鱼/虎牙/抖音/Twitch 等）弹幕连接统一生效（均复用 `WsClient`）。

**决策依据**：弹幕通道本就国内直连、不需出网代理，与"关闭代理录制"的整体直连语义一致；依赖最小化（不新增 `python-socks`）；不动系统设置；显式声明优于隐式探测（避免库升级改默认行为再踩坑）。若个别境外平台弹幕确需代理，可后续为 `WsClient` 增可选 `proxy` 参数按需透传，不全局跟随。

**验证**：无代理状态下完整跑通 `main.py`，弹幕正常落盘生成 SRT；`mypy src/ws_client.py` / `py_compile` 通过。排查弹幕异常先看 `logs/streamget.log`（DEBUG 记录采集线程启动 / 连接就绪 / 收到首条弹幕 / 连接关闭原因）。

### 问题 6: 抖音/斗鱼等平台状态"正在直播中"却完全不录制（无报错、无文件）

**现象**：`py web.py`（或 `python main.py`）运行期间，抖音、斗鱼房间每个监测周期都打印"正在直播中…"，但从未出现"准备开始录制视频"，不产生任何录制文件；同一配置下虎牙、B站可正常录制。日志无任何报错、警告或提示，状态面板一直显示"正在直播中"。

**影响范围**：所有 `get_record_headers()` 返回 `None` 的平台（实测：抖音、斗鱼）。这类平台的共同特征是没有专属录制请求头规则（Referer/Origin）且未配置对应 Cookie。

**根因（历史性结构 Bug）**：`main.py` 的 `run()` 中 `headers = get_record_headers(platform, ...)` 后的 `if headers:` 错误地包住了其后的**整个录制链**——tls_verify/proxy 插入、录制状态注册、TS/FLV/MP4/MKV 全部录制分支、`check_subprocess` 启动 ffmpeg、`record_success` 周期计数（约 490 行）。凡 `get_record_headers` 返回 `None` 的平台（`_RECORD_HEADER_RULES` 未配置 Referer/Origin 且无 Cookie），整个录制块被**静默跳过**：不打印、不报错、不录制、每周期空转。有专属录制头的平台（虎牙/B站）恰好不受影响，使问题看起来像"个别平台解析问题"而非全局结构问题。

**修复**：

1. **缩进层级修正（main.py）**：`if headers:` 块内只保留 `-headers` 插入（4 行）；tls_verify 插入、代理插入、录制状态注册、全部录制分支、周期计数**整体左移 4 空格**，脱离条件嵌套，无条件执行。
2. **校验器 UA 对齐（src/stream_select.py）**：新增 `MOBILE_UA` 常量（与 `main.py` ffmpeg 命令默认 UA 一字不差），`_validate_stream_url` 对无桌面 UA 的平台发移动 UA——斗鱼 hwa CDN 对非浏览器 UA 的 GET 偶发 403，校验与录制两端 UA 必须完全一致（方法 GET + 头 Referer/Cookie + UA 三位一体）。

**排查提示**：长录制链的入口条件必须与"是否录制"语义精确对应；"条件为假整块跳过"是最危险的失败模式（不抛异常、不打日志）。当所有代码路径分析都表明"应该有日志"而实际没有时，可在 `select_source_url` 返回后临时插桩打印真实 `real_url`、并对照缩进层级绘图核验块边界，是最短定位路径。

## 贡献指南

### 代码规范

- 格式化: `black .`
- 导入排序: `isort .`
- 类型检查: `mypy`（`disallow_untyped_defs = true`；CI 门禁，本机 + linux + win32 三跑）
- 类型检查（增强，本地）: `basedpyright` 已在 `pyproject.toml` 配置 `[tool.basedpyright]`（standard 模式、排除 `typings/`/`node/`/`ffmpeg/` 等、`venvPath` 与 `venv` 指向工作区 `.venv`）；CI 仍以 `mypy` 为准。
- 注释规范: 模块/函数说明统一使用 `#` 行注释，**不使用三引号 `"""` 文档字符串**；多行说明每行以 `#` 开头（功能性多行字符串字面量除外，如模板/SQL，应改用单引号 + 换行拼接而非 `"""`）

### 测试与覆盖率

- 运行测试: `pytest`（`asyncio_mode = "auto"`，异步用例无需显式标记）。
- 覆盖率门禁：全局 `fail_under = 60`；逐模块阈值唯一事实源为 `scripts/check_coverage.py` 的 `MODULE_THRESHOLDS`（spider / proxy ≥60、stream ≥70、utils ≥80、ttwid ≥85），未登记模块按全局地板判定。
- 并发专项：`test_concurrency.py` / `test_concurrency_rate_limit.py` 使用 `.coveragerc-concurrency`（不设全局阈值）。
- 通过数与覆盖率读数以最近一次门禁输出为准，本文档不固化易漂移的计数。

#### Web/接口冒烟测试工具（`scripts/smoke_test.py`）

通用、零依赖（纯标准库）的 Web/接口冒烟测试工具，用于快速验证 Web 管理面板等**运行中 HTTP 接口**的可达性与核心响应。

- 配置驱动：JSON 描述检查项（`url` / `method` / `expected_status` / `timeout` / `headers` / `body` / `expect_contains` / `expect_json`）
- `base_url` 前缀拼接，无需每个接口写完整地址
- 三种输出：控制台（带颜色）、JSON 报告、HTML 报告
- 任一检查失败退出码非 0，便于接入 CI
- **已接入 CI**：默认用例 `scripts/smoke_web.json` 探活 Web 面板 `/` 与 `/health`（后者为 `src/web_api.py` 提供的公开探活端点）；`.github/workflows/ci.yml` 的 `test` job 在 pytest 之后受控启动 `python web.py`，经 `scripts/_ci_web_smoke.sh` 做就绪等待 + 断言（走 `.github/actions/retry`），失败保留 `logs/web-smoke-*` 工件并使 job 变红——补齐 TestClient 覆盖不到的「面板进程能否真正监听并应答」链路

用法：

```bash
# 检查本机 Web 管理面板（默认 127.0.0.1:8000，示例见 scripts/smoke_web.json）
python scripts/smoke_test.py -c scripts/smoke_web.json

# 生成 HTML 报告
python scripts/smoke_test.py -c scripts/smoke_web.json -r smoke_report.html -f html
```

> 与 `build_exe.py --smoke`（打包产物冒烟，见上文第 5 节）不同，本工具针对**运行中的 HTTP 接口**做轻量探活，两者互补。

### 添加新平台支持

1. 在 `src/spider.py` 中添加平台数据获取函数
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑
4. 更新 `README.md` 和本文档

## 改动总览（按模块分类，2026-10-17）

> 本轮为 i18n 目录补齐、Qt 侧栏标签接线、GUI 字体安全、录制链 raise 文案接表、Web 422 校验文案、Docker GUI 开关、CI 工具抬版、包元数据/目录树同步与新增回归锁。逐模块文件清单与验证读数见 [`docs/changelog/code-wiki-history-zh.md`](docs/changelog/code-wiki-history-zh.md) 的 2026-10-17 条目；本轮无删除文件、无配置键移除。

## 改动总览（按模块分类，2026-10-29）

> 本轮新增 `.gitattributes`，将 119 个已跟踪文本文件的行尾由 CRLF 归一为 LF，`src/javascript/*.js` 由 `-text` 字节冻结；AST/字节级内容零改动，无配置项与依赖变化。完整文件清单、冲突修复过程与验证读数见 [`docs/changelog/code-wiki-history-zh.md`](docs/changelog/code-wiki-history-zh.md) 的 2026-10-29 条目。

## 更新日志

> **真机验证留存约定**（与 `AGENTS.md`「完成定义」第 2 步同源）：涉及录制链路 / 选源 / ffmpeg 参数 /
> 平台解析的改动，真机验证结论写在本文件对应版本条目的「验证」子节，中英同步。
> **滚动归档**：当前发布周期的详细条目已于 2026-10-31 逐字迁入 [`docs/changelog/code-wiki-history-zh.md`](docs/changelog/code-wiki-history-zh.md)；本节保留标题索引与版本概要（口径见上方「变更日志归档索引」）。
> 格式：`[YYYY-MM-DD] 平台 | 脱敏 URL | 脚本 | 结果 | 消息数`。
> 无法执行时结果列写 `SKIP(原因)`（如 `SKIP(无外网)` / `SKIP(房间未开播)`），
> 并补「交回用户」动作（如「请用户有活房间时手动跑」）；此情形不得宣布完成定义第 1→6 步完成。
> 脚本直跑时额外输出 `VERIFICATION_RESULT: {"platform":..., "status":..., ...}` 结构化一行供机器解析。
> 脚本：`tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py`（`python file.py <URL> [秒数]`，
> 需活房间 + 外网，默认人工通道）。

> **本节索引**：以下条目的逐字正文已于 2026-10-31 迁入 [归档卷](docs/changelog/code-wiki-history-zh.md) 的「迁入：当前发布周期」一节；本节仅保留标题索引，按标题原文可在归档卷检索。
>
> **v4.6.0 概要（2026-10-18 ~ 2026-10-31）**：① GUI 技术栈全面收敛到 PySide6，tkinter/pystray 遗留实现与 `src/ui_kit.py` / `src/ui_motion.py` 移除；② 统一 ICO 图标支持（GUI 托盘 / Web 托盘与页面 / 打包产物）；③ Web 托盘迁 Qt，运行日志自动折行；④ 五轮全仓审查整改（SSRF 逐跳复检、危险配置键、出站读取上限、凭据脱敏）；⑤ 行尾钉定、回归锁去日期化、元数据对账、CI 工具抬版与全仓注释精简。

### v4.7.0 (2026-11-01) — ffmpeg 三槽判据动态化：windows/linux 改取构建期当日官方清单值（advisory 显式放行 ADVISORY_ADOPT_ACK），linux 随最新月末标签解析直链，静态表退为回退基线

### v4.7.0 (2026-11-01) — 发布路径钉定动态化：node 槽位以 GPG 验签通过的官方 SHASUMS 为判据（--pin-source adopt），上游发新 LTS 不再打断发布

### v4.7.0 (2026-11-01) — 运行时钉定随上游 node v26.13.0 重钉：Node 26 转 LTS 令首条 lts 漂移，四平台 node SHA256 同时失配

### v4.7.0 (2026-11-01) — setuptools 构建下限 68.0 → 84.1.0 + uv.lock 锁面 84.0.0 → 84.2.1：外部路径逃逸公告（GHSA-xmj3-9gf7-h52w）只读排查后的加固

### v4.7.0 (2026-11-01) — 发布目录凭据校验（SEV-2213）误报修复：逐键比对收窄到「同键位」，根治 v4.6.0 四平台发布构建同红

### v4.7.0 (2026-11-01) — CI Linux 三处平台敏感用例转平台无关 + POSIX 优雅停止标记缺失纠正（recorder.py）

### v4.7.0 (2026-11-01) — brotli 声明下限 1.2.0 → 1.2.1：CI deps-audit「下限复核」抓出旧下限自身落在 PYSEC-2026-4322 受影响段

### v4.6.0 (2026-10-31) — 四份根文档同步真实状态并滚动归档：更新日志正文逐字迁入 `docs/changelog/`，根文档只保留标题索引与版本概要

### v4.6.0 (2026-10-31) — AGENTS.md 与仓库现状对齐并压缩表述（纯文档改动）

### v4.6.0 (2026-10-31) — 版本文档同步：CODE_WIKI 的 4.6.0-dev 更新日志按四类归纳进 README 双语 v4.6.0 条目，版本标签统一为 4.6.0

### v4.6.0 (2026-10-31) — i18n 资源同步：Web 托盘悬浮提示接入四语目录

### v4.6.0 (2026-10-31) — 元数据对账：以 `pyproject.toml` 为唯一事实源复核 15 个目标文件，修正 CODE_WIKI 依赖表与 egg-info 生成物

### v4.6.0 (2026-10-31) — CI 工具版本抬到 PyPI 最新：mypy 2.4.0 → 2.4.1、pytest 9.1.1 → 9.2.0

### v4.6.0 (2026-10-31) — 彻底移除 tkinter GUI 技术栈（PySide6 成为唯一窗口实现）

### v4.6.0 (2026-10-31) — GUI 运行日志窗口：自动换行随窗口宽度自适应

### v4.6.0 (2026-10-31) — 全仓注释级精简与一致性优化（零行为变化）

### v4.6.0 (2026-10-31) — CODE_REVIEW_2026-10-30 整改：P0 五条 + P1 八条 + P2 三条 + L 组可定位项

### v4.6.0 (2026-10-30) — CODE_REVIEW_2026-10-29 散落发现批次整改（未编号/待确认 15 项）

### v4.6.0 (2026-10-29) — CODE_REVIEW_2026-10-29 整改：S-03/S-04/S-06/S-07、M-01/M-04/M-05/M-13/M-17/M-26/M-34/M-35 落地

### v4.6.0 (2026-10-29) — 全仓静态代码审查（产出 `docs/worklog/CODE_REVIEW_2026-10-29.md`）+ `liveme.js` 钉定失配修复与字节对账锁

### v4.6.0 (2026-10-29) — 回归锁测试文件名去日期化：17 个文件改名、全仓引用同步

### v4.6.0 (2026-10-29) — 行尾钉定落地：新增 `.gitattributes` 并将 119 个已跟踪文本文件归一为 LF

### v4.6.0 (2026-10-22) — 统一 ICO 图标支持：GUI 托盘 / Web 托盘与页面 / 打包产物三处同源

### v4.6.0 (2026-10-21) — 审查整改第二轮：补齐「同族残留」与中断工作包，门禁/测试全绿

### v4.6.0 (2026-10-21) — 代码审查报告整改：16 项严重条目收口，判据族一次性统一

### v4.6.0 (2026-10-20) — 九个录制链路模块注释精简：删考古、折重复，逻辑零改动

### v4.6.0 (2026-10-20) — 十个运行时模块注释精简：删考古、压重复，逻辑零改动

### v4.6.0 (2026-10-20) — 全仓清理第二轮：未用 import / 只写变量 / 零引用函数与 38 处未读局部变量清零，TAG_NORMAL 与动效 token 接线

### v4.6.0 (2026-10-20) — 全仓依赖与死代码清点：摘除 python-multipart、删除死模块 src/ab_sign.py、18 个未使用 import 清零

### v4.6.0 (2026-10-20) — GUI 托盘菜单补齐「隐藏主窗口 / 设置」+ 遗留 pystray 托盘退役，pystray/Pillow 移出依赖清单

### v4.6.0 (2026-10-20) — Web 系统托盘由 pystray 迁到 PySide6（QSystemTrayIcon + QMenu），主线程改由 Qt 事件循环占用

### v4.6.0 (2026-10-19) — 2026-10-19 审查报告批：5 项严重问题全修 + M/L 级中低危收敛

### v4.6.0 (2026-10-18) — 审查整改后续批：死代码删除 + §7.11 三条机制性门禁落地（R9/R10 + 两个新锁文件）

### v4.5.0-dev (2026-10-18) — CI 修复：vbs-behavior-test job 只装 pytest，11 条用例全数 ERROR（ModuleNotFoundError: No module named 'distro'）

### v4.5.0-dev (2026-10-18) — 运行时钉定随上游 node v24.22.0 重钉：发布链四平台同时红的归因与处置

### v4.5.0-dev (2026-10-18) — SR-06 收口：`.agents/skills/` 纳入 git 跟踪（28 文件入库）+ 新增 `tests/test_skill_agents_consistency.py`（12 条回归锁），CI required check 不再在干净检出上必红

### v4.5.0-dev (2026-10-18) — 四份根文档同步真实状态 + 精简：滚动归档 v4.4.0 及更早条目、v4.5.0 发布说明压缩表述、目录树补 `src/config_read.py`

### v4.5.0-dev (2026-10-18) — 版本文档同步：CODE_WIKI 的 4.5.0-dev 更新日志按四类归纳进 README 双语 v4.5.0 条目（`README.md` / `README_EN.md`）

### v4.5.0-dev (2026-10-17) — 元数据同源复扫：以 `pyproject.toml` 为事实源核对 15 份目标文件，三处文档漂移已修（`README.md` / `README_EN.md` / `CODE_WIKI_EN.md`）

### v4.5.0-dev (2026-10-17) — config.ini 重复键不再让整份配置失效：新增 `src/config_read.py` 容错读取层 + Qt 等宽族名工厂（用户日志三条告警的归因与修复）

### v4.5.0-dev (2026-10-17) — `src/ui_fonts.py` 两处缺陷修复：字体复制失败不再零日志 + 落盘名清洗 Windows 保留设备名（新增 1 条日志模板 msgid，四目录 1131 → 1132 键；`tests/test_ui_fonts.py` 21 → 23 用例）

### v4.5.0-dev (2026-10-17) — i18n 孤儿裸文本键收回 6 条（四目录 1132 → 1126 键）+ CODE_WIKI 新增「按模块分类的改动总览」章节（`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` / `AGENTS.md` / `CODE_WIKI*.md`）

### v4.5.0-dev (2026-10-17) — AGENTS.md 事实复核与精简：6 处断言按实测改正、3 处 `file:line` 引用改锚点、一次实测读数外迁（`AGENTS.md` / `docs/agent-reference/measured-evidence.md`）

### v4.5.0-dev (2026-10-17) — i18n 批准项 B+C 落地：9 处 Qt 按钮图标恢复（复用既有键，零新条目）+ 21 处中文 raise 文案在产生点接 `tr()`（新增 16 条 msgid，四目录 1115 → 1131 键）（`src/gui_qt/main_window.py` / `src/gui_qt/pages/{dashboard,config,runlog}.py` / `main.py` / `src/spider.py` / `src/web_models.py` / 四份目录 + `zh_CN.mo` / 新增 `tests/test_i18n_raise_site_tr.py`、`tests/test_gui_qt_label_parity.py`）

### v4.5.0-dev (2026-10-17) — 测试侧修 Windows 专属红项 + 工具版本三面收敛 + `pyrightconfig.json` 让 IDE 结论可复核 + 覆盖率复跑（`tests/test_ui_fonts.py` / `.github/workflows/ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json` / `tests/test_pyright_config_parity.py`）

### v4.5.0-dev (2026-10-17) — 元数据同源同步（A1-A8 + B1）+ 镜像默认不装 GUI 依赖（`INSTALL_GUI` 单开关）（`AGENTS.md` / `CODE_WIKI*` / `README*` / `Dockerfile` / `docker-compose.yaml` / `config/config.ini` / `docs/agent-reference/project-structure.md` / 新增 `tests/test_dockerfile_image_gui_arg.py`）

### v4.5.0-dev (2026-10-17) — i18n 盲区④由「人工登记」升级为可机检：新增 `tests/test_i18n_catalog_coverage.py`（三条锁 + 变异验证）

### v4.5.0-dev (2026-10-17) — i18n 四语目录同步：补 Qt 侧栏导航 5 条「按名 tr()」msgid，四目录键数 1110 → 1115（`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`）

### v4.5.0-dev (2026-10-17) — GUI 窗口层迁移 PySide6：设计稿视觉语言 1:1 落地 + 打包链 Qt 死重剪除（`src/gui_qt/` / `gui.py` / `build_exe.py`）

### v4.5.0-dev (2026-10-17) — GUI 视觉语言改版：品牌蓝 → 暖赭橙 + 暖灰中性色（`src/ui_theme.py` / `gui.py`）

### v4.5.0-dev (2026-10-17) — GUI 右边框裁切修复 + 自选字体（`src/ui_fonts.py` / `gui.py` / `src/ui_kit.py`）

### v4.5.0-dev (2026-10-17) — 发布链运行时钉定新增「在线来源层」：默认 off，且只在清单有独立认证时才允许采用在线值

### v4.5.0-dev (2026-10-04) — GUI 界面现代化阶段6：字号层级重排 + 全局缩放设置 + 过渡动效（`src/ui_scale.py` / `src/ui_motion.py`）

### v4.5.0-dev (2026-10-04) — CI 工具版本常量对齐本地实装：`isort_version` 9.0.1 → 9.0.2（抬掉「本地全绿不可外推 CI」的最后一处版本差）

### v4.5.0-dev (2026-10-04) — GUI 静态标签接入 i18n：`src/ui_i18n.py`（T 标记 + 重译登记表）+ 语言切换整窗回填 + web_api 错误 detail 接线

### v4.5.0-dev (2026-10-04) — 小红书直播链接统一归一化：`/livestream/<房间ID>` / 动态路径 / `xhslink` 短链 / 分享参数四类接入

### v4.5.0-dev (2026-10-03) — UI 阶段5 收尾：customtkinter 依赖整体摘除 + 打包链清理 + 体积基线 + xvfb 常态化

### v4.5.0-dev (2026-10-03) — UI 阶段4 GUI 控件层：CTk → ttk 逐页替换 + `src/ui_kit.py` 工厂 + Treeview 增量表格 + 「界面主题」单入口

### v4.5.0-dev (2026-10-03) — `[tool.mypy].exclude` 目录名锚定：修掉裸 `"ffmpeg"`/`"node"` 子串误伤，12 个失明文件首次进无参 mypy 门禁

### v4.5.0-dev (2026-10-03) — B站移动端分享短链（b23.tv）接入：纯数字直取归一 + 短码 302 跟随解析（进程内缓存），复用桌面解析链路

### v4.5.0-dev (2026-10-03) — 斗鱼移动端链接（m.douyu.com）接入：准入白名单 + 分发表同表项复用 + 房间号提取归一（尾斜杠 / 查询参数 / http 协议）

### v4.5.0-dev (2026-10-03) — 虎牙移动端短链（hy.fan）接入：准入白名单 + 分发表新 resolver + 短码 301 跳转解析归一（标准 / 尾斜杠 / 查询参数 / http 协议）

### v4.5.0-dev (2026-10-03) — Linux arm64（aarch64）ffmpeg 支持三段落地：发布矩阵四平台 + 运行期官方直下新模块 + GHCR 多架构镜像发布链

### v4.5.0-dev (2026-10-02) — `CODE_REVIEW_2026-10-02` 整改收尾：补齐 L-04/L-05 两项 + 修正整改自引入的 3 处红与 3 处运行期缺陷

### v4.5.0-dev (2026-10-02) — 新增启动期陈旧字节码缓存清理 `src/startup_cleanup.py`（版本+内容哈希哨兵、白名单扫描根、开关默认开）

### v4.5.0-dev (2026-10-02) — 前端 `.mjs` 登记约束补上仓库侧完备性锁：新增 `tests/test_ci_frontend_registration.py`（清单↔目录双向差集 + 自举锁）

### v4.5.0-dev (2026-10-02) — CI typecheck 门禁补齐平台双跑：增跑 `mypy --platform win32`，win32 目标首次在合并边界参与类型检查（纯 CI / 门禁改动，零运行期变更）

### v4.5.0-dev (2026-10-02) — 全工作区代码审查（产出 `docs/worklog/CODE_REVIEW_2026-10-02.md`）：8 工作包逐文件深审 + Mimosa 深扫逐类裁断，严重 2 / 中等 17 / 轻微 47

### v4.5.0-dev (2026-10-02) — Harness 资产新增：项目级 Hook 执行体 `scripts/agent_hook_guard.py` + `/dlr-dod` 命令入口

### v4.5.0-dev (2026-10-02) — 4.4.0 文档定稿：双语 CODE_WIKI 20 处标题 v4.4.0-dev → v4.4.0 + README 双语 v4.4.0 条目补缺五项

### v4.5.0-dev (2026-10-02) — 重算签名脚本钉定表四条：pre-commit end-of-file-fixer 的尾字节漂移

### v4.5.0-dev (2026-10-02) — 版本推进 4.4.0 → 4.5.0 + dev 依赖新增 pre-commit：全仓元数据同步与派生生成物再生成
