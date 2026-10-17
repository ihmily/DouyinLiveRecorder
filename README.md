![video_spider](https://socialify.git.ci/y123ao6/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

简体中文&nbsp;&nbsp;|&nbsp;&nbsp;[**English**](README_EN.md)

## 💡 简介

[![Python Version](https://img.shields.io/badge/python-v3.14%2B-blue?logo=python)](https://www.python.org/downloads/)
[![Node.js Version](https://img.shields.io/badge/node.js-LTS_v24%2B-blue?logo=node.js)](https://nodejs.org/en/download)
[![FFmpeg Version](https://img.shields.io/badge/ffmpeg-v9.0%2B-blue?logo=ffmpeg)](https://www.ffmpeg.org/download.html)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%7CLinux%7CmacOS-blue)](https://github.com/y123ao6/DouyinLiveRecorder)
[![GitHub issues](https://img.shields.io/github/issues/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/issues)
[![Latest Release](https://img.shields.io/github/v/release/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/y123ao6/DouyinLiveRecorder/total)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/stargazers)

一款**简易**的可循环值守的直播录制工具，基于 FFmpeg 实现多平台直播源录制，支持自定义配置录制以及直播状态推送。

上游项目：[ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder)

## ✨ 功能特性

| 功能 | 说明 |
| --- | --- |
| 🎯 **多平台支持** | 支持抖音、TikTok、YouTube、快手、虎牙、斗鱼、B站等 **51 个平台**（持续添加中） |
| 🔄 **循环值守** | 自动检测直播状态，开播自动录制，断播自动停止 |
| 🎬 **多种格式** | 支持 TS、MKV、FLV、MP4、MP3、M4A 等格式输出 |
| 🖥️ **三模式运行** | 命令行模式、GUI 图形界面模式、Web 管理面板模式 |
| 📊 **画质监控** | 实时检测各直播间实际画质，画质降级时自动告警 |
| 💬 **弹幕录制** | 抖音 / 斗鱼 / 虎牙 / B站 / TwitchTV 弹幕采集，按分片输出 SRT 字幕，与视频同起同停 |
| 👀 **弹幕监控** | 独立的弹幕实时查看模式（不落盘），GUI 与 Web 面板均可查看 |
| 🏷️ **主播名自动更新** | 主播改名后自动同步 `URL_config.ini` 并重命名录制目录与文件 |
| 📱 **消息推送** | 支持钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus 等推送 |
| 🐳 **Docker 支持** | 支持 Docker 容器化部署，开箱即用 |
| 🌐 **国际化** | 内置简体中文 / English (US) / English (UK) / 繁體中文 四语，GUI 与 Web 面板**免重启热切换** |
| ⚙️ **灵活配置** | 支持按直播间自定义画质、格式、分段录制等，配置改动热加载 |
| 🔐 **Web 安全** | Token 认证、登录爆破限流、路径穿越防护、敏感配置脱敏、未认证写保护 |

## 🚀 快速开始

### 方式一：下载运行包（推荐新手）

1. 进入 [Releases](https://github.com/y123ao6/DouyinLiveRecorder/releases) 下载最新发布的 zip 压缩包。
   每个平台各出 **lite**（不含内置 ffmpeg/node，首启时程序尝试自动获取）与 **full**（内置运行时）两包。
   附件名的**平台段**由 `build_exe.make_zip()` 取 `sys.platform` 经 `{"win32": "windows", "darwin": "macos"}`
   归一（其余一律归 `linux`），**架构段**才是 `platform.machine().lower()` 的实际取值：

   | 运行平台 | 附件名 |
   | --- | --- |
   | Windows x64 | `DouyinLiveRecorder-v<版本>-windows-amd64-lite.zip` / `-full.zip` |
   | Linux x86_64 | `DouyinLiveRecorder-v<版本>-linux-x86_64-lite.zip` / `-full.zip` |
   | **Linux arm64** | `DouyinLiveRecorder-v<版本>-linux-aarch64-lite.zip` / `-full.zip` |
   | macOS（Apple Silicon） | `DouyinLiveRecorder-v<版本>-macos-arm64-lite.zip` / `-full.zip` |

   > Linux arm64 的架构段写作 **`aarch64`**——那是 `platform.machine().lower()` 在该架构上的实际取值，
   > **不是** `arm64`；该包由四平台发布矩阵（`windows` / `linux` / `linux-arm64` / `macos`）产出。
   > Linux 上 lite 包的自动获取顺序是 `yum` → `apt` → 官方月末构建直下（后者按 GitHub 公布的
   > asset digest 校验，需 `api.github.com` 可达；全链路都失败时才会提示手动安装）。
2. 解压后，在 `config` 文件夹内的 `URL_config.ini` 中添加直播间地址
3. 运行 `DouyinLiveRecorder.exe` 开始录制

### 方式二：源码运行（推荐开发者）

```bash
# 克隆项目
git clone https://github.com/y123ao6/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# 安装依赖（推荐使用 uv）
uv sync

# 或者使用 pip
pip install -r requirements.txt

# 运行程序
python main.py        # 命令行模式
python gui.py         # GUI 图形界面模式
python web.py         # Web 管理面板模式
```

### 方式三：Docker 运行

```bash
# 命令行录制模式（默认，不占用端口）
docker compose up -d

# Web 管理面板模式（浏览器访问 http://localhost:8000）
# 注意：需先在 config/config.ini 的 [Web] 节设置 web_host = 0.0.0.0，
#       并建议开启 web_auth_enable = true 配置访问密码
docker compose --profile web up -d

# 或本地构建并启动（APP_VERSION 取自 pyproject.toml；缺省则镜像 LABEL version 固化为空串）
docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" -t douyin-live-recorder .
docker run -d -v ./config:/app/config -v ./downloads:/app/downloads -v ./logs:/app/logs -v ./backup_config:/app/backup_config douyin-live-recorder
```

> 容器内 FFmpeg 与 Node.js 由镜像自带（apt 安装），无需挂载本地 `ffmpeg/`、`node/` 目录；
> `config/`、`downloads/`、`logs/`、`backup_config/` 通过卷挂载持久化。
> 不想本地构建时，可直接拉取 GHCR 上的预构建多架构镜像（`linux/amd64` + `linux/arm64`），
> 命令见下方「🐋 Docker 部署」的「拉取预构建的多架构镜像（GHCR）」小节。

### 手动安装 ffmpeg（Windows 用户指南）

Windows 版会在启动时自动从官方源 gyan.dev 下载 ffmpeg——**这是 Windows 上唯一的自动下载路径**（不设镜像兜底，
因为镜像产物没有可核对的官方摘要）。自动安装失败时（多为 gyan.dev 不可达、代理/防火墙拦截，
或 SHA256 基线校验被拒），照下面三步手动安装即可。

1. **下载官方 zip**：<https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip>
   需要自行核对来源时，比对该 zip 的官方摘要文档
   <https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256>（程序自动安装时校验用的就是这份）。
2. **把解压出来的 `bin` 文件夹放进程序目录并改名为 `ffmpeg`**：

| 你的运行方式 | 放置结果（务必是这一层） |
| --- | --- |
| 下载的运行包（exe） | `DouyinLiveRecorder\ffmpeg\ffmpeg.exe` |
| 源码运行 / 单文件版脚本 | `<项目根>\ffmpeg\ffmpeg.exe` |

   - **不要**保留成 `ffmpeg\bin\ffmpeg.exe`——程序只把 `ffmpeg\` 这一层目录加入查找路径，不会进子目录寻找。
   - 请把同目录下的 `ffprobe.exe` 一并放入（发布包出包自检要求 ffmpeg 与 ffprobe 都在且可执行）。
3. **验证**：在 `ffmpeg\` 目录里执行 `ffmpeg -version`，能打印版本号即成功。随后重启程序，
   日志（`logs\streamget.log`）中不再出现「未安装 ffmpeg。」即为生效。

也可以改用系统级安装（`winget install Gyan.FFmpeg`、Chocolatey，或任何你信任的构建）把它装进
系统 `PATH`——程序同样按 `PATH` 查找，两种放法等效。

**报错是 SHA256 基线校验被拒时**（日志会写出「请删除 …`_ffmpeg_official*.zip.sha256`… 后重试」）：
删除**程序目录**下匹配 `_ffmpeg_official*.zip.sha256` 的旁路文件，再重启程序。该文件记录的是首次
下载时核对到的摘要，而 gyan.dev 的下载链接是滚动地址——上游发布新构建后旧基线必然失配，删掉它等于
让程序按新构建重新记账。（其校验强度等同于该目录的写权限，不是独立的信任根，故不能替代官方摘要文档。）

> 适用范围：**full 版**发布包已内置 ffmpeg，一般无需任何安装；**lite 版**与单文件版不含，需自动安装
> 或按上文手动安装。macOS 走 Homebrew；Linux 依次为 `yum` → `apt` → 官方月末构建直下（按 `api.github.com`
> 公布的 asset digest 校验，需该域名可达）；三条都失败时按各自发行版方式手动安装。
> Apple Silicon 上「包内那份」与「系统原生那份」的取舍见下方常见问题。

## 🎈 已支持平台

**国内站点（37 个）**：抖音 | 快手 | 虎牙 | 斗鱼 | YY | B站 | 小红书 | bigo | blued | 网易CC | 千度热播 | 猫耳FM | Look直播 | TwitCasting | 百度 | 微博 | 酷狗 | 花椒 | 流星 | Acfun | 畅聊 | 映客 | 音播 | 知乎 | 嗨秀 | VV星球 | 17Live | 浪Live | 飘飘 | 六间房 | 乐嗨 | 花猫 | 淘宝 | 京东 | 咪咕 | 连接 | 来秀

**海外站点（14 个）**：TikTok | SOOP(原AfreecaTV) | PandaTV | WinkTV | TTingLive(原Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | YouTube | Faceit | Picarto

> 合计 **51 个**平台（对外标称 60+，含持续添加中的平台）。各平台数据获取函数位于 `src/spider.py`，流地址解析位于 `src/stream.py`。

**弹幕录制支持（5 个平台）**：抖音直播 | 斗鱼直播 | 虎牙直播 | B站直播 | TwitchTV

**实际画质回采与降级告警（7 个平台）**：抖音 | TikTok | 快手 | 虎牙 | 斗鱼 | B站 | 网易CC

**斗鱼支持的链接形态（两种域名走同一套录制流程）**：`https://www.douyu.com/8751648` | `https://m.douyu.com/8751648`（移动端）。尾斜杠（`.../8751648/`）、查询参数（`...?rid=8751648`、`...?dyshid=...`）、`http://` 协议与附加路径均可识别；字母号与分享链接会先还原为数字房间号再取流。链接缺少房间号或房间号非法时给出明确错误提示（链接入日志前一律脱敏）。

**B站支持的链接形态（两种域名走同一套录制流程）**：`https://live.bilibili.com/22747736` | `https://b23.tv/22747736`（移动端分享短域，纯数字房间号；尾斜杠、查询参数与 `http://` 协议均可识别）。字母短码（如 `https://b23.tv/ZyQrgYf`）会先跟随 302 跳转解析出真实房间号（结果进程内缓存，不重复请求）再取流；跳转落地不是B站直播间、或链接缺少房间号 / 房间号非法时给出明确错误提示（链接入日志前一律脱敏）。

**虎牙支持的链接形态（移动端分享短链与桌面链接走同一套录制流程）**：`https://www.huya.com/30764624` | `https://hy.fan/30764624`（移动端分享域，纯数字路径段即房间号；尾斜杠、查询参数与 `http://` 协议均可识别）。字母短码（如 `https://hy.fan/JbmwoV`）会先跟随 301 跳转解析出真实房间段（结果进程内缓存，不重复请求）再归一为桌面链接取流；跳转落地不是虎牙直播间、或链接缺少房间号 / 房间号非法时给出明确错误提示（链接入日志前一律脱敏）。

## 📁 项目结构

```
DouyinLiveRecorder/
├── config/                     # 配置文件目录
│   ├── config.ini             # 主配置文件
│   └── URL_config.ini         # 直播间地址列表
├── src/                        # 核心源码包
│   ├── __init__.py             # 包初始化 + Node.js 环境配置 + 弹幕平台注册表/工厂
│   ├── spider.py              # 直播流地址解析（60+ 平台，已抽离弹幕逻辑）
│   ├── stream.py              # 直播流录制编排（ffmpeg 命令/分段/格式）
│   ├── stream_select.py       # 流地址选源/可达性校验/探针退避
│   ├── scheduler.py           # 并发调度中枢（自适应容量 + 按平台熔断）
│   ├── room.py                # 直播间信息解析
│   ├── utils.py               # 工具函数库
│   ├── logger.py              # Loguru 日志配置
│   ├── proxy.py               # 代理检测
│   ├── ab_sign.py             # 抖音 A-Bogus 签名
│   ├── ttwid.py               # 抖音访客 ttwid 获取/缓存
│   ├── node_install.py        # Node.js 自动安装/初始化
│   ├── ffmpeg_install.py      # FFmpeg 安装脚本
│   ├── ffmpeg_master_download.py  # FFmpeg master 构建（按平台拉取并校验）
│   ├── ffmpeg_proc.py         # ffmpeg 子进程管理（抽离自 main.py）
│   ├── video_postprocess.py   # 录制后处理（转封装/转码）
│   ├── notify.py              # 直播状态消息推送（抽离自 main.py）
│   ├── recorder_status.py     # 录制状态跟踪（抽离自 main.py）
│   ├── config_io.py           # 配置读写/数值转换/备份（抽离自 main.py）
│   ├── config_bool.py         # 布尔配置解析（是/否 与 true/false/1/0/yes/no 等价，零依赖）
│   ├── config_read.py         # 容错配置读取（同节重复键折叠为最后一次取值并点名告警）
│   ├── cookie_cache.py        # 访客 Cookie 进程级共享缓存
│   ├── log_archive.py         # 运行日志归档（停止录制流程收尾：四日志按时间戳改名）
│   ├── http_config.py          # HTTP 客户端共享配置（SSL 验证开关）
│   ├── async_http.py          # 异步 HTTP 客户端 (httpx)
│   ├── sync_http.py           # 同步 HTTP 客户端
│   ├── web_api.py             # Web 管理面板 Starlette 应用
│   ├── web_config.py          # Web 面板配置读写
│   ├── web_tray.py            # Web 模式系统托盘（最小化到托盘）
│   ├── base.py               # 弹幕采集基类（DanmakuBase / DanmakuMessage）
│   ├── collector.py           # 弹幕采集器（线程桥接主流程）
│   ├── danmaku_monitor.py     # 弹幕监控枢纽（DanmakuMonitorHub）
│   ├── srt_writer.py         # 弹幕时间字幕（SRT）写入
│   ├── ws_client.py          # WebSocket 传输层（弹幕直连、proxy=None）
│   ├── platforms/            # 弹幕平台实现（按平台标识经工厂注册）
│   │   ├── douyin.py         # 抖音弹幕（protobuf + _tars 心跳）
│   │   ├── douyu.py          # 斗鱼弹幕（STT 协议）
│   │   ├── huya.py           # 虎牙弹幕（WSP 协议）
│   │   ├── bilibili.py       # B站弹幕（WebSocket）
│   │   ├── twitch.py         # Twitch 弹幕（IRC/WS）
│   │   ├── _tars.py          # TARS 私有协议编解码
│   │   └── _xbogus.py        # X-Bogus 签名
│   ├── proto/                # 抖音弹幕 protobuf 定义
│   │   ├── douyin.proto      # protoc 源定义
│   │   ├── douyin_pb2.py      # protoc 生成（DO NOT EDIT）
│   │   └── douyin_pb2.pyi     # 类型存根
│   ├── gui_qt/              # GUI 窗口层（PySide6/Qt，`gui.py:main()` 委托到该包）
│   │   ├── app.py           # Qt 应用装配与事件循环
│   │   ├── main_window.py   # 主窗口 / 侧边栏导航
│   │   ├── theme.py         # 设计令牌（25 键 × 3 主题）与 QSS 生成
│   │   └── pages/           # dashboard / config / danmaku / quality / runlog 五页
│   └── javascript/            # JavaScript 签名脚本
│       ├── crypto-js.min.js
│       ├── x-bogus.js
│       ├── haixiu.js
│       ├── liveme.js
│       └── migu.js
├── web/                        # Web 管理面板前端
│   ├── index.html              # 单页应用入口
│   ├── app.js                  # 前端逻辑（API、SSE、渲染）
│   └── style.css               # 样式表（主题、响应式）
├── typings/                    # 第三方库类型存根（静态检查用）
│   ├── execjs/                 # PyExecJS 存根
│   └── pystray/                # pystray 存根
├── scripts/                    # 工程辅助脚本
│   ├── smoke_test.py           # 通用 Web/接口冒烟测试（零依赖，配置驱动）
│   ├── smoke_web.json          # 冒烟测试示例用例（探活 Web 面板）
│   ├── compile_po.py           # .po → .mo 编译与同步校验（--check）
│   ├── check_coverage.py       # 逐模块覆盖率门禁（CI 使用）
│   ├── check_version.py        # 版本号「单一事实源」动态化校验
│   └── sync_version.py         # 版本号同步辅助
├── downloads/                  # 录制文件保存目录（运行时生成）
├── logs/                       # 日志文件目录（运行时生成，含 danmaku_monitor.jsonl）
├── i18n/                       # 国际化翻译目录（多语言多格式）
│   ├── zh_CN/LC_MESSAGES/      # 简体中文（gettext）
│   │   ├── zh_CN.po           # 中文翻译源（1127 个翻译键；含头部共 1128 条）
│   │   └── zh_CN.mo           # 编译后翻译（运行时必需，随仓库分发）
│   ├── en_US.json              # English (US)（JSON 格式目录）
│   ├── en_GB.json              # English (UK)（英式拼写变体）
│   └── zh_TW.yaml              # 繁體中文（YAML 格式目录，需 PyYAML）
├── ffmpeg/                     # FFmpeg 目录（Windows）
├── node/                       # Node.js 目录（Windows）
├── main.py                     # 命令行入口
├── gui.py                      # GUI 图形界面入口
├── web.py                      # Web 管理面板入口
├── index.html                  # M3U8 视频播放器（独立工具页）
├── msg_push.py                 # 消息推送模块
├── i18n.py                     # 国际化实现
├── build_exe.py                # PyInstaller 打包脚本（CLI/GUI/Web 三入口）
├── requirements.txt            # Python 依赖
├── pyproject.toml             # Python 项目配置
├── Dockerfile                  # Docker 构建文件（多阶段）
├── docker-compose.yaml         # Docker Compose（recorder/web/gui 三服务）
├── .dockerignore               # Docker 构建上下文排除
├── .gitignore                  # Git 排除
├── StopRecording.vbs          # Windows 停止录制脚本
├── CODE_WIKI.md               # 项目架构文档
└── README.md                   # 项目说明文档
```

## ⚙️ 配置说明

### 基础配置 (config/config.ini)

> 同一节内出现重复键不再让整份配置失效：按最后一次取值读取，并落一条点名「节 / 键 / 行号」的告警（经 `src/config_read.py` 容错读取层，2026-10-17 起生效）。

```ini
[录制设置]
# 界面语言：zh_CN | en_US | en_GB | zh_TW（留空跟随系统语言；值支持 zh_cn/zh-CN/en/en-GB/zh-Hant 等写法，自动归一；对应语言文件缺失时回退 en_US）
language =
# 是否跳过代理检测(是/否)
是否跳过代理检测(是/否) = 是
# 是否启用日志文件(是/否)
是否启用日志文件(是/否) = 是
# 启动时清理陈旧字节码缓存：仅当版本号或源码内容变化时清一次（源码没变则零动作）；
# 范围只有程序目录与 src/ 下的 __pycache__，不含 tests/ scripts/ downloads/ 等目录
是否启动时清理陈旧字节码缓存(是/否) = 是
# 直播保存路径(不填则默认 downloads/)
直播保存路径(不填则默认) =
# 主播改名时自动更新 URL_config.ini 并同步重命名录制目录/文件（默认 是）
是否自动更新主播名(是/否) = 是
# 保存文件夹是否以作者区分
保存文件夹是否以作者区分 = 是
# 保存文件夹是否以时间区分
保存文件夹是否以时间区分 = 否
# 保存文件夹是否以标题区分
保存文件夹是否以标题区分 = 否
# 保存文件名是否包含标题
保存文件名是否包含标题 = 否
# 是否去除名称中的表情符号
是否去除名称中的表情符号 = 是
# 视频保存格式 ts|mkv|flv|mp4|mp3音频|m4a音频
视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频 = ts
# 录制画质 原画|超清|高清|标清|流畅
原画|超清|高清|标清|流畅 = 原画
# 自定义画质选项(逗号分隔) - 用户自选画质子集，留空或全部非法时回退引擎内置全集（默认 空）；
# WEB 端增删画质 / GUI 端「切换画质」写回本项，选非默认画质按「画质,直播间地址」写回 config/URL_config.ini
自定义画质选项(逗号分隔) =
# 是否使用代理ip(是/否)
是否使用代理ip(是/否) = 否
# 代理地址
代理地址 =
# 同一时间访问网络的线程数
同一时间访问网络的线程数 = 3
# 最大同时录制数 - 全局并发录制上限，0 为不限制（默认 0）；改值后下一轮检测循环生效
最大同时录制数(0为不限制) = 0
# 循环时间(秒) - 直播状态检测间隔（默认 60）
循环时间(秒) = 60
# 排队读取网址时间(秒)
排队读取网址时间(秒) = 0
# 是否显示循环秒数
是否显示循环秒数 = 否
# 是否显示直播源地址
是否显示直播源地址 = 否
# 分段录制是否开启
分段录制是否开启 = 是
# 是否启用HLS采集(是/否) - 关闭则只走 FLV 等非 HLS 候选
是否启用HLS采集(是/否) = 是
# HLS采集排除平台(逗号分隔) - 命中平台无视「是否启用HLS采集」配置、恒按 FLV 采集
# （平台名须与日志/配置中显示的完全一致，如：斗鱼直播,虎牙直播；留空不排除任何平台）
HLS采集排除平台(逗号分隔) = 虎牙直播
# 是否启用https录制 - 已整合原「是否强制启用https录制」与「是否禁用SSL证书验证(是/否)」：
# 开启 = 流地址以 https 拉流并跳过 SSL 证书校验；关闭 = 流地址以 http 拉流并恢复默认证书校验
# （旧键「是否强制启用https录制」的值会自动迁移继承；TikTok/YouTube 等 https-only 海外平台在关闭时保持原样）
是否启用https录制 = 是
# 禁用SSL证书验证的平台(逗号分隔) - 仅在「是否启用https录制 = 否」（http 模式、需证书校验）时生效。
# FFmpeg 9.0 起 TLS 证书验证默认开启，证书异常平台需在此豁免；启动时会自动追加必需平台
# （虎牙直播 / B站直播），只追加不移除用户手填项
禁用SSL证书验证的平台(逗号分隔) = 虎牙直播,B站直播
# 录制空间剩余阈值(gb)
录制空间剩余阈值(gb) = 1.0
# 视频分段时间(秒)（默认 1800）
视频分段时间(秒) = 1800
# 录制完成后自动转为mp4格式
录制完成后自动转为mp4格式 = 否
# mp4格式重新编码为h264
mp4格式重新编码为h264 = 否
# 追加格式后删除原文件
追加格式后删除原文件 = 是
# 生成时间字幕文件
生成时间字幕文件 = 否
# 是否录制完成后执行自定义脚本
是否录制完成后执行自定义脚本 = 否
# 自定义脚本执行命令
自定义脚本执行命令 =
# 使用代理录制的平台(逗号分隔)
使用代理录制的平台(逗号分隔) = tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit
# 额外使用代理录制的平台(逗号分隔)
额外使用代理录制的平台(逗号分隔) =
# 是否录制弹幕(是/否) - 开启后弹幕落为 SRT 字幕文件，与视频录制同起同停
是否录制弹幕(是/否) = 是
# 是否弹幕监控(是/否) - 仅实时查看弹幕、不写 SRT（与弹幕录制解耦，可单独开启）
是否弹幕监控(是/否) = 是
# 弹幕分片时长(秒) - SRT 分片粒度，建议与「视频分段时间(秒)」一致
弹幕分片时长(秒) = 1800
# 弹幕录制平台(逗号分隔) - 目前支持的 5 个平台
弹幕录制平台(逗号分隔) = 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV
# 单次录制时长上限（秒）；0 表示不限制
单次录制时长上限(秒,0为不限制) = 0
```

### 推送配置 (config/config.ini)

```ini
[推送配置]
# 可选微信|钉钉|tg|邮箱|bark|ntfy|pushplus 可填多个
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

### Cookie 配置 (config/config.ini)

```ini
[Cookie]
# 录制抖音必填：请填入从浏览器 live.douyin.com 复制的有效 cookie（至少包含 ttwid）
# 留空将自动尝试获取访客 ttwid（可能触发风控，建议填写）
抖音cookie =
# 单独指定抖音 ttwid（留空则由 src/ttwid.py 自动获取并进程级缓存）
ttwid =
快手cookie =
tiktok_cookie =
tiktok_guest_cookie =
虎牙cookie =
斗鱼cookie =
yy_cookie =
b站cookie =
小红书cookie =
# 小红书 app 端接口的会话 sid（xy-common-params 头），留空则用内置缺省（可能已过期）
# 优先级：环境变量 XHS_SESSION_SID > 本键 > 内置缺省
xhs_session_sid =
bigo_cookie =
# ... 共 51 个平台 cookie 键，其余详见 config.ini
```

> 访客类 cookie（抖音 ttwid、快手 did 等）由 `src/cookie_cache.py` 以「归一化网址 + 代理」为 key 做进程级共享缓存（默认 30 分钟 TTL），多直播间并发时不会重复拉取触发风控。

### 授权配置 (config/config.ini)

```ini
[Authorization]
# PopkonTV 登录后取得的 token（由账号密码自动登录后写回）
popkontv_token =
```

### 账号密码配置 (config/config.ini)

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

### Web 管理面板配置 (config/config.ini)

```ini
[Web]
# Web 管理面板监听地址（默认仅本机；Docker/LAN 部署再显式改为 0.0.0.0）
web_host = 127.0.0.1
# Web 管理面板端口
web_port = 8000
# 是否启用密码登录（true/false）
web_auth_enable = false
# 访问密码（启用认证时必填）
web_password =
# token 有效期（秒）
web_token_expiry = 86400
# 是否显示控制台窗口（false 时后台运行，日志写入 logs/web_console.log）
web_show_console = true
# 控制台最小化到系统托盘（而非任务栏），仅 Windows 生效；
# 关闭按钮会被禁用，退出请使用托盘图标的「退出程序」
web_minimize_to_tray = true
# 受信任的反向代理来源（逗号分隔）。留空时不解析 X-Forwarded-For；
# 置于 Nginx/Caddy 之后时填入代理 IP，登录限流才能取到真实客户端 IP
web_trusted_proxy =
# 允许的 Host / Origin 白名单（逗号分隔）。仅在把 web_host 绑到 0.0.0.0/:: 且通过域名访问时需要；
# 未列出的多级域名 Host 会被拒绝，用于阻断 DNS 重绑定（attacker.tld → 127.0.0.1）
web_allowed_hosts =
```

> `web_host` 在仓库默认配置中为 `127.0.0.1`（仅本机可访问）。Docker 或需局域网/公网访问时改为 `0.0.0.0`，并务必同时开启 `web_auth_enable` 与 `web_password`。

### GUI 界面配置 (config/config.ini)

```ini
[GUI]
# 界面主题：light | dark | high_contrast（留空跟随系统外观明暗；GUI 侧边栏「界面主题」菜单选择后自动写回）
gui_theme = light
# 界面缩放：自动 | 85 | 100 | 115 | 130 | 150（「自动」按屏幕可用区现算；菜单选择后自动写回）
gui_scale = 自动
# 动效强度：跟随系统 | off | subtle | full（系统「关闭动画」优先于用户选择）
gui_motion = 跟随系统
# 界面字体：留空 = 系统默认（Microsoft YaHei UI）；填字体族名即用之
gui_font =
# 自定义字体文件路径：由侧边栏「导入字体…」写入；字体副本存放在 config/fonts/ 下
gui_font_file =
```

> 字体相关说明：下拉里的预设族按**本机是否已安装**过滤，避免出现「选了没反应」的项；
> 「导入字体…」支持 `.ttf` / `.otf` / `.ttc`（SFNT 容器），`.woff2` / `.woff` 属网页传输格式、
> Tk 在 Windows 下经 GDI 取字体认不了，需先转成 ttf/otf；日志终端与 URL 编辑器固定用等宽字体，
> 不随此项变化（保持字符对齐）。

### 直播间配置 (config/URL_config.ini)

抖音支持以下 5 种直播间/主页地址格式（其余平台格式见下方各平台示例）：

```
# 1) 网页端主播直播间（数字房间号）
https://live.douyin.com/745964462470

# 2) app端主播直播间（分享短链）
https://v.douyin.com/iQFeBnt/

# 3) 抖音号拼接（https://live.douyin.com/ + 抖音号，支持 VR 直播录制）
https://live.douyin.com/yall1102

# 4) app端主播主页（分享短链）
https://v.douyin.com/CeiU5cbX

# 5) 网页端主播主页（用户页地址）
https://www.douyin.com/user/MS4wLjABAAAA3kr2yA4aRD-sjf9cx8xkOH8Di3RjktpKcAvqIetpsF0
```

> 说明：
> - 格式 1/3/5 走网页端接口（支持 VR 直播）；格式 2/4 走 app 端接口
> - 格式 5（网页端主播主页 `www.douyin.com/user/<sec_uid>`）会直接从地址提取 `sec_user_id` 并解析出抖音号，按直播间地址走网页端接口录制，无需经过 app 端探测
> - 格式 4（app 端主页）等短链形态会先探测直播间地址，失败则自动回退到抖音号解析、再走网页端接口录制

```ini
# 指定画质（画质,直播间地址）
超清，https://live.douyin.com/745964462470

# 指定画质和主播名（画质,直播间地址,主播:名称）
高清，https://live.bilibili.com/123456，主播: B站主播

# 注释直播间（在地址前加 #）
# https://live.douyin.com/123456789
```

### 环境变量配置

| 变量名 | 说明 | 示例 |
| --- | --- | --- |
| `PYTHONUNBUFFERED` | 实时输出日志 | `1` |
| `PYTHONDONTWRITEBYTECODE` | 不生成 .pyc 文件 | `1` |
| `PYTHONIOENCODING` | Python 输出编码 | `utf-8` |
| `TZ` | 时区设置 | `Asia/Shanghai` |
| `TERM` | 终端类型 | `xterm-256color` |

## 🎬 使用说明

### 命令行模式

```bash
python main.py
```

### GUI 图形界面模式

```bash
python gui.py
```

GUI 功能（侧边导航 5 页）：
- 📊 控制台 - 录制状态总览、启停控制
- 🎯 画质监控 - 实时检测各直播间实际画质是否与设置一致
- 💬 弹幕监控 - 实时查看各房间弹幕流，支持按房间/类型过滤
- 📝 URL 配置 - 直播间地址管理
- 📋 运行日志 - 子进程日志查看

侧边栏另提供**外观**（浅色/深色/跟随系统）与**语言 Language**（简体中文 / English (US) / English (UK) / 繁體中文）选择器，切换语言即时生效并写回 `config.ini`，无需重启。

系统托盘图标支持最小化到托盘后台运行。

### Web 管理面板模式

```bash
python web.py
```

启动后浏览器访问 `http://localhost:8000`。

功能：
- **仪表盘**：实时查看监测/录制数、错误数、磁盘剩余、录制中列表、日志流（SSE 推送）
- **直播间管理**：在线增删改查直播间地址、启用/禁用（自动热加载到录制主循环）
- **配置编辑**：在线编辑 config.ini 各项（录制设置/推送/Cookie 等），敏感配置项脱敏
- **文件浏览**：浏览 downloads 目录并下载录制文件
- **实际画质展示**：录制表格显示"设置画质/实际画质"，降级时标红高亮
- **弹幕查看**：读取弹幕监控枢纽快照，实时展示各房间弹幕事件
- **语言切换**：顶栏语言选择器，四语即时切换（写回配置并热切换进程内翻译，无需重启）

主要 API 路由（均需 Token，认证关闭时除外）：

| 路由 | 方法 | 功能 |
| --- | --- | --- |
| `/api/login` | POST | 密码登录，返回 Token |
| `/api/status` | GET | 录制状态（含实际画质） |
| `/api/status/stream` | GET | 录制状态 SSE 流 |
| `/api/rooms` | GET/POST/PUT/DELETE | 直播间增删改查 |
| `/api/rooms/toggle` | POST | 启用 / 禁用直播间 |
| `/api/config` | GET/PUT | 读取 / 修改配置 |
| `/api/language` | GET/PUT | 查询 / 切换界面语言 |
| `/api/files`、`/api/files/download` | GET | 录制文件浏览与下载 |
| `/api/logs`、`/api/logs/stream` | GET | 日志查询 / SSE 实时推送 |
| `/api/danmaku` | GET | 弹幕监控快照 |

Web 模式与命令行模式共用同一录制引擎与配置文件，直播间地址的增删改会自动被录制主循环热加载。

后台运行模式：将 `web_show_console` 设为 `false`，Windows 下会隐藏控制台窗口，日志写入 `logs/web_console.log`，程序完全后台运行。

Windows 下控制台默认「最小化到系统托盘」（`web_minimize_to_tray = true`）：点击最小化后窗口不在任务栏显示，而是收起到系统托盘，双击托盘图标即可恢复；标题栏关闭按钮已禁用，需从托盘图标菜单的「退出程序」退出。

> ⚠️ **安全提示**：默认仅监听 `127.0.0.1` 且未启用认证；若为 Docker / 局域网 / 公网访问改绑 `0.0.0.0`，必须同时开启 `web_auth_enable` 并设置强密码。

### 录制格式推荐

- **长时间录制**：推荐使用 `ts` 格式，实时写入，断电不易损坏
- **短时间录制**：推荐使用 `mp4` 或 `mkv` 格式，录制完成后直接可用
- **仅音频录制**：推荐使用 `mp3` 或 `m4a` 格式

### 画质说明

| 画质代码 | 中文名 | 说明 |
| --- | --- | --- |
| OD | 原画 | Original Definition，最高画质 |
| BD | 蓝光 | Blu-ray，超高清 |
| UHD | 超清 | Ultra HD |
| HD | 高清 | High Definition |
| SD | 标清 | Standard Definition |
| LD | 流畅 | Low Definition，最低画质 |

支持平台：抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC。当平台实际下发画质低于设置画质时，会自动告警并标记。

### 采集方式选择（HLS/FLV）

录制拉流源在 HLS（m3u8，逐段拉取）与 FLV（单条长连接）之间自动选择：默认优先 HLS、校验不可达时按序回退 FLV，最后兜底 `record_url`。由两个配置项共同控制：

| 配置项 | 作用 |
| --- | --- |
| `是否启用HLS采集(是/否)` | 全局开关：开启（默认）时优先使用 HLS 源，不可达或源不存在时回退 FLV；关闭则所有平台只走 FLV 等非 HLS 候选 |
| `HLS采集排除平台(逗号分隔)` | 平台级排除列表：命中平台**无视全局开关、恒按 FLV 采集**（等效于仅对该平台关闭 HLS 采集，HLS 源不参与候选与回退） |

- **适用场景**：整体偏好 HLS 录制（HLS 逐段拉取免疫单条长连接被 CDN 掐断），但个别平台的 HLS 源不稳定或被风控，希望仅该平台强制走 FLV 时，将其加入排除列表即可——无需为此关闭全局 HLS 开关
- **填写格式**：平台名须与日志/配置文件中显示的**完全一致**（如 `斗鱼直播`，不能简写为 `斗鱼`）；多个平台逗号分隔（中英文逗号均可），如 `斗鱼直播,虎牙直播`；留空（默认）不排除任何平台，行为与旧版本完全一致
- **优先级语义**：排除列表优先于全局开关——即使「是否启用HLS采集(是/否) = 是」，命中平台也只走 FLV；列表外平台不受任何影响，仍按全局配置 HLS 优先
- **边界行为**：排除平台若解析结果仅有 HLS 源且无 FLV/record_url 可回退，本轮放弃录制并输出告警（日志会提示「可将该平台移出排除列表恢复 HLS 采集」）；h265 编码的 FLV 源不再触发切换 HLS（h265 FLV 录制自动改存 TS 格式的逻辑不受影响）
- **热更新**：主循环每轮重读配置，修改保存后无需重启程序，下一轮监测即生效

### 弹幕录制与弹幕监控

弹幕功能由两个**相互解耦**的开关控制，可单独或同时开启：

| 配置项 | 作用 |
| --- | --- |
| `是否录制弹幕(是/否)` | 弹幕落盘为 SRT 字幕文件，与视频录制同起同停 |
| `是否弹幕监控(是/否)` | 仅实时查看弹幕，不写 SRT（GUI「弹幕监控」页 / Web `/api/danmaku`） |
| `弹幕分片时长(秒)` | SRT 分片粒度，建议与「视频分段时间(秒)」一致 |
| `弹幕录制平台(逗号分隔)` | 启用弹幕的平台白名单 |

- **支持平台（5 个）**：抖音直播、斗鱼直播、虎牙直播、B站直播、TwitchTV
- **输出文件**：SRT 与视频分片一一对应，命名为 `{基础名}_{分片序号:03d}.srt`（如 `_000.srt` 对应 `_000.ts`）；未分段时为 `{基础名}.srt`。时间轴以单调时钟为基准，与 ffmpeg `segment -reset_timestamps` 的 PTS 对齐，可直接被播放器加载
- **弹幕连接直连**：弹幕 WebSocket 显式不跟随系统代理，避免 SOCKS 代理环境下连接即断
- **监控边车日志**：弹幕监控事件同时写入 `logs/danmaku_monitor.jsonl`（5MB 轮转）
- 抖音弹幕在 Cookie 为空时会自动获取访客 ttwid；B站弹幕会自动获取真实 buvid（登录 cookie → spi 接口 → 首页 Set-Cookie → 随机兜底）

### 主播名自动更新

开启 `是否自动更新主播名(是/否)`（默认「是」）后，程序在每轮解析到最新主播名时，若与 `URL_config.ini` 中记录的名称不同，会自动完成两件事：

1. **重命名文件系统**：`{保存路径}/{平台}/{旧主播名}` → 新主播名目录；递归重命名目录树内所有以 `{旧名}_` 开头的录制产物（TS / FLV / SRT / 字幕）及以 `_{旧名}` 结尾的标题目录；若新名目录已存在则逐项合并移入（兼容主播改回曾用名）
2. **回写配置文件**：按 URL 段级精确匹配只替换该行的主播名字段，完整保留画质段、`#` 注释前缀与行尾换行风格；操作幂等

安全约束：

- 检测点位于「解析直播数据之后、录制启动之前」，此时该线程必然不在录制中，天然避开 ffmpeg 文件占用窗口
- **先文件系统、后配置文件，两者全部成功才切换本轮使用名**；任一失败则保持旧名并在下轮轮询自动重试
- 个别文件被后台转码/播放器占用时仅告警跳过，不阻塞整体
- 自动跳过自定义流地址（其主播名含每轮随机 UUID）与清洗后为空白的昵称
- 关闭该开关即保持手动名称不变

### 多语言与界面切换

内置四套翻译目录，加载时按 `gettext .mo → <lang>.json → <lang>.yaml` 依次探测：

| 语言码 | 显示名 | 目录文件 |
| --- | --- | --- |
| `zh_CN` | 简体中文 | `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` |
| `en_US` | English (US) | `i18n/en_US.json` |
| `en_GB` | English (UK) | `i18n/en_GB.json` |
| `zh_TW` | 繁體中文 | `i18n/zh_TW.yaml` |

- 配置键 `language`：留空跟随系统语言；取值支持 `zh_cn` / `zh-CN` / `en` / `en-US` / `en-GB` / `zh-Hant` / `zh_CN.UTF-8` 等写法，自动归一化到规范语言码；键值不可识别或对应语言文件缺失时回退 `en_US`
- **热切换**：GUI 侧边栏语言选择器、Web 面板顶栏语言选择器、直接编辑 `config.ini` 三种途径均可切换；命令行主循环每轮检测配置变化并即时重载翻译，**无需重启进程**（录制中的 ffmpeg 子进程不受影响）
- 翻译不再依赖 `LANG` / `LANGUAGE` 环境变量（Windows 普遍未设置）
- `zh_TW.yaml` 需要 `PyYAML`；缺失时仅损失该语言，其余格式不受影响

### 停止录制

- **Windows**：执行 `StopRecording.vbs` 或在命令行按 `Ctrl+C`
- **Linux/macOS**：在命令行按 `Ctrl+C`
- **Docker**：执行 `docker-compose stop`

### 注意事项

1. 如需录制 TikTok、SOOP(原AfreecaTV) 等海外平台，请在配置中开启代理
2. 长时间挂机建议将循环时间设置长一些（如 60 秒），避免请求频繁被封 IP
3. 直播结束后会自动保存文件，无需手动停止
4. 如遇录制的视频文件损坏，建议使用 `ts` 格式录制
5. 录制抖音需要填写有效的 cookie（至少包含 ttwid），否则可能触发风控
6. 部分平台需要 Node.js 环境运行 JavaScript 签名脚本，Windows 下会自动安装

## 🐋 Docker 部署

### 前置要求

- 已安装 [Docker](https://docs.docker.com/get-docker/)
- 已安装 [Docker Compose](https://docs.docker.com/compose/install/)

### 快速启动

```bash
# 1. 克隆项目
git clone https://github.com/y123ao6/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# 2. 编辑配置文件
# 在 config/URL_config.ini 中添加直播间地址

# 3. 启动容器（默认命令行录制模式）
docker compose up -d

# 4. 查看日志
docker compose logs -f
```

### 拉取预构建的多架构镜像（GHCR）

发布工作流 `.github/workflows/docker-publish.yml` 在每次推 `v*` tag 时，由原生 amd64 与 arm64 两个 runner
各构建并推送一层，再按 manifest digest 合成多架构清单——**同一条 `docker pull` 在 x86_64 与 arm64 主机上
都会拿到本机架构那一层**：

```bash
# <owner> 换成实际持有该镜像的 GitHub 账号名（GHCR 命名空间一律小写）
docker pull ghcr.io/<owner>/douyin-live-recorder:latest
docker run -d -v ./config:/app/config -v ./downloads:/app/downloads \
  -v ./logs:/app/logs -v ./backup_config:/app/backup_config \
  ghcr.io/<owner>/douyin-live-recorder:latest
```

- 标签形态：`latest` 与 `vX.Y.Z`；`latest` 只随 `v*` tag 产出，不开放手动触发覆盖。
  两个分架构 tag（`:vX.Y.Z-amd64` / `-arm64`）属合成前的中间产物，当前不会自动清理。
- 匿名拉取要求该 GHCR 包的可见性为 **public**——那是仓库设置层面的一次性人工动作。
- 与 `docker-compose.yaml` 里的 `image: y123ao6/douyin-live-recorder:latest` **刻意不同源**（`gui` 服务另用 `:latest-gui`，见下方「切换运行模式」）：compose 走
  `pull_policy: build` 就地构建（不拉 registry 上的同名镜像），上面「快速启动」的说明保持不变；
  要用 GHCR 预构建镜像请按上面的 `docker run`，arm64 主机走 compose 就地构建同样可行。

### 切换运行模式

`docker-compose.yaml` 已内置三个服务（recorder / web / gui），通过 profile 切换，无需修改文件：

```bash
# 命令行录制模式（默认，不占用端口）
docker compose up -d

# Web 管理面板模式（映射 8000 端口，浏览器访问 http://localhost:8000）
docker compose --profile web up -d

# GUI 模式（需 X11 显示环境，先在宿主机执行 xhost +local:）
docker compose --profile gui up -d
```

> ℹ️ 镜像分两种依赖形态：`recorder` / `web` 用的默认镜像**不装** GUI 窗口层依赖（PySide6 解压后
> 本机实测 647.56MB，而这两个服务在屏蔽它后导入链完整，装进来也用不上）；`--profile gui` 会按
> `--build-arg INSTALL_GUI=true` **单独构建另一枚 tag**（`...:latest-gui`）并同时补装 Qt 运行库，
> 因此首次启用 GUI 模式会多一次构建，也不会覆盖 recorder / web 正在使用的镜像。

> ⚠️ Web 模式注意：`web.py` 默认监听 `127.0.0.1`，容器内必须在 `config/config.ini`
> 的 `[Web]` 节设置 `web_host = 0.0.0.0` 才能从宿主机访问；同时建议开启
> `web_auth_enable = true` 并配置 `web_password`。

### 数据挂载

```yaml
volumes:
  - ./config:/app/config:rw          # 配置文件目录（必需）
  - ./downloads:/app/downloads:rw    # 录制文件下载目录（必需）
  - ./logs:/app/logs:rw              # 运行日志目录
  - ./backup_config:/app/backup_config:rw  # 配置备份目录
```

### 端口映射

仅 `web` 服务（Web 管理面板模式）映射端口，`recorder` / `gui` 服务不监听任何端口：

```yaml
ports:
  - "127.0.0.1:8000:8000"   # Web 管理面板端口（仅 --profile web 时生效，默认只暴露给宿主机本地）
```

### 环境变量

> 与上文「环境变量配置」同一张表（`TZ` / `PYTHONUNBUFFERED` / `PYTHONDONTWRITEBYTECODE` / `PYTHONIOENCODING` / `TERM`），compose 已按该表注入，此处不重复列举。

### Docker 镜像特性

- **多阶段构建**：builder 阶段安装依赖到虚拟环境，runtime 阶段精简镜像
- **非 root 用户**：使用 `recorder` 用户运行，提升安全性
- **健康检查**：自动检测 `main.py` 或 `web.py` 进程是否存活
- **资源限制**：默认限制 2 CPU / 2G 内存（可在 docker-compose.yaml 调整）
- **日志轮转**：单文件 50MB，最多保留 3 份
- **内置 Node.js 24 LTS**：用于运行 JavaScript 签名脚本

## 🛠️ 开发指南

### 环境要求

- Python >= 3.14
- FFmpeg (Windows 版启动时自动从官方源下载；Linux 依次为 `yum` → `apt` → 官方月末构建直下、macOS 走 Homebrew，
  包管理器路线需 root/管理员，三条都失败时手动安装)
- Node.js (Windows 下自动下载并解压到程序目录；Linux 按发行版走 `yum`（RHEL 系，需 EPEL）或 `apt`、macOS 走 Homebrew，
  包管理器路线需 root/管理员，失败时手动安装)

### 安装开发依赖

```bash
# 使用 uv（推荐）
uv sync --dev

# 或使用 pip
pip install -r requirements.txt
pip install .[dev]
```

### 代码规范

```bash
# 格式化代码（line-length = 120）
black .

# 排序导入
isort .

# 类型检查（CI 以 mypy 为准；不带路径，范围由 pyproject.toml [tool.mypy].files 定义）
mypy

# 类型检查（本地增强，可选）：basedpyright
# 已在 pyproject.toml 配置 [tool.basedpyright]，venvPath 指向工作区 .venv（相对路径，可移植）
# 首次需创建并安装依赖：python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
basedpyright

# 运行测试
pytest
```

> **注释规范**：模块/函数说明统一使用 `#` 行注释，不使用三引号 `"""` 文档字符串；功能性多行字符串字面量（模板/SQL）改用单引号 + 换行拼接而非 `"""`。

> **五工具质量门禁**：本项目以 `mypy`（src + tests）/ `basedpyright`（tests）/ `pytest`（0 warnings）/ `black --check .` / `isort --check-only .` 五工具联合作为质量门禁，CI 全绿为合入前提。当前基线：**974 passed / 2 skipped / 0 warnings**。

> **测试说明**：`tests/test_web_api.py` 的符号链接相关用例（`TestListFiles::test_broken_symlink_skipped` / `test_symlink_outside_skipped`）在无法创建真实符号链接的环境（未开启开发者模式的 Windows、部分沙箱）会自动 `pytest.skip`，属正常现象，不代表代码缺陷。

### 项目文档

- [CODE_WIKI.md](CODE_WIKI.md) - 项目架构文档（详细的模块说明、依赖关系、设计模式）

### Web/接口冒烟测试

项目内置通用、零依赖的 Web/接口冒烟测试工具 `scripts/smoke_test.py`（纯标准库，无需安装第三方包），可对 Web 管理面板等**运行中 HTTP 接口**做轻量探活。

```bash
# 检查本机 Web 管理面板（默认 127.0.0.1:8000，示例配置见 scripts/smoke_web.json）
python scripts/smoke_test.py -c scripts/smoke_web.json

# 生成 HTML 报告
python scripts/smoke_test.py -c scripts/smoke_web.json -r smoke_report.html -f html
```

- 配置驱动（JSON）：`url` / `method` / `expected_status` / `timeout` / 请求头 / 请求体 / 响应应包含文本 / 期望 JSON 字段
- 支持 `base_url` 前缀拼接；控制台 / JSON / HTML 三种报告；失败时退出码非 0（可接入 CI）
- 与 `build_exe.py --smoke`（打包产物冒烟）不同，本工具针对**运行中的 HTTP 接口**做探活，两者互补
- 默认用例 `scripts/smoke_web.json` 探活 Web 面板 `/`（首页 200）与 `/health`（`{"status": "ok"}`，由 `src/web_api.py` 提供的公开探活端点，不受 `web_auth_enable` 支配）
- **已接入 CI**：`.github/workflows/ci.yml` 的 `test` job 在 pytest 之后受控启动 `python web.py`，就绪后跑 `scripts/smoke_web.json` 冒烟（经 `.github/actions/retry` 处理网络抖动、失败保留 `logs/web-smoke-*` 工件并使 job 变红），补齐「面板进程能否真正监听并应答」这条 TestClient 覆盖不到的链路

### 添加新平台支持

**视频录制平台：**

1. 在 `src/spider.py` 中添加平台流地址解析函数（参考现有平台实现）
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑（`PLATFORM_HOST` 列表和录制分支）
4. 更新 `README.md` 和 `CODE_WIKI.md`

**弹幕录制平台（如需支持弹幕）：**

1. 在 `src/platforms/` 下新建 `<平台>.py`，继承 `src/base.py` 的 `DanmakuBase`，实现连接/鉴权/消息解析
2. 在 `src/__init__.py` 的弹幕平台注册表中登记（平台名与 `main.py` 的 platform 标识一致），由 `get_danmaku_class` / `get_danmaku_collector` 工厂解耦创建
3. 在 `main.py` 的弹幕录制接线处补充平台分支（构造 `record_danmaku_args` 并传入 `check_subprocess`）
4. 更新 `README.md` 和 `CODE_WIKI.md`

> 注：弹幕子系统与 `src/spider.py`（视频流地址解析）是平行解耦的两套抽象，`spider.py` 不 import `src/platforms`。

## ❓ 常见问题

**Q: 录制时提示 "缺少 ffmpeg 无法进行录制"**

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows：full 版运行包已自带 ffmpeg，无需安装；
# lite 版 / 单文件版若自动安装失败，按「快速开始 → 手动安装 ffmpeg（Windows 用户指南）」放置
# 为 <程序目录>\ffmpeg\ffmpeg.exe（+ ffprobe.exe）即可，不要留在 ffmpeg\bin\ 子目录下。
```

**Q: Apple Silicon（M 系列芯片）Mac 上实际用的是哪一份 ffmpeg？**

发布包（full 版）内置的 macOS ffmpeg 是上游的 **x86_64 静态构建**（ffmpeg.org 官方只发布
「Static builds for macOS 64-bit」，**不提供 arm64 构建**），在 Apple Silicon 上经 **Rosetta 2**
转译执行。为避免它遮蔽用户自己安装的原生构建：当「macOS + arm64 + 系统 PATH 上已有另一份
ffmpeg」三条同时成立时，程序**优先使用系统那份**（例如 `brew install ffmpeg` 装上的原生
arm64 构建），不再把包内 `ffmpeg/` 目录前置到 `PATH`；其余情况（Intel Mac、Windows、Linux、
系统里没有 ffmpeg、或 PATH 上探到的其实就是包内那一份）维持原样，仍使用包内那份。
单文件版脚本 `douyin_live_recorder_standalone.py` 采用同一判据，只是表现为「`find_ffmpeg()` 直接
返回系统那份的路径」而不是调整 `PATH`。

确认当前生效的是哪一份：

```bash
ffmpeg -version          # Homebrew 安装的会带 --prefix=/opt/homebrew/...（Apple Silicon 原生）
                          # 包内的 evermeet 静态构建没有该前缀
which ffmpeg              # 指向包内 ffmpeg/ 目录 = 用的是包内那份
```

或查看 debug 日志（`config.ini` 中 `是否启用日志文件 = 是` 时写入 `logs/streamget.log`）里的
「FFmpeg PATH 优先级」一行，它会明确写出「让位于系统原生 ffmpeg <路径>」还是「仍前置包内目录 <路径>」。

> Docker 镜像不受此策略影响：镜像内的 ffmpeg 由 apt 安装，Apple Silicon 上按本机架构构建/运行
> Linux arm64 容器，本来就是原生执行。

**Q: 提示 "缺少 Node.js" 或 "execjs" 相关错误**

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_24.x | bash -
sudo apt-get install -y nodejs

# macOS
brew install node

# Windows
# 程序会自动下载安装到 node/ 目录
```

**Q: 提示 "IP 被禁止，请更换设备或网络"**

- 检查是否开启了代理
- 降低循环监测频率
- 等待一段时间后再尝试

**Q: 抖音风控无法获取数据**

- 在 `config.ini` 的 `[Cookie]` 节填入从浏览器 `live.douyin.com` 复制的有效 cookie（至少包含 `ttwid`）
- 降低循环监测频率（默认循环时间 120 秒已较保守，可酌情调大）
- 更换 IP 或使用代理
- 排查要点（实测结论）：
  - 抖音风控的典型信号是 **HTTP 200 + 空响应体**，而非 4xx 错误码；日志里看到 `web/enter` 返回 `status_code=10002 / unknown error` 后自动回退 HTML 抓取是**正常的容错链路**，不代表录制失败
  - 请求抖音接口必须使用**桌面端 User-Agent**，旧版移动端 UA 会被静默限流（返回空 body）
  - 主页类链接（格式 4/5）请直接填写完整地址；`iesdouyin.com/share/user/` 旧路径已变为反爬壳页，请勿使用

**Q: HLS 校验失败日志空白，总是回退到 FLV**

- 现象：日志出现 `get_response_status 校验失败（判定为不可达）: `（消息空白）后紧跟 `HLS URL validation failed, falling back to FLV`，且反复出现
- 原因（已修复于 2026-08-05）：
  - Windows 下 `socket.timeout` / `TimeoutError` 的 `str()` 为空，导致异常日志显示为空白，无法判断是超时、连接被拒还是证书问题
  - 流地址校验函数原先静默吞掉所有异常（`except Exception: return False`），回退 FLV 时无任何原因可查
  - m3u8 源 HEAD 探测原先未覆盖 404（抖音等 CDN 常对 HEAD 返回 404 而 GET 可正常拉流），且从 HLS 源选择到校验调用**未透传代理**，导致 TikTok 等需代理平台直连校验超时误判不可达
- 修复后表现：异常日志会带 URL 与异常类型；所有失败路径记录详细警告（含状态码 / content-type）；m3u8 HEAD 非 2xx（**含 404**）一律补 `Range: bytes=0-0` GET 探测；HLS 源选择正确透传代理。重新运行后若仍回退，日志会直接给出真实原因（如 `ConnectTimeout`、`HEAD=404, Range-GET=403`），此时多为 CDN 域名被墙或主播流地址失效等环境问题，而非代码误判

**Q: 录制的视频文件损坏**

- 推荐使用 `ts` 格式录制
- 检查磁盘空间是否充足
- 检查网络是否稳定

**Q: 如何只推送开播通知不录制？**

在 `config.ini` 的 `[推送配置]` 节设置 `只推送通知不录制(是/否) = 是`

**Q: Web 面板忘记密码怎么办？**

直接编辑 `config/config.ini` 中的 `web_password` 项，修改后重启 `web.py` 即可。密码变更后所有现有 Token 会自动失效，需重新登录。

## ❤️ 贡献者

<a href="https://github.com/y123ao6/DouyinLiveRecorder/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=y123ao6/DouyinLiveRecorder" />
</a>

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，欢迎 Star 和 Fork！

## ⏳ 更新日志

### v4.5.0 (2026-10-02 ~ 2026-10-17) — GUI 窗口层迁移 PySide6（Qt6）与界面现代化阶段4~6 收尾 / 移动端与短链平台接入（b23.tv / m.douyu.com / hy.fan / 小红书四类归一）/ Linux arm64 ffmpeg 与 GHCR 多架构镜像 / 启动期字节码缓存清理与发布链在线来源层 / config.ini 重复键容错读取层与 i18n 三批机检 / 全工作区代码审查与两轮元数据对账

> 本版本（v4.5.0，2026-10-02 ~ 10-17）是一次「GUI 全面现代化 + 平台接入扩张」周期：① **窗口层由 tkinter/ttk 迁到 PySide6（Qt6）**，新增 `src/gui_qt/`，令牌与 QSS 单一事实源、控制器层可离屏单测，打包侧靠 `QT_BLOAT_FILES` 剪除 Qt 死重；② **界面现代化阶段4~6 收尾**（CTk → ttk、`customtkinter` 摘除、字号 / 缩放 / 动效）；③ **平台接入扩张**（三类移动端短链 + 小红书四类链接归一，Linux arm64 与 GHCR 多架构补齐）；④ **config.ini 同节重复键不再整份失效**（新增 `src/config_read.py`）。**存在破坏性变更（GUI 实现与依赖面）**，见下方专节。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**✨ 新增功能 / 改进**
- **GUI 窗口层迁移 PySide6（Qt6）**：新增 `src/gui_qt/`（16 文件 4189 行，含 `pages/` 五页），`gui.py:main()` 委托 `src.gui_qt.app.main()`（tkinter 实现留作 `_legacy_main()`）。令牌与 QSS 单一事实源在 `theme.py`，线程模型换轨 Qt Signal/Slot + `QTimer`；控制器层无 Qt 布局代码，`QT_QPA_PLATFORM=offscreen` 即可离屏单测。
- **界面现代化阶段6（字号 / 缩放 / 动效）**：新增 `src/ui_scale.py`（语义字号七档 caption 10 → display 28、间距栅格、缩放档位、小屏自动降档）与 `src/ui_motion.py`（off/subtle/full，系统「关闭动画」优先）。缩放只改字号与间距，点值按 `factor ** 0.6` 温和增益（等宽再乘 0.9）。
- **GUI 视觉语言改版（品牌蓝 → 暖赭橙）**：`src/ui_theme.py` light/dark 两表换 16 个槽位，`gui.py` 的 `Colors` 同批换值；主色 `#B5573A`（白字 4.78；原型 `#C96442` 实测 3.90 不达 AA），深色 hover `#A8502F`。`high_contrast`、`TERMINAL_*` 与语义色槽未动。
- **GUI 自选字体**：新增 `src/ui_fonts.py`（SFNT name 表解析 + GDI 私有字体注册，拒收 woff2）；切族在同一 `configure` 完成、不重建控件树。可用性判据是让 Tk 解析一次并与缺失族名的兜底结果比对（`AddFontResourceExW(FR_PRIVATE)` 成功但 `tkfont.families()` 列不到私有字体）。
- **GUI 静态标签接入 i18n**：新增 `src/ui_i18n.py`（`T()` + `retranslate_all` + `apply_title`），静态标签 54 处、运行时串约 60 处接线，语言切换整窗回填不重建；`src/web_api.py` 27 处展示类文案经 `tr()`（稳定机器码 detail 不翻）。
- **移动端与短链平台接入**：B站 `b23.tv`（纯数字直取 + 短码 302 跟随）、斗鱼 `m.douyu.com`（白名单 + 房间号归一）、虎牙 `hy.fan`（新 resolver + 301 跳转归一）、小红书 `parse_xhs_live_url`（`/livestream/<房间ID>` / 动态路径 / `xhslink` / 分享参数四类）。归一后复用既有取流链，`record_host` 仍取短链域以便熔断分桶计数。
- **Linux arm64（aarch64）ffmpeg 三段落地**：发布矩阵新增 `ubuntu-24.04-arm`（四平台 × lite/full = 8 zip）；新增 `src/ffmpeg_linux_download.py`（官方 digest 优先、TOFU 降级、两趟安装）作无 root 兜底；新增 `docker-publish.yml`，原生双 runner 各出一架构层并按 digest 合成 manifest（仅 `v*` tag）。
- **启动期字节码缓存清理**：新增 `src/startup_cleanup.py`——正向白名单扫描根、基线 = `sha256(相对路径 + 字节)` + 版本号、落 `logs/.pyc_stamp`，只在源码或版本变过时回收一次（默认开，可关）。
- **发布链运行时钉定「在线来源层」**：`build_exe.py` 新增三态开关 `DLR_RUNTIME_PIN_SOURCE`（off/verify/adopt，默认 off 不发请求）；`adopt` 仅对「清单独立认证」（`trust=signed` 且验签通过）开放，在线值须过 64 位小写十六进制形状关。`_PINNED_RUNTIME_SHA256` 未改，默认行为与引入前一致。

**🐛 修复的问题**
- **config.ini 同节重复键让整份配置失效**：`[录制设置]` 同名键落两行时 `RawConfigParser()`（strict 默认 True）抛 `DuplicateOptionError`，一个键都读不出（`import main` 即崩、GUI 每 10s 报错）。新增 `src/config_read.py`（`tolerant_config_parser` / `find_duplicate_options` / `warn_duplicate_options`），接线 10 处读取点，缺键补写保持幂等。
- **Qt 等宽字体族名告警**：`QFont` 族名位只收单个 family，`QFont("Consolas, Menlo, Courier New, monospace")` 在未装 Consolas 的机器按 `styleHint=Monospace`（枚举 7）落进 `Terminal`，打出 `CreateFontFaceFromHDC() failed` 与 `setPointSize(-1)`。新增 `fixed_font()` 按候选取本机首个命中族名。
- **`src/ui_fonts.py` 两处缺陷**：① 复制失败被 `except Exception: return None` 吞掉且零日志 → 先落带 `{type_name}` / `{err}` 的 warning；② `_safe_filename` 不处理 Windows 保留设备名（`CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`），按首个点之前的基名大小写不敏感比对并加 `_` 前缀。
- **GUI 右边框裁切**：三条长提示初始 `wraplength=0` 把 `winfo_reqwidth()` 撑到 1248 > geometry 1120，而 grid 对「需求宽 > 分配宽」是裁切而非收缩。修法三段：抬首窗几何消首帧赤字、压到档位最小宽读出「收缩地板」后只抬 `minsize` 到地板、尺寸 clamp 到 `SCREEN_FILL_CEILING`。
- **小红书离线轮拿不到主播名**：改读 `liveStream.roomData.hostInfo.nickName`（实测 `liveStatus="end"` 时仍存在）；旧实现只在开播态抠 `roomInfo.deeplink`，等待开播的每一轮都误判失败，取不到时用 `小红书_<room_id>` 兜底。
- **斗鱼房间号提取两个边界洞**：旧正则未锚定参数边界（`?xyzrid=123` 误命中）且把尾斜杠与后续路径带进房间号（`/8751648/`）。改走 `urlsplit` 在解析层剥掉 scheme / 尾斜杠 / query / fragment；错误提示为 `i18n.tr` 常量模板且链接先过 `mask_credentials()`。
- **`CODE_REVIEW_2026-10-02` 整改收尾**：补 L-04（`shopee` / `花椒直播` 缺 `platform_cookie` 映射）与 L-05（删模块级死全局）；修正整改自引入的 4 类缺陷——`except Exception:` 仍引用 `type(e)` 的 `NameError`、`mask_credentials` 收 tuple 的 `TypeError`、日志刷新链复位点，以及裸真值把 `"0"` 误判私有（改走 `parse_config_bool`）。
- **i18n 三处**：Qt 侧栏 5 条「按名 `tr()`」msgid 缺失（Qt 用两空格形态、目录只有三空格形态）→ 四目录各 +5 条并存；9 处 Qt 按钮图标被 `set_text` 打回裸文本 → 构造标签与 `T()` 同 msgid、复用既有键（零新增）；21 处中文 raise 文案在产生点接 `tr()`（去重 16 条 msgid）。
- **签名脚本钉定表尾字节漂移**：pre-commit 的 `end-of-file-fixer` 给 `src/javascript/` 下 4 份脚本各追加换行，而 `_check_js_hash` 按原始字节求 SHA256，四条全失配；按拍板重算钉定表（`migu.js` 本就带尾换行，未动）。

**⚠️ 破坏性变更 / 行为变化**
- **`customtkinter` 整体摘除（阶段4~5）**：控件层 CTk → ttk，新增 `src/ui_kit.py`（六个兼容工厂 + `DataTable`），配色由 `ui_theme` 注册的 ttk 变体派生、「界面主题」成为唯一明暗入口；`CTkToplevel` → `tk.Toplevel`、`CTkFont` → 负数点值 `tkfont.Font`，存根删除。兼容契约逐字保持（`import gui` 无头导入、录制链一行不动）。
- **GUI 窗口层换轨 PySide6**：`gui.py:main()` 委托 `src.gui_qt.app.main()`，tkinter 实现留作 `_legacy_main()`；`packages` 增列 `src.gui_qt` 与 `src.gui_qt.pages`（显式 packages 不递归发现，漏列会让 `douyin-recorder-gui` 入口 `ModuleNotFoundError`）。
- **镜像默认不装 GUI 依赖**：`Dockerfile` 新增 `ARG INSTALL_GUI=false`——阶段1 按行首剔除 `pyside6` 后再装，阶段2 仅 true 时补 Qt 运行库；依据是「PySide6 解压 647.56MB，屏蔽后 `import main` / `import web` 仍成功」。过滤只在镜像侧，compose 的 `gui` 服务另用 `:latest-gui` tag。
- **`[tool.mypy].exclude` 目录名锚定**：该字段是路径子串正则，裸 `"ffmpeg"` / `"node"` 曾把 12 个文件（`src/ffmpeg_*`、`tests/test_ffmpeg_*`、`node_install`）排除在无参 mypy 门禁外；改 `(^|/)ffmpeg/` 与 `(^|/)node/` 后首次进门禁并暴露 8 处存量标注错误（已修）。
- **CI 真窗用例由 skip 转为真实执行**：test job 的 pytest 改 `xvfb-run -a` 包裹并加装 xvfb，另加「Tk 开显示」兜底步骤（xvfb 失效当场红，防真窗用例静默消失）。

**📦 依赖变更**
- **运行时依赖新增 `PySide6>=6.12.0`**：随窗口层迁移加入（摘除 `customtkinter` 后 20 条 → 21 条），下界 6.12 为实测支持 Python 3.14.8 的最小版；`uv.lock` 与 egg-info 经 `sync_metadata.py` 重生成。`pystray` / `Pillow` 保留（Web 托盘 `src/web_tray.py` 仍走 pystray）。
- **移除 `customtkinter`**：`requirements.txt`、`pyproject.toml`（运行时清单 + `.[gui]`）、`typings/customtkinter/` 同批摘除；`build_exe.py` 移除 `collect_data_files('customtkinter')`，excludes 条目按防御口径保留。
- **dev extra 新增 `pre-commit>=3.6.0`**（配套 `.pre-commit-config.yaml`）；属 dev extra、不入 `requirements.txt`，运行时依赖仍 21 条。
- **CI 工具版本常量对齐本地实装**：`isort_version` 9.0.2、`black_version` 26.10.1，`.pre-commit-config.yaml` 两个 mirror rev → 26.10.1 / 9.0.2，使「本地 venv / CI / 提交钩子」同值；抬值前两版 black 各跑一次全量 `--check`（判定不变），新 rev 逐个经 GitHub API 核实。

**🛠️ 仓库维护与文档**
- **界面现代化阶段4~6 收尾**：CTk → ttk 控件层、依赖摘除与打包清理、体积基线补齐（91.81MB / 224 文件）、xvfb 常态化，以及字号 / 缩放 / 动效。
- **i18n 机检三批**：新增 `tests/test_i18n_catalog_coverage.py`（按名调用点 msgid 四目录齐全 / 白名单集合相等 / 键集合逐项相等）、`test_i18n_raise_site_tr.py`、`test_gui_qt_label_parity.py`；`extract_i18n_strings.py` 认识 `T(...)`。四目录键数 1110 → 1127（期间收回 6 条孤儿键）。
- **门禁与 CI**：typecheck 补 `mypy --platform win32`；新增 `pyrightconfig.json`（include 等于 `[tool.mypy].files`、exclude 覆盖两份清单），使不带路径跑 `pyright` 复现 IDE 扫描面；新增 `tests/test_ci_frontend_registration.py`（`.mjs` ↔ ci.yml 清单双向差集）与 Hook 执行体 `scripts/agent_hook_guard.py` + `/dlr-dod`。
- **代码审查与元数据对账**：`CODE_REVIEW_2026-10-02.md`（8 工作包深审，严重 2 / 中等 18 / 轻微 47 = 67；报告矩阵原记 17 / 66 已按枚举更正）；两轮元数据同源对账（取值零改动）；`AGENTS.md` 69 项机检、6 处断言按实测改正、3 处 `file:line` 改锚点。
- **CODE_WIKI 双语新增「按模块分类的改动总览」**（11 个小节，同一张数据表渲染）；Linux arm64 与四平台矩阵同步进双语 README 的产物清单与 GHCR 拉取说明。

**🧪 测试与验证**
- 全量 `pytest` **4365 passed / 14 skipped / 0 failed、warnings 空**；`run_gates.py` **10/10 全绿 rc=0**（black 246 文件、无参 mypy 245 文件 + linux/win32 双跑）。
- 覆盖率总 **83.10%**，`check_coverage.py` **69 模块全达标**（`src/config_read.py` 98%）；basedpyright 与裸跑 `pyright` 均 0 errors / 0 warnings。
- 打包体积 **153.21MB / 359 文件**；`QT_BLOAT_FILES` 11 项 / 39.25MB 在 COLLECT 后按文件名剪除（excludes 管不到 hook 收的 DLL），冻结 GUI exe 实跑 9s 存活。
- 真机：虎牙 660000（2 条 / 206 B）、B站 545068（33 / 2642 B）、b23.tv 22747736（18 / 1402 B）均 PASS；`hy.fan/JbmwoV` 真实 301 解析到 `www.huya.com/30764624`（在播，该时段无弹幕记 WARN）；小红书 570480456678837366 解析 OK（`liveStatus=end`）；斗鱼 `m.douyu.com/5526219` 完整取流链返回 `flv_url` / `m3u8_url` / `record_url`。
- GUI 真窗：主题 ×4 / 缩放 ×5 / 动效 ×4 / 五页面 / 对话框 / 高级设置全 `ALL_OK`，85% / 100% / 150% 三档截图复核（「按钮内边距不跟随」「侧栏底部溢出」「页面滑入后消失」三缺陷即在此发现）。

### v4.4.0 (2026-09-29 ~ 2026-10-01) — Web 面板 FastAPI → Starlette 迁移（移除 fastapi/pydantic，24 条路由契约逐字保留）/ Web 前端动效层与移动端适配 / GUI 主题层（阶段3）与长文案自适应折行根除 DPI 卡死 / 抖音原画 HEVC 房「无可用源」死锁根治与 h265 候选按保存格式放行 / 两轮全量代码审查与 P0 修复（standalone SSRF 三道防线、ffmpeg 命令日志脱敏等）/ i18n 盲区补录 / 依赖与文档多轮对账

> 本版本（v4.4.0，2026-09-29 ~ 10-01）为一次「UI 现代化 + 全量审查修复」周期。四点最值得注意：① **Web 后端从 FastAPI 迁移到 Starlette 直接驱动**——自研路由适配器与零依赖校验层，24 条路由契约与全部安全不变量逐字保留，运行时依赖 23 → 21；② **两轮全量代码审查**（`CODE_REVIEW_2026-09-29_2` 31 编号全落地 + `CODE_REVIEW_2026-09-30` 严重 2 / 中等 51 / 轻微 160、P0 已修）清掉 standalone 独立发行版的 SSRF/本地文件读取链、ffmpeg 命令凭据明文落盘等一批静默失效形态；③ **抖音原画 HEVC 房死锁根治**——主播在播却每轮「本轮无可用源」永不录制的死锁（hevc 替换、h265 候选剔除、HLS 静默丢弃三规则叠加）已修复，h265 候选按保存格式（TS/MKV/MP4）放行直拷并新增零源观测告警；④ **GUI 主题层（阶段3）** 与 **Web 前端动效层（阶段1）** 落地，GUI 长文案自适应折行根除两侧裁切与 DPI 重缩放卡死。**存在破坏性变更（依赖面）**，见下方专节。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**✨ 新增功能 / 改进**
- **GUI 主题层（阶段3）**：新增 `src/ui_theme.py`（零显示依赖、可无头 import）——13 个语义槽位 × 三套主题（浅色 / 深色 / 高对比度），侧边栏「界面主题」菜单运行时切换并持久化到 `config.ini [GUI] gui_theme`；WCAG 对比度机检（正文 4.5 / 非文本与禁用 3.0）由 `tests/test_ui_theme.py`（34 用例）持续回归。
- **Web 前端动效层（阶段1）**：新增 `web/motion.js`（零依赖 IIFE，挂载 `window.__dlrMotion`）——滚动入场（IntersectionObserver 错峰）/ 视差粒子（数量按视口自适应、低核设备减半）/ `prefers-reduced-motion` 全降级 / 页面隐藏暂停 / `destroy()` 无残留定时器；`web/index.html` + `web/style.css` 接线；`tests/frontend/test_motion.mjs` 5 用例（node:test 沙箱，零 npm 依赖）。
- **Web 后端自研适配层**（随迁移新增）：`src/web_models.py`（9 个纯标准库 dataclass 请求模型，替代 pydantic）+ `src/web_api.py::_route` 路由适配器（JSON body 解析 / Query 上下界夹取 / 同步端点线程池派发 / JSONResponse 包装），24 个路由处理器函数体零改动。
- **`retry` 复合动作新增 `fail_fast_codes` 入参（按退出码分档）**：不传时既有 16 个调用点行为逐字不变；web smoke 调用点传 `"2"`，配置类错误立即失败不进入退避——不得为了流水线变绿退 0 或降级 warning。
- **两道新测试防线**：R7 真机脚本模板 AST 门禁（`__main__` 守卫 / 收集期零副作用 / argv 两步守卫 / 按平台前缀清理，5 个 live_collector 同批加固）；R8 全仓 `MUTATION-` 残留扫描（变异验证未还原即判红，配套三条硬约束写回 AGENTS.md）。
- **新增动态路由契约锁** `tests/test_web_api_routes.py`（24 条 method/path 精确集合 + `/web` 挂载点），取代被敏感门禁拦截的静态基线 JSON。
- **h265 候选按保存格式放行（TS/MKV/MP4 可直拷 HEVC）+ HLS 静默丢弃的零源观测告警**：`_h265_copy_format_supported()` 按 main 热更新的 `video_save_type` 判定容器能否直拷 HEVC——TS/MKV/MP4 放行（h265 主候选进常规探针序列）、FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展）/MP3/M4A/域外取值保守剔除；main.py 的 h265→TS 强制块加同一口径守卫（保存格式已是 TS/MKV/MP4 时不再接管、不再打「use TS format instead」告警）。m3u8 候选被 HLS 配置（全局开关/排除平台）整组静默剔除且本轮最终无可用源时，新增点名成因、候选条数与恢复开关指引的观测告警——补上此前唯一「零日志」的选源成因；选中源的健康轮不打。

**🐛 修复的问题**
- **抖音原画 HEVC 房「本轮无可用源」死锁根治**：主播在播却每轮跳过录制，状态行累计错误数恒 0（选源失败轮不计错误样本，纯看状态行会误判正常）。根因是三条各自成立的规则叠加——原画请求且接口下发 `hevc_flv_url` 时 h265 FLV **替换** h264 成为唯一 FLV 候选；`select_source_url` 把一切 `codec=h265` 候选在探针前剔除；HLS 采集关闭时 h264 m3u8 组被静默剔除、record_url（`.m3u8`）被联动禁用——过滤后零可用候选。修复：hevc 替换发生前把被替换的 h264 原画地址存入 `flv_url_list`（HLS 关闭/不可达时落到该备选；与 hevc 地址逐字相同或自带 `codec=h265` 标记的条目不收）。真机验证 hevc 原画在播房：HLS 关闭态选中 h264 FLV 备选（修复前该形态恒「本轮无可用源」）→ `E2E_RESULT: CURED`。
- **standalone 独立发行版孪生漂移（严重 2 项）**：① 探针/录制链 SSRF 与本地文件读取链（默认 `build_opener` 注册 FileHandler + 候选无协议/内网判定 + ffmpeg 缺 `-protocol_whitelist` 三层叠加，`file://` 与云元数据地址可被「探测→放行→录制落盘」完整走通）——补显式 Handler 白名单、`_untrusted_stream_target_reason` 内网判定（含 `2130706433`/`0x7f000001` 等缩写形态）与两处 `-protocol_whitelist`；② 完整 ffmpeg 命令（含 Cookie 头与带 token 流地址）逐轮明文落 `logs/ffmpeg.log`——写入前经 `_mask_ffmpeg_cmd_for_log` 脱敏。
- **P0 六项**：磁盘满暂停期退出的房间不再永久残留 `running_list`（空间恢复后全部房间不再拉起的根因）；GUI 保存配置改真原子写（POSIX 下不再把 0600 收紧还原成 umask 权限）；Web 口令 strip 三处统一（首尾带空格的口令不再认证自锁 403）；`update_config_line` 移除无引号值行内注释回落启发式（含 ` #` 的配置值不再被静默污染）；header 形态驼峰凭据（`myToken:`/`sessionKey:` 等）恢复脱敏；`replace_url` 改段级精确匹配（URL 前缀重叠的兄弟房间行不再被「地址失效自动注释」整行误伤）。
- **全量审查修复 31 编号**：Shopee 短链落地页双闸（域族白名单 + 内网判定，不可信即丢弃跳转、剥离 Cookie）；异步 HTTP **逐跳**重定向内网复检；`sync_req` scheme 白名单 opener（不再注册 file/ftp/data handler）；PandaTV/WinkTV 等平台进日志的原始 URL 一律脱敏；快手 did / B站 buvid 跨代理出口不再串用设备指纹；`anchor_name` 为 None 不再崩掉整轮解析；TikTok HLS-only 房间「选流畅实拉原画」且无降级提示的选档缺陷；B站弹幕 host 轮换「假关闭」吞真实断连；Web 认证拒绝文案不再被 stdio 重定向吞掉；`tr()` 二次异常不再顶掉原始异常；前端 reauth 口令改掩码弹窗、三条轮询链代次令牌防失联定时器；GUI 状态行匹配串按语言惰性重算、`after` 自续期链 `try/finally` 防永久断裂、「停止录制/彻底退出」共用单飞入口、tail 线程逐事件容错；真机脚本收集期真连平台/清空输出目录的会话污染（`pytest --collect-only` 20.55 秒 → 0.81 秒）。
- **同步探针内网收口**：同步探针此前连初始 URL 的内网/回环/云元数据判定都没有（协议形态白名单挡得住 `file://`、挡不住 `http://127.0.0.1:6379`）——`_probe_client()` 单点工厂 + 发请求前初始判定 + `RedirectHopRejected` 收敛；实测公网 HLS 走通、`127.0.0.1:6379`/`169.254.169.254`/`10.0.0.5`/CGNAT 全拒（末位候选也不放行）。
- **GUI 长文案两侧裁切与 DPI 卡死（同根因两批修复）**：`_bind_adaptive_wraplength` 自适应折行根除 pack 两侧对称裁切（5 处同形态一并修复）；随后把 `<Configure>` 同步追写改为「真防抖（风暴安静 120ms 才结算）+ 迟滞（|Δ| ≤ max(12, 2%) 不写）+ TclError 竞态守护」，根除与 CTk DPI 重缩放递归互泵的事件风暴（整窗卡死 / 文字高频闪烁 / 元素渲染不完整）。
- **Web 面板移动端适配**：顶栏两行化（固定 56px → min-height + ≤768px 换行）、`viewport-fit=cover` + `env(safe-area-inset-*)` 安全区适配、`100dvh` 动态视口、三张数据表窄屏面板内横向滚动——消除 iPhone 16 Pro Max / Pixel 10 上的顶栏裁切与整页横向滚动。
- **i18n 盲区补录**：提取器三类盲区（`print_colored` / `messagebox` / 推送正文）的用户可见文案全部 tr 化，四语目录登记 16 条新词条并重编 `.mo`；zh_TW 顺带去重 7 条重复键，四目录键集恢复严格一致（808 键；10-01 随 h265 零源观测告警词条再登记 1 条，终态 809 键）。

**⚠️ 破坏性变更 / 行为变化**
- **移除 `fastapi` / `pydantic` 运行时依赖**（明细见下方「依赖变更」）：Web 面板的 24 条路由、请求/响应形态、安全头与鉴权中间件行为不变；内部请求模型改 `.parse()` 读取，对外部使用方无 API 面变化。仅在面板之外直接 import 这两个包的自定义部署需要自行调整。

**📦 依赖变更**
- **运行时依赖 23 → 21 条**：删除 `fastapi>=0.140.0` 与 `pydantic>=2.13.4`；`requirements.txt` 与 `pyproject.toml [project.dependencies]` 包名集合逐项相等（回归锁 `tests/test_regression_2026_09_22_gates.py`），`uv.lock` 与 `DouyinLiveRecorder.egg-info` 经 `scripts/sync_metadata.py` 重建（二包零残留）。
- **`urllib3` 声明下限 2.7.0 → 2.8.0**：CI `deps-audit`「下限复核」实测旧下限自身落在 CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689 受影响段（修复版本均为 2.8.0）；`requirements.txt` 与 `pyproject.toml [project.dependencies]` 同步抬升（仍 21 条、包名集合不变），`uv.lock` 与 `DouyinLiveRecorder.egg-info` 经 `sync_metadata.py` 重建；本机 venv 已装 2.8.0，解析集合不变。
- **CI typecheck job 补装固定版本 `pytest==9.1.1`**：`tests/` 的类型检查不再半盲（fixture 与 `pytest.fail()` 的 `NoReturn` 恢复可见）。
- **文档依赖口径修复**：双语 README「安装开发依赖」pip 行由 5 条（缺 `pytest-cov`，照此装出的环境跑不了覆盖率门禁）改为 `pip install .[dev]` 单源形态（指向 `[project.optional-dependencies].dev` 六条）。

**🛠️ 仓库维护与文档**
- **两轮全量代码审查**：`docs/worklog/CODE_REVIEW_2026-09-29_2.md`（31 编号按 P0+P1+P2 全落地）与根目录 `CODE_REVIEW_2026-09-30.md`（18 批逐文件深审约 42,000 行生产代码 + 56,200 行测试，严重 2 / 中等 51 / 轻微 160，Mimosa 深扫交叉证据）；P0 已落地，P1/P2 待后续批次，standalone「回灌对齐」建议单独立项。
- **`AGENTS.md` 多轮对账与精简**：7 项事实同步（用例数 / 符号名 / 调用点数等旧读数更正）+ 信息保真精简 19 处（110,287 → 108,469 字节；门禁 bash 块与全部章节标题逐字未动，三道文档锁 73 passed / 1 skipped 不变）+ 三条门禁口径修正（质量门禁判定改为引用「格式化命令（门禁唯一基准）」一节、`pyright`/Pylance 定位厘清为非门禁、新增「本地门禁可外推前提：工具版本须与 `ci.yml` 钉定值同值」）；stop-hook 凭据风险提示经核查为误报后按建议把红线措辞显式化。
- **元数据对账**：15 个文件对照 `pyproject.toml` 全量核对（版本 4.4.0 / 21 条依赖 / 镜像与服务名 / 端口与挂载 / 打包参数），唯一漂移即上述 README dev-deps 行；`pyproject` `filterwarnings` 两条注释归因由「fastapi testclient」更正为 `starlette.testclient` 本体。
- **两处测试面修复（无生产代码改动）**：`test_gui_stop_exit_singleflight` 在 Linux CI 的 4 条假红系测试替身只桩 win32 信号分支（POSIX 走 `os.kill`），按「stdlib 替身走被测模块命名空间 shim」口径补打桩后，伪造 `sys.platform` 本地复现 POSIX 路径、四场景 25 项判据全过；`test_notify` 超时用例的墙钟余量改由生产常量推导（`taskkill /F /PID` 实测稳定 2.5~3.1s，1s 超时 + ~3s 恰撞 4.0s 手拍余量的机器态误报根除）。

**🧪 测试与验证**
- 全量 `pytest` **3721 passed / 14 skipped / 0 failed / 0 警告**（2026-10-01 终态实测；14 条 skip 均为平台条件性：符号链接特权缺失、Windows chmod 只读位语义、SIGKILL POSIX 形态、h2 已装致缺依赖分支不可达等）。
- 覆盖率 44 模块全部达阈（总 84.9%，coverage.json 实测）；basedpyright 0 error / 0 warning；`run_gates.py` 8/8 全绿。
- 真机验证（09-29 ~ 09-30）：抖音 PASS（59 条 / SRT 4518 字节）、B站 PASS（9 条 / 678 字节）、虎牙 WARN（连接正常、该时段无弹幕）、Twitch WARN、斗鱼 SKIP(房间未开播，解析链正常)、TikTok SKIP(无出境网络)；standalone `--dry-run` 虎牙真实在播房间 PASS（S-01/S-02 增量验证）；公网 HLS 分片探针走通且四类内网目标全拒。GUI 目视项、斗鱼/TikTok 活房间复跑、打包体积复测等交回动作见 [CODE_WIKI.md](CODE_WIKI.md)。
- 真机验证（10-01，抖音 hevc 原画在播房「央视网快看」）三态全 PASS：HLS 关 + TS 保存格式 → h265 FLV 主候选被放行并选中（codec=h265 实测探针通过）；HLS 关 + FLV → 落到 h264 原画备选（codec=h264）；摘除备选 → 返回 None 且零源观测告警实弹打出。

### v4.3.0 (2026-09-16 ~ 2026-09-27) — P0 修复 ffmpeg master 构建下录制 100% 失败（`-thread_queue_size` 被上游收窄为输出专属选项）/ 布尔配置解析口径统一（`true/false` 致 8 项配置静默失效、9 个海外平台无法录制）/ 两轮全量代码审查（62 + 106 项分级修复）/ 供应链加固（官方哈希优先 + GPG 验签 + 删除蓝奏云兜底）/ 发布链四处故障修复（**对外分发的 lite 包一度从未真正存在**）/ Apple Silicon 的 ffmpeg PATH 让位策略 / 日志房间关联字段与 `/health` 探活端点 / 构建产物体积 −21.6% / 覆盖率 73.28% → 82.03%（专项）与 83.91%（09-27 终态）

> 本版本（v4.3.0，2026-09-16 ~ 09-27）为一次以「正确性 + 供应链安全」为主线的收敛周期。四处最值得注意：① **P0**：ffmpeg master 构建把 `-thread_queue_size` 收窄为输出专属选项，我们仍放在 `-i` 之前，导致该构建下**每一次录制都以 `-22 (EINVAL)` 退出、零字节产物**；② **布尔配置解析口径统一**：`config.ini` 写 `true/false` 曾被判为无效并**静默**回落硬编码兜底值（无告警无日志），实测致 8 项配置生效值漂移，其中最严重的一项使 9 个海外平台 100% 无法录制，现已统一为「`是/否` 与 `true/false`/`1/0`/`yes/no`/`on/off` 等价」；③ **两轮全量代码审查**（09-19 的 62 项：严重 12 / 中等 22 / 轻微 28；09-21 的 `CODE_REVIEW_2026-09-20` 106 项：严重 10 / 中等 70 / 轻微 26）把 SSRF、面板接管、凭据明文落盘、弹幕线程死循环等一批静默失效形态一次性清掉；④ **发布链四处故障**（09-26 ~ 09-27），其中最影响用户的一条是：`make_zip` 用 `Path.with_suffix(".zip")` 收尾，而版本号本身带点，lite 与 full 算出同一个附件名，第二次以覆盖模式原地截断第一次，**某次 Release 实际只留下一个既无平台也无变体标识的包，精简版从未分发出去**。**存在破坏性变更**，见下方专节。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**🐛 修复的问题**
- **P0：ffmpeg master 构建下录制 100% 失败**：`-thread_queue_size` 被上游收窄为 muxer 专属选项，置于 `-i` 之前时 ffmpeg 以 `Option thread_queue_size … cannot be applied to input url … Error opening input files: Invalid argument`（返回码 -22）退出；与房间 / 平台 / CDN 无关，该构建下每次录制都失败。
- **P0：布尔配置解析口径统一**：散落四处的解析（原 `!= "否"` / `== "是"` / 前端 `=== '是'`）统一到 `src/config_bool.py::parse_config_bool`；修复后 `global_proxy` 不再被错误置 False，TikTok / SOOP / PandaTV / WinkTV / Flextv / PopkonTV / Twitch / LiveMe / Faceit 等 9 个海外平台恢复解析。
- **全量代码审查 62 项（09-19）**：GUI 空配置启动静默卡死；配置行多一个逗号致其后所有房间永久不录；Tars 解码缺边界校验致弹幕线程死循环；斗鱼弹幕被静默过滤（已修复项回归）；ffmpeg 挂起永久占用并发槽；零字节产物被判成功并撤销线路退避；`config.ini` 含凭据被明文复制到 `backup_config/`；Web 面板可被自身接口接管或锁死；房间 URL 零协议校验 → 盲 SSRF；脱敏黑名单漏掉「凭据嵌在值里」的 URL 型键；安装与打包链路零完整性校验。
- **`CODE_REVIEW_2026-09-20` 全轮落地 106 项（09-21）**：并发信号量把「可用许可数」当容量（网络并发上限实质失控）；`PUT /api/rooms` 绕过房间入口校验；内网地址拦截用字符串前缀黑名单（实测 7 条放行 5 条）；面板认证可被单个写请求热关闭、大小写变体绕过口令哈希 / 防自锁 / token 吊销；CRLF 配置下删除房间永久静默失效却回报 `{"ok": true}`；Shopee 站点后缀解析拼出非法域名；兜底装饰器与返回契约错配（故障伪装「未开播」）；录制看门狗「停滞」判据基准用错（容忍窗口实际只有 30 秒）；`only_flv` 分支缺 `flv_url` 致时间字幕线程死循环写盘；发布链运行时二进制哈希钉定表为空。
- **发布链与供应链**：macOS arm64 的 full 包**静默不含 ffmpeg**（上游无该产物，下载点已修复）；Windows 运行期 ffmpeg 主源经实测确认健康（gyan.dev 带 `.sha256` 文档，与发布期钉定互证）；官方 SHA256 钉定值回填 6/10 槽。
- **测试卫生（09-23）**：一处跨文件补丁泄漏（漏掉的 `undo()`）让同会话后续用例发出真实网络请求，造成 13 条失败里 11 条「全量红、单跑绿」的假失败。
- **P0：构建脚本污染测试会话（09-23）**：`build_exe._ensure_utf8_streams()` 裸 `reconfigure` 破坏 pytest 的 fd 捕获，表现为「GUI 启动失败」弹窗与无关用例被判 FAILED/ERROR（九个 CI job 全为 ubuntu，恒绿不复现）。
- **发布链四处故障（09-26 ~ 09-27，对外产物受影响）**：① 钉定表八个槽位被误改成「官方签名档」标记，`check_runtime_pins.py --strict` 在 prepare 阶段即 rc=1，发布根本走不到构建（已按官方通道回填哈希）；② Linux 内置 ffmpeg 的钉定值取自 BtbN 的滚动 `latest` 别名，上游同日重发同名资产即换 digest，发布链当天红在 SHA256 校验（改钉**月末不可变 release 标签** `autobuild-2026-08-31-13-27`，URL 与 digest 双不可变）；③ **lite 精简包从未真正分发出去**：`make_zip` 以 `Path.with_suffix(".zip")` 收尾，而版本号 `4.3.0` 自带点，`DouyinLiveRecorder-v4.3.0-windows-amd64-lite` 与 `-full` 被截成同一个 `DouyinLiveRecorder-v4.3.zip`，第二次以覆盖模式原地截断第一次且不报错，Release 附件里只剩一个既无平台也无变体标识的包；④ 任一平台构建失败时，预建的 Release 记录会以**空 Release** 留在仓库里。
- **元数据第二副本漂移（09-27）**：`DouyinLiveRecorder.egg-info/PKG-INFO` 的 `Requires-Dist: h2` 仍停在旧下限 `>=4.3.0`（清单早已抬到 `>=4.4.1` 却从未传播进元数据），内嵌 README 亦缺整段 v4.3.0 更新日志；重建修正。

**✨ 新增功能 / 改进**
- **日志房间关联字段 `extra[room]`**：`src/logger.py` 新增 `ROOM_FIELD` / `set_room_context()` / `get_room_context()`（内部 `ContextVar` + patcher），多房间交织日志可按房间切出。
- **Web 面板 `/health` 探活端点**：`GET /health` 返回 `{"status": "ok", "version": …}`，并把内置冒烟工具 `scripts/smoke_test.py` 接通为 CI 可执行的真实 HTTP 探活。
- **W6：Apple Silicon 的 ffmpeg PATH 让位策略**：darwin + arm64 且系统 PATH 上另有原生 ffmpeg 时，不再无条件前置包内那份 x86_64 构建（需经 Rosetta 转译），五条判据全部成立才让位；其余平台逐字不变。
- **运行时二进制完整性**：`build_exe.py` 新增 `_PINNED_RUNTIME_SHA256` 钉定表 + `--require-pinned`，配套 `scripts/check_runtime_pins.py`（结构模式进门禁 / `--strict` 进发布 prepare / `--emit-env` 供 CI 注入）；运行期首装改为「官方公布哈希优先」，发布期增加 GPG 验签与 full 包产物自检。
- **构建产物体积优化（09-24）**：排除 `PIL._avif`、`pydantic.v1.mypy`（拖入整个 mypy）、uvicorn 可选实现、`i18n/*.po` 等运行期不可达模块 + zip `compresslevel=9`，lite 产物 **82.77MB → 64.88MB（−21.6%）**、zip **54.84MB → 42.19MB（−23.1%）**，并新增 `scripts/report_bundle_size.py` 度量脚本。
- **新增五类门禁**：`PYTHONUTF8=1` + 「告警即失败」（消灭 GBK locale 下 isort 静默跳文件且 rc=0）、装饰器契约 AST 锁、测试卫生 AST 锁（R1–R4 / R6「手工 MonkeyPatch 必须配对 undo」）、前端目录一致性锁（`data-i18n*` 键与四语内嵌目录逐一比对）、`deps-audit` job 与覆盖率无数据硬失败。
- **动态并发下限下调**：`ConcurrencyScheduler` 的 `min_capacity` 默认值 8 → 1。
- **内置 ffmpeg 的上游与满足口径（09-26 ~ 09-27）**：Linux 两架构换源 BtbN 的 GPL 完整版资产（按 `<os>-<arch>` 运行时键分列），取数端点固定为月末不可变标签；macOS 两槽走**官方 GPG 签名档**（evermeet 不公布 SHA256，验签即该槽唯一判据，带外钉完整 40 位主钥指纹）。哈希钉定与验签两条防线互不替代。
- **`release-guard`：残缺即不发布（09-27）**：构建未全绿时用 `gh release delete` 回收预建的空/残缺 Release（默认不删 tag，修好后重跑工作流即可重新发布），并留 `::warning::`；上传步骤的 `fail_on_unmatched_files` 刻意不放宽，因为那条红是产物缺失的唯一可见信号。
- **`--dual` 双产物的两道新校验（09-27）**：出包前先清 `dist/` 里上一轮残留的 `DouyinLiveRecorder-v*.zip`（复用工作区的构建机不会把旧包一起扫进附件）；出包后必须确认 lite 与 full 两个产物路径互不相同且都已真实落件，否则当场终止。
- **CI 的 typecheck job 现在装固定版本 `pytest==9.1.1`（09-26）**：此前只装 `requirements.txt + mypy`，`tests/` 里所有 `pytest.*` 都按 `Any` 检查，fixture 与 `pytest.fail()` 的 `NoReturn` 全部失效，等于半个盲区。
- **文档体积整理（09-27，零信息删除）**：`CODE_WIKI*.md` 更新日志里 73 个历史「涉及文件（按模块分类）」清单块逐字外迁到 `docs/agent-reference/changelog-file-inventories{,-en}.md`（wiki 本体 zh −12.3% / en −5.0%），同时补回上一轮批量压缩静默用 `…` 截断的 109（zh）/ 181（en）处表格原文；`README.md` / `README_EN.md` 刻意不压缩（面向使用者的发布说明不做退化）。

**⚠️ 破坏性变更 / 行为变化**
- **Windows 运行期删除蓝奏云 ffmpeg 兜底**：自动安装只剩主源一条路（实测该直链为带人机验证的 HTML 页、伴生哈希文档全 404，不可用）；自动安装失败时改为给出明确的手动安装指引。**Windows 用户若原先依赖该兜底，需按 README 的「Windows 手动安装 ffmpeg」章节自行放置二进制。**
- **Apple Silicon 不再无条件前置包内 ffmpeg 目录**：已用 Homebrew 装原生 arm64 ffmpeg 的用户，录制子进程会改用系统那份（版本 / 编译选项可能不同）。
- **动态并发下限 8 → 1**：低负载场景下的网络并发额度不再被抬到 8。
- **布尔配置写法语义变化**：此前写 `true/false`、`1/0` 等被**静默忽略**（回落到兜底值）的键，升级后按其字面生效 —— 若你的配置依赖旧的错误兜底值，升级后生效值会改变，请在升级后核对 8 项相关配置。
- **运行时依赖 20 → 23 条**：新增显式声明 `urllib3>=2.7.0`（CVE-2026-44431）、`h2>=4.4.1`（PYSEC-2026-3628）与 `socksio>=1.0.0`（httpx 的 http2 / SOCKS 运行期依赖），`starlette` 下限 `>=0.49.1` → **`>=1.3.1`**（CVE-2026-48710 与 PYSEC-2026-2280/2281/248/249），`protobuf` 保持 `<8` 上限（gencode 兼容护栏）。
- **构建期**：`build-release.yml` prepare 以 `check_runtime_pins.py --strict` 拦下未钉定的运行时二进制。
- **`build_exe.py --dual --no-zip` 现在直接报错退出**：`--dual` 分支此前从不读 `no_zip`，即用户显式写的 `--no-zip` 被静默无视、照样压出两个大 zip。矛盾参数组合改为 fail-fast，不再让其中一个参数不起作用。
- **发布附件名恢复平台与变体标识，请改用新附件**：重新发布后 Windows / Linux / macOS 的附件名形如 `DouyinLiveRecorder-v4.3.0-<os>-<arch>-lite.zip` 与 `-full.zip`；此前形如 `DouyinLiveRecorder-v4.3.zip`（无平台段、无变体段）的附件属上述缺陷产物，其内容是完整版，精简版从未存在过。
- **Linux 完整版（full）体积显著增大**：换源 BtbN 后内置 ffmpeg 资产（未压缩口径）为 linux64 ≈126.6 MB / linuxarm64 ≈108.8 MB，而原 johnvansickle amd64 静态构建 ≈41.9 MB。选择 `lite` 包可保持小体积（运行期按需自动下载）。

**🛠️ 仓库维护与质量门禁**
- **测试覆盖率专项（09-21）**：`src/` 覆盖率 **73.28% → 82.03%**（仅动 `tests/`，产品代码零改动），并引入分层白名单（表默认空 + 到期即失败）。
- **四语目录持续补全与核验**：594 → **780 条**，四个目录键集逐条一致、无空值；`.mo` 随变更重编译。
- **元数据同源同步**：`AGENTS.md` 依赖条数与下限口径、`CODE_WIKI*.md` 依赖表（16 → 23 条）、`DouyinLiveRecorder.egg-info` 重建、`.dockerignore` 补 `_probe_*.py`、`config/config.ini` 补 `[Cookie] ttwid`。
- **类型存根与注释治理**：`typings/execjs/` 7 个 `.pyi` 补齐注解、两个抽象基类存根去 `six`（改 `metaclass=ABCMeta`）；全仓多批注释精炼（含 68 文件一轮），`scripts/check_annotations.py` 新增第三盲点（换行符形态）。
- **清理已删除模块残留**：`src/weverse_auth.py` / `tests/test_weverse_auth.py`（2026-09-23 删除）在目录树、依赖注释与四语目录中的 3 条孤儿译文一并清除。
- **跨文件一致性同步（09-27）**：`requirements.txt` ↔ `pyproject.toml [project.dependencies]` 23 ↔ 23 包名集合逐项相等、三组 extras 相等；`python_build = 3.14` 与 `node_version = 24` 在 `ci.yml` / `build-release.yml` 同值；14 个本地工具目录 + 6 个运行期产物目录在 `.gitignore` / `.dockerignore` / `pyproject` 各工具排除表 / `.coveragerc-concurrency` 四套清单中无缺项；本轮实际修订仅一处——`websockets>=14.0` 被截断的行内注释按同源文本补全（规格未动）。
- **`AGENTS.md` 体积整理（09-27）**：把已在 `docs/agent-reference/measured-evidence.md` 留存的读数改为指针、合并三处真重复，97,034 → 95,715 B（−1.4%）；同时以「token 保全审计」自证未丢约束（用例名 / 错误码 / 常量与环境变量名丢失数均为 0）。

**🧪 测试与验证**
- 全量 `pytest` **3240 passed / 14 skipped / 0 failed**（09-27 本机两轮实测，其中一轮带 `--cov=src`）。原先记述为「本机 Windows 恒红」的 `test_symlinked_system_hit_inside_bundled_dir_keeps_prepending` 现已改为按主机能力显式跳过（`symlink not permitted on this host`），计入上述 14 skipped，不再是失败项。
- `black --check .` **169 files unchanged**；`isort --check-only .` 无重排；无参数 `mypy` **158 files 0 issues**（追加 `mypy --platform linux` 亦 0）；`basedpyright`（standard）**0 errors / 0 warnings / 0 notes**。
- 覆盖率：`src/` 总覆盖率 **83.91%**，`scripts/check_coverage.py` **42 个模块全部达标**（`src/proto/douyin_pb2.py` 为 protoc 生成物，显式豁免）。
- `node --test tests/frontend/*.mjs` 通过；`scripts/check_version.py` 与 `scripts/check_runtime_pins.py` 均 rc=0；`scripts/compile_po.py --check` 报 `zh_CN.mo` 与 `.po` 同步（781 条）。

### 更早的更新日志（已归档）

19 条 2024-07-13 ~ 2026-10-15（v4.0.0 ~ v4.2.0）的发布说明条目已逐字迁出至 [release-notes-history-zh.md](docs/changelog/release-notes-history-zh.md)：17 条（v4.0.0 ~ v4.0.9.4）于 2026-09-28 迁出，另有 2 条（v4.2.0 / v4.1.0）于 2026-10-18 按「只留最近三个正式发布」的口径续迁；该卷同时按 `.workbuddy/docold` 基线回补了上一轮粗剪留下的行尾 `…` / 句中截断（口径见其卷首）。
迁出原因：仅「更新日志」一节就占本文件 33.2% 的字符数（21,181 / 63,742）。根文档只保留最近三个正式发布（v4.5.0 / v4.4.0 / v4.3.0）+ 本指针，正文才恢复可读。

## 💬 有问题或者需求可以向我提 Issue，欢迎 Star 与 Fork

[![Star History Chart](https://api.star-history.com/svg?repos=y123ao6/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#y123ao6/DouyinLiveRecorder&Timeline)
