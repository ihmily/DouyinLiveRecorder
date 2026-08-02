# DouyinLiveRecorder 项目架构文档

## 目录

- [项目概述](#项目概述)
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

---

## 项目概述

### 项目基本信息

- **项目名称**: DouyinLiveRecorder (抖音直播录制器)
- **版本**: 4.0.8.1
- **作者**: Hmily
- **开源协议**: MIT
- **项目地址**: [GitHub](https://github.com/ihmily/DouyinLiveRecorder)

### 功能特性

- ✅ 支持 60+ 个直播平台（抖音、TikTok、YouTube、快手、虎牙、斗鱼、B站、小红书等）
- ✅ 循环值守直播状态，开播自动录制，断播自动停止
- ✅ 多种视频格式输出：TS、MKV、FLV、MP4、MP3、M4A
- ✅ 命令行 + GUI + Web 管理面板三模式运行
- ✅ 多平台消息推送：钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus
- ✅ Docker 容器化部署
- ✅ 国际化支持（中文/英文）
- ✅ 灵活配置：画质选择、分段录制、自定义保存路径等
- ✅ 实际画质回采与降级告警（支持抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC）

### 技术栈

| 技术                               | 用途                                                   |
| -------------------------------- | ---------------------------------------------------- |
| Python 3.10+                     | 核心编程语言                                               |
| asyncio + httpx                  | 异步网络请求                                               |
| asyncio                          | 异步装饰器支持                                              |
| FFmpeg                           | 视频录制与转码                                              |
| Node.js + exejs/PyExecJS         | 运行 JavaScript 签名算法（exejs 优先，PyExecJS 回退）             |
| Loguru                           | 结构化日志                                                |
| CustomTkinter + pystray + Pillow | GUI 图形界面与系统托盘                                        |
| FastAPI + uvicorn                | Web 管理面板后端                                           |
| HTML + CSS + JavaScript          | Web 管理面板前端                                           |
| Docker                           | 容器化部署                                                |
| gettext (msgfmt)                 | 国际化翻译编译                                              |
| mypy                             | 静态类型检查（`--strict` 模式，`disallow_untyped_defs = true`） |
| pyflakes                         | 静态代码检查                                               |

---

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

---

## 目录结构

```
DouyinLiveRecorder/
├── config/                              # 配置文件目录
│   ├── config.ini                      # 主配置文件
│   └── URL_config.ini                  # 直播间地址列表
├── src/                                 # 核心源码包
│   ├── __init__.py                     # 包初始化 + Node.js 环境配置
│   ├── spider.py                       # 直播数据爬虫（60+ 平台）
│   ├── stream.py                       # 直播流地址解析（含画质回采）
│   ├── room.py                         # 直播间信息解析
│   ├── utils.py                        # 工具函数库
│   ├── logger.py                       # Loguru 日志配置
│   ├── proxy.py                        # 代理检测
│   ├── ab_sign.py                      # 抖音签名算法 (A-Bogus)
│   ├── node_install.py                # Node.js 自动安装/初始化
│   ├── weverse_auth.py                 # Weverse 平台认证
│   ├── ttwid.py                        # 抖音访客 ttwid 获取
│   ├── web_api.py                      # Web 管理面板 FastAPI 应用
│   ├── web_config.py                   # Web 面板配置读写（不依赖 FastAPI）
│   ├── web_tray.py                     # Web 模式系统托盘（Windows 最小化到托盘）
│   ├── http_config.py                  # HTTP 客户端共享运行时配置（SSL 验证开关）
│   ├── async_http.py                   # 异步 HTTP 客户端 (httpx)
│   ├── sync_http.py                    # 同步 HTTP 客户端
│   ├── javascript/                     # JavaScript 签名脚本
│   │   ├── crypto-js.min.js            # 加密库
│   │   ├── x-bogus.js                  # 抖音 X-Bogus 签名
│   │   ├── haixiu.js                   # 嗨秀签名
│   │   ├── laixiu.js                   # 来秀签名
│   │   ├── liveme.js                   # LiveMe 签名
│   │   ├── migu.js                     # 咪咕签名
│   │   └── taobao-sign.js              # 淘宝签名
│   └── ffmpeg_install.py                # FFmpeg 安装脚本
├── web/                                 # Web 管理面板前端
│   ├── index.html                      # 单页应用入口
│   ├── app.js                          # 前端逻辑（API 调用、SSE、渲染）
│   └── style.css                       # 样式表（主题、响应式）
├── i18n/                                # 国际化文件（gettext）
│   ├── zh_CN/LC_MESSAGES/
│   │   ├── zh_CN.po                   # 中文翻译源
│   │   └── zh_CN.mo                   # 编译后的翻译（运行时必需，随仓库/镜像分发）
│   └── en/LC_MESSAGES/                 # 英文（预留，当前为空）
├── typings/                             # 第三方库类型存根（仅静态检查用）
├── ffmpeg/                              # FFmpeg 二进制目录（Windows，git 忽略 exe）
├── node/                                # Node.js 二进制目录（Windows，git 忽略）
├── main.py                              # 命令行入口
├── gui.py                               # GUI 图形界面入口（CustomTkinter）
├── gui_legacy.py                        # 旧版 GUI（兼容保留）
├── web.py                               # Web 管理面板入口
├── i18n.py                              # 国际化实现（print 翻译包装）
├── msg_push.py                          # 消息推送模块
├── index.html                           # 独立 M3U8/FLV 播放器页面
├── StopRecording.vbs                    # Windows 停止录制脚本
├── build_exe.py                         # PyInstaller 打包脚本（CLI/GUI/Web 三入口）
├── DouyinLiveRecorder.spec              # 由 build_exe.py 自动生成（.gitignore 已忽略）
├── requirements.txt                     # Python 依赖列表
├── pyproject.toml                      # Python 项目配置
├── Dockerfile                          # Docker 构建文件（多阶段）
├── docker-compose.yaml                 # Docker Compose（recorder/web/gui 三服务）
├── .dockerignore                       # Docker 构建上下文排除文件
├── .gitignore                          # Git 排除文件
├── README.md                           # 项目说明
├── tests/                               # 单元测试目录
│   ├── conftest.py                     # Pytest 配置与 fixtures
│   ├── test_stream.py                  # stream.py 核心路径测试（工具函数 + 平台流解析）
│   ├── test_async_http.py              # async_http.py 核心路径测试（客户端管理 + 请求）
│   ├── test_room.py                    # room.py 直播间解析测试
│   ├── test_spider.py                  # spider.py 爬虫测试
│   ├── test_utils.py                   # utils.py 工具函数测试
│   └── test_douyin_url_resolution.py   # 抖音 URL 分发逻辑测试
├── .github/                             # GitHub Actions 工作流目录
│   └── workflows/
│       └── build-release.yml           # 三平台构建 + 自动发布 Release
└── CODE_WIKI.md                        # 本架构文档
```

---

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
- `select_source_url()` - 在 m3u8/FLV 源间选择，HLS 源校验失败时回退 FLV（`delay_default=120s` 轮询）
- `_validate_stream_url()` - 流地址校验（2026-08-01 增强）：content-type 判定补充 `mpegurl`；HEAD 被拒时对 `.m3u8` 源补 `Range: bytes=0-0` GET 探测——抖音 CDN 的 m3u8 常对 HEAD 返回 4xx，此前会被误判不可达而总回退 FLV

---

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

| URL 形态                                 | 处理路径                                                                                                                  |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `live.douyin.com/<房间号或抖音号>`            | 直调 `get_douyin_web_stream_data`（`web/enter` API 接受抖音号，无需重定向解析）                                                        |
| `www.douyin.com/user/<sec_uid>`（网页端主页） | 跳过必然失败的 `get_sec_user_id` 探测，走 `resolve_from_homepage()`：`get_unique_id()` 解析抖音号 → 拼接 `live.douyin.com/<抖音号>` → 直调网页端 |
| `v.douyin.com/<短链>`（App 短链，可能指向直播间或主页） | 先 `get_sec_user_id()` 跟随重定向；抛 `UnsupportedUrlError` 时回退 `resolve_from_homepage()`                                     |

- `resolve_from_homepage()` 直调 `get_douyin_web_stream_data`（网页端 API 优先、内置 HTML 兜底），不再绕经旧版 HTML 优先抓取路径（约 1MB 页面），并**显式透传 proxy_addr / cookies**（旧实现未透传，导致代理与 Cookie 配置在主页路径静默失效）
- `web/enter` API 调用封装为 `_try_web_api()` + `for attempt in range(2)`：首次失败（如瞬时风控 `status_code=10002`）→ `await asyncio.sleep(0.5)` 缓冲 → 静默重试；重试成功直接返回、跳过 HTML 兜底；两次都失败才记 WARNING 并回退 HTML（取 HEVC 原画的 HTML 抓取是各网页端路径通用行为，保持不变）

**实现特点**:

- 使用异步 HTTP 客户端 (`httpx`)
- 各平台独立的签名算法
- 代理支持
- Cookie 支持
- 错误重试机制
- B站 spider 返回 dict 结构（含 `current_qn`/`accept_qn` 元信息），供 stream 模块回采实际画质

---

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

| 函数                          | 平台     | 实际画质回采方式                                            |
| --------------------------- | ------ | --------------------------------------------------- |
| `get_douyin_stream_url()`   | 抖音     | 从 `flv_pull_url` / `hls_pull_url_map` 的 key 提取画质标签  |
| `get_tiktok_stream_url()`   | TikTok | 从 `vbitrate` 字段通过 `bitrate_to_quality()` 反查         |
| `get_kuaishou_stream_url()` | 快手     | 从 `flv_url_list` 的 `bitrate` 字段反查                   |
| `get_huya_stream_url()`     | 虎牙     | 从 `exsphd` ratio 值映射，处理降级选择                         |
| `get_douyu_stream_url()`    | 斗鱼     | 从平台下发的 `rate` 字段反向映射                                |
| `get_bilibili_stream_url()` | B站     | 从 spider 返回的 `current_qn` 反向映射为画质代码                 |
| `get_netease_stream_url()`  | 网易CC   | 从画质名（blueray/ultra/high）通过 `NETEASE_QUALITY_MAP` 映射 |

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

---

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

---

### 5. 工具模块 (`src/utils.py`)

**职责**: 提供通用工具函数

**主要工具**:

| 工具函数                       | 功能描述          |
| -------------------------- | ------------- |
| `Color` 类                  | 终端彩色输出常量      |
| `trace_error_decorator()`  | 错误追踪装饰器       |
| `check_md5()`              | 计算文件 MD5      |
| `dict_to_cookie_str()`     | cookie 字典转字符串 |
| `read_config_value()`      | 读取配置文件值       |
| `update_config()`          | 更新配置文件        |
| `remove_emojis()`          | 移除文本中的表情符号    |
| `remove_duplicate_lines()` | 移除文件重复行       |
| `handle_proxy_addr()`      | 处理代理地址格式      |
| `generate_random_string()` | 生成随机字符串       |

---

### 6. 日志模块 (`src/logger.py`)

**职责**: 基于 Loguru 配置结构化日志

**日志输出**:

- **控制台**: 彩色日志输出
- **`logs/streamget.log`**: DEBUG 级别（排除 INFO）
- **`logs/PlayURL.log`**: INFO 级别（仅直播流地址）

**日志文件开关**:

- 通过 `config/config.ini` 的 `是否启用日志文件(是/否)` 控制
- 默认启用，保持向后兼容
- logger.py 在初始化时直接读取配置（不依赖 main.py 执行顺序）

**日志轮转**: 300 KB 自动轮转，保留 1 份

---

### 7. 消息推送模块 (`msg_push.py`)

**职责**: 支持多种消息推送渠道

**支持渠道**:

| 渠道       | 函数名            | 说明               |
| -------- | -------------- | ---------------- |
| 钉钉       | `dingtalk()`   | 群机器人推送           |
| 微信       | `xizhi()`      | Server酱 / WeChat |
| Telegram | `tg_bot()`     | Bot 消息           |
| 邮件       | `send_email()` | SMTP 协议          |
| Bark     | `bark()`       | iOS 通知           |
| NTFY     | `ntfy()`       | 开源推送服务           |
| PushPlus | `pushplus()`   | 微信推送平台           |

---

### 8. 国际化模块 (`i18n.py`)

**职责**: 基于 gettext 的多语言支持系统，自动翻译 `src/` 目录下的 print 输出。

**实现机制**:

- `translated_print` 包装 `builtins.print`，自动翻译调用者来自 `src/` 包的输出
- 支持源码运行和 PyInstaller 打包两种路径检测（`_internal/i18n` vs `i18n/`）
- 默认语言：简体中文（zh_CN）

**翻译文件**:

| 文件                                | 说明           | 条目数 |
| --------------------------------- | ------------ | --- |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` | 中文翻译源文件（可编辑） | 200 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | 编译后的二进制翻译文件  | 200 |
| `i18n/en/LC_MESSAGES/`            | 英文翻译目录（预留）   | —   |

**翻译覆盖范围**:

- `src/spider.py` — 各平台直播数据获取消息（37 条）
- `src/room.py` — 直播间信息解析异常消息（2 条）
- `src/utils.py` — 配置文件读写、磁盘空间消息（7 条）
- `main.py` — 主程序通用消息（83 条，预留）
- `gui.py` — GUI 界面消息（70 条，预留）

---

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

---

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
- **SSL 验证**: 由全局配置 `src/http_config.py` 统一控制，默认启用
- **连接池清理**: 进程退出时通过 atexit / 信号处理器释放所有复用的 AsyncClient
- **`get_response_status()` m3u8 容错**（2026-08-01）: HEAD 校验失败时，若 URL 以 `.m3u8` 结尾则补一次 `Range: bytes=0-0` GET 轻量探测（返回 200/206 即判可达）；非 m3u8 源（FLV/record_url）行为不变。异常日志带上下文描述，避免 `str(e)` 为空时只输出空消息

**被以下模块导入**:

- `src/spider.py` - `async_req()`
- `src/stream.py` - `get_response_status()`

---

### 11. HTTP 客户端配置 (`src/http_config.py`)

**职责**: 提供 HTTP 客户端共享运行时配置

**功能**:

- SSL 证书验证全局开关（`ssl_verify`），默认启用（True，安全优先）
- 提供 `set_ssl_verify()` 函数，由主配置在启动时统一设置
- 异步 / 同步 HTTP 客户端在发起请求时读取此配置

---

### 12. 同步 HTTP 客户端 (`src/sync_http.py`)

**职责**: 封装 requests 和 urllib，提供同步 HTTP 接口

**功能**:

- 代理支持
- 超时设置
- Cookie 支持
- 重定向跟踪
- **SSL 验证**: 由全局配置 `src/http_config.py` 统一控制
- **Opener 预构建**: 按 SSL 验证开关预构建 insecure / secure 两个 opener，避免运行时重复构建

---

### 13. Web 管理面板 (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`)

**职责**: 提供 Web 界面远程管理录制器，包括仪表盘、直播间管理、配置编辑、日志查看

**架构**:

- `web.py` - 入口：守护线程运行 `main.main()`，主线程运行 uvicorn；支持后台隐藏运行模式
- `src/web_api.py` - FastAPI 应用：认证（Token）、REST API 路由、SSE 推送、静态资源挂载
- `src/web_config.py` - 配置读写（不依赖 FastAPI，便于单测）
- `web/` - 前端静态资源（单页应用）

**后台运行模式** (`web_show_console = false`):

- `_enter_background_mode()` 在启动录制引擎前调用
- Windows 下通过 `ctypes` 调用 `GetConsoleWindow()` + `ShowWindow(hwnd, SW_HIDE)` 隐藏控制台窗口
- stdout/stderr 重定向到 `logs/web_console.log`（行缓冲，实时写入）
- 程序完全后台运行，通过 Web 面板管理
- 恢复控制台：设置 `web_show_console = true` 后重启

**API 路由**:

| 路由                  | 方法         | 功能                       |
| ------------------- | ---------- | ------------------------ |
| `/api/login`        | POST       | 密码登录，返回 Token            |
| `/api/status`       | GET        | 获取录制状态（含 actual_quality） |
| `/api/rooms`        | GET/POST   | 直播间列表查询 / 新增             |
| `/api/rooms/{url}`  | PUT/DELETE | 编辑 / 删除直播间               |
| `/api/rooms/toggle` | POST       | 启用 / 禁用直播间               |
| `/api/config`       | GET/PUT    | 读取 / 修改配置                |
| `/api/logs/stream`  | GET        | SSE 实时日志推送               |

**前端功能** (`web/`):

- `index.html` - 单页应用入口（仪表盘 / 直播间 / 配置 三个视图）
- `app.js` - 前端逻辑（Token 认证、API 调用、SSE 日志流、状态渲染）
- `style.css` - 样式表（明暗主题、响应式布局、降级高亮）

**录制表格展示**:

- 名称 / 设置画质 / 实际画质 / 开始时间 / 已录时长
- 实际画质与设置画质不一致时标红显示（`.quality-down` 样式）

**安全机制**:

- 密码变更后自动吊销所有现有 Token，强制重新登录
- 监听 `0.0.0.0` 且未启用认证时输出安全告警
- 文件下载路径校验（`_is_within` 防目录穿越）
- 敏感配置项（Cookie / 账号密码 / web_password）API 返回时脱敏为 `***`

---

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

---

## 依赖关系

### Python 依赖 (`requirements.txt`，与 `pyproject.toml [project.dependencies]` 保持一致)

| 包名                | 版本要求      | 用途                                                |
| ----------------- | --------- | ------------------------------------------------- |
| requests          | >=2.34.2  | 同步 HTTP 请求                                        |
| httpx[http2]      | >=0.28.1  | 异步 HTTP 客户端（含 HTTP/2）                             |
| loguru            | >=0.7.3   | 结构化日志                                             |
| pycryptodome      | >=3.23.0  | 加密算法（SM3、RC4、AES）                                 |
| distro            | >=1.9.0   | Linux 发行版检测                                       |
| tqdm              | >=4.69.0  | 进度条                                               |
| exejs             | >=1.0.1   | JavaScript 执行引擎（PyExecJS 的活跃维护继任者，优先使用）           |
| PyExecJS          | >=1.5.1   | JS 执行引擎回退兼容（exejs 未安装时使用）                         |
| customtkinter     | >=6.0.0   | 现代化 GUI 框架                                        |
| pystray           | >=0.19.5  | 系统托盘（GUI / Web 托盘模式）                              |
| Pillow            | >=12.3.0  | 图像处理（托盘图标生成）                                      |
| fastapi           | >=0.140.0 | Web 管理面板后端框架                                      |
| starlette         | >=0.49.1  | ASGI 工具集（fastapi 传递依赖，`src/web_api.py` 直接导入故显式声明） |
| uvicorn[standard] | >=0.51.0  | ASGI 服务器                                          |
| python-multipart  | >=0.0.32  | 表单/文件上传解析                                         |
| pydantic          | >=2.13.4  | 请求模型校验                                            |

> 注 1：Weverse 平台认证由 `src/weverse_auth.py` 通过 requests 直接调用 API 实现，
>
> **不再依赖** pip 上的 `weverse` 包（该包拉入已废弃的 pycrypto，Python 3.10+ 无法编译）。
>
> 注 2：可执行文件打包需 PyInstaller，属于构建期可选依赖：`pip install .[build]`
>
> （对应 `pyproject.toml` 的 `[project.optional-dependencies] build`）。

### 外部依赖

| 依赖      | 用途                 | 安装方式                                                        |
| ------- | ------------------ | ----------------------------------------------------------- |
| FFmpeg  | 视频录制与转码            | Windows 内置（`ffmpeg/`），Linux/macOS 手动安装；Docker 内 apt 安装      |
| Node.js | 运行 JavaScript 签名算法 | Windows 自动安装（`node/`），Linux 需包管理器安装；Docker 内 apt 安装 Node 22 |

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
├── src/http_config.py
├── src/async_http.py
├── src/utils.py
│   └── src/logger.py
├── msg_push.py
└── src/ffmpeg_install.py

web.py
├── src/web_api.py
│   ├── src/web_config.py
│   └── main.py (get_status 等函数)
└── web/ (静态资源)
```

---

## 配置文件说明

### 主配置文件 (`config/config.ini`)

#### [录制设置] 节

| 配置项            | 说明                                  | 默认值                 |    |    |      |    |
| -------------- | ----------------------------------- | ------------------- | -- | -- | ---- | -- |
| language       | 界面语言                                | zh_cn               |    |    |      |    |
| 是否跳过代理检测       | 是否跳过代理检测                            | 是                   |    |    |      |    |
| 是否禁用SSL证书验证    | 是否禁用 SSL 证书验证                       | 否                   |    |    |      |    |
| 是否启用日志文件       | 是否将日志写入文件                           | 是                   |    |    |      |    |
| 直播保存路径         | 录制文件保存路径                            | (空，默认当前目录)          |    |    |      |    |
| 保存文件夹是否以作者区分   | 是否按主播名分类                            | 是                   |    |    |      |    |
| 视频保存格式         | ts/mkv/flv/mp4/mp3/m4a              | ts                  |    |    |      |    |
| 原画             | 超清                                  | 高清                  | 标清 | 流畅 | 默认画质 | 原画 |
| 是否使用代理ip       | 是否启用代理                              | 否                   |    |    |      |    |
| 代理地址           | 代理服务器地址                             | (空)                 |    |    |      |    |
| 同一时间访问网络的线程数   | 并发数                                 | 3                   |    |    |      |    |
| 循环时间(秒)        | 直播状态检测间隔                            | 300                 |    |    |      |    |
| 分段录制是否开启       | 是否分段                                | 是                   |    |    |      |    |
| 是否启用HLS采集(是/否) | 是否优先使用 HLS(m3u8) 源采集；关闭或源不可用时回退 FLV | 是                   |    |    |      |    |
| 视频分段时间(秒)      | 分段时长                                | 3600                |    |    |      |    |
| 使用代理录制的平台      | 需要代理的平台列表                           | tiktok, sooplive... |    |    |      |    |

#### [推送配置] 节

| 配置项             | 说明                 |    |    |    |      |      |          |
| --------------- | ------------------ | -- | -- | -- | ---- | ---- | -------- |
| 直播状态推送渠道        | 微信                 | 钉钉 | tg | 邮箱 | bark | ntfy | pushplus |
| 钉钉推送接口链接        | 钉钉 Webhook         |    |    |    |      |      |          |
| 微信推送接口链接        | Server酱 URL        |    |    |    |      |      |          |
| bark推送接口链接      | Bark API           |    |    |    |      |      |          |
| tgapi令牌         | Telegram Bot Token |    |    |    |      |      |          |
| tg聊天id          | 聊天 ID              |    |    |    |      |      |          |
| smtp邮件服务器       | SMTP 服务器           |    |    |    |      |      |          |
| ntfy推送地址        | NTFY 服务地址          |    |    |    |      |      |          |
| pushplus推送token | PushPlus Token     |    |    |    |      |      |          |
| 只推送通知不录制        | 是否仅通知不录制           |    |    |    |      |      |          |

#### [Cookie] 节

各平台的 Cookie 配置（录制部分平台必填）

#### [Authorization] 节

特殊平台的 Token 配置

#### [账号密码] 节

部分平台的账号密码配置

#### [Web] 节

Web 管理面板配置（`web.py` 模式专用）

| 配置项              | 说明                                    | 默认值       |
| ---------------- | ------------------------------------- | --------- |
| web_host         | 监听地址（Docker 内需设为 0.0.0.0）             | 127.0.0.1 |
| web_port         | 监听端口                                  | 8000      |
| web_auth_enable  | 是否启用密码认证                              | false     |
| web_password     | 登录密码（认证开启时必填，PBKDF2-HMAC-SHA256 哈希存储） | (空)       |
| web_token_expiry | Token 有效期（秒）                          | 86400     |
| web_show_console | 是否显示控制台窗口（false 时后台隐藏运行）              | true      |

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

---

## 运行方式

### 方式 1: 源码运行

#### 前置要求

- Python 3.10+
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

---

### 方式 2: Docker 运行

#### Dockerfile 多阶段构建说明（基础镜像 `python:3.13-slim-bookworm`）

```dockerfile
# 阶段 1: builder
# - 仅安装 build-essential（编译无二进制轮子的依赖）
# - 创建 Python 虚拟环境 /opt/venv 并安装 requirements.txt
#   （Node.js 只在运行时需要，builder 阶段不安装）

# 阶段 2: runtime
# - 精简基础镜像 + apt 安装 ffmpeg / nodejs(22 LTS) / tzdata / procps
# - 从 builder 复制 /opt/venv 虚拟环境
# - 非 root 用户 recorder(uid=1000) 运行
# - HEALTHCHECK 兼容 main.py 与 web.py 两种模式（pgrep）
# - ENTRYPOINT ["python", "main.py"]，EXPOSE 8000（Web 模式用）
```

**`.dockerignore` 要点**：

- 排除平台二进制（`ffmpeg/`、`node/`，容器内 apt 安装）、`config/*.ini`（运行时挂载）、

  `typings/`、`build_exe.py`、`gui_legacy.py` 等桌面/构建专用文件；
- **保留 `i18n/**/*.mo`** 编译翻译文件 —— gettext 运行时必需且 Dockerfile 不会重新编译，

  仅排除 `.po` 源文件与编译脚本。

#### 使用 docker compose (推荐)

仓库根目录的 `docker-compose.yaml` 已定义三个服务（共享同一镜像，通过 YAML 锚点复用配置）：

| 服务             | 入口               | 启动命令                                 | 端口          |
| -------------- | ---------------- | ------------------------------------ | ----------- |
| `recorder`（默认） | `python main.py` | `docker compose up -d`               | 无（纯 CLI）    |
| `web`（profile） | `python web.py`  | `docker compose --profile web up -d` | `8000:8000` |
| `gui`（profile） | `python gui.py`  | `docker compose --profile gui up -d` | 无（需 X11）    |

统一挂载卷：`./config`、`./downloads`、`./logs`、`./backup_config`。

> ⚠️ **Web 模式必读**：`web.py` 默认监听 `127.0.0.1:8000`，容器内必须在
>
> `config/config.ini` 的 `[Web]` 节设置 `web_host = 0.0.0.0`，宿主机端口映射才能访问；
>
> 同时强烈建议开启 `web_auth_enable = true` 并配置密码。

---

## 打包与发布

本项目提供一键式可执行文件打包（`build_exe.py`）与跨平台自动构建发布（`GitHub Actions`），将 **CLI / GUI / Web 三个入口**统一构建为可分发的发布目录。

### 1. 打包脚本 `build_exe.py`

PyInstaller `onedir` 模式 + `contents_directory='_internal'`，动态生成 `.spec` 文件后调用 PyInstaller 完成**三入口共享依赖**构建：

| 产物（exe 同级）                     | 入口        | 模式                              |
| ------------------------------ | --------- | ------------------------------- |
| `DouyinLiveRecorder(.exe)`     | `main.py` | 控制台（CLI 录制核心）                   |
| `DouyinLiveRecorder-GUI(.exe)` | `gui.py`  | 无控制台窗口（GUI）                     |
| `DouyinLiveRecorder-Web(.exe)` | `web.py`  | 控制台（Web 管理面板，监听 `0.0.0.0:8000`） |

三个入口共用一个 `COLLECT`，依赖去重后体积约为独立打包的 1/3。

**用法**：

```bash
python build_exe.py            # 打包并生成 zip 产物
python build_exe.py --smoke    # 打包后额外运行冒烟测试（CI 推荐）
python build_exe.py --no-zip   # 仅打包不压缩
```

**数据文件与隐藏导入**：

- `datas`：`src/javascript`（JS 签名脚本）、`i18n`（翻译）、`web`（前端静态资源），均经 `__file__` 定位，PyInstaller 自动收进 `_internal/`；`collect_data_files('customtkinter')`（主题 JSON）。
- `config/` 不进 `_internal`，由 `copy_external_binaries()` 复制到 exe 同级（见目录规范）。
- `hiddenimports`：`i18n`、`src.async_http`（main.py 经 `__import__` 动态导入）、`h2`（httpx[http2] 懒加载）；`a_web` 额外 `collect_submodules('uvicorn')`（协议模块按字符串导入）。
- `excludes`：CLI 排除 GUI/Web 库（tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette）；GUI 排除 Web 库；Web 排除 GUI 库。

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
    ├── (Crypto/ PIL/ certifi/ h2/ pydantic/ customtkinter/ watchfiles/ websockets/ yaml/ + 运行库 .dll)
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
- **中文 UTF-8 编码（关键修复）**：冻结后子进程 stdout 为管道，Python 回退到 GBK 写输出，而 GUI 以 UTF-8 读取管道 → 中文乱码（如 `自动获取 Cookie ttwid 成功` 变成乱码）。在 `main.py`/`gui.py`/`web.py` 顶部加入 `_fix_encoding()`：Windows 下 `sys.stdout/stderr.reconfigure(encoding='utf-8', errors='replace')` + `ctypes.windll.kernel32.SetConsoleOutputCP(65001)/SetConsoleCP(65001)`；非 Windows 仅 reconfigure。stream 加 `None`/`hasattr` 保护（windowed exe 的 stdout 可能为 `None`）。`web.py` 原有 `reconfigure(errors='replace')` 升级为同时设 `encoding='utf-8'`。

### 5. 冒烟测试

`build_exe.py --smoke` 在打包后自动运行三项验证（CI 推荐开启）：

- **CLI**：启动数秒，确认进入监控循环且输出无 `Traceback`/`ImportError`/`ModuleNotFoundError`。
- **Web**：HTTP 探活 `http://127.0.0.1:8000/`，返回 200 视为面板可用；同时验证内置 ffmpeg 被命中（不触发下载）。
- **GUI**：启动 8 秒确认进程存活无崩溃（无显示环境 `DISPLAY` 未设置时自动跳过）。

冒烟前会向 exe 级 `config/URL_config.ini` 写入一条注释 URL，避免 CLI 因 URL 列表为空而阻塞在 `input()`。

### 6. GitHub Actions 自动构建与发布

工作流文件：`.github/workflows/build-release.yml`（任务名 `Build Executables`）。

**触发方式**：

- 手动触发（`workflow_dispatch`）：三平台构建并上传 artifact。
- 推送 `v*` 标签（如 `v4.0.8`）：构建 + 自动创建 GitHub Release 并附三平台 zip。

**构建矩阵**：`windows-latest` / `ubuntu-latest` / `macos-latest`，Python 3.12。

**流程**：

1. Checkout → Setup Python 3.12（pip 缓存）。
2. 安装 ffmpeg（Linux/macOS 用系统包；Windows 用仓库内置）；Linux 额外装 `xvfb`（GUI 冒烟需虚拟显示）。
3. `pip install -r requirements.txt pyinstaller`。
4. `python build_exe.py --smoke`（Linux 用 `xvfb-run -a` 包裹）。
5. 上传 `dist/*.zip` artifact。
6. `release` job（仅 tag 触发）：下载全部 artifact，用 `softprops/action-gh-release@v2` 创建 Release 并附 zip，`generate_release_notes: true`。

**产物命名**：`DouyinLiveRecorder-v{version}-{os}-{arch}.zip`（如 `DouyinLiveRecorder-v4.0.7-windows-amd64.zip`，约 118 MB）。

### 7. 本地打包步骤

```bash
pip install pyinstaller          # 安装打包器
python build_exe.py --smoke      # 打包 + 冒烟测试
# 产物：dist/DouyinLiveRecorder/ 发布目录 + dist/DouyinLiveRecorder-vX.Y.Z-*.zip
```

注意：本仓库为本地副本，工作流需推送至 GitHub 仓库后才可运行。CI Linux/macOS 产物不含 `ffmpeg`/`node`，首次运行会自动下载。

---

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

---

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
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
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

---

## 贡献指南

### 代码规范

- 格式化: `black .`
- 导入排序: `isort .`
- 类型检查: `mypy src/`（已启用 `disallow_untyped_defs = true`，`--strict` 模式全通过）

### 添加新平台支持

1. 在 `src/spider.py` 中添加平台数据获取函数
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑
4. 更新 `README.md` 和本文档

---

## 更新日志

### v4.0.8.1-dev (2026-08-01) — mypy 严格模式全通过与类型注解收紧

**变更内容：**

- `pyproject.toml`：`disallow_untyped_defs` 从 `false` 改为 `true`，要求所有函数必须有完整类型注解
- `mypy src/ --strict` 从 61 errors 降至 0 errors（16 个源文件全通过）

**类型注解修复（9 个文件）：**

- `src/ab_sign.py`：`SM3.__init__`、`_fill` 添加 `-> None` 返回类型
- `i18n.py`：`init_gettext` 添加 `-> Callable[[str], str]` 返回类型
- `src/proxy.py`：`ProxyInfo.__post_init__`、`ProxyDetector.__init__`、`__del__` 添加 `-> None`
- `src/utils.py`、`src/room.py`、`src/spider.py`：移除未使用的 `type: ignore[no-redef]` 注释
- `src/web_config.py`：移除冗余 `cast("list[str]", parser.sections())`
- `src/spider.py`（最多修复）：为 20+ 函数添加参数/返回类型注解，修复泛型参数缺失（`dict` → `dict[str, object]`、`tuple` → 具体元组类型）、冗余 cast、内部函数类型不匹配
- `main.py`：`_fix_encoding` 添加 `-> None`
- `src/web_api.py`：所有 FastAPI 路由处理器添加返回类型注解（`dict[str, object]`、`StreamingResponse`、`FileResponse` 等）

**验证：** `mypy src/ --strict` 0 errors；`mypy src/` 0 errors；`pytest` 178 passed；`black` 格式化通过。

---

### v4.0.8.1-dev (2026-08-01) — 版本号收敛至 pyproject.toml 单一事实源

**变更内容：**

- `pyproject.toml` 成为版本号唯一权威来源（Single Source of Truth）
- `main.py`：移除硬编码 `version: str = "v4.0.8.1"`，改为 `_read_version_from_pyproject()` 动态读取（优先 `importlib.metadata`，回退直接解析 `pyproject.toml`）
- `build_exe.py`：`read_version()` 改为从 `pyproject.toml` 解析版本号
- `scripts/check_version.py`：基准源从 `main.py` 切换为 `pyproject.toml`，新增检测 `main.py` 是否仍存在硬编码版本号
- CI `version-check` job 无需修改，仍调用 `python scripts/check_version.py`

**版本更新流程（新）：** 只需修改 `pyproject.toml` 中的 `version` 字段，然后同步 `Dockerfile`、`README.md`、`CODE_WIKI.md`、`i18n/zh_CN.po`；`main.py` 无需手动修改。

### v4.0.8.1-dev (2026-08-01) — 核心模块单元测试补全与覆盖率门槛调整

**新增测试文件：**

- `tests/test_stream.py`（约 500 行）：覆盖 `src/stream.py` 核心数据流路径
  - 纯工具函数：`bitrate_to_quality`、`code_to_zh`、`is_downgrade`、`_pad_list`、`get_quality_index`
  - 常量一致性校验：`QUALITY_MAPPING` / `QUALITY_LEVEL` / `QUALITY_MAPPING_BIT` / `QUALITY_CODE_TO_ZH` 键集对齐
  - 平台流解析（异步 Mock）：抖音（离线/在线/仅FLV/降级）、TikTok（离线/在线）、快手（离线/在线/带码率）、YY、网易CC、通用入口（m3u8/flv/all 三种 url_type）
- `tests/test_async_http.py`（约 440 行）：覆盖 `src/async_http.py` 核心请求路径
  - `_get_client`：缓存复用、不同参数隔离、失效 client 替换
  - `_close_all_clients` / `close_all_clients_sync`：连接池清理
  - `async_req`：GET/POST（dict/str/bytes 数据）、redirect_url、return_cookies、include_cookies、异常回退、verify 默认值
  - `get_response_status`：200/404、m3u8 HEAD 405 降级 Range GET、异常处理、非 m3u8 不探测

**覆盖率变化：**

| 模块                  | 修改前    | 修改后    |
| ------------------- | ------ | ------ |
| `src/stream.py`     | 0%     | 70%    |
| `src/async_http.py` | 35%    | 83%    |
| 总覆盖率                | 15.29% | 22.35% |

**覆盖率门槛调整：**

- `pyproject.toml` `[tool.coverage.report] fail_under`：15 → 20（反映当前实际覆盖水平，为后续增量保留空间）

**验证：** `pytest --cov=src/ --cov-report=term-missing` — 178 passed，覆盖率门槛 20% 达标。

---

### v4.0.8.1-dev (2026-08-01) — 抖音 URL 全格式支持、格式5 链路优化、HLS 校验与日志修复

**抖音 URL 解析（支持 5 种格式，含本次全部修复）：**

- 分发逻辑重构（`spider.py: get_douyin_app_stream_data`）：`live.douyin.com/*` 直调网页端；`www.douyin.com/user/<sec_uid>` 跳过必然失败的 `get_sec_user_id` 探测、走 `resolve_from_homepage()`；`v.douyin.com` 短链先探测、抛 `UnsupportedUrlError` 再回退主页路径
- 主页解析改用 `iesdouyin.com/web/api/v2/user/info/` JSON 接口（取 `unique_id`，空则退 `short_id`），替代已变 JS 反爬壳页的 `share/user/` HTML；新增 `room.DESKTOP_UA` 桌面 UA（旧移动端 UA 被静默限流：HTTP 200 + 空 body）
- `room.py` 新增 `is_user_homepage_url()` + 零请求快速路径：网页端主页的 sec_user_id 直接从 URL 路径提取，省去一次约 71KB 的跟随重定向下载
- **修复隐藏 bug**：旧回退调用 `get_douyin_stream_data("live.douyin.com/"+unique_id)` 未透传 proxy_addr/cookies，导致代理与 Cookie 配置在主页路径静默失效；现由 `resolve_from_homepage()` 显式透传
- 删除死代码 `get_douyin_stream_data()`（约 94 行，重构后已无调用点）
- 新增 sec_uid→抖音号进程级缓存（`room.py`，`threading.Lock` 跨线程/跨 asyncio 循环去重，30 分钟 TTL）：主页解析后每轮轮询不再重请求 iesdouyin 接口
- 格式5 实测链路优化：请求数 4→3、下载量 ~1.3MB→~1.2MB、耗时 ~1.7s→~1.4s；剩余 ~1.1MB HTML 为取原画 HEVC 流（`stream.py: extract_douyin_hevc_flv_url`）的通用行为，不可删除

**HLS 校验与日志修复：**

- `async_http.py get_response_status()`：空消息日志修复（`logger.debug(e)` 在 `e` 为空串时只剩 `- `，改为带上下文描述）；HEAD 失败时对 `.m3u8` 源补 `Range: bytes=0-0` GET 探测
- `main.py _validate_stream_url()`：content-type 判定补 `mpegurl`；HEAD 被拒时对 `.m3u8` 补 Range GET 探测——修复抖音 CDN m3u8 对 HEAD 返回 4xx 被误判不可达、总回退 FLV 的问题
- `spider.py web/enter` API 调用封装 `_try_web_api()` + 静默重试 1 次（`asyncio.sleep(0.5)` 缓冲）：瞬时 `status_code=10002` 不再刷 WARNING，重试成功即跳过 HTML 兜底（省约 1MB 下载），两次都失败才回退

**测试与静态检查：**

- `tests/test_douyin_url_resolution.py` 扩至 17 个用例（5 种 URL 格式分发、缓存命中、10002 重试、web_rid 处理等）；新增 autouse fixture 清理 sec_uid 缓存防跨用例污染
- 全量 `pytest` 78 passed；`black`/`isort` 全绿；`mypy src/` 无问题；ruff 仅剩有意的 E402（项目既定晚导入模式）
- 顺手修复：`tests/test_utils.py` 未用导入（F401）、`src/stream.py` 歧义变量名 `l`（E741，改为 `level, ratio`）

---

- 全项目版本号统一升级至 `4.0.8.1`（main.py / pyproject.toml / Dockerfile / i18n / README / CODE_WIKI）

---

### v4.0.8.1-dev (2026-07-29) — 工程配置文件全面梳理与文档同步

**工程配置文件（六文件 + 双文档同步）：**

- `.gitignore`：修复三处自相矛盾——移除 `i18n/**/*.mo` 忽略（.mo 随仓库分发，gettext 运行时必需）；`*.vbs` 后加 `!StopRecording.vbs` 例外；不再忽略 CODE_WIKI.md。新增忽略 `.workbuddy/`、`.codebuddy/`、`.trae/`
- `.dockerignore`：重写。保留 `i18n/**/*.mo`（Dockerfile 不会重新编译，旧规则导致容器内翻译失效）；仅排除 `.po` 源与编译脚本。新增排除 typings/、build_exe.py、gui_legacy.py、AI 工具目录
- `Dockerfile`：builder 阶段移除无用的 Node.js 安装（Node 仅运行时需要，阶段2已装 Node 22）；EXPOSE 处补充 web_host=0.0.0.0 说明
- `docker-compose.yaml`：重构为三服务——recorder（默认，main.py，无端口）、web（profile，8000:8000）、gui（profile）。修复原设计中 recorder 占用 8000 端口的问题
- `pyproject.toml`：+`starlette>=0.49.1`（web_api.py 直接导入）；+`[project.optional-dependencies] build = ["pyinstaller>=6.10.0"]`；+`py-modules`（修复 project.scripts 入口缺模块）；移除无效的 i18n package-data
- `requirements.txt`：同步 starlette>=0.49.1 与 PyInstaller 构建期说明

**代码结构清理（对齐 git 工作区状态）：**

- 移除 `src/http_clients/` 子包（`__init__.py` / `async_http.py` / `config.py` / `sync_http.py`），HTTP 客户端统一由 `src/` 根模块提供（`async_http.py` / `sync_http.py` / `http_config.py`），`pyproject.toml` 的 `packages` 相应收窄为 `["src"]`
- 移除 `src/initializer.py` 与 `TRAE_AGENT_CODE_WIKI.md`（不再维护）

**文档同步：**

- `CODE_WIKI.md`：依赖表全面更新（移除 weverse，补 exejs/customtkinter/starlette/python-multipart）；Docker 章节改为描述实际 compose 三服务；目录结构树修正
- `README.md`：Docker 用法改为 `docker compose --profile web/gui`；补 web_host=0.0.0.0 警告；项目结构树同步；Markdown 格式统一（清理 13 处孤立 `</div>` 标签 + 规范章节空行，798→770 行）

---

### v4.0.8.1-dev (2026-07-28) — 修复 macOS CI smoke:gui 崩溃

- `gui.py`：macOS 改为 `tray.run_detached()`（非阻塞）+ 主线程 `root.mainloop()`，修复 Tcl/Tk 只能运行于主线程导致的 `RuntimeError: Calling Tcl from different apartment`
- `SystemTray` 拆出 `_build_icon()/_degrade()`；新增 `run_detached()`：主线程 `_assert_image()` 预热 PNG 编码后设置 `icon._icon_valid = True`，避免 setup 线程重回后台线程 PNG 编码的原生崩溃路径
- 修复隐藏 bug：旧 `run()` 在所有平台调用 darwin 专有的 `_assert_image()`，Windows/Linux 上抛 AttributeError 被吞导致托盘静默禁用
- `stop()`：darwin detached 模式先 `icon.visible = False` 再 `icon.stop()`

---

### v4.0.8.1-dev (2026-07-27) — ttwid 共享模块抽取与冒烟测试进程树清理

**ttwid 共享模块（`src/ttwid.py`）：**

- 新建 `src/ttwid.py`：进程级唯一 `_cached_ttwid` + `threading.Lock` 跨线程/跨事件循环去重，导出 `async def get_ttwid(proxy_addr)` 与 `def warmup_ttwid(proxy_addr)`
- `src/spider.py` / `src/room.py`：删除各自本地 ttwid 实现，统一委托给 `src/ttwid.py`
- `main.py`：`main()` 循环中用 `first_run` 门控调用 `warmup_ttwid(proxy_addr)`，保证整个进程 ttwid 仅获取一次
- `src/ttwid.py`：支持从 config.ini `[Cookie]` 段读取用户配置的 ttwid，获取优先级 = 缓存 > 配置 > 自动获取

**build_exe.py 冒烟测试进程树清理：**

- `_launch()` 让子进程自成进程组/会话（Windows `CREATE_NEW_PROCESS_GROUP`，Unix `start_new_session`）
- 新增 `_kill_tree(proc)`：Windows `taskkill /T /F /PID`，Unix `os.killpg(getpgid(pid), SIGKILL)`，消除 GitHub Actions runner 孤儿进程清理噪声

---

### v4.0.8.1-dev (2026-07-26) — basedpyright 全项目清零与 docstring 注释转换

**basedpyright 全项目 0/0/0（typings + src）：**

- `typings/execjs/`（6 个 .pyi）：文件级 pyright 指令放宽动态 JSON 相关严格检查（reportAny/reportExplicitAny/reportMissingParameterType 等）
- `typings/pystray/__init__.pyi`：reportAny/reportExplicitAny 放宽
- `src/spider.py`：文件级指令放宽 16 项规则（787 条告警→ 0，几乎全部来自 json.loads 返回 Any 级联）
- `src/room.py`：新增 execjs 存根、handle_proxy_addr 类型标注、cast 收窄、显式字符串拼接
- `src/sync_http.py`：OptionalDict 类型参数化、urllib cast、弃用 API 替换
- `src/async_http.py`：未使用参数/协程结果消解、data 类型补全、异常回退 cast

**docstring → # 注释转换：**

- 全项目 18 处三引号 docstring 转换为 `#` 行注释：build_exe.py(10)、main.py(3)、src/ab_sign.py(2)、src/logger.py(1)、src/web_tray.py(1)、i18n.py(1)

---

### v4.0.8.1-dev (2026-07-25) — 全量代码审查修复与安全加固

**关键 Bug 修复：**

- `main.py`：音频/视频分支 `if` → `elif` 互斥，修复同一直播间双重录制 + ffmpeg 命令畸形
- `src/stream.py`：`QUALITY_MAPPING` 改为与抖音 order 字典对齐的位置索引 `{OD:0,BD:1,UHD:2,HD:3,SD:4,LD:5}`，修复画质选错
- `src/proxy.py`：多协议代理 `http=1.2.3.4:5678` 解析先剥离协议前缀，修复 ValueError
- `main.py`：FLV 直下分支写入 recording/recording_time_list 包进 `record_state_lock`（数据竞争）
- `main.py`：`check_subprocess` 补 `process.wait(timeout=30)`（僵尸进程）

**安全加固：**

- `src/web_config.py` + `src/web_api.py`：web_password 改为 PBKDF2-HMAC-SHA256 存储，登录时历史明文自动升级为哈希
- `src/http_config.py`：`ssl_verify` 默认改为 `True`（安全优先）
- `msg_push.py`：PushPlus token 日志脱敏（`_mask_secret`，仅留前后各 2 位）
- `src/node_install.py`：`unzip_file` 增加 Zip Slip 防护

**其他修复：**

- `src/async_http.py`：失效 client 先 `aclose()` 再重建，修复连接池泄漏
- `web.py`：退出时主动 `cleanup_all_ffmpeg_processes()` + `close_all_clients_sync()`，杠绝孤儿 ffmpeg
- `gui.py`：新增 `self._stopping` 标志 + 停止期间禁用启动按钮，消除停止竞态窗口
- `src/ab_sign.py`：修复 SM3 GG 函数 bug（j>=16 时错误使用 ff_j 公式）
- `i18n.py`：翻译覆盖从仅 `src/` 扩展到项目根下所有源文件（main.py/web.py/gui.py/msg_push.py）

---

### v4.0.8-dev (2026-07-28) — 多直播间并发监控风控修复与静态检查清零

**抖音多直播间并发监控触发风控修复：**

- `src/spider.py`：`_ensure_ttwid()` 委托给共享 `src/ttwid.py` 模块（带 `threading.Lock` 跨线程去重），解决多线程并发时重复拉取 ttwid 触发风控的问题
- `src/room.py`：`_ensure_douyin_ttwid()` 同样委托给共享 `ttwid.py` 模块，统一 ttwid 获取入口
- `main.py`：新增 `_douyin_rate_limit()` 速率限制器，保证两次抖音 API 请求之间至少间隔 3 秒（`douyin_min_interval`），避免多线程背靠背连续请求触发抖音风控（返回空响应）
- `main.py`：新增全局变量 `douyin_rate_lock`、`douyin_last_request_time`、`douyin_min_interval` 用于速率控制

**静态检查清零（Pyright 0 errors, 0 warnings）：**

- `gui.py`：`Image.LANCZOS` → `Image.Resampling.LANCZOS`（Pillow 10+ 现代 API，修复 `reportAttributeAccessIssue`）
- `gui.py`：为 pystray 私有属性访问添加 `# type: ignore[attr-defined]`（`_assert_image()`、`_icon_valid`、`run_detached()`）
- `main.py`：`select_source_url()` 中 `_validate_stream_url(m3u8_url)` 添加 `cast(str, m3u8_url)`，修复 `reportArgumentType` 类型收窄问题

**验证：** `python -m pyright main.py web.py msg_push.py gui.py build_exe.py` 输出 `0 errors, 0 warnings, 0 informations`。

---

### v4.0.8-dev (2026-07-25) — 新增 PyInstaller 可执行文件打包与 GitHub Actions 发布

- 新增 `build_exe.py`：PyInstaller `onedir` + `contents_directory='_internal'`，动态生成 `.spec`，将 `main.py`/`gui.py`/`web.py` 三入口共享依赖构建为 `DouyinLiveRecorder(.exe)` / `-GUI(.exe)` / `-Web(.exe)`，并统一压缩为 `DouyinLiveRecorder-v{version}-{os}-{arch}.zip`（约 118 MB）
- 目录规范：`node/`、`ffmpeg/`、`config/` 与 exe 保持同级；`src/` 及全部 Python 依赖包统一收进 `_internal/`；运行时 `logs/`、`downloads/`（未通过 config.ini 指定时）、`backup_config/` 默认创建在 exe 同级
- 新增路径收敛函数 `src/logger._app_root()`（与 `main.py` 内联同名），冻结时返回 `dirname(sys.executable)`（exe 同级），使 `main.py`/`src/__init__.py`/`src/node_install.py`/`src/ffmpeg_install.py` 的运行时资源与 `src/logger.py` 的 logs 正确收敛
- `gui.py` 冻结适配：冻结时直接调用同目录 `DouyinLiveRecorder.exe` 拉起录制核心（避免 `sys.executable` 指向自身导致无限递归）；新增 `self.app_root` 定位 exe 级 config/downloads
- 中文 UTF-8 编码修复：在 `main.py`/`gui.py`/`web.py` 顶部加入 `_fix_encoding()`（Windows 切换控制台代码页 65001 + reconfigure UTF-8），修复冻结后子进程管道 GBK 输出被 GUI 按 UTF-8 读取导致的乱码
- `build_exe.py --smoke` 三项冒烟测试：CLI 存活、Web HTTP 探活 200（并验证内置 ffmpeg 命中）、GUI 存活 8 秒（无 DISPLAY 自动跳过）
- 新增 `.github/workflows/build-release.yml`：三平台 matrix（win/linux/mac，Python 3.12）+ 依赖安装 + 冒烟测试 + artifact 上传；推送 `v*` 标签自动创建 GitHub Release 并附三平台 zip

### v4.0.8-dev (2026-07-25) — 全项目类型错误修复与代码清理

**类型错误修复（Pyright / Pyrefly / basedpyright）：**

- `src/proxy.py`：修复跨平台类型错误——在平台判断前声明 `self.winreg: Any = None` 和 `self.__INTERNET_SETTINGS: Optional[Any] = None`，简化 `__del__` 析构函数用 `try/except` 包裹直接访问，配合 `is not None` 类型收窄
- `gui.py`：`Fonts.get()` 的 `weight` 参数从 `str` 收窄为 `Literal["normal", "bold"]`，匹配 `CTkFont` 签名
- `main.py`：补全模块级变量声明（约 160 个），按功能分组（代理/录制/推送/邮件/Cookie/循环临时变量等），消除 `push_message()`、`start_record()` 等函数中数百个 "Could not find name" 错误
- `main.py`：`get_status()` 重试循环前为 5 个快照变量（`recording_snapshot`、`recording_times`、`monitoring_val`、`running_val`、`error_val`）添加默认值，消除 "possibly unbound" 错误
- `main.py`：补漏 `twitcasting_cookie: str = ""` 模块级声明
- `msg_push.py`：`tg_bot()` 的 `chat_id` 参数从 `int` 放宽为 `str | int`，Telegram API 同时接受数字和字符串 chat ID
- `src/web_config.py`：移除 `str(raw)` 冗余调用（`parser.get()` 返回值始终为 `str`）
- `src/spider.py`：为 `sorted_stream_list` 和 `stream_data` 添加 `list[dict]` / `dict` 显式类型标注，修复 Pyrefly 推断为 `SupportsGetItem` 导致的 3 处 `.get()` 调用错误
- `src/spider.py`：删除 `get_bilibili_stream_data()` 末尾不可达的 `return None`（if/else 双分支均已 return）
- `src/http_config.py`：移除 `bool(value)` 冗余调用（参数已标注为 `bool`）
- `src/async_http.py`：`_get_client()` 重构为 early-return 模式，消除 `client` 可能未绑定错误
- `src/stream.py`：`QUALITY_LEVEL.get(video_quality, 4)` 改为 `QUALITY_LEVEL.get(video_quality or "", 4)`，处理 `str | None` 键类型
- `src/stream.py`：`quality, quality_index = ...` 改为 `_, quality_index = ...`，消除未使用变量提示

**代码清理（pyflakes / 未使用导入与变量）：**

- `src/spider.py`：修复 `get_baidu_stream_data()` 中 `result` 未赋值即引用的 `NameError`（`data_dict` 为空时触发）
- `src/spider.py`：移除未使用导入 `import ssl` 和 `from .ab_sign import ab_sign`
- `src/logger.py`：移除未使用导入 `import os`
- `gui.py`：为 `pystray` 类型标注添加 `TYPE_CHECKING` 守卫（`pystray` 在 `run()` 内延迟导入）
- `main.py`：移除 `start_record()` 中未使用的 `global error_count` 声明
- `main.py`：移除未使用的 `create_var` global 声明
- `main.py`：移除未使用的局部变量 `changed`

**验证：** 所有文件通过 `py_compile` 编译验证，`GetDiagnostics` 全项目返回空数组。

---

### v4.0.8-dev (2026-07-25) — 依赖扫描与 Docker 配置更新

**依赖扫描与 pyproject.toml 更新：**

- `pyproject.toml`：项目版本 `4.0.7` → `4.0.8-dev`，与 CODE_WIKI 更新日志一致
- `pyproject.toml` / `requirements.txt`：新增 `pydantic>=2.0.0` 依赖（`src/web_api.py` 直接 `from pydantic import BaseModel`，之前未声明）
- 全项目依赖扫描完成：14 个第三方包均已核对使用位置并确认声明状态（详见下表）

| 包名                | 声明状态      | 使用位置                                                                              |
| ----------------- | --------- | --------------------------------------------------------------------------------- |
| requests          | 已声明       | src/ffmpeg_install.py, src/node_install.py, src/sync_http.py, src/weverse_auth.py |
| httpx[http2]      | 已声明       | main.py, src/room.py, src/spider.py, src/async_http.py                            |
| loguru            | 已声明       | src/logger.py, msg_push.py                                                        |
| pycryptodome      | 已声明       | src/spider.py (Crypto.Cipher.AES)                                                 |
| distro            | 已声明       | src/node_install.py                                                               |
| tqdm              | 已声明       | src/ffmpeg_install.py, src/node_install.py                                        |
| PyExecJS          | 已声明       | src/room.py, src/spider.py, src/utils.py                                          |
| customtkinter     | 已声明       | gui.py                                                                            |
| pystray           | 已声明       | gui.py, gui_legacy.py (延迟导入)                                                      |
| Pillow            | 已声明       | gui.py, gui_legacy.py                                                             |
| fastapi           | 已声明       | src/web_api.py                                                                    |
| uvicorn[standard] | 已声明       | web.py (延迟导入)                                                                     |
| python-multipart  | 已声明       | FastAPI 表单处理隐式依赖                                                                  |
| **pydantic**      | **缺失→已补** | src/web_api.py (BaseModel)                                                        |

**Dockerfile 更新：**

- Python 基础镜像 `python:3.13.0-slim-bookworm` → `python:3.13-slim-bookworm`（两阶段）— 3.13.0 是 2024 年 10 月初始版本，缺少后续安全补丁；去掉 patch 号自动获取最新
- Node.js `setup_20.x` → `setup_22.x`（两阶段）— Node 20 LTS 于 2026 年 4 月 EOL，Node 22 是当前活跃 LTS
- 安全升级（`apt-get upgrade`）从 builder 阶段移至 runtime 阶段 — builder 是临时阶段，升级无意义；runtime 才是最终镜像，安全升级应在此
- LABEL version `4.0.7` → `4.0.8-dev`

**docker-compose.yaml：** 无需更新，结构已完整（卷挂载、端口映射、环境变量、健康检查、资源限制、日志轮转、GUI profile 均正确）。

---

### v4.0.8-dev (2026-07-24)

- 新增 GUI 画质监控页面（`gui.py` `_build_quality_page`），通过解析子进程日志实时检测各直播间实际画质是否与设置一致
- 新增 Web 控制台开关配置 `web_show_console`（默认 true），设为 false 时程序后台隐藏运行
- 新增 `_enter_background_mode()`：Windows 下隐藏控制台窗口（SW_HIDE），日志重定向到 `logs/web_console.log`
- 新增 `[Web]` 配置节文档，含 web_host / web_port / web_auth_enable / web_password / web_token_expiry / web_show_console 六项
- 新增 Web 安全机制说明：密码变更吊销 Token、监听告警、路径穿越防护、敏感配置脱敏
- 统一代码注释风格：将 `web.py`、`src/web_config.py`、`src/web_api.py`、`src/stream.py` 中所有函数 docstring 转换为 `#` 行注释
- 新增实际画质回采与降级告警功能，覆盖抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC 七个平台
- 新增 `bitrate_to_quality()`、`code_to_zh()`、`is_downgrade()` 画质工具函数（`src/stream.py`）
- 新增 `actual_quality` / `available_qualities` 返回字段，各平台 stream 函数统一返回实际下发画质
- 改造 `get_bilibili_stream_data()` 返回 dict（含 url/current_qn/accept_qn），stream 模块反向映射 qn 为画质代码
- 新增 Web 管理面板（`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`），支持仪表盘、直播间管理、配置编辑、SSE 日志推送
- 新增前端"实际画质"列展示，降级时标红高亮（`.quality-down` 样式）
- 新增 `tests/test_stream_quality.py` 测试文件（347 行，17 个测试用例）
- 修复 `display_info` 中 `recording_time_list` 解包错误（2 元素改为 3 元素后兼容性修复）
- 修复 `asyncio.run()` 导致的 httpx 客户端跨事件循环复用问题（`'NoneType' object has no attribute 'send'`）
- 优化各平台流地址选择，用显式截断替代 `_pad_list` 静默填充，避免越界

### v4.0.8-dev (2026-07-23)

- 新增 HTTP 客户端连接池复用机制，按 (代理, verify, http2) 维度复用 AsyncClient，提升请求性能
- 新增 SSL 证书验证全局开关（`src/http_config.py`），通过 config.ini 统一控制异步/同步 HTTP 客户端
- 新增日志文件开关配置项，可通过 config.ini 控制是否输出日志文件
- 重构代理检测逻辑，从联网探测 Google 改为读取本地系统代理配置，避免启动时卡顿
- 优化异步 HTTP 请求异常处理，按返回契约提供类型安全的回退值
- 优化进程退出清理，新增 HTTP 客户端连接池的 atexit / 信号处理器兜底释放
- Dockerfile 新增 ca-certificates 依赖，支持启用 SSL 证书验证时的证书校验

### v4.0.8-dev (2026-06-27)

- 修复 `trace_error_decorator` 严重 Bug：原同步装饰器应用于 71 个异步函数导致错误捕获完全失效，现使用 `asyncio.iscoroutinefunction()` 支持同步/异步双模式
- 修复返回值类型不一致 Bug：`execjs.ProgramError` 分支返回 `None` → `{}`
- 修复 B站画质默认值 `'0'` 不在字典键中导致 KeyError
- 修复虎牙 `flv_anti_code` 为 None 导致 `parse_qs(None)` 崩溃
- 修复 TikTok/快手/网易CC 流地址列表为空时 IndexError
- 修复 `get_stream_url` 空列表索引崩溃（该函数未被装饰器保护）

### v4.0.8-dev (2026-06-20)

- 修复 spider.py 5 个运行时 Bug（KeyError、响应类型转换、循环静默返回）
- 修复 stream.py 2 个运行时 Bug（B站 None 检查、快手 quality 条件）
- 修复 gui.py 死代码（未使用变量、f-string 无占位符）
- 清理 src/weverse_auth.py 未使用导入
- i18n 翻译文件更新：新增 20 条翻译条目（异常错误消息、配置文件、磁盘空间等），总条目 200 条
- 通过 pyflakes 静态检查验证

### v4.0.8-dev (2025-05-17)

- 全新现代化 GUI 界面（WCAG AA 高对比度、DPI 感知字体）
- Docker 多阶段构建关键修复（运行时 Node.js、HEALTHCHECK）
- 配置文件重构（pyproject.toml、requirements.txt、.gitignore、.dockerignore）
- 新增抖音流数据调试工具 `debug_douyin_streams.py`
- 完善国际化翻译（YouTube/FlexTV/PopkonTV/TwitCasting）

### v4.0.7 (2025-10-24)

- 修复抖音风控问题
- 新增 SOOP 平台支持
- 修复 Bigo 录制

### v4.0.6 (2025-01-27)

- 新增淘宝、京东、Faceit 直播
- 重构为异步架构
- 新增强制 H264 编码选项

---

*本文档最后更新: 2026-08-01（mypy 严格模式全通过与类型注解收紧）*
