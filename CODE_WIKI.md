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
- [更新日志](#更新日志)

## 文档统计与索引

> 本节由对**工作空间内所有 `*.md` 文件**的统计分析归纳而来（初版生成于 2026-08-09，2026-09-20 复核刷新，2026-09-27 随文档体积整理复算，2026-09-28 随版本同步与更新日志拆分归档两次复算）。
> **计数必须可复算**：下方数字是 2026-09-28 用取数命令得到的，命令一并写在这里，不复算即视为过期——
> `python -c "import pathlib; sk={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache'}; p=[x for x in pathlib.Path('.').rglob('*.md') if not (set(x.parts) & sk)]; print(len(p))"`

### 统计概览

排除 `.git/`/`.venv/`/`node_modules/` 后，工作空间共 **106** 个 Markdown 文件（2026-09-28 随更新日志拆分归档复算；较同日上一读数 101 增加 5：新落的 4 份 `docs/changelog/` 归档卷 + 1 份 harness 会话报告），按来源与维护方式分为七类：

| 分类 | 路径 | 数量 | 性质 | 是否手工维护 |
| --- | --- | --- | --- | --- |
| 项目根文档（事实来源） | `AGENTS.md` + 中英成对的 `README` / `CODE_WIKI` | 5 | 事实来源（source of truth，中英双语文档各成对） | ✅ 是 |
| 架构参考子文档 | `docs/agent-reference/**` | 6 | 从根文档外迁的**纯参考性长段**：目录树、一次性实测读数、会话经验、锁分类口径、更新日志的文件清单附录 | ✅ 是 |
| 一次性审查报告 | `docs/worklog/*.md` | 9 | 历史审查/诊断/提案产出：`CODE_REVIEW_2026-09-17`（AGENTS 约定评审）/`-09-18`/`-09-20`/`-09-21`/`-09-22`/`-09-22_1`/`-09-22_2` + `DIAGNOSIS_2026-09-23_*` + `PROPOSAL_2026-09-22_*`；原散在仓库根目录，现归档于此 | ❌ 历史产物 |
| 变更日志归档 | `docs/changelog/**` | 4 | **2026-09-28 新增**：根文档更新日志按发布周期滚动归档的历史条目卷（`README` / `CODE_WIKI` 中英各两卷）；条目逐字保留，只增不改 | ✅ 是 |
| 本地工具生成文档 | `.qoder/**` | 1 | 原 `.qoder/repowiki/**` 的 302 份 AI 生成英文知识库已于 2026-09-20 复核时确认不在工作区；现存 1 份为 harness 实践会话报告 | ❌ 自动生成 |
| 工作区记忆 | `.workbuddy/**` | 66 | 项目级持久记忆（`memory/` 53 份）+ 历次文档整理的 `docold/`/`docnew/`/`docopt/` 快照（各 4 份）+ 1 份质量报告 | ❌ 本地项目数据 |
| 历史记忆 | `.codebuddy/memory/**` | 14 | 旧版 agent 记忆（遗留） | ❌ 缓存 |
| CI 附带说明 | `.github/**/*.md` | 1 | workflow/issue 模板随附的说明文档 | ✅ 是 |

**结论**：真正由人工维护、应作为改动来源的文档是仓库根目录的 **5 个**（`AGENTS.md` 与中英成对的 `README` / `CODE_WIKI`）加上 `docs/agent-reference/` 的参考子文档与 `docs/changelog/` 的滚动归档卷；`docs/worklog/` 下的审查报告属历史产物，`.workbuddy/` 是不可删除的项目级持久数据，其余为 AI 生成衍生文档或旧版本地缓存，不应合并进本文档，以免引入与代码不同步的冗余内容。（统计快照初版生成于 2026-08-09；根文档数于 2026-08-28 随中英双语文档补齐更新为 5；2026-09-20 复核刷新；2026-09-27 起改为「取数命令 + 读数时刻」口径；2026-09-28 实测为 106）

### 根文档索引

| 文件 | 角色 | 主要内容 |
| --- | --- | --- |
| `AGENTS.md` | 编码代理约定 | 版本号单一事实源（`pyproject.toml`）、代码风格（black / isort / mypy）、项目结构、依赖/测试/构建命令、关键约定 |
| `README.md` | 用户/开发者说明 | 功能特性、已支持平台（51 个）、快速开始、配置说明、使用说明、Docker 部署、开发指南、FAQ、更新日志 |
| `CODE_WIKI.md` | 项目架构文档（本文档） | 模块详解、依赖关系、设计模式、常见问题排查、贡献指南、更新日志 |
| `README_EN.md` | 用户/开发者说明（英文） | `README.md` 的英文对应版（2026-08-24 新增，与中文版结构对齐） |
| `CODE_WIKI_EN.md` | 项目架构文档（英文） | 本文档的英文对应版（2026-08-24 新增，条目与中文版一一对应） |

> 五份文档职责互补：改动平台支持/配置项时须同步更新 `README.md` 与本文档；工程约定以 `AGENTS.md` 为准；`README_EN.md` / `CODE_WIKI_EN.md` 随对应中文版同步更新。

### 参考子文档索引（`docs/agent-reference/`）

> 这里是「从根文档外迁的纯参考性长段」的落点，判定口径见 `AGENTS.md` 头部：约束句留根文件，佐证读数与清单外迁。

| 文件 | 内容 | 外迁自 |
| --- | --- | --- |
| `project-structure.md` | 完整目录树 | `AGENTS.md`「项目结构」 |
| `measured-evidence.md` | 一次性实测读数（探针提速 / keepalive / 虎牙选档 / 斗鱼钳制 / 发布链体积） | `AGENTS.md` 坑条目末尾的长段读数 |
| `session-learnings.md` | 会话经验双轨记录（完成定义第 6 步） | `.workbuddy/memory/*.md` |
| `lock-classification.md` | 锁的可重入性分类口径 | `AGENTS.md`「已知坑」 |
| `changelog-file-inventories.md` | **2026-09-27 新增**：本文档更新日志里 41 个「涉及文件（按模块分类）」清单块的逐字原文；原处保留小节标题 + 一行指针 | 本文档更新日志 |
| `changelog-file-inventories-en.md` | 同上条目的英文对应版（32 个清单块），对应 `CODE_WIKI_EN.md` | `CODE_WIKI_EN.md` 更新日志 |

### 变更日志归档索引（`docs/changelog/`）

> **2026-09-28 新增，与上一节的分工不同**：`docs/agent-reference/` 放「从根文档抽走的参考长段」，本目录放「按发布周期滚走的完整历史条目」。
> 滚动规则：根文档只保留**当前发布周期**（本文档）或**最近三个正式发布**（`README`）的条目，其余整卷迁入归档；新条目写入根文档后，超出窗口的最旧条目随即追加到对应归档卷尾部。
> 归档卷**只增不改**：条目正文逐字保留，仅对上一轮粗剪留下的行尾 `…` / 句中截断按 `.workbuddy/docold` 基线做逐行前缀回补（各卷卷首写明口径）。

| 文件 | 内容 | 迁出自 |
| --- | --- | --- |
| `code-wiki-history-zh.md` | 本文档更新日志的 164 条历史条目（2026-05-17 ~ 2026-09-24） | `CODE_WIKI.md`「更新日志」 |
| `code-wiki-history-en.md` | 同上条目的英文对应版（164 条，与中文版一一对应） | `CODE_WIKI_EN.md`「Changelog」 |
| `release-notes-history-zh.md` | `README.md` 的 17 条早期发布说明（v4.0.0 ~ v4.0.9.4，2024-07-13 ~ 2026-09-06） | `README.md`「更新日志」 |
| `release-notes-history-en.md` | 同上条目的英文对应版（17 条） | `README_EN.md`「Changelog」 |

## 项目概述

### 项目基本信息

- **项目名称**: DouyinLiveRecorder (抖音直播录制器)
- **版本**: 4.5.0
- **作者**: y123ao6
- **开源协议**: MIT
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
| asyncio + httpx | 异步网络请求 |
| asyncio | 异步装饰器支持 |
| FFmpeg | 视频录制与转码 |
| Node.js + exejs/PyExecJS | 运行 JavaScript 签名算法（exejs 优先，PyExecJS 回退） |
| Loguru | 结构化日志 |
| tkinter.ttk + pystray + Pillow | GUI 图形界面与系统托盘 |
| Starlette + uvicorn | Web 管理面板后端 |
| HTML + CSS + JavaScript | Web 管理面板前端 |
| Docker | 容器化部署 |
| gettext (msgfmt) | 国际化翻译编译 |
| mypy | 静态类型检查（`--strict` 模式，`disallow_untyped_defs = true`） |
| pyflakes | 静态代码检查 |
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
│   ├── ffmpeg_master_download.py       # FFmpeg master 构建下载器（按平台/架构拉取 + 校验，含挑战页识别与 TOFU）
│   ├── ttwid.py                        # 抖音访客 ttwid 获取
│   ├── web_api.py                      # Web 管理面板 Starlette 应用
│   ├── web_models.py                   # Web 请求体校验层（纯标准库 dataclass + parse，替代 pydantic）
│   ├── web_config.py                   # Web 面板配置读写（不依赖 Web 框架）
│   ├── web_tray.py                     # Web 模式系统托盘（Windows 最小化到托盘）
│   ├── ui_theme.py                     # GUI 主题层（语义 token + 多主题 + ttk 注册 + 持久化 + 对比度机检）
│   ├── ui_kit.py                       # GUI 控件工厂（ttk 变体样式映射 + Treeview 增量表格）
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
├── uv.lock                              # uv 依赖锁文件（随仓库分发；镜像/CI 走 pip + requirements.txt，不消费）
├── pyproject.toml                      # Python 项目配置（版本号/工具配置/覆盖率门禁单一事实源）
├── scripts/                             # 辅助脚本
│   ├── check_version.py                # 版本号一致性校验（CI static job 调用）
│   ├── check_annotations.py            # 注释规范与逻辑等价性校验（禁 docstring / 密度下限 / --baseline AST 等价比对，CI static job 调用）
│   ├── check_coverage.py               # 逐模块覆盖率门禁（CI test job 调用，阈值 MODULE_THRESHOLDS）
│   ├── compile_po.py                   # gettext 翻译编译（.po → .mo；--check 零副作用校验同步，CI static job 调用）
│   ├── extract_i18n_strings.py         # i18n 待翻译串提取器（AST 扫描 print/logger 字面量 + 四语目录比对，维护期使用）
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
│   ├── test_scheduler.py               # 调度器测试（ResizableSemaphore / PlatformBreaker / ConcurrencyScheduler 共 16 用例）
│   ├── test_record_failure_feedback.py # 录制结果反馈测试（成功样本/快速失败退避/慢速失败/缺 -i/容量回退/直下失败与成功样本共 7 用例）
│   ├── test_stream_select.py           # 流选择与探针退避标记测试
│   ├── test_cookie_cache.py            # 访客 Cookie 缓存测试
│   ├── test_danmaku_monitor.py         # 弹幕监控枢纽测试
│   ├── test_http_config.py             # HTTP 配置测试
│   ├── test_config_io_readonly.py      # 配置只读/语言键迁移测试
│   ├── test_config_io_backup.py        # 配置备份测试
│   ├── test_bilibili_danmaku_info.py   # B站弹幕信息获取测试
│   ├── test_huya_danmaku.py            # 虎牙弹幕测试
│   ├── test_concurrency_rate_limit.py  # 抖音速率限制并发测试
│   ├── test_node_install.py            # Node.js 自动安装器离线测试（2026-09-21 新增）
│   ├── test_web_tray.py                # Web 控制台系统托盘离线测试（2026-09-21 新增）
│   ├── test_platform_danmaku_offline.py # 斗鱼/B站/Twitch 弹幕帧编解码离线测试（2026-09-21 新增）
│   ├── test_config_io_update_file.py   # 配置写侧（update_file / 主播名 / 备份脱敏）测试（2026-09-21 新增）
│   └── test_video_postprocess_paths.py # 视频后处理分支与异常分类测试（2026-09-21 新增）
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

### 9. GUI 模块 (`gui.py`)

**职责**: 提供现代化图形用户界面

**设计特点**:

- **高对比度色彩系统**: 满足 WCAG AA 无障碍标准
- **DPI 感知字体**: 自适应分辨率缩放
- **系统托盘**: 最小化到托盘运行
- **现代组件**: 卡片式设计、渐变横幅、状态指示器

**主要组件**:

- `Colors` - 色彩常量类
- `DpiFont` - DPI 感知字体系统
- `SystemTray` - 系统托盘管理
- `CardFrame` - 卡片容器
- `GradientBanner` - 渐变横幅
- `StatusIndicator` - 状态指示器
- `ModernTextWidget` - 现代文本控件

**导航页面**:

- 📊 控制台 - 录制状态总览、启停控制
- 🎯 画质监控 - 实时检测各直播间实际画质是否与设置一致
- 📝 URL 配置 - 直播间地址管理
- 📋 运行日志 - 子进程日志查看

**画质监控页面** (`_build_quality_page`):

- 通过解析 main.py 子进程 stdout 日志获取画质信息
- 解析 loguru 日志前缀（`|` + `-` 分隔），提取 message 内容
- 降级告警匹配：`{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})`
- 录制状态匹配：`{name}[{quality}] 正在录制中 {duration}`
- 统计卡片：录制中 / 画质正常 / 画质降级 计数
- 降级行以红色背景高亮，正常行显示"✓ 同等"
- 线程安全：`_quality_lock` 保护共享数据，UI 更新仅在主线程执行
- 超时清理：30 秒未更新的录制标记自动清除

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
- **Session 生命周期管理（2026-09-02）**: thread-local `requests.Session` 经模块级 `WeakSet` 弱引用登记（线程销毁后条目自动回收、不阻止 GC）；`atexit` 注册 `close_all_sessions()` 在进程退出时统一优雅关闭全部存活连接池（80+ 房间长跑场景）；另提供 `close_session()` 供房间线程退出路径显式释放当前线程 Session，关闭后下次 `_session()` 自动重建
- **Opener 构造形态（F-12 落地后，2026-09-24 校准本小节）**: 仅 `_opener_secure`（禁用代理 + 保留证书验证）在模块级预构建；不校验证书的 `SSLContext` 与 opener 一律**按需惰性构造**（`_get_insecure_context()` / `_get_insecure_opener()`）——2026-09-12 审查 6.7 指出「import 期即存在不校验上下文」等于给全进程开静默降级面，故禁止改回常驻
- **`ssl_verify` 单次覆盖（F-12）**: `sync_req(..., ssl_verify=None/True/False)` 由 `_resolve_ssl_verify()` 裁决（`None` = 跟随 `http_config.ssl_verify` 全局开关，显式传值以本次调用为准），且该次裁决必须**同时透传 urllib 与 requests(代理) 两条路径**，凭据类调用点可显式强制校验而不被全局降级拖下水
- **线程级 Session 公开出口（MIN-08）**: `session()` 供「必须拿状态码 / 响应头、无法走 `sync_req`（其失败契约是一律返回空串）」的调用点复用同一份连接池；打桩目标仍是 `_session`（测试约定）
- **响应体上限（SEV-2226 收尾，2026-09-23）**: 无代理 urllib 路径两道上限缺一不可——`_read_capped()` 限制压缩/原始响应体读入（`_MAX_RESPONSE_BYTES` 8 MiB）、`_gunzip_capped()` 分块解压并限制产出（`_MAX_DECOMPRESSED_BYTES` 32 MiB），超限抛 `ValueError` 由既有失败分支记脱敏日志并返回空串；**代理分支的 `response.text` 由 requests 自行解码 gzip，仍不受该上限保护**（已知残留缺口，见源码注释）
- **现状（SEV-2226 取证，2026-09-23）**: 本模块**当前无任何生产 importer**（`src/spider.py` 走 `from .async_http import async_req` 的 httpx 异步面；原调用方 `src/weverse_auth.py` 已于 2026-09-23 删除），去留待维护者决定；本体仍承载 F-12 不变量与 `tests/test_sync_http.py` 对该不变量的回归锁

### 13. Web 管理面板 (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`)

**职责**: 提供 Web 界面远程管理录制器，包括仪表盘、直播间管理、配置编辑、日志查看

**架构**:

- `web.py` - 入口：守护线程运行 `main.main()`，主线程运行 uvicorn；支持后台隐藏运行模式
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

**API 路由**:

| 路由 | 方法 | 功能 |
| --- | --- | --- |
| `/api/login` | POST | 密码登录，返回 Token |
| `/api/status` | GET | 获取录制状态（含 actual_quality） |
| `/health` | GET | 探活端点（`{"status": "ok", "version"}`，恒公开、不受认证支配；CI 冒烟 / LB 健康检查用） |
| `/api/rooms` | GET/POST | 直播间列表查询 / 新增 |
| `/api/rooms/{url}` | PUT/DELETE | 编辑 / 删除直播间 |
| `/api/rooms/toggle` | POST | 启用 / 禁用直播间 |
| `/api/recording/toggle` | POST | 录制全局开关（开始/停止录制；停止时触发运行日志归档） |
| `/api/config` | GET/PUT | 读取 / 修改配置 |
| `/api/logs/stream` | GET | SSE 实时日志推送 |

**前端功能** (`web/`):

- `index.html` - 单页应用入口（仪表盘 / 直播间 / 配置 三个视图）
- `app.js` - 前端逻辑（Token 认证、API 调用、SSE 日志流、状态渲染）
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

### 签名算法 (`src/ab_sign.py`)

抖音平台的 A-Bogus 签名算法，包含：

- SM3 哈希
- RC4 加密
- 复杂的参数混淆

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
| PyExecJS | >=1.5.1 | JS 执行引擎回退兼容（exejs 未安装时使用） || pystray | >=0.19.5 | 系统托盘（GUI / Web 托盘模式） |
| Pillow | >=12.3.0 | 图像处理（托盘图标生成） |
| starlette | >=1.3.1 | ASGI 框架（`src/web_api.py` 阶段2 由 FastAPI 迁移为直接依赖 Starlette 驱动；下限 0.49.1→1.0.1→1.3.1 见 CVE/PYSEC 说明） |
| uvicorn[standard] | >=0.51.0 | ASGI 服务器 |
| python-multipart | >=0.0.32 | 表单/文件上传解析 |
| websockets | >=14.0 | 弹幕 WebSocket 客户端（`src/ws_client.py`；`additional_headers` 为 14.0+ API） |
| protobuf | >=6.33.5,<8 | 抖音弹幕协议解码（`src/proto/douyin_pb2.py`；上限 <8 为 gencode 兼容护栏） |
| brotli | >=1.2.0 | B站弹幕解压（protover=3） |
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
│   ├── src/ab_sign.py
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
| 循环时间(秒) | 直播状态检测间隔；运行时下限钳制为 30 秒 | 120 |
| 排队读取网址时间(秒) | 逐条调度直播间 URL 的间隔 | 0 |
| 是否显示循环秒数 | 是否显示轮询倒计时 | 否 |
| 是否显示直播源地址 | 是否在日志中显示解析后的源地址 | 否 |
| 分段录制是否开启 | 是否按时长分段输出 | 是 |
| 是否启用HLS采集(是/否) | 优先使用 HLS；关闭或不可达时走非 HLS 候选 | 是 |
| HLS采集排除平台(逗号分隔) | 命中平台恒按 FLV 采集；留空不排除任何平台 | （空） |
| 是否启用https录制 | 开启时使用 HTTPS 并跳过证书校验；关闭时恢复 HTTP/默认校验 | 否 |
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
| 是否录制弹幕(是/否) | 将弹幕落为 SRT 字幕 | 否 |
| 是否弹幕监控(是/否) | 实时查看弹幕但不要求落盘 | 否 |
| 弹幕分片时长(秒) | 弹幕 SRT 分片时长 | 1800 |
| 弹幕录制平台(逗号分隔) | 允许采集弹幕的平台白名单 | 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV |
| 单次录制时长上限(秒,0为不限制) | 单次 ffmpeg 录制的最长时长；0 表示不限制 | 21600 |

#### [推送配置] 节

| 配置项 | 说明 | 默认值 |  |  |  |  |  |  |
| -------------------- | ------------------------------------------------------------------------ | ------ | -- | -- | ---- | ---- | ------------- | --- |
| 直播状态推送渠道 | 可选渠道：微信 | 钉钉 | tg | 邮箱 | bark | ntfy | pushplus（可多选） | (空) |
| 钉钉推送接口链接 | 钉钉 Webhook | (空) |  |  |  |  |  |  |
| 微信推送接口链接 | Server酱 URL | (空) |  |  |  |  |  |  |
| bark推送接口链接 | Bark API | (空) |  |  |  |  |  |  |
| bark推送中断级别 | Bark 中断级别，可选 critical（重要提醒）/ active（默认）/ timeSensitive（时效性）/ passive（静默） | active |  |  |  |  |  |  |
| tgapi令牌 | Telegram Bot Token | (空) |  |  |  |  |  |  |
| tg聊天id | 聊天 ID | (空) |  |  |  |  |  |  |
| smtp邮件服务器 | SMTP 服务器 | (空) |  |  |  |  |  |  |
| 是否使用SMTP服务SSL加密(是/否) | 是否启用 SMTP SSL 加密（留空视为「是」）；启用时端口通常为 465 | 是 |  |  |  |  |  |  |
| ntfy推送地址 | NTFY 服务地址 | (空) |  |  |  |  |  |  |
| pushplus推送token | PushPlus Token | (空) |  |  |  |  |  |  |
| 只推送通知不录制(是/否) | 是否仅通知不录制 | 否 |  |  |  |  |  |  |

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

# 阶段 2: runtime
# - 精简基础镜像 + apt 安装 ffmpeg / nodejs(24 LTS) / tzdata / procps
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
- `excludes`：CLI 排除 GUI/Web 库（tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette）；GUI 排除 Web 库；Web 排除 GUI 库；三个入口均额外排除 `brotlicffi`（修复打包后 brotlicffi 模块缺失 `error` 属性的报错，httpx 无 brotli 时自动回退）。

**版本号**：从 `pyproject.toml` 的 `version` 字段解析（单一事实源），用于 zip 命名，解析失败回退 `0.0.0`。`main.py` 运行时同样从 `pyproject.toml` 动态读取版本号（优先 `importlib.metadata`，回退直接解析文件）。

### 2. 目录结构规范（打包产物）

采用 `onedir + contents_directory='_internal'` 后，PyInstaller 把依赖与经 `__file__` 定位的资源收进 exe 同级的 `_internal/`；而经 `sys.argv[0]`/`sys.executable` 定位的运行时资源由打包脚本在 `COLLECT` 之后复制到 exe 同级。最终产物结构：

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
| `static` | py3.14 | `black --check .` + `isort --check .` + `python scripts/check_version.py`（版本号单一事实源校验） + `python scripts/compile_po.py --check`（i18n po/mo 同步校验，零副作用） + `python scripts/check_annotations.py`（注释规范：禁 docstring / 密度下限 / 模块头，零副作用） |
| `typecheck` | py3.14 | 安装 requirements + 固定版 mypy/pytest 后运行无参 `mypy`（范围由 `pyproject.toml [tool.mypy].files` 定义） |
| `test` | py3.14 | `pytest --cov=src --cov-report=term-missing`（全局 `fail_under=50` 门禁，`fail-fast: false`）+ `scripts/check_coverage.py` 逐模块门禁 + coverage.xml 上传 + 可选 Codecov |
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
pip install pyinstaller          # 安装打包器
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
- 类型检查: `mypy`（已启用 `disallow_untyped_defs = true`，`--strict` 模式全通过）
- 类型检查（增强，本地）: `basedpyright` 已在 `pyproject.toml` 配置 `[tool.basedpyright]`（standard 模式、排除 `typings/`/`node/`/`ffmpeg/` 等、`venvPath` 指向 workbuddy managed venv）；CI 仍以 `mypy` 为准（basedpyright 非 CI 检查项，换机需重新指定 venvPath）
- 注释规范: 模块/函数说明统一使用 `#` 行注释，**不使用三引号 `"""` 文档字符串**；多行说明每行以 `#` 开头（功能性多行字符串字面量除外，如模板/SQL，应改用单引号 + 换行拼接而非 `"""`）

### 测试与覆盖率

- 运行测试: `pytest`（`asyncio_mode = "auto"`，异步用例无需显式标记）；当前 3690 passed / 14 skipped，总覆盖率 85%（coverage.json 实测）
- 覆盖率配置集中在 `pyproject.toml`：`source = ["src"]`，全局门禁 `fail_under = 50`
- 高频变更核心模块设独立覆盖率门禁（记录于 `pyproject.toml` 注释，CI 中通过 `--cov-fail-under` 或脚本检查）：

| 模块 | 门禁 | 当前覆盖 |
| --- | --- | --- |
| `spider.py` | ≥50% | 50% |
| `stream.py` | ≥70% | 70% |
| `utils.py` | ≥80% | 82% |
| `ttwid.py` | ≥85% | 85% |
| `ab_sign.py` | ≥95% | 99% |
| `proxy.py` | ≥50% | 51% |

- 并发专项测试（`test_concurrency.py` / `test_concurrency_rate_limit.py`）使用专用配置 `.coveragerc-concurrency`（不设全局阈值），验证 `threading.Lock` 去重与抖音速率限制在多线程环境下的正确性

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

## 更新日志

> **真机验证留存约定**（与 `AGENTS.md`「完成定义」第 2 步同源）：涉及录制链路 / 选源 / ffmpeg 参数 /
> 平台解析的改动，真机验证结论写在本文件对应版本条目的「验证」子节，中英同步。
> **滚动归档**：本节只保留当前发布周期的条目，更早条目整卷存于 [`docs/changelog/code-wiki-history-zh.md`](docs/changelog/code-wiki-history-zh.md)（口径见上方「变更日志归档索引」）。
> 格式：`[YYYY-MM-DD] 平台 | 脱敏 URL | 脚本 | 结果 | 消息数`。
> 无法执行时结果列写 `SKIP(原因)`（如 `SKIP(无外网)` / `SKIP(房间未开播)`），
> 并补「交回用户」动作（如「请用户有活房间时手动跑」）；此情形不得宣布完成定义第 1→6 步完成。
> 脚本直跑时额外输出 `VERIFICATION_RESULT: {"platform":..., "status":..., ...}` 结构化一行供机器解析。
> 脚本：`tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py`（`python file.py <URL> [秒数]`，
> 需活房间 + 外网，默认人工通道）。

### v4.5.0-dev (2026-10-04) — GUI 静态标签接入 i18n：`src/ui_i18n.py`（T 标记 + 重译登记表）+ 语言切换整窗回填 + web_api 错误 detail 接线

> 范围：新增 `src/ui_i18n.py`（静态标签标记 `T()`、登记表 `register`/`retranslate_all`、窗口标题 `apply_title`）；`src/ui_kit.py` 工厂（Label/Button/DataTable 表头）识别 Translatable；`gui.py` 静态标签逐点接线 + 语言切换钩子重译 + 哨兵值改 tr 后形态 + 托盘菜单重建；`gui.py` 运行时串（`_log`/`_set_hint`/`_warn_chain`/表格单元格/弹幕流）与 `src/web_api.py` 错误 detail 全部经 `i18n_module.tr` 渲染；四语目录各 +169 条并重编 `.mo`（1034 条）。稳定机器码 detail（`unauthorized`/`rate_limited`/`host_not_allowed`/`insecure_bind_disabled`）与配置键、正则、安全黑名单刻意不翻。

- **为什么要登记表而不是销毁重建**：静态标签（按钮/卡片标题/表头/窗口标题）在控件创建时定型，语言热切换原先只影响之后经 `tr()` 查表的文案。Tk 下销毁重建会丢日志内容/URL 编辑器内容/监控表格等运行态，且挂在其上的 `after` 任务句柄会大面积 `TclError`。改为与 Qt retranslateUi 同构的「登记（控件弱引用, 应用模式, 标记）+ 切换时回填」：零状态损失，Toplevel 开关不泄漏（弱引用 + 回填时顺带清理死亡条目）。
- **工厂接线单点**：`ui_kit.Label/Button` 的 `text=` 与 `DataTable` columns 的第 2 元素（表头）接受 `str | ui_i18n.Translatable`——传 `T("…")` 时建时查表渲染 + 按 `text` / `heading:<col>` 模式登记；传普通 `str` 原样透传（动态拼接文本不参与重译）。`apply_title(win, T("…"))` 承接窗口标题（Tk 标题是方法不是 `configure` 选项）。模式分派只有 `text` / `title` / `heading:<col>` 三种，误派会静默失效（title 不是合法 configure 选项 → `TclError` 被吞）。
- **语言切换四条行为（回归锁逐条钉）**：`_on_language_change` 调 `retranslate_all()` 回填登记表；哨兵值（`默认画质`/`全部房间`）按 `i18n.tr(...)` 后形态重置（关键约定#13 同口径：比较双方都取 tr 后形态）；动态面（状态栏/画质表/弹幕表/筛选菜单/托盘菜单）重建或重渲染；`language` 写回 config.ini。重译异常与写回各自独立 try（重译炸了不得吞掉落盘）。启动期 `_setup_ui` 末尾补一次 `retranslate_all()`——`_build_sidebar` 里 `set_language` 之前构建的少数标签（品牌/主题菜单初值）按导入默认语言定型，回填保证整窗一致（实测宿主探测 en_US 时品牌标签曾中英不一致）。
- **运行时串接线形态**：`_log`/`_set_hint`/`_warn_chain` 的常量首参统一 `tr()` 包裹；含占位符的 f-string/拼接全部改写为 `i18n_module.tr(常量模板, **kw)`（占位符纯标识符、与 kwargs 严格一致，由 migration 不变量②机检）。表格单元格（`✓ 同等`/`⚠ 降级`/`已连接`/`已断开`）与弹幕流文本（`[礼物] `、`（+N 条已省略）`、`暂无弹幕数据`）在产生点 tr。`_INSECURE_BIND_ENV_TAIL` 等「按名传入 tr()」的模块常量提取器看不见，手工登记进四目录。
- **web_api 错误文案**：`HTTPException(status, detail)` 的展示类 detail 与 `JSONResponse` 的 `message` 字段全部经 `i18n_module.tr`；`_insecure_bind_detail` 改为组合模板（`bind`/`context`/`action`/`tail` 四段均为调用时查表）——403 文案随语言切换、并保留 SEV-N03「报出实际监听地址」语义。稳定机器码 detail 不动（前端 `apiError` 读 `detail` 原样弹 toast，翻译它们会破坏契约）。
- **提取面扩展**：`scripts/extract_i18n_strings.py` 与 `tests/test_i18n_migration.py` 同步认识 `T(...)`（新增 `T_CALLER_IDS`），静态标签词条纳入「目录覆盖完整」（不变量③）机检；探针用例 `test_extractor_sees_T_marker_templates` 防「提取看不见 = 永远绿」。
- **测试与验证**：新增 `tests/test_ui_i18n.py`（5 用例：渲染/回填/死亡引用清理/同槽位覆盖/三模式分派）与 `tests/test_gui_language_retranslate.py`（3 用例：重译+哨兵、托盘重建、重译失败不阻断落盘）；`tests/test_ui_kit.py` +1（工厂 Translatable 集成，真窗）；`tests/test_web_api.py` +5（login/files/rooms detail 经 tr、组合模板四段、中间件机器码 detail 不翻 + message 翻）；`tests/test_i18n_migration.py` +1（提取器 T 探针）。**变异验证五处全部转红并按字节还原**：工厂 register 移除（`MUTATION-I18NUIKIT`）、语言钩子 retranslate 移除（`MUTATION-I18NTRT`）、web_api detail 回退裸字面量（`MUTATION-I18NWEB`）、提取器 T 支持移除（`MUTATION-I18NSCAN`）、哨兵回退裸字面量（`MUTATION-I18NSENT`，锚点必须取钩子处两行块——单行锚点会命中 `__init__` 同名赋值而桩实例跳过 `__init__`，实测踩过）。附带修复：`tests/test_gui_wrap_hints.py` 子进程探针原先按简中源文前缀匹配 4 个标签，静态标签接入 i18n 后宿主语言决定译文，探针在构造后 `set_language("zh_CN")` + `retranslate_all()` 钉定语言（与用户切语言同路径）。
- **门禁读数**：`run_gates.py` **10/10 全绿**（内置 pytest 兜底 4095 passed / 0 警告）；全量 `pytest --cov` **4095 passed / 14 skipped / 0 警告**；`check_coverage.py` **48 模块全部达标**（84.89%，含新模块 `src/ui_i18n.py`）；`mypy` 0 issues；`basedpyright` **0/0/0**。

| GUI i18n 接线 | 新增 `src/ui_i18n.py`（约 100 行）、`tests/test_ui_i18n.py`（5 用例）、`tests/test_gui_language_retranslate.py`（3 用例）；改动 `gui.py`（静态标签 54 处 T()/apply_title + 运行时串 ~60 处 tr + 语言钩子 + 哨兵 + 托盘 `_build_menu`/`rebuild_menu` + `_setup_ui` 回填 + 工厂 helper 形参放宽）、`src/ui_kit.py`（Label/Button/DataTable 识别 Translatable）、`src/web_api.py`（27 处 detail/message 接线 + 模块级 `import i18n`）、`scripts/extract_i18n_strings.py`（T 扫描）、`tests/test_ui_kit.py`/`tests/test_web_api.py`/`tests/test_i18n_migration.py`/`tests/test_gui_wrap_hints.py`（回归锁与探针语言钉定）、四语目录各 +169 条并重编 `zh_CN.mo`（1034 条）；文档 `AGENTS.md` +约定/坑条目、本条目（中英同步）。一次性脚本 5 个（接线/盘点/翻译写入/变异验证，均落 `%TEMP%` 且已清理） |

### v4.5.0-dev (2026-10-04) — 小红书直播链接统一归一化：`/livestream/<房间ID>` / 动态路径 / `xhslink` 短链 / 分享参数四类接入

> 工作包来源：`docs/worklog/PROPOSAL_2026-10-04_xhs-live-link-normalization.md`（已获批）。范围：新增纯解析入口 `src/spider.py::parse_xhs_live_url`、接入既有 `get_xhs_stream_url` 取流链与 `main._resolve_xhslink_com` 分派、URL 配置归一化改走同一判据、四语 i18n 同步、`tests/test_xhs_live_links.py` 专项。不新增平台注册表项，沿用既有 `PLATFORM_HOST` / `_PLATFORM_RESOLVERS` / `start_record` 链路。

- **统一解析入口（纯函数，零网络）**：`parse_xhs_live_url(url) -> dict[str, str]` 返回 `kind` / `normalized_url` / `room_id` / `user_id`，四类形态一次覆盖——标准直播 `https://www.xiaohongshu.com/livestream/<数字房间ID>`、动态段直播 `/livestream/<动态段>/<数字房间ID>`、分享短链 `https://xhslink.com/o/<短码>`、作者主页 `/user/profile/<id>`（历史监控入口保留）。判定顺序固定为 scheme → userinfo → port → 精确 host → 路径：host 只认 `www.xiaohongshu.com` 与 `xhslink.com`（后缀伪装、尾部点、userinfo 伪装、路径里出现域名词一律拒），仅 http/https 且规范输出统一 https，默认端口放行并从规范 URL 移除。房间 ID 按 **ASCII 数字**（`[0-9]+`，不用 `\d+`，否则放行全角数字）判定，动态段 / 短码 / 主页 ID 收紧为 `[A-Za-z0-9_-]+`（`.`/`..`/`%2e%2e` 点段不进规范 URL）。动态段**原样保留**，不折叠成标准路径。
- **参数白名单**：`host_id`、`xsec_token`、`xsec_source` 三项按固定顺序重建，剥离 `timestamp` / `share_source` / `share_id` / fragment 与其余未知参数。活体取证（2026-10-04）：用户给出的短链最终落到 `/livestream/<动态段>/<数字房间ID>`，其 query 实际含 `host_id`/`share_id`/`share_source`/`source`/`timestamp`/`xsec_source`/`xsec_token`——鉴权两项必须保留，其余只用于分享溯源。
- **错误分类可机检**：`XhsUrlError` 带稳定 `code`（`host` / `non_live_path` / `room_id` / `short_path` / `scheme` / `userinfo` / `port` / `format`），消息**不回显原始 URL、query token 或 path**（`xsec_token` 不得经日志明文落地；调用方需要记录 URL 时仍走 `utils.mask_credentials()`）。`/livestream` 前缀命中但房间段非法统一归 `room_id`（提示「房间 ID 缺失或非数字」），与「不是直播间或作者主页地址」彻底分开。
- **取流链接入**：`get_xhs_stream_url` 在构造任何带凭据请求前先过统一解析，非法链接直接返回 `error` 类别且**不发出任何请求**；短链先解重定向（保留 SEV-2214 域族白名单 + `web_config._host_internal_reason` 内网双闸），落地页再过一次统一解析，指向笔记页/搜索页时按类别失败且不对落地页发带凭据请求。返回值新增 `room_id` 与 `normalized_url` 两个稳定字段。
- **离线轮可建作业（本次修掉的实质缺陷）**：主播名改读 `liveStream.roomData.hostInfo.nickName`——活体验证该字段在 `liveStatus="end"`（未开播/已下播）时依然存在，而旧实现只在开播态从 `roomInfo.deeplink` 抠 `host_nickname`。此前标准 `/livestream/<id>` 链接在等待开播的**每一轮**都拿不到 `anchor_name`，`start_record` 判「网址内容获取失败」并持续重试，表现为「配了链接却永远等不到开播提示」。仍取不到昵称时用 `小红书_<room_id>` 兜底为稳定监控名（原先会对空 `user_id` 请求 `/user/profile/None` 白费一轮）。
- **分派与配置回写**：`main._resolve_xhslink_com` 读 `port_info["error"]` → 落 `i18n.tr` 告警并置 `ctx.unrecognized`（不再与「主播没开播」混为一谈空转）；读 `normalized_url` → 走既有 `new_record_url` 通道回写 URL_config.ini，后续轮次直接用长链、省掉每轮一次短链跳转。`new_record_url` 的语义注释由「Shopee 专用」改为「解析后需回写的规范地址」。URL 配置读取阶段对 `www.xiaohongshu.com` 长链改调统一解析器（原 `re.search("&host_id=…")` 只认 `&` 前缀的首参数形态整条落空，且把鉴权参数一并剥掉）；短链**不在准入阶段**归一化（解跳转要发网络请求，抖动会改写用户配置）。四语目录各 +4 条并重编 `zh_CN.mo`。
- **测试与验证**：新增 `tests/test_xhs_live_links.py`（75 用例，覆盖四类形态、参数白名单、scheme/端口/userinfo/点段/全角数字反例、错误分类与脱敏、短链安全边界、分派回写与 i18n 模板静态锁，以及一条经 `start_record` 的**录制启动集成用例**：未开播轮登记监控作业、开播轮真的拉起 `check_subprocess` 且入参为 XHS 流地址）。既有 `TestXhsHardening` / `TestXhsRedirectCredentialContainment` 的杜撰 URL（`/live/livestream/x123`、`https://www.xiaohongshu.com/live/123`）同步换成真实形态 `/livestream/<数字ID>`。安全不变量**变异验证**两处均转红并按字节还原：房间号分类判据（`MUTATION-XHSROOMID`）、参数白名单（`MUTATION-XHSQ`）。门禁读数：`run_gates.py` **10/10 全绿**（内置 pytest 兜底 4072 passed / 0 警告）；全量 `pytest --cov` **4072 passed / 14 skipped / 0 警告**；`check_coverage.py` **47 模块全部达标**（84.79%）；`mypy` 0 issues；`basedpyright` **0/0/0**。
- **活体验证（DoD 第 2 步，解析侧）**：`[2026-10-04] 小红书 | https://www.xiaohongshu.com/livestream/570480456678837366 | 直接调用 get_xhs_stream_url | OK（识别到房间 ID 与主播名；该房间当时 liveStatus=end，故未取到流地址）| —`；短链重定向、动态路径链接、完整分享参数链接三者同样解析到同一房间。**未做**：真实开播下的拉流录制（需要正在直播的房间，交由用户在有活房间时验证）。

| 小红书链接归一化 | 新增 `src/spider.py::parse_xhs_live_url` + `XhsUrlError`（约 120 行）；改动 `src/spider.py::get_xhs_stream_url`（统一解析入口 + 短链落地二次校验 + hostInfo 昵称 + 房间 ID 兜底 + `room_id`/`normalized_url` 返回字段）、`main.py::_resolve_xhslink_com`（错误类别告警 + 规范 URL 回写）、`main.py` URL 配置读取段（小红书归一化改走统一解析器）、`i18n` 四目录各 +4 条并重编 `.mo`（865 条）；新增 `tests/test_xhs_live_links.py`（75 用例）；调整 `tests/test_spider_hardening.py`（URL 与 expected 换真实形态）、`tests/test_regression_2026_09_22_spider.py`（短链/落地页 URL 换真实形态）；文档 `AGENTS.md` +1 条、本条目（中英同步）、`docs/worklog/PROPOSAL_2026-10-04_xhs-live-link-normalization.md`。一次性脚本 0 个 |

### v4.5.0-dev (2026-10-03) — UI 阶段5 收尾：customtkinter 依赖整体摘除 + 打包链清理 + 体积基线 + xvfb 常态化

> 工作包来源：`PROPOSAL_2026-09-29_ui-modernization.md` §6 阶段5 + 工作日志 §2.5；2026-10-03 用户指令启动。范围：依赖摘除（gui.py CTk 残留替代 / requirements / pyproject / typings 存根 / build_exe 收集）、`--smoke` 三入口冒烟、体积复测（补阶段0 基线）、xvfb 评估与落地。

- **gui.py 去 CTk 化（兼容契约保持）**：`root = tk.Tk()`、两处 `CTkToplevel`→`tk.Toplevel`（bg 随主题 token；**标题栏跟随系统明暗为登记在案的观感边界**——自绘暗色标题栏需 dwmapi 额外接入，未纳入）；`CTkFont`→`tkfont.Font` **负数点值**（CTk size 语义 = 100% DPI 逻辑像素，1pt=4/3px@100%，按 3/4 折算逐档等价且随 `tk scaling` 跨 DPI 自动缩放；正数像素值不缩放、高 DPI 偏小，禁用），`Fonts.mono()` 元组同步转 `-8` 点值；`_THEME_CTK_MODE`/`_ctk_mode_to_theme` 退役，「跟随系统」改 `ui_theme.detect_system_appearance()`（win32 读注册表 `AppsUseLightTheme` / darwin 走 `defaults read` / 其余浅色兜底，任何失败回 light 不阻断启动）；新增 `_apply_root_chrome()` 按 token 上 root 底色（承接 CTk root 外观底色职责）。
- **依赖摘除三处同批**：`requirements.txt`、`pyproject.toml`（运行时清单 + `.[gui]` extra 双处）、`typings/customtkinter/` 存根目录删除（README 双语目录树同步）；`uv.lock`/`DouyinLiveRecorder.egg-info` 经 `sync_metadata.py` 重生成（双侧包名集合回归锁动态比对、无需改锁）。venv 内 customtkinter 本体**未卸载**（批量卸装属用户终端动作，红线口径）——零 import 后对门禁与产物无影响。
- **build_exe.py**：移除 `collect_data_files('customtkinter')`（无资源可收）；excludes 里的 `'customtkinter'` 条目按 fastapi 同款防御口径**保留**（防 venv 残留回渗打包）。
- **打包与体积（阶段0 缺失基线补齐）**：`build_exe.py --smoke --no-zip --no-runtime` 三入口（CLI/Web/GUI）冒烟全过（GUI 真窗运行 8s 无 FATAL_MARKERS），`_internal/` 逐项核对**零 CTk 条目**；`report_bundle_size.py` 实跑读数 **91.81 MB / 224 文件**（大头：exe 本体 32.28、numpy 26.29、python314.dll 6.48、libcrypto 5.74、Tcl/Tk 5.28），工具链泄漏检查未发现——读数与历史口径一并落 `docs/agent-reference/measured-evidence.md`。
- **xvfb 常态化（评估后落地）**：test job 的 apt 步骤加装 xvfb，`Run pytest with coverage` 改为 `xvfb-run -a` 包裹——真 Tk 集成用例（wrap_hints 真窗/压力、ui_theme TestApplyTtk、ui_kit 浮层编辑器）在 CI 从 skip 变为真实执行；按 MID-2264 反 skip 口径加「Tk 开显示」兜底步骤（xvfb 失效当场红，防真窗用例静默消失）。落地依据：阶段4/5 实证真窗用例抓到两个无头不可见的真 bug（ttk 无控件级 `-font`、CTk configure 静默忽略 cnf 字典）。
- **门禁读数（最终修订之后）**：`run_gates.py` **10/10 全绿**（内置 pytest 兜底 3993 passed / 0 警告）；全量 `pytest --cov` **3993 passed / 14 skipped / 0 警告**（14 条 skip 全为平台条件性，真窗用例本机 0 skip）；`check_coverage.py` **47 模块全部达标**（84.70%）；`mypy` **207 files 0 issues**；`basedpyright` **0/0/0**。
- **文档同源**：AGENTS.md 四处条目更新（typings 存根现存量①处、`.[gui]` 两包、GUI 两包下限、wraplength 坑位换 ttk 依据）；本文件与 CODE_WIKI_EN 同条目；工作日志 §0/§2.5/§4 收账。
- **DoD 第 2 步（真机）**：GUI 侧已由冻结产物冒烟（GUI exe 真窗 8s）+ 真窗回归锁覆盖；录制链路本批零改动。CI 首跑验证项（xvfb test job / mypy 2.4.0 consts）交由下一次 push 的 CI 实跑确认。

| UI 阶段5 收尾 | 改动 `gui.py`（root/Toplevel/Fonts/主题回调去 CTk 化 + `_apply_root_chrome`）、`src/ui_theme.py`（+`detect_system_appearance`）、`src/ui_kit.py`（头注释）、`requirements.txt`/`pyproject.toml`（摘 customtkinter ×2 处）、`build_exe.py`（-collect_data_files）、`typings/customtkinter/`（删除）、`README.md`/`README_EN.md`（目录树 -1 行）、`.github/workflows/ci.yml`（xvfb 三步）、`tests/test_gui_wrap_hints.py`（真窗分支转原生控件 + tk scaling 风暴源）、`tests/test_test_hygiene.py`（名单 -1）、`tests/test_danmaku_monitor.py`/`tests/test_regression_2026-09-22_gui.py`（importorskip 理由文案）；生成物 `uv.lock`/`DouyinLiveRecorder.egg-info` 经 `sync_metadata.py` 重生成；文档 `AGENTS.md` ×4、本条目（中英同步）、`measured-evidence.md` +体积读数、工作日志收账。一次性脚本 0 个（打包走既有入口） |

### v4.5.0-dev (2026-10-03) — UI 阶段4 GUI 控件层：CTk → ttk 逐页替换 + `src/ui_kit.py` 工厂 + Treeview 增量表格 + 「界面主题」单入口

> 工作包来源：`PROPOSAL_2026-09-29_ui-modernization.md` §3.3/§5.3（已获批规格），工作日志 §2.4 待办；2026-10-03 用户指令启动。范围：`src/ui_kit.py` 新建 + gui.py 六处（控制台/画质监控/弹幕监控/URL 配置/运行日志/高级设置）+ 侧边栏逐页替换；「外观模式/界面主题」两菜单统一；表格改 Treeview 验「不再闪烁、点击不落空」。兼容契约逐字保持：`LiveRecorderGUI`/`SystemTray`/`AdvancedSettingsWindow`/`Colors`/`Fonts`/`_quality_alert_expired` 符号与签名不变、`import gui` 无头导入、录制链/web_config/调度一行不动。

- **架构落点（颜色不进工厂）**：`src/ui_kit.py`（约 430 行）提供 `Frame`/`Label`/`Button`/`Menu`/`EditorText`/`terminal_text` 六个 CTk 兼容工厂 + `DataTable` 表格封装；**全部配色由 ui_theme 按 token 注册的 ttk 变体样式派生**（`Card.TFrame`/`Alt.TFrame`/`Primary.TFrame`/`Muted.TLabel`/`Success.TButton`/`Ghost.TButton`/`Nav.TButton`/`NavActive.TButton` 等），主题切换由 ttk 全局样式统一重绘，调用方以 `variant=` 字符串选样式、不得直写颜色；`Colors.TERMINAL_*` 是唯一例外（刻意的主题无关终端配色，经 `terminal_text()` 以 tk 控件落地）。ui_theme 同批扩展：`_shade()` 由基础槽位派生悬停色、Treeview `rowheight=32`、Combobox 下拉弹层经 option DB 上色、对比度契约 +3 对（`primary/surface_alt`、`on_primary/success`、`on_primary/danger`，均 4.5）。
- **两处机制性实测裁定**（探针脚本已删，结论由注释与测试锚点固化）：① **ttk 的 wraplength 是原始设备像素**（Tk 9.0 实测：`tk scaling`×2 后同值 reqwidth 恒定），`_compute_wraplength` 去掉 CTk 时代的缩放率除法（旧锚点 1584@1.5→1050 与新锚点 1584→1576 在 150% DPI 视觉等价），`ScalingTracker` 依赖退役；② **ttk.Button 无控件级 `-font`**（TclError），经 `font_style()` 按「变体样式+字体」缓存派生样式并**显式复制**基础变体的静态配置与状态映射（实测多段样式名的 configure/map 跨段回退不可靠）。
- **DataTable 行级增量更新**：`sync(keys, values, tags)` 按 key 差异化 `insert/delete/item/move`——未变化行零触碰、顺序错位才 move（不重建行对象），从结构上消灭旧 `CTkScrollableFrame` 每轮 destroy+重建的闪烁与点击落空；行 key 直接用业务键（含空格的「序号N 主播名」，tkinter 参数化调用安全）。每行「切换画质」用 Treeview 单元格 bbox 浮层 readonly Combobox 实现（tkinter 官方 editable-cell recipe）：点击弹出、初值=该行当前画质（`_quality_row_setq` 随 sync 缓存）、选中即走既有 `_on_room_quality_change`（未保存裁决/反查写回全复用），`.set()` 不触发回调的语义与 CTkOptionMenu 一致。旧 `_add_quality_header_row`/`_add_quality_data_row`/`_add_danmaku_header_row`/`_add_danmaku_data_row` 四方法删除，表头由 Treeview headings 承担；行级着色（降级红/断连灰）经 tag 由 `_sync_table_tags()` 按 token 配置——Treeview tag 是行级的，旧「逐格着色」不可表达，✓/⚠ 字形保留状态语义；空态占位改单实例 grid 叠放切换（不再每轮重建）。
- **菜单统一**：侧边栏「外观模式」（跟随系统/浅色/深色，硬编码中文遗留）移除，「界面主题」成为唯一明暗/对比度入口——新增「跟随系统」选项（i18n 四目录 +1 条，.mo 重编 861 条）：按当前系统明暗落 light/dark，并把 `[GUI] gui_theme` **写空值**（`load_theme_preference` 对空值按「未设置」处理 → 下次启动继续跟随）；三个显式主题即选即持久化。`_on_theme_change` 收编「跟随系统」分支；root/Toplevel 仍是 CTk，`_THEME_CTK_MODE` 继续驱动窗体明暗（依赖摘除归阶段5）；`_sync_theme_extras()` 在主题切换后重上色三类 tk 控件（Canvas 圆点 token 化、两表行标记、两编辑器）。
- **真机验证（DoD 第 2 步，真窗已执行）**：本机桌面实跑一次性驱动（已删）——完整 GUI 构建、五页切换（`_current_page` 逐页核对 + 导航选中态落带字体的派生样式）、画质表注入两行（降级行 `downgraded` 标记、占位隐藏）、**浮层编辑器点击弹出→初值「原画」→提交「高清」→ URL_config 副本写入「高清,URL,主播A」→ 日志「画质已切换」** 全链成立、弹幕表断连标记、dark 主题持久化（config 副本）、编辑器 fg 跟随 token、跟随系统写空值、空态占位回切。真窗回归锁（`tests/test_gui_wrap_hints.py` 窄容器折行 + DPI 翻转压力）在新 GUI 上 0 skip 全绿；压力采集面扩为 ttk.Label+CTkLabel（共存期）。
- **门禁读数（最终修订之后）**：`run_gates.py` **10/10 全绿**（内置 pytest 兜底 3993 passed / 0 警告）；全量 `pytest --cov` **3993 passed / 14 skipped / 0 警告**（净增 12 条：`tests/test_ui_kit.py` 11 条——sync 增量六格+空格 key+结构锁+真窗浮层编辑器/派生样式，及 wrap_hints 新锚点）；`check_coverage.py` **47 模块全部达标**（ui_kit 入列，总覆盖 84.90%）；`mypy` **207 files 0 issues**（新文件入扫描面）；`basedpyright` **0/0/0**。**变异验证**：`DataTable.sync` 改回「整表删除重建」→ 行级增量锁 5 条当场转红 → 按字节还原 → 复绿（`MUTATION-UDDT`，驱动落 %TEMP% 已删）。
- **文档与配置同源**：AGENTS.md「已知坑 · GUI」+1 条（ttk 适配三坑：wraplength 设备像素、Button 无控件级 font、CTk configure 静默忽略 cnf 字典）；本文件与 CODE_WIKI_EN 同条目；工作日志 `PROPOSAL_2026-09-29_ui-modernization-work.md` §2.4 收账。**本批未做**（阶段5 范围）：customtkinter 依赖摘除与 `build_exe.py` 数据收集清理、体积复测、xvfb 常态化评估。

| UI 阶段4 控件层 | 新增 `src/ui_kit.py`（约 430 行）+ `tests/test_ui_kit.py`（11 用例）；改动 `gui.py`（六处页面 + 侧边栏 + 主题回调 + wraplength 公式）、`src/ui_theme.py`（+15 变体样式 + 3 契约对 + option DB + _shade）、`tests/test_gui_wrap_hints.py`（新锚点 + 占位单实例锁 + 压力采集面）、`tests/test_gui_tail_robustness.py`（桩面换 DataTable 接口）、`i18n` 四目录各 +1 条并重编 `zh_CN.mo`（861 条）；文档 `AGENTS.md` +1 条、本条目（中英同步）、工作日志收账。一次性脚本 2 个（真窗冒烟驱动 + 变异验证驱动）均落 `%TEMP%`，收尾已删 |

### v4.5.0-dev (2026-10-03) — `[tool.mypy].exclude` 目录名锚定：修掉裸 `"ffmpeg"`/`"node"` 子串误伤，12 个失明文件首次进无参 mypy 门禁

> 工作包来源：`PROPOSAL_2026-10-03_linux-arm64-ffmpeg-rulings.md` §二.5（R-8，原「待维护者决策」的两项顺手修之一，2026-10-03 获开工指令）。mypy 的 `exclude` 是 `re.search` 对「相对路径 + 正斜杠归一、目录补尾 `/`」的**子串**匹配，裸目录名会把模块名含该词的源码整个排除出门禁；black（只命中目录段）/ isort（按名）/ basedpyright（目录 glob）的同名排除均无此误伤。

- **修复内容**：`pyproject.toml [tool.mypy].exclude` 的 `"node"` → `"(^|/)node/"`、`"ffmpeg"` → `"(^|/)ffmpeg/"`（目录段锚定，跨平台等价——mypy 归一路径恒用正斜杠），并在清单注释写明「新增排除项一律写锚定形态」。逐文件枚举确认修复面：裸 `"ffmpeg"` 误伤 `src/ffmpeg_*` ×4 + `tests/test_ffmpeg_*` ×6 共 **10** 个文件、裸 `"node"` 误伤 `src/node_install.py` + `tests/test_node_install.py` 共 **2** 个（node 误伤属本轮新发现，AGENTS.md 原条目未记录）；其余裸名条目（`downloads`/`recordings`/`logs`/`backup_config`/`typings` 等）经全量枚举无 `.py`/`.pyi` 路径碰撞，维持原样、不扩大 diff。
- **新暴露的 8 处存量错误（全在测试替身，src/ 侧零错误）**：① 4 处「恒回 False 的 `__exit__` 标注 `-> bool`」触发 mypy `[exit-return]`——改 `-> None`（falsy 语义不变，不抑制异常的行为逐字等价），`tests/test_ffmpeg_install.py` 的 `_Resp`/`_Bar` 与 `tests/test_node_install.py` 的 `_FakeResponse`/`_DummyTqdm`；② 4 处「lambda 消费 `list.append` 返回值」（`LIST.append(x) or False` / `(calls.append(url), resp)[1]` 形态）触发 `[func-returns-value]`——改嵌套 def（`*args: Any, **kwargs: Any` 按转发桩口径注解），行为逐字等价。
- **回归锁（新增安全不变量，变异验证必做）**：`tests/test_run_gates.py::test_mypy_exclude_never_shadows_source_files`——从 pyproject 解析 `[tool.mypy].files` 扫描面（206 个 `.py`/`.pyi`），断言**任何 exclude 模式都不得子串命中扫描面内源文件**（语义锁，不钉 `^ffmpeg/` 与 `(^|/)ffmpeg/` 的写法差异）；带三重反假绿见证（exclude ≥10 项、扫描面 ≥200 文件、两个曾经的失明家族文件必须在枚举集内）。**变异验证 PASS**：pyproject 改回裸 `"ffmpeg"`（带 `MUTATION-MYPYEXCL` 标记）→ 用例 1 failed；按字节还原（断言 `read_bytes()==原字节`）→ 复跑 1 passed；驱动脚本落 `%TEMP%` 收尾已删。
- **门禁读数（最终修订之后执行）**：无参 `mypy` 193→**205 source files**（+12 恰为枚举集合）0 issues——本机 venv **mypy 2.4.0** 与 CI 钉定 **2.3.1**（`pip install --target` 装临时目录交叉验证，项目 venv 未动）各跑一遍均全绿，版本差异按「本地门禁外推前提」条目口径完成复核；`run_gates.py` **10/10 全绿**（38.2s，顺带补上 arm64 批次「未端到端复跑」欠账）；`pytest` **3979 passed / 14 skipped / 0 警告**；`check_coverage.py` **46 模块全部达标**（总覆盖 85.02%）；`basedpyright` **0 error / 0 warning / 0 note**。black/isort 对全部改动文件 unchanged。
- **文档同源**：`AGENTS.md`「已知坑 · 类型检查」对应条目改写为「运行时二进制目录条目必须写目录段锚定形态 `(^|/)<名>/`，禁止裸名」的硬约束（含 `[历史注]` 保留修复前 189/190 source files 实测读数与已退役的「显式传参 + basedpyright」代偿口径）；本条目（中英同步）。
- **DoD 第 2 步豁免**：本批只动类型门禁配置与测试替身的标注/形态，不涉及录制链路 / 选源 / ffmpeg 参数 / 平台解析的运行时行为。

| mypy exclude 目录名锚定 | 改动 `pyproject.toml`（2 条 exclude + 注释）、`tests/test_ffmpeg_install.py`（5 处替身修复）、`tests/test_node_install.py`（3 处替身修复）、`tests/test_run_gates.py`（+1 语义锁）、`AGENTS.md`（1 条改写）；本条目（中英同步）。一次性脚本 1 个（变异验证驱动）落仓库外 `%TEMP%`，收尾已删 |

### v4.5.0-dev (2026-10-03) — B站移动端分享短链（b23.tv）接入：纯数字直取归一 + 短码 302 跟随解析（进程内缓存），复用桌面解析链路

> 用户口径：新增 `https://b23.tv/ZyQrgYf` 支持，覆盖「房间号直接跟在路径后 / 带尾斜杠 / 带查询参数 / http 版本」四种形态；提取到房间号后**复用现有B站录制流程**（拉流地址获取、清晰度选择、录制与保存），保证与 live.bilibili.com 链接行为一致、不重复实现；对无法识别、缺少房间号或房间号非法的链接返回清晰错误提示。

- **成因与需求第 3 步确认结论**：b23.tv 是B站移动端分享域，链接两类——纯数字路径（`b23.tv/22747736`，路径段即房间号）与字母短码（`b23.tv/ZyQrgYf`，302 跳转到 `https://live.bilibili.com/22747736?share_...`，2026-10-03 实测）。接入前两类都在读取 URL 配置阶段被判「本行包含未知链接.此条跳过」并注释（`b23.tv` 不在 `PLATFORM_HOST`）。**现有流程只依赖数字 room_id、不依赖桌面页面**：`_resolve_live_bilibili_com` → `spider.get_bilibili_room_info`（`room_init?id=` / `Master/info?uid=` / `getH5InfoByRoom?room_id=`）/ `stream.get_bilibili_stream_url`（`playUrl`）/ `get_bilibili_danmaku_info`（`getDanmuInfo`）全部是与输入链接形态无关的 API——移动端链接归一成 `live.bilibili.com/<房间号>` 后整链复用，**无需要新增请求的接口字段**；短码解析仅新增一次 `GET https://b23.tv/<短码>`（跟随重定向、只解析落地页路径段，不请求落地页内容），逐跳 SSRF 复检由 async_http 响应钩子既有承担。
- **实现（与同日已落地的 hy.fan 虎牙移动端短链同一套模式）**：`main.py` 新增 b23.tv 平台节（置于 `_resolve_live_bilibili_com` 之后、分发表之前，F-01c 布局约定）——`_b23_tv_path_segment`（唯一路径段提取；空路径 / 多级目录 / 非法字符 / 全角数字抛带原因的 ValueError）、`_bilibili_room_id_from_landing`（host 精确等于或 `.live.bilibili.com` 后缀；接受 `/<房间号>` 与移动端 `/h5/<房间号>` 两种形态且必须纯数字——live.bilibili.com 无字母房间号；视频页 / 自指短链 / 连字符拼接域一律空串）、`_resolve_b23_tv_room_segment`（`async_req(redirect_url=True)`，失败转带原因 ValueError）、`_resolve_b23_tv`（纯数字零网络直取归一；短码走 `_B23_TV_ROOM_CACHE` 进程内缓存、未命中才发跳转请求；失败 `logger.error`（模板经 i18n.tr、URL 经 `mask_credentials`）+ `ctx.unrecognized` 交房间线程延迟重试），归一后委托 `_resolve_live_bilibili_com` 回写 ctx 四字段，本函数不重复赋值。`PLATFORM_HOST` 登记 `"b23.tv"`、分发表B站条目之后新增 `(_match_host("b23.tv/"), _resolve_b23_tv)`（MID-04 契约：白名单每项必被某个 resolver 片段命中）。房间线程 `record_host` 保持 `b23.tv`：按 host 隔离的熔断桶把「短链解析失败」与桌面取流失败分开计数（与 `_resolve_hy_fan` 同判据）。与 hy.fan 同款**刻意不在准入层改写配置行**（跳转解析依赖网络，放主循环准入会把一次网络抖动放大成「配置行被注释/改写」）。
- **未动**：`spider.get_bilibili_room_info` / `get_bilibili_danmaku_info`、`stream.get_bilibili_stream_url`、弹幕采集（`src/platforms/bilibili.py`）、`CLEAN_URL_HOST_LIST`、`src/web_config.py`（Web 面板 `parse_url_config` / `normalize_url` 对 b23.tv 链接原样放行，录制侧统一归一）全部零改动；同日 `hy.fan` / `m.douyu.com` 两个并行工作包一行未动。
- **验证**：`pytest tests/test_b23_tv_dispatch.py tests/test_platform_dispatch.py tests/test_hy_fan_dispatch.py` **80 passed**（新增 22 条：`tests/test_b23_tv_dispatch.py` 21 条——四种形态归一根契约（spider 收到 `live.bilibili.com` 链接而非原始 b23 地址）、短码解析+二轮命中缓存（两轮只发一次解析请求）、解析失败 / 意外异常按未识别且 spider 零调用、路径段合法 / 非法（含全角数字）、落地页域与形态边界（视频页 / 自指短链 / 连字符拼接域 / 字母段拒绝）+ `test_platform_dispatch.py` `_DISPATCH_CASES` 1 条）；`compile_po.py --check` **860 条同步**；black / isort 对改动文件 unchanged。**变异验证 4/4 转红**（M-B23-1 摘路径段字符白名单 / M-B23-2 摘多级目录拒绝 / M-B23-3 摘落地页纯数字判定 / M-B23-4 摘归一化回写根契约；均「按行改写（改动行带 `MUTATION-` 标记）→ 跑真实用例转红 → 字节级还原断言一致」，与 hy.fan 同形的两行按附近锚点行消歧，零残留）。
- **真机验证（DoD 第 2 步，已执行）**：本机外网可达、目标房间在播。① DoD 指定脚本 `tests/test_bili_live_collector.py https://b23.tv/22747736 25` → **PASS**（`VERIFICATION_RESULT: {"platform": "bilibili", "status": "PASS", "messages": 18, "srt_bytes": 1402}`，b23.tv 链接直入弹幕采集链路、真实弹幕写入 SRT）；② 真实网络直调 `_resolve_platform_stream`：短码 `https://b23.tv/ZyQrgYf` 经真实 302 解析出房间 22747736（`anchor=不死鸟总监`、`is_live=True`、`title=新游戏 战争机器：E-DAY`、`actual_quality=OD`，弹幕参数 `room_id`/`token`/`buvid`/`host_list` 全齐），四种数字形态解析结果与短码逐项一致；非法形态 `https://b23.tv/` 与 `https://b23.tv/a/b` → 返回 None 且 error 日志点名原因（「路径为空，缺少房间号」「路径含多级目录，不是标准房间链接」）。
- **文档同源**：`README.md` / `README_EN.md`「已支持平台」各 +1 条B站链接形态说明（短码 302 解析与进程内缓存口径）；本条目（中英同步）。

| B站移动端分享短链（b23.tv）接入 | 改动 `main.py`（+b23.tv 平台节 4 个函数与缓存、`PLATFORM_HOST` +1 host、分发表 +1 条目）、`i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` 各 +2 条并重编 `zh_CN.mo`（860 条）、新增 `tests/test_b23_tv_dispatch.py`（21 用例）、`tests/test_platform_dispatch.py`（+1 条分派用例）；文档 `README.md` / `README_EN.md` 各 +1 条、本条目（中英同步）。一次性脚本 2 个（变异验证 + 真机驱动）均落仓库外 `%TEMP%`，收尾已删 |

### v4.5.0-dev (2026-10-03) — 斗鱼移动端链接（m.douyu.com）接入：准入白名单 + 分发表同表项复用 + 房间号提取归一（尾斜杠 / 查询参数 / http 协议）

> 用户口径：新增 `https://m.douyu.com/8751648` 支持，覆盖「房间号直接跟在路径后 / 带尾斜杠 / 带查询参数 / http 版本」四种形态；提取到房间号后**复用现有斗鱼录制流程**（拉流地址获取、清晰度选择、录制与保存），不重复实现；对无法识别、缺少房间号或房间号非法的链接返回清晰错误提示。设计阶段已确认两点口径：① 非纯数字房间号（字母号 / 个性域名）**保留**既有的移动端页面还原能力，还原不出数字才报错；② 路径里已是纯数字时**保持现状**仍抓移动端页面还原，不做「数字即跳过抓取」的快路径。

- **接手时的真实状态（先取证再动手）**：移动端链接此前**两处都进不去**。① `PLATFORM_HOST` 只有 `www.douyu.com`，而准入按 `url_host in PLATFORM_HOST` **精确 host** 匹配 → `https://m.douyu.com/8751648` 在读取 URL 配置阶段就被判「本行包含未知链接.此条跳过」并注释掉；② 分发表只写 `_match_host("www.douyu.com/")`，即便准入通过也会落到 `_resolve_unrecognized` 无限空转（与 SEV-2203 同一失败型：永不录制、不记 `record_error`、白占监控位）。两处缺一即不可用。
- **复用性结论（需求「现有流程能否直接复用」的答复）**：**可以，无需新增任何请求地址或字段**。链路上的三个接口（`https://www.douyu.com/betard/{rid}`、`https://www.douyu.com/lapi/live/getH5PlayV1/{rid}`、`https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption`）**只吃数字 rid**，`Referer` 恒按 `https://www.douyu.com/{rid}` 构造，与来源域名无关；而房间号还原用的 `https://m.douyu.com/{候选}` 本来就是移动端页面（实测 `https://m.douyu.com/8751648` 返回 `vike_pageContext`，`rid=8751648`）。真机取证见「验证」。
- **房间号提取归一（`src/spider.py`）**：新增两个可单测函数 `extract_douyu_rid_param()` / `extract_douyu_room_id()`，替换原两处整串正则。旧正则各有一个边界洞：`rid=(.*?)(?=&|$)` 未锚定参数边界（`?xyzrid=123` 会被误命中成房间号）；`douyu.com/(.*?)(?=\?|$)` 把尾斜杠与后续路径段一起带进房间号（`/8751648/` → `"8751648/"`、`/topic/x` → `"topic/x"`），于是 `betard` 请求拿不到 `room`，用户只看到「房间不存在」这类误导性结果。改走 `urlsplit` 后 scheme / 尾斜杠 / query / fragment 都在解析层剥掉，http 与 https、www 与 m 同一口径；无 scheme 输入按准入侧同一规则补 `https://`（否则首个非空段取到的是主机名）。
- **错误提示（需求第 1 点）**：路径无房间号 → `斗鱼链接缺少房间号: {masked_url}`；URL 畸形到 `urlsplit` 抛 `ValueError` → `斗鱼链接无法解析房间号: {masked_url}`；还原产物非数字 → `斗鱼房间号还原结果非数字: candidate={candidate} rid={rid}`（`betard` / `getH5PlayV1` 只认数字 rid，旧实现拿非数字直拼必然失败且无提示）。三条均为 `i18n.tr` 常量模板，链接入文案前过 `utils.mask_credentials`；四语目录各 +3 条并重编 `zh_CN.mo`（**856 条** = 键数 855 + 1 条头部空 msgid，`compile_po.py --check` 同步）。另：`rid` 查询参数只在**值是纯数字**时才作数，`?rid=abc` 回落路径首段（旧实现会直拼 betard）。
- **入口接入（`main.py`）**：`PLATFORM_HOST` 增 `m.douyu.com`；分发表斗鱼表项改 `(_match_host("www.douyu.com/", "m.douyu.com/"), _resolve_douyu_com)`——**共用同一个处理函数**，不新增分支。匹配器 `_match_host` 已按 `urlsplit` 的 `scheme://host/` 归一比对（M-03 口径），故 `https://example.com/m.douyu.com/8751648` 这类「路径里藏域名词」的地址不会被路由进斗鱼（已入回归锁）。
- **并行写入方（非本批，需留意）**：本批编辑期间另一工作包在 `main.py` 插入了虎牙移动端短链 `hy.fan`（表项位于 `_resolve_huya_com` 之后、`_resolve_douyu_com` 之前，`PLATFORM_HOST` 同批登记 `hy.fan`）。该插入把斗鱼表项从下标 4 挪到 5，`tests/test_platform_dispatch.py::test_resolver_table_priority_head` 的顺序锁因此转红——本批按**实际顺序**把该锁同步为前六项（`…_resolve_huya_com` → `_resolve_hy_fan` → `_resolve_douyu_com`）并补注「插入新表项会挪动其后下标，改顺序须同步改这里」。`hy.fan` 的实现与用例本批一行未动。
- **未动**：取流与画质链路（`stream.get_douyu_stream_url` / `spider.get_douyu_stream_data` / `get_token_js`）、弹幕链路（`src/platforms/douyu.py`）、`CLEAN_URL_HOST_LIST`（斗鱼本就不在其中）全部零改动；`scripts/douyin_live_recorder_standalone.py` 孪生副本**已核对 / 刻意不回灌**——其平台匹配用 `douyu\.com`（本就覆盖 m 子域）、房间号取 `url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]`（已处理尾斜杠与 query）、且已有「斗鱼房间号必须是纯数字」的显式错误，不存在本批对应的缺陷。
- **验证**：`pytest tests/test_douyu_url_resolution.py tests/test_platform_dispatch.py -q` **66 passed / 0 警告**；`black --check` 4 个改动文件 unchanged、`isort --check-only` 无重排；无参 `mypy` **192 source files 0 issues**；`compile_po.py --check` 856 条同步。**变异验证两处**（均「改写并带 `MUTATION-` 标记 → 跑真实用例 → 还原后比对 sha256 `f92a15b7…1a72` 一致」）：① 摘掉 `if not rid.isdigit():` → `test_non_numeric_resolved_rid_raises` 转红（`DID NOT RAISE ValueError`）；② `return segments[0]` 改 `"/".join(segments)`（退回「整段路径」旧口径）→ **首轮未转红**（用例只覆盖了单段路径，属测试缺口）→ 补 `https://m.douyu.com/8751648/extra` 多段用例后转红（`assert '8751648/extra' == '8751648'`），该用例已保留。全量 `pytest --cov=src` **3977 passed / 14 skipped / 0 failed、warnings summary 为空**（691.7s）；`scripts/check_coverage.py` **PASSED: All 46 module(s) meet coverage threshold**（`src/spider.py` 75.2%）；`scripts/run_gates.py` **10 条全部 PASS**（black 205 files unchanged / isort / 三遍 mypy 192 files 0 issues / check_annotations 202 文件、悬空引用 0 处 / compile_po --check / check_version / check_runtime_pins / check_skill_agents）。
- **时序说明（不粉饰）**：本批**首次** `run_gates.py`（04:0x）的 pytest 兜底报 rc=1——当时并行会话仍在写 `main.py`（其 `hy.fan` 改动在途）；该轮只记录了返回码、**失败清单未落盘**，故此处不逐条归因。并行会话收尾后全量 `pytest --cov=src` 复跑转绿，首次红按「在途编辑」理解但**未经单条取证**。
- **真机验证（DoD 第 2 步，已执行）**：本机外网可达。① 四种形态（`https://m.douyu.com/8751648`、`https://m.douyu.com/8751648/`、`http://m.douyu.com/8751648?rid=8751648`、`https://www.douyu.com/8751648`）解析结果逐项一致：`anchor_name=有鬼yougui`（该房当时未开播，`is_live=false`）；② 换在播房间 `https://m.douyu.com/5526219`（南波儿大魔王丶，`is_live=true`、`room_id=5526219`、标题「王者前十冲第一!」）跑完整链路 → `stream.get_douyu_stream_url` 返回 `flv_url` / `m3u8_url` / `record_url`（`huosa.douyucdn2.cn/live/5526219r…_4000.flv?wsAuth=…`）与 `quality` / `actual_quality`，**证明移动端链接与 www 链接走同一条取流链**。
- **文档同源**：`README.md` / `README_EN.md`「已支持平台」各 +1 条斗鱼链接形态说明（`-dev` 条目按既有约定不进 README 更新日志，发版时由 CODE_WIKI 提炼）；本条目（中英同步）。

| 斗鱼移动端链接接入 | 改动 `src/spider.py`（+2 个提取函数、替换 2 处旧正则、+1 处还原出口校验）、`main.py`（白名单 +1 host、分发表斗鱼片段 +1）、`i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` 各 +3 条并重编 `zh_CN.mo`、新增 `tests/test_douyu_url_resolution.py`（27 用例）、`tests/test_platform_dispatch.py`（+2 条分派用例 +1 条准入/反例锁 + 顺序锁按实际顺序同步）；文档 `README.md` / `README_EN.md` 各 +1 条、本条目（中英同步）。未产生一次性脚本（验证一律走 `python -c` 与内存变异，输出落在仓库外 `%TEMP%`） |

### v4.5.0-dev (2026-10-03) — 虎牙移动端短链（hy.fan）接入：准入白名单 + 分发表新 resolver + 短码 301 跳转解析归一（标准 / 尾斜杠 / 查询参数 / http 协议）

> 用户口径：新增 `https://hy.fan/` 支持（示例 `https://hy.fan/JbmwoV`），覆盖「房间号直接跟在路径后 / 带尾斜杠 / 带查询参数 / http 版本」四种输入形态；提取到房间号后**复用现有虎牙录制流程**（拉流地址获取、清晰度选择、录制与保存），保证移动端链接与已有 www.huya.com 链接行为一致，不重复实现；对无法识别、缺少房间号或房间号非法的链接返回清晰错误提示。需求第 3 点（现有流程是否依赖桌面页面 / 接口）的答复：**依赖，但无需新增任何请求地址或字段**——桌面链路（页面内联 `stream:` 对象 / `mp.huya.com` 小程序接口）只认 `www.huya.com/<房间号>` 形态，故本批在解析层先归一再委托，桌面侧零改动。

- **短链实测行为（设计前取证，2026-10-03）**：`https://hy.fan/JbmwoV` 为 **301 → `https://www.huya.com/30764624?source=android&shareid=…&hyaction=live…`**——短码不是房间号、必须跟随跳转解析；纯数字路径段（`hy.fan/30764624`）与短码形态解析结果同指一间。`hy.fan` 在此之前全仓零引用：`PLATFORM_HOST` 没有它 → 读 URL 配置阶段就被判「本行包含未知链接.此条跳过」并注释掉（与斗鱼批次记录的 SEV-2203 同一失败型，两处缺一即不可用）。
- **入口接入（`main.py`）**：`PLATFORM_HOST` 增 `hy.fan`；分发表新增 `(_match_host("hy.fan/"), _resolve_hy_fan)`，置于 `_resolve_huya_com` 之后（匹配片段互不重叠、无遮蔽；`test_resolver_table_priority_head` 的顺序锁由斗鱼批次按实际顺序同步为前六项——见斗鱼条目「并行写入方」，本批未动该锁）。
- **归一化与复用（需求第 1、2 点）**：`_hy_fan_path_segment` 取唯一路径段（空路径 / 多级目录 / 非法字符——含全角数字按 `isascii` 收紧——抛带原因的 `ValueError`）；纯数字段零网络直接归一 `https://www.huya.com/<段>`（覆盖四种形态）；非数字段视为短码 → `_resolve_hy_fan_room_segment` 走 `async_req(redirect_url=True)`（与 xhslink.com 短链解析同一契约：成功回最终落地 URL、失败回空串，按 `isinstance+非空` 收窄）→ `_huya_room_segment_from_landing` 要求落地 host 精确等于 `huya.com` 或 `.` 后缀、唯一 ASCII 字母数字路径段（自指短链域 / `evil-huya.com` 连字符拼接域 / 多段一律空串）→ 成功才写 `_HY_FAN_ROOM_CACHE`（进程内缓存：短链与房间映射稳定，幂等写、GIL 原子、条目上界为配置行数，监测轮不重复发 301）。归一后委托 `_resolve_huya_com` 回写 ctx 四字段，拉流/画质/弹幕/录制与桌面链接同一条链路；跳转落地若是主播自定义字母号，沿用 app 路径 ProfileRoom 反查数字房间号的既有链路，不二次实现。
- **错误提示（需求第 1 点）**：`虎牙移动端链接缺少有效房间号，本轮跳过: {record_url} - {reason}`（reason：URL 无法解析 / 路径为空，缺少房间号 / 路径含多级目录，不是标准房间链接 / 房间号含非法字符）与 `虎牙移动端短链解析失败，本轮跳过: {record_url} - {reason}`（reason：未获取到跳转地址 / 跳转地址不是虎牙直播间 / `{type_name}: {err}`）。两条均为 `i18n.tr` 常量模板、链接入文案前过 `utils.mask_credentials`；四语目录各 +2 条并重编 `zh_CN.mo`。
- **已知边界（刻意不修，非生产路径）**：`tests/test_huya_live_collector.py` 把 URL **直喂** `spider.get_huya_app_stream_url`（绕过 main.py 解析层）时，短码形态会在 ProfileRoom 反查处失败（app UA 下 301 落地页正则未命中 → `Please use "https://www.huya.com/+room_number"`）→ 脚本按 `SKIP` 退出。生产链路中 resolver 先行归一、spider 永远只收到数字房间链接，spider 侧不感知 hy.fan，故 `src/spider.py` 不改；`scripts/douyin_live_recorder_standalone.py` 孪生副本同此边界、未回灌。
- **未动**：`src/spider.py` / `src/stream.py` / 弹幕链路（`src/platforms/huya.py`）/ `CLEAN_URL_HOST_LIST`（query 在归一时丢弃，无需进清洗名单）零改动；`record_host` 仍取 `hy.fan`——按 host 隔离的熔断桶把「短链解析失败」与桌面链接的取流失败分开计数，语义更准，不回填 `www.huya.com`（与 `_resolve_b23_tv` 同判据）。
- **验证**：新增 `tests/test_hy_fan_dispatch.py` **21 用例**全绿 0 警告（四形态归一根契约——spider 收到 `https://www.huya.com/30764624` 而非原始 hy.fan 地址；短码解析 + 第二轮缓存命中恰一次请求；解析失败 / 非 ValueError 意外异常按未识别且 spider 零调用；落地页域族与形态边界）；**变异验证 1/1 红**（改坏归一化赋值行为 → 6 用例转红 → 字节级还原断言一致、`MUTATION-hyfan1` 零残留）；无参 `mypy` **192 source files 0 issues**；`basedpyright` **0 errors / 0 warnings**；覆盖率门禁 46 模块全过阈值（总覆盖 84.90%）。
- **真机验证（DoD 第 2 步，已执行，读数时刻 2026-10-03 04:22-04:24）**：本机外网可达、目标房在播。① 真网直调 `main._resolve_platform_stream("https://hy.fan/JbmwoV", None, "原画")` → `platform=虎牙直播`、`anchor_name=Horcus`、`is_live=True`、`flv_url` 250 B / `m3u8_url` 251 B（`hs.flv.huya.com` / `hs.hls.huya.com` 带签名 CDN 直链）、弹幕三元组 `{ayyuid: 35184700893343, topSid: 1239543859098, subSid: 1239543859098}`；② `https://hy.fan/30764624`（纯数字形态）解析结果逐项一致（证明短码与数字形态同指一间、同链路）；③ `python tests/test_huya_live_collector.py https://www.huya.com/30764624 20`（归一后链接走既有 app 路径 + collector）→ **WARN**（`VERIFICATION_RESULT: {"platform": "huya", "status": "WARN", "messages": 0, "srt_bytes": 0}`，连接正常、该时段无弹幕）；④ 直喂原始短链的 collector 跑法见上「已知边界」→ `SKIP(room_offline 标记实为反查失败)`。交回用户：该时段无弹幕，如需 SRT 字节级读数请在弹幕活跃时段用归一后链接复跑。
- **文档同源**：`README.md` / `README_EN.md`「已支持平台」各 +1 条虎牙链接形态说明（`-dev` 条目按既有约定不进 README 更新日志，发版时由 CODE_WIKI 提炼）；本条目（中英同步）。

| 虎牙移动端短链接入 | 改动 `main.py`（+hy.fan 平台节：4 个函数与 1 个缓存、`PLATFORM_HOST` +1 host、分发表 +1 表项、`src.async_http` 导入 +1 名）、`i18n/zh_CN.po` + `en_US.json` + `en_GB.json` + `zh_TW.yaml` 各 +2 条并重编 `zh_CN.mo`（860 条读数含同日 b23.tv 并行批次）、新增 `tests/test_hy_fan_dispatch.py`（21 用例）；文档 `README.md` / `README_EN.md` 各 +1 条、本条目（中英同步）。变异验证以 `python - <<PY` 内存字节备份改写还原完成，零一次性脚本落盘 |

### v4.5.0-dev (2026-10-03) — Linux arm64（aarch64）ffmpeg 支持三段落地：发布矩阵四平台 + 运行期官方直下新模块 + GHCR 多架构镜像发布链

> 用户口径：三个范围项（发布链产出 arm64 包 / 运行期 Linux 原生直下 / Docker 镜像 arm64 可用）已于 2026-10-02 逐条批准，完整性口径选「官方哈希优先 + 降级 TOFU」、实现落点选方案 A（新建 `src/ffmpeg_linux_download.py`）、`docker-compose.yaml` 的镜像名**不改**、镜像发布仅 `v*` tag 触发。规格 `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`，计划 `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg-plan.md`。

- **成因（先坐实「已经有什么」）**：Linux arm64 的**取数与钉定早已就绪**（`build_exe._FFMPEG_DOWNLOAD_URLS` 的 `linuxarm64-gpl-9.0.tar.xz` 月末标签、`_PINNED_RUNTIME_SHA256` 的 `linux-arm64` 双槽、`RELEASE_RUNTIME_KEYS` 含该键、递归按名取件），缺的是另外三件事——**谁构建它**（发布矩阵只有 `windows-latest`/`ubuntu-latest`/`macos-latest`，arm64 包从未出现在 Release 里）、**运行期能不能自己拿到已校验的原生二进制**（`install_ffmpeg_linux()` 只有 `yum`→`apt` 两条路，都要求 root 且要求发行版仓库里有 ffmpeg 包；`ffmpeg_master_download.py` 是 Windows 专属）、**镜像是否真发得出 arm64 层**（`Dockerfile` 的 ffmpeg 走 apt 天然随架构，但仓库当时没有任何镜像发布工作流）。
- **S1 发布矩阵（四平台）**：`.github/workflows/build-release.yml` 的 `matrix.include` 新增 `- os: ubuntu-24.04-arm` + `platform: linux-arm64`，**插在 `ubuntu-latest` 之后**（位置即契约：`check_runtime_pins._runtime_matrix_keys()` 按 `os:` 行出现顺序返回键列表，`tests/test_check_runtime_pins.py::test_workflow_matrix_and_test_constant_stay_in_sync` 断言逐序相等而非集合比较）；两个 Linux 步骤的 `if:` 由 `matrix.platform == 'linux'` 改家族判定 `startsWith(matrix.platform, 'linux')`，取反那步写成**带引号**的 `if: "!startsWith(matrix.platform, 'linux')"`（YAML 把行首 `!` 当 tag 指令，无引号实测 `ParserError`）；`Verify artifact completeness` 的 `-lt 6` → `-lt 8`（4 平台 ×（lite+full）），描述发布矩阵的平台计数措辞按实况更正为四平台：`.github/workflows/build-release.yml` 头部/章节注释与 `build_exe.py:425` 由 S1 那批改；2026-10-03 文档同轮另更正 `build-release.yml:567` 的 Release 正文模板（用户可见）、`AGENTS.md` 的「打包与冒烟测试语义」与「release-guard」两条、本文件中英两版的目录树注释与 CI/CD 章、`docs/agent-reference/project-structure.md` 的目录树。`build_exe.py` 里指 **OS 家族数 3**（`linux-x64` 与 `linux-arm64` 同族共用一支 `.tar.xz` 构建、共用 `-version` 探针）的措辞，以及带日期的历史读数，一律不改。四平台 / 8 zip 的实况口径唯一登记在 `AGENTS.md`「CI / workflow 约定」的「发布矩阵为四平台」条目，其余处只引用不复述。`scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY` 新增 `"ubuntu-24.04-arm": "linux-arm64"`（**唯一登记点**，未登记标签走 `sys.exit(2)`、发布链在 prepare 即断），`tests/test_check_runtime_pins.py` 的 `_MATRIX_KEYS` 同步为四键。产物名 `DouyinLiveRecorder-v<版本>-linux-aarch64-{lite,full}.zip`——架构段取 `platform.machine().lower()` 的实际值 `aarch64`，**不是** `arm64`。
- **S2 运行期 Linux 原生直下**：新增 `src/ffmpeg_linux_download.py`（476 行，LF-only）+ `tests/test_ffmpeg_linux_download.py`（**46 用例**，`--collect-only -q` 实测 `46 tests collected`）。裁决面是规格 §4.1 的完整性真值表四格：digest 取到且匹配 → 安装；取到但不符 → 拒装、删包、error 级指引人工核对；取不到 + `FFMPEG_MASTER_ALLOWED` 假（默认）→ 拒装；取不到 + 开关真 → TOFU（有基准比基准、无基准首次记账并安装，warning）。三条不变量：默认路径必须已校验、基准存在却读不出即拒装（SEV-2222 同口径）、形态先于哈希（先判是不是 tar.xz 再算哈希再解压）。实现要点：`_linux_arch()` 只认 `arm64`/`aarch64` 为 ARM、其余保守回 `linux64`；`_api_release_url()` **从下载 URL 反解** repo/tag（不新增第二个 URL 常量，杜绝「下载走新标签、取 digest 走旧标签」）；digest 过 `^[0-9a-f]{64}$` 形状关且**不带 `.lower()`**（大写形态判「取不到」= fail-closed）；`_install_binaries()` 是**两趟**（先全量递归定位 `ffmpeg`/`ffprobe`、缺件即返回且 dest 侧零改动，两件齐了才 mkdir + copy + 补执行位），回归锁 `TestBinaryLayoutDiscovery::test_missing_companion_leaves_no_half_install`；`extractall(filter="data")` 显式传参（MI-26 同源）；顶层入口**失败一律回 False 绝不抛出**。TOFU 基准文件名带资产名（`_ffmpeg_linux.<asset_stem>.tar.xz.sha256`），换标签即换基准。开关由 `install_ffmpeg_linux()` 以 `master_allowed=_master_source_allowed()` **传参**——新模块不读环境变量，否则与 `ffmpeg_install` 成循环依赖。接线在 `install_ffmpeg_linux()` 的**函数末尾统一出口**（包管理器仍是首选，apt/yum 天然给原生 arm64 且带发行版签名链）；同轮删除了「`apt update` 非零即在 apt 块内 `return False`」的早退、把 `apt install` 收进 `else:` 分支——无 root 的 Debian/Ubuntu arm64 上 `apt update` 失败是常态，而这类机器正是本模块的目标人群，早退等于给他们留一条不进兜底的路径。`tests/test_ffmpeg_install.py`：`DOWNLOAD_SOURCES` 新增 `api.github.com` = `官方哈希`、`DOWNLOAD_MODULES` 新增 `src.ffmpeg_linux_download`（AGENTS「关键约定」#10 的两处缺一即锁红），**`github.com` 仍是 `TOFU`**（master-latest 那条路还在，两条不得合并）；新增 6 条接线/顺序/实参行为锁（含「包管理器成功时不得触达直下」优先级锁与「`FFMPEG_MASTER_ALLOWED=1` 时开关确实传到兜底」），该文件 **116 用例**（接线前基线 110 → 114 → 116）。i18n 四目录各 +20 条新模板并重编 `.mo`（`compile_po.py --check` 读数 853 条 = 键数 852 + 1 条头部空 msgid，2026-10-02）。
- **S3 GHCR 多架构镜像**：新增 `.github/workflows/docker-publish.yml`（210 行，LF-only）+ 结构锁 `tests/test_docker_publish_workflow.py`（**12 条**）。口径：仅 `push: tags: ["v*"]` 触发；`prepare` 从 `GITHUB_REPOSITORY_OWNER` 派生镜像名并**小写化**（GHCR 强制小写命名空间）；`docker-build-amd64`(`ubuntu-latest`) 与 `docker-build-arm64`(`ubuntu-24.04-arm`) **原生双 runner 各出一层**、只推分架构临时 tag `:vX.Y.Z-amd64`/`-arm64`，并各显式 `provenance: false`（不写时动作按仓库可见性代拼 `--attest`，公开仓库落 `mode=max`，会把不可运行条目混进对外清单）；两个构建 job 的 `steps.build.outputs.digest` **提升为 job 级 `outputs:`**，`docker-manifest` 用 `docker buildx imagetools create` 按**两个 digest**（不是分架构 tag）一次合成 `latest` 与版本 tag。**刻意不用单 job QEMU 交叉**（构建期 apt + pip 全量安装在模拟下是整层重活）；凭据只有自动 `GITHUB_TOKEN`，`permissions` 顶层 `contents: read`、`packages: write` 只在三个推镜像的 job 上按需授予；`cancel-in-progress: false`；job 内零安装步骤（结构锁反向钉住，故无 `.github/actions/retry` 适用点）。第三方动作走浮动大版本（触发源是维护者推的 `v*` tag，属可信输入，同 MIN-17 的区分线）。
- **活体取证（`api.github.com` 与发布钉定值逐字相等）**：`api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27` 的 `assets[].digest` 对照 `build_exe._PINNED_RUNTIME_SHA256`——linux64 `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0.tar.xz` = 126,600,656 B / `sha256:182c1b509720e939bb47bfb47dc29cc0c298640401128e3dce8627d10707eb5a`、linuxarm64 同名 `...-linuxarm64-gpl-9.0.tar.xz` = 108,761,296 B / `sha256:e2dd447c8a47849c5812d87e54a47b20ae0f3603d38989440f4a5fe1af8755b1`，两 arch 均 `api digest == release pin: True`（读数时刻：2026-09-27 首次登记于 `docs/agent-reference/measured-evidence.md`，**2026-10-02** 由本计划复核逐字相等）。口径提醒：该通道属**同源一致性校验而非来源认证**（与产物同平台、异服务，与 gyan.dev 的 `.sha256` 同级，MIN-2258 同一措辞），注释与日志都不得写成「已认证来源」。
- **未动**：`install_ffmpeg_windows`/`install_ffmpeg_mac`/`_windows_arch`/`download_ffmpeg_official` 一行未改（Windows 侧零改动）；`docker-compose.yaml` 与 `Dockerfile` 未动（compose 的 `image: ihmily/douyin-live-recorder:latest` 与 GHCR 名**不同源是刻意分工**，走 `pull_policy: build` 就地构建，MIN-18 不变）；`build_exe._ALLOWED_HOSTS` 未动（`github.com` 已在，运行期侧的 `api.github.com` 属 `DOWNLOAD_SOURCES` 那一把锁，两者互不替代）；`pyproject.toml` 的 `[tool.mypy].exclude` **不改**（见下条「已知缺陷」）；`scripts/douyin_live_recorder_standalone.py` 孪生副本**已核对 / 刻意不回灌**——`grep -n "install_ffmpeg\|download_ffmpeg"` 零命中，该副本不含 ffmpeg 安装链，只有 `should_prepend_bundled_ffmpeg_dir` 的同名 PATH 让位判据，本次未改其语义。
- **已知缺陷（本轮以代偿口径通过，留独立工作包）**：`[tool.mypy].exclude` 的裸 `"ffmpeg"` 是**路径子串**正则，使 `src/ffmpeg_*` 与 `tests/test_ffmpeg_*` 对「不带路径的 mypy」门禁失明——实测新增这两个文件前后无参 `mypy` 同为 `189 source files`（显式传它们才 `checked 2 source files`），次日加入名字不含 `ffmpeg` 的 `tests/test_docker_publish_workflow.py` 后读到 `190 source files`。本轮类型面结论由「显式传参 `mypy <具体文件>`（新增两文件 `Success: no issues found in 2 source files`；同族存量 `tests/test_ffmpeg_install.py` 有 5 条既有错误——`exit-return` ×2（`:436`/`:458`）+ `func-returns-value` ×3（`:514`/`:737`/`:739`），五条**全在该测试文件**，`src/ffmpeg_install.py` 单跑为 `Success: no issues found in 1 source file`；本轮新增代码 0 条）+ `basedpyright`（不带路径 `0 errors, 0 warnings, 0 notes`，两个新文件 `filesAnalyzed: 2`/`errorCount: 0`）」给出；**「mypy 全绿」不得当作这批文件的门禁证据**。修 exclude 形态属独立工作包、待维护者决策，细则已写回 `AGENTS.md`「已知坑 · 类型检查、注释与静态门禁」。
- **验证**（各单元 scoped 自跑，全部发生在其自身最后一次编辑之后；全量门禁由收尾单元统一执行，故本条不构成「全量门禁已绿」的声明）：`pytest tests/test_ffmpeg_linux_download.py -q -W error` **46 passed / 0 警告**；`pytest tests/test_ffmpeg_install.py -q -W error` **116 passed / 0 警告**；`pytest tests/test_docker_publish_workflow.py -q -W error` **12 passed / 0 警告**；邻居文件未被牵连 `test_ffmpeg_linux_download + test_build_exe + test_test_hygiene` = **682 passed**（46 + 105 + 531，`tests/test_test_hygiene.py` 的 R8 全仓变异标记扫描同时作磁盘级反向见证）；`pytest tests/test_check_runtime_pins.py -q` 20 passed；`check_runtime_pins.py` 结构模式与 `--strict` 均 rc=0、矩阵打印 `windows-x64, linux-x64, linux-arm64, macos-arm64`；`PYTHONUTF8=1 python scripts/check_annotations.py` 全部通过（2026-10-03 读数：213 个 Python 文件、悬空引用 0 处）；`compile_po.py --check` 853 条同步、`extract_i18n_strings.py` 缺失 0 条且无 `[不一致]` 行；两份 YAML 均 `yaml.safe_load` 读通（矩阵四支、三个 `if:` 表达式、docker 工作流 4 个 job 名齐全）。**变异取证逐单元计数**（Task 1 一次：`linux-arm64/ffmpeg` 改回占位 → `--strict` rc=1 且该键进入失败集合，反向证明它已进门禁；Unit A 11 条全部 ≥1 红；Unit B 首轮 2 条 + 修复轮 3 条；Unit 6 首轮 3 条 + 修复轮 5 条），全部「内存字节备份 → 改写（改动行带 `MUTATION-` 标记）→ 跑真实用例 → `finally` 还原并断言 `read_bytes()` 相同」，零残留。唯一一条本机存活的变异是 Unit A 补跑的 `M-A1-CHMPOFF`（删掉 `target.chmod(...)` 执行位补回）——Windows 上 tar 成员 mode 一律回报 `0o666`、`S_IXUSR` 不回报，该格在非 POSIX 宿主收敛为存在性断言，**执行位判据由 Linux CI 承载**，不得当成已锁。
- **未执行 + 交回用户（DoD 第 2 步）**：`SKIP(本机 Windows x86_64，无法产出也无法运行 arm64 产物)`。① arm64 真机录制两分支需在 aarch64 容器（如 `arm64v8/debian:trixie`，不装 ffmpeg）跑：其一保留 apt 但以非 root 运行（`apt update` rc≈100 → 应看到 `Failed to update package lists using apt` → 官方直下 → 安装并验证 → True），其二遮蔽 yum 与 apt；② `ubuntu-24.04-arm` 是否计入本账号免费额度只能首跑裁定（官方页无定价口径），配额不足时的退化方案（矩阵保留 linux-arm64 但仅 `workflow_dispatch` 启用）**需另行批准**；③ GHCR 包可见性设为 public 是一次性人工动作，`GITHUB_TOKEN` 不会代为放开，`docker pull ghcr.io/<owner>/douyin-live-recorder:latest` 的匿名可达性在首次推送前未经核实；④ 本改动**不触碰录制链/选源/ffmpeg 参数/平台解析**，collector 真机脚本（`tests/test_{bili,douyin,douyu,huya,twitch}_live_collector.py`）无可归因的增量项，故本轮不写「真机已验证」的表述。
- **文档同源**：`AGENTS.md` 三处写回——「CI / workflow 约定」+2 条（发布矩阵四平台与 runner 映射单点登记、多架构镜像口径）、「已知坑 · 构建产物、依赖与运行时基线」+2 条（两份 URL 物理副本与 `api.github.com` 口径、运行期直下的两条不得回退形态）、「已知坑 · 类型检查、注释与静态门禁」+1 条（mypy exclude 子串失明）；`README.md`/`README_EN.md` 补 linux-aarch64 产物清单与 GHCR 拉取方式（compose 说明原样保留）；本条目（中英同步）；规格「九、回滚方案」的 S2 一句按实况更正（见下条）。2026-10-03 评审修复轮（Unit 7 Fix round 1）在同批补齐：上条列出的其余残留落点（`AGENTS.md` 两条平台计数措辞改按「发布矩阵为四平台」条目引用、本文件中英两版的目录树注释与 CI/CD 章矩阵枚举 + zip 计数、`docs/agent-reference/project-structure.md` 目录树、`build-release.yml:567` 用户可见的 Release 正文模板仅改文案、`README.md`/`README_EN.md` 的自动安装路径穷举枚举与「自动下载路径唯一性」表述限定到 Windows）；两处本条目自写的事实错误（产物名平台段的归因由 `platform.system()` 改为 `build_exe.make_zip()` 的 `sys.platform` + `{"win32": "windows", "darwin": "macos"}` 归一，mypy 既有 5 条错误的归因文件由 `src/ffmpeg_install.py` 改为 `tests/test_ffmpeg_install.py`）；以及规格「九」S1 的回滚序号描述（改按 `os` 标签点名）。

- **规格回滚口径更正（被实现证伪）**：`docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md` 原写「S2 回滚 = 新模块整体删除 + `install_ffmpeg_linux()` 去掉那一行调用」——接线轮（2026-10-03）除那一行调用外还删了 `apt update` 失败的早退并把 `apt install` 收进 `else:` 嵌套，只删调用点会留下「update 失败仍落统一出口」的行为差，故回滚必须一并还原；正文已改正并留一行带日期历史注。

| Linux arm64 ffmpeg 支持 | 新增 `src/ffmpeg_linux_download.py`（476 行）、`tests/test_ffmpeg_linux_download.py`（46 用例）、`.github/workflows/docker-publish.yml`（210 行）、`tests/test_docker_publish_workflow.py`（12 条锁）；改动 `.github/workflows/build-release.yml`（矩阵/`if:`/`-lt 8`/注释计数）、`scripts/check_runtime_pins.py`（映射 + 注释）、`build_exe.py`（仅注释措辞）、`src/ffmpeg_install.py`（import + 统一出口兜底 + `apt update` 早退改 `else:` 嵌套）、`tests/test_ffmpeg_install.py`（两张注册表 + 6 条接线锁，共 116 用例）、`tests/test_check_runtime_pins.py`（`_MATRIX_KEYS` 四键 + 未登记标签样本改判）、`i18n/zh_CN.po`+`en_US.json`+`en_GB.json`+`zh_TW.yaml` 各 +20 条并重编 `zh_CN.mo`；文档 `AGENTS.md` +5 条、`README.md`/`README_EN.md` 产物与镜像口径、`CODE_WIKI.md`/`CODE_WIKI_EN.md` 本条目、`docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md` 回滚段更正。本单元未产生一次性脚本 |

### v4.5.0-dev (2026-10-02) — `CODE_REVIEW_2026-10-02` 整改收尾：补齐 L-04/L-05 两项 + 修正整改自引入的 3 处红与 3 处运行期缺陷

> 用户口径：读取 `docs/worklog/CODE_REVIEW_2026-10-02.md`，逐条提取全部问题项、定位文件与代码位置后逐一修复；遵循现有风格、不做超范围重构；描述模糊或无法定位者说明原因、不得猜测性修改；收尾跑构建/测试/静态检查并输出「已解决清单 + 改动文件 + 验证结果 + 需人工确认遗留项」。

- **接手时的真实状态（先取证再动手）**：报告所列各项**已有 63 项在上一轮会话落地**（源码内带 `（2026-10-02）` 归因注、`tests/` 带同名回归锁），工作树尚未提交、且收尾门禁未跑完——`run_gates.py` 停在第一条 black（4 个文件待重排），其后续 9 条从未执行。本会话因此以「逐项核对是否真落地」为主线，而非重复改一遍。
- **报告计数更正（写文档前实测）**：报告头部与 §3.2 矩阵记「中等 17 / 合计 66」，但 §5 实际枚举 M-01…M-18 共 **18** 项——矩阵「工具/配置/通知基建」行把 M-01 漏计（该行标 3、实为 4）。逐项清点口径：严重 2 + 中等 18 + 轻微 47 = **67**。
- **本会话补的两项报告项**：① **L-04** `main.py` 的 `platform_cookie` 映射缺两个强制直下平台（`only_flv_platform_list = ["shopee", "花椒直播"]`）——二者的 `[Cookie] shopee_cookie` / `huajiao_cookie` 在 main.py 已有读取点并透传给解析函数，却不进映射，于是同一份用户 Cookie 在「解析」与「探针 / ffmpeg 录制头 / 直下」两条路口径不一。实测缺口规模：**已声明 50 个 `*_cookie` 全局、映射内 23 个、缺 27 个**；本批只补报告点名的两个，其余 25 个**刻意不补**——逐平台是否需要登录态取流未经现网抓包确认，盲加等于改变 25 个平台的出站请求头。回归锁 `tests/test_platform_dispatch.py::test_forced_direct_download_platforms_carry_cookie`（AST 不变量锁：两个直下平台必须在映射内且值绑定 `*_cookie` 变量而非空串字面量；带「映射整体丢失即红」的反向见证）。② **L-05** 收尾——模块级 `pre_max_request` / `record_danmaku_args` / `seen_urls` 三个死全局上一轮已删声明，但 `main.py` 仍留 `seen_urls = _seen_urls` 一行；因 `main()` 的 `global` 清单里没有 `seen_urls`，该行只绑定一个无人读取的函数局部名，随删除并把同处「四个集合整体换位」的失实计数改正为三个。
- **修正整改自引入的缺陷（4 类，均非报告项）**：① `src/spider.py` 的 L-10 补日志写成 `except Exception:` 却引用 `type(e)`/`{e}` —— 走到该分支即 `NameError`，「补一条 debug」把兜底变成抛点；改 `except Exception as e:`（mypy 三遍同报，是本轮唯一由类型检查抓到的运行期缺陷）。② `main.py` 的 M-02 把 `url_data`（`tuple[str, str, str]`）整串递给只接受 `str` 的 `mask_credentials`，内部全 `re.sub` → `TypeError` 会穿透「获取失败重试」这条 print；改为 `mask_credentials(str(url_data))`，模板与目录 msgid 的 `{url_data}` 占位符保持不动。③ `gui.py` 的 L-39 把 `_log_queue_has_data = False` 从「渲染成功后」上移到「取空队列即清」，修掉了哨兵单独取空时的永久空转，但同时把 M-15 锁住的「渲染中途抛错 ⇒ 链不断」判据打穿（`test_log_flush_chain_rearms_when_render_raises` 红）；现保留 L-39 的无条件清除，在 `_schedule_log_flush` 的 except 分支复位 `has_data=True`，令 finally 照常续期、下一轮取空后自然转休眠（只多一个空闲节拍，不重新点燃空转）。④ `src/spider.py` 的 M-05 按报告建议改成裸真值 `if is_private`，其注释自称「对 `"0"`/0/False 均语义正确」**是错的**——`bool("0")` 为 True，API 以字符串 `"0"` 下发时公开房间会被误判私有并整轮报错；改走全仓统一口径 `parse_config_bool(is_private, False)`（bool 短路 / int 非零 / `"0"`·`"false"`·`"否"` token 归一，无法识别按非私有放行），注释里的错误结论按「注释约定」例外原地改正并留一行 `[历史注]`。回归锁 `tests/test_spider_platforms.py::TestPopkontvIsPrivateParsing`（bool/int/字符串 10 格矩阵）。
- **另两处门禁红**：`src/room.py` 的 L-13 删除 `get_live_room_id` 后把文件尾 `__main__` 演示块的输出改成 `print("return sec_user_id:", sec_uid)`，该常量串进入 i18n 提取面但未入目录 → `test_runtime_templates_covered_by_catalog` 恒红；按既有先例（`return web_rid:` 同族四条目录齐备）在 `zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml` 各 +1 条并重编 `.mo`（833 条 = 键数 832 + 1 条头部空 msgid，`compile_po.py --check` 同步）。`tests/test_regression_2026_09_22_gui.py` 的 `assert len(runs) == 4` 是 L-40 删除两段不可达兜底过滤器后的陈旧条数——写死条数不表达判据、只会跟着每次合法增删漂移，改为「非空反向见证 + 逐个 `capture_output`/禁 text 形态断言」。
- **未动**：M-10 的行为侧（`_is_same_origin` 是否信任 `Sec-Fetch-Site`）——报告明确「交维护者裁决修行为还是修文档」，上一轮已走文档路线（`web_config.py` 注释更正 + `web.py` 警告文案补该约束），本会话不擅自扩大；带「待确认」标记的 L-30 请求体上限取值、L-44 TOFU 口径、M-05 的真实字段类型仍需现网抓包；报告 §8.3 的三条结构性建议（脱敏矩阵测试化 / standalone 回灌清单机检 / 内存界承诺对齐）属新建设计，未纳入本批；§2.3 建议删除的未跟踪杂散文件 `markdown-DX-TNHnc.js` **已被 `git add` 进索引**，删除属用户决定，见本条「残留」。
- **验证**（读数时刻 18:0x–18:4x，本批最后一次代码编辑之后；其后仅有文档改动，无门禁或用例消费文档正文）：`python scripts/run_gates.py` **10 条全部 PASS**（black 先对本批 4 个文件实排后复检；isort；`mypy` 无参 189 files 0 issues + `--platform linux` + `--platform win32` 三遍同干净；`check_annotations.py` 203 个 Python 文件、悬空引用 0 处（正是这条兜住 L-05 删全局后的调用点）；`compile_po.py --check` 833 条同步；`check_version.py`；`check_runtime_pins.py`；`check_skill_agents_consistency.py` 5 个 Skill 一致，套件末次跑到该条时汇总行未落盘，另以单跑 `rc=0` 复证）。**终态：`run_gates.py --keep-going` 输出「门禁全绿：10 条全部通过（耗时 173.9s）」，其末尾 pytest 兜底亦 `[PASS] pytest 3841 passed 且 warnings summary 为空 (408.2s)` → 整脚本 rc=0**。同树早一次跑法曾因 `pytest` 返回 1 让这条兜底判失败（整体 rc=1），但那不是 10 条门禁中任何一条红；兜底随后转绿本身也反证了那批 subprocess 失败属顺序/句柄噪声而非代码。工具版本与 `ci.yml` consts 同值口径未复核（本机 `python` 为用户级 3.14 core，非 `.venv`），故「本地全绿」不等同 CI 同版本验证。覆盖率：按既有做法把 `COVERAGE_FILE` 指到 `%TEMP%` 跑 `pytest --cov=src`（不带 `--cov-report=json`，已跟踪的 `coverage.json` 与文档读数不被本轮噪声改写），再跑 `python scripts/check_coverage.py` → **PASSED: All 46 module(s) meet coverage threshold**（rc=0）。全量 `pytest --cov=src`：本批改前 **24 failed / 3792 passed / 15 skipped**，本批改后 **30 failed / 3786 passed / 15 skipped**（两次总数同 3831），收尾终跑 **21 failed / 3818 passed / 15 skipped**（总数 3854，+23 全属并行工作包，见「残留」③）。改前的 3 条**确定性红**（i18n 目录覆盖、gui 日志刷新链、gui run 条数锁）在终跑失败清单中已消失（`grep -c` 读数 0）；余下失败只落在 `test_build_exe`/`test_ci_retry_action`/`test_notify`/`test_notify_script_guard`/`test_regression_2026_09_22_standalone`/`test_stop_recording_vbs` 这六个子进程族文件，判定依据是这些文件**逐个独跑全绿**（build_exe 105 / ci_retry_action 12 / notify 4 / notify_script_guard 18 / stop_recording_vbs 11 / regression_2026_09_22_standalone 49 / run_gates 43 / regression_2026_09_22_gates 27），且失败堆栈一律停在 `subprocess._make_inheritable` 的 `WinError 6/50`（句柄继承）、无一条是断言失败；实测给 shell 重定向 stdin（`< /dev/null` 与 `< 某文件`）**不能**消除。变异验证两处，均「内存字节备份→改写→跑→`finally` 还原并断言 `read_bytes()` 相同」：裸真值形态 → `TestPopkontvIsPrivateParsing` 字符串两格转红（2 failed / 8 passed）；删 `shopee` 映射键 → L-04 锁转红（1 failed）；还原见证 True，`MUTATION-` 全仓零残留。行尾形态：本批 11 个改动文件逐文件复核，`main.py`/`gui.py`/`src/spider.py` 保持纯 CRLF；两份测试文件曾由 heredoc 追加产生 44/18 条孤立 LF（AGENTS「三个盲点」第 3 条，black 与 AST 双隐形），已按原形态归一并复测 lone-LF=0；`core.autocrlf=true` 说明「索引存 LF / 工作树是 CRLF」并不矛盾。
- **未执行 + 交回（DoD 第 2 步）**：真实 URL 端到端增量跑**未执行**。本机外网可达（实测 `live.douyin.com` DNS 解析 + HTTP 200），但本批补的 L-04（shopee / 花椒直下）、M-05（popkontv 私有房）与上一轮落地的 SR-01（内网分片正文）均需**活房间 + 平台账号**才能取到有意义结论，而 `config/URL_config.ini` 是用户真实房间清单、跑 `python main.py` 会立即发起录制与外网写盘，属需授权副作用。请用户在有活房间时手跑并回填本条目：`python tests/test_douyu_live_collector.py <脱敏 URL> 60`（斗鱼/虎牙覆盖 HLS 分片探测与 `codec=h265` 链）、`python tests/test_huya_live_collector.py <脱敏 URL> 60`；shopee / 花椒 / popkontv 三个平台仓库内**没有** collector 脚本，需先按「测试编写强制约定」的双模脚本四条模板约束补一个，或按报告 L-04 的验证方法抓包比对 `Cookie` 请求头是否落到探针与 ffmpeg。此情形下不得宣布完成定义 1→6 全部达成。
- **残留（交回用户，代理不得代删）**：① `markdown-DX-TNHnc.js`（报告 §2.3 判定为误落仓库根目录的 VSCode Markdown 语法产物、§8.3 建议删除）**已在 git 索引中**（状态 `A`），删除已被跟踪意图的条目属用户决定，本批仅列出不动。② i18n 目录侧孤儿 msgid `"return web_rid:"`（L-13 删除其唯一使用点后成为无引用条目，四目录各一条）——AGENTS「i18n 扫描盲区」已注明孤儿 msgid 不会变红、需人工核对，删除会连带改动 CODE_WIKI/README 已引用的键数读数，故留待用户决定。③ **本工作树存在并行写入方（非本会话、非本批）**：收尾期间另一工作包正在同一树里实现「Linux 原生 ffmpeg 直下安装器」——未跟踪新文件 `src/ffmpeg_linux_download.py` 与 `tests/test_ffmpeg_linux_download.py`（19 用例）、并改动 `src/ffmpeg_install.py` / `tests/test_ffmpeg_install.py`（工作区较索引多 21 行）；全量用例总数从 3831 增至 3854 的 **+23 全部属该并行批次**（19 + 4），本批一行未动这些文件。**[历史注]** 本条初版曾把这两处 mtime 变更记成「同字节重写、成因不明」——那是我自己的取证错误：`git diff HEAD -- <未跟踪文件>` 对不在 HEAD 的文件恒空，我把「无差异」当成了「内容未变」。教训：判定「内容是否被改写」必须用 `git status --short` 的跟踪状态（`??` 即未跟踪）＋ `git ls-files --others --exclude-standard` 的未跟踪清单，不能只看 `git diff` 空不空。连带影响：`check_annotations.py` 因该并行新增的 `tests/test_ffmpeg_linux_download.py` 注释密度 11.0% 低于 13.0% 阈值而判红（本批不代修，改了会与对方互相覆盖），且覆盖率门禁首跑按「数据陈旧」拒评 rc=2（`src/` 出现更新 mtime）。故本批「门禁全绿」的读数**只指向本批最后一次编辑之后的时刻**，其后合并边界仍以 CI 为准。

| 整改收尾 | 本批改动 11 个文件：`main.py`（L-04 两个直下平台键 + L-05 死赋值删除 + M-02 实参形态）、`gui.py`（L-39 与 M-15 交界的 has_data 复位）、`src/spider.py`（L-10 `as e` + M-05 `parse_config_bool` + 1 处 import）、`tests/test_spider_platforms.py` +1 类 10 用例、`tests/test_platform_dispatch.py` +1 helper +1 锁、`tests/test_regression_2026_09_22_gui.py` 条数锁改反向见证、`i18n/zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml` 各 +1 条并重编 `zh_CN.mo`（833 条）、本条目（中英同步）。未产生一次性脚本（验证一律走 heredoc 与内存变异，门禁/测试日志落在仓库外的 `%TEMP%`/`/tmp`）；`logs/.pyc_stamp` 等运行期产物按红线不动 |

### v4.5.0-dev (2026-10-02) — 新增启动期陈旧字节码缓存清理 `src/startup_cleanup.py`（版本+内容哈希哨兵、白名单扫描根、开关默认开）

> 用户口径：新增「启动前自动清理 `__pycache__`」功能；设计阶段在四个候选触发策略中选定「版本哨兵触发，只清一次 + 引入配置开关默认开」，并批准按 1→8 条落地。

- **成因**：源码直跑形态的升级方式是「解压覆盖」，复制工具常保留源文件的 mtime；若被改模块的字节数恰好也没变，CPython 基于 (mtime, size) 的 timestamp 失效判定会认定缓存仍新鲜并**静默沿用旧 .pyc**（表现为「改了代码却还在跑旧逻辑」，且门禁与日志都不指向缓存这一层）。同时「每次启动整树删」在本机实测要每轮多付 345 ms 全量重编译（同集合 51 个文件），且 CLI / GUI 录制子进程 / Web 三入口共用同一批 `src/` 缓存、会互删对方刚生成的成果——故触发条件收敛为「源码或版本真的变过」。
- **改动**：① 新增 `src/startup_cleanup.py`：扫描根走**正向白名单**（程序目录顶层 + `src/` 下直接含 `.py` 的目录，本机实测命中 4 处），只回收其下 `__pycache__/` 内的 `.pyc`/`.pyo`（逐文件处理后再收目录，目录里的非字节码残留一律原样保留并告警——宁可留不净，也不越界碰不认识的内容）；判定基线 = `sha256(相对路径 + 文件字节)` 与版本号，落 `logs/.pyc_stamp`（`版本|哈希` 两字段，写入经同目录临时文件 + `os.replace` 原子落盘，刻意不复用 `src.config_io._atomic_write_text`，以免把 GUI 进程接进 `main.file_update_lock` 录制引擎锁体系）；`_IS_FROZEN` 与开关关闭两条路径一律零 I/O（不遍历、不哈希、不碰哨兵）；基线缺失或读失败按「无法证明缓存新鲜」处理为一轮回收，写失败仍然执行并 warning（退化成用户手工删缓存的语义，不静默失效）。② `main.py` 在 `utils.remove_duplicate_lines(url_config_file)` 之后接线（+7 行 = 1 行 import + 1 空行 + 2 行位置说明 + 3 行调用）：该位置 `src.*` 已导入完毕，本轮启动不受影响，一处接线同时覆盖 CLI、GUI 拉起的录制子进程与 Web 三条链。③ 配置三处同值：开关键 `是否启动时清理陈旧字节码缓存(是/否)` 走 `read_config_bool`（默认「是」），`config/config.ini` +1 行（UTF-8 BOM 与整文件 CRLF 原样保留）、`README.md` +3 行 / `README_EN.md` +4 行配置块。④ 5 条新 `tr()` 模板落 `zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml` 并跑 `scripts/compile_po.py` 重编 `.mo`（四目录键集合 831↔831 一致；`.mo` 头部 832 条 = 键数 + 1 条头部空 msgid）。⑤ `AGENTS.md`「关键约定」新增第 15 条，把「白名单根」与「必须内容哈希」钉成硬约束并附变异验证判据。
- **未动**：`build_exe.py` 的打包前字节码剔除与 `RUNTIME_ARTIFACT_DIR_NAMES`（本功能把哨兵放进已在三处排除口径里的 `logs/`，不新增第四处）；`tests/`、`scripts/`、`.venv/`、`node/`、`ffmpeg/`、`downloads/`、`logs/` 不在回收范围内；`scripts/douyin_live_recorder_standalone.py` 孪生副本**刻意不回灌**——已核对不属于「sync_http opener 白名单 / `-protocol_whitelist` / ffmpeg 终止链 / `config_bool` 布尔口径 / MID-49 签名编码」五类必须同步范围，且该副本是单文件发行形态、其字节码落在 `scripts/__pycache__`，正在白名单之外。
- **验证**：TDD 先跑出 RED（`ModuleNotFoundError: No module named 'src.startup_cleanup'`）→ 实现后 `tests/test_startup_cleanup.py` 9 passed / 0 警告。三条变异全部被抓：① 扫描根改成从程序目录起全树递归 → `test_purges_only_whitelisted_roots` 转红（**首版用例是真假绿**：越界位置里没放 `.py`，全树递归也碰不到它们；补成「含 `.py` 但不在白名单根」与「在白名单树内但不含 `.py`」两类分轴才真正锁住）；② 内容哈希退化为 (size, mtime) → `test_same_size_same_mtime_content_change_is_detected` 转红；③ 去掉「目录须含 `.py`」判据 → 同 ① 转红。三次变异均按「内存字节备份→改写→跑→`finally` 还原并断言 `read_bytes()` 相同」单进程执行，还原见证 True、`MUTATION-` 标记零残留。真实仓库树函数级实测：run1 判定触发、回收 4 个目录释放 1,758,820 B、耗时 12.9 ms，`.venv`/`tests`/`scripts` 下缓存逐个存活；run2 源码与版本未变 → `triggered=False` 零动作、7.8 ms；run3 开关关闭 → 0.0 ms 零 I/O。全量 `pytest --cov=src` **3803 passed / 14 skipped / 3 failed**，3 项全落在工作树在途 WIP（`gui.py` 的 AST 结构锁 2 项 + `src/room.py:261` 遗留调试 print 使 i18n 目录覆盖门禁红 1 项），这两个文件本批一行未动；`src/startup_cleanup.py` 覆盖 88%（111 句 / 13 未覆），高于未登记模块下限 `GLOBAL_FLOOR=50%`。`run_gates.py --keep-going`：isort / check_annotations / compile_po --check / check_version / check_runtime_pins / check_skill_agents_consistency 六条 PASS；black 与三遍 mypy 四条 FAIL 全部指向在途 WIP——black 的 4 个文件是 `main.py`/`src/spider.py`/`tests/test_web_api.py`/`scripts/douyin_live_recorder_standalone.py`，其中 `main.py` 在本批改动前既有 4 个 hunk、改动后仍 4 个且无一命中本批新增行；mypy 三遍同为 3 错、均不在本批文件。本批两个新文件单独跑 black + isort + mypy 全绿、行尾纯 LF 无混存。
- **未执行（诚实边界）**：DoD 第 2 步的三入口完整启动真机跑**未执行**——本机 `config/URL_config.ini` 是用户的真实房间清单，跑 `python main.py` / GUI / Web 会立即发起实际录制与外网请求，属需用户授权的副作用；本批不触碰录制链路 / 选源 / ffmpeg 参数 / 平台解析，按「完成定义」第 2 步属豁免范围，改以上述「真实树两轮 + 开关三轮」实测替代。**交回用户**：下次正常启动后在 `logs/PlayURL.log` 查到一行「源码或版本已变化，已清理 N 个字节码缓存目录（释放 X KB）」即为接线生效（本条为 INFO 级，按 `src/logger.py` 的分级落盘约定进 `PlayURL.log`，不在 `streamget.log`；本批实测已在该文件取到两行，最近一条为 `2026-10-02 14:50:24.920 | 源码或版本已变化，已清理 2 个字节码缓存目录（释放 108 KB）`）。
- **残留（交回用户，代理不得代删）**：验证期间由本功能正常写入的 `logs/.pyc_stamp`（现值前缀 `v4.5.0-realcheck-2`）仍在盘上；它位于运行期产物目录，按「风险控制·清理范围越界」红线与项目 Hook 的 R-CLEAN-SCOPE 规则不由代理处置（实测该次尝试被当场拦下）。留着的效果是下次启动多回收一轮缓存（一次性、无害）；如需即刻归零，请用户自行处置该文件。

- **本机测试面噪声（本批取证时发现，非本批引入）**：同一命令在全量运行下的失败数在 3↔24 间摆动，成因是**导入顺序**而非代码：`tests/test_ci_retry_action.py`/`test_build_exe.py`/`test_notify.py`/`test_notify_script_guard.py`/`test_stop_recording_vbs.py`/`test_regression_2026_09_22_standalone.py` 六个文件单独跑固定红 20 条，而把任一「先导入过 `src` 侧模块」的测试文件排在它们之前即 **0 红**——对照实验用了本批从未触碰的 `tests/test_config_bool.py`（261 passed）与本批新文件（208 passed）两种前置，结果同形，故不得把这条红算到本批头上；失败输出里 `WinError 6`（子进程继承已关闭 stdin）出现 23 次，与 `docs/agent-reference/session-learnings.md` 既记的同族环境坑一致。留待后续：这六个文件应自带「导入前置」或改为显式给子进程 `stdin=`，属独立待办。

| 运行期与启动链 | 新增 `src/startup_cleanup.py`（111 句）与 `tests/test_startup_cleanup.py`（9 用例）；`main.py` +7 行接线；`config/config.ini` +1 键；`README.md` +3 / `README_EN.md` +4 行；`AGENTS.md` 关键约定 +1 条；i18n 四目录各 +5 条并重编 `.mo`；`docs/agent-reference/session-learnings.md` +3 条经验；本条目（中英同步）。未产生一次性脚本（验证一律走 `python -c` 与 heredoc 内联）；唯一残留见上一条 |

### v4.5.0-dev (2026-10-02) — 前端 `.mjs` 登记约束补上仓库侧完备性锁：新增 `tests/test_ci_frontend_registration.py`（清单↔目录双向差集 + 自举锁）

> 用户口径：给「新增前端 `.mjs` 必须登记进 CI」这条已有约束补上随仓库分发、对任何贡献者与 CI 都成立的完备性锁，做法收敛为一条确定性比对（枚举 `tests/frontend/*.mjs`，与 ci.yml「Gate frontend tests not skipped」点名的入口求差集，差集非空即失败）；复用既有双文件约定与既有钉法（参照 `tests/test_pre_commit_config.py` 的清单↔配置双向钉），不新增第二份门禁清单，不动 `python_build`/`node_version` 常量。

- **成因**：这条约束此前只有两处载体——`AGENTS.md`「测试」条目的文字，与 `scripts/agent_hook_guard.py` 的 PostToolUse 规则 P-MJS-REGISTER；后者位于 `.qoder/` 本地工具目录（AGENTS.md「项目级 Hooks / Commands」明写不随仓库分发、不得进镜像），因此对其它贡献者与 CI 本身都不成立：未装 Hook 的人把 M-28 那类「包装写了、清单没加、回归锁在正常 CI 里从不执行」的漂移重新入库时，CI 依旧全绿。
- **改动**：① 新增 `tests/test_ci_frontend_registration.py`（5 条用例）：前置守卫（该步骤唯一存在 + 清单可解析出 node-id + 目录枚举非空 + 映射机制非空，防「扫不到东西的绿灯」）、正向差集（每个 `.mjs` 必须被某个**已登记**包装引用）、反向差集（入口的包装存在、用例函数已定义、引用的 `.mjs` 仍在盘上）、自举锁（本锁自身入口必须在清单里）、门禁自检（在 `tmp_path` 合成最小仓库、只改本模块三个路径全局，证明正反向差集真会报）。包装↔用例本体的映射取自包装 AST 里的路径常量而不是同名巧合——现存四个包装有两个位于 `tests/` 顶层且与 `.mjs` 不同名，照抄 Hook 的同名判据会把既有合法形态判红。② `ci.yml` 该步骤的 node-id 清单补一条 `tests/test_ci_frontend_registration.py::test_every_frontend_mjs_is_registered`，并在步骤上方追加四行成因注（只增不改）。③ `AGENTS.md`「测试」条目补一句：完备性已由该用例机检、本机 Hook 只是即时反馈通道不能替代。
- **未动**：`python_build`/`node_version` 常量、该步骤的「有 skip 即红」判据与其它 job、`tests/frontend/*.mjs` 用例本体、Hook 的 P-MJS-REGISTER 规则（保留为写入当下的即时反馈），以及全部门禁命令清单（`run_gates.py` 仍从 AGENTS.md 解析，未新增并行项）。
- **验证**：目录侧探针实测——落一份未登记的 `tests/frontend/tmp_probe_unregistered.mjs` → `test_every_frontend_mjs_is_registered` 单独转红并逐字点名该文件（1 failed / 4 passed），删除后 5 passed；清单侧变异按「内存备份→改写→跑→字节还原并断言相同」单进程执行，从 node-id 清单里摘掉本锁入口 → `test_lock_itself_runs_inside_the_frontend_gate` 转红、还原见证 `RESTORED_BYTE_IDENTICAL: True`。新文件 black / isort / mypy 单文件全绿且行尾纯 CRLF。全量 `run_gates.py` 的 black/mypy 失败项全部落在工作树在途 WIP（`main.py`/`src/spider.py`/`tests/test_web_api.py`/`scripts/douyin_live_recorder_standalone.py`）；全量 pytest 3782 passed / 14 skipped / 11 failed，11 项为上述 WIP（i18n 模板 `return sec_user_id:`、gui `_schedule_log_flush`）与本机 bash 入口被 WSL 服务禁用（0x80070422）所致，无一项指向本批。本批不触碰录制链路/选源/ffmpeg 参数，DoD 第 2 步真机验证豁免。

| 文档与门禁 | 本批为测试资产 + CI 清单改动：新增 1 个 `tests/*.py`、`ci.yml` 加 1 行 id 与 4 行注释、`AGENTS.md` 补一句、本条目（中英同步）；探针与一次性验证脚本均已删除，零残留 |

### v4.5.0-dev (2026-10-02) — CI typecheck 门禁补齐平台双跑：增跑 `mypy --platform win32`，win32 目标首次在合并边界参与类型检查（纯 CI / 门禁改动，零运行期变更）

> 用户口径：把已声明为门禁的「双跑」补齐到合并边界——在 typecheck job 里按与现有 linux 目标对称的方式增跑一次 win32 目标，同一 `[tool.mypy].files` 范围、同样不带路径参数；不收窄检查范围、不新增并行清单、不动 pytest/node 常量。

- **成因**：`AGENTS.md`「格式化命令（门禁唯一基准）」长期声明 mypy 平台双跑（裸跑 + `mypy --platform linux`），但 CI typecheck job 只跑一条裸 `mypy`，ubuntu runner 上默认即 linux 目标——win32 侧门控分支（`if sys.platform == "win32":` 内的 `ctypes.windll`、`subprocess.STARTUPINFO` 等）只在 Windows 开发机被顺带检查，合并边界从不验证，构成「本地绿、CI 无从判 win32」的检查面缺口。
- **改动**：① `ci.yml` typecheck job 拆为两步——`Run mypy (linux target)`（裸 `mypy`，ubuntu 上即 linux）+ 新增对称的 `Run mypy (win32 target)`（`mypy --platform win32`），同范围、均不带路径参数，未改 job 级 `if` 过滤条件。② `AGENTS.md` 门禁 bash 块补第三行 `mypy --platform win32`（与 `--platform linux` 对称），使 `run_gates.py` 在任一主机都同时覆盖 linux 与 win32 两侧；同步 mypy 专节「平台符号门控双跑」条与 run_gates 说明条，口径单一、不留第二份事实源。
- **未动**：pytest / node 相关常量、`ci-summary` 的 needs 清单与 `failure/cancelled` 判据、检查范围（`[tool.mypy].files`）——`typecheck` 仍作为一个整体 job 被 `ci-summary` 依赖，被路径过滤时（含新增步骤）整体 skip 视为通过，口径不变。
- **验证**：本机 mypy 2.3.1（与 CI consts 钉定值同值）对 `[tool.mypy].files` 全量 186 文件跑三遍——裸 `mypy`（本机 win32）、`--platform linux`、`--platform win32`，三者输出**逐行完全一致**（`Compare-Object` 空差），证明 win32 目标与 linux 判定面相同、不与任何既有 `# type: ignore` 冲突（无「一平台必需、另一平台多余」型 ignore）。三遍同现的 3 个错来自工作树在途 WIP（`main.py`/`src/spider.py`）、两平台一致、与平台无关，不属本批范围。`run_gates.py --list` 解析出含 `mypy --platform win32` 的完整清单；`ci.yml` YAML 合法性 + `ci-summary.needs` 含 `typecheck` 复核通过；回归锁 `tests/test_pre_commit_config.py`（7 passed）、`tests/test_run_gates.py`（42 passed / 1 skipped）不受影响。本批不触碰录制链路/选源/ffmpeg 参数，DoD 第 2 步真机验证豁免。

| 文档与门禁 | 本批为纯 CI / 门禁配置改动：改 `ci.yml` typecheck job + `AGENTS.md` 门禁块与两处说明条 + 本条目（中英同步），零 `.py`/前端资产改动；无新增一次性脚本 |

### v4.5.0-dev (2026-10-02) — 全工作区代码审查（产出 `docs/worklog/CODE_REVIEW_2026-10-02.md`）：8 工作包逐文件深审 + Mimosa 深扫逐类裁断，严重 2 / 中等 17 / 轻微 47

> 用户口径：对本工作空间全部源代码（Python/JavaScript/Node.js 等，排除 node_modules、dist、build）全面审查，重点排查代码质量、潜在缺陷、安全漏洞与逻辑错误，逐文件记录并按严重程度分类成正式报告。

- **报告**：[`docs/worklog/CODE_REVIEW_2026-10-02.md`](CODE_REVIEW_2026-10-02.md)（审查记录通配符既有 `.dockerignore` 排除，不入镜像）。8 个并行深审工作包覆盖 main.py / gui.py / spider.py / 选源调度 HTTP / 弹幕 / Web 前后端 / 基建 / 构建安装链 / standalone 孪生 / tests 风险面，66 项发现全部带行号与修复建议。
- **两项严重（均行级复核证实，属「防线接线/回灌缺口」而非「防线缺失」）**：SR-01 `stream_select.py` 的 `_probe_hls_segment` 对正文派生地址命中内网闸后仍 `return True` 维持候选可达（与同函数 WP-J 注释自述矛盾），内网目标可经被劫持播放列表交 ffmpeg；SR-02 standalone 探针 opener 白名单含 `HTTPRedirectHandler`、重定向逐跳不复检，主线 2026-09-30 补的 hop-guard 未回灌独立发行版。
- **实测复现**：`mask_credentials` 对 B 站 `SESSDATA`/`bili_jct` 与抖音 `sessionid_ss`/`sid_tt` 原样放行（M-01，关键约定 #11 同族新实例）；`httpx.InvalidURL` 直继 `Exception`（M-06 异常集缺口成立）。
- **交叉证据**：`basedpyright` 0 error / 0 warning / 0 notes；Mimosa deep 扫描（`scan-2026-10-01T18-57-00.175Z-21bb8f2f1ff5`，40 项原始告警）逐类裁断 **0 项新增确认漏洞**、3 项降信息级（run_gates `shell=True` 受控输入、海秀/LiveMe 平台匿名票据、依赖情报 1 包）；tests/ 抽查无 MUTATION 残留、无真实凭据、无过宽 mock。
- **后续行动**：报告第 8 章 P0 五项（两严重 + 两脱敏 + node 启动崩溃防线）、P1 分批、P2 顺手收敛；三条结构性建议（脱敏键型矩阵测试化 / standalone 回灌清单机检 / 「内存有界」承诺与实现对齐）。

| 文档与门禁 | 本批为纯文档产出：新增 `docs/worklog/CODE_REVIEW_2026-10-02.md` + 本条目（中英同步），零代码改动；按「完成定义」豁免：第 1 步门禁不适用（无 `.py`/前端资产改动）、第 2 步真机验证不适用（不触碰录制链路/选源/ffmpeg 参数）、第 3/5 步不适用（无回归锁改动、未产生一次性脚本） |

### v4.5.0-dev (2026-10-02) — Harness 资产新增：项目级 Hook 执行体 `scripts/agent_hook_guard.py` + `/dlr-dod` 命令入口

- **触发**：better-harness 复核指出 AGENTS.md 的高频手动流程只有 prose 约束、无生命周期资产承接（判据靠每次会话自觉执行）。用户要求「为高频手动流程创建项目级 hooks 或 commands 资产」，验收口径定为「至少一个资产存在 + 触发条件与 AGENTS.md 约束一致」。（本次调用未携带 `better-harness-fix-output` 机器回调，故不往历史 findings.json 写修复记录。）
- **改动**：① 新增 `scripts/agent_hook_guard.py`：从 stdin 收 Qoder Hook 事件 JSON，以退出码 2 拦截。`PreToolUse`（Bash）三规则——`R-PIP-BULK`（批量重装 venv 依赖，只拦 `--force-reinstall` 与 `--ignore-installed`+`-r`，二级单包补装放行）、`R-CLEAN-SCOPE`（删除语句目标命中运行期产物目录或 `scripts/`，`-notmatch`/`-Exclude` 排除式不误伤，语句按 `&&`/`||`/`;`/换行切分而管道不切）、`R-WIPE-SCOPE`（无 `-Include`/`-name` 过滤面的递归通配删除与 `git clean -f*`）；`PostToolUse`（Write/Edit）三规则——`P-MUTATION`（变异标记残留，对 black/mypy/注释检查三面隐形）、`P-LINE-ENDING`（`.py` 同时出现 CRLF 与孤立 LF，即整文件重写静默翻转的指纹）、`P-MJS-REGISTER`（`tests/frontend/*.mjs` 未登记 ci.yml 的 node-id 清单，M-28 同类）。拒绝消息只给规则短 id 与命中目录名，不回显命令原文；脚本异常或不认识的事件形态一律 fail-open。
- **改动（续）**：② 资产接线：`.qoder/settings.json` 的 `hooks.PreToolUse`（matcher 盖 Bash）与 `hooks.PostToolUse`（matcher 盖 Write|Edit|SearchReplace）均指向该脚本；新增 `.qoder/commands/dlr-dod.md`（`/dlr-dod`）只做 DoD 1→6 入口，委托 `scripts/run_gates.py` 与 `scripts/check_coverage.py`，不复制门禁参数。两项均位于 `.gitignore`/`.dockerignore` 已忽略的 `.qoder/`，不随仓库分发、不得进镜像。③ `AGENTS.md`「项目级 Skill」章后新增「项目级 Hooks / Commands（生命周期资产）」表与两条口径。④ 新增 `tests/test_agent_hook_guard.py` 33 用例：行为锁（拦与放行面双向）+ 一致性锁（受保护目录集合 == AGENTS.md「运行期产物目录」枚举）+ CLI 契约（stdin JSON → rc 2/0、不认识的事件 fail-open）+ 资产接线锁（`.qoder/` 缺失时 skip，不冒充仓库门禁）+ 内存式变异验证四组（不落盘、不留标记）。
- **附带修正**：`scripts/check_skill_agents_consistency.py`（前序会话遗留的未跟踪脚本，已是门禁第 9 条）此前让 `black --check .` 恒红；本次按 black 口径重排，改动前后 `ast.dump` 的 sha256 同为 `ea18a7f57727710e`，逻辑零改动。
- **验证**：`python scripts/run_gates.py` 的 9 条全部 [PASS]（含 `mypy` 无参 186 文件 0 issues、`mypy --platform linux`、`check_annotations.py`、`check_skill_agents_consistency.py` 5 个 Skill 条目一致）；`pytest tests/test_agent_hook_guard.py tests/test_test_hygiene.py` 552 passed / 0 warnings（R8 全仓扫描曾抓到本脚本注释里的变异标记字面量，已按自指规避改写）；Hook 实跑取证：批量重装命令 rc=2 拦下，AGENTS.md 两条官方收尾清理命令与 `python scripts/run_gates.py` rc=0 放行，`--self-test` rc=0（六类样例）；本仓改动文件行尾均保持纯 CRLF。**全量 `pytest` 在本代理 shell 下不可靠**：同一条命令两次跑出 22/17 条失败，移出本次新增两文件后同样跑出 9 条失败（与保留时同集合），成因是子进程继承已关闭 stdin（`OSError WinError 6`）与 `bash` 解析到 Windows 存根（`0x80070422`），属环境限制、非代码回归；因此 `run_gates.py` 末尾的 pytest warnings summary 兜底报 rc=1 未能作为结论。本次不触碰录制链路/选源/ffmpeg 参数，DoD 第 2 步真机验证豁免。

### v4.5.0-dev (2026-10-02) — 4.4.0 文档定稿：双语 CODE_WIKI 20 处标题 v4.4.0-dev → v4.4.0 + README 双语 v4.4.0 条目补缺五项

- **触发**：用户「版本文档同步」任务：读取 CODE_WIKI 的 4.4.0-dev 完整更新日志按四类归纳，写入 README 的 v4.4.0 条目，并把版本号 4.4.0-dev 统一为 4.4.0。README 双语在 2026-10-01 已建 v4.4.0 条目（彼时 -dev 标题刻意未改），本批是该决策的显式反转 + 条目补全。
- **改动**：① `CODE_WIKI.md` / `CODE_WIKI_EN.md` 各 20 处 `### v4.4.0-dev` 标题统一为 `### v4.4.0`（仅版本号段逐字替换，日期与正文不动；v4.3.0-dev/v4.5.0-dev 不在范围不动）。② `README.md` / `README_EN.md` v4.4.0 条目逐条比对后补五项缺漏：标题与摘要由「三点」扩为「四点」补 HEVC 死锁根治；🐛 节首插「抖音原画 HEVC 房『本轮无可用源』死锁根治」（三规则叠加根因 + `flv_url_list` 备选 + `E2E_RESULT: CURED`）；✨ 节补「h265 候选按保存格式放行 + HLS 静默丢弃零源观测告警」；📦 节补「urllib3 下限 2.7.0 → 2.8.0（CVE-2026-97687/97688/97689）」；🛠️ 节补「两处测试面修复」（singleflight Linux CI 假红补 POSIX 打桩、`test_notify` 墙钟余量改由生产常量推导）并给 AGENTS 条目补「三条门禁口径修正」。③ 读数更正：pytest 3690 → **3721**（10-01 终态）、覆盖率总 85% → **84.9%**（coverage.json 实测）、i18n 键数 808 补「终态 809」、🧪 节补 10-01 hevc 原画房三态真机 PASS。
- **验证**：四文件行尾纯 CRLF 保持（双语 README 各 +5 行、LF-only 仍为 0）；全仓 grep `4.4.0-dev` 残留 0；双语条目六小节（✨/🐛/⚠️/📦/🛠️/🧪）逐节对称、新增 bullet 各 5 条相等；纯文档改动，无门禁消费 README/CODE_WIKI 正文，按 DoD 豁免只跑受影响面（无）。

### v4.5.0-dev (2026-10-02) — 重算签名脚本钉定表四条：pre-commit end-of-file-fixer 的尾字节漂移

- **触发**：用户运行 pre-commit 后，`end-of-file-fixer` 给 `src/javascript/{crypto-js.min.js, x-bogus.js, haixiu.js, liveme.js}` 尾部各追加一个换行——`utils._check_js_hash` 按**原始字节**（rb）求 SHA256 对比钉定表，尾字节变化即四条全部失配：默认形态每次执行这些脚本打「与钉定值不符」告警（x-bogus 即抖音签名链），`DLR_JS_STRICT_HASH=1` 时直接拒绝执行；migu.js 本就带尾换行、未被改写，钉定值仍匹配。`test_utils.py` 的 JsPinTable 三用例只锁键集 / 存在性 / 表与目录双向相等、不比对实际哈希——pytest 全绿挡不住这类漂移（三面盲区之外的第四类）。
- **改动**：用户在「回退文件 / 给钩子加 exclude / 重算钉定表」三方案中拍板**重算**；`src/utils.py::_JS_SHA256_EXPECTED` 四条按当前原始字节更新，附日期化重算注释（旧值以截断形态留档，migu.js 未动）。钩子此后幂等（文件已带尾换行），重算是稳定终态而非临时掩盖。
- **验证**：以真实表对盘上 5 份脚本逐一求 SHA256 全部匹配；`pytest tests/test_utils.py` 81 passed / 1 skipped；black 定向检查 unchanged；旧哈希前缀全仓 grep 仅剩 utils.py 历史注一行；`src/utils.py` 行尾形态不变（纯 CRLF）。

### v4.5.0-dev (2026-10-02) — 版本推进 4.4.0 → 4.5.0 + dev 依赖新增 pre-commit：全仓元数据同步与派生生成物再生成

- **触发**：`pyproject.toml` 两处事实源改动：`[project].version` 4.4.0 → 4.5.0；`[project.optional-dependencies].dev` 新增 `pre-commit>=3.6.0`（配套根目录 `.pre-commit-config.yaml`，pre-commit 钩子定义）。
- **同步面**：`AGENTS.md` 版本行 + 「开发 / 构建 / GUI 依赖」枚举（六条 → 七条）；`docker-compose.yaml` 头部 `.env` 示例 `APP_VERSION=4.4.0` → `4.5.0`、Web 服务注释「FastAPI/uvicorn」→「Starlette/uvicorn」（fastapi 已随 v4.4.0 阶段2 移除，注释残留旧事实）；`requirements.txt` 头部注释的 .dev 枚举补 pre-commit；`.dockerignore` 新增裸模式 `.pre-commit-config.yaml`（开发工具配置，与 scripts/ 同类不进镜像）；`CODE_WIKI.md`/`CODE_WIKI_EN.md` 头部版本行。**README 双语零改动**：dev 安装指引已是 `pip install .[dev]` 单源形态（指向 extra 本体、不枚举包名，dev 组增删不产生漂移），v4.4.0 更新日志条目属历史记录不动；运行时依赖仍为 21 条（pre-commit 是 dev extra，不入 requirements.txt）。
- **生成物**：`uv.lock` 与 `DouyinLiveRecorder.egg-info` 经 `python scripts/sync_metadata.py` 再生成，未手改派生文件：uv.lock 根包 4.5.0 + dev extra 增 pre-commit 4.6.2（现装解析落点，满足 >=3.6.0 下限）及其传递依赖 7 包（cfgv 3.5.0 / distlib 0.4.3 / filelock 4.0.8 / identify 2.6.20 / nodeenv 1.11.0 / python-discovery 1.6.1 / virtualenv 21.14.2），既有钉定版本零变动；egg-info PKG-INFO 除版本与 dev extra 外还回灌了 README 长描述的当前内容（`language =` 留空、循环时间 60、HLS 排除示例虎牙、https 录制/录制弹幕示例值等——README 此前已改而旧 PKG-INFO 未再生成，`sync_metadata --check` 只对版本与依赖清单、不比对长描述，故上轮对账未暴露）。
- **验证**：`sync_metadata.py --check` OK（uv.lock / egg-info 均 4.5.0）；`check_version.py` PASS（main / web_api / Dockerfile 动态消费方全 OK）；`pytest tests/test_regression_2026_09_22_gates.py` 27 passed；`git diff` 复核 uv.lock 仅根包版本 + 新增包节点、无既有钉定漂移。

### v4.4.0 (2026-10-01) — h265 候选按保存格式放行（TS/MKV/MP4 可直拷 HEVC）+ HLS 配置静默丢弃的零源观测告警

- **触发**：同日上一条目（原画 hevc 房死锁根治）交付时遗留的两项候选改进，用户拍板实施（「放宽并补观测」）。
- **改动**：① `src/stream_select.py` 新增 `_h265_copy_format_supported()`——按 main 的热更新全局 `video_save_type` 判定当前保存格式的容器能否直拷 HEVC：TS(mpegts)/MKV(matroska)/MP4 三个 muxer 支持（main.py 选中 h265 地址时强制转 TS 是同一事实）；FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展、仓库口径不支持）、MP3/M4A 纯音频（装不下视频轨）、域外/缺失取值保守判不支持。h265 过滤从「无条件剔除」收窄为「不支持直拷时剔除」，TS 用户解析原画 hevc 房时 h265 FLV 主候选直接进常规序列参与探针；`_is_h265` 与候选序列注释里「h265 无法 copy 录制」的已证伪整段表述按注释约定改正并压为带日期历史注。② `main.py` 的 h265→TS 强制块加同一口径守卫：保存格式已是 TS/MKV/MP4 时不再接管、不再打「use TS format instead」告警（否则 TS 用户每轮一条误导告警）；FLV/纯音频形态维持原强制语义。③ 无源结论前新增观测告警：m3u8 候选被 HLS 配置（全局开关/HLS采集排除平台）整组静默剔除且本轮最终无可用源时，点名成因、候选条数与恢复开关指引——这是此前唯一「零日志」的选源成因（同日死锁房排查盲区：有 FLV 兜底时早退告警不触发、序列里也看不到 m3u8 踪影）；选中源的轮次不打。i18n 四目录同步登记 1 条新 msgid（zh_CN.po 尾部新分区 + PO-Revision-Date 推进；en/en_GB 「」转双引号；zh_TW 术语对齐採集/清單/丟棄）并重编 zh_CN.mo（810 条 = 809 键 + 头部）。
- **回归锁**：`tests/test_stream_select.py` 新增 h265×保存格式双矩阵（TS/ts/MKV/MP4 放行且首个选中 h265 主候选；FLV/MP3/M4A音频/webm/空串 剔除并落到 h264 备选，均断言 h265 零探针）、`_h265_copy_format_supported` 判定矩阵 11 格（大小写/空白/域外/None/int）与缺失全局保守回退、无源观测告警正反 2 条（失败轮必打且恰 1 条、健康轮零告警）；`tests/test_main_fixes.py` 两条 h265 选源用例随语义收窄显式钉保存格式并留历史注；`tests/test_stream_select.py` 的 `test_excluded_platform_h265_flv_not_switched_to_hls` 同步钉 FLV。变异验证：判定反转（MUTATION-H265RELAX）24 条转红、观测告警条件置恒假（MUTATION-HLSOBS）正例转红，均当轮字节级还原、残留 grep 为 0。
- **验证**：`pytest --cov=src` 3720 passed / 14 skipped / 1 failed——`tests/test_notify.py::test_run_script_timeout_kills_process` 以 4.04s 撞 4.0s 断言余量，当时归因为「会话沙箱环境态」，**该归因后被用户在正常 PowerShell 复跑推翻**（见下条修正）。
- **后续修正（2026-10-02 00:41 用户终端复现后）**：正常终端同用例仍失败（elapsed=4.01s）→ 补对照实验重新定性：`proc.kill()`（Popen 直杀）0.01s、PowerShell `Stop-Process` 0.71s、`taskkill /?` 0.10s，而 `taskkill /F /PID` 杀真实进程**稳定 2.5~3.1s**（rc=0、CPU 6%）——慢的是 taskkill.exe 自身的实现链路（WMI 特征），不是进程终止动作、更与本仓代码无关；1s 测试超时 + ~3s taskkill 恰好撞 4.0s 手拍余量。修复：`tests/test_notify.py::test_run_script_timeout_kills_process` 的墙钟余量改为**由生产常量推导**（`_SCRIPT_TIMEOUT_SECONDS + _TREE_KILL_TIMEOUT_SECONDS + 2.0`，≈8s）——taskkill 吃满自家 5s 预算也不误报，而「永久阻塞 / 杀树超预算 / 管道回收悬挂」仍会撞线转红，原「超时后不再占着调用线程」判据意图不变；逐条行为锁仍在 `tests/test_notify_script_guard.py`。机器态根因（taskkill/WMI 为何 ~3s）属 OS 层，不在本仓处置范围。教训：测试的时间余量应从被测路径的生产常量推导，不得手拍绝对值——手拍值隐含「外部工具正常态」假设，机器态变化时既误报又难归因。
- **验证（修正后终态）**：`pytest --cov=src` **3721 passed / 14 skipped / 0 警告**、`check_coverage.py` 44 模块达标、basedpyright 0 error / 0 warning、`compile_po --check` 同步、`run_gates.py` 8 门禁全绿。真机验证（hevc 原画房 127453393722「央视网快看」在播，内联选源脚本）：HLS 关 + ts → **h265 FLV 主候选被放行并选中**（codec=h265 实测探针通过）；HLS 关 + FLV → 落到 h264 原画备选（codec=h264）；HLS 关 + FLV + 摘除备选 → None 且新观测告警实弹打出（英文目录形态含恢复开关指引与主播名）→ 三态全 PASS。

### v4.4.0 (2026-10-01) — 抖音原画 hevc 房「本轮无可用源」死锁根治：hevc 替换时保留 h264 原画 FLV 进 `flv_url_list`

- **触发**：用户运行实例日志——两间抖音原画房（H131-好几百个八 / 新增的大山摩旅中国）每轮 `h265 编码候选无法 copy 录制，跳过` → `选源结论: platform=抖音直播 本轮无可用源` → 跳过录制，主播在播却永不录制；状态行「累计错误数」恒 0（选源失败轮不计错误样本，纯看状态行会误判一切正常）。
- **根因**：三条各自成立的规则叠加成死锁。① `src/stream.py::get_douyin_stream_url` 原画请求（quality_index==0）且接口下发 `hevc_flv_url` 时，用 h265 FLV **替换** h264 FLV 作唯一 FLV 候选（m3u8 非 h265 才触发）；② `select_source_url` 把一切 `codec=h265` 候选在探针之前剔除（h265 不进常规候选序列，只留 record_url 末位通道）；③ 运行实例 HLS 采集关闭时，h264 m3u8 组被**静默**剔除（有 FLV 兜底时不打「HLS 未启用」告警），且 record_url（抖音=`m3u8_url or flv_url`）因是 `.m3u8` 被 HLS 开关联动禁用——过滤后零可用候选。日志判读依据：「h265 告警 → 选源结论」同毫秒＝过滤后零探针发出；无 `record_url has h265 codec` 英文告警＝record_url 是 m3u8（即 m3u8 每轮存在而非缺席）。
- **改动**：`src/stream.py::get_douyin_stream_url` 在 hevc 替换发生前，把被替换的 h264 原画地址存入 `flv_url_list`（新增返回键；`select_source_url` 的既有消费点会把它追加在主候选之后）——HLS 开启时仍 m3u8 优先，HLS 关闭/不可达时落到这条 h264 FLV。防御性过滤：`flv_pull_url` 条目与 hevc 地址逐字相同、或自带 `codec=h265` 标记（钉定约定该参数只应出现在 hevc_flv_url 上）时不收，避免收进同样会被剔除的地址徒增告警。`record_url` 契约不变。候选改进另两项（HLS 静默丢弃补告警、h265 过滤按保存格式放宽）本次未做，待用户决定。
- **回归锁**：`tests/test_stream.py::TestGetDouyinStreamUrl` 新增 6 条（原画替换保留 h264 备选、m3u8 探针失败降级后备选不丢、非原画不触发、仅 hevc 无 flv_pull_url 时备选为空、逐字同址不重复收、h265 标记条目不收）；`tests/test_stream_select.py` 新增 2 条（HLS 关闭时从 `flv_url_list` 选中 h264 备选且 h265 主候选零探针；对照组 h265-only 无备选时恒 None 且不打探针）。变异验证：拆掉 append（标记 MUTATION-H265FB）后两条 stream 侧锁转红，字节级还原后回绿。
- **验证**：`run_gates.py` 8 门禁全绿（内嵌全量 pytest 3698 passed / 0 警告）；`pytest --cov=src` 3698 passed / 14 skipped 后 `check_coverage.py` 44 模块达标；basedpyright 0 error / 0 warning。真机验证（内联脚本，复用 `tests/test_douyin_live_collector.py` 的 web 路径与 cookie 三级回退）：
  `[2026-10-01] 抖音直播 | https://live.douyin.com/127453393722（央视网快看） | 内联选源脚本（web 路径） | PASS | status=2，h265 主候选 + h264 备选，SELECT hls_off → h264 FLV`
  该房恰为在播 hevc 原画房（与用户死锁房间同型）：接口下发 h265 FLV 主候选（`pull-f3.douyinliving.com/…codec=h265`，选源层各打 1 条剔除告警）+ 保留的 h264 原画 FLV 备选（`pull-flv-f1.douyinliving.com/…codec=h264`）；HLS 开启选中 m3u8(h264)（优先级不变），HLS 关闭**选中 h264 FLV 备选**（修复前该形态恒「本轮无可用源」）→ `E2E_RESULT: CURED`。另试 656722643531（大山摩旅中国）、699394970561 均 `SKIP(房间未开播)`；用户死锁房间的运行实例侧确认（HLS 开关状态）交回用户。

### v4.4.0 (2026-10-01) — 修复 test_gui_stop_exit_singleflight 的 Linux CI 4 条假红：POSIX 信号分支缺打桩点

- **触发**：CI `test` job（ubuntu）4 failed / 3679 passed——`tests/test_gui_stop_exit_singleflight.py` 四个场景的「恰一次附着」断言实测 0 次（`attaches: []`），场景 A 的 `reuse_logged` 同时为 False；本地 Windows 全量绿。
- **根因**：`gui._send_stop_signal_and_wait` 按平台分流——win32 走 `_send_ctrl_break_to_child`（原打桩点），POSIX 走 `os.kill(proc.pid, SIGINT)`。子进程脚本只桩 win32 侧，Linux 上记账替身恒不触发；连带效应：停止链失去 0.35s 模拟耗时而瞬时完成，场景 A 的 `sleep(0.05)` 后在途线程已结束、`_current_stop_worker()` 返回 None，「复用在途停止线程」判据同时落空。CI 读数（attaches 空 / wait_calls=1 / reuse_logged False）与「替身缺失」单因完全吻合，非并发缺陷。
- **改动**（仅测试文件，无生产代码）：子进程脚本在非 win32 下按 AGENTS「stdlib 替身走被测模块命名空间 shim」口径把 `gui.os` 换 `SimpleNamespace(**vars(os))` 副本、只覆盖 `kill` 为同一记账替身（finally 还原）；`make_attach_spy` 增加 `sig=None` 形参兼容 `os.kill(pid, sig)` 调用形状；场景 D 两侧替身同步换 0.05s 短耗时版；头部注释更正「唯一外部副作用点」的已证伪表述并留带日期历史注。AGENTS「测试编写强制约定」新增「打桩点必须覆盖平台分流全部分支」条目。
- **验证**：Windows 全量 `pytest --cov=src` 3690 passed / 14 skipped / 0 警告，`check_coverage.py` 44 模块达标；`run_gates.py` 8 门禁全绿；basedpyright 0 error / 0 warning。伪造 `sys.platform="linux"` 本地复现 POSIX 路径——四场景 25 项判据全过（技巧：`import gui` **之后**再改 `sys.platform`；导入前改会让 loguru 的 `enqueue=True` 按 posix 初始化 multiprocessing、Windows 上撞 `No module named '_posixsubprocess'`）。变异验证：拆掉单飞闸门（复用判定与 `_console_stop_lock` 拆除）后 3 条行为锁 + 1 条结构锁全部转红，`gui.py` 字节级还原。真机验证豁免（纯测试改动，不涉录制链路）。

### v4.4.0 (2026-10-01) — deps-audit「下限复核」抓出 urllib3 2.7.0 三条新 CVE，声明下限抬至 2.8.0

- **触发**：CI `deps-audit` job 的「Audit declared floors against OSV (no resolution)」步骤实测 rc=1——把每条下限钉成 `==` 逐项审计时 `urllib3==2.7.0` 报 CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689 三条公告，修复版本均为 2.8.0，旧下限自身落在受影响段（与 starlette / protobuf / h2 三次「下限复核」同型；解析模式对这类形态失明）。
- **改动**：`requirements.txt` 与 `pyproject.toml [project.dependencies]` 的 `urllib3>=2.7.0` → `>=2.8.0`（清单仍 21 条，两侧包名集合不变），requirements 注释按 h2 先例补带日期的复核记录；`python scripts/sync_metadata.py` 重生成 `uv.lock`（锁定版本 2.7.0 → 2.8.0、specifier 同步）与 `DouyinLiveRecorder.egg-info/requires.txt`。本机 venv 实测已装 2.8.0，抬下限不改解析集合、无需重装。
- **验证**：本地按 CI 同款逻辑复跑两步审计——解析模式与 `==` 钉定下限 `--no-deps` 模式均 `No known vulnerabilities found`（rc=0，21 条下限）；`run_gates.py` 8 条门禁全绿（内嵌全量 pytest 3690 passed / 0 警告兜底）；`pytest --cov=src` 3690 passed / 14 skipped 后 `check_coverage.py` 44 模块全部达标；basedpyright 0 error / 0 warning。无生产代码改动，真机验证不适用（豁免）。
- **文档**：`AGENTS.md`「依赖管理·安全下限」条目与本表 `urllib3` 行同步更新。

### v4.4.0 (2026-10-01) — 会话改动按模块归档：AGENTS.md 信息保真精简（−1,818 B / −21 行，19 处）+ stop-hook 红线措辞硬化；本会话无生产代码改动、无文件增删

- **改动面声明**：本会话全部改动集中在仓库约定与用户文档，**无新增功能、无生产代码（`src/`/根入口/`build_exe.py`/`scripts/`）改动、无文件新增或删除**；「删除项」仅为 AGENTS.md 内的冗余文本（见下表）。运行时行为零影响，故无真机验证项。
- **按模块改动清单**：

| 模块 | 文件 | 类型 | 改动内容 |
| --- | --- | --- | --- |
| 仓库约定 | `AGENTS.md` | 修改 | 信息保真精简 19 处：删除冗余重复 2（「格式化命令」节 mypy 指针条目、「safe-delete 护栏」条目内嵌的重复 PowerShell 清理命令）；合并相近条目 4 组（注释约定「写为什么+三层次」、调度中枢 ConcurrencyScheduler 两条、测试收尾清理「范围+核对」两条、Python 版本↔已知坑 PEP 758 去重）；压缩已被推翻的考古链/历史读数 8 处（依赖 21 条复核史、安全下限旧区间、回归测试旧读数、弹幕接线点 `[历史注]`、质量门禁旧条目转述、M-28 计数、假绿用例重写史等）；措辞收紧 5 处（M-26、wraplength、Web 后端尾注、skipif、配置键审计）。「格式化命令」bash 块与全部 `##`/`###`/`####` 章节标题逐字未动，37 处「回归锁」引用与判据读数逐字保留。110,287 → 108,364 字节（−1,818 B）、519 → 498 行、纯 CRLF 保持 |
| 仓库约定 | `AGENTS.md`（CI/workflow·配置键审计条） | 修改 | Mimosa stop-hook 处置：该条被扫描器判为「敏感文件+对外发送」组合风险，核查为误报（该行是防泄露禁止性约定，审计对象是脱敏模板的键名而非凭据值）后按建议硬化为「**禁止**把真实凭据写入提交或以任何形式外传（红线见「风险控制（前置）·凭据与敏感配置红线」）」——语义不变、禁止意图显式化（108,364 → 108,469 字节） |
| 用户文档 | `README.md` / `README_EN.md` | 修改 | 「安装开发依赖」pip 行 `pip install pytest pytest-asyncio black isort mypy`（5 条、缺 `pytest-cov`，照此装出的环境跑不了覆盖率门禁）→ `pip install .[dev]`（单源指向 `[project.optional-dependencies].dev` 六条，与 AGENTS.md「依赖管理」同口径）；细节见同日上一条目（元数据同源对账） |
| 更新日志 | `CODE_WIKI.md` / `CODE_WIKI_EN.md` | 修改 | 本日两条目（元数据同源对账 + 本条）中英双份同步登记 |

- **验证**：`run_gates.py --list` 从精简后的 AGENTS.md 解析出全部 8 条门禁且顺序不变；`tests/test_run_gates.py`+`tests/test_regression_2026_09_22_gates.py`+`tests/test_check_annotations.py` = **73 passed / 1 skipped**（与 2026-09-30 基线一致）；`tests/test_regression_2026_09_22_gates.py`（含「从 AGENTS.md 解析门禁清单」来源锁）单独复跑 **27 passed**；`diff` 章节标题 HEAD vs 新版 **ALL HEADINGS IDENTICAL**；行尾核验：本批全部改动文件保持纯 CRLF（AGENTS.md 498 行、双 README 1049/1050 行、双 CODE_WIKI 同形态）。

### v4.4.0 (2026-10-01) — 元数据同源对账（15 文件 vs `pyproject.toml`）：仅 README 开发依赖指引漂移一处，其余零改动

- **对账范围**：`AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` / `config/config.ini` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `README.md` / `README_EN.md` / `DouyinLiveRecorder.egg-info` / `build_exe.py` / `uv.lock`，以 `pyproject.toml` 为唯一事实源核对版本号 4.4.0、项目名与三入口、Python >= 3.14、21 条运行时依赖及下限、镜像 / 服务名、端口 8000 与四个挂载目录、`build_exe.py` 打包参数。
- **唯一改动**：`README.md` / `README_EN.md`「安装开发依赖」pip 行 `pip install pytest pytest-asyncio black isort mypy`（5 条，缺 `pytest-cov`——照此装出的开发环境跑不了覆盖率门禁 `pytest --cov=src`）改为规范形态 `pip install .[dev]`（单源指向 `[project.optional-dependencies].dev` 六条，与 `AGENTS.md`「依赖管理」同口径，此后 extras 增删无需再改文档）。
- **核对佐证**：`sync_metadata.py --check` OK（uv.lock / egg-info 均 4.4.0）、`check_version.py` PASS；egg-info `Requires-Dist` 21 条与 dev/gui/build extras 逐项一致（setuptools 把 `protobuf` 规格规范化为 `<8,>=6.33.5`，顺序差异非漂移）、`uv.lock` 无 fastapi/pydantic 残留；`.coveragerc-concurrency` omit 23 条 + `exclude_also` 4 条与 pyproject 逐条一致；README 改动为单行替换，行尾形态不变（两文件仍纯 CRLF）。
- 纯文档改动：不涉录制链路，无真机验证项；门禁按「完成定义」豁免只跑受影响面。

### v4.4.0 (2026-09-30) — i18n 盲区补录批次：提取器盲区①②③的用户可见文案 tr 化 + 四语目录同步登记 16 条 + zh_CN.mo 重编

**调用点 tr 化（先查表后插值，消除「目录有词条但运行时永远查不到」）**

- **print_colored（盲区①）**：`main.py` 下载中断 / 线程退出两条、`src/notify.py` 推送失败 / 移除录制列表两条——f-string 直传改 `i18n.tr(常量模板, **kw)` 预格式化后整体传入（MIN-2233 同型）。
- **messagebox（盲区②）**：`gui.py` 共 10 处——6 条错误正文（加载/保存配置文件失败、启动录制失败、写入 URL_config.ini 失败、未找到直播间地址）补 tr，7 处标题补 tr（错误×4 个调用点、切换画质失败×2、成功、配置文件已变更×2、GUI 启动失败），对齐 MIN-2247「标题与正文一并走 tr」口径。
- **推送文案（盲区③）**：`src/notify.py` 推送标题兜底「直播间状态更新通知」过 tr；`msg_push.py` SMTP CRLF 守卫改 `tr("{kind} 含换行符，禁止用于邮件头", kind=tr(kind))`（4 个 kind 标签在调用点翻译）；6 处推送失败 `errmsg` 兜底「未知错误」过 tr。

**四语目录登记（16 条新 msgid）**：zh_CN 恒等（po 尾部新分区 + 更新日期/PO-Revision-Date）；en_US/en_GB 同文英文（「」转双引号）；zh_TW 繁体且术语对齐既有条目（配置文件→設定檔、线程→線程、消息→訊息、注释→註釋）。zh_TW 顺带**去重 7 条主题段重复键**（值完全一致，`界面主题` 等 7 条被整块登记两次，摘除前一份），四目录键集恢复严格一致（808 键）。

**回归锁**：`tests/test_i18n_migration.py` 新增不变量④ `test_no_valuable_fstring_in_print_colored_or_messagebox`——全仓扫描盲区实参位禁插值 f-string + 谓词自检（tr 预格式化 / 常量 / 动态非模板实参不误伤）；变异验证：回改一处为 f-string 用例即红、按字节还原无残留。

**验证**

- 门禁：`run_gates.py` 8/8 绿；全量 pytest 3690 passed / 14 skipped / 0 警告；`check_coverage.py` 44 模块全达标（84.76%）；basedpyright 0 error / 0 warning；`compile_po.py --check` .po/.mo 同步（.mo 头部 N=809，即 808 键+1）。
- i18n 链路端到端：四语言 `set_language` 逐一热切换，16 条新词条经 `.mo`（zh_CN）/ JSON（en 两语）/ YAML（zh_TW）全部命中（含 SMTP 守卫抛错文案 en_US/zh_TW 双语核对）。本批为文案管道改动，不涉录制链路 / 选源 / ffmpeg 参数 / 平台解析行为，无需真机房间验证。

### v4.4.0 (2026-09-30) — P0 修复批次：`CODE_REVIEW_2026-09-30.md` 严重 2 项 + P0 六项落地（每项带回归锁）

> 按报告第 8 章「P0（立即修复）」执行；P1（安装链/HTTP 面上界/测试防线等）与 P2 待后续批次。

**严重（standalone 孪生漂移）**

- **S-01**：`scripts/douyin_live_recorder_standalone.py` 补三道防线——① `_build_opener` 改显式 Handler 白名单（不再经 `build_opener`，file/ftp/data 不再注册，与主线 `sync_http` 定稿同构，`UnknownHandler` 保留为白名单外协议的统一拒绝口）；② 新增 `_untrusted_stream_target_reason`（协议白名单 + IP 字面量含 inet_aton 缩写形态 `2130706433`/`0x7f000001`/`0177.0.0.1`/`127.1` + IPv4 映射 + CGNAT + 内部用途主机名，零 DNS 离线判定，与主线 `web_config._internal_ip_reason` 同判据的离线子集），接线进 `validate_stream_url` 入口（last_resort 也不放行——「末位候选仅告警放行」的对象是 CDN 拒绝类误杀）与 `select_source_url` 候选过滤（逐条留日志可归因）；③ 两处 ffmpeg 命令定义点补 `-protocol_whitelist`（与 `main.py:3472` 逐字同值、位于 `-i` 之前）。
- **S-02**：ffmpeg 命令日志脱敏——`run_ffmpeg` 写 `logs/ffmpeg.log` 前经 `_mask_ffmpeg_cmd_for_log`（`-headers` 值换 `<headers:N chars>` 占位符、`-i` 值走 `strip_query` 保留路径），平台 Cookie 与反盗链 token 不再明文落盘（该日志 append 无轮转）。

**中等（P0 组）**

- **M-01**：`notify.remove_room_from_running` 不再因 `exit_recording=True` 跳过清理（磁盘满暂停并非进程退出，且清理在 `record_state_lock` 内幂等、真进程退出多跑一次无害）——暂停期退出的房间不再残留 `running_list`，空间恢复后主循环拉起条件重新成立，恢复日志与实际行为一致。
- **M-02**：`gui._save_text_to_file` 委托 `src.utils.atomic_write_text`（全仓唯一加固实现：flush+fsync + replace 前保留目标文件原 mode；utils 不 import main、无 config_io 那条副作用），消除 SEV-2211 同族的「POSIX 下每次保存把 0600 收紧还原成 umask 权限」缺口；失败语义不变（False 转 OSError 上抛供错误框）。
- **M-06**：Web 口令 strip 口径三处统一——写入侧先 strip 再哈希、登录比对 strip、历史明文升级哈希也以 strip 形态为准；设置首尾带空格的口令后 reauth 不再永久 403（认证配置经面板自锁）。
- **M-07**：`web_config.update_config_line` 移除无引号值的 `" #"`/`" ;"` 行内注释回落启发式（读侧 configparser 从未开启 inline_comment_prefixes，旧值含 ` #` 时该串本就是值的一部分，拼回新值＝静默污染）；带引号值只在**闭合引号之后**找注释（F-23 语义保持，`key = "a #b"` 不再被回落分支二次污染）。
- **M-17**：`utils._SECRET_HEADER_RE` 驼峰分支摘掉恒死 guard（与 `(?<=[a-z])` 同位置互斥、分支永不匹配）——header 形态的驼峰复合键（`myToken:`/`sessionKey:` 等）恢复脱敏；两条配套边界：独立参数分支**不得**加 quote 排除（shell 命令串 `--header "Authorization: Bearer X"` 键名前恰是引号，排除即漏抹，`tests/test_notify_script_guard.py` 全组同证）；「guard 防 https: 被误抹」的旧结论在当前键名表下已被证伪（无键名可匹配 `https:`）。
- **M-18**：`utils.replace_url` 改段级精确匹配——匹配实现下沉为 `utils.rewrite_line_by_segment`（`config_io._rewrite_line_by_match` 变薄封装委托，单一实现消除双轨漂移），URL 前缀重叠的兄弟房间行（`…/l/123456` 与 `…/l/1234567`）不再被花椒「地址失效自动注释」整行误伤。

**验证**

- `[2026-09-30] 虎牙 | https://www.huya.com/660002 | scripts/douyin_live_recorder_standalone.py --dry-run | PASS | 真实在播房间解析出「王者荣耀赛事」，候选全部过新守卫，探针 403 重试救回→tx 线 200，选中流地址（S-01 三道防线 + S-02 增量验证）`。
- 门禁：`run_gates.py` 8/8 绿；全量 pytest 3689 passed / 14 skipped / 0 警告；`check_coverage.py` 44 模块全达标；basedpyright 0 error / 0 warning。M-18 回归锁做变异验证（旧子串实现下用例变红、按字节还原、行尾形态未破坏）。
- 回归锁：`tests/test_regression_2026_09_22_standalone.py`（TestUntrustedStreamTargetGuard / TestWhitelistOpener / TestFfmpegCommandHardening / TestFfmpegCommandLogMasking）、`tests/test_regression_2026_09_22_utils.py`（header 形态驼峰复合键 + 带引号 header）、`tests/test_web_api.py::TestPasswordManagement::test_password_with_surrounding_whitespace_not_self_locking`、`tests/test_web_config.py::TestUpdateConfigLine::test_hash_in_value_reads_back_as_new_value`、`tests/test_utils.py::TestReplaceUrl::test_prefix_overlapping_sibling_line_untouched`、`tests/test_regression_2026_09_22_main.py::TestDiskFullPauseCleanupStillRuns`、`tests/test_gui_save_atomic.py`。

### v4.4.0 (2026-09-30) — 全工作区代码审查（产出 `CODE_REVIEW_2026-09-30.md`）：18 批逐文件深审 + Mimosa 深扫交叉证据，严重 2 / 中等 51 / 轻微 160

> 用户口径：对本工作空间全部源代码（Python/JavaScript/Node.js/HTML/CSS/CI 等，排除 node_modules、dist、build 等第三方依赖目录与构建产物）做全面审查，重点排查代码质量、潜在缺陷、安全漏洞与逻辑错误，逐文件记录、按严重程度分类成正式报告。报告落盘为根目录 [`CODE_REVIEW_2026-09-30.md`](CODE_REVIEW_2026-09-30.md)。

| 项 | 内容 |
| --- | --- |
| 审查方法与覆盖 | 18 个按模块分组的独立深审批次（12 生产 + 6 测试），每组全文逐行读完、附「既定约定防误报清单 + 专项锚点」；覆盖生产代码约 42,000 行（`main.py` 5,465 / `gui.py` 4,526 / `src/spider.py` 7,100 / Web 层 3,439 / 选源调度 3,498 / 弹幕链 2,743 / HTTP 基建 2,084 / 工具层 3,524 / 安装后处理 2,600 / 前端与签名 JS 4,805 / 构建门禁 CI 约 8,000 / standalone 2,261）与测试约 56,200 行（`tests/*.py` 124 文件 + `tests/frontend` 8 文件）；排除 `typings/`、`src/proto/douyin_pb2.py`（protoc 生成）、`src/javascript/crypto-js.min.js`（仅做篡改专项检查：全文件模式扫描无网络外发/动态构造/系统能力调用，判定为标准 crypto-js 4.x 未被改动）。报告成文前由主审对 2 项严重 + 5 项代表性中等做行号级复核，全部证实 |
| 严重 2 项（均在 `scripts/douyin_live_recorder_standalone.py`，孪生漂移） | ① 探针/录制链 SSRF 与本地文件读取链（`:180-187/:746-756/:1456-1494`）：默认 `build_opener` 含 FileHandler + 平台候选无协议/内网判定 + ffmpeg 命令缺 `-protocol_whitelist`（主线 `main.py:3466` 已有）三层叠加，`file://` 与 `169.254.169.254` 可被「探测→放行→ffmpeg 录制落盘」完整走通；② 完整 ffmpeg 命令（含 Cookie 头与带 token 流 URL）逐轮写入 `logs/ffmpeg.log` 且无轮转（`:1543/:1552`），与「凭据不落盘」红线冲突 |
| 中等 51 项的分布与代表 | 生产 37：standalone 4（MID-49 斗鱼 POST 未回灌、探针异常带全 URL、GBK 配置启动崩溃、Windows terminate 硬杀截断 mp4）；安装链 6（node TOFU 基准读失败 fail-open、新 zip 无形态校验即记账、版本号零校验、直解压应用根、导入期 `check_node` 并发安装竞态、`check_node` 异常可炸掉 `import src`）；工具层 4（`_SECRET_HEADER_RE` 驼峰分支两 lookbehind 互斥恒死——header 形态驼峰凭据不脱敏、`replace_url` 子串误伤注释掉 ID 前缀重叠的兄弟房间、logger 双 sink 部分失败泄漏、`run_node_script_async` 缺 wait_for 可永久挂死房间线程）；Web 3（请求体无大小上限、密码 strip 三处口径不一可致认证配置永久自锁、行内注释保留逻辑污染含 `#` 的配置值）；HTTP 4（sync_http 内网跳转缺口/HTTPError 无上限/data-json 分叉、async_http 钩子内同步 getaddrinfo）；弹幕 3（singleflight 异常未脱敏、在途登记不注销、SRT 失败静默丢且告警链不触发）；选源 2（`_PRIVATE_HOST_PATTERN` 字面量缺口、room.py 裸 AsyncClient 跟随重定向）；spider 2（浪Live/映客/京东 MID-2212 同族残留、xhs sid 重定向外送）；main 1（磁盘满恢复后 `running_list` 永久残留致全部房间不再拉起）；GUI 1（`_save_text_to_file` 弱化原子写，POSIX 下还原 0600——SEV-2211 同族）；构建 CI 6（softprops/paths-filter 浮动 ref×最高权限、check_annotations 主目录防护方向反、冒烟不排空管道/不断言存活、一次性脚本 ROOT 硬编码）；前端 1（语言切换清空已渲染配置表单）。测试 14：恒真断言（test_http_config:153、test_proxy:149）、替身打到进程级本体（configparser/ctypes/time.sleep/httpx/loguru）、前端三包装缺 node 侧 skipped 校验（`{skip:true}` 全链路假绿）、沙箱缺 sessionStorage 致 token 主路径零覆盖、MID-2253/2238 文本锁可逃逸等 |
| 机扫交叉（Mimosa） | scanId `scan-2026-09-30T02-25-56.161Z-3255898c38d0`、seal `sha256:5350da9801cb…d78a1`、深度 deep、证据边界 static_only、状态 **inconclusive**（198/198 文件解析、threatModel 未建全、validation 阶段 investigated=0——41 条均为未验证静态发现）：HIGH 命令注入 3 / 硬编码凭据 3 / 路径穿越 11 / SSRF 7 + LOW 随机数 17。逐条人工复核：0 条构成人工未见的可利用漏洞（2 条与人工发现重合互证——node 版本号零校验、sync_http 内网复检缺失；其余为模式误报或设计内公共客户端标识）；机扫选取面未覆盖 standalone——最重的 S-01/S-02 由人工深审找出 |
| 报告结构与行动项 | 报告含审查概述/范围/统计矩阵/严重 2 项与中等 51 项逐项详述（问题+影响分析+修复建议）/轻微 160 项分区域表格/机扫复核表/P0-P2 修复优先级/流程性建议（「孪生回灌」硬约定提案、R1 名单补 configparser 与 `_SANCTIONED` 登记、standalone 回灌专项）/总结结论；「待确认」条目 10 余项需真机或特定环境复现后再定级 |
| 文档与门禁 | 本批为纯文档产出：新增 `CODE_REVIEW_2026-09-30.md`（根目录；`.dockerignore` 已有 `CODE_REVIEW_*.md` 通配、不入镜像）+ 本条目（中英同步），零代码改动；按「完成定义」豁免：第 1 步门禁不适用（无 `.py`/前端资产改动）、第 2 步真机验证不适用（不触碰录制链路/选源/ffmpeg 参数）、第 3/5 步不适用（无回归锁改动、未产生一次性脚本） |
| 交回用户 | P0 修复队列五组见报告第 8 章（standalone 孪生回灌、脱敏死分支、Web 认证自锁与配置值污染、`replace_url` 误伤与磁盘恢复拉起、GUI 原子写）；standalone 建议单独立项做「回灌对齐」专项 |

### v4.4.0 (2026-09-30) — `AGENTS.md` 与工作区对账（7 项事实同步）+ 冗余量化后只做信息保真精简：本批净 +529 字节（精简类操作 −170 B，事实同步 +699 B）

> 用户口径：扫描工作区 → 按 `git status`/`git diff` 识别自上次提交以来的增删改 → 回写 `AGENTS.md` 受影响配置 → 在此之上精简。
> 工作区实测：`git status --porcelain` 仅 5 条 `M`（`AGENTS.md`/`CODE_WIKI.md`/`CODE_WIKI_EN.md`/`docs/agent-reference/session-learnings.md`/`pyproject.toml`），
> **0 新增、0 删除、0 未跟踪**（`filter.lfs.*` 已配置，不影响 status 采集）；对账基准 HEAD `046bb73`。
> `pyproject.toml` 本批只改 `[tool.pytest.ini_options].filterwarnings` 两条**注释归因**、零取值变更 → `AGENTS.md` 无需随动（运行时依赖 21 条与 `requirements.txt` 已复核相等）。

| 项 | 内容 |
| --- | --- |
| 事实同步 7 项（均给实测判据） | ① 「开发/构建/GUI 依赖」`.[dev]` 由「pytest/black/isort/mypy」补全为**六条**（另 `pytest-asyncio`、`pytest-cov`，与 `pyproject [project.optional-dependencies].dev` 逐项核对）；② `tests/test_scheduler.py`「16 用例」→ **29**、`tests/test_record_failure_feedback.py`「5 用例」→ **8**（`pytest --collect-only -q`）；③ 已知坑里的符号名 `_allow_sleep` **不存在**，`src/scheduler.py` 实为模块级 `_sleep`（:531）与 `_now()`（:525）；④ 「6 处 `check_subprocess(...)`」→ **1 处**（`main.py:3595`；F-01 收敛后各平台分支只填 `ctx.record_danmaku_args`，现 52 处赋值，`grep -c` 实测）；⑤ `_loads_dict`「约 40 处调用」→ **103 处**（`grep -c '_loads_dict(' src/spider.py` = 104 行含 1 处定义）；⑥ 「产物体积大头」中 `pydantic_core` 4.93MB 与「合计约 24MB」随 `046bb73` 移除 fastapi/pydantic 失效，且本机无 `dist/` 可复测 → 读数外迁、根文件只留「三项固定成本」约束；⑦ 复核为**真**、未改动的读数：`BARE_JSON_LOADS_CEILING = 1`、`tests/test_ci_retry_action.py` 真 bash 行为锁 8 格、`test_twin_agrees_on_every_criterion_combination` 9 格矩阵、web_api 路由 24 条、`_FFMPEG_FAST_FAIL_SECONDS = 20.0`、`_PROBE_LEASE_SECONDS = 60.0`、`_PROBE_BACKOFF_PLATFORMS`/`_FLV_FIRST_PLATFORMS = ("虎牙直播",)`、ci.yml consts（black 26.5.1 / isort 9.0.1 / mypy 2.3.1 / pytest 9.1.1 / python 3.14 / node 24）、actions v7、`release-guard`、R7/R8、两条元数据回归锁、`MIN-2241` 的 `\r?\n\r?\n` 锚点、`test_motion.mjs` 5 条锁 |
| 冗余量化（先测后改） | 体积一律按**原始文件字节（CRLF 形态）**计：HEAD `046bb73` 515 行 / 107 227 B → 本会话进场 517 行 / 109 009 B（含上一批未提交的三条门禁口径条目）→ 本批结束 **518 行 / 109 538 B**。本批两组操作的实测拆分：精简类 −170 B（`PYTHONUTF8` 两条合一 −39 B、`subprocess`+`FakePopen` 合一 **+33 B**——合并时补了「`__class_getitem__` 不可省」的因果框架文字，故不降反升、须如实记；collector 两条合一 −175 B、体积读数外迁使根文件 −137 B、两条新指针 +148 B），事实同步类 +699 B（7 项实测读数与 `[历史注]`）。机检结果：trailing whitespace **0** 行、逐字重复行 **1**（两段清理脚本各含同一 `Where-Object`，属刻意并列非冗余）、加粗小标题重复 **0** 处、连续空行段 **8**（均 ≤3 行）、113 条 >200 字符 bullet 与 `CODE_WIKI.md`+`CODE_WIKI_EN.md` 的 25 字 shingle 重叠 >50% 者 **0** 条、bullet 之间重叠 >40% 者 **0** 对。**结论：本文件已无「冗余重复表述」可删**（约 41% 字节是回归锁与约束本体，即事实源本身）；要再降体积只能压缩「更正考古」或继续外迁读数，两类都改信息形态而非删重复，须先获批准 |
| 信息保真操作（唯一可行的三类） | 合并同主题条目 **3 处**：「`PYTHONUTF8=1` 告警即失败」与「父进程转发 / `errors="replace"`」两条并为一条（MID-63、「重复实现于 6 处」、`run_gates.ensure_utf8_streams()`、`_guard_stdio_encoding_policy`、`gui._install_crash_sink()` 全留）；「patch `main.py` subprocess」与「`FakePopen` 须带 `__class_getitem__`」并一条；「双模式 collector 的 `int(sys.argv)` 两步守卫」与「执行体须包在 `__main__` 内」并一条（四条模板约束改 ①②③④ 编号，20.55 秒 / 退出码 5 / 4 errors during collection 三处读数逐字保留） |
| 外迁 + 指针修复 | 体积 MB 读数与 `pydantic_core` 失效史外迁到 `docs/agent-reference/measured-evidence.md` 新小节「产物体积大头读数」（该文件判据：句中不得出现祈使式约束，已核对）；同时修复**根文件失去入口**的两份子文档——`measured-evidence.md` 与 `lock-classification.md` 早已外迁但 `AGENTS.md` 无指针（此前只剩 `project-structure.md` 挂着），现各补一条引用式链接（`[体积读数]`、`[锁分类快照]`） |
| 信息零丢失自证 | 与 HEAD 逐类比对并被 `measured-evidence.md` 兜住后：`test_*` 标识符 **69 → 69（丢失 0）**、MID/SEV/MIN/CVE/PYSEC/GHSA 编号 **19 → 19（丢失 0）**、`UPPER_SNAKE` 常量 **77 → 77（丢失 0）**；反引号片段丢失 5 个均为同物改写（`_now`→`_now()`、`libcrypto/libssl`→`libcrypto`/`libssl`、`record_danmaku_args`→`ctx.record_danmaku_args`、`basedpyright tests/` 为上一批已删除的错误口径、`__main__` 由枚举短句并入完整 `if __name__ == "__main__": main()`） |
| 门禁 | `python scripts/run_gates.py` → **8/8 全绿（41.1s）** + 尾部兜底 **3653 passed 且 warnings summary 为空（194.5s）**，退出码 0；`run_gates.py --list` 仍解析出 **8 条**且首条逐字为 `python -m black --check --diff --line-length 120 --target-version py314 .`（章节标题/围栏/`PYTHONUTF8=1` 行首前缀均未动）；三条文档锁 `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = **73 passed / 1 skipped / 0 警告（36.57s）**；`AGENTS.md` 行尾形态 **CRLF 518 / 裸 LF 0**、`measured-evidence.md` 仍纯 CRLF、`session-learnings.md` 仍纯 LF。另记一条副作用：跑完全量门禁（含尾部 pytest）后 `git status --porcelain` 多出**已跟踪**的 `config/config.ini`——`[GUI]` 前一个空行被配置回写路径吞掉，属用例副作用而非本批意图改动；因恢复已跟踪文件归用户决定，未擅自 `git restore`，列为 N-4 |
| 未复跑项与理由 | `scripts/check_coverage.py` 与 `basedpyright` 本批**未重跑**：本轮零 `.py`/`.sql`/前端资产改动（纯 `.md`），二者结论沿用同日实测（44 模块全部达阈 / 191 文件 0 error 0 warning）；另 `check_coverage.py` 需 `pytest --cov=src` 的 coverage 数据，而 `run_gates.py` 的兜底跑法不带 `--cov`，此刻重跑只会落「无数据 rc=2」的假信号 |
| 真机验证 | **未执行**：本批不触碰录制链路 / 选源 / ffmpeg 参数 / 平台解析，按「完成定义」第 2 步豁免；仅执行第 1（受影响部分）/4/6 步 |
| 仍需人工处理（编号，交回用户） | **N-1** 陈旧注释残留「FastAPI」三处：`.github/workflows/ci.yml:6`、`.github/workflows/ci.yml:606`、`docker-compose.yaml:100`——`fastapi` 已随 `046bb73` 移除，面板为 Starlette 直接驱动；纯注释改动，未动以免越出「只改 `AGENTS.md`」授权范围。**N-2** `scripts/compile_po.py:136-137` 写的是 `reconfigure(encoding="utf-8")` 而**未给 `errors`**，与 `AGENTS.md`「任何 `reconfigure` 显式给 `errors`」这条自家约束相违（省略会把错误处理器重置为 `strict`，同 MID-63 事故族）；修复须配回归锁，未擅自改维护脚本。**N-3** 上一批遗留两项派生元数据问题仍未决：`src/proto/douyin_pb2.pyi` 是否列入 `[tool.setuptools.package-data]`、`.[dev]` 下限是否抬至 CI 钉定值 |

### v4.4.0 (2026-09-30) — 全量门禁复核（191 个源文件 / 3653 条用例）：代码面零缺陷，`AGENTS.md` 三条门禁口径修正

> 用户要求对工作空间全部 Python 代码跑完整质量检查与测试。结论：**black / isort / mypy（宿主 + `--platform linux` 双跑）/ basedpyright / pyright / pytest / 逐模块覆盖率七个面全绿，业务代码零改动**；本轮唯一落盘的代码库改动是 `AGENTS.md` 的三条门禁口径条目。

| 项 | 内容 |
| --- | --- |
| 门禁读数 | `python scripts/run_gates.py` → 8/8 PASS（45.3s）+ 尾部 pytest 兜底「3653 passed 且 warnings summary 为空」（190.5s，与独立一次 `pytest --cov=src -q` 的 3653 passed / 14 skipped 相互印证）；`scripts/check_coverage.py` → 44 模块全部达阈（总 84.69%，`src/proto/douyin_pb2.py` 8.7% 属显式豁免的 protoc 生成物）；`basedpyright` 不传路径 → 191 文件 0 error/0 warning（旧口径 `basedpyright tests/` 的 126 文件亦 0/0）；`pyright` 1.1.414 显式传 `[tool.mypy].files` 同集合路径 → 191 文件 0/0，裸跑 → 205 文件（多出的 14 份即 `typings/` 存根）同样 0/0 |
| `AGENTS.md` 更正 1 | 「测试 → 质量门禁（须保持）」原写「black/isort/mypy 三条（路径换成 `tests/`）」，与本文件「`mypy` 不带路径参数」互斥——显式传参会覆盖 `[tool.mypy].files`、等于自行缩小覆盖面。改为引用「格式化命令（门禁唯一基准）」一节，判定口径（0 警告 / 全绿 / 0 error 0 warning）逐字不变 |
| `AGENTS.md` 更正 2 | 「basedpyright（本地补充门禁，CI 不跑）」补 `pyright` 与 Pylance 的定位：`pyright` 只是 basedpyright 的引擎基座、**不是第三条门禁**；Pylance 无命令行入口，「Pylance 已查过」不得充当门禁证据；本仓没有 `[tool.pyright]` 配置段，裸跑 `pyright` 的扫描面大于 `[tool.basedpyright]` 的排除口径 |
| `AGENTS.md` 新增 | 「格式化命令」补一条可外推前提：本地 black/isort/mypy/pytest 版本须与 `ci.yml` consts 钉定值逐一同值，否则结论必须标注「本地口径，未经 CI 同版本验证」。实测差异一项：**isort 本机 9.0.2 vs CI 钉定 9.0.1**（black 26.5.1 / mypy 2.3.1 / pytest 9.1.1 同值）。未擅自改 workflow 常量、未重装 venv 依赖（后者按「风险控制（前置）」属用户通道） |
| 14 条 skip 归因 | 全部为环境形态限制、非失败：Windows 语义 4（`tests/test_proxy.py:199`、`tests/test_regression_2026_09_22_utils.py:178`、`tests/test_utils.py:574`、`tests/test_run_gates.py:218`）；符号链接特权缺失 3（`tests/test_ffmpeg_path_preference.py:262`、`tests/test_web_api.py:2137`/`:2157`，WinError 1314）；本机 `h2` 可用故构造期缺依赖分支不可达 1（`tests/test_regression_2026_09_22_net.py:681`）；平台无文档化离线形态 6（`tests/test_spider_hardening.py:198`） |
| 真机验证 | **未执行**：本轮零代码改动（纯文档），按「完成定义」豁免条款只做第 1/4/6 步；录制链路未被触碰 |
| 文档锁自证 | 改完 `AGENTS.md` 后复跑依赖该文件的三条文档锁 `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped；「格式化命令」bash 块的解析与条数锁未受影响（新增条目均落在围栏之外）；`AGENTS.md` 行尾形态复核为 CRLF 517 / 裸 LF 0（与 HEAD 同形态，未被编辑打混） |

### v4.4.0 (2026-09-30) — pyproject.toml 与工作区变更对账（依赖 / 派生元数据 / 包清单 / 排除清单四项）：取值零改动，仅更正 `filterwarnings` 两条注释的归因

**背景**：按「扫描工作区 → 识别自上次提交以来的增删改 → 回写受影响的 pyproject 配置」口径复核。工作树对 HEAD 干净，故对账基准取未推送的 `046bb73`（该批移除 fastapi / pydantic）。

| 复核项 | 判据（本机实测） | 结论 |
| --- | --- | --- |
| 运行时依赖集合 | `pyproject [project.dependencies]` 21 条 ↔ `requirements.txt` 剥行内注释后 21 条；`tests/test_regression_2026_09_22_gates.py` 27 passed | 已随 `046bb73` 同步，无需改 |
| 派生产物 | `python scripts/sync_metadata.py --check` | OK：`uv.lock` 内已无 fastapi/pydantic 节点，egg-info 版本与依赖均同步 |
| 未声明的第三方 import | AST 扫全仓 243 个 `.py` 顶层 import 与声明集合对账（脚本走 stdin，不落盘） | 产品码零缺口；`fastapi`/`pydantic` 仅残留在 `.workbuddy/tmp/` 的旧快照备份，该目录已在各工具排除清单内 |
| 包清单 | `src/` 子包仍只有 `platforms` / `proto`；根目录 6 个 `.py` 全在 `py-modules` 与 `[tool.mypy].files`；本批新增文件落 `src/`、`tests/`、`web/`、`docs/worklog/` | `packages` / `py-modules` / `package-data` 均无需改 |
| 排除清单同源 | black / isort / mypy / coverage / basedpyright 五侧与 `.coveragerc-concurrency` 的 omit 逐项一致；`tests/`、`docs/`、`web/` 下无新增 `.py` 资产目录 | 无需改 |

**实际改动（仅注释）**：`[tool.pytest.ini_options].filterwarnings` 两条归因更正——

- 第一条**承重**：带 `-W default::UserWarning` 跑 `tests/test_web_api.py` 时 warnings summary 恰落 1 条，发出方是 `starlette/testclient.py` 本体（类别 `StarletteDeprecationWarning`，为 `UserWarning` 子类）；原注释记作「fastapi testclient 内部 import」，已被 `046bb73` 证伪。
- 第二条在现装组合（starlette 1.7.0 + anyio 4.15.1）下**实测不触发**：带 `-W always::DeprecationWarning`（命令行 `-W` 覆盖 ini 过滤）跑 `test_web_api.py` + `test_web_api_routes.py` 得 163 passed 且 summary 为空，starlette 三处引用已全走 `anyio.from_thread.BlockingPortal`。仍保留不删——声明下限 `starlette>=1.3.1` 区间的形态未经本机构验。

**门禁**：`check_version.py` PASS、`sync_metadata.py --check` OK、`pytest tests/test_regression_2026_09_22_gates.py tests/test_web_api.py` = 190 passed / 2 skipped / 0 警告；另核 TOML 可解析与全文件 ≤120 列。
**真机验证**：未执行——本批不涉及录制链路 / 选源 / ffmpeg 参数 / 平台解析，按 DoD 第 2 步豁免。
**未随本批改动（交回用户）**：① `src/proto/douyin_pb2.pyi`（2026-08-18 起存在）未列入 `[tool.setuptools.package-data]`，wheel 是否收录未实测（本机无已安装发行包、无 `.whl` 可核），需真构建再判；② `[project.optional-dependencies].dev` 下限（pytest>=7.0.0 / mypy>=1.5.0 / pytest-asyncio>=0.21.0）与 `ci.yml` consts 钉定值（pytest 9.1.1 / mypy 2.3.1 / black 26.5.1）落差较大，是否抬至 CI 同值待定。

**同日追加（经用户批准的单独一项）**：`AGENTS.md`「依赖管理」条原写「23 条」——该读数已被 `046bb73`（移除 `fastapi`/`pydantic`）证伪。本轮先因该文件正被并行编辑而未动，用户单独下达指令后改为「21 条，2026-09-30 复核：`fastapi`/`pydantic` 随阶段2 移除后由 23→21」，并把先前 2026-09-26 的 21→23 读数改写为「已被该移除推翻」的历史注（旧事实与常量名逐字保留，不删）。改后复测：`AGENTS.md` 行尾形态仍为 CRLF 517 / 裸 LF 0；读该文件的三条文档锁 `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped / 0 警告（「格式化命令」bash 块解析与命令条数不受影响，本次改动落在围栏之外）。

### v4.4.0 (2026-09-30) — 审查报告三项「待决策」落地（1-A 同步探针内网收口 / 2-A retry 按退出码分档 / 3-A 真机脚本模板门禁）+ 一道防「变异验证未还原」的机检

> 上一批（CODE_REVIEW_2026-09-29_2 修复）收尾时留下三条需用户决策的残余缺口，本轮按批准的 1-A / 2-A / 3-A 组合全部落地。
> 过程中发现并修复了一起**变异验证残留留在生产代码**的真实事故，并把它变成机器可检（新规则 R8）。

**一、1-A　同步探针的内网收口（`src/stream_select.py`、`src/async_http.py`）**

上一批只给异步侧接了逐跳复检，当时我把它描述成「同步探针同样形态未接线（逐跳层面）」。本轮复核**更正该前提**：
`src/stream_select.py` 里全仓唯一的内网判定调用点只有 `async_http.get_response_status`，同步探针侧
**连初始 URL 的内网/回环/云元数据判定都没有**——它只有 `_is_recordable_url` 的协议形态白名单，
挡得住 `file://`/`concat:`，挡不住 `http://127.0.0.1:6379`。被劫持的平台接口回传一个内网流地址即可命中。

| 项 | 内容 |
| --- | --- |
| 单点工厂 | 两处自建 `httpx.Client` 收敛到 `_probe_client()`，客户端自带同步 response 逐跳钩子（`build_sync_hop_guard`）；判定复用 `async_http` 同一份 helper，**不在 stream_select 另写一份** |
| 导入环 | 钩子工厂经**函数内 import** 取得，沿 `async_http.py:518-521` 记录的同一手法（本模块有模块级 `import main`，加模块级出边会改变初始化顺序） |
| 初始判定 | `_validate_stream_url` 在发第一个请求之前过 `internal_stream_target_reason`；刻意不复用带 scheme 白名单的那份判定——协议维度已由 `_is_recordable_url` 把关，两道互不替代 |
| 异常收敛 | `RedirectHopRejected`（继承 `httpx.HTTPError` 而非 `RuntimeError`）在 `_validate_stream_url` 内转成既有「本候选校验失败」的同一个 False，**绝不穿透**给调用方；`_confirm_get_ok` / `_probe_hls_segment` 的「按列表可达处理」兜底一律 `raise` 上抛——否则末位候选会 `return True` 把内网地址交给 `ffmpeg -i` |
| 未回退 | 探针客户端复用作用域仍是单次选源、不做 `(proxy, verify)` 全局缓存、不关 keepalive、`utils.handle_proxy_addr` 归一位置不动 |
| 回归锁 | `tests/test_sync_probe_internal_guard.py`（含 AST 结构锁：构造点唯一、`event_hooks` 实参必须来自同步工厂、两处调用点都过初始判定）；异步侧锁 `tests/test_regression_2026_09_29_wp_b_netguard.py` 保持全绿 |

**二、2-A　retry 复合动作支持按退出码分档（`.github/actions/retry/action.yml`、`.github/workflows/ci.yml`）**

| 项 | 内容 |
| --- | --- |
| 新增可选入参 | `fail_fast_codes`，`required: false`、`default: ""`；**不传时既有调用点行为逐字不变**（含退避算法、两条文案、最终 `exit 1`） |
| 命中语义 | 位于退避 `sleep` **之前**，打 `::error:: … 属配置类错误 … 不重试` 并 `exit "$rc"` 保留原码；**不得**退 0 或降级成 warning（假绿） |
| 解析 | `IFS=", "` + `set -f` + `case ''|*[!0-9]*`，空格/逗号混合可解析、非法项忽略并 `::warning::`、以空格包围串做整码匹配（列表含 `2` 不命中 rc=12）；全程 POSIX 写法不用 bash-only 关联数组 |
| 接线 | 仅 web smoke 调用点传 `"2"`，闭合 M-32② 的「配置问题不该重试」 |
| 前提更正 | 工单写「共 10 个调用点」，实测 **16 个**（ci.yml 11 / build-release.yml 5）——此前批次已把更多安装步骤接入该动作；结构锁据实取下限 16（只降不升语义），并断言「正则口径 == YAML 结构口径」防 `uses` 形态漂移让 AGENTS 的 grep 门禁自身失真 |
| 回归锁 | `tests/test_ci_retry_action.py`：4 条结构锁 + 8 格真 `bash` 行为锁（跑的就是从 `action.yml` 抽出的生产脚本本体，无副本，删生产分支必红）；bash 缺失时**显式失败而非 skip** |

**三、3-A　真机脚本模板门禁 R7（`tests/test_test_hygiene.py` + 5 个 `test_*_live_collector.py`）**

四条 AST 判据逐条点名：① `__main__` 守卫且守卫内真调 `main()`；② 模块级零收集期副作用（只放行 import / 常量赋值 / `sys.path` 注入等既有惯例）；③ argv 数值守卫；④ 清理输出目录必须按平台前缀过滤且先判类型。

实现过程中**抓出一个 AGENTS 明文样例本身是错的**（下列第四项）。反向见证按要求扩展：四条判据各喂最坏形态断言必红、各造合规源码断言不误报，并新增 4 条「在真实脚本上做定向变异、要求只红对应那一条」的用例。

**四、两处对既有文档/前提的证伪与更正**

1. **AGENTS 的 argv 守卫样例被实测证伪**：原写法 `SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else N` 在 `pytest a.py b.py` 一次点多个文件时，`sys.argv[2]` 是**下一个测试文件的路径**——它不带 `-` 前缀，只判非选项会放行，随后 `int(路径)` 抛 ValueError、该模块收集直接 ERROR（实测 4 errors during collection）。5 个脚本统一改为两步式 `_SECONDS_RAW = …` → `int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else N`，判据由 R7③ 机检，`AGENTS.md` 该条正文按「被证伪条目直接改正文」口径改正。
2. **审查报告点名的无差别清空确有其事**：`test_bili_live_collector.py` / `test_huya_live_collector.py` 原为 `for f in os.listdir(base_dir): os.remove(...)`（无前缀过滤、不判目录），混入子目录即抛错、并行验证互删；已改为按平台前缀 + `isfile` 判定后删，保留「手跑前从干净目录开始」的原意。
3. **上一批 AGENTS 里「retry 对 rc 不敏感、rc=2 不能真的立刻停（待决策缺口）」已被 2-A 闭合**，正文同步更正。

**五、事故与新增机检 R8（防「变异验证没还原」）**

一个并行工作包在 `src/stream_select.py` 分片探测分支上做「摘掉 `except RedirectHopRejected: raise`」的变异，跑到轮次上限中断，把 `pass  # MUTATION-M4c …` **原样留在生产代码里**。后果不是少一条注释：`seg_resp` 未赋值 → `UnboundLocalError` 被外层 `except Exception` 当「探测异常」吞掉 → 末位候选 `return True` → **内网地址被交给 `ffmpeg -i`**。该形态对 black / mypy / 注释检查**三面全隐形**（语法合法、类型不报错、注释反而更多），只有用例真跑到那条分支才现形——本次正是新写的同步探针用例把它抓出来的。

据此新增 **R8**：全仓扫描源文件里的 `MUTATION-` 标记，留着即判红；配套三条硬约束写回 `AGENTS.md`「测试编写强制约定」（内存备份 + `finally` 按字节还原 + 必须留标记 + 接手被中断的工作包时第一件事是扫残留而非假设实现已完成）。守卫自身做了三件防自指/防空转的事：标记字面量拆两段拼接（否则守卫判红自己）、断言遍历面 > 200 个文件（否则扫描根写错会静默空转）、反向见证覆盖「带标记必红 / 去掉标记必绿 / 守卫文件自身不含完整字面量」。

**六、验证**

| 项 | 读数 |
| --- | --- |
| 1-A 真实出站探针 | 公网 HLS（走播放列表 + **分片探测**那条曾残留变异的分支）`test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` → **True**（不误杀）；`http://127.0.0.1:6379/`、`http://169.254.169.254/latest/meta-data/`、`http://10.0.0.5/live.m3u8`、`http://100.64.0.1/live.m3u8` → 全部 **False**；内网 + `last_resort=True` → **False**（末位不放行）；`file:///etc/passwd` → **False**（形态白名单仍在） |
| 「公网 → 内网」真实跳转链 | **SKIP(无可用的公开跳转器)**：httpbingo.org 对本机回 403，公网公开且会 302 到内网的端点不存在；由 `httpx.MockTransport` 锁覆盖，不伪造读数 |
| 2-A | `pytest tests/test_ci_retry_action.py` 单文件 **12 passed / 0 警告**（4 结构锁 + 8 真 bash 行为锁）；端到端接线核对用 ci.yml 真实 `with` 值 + default 按 GitHub 口径填充 → `runs=1 / rc=2 / 0.23s`（`backoff=5` 若真退避应 ≥5s）；三次变异验证实跑：删分支 `4 failed, 8 passed`、`default` 改 `"2"` `1 failed, 11 passed`、分支挪到 `sleep` 之后 `4 failed, 8 passed`，均按字节还原 |
| 3-A / R8 | `pytest tests/test_test_hygiene.py` **507 passed**；R8 磁盘路径以一次性探针文件实测：放入 `tests/_tmp_r8_probe.py`（含标记）→ `AssertionError: tests/_tmp_r8_probe.py:7` 点名，删除后转绿；探针文件已删 |
| 真机录制链路 | 抖音 `live.douyin.com/699394970561`（`tests/test_douyin_live_collector.py`，15 秒窗口）→ **SKIP(房间未开播)**；脚本按**既有**的 `status: SKIP` + `reason: room_offline` 结构化一行返回（非本批改动，已用 `git show HEAD:` 核对），不当成失败刷红。本批受影响面是选源校验器而非采集线程，真实出站证据以上方 1-A 那行为准（公网 HLS 走通、四类内网目标全拒）；采集链路健康度以上一批的抖音 PASS(59 条/4518 字节)、B站 PASS(9 条/678 字节) 为基线 |
| 全量门禁 | `python scripts/run_gates.py` 8 条全绿 + 内嵌 pytest warnings summary 为空（读数见交付回复） |

**七、仍未闭合**

- GitHub Actions 侧的 `inputs → env` 展开由 runner 完成，本机只验证了「按 GitHub 口径填 default 后脚本行为正确」；合并后建议看一眼首个 web smoke 失败件日志是否出现 `退出码 2 属配置类错误 … 不重试`。
- `build-release.yml` 的 5 个调用点刻意不传 `fail_fast_codes`（都是 choco/apt/brew/pip 安装，不存在「配置类错误」这一档退出码，传值只会削弱网络抖动重试），已由结构锁显式钉住「无人传」而非放任漂移。
- 逐跳钩子的触发时机仍在响应已收到之后（闭合「不再跟随 + 不外流」，不是「不建连」）；要建连前拦断需改 request 钩子（每跳两次判定/两次 `getaddrinfo`），DNS 重绑定窗口本层不闭合——两者都作为残余风险写在源码注释与本条。
- 上一批的目视项与真机缺口不变（M-14/M-16/M-18/M-22 观感验证、TikTok 需可出境网络复跑 M-11、斗鱼当时均无活房间、`basedpyright` 本机未安装）。

### v4.4.0 (2026-09-29) — 全量审查报告 CODE_REVIEW_2026-09-29_2 修复批次（P0+P1+P2 共 31 个编号）

> 依据 `docs/worklog/CODE_REVIEW_2026-09-29_2.md`，按用户批准范围 P0+P1+P2 落地（31 个编号 / 33 个独立问题）。
> 同批未纳入：轻微项 43-47（前端 a11y）、P3 的 M-6（VBS 匹配面收紧）/ M-7（migu wasm SRI）/ M-20（冻结环境 i18n 实测），
> 及各标「待核实」条目。所有修复均附回归锁，安全不变量类另做变异验证。

**一、安全收口（S-1、M-1 ~ M-5）**

| 编号 | 落点 | 内容 |
| --- | --- | --- |
| S-1 | `src/spider.py:140-174`、`112-121`、`6183-6254` | Shopee 短链落地页补齐与小红书 SEV-2214 **同型**的双闸：域族后缀白名单（`urlparse().hostname` 精确/`.` 后缀 + 拒 userinfo）+ `web_config._host_internal_reason` 内网判定；不可信即丢弃跳转、保留原始 url 并剥 Cookie；`api_host` 构造后再过一次白名单（投毒 `host_suffix` 也拦得住）；`_shopee_host_suffix` 由裸字符串切分改判 hostname |
| M-1 | `src/async_http.py:87`、`460`、`532-588`、`679` | 探针与 `async_req` 全部分支的**逐跳**重定向复检：在 `_build_client` 单点挂 `event_hooks` 响应钩子，每一跳落地 URL 复用 `_internal_stream_target_reason`，命中即停止跟随并按既有「不可达」语义返回；DNS 重绑定窗口登记为残余风险（判定结果刻意不加缓存） |
| M-2 | `src/sync_http.py:56-140`、`309`、`375` | `sync_req` 补 scheme 白名单（复用 `utils.is_safe_http_url`，不自写第二份判定），opener 改显式白名单构造、不再注册 FileHandler/FTPHandler/DataHandler；abroad 分支用进程全局 urlopen，故另加落地复核 |
| M-3 | `src/spider.py:716-720`、`911`、`1126`、`1289`、`1848`、`3324`、`3490`、`4279`、`4512`、`5137` 等 | 进 raise/日志的原始 URL 一律先过 `utils.mask_credentials`（PandaTV/WinkTV 私有房 `pwd` 明文落轮转日志为主因，抖音/TwitCasting/微博同口径收口） |
| M-4 | `src/spider.py:3908-3920` | `login_popkontv`（全文件唯一绕过 `async_req` 的生产 httpx 请求）异常文本过脱敏并补 `type_name`，防代理 `user:pass@` 外泄 |
| M-5 | `src/notify.py:92-98`、`113-155`、`173-187`、`203-205` | 录后自定义脚本四条失败分支的命令原文一律脱敏；超时后第二次 `communicate()` 加有限超时；进程树回收 POSIX 走 `start_new_session` + `killpg`、Windows 走 `taskkill /T /F`（argv 列表，禁 shell=True），失败一律退化到原 `kill` |

**二、录制与解析正确性（M-8 ~ M-13）**

| 编号 | 落点 | 内容 |
| --- | --- | --- |
| M-8 | `src/spider.py:207-324` | 快手 did / B站 buvid 的模块全局快路补 proxy 一致性判定，跨代理出口不再串用设备指纹（镜像 ttwid MIN-2220 的已修形态），锁类型与跨 await 语义未动 |
| M-9 | `src/spider.py:723`、`914`、`1173`、`1370`、`1610`、`3200` | `anchor_name` 可为 `None` 的漏网点统一到 `_dig_str` / `isinstance(v, str)`，根除 `clean_name(None)` 崩掉整轮解析 |
| M-10 | `src/spider.py:4325-4331` | TwitCasting 受限房登录回退由只接 `AttributeError` 扩为同时接住 `ValueError`（PEP 758 无括号），原「解析失败→登录重试」死分支复活 |
| M-11 | `src/stream.py:654-691` | TikTok 选档不再把 FLV 钳过的下标写回共享变量：保留原始请求索引，FLV/HLS 各按自身长度钳制（与本文件抖音分支同口径），回退基准同批修正；HLS-only 房间「选流畅实拉原画」且无降级提示的形态闭合 |
| M-12 | `main.py:4950-4959` | 弹幕平台列表改列表推导 `strip()` + 去空项，与同函数 HLS 排除列表同口径；`"斗鱼直播, B站直播"` 不再恒不命中 |
| M-13 | `src/platforms/bilibili.py:55-159` | B站 host 轮换加 `_report_close` 闸门：仍有候选未尝试属中间态（转 `_on_reconnect` 留痕），排空或 `_stopped` 终态才上报且恰好一次；轮换结束把 `_hosts_left` 归零，否则会话期真实断连被吞。未下沉 WsClient、未合并 `backup_url` 主备轮换、`src/ws_client.py` 零改动 |

**三、Web / i18n / 前端（M-18、M-19、M-21 ~ M-23、M-26）**

| 编号 | 落点 | 内容 |
| --- | --- | --- |
| M-18 | `web.py:199-239`、`258-262` | 「未启用认证不允许监听非回环」安全闸门整体上移到 `_enter_background_mode` **之前**，拒绝文案不再被 stdio 重定向吞掉；被证伪的「拒绝即零副作用退出」注释按 AGENTS 例外条款改正并压为一行历史注 |
| M-19 | `i18n.py:399-414` | `tr()` 两层 except 扩为含 `AttributeError, TypeError`（实测 `{x.y}`+None 抛 AttributeError、`{x:d}`+None 抛 TypeError），兑现「永不抛」承诺；`translated_print` 复核无同类缺口（全程不做 `.format`） |
| M-21 | `web/app.js:753-870` | 三条轮询链（SSE / 日志 / 弹幕）的续期统一经 `makePollChain()` 代次令牌：`halt()` 与 `begin()` 都推进代次，在途回调落地时代次不符即丢弃且不重排，失联定时器链不再产生 |
| M-22 | `web/app.js:1498-1560`、`web/index.html:176-190`、`web/style.css` | 认证复验口令由 `window.prompt` 明文采集改为 `type="password"` 弹窗，四个出口一律经 `_settleReauth()` 立即清空输入节点；`reauth_password` 只在认证两键的 PUT 上携带，不再污染同批其余键的请求体 |
| M-23 | `web/app.js:1107-1117` | 弹幕折叠计数 `m.dropped` 补过 `esc()`，恢复本文件「拼接路径一律转义」不变量 |
| M-26 | `tests/frontend/test_regression_2026_09_22_gates.mjs` | 删除两条钉旧源码字面量的 `doesNotMatch` 文本锁（后端已实现强制复验、字面量已漂移，断言空洞成立且与 Python 侧新契约互相矛盾），改为锁「前端认证两键路径确实采集并下发 `reauth_password`」的正向行为锁；用例数 32 → 36 |

**四、GUI 健壮性（M-14 ~ M-17、M-24、M-31）**

| 编号 | 落点 | 内容 |
| --- | --- | --- |
| M-14 | `gui.py:1110-1360`、`3627`、`3684` | 画质监控的匹配串改由**与生产侧同 msgid 的 `i18n.tr()` 结果**派生（转义后组装）并按语言惰性重算，硬编码简中常量清除；`src/recorder_status.py` 那条**未过 tr 的裸字面量**继续按原文匹配并在注释写明原因。**刻意未引入** `#DLRQ` 结构化协议（AGENTS 关键约定 #13 列为待批准长期方案）。收尾自查另修一处本批自己引入的缺陷：按语言缓存改为「组装后复验语言码未变才落键」——组装要连读 6 次 `tr()` 而录制线程与 UI 线程可并发切语言，无条件写入会把**混语** patterns 固化（回归锁 `test_mid_build_language_switch_is_not_cached`） |
| M-15 | `gui.py:1466`、`3519`、`3667`、`3132` 一带 + `gui.py:1599-1612` | `after` 自续期链的续期注册移入 `try/finally` 无条件重排；`ts` 等外部字段走统一数值容错 helper（`null` 记录不再打断定时链）。收尾补齐**第 4 支同型链** `_pump_ui_events`（UI 事件泵）：它把续期写在函数最后一句，而前面的「按需激活日志刷新链」会在窗口销毁竞态中抛错——断了即 `post_ui` 排队的收尾回调永不执行（关不掉窗口）；结构锁 `_CHAINS` 已扩到四链逐条点名 |
| M-16 | `gui.py:3226-3352`、`4175-4189` | 新增单飞入口 `_stop_child_once`：「停止录制」与「彻底退出」共用，退出复用在途停止线程而非并行第二遍控制台附着（控制台附着是进程全局状态）；在途登记与注销都落在无条件路径上 |
| M-17 | `gui.py:3801-3844` | tail 线程 try/except 下沉到**每条事件**（坏条 continue），同批完好事件不再被一条脏数据连带丢弃；最外层异常有限频 warning 留痕 |
| M-24 | `tests/test_danmaku_monitor.py:562-599` | tail 用例改为对**实际传入的那个 Event** set，并补 `assert not t.is_alive()`——「轮转后能停」第一次被真正验证（此前守护线程静默残留至进程退出） |
| M-31 | `tests/test_gui_monitor.py:79-85`、`tests/test_danmaku_monitor.py:429` | 子进程显式注入 `PYTHONUTF8`/`PYTHONIOENCODING`；`import gui` 从收集期移入用例内并配 autouse fixture 成对还原 `DLR_GUI_PARENT`（禁 `patch.dict(os.environ)`） |

**五、测试体系与维护脚本（S-2、M-25、M-27 ~ M-30、M-32）**

| 编号 | 落点 | 内容 |
| --- | --- | --- |
| S-2 | `tests/test_twitch_live_collector.py:42`、`109`，结构锁 `118-190` | 执行体整体移入 `def main()` + `if __name__ == "__main__": main()`，与其余 4 个兄弟真机脚本同构。取证：`pytest --collect-only` 由 **20.55 秒 / no tests collected / 退出码 5** 变为 **0.81 秒 / 1 test collected**，收集期真机连接、`sleep 20`、清空 `tests/_out_live`、`sys.exit(1)` 中断会话全部消失 |
| M-25 | `tests/test_huya_danmaku.py:121` | 裸赋值 `spider.async_req = fake` 改 `monkeypatch.setattr`（原形态不还原、假签名残缺，污染整个 pytest 会话） |
| M-27 | `tests/test_config_io_backup.py:20-26`、`tests/test_log_archive.py:114`、`tests/test_anchor_rename.py:15-20` | 进程全局 `os.remove`/`os.rename` 的 patch 一律改走被测模块命名空间的 `SimpleNamespace(**vars(os))` shim（窗口内不再波及 loguru 与其他后台线程） |
| M-28 | `tests/frontend/test_motion.py`（新）、`.github/workflows/ci.yml` | `test_motion.mjs` 5 条用例补 Python 包装并入 CI「Gate frontend tests not skipped」的 node-id 清单（`node --test <文件>` 只跑被点名文件、不会顺带发现同级其他 .mjs，此前这些降级/清理锁在正常 CI 中从不执行）；本批另把 WP-G 新增的 `tests/frontend/test_auth_reauth.py::test_auth_reauth` 一并登记进同一清单 |
| M-29 | `tests/test_machine_validation_fixes.py` | 心跳超时用例改为记录每次 `close()` 的**时刻与来源**并逐入口归因，断言第一次 close 发生在超时点且早于主动停止（原 `len(close_called) >= 1` 对「删掉超时分支」全盲）；同文件「三处调用都超时」的聚合计数同批收紧为逐入口 |
| M-30 | `tests/test_notify.py:27`、`63`、`74` | 子进程命令由字面量 `python` 改 `sys.executable`（只提供 `python3` 的 Linux/CI 镜像必失败、本机 Windows 恒绿的形态消除） |
| M-32 | `scripts/sync_metadata.py:112-158`、`scripts/smoke_test.py:87-192`、`214-218` | ① `shutil.which` 早退 + 捕 `OSError`，uv 缺失时 WARN 分支可达且后续 egg-info 重建照做（`--check` 只读路径零子进程，由 tripwire 用例钉住）；② `load_config` 成为唯一校验点，headers/checks 形态畸形一律走 rc=2（原 `.items()` 抛 AttributeError → rc=1，破坏 `_ci_web_smoke.sh` 区分「面板故障可重试 / 配置问题」的契约） |

**六、i18n 目录同步（S-1/M-4 新增文案）**

- 新增 4 条 msgid（Shopee 双闸 3 条 + popkontv 异常带 `type_name` 1 条）已落 `zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` 四目录并重编 `.mo`；
  并行防撞中间态 `_i18n_pending_wpa.json` 按 AGENTS 关键约定 #14 在中央合并后已删除。
- 条目数两种口径（2026-09-29 本机实读，不推算）：JSON 键数 **791**；`.mo` 头部 N **792**（含头部空 msgid，故 N = 键数 + 1）。取数命令：
  `python -c "import struct;print(struct.unpack('<6I', open('i18n/zh_CN/LC_MESSAGES/zh_CN.mo','rb').read(24))[2])"`；
  `python scripts/compile_po.py --check` 自报同为 792（.po/.mo 同步）；`python scripts/extract_i18n_strings.py` 报「缺失 0 条」。

**七、验证（真机，按 AGENTS 完成定义第 2 步）**

| 日期 | 平台 | 房间地址（脱敏） | 脚本 | 结果 | 可核对读数 |
| --- | --- | --- | --- | --- | --- |
| 2026-09-29 | 抖音 | live.douyin.com/699394970561 | `tests/test_douyin_live_collector.py` | PASS | 59 条 / SRT 4518 字节 |
| 2026-09-29 | B站直播 | live.bilibili.com/21452505 | `tests/test_bili_live_collector.py` | PASS | 9 条 / SRT 678 字节，`_report_close` 闸门下无「假关闭」 |
| 2026-09-29 | 虎牙直播 | www.huya.com/660000 | `tests/test_huya_live_collector.py` | WARN | 0 条，连接正常、该时段无弹幕（SRT 已生成） |
| 2026-09-29 | Twitch | twitch.tv/forsen | `tests/test_twitch_live_collector.py` | WARN | 0 条；守卫后独立直跑仍可用（S-2 活证） |
| 2026-09-29 | Shopee | shp.ee/****（无效短链） | 进程内探针 `spider.get_shopee_stream_url` | 拦截活证 | 落地页拼出的 `api_host=https://live.shopee.ee` 被域族白名单闸拦下并落 warning，按未开播返回——S-1 的真实出站证据 |
| 2026-09-29 | 斗鱼直播 | www.douyu.com/1、/23059、/9235411 | `tests/test_douyu_live_collector.py` | SKIP(房间未开播) | 主播名仍正确解析出（「斗鱼官方视频号」「注意前方猪妖」），解析链未坏；请用户有活房间时复跑 |
| 2026-09-29 | TikTok | www.tiktok.com/@tiktok | 进程内探针 | SKIP(无出境网络) | `ConnectTimeout` + 内置游客 cookie 过期告警；M-11 需用户在可出境网络下用真实房间、画质设「流畅」复跑，核对 `logs/PlayURL.log` 选中的 m3u8 非首档 |

**八、残余缺口与交回用户的动作**

- **GUI 目视项**：M-14/M-15/M-16/M-17 的无头验证不能替代观感——需用户切英文后重启录制，确认画质监控页仍有录制中行/降级告警/空态清除；M-22 需确认口令窗掩码显示、取消后输入节点已清空。
- **M-18**：拒绝文案现落在未被重定向的 stdout/stderr + 一条 warning，但桌面双击 `python web.py` 时控制台仍随 `sys.exit(1)` 销毁；要彻底不「一闪」需产品决策（拒绝前暂停或写横幅）。
- **逐跳复检（M-1）的三条边界**：`src/stream_select.py` 的同步探针自用 `httpx.Client`、不经 `_build_client`，同形态仍未接线；response 钩子在该跳响应已收到后才触发（闭合的是「不外流 + 不再跟随」，不是「不建连」）；DNS 重绑定窗口本层不可消除。
- **retry 动作对 rc 不敏感**：`.github/actions/retry` 对任何非 0 退出码一视同仁重试，故 M-32② 修正的「rc=2 配置问题立刻停」目前只在步日志可见，job 结论层面 1 与 2 仍不可分——需决策是否给 retry 加退出码分档入参。
- **建议的新门禁未实现**：真机脚本模板与 lint 检查（必须有 `__main__` 守卫 + 平台前缀清理）作为建议项留存，未擅自新增门禁。
- **P3 / 待核实项未动**：M-6、M-7、M-20，以及各标「待核实」的轻微项。

### v4.4.0 (2026-09-29) — GUI 卡死修复：自适应 wraplength 改「真防抖 + 迟滞」，根除 DPI 重缩放期的事件风暴互振

> 用户实测：文字高频闪烁 → 部分界面元素渲染不完整 → 整个界面卡死无响应。根因是**前一修复（自适应
> wraplength）在 `<Configure>` 里同步追写**，与 CTk 的 DPI 重缩放机制互振。触发路径 = 用户把窗口拖到
> 不同缩放率的显示器（或系统 DPI 调整）——与开发期压力探针挂死是同一机制的两个入口。

**一、根因链（全部实证）**

1. CTk 的 DPI 变化处理走 `ScalingTracker.update_scaling_callbacks_* → 控件 _set_scaling → _draw → _update_dimensions_event → update_idletasks` 的**递归互泵**（ctk_scrollbar.py 深处可见互相嵌套帧）。
2. 重缩放期间内部标签宽度剧烈瞬时摆动（探针实测 350↔1566 设备像素，同一宽度下 wraplength 被追逐成 `334→1038→190→858→…`）。
3. 旧绑定在每个 Configure 里同步 `label.configure(wraplength=…)`——每次写入使几何再失效、排进同一 idle 队列，队列永不排空：**`update()`/mainloop 永不返回 = 卡死**；高频重排 = 文字闪烁；绘制饥饿 = 元素渲染不完整。
4. 判定性对照：同一 10 次 DPI 翻转压力（走 `set_widget_scaling`，与 `check_dpi_scaling` 同一回调链）——绑定生效版 120s 泵不完（超时被杀 = 卡死复现）；绑定 no-op 化对照组 **9.2s 正常跑完**。

**二、修复（gui.py）**

| 项 | 内容 |
| --- | --- |
| 真防抖 | `<Configure>` 只重置计时器（`after_cancel` + `after(120ms)`），风暴不安静就**一次都不写**——结构性杜绝把几何失效喂回递归；刻意不用「每 120ms 节流一次」（风暴中途的写入仍可能经滚动条阈值互振重新点燃递归） |
| 迟滞 | `_wrap_should_apply(current, new, scale_changed)` 纯函数：`|new−current| ≤ max(12, 2%)` 且缩放率未变 → 不写。滚动条出现/消失的 ±~11 逻辑像素抖动被吸收；首次应用（current==0）与缩放率变化（换算基准变了）强制写 |
| 竞态守护 | `_run` 全程 TclError 守卫——弹幕/画质占位每 2s 重建，防抖回调可能与销毁竞态 |
| 启动成形 | 绑定时若已有实宽（winfo_width>1）同步先应用一次，首帧即折行；后续变更走防抖 |

**三、验证**

- 压力回归锁（`tests/test_gui_wrap_hints.py::TestRealWindowWrap::test_dpi_flip_stress_*`，真窗、无显示 skip）：完整构建 GUI + 8 次 DPI 翻转，必须排空事件循环（修复前等价场景直接超时）且每标签 wraplength 写入 ≤24（实测 ~1 次/翻转）。
- 端到端真窗终验（1120×740，150% 系统缩放）：四条长提示全部无裁切；模拟 DPI 1.2↔1.0 翻转后全部收敛到正确折行、零卡死。
- 迟滞纯函数 5 用例（无头）+ 防抖/守卫 AST 源码锁；`run_gates.py` 8/8、pytest 3308 passed/0 警告、basedpyright 0/0/0。

**四、已知微边界**

- 启动后 ~120ms 内长提示可能先以未折行形态渲染一帧（防抖首笔结算前），随后成形——不可感知级折衷，换风暴期零写入的结构性安全。

### v4.4.0 (2026-09-29) — GUI 文字截断修复：长提示自适应折行（`_bind_adaptive_wraplength`），根除 pack 两侧对称裁切

> 用户截图实测（150% DPI，默认 1120×740 窗口）：控制台「启动后将调用 main.py…」提示两侧各缺半个字、
> 弹幕占位提示右缘裁切。根因是同族的：**长文案标签请求宽超过父容器分配宽时，Tk pack 按默认
> anchor=center 两侧对称裁切**；画质页说明的定宽 `wraplength=1000` 在窄窗口下是同一失效的变体
> （右缘裁切）。全库排查共 5 处同形态，一并修复。

**一、改动按模块分类**

| 模块 | 变更性质 | 主要文件 | 关键改动 / 判据 |
| --- | --- | --- | --- |
| 自适应折行 | 新增 | `gui.py` | `_compute_wraplength(width_device_px, scale, margin)` 纯函数（设备像素→逻辑值：CTk 对 wraplength 做 DPI 缩放（`ctk_label.py` configure 时乘 `_widget_scaling`），`<Configure>` 事件给的是设备像素，须除以 `ScalingTracker.get_widget_scaling` 折回；下限 120 防止 wraplength→0 退回不折行）；`_bind_adaptive_wraplength(label)` 绑标签**自身**窗口宽（前提 `pack(fill=tk.X)`：窗口宽由 packer 分配、与标签自请求解耦，无「wraplength→请求宽→窗口宽」回环；绑定时先按当前宽设初值——重 pack 而几何不变时 Configure 不触发）；`ScalingTracker` 从 `customtkinter.windows.widgets.scaling.scaling_tracker` 显式导入（顶层命名空间不导出，类型检查报 reportAttributeAccessIssue） |
| 接线点 | 修改 | `gui.py` | 控制台提示改 `pack(fill=tk.X, expand=True)` + 绑定；画质说明去定宽 `wraplength=1000` 改绑定；画质/弹幕两个占位提示收敛到 `_make_quality_placeholder` / `_make_danmaku_placeholder` 工厂（参数 `tk.Misc`——CTk 6.0 的 CTkScrollableFrame 不是 CTkFrame 子类），初始构建与每轮刷新重建共用，文案从 4 份重复收敛为各 1 份 |
| 测试 | 新增 | `tests/test_gui_wrap_hints.py` | 三层锁：纯函数子进程单测（换算锚点 1584@1.5→1050 固化、120 下限、零/负缩放、单调性）；AST 源码锁（绑定助手定义一次且恰 4 接线点、占位文案各只出现一次、全库无定宽 wraplength kwargs、工厂必须 fill=tk.X+绑定、构建与刷新两路径都必须走工厂）；真窗用例（fill=X 标签窄容器自动折行不裁切、加宽后 wraplength 增长；无显示环境 skip——唯一 skip 面） |

**二、根因与设计要点**

1. **为什么两侧对称缺字**：pack 的默认 anchor=center 把放不下的子件在分配到的窄 parcel 里居中，超出部分两侧等量被父容器剪掉——左缘「启」缺半、右缘「制」缺半，是「请求宽 > 分配宽」的指纹性症状。
2. **为什么绑标签自身窗口宽是安全的**：`fill=tk.X` 下窗口宽完全由 packer 分配，改 wraplength 只改请求高度不改窗口宽，机制上不存在振荡；绑父容器宽则要另行扣除兄弟控件（按钮行）宽度，更脆。
3. **真窗用例刻意不调 `set_widget_scaling`**：手动缩放覆盖与 CTk 的系统 DPI 追踪在真窗映射时互相触发全量重缩放（实测事件风暴 → `update()` 永不返回）；系统自身 DPI 已让缩放折算被真实验证，换算公式由纯函数锚点锁钉死。
4. **CTk 6.0.0 两处事实**（源码核实）：`configure(wraplength=...)` 内部乘 `_widget_scaling`，`cget("wraplength")` 返回逻辑值；`CTkScrollableFrame` 的 MRO 不含 `CTkFrame`（两者仅共享 `CTkBaseClass` 祖先）。

**三、验证**

- 端到端实测（本机 Windows，150% 系统缩放，子进程构建完整 `LiveRecorderGUI`，与截图同尺寸 1120×740）：修复前控制台提示 reqwidth 768 > 实宽 ~520（两侧裁切）、弹幕占位 1564 > 1538；修复后四条长提示（控制台提示 / 弹幕占位 / 画质占位 / 画质说明）全部「请求宽 ≤ 实际宽、wraplength 生效」（540≥519、1196≥1092、1196≥540、1230≥986），控制台提示折为两行。
- `run_gates.py` 8/8 全绿；全量 pytest 3300 passed / 14 skipped / 0 警告；覆盖率 44 模块全达标；basedpyright 0 errors / 0 warnings / 0 notes；真窗用例连续三轮 8s 稳定通过。
- 回归锁：`tests/test_gui_wrap_hints.py`（10 用例）；变异验证——去掉任一工厂的 `_bind_adaptive_wraplength` 调用或把 fill=tk.X 删掉，AST 锁立即转红。

### v4.4.0 (2026-09-29) — GUI 主题层（阶段3）：语义 token 三主题 + 运行时切换 + `[GUI] gui_theme` 持久化 + WCAG 对比度机检

> 本节是本次改动的模块级总览。阶段3（UI 现代化 · GUI 主题层）新增 `src/ui_theme.py`（零显示依赖、可无头 import），
> `gui.py` 侧边栏新增「界面主题」菜单（浅色 / 深色 / 高对比度），选择即写回 `config.ini [GUI] gui_theme`
> 并注册为 ttk 主题（`dlr-<id>`，基底 clam）；`Colors` / `Fonts` 门面与全部既有符号签名不变。

**一、改动按模块分类（含新增 / 修改 + 文件路径）**

| 模块 | 变更性质 | 主要文件 | 关键改动 / 判据 |
| --- | --- | --- | --- |
| 主题引擎 | 新增 | `src/ui_theme.py` | 13 个语义槽位（提案 §5.2 十二槽 + `on_primary`：深色/高对比主题主按钮为亮蓝填充、标签需近黑前景，`surface` 兼作按钮前景在深色下不成立）；`THEMES` 三套（light / dark / high_contrast）；`contrast_ratio` WCAG 相对亮度；`CONTRAST_REQUIREMENTS` 对比度契约（正文 4.5 / 非文本与禁用 3.0）；`ThemeManager`（select/apply 幂等，`theme_create` 重复注册守卫）；`load/save_theme_preference` 走 `update_or_append_config_line`（缺节/缺键补建 + 注释保留 + 原子写），刻意不经 `config_io.read_config_value`（其写回持 `main.file_update_lock`，GUI 不进录制引擎锁体系） |
| GUI 接线 | 修改 | `gui.py` | 导入 `src.ui_theme`；`__init__` 读 `[GUI] gui_theme`——有显式偏好则按主题归属同步 CTk 外观模式，无偏好跟随系统外观（保持升级前行为）；侧边栏「界面主题」`CTkOptionMenu`（显示名经 i18n）+ `_on_theme_change`（select → apply → 持久化 → 外观模式映射 → 外观菜单显示同步 → `_sync_canvas_bg`）；`_THEME_CTK_MODE` / `_THEME_LABELS` 模块常量；`Colors`/`Fonts`/`LiveRecorderGUI`/`SystemTray`/`AdvancedSettingsWindow`/`_quality_alert_expired` 符号与签名逐字不变 |
| 模板与文档 | 修改 | `config/config.ini`、`README.md` | 模板新增 `[GUI] gui_theme =`（空 = 跟随外观）；README 配置块补 GUI 节说明 |
| i18n | 同步 | `zh_CN.po`(+`.mo`)、`en_US.json`、`en_GB.json`、`zh_TW.yaml` | 新增 7 条：界面主题 / 浅色 / 深色 / 高对比度 / 两条切换成功与写回失败文案（含 `{theme}`/`{type_name}`/`{err}` 占位符）。四目录键集一致（i18n 测试锁全绿）；`web/app.js` 无需同步——主题菜单为 GUI 独有文案，无 Web 面 |
| 测试 | 新增 | `tests/test_ui_theme.py` | 34 用例：对比度数学锚点（黑白 21:1、白压 #4F6DF5 4.34 固化）、注册表完整性（逐槽/严格 #RRGGBB）、对比度契约全对全主题参数化、持久化（缺失/非法/往返/注释保留/重复保存单行）、切换幂等（同 id 短路 + 配置字节不变）、ttk settings 纯数据断言 + 真 Tk 集成（无显示环境 skip，仅此一条） |

**二、根因与设计要点**

1. **对比度先行**：先以迭代脚本把三套主题全部 token 对调到达标（正文 4.5 / 非文本 3.0），再把取值定稿进模块；light 的 `primary` 取 `#4358E8`（品牌蓝同色相加深）——原 `#4F6DF5` 与白标签 4.34:1 不达 AA，迭代脚本已删，数值由 `tests/test_ui_theme.py` 持续回归。
2. **边框 3:1 的代价**：WCAG 1.411 非文本对比要求让 light 边框取到 `#848DA0`（比常见浅灰边框深）——机检契约优先于视觉习惯。
3. **阶段3 的可见效果边界**：CTk 控件颜色体系由阶段4（ui_kit）接管 token，本阶段主题切换的可见效果 = CTk 外观模式映射（high_contrast 归入 dark）+ ttk 元素配色（Treeview 等阶段4 控件就位后生效）；「外观模式」菜单保留（含「跟随系统」），阶段4 统一两控件。
4. **幂等三处**：`select` 同 id 短路（不重复写配置）、`save` 重复保存单行（update 优先于 append）、`apply` 重复注册守卫（`theme_create` 对已存在主题名抛 TclError）。

**三、验证**

- `pytest tests/test_ui_theme.py` → 34 passed（本机含 3 条真 Tk 集成；无头 CI 上该 3 条 skip，其余 31 条全量执行）。
- 真窗冒烟（本机 Windows，子进程构建完整 `LiveRecorderGUI`）：无偏好时跟随系统外观落 `light` 主题；菜单显示名 i18n 正确；模拟点击「高对比度」后 `theme_manager.theme_id == "high_contrast"`、`[GUI] gui_theme` 写入临时副本生效、ttk 主题切到 `dlr-high_contrast`、CTk 外观映射 Dark、外观菜单显示同步「深色」；真实 `config.ini` 未被写入（写路径重定向）。
- `python scripts/run_gates.py` → 8/8 全绿；全量 pytest 3286 passed / 14 skipped / 0 警告；覆盖率 84.07%（44 模块全达标）；basedpyright 0 errors / 0 warnings / 0 notes；`import gui` 无头导入成功（兼容性契约）。

**四、已知边界与交回**

- 真窗 Tk 集成用例在无头 CI 上 skip（ubuntu 无 X server）；若要在 CI 常态执行，可在 test job 加 xvfb（留待阶段5 一并评估）。
- 「外观模式」与「界面主题」两个控件并存属阶段3 过渡形态（前者管 CTk 明暗含跟随系统、后者管 token 主题并持久化），阶段4 控件层替换时统一。

### v4.4.0 (2026-09-29) — Web 后端 FastAPI → Starlette 迁移：自研路由适配器 + 零依赖校验层，24 条路由契约与全部安全不变量逐字保留

> 本节是本次改动的模块级总览。阶段2（UI 现代化 · 框架替换）把 Web 管理面板后端从 FastAPI 迁移到 Starlette 直接驱动：
> 删除 fastapi / pydantic 两个依赖，新增 `src/web_models.py`（纯标准库 dataclass 校验层）与 `src/web_api.py` 内 `_route`
> 适配器（复刻 FastAPI 的模型参数解析 / Query 夹取 / dict→JSON 序列化 / 同步端点线程池派发语义）。所有 24 个路由处理器
> 函数体零改动，业务逻辑与全部安全不变量（MID-*/SEV-*）逐字保留；新增 `tests/test_web_api_routes.py` 动态断言路由契约，
> 取代被敏感门禁拦截的静态基线 `web_api_routes_baseline.json`。

**一、改动按模块分类（含新增 / 修改 / 删除 + 文件路径）**

| 模块 | 变更性质 | 主要文件 | 关键改动 / 判据 |
| --- | --- | --- | --- |
| Web 后端框架 | 迁移（去依赖） | `src/web_api.py` | `FastAPI()` → `Starlette()`；24 个 `@app.post/get/...` 装饰器替换为 `@_route(app, [METHOD], path)`；5 个 `Query(...)` 参数去装饰器化改为普通默认值；`cast(FastAPI, request.app)` → `cast(Starlette, ...)`；认证中间件改 `app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)` [更正 2026-09-29 运行期验证]：初稿「`@app.middleware("http")` 为 Starlette 原生支持，逐字保留」的判断有误——Starlette 无该装饰器方法，导入即抛 AttributeError（mypy attr-defined 同证），FastAPI 该装饰器底层即 `add_middleware(BaseHTTPMiddleware, dispatch=...)`；另注册 JSON 版 `HTTPException` handler（Starlette 内建 handler 回 PlainTextResponse，会丢 `{"detail": ...}` 错误契约） |
| 请求模型校验 | 新增（零依赖） | `src/web_models.py` | 9 个 dataclass（LoginRequest / RoomCreate / RoomUpdate / RoomToggle / RoomQualityUpdate / QualityOptionsUpdate / RecordingToggle / ConfigUpdate / LanguageUpdate）以 `.parse(data)` classmethod 替代 pydantic `BaseModel`；缺字段/类型错→ValueError；bool 仅接受 Python bool；多余字段忽略 |
| 路由适配层 | 新增 | `src/web_api.py` | `_route` 装饰器工厂：`inspect.signature` 驱动分类（模型参数 / Query 参数 / request）；JSON body 经 `_read_json_body` 解析，非法体→422；Query 按 `_QUERY_DEFAULTS` 默认值与上下界夹取；同步 def 端点经 `run_in_threadpool` 派发（对齐 FastAPI 行为，避免阻塞事件循环）；非 Response 返回值统一包 JSONResponse |
| 测试 | 迁移 + 新增 | `tests/test_web_api.py`、`tests/test_web_config_locks.py`、`tests/test_danmaku_monitor.py`、`tests/test_regression_2026_09_22_web_g.py`、`tests/test_web_api_routes.py` | 5 处 `TestClient` import 切到 `starlette.testclient`；新增动态路由契约测试断言 24 条路由 method/path 精确集合 + `/web` 挂载点；删除 `tests/web_api_routes_baseline.json` |
| 依赖清单 | 同步删除 | `requirements.txt`、`pyproject.toml` | 删除 `fastapi>=0.140.0` 与 `pydantic>=2.13.4`；保留 `starlette>=1.3.1` / `uvicorn` / `python-multipart`；两侧包名集合相等性经 `tests/test_regression_2026_09_22_gates.py` 实测通过 |

**二、根因明细**

1. **性能与体积**：FastAPI 依赖 pydantic + pydantic_core，是 Web 面板主要体积大头之一；Starlette 直接驱动后移除两者，降低打包体积与启动开销（体积待 `scripts/report_bundle_size.py` 本机复测）。
2. **接线语义保留**：Starlette 不像 FastAPI 自动把 `def` 同步端点派发到线程池、也不自动解析 JSON body，缺失即阻塞事件循环或 422 行为偏差——`_route` 适配器逐项补回等价语义，处理器函数体零改动。
3. **422 契约偏差（已知）**：旧 pydantic 的字段级 422 detail 改为字符串 detail（`str(ValueError)`）；前端 `apiError()` 只读取 detail 文案，行为兼容。

**三、验证（2026-09-29 运行期复测，venv 已恢复）**

- `python scripts/run_gates.py` → **8/8 全绿**（black / isort / mypy / 注释规范 / compile_po / check_version / check_runtime_pins / pytest 兜底）。
- `pytest` → **3248 passed, 14 skipped, 0 failed，warnings summary 为空**；`--cov=src` 后 `scripts/check_coverage.py` 43 模块全部达标（总覆盖 83.98%）；`basedpyright` 0 errors / 0 warnings / 0 notes。
- `pytest tests/test_web_api.py tests/test_web_api_routes.py -q` → 165 passed, 2 skipped, 0 warnings。
- 运行期抓出并修复两处接线错误（此前仅静态验证未能发现）：
  1. `@app.middleware("http")` 在 Starlette 上导入即抛 AttributeError（P0，面板不可用）→ 改 `add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)`；
  2. 端点内 `raise HTTPException` 的响应体被 Starlette 内建 handler 写成纯文本 detail，`{"detail": ...}` JSON 契约漂移（批量安全用例转红）→ 注册 FastAPI 同款 JSON handler（headers 透传保留 Retry-After 等用法）。
- 配套修正：`scripts/check_version.py` 的 web_api 版本检查对象从 `FastAPI(version=)` 换成 importlib.metadata 动态读取形态（MIN-2262 fail-closed 语义保留，三分支变异验证通过）；`tests/frontend/test_regression_2026_09_22_gates.mjs` 的 MID-2241 字段扫描锚点迁到 `src/web_models.py`、端点截取锚点迁到 `@_route(app, ["GET"], "/api/language")`；`test_web_api.py` 的 `/health` version 断言改读同源 `_APP_VERSION`；`uv.lock`/`egg-info` 经 `sync_metadata.py` 重建（requires.txt 已无 fastapi/pydantic）。

**四、未实测与交回动作（已闭环）**

- ~~门禁全绿与运行期验证~~：已完成（见「三、验证」）。
- 仍交回后续阶段：打包体积复测 `python scripts/report_bundle_size.py dist/DouyinLiveRecorder` 需先跑一次 `build_exe.py`（本机 dist/ 为空；属阶段5 收尾项）。注意本机 venv 仍残留已卸载清单的 fastapi/pydantic 包（`pip install -r requirements.txt` 不卸载旧包），门禁与测试不受影响，打包复测前建议由用户在普通终端 `pip uninstall fastapi pydantic` 确保环境与清单一致。

**五、破坏性变更**

- 移除 `fastapi` / `pydantic` 运行时依赖；`src/web_models` 模型以 `.parse()` 读取而非 pydantic API（内部使用，对外部插件无影响）。其余路由、请求/响应形态、安全头与鉴权中间件行为不变。

### v4.4.0 (2026-09-29) — Web 前端动效层（阶段1）：滚动入场 / 视差粒子 / reduced-motion 降级，零依赖零构建

> 模块级总览：阶段1（UI 现代化 · 前端动效）新增 `web/motion.js`（223 行、零依赖 IIFE，挂载 `window.__dlrMotion`），
> `web/index.html` 加 `<canvas id="bg-canvas">` 背景层与脚本引用，`web/style.css` 增动效 token 与
> `prefers-reduced-motion` 全覆盖。**动效只加 class、不插包裹元素**——`tests/frontend/*.mjs` 的
> `tbody.innerHTML` 片段断言回归锁不受影响；动态渲染的表格行不参与入场动效。

**一、改动按模块分类（含新增 / 修改 + 文件路径）**

| 模块 | 变更性质 | 主要文件 | 关键改动 / 判据 |
| --- | --- | --- | --- |
| 动效引擎 | 新增 | `web/motion.js` | 单 rAF 循环、IntersectionObserver 入场（threshold 0.15、rootMargin `0px 0px -8% 0px`、错峰 `min(index*40, 240)ms`、命中即一次性 unobserve）、DPR 封顶 2、`document.hidden` 暂停、`prefers-reduced-motion: reduce` 全降级、`destroy()` 无残留定时器；粒子数 `clamp(18, floor(视口面积/22000), 64)`，视口 <768px 或 `hardwareConcurrency ≤ 4` 时减半 |
| 页面接线 | 修改 | `web/index.html` | `<body>` 首行加 `<canvas id="bg-canvas" aria-hidden="true">`（pointer-events:none、z-index -1）；末尾加 `<script src="/web/motion.js">`（defer，不阻塞首屏） |
| 动效样式 | 修改 | `web/style.css` | `#bg-canvas` 固定层、`.reveal`/`.is-revealed` 过渡、`:focus-visible` 焦点环、`@media (prefers-reduced-motion: reduce)` 全覆盖（动效段约 508–547 行）；过渡只动 transform/opacity/border-color/box-shadow，不触发布局属性 |
| 测试 | 新增 | `tests/frontend/test_motion.mjs` | 5 用例（node:test + node:vm 沙箱驱动 motion.js：降级闸门 / 入场 / 粒子参数 / 隐藏暂停 / destroy 清理），零 npm 依赖 |

**二、验证与已知偏差**

- `node --test tests/frontend/*.mjs` → **65/65 全绿**（既有回归锁 + 新增 5 条）；`tbody.innerHTML` 片段断言不破坏。
- **已知偏差**：motion.js 实测 9449 字节（≈9.2KB），超出提案 §5.1 的 ≤8KB 性能预算约 15%——defer 加载不阻塞首屏、单 rAF 与读写分离已达标，体积偏差留待阶段5 收尾评估（压缩/拆分均可，不影响功能）。

### v4.4.0 (2026-09-29) — Web 面板移动端适配修复：顶栏两行化 + safe-area / `dvh` 适配 + 数据表面板内滚动，消除 iPhone 16 Pro Max 与 Pixel 10 上的裁切与横向滚动

> 本节是本次改动的**模块级总览**（模块表 + 根因明细 + 验证读数）。改动面仅 Web 前端静态资源
> （`web/index.html` + `web/style.css`），Python 侧零改动；**无删除项**——未删除任何规则、元素或文件，
> 既有注释按「只增不改」惯例全部保留，本次只做「新增规则 + 改写已有声明」。

**一、改动按模块分类（含新增 / 修改 / 删除 + 文件路径）**

| 模块 | 变更性质 | 主要文件 | 关键改动 / 判据 |
| --- | --- | --- | --- |
| Web 页面骨架 | 修改 1 处 | `web/index.html` | viewport meta 补 `viewport-fit=cover`——缺省时 `env(safe-area-inset-*)` 恒为 0，安全区适配无从生效 |
| Web 样式：顶栏 | 修改（重写布局约束） | `web/style.css` | `height:56px` → `min-height:56px`；四向 padding 改 `max(20px, env(safe-area-inset-*))`；`.tabs` 加 `min-width:0`；≤768px 断点下 `flex-wrap:wrap` 拆两行（第一行品牌 + 语言/主题，第二行标签页整行横向滚动） |
| Web 样式：主内容区 | 修改 + 新增 | `web/style.css` | `.view` 左右 padding 接入安全区；`body` 新增 `min-height:100dvh`（保留原 `100vh` 作回退）与 `text-size-adjust:100%` 防横屏字号放大 |
| Web 样式：数据表 | 新增 | `web/style.css` | ≤768px 断点下 `.panel{overflow-x:auto}`，仪表盘 / 弹幕 / 文件三张表 `min-width:540px`——列头不再被压成竖排折字，改为面板内横向滚动 |
| Web 样式：控制条 / 工具条 / toast | 修改 | `web/style.css` | `.recording-control`、`.danmaku-toolbar`、`.file-header` 加 `flex-wrap:wrap`；`.toast` 定位改 `max(24px, env(safe-area-inset-bottom/right))`；`.inline-form input[type="text"]` 改可收缩的 `flex:1 1 160px; min-width:0` |
| Web 前端逻辑与测试 | **零改动** | `web/app.js`、`tests/frontend/*.mjs` | 纯 CSS/HTML 改动，不涉及 JS 行为面；既有前端套件无需新增用例（无新增 DOM 契约） |
| Python 侧（录制链路 / Web 后端 / 配置 / i18n） | **零改动** | 无 | 本次未触碰任何 `.py`、依赖清单、配置文件与四语目录 |

**二、根因明细（按问题编号，均来自两机型截图比对 + 样式表核对）**

1. **顶栏溢出（主因，两机型共现）**：`.topbar` 固定 `height:56px`、单行 flex 不换行，`.brand` 又带 `white-space:nowrap`，
   「品牌 + 5 个标签页 + 语言下拉 + 主题按钮」的最小内容宽超过两机视口 → flex 子项被压扁：截图里「仪表盘」竖排折字、
   右侧主题按钮裁出屏幕右缘，顶栏整体溢出并引发整页横向滚动。处置见模块表第 2 行。
2. **安全区缺失**：viewport 无 `viewport-fit=cover`、全样式未用 `env(safe-area-inset-*)` → 灵动岛、圆角与 Home Indicator
   会遮挡顶栏内容与右下角 toast，横屏时左右两侧同样被裁。
3. **`100vh` 视口高度**：`body{min-height:100vh}` 在移动端地址栏收展时不跟随动态视口，表现为底部被工具栏遮挡 / 布局跳动，
   改为 `100dvh`（旧浏览器回退 `100vh`）。
4. **仪表盘「正在录制」表无滚动兜底**：5 列 auto 布局在窄屏按 min-content 撑破 `.panel`，「设置画质 / 实际画质」列头竖排折字、
   行高参差。处置为「面板内滚动 + 保底宽度」，与 `#rooms-view` 既有的 `table-layout:fixed` 定宽方案**并存不冲突**
   （后者作用域仍严格限定在 `#rooms-view`，其注释约束③未被放宽）。
5. **控制条 / 工具条不换行**：`.recording-control` 的状态文本与两个按钮、`.danmaku-toolbar` 的标题与筛选下拉在窄屏互相挤压，
   加 `flex-wrap:wrap` 后换行而非压缩，触控目标保持完整。

**三、验证**

- `node --test tests/frontend/*.mjs` → **60 passed / 0 failed**（含 MIN-2241 根 `index.html` integrity / crossorigin 锁、
  `parseConfigBool` 前端一致性锁等既有 60 条，本轮未新增、未删除用例）。
- 行尾形态复核（改动后实测）：`web/style.css` CRLF=0 / LF-only=506（仍纯 LF）、
  `web/index.html` CRLF=175 / LF-only=0（仍纯 CRLF）——两文件「原本为 0 的那项」改动后仍为 0，未混入相反形态的行。
- Python 侧零改动，故本轮未跑 `pytest` / mypy / black / isort 全量门禁；`scripts/check_annotations.py` 不适用（未改 Python 文件）。

**四、未实测与交回动作（诚实边界）**

- 真机验证结果列：`SKIP(无真机 / 无远程调试通道)`。两机型视口读数（iPhone 16 Pro Max 440×956 CSS px、DPR 3；
  Pixel 10 约 412 CSS px 宽、DPR ≈2.6）取自设备规格与截图推算，本机**未**做 Safari/Chrome 远程调试或真机截图复核。
- 交回动作：清缓存后（Ctrl+F5）在真机或设备模拟器上按四项要点确认——顶栏两行完整可见且标签页可横向滑动、
  页面整体无横向滚动条、灵动岛/Home Indicator 不遮挡顶栏与 toast、三张数据表在面板内横向滚动可看全列。
- 完成定义第 2 步（真机验证）不适用于纯前端样式改动（不涉及录制链路 / 选源 / ffmpeg 参数 / 平台解析），
  但上述四项要点须由用户真机确认后才算闭环。

### v4.3.0-dev (2026-09-27) — 本日改动按模块分类总览：发布链四处修复 + finding 4/5/6 + 四文档体积整理 + AGENTS 精简 + 元数据一致性同步

> 本节是 2026-09-27 全天改动的**模块级总览**（摘要表 + 判据读数）。路径级明细已按当日整理口径外迁，
> 与其余 73 个历史清单同处一地；同日四条明细条目（发布链三处故障、finding 4/5/6 + 文档整理、`AGENTS.md` 精简）在本节下方，可交叉印证。

| 模块 | 变更性质 | 主要文件 | 关键读数 / 判据 |
| --- | --- | --- | --- |
| 打包与发布链 | 修改 `make_zip` 命名与守卫、更正 Linux ffmpeg 来源与八槽钉定；**新增** `_clean_stale_release_zips` / `_drop_stale_release_zips` / `_assert_dual_zips_are_two_files` 与 `--dual`↔`--no-zip` 互斥 | `build_exe.py` | 未删任何函数或下载源；产物名 `DouyinLiveRecorder-v4.3.0-windows-amd64-{lite,full}.zip` |
| CI 与发布工作流 | **新增** `release-guard` job 与 `Verify dist contains both lite & full zips` 步骤 | `.github/workflows/build-release.yml` | `gh release delete` 默认不删 tag；`fail_on_unmatched_files: true` 不放宽；08:14 的他人改动本会话未触碰（已备案） |
| 测试 | **新增** 9 条用例（10 个断言单元），改造 `_stub_build_steps`，更正两处注释 | `tests/test_build_exe.py` | 单文件 100 → **105 passed**；4 次变异各自只红自己那条；`DIST_DIR` 已改指 `tmp_path` 以免真删用户产物 |
| 根约定 | `make_zip` 条目补 ④⑤ 判据与 9 个锁名；protobuf 区间更正为 `>=6.33.5,<8`；体积精简 | `AGENTS.md` | 97,034 → **95,715 B**（−1.4%）；token 保全审计：`test_` 名 / CVE 编号 / `UPPER_SNAKE` 名丢失均为 0 |
| 中英 wiki | **新增** 4 条明细条目 + 本总览；73 个历史清单块外迁；109（zh）/181（en）处表格截断补回；索引与统计小节重写；「打包与发布」第 4 步更正 | `CODE_WIKI.md`、`CODE_WIKI_EN.md` | `^### v` 169 → **173 = 173**；未闭合代码 span 段落 26/18 → **0**；两侧均纯 CRLF |
| 面向用户文档 | **同日后续步骤：版本条目同步**（把 09-26 ~ 09-27 的变更并入 `v4.3.0` 条目、日期区间延至 09-27、测试读数与「本机恒红用例」的旧记述一并更正） | `README.md`（104,040 → 109,648 B）、`README_EN.md`（123,017 → 129,644 B） | 五小节条目数中英逐节相等（🐛 9 / ✨ 12 / ⚠️ 9 / 🛠️ 7 / 🧪 4）且顺序一致；`^### v` 20 = 20；两文件仍纯 CRLF。此前一致性审计中它们确属「无需更新」，本次是**新增内容**而非压缩，README 更新日志依旧不做精简 |
| 参考子文档与本机记录 | **新增** 两份文件清单附录；追加会话经验与日志 | `docs/agent-reference/changelog-file-inventories.md`（130,064 → 139,024 B）、`-en.md`（98,458 → 107,897 B）、`session-learnings.md`、`.workbuddy/memory/2026-09-27.md` | 41（zh）/ 32（en）条历史清单 + 本块；指针定位逐条命中，孤立表头 0 |
| 构建产物元数据 | **重建** egg-info，修掉两处真实漂移 | `DouyinLiveRecorder.egg-info/`（gitignored + dockerignored） | `PKG-INFO` 的 `Requires-Dist: h2` `>=4.3.0` → `>=4.4.1`；内嵌 README 补 v4.3.0 段；其余四个文件逐字节不变 |
| 依赖 / 版本 / 忽略清单 / 配置 / i18n | **仅 1 处注释修复，其余经核对确认无需更新** | `requirements.txt`（行内注释补全）、`pyproject.toml`、`Dockerfile`、`docker-compose.yaml`、`.gitignore`、`.dockerignore`、`.coveragerc-concurrency`、`config/config.ini`、四语目录 | `websockets>=14.0` 的行内注释原先断在「…14.0+ API，」（行尾注释无法续行，属真截断），按 `pyproject.toml` 同条注释补全为「12/13.x 时 `connect()` 直接 TypeError 且被重连循环吞掉，弹幕永远连不上」；**规格本身零改动**，23↔23 包名集合仍相等、`tests/test_regression_2026_09_22_gates.py` 25 passed、文件行尾仍纯 LF。其余：`python 3.14` / `node 24` 跨 workflow 同值；工具与实装版本一致；排除清单四套无缺项；`config.ini` 6 节 143 键且本轮零新增配置面；四目录 780 键集相等、`.mo` 与 `.po` 同步 781 条、提取器缺失 0 条 |

- **一致性核验读数（本轮实测，均可复算）**：`grep -c '^### v' CODE_WIKI.md CODE_WIKI_EN.md` → 173 = 173；
  `importlib.metadata.version('DouyinLiveRecorder')` → 4.3.0；`scripts/check_version.py` PASS；
  `scripts/compile_po.py --check` 同步 781 条；`scripts/extract_i18n_strings.py` 缺失 0 条；
  `pytest tests/test_i18n.py -k "keyset or sync or catalogs"` → 6 passed；
  `pytest tests/test_proto_runtime_compat.py tests/test_i18n.py` → 43 passed。
- **本轮未做（诚实边界）**：`requirements.txt` 与 `pyproject.toml` 未新增任何依赖（无需求）；`config/config.ini` 未写入
  （含凭据、被忽略，且无新增键需求）；`README*.md` 未改动（用户 09-27 口径）；`docs/agent-reference/session-learnings.md`
  仍是 `docs/agent-reference/` 内唯一 LF-only 文件（finding 7 遗留，不在本轮范围）。
> 路径级明细已逐字外迁至 [docs/agent-reference/changelog-file-inventories.md](docs/agent-reference/changelog-file-inventories.md)（条目：v4.3.0-dev (2026-09-27) — 本日改动按模块分类总览：发布链四处修复 + finding 4/5/6 + 四文档体积整理 + AGENTS 精简 + 元数据一致性同步｜小节：本日改动按模块分类总览（新增 / 修改 / 删除 + 文件路径））。

### v4.3.0-dev (2026-09-27) — `AGENTS.md` 体积精简：三处真重复消除 + 读数指针化；实测结论是「根文件已达约束密度下限」

- **动因**：用户要求精简 `AGENTS.md` 体积，保留全部核心指令/关键约束。先按冗余类别量化，再决定手法。
- **实测的冗余分布**：可外迁的**一次性实测读数**其实早已外迁干净——`BtbN 126,600,656 B / 108,761,296 B`、
  `johnvansickle 41,888,096 B`、`autobuild-2024-10-31`、`latest` 于 2026-09-26T13:22:38Z 重发、日更标签仅剩
  `09-13~09-26` 共 15 条、`api.github.com` 的 `assets[].digest` 六项读数**逐条早已存在于
  `docs/agent-reference/measured-evidence.md`「运行时上游完整性产物实测」**，而 `AGENTS.md` 又抄了一遍 →
  本轮把 SEV-10 条目与「来源增删改三处」条目里的这些数值改为指向该小节（并写明「本文件不再复制数值」）。
- **消除的三处真重复**（本文件自身的「不得出现第二份事实源」口径）：① 「关键约定」第 14 条与「已知坑 → i18n」
  的提取器盲区条目内容重叠 → 合并进第 14 条（吸收四目录文件名与「报 0 缺失假绿」两点），删除后者；
  ② 「项目概览」的版本行把「关键约定」第 1 条（`importlib.metadata` / `APP_VERSION` / `zh_CN.po`）整段复述
  → 压成一行指针；③ 「风险控制」两条路由句把细则条目里的命令与目录清单重抄一遍 → 只留判据 + 指向细则
  （命令 `pip install --ignore-installed --no-deps -r requirements.txt` 与 `downloads/`/`logs/`/`backup_config/`
  禁令在「CI / workflow 约定」「测试收尾清理临时脚本」两处细则里逐字仍在）。
  另把「格式化命令」里 `PYTHONUTF8` 父进程转发与 `reconfigure(errors="replace")` 两条同因条目合并为一条。
- **读数**：`AGENTS.md` 97,034 → **95,715 B**（−1,319，−1.4%），496 行、纯 CRLF（LF-only 0）。
- **为什么只有 1.4%（结论级，写给后来的会话）**：全文顶层条目 **224 条、平均 383 B**（口径：
  `python -c "import pathlib,re; t=pathlib.Path('AGENTS.md').read_text(encoding='utf-8'); top=[x for x in t.splitlines() if re.match(r'^([-*] |[0-9]+[.] )', x)]; print(len(top), sum(len(x.encode()) for x in top)//len(top))"`），
  逐条核对后几乎每条都是「判据 + 常量名 + 用例名 + 错误码」的不可压缩载荷。
  保全审计的实测口径：原文 997 个 code span 中仅 15 个不再以原形态出现在 `AGENTS.md`，逐条核对分别是
  ①9 个 `::test_…` 片段（改成「文件名写一次 + 用例名并列」的写法，**55 个用例名全部仍在**）与
  ②6 个已在 wiki/measured-evidence 留存的读数；`test_` 标识符、CVE/PYSEC/GHSA 与 MIN/SEV/MID 编号、
  `UPPER_SNAKE` 常量与环境变量名三类 token 的**丢失数均为 0**（仅 3 个体积字节读数按设计只留在 measured-evidence）。
  故在现有架构下体积已接近下限；要进一步下降只能改架构（把「已知坑」细则按主题外迁、根文件只留索引与硬规则），
  而这与本文件开头「『已知坑』的约束句一律留在本文件内」的自我约定冲突，**须用户先批准**，本轮未做。
- **验证**：`scripts/run_gates.py --list` 仍解析出 8 条门禁（解析器读「格式化命令」章节的 bash 围栏，本轮未动该围栏）；
  `pytest tests/test_run_gates.py tests/test_regression_2026_09_22_gates.py` → **67 passed / 1 skipped**
  （含「首条命令必须是逐字 black 门禁行」「`PYTHONUTF8=1` 前缀必须被解析为 env」「章节改名即返空」三条来源锁）；
  行尾形态不变。纯文档改动，完成定义第 2 步真机验证不适用。

### v4.3.0-dev (2026-09-27) — 发布链第四处加固：`--dual` 出包后校验两个返回路径 + 出包前清 `dist/` 陈旧 zip，并完成四文档体积整理（外迁 73 个历史文件清单块 + 补回被 `…` 截断的表格单元格）

- **动因**：上一条目收尾时并行审查代理列出 finding 1~8，用户批准已修的 1/2/3，要求补做 4/5/6，并顺带整理四份文档体积。
  4 = `make_zip` 的返回值在 `--dual` 分支被 `_ =` 丢弃，本地没有任何「两个变体真的互不相同且都落件」的事后校验，
  且 `dist/` 不清理时上一轮残留会被 `path: dist/*.zip` 扫进附件；5 = 产物名示例仍写着 `windows-x64`
  （Windows 实测架构段是 `amd64`，`x64` 只是 `_NODE_ARCH_MAP` 归一后的运行时键名）；6 = 「两条既有用例**只**断言
  `zip_path.is_file()`」不精确（其中 `test_make_zip_aborts_when_archive_still_contains_logs` 断言的是 `SystemExit` 文本）。
- **处置（`build_exe.py`，三项）**：① `_assert_dual_zips_are_two_files(lite_zip, full_zip)`——名字相同即 `SystemExit`
  （`zipfile "w"` 原地截断不报错，单次调用的守卫看不见「两次撞一个文件」），其中一个不存在同样 `SystemExit`；
  ② `_clean_stale_release_zips()` + `_drop_stale_release_zips()`——**只在真要出包时**按 `{APP_NAME}-v*.zip` 命中并删除，
  返回并打印被删清单（静默删除与不删同样糟），`--no-zip` 路径一律不清；清理点必须在**第一个** zip 之前，
  放进 `make_zip` 内会让第二次删掉第一次的产物；③ 非 `--dual` 路径接住 `make_zip` 返回值，末行打印实际产物名。
- **同族更正**：`tests/test_build_exe.py` 的截断事故注释改写成真实产物名 + 精确用例判据；「打包与发布」第 4 步
  原写「冒烟测试跑在 lite 版本上」已被 MID-2254 的顺序改动证伪，改为「冒烟排在**两个** zip 之后、跑装满运行时的发布目录」，
  并补写清理与事后校验；该步顺带修掉一处陈旧异常类名（`ChallengePageError` 已于 2026-09-23 按 MIN-2267 删除，
  实际只剩 `IntegrityError` / `NetworkError`）——同一行还留着会把代码 span 截断的 `…`。
- **回归锁（`tests/test_build_exe.py` 新增 5 条用例，全部做过变异验证）**：
  `test_dual_build_aborts_when_both_variants_land_on_one_zip`、
  `test_dual_build_aborts_when_a_variant_zip_is_missing`、
  `test_dual_build_prunes_stale_zips_before_first_zip`、
  `test_no_zip_build_keeps_existing_dist_zips`（反向锁：不出包就不许删）、
  `test_clean_stale_release_zips_only_touches_own_artifacts`（含「`dist/` 不存在时空操作」与幂等）。
  `_stub_build_steps` 的 `make_zip` 桩改为**按 suffix 产出不同名字并真实落件**——旧桩返回常量 `stub.zip`，
  接上新校验后三条 `--dual` 用例会全部误红；`DIST_DIR` 一并改指 `tmp_path`，否则测试会真删仓库 `dist/` 下的用户产物。
  变异读数：清理函数改空操作 → 2 红；`--dual` 分支去掉清理接线 → 1 红；事后校验整体失效 → 1 红；
  仅存在性校验失效 → 1 红；四次变异都只红自己那条，改完 `build_exe.py` 与备份逐字节相同。
- **文档体积整理（口径：只搬不删）**：先实测冗余，结论是四份文档**没有**可删的空白行/重复段落
  （行尾空白 0 行、连续空行 >1 的段 0 处、与 `CODE_WIKI` 逐字重复的行 README 侧仅 1 行），体积全在正文里。
  真正可动的是更新日志里 73 个「涉及文件（按模块分类）」历史清单块（zh 41 块 / en 32 块），逐字搬到
  `docs/agent-reference/changelog-file-inventories.md` / `-en.md`，原处保留小节标题 + 一行「条目名｜小节名」指针。
  同时发现并修复上一轮（2026-09-25）压缩脚本的静默信息损失：表格单元格里 109（zh）/181（en）处被
  `…` 截断的原文按前缀唯一匹配从 `.workbuddy/docold` 补回（zh +18,439 B / en +33,117 B，2 处匹配不唯一刻意跳过）。
  读数（**本条目写入前**，`README*` 与原件逐字节相同）：`CODE_WIKI.md` 638,616 → 552,368 B（−86,248，−13.5%）、
  `CODE_WIKI_EN.md` 692,281 → 649,906 B（−42,375，−6.1%）、`README.md` 104,040 B 与 `README_EN.md` 123,017 B 未改；
  新增两份附录 130,064 B / 98,458 B。用户口径确认：README 的更新日志面向使用者，不做压缩。
- **完整性自证**（可复算）：`grep -c '^### v'` 两侧仍 **170 = 170**；逐行对账「原文件里每一条非空行要么仍在原文档、
  要么在附录里」，仅上述 109/181 条被补回的表格行以旧形态消失；指针定位 41/32 条全部命中附录中真实存在的
  「条目 + 小节」对；孤立表头 0 处；未闭合代码 span 段落数由 26（zh）/18（en）降到 0；
  外迁块边界一律落在标题或「验证/影响范围/结论」类标签之前，故没有把表头与表体切开；
  四份文档 + 两份附录全部纯 CRLF（LF-only 计数 0）。
- **顺带修正的文档漂移**：`CODE_WIKI(_EN)`「文档统计与索引」原写「285 个 Markdown 文件」且未附取数命令、无法复算，
  现改为「取数命令 + 读数时刻」口径（2026-09-27 实测 100），并把审查报告的行改成真实位置 `docs/worklog/`（9 份）、
  新增 `docs/agent-reference/` 行与「参考子文档索引」小节；`CODE_WIKI_EN.md` 打包命令代码块内 9 行中文注释补英文。
  已知未做：EN 文档代码块内仍有 162 行中文（架构图与目录树标签），属翻译工作量而非体积冗余，留给后续单独一轮。
- **验证**：`scripts/run_gates.py` 8/8 rc=0（含 `check_annotations.py` PASS、平均注释密度 23.8%、
  `compile_po.py --check` 781 条同步、`check_version.py`、`check_runtime_pins.py` 全槽位钉定）；
  其内置全量 pytest 兜底 **3240 passed / warnings summary 空**（较上轮 3235 = 本次新增 5 条用例）；
  `pytest --cov=src` → 3240 passed / 14 skipped、总覆盖率 **83.91%**，`scripts/check_coverage.py`
  **PASSED：42 个模块全部达标**（`src/proto/douyin_pb2.py` 显式豁免）；`basedpyright`（不带路径）0 errors /
  0 warnings / 0 notes；`mypy`（无参）Success；black / isort 对 `build_exe.py`、`tests/test_build_exe.py` unchanged；
  `python -m pytest tests/test_build_exe.py` 单文件独立跑 **105 passed**（100 → 105）。
- **未实测与交回动作**：① 本机**未**跑 `python build_exe.py --smoke --dual`（需 PyInstaller 全量构建 + 约 300MB 上游下载），
  「清理 + 两个 zip 同时落 `dist/`」的真实链路仍由 CI 的 `Verify dist contains both lite & full zips` 首跑确认；
  ② 文档整理为纯文档改动，不涉及录制链路/选源/ffmpeg 参数/平台解析，故完成定义第 2 步真机验证不适用；
  ③ 被补回的表格单元格以 `.workbuddy/docold`（2026-09-25 整理前快照）为准，若某条原文在该快照之前就被改写过，
  补回的是快照形态；④ 若不希望历史清单外迁（要求全部留在原文档内），删除本条目两处改动即可回滚：
  两份附录文件 + 73 行指针。

### v4.3.0-dev (2026-09-27) — 发布链第三处故障：`make_zip` 用 `Path.with_suffix(".zip")` 截断产物名，lite 被 full 原地覆盖

- **现象**：`Build & Release` 这次**通过了**钉定校验与 `Build executables + smoke test`，红在下一步
  `Verify dist contains both lite & full zips`：`Found 0 lite zip(s) and 0 full zip(s)`，
  `Error: Expected both *-lite.zip and *-full.zip in dist/, but missing one or both.`，而
  `Full listing:` 明确列出一个 160,298,993 B 的文件 `dist/DouyinLiveRecorder-v4.3.zip`。
  即产物**存在**，但两个变体的名字里 `-lite` / `-full` 与 `-<os>-<arch>` 段全部消失——与前两次同族
  红（`Pattern 'dist/*-lite.zip' does not match any files`）症状同源、病因完全不同，断点又前移了一步。
- **根因**：`build_exe.make_zip()` 先拼 `zip_base = DIST_DIR / f"{APP_NAME}-v{version}-{os}-{arch}{suffix}"`
  再 `zip_path = zip_base.with_suffix(".zip")`。`Path.with_suffix` 按**最后一个点**切分扩展名，而版本号
  本身带点：本机实测三平台真实产物名截断结果一致——
  `Path('DouyinLiveRecorder-v4.3.0-windows-amd64-lite').suffix == '.0-windows-amd64-lite'` →
  `with_suffix('.zip')` 得 `DouyinLiveRecorder-v4.3.zip`（`-full` 同解；`linux-x86_64` 亦同解）。
  于是 `--dual` 的两次 `make_zip` 写到同一个路径，第二次（full）以 `zipfile` 的 `"w"` 模式截断重写第一次
  （lite），磁盘上只剩 full 的内容、却顶着一个不含任何变体/平台标识的名字。
- **为什么长期没被抓到**：`make_zip` 的两条既有用例对**名字**都不设判据（一条只断言 `zip_path.is_file()`，
  一条只断言 `SystemExit` 的文本）——名称漂移对「文件在不在」完全隐形；仓库里唯一看名字的判据是 CI 的
  `dist/*-lite.zip` 通配，所以只有真跑 `--dual` 才红。同理，非 `--dual` 路径（`ci.yml` 的 build-verify 用
  `--no-zip`）从未暴露名称丢平台段的问题。
- **处置（三项，均在 `build_exe.py`）**：① `.zip` 与其余段拼进同一个 f-string，命名保持单点定义，
  并在 `make_zip` 内写明禁用 `with_suffix` 的判据注释；② 新增结构性不变量——拼出的 `zip_path.parent`
  必须仍是 `DIST_DIR`，否则 `SystemExit`（`version`/`suffix` 含路径分隔符时 f-string 产出的是**子路径**，
  成品会静默落到 `dist/` 之外，Windows 下 pathlib 连 `\` 也当分隔符）；③ `--dual` 与 `--no-zip` 判为互斥
  并 fail-fast——`--dual` 分支从不读 `no_zip`，旧形态下 `--dual --no-zip` 会**静默无视**用户显式写的
  `--no-zip`、照样压出两个大 zip（矛盾组合要么报错要么有一个参数不起作用，不得各走一半）。
- **回归锁（`tests/test_build_exe.py`，四条 / 五个用例，全部做过变异验证）**：
  `test_make_zip_name_keeps_dotted_version_and_variant_suffix`（正则结构锁：完整 `v4.3.0` +
  `<os>-<arch>` + `-lite`/`-full` + `.zip`；Windows 实跑名形如
  `DouyinLiveRecorder-v4.3.0-windows-amd64-lite.zip`）、
  `test_dual_suffixes_do_not_collide_on_one_zip`（两次 `make_zip` 必须产出两个不同文件）、
  `test_make_zip_refuses_name_containing_path_separator`（`version` 与 `suffix` **两个入参位各测一次**，
  用 `'/'` 而非 `os.sep`，两侧平台都真实走到拒收分支）、
  `test_dual_and_no_zip_are_mutually_exclusive`（断言 `order == []`，锁「判定早于任何构建步骤」）。
  变异读数：把实现改回 `with_suffix(".zip")` → 前两条用例红，而既有两条 `make_zip` 用例仍绿（证伪旧口径）；
  把 ②③ 两个守卫改成 `if False:` → 后两条用例红（②那一删是 `FileNotFoundError`，证明断言真被执行到）。
- **验证**：`pytest tests/test_build_exe.py` **100 passed**；`run_gates.py` 8/8 rc=0（其内置全量 pytest
  兜底 **3235 passed**、warnings summary 空）；`pytest --cov=src` → `check_coverage.py` **PASSED：42 个模块全部达标**；
  `basedpyright build_exe.py tests/test_build_exe.py`
  0 errors / 0 warnings / 0 notes；`mypy`（无参）158 files Success；`black --check` / `isort --check-only`
  对两文件 unchanged；`check_annotations.py` 通过；改动文件行尾形态不变（`build_exe.py` 与 `AGENTS.md`
  纯 CRLF、`tests/test_build_exe.py` 纯 LF）。
- **未实测与交回动作**：① 本机**未**跑 `python build_exe.py --smoke --dual`（需 PyInstaller 全量构建 +
  约 300MB 上游下载），「lite + full 两个 zip 同时落在 dist/」只能由 CI 的
  `Verify dist contains both lite & full zips` 步骤首跑确认；② 已失败的这次 Release 记录由
  `release-guard` 回收（`needs.build.result != 'success'`），tag 保留，修好后重跑工作流即可；
  ③ 历史发布物里凡是 `DouyinLiveRecorder-v<主版本>.<次版本>.zip` 形态的名字都属于本缺陷产物（lite 那份
  从未真正分发出去），重跑发版才会生成带平台与变体的正确附件。

### v4.3.0-dev (2026-09-27) — 发布链修复：Linux ffmpeg 钉定改钉「月末不可变 release 标签」，并新增 `release-guard` 回收 build 失败遗留的空 Release

- **背景**：tag 推送触发的 `Build & Release` 在 Linux build job 的 ffmpeg 下载步终止，日志末行
  `[build][FATAL] _ffmpeg_temp.tar.xz SHA256 不匹配（期望 87de0900…，实际 0cfb2146…），已终止构建`；紧随
  其后的 `softprops/action-gh-release` 步骤报 `⚠️ Pattern 'dist/*-lite.zip' does not match any files`
  （`fail_on_unmatched_files: true`）。后者是「dist/ 无产物」的**连带症状**，不是独立故障——关掉
  `fail_on_unmatched_files` 只会把这唯一可见的信号抹掉。
- **根因**：`_FFMPEG_DOWNLOAD_URLS` 的 linux 两槽指向 BtbN 的 `releases/download/latest/...`。`latest` 是
  **滚动别名**：同名资产被上游反复重传，digest 随之变化——实测 tag `latest` 的 `published_at` =
  2026-09-26T13:22:38Z，即当日更早取到的钉定值 `87de0900…` 在同日即失配；linuxarm64 的 `30774c8f…` 同样
  已失效（当前 `f2fe35e9…`）。
- **处置（用户选定「换月度不可变标签」）**：两槽 URL 改钉**月末** autobuild 标签
  `autobuild-2026-08-31-13-27`（资产 `ffmpeg-n9.0.1-11-ge47273f4d9-linux{64,arm64}-gpl-9.0.tar.xz`），
  钉定值取自 `api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/<标签>` 的 `assets[].digest`
  （linux64 `182c1b50…`、linuxarm64 `e2dd447c…`）。为什么必须钉月末标签：该库全量仅 **38 条** release，
  日更 `autobuild-*` 只保留最近约两周（实测仅剩 09-13~09-26 共 15 条）→ 钉日更标签等于预埋一次 404；
  月末标签实测可回溯到 `autobuild-2024-10-31`，是 URL 与 digest 双双不可变的唯一组合。代价：内置 ffmpeg
  落后于 `latest` 的 n9.0.2（现 n9.0.1-11-ge47273f4d9），升级要人工换标签 + 换钉定值——与 SEV-10 的
  人工闸口同口径，刻意不改自动取哈希。
- **护栏（第二项）**：`build-release.yml` 新增 `release-guard` job（`needs: [prepare, build]`、
  `if: always() && 发版路径 && needs.build.result != 'success'`），build 未全绿时用 `gh release delete`
  回收 `release-create` 预建的空/残缺 Release（默认**不删 tag**）并留 `::warning::`。动因：
  `release-create` 为消除三平台并发创建竞态，刻意在 build **之前**建记录；build 失败时收尾的 `release`
  job 因 `needs: build` 被跳过，那条记录就以空 Release 形态留在仓库里，用户点进去一个附件都没有。
- **改动面**：`build_exe.py`（URL 两条 + 钉定表两格 + 三处注释/取数口径更正：维护说明、Linux 来源段、
  归档布局示例）；`tests/test_build_exe.py`（新增 `test_linux_ffmpeg_urls_pin_an_immutable_release_tag`：
  禁 `/releases/download/latest/`、禁 `n9.0-latest-` 资产名、两架构必须同一标签）；
  `.github/workflows/build-release.yml`（新增 `release-guard`，矩阵/缓存/构建/上传逻辑零改动）；
  `AGENTS.md`（SEV-10 条目补「取数端点必须是月末标签」+ 回归锁名、「CI / workflow 约定」新增空 Release
  护栏条目、体积读数按新资产更新）；`docs/agent-reference/measured-evidence.md`（2026-09-27 复测表）。
- **实测（2026-09-27）**：`releases/latest` → linux64 150,999,836 B / `0cfb2146…`、linuxarm64 127,395,868 B /
  `f2fe35e9…`（与旧钉定值均不相等）；`releases?per_page=100` → 全库 38 条；月末标签资产 → linux64
  126,600,656 B / `182c1b50…`、linuxarm64 108,761,296 B / `e2dd447c…`（另有 `checksums.sha256` 资产可供
  二次核对）；gyan.dev Windows `.sha256` 仍 `60f46726…`（未漂移）；nodejs.org 首个 `lts` 仍 `v24.21.0`
  （未漂移）。月末资产经前缀取回确认是合法 xz（魔数 `fd377a585a00`），顶层目录
  `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0/`。
- **验证**：`pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` **115 passed**；全量 `pytest`
  3229 passed / 14 skipped 且 warnings summary 为空（唯一失败 `test_web_config.py::TestFormatUrlLine::
  test_normal_line` = 沙箱 DNS 解析 `live.douyin.com` 失败，单独重跑该用例 **1 passed**，与本次改动无关）；
  `mypy`（无参）158 files Success；`basedpyright tests/test_build_exe.py` 0 errors / 0 warnings / 0 notes；
  `black --check` / `isort --check-only` unchanged；`check_annotations.py` 通过；
  `check_runtime_pins.py --strict` 仍 rc=0；`yaml.safe_load` 解析 workflow 通过且 `jobs` 顺序为
  prepare / release-create / build / release-guard / release。改动文件行尾形态不变（build_exe.py、
  AGENTS.md、CODE_WIKI*.md、measured-evidence.md 纯 CRLF；tests/test_build_exe.py 与 workflow 纯 LF）。
- **未实测与交回动作**：① 本机 `github.com` 直链被重置（前缀取回 http=000、全量取回在 5.4MB 处中断），
  「按新 URL 全量下载并比对钉定值」只能由 GitHub runner 首跑验证；② 月末资产归档内的
  `bin/ffmpeg` / `bin/ffprobe` 未由本次前缀直接确认（5.4MB 前缀只覆盖 `doc/`），沿用 09-26 对同系列资产的
  实测——缺件时 `_extract_linux_ffmpeg_binaries()` 会 `SystemExit`，不会退化成「一行 warning + 静默空包」；
  ③ Linux full 包体积随换标签变化（126,600,656 B / 108,761,296 B），须由 CI 产物经
  `scripts/report_bundle_size.py` 复核后再决定是否需要按平台调阈值。

### v4.3.0-dev (2026-09-27) — 修复发布链第二处故障：`_PINNED_RUNTIME_SHA256` 八个槽位被误改成官方签名档标记，按官方通道重新回填哈希

- **现象**：粘贴日志只有末两行 `Run softprops/action-gh-release@v3` / `⚠️ Pattern 'dist/*-lite.zip'
  does not match any files`。该行的判读口径与上一条同源（`fail_on_unmatched_files: true` 是产物缺失的
  唯一可见信号，不得关闭）。但本机复算时发现**当前工作区还有第二处、且更早发作的故障**：
  `build_exe.py` 的 `_PINNED_RUNTIME_SHA256` 中 8 个槽位取值被整体写成 `OFFICIAL_SIGNATURE_PIN`
  （文件 mtime 07:58，晚于上一条 01:45 的收尾记录），使发布链断点由 build job 前移到 prepare job。
- **根因**：签名档只适用于「上游确实不公布哈希、且已在 `_RUNTIME_GPG_SIGNATURES` 登记签名 URL +
  完整 40 位主钥指纹」的槽位，本仓只有 macOS 的 ffmpeg/ffprobe 四槽符合。node 五槽（nodejs.org
  `SHASUMS256.txt`）、windows-x64/ffmpeg（gyan.dev `.sha256`）、linux 两槽 ffmpeg（BtbN 资产的
  `assets[].digest`）都有官方公布值，改成标记后 `_is_signature_satisfied` 因「该槽未登记」判 False
  → `_slot_is_gated` 三个析取项全 False。两条后果：`scripts/check_runtime_pins.py --strict` **rc=1**
  （prepare 的 fail-closed 步直接红），以及 `tests/test_build_exe.py::
  test_table_never_declares_signature_mode_without_satisfaction` **转红**（该锁正是为拦下这种改写而存在）。
- **处置**：8 个槽位一律按 AGENTS.md/`build_exe.py` 维护说明的**官方通道**重新取数后回填，
  **未**使用本地下载自算值：
  `curl -sS https://nodejs.org/dist/v24.21.0/SHASUMS256.txt`（win-x64 `.zip`、linux/macos `.tar.gz`
  五种资产，扩展名与 `_download_nodejs` 实际取用的包一致）；
  `curl -sSL https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256` → `60f46726…47ba`
  （未漂移）；`curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27`
  → linux64 `182c1b50…` / linuxarm64 `e2dd447c…`（与 measured-evidence.md 记录逐字相等，月末标签 digest 不可变）；
  并确认 `dist/index.json` 首个 `lts` 仍 `v24.21.0`（Krypton）。macOS 两槽的 ffmpeg/ffprobe 保持签名档不动。
- **改动面**：仅 `build_exe.py`（钉定表 8 格取值 + 表头一行 `[2026-09-27 恢复]` 注 + 每条 node 行的来源资产名注释）；
  逻辑、URL 表、判定函数、测试与 workflow **零改动**。
- **验证**：改前 `check_runtime_pins.py --strict` **rc=1**、`test_table_never_declares_signature_mode_without_satisfaction`
  FAILED（offenders 逐槽点名 8 个）；改后 `--strict` 与结构模式均 **rc=0**，`pytest tests/test_build_exe.py`
  **95 passed**，`python scripts/run_gates.py` **8/8 全绿 rc=0**，全量 `pytest` **3230 passed / 14 skipped**
  且 warnings summary 为空，`basedpyright build_exe.py` 0 errors / 0 warnings / 0 notes，
  `black --check` / `isort --check-only` / `py_compile` 均通过。行尾形态不变（build_exe.py 纯 CRLF，
  1686 个 CRLF / 0 个孤立 LF）。
- **未实测与交回动作**：① 「按钉定值全量下载并比对」仍只能由 GitHub runner 首跑验证——本机 `github.com`
  直链被重置，只有 `api.github.com` 与 `nodejs.org`/`gyan.dev` 可用；② 本次会话期间 `build-release.yml`
  在 08:14 被**并行**改动（新增 `Verify dist contains both lite & full zips` 一步、构建命令加 `| tee build_exe.log`），
  该文件不由本条改动、也未由本条复核，`pipefail` 下 `tee` 不会吞掉 `SystemExit`，但发版前请由作者确认。

### v4.3.0-dev (2026-09-26) — 发布链完整性门禁新增「官方签名档」，Linux ffmpeg 换源 BtbN：让 `build-release.yml` 的 prepare 由 rc=1 转 rc=0，同时不放宽 SEV-10 的 fail-closed 语义

- **背景**：`build-release.yml` 的 prepare job 在 `Verify runtime binary SHA256 pins (fail-closed)` 一步报
  `Error: Process completed with exit code 1.`，日志正文即 `scripts/check_runtime_pins.py --strict` 的输出：
  矩阵内 2 个槽位（`linux-x64/ffmpeg`、`macos-arm64/ffmpeg`）仍是占位标记。定位结论——报错步骤在
  `.github/workflows/build-release.yml:141-149`，rc=1 由 `check_runtime_pins.py` 的 `--strict` 分支返回；
  这不是缺陷而是门禁按设计拦停（`build_exe.py` 钉定表注释与 `AGENTS.md` SEV-10 条目均写明「上游不公布哈希时
  宁可让发布链红」）。
- **为什么不删门禁**：钉定表不在工作流里（事实源是 `build_exe._PINNED_RUNTIME_SHA256`，workflow 只有
  `DLR_RUNTIME_SHA256` 透传）；且 `require_pinned_hashes()` 在 `GITHUB_ACTIONS=true` 下自动为真，删掉 prepare
  那步只会把同一处失败从 prepare 后移到三个 build job（各先跑完 pip 安装、仍在下载前 `SystemExit`），产物数不变 0。
- **处置（用户选定「按上游能力分档」）**：类别 ①「发布期运行时二进制」在**同一口径**
  `build_exe._slot_is_gated()` 下并上第二档**官方签名档**——取值 = `OFFICIAL_SIGNATURE_PIN` 标记，且该槽在
  `_RUNTIME_GPG_SIGNATURES` 确有登记、指纹为 40 位十六进制（标记本身绝不构成放行，与第 4 类 `SOURCE_BUILD_PROVENANCE`
  同一条「换个更容易填的标记拿免检」防线）。macOS 两槽（evermeet 只给 `/sig` 不给哈希）走该档；Linux 两槽换源到
  BtbN 的 n9.0 系列资产，取 `api.github.com` 的 `assets[].digest` 作官方公布哈希正常钉定，故不需要 MD5 降级档。
- **顺带修掉 SEV-2221**：`_download_file()` 下载前的闸口原只认 `_is_pinned()`，而验签调用点在下载后、
  「哈希已过」分支内——占位值的 macOS 槽永远走不到下载，那一档 P-2 验签在真实构建路径上**一次都没跑过**。
  现闸口认两档，签名档槽位下载后**必须**验签（BADSIG / 指纹不在环内 / 发布路径 gpg 缺失或取不到签名一律
  `SystemExit`），并把实测 SHA256 打进食包日志作滚动别名的审计线索。
- **改动面**：`build_exe.py`（新常量与谓词、`_download_file` 分派、`_unpinned_action` 报错点名「签名档未满足」
  的具体原因、`_FFMPEG_DOWNLOAD_URLS` Linux 两条、钉定表 4 格、Linux 解压抽成布局无关的
  `_extract_linux_ffmpeg_binaries()`）；`scripts/check_runtime_pins.py`（按档 `[NOTE]` 播报，判定仍委托
  `_slot_is_gated`）；`tests/test_build_exe.py`（+12 用例：签名档真值表、大小写无关、指纹形状关、表/登记同批不变量、
  SEV-2221 可达性锁、验签失败与 gpg 缺失必须终止、未登记标记不得发起下载、两种归档布局与缺件终止；`_ALLOWED_HOSTS`
  增 `github.com` 移除 `johnvansickle.com`；`_FakeResponse` 补 `headers` 与分块排空）；
  `tests/test_check_runtime_pins.py`（`_fake_module` 暴露新符号 + 2 条签名档分流用例）；
  `.github/workflows/build-release.yml` **仅注释**（4 处：`DLR_RUNTIME_SHA256` 说明、prepare 步说明、来源主机清单、
  gnupg 步骤「验签已是唯一判据」），矩阵/缓存/构建/上传/Release 逻辑零改动；`AGENTS.md`（SEV-10 条目、三类边界条目、
  新增「发布面来源增删同改三处」条目）；`docs/agent-reference/measured-evidence.md`（本次全部取数命令与读数）。
- **实测（2026-09-26）**：`evermeet.ca/ffmpeg/getrelease/zip/sig` → 200 / `application/pgp-signature` / 594 B 二进制
  OpenPGP 包，落点 `e.deolaha.ca:4242/pub/ffmpeg/ffmpeg-9.0.2.zip.sig`；`keys.openpgp.org` 查
  `0x476C4B611A660874` → 200，UID `static FFmpeg binaries (signing key)`，服务端回显指纹 ≡ 钉定值（**独立第二渠道**，
  R-2 的「指纹未经二渠道确认」就此解掉）；`johnvansickle ...amd64-static.tar.xz.md5` → 200 且取值与 09-22 逐字相同、
  `.sha256` → 404；BtbN `linux64-gpl-9.0` 150,998,508 B / `linuxarm64-gpl-9.0` 127,417,700 B，归档成员经前缀取回后
  `tar -tJf` 实测为 `bin/ffmpeg`、`bin/ffprobe`。
- **验证**：`scripts/run_gates.py` 8/8 全绿；`pytest` 全量 **3220 passed 且 warnings summary 为空**；
  `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` 105 passed；
  `check_runtime_pins.py --strict` 由 rc=1 → **rc=0**（两条 `[NOTE]` 明确说「走官方签名档」而非「已钉定」）；
  5 条变异全部被抓红（漏并签名档 / SEV-2221 回退 / 光标记即满足 / 写死 `bin/` 布局 / 缺件不终止）。
- **未实测与交回动作**：① 本机 `github.com/.../releases/download/...` 直链 `Connection was reset`，
  「按来源表全量下载并比对钉定值」只能由 GitHub runner 首跑验证；② evermeet 验签在真实构建路径的首次执行即
  macOS CI 跑（`--recv-keys` 能否成功已由 keyserver 探针旁证，但 `gpg` 全流程未在本机跑过）；③ Linux full 包体积
  因换源大幅上涨（见上表读数），`report_bundle_size.py` 本机无 Linux 未实测，须由 CI 产物复核后再决定是否需要
  按平台调体积门禁阈值。滚动别名只钉住「谁签的」钉不住「哪个版本」，evermeet 出新构建时 macOS 产物会随之变化而
  门禁不会拦——这是该档的固有边界，靠日志里的实测 SHA256 做事后审计。

### v4.3.0-dev (2026-09-26) — CI typecheck 门禁补装固定版本 pytest，并修掉 `tests/test_proto_runtime_compat.py` 的 `[return]` 误报：消除「本机绿、CI 红」的检查面漂移（纯 CI / 测试改动，零运行期变更）

- **背景**：CI 的 `typecheck` job 报 `tests/test_proto_runtime_compat.py:33: error: Missing return statement  [return]`（checked 159 files），而本机 `mypy` 158 files 全绿、完全无法复现。
- **根因**：该 job 只装 `requirements.txt + mypy`、**未装 pytest** → `import pytest` 被解析为 `Any`，`pytest.fail()` 的 `NoReturn` 标注丢失，mypy 认为 `_declared_protobuf_specifier() -> str` 可能隐式返回 `None`。这是环境差异而非代码缺陷；同一原因还意味着 `tests/` 里所有 `pytest.*`（fixture / `MonkeyPatch` / `raises`）此前**全部免检**——门禁本就是半盲的。本机复现手法：`mypy --no-site-packages`（遮蔽已装包即可精确复现同一条；该模式额外多出的 5 条 `no-any-return` 属过度剥离噪声）。
- **改动性质**：只改 CI 工作流 + 一条测试辅助函数 + `AGENTS.md`；`src/`、`main.py`、`gui.py`、`web.py`、`web/app.js`、`requirements.txt` / `pyproject.toml` 零改动，未增删任何依赖（pytest 只进 typecheck job 的临时安装，不进运行时清单）。

**涉及文件（按模块分类）**：

> 明细清单已逐字外迁至 [docs/agent-reference/changelog-file-inventories.md](docs/agent-reference/changelog-file-inventories.md)（条目：v4.3.0-dev (2026-09-26) — CI typecheck 门禁补装固定版本 pytest，并修掉 `tests/test_proto_runtime_compat.py` 的 `[return]` 误报：消除「本机绿、CI 红」的检查面漂移（纯 CI / 测试改动，零运行期变更）｜小节：涉及文件（按模块分类））。

**验证**：`mypy`（无参）与 `mypy --platform linux` 均 Success 158 files（本机 pytest 9.1.1，与 CI 新口径同版本）；`mypy --no-site-packages` 下原 `[return]` 已消失，仅剩 5 条剥离噪声；`basedpyright tests/test_proto_runtime_compat.py` 0 errors / 0 warnings / 0 notes；`black --check` unchanged；`pytest tests/test_proto_runtime_compat.py` 4 passed；`yaml.safe_load` 解析 `ci.yml` 通过且 outputs / steps 结构如预期；改动文件行尾形态不变（`ci.yml` 纯 LF，`AGENTS.md` 与该测试文件纯 CRLF）。

**遗留观察**：CI 那次运行报 `checked 159 source files`，本机按 `[tool.mypy].files` 口径数出 158 个 `.py`，差 1 个未定位（疑为该次运行所在提交上的多余文件），与本次修复无关。

### v4.3.0-dev (2026-09-26) — 仓库元数据与文档同源同步：依赖表 / 目录树 / egg-info / 忽略清单对齐，清理已删除模块 `weverse_auth` 的残留记载（纯元数据与文档改动，零运行期代码变更）

- **背景**：全仓通读核对「版本 / 依赖 / 目录树 / 忽略清单」四类同源信息，发现多处滞后：`CODE_WIKI*.md` 依赖表仍停在 16 条且 `starlette` 下限写着 `>=0.49.1`；目录树仍列 2026-09-23 已删除的 `src/weverse_auth.py` 与 `tests/test_weverse_auth.py`；`DouyinLiveRecorder.egg-info/requires.txt` 缺 2026-09-23 补入的 `h2`/`socksio`；`AGENTS.md` 依赖条数仍写 21 条。
- **改动性质**：只改文档 / 元数据 / 忽略清单并重建 `egg-info`；`src/`、`main.py`、`gui.py`、`web.py`、`web/app.js` 零改动，运行期依赖集合未变（两侧各 23 条、包名集合逐项相等）。

**涉及文件（按模块分类）**：

> 明细清单已逐字外迁至 [docs/agent-reference/changelog-file-inventories.md](docs/agent-reference/changelog-file-inventories.md)（条目：v4.3.0-dev (2026-09-26) — 仓库元数据与文档同源同步：依赖表 / 目录树 / egg-info / 忽略清单对齐，清理已删除模块 `weverse_auth` 的残留记载（纯元数据与文档改动，零运行期代码变更）｜小节：涉及文件（按模块分类））。

**验证**：`scripts/check_version.py` rc=0（`pyproject.toml` 为版本唯一事实源，四处消费方均动态读取）；`scripts/check_runtime_pins.py` rc=0；`pytest tests/test_regression_2026_09_22_gates.py tests/test_build_exe.py` 全绿（含「requirements.txt 与 pyproject 包名集合相等」回归锁）；`pytest tests/test_i18n.py tests/test_i18n_migration.py tests/test_i18n_tr.py tests/test_frontend_*.py` 56 passed；`node --test tests/frontend/*.mjs` 通过。

**交回用户（需人工裁定）**：`config/config.ini` 的 `禁用SSL证书验证的平台(逗号分隔)` 现为 `虎牙直播,B站直播,抖音直播`，而代码强制集 `main.SSL_DISABLE_REQUIRED_PLATFORMS` 只有 `虎牙直播`/`B站直播`、README 默认值同为这两个。`抖音直播` 一项属历史遗留的额外豁免（会关闭抖音拉流的证书校验），是否移除由用户决定——本次未擅自改动安全相关开关。

### 更早的更新日志（已归档）

164 条 2026-05-17 ~ 2026-09-24 的逐日开发记录已于 2026-09-28 逐字迁出至 [code-wiki-history-zh.md](docs/changelog/code-wiki-history-zh.md)；该卷同时按 `.workbuddy/docold` 基线回补了上一轮粗剪留下的行尾 `…` / 句中截断（口径见其卷首）。
迁出原因：仅「更新日志」一节就占本文件 68.6% 的字符数（242,626 / 353,821）。根文档只保留当前发布周期的条目 + 本指针，正文才恢复可读。
