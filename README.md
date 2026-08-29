![video_spider](https://socialify.git.ci/y123ao6/DouyinLiveRecorder/image?font=Inter&forks=1&language=1&owner=1&pattern=Circuit%20Board&stargazers=1&theme=Light)

简体中文&nbsp;&nbsp;|&nbsp;&nbsp;[**English**](README_EN.md)

## 💡 简介

[![Python Version](https://img.shields.io/badge/python-3.14+-blue.svg)](https://www.python.org/downloads/)
[![Supported Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-blue.svg)](https://github.com/y123ao6/DouyinLiveRecorder)
[![GitHub issues](https://img.shields.io/github/issues/y123ao6/DouyinLiveRecorder.svg)](https://github.com/y123ao6/DouyinLiveRecorder/issues)
[![Latest Release](https://img.shields.io/github/v/release/y123ao6/DouyinLiveRecorder)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/y123ao6/DouyinLiveRecorder/total)](https://github.com/y123ao6/DouyinLiveRecorder/releases/latest)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Stars](https://img.shields.io/github/stars/y123ao6/DouyinLiveRecorder?style=flat-square)](https://github.com/y123ao6/DouyinLiveRecorder/stargazers)

一款**简易**的可循环值守的直播录制工具，基于 FFmpeg 实现多平台直播源录制，支持自定义配置录制以及直播状态推送。

上游项目：[ihmily/DouyinLiveRecorder](https://github.com/ihmily/DouyinLiveRecorder)

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 🎯 **多平台支持** | 支持抖音、TikTok、YouTube、快手、虎牙、斗鱼、B站等 **51 个平台**（对外标称 60+，持续添加中） |
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

> 合计 **51 个**平台（对外标称 60+，含持续添加中的平台）。各平台数据获取函数位于 `src/spider.py`，流地址解析位于 `src/stream.py`。

**弹幕录制支持（5 个平台）**：抖音直播 | 斗鱼直播 | 虎牙直播 | B站直播 | TwitchTV

**实际画质回采与降级告警（7 个平台）**：抖音 | TikTok | 快手 | 虎牙 | 斗鱼 | B站 | 网易CC

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
│   ├── room.py                # 直播间信息解析
│   ├── utils.py               # 工具函数库
│   ├── logger.py              # Loguru 日志配置
│   ├── proxy.py               # 代理检测
│   ├── ab_sign.py             # 抖音 A-Bogus 签名
│   ├── ttwid.py               # 抖音访客 ttwid 获取/缓存
│   ├── node_install.py        # Node.js 自动安装/初始化
│   ├── ffmpeg_install.py      # FFmpeg 安装脚本
│   ├── ffmpeg_proc.py         # ffmpeg 子进程管理（抽离自 main.py）
│   ├── video_postprocess.py   # 录制后处理（转封装/转码）
│   ├── notify.py              # 直播状态消息推送（抽离自 main.py）
│   ├── recorder_status.py     # 录制状态跟踪（抽离自 main.py）
│   ├── config_io.py           # 配置读写/数值转换/备份（抽离自 main.py）
│   ├── cookie_cache.py        # 访客 Cookie 进程级共享缓存
│   ├── weverse_auth.py        # Weverse 平台认证
│   ├── http_config.py          # HTTP 客户端共享配置（SSL 验证开关）
│   ├── async_http.py          # 异步 HTTP 客户端 (httpx)
│   ├── sync_http.py           # 同步 HTTP 客户端
│   ├── web_api.py             # Web 管理面板 FastAPI 应用
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
│   └── javascript/            # JavaScript 签名脚本
│       ├── crypto-js.min.js
│       ├── x-bogus.js
│       ├── haixiu.js
│       ├── laixiu.js
│       ├── liveme.js
│       ├── migu.js
│       └── taobao-sign.js
├── web/                        # Web 管理面板前端
│   ├── index.html              # 单页应用入口
│   ├── app.js                  # 前端逻辑（API、SSE、渲染）
│   └── style.css               # 样式表（主题、响应式）
├── typings/                    # 第三方库类型存根（静态检查用）
│   ├── customtkinter/          # customtkinter 存根
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
│   │   ├── zh_CN.po           # 中文翻译源（288 条）
│   │   └── zh_CN.mo           # 编译后翻译（运行时必需，随仓库分发）
│   ├── en_US.json              # English (US)（JSON 格式目录）
│   ├── en_GB.json              # English (UK)（英式拼写变体）
│   └── zh_TW.yaml              # 繁體中文（YAML 格式目录，需 PyYAML）
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
# 界面语言：zh_CN | en_US | en_GB | zh_TW（留空跟随系统语言；值支持 zh_cn/zh-CN/en/en-GB/zh-Hant 等写法，自动归一；对应语言文件缺失时回退 en_US）
language = zh_CN
# 是否跳过代理检测(是/否)
是否跳过代理检测(是/否) = 是
# 是否启用日志文件(是/否)
是否启用日志文件(是/否) = 是
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
# 是否使用代理ip(是/否)
是否使用代理ip(是/否) = 否
# 代理地址
代理地址 =
# 同一时间访问网络的线程数
同一时间访问网络的线程数 = 3
# 循环时间(秒) - 直播状态检测间隔（默认 120）
循环时间(秒) = 120
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
# 是否启用https录制 - 已整合原「是否强制启用https录制」与「是否禁用SSL证书验证(是/否)」：
# 开启 = 流地址以 https 拉流并跳过 SSL 证书校验；关闭 = 流地址以 http 拉流并恢复默认证书校验
# （旧键「是否强制启用https录制」的值会自动迁移继承；TikTok/YouTube 等 https-only 海外平台在关闭时保持原样）
是否启用https录制 = 否
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
是否录制弹幕(是/否) = 否
# 是否弹幕监控(是/否) - 仅实时查看弹幕、不写 SRT（与弹幕录制解耦，可单独开启）
是否弹幕监控(是/否) = 否
# 弹幕分片时长(秒) - SRT 分片粒度，建议与「视频分段时间(秒)」一致
弹幕分片时长(秒) = 1800
# 弹幕录制平台(逗号分隔) - 目前支持的 5 个平台
弹幕录制平台(逗号分隔) = 斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV
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
# 单独指定抖音 ttwid（留空则由 src/ttwid.py 自动获取并进程级缓存）
ttwid =
快手cookie =
tiktok_cookie =
虎牙cookie =
斗鱼cookie =
yy_cookie =
b站cookie =
小红书cookie =
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
# 受信任的反向代理来源（逗号分隔）。留空时不解析 X-Forwarded-For；
# 置于 Nginx/Caddy 之后时填入代理 IP，登录限流才能取到真实客户端 IP
web_trusted_proxy =
```

> `web_host` 在仓库默认配置中为 `127.0.0.1`（仅本机可访问）。Docker 或需局域网/公网访问时改为 `0.0.0.0`，并务必同时开启 `web_auth_enable` 与 `web_password`。

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
|------|------|------|
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

### 弹幕录制与弹幕监控

弹幕功能由两个**相互解耦**的开关控制，可单独或同时开启：

| 配置项 | 作用 |
|--------|------|
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
|--------|--------|----------|
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
- **内置 Node.js 24 LTS**：用于运行 JavaScript 签名脚本

## 🛠️ 开发指南

### 环境要求

- Python >= 3.14
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

> **五工具质量门禁**：本项目以 `mypy`（src + tests）/ `basedpyright`（tests）/ `pytest`（0 warnings）/ `black --check .` / `isort --check-only .` 五工具联合作为质量门禁，CI 全绿为合入前提。当前基线：**699 passed / 2 skipped / 0 warnings**。

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

## ❤️ 贡献者

<a href="https://github.com/y123ao6/DouyinLiveRecorder/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=y123ao6/DouyinLiveRecorder" />
</a>

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源，欢迎 Star 和 Fork！

## ⏳ 更新日志

### v4.0.9.2 (2026-08-28 ~ 2026-08-29) — Web 面板录制手动控制 / 虎牙·斗鱼蓝光细粒度画质档位 / 性能审查优化落地（P1~P5）/ 探针退避窗口自愈与虎牙 FLV-first / Web 后台日志 sink 重建

> 本版本沿「可控性、画质粒度、高并发性能」三条主线：Web 面板移除启动自动录制、新增「开始/停止录制」手动控制（全局开关 + 录制主链 7 处中断点 + ffmpeg 分级优雅终止）；虎牙/斗鱼支持蓝光细粒度档位（蓝光4M/8M/20M/30M 的选档 → 拉流 → 不可用就近降级全链路）；性能审查落地 P1~P5 五项优化（80 房间选源探针耗时 12.7s → 1.15s），并经三轮真机验证根治虎牙冷启动「探针假绿 → ffmpeg 403」死循环（退避窗口对齐主循环 + 录制成功清除退避 + 虎牙 FLV-first）与 Web 后台模式日志写向被隐藏窗口的问题。**无破坏性变更**（配置项与运行时语义完全兼容；虎牙选源顺序反转为 FLV-first、斗鱼保持 HLS-first，属行为变更）。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**🎥 Web 面板录制手动控制（新增功能）**
- 全局开关 `main.recording_enabled`（默认 True，CLI/GUI 直跑完全不受影响）：Web 启动录制引擎前先置 False，面板默认**不再自动录制**；点「开始录制」后主循环按 URL 配置逐个拉起房间，配置热加载、并发调度器、弹幕监控全程保持运行。
- 录制主链注入 **7 处中断点**：ffmpeg 轮询（1s 周期）、直下下载 chunk 级、房间线程入口、直下失败判定排除、循环等待期打断、主循环拉起新线程前、线程退出 finally 兜底（`remove_room_from_running` 幂等清理运行列表，保证重新开始后房间能再次拉起）。
- 新增 `POST /api/recording/toggle` 切换端点（处于既有 Bearer 认证中间件覆盖内）与状态快照 `recording_enabled` 字段；前端新增「开始/停止录制」按钮与运行状态标签，仪表盘 2s 轮询持续同步真实态（按钮防重复点击、引擎存活联动禁用）。
- **停止语义为主动分级优雅终止**：轮询命中开关关闭即按「stdin 写 'q'（写完文件尾，TS/FLV/分段不损坏）→ terminate → kill」三级升级（总窗口 30s），进程 wait 回收、注册表注销，无孤儿 ffmpeg；停止中断不计入错误样本（防止误触按 host 熔断与错误背压降容）。
- `recording_enabled` 为会话级运行时开关、不持久化：重启后面板回到停止态，避免从后门重新引入「启动即自动录制」。

**🎚️ 虎牙/斗鱼蓝光细粒度画质档位（新增功能）**
- 画质代码层扩展：`QUALITY_LEVEL` / `QUALITY_MAPPING_BIT` / `QUALITY_CODE_TO_ZH` 由 6 项扩为 10 项（新增 `BD30`/`BD20`/`BD8`/`BD4`）并新增 `BD_SUB_TIERS` 冻结集合；`get_quality_index` 将蓝光子档位折叠到 `BD` 槽位，抖音/TikTok 等按数字 0–5 选档平台的语义完全不变。
- 虎牙：新增 `HUYA_FIXED_TIERS`（ratio 即码率上限 kbps，直接拼在 FLV/HLS URL query 上选档、流地址路径不变）；`exsphd` 档位表优先、`gameLiveInfo.bitRate` 兜底推导可用档；请求档不可用时**就近向下降级**并明确告警（含请求档/房间上限/实际档），无任何更低档时按原画拉流、链路不中断。
- 斗鱼：新增 `DOUYU_RATE_BY_CODE` / `DOUYU_RATE_TO_CODE` / `DOUYU_RATE_DESC`；请求档被限制（如游客态原画被拒）时按全序**本地最多回退 2 档重试**；服务端「就近钳制」的真实档位经 `rate` 字段回采（实测请求 rate=8200 无此档被钳到 rate=4 → 蓝光4M）。斗鱼无 20M/30M 档，选择时按蓝光8M 请求。
- Web 面板画质下拉新增 蓝光30M/20M/8M/4M 四个选项；真机 ffprobe 采样确认各档分辨率/帧率与档位表一致（原画 2560×1440@60、蓝光30M~8M 1920×1080@60、蓝光4M 1080p30、超清 720p30、流畅 450p24）。

**⚡ 性能优化（审查落地 P1~P5）**
- **P1 探针客户端整轮复用**：`select_source_url` 全部候选共用一支 `httpx.Client`（`finally` 关闭，UA/Referer/Cookie 改逐请求下发）；80 房间 × 10 探针的每轮选源耗时 **12.7s → 1.15s**，并发连接峰值反而 4 → 1。刻意不做全局客户端缓存（虎牙 CDN 按连接预算限流，常驻 keepalive 会与 ffmpeg 拉流争抢预算），并实测证明**禁止为保险关 keepalive**（反而 8 连接 / 72.99ms，收益全退）。
- **P2 `requests.Session` 线程级复用**：`sync_http` 经 `threading.local` 每线程一支 Session（125 个调用点全部受益），实测单请求 11.9ms → 1.47ms。
- **P3 主循环去重容器 set 化**：`url_comments` / `line_list` / `url_line_list` 由 list 改 set（成员检测 O(N²) → O(1)），`url_comments.discard` 取代每行整表重建。
- **P4 调度器计数增量**：熔断窗口与全局错误窗口改增量维护（O(1) 替代持锁下 O(40) 全量求和），缩短锁持有时间。
- **P5 高频正则提模块级常量**：表情模式（约 400 字符）、URL 片段、HLS 带宽、抖音 HEVC 等 5 处函数内 `re.compile` 上提为模块级常量；`update_config_line` 按 key 编译的正则经 `functools.lru_cache` 缓存。

**🐛 问题修复（真机验证衍生）**
- **探针退避窗口自愈（虎牙假绿死循环根因）**：原固定 60s 退避窗口小于主循环默认 120s 间隔——快速失败记入退避后下一轮 T+124s 才到、早已过期，历史日志中「CDN 探针退避中」告警从未出现；改为 `_probe_backoff_window() = max(60s, 循环间隔 + 70s)`，覆盖「单轮等待 = 间隔 + ±5s 抖动 + 错误窗口满 5 次再 +60s」的最坏节奏。
- **录制成功撤销探针退避**：新增 `clear_ffmpeg_reject()` 与失败侧 `mark_ffmpeg_reject` 配对——已恢复的线路不再被窗口内继续跳过、白白回退到次优线路。
- **虎牙选源反转为 FLV-first**：三轮真机实证 HLS 三条 CDN（hs/tx/al）冷启动探针假绿（探针 200/206、ffmpeg 打开即 403），FLV 每轮稳定可用（最长连录 6 分钟）——虎牙候选顺序改为 FLV → HLS → record_url，冷启动假绿损失约 2 分钟 → 0（斗鱼绝不加入，其游客态 FLV 约 70 秒被 CDN 掐断必须 HLS-first）；h265 候选在构建统一候选序列时即剔除，不再白烧探针。真机对比：修复前 5 次秒退、12 分钟才稳定 → 修复后 1 次秒退、2 分钟即稳定。
- **Web 后台模式日志 sink 重建**：loguru 的 sink 在 `add()` 时绑定具体对象、不随 `sys.stderr` 重定向而变——不重建则 DEBUG/WARNING 全部写向被 SW_HIDE 隐藏的控制台，`web_console.log` 只剩 print 输出（实测曾据此把「探针假绿」误判成「校验未执行」）；`logger.py` 新增 `rebind_console_sink()`，`web.py` 后台模式重定向后重建 sink，并补 `sys.stderr is None` 判空（pythonw / 冻结 exe 导入期静默崩溃根治）。
- **Web 录制控制双轮审查修复**：前端状态标签选择器缺陷（容器实为 class 却用 `#id` 选择器、状态永不切换，P1）等 3 处。

**🧪 测试与验证**
- 新增 `tests/test_quality_tiers.py`（29 用例：子档位映射/索引折叠/虎牙就近降级/斗鱼重试链）、`tests/test_logger_console_sink.py`（3 用例：跟随当前 stderr / 替换而非追加 / None 静默）；`test_stream_select.py` 新增客户端整轮复用与逐请求头、退避窗口覆盖主循环周期、成功清除退避、虎牙 FLV-first 与斗鱼保持 HLS-first 用例；`test_record_failure_feedback.py` 增「停止录制中断不采样」用例；`test_web_api.py` 增录制开关端点用例。
- 全量 `pytest` **786 passed / 2 skipped**；black / isort / `compile_po.py --check` 全绿。类型门禁存数处已知遗留（`stream.py:609` 的 mypy 报错、`test_quality_tiers.py` 的 basedpyright 5 处 `await_args` Optional 访问、CI 测试矩阵 3.13 档与 PEP 758 语法冲突），均不影响运行时，修复项已记录于 CODE_WIKI 总览条目「验证」节。
- 三轮真机验证（虎牙 880214 / chuhe、斗鱼 3168536）：退避告警首次出现、FLV 稳定连录 6 分钟、`web_console.log` 恢复完整 DEBUG/WARNING；斗鱼 rate 钳制与回采行为实测吻合。

### v4.0.9.1 (2026-08-27 ~ 2026-08-28) — 高并发调度加固 / 本地化系统修复 / 编译与熔断门禁修复 / CI 工作流优化与重试收敛

> 本版本为 4.0.9 调度体系的审查修复与加固批次，并收尾本地化子系统：全量质量门禁 + 并行代码审查发现并修复多个高危/中危缺陷，i18n 目录经全仓 AST 扫描全量补全至 496 条、解除 i18n 模块语法阻塞并重新编译 `zh_CN.mo`；08-28 追加 CI 工作流优化（重试收敛为复合动作）、PEP 758 格式化随 black 26 落地与仓库元数据八文件同步。**无破坏性变更**（配置项与运行时语义完全兼容）。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**✨ 新增功能**
- **Web 配置行级追加 API**：`web_config.py` 新增 `append_config_line(config_file, section, key, value)`，在键/节缺失时按行级文本风格补建（与既有 `update_config_line` 互补），便于缺键配置的安全写入。
- **语言切换写回降级**：`web_api.py` 的 `PUT /api/language` 写回在行级替换失败时自动调用 `append_config_line` 节末追加补建，历史 config.ini 缺 `language` 键时不再恒 500。
- **i18n 四目录全量补全（288 → 496 条）**：AST 扫描全仓运行时 `print()`/`logger.*()` 常量串（47 文件、355 串），新增 204+ 条翻译（并发调度日志、流地址校验全套消息、B站 buvid 认证链、弹幕采集/监控、七渠道推送失败分支、ffmpeg/Node.js 安装、配置读写等）；四语键集完全一致，重编译 `zh_CN.mo`（`--check` 字节级同步）。
- **CI 网络安装重试复合动作（`.github/actions/retry`）**：新增复合动作统一包装 pip / apt / choco / brew 网络安装命令的线性退避重试（`command` / `label` / `attempts` / `backoff` 可参数化），取代两份 workflow 共 13 处几乎相同的内联重试脚本（ci.yml 9 处 + build-release.yml 4 处）——重试策略唯一事实源为 action.yml 一处，调整一处全局生效；经成功/失败双路径模拟验证。

**🐛 问题修复**
- **i18n 本地化系统阻断（高危）**：`i18n.py`（3 处）与 `scripts/compile_po.py`（1 处）的 Python 2 风格 `except A, B:`（含一例三异常逗号）多异常写法改为 `except (A, B):`，解除 Python 3 硬 `SyntaxError`——此前 `i18n` 无法 `import`、`.mo` 无法编译、CLI/GUI/Web 本地化整体失效；修复后受管 3.13 与 3.14 运行时均合法，并重新编译 `zh_CN.mo`（496 条，`--check` 字节级同步）。
- **CI black 门禁（PEP 758 格式化）**：上述 4 处元组括号随后按 black 26.5.1（`target-version=['py314']`，CI 与本地同版本）的 PEP 758 规范化统一为免括号形式（`except A, B:` 与 `except (A, B):` 在 3.14 下完全等价、语义零变化），CI `black --check` 恢复绿色；**此 4 处今后由 black 维护，勿手工改括号**。
- **编译同步门禁恒真（P1）**：`scripts/compile_po.py` 的 `write_mo()` 改为纯内存产出（去除写盘副作用），落盘决策上移至调用方，`--check` 不再「先落盘再读回自比」（此前恒真），改为真实比对已提交 `.mo`；`ci.yml` 的 paths-filter 新增 `i18n/**`，纯翻译变更也会触发 static 门禁。
- **熔断探针租约自愈（高危）**：根治 `PlatformBreaker` half-open 探针泄漏——探针轮以 `continue` 结束且不上报样本时 `_probing` 标志永不复位、该 host 永久熔断直到进程重启；新增探针租约（`_PROBE_LEASE_SECONDS = 60s`）超时自动重新授予，实现自愈。
- **调度成功采样缺口（中危）**：`start_record` 解析成功分支补报 `record_success(record_host)`（与失败分支对称），half-open 探针房间长录期间同 host 其余房间不再持续饿死。
- **直下路径熔断采样缺口（P1）**：`main.py` 直下下载分支「非 200 / 网络异常」失败原在函数内部消化为 `False`、调用方不上报样本，坏线路绕开按 host 熔断被无限重撞；新增 `record_error(record_host)` 补报（被注释/退出标志的中断不计样本）。
- **调度器线程安全 + 类型/日志**：`ConcurrencyScheduler` 配置字段加锁（单次加锁快照 + 锁内写入），消除主线程与 `adjust_loop` 守护线程间理论竞态；`notify.py` 三参 `getattr(main,"scheduler")` 改直接属性访问消除 mypy 假绿、`run_script` 三处裸 `logger.error(e)` 补异常类型与命令上下文。
- **直下日志缺失修复**：`main.py` 的 `direct_download_stream` 非 200 分支补请求 URL、异常分支补 `{type(e).__name__}`（Windows 超时类 `str()` 为空）；`async_http.py` 两处裸 `logger.debug(e)` 规范为带 URL/类型的格式。
- **弹幕参数每轮重置恢复**：`main.py` 内层监测循环顶部恢复 `record_danmaku_args = None`（此前重构合并了轮内重置点）。
- **损坏 YAML 目录致 500**：`_load_yaml_catalog()` 补捕获 `yaml.YAMLError`（非 OSError/ValueError 子类），降级跳过到下一格式。
- **ISSUE_TEMPLATE 版本缺失**：`.github/ISSUE_TEMPLATE` 四个模板 Python 版本下拉补 `Python 3.14`。
- **i18n 提取器两处噪声源**：`scripts/extract_i18n_strings.py` 的 `is_valuable()` 改以花括号块之外的残渣判定（纯占位符模板如 `{color}{text}` 不再误报为缺失）、po 头部空 `msgid ""` 比对前剔除（消除四语一致性「少 1」假阳性）；修正后重跑确认四语目录零缺失（318 条有价值串全在库、各 496 条）。

**🎨 体验优化**
- **前端硬编码中文入翻译字典**：`web/app.js` 约十处硬编码中文字符串改走内嵌四语字典 `t()`（录制/弹幕空态、截断提示、开关/操作 toast、配置/文件列表空态、进入/下载按钮等），英文/繁体界面不再显示简体中文。
- **GUI 崩溃弹窗去重**：`gui.py` 顶层异常不再双弹窗/日志双份堆栈，`_bootstrap_error_sink` 置位标记后 re-raise 触发的 excepthook 据此跳过。

**🔧 CI / 工程维护**
- **CI 工作流优化（ci.yml 重写，job 与门禁语义不变）**：`actions/checkout` v5→v7、`setup-python` v6→v7（与 build-release.yml 对齐消除版本漂移）；apt 安装补强化参数（`DEBIAN_FRONTEND=noninteractive` + `Acquire::Retries=3` + `--no-install-recommends`，更抗网络抖动）；macOS `brew trust aws/tap` 拆为独立幂等步骤、`HOMEBREW_*` 变量改命令内 `export`；头注释补 job 拓扑图与「止于验证、不含部署」职责边界。
- **仓库元数据八文件同步**：requirements.txt / Dockerfile 过时的 `src/danmaku/` 路径注释修正为实际模块位置；`.dockerignore` 补 16 个排除项（本地工具目录 / `uv.lock` / `scripts/` / 双语文档等，镜像上下文瘦身）；`.gitignore` 补 `.mimosa/` 等；pyproject 清理死目录；docker-compose 示例版本对齐 `4.0.9.1`；`AGENTS.md` 模块计数 39→41 并新增 CI/workflow 约定小节。

**🧪 测试与验证**
- 新增 `tests/test_record_failure_feedback.py`（5 → 7 用例）、`tests/test_web_api.py` 缺键补建/边界用例；`test_scheduler.py` 探针租约自愈（15 → 16）、`test_i18n.py` 损坏 YAML 降级并适配 `write_mo()` 新签名。
- 全量 `pytest` **744 passed / 2 skipped**；black / isort / mypy（Windows + Linux 双平台）/ basedpyright 全绿；`compile_po.py --check` 字节级同步、提取器零缺失；两 workflow YAML 结构断言（needs 链 / retry 调用计数 / action 版本计数）通过。

### v4.0.9 (2026-08-23 ~ 2026-08-24) — 高并发多平台录制调度优化 / 录制反馈闭环 / 并发双模式 / Python 3.14 升级与语言键迁移 / 四语本地化目录统一与英式美式分流 / 类型与 CI 质量门禁修复

> 本批改动聚焦高并发（80+ 任务）多平台录制的调度中枢治理、录制侧反馈闭环与 Python 3.14 基线升级。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**🚀 高并发调度中枢（新增 src/scheduler.py）**
- 引入 `ResizableSemaphore`（运行期可重置容量）、`PlatformBreaker`（按 host 熔断器，closed→open→half-open 状态机）、`ConcurrencyScheduler`（自适应全局并发容量，默认下限 8 / 上限 128，错误率高时温和降容、永不低于安全下限）、`host_of(url)`。
- 取代旧「全局固定 3 槽信号量 + 单向错误率压制」模型，支持 80+ 任务跨多平台录制、降低排队延迟；单平台接口抖动被隔离降级，不再连锁拖垮全局。
- 仅在 `main.py` / `notify.py` 固定接线点接入，未改写 50+ 平台分派/录制函数，向后兼容；新增配置项「最大同时录制数(0=不限制)」（默认 0=不限制）。

**🔁 录制结果反馈闭环（虎牙 403 死循环根治）**
- 修复录制侧反馈缺失：`check_subprocess` 此前按退出码既不上报失败样本、轮末还无条件上报成功，导致按 host 熔断统计被稀释、永不触发，虎牙房间无限重撞「探针 200 → ffmpeg 403」死线路。
- 现按退出码上报成功/失败样本（按 host）；ffmpeg 快速失败（CDN 拒绝签名）触发 `mark_ffmpeg_reject` 探针退避（60 秒），下一轮改试下一 CDN 候选而非重试同一坏线路（退避白名单仅限虎牙）。
- 控制台状态行改为显示调度器实时并发容量（`_live_network_capacity`），不再误显配置值。

**⚙️ 网络并发双模式（动态调速 / 固定并发）**
- 在自适应容量基础上新增「固定并发」模式：「最大同时录制数(0=不限制)」兼作模式开关——=0 启用动态调速（随活跃任务数自适应、下限 8/上限 128），≠0 忽略动态调速器、容量恒为「同一时间访问网络的线程数」（热更新即时生效、最小 1 槽）。
- 按 host 平台熔断与模式正交，两种模式下均生效；同时录制上限仍由 `scheduler.set_recording_limit` 管控，不受模式切换影响。

**🐍 Python 3.14 升级 + 语言配置键迁移（综合维护）**
- 项目基线由 Python 3.10 提升至 `>=3.14`（`pyproject.toml` / `Dockerfile` / CI 全链路）；修复 `async_http.py` 在 3.14 下 `asyncio.get_event_loop()` 不再隐式创建事件循环的兼容问题。
- `config.ini` 语言键 `language(zh_cn/en)` 统一迁移为 `language`：留空跟随系统语言、非法值回退 en_US、GUI/Web 面板免重启热切换、启动自动迁移旧键。
- 修复 14 个源文件共 21 处 Python 2 风格 `except A, B:` 残留语法，使项目在 Python 3 下可导入/可测试；全量 `pytest` **714 passed / 2 skipped / 0 warnings**，black/isort/mypy/basedpyright 全绿。

**🌐 四语本地化目录统一与英式/美式英语分流**
- 统一 zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml 四份目录为同一 288 条 key 集合（原 282 条 + 补齐 build_exe.py 的 6 条打包/冒烟常量串）。
- 修正 en_US 内部混用的英式拼写（统一为美式 minimizes/minimized/canceled）；en_GB 原是 en_US 克隆，改写为真正英式（minimise/minimises/minimised/cancelled），仅在 4 条拼写相关条目上与 en_US 不同。
- 重新编译 zh_CN.po → zh_CN.mo（compile_po.py --check 确认字节级同步），不影响任何运行时逻辑。

**🧪 类型检查 / CI 质量门禁修复**
- 修复 CI `mypy src/` 两处报错：`i18n.py` 的 `ctypes.WinDLL` 平台门控（`sys.platform != "win32"` 早返回，双端干净）、`src/recorder_status.py` 三参 `getattr` 改为直接属性访问（消除 `no-any-return` 泄漏）。
- 修复 CI `pytest` 在 C/POSIX locale 下 `detect_system_language()` 回退路径未过滤 `("C","POSIX")` 导致断言失败；测试中 4 处 `patch.dict(os.environ)` 改为 `monkeypatch.setenv/delenv`（遵循 AGENTS.md 强制规约，规避 Windows 32767 字符上限溢出）。
- 修复 `src/config_io.py` 的 `read_config_value()` 在 Python 3.14 下含分隔符键 `write()` 抛 `InvalidWriteError` 的写回崩溃（内存完整序列化成功后才落盘，坏键回滚）。
- 全仓 black 26.5.1 + `target-version=['py314']` 重排（剥除 PEP 758 `except (A, B):` 括号），本地 dev venv 升级至 3.14.7；四大门禁在 3.14 环境全绿。

**📦 构建 / 依赖 / 平台适配**
- 版本号 `4.0.8.3` → `4.0.9`（唯一事实源）；`requires-python` 升 `>=3.14`、classifiers 收敛为仅 3.14；新增 `PyYAML>=6.0.3` 依赖（i18n 的 zh_TW.yaml 支持）。
- `Dockerfile` 基础镜像升 `python:3.14-slim-bookworm`、Node.js 源 `setup_22.x` → `setup_24.x`；CI 矩阵同步升 3.14。
- `src/spider.py` 咪咕 `get_migu_stream_url()` 现采用重写版 `migu.js` 输出带 `ddCalcu`/`sv` 参数的完整地址（移除本地过期固定 `sv=10010`）；FFmpeg 下载源 `wweb.lanzouv.com` → `wwasx.lanzout.com` 切换。

### v4.0.8.3 (2026-08-19 ~ 2026-08-22) — 主播名自动更新 / SSL 配置整合 / 四语国际化 / FFmpeg9·Node24 兼容 / 类型安全加固 / start_record 复杂度治理 / 窗口化崩溃加固 / 类型检查缺陷修复

> 本版本在 4.0.8.2 系列修复基础上补齐多项新增能力与底层兼容，并以 mypy / basedpyright / pytest(0 warnings) / black / isort 五工具门禁全绿收口。详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**👤 主播名自动更新（新增功能）**
- `URL_config.ini` 每次解析到最新主播名时，若与配置不同则自动回写配置文件；主播改名时同步重命名以其命名的录制文件夹及内部全部相关文件（TS/FLV/弹幕 SRT/字幕等同前缀产物），保证路径引用完整。
- 新增 `src/config_io.py:update_anchor_name` + `main.py:rename_anchor_directory`；改名只发生在该房间未录制时（先文件系统、后配置文件，全部成功才切换本轮使用名）；配置开关 `是否自动更新主播名(是/否)`（默认「是」，支持热加载），跳过自定义流地址与空白昵称。

**🔒 SSL / HTTPS 配置整合**
- 旧「是否强制启用https录制」+「是否禁用SSL证书验证(是/否)」合并为单一「是否启用https录制」：开启 = https 拉流 + 跳过证书校验，关闭 = http 拉流 + 默认严格校验。旧键只读迁移写回、不重建。
- 主循环每轮热同步 `set_https_recording` / `set_ssl_verify`；关闭时 `https://`→`http://`（TikTok/YouTube 等 https-only 海外平台保持原样，避免必然拉流失败）。
- 平台级覆盖 `禁用SSL证书验证的平台(逗号分隔)` 仅在 http 模式（需要证书校验时）生效；启动时自动追加必需平台（虎牙直播/B站直播），只追加不移除用户手填项。

**🌐 国际化四语重构 + 即时切换**
- `i18n.py` 重构：多格式目录加载（gettext `.mo` → `<lang>.json` → `<lang>.yaml`）、`SUPPORTED_LANGUAGES`（zh_CN/en_US/en_GB/zh_TW）、`normalize_language()` 别名归一、`set_language()` 热切换（无需重启）。
- zh_CN 目录补全至 282 条；新增 en_US/en_GB/zh_TW 三语翻译；Web 顶栏 + GUI 侧边栏语言选择器即时切换并持久化（Web 经 `GET/PUT /api/language`）；不再依赖 `LANG`/`LANGUAGE` 环境变量。zh_TW 需 PyYAML（缺失仅损失该格式）。

**⚙️ FFmpeg 9.0 / Node 24 兼容基线**
- 全库 ffmpeg 命令核查对齐 FFmpeg 9.0（2026-08-04 发布，TLS 证书验证默认开启），移除已废弃 CLI 参数与死参数 `-v verbose`；`-tls_verify 0` 统一经 `get_effective_ssl_verify` 裁决。
- `src/javascript/migu.js` 全量重写：适配咪咕播放器 mgprtcl.wasm 接口变更（导入函数 3→12、导出名重排、加密因子改由接口下发），修复旧脚本任何 Node 版本下实例化即 `LinkError` 的致命问题；输出完整签名地址（旧版仅输出 ddCalcu 值）。Dockerfile Node 源升级至 24.x LTS。

**🧪 类型安全加固（五工具全绿）**
- mypy tests/ 由 435 errors → 0（自动注解约 420 处 + 人工修复约 60 处真实类型问题）；basedpyright tests/ 0 errors / 0 warnings / 0 notes；pytest **699 passed / 2 skipped / 0 warnings**；black / isort 全项目通过。
- 新增测试覆盖：语言 API 5 个、i18n 新功能 10 个、SSL 平台自动追加 3 个、SSL 新语义 2 个、migu 输出契约 1 个、主播名自动更新 21 个。

**🧹 start_record 复杂度治理（代码质量）**
- `main.py:start_record`（原约 1600 行）的平台分派 if/elif 链（52 平台分支）抽取为独立模块级函数 `_resolve_platform_stream`，录制执行链控制流未动；消除 19 个被掩盖的 `possibly unbound`（移除恒真冗余 `if real_url:` 包装、清理失效 cast、修复 `record_name` 绑定），同时修复「录制链不得嵌套于条件内」反模式。basedpyright 原「过于复杂」错误消除。

**🧩 类型检查缺陷修复（代码质量）**
- `i18n.py`：`import yaml` 加 `# type: ignore[import-untyped]` 忽略可选依赖缺失存根提示（保留「缺失仅损失 YAML 格式」的运行时降级语义，符合 AGENTS.md 约定）；降级分支 `yaml = None` 改为 `yaml: Any | None = None` 显式注解。
- `gui.py`：`messagebox` 由属性式 `_tk.messagebox` 改为显式 `from tkinter import messagebox as _mb` 导入（两处崩溃弹窗），消除 `reportAttributeAccessIssue`；线程钩子 `_thread_dump` 对 `args.exc_value` 为 `None` 时新增 `if args.exc_value is None: return` 守卫，消除 `BaseException | None` 不兼容报错。
- 验证：`mypy i18n.py` → `Success: no issues found`；`basedpyright gui.py` → 0 errors / 0 warnings / 0 notes；`black --check` / `isort --check-only` 通过；运行时行为不变。

**🪟 窗口化运行崩溃可观测性加固（缺陷修复）**
- 修复 `pythonw.exe`（及 `console=False` 冻结 exe）启动 GUI 时**完全无窗口、无任何报错**的问题：根因为 `src/logger.py` 在导入期 `logger.add(sink=sys.stderr, ...)` 遇 `sys.stderr=None` 抛 `TypeError: Cannot log to objects of type 'NoneType'`，于导入链上静默退出。**已加 `sys.stderr is not None` 守卫**，无控制台环境跳过控制台 sink、由 `logs/streamget.log`、`PlayURL.log` 文件 sink 兜底。
- `gui.py` 顶部新增 `_install_crash_sink()`：在**所有风险导入之前**装 `sys.excepthook` / `threading.excepthook`，将未捕获异常（含导入期失败）完整堆栈写入 `%TEMP%/douyin_recorder_gui_error.log` 并尽力弹错误框，根治窗口化静默死亡；UI 回调异常分支改用程序内「运行日志」队列，`__main__` 包 `try/except` 保留控制台原始堆栈。
- 验证：模拟 `sys.stderr=None` 下 `import src.logger` 成功、注册 2 个文件 sink、不抛 `TypeError`；`py_compile` 与 `black --check` 均通过。

**📚 架构文档更新**
- `CODE_WIKI.md` 补全弹幕采集子系统（基类/采集器/5 平台客户端/监控枢纽/SRT/WS/访客 Cookie 缓存/protobuf）、`src/platforms` 与 `src/proto` 模块说明、模块依赖图与设计模式；版本号更正为 4.0.8.3（对齐 `pyproject.toml` 唯一事实源）。

### v4.0.8.2 (2026-08-16 ~ 2026-08-18) — 录制/弹幕/国际化/类型检查 系列修复

> 本批改动集中解决了多个历史遗留的「能跑但录制/弹幕经常失败」类问题，并通过真机实测闭环验证。下分模块概述，详细根因与验证见 [CODE_WIKI.md](CODE_WIKI.md)。

**🎯 录制引擎核心修复（影响所有平台）**
- **致命结构 Bug**：录制主链曾被嵌套在 `if headers:` 条件内，导致抖音/斗鱼等无专属请求头的平台**从未真正录制**（仅显示"正在直播中"）。已修复——条件仅控制请求头插入，录制链无条件执行。
- **斗鱼崩溃修复**：`select_source_url` 返回空时不再触发 `UnboundLocalError`（标题变量未绑定），直接告警并等待下一轮；末位候选的 content-type 拒绝与 m3u8 Range-GET 偶发 403 现均支持「重试一次再定罪 / 末位告警放行」，根治斗鱼 HLS 假红与 FLV ~70 秒被 CDN 掐断。
- **流地址校验三层降风控**：新增「探针节流 + 重试抖动 + 被拒后退避（仅虎牙）」机制，消除 CDN 按机器人节奏指纹识别导致的 403 失败循环；校验器与 ffmpeg 双端 User-Agent 现已**一字不差**对齐（指纹自洽，防校验假红/假绿）。
- **HTTPS/SSL 配置整合**：`是否启用https录制`（合并原 `是否强制启用https录制` 与 `是否禁用SSL证书验证(是/否)`）——开启 = https 拉流 + 跳过证书校验，关闭 = http 拉流 + 默认证书校验。对「虎牙直播」平台跳过协议转换（其 `*.hls.huya.com` 仅 http 可用）；TikTok/YouTube 等 https-only 海外平台在关闭时保持 https 原样，避免必然的拉流失败。

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

### v4.0.8.1 (2026-08-01 ~ 2026-08-09) — 注释规范 / 冒烟测试 / GUI 优雅退出 / 校验修复 整合

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

### v4.0.8 (2026-07-30) — Web 面板 / 画质监控 / 代理与类型修复

- **新增 Web 管理面板**（`web.py`+`src/web_api.py`+`src/web_config.py`+`web/`）：仪表盘、直播间管理、配置编辑、SSE 日志推送。
- **新增 GUI 画质监控**：实时检测实际画质是否匹配设置，覆盖抖音/TikTok/快手/虎牙/斗鱼/B站/网易CC 七平台。
- **配置项新增**：`web_show_console`（后台隐藏运行）、SSL 证书验证全局开关（config.ini）、日志文件开关。
- **连接优化**：HTTP 客户端按 (代理, verify, http2) 维度复用连接池；代理检测从联网探测改为读本地系统代理配置。
- **缺陷修复**：`trace_error_decorator` 同步装饰器误用于 71 个异步函数致错误捕获失效；`asyncio.run()` 致 httpx 跨事件循环复用问题；多个 IndexError/KeyError/类型错误。
- **凭据清理**：硬编码过期凭据改自动获取（抖音 ttwid、快手 did、Twitch Client-Id 等）。
- **构建/依赖**：Dockerfile 升 Node.js 22 LTS、非 root 运行；新增 `pydantic>=2.0.0` 依赖声明；全项目类型检查（Pyright/Pyrefly/basedpyright）清理。

<details><summary>点击展开更多历史版本</summary>

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

## 💬 有问题或者需求可以向我提 Issue，欢迎 Star 与 Fork

[![Star History Chart](https://api.star-history.com/svg?repos=y123ao6/DouyinLiveRecorder&type=Timeline)](https://star-history.com/#y123ao6/DouyinLiveRecorder&Timeline)
