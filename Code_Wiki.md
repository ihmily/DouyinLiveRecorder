# DouyinLiveRecorder Code Wiki

> **项目名称**: DouyinLiveRecorder  
> **版本**: v4.0.7  
> **许可证**: MIT  
> **Python要求**: >=3.10  
> **作者**: Hmily  
> **仓库**: https://github.com/ihmily/DouyinLiveRecorder

---

## 目录

1. [项目概述](#1-项目概述)
2. [项目架构总览](#2-项目架构总览)
3. [目录结构](#3-目录结构)
4. [核心模块职责详解](#4-核心模块职责详解)
   - 4.1 [main.py — 主程序入口](#41-mainpy--主程序入口)
   - 4.2 [src/spider.py — 直播数据爬取层](#42-srcspiderpy--直播数据爬取层)
   - 4.3 [src/stream.py — 直播流地址解析层](#43-srcstreampy--直播流地址解析层)
   - 4.4 [src/room.py — 直播间信息获取](#44-srcroompy--直播间信息获取)
   - 4.5 [src/ab_sign.py — 抖音签名算法](#45-srcab_signpy--抖音签名算法)
   - 4.6 [src/utils.py — 工具函数库](#46-srcutilspy--工具函数库)
   - 4.7 [src/logger.py — 日志模块](#47-srcloggerpy--日志模块)
   - 4.8 [src/proxy.py — 代理检测模块](#48-srcproxypy--代理检测模块)
   - 4.9 [src/initializer.py — Node.js环境初始化](#49-srcinitializerpy--nodejs环境初始化)
   - 4.10 [src/weverse_auth.py — Weverse认证](#410-srcweverse_authpy--weverse认证)
   - 4.11 [src/http_clients/ — HTTP客户端层](#411-srchttp_clients--http客户端层)
   - 4.12 [src/javascript/ — JS签名脚本](#412-srcjavascript--js签名脚本)
5. [辅助模块](#5-辅助模块)
   - 5.1 [msg_push.py — 消息推送](#51-msg_pushpy--消息推送)
   - 5.2 [ffmpeg_install.py — FFmpeg安装](#52-ffmpeg_installpy--ffmpeg安装)
   - 5.3 [demo.py — 测试示例](#53-demopy--测试示例)
   - 5.4 [i18n.py — 国际化](#54-i18npy--国际化)
6. [关键类与函数说明](#6-关键类与函数说明)
7. [数据流与处理流程](#7-数据流与处理流程)
8. [依赖关系](#8-依赖关系)
9. [配置系统](#9-配置系统)
10. [项目运行方式](#10-项目运行方式)
11. [支持平台一览](#11-支持平台一览)

---

## 1. 项目概述

DouyinLiveRecorder 是一款**可循环值守的多平台直播录制工具**，基于 FFmpeg 实现直播源录制，支持 40+ 直播平台的直播流监测、录制与状态推送。其核心能力包括：

- **多平台直播流获取**: 通过各平台 API 或页面解析获取直播流地址
- **循环值守录制**: 持续监测直播间状态，开播自动录制，下播自动停止
- **多格式输出**: 支持 TS/FLV/MKV/MP4/MP3/M4A 等格式保存
- **分段录制**: 按时间分段录制，避免单文件过大
- **自动转码**: 录制完成后自动转为 MP4，可选 h264 重编码
- **消息推送**: 支持微信/钉钉/Telegram/邮箱/Bark/Ntfy/PushPlus 等多种推送渠道
- **代理支持**: 海外平台通过代理录制
- **Docker部署**: 支持容器化运行

---

## 2. 项目架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py (主控)                        │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │ 配置读取  │  │ URL解析  │  │ 录制调度  │  │ 状态显示   │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────────────┘  │
│       │              │              │                         │
│  ┌────▼──────────────▼──────────────▼──────────────────┐    │
│  │              start_record() 录制循环                  │    │
│  │  ┌─────────────────┐  ┌─────────────────────────┐   │    │
│  │  │  spider.py      │  │  stream.py              │   │    │
│  │  │  (数据爬取层)    │  │  (流地址解析层)          │   │    │
│  │  └────────┬────────┘  └───────────┬─────────────┘   │    │
│  │           │                        │                  │    │
│  │  ┌────────▼────────────────────────▼─────────────┐   │    │
│  │  │           http_clients (HTTP请求层)            │   │    │
│  │  │     async_http.py / sync_http.py              │   │    │
│  │  └───────────────────────────────────────────────┘   │    │
│  │                                                      │    │
│  │  ┌──────────────┐  ┌───────────┐  ┌──────────────┐  │    │
│  │  │  room.py     │  │ ab_sign.py│  │  javascript/ │  │    │
│  │  │  (房间信息)   │  │ (签名算法) │  │  (JS脚本)    │  │    │
│  │  └──────────────┘  └───────────┘  └──────────────┘  │    │
│  └──────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ msg_push.py  │  │ffmpeg_install│  │  utils.py        │   │
│  │ (消息推送)    │  │ (FFmpeg安装) │  │  (工具函数)      │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**架构分层说明**:

| 层次 | 模块 | 职责 |
|------|------|------|
| 调度层 | `main.py` | 配置管理、URL解析、录制线程调度、FFmpeg进程管理 |
| 爬取层 | `src/spider.py` | 各平台直播数据获取（API请求、页面解析） |
| 解析层 | `src/stream.py` | 直播流URL解析、画质选择 |
| 签名层 | `src/ab_sign.py` + `src/room.py` + `src/javascript/` | 抖音AB签名、X-Bogus签名、房间ID解析 |
| 网络层 | `src/http_clients/` | 异步/同步HTTP请求封装 |
| 基础设施层 | `src/utils.py` / `src/logger.py` / `src/proxy.py` | 工具函数、日志、代理检测 |
| 推送层 | `msg_push.py` | 多渠道消息推送 |
| 安装层 | `ffmpeg_install.py` / `src/initializer.py` | FFmpeg/Node.js 环境安装 |

---

## 3. 目录结构

```
DouyinLiveRecorder/
├── main.py                    # 主程序入口
├── demo.py                    # 测试示例脚本
├── msg_push.py                # 消息推送模块
├── ffmpeg_install.py          # FFmpeg 安装脚本
├── i18n.py                    # 国际化(i18n)支持
├── gui.pyw                    # GUI入口(系统托盘)
├── index.html                 # 在线播放M3U8/FLV的网页
├── StopRecording.vbs          # Windows停止录制脚本
├── pyproject.toml             # 项目元数据与依赖
├── requirements.txt           # Python依赖列表
├── Dockerfile                 # Docker镜像构建
├── docker-compose.yaml        # Docker Compose编排
│
├── config/
│   ├── config.ini             # 主配置文件(录制设置/推送/Cookie/账号)
│   └── URL_config.ini         # 直播间URL列表
│
├── src/                       # 核心源码包
│   ├── __init__.py            # 包初始化(Node.js检查)
│   ├── spider.py              # 各平台直播数据爬取
│   ├── stream.py              # 直播流URL解析
│   ├── room.py                # 直播间信息获取
│   ├── ab_sign.py             # 抖音AB签名算法
│   ├── utils.py               # 工具函数
│   ├── logger.py              # 日志配置
│   ├── proxy.py               # 系统代理检测
│   ├── initializer.py         # Node.js环境初始化
│   ├── weverse_auth.py        # Weverse认证
│   │
│   ├── http_clients/          # HTTP客户端封装
│   │   ├── __init__.py
│   │   ├── async_http.py      # 异步HTTP客户端(httpx)
│   │   └── sync_http.py       # 同步HTTP客户端(requests/urllib)
│   │
│   └── javascript/            # JS签名脚本
│       ├── crypto-js.min.js   # CryptoJS库
│       ├── x-bogus.js         # 抖音X-Bogus签名
│       ├── taobao-sign.js     # 淘宝签名
│       ├── migu.js            # 咪咕签名
│       ├── liveme.js          # LiveMe签名
│       ├── haixiu.js          # 嗨秀签名
│       └── laixiu.js          # 来秀签名
│
└── i18n/                      # 国际化翻译文件
    ├── en/LC_MESSAGES/
    └── zh_CN/LC_MESSAGES/
        ├── zh_CN.po
        └── zh_CN.mo
```

---

## 4. 核心模块职责详解

### 4.1 main.py — 主程序入口

**文件路径**: [main.py](/workspace/main.py)

主程序是整个录制工具的控制中心，负责：

1. **环境初始化**: 检查 FFmpeg 是否可用，启动配置文件备份线程
2. **配置读取**: 从 `config/config.ini` 读取所有录制设置、推送配置、Cookie、账号密码等
3. **URL解析**: 从 `config/URL_config.ini` 读取直播间地址列表，解析画质、主播名、注释标记
4. **代理检测**: 检测系统是否开启代理，自动配置代理地址
5. **录制调度**: 为每个直播间创建独立线程，调用 `start_record()` 进行循环监测与录制
6. **FFmpeg进程管理**: 注册/注销/清理所有 FFmpeg 子进程，支持安全退出
7. **视频后处理**: 录制完成后自动转码（TS→MP4）、分段、生成字幕文件
8. **消息推送**: 直播状态变化时推送通知

**关键全局变量**:

| 变量 | 类型 | 说明 |
|------|------|------|
| `recording` | `set` | 当前正在录制的直播名称集合 |
| `error_count` | `int` | 瞬时错误计数 |
| `max_request` | `int` | 同一时间访问网络的线程数上限 |
| `monitoring` | `int` | 当前监测中的直播间数量 |
| `running_list` | `list` | 正在运行的URL列表 |
| `url_tuples_list` | `list` | 待录制的URL元组列表 `(画质, URL, 主播名)` |
| `url_comments` | `list` | 被注释（暂停录制）的URL列表 |
| `exit_recording` | `bool` | 退出录制标志 |
| `_ffmpeg_processes` | `list` | 全局FFmpeg进程跟踪列表 |

**关键函数**:

| 函数 | 说明 |
|------|------|
| `start_record(url_data, count_variable)` | 核心录制循环：监测直播状态→获取流地址→启动FFmpeg录制 |
| `check_subprocess(record_name, record_url, ffmpeg_command, ...)` | 监控FFmpeg子进程，处理录制完成/出错/注释停止 |
| `display_info()` | 后台线程：定期显示录制状态信息 |
| `adjust_max_request()` | 后台线程：根据错误率动态调整并发请求数 |
| `push_message(record_name, live_url, content)` | 统一消息推送入口 |
| `safe_exit(signum, frame)` | 信号处理：安全退出并清理所有FFmpeg进程 |
| `converts_mp4(converts_file_path, is_original_delete)` | 录制完成后转码为MP4 |
| `segment_video(...)` | 视频分段处理 |
| `generate_subtitles(record_name, ass_filename, sub_format)` | 生成时间字幕文件 |
| `backup_file_start()` | 后台线程：定期备份配置文件 |
| `read_config_value(config_parser, section, option, default_value)` | 安全读取配置项（不存在时写入默认值） |

### 4.2 src/spider.py — 直播数据爬取层

**文件路径**: [src/spider.py](/workspace/src/spider.py)

这是项目中最大的模块（约3600行），包含了所有平台的直播数据爬取逻辑。每个平台对应一个或多个异步函数，负责：

- 请求平台API或页面
- 解析返回数据，提取直播间信息（主播名、直播状态、流地址等）
- 处理登录认证（部分平台需要账号密码登录获取Cookie）
- 调用JS脚本进行签名计算

**平台爬取函数一览**:

| 函数名 | 平台 | 说明 |
|--------|------|------|
| `get_douyin_web_stream_data()` | 抖音(Web) | 通过Web API获取抖音直播数据 |
| `get_douyin_app_stream_data()` | 抖音(App) | 通过App API获取抖音直播数据（短链接/主页地址） |
| `get_tiktok_stream_data()` | TikTok | 获取TikTok直播数据 |
| `get_kuaishou_stream_data()` | 快手 | 获取快手直播数据 |
| `get_huya_stream_data()` | 虎牙 | 获取虎牙直播数据（低画质） |
| `get_huya_app_stream_url()` | 虎牙(App) | 获取虎牙直播数据（原画/蓝光） |
| `get_douyu_info_data()` | 斗鱼 | 获取斗鱼直播间信息 |
| `get_douyu_stream_data()` | 斗鱼(流) | 获取斗鱼直播流数据 |
| `get_yy_stream_data()` | YY | 获取YY直播数据 |
| `get_bilibili_room_info()` | B站 | 获取B站直播间信息 |
| `get_bilibili_stream_data()` | B站(流) | 获取B站直播流数据 |
| `get_xhs_stream_url()` | 小红书 | 获取小红书直播流 |
| `get_bigo_stream_url()` | Bigo | 获取Bigo直播流 |
| `get_blued_stream_url()` | Blued | 获取Blued直播流 |
| `get_sooplive_stream_data()` | SOOP | 获取SOOP(AfreecaTV)直播数据（含登录） |
| `get_netease_stream_data()` | 网易CC | 获取网易CC直播数据 |
| `get_qiandurebo_stream_data()` | 千度热播 | 获取千度热播直播数据 |
| `get_pandatv_stream_data()` | PandaTV | 获取PandaTV直播数据 |
| `get_maoerfm_stream_url()` | 猫耳FM | 获取猫耳FM直播流 |
| `get_winktv_stream_data()` | WinkTV | 获取WinkTV直播数据 |
| `get_flextv_stream_data()` | FlexTV | 获取FlexTV直播数据（含登录） |
| `get_looklive_stream_url()` | Look直播 | 获取Look直播流 |
| `get_popkontv_stream_url()` | PopkonTV | 获取PopkonTV直播流（含登录） |
| `get_twitcasting_stream_url()` | TwitCasting | 获取TwitCasting直播流（含登录） |
| `get_baidu_stream_data()` | 百度直播 | 获取百度直播数据 |
| `get_weibo_stream_data()` | 微博直播 | 获取微博直播数据 |
| `get_kugou_stream_url()` | 酷狗直播 | 获取酷狗直播流 |
| `get_twitchtv_stream_data()` | TwitchTV | 获取Twitch直播数据 |
| `get_liveme_stream_url()` | LiveMe | 获取LiveMe直播流 |
| `get_huajiao_stream_url()` | 花椒直播 | 获取花椒直播流 |
| `get_liuxing_stream_url()` | 流星直播 | 获取流星直播流 |
| `get_showroom_stream_data()` | ShowRoom | 获取ShowRoom直播数据 |
| `get_acfun_stream_data()` | Acfun | 获取Acfun直播数据 |
| `get_changliao_stream_url()` | 畅聊直播 | 获取畅聊直播流 |
| `get_yingke_stream_url()` | 映客直播 | 获取映客直播流 |
| `get_yinbo_stream_url()` | 音播直播 | 获取音播直播流 |
| `get_zhihu_stream_url()` | 知乎直播 | 获取知乎直播流 |
| `get_chzzk_stream_data()` | CHZZK | 获取CHZZK直播数据 |
| `get_haixiu_stream_url()` | 嗨秀直播 | 获取嗨秀直播流 |
| `get_vvxqiu_stream_url()` | VV星球 | 获取VV星球直播流 |
| `get_17live_stream_url()` | 17Live | 获取17Live直播流 |
| `get_langlive_stream_url()` | 浪Live | 获取浪Live直播流 |
| `get_pplive_stream_url()` | 漂漂/花猫 | 获取漂漂/花猫直播流 |
| `get_6room_stream_url()` | 六间房 | 获取六间房直播流 |
| `get_shopee_stream_url()` | Shopee | 获取Shopee直播流 |
| `get_youtube_stream_url()` | Youtube | 获取Youtube直播流 |
| `get_taobao_stream_url()` | 淘宝 | 获取淘宝直播流 |
| `get_jd_stream_url()` | 京东 | 获取京东直播流 |
| `get_faceit_stream_data()` | Faceit | 获取Faceit直播数据 |
| `get_migu_stream_url()` | 咪咕 | 获取咪咕直播流 |
| `get_lianjie_stream_url()` | 连接直播 | 获取连接直播流 |
| `get_laixiu_stream_url()` | 来秀直播 | 获取来秀直播流 |
| `get_picarto_stream_url()` | Picarto | 获取Picarto直播流 |

**通用辅助函数**:

| 函数 | 说明 |
|------|------|
| `get_play_url_list(m3u8, proxy, header, abroad)` | 解析M3U8播放列表，按带宽排序返回URL列表 |
| `get_params(url, params)` | 从URL中提取指定查询参数 |

### 4.3 src/stream.py — 直播流地址解析层

**文件路径**: [src/stream.py](/workspace/src/stream.py)

负责将 `spider.py` 获取的原始数据解析为可用的直播流URL，并处理画质选择逻辑。

**核心函数**:

| 函数 | 说明 |
|------|------|
| `get_douyin_stream_url(json_data, video_quality, proxy_addr)` | 解析抖音直播流URL，选择FLV/HLS源 |
| `get_tiktok_stream_url(json_data, video_quality, proxy_addr)` | 解析TikTok直播流URL，按码率排序选择 |
| `get_kuaishou_stream_url(json_data, video_quality)` | 解析快手直播流URL |
| `get_huya_stream_url(json_data, video_quality)` | 解析虎牙直播流URL，含反盗链签名计算 |
| `get_douyu_stream_url(json_data, video_quality, cookies, proxy_addr)` | 解析斗鱼直播流URL |
| `get_yy_stream_url(json_data)` | 解析YY直播流URL |
| `get_bilibili_stream_url(json_data, video_quality, proxy_addr, cookies)` | 解析B站直播流URL |
| `get_netease_stream_url(json_data, video_quality)` | 解析网易CC直播流URL |
| `get_stream_url(json_data, video_quality, url_type, spec, hls_extra_key, flv_extra_key)` | **通用流URL解析函数**，适用于多个平台 |

**画质映射**:

```python
QUALITY_MAPPING = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}
QUALITY_MAPPING_BIT = {'OD': 99999, 'BD': 4000, 'UHD': 2000, 'HD': 1000, 'SD': 800, 'LD': 600}
```

| 代码 | 中文 | 说明 |
|------|------|------|
| OD | 原画 | Original Definition |
| BD | 蓝光 | Blue-ray Definition |
| UHD | 超清 | Ultra High Definition |
| HD | 高清 | High Definition |
| SD | 标清 | Standard Definition |
| LD | 流畅 | Low Definition |

### 4.4 src/room.py — 直播间信息获取

**文件路径**: [src/room.py](/workspace/src/room.py)

专门处理抖音直播间的ID解析，包括短链接转换、sec_user_id获取、抖音号获取、web_rid获取。

| 函数 | 说明 |
|------|------|
| `get_xbogus(url, headers)` | 计算抖音X-Bogus签名（通过Node.js执行JS脚本） |
| `get_sec_user_id(url, proxy_addr, headers)` | 从短链接获取room_id和sec_user_id |
| `get_unique_id(url, proxy_addr, headers)` | 获取抖音号（unique_id） |
| `get_live_room_id(room_id, sec_user_id, proxy_addr, params, headers)` | 获取直播间web_rid |

**异常类**: `UnsupportedUrlError` — 不支持的URL格式时抛出

### 4.5 src/ab_sign.py — 抖音签名算法

**文件路径**: [src/ab_sign.py](/workspace/src/ab_sign.py)

纯Python实现的抖音AB签名算法，用于绕过抖音API的请求验证。包含：

| 函数/类 | 说明 |
|---------|------|
| `SM3` | 国密SM3哈希算法实现 |
| `rc4_encrypt(plaintext, key)` | RC4加密算法 |
| `result_encrypt(long_str, num)` | 魔改Base64编码（使用自定义编码表） |
| `generate_random_str()` | 生成随机字符串前缀 |
| `generate_rc4_bb_str(url_search_params, user_agent, window_env_str, suffix, arguments)` | 生成RC4加密的主体部分 |
| `ab_sign(url_search_params, user_agent)` | **主入口**: 生成AB签名 |

**签名流程**:
1. 对URL查询参数进行SM3双重哈希
2. 对后缀字符串进行SM3双重哈希
3. 对User-Agent进行RC4加密+魔改Base64+SM3哈希
4. 构建配置对象，计算校验和
5. RC4加密最终字节数组
6. 魔改Base64编码输出

### 4.6 src/utils.py — 工具函数库

**文件路径**: [src/utils.py](/workspace/src/utils.py)

提供全局共享的工具函数和装饰器：

| 函数/类 | 说明 |
|---------|------|
| `Color` | 终端彩色输出类（RED/GREEN/YELLOW/BLUE等） |
| `trace_error_decorator(func)` | 错误追踪装饰器，捕获异常并记录详细错误信息 |
| `check_md5(file_path)` | 计算文件MD5值 |
| `dict_to_cookie_str(cookies_dict)` | 字典转Cookie字符串 |
| `read_config_value(file_path, section, key)` | 读取INI配置值 |
| `update_config(file_path, section, key, new_value)` | 更新INI配置值 |
| `get_file_paths(directory)` | 递归获取目录下所有文件路径 |
| `remove_emojis(text, replace_text)` | 移除文本中的Emoji字符 |
| `remove_duplicate_lines(file_path)` | 移除文件中的重复行 |
| `check_disk_capacity(file_path, show)` | 检查磁盘剩余空间(GB) |
| `handle_proxy_addr(proxy_addr)` | 规范化代理地址格式 |
| `generate_random_string(length)` | 生成随机字符串 |
| `jsonp_to_json(jsonp_str)` | JSONP响应转JSON |
| `replace_url(file_path, old, new)` | 替换文件中的URL |
| `get_query_params(url, param_name)` | 获取URL查询参数 |

### 4.7 src/logger.py — 日志模块

**文件路径**: [src/logger.py](/workspace/src/logger.py)

基于 `loguru` 的日志系统，配置了三个输出通道：

| 通道 | 目标 | 级别 | 说明 |
|------|------|------|------|
| stderr | 控制台 | DEBUG | 彩色格式化输出 |
| `logs/streamget.log` | 文件 | DEBUG（排除INFO） | 详细调试日志，300KB轮转 |
| `logs/PlayURL.log` | 文件 | INFO | 直播源地址日志，300KB轮转 |

### 4.8 src/proxy.py — 代理检测模块

**文件路径**: [src/proxy.py](/workspace/src/proxy.py)

| 类/方法 | 说明 |
|---------|------|
| `ProxyInfo` | 代理信息数据类（ip, port），含格式验证 |
| `ProxyDetector.get_proxy_info()` | 获取系统代理信息 |
| `ProxyDetector.is_proxy_enabled()` | 检测系统代理是否启用 |
| `ProxyDetector._get_proxy_info_windows()` | Windows: 读取注册表获取代理 |
| `ProxyDetector._get_proxy_info_linux()` | Linux: 读取环境变量获取代理 |
| `ProxyDetector._is_proxy_enabled_windows()` | Windows: 检查注册表ProxyEnable |
| `ProxyDetector._is_proxy_enabled_linux()` | Linux: 检查http_proxy等环境变量 |

### 4.9 src/initializer.py — Node.js环境初始化

**文件路径**: [src/initializer.py](/workspace/src/initializer.py)

确保Node.js运行时可用，因为部分签名算法需要通过 `PyExecJS` 执行JavaScript代码。

| 函数 | 说明 |
|------|------|
| `check_node()` | 检查Node.js是否安装，未安装则自动安装 |
| `check_nodejs_installed()` | 检测Node.js是否可用 |
| `install_nodejs()` | 根据平台选择安装方式 |
| `install_nodejs_windows()` | Windows: 下载Node.js zip包并解压 |
| `install_nodejs_centos()` | CentOS: yum安装 |
| `install_nodejs_ubuntu()` | Ubuntu: apt安装 |
| `install_nodejs_mac()` | macOS: brew安装 |
| `get_package_manager()` | 检测Linux发行版包管理器类型 |

### 4.10 src/weverse_auth.py — Weverse认证

**文件路径**: [src/weverse_auth.py](/workspace/src/weverse_auth.py)

| 函数 | 说明 |
|------|------|
| `refresh_weverse_token(refresh_token)` | 使用refresh_token刷新Weverse访问令牌 |

### 4.11 src/http_clients/ — HTTP客户端层

**文件路径**: [src/http_clients/](/workspace/src/http_clients/)

封装了异步和同步两种HTTP客户端，供 `spider.py` 和其他模块使用。

#### async_http.py — 异步HTTP客户端

基于 `httpx` 的异步HTTP请求封装，支持HTTP/2。

| 函数 | 说明 |
|------|------|
| `async_req(url, proxy_addr, headers, data, json_data, timeout, ...)` | 通用异步HTTP请求（GET/POST），支持代理、重定向、Cookie |
| `get_response_status(url, proxy_addr, headers, timeout, ...)` | 异步HEAD请求检测URL可达性 |

**连接池配置**: `max_connections=100, max_keepalive_connections=20`

#### sync_http.py — 同步HTTP客户端

基于 `requests` 和 `urllib` 的同步HTTP请求封装。

| 函数 | 说明 |
|------|------|
| `sync_req(url, proxy_addr, headers, data, json_data, timeout, ...)` | 通用同步HTTP请求，有代理时用requests，无代理时用urllib |

### 4.12 src/javascript/ — JS签名脚本

**文件路径**: [src/javascript/](/workspace/src/javascript/)

存放各平台签名算法的JavaScript实现，通过 `PyExecJS` + `Node.js` 执行：

| 文件 | 用途 |
|------|------|
| `x-bogus.js` | 抖音X-Bogus签名算法 |
| `taobao-sign.js` | 淘宝直播签名算法 |
| `migu.js` | 咪咕直播签名算法 |
| `liveme.js` | LiveMe签名算法 |
| `haixiu.js` | 嗨秀直播签名算法 |
| `laixiu.js` | 来秀直播签名算法 |
| `crypto-js.min.js` | CryptoJS加密库（被其他脚本引用） |

---

## 5. 辅助模块

### 5.1 msg_push.py — 消息推送

**文件路径**: [msg_push.py](/workspace/msg_push.py)

支持7种消息推送渠道：

| 函数 | 渠道 | 说明 |
|------|------|------|
| `dingtalk(url, content, number, is_atall)` | 钉钉 | 通过Webhook推送钉钉消息，支持@指定人 |
| `xizhi(url, title, content)` | 微信(息知) | 通过息知API推送微信消息 |
| `send_email(email_host, login_email, ...)` | 邮箱 | SMTP邮件推送，支持SSL |
| `tg_bot(chat_id, token, content)` | Telegram | 通过Bot API推送Telegram消息 |
| `bark(api, title, content, level, sound, ...)` | Bark | iOS Bark推送，支持铃声/级别 |
| `ntfy(api, title, content, tags, priority, ...)` | Ntfy | Ntfy推送，支持标签/优先级/邮件 |
| `pushplus(token, title, content)` | PushPlus | PushPlus微信公众号推送 |

所有推送函数均返回 `{"success": [...], "error": [...]}` 格式的结果，支持批量推送地址（逗号分隔）。

### 5.2 ffmpeg_install.py — FFmpeg安装

**文件路径**: [ffmpeg_install.py](/workspace/ffmpeg_install.py)

| 函数 | 说明 |
|------|------|
| `check_ffmpeg()` | 检查FFmpeg是否可用，不可用则自动安装 |
| `check_ffmpeg_installed()` | 检测FFmpeg是否已安装 |
| `install_ffmpeg()` | 根据平台选择安装方式 |
| `install_ffmpeg_windows()` | Windows: 从蓝奏云下载FFmpeg |
| `install_ffmpeg_linux()` | Linux: yum/apt安装 |
| `install_ffmpeg_mac()` | macOS: brew安装 |

### 5.3 demo.py — 测试示例

**文件路径**: [demo.py](/workspace/demo.py)

提供各平台直播流获取的测试入口，通过 `LIVE_STREAM_CONFIG` 字典配置平台名称→URL→爬取函数的映射。

```python
# 使用示例
python demo.py  # 默认测试抖音
# 或修改 platform 变量测试其他平台
```

### 5.4 i18n.py — 国际化

**文件路径**: [i18n.py](/workspace/i18n.py)

基于 `gettext` 的国际化支持，通过替换 `builtins.print` 实现自动翻译：

| 函数 | 说明 |
|------|------|
| `init_gettext(locale_dir, locale_name)` | 初始化gettext绑定 |
| `translated_print(*args, **kwargs)` | 替换内置print，自动翻译src包内的输出 |

---

## 6. 关键类与函数说明

### 核心数据流关键函数

#### `start_record(url_data, count_variable)` — 录制主循环

这是最核心的函数，每个直播间一个线程，循环执行以下逻辑：

```
while True:
    1. 根据URL判断平台
    2. 调用 spider.get_xxx_stream_data() 获取直播数据
    3. 调用 stream.get_xxx_stream_url() 解析流URL
    4. 检查直播状态:
       - 未开播: 等待循环
       - 正在直播: 构建FFmpeg命令，启动录制
    5. 推送直播状态消息
    6. 监控FFmpeg子进程
    7. 录制完成后进行后处理（转码/分段）
    8. 等待循环间隔后重新检测
```

#### `check_subprocess(record_name, record_url, ffmpeg_command, save_type, script_command)` — FFmpeg进程监控

- 启动FFmpeg子进程并注册到全局进程列表
- 持续检查进程状态和URL注释标记
- 支持安全终止：`q`命令 → SIGINT → terminate → kill
- 录制完成后触发转码和自定义脚本

#### `ab_sign(url_search_params, user_agent)` — 抖音AB签名

纯Python实现的抖音API签名，无需依赖JS执行，流程：
1. SM3双重哈希URL参数
2. SM3双重哈希后缀
3. RC4+魔改Base64+SM3处理UA
4. 构建字节序列并RC4加密
5. 魔改Base64编码

### 画质选择机制

```python
# 画质代码映射
"原画" → "OD"    "蓝光" → "BD"    "超清" → "UHD"
"高清" → "HD"    "标清" → "SD"    "流畅" → "LD"

# 画质索引映射（从高到低）
QUALITY_MAPPING = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}
```

每个平台的流地址列表按画质从高到低排列，通过索引选择对应画质。如果首选画质不可用，自动降级到相邻画质。

---

## 7. 数据流与处理流程

### 完整录制流程

```
用户配置URL → main.py读取URL_config.ini
    │
    ▼
解析URL → 判断平台 → 创建录制线程
    │
    ▼
┌─────────────── 录制循环 ───────────────┐
│                                         │
│  spider.get_xxx_stream_data(url)        │
│         │                               │
│         ▼                               │
│  stream.get_xxx_stream_url(data, qn)    │
│         │                               │
│         ▼                               │
│  检查直播状态                            │
│    ├─ 未开播 → 等待 → 重新检测           │
│    └─ 已开播 ↓                          │
│                                         │
│  构建FFmpeg命令                          │
│    ├─ 选择格式: TS/FLV/MKV/MP4/音频     │
│    ├─ 设置代理、Headers、超时参数         │
│    └─ 分段录制/直接录制                   │
│         │                               │
│         ▼                               │
│  启动FFmpeg子进程                        │
│    ├─ check_subprocess() 监控           │
│    ├─ 支持注释停止                       │
│    └─ 安全终止机制                       │
│         │                               │
│         ▼                               │
│  录制完成 → 后处理                       │
│    ├─ converts_mp4() 转码               │
│    ├─ segment_video() 分段              │
│    ├─ generate_subtitles() 字幕         │
│    └─ run_script() 自定义脚本           │
│         │                               │
│         ▼                               │
│  推送消息 → 循环等待 → 重新检测          │
└─────────────────────────────────────────┘
```

### 代理选择逻辑

```
1. 检查全局代理 (global_proxy)
2. 检查URL是否匹配 enable_proxy_platform_list（需代理的平台列表）
3. 检查URL是否匹配 extra_enable_proxy_platform_list（额外需代理的平台）
4. 海外平台默认需要代理
```

---

## 8. 依赖关系

### Python依赖

| 包名 | 版本 | 用途 |
|------|------|------|
| `requests` | - | 同步HTTP请求（代理场景） |
| `loguru` | - | 日志记录 |
| `pycryptodome` | - | 加密算法（AES等） |
| `distro` | - | Linux发行版检测 |
| `tqdm` | - | 下载进度条 |
| `httpx[http2]` | - | 异步HTTP客户端（支持HTTP/2） |
| `PyExecJS` | - | 执行JavaScript签名脚本 |
| `pystray` | - | 系统托盘图标（GUI模式） |
| `Pillow` | - | 图像处理（托盘图标） |
| `weverse` | - | Weverse平台API |

### 外部依赖

| 依赖 | 用途 | 安装方式 |
|------|------|----------|
| **FFmpeg** | 视频录制核心 | 自动安装或系统包管理器 |
| **Node.js** | 执行JS签名脚本 | 自动安装或系统包管理器 |

### 模块间依赖关系

```
main.py
  ├── src.spider (直播数据爬取)
  ├── src.stream (流URL解析)
  ├── src.proxy (代理检测)
  ├── src.utils (工具函数)
  ├── msg_push (消息推送)
  └── ffmpeg_install (FFmpeg安装)

src.spider
  ├── src.http_clients.async_http (异步HTTP)
  ├── src.room (抖音房间信息)
  ├── src.ab_sign (抖音AB签名)
  ├── src.utils (工具函数)
  └── src.javascript/* (JS签名脚本，通过PyExecJS)

src.stream
  ├── src.spider (部分平台需再次请求数据)
  ├── src.http_clients.async_http (URL可达性检测)
  └── src.utils (工具函数)

src.room
  ├── src.http_clients (HTTP请求)
  ├── src.utils (工具函数)
  └── src.javascript/x-bogus.js (X-Bogus签名)

src.__init__
  └── src.initializer (Node.js检查)
```

---

## 9. 配置系统

### config.ini 配置项

配置文件使用INI格式，分为5个Section：

#### [录制设置]

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `language(zh_cn/en)` | zh_cn | 界面语言 |
| `是否跳过代理检测(是/否)` | 否 | 跳过启动时的代理检测 |
| `直播保存路径(不填则默认)` | (空) | 录制文件保存路径，默认 `./downloads` |
| `保存文件夹是否以作者区分` | 是 | 按主播名创建子文件夹 |
| `保存文件夹是否以时间区分` | 否 | 按日期创建子文件夹 |
| `保存文件夹是否以标题区分` | 否 | 按直播标题创建子文件夹 |
| `保存文件名是否包含标题` | 否 | 文件名中包含直播标题 |
| `是否去除名称中的表情符号` | 是 | 清理文件名中的Emoji |
| `视频保存格式` | ts | 支持 ts/mkv/flv/mp4/mp3音频/m4a音频 |
| `原画\|超清\|高清\|标清\|流畅` | 原画 | 默认录制画质 |
| `是否使用代理ip(是/否)` | 否 | 全局代理开关 |
| `代理地址` | (空) | 代理服务器地址，如 `127.0.0.1:7890` |
| `同一时间访问网络的线程数` | 3 | 并发请求上限 |
| `循环时间(秒)` | 300 | 检测直播状态的间隔 |
| `分段录制是否开启` | 否 | 按时间分段录制 |
| `视频分段时间(秒)` | 3600 | 分段时长 |
| `录制完成后自动转为mp4格式` | 否 | 自动转码 |
| `mp4格式重新编码为h264` | 否 | h264重编码 |
| `追加格式后删除原文件` | 是 | 转码后删除原始文件 |
| `生成时间字幕文件` | 否 | 生成SRT时间字幕 |
| `是否录制完成后执行自定义脚本` | 否 | 录制完成后执行脚本 |
| `使用代理录制的平台(逗号分隔)` | tiktok,soop,... | 需要代理的平台列表 |
| `录制空间剩余阈值(gb)` | 1.0 | 磁盘空间低于此值停止录制 |

#### [推送配置]

| 配置项 | 说明 |
|--------|------|
| `直播状态推送渠道` | 可选: 微信/钉钉/tg/邮箱/bark/ntfy/pushplus，逗号分隔 |
| `只推送通知不录制(是/否)` | 仅推送开播通知，不进行录制 |
| `开播推送开启(是/否)` | 开播时推送 |
| `关播推送开启(是/否)` | 关播时推送 |
| `自定义推送标题` | 推送消息标题模板 |
| `自定义开播/关播推送内容` | 支持 `[直播间名称]` `[时间]` 占位符 |

#### [Cookie]

每个平台对应一个Cookie配置项，用于需要认证的平台（如抖音、B站等）。

#### [Authorization]

| 配置项 | 说明 |
|--------|------|
| `popkontv_token` | PopkonTV访问令牌 |

#### [账号密码]

部分需要登录的平台账号配置（SOOP、FlexTV、PopkonTV、TwitCasting）。

### URL_config.ini 格式

```
# 注释行（不录制）
https://live.douyin.com/745964462470
超清，https://live.kuaishou.com/u/yall1102
https://live.bilibili.com/320 主播: 某某
```

- 每行一个直播间URL
- `#` 开头表示暂停录制
- 可在URL前加画质：`超清，URL`
- 可在URL后加主播名：`URL 主播: 名字`

---

## 10. 项目运行方式

### 方式一：源码运行

```bash
# 1. 克隆仓库
git clone https://github.com/ihmily/DouyinLiveRecorder.git
cd DouyinLiveRecorder

# 2. 安装依赖（推荐使用uv）
pip3 install -r requirements.txt
# 或
uv sync

# 3. 安装FFmpeg（Linux）
# CentOS: yum install ffmpeg
# Ubuntu: apt install ffmpeg
# macOS: brew install ffmpeg

# 4. 配置直播间地址
# 编辑 config/URL_config.ini

# 5. 运行
python main.py
# 或
uv run main.py
```

### 方式二：Docker运行

```bash
# 快速启动
docker-compose up

# 后台运行
docker-compose up -d

# 自定义构建
docker build -t douyin-live-recorder:latest .
docker-compose up

# 停止
docker-compose stop
```

**Docker Compose配置**:
- 镜像: `ihmily/douyin-live-recorder:latest`
- 挂载卷: `config/`, `logs/`, `backup_config/`, `downloads/`
- 自动重启: `restart: always`

### 方式三：打包运行

从 [Releases](https://github.com/ihmily/DouyinLiveRecorder/releases) 下载打包好的可执行文件，解压后直接运行 `DouyinLiveRecorder.exe`。

### 停止录制

- **Windows**: 运行 `StopRecording.vbs` 或 `Ctrl+C`
- **Linux/macOS**: `Ctrl+C` 或 `kill -SIGINT <pid>`

> **重要**: 推荐使用 `ts` 格式保存，避免手动中断导致视频文件损坏。

---

## 11. 支持平台一览

### 国内站点

| 平台 | URL特征 | 需Cookie | 需代理 |
|------|---------|----------|--------|
| 抖音 | `live.douyin.com` / `v.douyin.com` | 推荐 | 否 |
| 快手 | `live.kuaishou.com` | 可选 | 否 |
| 虎牙 | `www.huya.com` | 可选 | 否 |
| 斗鱼 | `www.douyu.com` | 可选 | 否 |
| YY | `www.yy.com` | 可选 | 否 |
| B站 | `live.bilibili.com` | 推荐 | 否 |
| 小红书 | `xiaohongshu.com` / `xhslink.com` | 可选 | 否 |
| bigo | `www.bigo.tv` | 可选 | 否 |
| blued | `app.blued.cn` | 可选 | 否 |
| 网易CC | `cc.163.com` | 可选 | 否 |
| 千度热播 | `qiandurebo.com` | 可选 | 否 |
| 猫耳FM | `fm.missevan.com` | 可选 | 否 |
| Look直播 | `look.163.com` | 可选 | 否 |
| 百度直播 | `live.baidu.com` | 可选 | 否 |
| 微博直播 | `weibo.com` | 可选 | 否 |
| 酷狗直播 | `kugou.com` | 可选 | 否 |
| 花椒直播 | `www.huajiao.com` | 可选 | 否 |
| 流星直播 | `7u66.com` | 可选 | 否 |
| Acfun | `live.acfun.cn` | 可选 | 否 |
| 畅聊直播 | `live.tlclw.com` | 可选 | 否 |
| 映客直播 | `www.inke.cn` | 可选 | 否 |
| 音播直播 | `ybw1666.com` | 可选 | 否 |
| 知乎直播 | `www.zhihu.com` | 可选 | 否 |
| 嗨秀直播 | `www.haixiutv.com` | 可选 | 否 |
| VV星球 | `vvxqiu.com` | 可选 | 否 |
| 17Live | `17.live` | 可选 | 否 |
| 浪Live | `www.lang.live` | 可选 | 否 |
| 漂漂直播 | `m.pp.weimipopo.com` | 可选 | 否 |
| 六间房 | `v.6.cn` | 可选 | 否 |
| 乐嗨直播 | `lehaitv.com` | 可选 | 否 |
| 花猫直播 | `h.catshow168.com` | 可选 | 否 |
| 淘宝 | `tb.cn` / `tbzb.taobao.com` | 必需 | 否 |
| 京东 | `3.cn` / `m.jd.com` | 可选 | 否 |
| 咪咕 | `miguvideo.com` | 可选 | 否 |
| 连接直播 | `show.lailianjie.com` | 可选 | 否 |
| 来秀直播 | `www.imkktv.com` | 可选 | 否 |

### 海外站点

| 平台 | URL特征 | 需Cookie | 需代理 |
|------|---------|----------|--------|
| TikTok | `www.tiktok.com` | 可选 | 是 |
| SOOP | `sooplive.co.kr` | 可选 | 是 |
| PandaTV | `pandalive.co.kr` | 可选 | 是 |
| WinkTV | `winktv.co.kr` | 可选 | 是 |
| FlexTV | `flextv.co.kr` / `ttinglive.com` | 可选 | 是 |
| PopkonTV | `popkontv.com` | 可选 | 是 |
| TwitCasting | `twitcasting.tv` | 可选 | 是 |
| TwitchTV | `www.twitch.tv` | 可选 | 是 |
| LiveMe | `liveme.com` | 可选 | 是 |
| ShowRoom | `showroom-live.com` | 可选 | 是 |
| CHZZK | `chzzk.naver.com` | 可选 | 是 |
| Shopee | `live.shopee.` / `shp.ee` | 可选 | 是 |
| Youtube | `youtube.com` / `youtu.be` | 可选 | 是 |
| Faceit | `faceit.com` | 可选 | 是 |
| Picarto | `picarto.tv` | 可选 | 是 |

### 自定义录制

支持直接输入 `.m3u8` 或 `.flv` 格式的直播源地址进行录制。

---

> 本文档基于 DouyinLiveRecorder v4.0.7 源码分析生成
