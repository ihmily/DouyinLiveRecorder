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
- ✅ 命令行 + GUI 双模式运行
- ✅ 多平台消息推送：钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus
- ✅ Docker 容器化部署
- ✅ 国际化支持（中文/英文）
- ✅ 灵活配置：画质选择、分段录制、自定义保存路径等

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
| Docker | 容器化部署 |
| gettext (msgfmt) | 国际化翻译编译 |
| pyflakes | 静态代码检查 |

---

## 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         用户交互层                                │
├─────────────────────────────┬───────────────────────────────────┤
│      命令行模式 (main.py)   │      GUI 图形界面 (gui.py)        │
└─────────────────────────────┴───────────────────────────────────┘
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
   - 验证流地址可用性

4. **录制执行阶段**
   - 启动 FFmpeg 子进程
   - 实时监控录制状态
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
│   ├── stream.py                       # 直播流地址解析
│   ├── room.py                         # 直播间信息解析
│   ├── utils.py                        # 工具函数库
│   ├── logger.py                       # Loguru 日志配置
│   ├── proxy.py                        # 代理检测
│   ├── ab_sign.py                      # 抖音签名算法 (A-Bogus)
│   ├── initializer.py                  # Node.js 自动初始化
│   ├── weverse_auth.py                 # Weverse 平台认证
│   ├── debug_douyin_streams.py         # 抖音流数据调试工具
│   ├── http_clients/                   # HTTP 客户端
│   │   ├── __init__.py
│   │   ├── async_http.py               # 异步 HTTP 客户端 (httpx)
│   │   └── sync_http.py                # 同步 HTTP 客户端
│   └── javascript/                     # JavaScript 签名脚本
│       ├── crypto-js.min.js            # 加密库
│       ├── x-bogus.js                  # 抖音 X-Bogus 签名
│       ├── haixiu.js                   # 嗨秀签名
│       ├── laixiu.js                   # 来秀签名
│       ├── liveme.js                   # LiveMe 签名
│       ├── migu.js                     # 咪咕签名
│       └── taobao-sign.js              # 淘宝签名
├── i18n/                                # 国际化文件
│   ├── zh_CN/LC_MESSAGES/
│   │   ├── zh_CN.po                   # 中文翻译源
│   │   └── zh_CN.mo                   # 编译后的翻译
│   └── en/LC_MESSAGES/
├── main.py                              # 命令行入口
├── gui.py                               # GUI 图形界面入口
├── msg_push.py                          # 消息推送模块
├── ffmpeg_install.py                    # FFmpeg 安装脚本
├── demo.py                              # 调用示例
├── requirements.txt                     # Python 依赖列表
├── pyproject.toml                      # Python 项目配置
├── Dockerfile                          # Docker 构建文件
├── .dockerignore                       # Docker 排除文件
├── .gitignore                          # Git 排除文件
├── README.md                           # 项目说明
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
```

**主流程函数**:
- `main()` - 入口函数
- `read_config()` - 读取配置
- `check_url_config()` - 检查 URL 配置
- `start_recording()` - 启动录制
- `stop_recording()` - 停止录制
- `check_live_status()` - 检测直播状态

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
- `get_play_url_list()` - 获取 M3U8 播放列表中的清晰度选项
- `get_params()` - 从 URL 提取参数

**实现特点**:
- 使用异步 HTTP 客户端 (`httpx`)
- 各平台独立的签名算法
- 代理支持
- Cookie 支持
- 错误重试机制

---

### 3. 直播流解析模块 (`src/stream.py`)

**职责**: 解析直播流地址，支持多种画质选择

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
```

**关键函数**:
- `get_quality_index()` - 解析画质参数，返回索引
- `get_douyin_stream_url()` - 获取抖音直播流地址
- `get_tiktok_stream_url()` - 获取 TikTok 直播流地址
- `get_bilibili_stream_url()` - 获取 B站 直播流地址
- `_pad_list()` - 填充列表到指定最小长度

**实现特点**:
- 按带宽排序的清晰度选择
- 自动降级策略（首选画质不可用时自动降级）
- FLV 与 M3U8 双协议支持
- 状态码验证

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

---

### 10. 异步 HTTP 客户端 (`src/http_clients/async_http.py`)

**职责**: 封装 httpx，提供统一的异步 HTTP 接口

**功能**:
- 代理支持
- 超时设置
- 自动重试
- 状态码检查
- HTTP/2 支持

**被以下模块导入**:
- `src/spider.py` - `async_req()`
- `src/stream.py` - `get_response_status()`
- `src/debug_douyin_streams.py` - `async_req()`

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
│   └── src/utils.py
├── src/stream.py
│   ├── src/spider.py
│   └── src/http_clients/async_http.py
├── src/utils.py
│   └── src/logger.py
├── msg_push.py
└── ffmpeg_install.py
```

---

## 配置文件说明

### 主配置文件 (`config/config.ini`)

#### [录制设置] 节

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| language | 界面语言 | zh_cn |
| 是否跳过代理检测 | 是否跳过代理检测 | 是 |
| 直播保存路径 | 录制文件保存路径 | (空，默认当前目录) |
| 保存文件夹是否以作者区分 | 是否按主播名分类 | 是 |
| 视频保存格式 | ts/mkv/flv/mp4/mp3/m4a | ts |
| 原画\|超清\|高清\|标清\|流畅 | 默认画质 | 原画 |
| 是否使用代理ip | 是否启用代理 | 否 |
| 代理地址 | 代理服务器地址 | (空) |
| 同一时间访问网络的线程数 | 并发数 | 3 |
| 循环时间(秒) | 直播状态检测间隔 | 300 |
| 分段录制是否开启 | 是否分段 | 是 |
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
2. 在 `src/stream.py` 中添加流地址解析函数
3. 在 `main.py` 中添加平台识别逻辑
4. 更新 `README.md` 和本文档

---

## 更新日志

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

*本文档最后更新: 2026-06-27*
