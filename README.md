![video_spider](https://socialify.git.ci/ihmily/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

## 💡 简介

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)](https://github.com/ihmily/DouyinLiveRecorder)
[![Docker Pulls](https://img.shields.io/docker/pulls/ihmily/douyin-live-recorder?label=Docker%20Pulls&color=blue&logo=docker)](https://hub.docker.com/r/ihmily/douyin-live-recorder/tags)
![GitHub issues](https://img.shields.io/github/issues/ihmily/DouyinLiveRecorder.svg)
[![Latest Release](https://img.shields.io/github/v/release/ihmily/DouyinLiveRecorder)](https://github.com/ihmily/DouyinLiveRecorder/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/ihmily/DouyinLiveRecorder/total)](https://github.com/ihmily/DouyinLiveRecorder/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/ihmily/DouyinLiveRecorder?style=flat-square)](https://github.com/ihmily/DouyinLiveRecorder/stargazers)

一款**简易**的可循环值守的直播录制工具，基于 FFmpeg 实现多平台直播源录制，支持自定义配置录制以及直播状态推送。

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🎯 **多平台支持** | 支持抖音、TikTok、YouTube、快手、虎牙、斗鱼、B站等 **60+ 平台** |
| 🔄 **循环值守** | 自动检测直播状态，开播自动录制，断播自动停止 |
| 🎬 **多种格式** | 支持 TS、MKV、FLV、MP4、MP3、M4A 等格式输出 |
| 🖥️ **三模式运行** | 命令行模式、GUI 图形界面模式、Web 管理面板模式 |
| 📊 **画质监控** | 实时检测各直播间实际画质，画质降级时自动告警 |
| 📱 **消息推送** | 支持钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus 等推送 |
| 🐳 **Docker 支持** | 支持 Docker 容器化部署，开箱即用 |
| 🌐 **国际化** | 支持中文、英文等多语言界面 |
| ⚙️ **灵活配置** | 支持按直播间自定义画质、格式、分段录制等 |
| 🔐 **Web 安全** | Token 认证、路径穿越防护、敏感配置脱敏 |

## 🚀 快速开始

### 方式一：下载运行包（推荐新手）

1. 进入 [Releases](https://github.com/ihmily/DouyinLiveRecorder/releases) 下载最新发布的 zip 压缩包
2. 解压后，在 `config` 文件夹内的 `URL_config.ini` 中添加直播间地址
3. 运行 `DouyinLiveRecorder.exe` 开始录制

### 方式二：源码运行（推荐开发者）

```bash
# 克隆项目
git clone https://github.com/ihmily/DouyinLiveRecorder.git
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

# 或本地构建并启动
docker build -t douyin-live-recorder .
docker run -d -v ./config:/app/config -v ./downloads:/app/downloads douyin-live-recorder
```

> 容器内 FFmpeg 与 Node.js 由镜像自带（apt 安装），无需挂载本地 `ffmpeg/`、`node/` 目录；
> `config/`、`downloads/`、`logs/`、`backup_config/` 通过卷挂载持久化。

## 🎈 已支持平台

**国内站点（37 个）**：抖音 | 快手 | 虎牙 | 斗鱼 | YY | B站 | 小红书 | bigo | blued | 网易CC | 千度热播 | 猫耳FM | Look直播 | TwitCasting | 百度 | 微博 | 酷狗 | 花椒 | 流星 | Acfun | 畅聊 | 映客 | 音播 | 知乎 | 嗨秀 | VV星球 | 17Live | 浪Live | 漂漂 | 六间房 | 乐嗨 | 花猫 | 淘宝 | 京东 | 咪咕 | 连接 | 来秀

**海外站点（14 个）**：TikTok | SOOP(原AfreecaTV) | PandaTV | WinkTV | TTingLive(原Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | Youtube | Faceit | Picarto

- [x] 抖音
- [x] TikTok
- [x] 快手
- [x] 虎牙
- [x] 斗鱼
- [x] YY
- [x] B站
- [x] 小红书
- [x] bigo
- [x] blued
- [x] SOOP(原AfreecaTV)
- [x] 网易cc
- [x] 千度热播
- [x] PandaTV
- [x] 猫耳FM
- [x] Look直播
- [x] WinkTV
- [x] TTingLive(原Flextv)
- [x] PopkonTV
- [x] TwitCasting
- [x] 百度直播
- [x] 微博直播
- [x] 酷狗直播
- [x] TwitchTV
- [x] LiveMe
- [x] 花椒直播
- [x] 流星直播
- [x] ShowRoom
- [x] Acfun
- [x] 映客直播
- [x] 音播直播
- [x] 知乎直播
- [x] CHZZK
- [x] 嗨秀直播
- [x] vv星球直播
- [x] 17Live
- [x] 浪Live
- [x] 畅聊直播
- [x] 飘飘直播
- [x] 六间房直播
- [x] 乐嗨直播
- [x] 花猫直播
- [x] Shopee
- [x] YouTube
- [x] 淘宝
- [x] 京东
- [x] Faceit
- [x] 咪咕
- [x] 连接直播
- [x] 来秀直播
- [x] Picarto
- [ ] 更多平台正在更新中

## 📁 项目结构

```
DouyinLiveRecorder/
├── config/                     # 配置文件目录
│   ├── config.ini             # 主配置文件
│   └── URL_config.ini         # 直播间地址列表
├── src/                        # 核心源码包
│   ├── __init__.py             # 包初始化 + Node.js 环境配置
│   ├── spider.py              # 直播数据爬虫（60+ 平台）
│   ├── stream.py              # 直播流解析（含画质回采）
│   ├── room.py                # 直播间信息解析
│   ├── utils.py               # 工具函数库
│   ├── logger.py              # Loguru 日志配置
│   ├── proxy.py               # 代理检测
│   ├── ab_sign.py             # 抖音 A-Bogus 签名
│   ├── node_install.py        # Node.js 自动安装/初始化
│   ├── weverse_auth.py        # Weverse 平台认证
│   ├── ttwid.py               # 抖音访客 ttwid 获取
│   ├── web_api.py             # Web 管理面板 FastAPI 应用
│   ├── web_config.py          # Web 面板配置读写
│   ├── web_tray.py            # Web 模式系统托盘（最小化到托盘）
│   ├── http_clients/          # HTTP 客户端
│   │   ├── __init__.py
│   │   ├── config.py          # HTTP 客户端共享配置（SSL 验证开关）
│   │   ├── async_http.py      # 异步 HTTP 客户端 (httpx)
│   │   └── sync_http.py       # 同步 HTTP 客户端
│   ├── javascript/            # JavaScript 签名脚本
│   │   ├── crypto-js.min.js
│   │   ├── x-bogus.js
│   │   ├── haixiu.js
│   │   ├── laixiu.js
│   │   ├── liveme.js
│   │   ├── migu.js
│   │   └── taobao-sign.js
│   └── ffmpeg_install.py     # FFmpeg 安装脚本
├── web/                        # Web 管理面板前端
│   ├── index.html              # 单页应用入口
│   ├── app.js                  # 前端逻辑（API、SSE、渲染）
│   └── style.css               # 样式表（主题、响应式）
├── typings/                    # 第三方库类型存根（静态检查用）
├── downloads/                  # 录制文件保存目录（运行时生成）
├── logs/                       # 日志文件目录（运行时生成）
├── i18n/                       # 国际化文件（gettext）
│   ├── zh_CN/LC_MESSAGES/
│   │   ├── zh_CN.po           # 中文翻译源
│   │   └── zh_CN.mo           # 编译后翻译（运行时必需）
│   └── en/LC_MESSAGES/         # 英文（预留）
├── ffmpeg/                     # FFmpeg 目录（Windows）
├── node/                       # Node.js 目录（Windows）
├── main.py                     # 命令行入口
├── gui.py                      # GUI 图形界面入口
├── gui_legacy.py               # 旧版 GUI（兼容保留）
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

```ini
[录制设置]
# 界面语言 (zh_cn/en)
language(zh_cn/en) = zh_cn
# 是否跳过代理检测(是/否)
是否跳过代理检测(是/否) = 是
# 是否禁用SSL证书验证(是/否)
是否禁用SSL证书验证(是/否) = 是
# 是否启用日志文件(是/否)
是否启用日志文件(是/否) = 是
# 直播保存路径(不填则默认 downloads/)
直播保存路径(不填则默认) =
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
# 是否使用代理ip(是/否)
是否使用代理ip(是/否) = 否
# 代理地址
代理地址 =
# 同一时间访问网络的线程数
同一时间访问网络的线程数 = 3
# 循环时间(秒) - 直播状态检测间隔
循环时间(秒) = 300
# 排队读取网址时间(秒)
排队读取网址时间(秒) = 0
# 是否显示循环秒数
是否显示循环秒数 = 否
# 是否显示直播源地址
是否显示直播源地址 = 否
# 分段录制是否开启
分段录制是否开启 = 是
# 是否强制启用https录制
是否强制启用https录制 = 否
# 录制空间剩余阈值(gb)
录制空间剩余阈值(gb) = 1.0
# 视频分段时间(秒)
视频分段时间(秒) = 3600
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
使用代理录制的平台(逗号分隔) = tiktok, sooplive, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu
# 额外使用代理录制的平台(逗号分隔)
额外使用代理录制的平台(逗号分隔) =
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
bark推送铃声 =
钉钉通知@对象(填手机号) =
钉钉通知@全体(是/否) = 否
tgapi令牌 =
tg聊天id(个人或者群组id) =
smtp邮件服务器 =
是否使用SMTP服务SSL加密(是/否) =
SMTP邮件服务器端口 =
邮箱登录账号 =
发件人密码(授权码) =
发件人邮箱 =
发件人显示昵称 =
收件人邮箱 =
ntfy推送地址 = https://ntfy.sh/xxxx
ntfy推送标签 = tada
ntfy推送邮箱 =
pushplus推送token =
自定义推送标题 =
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
快手cookie =
tiktok_cookie =
虎牙cookie =
斗鱼cookie =
yy_cookie =
b站cookie =
小红书cookie =
bigo_cookie =
# ... 其余平台 cookie 详见 config.ini
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
# Web 管理面板监听地址
web_host = 0.0.0.0
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
```

### 直播间配置 (config/URL_config.ini)

```
# 基础格式
https://live.douyin.com/745964462470

# 指定画质（画质,直播间地址）
超清，https://live.douyin.com/745964462470

# 指定画质和主播名（画质,直播间地址,主播:名称）
高清，https://live.bilibili.com/123456，主播: B站主播

# 注释直播间（在地址前加 #）
# https://live.douyin.com/123456789
```

### 环境变量配置

| 变量名 | 说明 | 示例 |
|--------|------|------|
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

GUI 功能：
- 📊 控制台 - 录制状态总览、启停控制
- 🎯 画质监控 - 实时检测各直播间实际画质是否与设置一致
- 📝 URL 配置 - 直播间地址管理
- 📋 运行日志 - 子进程日志查看
- 系统托盘图标 - 最小化到托盘运行

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

Web 模式与命令行模式共用同一录制引擎与配置文件，直播间地址的增删改会自动被录制主循环热加载。

后台运行模式：将 `web_show_console` 设为 `false`，Windows 下会隐藏控制台窗口，日志写入 `logs/web_console.log`，程序完全后台运行。

Windows 下控制台默认「最小化到系统托盘」（`web_minimize_to_tray = true`）：点击最小化后窗口不在任务栏显示，而是收起到系统托盘，双击托盘图标即可恢复；标题栏关闭按钮已禁用，需从托盘图标菜单的「退出程序」退出。

> ⚠️ **安全提示**：默认监听 0.0.0.0 且未启用认证，公网/局域网部署请务必开启 `web_auth_enable` 并设置强密码，或将 `web_host` 改为 `127.0.0.1`。

### 录制格式推荐

- **长时间录制**：推荐使用 `ts` 格式，实时写入，断电不易损坏
- **短时间录制**：推荐使用 `mp4` 或 `mkv` 格式，录制完成后直接可用
- **仅音频录制**：推荐使用 `mp3` 或 `m4a` 格式

### 画质说明

| 画质代码 | 中文名 | 说明 |
|---------|--------|------|
| OD | 原画 | Original Definition，最高画质 |
| BD | 蓝光 | Blu-ray，超高清 |
| UHD | 超清 | Ultra HD |
| HD | 高清 | High Definition |
| SD | 标清 | Standard Definition |
| LD | 流畅 | Low Definition，最低画质 |

支持平台：抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC。当平台实际下发画质低于设置画质时，会自动告警并标记。

### 停止录制

- **Windows**：执行 `StopRecording.vbs` 或在命令行按 `Ctrl+C`
- **Linux/macOS**：在命令行按 `Ctrl+C`
- **Docker**：执行 `docker-compose stop`

### 注意事项

1. 如需录制 TikTok、SOOP 等海外平台，请在配置中开启代理
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
git clone https://github.com/ihmily/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# 2. 编辑配置文件
# 在 config/URL_config.ini 中添加直播间地址

# 3. 启动容器（默认命令行录制模式）
docker compose up -d

# 4. 查看日志
docker compose logs -f
```

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
  - "8000:8000"   # Web 管理面板端口（仅 --profile web 时生效）
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TZ` | 时区 | `Asia/Shanghai` |
| `PYTHONUNBUFFERED` | 实时输出 | `1` |
| `PYTHONDONTWRITEBYTECODE` | 不生成 .pyc 文件 | `1` |
| `PYTHONIOENCODING` | Python 输出编码 | `utf-8` |
| `TERM` | 终端类型 | `xterm-256color` |

### Docker 镜像特性

- **多阶段构建**：builder 阶段安装依赖到虚拟环境，runtime 阶段精简镜像
- **非 root 用户**：使用 `recorder` 用户运行，提升安全性
- **健康检查**：自动检测 `main.py` 或 `web.py` 进程是否存活
- **资源限制**：默认限制 2 CPU / 2G 内存（可在 docker-compose.yaml 调整）
- **日志轮转**：单文件 50MB，最多保留 3 份
- **内置 Node.js 22 LTS**：用于运行 JavaScript 签名脚本

## 🛠️ 开发指南

### 环境要求

- Python >= 3.10
- FFmpeg (Linux/macOS 需要手动安装)
- Node.js (Windows 下自动安装，Linux/macOS 需手动安装)

### 安装开发依赖

```bash
# 使用 uv（推荐）
uv sync --dev

# 或使用 pip
pip install -r requirements.txt
pip install pytest pytest-asyncio black isort mypy
```

### 代码规范

```bash
# 格式化代码（line-length = 120）
black .

# 排序导入
isort .

# 类型检查
mypy .

# 运行测试
pytest
```

### 项目文档

- [CODE_WIKI.md](CODE_WIKI.md) - 项目架构文档（详细的模块说明、依赖关系、设计模式）

### 添加新平台支持

1. 在 `src/spider.py` 中添加平台数据获取函数（参考现有平台实现）
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑（`PLATFORM_HOST` 列表和录制分支）
4. 在 `tests/test_stream_quality.py` 中添加画质回采测试
5. 更新 `README.md` 和 `CODE_WIKI.md`

## ❓ 常见问题

**Q: 录制时提示 "缺少 ffmpeg 无法进行录制"**

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg

# Windows
# 程序已自带 ffmpeg，无需安装
```

**Q: 提示 "缺少 Node.js" 或 "execjs" 相关错误**

```bash
# Ubuntu/Debian
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
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
- 降低循环监测频率
- 更换 IP 或使用代理

**Q: 录制的视频文件损坏**

- 推荐使用 `ts` 格式录制
- 检查磁盘空间是否充足
- 检查网络是否稳定

**Q: 如何只推送开播通知不录制？**

在 `config.ini` 的 `[推送配置]` 节设置 `只推送通知不录制(是/否) = 是`

**Q: Web 面板忘记密码怎么办？**

直接编辑 `config/config.ini` 中的 `web_password` 项，修改后重启 `web.py` 即可。密码变更后所有现有 Token 会自动失效，需重新登录。

## 🤖 相关项目

- [StreamCap](https://github.com/ihmily/StreamCap) - 直播录制工具
- [streamget](https://github.com/ihmily/streamget) - 流媒体获取工具

## ❤️ 贡献者

[![Hmily](https://github.com/ihmily.png?size=50)](https://github.com/ihmily)
[![iridescentGray](https://github.com/iridescentGray.png?size=50)](https://github.com/iridescentGray)
[![annidy](https://github.com/annidy.png?size=50)](https://github.com/annidy)
[![wwkk2580](https://github.com/wwkk2580.png?size=50)](https://github.com/wwkk2580)
[![missuo](https://github.com/missuo.png?size=50)](https://github.com/missuo)
[![xueli12](https://github.com/xueli12.png?size=50)](https://github.com/xueli12)
[![kaine1973](https://github.com/kaine1973.png?size=50)](https://github.com/kaine1973)
[![yinruiqing](https://github.com/yinruiqing.png?size=50)](https://github.com/yinruiqing)
[![Max-Tortoise](https://github.com/Max-Tortoise.png?size=50)](https://github.com/Max-Tortoise)
[![justdoiting](https://github.com/justdoiting.png?size=50)](https://github.com/justdoiting)
[![dhbxs](https://github.com/dhbxs.png?size=50)](https://github.com/dhbxs)
[![wujiyu115](https://github.com/wujiyu115.png?size=50)](https://github.com/wujiyu115)
[![zhanghao333](https://github.com/zhanghao333.png?size=50)](https://github.com/zhanghao333)
[![gyc0123](https://github.com/gyc0123.png?size=50)](https://github.com/gyc0123)

[![HoratioShaw](https://github.com/HoratioShaw.png?size=50)](https://github.com/HoratioShaw)
[![nov30th](https://github.com/nov30th.png?size=50)](https://github.com/nov30th)
[![727155455](https://github.com/727155455.png?size=50)](https://github.com/727155455)
[![nixingshiguang](https://github.com/nixingshiguang.png?size=50)](https://github.com/nixingshiguang)
[![1411430556](https://github.com/1411430556.png?size=50)](https://github.com/1411430556)
[![Ovear](https://github.com/Ovear.png?size=50)](https://github.com/Ovear)

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，欢迎 Star 和 Fork！

## ⏳ 更新日志

### v4.0.8-dev (2026-07-25)

- 新增 Web 管理面板（`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`），支持仪表盘、直播间管理、配置编辑、SSE 日志推送
- 新增 GUI 画质监控页面，实时检测各直播间实际画质是否与设置一致
- 新增实际画质回采与降级告警功能，覆盖抖音、TikTok、快手、虎牙、斗鱼、B站、网易CC 七个平台
- 新增 Web 控制台开关配置 `web_show_console`，支持后台隐藏运行模式
- 新增 HTTP 客户端连接池复用机制，按 (代理, verify, http2) 维度复用 AsyncClient
- 新增 SSL 证书验证全局开关，通过 config.ini 统一控制
- 新增日志文件开关配置项
- 重构代理检测逻辑，从联网探测改为读取本地系统代理配置
- 修复 `trace_error_decorator` 严重 Bug（原同步装饰器应用于 71 个异步函数导致错误捕获失效）
- 修复 `asyncio.run()` 导致的 httpx 客户端跨事件循环复用问题
- 修复多个 IndexError / KeyError / 类型错误运行时 Bug
- 全项目类型错误修复与代码清理（Pyright / Pyrefly / basedpyright）
- 清理硬编码过期凭据，改为自动获取（抖音 ttwid、快手 did、Twitch Client-Id 等）
- Dockerfile 升级 Node.js 22 LTS，使用非 root 用户运行
- 依赖扫描完成，新增 `pydantic>=2.0.0` 依赖声明

### v4.0.7 (2025-10-24)

- 修复抖音风控无法获取数据问题
- 新增 soop.com 录制支持
- 修复 bigo 录制

### v4.0.6 (2025-01-27)

- 新增淘宝、京东、faceit 直播录制
- 修复小红书直播流录制以及转码问题
- 修复畅聊、VV星球、flexTV 直播录制
- 修复批量微信直播推送
- 新增 email 发送 ssl 和 port 配置
- 新增强制转 h264 配置
- 更新 ffmpeg 版本
- 重构包为异步函数！

### v4.0.5 (2024-11-30)

- 新增 shopee、youtube 直播录制
- 新增支持自定义 m3u8、flv 地址录制
- 新增自定义执行脚本，支持 python、bat、bash 等
- 修复 YY 直播、花椒直播和小红书直播录制
- 修复 b 站标题获取错误
- 修复 log 日志错误

### v4.0.4 (2024-10-30)

- 新增嗨秀直播、vv星球直播、17Live、浪Live、SOOP、畅聊直播、飘飘直播、六间房直播、乐嗨直播、花猫直播等 10 个平台直播录制
- 修复小红书直播录制，支持小红书作者主页地址录制直播
- 新增支持 ntfy 消息推送，以及新增支持批量推送多个地址
- 修复 Liveme 直播录制、twitch 直播录制
- 新增 Windows 平台一键停止录制 VB 脚本程序

<details><summary>点击展开更多历史版本</summary>

### v4.0.3 (2024-10-05)

- 新增邮箱和 Bark 推送
- 新增直播注释停止录制
- 优化分段录制
- 重构部分代码

### v4.0.2 (2024-09-28)

- 新增知乎直播、CHZZK 直播录制
- 修复音播直播录制

### v4.0.1 (2024-09-03)

- 新增抖音双屏录制、音播直播录制
- 修复 PandaTV、bigo 直播录制

### v4.0.0 (2024-07-13)

- 新增映客直播录制

### 更多历史版本...

</details>

## 💬 有问题可以提 Issue，我会在这里持续添加更多直播平台的录制 欢迎 Star

[![Star History Chart](https://api.star-history.com/svg?repos=ihmily/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#ihmily/DouyinLiveRecorder&Timeline)