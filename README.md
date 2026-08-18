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

**国内站点（37 个）**：抖音 | 快手 | 虎牙 | 斗鱼 | YY | B站 | 小红书 | bigo | blued | 网易CC | 千度热播 | 猫耳FM | Look直播 | TwitCasting | 百度 | 微博 | 酷狗 | 花椒 | 流星 | Acfun | 畅聊 | 映客 | 音播 | 知乎 | 嗨秀 | VV星球 | 17Live | 浪Live | 飘飘 | 六间房 | 乐嗨 | 花猫 | 淘宝 | 京东 | 咪咕 | 连接 | 来秀

**海外站点（14 个）**：TikTok | SOOP(原AfreecaTV) | PandaTV | WinkTV | TTingLive(原Flextv) | PopkonTV | TwitchTV | LiveMe | ShowRoom | CHZZK | Shopee | YouTube | Faceit | Picarto

> 更多平台持续添加中。

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
│   ├── http_config.py          # HTTP 客户端共享配置（SSL 验证开关）
│   ├── async_http.py          # 异步 HTTP 客户端 (httpx)
│   ├── sync_http.py           # 同步 HTTP 客户端
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

# 类型检查（CI 以 mypy 为准）
mypy .

# 类型检查（本地增强，可选）：basedpyright
# 已在 pyproject.toml 配置 [tool.basedpyright]，venvPath 指向工作区 .venv（相对路径，可移植）
# 首次需创建并安装依赖：python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
basedpyright .

# 运行测试
pytest
```

> **注释规范**：模块/函数说明统一使用 `#` 行注释，不使用三引号 `"""` 文档字符串；功能性多行字符串字面量（模板/SQL）改用单引号 + 换行拼接而非 `"""`。

> **测试说明**：`tests/test_web_api.py` 的符号链接相关用例（`TestListFiles::test_broken_symlink_skipped` / `test_symlink_outside_skipped`）在无法创建真实符号链接的环境（未开启开发者模式的 Windows、部分沙箱）会自动 `pytest.skip`，属正常现象，不代表代码缺陷。当前结果：496 passed / 2 skipped。

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

### 添加新平台支持

1. 在 `src/spider.py` 中添加平台数据获取函数（参考现有平台实现）
2. 在 `src/stream.py` 中添加流地址解析函数，返回值包含 `actual_quality` 和 `available_qualities` 字段
3. 在 `main.py` 中添加平台识别逻辑（`PLATFORM_HOST` 列表和录制分支）
4. 更新 `README.md` 和 `CODE_WIKI.md`

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

### v4.0.8.2-dev (2026-08-16 ~ 2026-08-18) — 录制/弹幕/国际化/类型检查 系列修复

> 本批改动集中解决了多个历史遗留的「能跑但录制/弹幕经常失败」类问题，并通过真机实测闭环验证。下分模块概述，详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**🎯 录制引擎核心修复（影响所有平台）**
- **致命结构 Bug**：录制主链曾被嵌套在 `if headers:` 条件内，导致抖音/斗鱼等无专属请求头的平台**从未真正录制**（仅显示"正在直播中"）。已修复——条件仅控制请求头插入，录制链无条件执行。
- **斗鱼崩溃修复**：`select_source_url` 返回空时不再触发 `UnboundLocalError`（标题变量未绑定），直接告警并等待下一轮；末位候选的 content-type 拒绝与 m3u8 Range-GET 偶发 403 现均支持「重试一次再定罪 / 末位告警放行」，根治斗鱼 HLS 假红与 FLV ~70 秒被 CDN 掐断。
- **流地址校验三层降风控**：新增「探针节流 + 重试抖动 + 被拒后退避（仅虎牙）」机制，消除 CDN 按机器人节奏指纹识别导致的 403 失败循环；校验器与 ffmpeg 双端 User-Agent 现已**一字不差**对齐（指纹自洽，防校验假红/假绿）。
- **HTTPS 录制**：`是否强制启用https录制` 对「虎牙直播」平台跳过（其 `*.hls.huya.com` 仅 http 可用，强制 https 会制造「校验 http 通过、录制 https 被拒」的假绿）。

**🐯 虎牙专项（多 CDN 选源 + Referer 纠偏）**
- 改为**枚举全部 CDN 候选**（HS/HW/TX/AL），不再固定取首位或固定 TX 优先；统一降为 `http://` 并保留原始防盗链参数，由 `select_source_url` 逐条可达性校验择优，动态规避任意离线线路。
- **Referer 规则已移除**：实测虎牙 CDN 现已反向校验——**带 Referer 一律 403，不携带 Referer 时 HS 线路才 200**。历史上注入的 Referer 规则反成录制失败元凶，已清除。
- App 路径（`get_huya_app_stream_url`）TX 选中时与 `record_url` 一致地做 `tars_mp→huya_webh5`/`bhct→bgct` 参数替换，根治「priority 选源后 TX 仍带原始 `tars_mp` 导致秒级断流」的回归。

**📺 B站弹幕认证链闭环**
- 修复 spi 端点拼写（`/finger/sp` → `/finger/spi`，少写结尾 `i` 导致 200+空 body）；buvid 获取链新增 `www.bilibili.com` 首页 Set-Cookie 备取路径，并区分真实 buvid 与随机 UUID 兜底（标记 `is_fallback`）。
- 弹幕进房包**观众 uid 误传主播 uid** 导致 AUTH 软拒绝（连接保持、0 弹幕）已修复；`_decode_packet` 显式校验 operation=8 回应的 code，非 0 时告警+断开+失效 buvid 缓存（避免被拒 UUID 死循环），并新增 8 秒静默拒绝看门狗兜底。
- 弹幕三元组（OD/BD/UHD app 路径）返回补全，消除原静默跳过。

**🌐 国际化机制修复**
- 补齐缺失的 `zh_CN.mo` 编译产物并随仓库分发；`init_gettext` 改为显式 `languages=["zh_CN"]` 加载，**不再依赖 `LANG`/`LANGUAGE` 环境变量**（Windows 普遍未设置）。中文环境下英文提示（如「IP banned」）现已正确翻译。

**🍪 访客 Cookie 统一缓存**
- 新增 `src/cookie_cache.py`：以「归一化网址 + 代理」为 key 的进程级共享缓存，抖音 ttwid、快手 did 等通用访客 cookie 跨模块/跨房间复用同一份，**杜绝同网址重复拉取触发风控**。

**🧩 架构与质量**
- `main.py` 拆分 6 类功能至 `src/` 子模块（ffmpeg_proc / video_postprocess / stream_select / notify / recorder_status / config_io），经 re-export 保持兼容；弹幕子包 `src/danmaku/*` 扁平化至 `src/`；注释规范落地：全量 `"""` docstring 转为 `#` 行注释。
- 配置健壮性：`config.ini` 不可写时 `import main` 阶段不再崩溃（读回 best-effort）；旧键兼容仅读取不写回；备份旋转删除改为 best-effort。
- 全库 UA 统一升级至 2026 基准（Chrome/141、Firefox/148、移动端 Android 14 Chrome/141），消除过旧指纹。

**🛡️ 平台兼容与运行健壮性**
- **跨事件循环锁误判风控根治**（`src/async_http.py`）：模块级单例 `asyncio.Lock()` 在首个 room 的 `asyncio.run()` 循环惰性绑定后，后续 room 起新循环再次 `await` 会抛 `bound to a different event loop`，被 `async_req` 吞掉返回空串、被 `spider.py` 误判「风控空响应」并级联回退 HTML 抓取失败。现改为随**当前事件循环**缓存/重建 `(lock, loop)` 二元组（与 `_client_cache` 机制一致），`tests/test_async_http.py` 新增 `TestGetClientLock` 锁定该行为。
- **空白异常日志收口**：`async_req` / `_close_all_clients` 及跨循环旧 client 关闭处原为 `logger.debug(e)`，Windows 下异常 `str()` 为空时打出空白日志、无法定位；全部改为带 `type(e).__name__`（必要时含 URL）。
- **平台兼容修复**：`web.py` 的 ctypes 3.13+ 兼容（`windll` 已移除）+ 64 位 `HWND` 截断导致控制台窗口隐藏失败，改用 `ctypes.WinDLL` 并显式声明 `argtypes`/`restype`；`main.py` 修复 PATH 拼接覆盖后续追加/重复插入（改用实时 `os.environ["PATH"]` 并去重）；`msg_push.py` 修复 `tg_bot` 未绑定变量（`NameError` 崩溃）与 Telegram 业务失败（`{"ok": false}`）漏检，成功标识改为 chat_id。

**🧪 静态检查 / CI 加固**
- mypy / basedpyright 在 `src/` 与 `main.py` 全面清零（含 spider.py / sync_http.py / web_api.py `_FAILED_LOGINS` 补全 `deque` 类型参数消除 10 处级联告警）；`main.py` 的 `get_startup_info()` 改为返回 `object | None`（`sys.platform == "win32"` 门控保留）以根治 Windows 专属 typeshed 符号跨平台 `TYPE_CHECKING` 别名误报；`gui.py` / `build_exe.py` / `web.py` / `msg_push.py` 同期 basedpyright 0/0/0、mypy 通过。
- 脚本健壮性：`scripts/check_coverage.py` 修复全局覆盖率 < 50% 时门禁被跳过、临时文件残留、`subprocess.run` 缺 `encoding`（Windows 非 UTF-8 locale 崩溃）；`scripts/smoke_test.py` 修复 Windows GBK 控制台 `UnicodeEncodeError` 崩溃与常量重定义、失败标记改 ASCII、新增 `_safe_print` 容错。
- CI `lint` job 运行 Python 由 3.12 升到 3.13（与 `target-version` 最高值对齐，消除 AST 安全校验告警噪声），`black --check .` 格式违规已手工修复。
- 全量测试约 635 passed / 2 skipped（排除已知沙箱删除保护项）。

### v4.0.8.1-dev (2026-08-01 ~ 2026-08-09) — 注释规范 / 冒烟测试 / GUI 优雅退出 / 校验修复 整合

**注释规范与质量基线**
- 模块/函数说明统一使用 `#` 行注释，不再使用三引号 `"""` 文档字符串。
- 全量审查通过：`compileall` / `black`(行宽120) / `isort` / `mypy`(src/) / `pytest` 全绿（417 passed，无回归；08-01 增量 78 passed，`ruff` 亦通过）；修复 black 格式违规 2 处。
- ⚠️ **构建 Bug 修复（`pyproject.toml`）**：`email="ihmily@github"` 非合法 IDN 邮箱，新版 setuptools 拒绝构建、`pip install .` 必失败；已改为 `ihmily@users.noreply.github.com`（CI 裸装未触发，**本地开发必踩**）。

**新增 Web/接口冒烟测试工具**
- `scripts/smoke_test.py`（**零依赖、配置驱动**）：支持 GET/POST、`base_url` 拼接、期望状态码、文本/JSON 断言；输出控制台/JSON/HTML 报告；失败退出码非 0。默认用例 `scripts/smoke_web.json` 探活 Web 面板 `http://127.0.0.1:8000`。

**GUI 停止录制优雅退出加固**
- **根因**：`pythonw.exe` 启 GUI 时 `sys.executable` 指向无控制台的 pythonw，其拉起的录制子进程也无控制台 → `AttachConsole` 必失败、CTRL_BREAK 结构性不可达；现检测到 pythonw 时改用同目录 `python.exe`（console 子系统）启录制核心。**打包版（CLI exe `console=True`）不受影响**。
- CTRL_BREAK 失败改 `taskkill /F /T /PID` 整树终止（连同 ffmpeg 清理），日志如实区分「优雅退出」与「硬杀路径」。
- 实测：pythonw 父进程复现后 `AttachConsole` 成功、`SIGBREAK` 处理器触发（`signum=21`）；另 Python 3.13 的 `time.sleep()` 不被 CTRL_BREAK 唤醒（走 pending-call 机制），因 `main.py` 录制主循环无长 sleep（≤5s），15 秒窗口内 `safe_exit` 必执行清理。
- ⚠️ **遗留（未改）**：旧 `gui_legacy.py` 用 `CREATE_NO_WINDOW` 启子进程，`send_signal(CTRL_BREAK_EVENT)` 静默无效，优雅停止从未生效（每次等 15 秒超时强杀）；**建议迁移到 gui.py**。

**流地址校验修复（HLS/代理/日志）**
- 空白日志收口：`get_response_status` 异常日志现带 URL 与异常类型（如 `ConnectTimeout`/`TimeoutError`），消除 Windows 下 `socket.timeout` 的 `str()` 为空只打空白。
- m3u8 误判修复：HEAD 探测范围从 `400/401/403/405` 扩至**含 404 的所有非 2xx**；对 `.m3u8` 一律补 `Range: bytes=0-0` GET 探测（200/206 即判可达），避免可用 HLS 源被误回退 FLV。
- `_validate_stream_url` 新增 `verify` 参数沿用全局 SSL 开关，所有失败路径记 warning（URL + 异常类型/状态码/content-type）。
- `select_source_url` 新增 `proxy_addr` 并透传三处校验，修复 TikTok 等需代理平台直连校验超时误判不可达。

**抖音录制增强**
- 支持 5 种 URL 格式：网页/App 直播间、抖音号拼接（含 VR）、App/网页端主播主页。
- 主播主页（格式 5）直接提取 `sec_user_id` 跳重复下载，请求数 4→3；主页类链接现正确透传 `proxy_addr`/`cookies`（修复静默丢失）；新增 `sec_user_id → 抖音号` 进程级缓存（30 分钟 TTL）。
- CDN 对 HEAD 返 4xx 时补 `Range` GET 探测；`web/enter` 偶发 `status_code=10002` 首次失败后静默重试一次，跳过约 1MB HTML 兜底抓取；删除死代码 `get_douyin_stream_data`。

### v4.0.8.1 (2026-07-30) — Web 面板 / 画质监控 / 代理与类型修复

- **新增 Web 管理面板**（`web.py`+`src/web_api.py`+`src/web_config.py`+`web/`）：仪表盘、直播间管理、配置编辑、SSE 日志推送。
- **新增 GUI 画质监控**：实时检测实际画质是否匹配设置，覆盖抖音/TikTok/快手/虎牙/斗鱼/B站/网易CC 七平台。
- **配置项新增**：`web_show_console`（后台隐藏运行）、SSL 证书验证全局开关（config.ini）、日志文件开关。
- **连接优化**：HTTP 客户端按 (代理, verify, http2) 维度复用连接池；代理检测从联网探测改为读本地系统代理配置。
- **缺陷修复**：`trace_error_decorator` 同步装饰器误用于 71 个异步函数致错误捕获失效；`asyncio.run()` 致 httpx 跨事件循环复用问题；多个 IndexError/KeyError/类型错误。
- **凭据清理**：硬编码过期凭据改自动获取（抖音 ttwid、快手 did、Twitch Client-Id 等）。
- **构建/依赖**：Dockerfile 升 Node.js 22 LTS、非 root 运行；新增 `pydantic>=2.0.0` 依赖声明；全项目类型检查（Pyright/Pyrefly/basedpyright）清理。

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