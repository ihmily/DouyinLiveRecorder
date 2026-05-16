# DouyinLiveRecorder 代码文档

> 版本: v4.0.7 | 项目地址: https://github.com/ihmily/DouyinLiveRecorder

---

## 目录

- [项目概述](#项目概述)
- [项目架构](#项目架构)
- [模块详解](#模块详解)
- [核心类与函数](#核心类与函数)
- [依赖关系](#依赖关系)
- [配置说明](#配置说明)
- [运行方式](#运行方式)

---

## 项目概述

**DouyinLiveRecorder** 是一个开源的直播录制工具，支持国内外60+直播平台的实时录制。该项目使用 Python 开发，核心功能通过 `ffmpeg` 实现直播流下载与格式转换。

### 主要特性

- 多平台支持：抖音、快手、虎牙、斗鱼、B站、TikTok、YouTube 等
- 异步HTTP请求：使用 `httpx` 实现高效的并发录制
- 智能重试机制：自动检测直播状态，断线重连
- 多种输出格式：TS、MKV、FLV、MP4、MP3、M4A
- 消息推送：支持钉钉、微信、邮箱、TG、Bark、NTFY、PushPlus
- 图形界面：提供 `gui.pyw` 实现的 Tkinter GUI
- Docker 支持：提供 Dockerfile 和 docker-compose.yaml

---

## 项目架构

```
DouyinLiveRecorder-code/
├── main.py                 # 命令行主入口，核心录制逻辑
├── gui.pyw                # 图形界面主入口
├── msg_push.py            # 消息推送模块
├── i18n.py                # 国际化支持
├── ffmpeg_install.py      # ffmpeg 安装与检测
├── demo.py                # 示例文件
├── requirements.txt        # Python 依赖
├── pyproject.toml         # 项目配置
├── Dockerfile             # Docker 构建文件
├── docker-compose.yaml    # Docker Compose 配置
├── StopRecording.vbs      # Windows 停止录制脚本
├── config/
│   ├── config.ini         # 主配置文件
│   └── URL_config.ini     # 直播URL列表
├── src/
│   ├── __init__.py        # 包初始化
│   ├── spider.py          # 直播数据爬取（核心）
│   ├── stream.py          # 直播流URL解析
│   ├── room.py            # 抖音房间信息获取
│   ├── utils.py           # 工具函数
│   ├── logger.py          # 日志配置
│   ├── proxy.py           # 代理检测
│   ├── ab_sign.py         # 抖音 A-Bogus 签名
│   ├── initializer.py     # 初始化器
│   ├── weverse_auth.py    # Wevers 认证
│   └── http_clients/
│       ├── async_http.py  # 异步 HTTP 客户端
│       └── sync_http.py   # 同步 HTTP 客户端
├── ffmpeg/
│   └── ffmpeg.exe         # Windows ffmpeg 二进制
├── downloads/              # 录制文件输出目录
└── i18n/                  # 国际化文件
```

---

## 模块详解

### 1. main.py（命令行入口）

**职责**：核心录制逻辑，处理配置读取、线程调度、录制控制。

**关键全局变量**：

| 变量 | 类型 | 说明 |
|------|------|------|
| `recording` | `set` | 当前正在录制的直播间集合 |
| `monitoring` | `int` | 监测中的直播间数量 |
| `running_list` | `list` | 运行中的URL列表 |
| `error_count` | `int` | 错误计数器 |
| `max_request` | `int` | 最大并发线程数 |
| `exit_recording` | `bool` | 退出标志 |
| `global_proxy` | `bool` | 全局代理状态 |

**关键常量**：

| 常量 | 说明 |
|------|------|
| `PLATFORM_HOST` | 支持的平台域名列表 |
| `OVERSEAS_PLATFORM_HOST` | 海外平台域名列表 |
| `CLEAN_URL_HOST_LIST` | 需要清理参数的URL域名 |

**关键函数**：

| 函数 | 说明 |
|------|------|
| `start_record(url_data, count_variable)` | 录制线程主函数，处理单个直播间的录制逻辑 |
| `check_subprocess(record_name, record_url, ffmpeg_command, ...)` | 执行 ffmpeg 录制命令并监控 |
| `direct_download_stream(...)` | 直接下载 FLV 流 |
| `display_info()` | 显示录制状态信息 |
| `adjust_max_request()` | 动态调整并发数 |
| `converts_mp4(path)` | 转换视频为 MP4 |
| `converts_m4a(path)` | 提取音频为 M4A |
| `segment_video(...)` | 视频分段 |
| `cleanup_all_ffmpeg_processes()` | 清理所有 ffmpeg 进程 |
| `safe_exit(signum, frame)` | 安全退出处理 |

**录制流程**：

1. 读取 `URL_config.ini` 获取直播URL列表
2. 为每个URL创建 `threading.Thread` 线程
3. 根据URL匹配平台，调用对应的 `spider.get_xxx_stream_data()` 获取直播数据
4. 调用 `stream.get_xxx_stream_url()` 解析流地址
5. 构建 ffmpeg 命令执行录制
6. 循环检测直播状态，断线自动重连

### 2. src/spider.py（数据爬取）

**职责**：从各平台API获取直播间状态和流信息。

**核心函数**：

| 函数 | 平台 | 说明 |
|------|------|------|
| `get_douyin_web_stream_data()` | 抖音-Web | 获取抖音网页端直播数据 |
| `get_douyin_app_stream_data()` | 抖音-App | 获取抖音App端直播数据 |
| `get_douyin_stream_data()` | 抖音-旧版 | 兼容旧版抖音解析 |
| `get_tiktok_stream_data()` | TikTok | 获取TikTok直播数据 |
| `get_kuaishou_stream_data()` | 快手 | 获取快手直播数据 |
| `get_huya_stream_data()` | 虎牙-Web | 获取虎牙网页端数据 |
| `get_huya_app_stream_url()` | 虎牙-App | 获取虎牙App端流地址 |
| `get_douyu_info_data()` | 斗鱼 | 获取斗鱼房间信息 |
| `get_yy_stream_data()` | YY | 获取YY直播数据 |
| `get_bilibili_room_info()` | B站 | 获取B站直播信息 |
| `get_netease_stream_data()` | 网易CC | 获取网易CC直播数据 |
| `get_sooplive_stream_data()` | SOOP | 获取SOOP直播数据 |
| `get_pandatv_stream_data()` | PandaTV | 获取PandaTV数据 |
| `get_winktv_stream_data()` | WinkTV | 获取WinkTV数据 |
| `get_flextv_stream_data()` | FlexTV | 获取FlexTV数据 |
| `get_twitchtv_stream_data()` | Twitch | 获取Twitch数据 |
| `get_showroom_stream_data()` | ShowRoom | 获取ShowRoom数据 |
| `get_chzzk_stream_data()` | CHZZK | 获取CHZZK数据 |
| `get_faceit_stream_data()` | Faceit | 获取Faceit数据 |
| `get_youtube_stream_url()` | YouTube | 获取YouTube直播数据 |
| `get_taobao_stream_url()` | 淘宝 | 获取淘宝直播数据 |
| `get_xhs_stream_url()` | 小红书 | 获取小红书直播数据 |
| `get_bigo_stream_url()` | Bigo | 获取Bigo直播数据 |
| `get_blued_stream_url()` | Blued | 获取Blued直播数据 |
| `get_maoerfm_stream_url()` | 猫耳FM | 获取猫耳FM数据 |
| `get_looklive_stream_url()` | Look | 获取Look直播数据 |
| `get_twitcasting_stream_url()` | TwitCasting | 获取TwitCasting数据 |
| `get_baidu_stream_data()` | 百度直播 | 获取百度直播数据 |
| `get_weibo_stream_data()` | 微博 | 获取微博直播数据 |
| `get_kugou_stream_url()` | 酷狗 | 获取酷狗直播数据 |
| `get_liveme_stream_url()` | LiveMe | 获取LiveMe数据 |
| `get_huajiao_stream_url()` | 花椒 | 获取花椒直播数据 |
| `get_liuxing_stream_url()` | 流星 | 获取流星直播数据 |
| `get_acfun_stream_data()` | Acfun | 获取Acfun数据 |
| `get_changliao_stream_url()` | 畅聊 | 获取畅聊直播数据 |
| `get_yinbo_stream_url()` | 音播 | 获取音播直播数据 |
| `get_yingke_stream_url()` | 映客 | 获取映客直播数据 |
| `get_zhihu_stream_url()` | 知乎 | 获取知乎直播数据 |
| `get_haixiu_stream_url()` | 嗨秀 | 获取嗨秀直播数据 |
| `get_vvxqiu_stream_url()` | VV星球 | 获取VV星球数据 |
| `get_17live_stream_url()` | 17Live | 获取17Live数据 |
| `get_langlive_stream_url()` | 浪Live | 获取浪Live数据 |
| `get_pplive_stream_url()` | 漂漂 | 获取漂漂直播数据 |
| `get_6room_stream_url()` | 六间房 | 获取六间房数据 |
| `get_shopee_stream_url()` | Shopee | 获取Shopee直播数据 |
| `get_jd_stream_url()` | 京东 | 获取京东直播数据 |
| `get_migu_stream_url()` | 咪咕 | 获取咪咕直播数据 |
| `get_lianjie_stream_url()` | 连接 | 获取连接直播数据 |
| `get_laixiu_stream_url()` | 来秀 | 获取来秀直播数据 |
| `get_picarto_stream_url()` | Picarto | 获取Picarto数据 |
| `get_qiandurebo_stream_data()` | 千度热播 | 获取千度热播数据 |
| `get_popkontv_stream_url()` | PopkonTV | 获取PopkonTV数据 |

### 3. src/stream.py（流URL解析）

**职责**：解析各平台的直播流URL，支持质量选择。

**常量**：

```python
QUALITY_MAPPING = {"OD": 0, "BD": 0, "UHD": 1, "HD": 2, "SD": 3, "LD": 4}
QUALITY_MAPPING_BIT = {'OD': 99999, 'BD': 4000, 'UHD': 2000, 'HD': 1000, 'SD': 800, 'LD': 600}
```

**核心函数**：

| 函数 | 说明 |
|------|------|
| `get_douyin_stream_url(json_data, quality, proxy)` | 解析抖音流地址 |
| `get_tiktok_stream_url(json_data, quality, proxy)` | 解析TikTok流地址 |
| `get_kuaishou_stream_url(json_data, quality)` | 解析快手流地址 |
| `get_huya_stream_url(json_data, quality)` | 解析虎牙流地址 |
| `get_douyu_stream_url(json_data, quality, cookies)` | 解析斗鱼流地址 |
| `get_yy_stream_url(json_data)` | 解析YY流地址 |
| `get_bilibili_stream_url(json_data, quality, cookies)` | 解析B站流地址 |
| `get_netease_stream_url(json_data, quality)` | 解析网易CC流地址 |
| `get_stream_url(json_data, quality, ...)` | 通用流地址解析 |

**返回数据结构**：

```python
{
    "anchor_name": str,      # 主播名称
    "is_live": bool,         # 是否正在直播
    "title": str,            # 直播标题
    "quality": str,          # 画质代码
    "m3u8_url": str,         # HLS流地址
    "flv_url": str,          # FLV流地址
    "record_url": str        # 实际录制地址
}
```

### 4. src/utils.py（工具模块）

**职责**：提供通用工具函数。

**核心函数**：

| 函数 | 说明 |
|------|------|
| `trace_error_decorator(func)` | 错误追踪装饰器 |
| `check_md5(file_path)` | 计算文件MD5 |
| `dict_to_cookie_str(cookies)` | 字典转Cookie字符串 |
| `read_config_value(path, section, key)` | 读取配置项 |
| `update_config(path, section, key, value)` | 更新配置项 |
| `get_file_paths(directory)` | 获取目录下所有文件 |
| `remove_emojis(text, replace)` | 移除表情符号 |
| `remove_duplicate_lines(path)` | 去除重复行 |
| `check_disk_capacity(path)` | 检查磁盘空间 |
| `handle_proxy_addr(addr)` | 处理代理地址格式 |
| `generate_random_string(length)` | 生成随机字符串 |
| `jsonp_to_json(jsonp_str)` | JSONP转JSON |
| `get_query_params(url, name)` | 解析URL参数 |

**Color 类**：

```python
class Color:
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    # ...
    @staticmethod
    def print_colored(text, color): ...
```

### 5. src/room.py（房间信息）

**职责**：获取抖音直播间特定信息。

**核心函数**：

| 函数 | 说明 |
|------|------|
| `get_xbogus(url, headers)` | 计算X-Bogus签名 |
| `get_sec_user_id(url, proxy, headers)` | 获取sec_user_id |
| `get_unique_id(url, proxy, headers)` | 获取抖音号 |
| `get_live_room_id(room_id, sec_uid, ...)` | 获取直播间webID |

### 6. src/http_clients/（HTTP客户端）

**async_http.py**：

| 函数 | 说明 |
|------|------|
| `async_req(url, proxy, headers, ...)` | 异步GET/POST请求 |
| `get_response_status(url, ...)` | HEAD请求检查URL状态 |

**sync_http.py**：同步HTTP请求实现（备用）

### 7. src/ab_sign.py（签名模块）

**职责**：实现抖音 A-Bogus 签名算法，用于绕过反爬机制。

### 8. src/proxy.py（代理检测）

**职责**：检测系统代理配置。

**ProxyDetector 类**：

```python
class ProxyDetector:
    def is_proxy_enabled() -> bool
    def get_proxy_info() -> ProxyInfo
```

### 9. src/logger.py（日志模块）

**职责**：使用 Loguru 配置日志系统。

### 10. gui.pyw（图形界面）

**职责**：提供 Tkinter GUI 界面。

**核心类**：

| 类 | 说明 |
|------|------|
| `SystemTray` | 系统托盘管理 |
| `AdvancedSettingsWindow` | 高级设置窗口 |
| `LiveRecorderGUI` | 主GUI类 |

**GUI 功能**：

- 开始/停止录制按钮
- URL配置编辑区
- 实时日志显示
- 系统托盘支持
- 配置文件热重载

### 11. msg_push.py（消息推送）

**职责**：实现多平台消息推送。

**支持平台**：

| 平台 | 函数 | 说明 |
|------|------|------|
| 钉钉 | `dingtalk(url, content, phone, is_atall)` | 钉钉群机器人 |
| 微信 | `xizhi(url, title, content)` | 微信推送 |
| 邮箱 | `send_email(host, login, pass, ...)` | SMTP邮件 |
| TG | `tg_bot(chat_id, token, content)` | Telegram Bot |
| Bark | `bark(api, title, content, ...)` | iOS推送 |
| NTFY | `ntfy(api, title, content, ...)` | NTFY通知 |
| PushPlus | `pushplus(token, title, content)` | 微信推送+ |

### 12. ffmpeg_install.py（FFmpeg管理）

**职责**：检测和管理ffmpeg安装。

**核心函数**：

| 函数 | 说明 |
|------|------|
| `check_ffmpeg()` | 检查ffmpeg是否存在 |
| `get_ffmpeg_path()` | 获取ffmpeg路径 |

---

## 核心类与函数

### 录制线程执行流程

```python
def start_record(url_data: tuple, count_variable: int = -1) -> None:
    """
    录制线程主函数
    
    url_data: (画质, URL, 主播名) 元组
    count_variable: 序号
    """
    while True:
        # 1. URL路由到对应平台解析器
        if 'douyin.com' in url:
            json_data = spider.get_douyin_web_stream_data(url, proxy, cookies)
            port_info = stream.get_douyin_stream_url(json_data, quality, proxy)
        # ... 其他平台
        
        # 2. 检查直播状态
        if not port_info['is_live']:
            print("等待直播...")
            time.sleep(delay)
            continue
        
        # 3. 获取流地址
        real_url = select_source_url(url, port_info)
        
        # 4. 构建ffmpeg命令
        ffmpeg_command = build_ffmpeg_command(real_url, save_path)
        
        # 5. 执行录制
        check_subprocess(record_name, url, ffmpeg_command, save_type)
```

### FFmpeg命令构建

```python
ffmpeg_command = [
    'ffmpeg', "-y",
    "-v", "verbose",
    "-rw_timeout", "15000000",
    "-loglevel", "error",
    "-user_agent", user_agent,
    "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
    "-re", "-i", real_url,
    "-reconnect_delay_max", "60",
    "-reconnect_streamed", "-reconnect_at_eof",
    # 视频编码参数...
    "-c:v", "copy", "-c:a", "copy",
    "-f", "mpegts",  # 或 flv/mp4/mkv
    save_file_path
]
```

### 消息推送机制

```python
def push_message(record_name, live_url, content) -> None:
    """根据配置推送直播状态通知"""
    push_functions = {
        '微信': lambda: xizhi(xizhi_api_url, msg_title, content),
        '钉钉': lambda: dingtalk(dingtalk_api_url, content, ...),
        '邮箱': lambda: send_email(...),
        'TG': lambda: tg_bot(tg_chat_id, tg_token, content),
        'BARK': lambda: bark(bark_msg_api, title, content, ...),
        'NTFY': lambda: ntfy(ntfy_api, title, content, ...),
        'PUSHPLUS': lambda: pushplus(pushplus_token, title, content),
    }
    
    for platform, func in push_functions.items():
        if platform in live_status_push.upper():
            threading.Thread(target=func).start()
```

---

## 依赖关系

```
requirements.txt
├── requests              # HTTP请求库
├── loguru                # 日志库
├── pycryptodome          # 加密算法
├── distro                # 系统信息
├── tqdm                  # 进度条
├── httpx[http2]          # 异步HTTP客户端
├── PyExecJS              # JavaScript执行
├── pystray               # 系统托盘
├── Pillow                # 图像处理
└── weverse               # Wevers SDK
```

### 模块依赖图

```
main.py
├── src/spider.py ──────> src/http_clients/async_http.py
│                       ├── src/room.py
│                       ├── src/ab_sign.py
│                       └── src/utils.py
├── src/stream.py ──────> src/spider.py
│                       └── src/http_clients/async_http.py
├── src/utils.py
├── src/proxy.py
├── msg_push.py ─────────> src/logger.py
├── ffmpeg_install.py
└── i18n.py

gui.pyw ────────────────> main.py (子进程)
                      └── tkinter (系统库)
```

---

## 配置说明

### config/config.ini

**录制设置**：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `language(zh_cn/en)` | zh_cn | 语言 |
| `直播保存路径(不填则默认)` | - | 保存路径 |
| `保存文件夹是否以作者区分` | 是 | 按主播名建目录 |
| `保存文件夹是否以时间区分` | 否 | 按日期建目录 |
| `保存文件夹是否以标题区分` | 否 | 按标题建目录 |
| `保存文件名是否包含标题` | 否 | 文件名含标题 |
| `是否去除名称中的表情符号` | 是 | 清理Emoji |
| `视频保存格式` | ts | ts/mkv/flv/mp4/mp3/m4a |
| `原画\|超清\|高清\|标清\|流畅` | 原画 | 录制画质 |
| `是否使用代理ip` | 否 | 启用代理 |
| `同一时间访问网络的线程数` | 3 | 并发录制数 |
| `循环时间(秒)` | 120 | 检测间隔 |
| `分段录制是否开启` | 否 | 分段录制 |
| `视频分段时间(秒)` | 1800 | 30分钟一段 |
| `录制完成后自动转为mp4格式` | 否 | 自动转码 |
| `mp4格式重新编码为h264` | 否 | H.264编码 |

**Cookie配置**：

各平台需要登录后获取Cookie才能录制，配置在 `[Cookie]` 节：

- 抖音cookie、B站cookie、快手cookie 等
- 部分平台需要填写Cookie才能获取直播流

**推送配置**：

| 配置项 | 说明 |
|--------|------|
| `直播状态推送渠道` | 微信\|钉钉\|tg\|邮箱\|bark\|ntfy\|pushplus |
| `开播推送开启` | 开播时推送通知 |
| `关播推送开启` | 关播时推送通知 |
| `只推送通知不录制` | 仅监控不录制 |

### URL配置格式 (URL_config.ini)

```
# 格式: 画质,URL,主播名
原画,https://live.douyin.com/xxxxx,主播昵称
# 抖音分享链接
原画,https://v.douyin.com/xxxxx,张三
# 注释行
#超清,https://...
```

---

## 运行方式

### 1. 命令行模式

```bash
# 安装依赖
pip install -r requirements.txt

# 运行录制
python main.py
```

### 2. 图形界面模式

```bash
python gui.pyw
```

### 3. Docker部署

```bash
# 构建镜像
docker build -t douyin-live-recorder .

# 运行容器
docker run -d \
  -v ./config:/app/config \
  -v ./downloads:/app/downloads \
  douyin-live-recorder
```

或使用 docker-compose：

```bash
docker-compose up -d
```

### 4. 环境要求

- Python 3.8+
- ffmpeg（程序会自动检测，Windows内置）
- 网络连接（访问直播平台）

### 5. 常见问题

**Q: 录制失败提示"请检查网络"**
A: 检查是否需要代理，部分海外平台需要全局代理

**Q: 抖音无法录制**
A: 需要在 config.ini 中配置有效的抖音 Cookie

**Q: ffmpeg 未找到**
A: 确保 ffmpeg 已安装并加入 PATH，或使用程序内置的 ffmpeg

---

## 贡献者

- 作者: Hmily
- GitHub: https://github.com/ihmily
- 许可证: MIT License
