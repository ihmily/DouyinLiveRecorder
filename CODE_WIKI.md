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
| `code-wiki-history-zh.md` | 本文档更新日志的 193 条历史条目（2026-05-17 ~ 2026-10-17；2026-10-18 再迁入 v4.4.0 20 条 + v4.3.0-dev 9 条） | `CODE_WIKI.md`「更新日志」 |
| `code-wiki-history-en.md` | 同上条目的英文对应版（193 条，与中文版一一对应） | `CODE_WIKI_EN.md`「Changelog」 |
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
| PySide6 (Qt6) + pystray + Pillow | GUI 图形界面与系统托盘（2026-10-17 起窗口层为 `src/gui_qt/`；tkinter.ttk 实现迁移期保留） |
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
├── gui.py                               # GUI 图形界面入口（委托 src/gui_qt/，PySide6 窗口层；tkinter 实现迁移期保留）
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

> **2026-10-17 起窗口层已迁到 PySide6**：本节描述的是迁移期保留的 tkinter 实现（`_legacy_main()`），现行窗口实现见 `src/gui_qt/`（`app.py` 装配 / `theme.py` 设计令牌与 QSS / `widgets.py` Card·Toast·DataTable / `main_window.py` 主窗 / `pages/` 五页 / `recorder.py`·`danmaku_monitor.py` 控制器），视觉事实源 `docs/gui-redesign/index.html`，详见「更新日志」当日条目。

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
| PyExecJS | >=1.5.1 | JS 执行引擎回退兼容（exejs 未安装时使用） |
| PySide6 | >=6.12.0 | GUI 窗口层（`src/gui_qt/`，QSS token 主题 + Qt 控件；下界 6.12 为本机实测支持 Python 3.14.8 的最小版） |
| pystray | >=0.19.5 | 系统托盘（GUI / Web 托盘模式） |
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

## 改动总览（按模块分类，2026-10-17）

> 范围口径：基线 `72d1664`（本会话开始时的 HEAD）→ 当前工作区（读数取 2026-10-17 23:00），覆盖**已提交**（`553b036`）、**未提交**与**仅存在于暂存区**三类变更。本轮**没有删除文件**；被移除的只有 i18n 目录里的 6 条孤儿条目（见第 1 节），配置键未被移除。
>
> 并发工作包提醒：`src/config_read.py` 与 `tests/test_config_read.py`（未跟踪）及 `main.py`、`src/gui_qt/{settings_dialog,widgets,danmaku}.py`、`src/ui_{motion,scale,theme}.py`、`tests/test_config_io.py` 的改动**不属本代理**，不计入下表；它新增的模板 `config.ini 存在重复配置项，已按最后一次取值读取: {detail}` 曾有一度未登记，使 `tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 短暂为红（当时提取器报的唯一缺失项即此条）；该包随后自行补齐四目录，复测缺失 0 条、`test_i18n_migration.py` + `test_i18n_raise_site_tr.py` 8 passed。
>
> 标注图例：〔破坏性〕改变对外契约 / 镜像内容 / 安装产物；〔配置〕涉及配置项或默认值；〔依赖〕涉及依赖或版本常量；〔字符串契约〕改动的是可能被别处按字面比对的文本。

### 1. 本地化目录（i18n）

- **修改内容** · `i18n/zh_CN/LC_MESSAGES/zh_CN.po`、`i18n/en_US.json`、`i18n/en_GB.json`、`i18n/zh_TW.yaml` — 补 5 条 Qt 侧栏导航 msgid（两空格形态，按名传入 `tr()`，提取器看不见），四目录键数 1110 → 1115
- **修改内容** · 同上四份目录 — 〔字符串契约〕补 16 条 raise 位中文文案 msgid（`main.py` 7 条 / `src/spider.py` 3 条 / `src/web_models.py` 6 条），键数 1115 → 1131
- **修改内容** · 同上四份目录 — 补 1 条字体复制失败的日志模板 msgid，占位符为 `{name}`/`{target}`/`{type_name}`/`{err}`，键数 1131 → 1132
- **修改内容** · `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` — 由 `scripts/compile_po.py` 重编：1133 条 / 149 505 字节（含头部空 msgid，N == 键数 + 1）；四目录键集合逐项相等；`.po` 头部日期更新为 2026-10-17
- **修改内容** · 同上四份目录 — **收回 6 条孤儿裸文本键**（`停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志`）：它们是 GUI 层改带图标键后失去调用点的历史条目，AST 全仓扫字符串常量确认无任何消费者（`停止录制` 只在 `web/app.js` 内嵌目录里作为**值**出现，与后端键无关）。四目录键数 1132 → 1126，`.mo` 重编为 1127 条 / 149 231 字节
- **说明** · `开始录制`（四目录保留） — 同形裸键但**不收回**：`tests/test_i18n.py::test_load_translations_priority` 与 `::test_set_language_hot_swaps_translator` 拿它当样本 msgid 验证「`.mo` 优先于 JSON/YAML」的三档加载与热切换，收回即打红两条机制用例。该耦合已写进 `AGENTS.md` 盲区清单

### 2. GUI 窗口层（`src/gui_qt/`）

- **修改内容** · `src/gui_qt/main_window.py`、`src/gui_qt/pages/dashboard.py`、`src/gui_qt/pages/config.py`、`src/gui_qt/pages/runlog.py` — 9 处按钮的构造标签与 `T()` 登记键统一为**同一个带 emoji 的既有目录键**（三空格形态），修掉「启动回填与每次 `retranslate_all()` 把图标打回裸文本」的故障；四目录零新增
- **新增功能** · 同上 4 个文件 — 在配对处补「构造标签必须与登记键同 msgid」的理由注释：完整表述留 `main_window.py`，其余三个文件各一行指向它（避免第二事实源）

### 3. GUI 字体模块（`src/ui_fonts.py`）

- **修改内容** · `src/ui_fonts.py::install_font_file` — 〔依赖〕`except Exception: return None` 之前先落一行 `logger.warning(i18n.tr("复制字体文件失败: {name} -> {target} - {type_name}: {err}", name=src.name, target=str(target), type_name=type(e).__name__, err=e))`；被占用 / 目录只读 / 磁盘满 / 源文件被移走这几种在 UI 上同形的成因从此可归因。模块新增 `import i18n` 与 `from src.logger import logger`
- **修改内容** · `src/ui_fonts.py::_safe_filename`、`src/ui_fonts.py::_WIN_RESERVED_NAMES` — 〔配置〕新增 Windows 保留设备名清洗（`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`：整段基名、大小写不敏感、加 `_` 前缀且幂等；`COM10` 刻意不算）。理由是跨构建/跨 API 的可移植性——本机 Windows 10.0.26300 实测 `CON.ttf`/`AUX.ttf` 反而能落成普通文件；清洗后的名字会写进 `gui_font_file` 持久化并在下次启动读回

### 4. 录制链与平台解析（`main.py` / `src/spider.py`）

- **修改内容** · `main.py`（`_hy_fan_path_segment`、`_b23_tv_path_segment` 及两支短链解析器，共 12 处） — 〔字符串契约〕中文 raise 文案改为在产生点 `i18n.tr(...)`：这些消息原先被当 `{reason}` 实参插进一条已翻译的日志模板，模板查表、消息从不查表，所以只有产生点接表才有目录意义。成功路径未改动
- **修改内容** · `src/spider.py`（TTingLive 登录、TwitCasting、微博，共 3 处） — 〔字符串契约〕TTingLive 登录失败整句接 `tr()`；TwitCasting/微博两处 f-string 改写为常量模板 + 命名实参 `{masked_url}`（脱敏仍由调用方求值后传入），与既有斗鱼站点同形态
- **说明** · `src/spider.py::XhsUrlError` 的 9 条消息 — 刻意**不接** `tr()`、**不登记**：`src/spider.py` 两处 `except XhsUrlError` 与 `main._resolve_xhslink_com` 一律只读 `e.code`，message 从不显示，登记即造死条目。已由 `tests/test_i18n_raise_site_tr.py` 的白名单集合相等钉住

### 5. Web 面板后端（`src/web_models.py`）

- **修改内容** · `src/web_models.py`（`_as_str`/`_as_opt_str`/`_as_bool`/`_as_str_list`/`_require_dict`，共 6 处） — 〔字符串契约〕422 校验文案接 `tr()`，f-string 改常量模板 + 命名实参 `field=`（不变量①：模板必须是字面量、占位符只能是纯标识符）
- **修改内容** · `src/web_models.py` 导入段 — 〔依赖〕新增 `import i18n`（该模块「零依赖」原指不引 pydantic/fastapi；`i18n` 只依赖 stdlib + loguru，不回指任何 `web_*` 模块，无环）。面板按 `detail` **键**取错误文本、未钉具体文案，故前端契约不受影响

### 6. 容器与部署（`Dockerfile` / `docker-compose.yaml`）

- **修改内容** · `Dockerfile`（两阶段各一条 `ARG INSTALL_GUI=false`） — 〔破坏性〕〔配置〕镜像的 GUI 依赖改由单开关控制：阶段 1 默认从依赖清单剔除 PySide6，阶段 2 仅在开关为 true 时装 Qt 运行库（`libEGL`/`libGL`/glib/fontconfig/xkbcommon 等）。默认 false 使只跑 `main.py`/`web.py` 的镜像不再装整只轮子
- **修改内容** · `docker-compose.yaml`（`gui` 服务） — 〔配置〕`gui` 服务显式传 `INSTALL_GUI: "true"` 并改用独立 tag `:latest-gui`——build 配置不同的服务共用同一 image 名时，后构建的一方会覆盖另一方正在使用的 tag
- **说明** · `.github/workflows/docker-publish.yml` — 发布链**不传** true，对外镜像保持 slim（该文件本轮未改，作为约束的另一半登记在此）

### 7. CI 与门禁工具链（`ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json`）

- **修改内容** · `.github/workflows/ci.yml` — 〔依赖〕`black_version` 26.5.1 → 26.10.1，与本机实装同值；抬值前用两版各跑一次全量 `black --check`，两版结论逐字相同（这才是判据本体）——抬常量只消除版本差，不等于 CI 实跑已验证
- **修改内容** · `.pre-commit-config.yaml` — 〔依赖〕black mirror rev 25.9.0 → 26.10.1、isort 6.1.0 → 9.0.2，使「本地 venv / CI 钉定 / 提交钩子」三面只剩一个版本值；两个 rev 的存在性经 GitHub API 核实、`validate-config` 通过，但本机 clone 被代理拦住，「钩子真的装起来跑一遍」仍未验证
- **新增功能** · `pyrightconfig.json` — 〔配置〕IDE 语言服务器与 `pyright` CLI 的共用配置：include 逐项等于 `[tool.mypy].files`、exclude 覆盖 mypy 与 basedpyright 两份清单、typeCheckingMode/pythonVersion/venv 同 `[tool.basedpyright]`。此后不带路径跑 `pyright` 即复现 IDE 扫描面；Pylance 本体因许可证不得被 shell 驱动，这条才是「IDE 结论可复核」的正解

### 8. 包元数据与派生产物（`pyproject.toml` / `egg-info` / `coverage.json`）

- **修改内容** · `pyproject.toml`（`[tool.setuptools]` 的 `packages`） — 〔破坏性〕〔依赖〕增补 `src.gui_qt`、`src.gui_qt.pages`：显式 `packages` 不递归发现，漏列会让 `pip install .` 产出的发行包缺这两个子包，`douyin-recorder-gui` 入口在导入链第一段就 `ModuleNotFoundError`
- **修改内容** · `DouyinLiveRecorder.egg-info/SOURCES.txt` — 〔依赖〕派生产物随上条重建（`python scripts/sync_metadata.py`）。`uv.lock` 与 egg-info 都是 pyproject 的派生消费方，不得手改版本字段；`sync_metadata.py --check` 复验一致
- **修改内容** · `coverage.json` — 由 `pytest --cov=src --cov-report=json` 重新生成：总覆盖 83.02% → 83.04%；`scripts/check_coverage.py` 报 68 个模块全部达标（`src/proto/douyin_pb2.py` 为显式豁免的 protoc 生成物）

### 9. 配置基线（`config/config.ini`）

- **修改内容** · `config/config.ini`（已提交部分） — 〔配置〕补齐默认键并与 `README.md`/`README_EN.md` 配置块、代码 fallback 逐项对账。该文件是**已跟踪的脱敏基线模板**，`.gitignore` 对它不生效，本地填入真实 Cookie / 代理 / 面板密码后不得提交
- **待处置** · `config/config.ini`（仅存在于暂存区的一行） — 〔破坏性〕〔配置〕暂存副本含同一节内的重复键 `是否启动时清理陈旧字节码缓存(是/否)`（第 5 行与第 44 行同处 `[录制设置]`），会让 `RawConfigParser()`（默认 `strict=True`）在下一次 `read()` 抛 `DuplicateOptionError`，即基线配置不可读。工作区已还原为与 HEAD 一致；**索引里那份未动**，清理动作 `git restore --staged config/config.ini` 交回维护者。写入侧根因未定位（单跑一次读取+补写不改写文件、`config_parser.write()` 只产出 1 份键、复跑整条 `run_gates.py` 也未复现），故本轮不声称已修，危害与复现判据已写进 `AGENTS.md`

### 10. 测试（`tests/`）

- **新增功能** · `tests/test_i18n_catalog_coverage.py`（3 用例） — 把 i18n 盲区④从「人工登记」升级为机检：按名传入 `tr()`/`T()` 的候选 msgid 必须四目录齐全、四目录键集合逐项相等、解析不出的调用点走白名单集合相等（新增即红，消解后不收回也红）
- **新增功能** · `tests/test_i18n_raise_site_tr.py`（2 用例） — 盲区⑤：未接 `tr()` 的中文 raise 站点走白名单集合相等（现 10 条），已接的 msgid 断言四目录齐全，并用锚点防「解析结果为空 = 假绿」
- **新增功能** · `tests/test_gui_qt_label_parity.py`（2 用例） — AST 收集「构造标签」与「`T()` 登记键」两张表按控件属性名配对判等，另设带 emoji 配对下限（9）与「登记键必须四目录齐全」两条判据；行为侧证据走 offscreen 真建控件读 `text()`
- **新增功能** · `tests/test_dockerfile_image_gui_arg.py`（5 用例） — 镜像 GUI 开关的结构锁：`ARG` 声明早于使用（按 Docker 阶段切分，`ARG` 不跨阶段）、过滤表达式确实选中 PySide6 且零误伤、compose 两服务 tag 互异、发布工作流不得传 true，另含判据自检
- **新增功能** · `tests/test_pyright_config_parity.py`（5 用例） — 钉住 `pyrightconfig.json` 与 `[tool.mypy].files`、basedpyright 两份清单的同源性（include 逐项相等、exclude 覆盖两份清单、严格度/版本/venv 同值、三个根入口反向见证），并禁止把 Pylance 当门禁证据
- **修改内容** · `tests/test_ui_fonts.py`（21 → 23 用例） — Windows 专属红项修在测试侧：夹具名含 `:` 会被解析成名为 `font` 的备用数据流（`exists()` 为真、`shutil.copy2` 抛 WinError 3），故把字符清洗下沉为纯函数用例、fs 用例改用两端都能创建但仍需清洗的名字；另补「保留设备名清洗」与「失败必须留一行带异常类型名的 warning」两条
- **说明** · 全量 `pytest` — 4345 passed / 14 skipped / 0 failed / warnings summary 为空。总数比上一轮 +12：+4 是本轮两条新锁的用例，**+8 来自 `tests/test_test_hygiene.py` 的 4 条按 `tests/` 目录参数化的检查**各多访问两个新文件（采集面变化，不是新增断言）

### 11. 文档与知识资产（`AGENTS.md` / `CODE_WIKI*` / `README*` / `docs/agent-reference/`）

- **修改内容** · `AGENTS.md` — 补登记四条：i18n 盲区⑤（raise 位必须在产生点接 `tr()`）、Qt 构造标签与 `T()` 键必须同 msgid（第 ⑦ 条）、自选字体第 ④ 条（失败必留 warning + 保留设备名清洗）、缺键补写必须幂等；另立「引用代码位置优先写锚点而非 `file:line`」新约定
- **修改内容** · `AGENTS.md` — 事实改正 6 处：设计令牌 26 → **25** 键 × 3 主题、`record_danmaku_args` 52 → **60** 处赋值、三处失效 `file:line` 引用改锚点（`main.py:3595`、`Dockerfile:112`、`src/ffmpeg_install.py:583`）、black 与 mypy 的文件计数不再当常量引用（两个口径互不相等）
- **修改内容** · `AGENTS.md`、`docs/agent-reference/measured-evidence.md` — 精简采取外迁 + 合并而非删除：五组一次性实测读数逐字搬入参考文档（19 341 → 24 042 B），根侧留约束与指针；两条挂在同一标题下的条目按内容分标题、DoD 第 5 步改为指针、两处 `[历史注]` 压成一行。根文件体积 157 364 → 158 266 B（净增，因为同轮新增了两条长期约定）
- **修改内容** · `README.md`、`README_EN.md` — 〔配置〕配置块默认值与 `config/config.ini`、代码 fallback 逐项对账同步；版本条目保持中英一一对应
- **修改内容** · `docs/agent-reference/project-structure.md`、`docs/agent-reference/session-learnings.md` — 目录树同步新增模块与测试文件；经验条目追加（ADS 夹具、保留设备名实测、用例数增量归因、offscreen 探针的退出形态、先测后改的冗余度量、锚点优于行号、`strict=True` 下的重复键）
- **新增功能** · `CODE_WIKI.md`、`CODE_WIKI_EN.md` — 本「按模块分类的改动总览」章节（中英同结构、同条目数、逐条对应），以及逐批更新日志条目随改动追加并保持双语一一对应
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

### v4.5.0-dev (2026-10-18) — 四份根文档同步真实状态 + 精简：滚动归档 v4.4.0 及更早条目、v4.5.0 发布说明压缩表述、目录树补 `src/config_read.py`

- **先量化再动手**：四份文档基线 `README.md` 125,120 B / `README_EN.md` 142,725 B / `CODE_WIKI.md` 480,656 B / `CODE_WIKI_EN.md` 542,868 B。冗余形态实测：完全重复长句 3 / 6 / 4 / 6 条、连续空行 0 / 0 / 2 / 2 处、无用格式标记（分隔线 / 空粗体 / `<br>`）0；真正的大头是**更新日志**（分别占 31.8% / 55.6% / 42.2%）。
- **同步真实状态（依据工作区变更）**：四份目录树补 `src/config_read.py`（2026-10-17 新增的容错读取层）；两份 README 的「基础配置」补一句真实行为注记——同节重复键不再让整份配置失效，按最后一次取值并落点名 节 / 键 / 行号 的告警。
- **精简三处**：① 滚动归档——按根文档自述策略把 `CODE_WIKI` 的 v4.4.0 + v4.3.0-dev 共 29 条、两份 `README` 的 v4.2.0 / v4.1.0 共 2 条**逐字**迁入 `docs/changelog/` 对应归档卷（搬移前先落盘并逐行校验，确认归档卷已含全部内容才从根文档删除；`code-wiki-history` 卷条目数 164 → 193，`release-notes-history` 卷 17 → 19，两侧索引计数同步修正）；② 两份 README 的 v4.5.0 条目 37 条压缩表述（中文 18,928 → 12,733 B、英文 22,333 → 15,228 B），判据、读数与真机结论逐条保留，细节仍在本文件对应条目；③ 删掉两份 README 中「配置说明」与「Docker 部署」里重复的环境变量表（后者改为指针）、合并 CODE_WIKI 双语各 2 处连续空行。
- **踩坑（可复用）**：`pathlib.Path.read_text()` 会做**通用换行翻译**（`\r\n` → `\n`），用它读纯 CRLF 文档再写回会把整份行尾静默改成 LF——本轮 README 双语一度因此失去 CRLF（实测 CRLF 仅剩 53 条、裸 LF 1,165 / 1,182 条），已按 `read_bytes()` 取回并整体归一修复。批量改这四份文档一律走字节级 `\r\n`。
- **复核**：四份文档仍纯 CRLF（裸 LF 均为 0）；`README` 双语 14 个二级标题 + 3 个版本条目逐项对应，`CODE_WIKI` 双语 16 个二级标题 + 35 条更新日志一一对应；三份文档锁 `test_run_gates.py` + `test_regression_2026_09_22_gates.py` + `test_check_annotations.py` = 74 passed / 1 skipped；`check_version.py` PASS。


### v4.5.0-dev (2026-10-18) — 版本文档同步：CODE_WIKI 的 4.5.0-dev 更新日志按四类归纳进 README 双语 v4.5.0 条目（`README.md` / `README_EN.md`）

- **归纳口径**：读取 `CODE_WIKI.md` 更新日志里 34 条 `v4.5.0-dev` 条目（2026-10-02 ~ 10-17），按 README 既有版本条目的六小节归位——✨ 新增功能 / 改进 9 条、🐛 修复的问题 9 条、⚠️ 破坏性变更 / 行为变化 5 条、📦 依赖变更 4 条、🛠️ 仓库维护与文档 5 条、🧪 测试与验证 5 条；中英逐节条目数相等、小节标题与顺序沿用 v4.4.0 条目。
- **版本号口径（冲突交回后按确认执行）**：用户原指令写「4.5.0-dev → 4.4.0、写入 README 的 4.5.0 条目」，与「README 已有 v4.4.0 正式发布条目（2026-09-29 ~ 10-01）」冲突；确认后按**新建 `### v4.5.0 (2026-10-02 ~ 2026-10-17)` 条目、插在 v4.4.0 之前**执行，已有 v4.4.0 条目原样不动。
- **只归纳、不增补**：条目正文严格取自 CODE_WIKI 原文，体积（153.21MB / 359 文件）、覆盖率（83.10% / 69 模块）、真机读数（虎牙 660000 / B站 545068 / b23.tv 22747736 等）均为日志内既有数字，未新增日志中不存在的结论。`customtkinter` 摘除与 `PySide6` 加入的净效果按日志两处读数如实表述为「20 → 21 条」（摘除后 20、加 PySide6 后 21），不合并成一句笼统的「21 条」。
- **验证**：两文件行尾仍纯 CRLF（`README.md` 1221 / `README_EN.md` 1238 条 CRLF，裸 LF 均为 0）；`scripts/check_version.py` PASS、`scripts/sync_metadata.py --check` OK 复跑仍绿。

### v4.5.0-dev (2026-10-17) — 元数据同源复扫：以 `pyproject.toml` 为事实源核对 15 份目标文件，三处文档漂移已修（`README.md` / `README_EN.md` / `CODE_WIKI_EN.md`）

- **事实源取值**：`version = 4.5.0` / `requires-python = ">=3.14"` / 运行期依赖 21 条 / extras dev 7·gui 3·build 1 / 三入口 `douyin-recorder{,-gui,-web}` / `packages` 5 项（含 `src.gui_qt`、`src.gui_qt.pages`）。
- **机器门禁先复核为绿**（故本轮只改表述、不改取值）：`scripts/check_version.py` PASS、`scripts/sync_metadata.py --check` OK、`requirements.txt` 21 ↔ pyproject 21 包名集合差集双向为空、`PKG-INFO` 运行期 `Requires-Dist` 21 条逐规格相等、`uv.lock` 本包 4.5.0 与 21 条依赖逐条一致、`.coveragerc-concurrency` 的 omit 24↔24 与 `exclude_also` 4↔4、`egg-info/SOURCES.txt` 已含 `src/gui_qt` 与 `src/gui_qt/pages`。
- **三处修订**：① `README_EN.md` 结构树里 `web_api.py` 的注释仍写「FastAPI app」——`fastapi` 已随 v4.4.0 阶段2 移除，改为 `Starlette app`（中文侧同位置早已是「Starlette 应用」，改后两侧同形）；② `CODE_WIKI_EN.md` 的 `src/ui_fonts.py` 条目标题被渲染两次（其中一条无正文），EN 更新日志 63 条 vs 中文 62 条，删掉空洞那条回到 62↔62；③ 两份 README 结构树补 `src/gui_qt/`（`app.py` / `main_window.py` / `theme.py` / `pages/`）——该包已由 `[tool.setuptools].packages` 声明、`gui.py:main()` 委托到它，树里缺项会让 GUI 入口没有文档落点。
- **顺带修正（非 pyproject 派生，经确认后改）**：两份 README 结构树里 `zh_CN.po` 的键数读数 780/781 已陈旧，按实测改为 1127 键 / 含头部 1128 条（四目录各 1127 键，`.mo` N = 键数 + 1）。
- **无需修改**：`AGENTS.md`、`requirements.txt`、`Dockerfile`、`docker-compose.yaml`、`.gitignore`、`.dockerignore`、`.coveragerc-concurrency`、`config/config.ini`、`DouyinLiveRecorder.egg-info`、`uv.lock`、`build_exe.py` 共 11 份逐项核对无漂移。
- **验证**：改动后四份文档行尾形态复测仍为纯 CRLF（`README.md` 1168 / `README_EN.md` 1185 / `CODE_WIKI.md` 3010 / `CODE_WIKI_EN.md` 3111 条 CRLF，裸 LF 均为 0）；`check_version.py` 与 `sync_metadata.py --check` 复跑仍绿。

### v4.5.0-dev (2026-10-17) — config.ini 重复键不再让整份配置失效：新增 `src/config_read.py` 容错读取层 + Qt 等宽族名工厂（用户日志三条告警的归因与修复）

- **触发（用户粘贴运行时日志）**：`D:\LiveRecorder\config\config.ini` 的 `[录制设置]` 内 `是否启动时清理陈旧字节码缓存(是/否)` 同时出现在第 5 行与第 44 行（两行字节完全相同，逐行 diff 实测）。configparser 默认 `strict=True`，下一次读取即抛 `DuplicateOptionError`，后果是**一个键都读不出来**：① `main.py` 的模块级裸读让录制核心 `import main` 即崩（现场 `logs/` 里只有 `gui.log`、没有 `streamget.log`）；② GUI 状态栏每 10s 打一条「读取 config.ini 失败，使用默认值」。
- **改动**：① 新增 `src/config_read.py`（只依赖 stdlib + i18n + logger，GUI 侧可安全 import，不经 `config_io`→`main` 那条引擎锁链）：`tolerant_config_parser(preserve_case=)`（`strict=False` + `interpolation=None`，可选恒等 `optionxform`，复刻被它替换掉的 GUI 本地闭包）、`find_duplicate_options(text)`（按 configparser 口径复刻注释 / 分节 / `=` 与 `:` 分隔 / 大小写判据）、`warn_duplicate_options(path)`（同一「路径 + mtime」只落一条 warning，点名 节 / 键 / 行号；记忆集封顶 32 项后清空重记）。② 接线读取点 10 处：`main.py` 的模块级 `config` 与 `_hot_reload_config`、`src/gui_qt/main_window.py` 的 `_dynamic_status_info`（连同已被工厂取代的本地闭包与随之无用的 `import configparser`）与 `_read_config_value`、`src/ui_theme.py` / `src/ui_scale.py` / `src/ui_motion.py` 的偏好读取、`src/ui_fonts.py` 两处（连同其函数内 `import configparser`）。③ Qt 等宽字体：新增 `src/gui_qt/widgets.py::fixed_font(point_size=None)`，按 `_FIXED_FONT_CANDIDATES` 取本机第一个命中族名，候选全缺时交回 `QFontDatabase.systemFont(FixedFont)`；替换 4 处 `QFont("Consolas, Menlo, Courier New, monospace")`（`widgets.TerminalText`、`settings_dialog`、`pages/config`、`pages/danmaku`），并删掉 `pages/danmaku.py` 里那份「构造完即被丢弃的 mono」与硬写死的 `setFontFamily("Consolas")`。
- **两条 Qt 告警的归因（实测，非推测）**：`QFont` 的族名位只收**单个** family。装了 Consolas 的机器上侥幸命中（`QFontInfo` 回读 `Consolas`）；没装的那台机器上 Qt 按 `styleHint=Monospace`（枚举值本机实测为 7，与用户日志里的 `styleHint=7` 对上）落进遗留别名表里的 `Terminal`，于是 `CreateFontFaceFromHDC() failed ... Family="Terminal"` 与紧随其后的 `QFont::setPointSize: Point size <= 0 (-1)` 同因一并出现。修复后本机以 windows 平台插件真建 `TerminalText`，捕获到的 Qt 消息为 0 条。
- **端到端真机验证**：本条属配置读取层与 GUI 字体层，未动录制链 / 选源 / ffmpeg 参数 / 平台解析 → 按「完成定义」第 2 步免做。live 侧证据：`D:\LiveRecorder\config\config.ini` 删除第 44 行（改前已备份 `config.ini.bak-dup`，diff 仅一行）后，strict 解析通过、`[录制设置]` 42 键可读、重复键计数归 1。
- **回归锁与变异验证**：新增 `tests/test_config_read.py` 11 条；`tests/test_config_io.py` 新增 `TestMissingKeyWritebackIdempotency` 2 条；`tests/test_gui_qt_units.py` 新增 `fixed_font` 3 条（打桩 `QFontDatabase.families` / `systemFont`，不依赖本机字体表）。变异 5 项实测全部符合预期：M1 `strict=False→True` → 2 failed；M2 摘掉去重守卫 → 1 failed；M3 `main` 退回 `RawConfigParser()` → 1 failed；M4 把补写改成追加式写盘 → 1 failed（**加固前该项漏检**——只数「该键出现几次」挡不住整节被重复追加，故补「写回产物必须仍能被 strict 解析器整份读出」的判据）；M5 `fixed_font` 返回逗号串 → 2 failed。全部按字节还原。
- **i18n**：新增 1 条日志模板 msgid `config.ini 存在重复配置项，已按最后一次取值读取: {detail}`，四目录同批登记并重编 `zh_CN.mo`（1128 条）。
- **未覆盖边界（交回用户）**：① 仓库 `config/config.ini` 的**索引副本**仍存着带重复键的那一版（`git status` = `MM`），照此提交即把自坏模板分发出去，需用户执行 `git restore --staged config/config.ini`；② 其余 strict 解析器未纳入本轮：`src/web_config.py`×3、`src/utils.py`×2、`gui.py`×2、`build_exe.py`×2、`src/web_api.py`、`src/ttwid.py`、`src/logger.py`、`scripts/douyin_live_recorder_standalone.py`（孪生副本）——重复键下它们各自按现有 `except` 静默降级，不构成崩口；③ 用户机器上的 `D:\LiveRecorder` 是独立源码副本，本轮修复需同步过去才对那台机器生效。
- **验证**：`scripts/run_gates.py` **10/10 全绿 rc=0**（black 246 files unchanged；无参 `mypy` 245 source files + `--platform linux` / `--platform win32` 双跑；`check_annotations.py`；`compile_po --check` 1128 条同步；`check_version` / `check_runtime_pins` / `check_skill_agents_consistency` 全 OK；内嵌全量 `pytest` **4365 passed / 14 skipped / 0 failed、warnings summary 空**）；`pytest --cov=src` 总覆盖率 **83.10%**，`scripts/check_coverage.py` **69 个模块全部达标**（`src/config_read.py` 49 语句 / 1 未覆盖 = **98%**）；`basedpyright` **0 errors / 0 warnings / 0 notes**。改动文件行尾形态复测不变（`main.py`、`src/gui_qt/main_window.py`、`src/ui_theme|ui_scale|ui_motion.py`、`tests/test_gui_qt_units.py` 仍纯 CRLF；`src/config_read.py`、`src/gui_qt/widgets.py`、`src/ui_fonts.py`、`src/gui_qt/pages/config.py`、`tests/test_config_read.py`、`tests/test_config_io.py` 仍纯 LF）。五项变异 M1–M5 逐项转红并按字节还原，收尾 `grep -rn MUTATION-` 归零。文档条目落完后再复跑一次 `run_gates.py` 作收尾证据。
- **AGENTS.md**：「缺键补写必须幂等」条补写容错层口径与回归锁用例名。

### v4.5.0-dev (2026-10-17) — `src/ui_fonts.py` 两处缺陷修复：字体复制失败不再零日志 + 落盘名清洗 Windows 保留设备名（新增 1 条日志模板 msgid，四目录 1131 → 1132 键；`tests/test_ui_fonts.py` 21 → 23 用例）

> 交回清单里的两项，均为单文件生产修复，不动录制链。

- **① 异常吞成 `None` 且不留日志**：`install_font_file` 的 `except Exception: return None` 现改为一行 `logger.warning(i18n.tr("复制字体文件失败: {name} -> {target} - {type_name}: {err}", …))` 后再返回 `None`。归因必要性在于调用方拿 `None` 只能弹**分类级**提示（`main_window.py:599/606` 的对话框文案不含 OSError 细节），文件被占用 / 目标目录只读 / 磁盘满 / 源文件在复制瞬间被移走这几种成因在 UI 上完全同形。按「异常日志必须带异常类型与上下文」的既有约定，`{type_name}` 与 `{err}` 并列——Windows 上部分异常的 `str()` 为空串，只打 `{err}` 会打出空白行。模板本身是盲区外的常规形态（字面量首参 + 命名占位符），已登记进四目录并重编 `.mo`。`src/ui_fonts.py` 因此新增 `import i18n` 与 `from src.logger import logger`。
- **② `_safe_filename` 不处理 Windows 保留设备名**：新增 `_WIN_RESERVED_NAMES`（`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`），清洗后按**首个点之前的整段基名**大小写不敏感比对，命中即加 `_` 前缀（幂等：`_CON.ttf` 再过一遍不变）。`COM10`/`LPT10` 刻意不算保留名（MSDN 保留段只到 1..9），`console.ttf`/`NULx.ttf`/`myCON.ttf` 只是形似、不改。该名字会写进 `gui_font_file` 持久化并在下次启动读回，属于跨机器分发的路径。
  **本条的立论按实测改写**：最初把理由写成「copy 到 `CON.ttf` 会抛 OSError / 写出打不开的文件」，本机实测直接证伪——Windows 10.0.26300 上 `CON.ttf`/`AUX.ttf` 经 Python `open()` 与 `cmd` 重定向**都能落成普通文件**（`iterdir()` 可见、`getsize`=8），而 `\\?\` 扩展前缀写 `AUX.ttf` 反而 `OSError [Errno 22] Invalid argument`。即同一名字在不同 API 路径/不同 Windows 构建下语义不一致，保留它才是风险；注释与用例说明一律改成「可移植性防御 + 实测记录」，不得写成「本机写不进去」。
- **真机验证（GUI 面，非录制链）**：导入真实系统字体 `C:\Windows\Fonts\cambria.ttc` → 落 `app\config\fonts\cambria.ttc`、`exists()` 为真、**1 792 664 字节**；失败面把源换成不存在的子路径 → 返回 `None` 且日志恰一行 `复制字体文件失败: nofile.ttf -> …\config\fonts\nofile.ttf - FileNotFoundError: [WinError 2] 系统找不到指定的文件。`（含类型名与目标路径，正是修复前会丢的那条信息）。
- **回归锁与变异**：`tests/test_ui_fonts.py::TestInstallAndRegister::test_install_font_file_logs_copy_failure_with_reason` （`shutil` 按 shim 口径挂到被测模块命名空间 + `logger.add(level="WARNING")` 捕获、`finally` 里 `logger.remove`）与 `…::test_safe_filename_prefixes_windows_reserved_device_names`（6 个保留名 + 幂等 + 5 个边界不改名）。变异 5 项全部符合预期：A1 摘掉 warning → 日志锁红、保留名锁绿；A2 摘掉保留名判定 → 反向（保留名锁红、日志锁绿）；A3 把判定放宽成子串匹配 → 边界用例红（证明 `console.ttf` 那条断言真在咬）。三处变异均按字节还原。
- **AGENTS.md**：「自选字体」条由三条硬约束扩为**四条**，新增 ④（失败必须留 warning + 保留名清洗，并写明「不得写成本机写不进去」的实测边界）。

**验证**：`run_gates.py` **10/10 全绿 rc=0**（black 244 files unchanged、无参 mypy 243 source files + 两平台增跑、`compile_po --check` 1133 条同步）；全量 `pytest --cov` **4345 passed / 14 skipped / 0 failed / 0 警告**，总覆盖 **83.02% → 83.04%**（新增两条用例覆盖到此前未触达的失败分支），`check_coverage.py` 68 模块达标；basedpyright **0/0/0**、裸跑 `pyright` **0/0/0**；四目录键集合逐项相等（各 1132 键），`.mo` 1133 条 / 149 505 字节（N == 键数 + 1）；`src/ui_fonts.py` 与被改用例文件行尾形态复测未变（各自保持纯 CRLF / 纯 LF）。

### v4.5.0-dev (2026-10-17) — i18n 孤儿裸文本键收回 6 条（四目录 1132 → 1126 键）+ CODE_WIKI 新增「按模块分类的改动总览」章节（`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml` / `AGENTS.md` / `CODE_WIKI*.md`）

- **收回前逐个证伪消费者**（不是按「生产侧无调用点」一刀切）：用 AST 枚举 `main.py`/`gui.py`/`web.py`/`i18n.py`/`msg_push.py`/`src/`/`scripts/`/`tests/`/`web/` 里**所有字符串常量**（不限 `T()`/`tr()` 首参），结果 5 条零消费者、`停止录制` 只作为**值**出现在 `web/app.js` 内嵌目录（与后端键无关），而 `开始录制` 有 12 处消费者且全在 `tests/test_i18n.py`——它被 `test_load_translations_priority` 与 `test_set_language_hot_swaps_translator` 当样本 msgid 用来验证「`.mo` 优先于 JSON/YAML」的三档加载与热切换。**因此收回 6 条、保留 1 条**：删 `停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志`，留 `开始录制`。该耦合已写进 AGENTS.md 盲区清单，防止下一次把它当孤儿删掉。
- **四目录的删条目形态各异，逐个处理并先验证语法再落盘**：`.po` 删 `msgid`+`msgstr` 块（含其后空行）；两份 JSON 按键前缀删行后，还得**在条目区内**做逗号归一（末条目不带逗号、其余都带——删掉的若是末条目，前一行的逗号必须补回，否则 JSON 非法），`json.loads` 通过才写盘，并断言「键集合 == 原集合 − 6」且保留条目 `开始录制` 的值未被动过；`zh_TW.yaml` 的键**混用单双引号**（正文多为 `'键': '值'`、文件尾部为 `"键": "值"`），只按双引号匹配会只删掉 2 条（实测断言当场抓到 2≠6）。收回动作的即时读数：四目录各 1126 键、键集合逐项相等，`.mo` 1127 条 / 149 231 字节（N == 键数 + 1），`extract_i18n_strings.py` 的「疑似冗余」由 247 降到 241 条；随后并发包登记其模板，当前为四目录各 1127 键、`.mo` N=1128 / 149 399 字节。
- **CODE_WIKI 新增「按模块分类的改动总览」章节**（中英各一节，置于「更新日志」之前，目录同步补锚点）：11 个模块小节、每节逐条记类型/路径/说明，并标〔破坏性〕〔配置〕〔依赖〕〔字符串契约〕。范围口径写明基线 `72d1664`（本会话开始时的 HEAD）→ 当前工作区，覆盖已提交（`553b036`，会话中途由他人提交）、未提交与仅存在于暂存区三类；本轮无删除文件，被移除的只有上述 6 条目录条目。**中英由同一张数据表渲染**，并内建自查：小节数、逐节条目数、编号顺序逐项相等，EN 去掉代码段后不得残留 CJK，且不得含 `TODO`/`待补`/`…` 之类占位或省略——自查实测抓到两处自己的问题（EN 曾把标签渲染成中文 `[依赖]`、代码示例里留了 `…`），已修。
- **并发工作包不属于本代理，已如实排除**：`src/config_read.py` 与 `tests/test_config_read.py`（均未跟踪）以及 `main.py`、`src/gui_qt/{settings_dialog,widgets,danmaku}.py`、`src/ui_{motion,scale,theme}.py`、`tests/test_config_io.py` 的改动在进行中落地。它新增的模板 `config.ini 存在重复配置项，已按最后一次取值读取: {detail}` 一度未登记，使 `tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 短暂为红（提取器当时报的唯一缺失项即此条）；本代理不代其登记（消息仍可能改名，代填只会造出新的孤儿条目），该包随后自行补齐，复测缺失 0 条、相关 8 用例全过。

**验证**：收回后 `scripts/compile_po.py --check` 报 `.mo` 与 `.po` 同步（1127 条）；本代理相关的锁 `tests/test_i18n.py`、`test_i18n_catalog_coverage.py`、`test_ui_fonts.py`、`test_gui_qt_label_parity.py` **67 passed**；四目录行尾与 BOM 复测保持原样（四份均纯 CRLF、无 BOM）。那一度唯一的红点属上述并发包的新模板（其未登记状态），与本代理的收回无关，现已由该包补齐。

### v4.5.0-dev (2026-10-17) — AGENTS.md 事实复核与精简：6 处断言按实测改正、3 处 `file:line` 引用改锚点、一次实测读数外迁（`AGENTS.md` / `docs/agent-reference/measured-evidence.md`）

> 本轮起因是「扫描工作区 → 按变更同步 AGENTS.md → 再精简」。先记录一个改变判定的事实：**会话中途有人提交了 `553b036`（22:13:55，非本代理所为）**，本会话此前的全部改动（含 22:13 之前的 `AGENTS.md`、i18n、Docker、Qt、测试）都已进入该提交，因此「自上次提交以来的变更」实测只剩一个文件——`config/config.ini` 的 +1 行，而那一行是**损坏**的。

- **`config/config.ini` 的同节重复键（实测并还原）**：`是否启动时清理陈旧字节码缓存(是/否)` 同时出现在第 5 行与第 44 行，两处都在 `[录制设置]` 内。后果不是「多一行注释」而是**基线不可读**：本仓解析器是 `configparser.RawConfigParser()`（`strict` 默认 True），实测 `read()` 直接抛 `DuplicateOptionError: ... option '是否启动时清理陈旧字节码缓存(是/否)' in section '录制设置' already exists`。已删除重复行并复验工作区 == HEAD；**写入侧根因未定位**，不得据此声称已修——单跑一次 `read_config_bool`（键已存在）不改写文件、`config_parser.write()` 的序列化产物该键恰 1 次，所以缺陷形态是「两个持有不同快照的写者并发」而非「补写逻辑必然写重」。收尾复跑整条 `run_gates.py` 也**未复现**（键数仍为 1），说明它是竞态、不是确定性路径。索引里那份带重复键的暂存内容**未动**（是否 `git restore --staged config/config.ini` 由用户定）。该危害已写进 AGENTS.md 的「配置键名、布尔口径与 SSL 验证」。
- **断言复核：69 项机检、6 处改正**（脚本逐条比对 pyproject/requirements/符号存在性/用例收集数/路径与指针存在性，读数见下）。改正清单：① 设计令牌 **26 键 → 25 键 × 3 主题**（AST 数 `_LIGHT`/`_DARK`/`_HIGH_CONTRAST` 键数，三主题键集合相同）；② `ctx.record_danmaku_args` 赋值 **52 处 → 60 处**（口径 `grep -c 'record_danmaku_args = ' main.py`）；③④⑤ 三处 `file:line` 引用实测已失效，改为锚点形态——弹幕链路唯一调用点 `main.py:3595` → `comment_end = check_subprocess(...)`（真身 3952 行）、`Dockerfile:112` 的 `COPY . ./` → `COPY --chown=recorder:recorder . ./`（真身 149 行，连字面量都变了）、`src/ffmpeg_install.py:583` → 直下入口调用那一处（真身 594 行）；⑥ 「抬 `black_version` 不改判定」条目里的 `239/242 files` 与 mypy `241 source files` 一类**随文件数变动的计数**不再当常量引用（black 计被扫文件、mypy 计 Python 模块，两个口径互不相等）。另有两处「看似漂移实为脚本判据太粗」已当场排除：`MAX_FRAMES=12`/`MONO_SCALE_FACTOR=0.9` 是 `Final[...]` 注解写法（正则没认），`tests/test_ci_retry_action.py` 的「8 格」指 `_BEHAVIOUR_CASES` 的 8 个行为用例、收集数 12 = 8 + 4 条结构锁。
- **新增两条长期约定**（不是精简，是补登记）：① 「引用代码位置优先写锚点而非 `file:line`」——一轮复核就实测到三处失效，坐标是会过期的；② 「缺键补写必须幂等，同一节内不得出现重复键」，含复现判据（同一份文件连跑两轮读取+补写，断言该键出现次数仍为 1）。
- **精简采取的是「外迁 + 合并」而非删除**（与 `docs/agent-reference/measured-evidence.md` 开头「与根文件的分工」一致）：五组一次性读数逐字外迁到该文档（19 341 → 24 042 B），根文件侧改为约束 + 指针——GUI 右边框裁切的 px 读数、`sync_http` 复用收益、PySide6/`Qt6WebEngineCore`/`QT_BLOAT_FILES` 体积、门禁被扫文件计数、历次版本对齐读数与 exclude 锚定修复前后读数。合并与压缩四处：把两条挂在同一个标题下的条目按各自内容分标题（`Tkinter after 自续期链` 与「停止/退出单飞闸门」原本共用一句标题，属迁移期复制粘贴痕迹，非内容重复）、DoD 第 5 步改为指向「测试收尾清理临时脚本」，两处 `[历史注]` 压成一行、collector 单行式守卫的证伪段去掉重复代码。**体积如实报告**：根文件 157 364 → 158 266 B（+902），因为本轮新增了两条约束而外迁只把读数搬走；剩下的可压缩段（MID-63 事故链、Starlette 迁移 ⑥⑦ 的验证方式说明、`.superpowers` 漏登记史）都是「为什么」类承重内容，再压就得删判据——按项目约定不做，已列为剩余杠杆交回。
- **精简前的冗余度量（先量后改）**：全文 547 行 / 93 696 字符，尾部空白行 0、连续空行段 0、完全重复行仅 6 组且全是结构符（``` / ```bash / >），>120 字符条目两两相似度 >0.45 的只有 3 对——其中 1 对是同节 Black/isort 的「取值」小标题（假阳性），1 对是 DoD 第 5 步与清理节（已改为指针），1 对是 3.14 破坏面与并章节的 `get_event_loop()`（已把细节收敛到并发节、破坏面只留登记）。精简后复查：同名加粗标题归零（除结构性「取值」），高相似对剩 2（均为上表的假阳性与已认可的双写）。

**验证**：`run_gates.py` **10/10 全绿 rc=0**（black 244 files unchanged、无参 mypy 243 source files + 两平台增跑、`compile_po --check` 1133 条同步、内嵌 pytest **4345 passed** 且 warnings summary 为空）；AGENTS.md 的三个真实读者各自复验——`scripts/run_gates.py` 解析的门禁 bash 块未动、`scripts/check_skill_agents_consistency.py` rc=0、`tests/test_agent_hook_guard.py + test_run_gates.py + test_regression_2026_09_22_gates.py + test_ci_frontend_registration.py` **118 passed / 1 skipped**；`AGENTS.md` 与 `measured-evidence.md` 行尾形态复测仍为纯 CRLF（bareLF 0）；本轮属纯文档改动，按 DoD 豁免只做「门禁 + 文档同源 + 日志 + 清理一次性脚本」，端到端真机项不适用。

### v4.5.0-dev (2026-10-17) — i18n 批准项 B+C 落地：9 处 Qt 按钮图标恢复（复用既有键，零新条目）+ 21 处中文 raise 文案在产生点接 `tr()`（新增 16 条 msgid，四目录 1115 → 1131 键）（`src/gui_qt/main_window.py` / `src/gui_qt/pages/{dashboard,config,runlog}.py` / `main.py` / `src/spider.py` / `src/web_models.py` / 四份目录 + `zh_CN.mo` / 新增 `tests/test_i18n_raise_site_tr.py`、`tests/test_gui_qt_label_parity.py`）

> 本批只落地用户批准的 B、C 两项（A 项目录覆盖锁已于同日第三批完成）。

- **B｜9 处按钮图标的根因**：`action_button("📥  最小化到托盘")` 之后紧跟 `set_text(btn, T("最小化到托盘"))`——`set_text` 建时即回填并登记重译，构造期带 emoji 的标签在启动回填与每次 `retranslate_all()` 都被打回裸文本，图标永久消失；单看任一行都「像是对的」。修法是把两处写成**同一个 msgid**，并取目录里**已存在的 Tk 三空格键**（`▶   开始录制` / `⏹   停止录制` / `⚙   高级设置` / `📂   打开下载目录` / `💾   保存 URL 配置` / `🔄   重新读取` / `🗑   清空日志` / `📥   最小化到托盘` / `❌   彻底退出`），**四目录零新增**。站点分布：侧栏 2（`main_window.py:256-259`）、dashboard 4（`:76-79`、`:104-107`）、config 2（`:55-58`）、runlog 1（`:50-51`）。行为证据走 offscreen 真建控件读 `text()`：三个页面（dashboard/config/logs）7 枚按钮 + `MainWindow` 侧栏 2 枚，在 `zh_CN`/`en_US`/`zh_TW` 下均在 `retranslate_all()` 之后仍带图标（如 `▶   Start Recording`、`🗑   清空日誌`）。顺带实测：`MainWindow` 自带语言探测，探针里 `set_language` 之后仍可能被它按持久化配置改判，读标签前必须钉语言（AGENTS.md 已知坑⑤同源）。
- **C｜判据不是「有没有中文」而是「消息会不会被显示」**：21 个站点（`main.py` 12 / `src/spider.py` 3 / `src/web_models.py` 6，去重 16 条 msgid）在产生点包 `i18n.tr()`。原因是一条已经 `tr()` 过的日志模板会把异常消息当 `{reason}` 实参插值——**模板查表、消息从不查表**，只登记原文等于造死条目。三条 f-string 站点按不变量① 改写成常量模板 + 命名实参（`无法从链接中解析 TwitCasting 主播 ID: {masked_url}`、`...微博用户 ID: {masked_url}`、`字段 {field} 必须是…` 五条）；`src/web_models.py` 因此新增 `import i18n`（i18n 只依赖 stdlib + loguru，不回指 `web_*`，无环）。`extract_i18n_strings.py` 报**缺失 0 条**，四目录键集合逐项相等（各 1131 键），`.mo` 重编为 1132 条 / 149 357 字节（含头部空 msgid，N == 键数 + 1）。
  运行时按语言实测（真函数、非桩）：`main._hy_fan_path_segment` 与 `web_models._as_bool/_as_str_list` 在四语下分别给出 `Path is empty, room ID missing` / `欄位 web_auth_enable 必須是布林值` / `房間號含非法字元` 等译文，占位符 `{field}` 由调用方实参填充。
- **刻意不登记的 10 条（白名单集合相等钉住）**：`XhsUrlError` 九条消息——`src/spider.py` 两处 `except XhsUrlError` 与 `main._resolve_xhslink_com` 一律只读 `e.code`，message 从不显示；以及一条整句英文、只有括号里「原」字是汉字的站点（`TTingLive(原Flextv) login failed`），译它等于把英文再写成英文。`src/spider.py` 的斗鱼三条早已是 `i18n.tr()` 形态，本批未动。
- **两条新锁 + 13 次变异**：`tests/test_i18n_raise_site_tr.py`（未接 `tr()` 站点走白名单集合相等、已接的 msgid 断言四目录齐全、锚点防空转）与 `tests/test_gui_qt_label_parity.py`（AST 判「构造标签 == 登记键」+ 带 emoji 配对下限 + 键必须四目录齐全）。变异 13 项里 12 项与预期一致；**第 13 项是我的预期写错而不是锁写错**——E2b（同源但整体去图标）我标了「绿」，实得红在 `assert 8 >= 9` 的 emoji 下限分支，正是它该咬的位置；全部变异按字节还原（`read_bytes()` 逐文件比对）。用例数增量口径：全量 `pytest` 4331 → **4343**，其中 +4 是两条新锁的用例，**+8 来自 `tests/test_test_hygiene.py` 的 4 条按 `tests/` 目录参数化的检查各命中两个新文件**（不是新增断言，属采集面变化）。
- **真机端到端（DoD 第 2 步，受影响平台各跑一条真实房间）**：`python tests/test_huya_live_collector.py https://www.huya.com/660000 20` → **PASS，2 条弹幕 / SRT 206 字节**；`python tests/test_bili_live_collector.py https://live.bilibili.com/545068 20` → **PASS，33 条弹幕 / SRT 2 642 字节**（两份 `.srt` 为本次验证产物，已按收尾口径删除）。本轮改动的 `main.py` 站点在 hy.fan/b23.tv 短链解析的错误分支、`src/spider.py` 站点在 TwitCasting/微博/TTingLive 的畸形链接分支，真实房间走的是成功路径，与错误分支互不重叠——增量跑的意义在于证明导入链与解析链未被改动带偏。
- **AGENTS.md 两处写回**：关键约定 #14 增「盲区⑤（raise 位文案）」及其准入条件；已知坑「GUI 静态标签走 `T()` 登记表」增第 ⑦ 条（Qt 构造标签与 `T()` 键必须同一 msgid）。**遗留交回**：B 之后 7 条裸文本键（`开始录制`/`停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志`）已无调用点（AST 枚举确认，`最小化到托盘`/`彻底退出` 仍被 `gui.py:782`、`src/gui_qt/tray.py` 用着），孤儿条目无门禁判红、也不在本批范围内，是否从四目录收回由维护者定。

**验证**：`run_gates.py` **10/10 全绿**（无参 mypy 241 source files、black 242 files unchanged、两平台增跑、`compile_po --check` 1132 条同步）；全量 `pytest --cov` **4343 passed / 14 skipped / 0 failed / 0 警告**，总覆盖 **83.02%（与上一轮同值）**、`check_coverage.py` 68 模块达标；basedpyright **0 errors / 0 warnings / 0 notes**、裸跑 `pyright` **0 errors / 0 warnings / 0 informations**；`extract_i18n_strings.py` 缺失 0 条；四目录行尾形态逐文件复测保持原样（`.po`/两份 `.json`/`.yaml` 均纯 CRLF、无 BOM，追加后 bareLF 仍为 0）；`git status` 无杂散临时文件、`MUTATION-` 标记残留 0。未验证边界：`en_GB` 与 `en_US` 这 16 条同值——措辞里不含 `-ise/-ize`、`canceled/cancelled`、`catalog/catalogue` 一类英美分歧词，硬造差异反而破坏目录既有的「仅在真正分歧处分侧」惯例（全仓现有 22 条分歧条目）。

### v4.5.0-dev (2026-10-17) — 测试侧修 Windows 专属红项 + 工具版本三面收敛 + `pyrightconfig.json` 让 IDE 结论可复核 + 覆盖率复跑（`tests/test_ui_fonts.py` / `.github/workflows/ci.yml` / `.pre-commit-config.yaml` / `pyrightconfig.json` / `tests/test_pyright_config_parity.py`）

> 本批是用户对上一轮报告里四项「需人工处理」的批准落地：① 只改测试侧修掉唯一红项；② 解决 black/isort 的三面版本漂移；③ 跑覆盖率；④ 解决「Pylance 无法作为证据」。业务逻辑零改动。

- **① `test_filename_is_sanitized` 的根因与修法（只动 `tests/`）**：夹具名 `font:with|weird*chars?.ttf` 里的 `:` 让 Windows 把它解析成名为 `font` 的**备用数据流（ADS）**——实测 `iterdir()` 只列出 `font`、`exists()/is_file()` 因流可 stat 而为真，但 `shutil.copy2` 抛 `FileNotFoundError [WinError 3]`，被 `src/ui_fonts.py` 的 `except Exception → return None` 收敛，于是「本机红、Linux CI 绿」。修法是把两件事拆开：**非法字符那半边下沉为纯函数用例**（直接断 `_safe_filename(...)`，不碰文件系统，两端语义一致），**fs 那半边换成两端都能创建、但仍需清洗的名字**（`"  my font  (v2) ..ttf"`），并补一条空名/纯点名必须回落 `custom_font.ttf` 的用例。`src/ui_fonts.py` 一行未动。变异验证：把 `_safe_filename` 改成恒等 → 三条用例同时转红（3 failed），按字节还原。
- **② 三面收敛**：本机实装 black 26.10.1 / isort 9.0.2，CI 钉定 `black_version` 原为 26.5.1，而 `.pre-commit-config.yaml` 的两个 mirror rev 是第三套（black 25.9.0 / isort 6.1.0）。抬 CI `black_version` → 26.10.1、两个 mirror rev → 26.10.1 / 9.0.2，使「本地 venv / CI 钉定 / 提交钩子」只剩一个值。**抬之前先用 26.5.1 与 26.10.1 各跑一次全量 `black --check`**，两者都是 `242 files would be left unchanged`（解包 wheel 到临时目录跑，不动 venv；计数在清掉误建于仓库内的一次性目录之后取得），故这次抬值只消除版本差、不改变判定。两个新 rev 的存在性经 GitHub API 逐个核实（`refs/tags/26.10.1`、`refs/tags/9.0.2` 均 HTTP 200）；`pre-commit validate-config` OK。本机 clone 被代理拦住，所以「钩子真的装起来跑一遍」未经验证。
- **③ 覆盖率复跑**：`pytest -q --cov=src --cov-report=json` → **4331 passed / 14 skipped / 0 failed**，总覆盖 **82.68% → 83.02%**；`scripts/check_coverage.py` → **68 模块全部达标**（`src/proto/douyin_pb2.py` 为显式豁免的 protoc 生成物）。模块级变化 6 处：`gui_qt/pages/quality.py` 61.62→84.00、`gui_qt/pages/danmaku.py` 55.11→71.75、`gui_qt/widgets.py` 80.81→87.38、`gui_qt/main_window.py` 64.34→65.07 上升，`src/proxy.py` 92.02→84.66、`src/web_api.py` 84.32→83.90 下降——本轮新增的用例把导入闭包拉宽后，先前靠别的用例顺带命中的行不再被覆盖，属**测量面变化而非回归**（两者仍远高于各自阈值）。
- **④ Pylance 的可复核化**：先证伪一条捷径——本机确实装着 Pylance（`.vscode/extensions/ms-python.vscode-pylance-2026.4.101`，其 `dist/server.bundle.js` 能被 node 拉起来），但它的 LICENSE 明文只授权「在 Visual Studio 系产品内使用」，所以**不写**去 shell 驱动该 bundle 的工具，AGENTS.md 里把这条禁令钉死。改为治根因：IDE 与 CLI 之前没有共用配置（本仓既无 `[tool.pyright]` 也无 `pyrightconfig.json`，裸跑 pyright 走自带默认范围），于是 IDE 的红线本来就无法复现。现新增 `pyrightconfig.json`：include 逐项目等于 `[tool.mypy].files`、exclude 覆盖 mypy 与 basedpyright 两份清单、typeCheckingMode/pythonVersion/venv 同 `[tool.basedpyright]` → **不带路径跑 `pyright` 就是在复现 IDE 的扫描面**，本轮读数 0 errors / 0 warnings。同源关系由 `tests/test_pyright_config_parity.py`（5 用例）机检，五处变异各自转红（include 删一个根入口、typeCheckingMode 改 off、exclude 删项、venv 指错），配置按字节还原。
  两处实测细节写进了配置注释：① pyright 只接受**已知顶层键**，把说明写成 `"//"` 键会报 `Config contains unrecognized setting`，故说明一律用 JSONC 行注释；② `$schema` 同样不被识别（每次跑都吐一行噪声），已挪进注释。
- **AGENTS.md 两处随之更新**：「本地门禁可外推的前提」追加三面收敛读数（并保留抬常量 ≠ CI 实跑已验证的原口径）；「`pyright` 与 Pylance 的定位」按新事实改写（原先写「本仓没有 pyright 配置段、要复现就得显式传路径」，现已被这份配置取代），并按 AGENTS.md 自身规则直接改正文而非叠层。

**验证**：`run_gates.py` **10/10 全绿**（无参 mypy 241 source files，black 侧 242 files unchanged + 两平台增跑、`compile_po --check` 1116 条同步）；全量 `pytest --cov` **4331 passed / 14 skipped / 0 failed / 0 警告**；basedpyright **0 errors / 0 warnings / 0 notes**；裸跑 `pyright`（走新配置）**0 errors / 0 warnings / 0 informations**；`check_coverage.py` 68 模块达标；`test_ui_fonts.py` 21 passed（本轮从 20 passed + 1 failed 变全绿）、`test_pyright_config_parity.py` 5 passed、`test_pre_commit_config.py + test_run_gates.py` 合计通过；`MUTATION-` 标记残留双查为 0，`src/ui_fonts.py` 与 `pyrightconfig.json` 改前后按字节断言一致。未容器实测的边界照旧：无 Docker 守护进程、pre-commit 的 clone 被本机代理拦住。

### v4.5.0-dev (2026-10-17) — 元数据同源同步（A1-A8 + B1）+ 镜像默认不装 GUI 依赖（`INSTALL_GUI` 单开关）（`AGENTS.md` / `CODE_WIKI*` / `README*` / `Dockerfile` / `docker-compose.yaml` / `config/config.ini` / `docs/agent-reference/project-structure.md` / 新增 `tests/test_dockerfile_image_gui_arg.py`）

> 基线：HEAD `72d1664` 起的全部工作区改动（含 Qt 会话遗留的 `pyproject.toml` packages 与 `egg-info/SOURCES.txt`）；事实源 `pyproject.toml`：version 4.5.0 / requires-python >=3.14 / 运行期依赖 21 条（含 `PySide6>=6.12.0`）/ extras dev 7·gui 3·build 1 / 三入口 scripts / packages 5 项。

- **机器门禁先复核为绿**（因此本批只改表述，不改取值）：`check_version.py` PASS、`sync_metadata.py --check` OK、`requirements.txt` 21 ↔ pyproject 21 集合相等、`uv.lock` 本包 4.5.0 且锁内 21 条与 pyproject 逐条一致、`PKG-INFO` 运行期 `Requires-Dist` 21 条逐规格相等（protobuf 的 `<8,>=6.33.5` 是 setuptools 规范化形态）、`.coveragerc-concurrency` 的 omit 24↔24 与 exclude_also 4↔4、`.gitignore`/`.dockerignore` 的 19 个同源目录名齐全、compose 三服务 ↔ 三入口、`python_build=3.14`/`node_version=24` 两 workflow 同值。
- **A1-A3（AGENTS.md 依赖管理段三处漂移）**：运行时依赖条数 20 → **21**（复核日期同步到 2026-10-17，并注明 `PySide6` 随窗口层迁移加入）、`.[gui]` 由「pystray/Pillow」改为「PySide6/pystray/Pillow 三条」、「GUI 两包版本下限」改为**三包**并补 `PySide6>=6.12.0`（历史注按「只增不改」追加，不删原句）。
- **A4-A8（CODE_WIKI 双语）**：技术栈表 `tkinter.ttk + pystray + Pillow` → `PySide6 (Qt6) + pystray + Pillow`（注明 tkinter 实现为迁移期保留）；Python 依赖表补 `PySide6 >=6.12.0` 行——CN 侧顺带修掉一个**表格断行缺陷**（PyExecJS 与 pystray 两行被挤在同一物理行，markdown 渲染成坏行、且让 CN 比 EN 少一行），两文件现各 21 行且`|` 计数逐行相等；目录树 `gui.py` 入口注改指 `src/gui_qt/`；src 子树补 `gui_qt/` 子包与 `ui_i18n.py`/`ui_fonts.py`/`ffmpeg_linux_download.py`/`startup_cleanup.py` 四条（双语同文本，与本段既有写法一致）。
- **B1（config.ini 模板补两键）**：README 双语 L481-483/L495-497 已记录、`src/ui_fonts.py` 在读，而基线模板缺 `gui_font` / `gui_font_file` → 按 AGENTS.md「模板默认值须与代码 fallback、README 配置块逐项对账」补入；该文件是 **BOM + 纯 LF**（不是 CRLF），按自身形态写入并复测。对账判据：三处 `[GUI]` 键集合现在两两相等。
- **C1（外迁目录树明细）**：`docs/agent-reference/project-structure.md` 补 GUI 层 5 模块 + `gui_qt/` + `startup_cleanup.py` + 两个 ffmpeg 下载模块，并删掉 2026-09-23 已整体删除的 `weverse_auth.py` 残留条目；该文件行尾**混存**（CRLF 为主 + 17 处裸 LF），故不走整文件 split/join（那会把 17 行静默转成 CRLF），改用「锚点行 + 其自身行尾」的定点插入。复核：src 实际模块在两份树里已无缺项、无幽灵。
- **镜像 slim（本轮唯一的行为变更）**：新增 `ARG INSTALL_GUI=false`——阶段1 在 false 时按行首包名剔除 `pyside6` 后再 `pip install`，阶段2 仅在 true 时补装 Qt 运行库（libegl1/libgl1/libglib2.0-0/libfontconfig1/libxkbcommon*/libdbus-1-3/libxcb-*）。依据是实测而非推断：本机 venv 里 PySide6 解压 **647.56MB**；用元路径拦截器屏蔽 PySide6 后 `import main` / `import web` 均成功（`gui.py` 也把窗口层延迟到 `main()` 内，import 期不碰它）。**清单不动**：过滤只发生在镜像侧，`requirements.txt` 与 pyproject 的集合相等锁不受影响（实测 grep 后 21 → 20 条、仅剔 pyside6、零误伤，残留的两行是纯注释、pip 视为注释）。compose 的 `gui` 服务显式传 `INSTALL_GUI: "true"` 并**另用 tag** `:latest-gui`（build 配置不同的服务共用同一 image 名会互相覆盖正在用的 tag）；`docker-publish.yml` 不传该参数，对外镜像保持 slim。
- **新增回归锁 `tests/test_dockerfile_image_gui_arg.py`（5 用例）**：① 每个引用 `$INSTALL_GUI` 的阶段先声明后使用（ARG 不跨阶段，与 MIN-14 同族；`_stages` 丢弃纯注释的头部桶，否则诊断里的阶段号错一位）＋ 判据自检用例（合成源码喂进同一条判据，证明「使用先于声明」「整段没声明」两种破坏都能被抓到）；② 默认值必须 false + 过滤形态必须是「grep 剔除 + 临时清单」+ 清单里 PySide6 仍在（requirements 与 pyproject 两侧都断言）；③ compose gui 开开关且 tag 与 recorder 不同；④ 发布工作流不得出现 `INSTALL_GUI=true`。
- **未做与边界（不得当作已验证）**：本机 **没有 Docker 守护进程**，因此「瘦身后的镜像确实能跑」与「GUI=true 分支真能起窗」都**未经容器实测**。已做的替代验证：6 条 RUN 载荷 `sh -n`/`bash -n` 全通过；把 pip 换成 echo 替身跑四条分支轨迹（`true`→整份清单，`false`/`TRUE`/空→临时清单，即大小写敏感、只认精确 `true`）；compose `yaml.safe_load` OK。容器内真窗验证交回有 Docker 的环境。

**验证**：`run_gates.py` 10/10 全绿（无参 mypy 240 文件 + 两平台增跑、`compile_po --check`、`check_skill_agents_consistency`）；新增锁 5 用例 + `test_docker_publish_workflow` + `test_config_io_backup` + `test_web_config` + `test_i18n_catalog_coverage` + `test_regression_2026_09_22_gates` 合计 177/186 passed 无告警；全量 `pytest -q` 见本轮收尾读数；变异验证六项全部按预期转红（阶段2 声明挪后 / 阶段1 默认值改 true / 过滤动作摘成 cat / gui 删开关 / gui 改回同 tag / 发布链塞 true），四文件改前后备份-还原按字节断言一致，`MUTATION-` 残留双查为 0。

### v4.5.0-dev (2026-10-17) — i18n 盲区④由「人工登记」升级为可机检：新增 `tests/test_i18n_catalog_coverage.py`（三条锁 + 变异验证）

- **动因**：同一天的四语目录同步暴露出盲区④完全没有防线——`scripts/extract_i18n_strings.py` 与不变量③只看 `tr()`/`T()` 的**字面量首参**，对 `i18n.tr(msgid)`（msgid 来自元组表）、`tr(THEME_LABELS[k])`、`T(title)`（循环变量）一概看不见；Qt 侧栏正是这种形态，于是「目录缺词条」与「一切正常」在门禁上不可区分（提取器恒报 0 缺失的假绿）。
- **三条锁**：⑤-A 按名调用点解析出的 msgid 候选必须**四份目录齐全**；⑤-B 解析不出的调用点用**白名单集合相等**判定（比计数上限强：新增即红、已知点被消解后不收回白名单也红），当前白名单只含 `src/ui_i18n.py:34`；⑤-C 四份目录键集合逐项相等（含 `.po` 剔除头部空 msgid 的既有口径）。⑤-A 自带两处锚点断言（`found` 非空、必须解析出含「控制台」的导航 msgid），使「解析器什么都没抓到」不能冒充全绿。
- **解析器口径**：扫描面直接取提取器的 `SCAN_FILES`（不另建第二份清单，本仓「清单复制即漂移」先例已成把尺子）；名字→候选集合的解析收四类绑定（模块级 UPPER_CASE 常量跨文件合并，用于 `THEME_LABELS` 这类导入表；本文件局部赋值；`for page_id, msgid in ((...))` **按位置**对齐取元素，取错位会把 `dashboard` 这类 id 当文案造成假红；形参位实参），并按 `_INDEX_PASSES=3` 轮迭代收敛两层链（`_pattern_from_template → _sentinel_text`）。小写名**不跨文件**合并，避免同名变量互灌。
- **性能**：首版在 `_binding_index` 里对每个函数再走一遍 `ast.walk(tree)`，实测单次 35s；把调用点收一次后降到 ~6s，三条用例共用 `functools.lru_cache` 的同一份解析（本文件总耗时 6.5s）。
- **变异验证**（四条各钉一个咬合点，全部按预期转红/转绿，改前后按字节还原并断言一致）：M1 en_US 用等长标记键替换一条导航键 → ⑤-A 与 ⑤-C 同时红；M2 zh_TW 删一条按名 msgid → 两者红；**M3 源码侧把 `📊  控制台` 改成目录里没有的形态 → 只有 ⑤-A 红、⑤-C 绿**（四侧一致缺失时键集合仍相等，这正是 ⑤-A 独立存在的理由）；M4 把 `tr(self.msgid)` 换成字面量 → ⑤-B 因白名单陈旧而红。
- **未做**：不改任何生产代码；`main.py`/`src/spider.py`/`src/web_models.py` 里 15 条含中文、去重约 9 条的 raise 位文案仍未接 `tr()`（接了才有目录意义），属下一轮独立改动。

**验证**：`pytest tests/test_i18n_catalog_coverage.py -q` 3 passed；`tests/test_test_hygiene.py + test_i18n_migration.py + 本文件` 合计 604 passed；`run_gates.py` 10/10 全绿（无参 mypy 239 文件、`compile_po --check` 1116 条同步）；全量 `pytest -q` 4303 passed / 14 skipped / 1 failed，唯一红项仍是 `tests/test_ui_fonts.py::TestInstallAndRegister::test_filename_is_sanitized`（本机文件名含 `:` → ADS 解析，与 i18n 无关）。

### v4.5.0-dev (2026-10-17) — i18n 四语目录同步：补 Qt 侧栏导航 5 条「按名 tr()」msgid，四目录键数 1110 → 1115（`i18n/zh_CN/LC_MESSAGES/zh_CN.po|.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`）

- **扫描面**：以 `scripts/extract_i18n_strings.py` 为基线（其 SCAN_FILES 报 0 缺失），另做独立 AST 全量扫描——74 个运行期 `.py`（根 5 入口 + `src/**`，排除 `.venv`/`node`/`ffmpeg`/`__pycache__`/`tests`/`scripts`/`build_exe.py`），逐条过第 14 条四个盲区：① `color_obj.print_colored` 字面量全部已登记；② `messagebox.show*` 与 Qt 文本位（`setText`/`setWindowTitle`/`setToolTip`/`addButton`/`addItem`/`setHorizontalHeaderLabels`）无未登记字面量，残留命中只有品牌名 `DouyinLiveRecorder`、装饰符 `☰`/`🌓` 与 `'-'`；③ `msg_push.py` 未登记的仅 `__main__` 自测样例两处；④ 按名传入 `tr()`/`T()` 的 15 处调用点逐一解引用（`_THEME_LABELS`/`_MOTION_LABELS`/`STATUS_TPL_*`/`_INSECURE_BIND_ENV_TAIL`/dashboard 网格标题）全部命中目录。
- **唯一真缺口是盲区④的形态漂移**：`src/gui_qt/main_window.py:238-242` 把侧栏 msgid 放在元组里 `i18n.tr(msgid)` 按名传入，Qt 用**两空格**形态（`📊  控制台`），而目录只有 Tk 遗留的**三空格**形态（`📊   控制台`）→ 切 en_US/en_GB/zh_TW 后侧栏与派生页标题（`:380` 的 `text().split("  ")[-1]`）恒回落简中原文。四目录各 +5 条并重编 `.mo`。
- **两套形态并存是刻意决定，不是重复登记**：`gui.py:2110-2114` 的 `_legacy_main()`（九份 `tests/test_gui_*.py` 以 AST/subprocess 钉在该模块）仍在用三空格形态。首轮按「源文已变更」做了改名，随即被提取器报「5 条缺失」暴露并**撤销改为并存**——改名会同时弄坏 Tk 侧栏译文。判据教训：非 ASCII + 连续多空格的模式在 Git Bash `grep` 下**静默漏配** `gui.py` 的调用点，孤儿判定一律走 AST 常量值比对。
- **刻意不动的两类**：① `build_exe.py` 的 `[build]` 日志（发布链开发侧输出，不在 i18n 扫描面，47 条）；② `action_button("📥  最小化到托盘")` 等 9 处构造器字面量——下一行 `set_text(..., T("最小化到托盘"))` 立即覆盖，既不进显示也不查目录，登记只会造成死条目。**代码侧待办**：Qt 按钮的 emoji 前缀因此实际丢失。
- **面板可见但未接 `tr()` 的一类（登记即死条目，本次不登记）**：`src/web_config.py::_check_url_target` 的 ValueError 文案与 `_INTERNAL_TARGET_HINT`（作为 f-string 实参注入，从不查表）、`src/web_models.py` 类型错误文案（经 `HTTPException(422, str(exc))` 原样出面板）、以及 raise 位常量消息共 **115 条**不在目录（`src/spider.py` 87 / `main.py` 12 / 其余 16）。要覆盖须先在产生点接 `tr()`，属代码改动、不在目录同步范围内。
- **前端与脚本**：`web/app.js` 内嵌四套目录（127 键 × 4 语，与后端四目录不同源、面板点分键不进后端）只读核对两两相等、无漂移；`StopRecording.vbs`（UTF-16 LE）只含进程名标识符，无用户文案。

**验证**：`extract_i18n_strings.py` 缺失 0 条、无「不一致」读数；四目录键数各 1115 且键集合逐项相等；`python scripts/compile_po.py` 生成 `.mo`（1116 条含头部空 msgid，147 743 字节）、`--check` 报同步、`gettext.GNUTranslations` 回读 1116 条；本机 GNU `msgfmt --check` rc=0、与仓库产物 msgid 集合逐项相等（仅头部元信息串形态不同）。进程内复现导航真实链路 `tr(msgid)` → `split("  ")[-1]`：en_US 得 `📊  Console` / `Console`，zh_TW 得 `🎯  畫質監控` / `畫質監控`，未启动 GUI 窗口（不打扰桌面）。`python scripts/run_gates.py` **10/10 全绿**；`pytest -q` **4303 passed / 14 skipped / 1 failed**，唯一红项 `tests/test_ui_fonts.py::TestInstallAndRegister::test_filename_is_sanitized` 与 i18n 无关（用例构造的文件名含 `:`，本机 `shutil.copy2` 失败；`test_ui_fonts.py` 与 `src/ui_fonts.py` 均零 `i18n` 引用，属 Windows 专属、Linux CI 不现）。四份目录行尾形态逐文件复测保持原样（纯 CRLF、无 BOM），`.po` 头部两处日期字段更新为 2026-10-17。真机端到端（第 2 步）：不涉及录制链/选源/ffmpeg/平台解析，未执行。

### v4.5.0-dev (2026-10-17) — GUI 窗口层迁移 PySide6：设计稿视觉语言 1:1 落地 + 打包链 Qt 死重剪除（`src/gui_qt/` / `gui.py` / `build_exe.py`）

> 工作包来源：`docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md`（2026-10-17 用户批准「无异议，执行」）。范围：新增 `src/gui_qt/`（16 文件 4189 行：`app` / `theme` / `shared` / `widgets` / `main_window` / `tray` / `settings_dialog` / `danmaku_monitor` / `quality_monitor` / `recorder` + `pages/` 五页），`gui.py` 的 `main()` 改为委托 `src.gui_qt.app.main()`（原 tkinter 实现改名 `_legacy_main()` 迁移期保留）；`src/ui_i18n.py` 新增 `"qt"` 模式与 `set_text()`；`build_exe.py` 接入 PySide6 收集并新增 `QT_BLOAT_FILES` 剪除；`pyproject.toml` / `requirements.txt` 双写 `PySide6`；新增 `tests/test_gui_qt_{theme,window,units}.py` 共 42 用例；i18n 四目录各 +47 条并重编 `.mo`（1111 条）。

- **为什么迁移而不是继续 ttk**：设计稿 `docs/gui-redesign/index.html` 的 18/24px 大圆角卡片、三档柔和投影与弹簧动效在 ttk 下无法原生实现（clam 主题没有圆角、没有控件级 alpha），自绘 Canvas 又不参与布局系统的尺寸协商；Qt 的 QSS + `QGraphicsDropShadowEffect` 可 1:1 还原，且 `QTableView` / `QTextEdit` 自带虚拟化与 `maximumBlockCount`，日志/弹幕高吞吐不需要自建渲染节流。用户决策（2026-10-17）：迁移 PySide6，还原范围 = 视觉语言全覆盖 + 空状态引导 / Toast / 卡片悬浮态。
- **控制器层与 UI 解耦是本次的净收益**：`recorder`（子进程生命周期）、`danmaku_monitor`（tail 边车 JSONL）、`shared`（配置裁决）、`settings_dialog` 都不含 Qt 布局代码，`QT_QPA_PLATFORM=offscreen` 即可离屏单测——旧 tk 版大量逻辑只能在真窗下验证的困境消除。
- **线程模型整体换轨**：旧 `_ui_event_queue + post_ui` 事件泵 + 5 处 `after` id 守卫 → Qt Signal/Slot（跨线程 Queued 连接）+ `QTimer`。子进程 stdout 读取线程经 Signal 回主线程；周期链（状态刷新 3s / 弹幕 1s）挂 `QTimer`，回调内仍包 try/except + 30s 限频留痕（「异常→静默」的老故障形态显式消掉）。
- **设计令牌单一事实源在 `theme.py`**：HTML `:root` 的 CSS 变量 → Python token 表（26 键 × 3 主题）→ `build_stylesheet()` 运行时现算 QSS 后整窗 `setStyleSheet` 一次生效；主题切换只换 token 重生成，不重建控件树。QSS 只认 objectName 选择器（`QFrame#card`）——写 `QFrame` 会命中 `QTableView` 的内嵌 frame。
- **竞态逐条搬运而非重写**（旧版踩过的坑一个不丢）：session_id 迟到回调、`_stopping` 复位放 `finally` 且早于会话校验、停止/退出共用单飞闸门 `_stop_child_once()`（控制台附着是进程全局状态，重复附着会让 pytest 的 stdout 跟着丢）。
- **打包两道闸，缺一不可**：① spec **不加任何 `collect` 调用**——`collect_all('PySide6')` 会把 647MB 的轮子（含 194MB 的 Qt6WebEngineCore）拖进产物，收集交给 PyInstaller 自带的 `hook-PySide6.py`（按实际导入的 Qt 模块逐个收），`'PySide6'` 只加在 CLI/Web 两个 Analysis 的 excludes 上；② hook 收完**还须剪**：hook 按「插件类型整目录」收插件、插件链接依赖再递带入包——`imageformats` 整目录收进了 `qpdf.dll`（拖入 Qt6Pdf 4.41MB），`platforminputcontexts` 整目录收进了 `qtvirtualkeyboardplugin.dll`（拖入 VirtualKeyboard→Quick→Qml 五件套约 14.3MB），`collect_extra_binaries` 还无条件收 Mesa 软件 GL `opengl32sw.dll` 19.68MB。excludes 管不到 hook 收的 DLL，只能 COLLECT 之后按文件名删：`build_exe.QT_BLOAT_FILES` 11 项 / 39.25MB，判据与 `BLOAT_EXCLUDES` 同源（**能指出它在产物里 + 运行期不可达**），入表判据是对 `_internal/PySide6/` 全部 dll/pyd 做链接依赖扫描（剪除项零反向引用、删除后无未解析导入）+ 冻结 GUI 实跑 9s 存活。剪后读数：91.81MB → 192.46MB → **153.21MB / 359 文件**（较阶段5 基线 +61.4MB，落在方案接受的 +50~70MB 区间），明细与判据落 `docs/agent-reference/measured-evidence.md`；回归锁 `tests/test_build_exe.py` 新增 2 条（剪除项不得含路径穿越/必须全在 PySide6 目录下 + 只删清单命中项）。
- **测试与门禁抓出的四个真问题**（都是写完才暴露，逐个修掉）：① `main_window._dynamic_status_info` 的 `interval` 在 config.ini 缺 `[录制设置]` 节时未绑定（basedpyright `reportPossiblyUnbound` 抓出）——先落默认值再进 try；② `app.py` 源码运行取 `app_root` 多上一级（落到项目根的父目录，config/ 全错位，装配用例抓出）；③ `pages/logs.py` 撞 `[tool.mypy].exclude` 裸名 `logs` 被无参 mypy 静默漏查（`test_mypy_exclude_never_shadows_source_files` 抓出）→ 改名 `runlog.py`；④ Qt 控件被 C++ 侧销毁后 Python 包装仍存活，`retranslate_all()` 不接 `RuntimeError` 会让一条死条目崩掉整轮回填（`tests/test_ui_i18n.py` 全局条数断言抓出）。
- **i18n**：47 条运行时模板四语目录同批登记（zh_CN.po 追加并重编 `.mo` 1111 条；en_US/en_GB JSON、zh_TW YAML 文本追加，保持既有键序）；`src/ui_i18n.py` 新增 `"qt"` 模式（`setText`）与 `set_text()` 入口。`tests/test_gui_qt_units.py` 打桩 subprocess 时必须走 `types.SimpleNamespace(**vars(mod))` 浅拷贝 shim——`test_test_hygiene` 的 R1 锁把 `setattr(subprocess, "run", ...)` 判为全进程生效改写。
- **迁移期并存与退役计划**：`gui.py` 顶层 tkinter 实现保留（九份 `tests/test_gui_*.py` 以 AST 静态锁 / subprocess 钉在本模块），Tcl/Tk 5.28MB 因此仍在产物里；旧版验证后退役（git 历史可回滚）。

**验证**：`python scripts/run_gates.py` 全绿 10/10（black / isort / mypy ×3 平台 238 files / check_annotations / compile_po 1111 条 / check_version / check_runtime_pins / consistency；内置 pytest 兜底 **4301 passed 且 warnings summary 为空**）；`scripts/check_coverage.py` **68 模块全部达标**（总量 82.68%；`src/gui_qt` 全部模块 ≥55%，最低 `pages/danmaku.py` 55.1%）；basedpyright 对 `src/gui_qt` + 新测试文件 0 errors；`scripts/report_bundle_size.py` 实跑 **153.21 MB / 359 文件**、工具链泄漏「未发现」；打包实跑 + 离屏截图（浅/深主题 × 5 页 + 85% 缩放档）布局正常（offscreen 平台无 CJK 字体回退，字形显示为方块属平台限制、非样式缺陷）；冻结 GUI exe 实跑 9s 存活、窗口标题正常。端到端目视确认交回用户：源码运行 `python gui.py` 切主题/缩放/语言目检。

| GUI PySide6 迁移 | 新增 `src/gui_qt/`（16 文件 4189 行）、`tests/test_gui_qt_theme.py`（8 用例）、`tests/test_gui_qt_window.py`（9 用例）、`tests/test_gui_qt_units.py`（25 用例）、`docs/gui-redesign/`（设计原型）、`docs/worklog/PROPOSAL_2026-10-17_gui-pyside6-redesign.md`；改动 `gui.py`（`main()` 委托 + `_legacy_main`）、`src/ui_i18n.py`（qt 模式 + RuntimeError 容错）、`build_exe.py`（spec 注释 + `QT_BLOAT_FILES` + `prune_qt_bloat()`）、`pyproject.toml` / `requirements.txt`（+PySide6 双写）、i18n 四目录各 +47 条并重编 `.mo`、`tests/test_build_exe.py`（+2 剪除回归锁）；生成物 `uv.lock` / `DouyinLiveRecorder.egg-info` 经 `sync_metadata.py` 重生成；文档 `AGENTS.md` ×3、本条目（中英同步）、`measured-evidence.md` +体积读数。一次性脚本 3 个（i18n 补录 / 依赖扫描 / 离屏截图，均落仓库外且已清理） |

### v4.5.0-dev (2026-10-17) — GUI 视觉语言改版：品牌蓝 → 暖赭橙 + 暖灰中性色（`src/ui_theme.py` / `gui.py`）

> 范围：纯表现层换色，零功能逻辑改动。`src/ui_theme.py` 的 THEMES `light`/`dark` 两表换 16 个槽位值（surface_alt / border / text / text_muted / primary / primary_hover / disabled_bg / disabled_fg，各 8 槽）；`gui.py` 的 `Colors` 品牌色组与中性色组同批换值（PRIMARY / PRIMARY_HOVER / PRIMARY_SOFT_* / BG_* / CARD_* / SIDEBAR_* / BORDER_* / TEXT_* / MUTED_*）。刻意未动：`high_contrast` 主题（无障碍主题不随品牌改版）、`TERMINAL_*` 终端配色（主题无关常量）、success / danger / warning / on_primary / surface 槽（对比度契约已锁定的语义色）、`src/ui_scale.py` 字号与间距 token（阶段6 已语义化，本次无可调项）。

- **设计语言来源**：`docs/gui-redesign/index.html`（单文件零依赖原型）定下的暖中性底 + 赭橙点缀；改版只把「色」落到既有主题层，控件结构、布局、字号层级、间距 token 一律沿用阶段4~6 的既有体系。
- **为什么主色不是原型里的 #C96442**：CONTRAST_REQUIREMENTS 强制 `on_primary`（白字）对 primary ≥ 4.5（正文 AA），#C96442 实测 3.90 不达标；同色相加深到 #B5573A 得 4.78。深色主题取 #B85A3F（4.59）——深色下还要满足 primary 对两种底 ≥3.0，亮度窗口只剩 0.13~0.18，更亮的 #D97757（白字 3.12）与更暗的同色都会越界。
- **深色主题的 hover 为什么是变暗而不是变亮**：`on_primary` 对 `primary_hover` 同样有 4.5 契约，深色下把 hover 调亮会跌破（#C96A4A 实测 3.72），故取更暗的 #A8502F；浅色主题相反，hover 走加深方向 #9C4A2C。
- **border 不得取「好看的浅灰」**：契约强制 border 对 surface / surface_alt ≥3.0（WCAG 1.4.11 非文本），浅色边框因此落在暖灰 #7A766F 一档——这是「边框可辨」与「克制配色」之间被机检钉死的下限。
- **`gui.Colors` 与 `ui_theme.THEMES` 是同值同源的两处落点**：品牌色改动必须成对修改（本次即按此口径执行）；`Colors` 的中性色组是品牌基调声明，控件实际着色全部走 ui_theme 槽位。

**验证**：`python scripts/run_gates.py` 全绿 10/10（black / isort / mypy ×3 平台 / check_annotations / basedpyright 0 错；pytest 4245 passed 0 warnings）；`tests/test_ui_theme.py` 35 passed（对比度机检全过）；`scripts/check_coverage.py` 51 模块全过（84.27%）；两改动文件复核均为纯 CRLF（LF-only 计数 0）；无窗冒烟：三主题 `ThemeManager.apply` 注册切换正常（dlr-light@100 / dlr-dark@100 / dlr-high_contrast@100）。端到端目视确认交回用户：启动 GUI 切换浅色/深色主题目检。

### v4.5.0-dev (2026-10-17) — GUI 右边框裁切修复 + 自选字体（`src/ui_fonts.py` / `gui.py` / `src/ui_kit.py`）

> 范围：`gui.py` 新增 `_raise_width_to_fit_content` / `_settled_reqwidth` / `Fonts.bind_family` / `Fonts.set_family` / `_activate_saved_font` / `_apply_font_family` / `_refresh_font_menu_values` / `_on_font_change` / `_on_import_font`，三条长提示标签补初始 `wraplength`、URL 配置页提示补接 `_bind_adaptive_wraplength`；新增 `src/ui_fonts.py`（SFNT name 表解析 + GDI 私有字体注册 + 偏好读写）；`src/ui_kit.py` 的 `EditorText` / `terminal_text` 加 `width=1` 与行距 `spacing1/spacing3`；新增 `tests/test_gui_right_edge_fit.py`、`tests/test_ui_fonts.py`，`tests/test_gui_wrap_hints.py` 的接线点锁由 4 改 5；i18n 四目录补 16 条 key。

- **右边框裁切的根因是「需求宽赤字 + Tk grid 裁切」两层**：① 三条长提示标签初始 `wraplength=0`（== 不折行，按单行全文 725~820px 计入需求宽）、`ui_kit` 两处 `tk.Text` 用默认 80 字符宽，把 `root.winfo_reqwidth()` 撑到 **1248 > geometry 1120**；② Tk grid 对「需求宽 > 分配宽」的 slave 是**裁切而不是收缩**，赤字从内容列右缘开始切，卡片右边框与 20px 右边距整段消失——与用户截图里「左边框在、右边框没了」完全同形。
- **为什么不能直接抬 `minsize` 到需求宽**：那会把窗口最小宽锁死在需求宽（本机实测 1389px），用户再也拖不窄，是可用性回退。实现走三段——抬**首窗几何**到需求宽消掉首帧赤字；把几何临时压到档位最小宽再读数，得到内容的**收缩地板**（本机 1108~1151px，随语言/内容变化）并只把 `minsize` 抬到地板；所有尺寸 clamp 到 `SCREEN_FILL_CEILING` 保证小屏仍可操作。
- **需求宽必须迭代到稳定再读**：Treeview 列宽在 `<Configure>` 回调里按树宽重算，`update_idletasks()` 不处理 Configure 事件——只用 idle 会让读数停在大窗时的旧值（实测差 300+px），`_settled_reqwidth()` 就是为此存在。实测 4 次迭代后 `reqwidth` 稳定，重复调用不会自激放大。
- **自选字体：为什么不依赖 `tkfont.families()` 判可用**（本次最大的坑，实测结论写进 `ui_fonts.family_resolves` 的注释）：`AddFontResourceExW(FR_PRIVATE)` 返回成功、Tk 也能按该族名排出字形，但 **`families()` 永远列不到它**（Tk 只枚举注册表里已安装的字体）；而字体不存在时 Tk 又**静默回退**到兜底字体、既不报错也不给 Families 提示。于是「在 families() 里」既非必要也非充分，唯一能分辨「真加载了」与「静默回退」的判据是让 Tk 解析一次并与人造缺失族名的兜底结果比对。验证方式：把系统字体副本的全部 `nameID=1` 记录改成同一个标记名，`Font(标记名).actual()["family"]` 确实返回了副本里的姓——证明私有注册这条路走得通。
- **`woff2` 为什么被明确拒收**：Tk 在 Windows 上经 GDI 取字体，只认 SFNT 容器（`.ttf`/`.otf`/`.ttc`）；woff2 是网页传输格式，引入解压依赖只为收一个 GUI 下拉框不划算，故在导入入口直接挡掉并给出「请先转成 ttf/otf」的可读原因，而不是「导入成功但没变化」。
- **切热衷于同一次 `configure` 完成，不重建控件树**：`Fonts.set_family()` 对已缓存的比例字体对象原地改 `family=`（Tk 字体是具名共享资源，控件持有名字而非快照），日志内容 / URL 编辑器未保存内容 / 两张监控表零损失；`_apply_font_family` 随后 `restyle_fonts` + 各页 `update_idletasks` + 重跑 `_raise_width_to_fit_content` / `_raise_minsize_to_fit_sidebar`，把「换族后需求宽变化」在同一 sync 里消化，避免偏到右边框裁切那条老路上。等宽链路（`mono_*`）刻意不动——日志终端与 URL 编辑器靠字符对齐读。
- **字体显示的一致性**：字号/行距仍由 `src/ui_scale.TYPE_SCALE` 的语义档位单一事实源决定（本次只补了 tk.Text 的上下 2px 行余量：中文没有西文那样的降部空间，默认 leading 挤成一片）；抗锯齿由系统 ClearType 决定、非 Fontconfig 配置所能改；中英文混排依赖 Windows 的字体回退链（缺字形按字形级回退），预设列表因此优先列本机命中且带 CJK 字面的族。

**验证**：`python scripts/run_gates.py` 全绿（black/isort/mypy 三平台/check_annotations/basedpyright）；`pytest tests/test_gui_right_edge_fit.py tests/test_ui_fonts.py tests/test_gui_wrap_hints.py tests/test_ui_kit.py tests/test_ui_scale.py tests/test_i18n.py tests/test_gui_language_retranslate.py -q` → 0 warnings passed；真机（1366×768 @133% DPI）几何探针读数由「reqw 1248 < width 1120（裁切）」变为「reqw 1108 ≤ width 1389、`minsize` 宽 1108，各宽度下卡片右缘溢出 0」。

### v4.5.0-dev (2026-10-17) — 发布链运行时钉定新增「在线来源层」：默认 off，且只在清单有独立认证时才允许采用在线值

> 范围：`build_exe.py` 新增「运行时钉定的在线来源」一节（三态开关 + 信任档 + 来源表 + 缓存 + 落点函数）、`--pin-source` 命令行参数、`_pinned_slots()` 接线、`_download_nodejs` 记录本次解析出的版本/文件名、`_verify_gpg_artifact` 增 `strict` 关键字并改为返回 `bool`；`tests/test_build_exe.py` 新增 17 条用例并把 `api.github.com` 并入来源主机白名单。**`_PINNED_RUNTIME_SHA256` 一个值都没改**，默认行为与引入本层前逐字相同。

- **为什么没有按「把硬编码哈希换成运行时拉取」实现**：那张表是「维护者在某时刻从官方渠道抄下来的带外基线」，强度恰恰来自**通道独立**。改成运行时拉取后，期望值与产物走同一条通道——gyan.dev 的 `.sha256` 文档就是它自己服务器发的，`api.github.com` 的 digest 与产物同在 github.com——中间人换掉归档的同时就把清单一起换了，于是「拉清单 → 当期望值 → 比对产物」三步恒等通过。故本层**默认 off**，并把来源分成 `signed` / `advisory` 两档，而不是统一放行。
- **三态开关（off / verify / adopt）**：`off`（默认）一次网络请求都不发；`verify` 拉取后**只与内置表比对**，一致即印证内置表仍有效、不一致在发布路径 `SystemExit` 并打印在线值供回填，**永不写入**——写进去就等于跳过「人工回填内置表」这道闸口，而那道闸口同时也是「重新确认版本代次 / 体积门禁 / 冒烟」的触发点；`adopt` 才把在线值升格为判据。环境变量为 `DLR_RUNTIME_PIN_SOURCE`，未识别值（如拼写错的 `verfiy`）告警后按 `off`，绝不猜成别的档。
- **adopt 的准入门是「清单有独立认证」，不是「清单能拉到」**：只有 `trust=signed`（配套分离 GPG 签名 + 已钉 40 位主钥指纹）且**清单本身验签通过**的槽位可采用。验签复用的就是产物侧那段 `_verify_gpg_artifact`（判据只有一份：`GOODSIG`+`VALIDSIG` 且签名钥匙属于钉定指纹那把钥匙），只把 `strict` 置 False 让它改成「不采用」而不是「终止构建」——真正的 fail-closed 闸口仍在产物下载那一步。`advisory` 档与「signed 但没钉指纹」一律拒绝采用并回退内置值。
- **`strict` 只改「失败怎么处置」，不改判据**：原语义本来就分两类——「取不到签名 / gpg 不可用」在本地路径是留痕跳过、发布路径终止；「指纹不在环内 / BADSIG / 无 VALIDSIG」两侧都终止。本次把两类分别收进 `_skip_or_fail` / `_hard_fail`，判据与报错文案逐字保留（`test_gpg_tool_or_sig_missing_never_passes_silently` 与 `test_gpg_rejects_every_untrustworthy_shape` 未改一条断言）。
- **形状关只有一处**：在线值必须过 `_SHA256_PATTERN`（64 位小写十六进制）才可能被采用；空响应体 / HTML 错误页 / 长度不足 / 非十六进制 / GitHub digest 的 `sha256:` 前缀，全部在这一处收敛。解析不出即按「没拉到」处理，且失败值**不进缓存**——一次超时不该把整轮构建的在线核对钉死在「拉不到」上。
- **缓存与刷新频率**：进程内 `(运行时键, 槽位) → (时刻, 值)`，TTL 默认 24h（`DLR_PIN_CACHE_TTL`，设 0 = 每次重取），拉取超时 `DLR_PIN_FETCH_TIMEOUT` 默认 30s（清单只有几 KB，不该按产物下载的 180s 给）。一轮构建远短于 24h，故它实际只在「同一进程多次问同一槽位」时生效。跨进程磁盘缓存**刻意未做**：那会落一份无人复核的状态文件，反而给「陈旧值被当成刚拉的」留了通道。
- **node 清单必须按本次实际版本拼 URL**：下载点是从 `nodejs.org/dist/index.json` 选出的最新 LTS，版本每次构建都可能不同。故 `_download_nodejs` 在 `_download_file` 之前把版本与文件名写进 `_NODE_RESOLVED_VERSION` / `_NODE_RESOLVED_FILENAME`，来源表用 `{version}` / `{filename}` 占位；版本尚未解析时**显式跳过**而不是拼一条恒 404 的残缺 URL——那会让报错指向「上游挂了」，把真因藏起来。
- **待补（本条目明确标注未填）**：`_PIN_SOURCE_TABLE` 里 node 槽的 `fingerprint` 仍是空串 → 该槽**不可 adopt**（有意的 fail-closed）。填 Node.js 发布钥匙的完整 40 位主钥指纹后该槽才会在 `adopt` 下真正生效。macOS 两槽（evermeet 不公布哈希）未登记来源，维持官方签名档，`verify`/`adopt` 都不会去打扰它们。
- **门禁读数（改后复跑）**：`black --check` 两个改动文件 unchanged；`isort --check-only` rc=0；`mypy` 不带路径 rc=0；`scripts/check_annotations.py` rc=0；`scripts/check_runtime_pins.py` rc=0 且 `--strict` rc=0；`pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` **142 passed**（改动前 125，新增 17 条）。两个改动文件换行形态复核均为纯 CRLF（LF-only 计数 0）。
- **端到端真机验证（DoD 第 2 步）**：**未执行**——默认 off 路径零行为变化，非默认路径（`--pin-source verify/adopt`）需外网访问 nodejs.org / gyan.dev / api.github.com 且本机需装 gpg；17 条新用例全部离线打桩。交回用户的动作：补齐 node 发布钥匙指纹后，建议在本机实跑一次 `python build_exe.py --pin-source verify --no-zip --no-runtime` 核对日志。

### v4.5.0-dev (2026-10-04) — GUI 界面现代化阶段6：字号层级重排 + 全局缩放设置 + 过渡动效（`src/ui_scale.py` / `src/ui_motion.py`）

> 范围：新增 `src/ui_scale.py`（语义字号 token + 间距栅格 + 缩放档位 + 小屏降档 + 持久化）与 `src/ui_motion.py`（off/subtle/full 三档 + 插值原语 + 系统「关闭动画」感知 + 持久化）；`src/ui_theme.py` 的 ttk padding / rowheight / 表格字体改由 ScaleProfile 派生、ttk 主题名带档位段；`src/ui_kit.py` 的字体派生样式缓存键加档位段、补`restyle_fonts` 重指与 `slide_in`/`scale_in_window`/`blend` 过渡原语、`DataTable.sync` 返回变化行供高亮反馈；`gui.py` 的 `Fonts` 改 token 驱动 + 原地改字号、侧栏底部四项偏好重排 2×2、新增缩放/动效两个菜单与回调、窗口与侧栏几何随档位缩放并 clamp 到屏幕；`config/config.ini` 补两个键与注释；四语目录各 +14 条并重编 `.mo`（1048 条）。

- **字号层级重排（本次的起因）**：阶段5 的档位是 12/13/15/20/26逻辑 px，**12 与 13 只差 1px**，视觉上「辅助文字」与「正文」根本分不开——这正是用户截图中侧栏状态文字与导航项糊成一档的原因。新体系按「相邻档位至少差 1.5pt、辅助文字不小于 10pt」重排为 caption 10 / label 11 / body 12 / heading 14 / stat 16 / title 19 / display 28（100% 档位的点值），并把表格/列表这一档显式命名为 `label`、统计数值独立为 `stat`（原先两者都复用 `body`/`title`，表格里数字与正文同重、扫读没有锚点）。
- **缩放只改字号与间距，不改信息密度**：行高、padding、侧栏宽度随档位线性放大，但表格列数、卡片结构、导航项数量全部不变。否则「放大界面」会退化成「重排信息架构」。
- **即时生效且不丢运行态（本阶段能成立的关键）**：`tkfont.Font` 是**具名共享资源**，控件 `-font` 指向的是名字而非快照，故`Fonts.rescale_all` 只对已缓存的 Font 对象 `configure(size=...)`，所有引用它的控件自动重绘——**不重建控件树**。重建会清空日志内容、URL 编辑器未保存内容与两张监控表（与阶段4 之前「每轮 destroy + 重建」的整表闪烁是同一类事故）。等宽字体也相应从元组改为 Font 对象（元组是快照，不随缩放变）。
- **DPI 与缩放是两件事**：DPI 适配由 Tk 的 `tk scaling` + 负数点值天然承担（阶段5 起已是如此，本次未改）；本阶段补的是**低分辨率屏**这一层——`auto_scale_for_screen` 按屏幕可用区给小屏降一档（两个维度取更严的一方，1366x768 与 1920x700 都降），`window_size` 把窗口四值 clamp 到屏幕的 94%，保证 150% 档在 1366x768 上开不出比屏幕还大的窗口。屏幕尺寸读不到时不做 clamp 但也不崩。
- **点值不按系数线性放大**：点本身已是与 DPI 无关的物理量，再乘一次用户系数会让 150% 档正文达18pt（约 24px @96dpi），行高与卡片全部撑坏。故用 `factor ** 0.6` 的温和增益（150% 档得 1.30倍、85% 档得 0.90 倍）——用户能明确感到变大变小，但布局不被撑坏。等宽再乘 0.9（等宽字符变宽会让一行能装的列数骤减）。
- **ttk 主题名必须带档位段**：`theme_create` 对同名第二次调用抛 TclError，而 Tk 没有「更新已注册主题」的 API。换档后若沿用 `dlr-light` 这个名字就拿不到新的 padding/rowheight，只能换名重注册（`dlr-light@115`）。旧主题名残留在 `theme_names()` 里无害（Tk 不回收）。
- **换档后必须 `restyle_fonts` 重指按钮样式**：`font_style` 的派生样式在创建时**拷贝**了基础变体的 configure（含 padding），换档后基础变体已变而已存在的按钮仍指着旧派生样式名——表现为「字号变大了但按钮内边距还是老样子」，85% 档尤其明显（按钮相对文字过大，真机截图复核时发现）。`restyle_fonts` 遍历控件树把带字体的按钮重新指向按新主题派生的样式。
- **Tk 能力边界（如实说明，不假装能）**：ttk/clam 没有圆角、没有控件级 alpha。因此卡片继续用 1px 描边（扁平风本就如此），「圆角」只落在 Canvas 自绘的大圆点/状态胶囊上；页面切换与弹窗用**位移 + 尺寸插值**（滑入 / 缩放落位），**不做假淡入**——硬做只能靠截图覆盖，既慢又脏。
- **动效三档 + 无障碍优先**：`off`/`subtle`/`full`，默认 `subtle`。系统「关闭动画」开关（Windows `SPI_GETCLIENTAREAANIMATION`、macOS `reduceMotion`）**优先于**用户在设置里的选择，一律压到 `off`；此时侧栏菜单显式落到「关闭」并落一条日志——用户选了却毫无反应几乎必然被当成 bug 报上来。`off` 档**不排 after、同步落终态**（不落终态就会停在半途位置），且立刻停掉在途的状态点呼吸链（那是本窗口唯一「界面静止也在持续重绘」的来源）。
- **帧数硬上限**：`MAX_FRAMES=12` 与调用方传入的 frames 取小，`subtle` 档再收一半。这是「流畅克制」的可机检形态，防止用户选 full 就把主线程占满。
- **表格变化行高亮**：`DataTable.sync` 改为返回本轮真正变化的行（新增 + 值/标记变化），gui 据此挂一个 `flash` tag 并逐帧混回原色。**末帧必须显式摘 tag**：末帧颜色虽已等于常态底色，但 tag 仍在，下一轮 sync 改 tags 时会因「多了一个 tag」被判成变化而误触高亮，形成「每轮都闪一下」的自激循环。高亮色取 primary 与 surface_alt 的中间色而非 success/danger——好坏已由 `downgraded`/`disconnected` 两个 tag 表达，复用语义色会让两种含义叠在一起。
- **侧栏底部重排 2×2（真机截图暴露的布局缺陷）**：阶段5 是「每项一个标签 + 一个整宽下拉」竖排四项，底部约 344px；加缩放与动效后继续竖排要约 470px，在 85% 档（窗口高 629px、侧栏需求高 662px）会把「彻底退出」顶出窗口——用户表现为「退出按钮只剩一条红边」。2×2 布局把底部压回约 200px。另补 `_raise_minsize_to_fit_sidebar`：把侧栏的**实测** `winfo_reqheight` 纳入 minsize 下限（写死常量必然在某个「档位 × 语言 × 译文行数」组合下失准），但仍以当前窗口高封顶，避免屏幕装不下时窗口拖不动。
- **页面滑入不能只`place_forget` 收尾（真机发现的真bug）**：`place_forget` 会把控件从**所有**几何管理器里摘掉，页面原本是 grid 排的，forget 之后它既不在 grid 里也不在任何地方，控件直接从窗口上消失。正确做法是过渡前抓一份原布局器的 `grid_info`/`pack_info`、终帧 `place_forget` + 按原布局器写回。
- **i18n**：新增 14 条文案（`界面缩放`/`动效强度`/`自动`/`关闭`/`轻微`/`完整`/`{percent}%` 及 6 条形参日志、`系统已关闭动画效果…` 提示）四语目录同批登记并重编 `.mo`（1034 → 1048 条）。`en_US.json`/`en_GB.json` 以**文本追加**而非 `json.dumps(sort_keys=True)` 重写：既有键序由提取器的本地化排序决定，重写会造成近千行无意义 diff（门禁校验键集合而非顺序）。
- **测试与变异验证**：新增 `tests/test_ui_scale.py`（44 用例：档位体系/夹取/字号层级单调性/点值恒负/窗口 clamp/自动降档/解析容错/持久化往返与注释保留）与 `tests/test_ui_motion.py`（38 用例：帧计划不含终帧/帧数上限/无障碍优先/控制器/`blend` 终点精确归位/持久化）；`tests/test_ui_theme.py` 改 2 条断言（主题名带档位段）并新增换档重注册用例。**变异验证四处**：`a11y_priority`（拆掉系统优先）→ `test_system_off_overrides_user_choice` 转红；`include_final`（帧序列含终帧）→ `test_plan_excludes_final_frame` 转红；`frame_cap_all`（拆掉帧数上限）→ `test_frames_capped_by_max` + `test_subtle_is_shorter_than_full` 转红；`off_all_three`（同时拆掉 off 档的三道冗余守卫：表值 / 短路 / `total<=1`）→ `test_off_returns_empty` + `test_off_runs_terminal_state_synchronously` 转红。第四项的必要性：前三处单点变异被 `frame_plan` 里的**冗余守卫**掩盖（拆一个另一个仍兜住），只有同时拆掉三道才能证明不变量本身被测到、不是假绿。
- **门禁读数**：`pytest`（无 coverage）**4184 passed / 16 skipped / 0 failed**；`check_coverage.py` **50 模块全部达标**（新模块 `src/ui_scale.py` 96.1%、`src/ui_motion.py` 80.9%，`src/ui_theme.py` 85.0%、`src/ui_kit.py` 55.4%）；`mypy` 不带路径 **215 source files / no issues**；`black --check` 216 files unchanged；`isort --check-only` rc=0；`compile_po.py --check` rc=0（1048 条）。`run_gates.py` 的 `check_skill_agents_consistency.py` 一项 rc=2（本worktree 无 `.agents/skills` 目录，属「没跑」而非代码不合格，与本次改动无关），其余 10 项全绿。带 `--cov` 的整轮出现 17 failed + `INTERNALERROR`，根因是 harness `sitecustomize.py` 的 safe-delete 批量守卫在后台线程 spawn node 时 `WinError 6`（句柄无效）——环境拦截、非代码回归，无 coverage 的同轮全绿可对照。
- **端到端真机验证（DoD 第 2 步）**：**已执行**。真窗起GUI 逐项切换主题×4 / 缩放×5 / 动效×4 / 五个页面 / 关闭对话框 / 高级设置窗口，全部无异常（`ALL_OK`）；并在 85% / 100% / 150% 三档各截图人工复核——上述「按钮内边距不跟随」「侧栏底部溢出」「页面滑入后消失」三个缺陷都是这一步发现的，不是读代码看出来的。

### v4.5.0-dev (2026-10-04) — CI 工具版本常量对齐本地实装：`isort_version` 9.0.1 → 9.0.2（抬掉「本地全绿不可外推 CI」的最后一处版本差）

> 范围：只改 `.github/workflows/ci.yml` setup job `consts` 的 `isort_version` 一行 + 三点注释，`AGENTS.md`「格式化命令」可外推前提条目补记本次抬升，本条目（中英同步）。**未**改 `[tool.isort]` 配置、**未**改 `pyproject.toml`/`requirements.txt` 依赖声明、**未**动任何 `.py` 源码或测试。

- **为什么抬 CI 而不是压本地**: 本地 `.venv` 实装 isort 9.0.2（`importlib.metadata.version('isort')` 读数），CI 钉 9.0.1 差一个补丁位。按「格式化命令」条目的口径，这一处差使得 isort 门禁结论只能标注「本地口径，未经 CI 同版本验证」；而本地 9.0.2 已对全仓 212 文件判 `rc=0` 且无 silent-skip，把 CI 抬到实装版本是**放行方向与验证方向一致**的那一侧。反过来把本地压回 9.0.1 需重装 venv 包，按「风险控制（前置）」属用户通道。经用户批准执行（2026-10-04）。
- **单点改动即全覆盖**: `isort_version` 只有一个登记点（`echo "isort_version=…"`），lint job 与 test job 两处 `pip install` 都经 `${{ needs.setup.outputs.isort_version }}` 消费，不存在第二份副本需要跟改。四值现与本地实装逐一同值：black 26.5.1 / isort 9.0.2 / mypy 2.4.0 / pytest 9.1.1。
- **抬常量只消除版本差，不等于 CI 实跑已验证**（原注释已把这条例外写进 AGENTS.md 正文）: 本次证据全部来自本机 Windows/GBK locale 跑法，CI 侧 ubuntu + 已 `env: PYTHONUTF8: "1"` 的等价性由既有 MID-63 防线保障，不靠本次外推。
- **`uv.lock` 仍是 9.0.1，刻意不重生成**: CI 装 isort 走 `pip install "isort==<const>"`，**不经** `uv sync`；`uv.lock` 里 9.0.1 是 `[project.optional-dependencies] dev` 的 `isort>=5.12.0` 在**上次锁定时**的解析产物，与本常量无耦合。`pyproject.toml` 未改 → `sync_metadata.py --check`（static job 与元数据回归锁）判定面不变，无需 `uv lock` 重算。
- **门禁读数（改后复跑，指向最后一次编辑之后）**: `black --check` **212 files unchanged / rc=0**；`isort --check-only --diff` **rc=0、diff 空、无 `Unable to parse file`**（`Skipped 17 files` 为 `extend_skip` 预期）；`mypy` 不带路径 **211 source files / no issues**，`--platform linux` 与 `--platform win32` 各 0，另用 `--cache-dir` 冷缓存复跑三遍排除陈旧缓存假绿；`basedpyright` **0 errors / 0 warnings**（`filesAnalyzed=212`）；`pyright` 显式传与 `[tool.mypy].files` 同集合路径 **0/0/0**（裸跑扫描面与门禁不同，只作参考）；`pytest` **4095 passed / 14 skipped / 0 failed / warnings summary 空**；`check_coverage.py` **48 模块全部达标（84.89%）**；`scripts/run_gates.py` **10/10 PASS**。14 项跳过全属平台/权限门控（`test_spider_hardening.py:198` 参数化 6 项、符号链接特权 3 项 `WinError 1314`、Windows `os.chmod` 只读位 2 项、环境变量大小写 1 项、SIGKILL 自杀 POSIX 形态 1 项、本机 h2 可用 1 项），非代码回归。
- **端到端真机验证（DoD 第 2 步）**: **未执行**——本次零录制链路/选源/ffmpeg 参数/平台解析改动（只动 workflow 常量与文档），按该步适用条件豁免；交回用户的动作：无。

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

> **滚动归档**：v4.4.0 及更早的条目已整卷迁入 [docs/changelog/code-wiki-history-zh.md](docs/changelog/code-wiki-history-zh.md)，本节只保留当前发布周期的条目。
