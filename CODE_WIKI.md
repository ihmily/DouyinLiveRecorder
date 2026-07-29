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

---

## 项目概述

### 项目基本信息
- **项目名称**: DouyinLiveRecorder (抖音直播录制器)
- **版本**: 4.0.8-dev
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
| 技术 | 用途 |
|------|------|
| Python 3.10+ | 核心编程语言 |
| asyncio + httpx | 异步网络请求 |
| asyncio | 异步装饰器支持 |
| FFmpeg | 视频录制与转码 |
| Node.js + PyExecJS | 运行 JavaScript 签名算法 |
| Loguru | 结构化日志 |
| tkinter + pystray + Pillow | GUI 图形界面与系统托盘 |
| FastAPI + uvicorn | Web 管理面板后端 |
| HTML + CSS + JavaScript | Web 管理面板前端 |
| Docker | 容器化部署 |
| gettext (msgfmt) | 国际化翻译编译 |
| pyflakes | 静态代码检查 |

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
│   ├── debug_douyin_streams.py         # 抖音流数据调试工具
│   ├── web_api.py                      # Web 管理面板 FastAPI 应用
│   ├── web_config.py                   # Web 面板配置读写（不依赖 FastAPI）
│   ├── http_clients/                   # HTTP 客户端
│   │   ├── __init__.py
│   │   ├── config.py                  # HTTP 客户端共享运行时配置（SSL 验证开关）
│   │   ├── async_http.py               # 异步 HTTP 客户端 (httpx)
│   │   └── sync_http.py                # 同步 HTTP 客户端
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
├── i18n/                                # 国际化文件
│   ├── zh_CN/LC_MESSAGES/
│   │   ├── zh_CN.po                   # 中文翻译源
│   │   └── zh_CN.mo                   # 编译后的翻译
│   └── en/LC_MESSAGES/
├── main.py                              # 命令行入口
├── gui.py                               # GUI 图形界面入口
├── web.py                               # Web 管理面板入口
├── msg_push.py                          # 消息推送模块
├── demo.py                              # 调用示例
├── build_exe.py                         # PyInstaller 打包脚本（CLI/GUI/Web 三入口）
├── DouyinLiveRecorder.spec              # 由 build_exe.py 自动生成（.gitignore 已忽略）
├── requirements.txt                     # Python 依赖列表
├── pyproject.toml                      # Python 项目配置
├── Dockerfile                          # Docker 构建文件
├── .dockerignore                       # Docker 排除文件
├── .gitignore                          # Git 排除文件
├── README.md                           # 项目说明
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

---

### 2. 爬虫模块 (`src/spider.py`)

**职责**: 负责从各大直播平台获取直播间数据

**支持平台**:
国内：抖音、快手、虎牙、斗鱼、YY、B站、小红书、Bigo、Blued、网易CC、千度热播、猫耳FM、Look、TwitCasting、百度、微博、酷狗、花椒、流星、Acfun、畅聊、映客、音播、知乎、嗨秀、VV星球、17Live、浪Live、飘飘、六间房、乐嗨、花猫、淘宝、京东、咪咕、连接、来秀
海外：TikTok、SOOP、PandaTV、WinkTV、FlexTV、PopkonTV、Twitch、LiveMe、ShowRoom、CHZZK、Shopee、YouTube、Faceit、Picarto

**关键函数**:
- `get_douyin_web_stream_data()` - 获取抖音 Web 端直播数据
- `get_tiktok_stream_data()` - 获取 TikTok 直播数据
- `get_youtube_stream_data()` - 获取 YouTube 直播数据
- `get_bilibili_stream_data()` - 获取 B站直播流数据（返回 dict，含 url/current_qn/accept_qn）
- `get_play_url_list()` - 获取 M3U8 播放列表中的清晰度选项
- `get_params()` - 从 URL 提取参数

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
QUALITY_MAPPING = {
    "OD": 0,    # 原画 (Original Definition)
    "BD": 0,    # 蓝光 (Blu-ray)
    "UHD": 1,   # 超清 (Ultra HD)
    "HD": 2,    # 高清 (High Definition)
    "SD": 3,    # 标清 (Standard Definition)
    "LD": 4     # 流畅 (Low Definition)
}
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
|------|------|-----------------|
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

---

### 4. 直播间信息模块 (`src/room.py`)

**职责**: 解析直播间 URL，提取房间 ID、主播信息等

**关键函数**:
- `get_sec_user_id()` - 获取房间 ID 和用户 sec_user_id
- `get_unique_id()` - 获取抖音号
- `get_live_room_id()` - 获取直播间 web ID
- `get_xbogus()` - 生成 X-Bogus 签名

**异常处理**:
- `UnsupportedUrlError` - 不支持的 URL 格式异常

---

### 5. 工具模块 (`src/utils.py`)

**职责**: 提供通用工具函数

**主要工具**:

| 工具函数 | 功能描述 |
|---------|---------|
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

| 渠道 | 函数名 | 说明 |
|------|--------|------|
| 钉钉 | `dingtalk()` | 群机器人推送 |
| 微信 | `xizhi()` | Server酱 / WeChat |
| Telegram | `tg_bot()` | Bot 消息 |
| 邮件 | `send_email()` | SMTP 协议 |
| Bark | `bark()` | iOS 通知 |
| NTFY | `ntfy()` | 开源推送服务 |
| PushPlus | `pushplus()` | 微信推送平台 |

---

### 8. 国际化模块 (`i18n.py`)

**职责**: 基于 gettext 的多语言支持系统，自动翻译 `src/` 目录下的 print 输出。

**实现机制**:
- `translated_print` 包装 `builtins.print`，自动翻译调用者来自 `src/` 包的输出
- 支持源码运行和 PyInstaller 打包两种路径检测（`_internal/i18n` vs `i18n/`）
- 默认语言：简体中文（zh_CN）

**翻译文件**:
| 文件 | 说明 | 条目数 |
|------|------|--------|
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` | 中文翻译源文件（可编辑） | 200 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | 编译后的二进制翻译文件 | 200 |
| `i18n/en/LC_MESSAGES/` | 英文翻译目录（预留） | — |

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
- 解析 loguru 日志前缀（` | ` + ` - ` 分隔），提取 message 内容
- 降级告警匹配：`{name} 画质降级：设置 {zh}({code}) 实际 {zh}({code})`
- 录制状态匹配：`{name}[{quality}] 正在录制中 {duration}`
- 统计卡片：录制中 / 画质正常 / 画质降级 计数
- 降级行以红色背景高亮，正常行显示"✓ 同等"
- 线程安全：`_quality_lock` 保护共享数据，UI 更新仅在主线程执行
- 超时清理：30 秒未更新的录制标记自动清除

---

### 10. 异步 HTTP 客户端 (`src/http_clients/async_http.py`)

**职责**: 封装 httpx，提供统一的异步 HTTP 接口

**功能**:
- 代理支持
- 超时设置
- 自动重试
- 状态码检查
- HTTP/2 支持
- **连接池复用**: 按 (代理, verify, http2) 维度复用 AsyncClient，发挥 keepalive 连接池作用
- **事件循环检测**: 缓存记录每个 client 创建时的事件循环引用，检测到 `asyncio.run()` 导致循环变更时自动重建客户端，避免 `'NoneType' object has no attribute 'send'` 错误
- **SSL 验证**: 由全局配置 `src/http_clients/config.py` 统一控制，默认禁用
- **连接池清理**: 进程退出时通过 atexit / 信号处理器释放所有复用的 AsyncClient

**被以下模块导入**:
- `src/spider.py` - `async_req()`
- `src/stream.py` - `get_response_status()`
- `src/debug_douyin_streams.py` - `async_req()`

---

### 11. HTTP 客户端配置 (`src/http_clients/config.py`)

**职责**: 提供 HTTP 客户端共享运行时配置

**功能**:
- SSL 证书验证全局开关（`ssl_verify`），默认禁用（False）以兼容历史行为
- 提供 `set_ssl_verify()` 函数，由主配置在启动时统一设置
- 异步 / 同步 HTTP 客户端在发起请求时读取此配置

---

### 12. 同步 HTTP 客户端 (`src/http_clients/sync_http.py`)

**职责**: 封装 requests 和 urllib，提供同步 HTTP 接口

**功能**:
- 代理支持
- 超时设置
- Cookie 支持
- 重定向跟踪
- **SSL 验证**: 由全局配置 `src/http_clients/config.py` 统一控制
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

| 路由 | 方法 | 功能 |
|------|------|------|
| `/api/login` | POST | 密码登录，返回 Token |
| `/api/status` | GET | 获取录制状态（含 actual_quality） |
| `/api/rooms` | GET/POST | 直播间列表查询 / 新增 |
| `/api/rooms/{url}` | PUT/DELETE | 编辑 / 删除直播间 |
| `/api/rooms/toggle` | POST | 启用 / 禁用直播间 |
| `/api/config` | GET/PUT | 读取 / 修改配置 |
| `/api/logs/stream` | GET | SSE 实时日志推送 |

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

### Python 依赖 (`requirements.txt`)

| 包名 | 版本要求 | 用途 |
|------|---------|------|
| requests | >=2.28.0 | 同步 HTTP 请求 |
| httpx | >=0.25.0 | 异步 HTTP 客户端 |
| loguru | >=0.7.0 | 结构化日志 |
| pycryptodome | >=3.15.0 | 加密算法（SM3、RC4） |
| distro | >=1.8.0 | Linux 发行版检测 |
| tqdm | >=4.65.0 | 进度条 |
| PyExecJS | >=1.5.1 | JavaScript 执行引擎 |
| pystray | >=0.19.4 | 系统托盘（GUI） |
| Pillow | >=10.0.0 | 图像处理（GUI 图标） |
| weverse | >=0.9.0 | Weverse 平台 SDK |
| fastapi | >=0.100.0 | Web 管理面板后端框架 |
| uvicorn | >=0.23.0 | ASGI 服务器 |
| pydantic | >=2.0.0 | 请求模型校验 |

### 外部依赖

| 依赖 | 用途 | 安装方式 |
|------|------|---------|
| FFmpeg | 视频录制与转码 | Windows 内置，Linux/macOS 需手动安装 |
| Node.js | 运行 JavaScript 签名算法 | Windows 自动安装，Linux 需包管理器安装 |

### 模块依赖关系图

```
main.py
├── src/spider.py
│   ├── src/room.py
│   ├── src/ab_sign.py
│   ├── src/http_clients/async_http.py
│   │   └── src/http_clients/config.py
│   ├── src/http_clients/config.py
│   └── src/utils.py
├── src/stream.py
│   ├── src/spider.py
│   └── src/http_clients/async_http.py
├── src/http_clients/config.py
├── src/http_clients/async_http.py
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

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| language | 界面语言 | zh_cn |
| 是否跳过代理检测 | 是否跳过代理检测 | 是 |
| 是否禁用SSL证书验证 | 是否禁用 SSL 证书验证 | 是 |
| 是否启用日志文件 | 是否将日志写入文件 | 是 |
| 直播保存路径 | 录制文件保存路径 | (空，默认当前目录) |
| 保存文件夹是否以作者区分 | 是否按主播名分类 | 是 |
| 视频保存格式 | ts/mkv/flv/mp4/mp3/m4a | ts |
| 原画\|超清\|高清\|标清\|流畅 | 默认画质 | 原画 |
| 是否使用代理ip | 是否启用代理 | 否 |
| 代理地址 | 代理服务器地址 | (空) |
| 同一时间访问网络的线程数 | 并发数 | 3 |
| 循环时间(秒) | 直播状态检测间隔 | 300 |
| 分段录制是否开启 | 是否分段 | 是 |
| 是否启用HLS采集(是/否) | 是否优先使用 HLS(m3u8) 源采集；关闭或源不可用时回退 FLV | 是 |
| 视频分段时间(秒) | 分段时长 | 3600 |
| 使用代理录制的平台 | 需要代理的平台列表 | tiktok, sooplive... |

#### [推送配置] 节

| 配置项 | 说明 |
|--------|------|
| 直播状态推送渠道 | 微信\|钉钉\|tg\|邮箱\|bark\|ntfy\|pushplus |
| 钉钉推送接口链接 | 钉钉 Webhook |
| 微信推送接口链接 | Server酱 URL |
| bark推送接口链接 | Bark API |
| tgapi令牌 | Telegram Bot Token |
| tg聊天id | 聊天 ID |
| smtp邮件服务器 | SMTP 服务器 |
| ntfy推送地址 | NTFY 服务地址 |
| pushplus推送token | PushPlus Token |
| 只推送通知不录制 | 是否仅通知不录制 |

#### [Cookie] 节

各平台的 Cookie 配置（录制部分平台必填）

#### [Authorization] 节

特殊平台的 Token 配置

#### [账号密码] 节

部分平台的账号密码配置

#### [Web] 节

Web 管理面板配置（`web.py` 模式专用）

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| web_host | 监听地址 | 0.0.0.0 |
| web_port | 监听端口 | 8000 |
| web_auth_enable | 是否启用密码认证 | false |
| web_password | 登录密码（认证开启时必填） | (空) |
| web_token_expiry | Token 有效期（秒） | 86400 |
| web_show_console | 是否显示控制台窗口（false 时后台隐藏运行） | true |

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

#### Dockerfile 多阶段构建说明

```dockerfile
# 阶段 1: builder
# - 安装 Node.js
# - 创建 Python 虚拟环境（venv）
# - 安装 Python 依赖到 venv

# 阶段 2: runtime
# - 精简基础镜像
# - 安装 Node.js + ffmpeg + procps 等运行时依赖
# - 从 builder 复制 Python 虚拟环境
# - 使用非 root 用户运行
```

#### 使用 docker-compose (推荐)

**创建 `docker-compose.yml`**:
```yaml
services:
  douyin-live-recorder:
    build: .
    container_name: douyin-live-recorder
    restart: unless-stopped
    volumes:
      - ./config:/app/config
      - ./downloads:/app/downloads
      - ./logs:/app/logs
      - ./backup_config:/app/backup_config
    environment:
      - TZ=Asia/Shanghai
    healthcheck:
      test: ["CMD-SHELL", "pgrep -f 'python main.py' || exit 1"]
      interval: 30s
      start_period: 15s
```

**运行**:
```bash
docker-compose up -d
```

---

## 打包与发布

本项目提供一键式可执行文件打包（`build_exe.py`）与跨平台自动构建发布（`GitHub Actions`），将 **CLI / GUI / Web 三个入口**统一构建为可分发的发布目录。

### 1. 打包脚本 `build_exe.py`

PyInstaller `onedir` 模式 + `contents_directory='_internal'`，动态生成 `.spec` 文件后调用 PyInstaller 完成**三入口共享依赖**构建：

| 产物（exe 同级） | 入口 | 模式 |
|------------------|------|------|
| `DouyinLiveRecorder(.exe)` | `main.py` | 控制台（CLI 录制核心） |
| `DouyinLiveRecorder-GUI(.exe)` | `gui.py` | 无控制台窗口（GUI） |
| `DouyinLiveRecorder-Web(.exe)` | `web.py` | 控制台（Web 管理面板，监听 `0.0.0.0:8000`） |

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
- `hiddenimports`：`i18n`、`src.http_clients.async_http`（main.py 经 `__import__` 动态导入）、`h2`（httpx[http2] 懒加载）；`a_web` 额外 `collect_submodules('uvicorn')`（协议模块按字符串导入）。
- `excludes`：CLI 排除 GUI/Web 库（tkinter/customtkinter/pystray/PIL/fastapi/uvicorn/starlette）；GUI 排除 Web 库；Web 排除 GUI 库。

**版本号**：从 `main.py` 的 `version` 变量解析（如 `v4.0.7`），用于 zip 命名，解析失败回退 `0.0.0`。

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

**解决**:
- 更新 Cookie
- 降低循环监测频率
- 更换 IP

---

## 贡献指南

### 代码规范

- 格式化: `black .`
- 导入排序: `isort .`
- 类型检查: `mypy .`

### 添加新平台支持

1. 在 `src/spider.py` 中添加平台数据获取函数
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑
4. 在 `tests/test_stream_quality.py` 中添加画质回采测试
5. 更新 `README.md` 和本文档

---

## 更新日志

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
- `src/http_clients/config.py`：移除 `bool(value)` 冗余调用（参数已标注为 `bool`）
- `src/http_clients/async_http.py`：`_get_client()` 重构为 early-return 模式，消除 `client` 可能未绑定错误
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

| 包名 | 声明状态 | 使用位置 |
|------|---------|---------|
| requests | 已声明 | src/ffmpeg_install.py, src/node_install.py, src/http_clients/sync_http.py, src/weverse_auth.py |
| httpx[http2] | 已声明 | main.py, src/room.py, src/spider.py, src/http_clients/async_http.py |
| loguru | 已声明 | src/logger.py, msg_push.py |
| pycryptodome | 已声明 | src/spider.py (Crypto.Cipher.AES) |
| distro | 已声明 | src/node_install.py |
| tqdm | 已声明 | src/ffmpeg_install.py, src/node_install.py |
| PyExecJS | 已声明 | src/room.py, src/spider.py, src/utils.py |
| customtkinter | 已声明 | gui.py |
| pystray | 已声明 | gui.py, gui_legacy.py (延迟导入) |
| Pillow | 已声明 | gui.py, gui_legacy.py |
| fastapi | 已声明 | src/web_api.py |
| uvicorn[standard] | 已声明 | web.py (延迟导入) |
| python-multipart | 已声明 | FastAPI 表单处理隐式依赖 |
| **pydantic** | **缺失→已补** | src/web_api.py (BaseModel) |

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
- 新增 SSL 证书验证全局开关（`src/http_clients/config.py`），通过 config.ini 统一控制异步/同步 HTTP 客户端
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

*本文档最后更新: 2026-07-28（多直播间并发监控风控修复与静态检查清零）*
