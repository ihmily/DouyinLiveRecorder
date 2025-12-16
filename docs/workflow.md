# DouyinLiveRecorder 工作流程文档

## 概述

DouyinLiveRecorder 是一个多平台直播录制工具，支持 40+ 直播平台。核心功能是监控直播间 URL，在主播开播时自动使用 FFmpeg 录制，并在录制完成后可选转换为 MP4 格式。

## 总体架构

```
主程序入口 (main.py)
    │
    ├── 配置加载 (config/config.ini, config/URL_config.ini)
    │
    ├── 后台监控线程
    │   ├── display_info: 状态显示 (5秒刷新)
    │   ├── adjust_max_request: 动态调整并发 (5秒)
    │   └── backup_file_start: 配置备份 (10分钟)
    │
    └── 主循环 (每3秒)
        │
        ├── 读取 URL 列表
        ├── 平台检测
        └── 为每个 URL 创建录制线程
            │
            └── start_record() 线程
                ├── 等待直播开始
                ├── 获取流数据 (spider.py)
                ├── 处理流 URL (stream.py)
                ├── FFmpeg 录制
                └── 录制完成处理 (转 MP4、通知等)
```

## 核心文件说明

| 文件 | 作用 |
|------|------|
| `main.py` | 主入口，配置加载、线程管理、FFmpeg 录制 |
| `src/spider.py` | 平台特定的直播流数据获取（异步） |
| `src/stream.py` | 流 URL 处理，根据质量选择最优源 |
| `src/room.py` | 房间/用户 ID 解析 |
| `msg_push.py` | 推送通知（微信、钉钉、Telegram 等） |
| `config/config.ini` | 主配置文件 |
| `config/URL_config.ini` | 直播间 URL 列表 |

---

## 一、启动流程

### 1.1 初始化 (main.py:1714-1783)

```
1. FFmpeg 检查 (main.py:1723-1725)
   └── 未安装则退出

2. 启动后台线程 (main.py:1727-1728)
   └── 配置备份线程

3. URL 去重 (main.py:1729)
   └── 移除 URL_config.ini 中重复行

4. 代理检测 (main.py:1765-1782)
   └── 检测系统全局代理设置
```

### 1.2 关键配置项 (main.py:1803-1876)

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `video_save_type` | ts | 录制格式 (ts/mkv/flv/mp4/mp3/m4a) |
| `video_record_quality` | 原画 | 质量 (原画/超清/高清/标清/流畅) |
| `max_request` | 3 | 并发线程数 |
| `delay_default` | 120 | 循环检测间隔(秒) |
| `split_video_by_time` | False | 是否分段录制 |
| `split_time` | 1800 | 分段时长(秒) |
| `converts_to_mp4` | False | TS 转 MP4 |
| `converts_to_h264` | False | 重新编码为 h264 |
| `delete_origin_file` | False | 转码后删除原文件 |
| `disk_space_limit` | 1.0 | 磁盘空间阈值(GB) |

---

## 二、URL 监控与平台检测

### 2.1 URL 格式支持

```ini
# 单个 URL
https://live.douyin.com/123456

# URL + 质量
原画,https://live.douyin.com/123456

# URL + 主播名
https://live.douyin.com/123456,主播: 张三

# URL + 质量 + 主播名
原画,https://live.douyin.com/123456,主播: 张三
```

### 2.2 支持的平台 (main.py:1996-2072)

**国内平台**：抖音、快手、虎牙、斗鱼、YY、B站、小红书、bigo、blued 等

**海外平台**：TikTok、SOOP、Twitch、YouTube、LiveMe、ShowRoom、CHZZK 等

### 2.3 平台检测逻辑 (main.py:2092-2111)

```python
# 检查 URL 是否属于已知平台
if url_host in platform_host or any(ext in url for ext in (".flv", ".m3u8")):
    # URL 有效，添加到录制队列
else:
    # 未知平台，标记为注释行
```

---

## 三、线程管理

### 3.1 线程创建 (main.py:2127-2142)

每个直播 URL 创建一个独立的 daemon 线程：

```python
for url_tuple in text_no_repeat_url:
    if url_tuple[1] not in running_list:
        thread = threading.Thread(target=start_record, args=[url_tuple, monitoring])
        thread.daemon = True
        thread.start()
```

### 3.2 并发控制 (main.py:298-325)

使用信号量限制并发请求数：

```python
semaphore = threading.Semaphore(max_request)

# 在获取流数据时使用
with semaphore:
    json_data = asyncio.run(spider.get_douyin_web_stream_data(...))
```

**动态调整**：根据错误率自动调整并发数（每 5 秒）

---

## 四、直播流数据获取

### 4.1 start_record 主函数 (main.py:545-1647)

```
start_record(url_data, count_variable)
    │
    ├── 平台识别 (main.py:577-1040)
    │
    ├── 获取流数据 (spider.py)
    │   └── get_douyin_web_stream_data()
    │   └── get_tiktok_stream_data()
    │   └── get_bilibili_room_info()
    │   └── ...
    │
    └── 处理流 URL (stream.py)
        └── get_douyin_stream_url()
        └── get_tiktok_stream_url()
        └── ...
```

### 4.2 spider.py 关键函数

| 平台 | 函数 | 行号 |
|------|------|------|
| 抖音 | `get_douyin_web_stream_data()` | 68 |
| 抖音APP | `get_douyin_app_stream_data()` | 145 |
| TikTok | `get_tiktok_stream_data()` | 286 |
| 快手 | `get_kuaishou_stream_data()` | 316 |
| 虎牙 | `get_huya_stream_data()` | 408 |
| 斗鱼 | `get_douyu_info_data()` | 548 |
| B站 | `get_bilibili_room_info()` | 677 |

### 4.3 返回数据格式

```python
{
    "anchor_name": "主播名",
    "is_live": True,
    "title": "直播标题",
    "m3u8_url": "HLS 直播源",
    "flv_url": "FLV 直播源",
    "record_url": "最终录制地址"
}
```

---

## 五、文件命名与目录结构

### 5.1 目录结构 (main.py:1118-1145)

```
downloads/
├── 抖音直播/
│   ├── 主播A/
│   │   └── 2025-12-16/
│   │       └── 主播A_直播标题_2025-12-16_14-30-00.ts
│   └── 主播B/
├── TikTok直播/
└── B站直播/
```

**路径选项**：
- `folder_by_author`: 按主播分文件夹
- `folder_by_time`: 按日期分文件夹
- `folder_by_title`: 按标题分文件夹

### 5.2 文件命名 (main.py:1120-1125)

```
{主播名}_{标题(可选)}_{YYYY-MM-DD_HH-MM-SS}.{格式}

示例：
Seven(国服老虎)_2025-12-16_14-50-21_000.ts
```

---

## 六、FFmpeg 录制

### 6.1 基础命令参数 (main.py:1175-1205)

```bash
ffmpeg -y \
    -v verbose \
    -rw_timeout 15000000 \
    -loglevel error \
    -hide_banner \
    -user_agent "..." \
    -protocol_whitelist "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy" \
    -thread_queue_size 1024 \
    -analyzeduration 20000000 \
    -probesize 10000000 \
    -fflags +discardcorrupt \
    -re -i {直播流URL} \
    -bufsize 8000k \
    -sn -dn \
    -reconnect_delay_max 60 \
    -reconnect_streamed \
    -reconnect_at_eof \
    ...
```

### 6.2 格式特定参数

#### TS 格式 (main.py:1522-1603)

```bash
# 非分段
-c:v copy -c:a copy -map 0 -f mpegts output.ts

# 分段
-c:v copy -c:a copy -map 0 \
-f segment -segment_time 1800 -segment_format mpegts \
-reset_timestamps 1 \
output_%03d.ts
```

#### MP4 格式 (main.py:1475-1520)

```bash
-c:v copy -c:a aac -map 0 \
-f segment -segment_time 1800 -segment_format mp4 \
-movflags +frag_keyframe+empty_moov \
output_%03d.mp4
```

#### FLV 格式 (main.py:1353-1425)

```bash
-map 0 -c:v copy -c:a copy \
-bsf:a aac_adtstoasc \
-f flv output.flv
```

### 6.3 进程监控 (main.py:436-450)

```python
while process.poll() is None:  # 进程运行中
    # 检查 URL 是否被注释
    if record_url in url_comments:
        process.send_signal(signal.SIGINT)
        process.wait()
        return
    time.sleep(1)
```

---

## 七、TS 转 MP4 流程

### 7.1 触发条件 (main.py:451-491)

```python
if converts_to_mp4 and save_type == 'TS':
    if split_video_by_time:
        # 分段文件逐个转换
        for path in file_paths:
            threading.Thread(target=converts_mp4, args=(path,)).start()
    else:
        # 单文件转换
        threading.Thread(target=converts_mp4, args=(save_file_path,)).start()
```

### 7.2 转换函数 (main.py:219-251)

#### 快速转封装（默认）

```bash
ffmpeg -i input.ts -c:v copy -c:a copy -f mp4 output.mp4
```

- 速度快，不重新编码
- 直接复制视频和音频流

#### H264 重新编码

```bash
ffmpeg -i input.ts \
    -c:v libx264 -preset veryfast -crf 23 \
    -vf format=yuv420p \
    -c:a copy \
    -f mp4 output.mp4
```

- 适用于需要兼容性的场景
- 配置项：`converts_to_h264 = True`

### 7.3 转换后处理

```python
if delete_origin_file:
    os.remove(input_ts_file)  # 删除原 TS 文件
```

---

## 八、工作流时序图

```
┌────────────────────────────────────────────────────────────┐
│                      程序启动                              │
│  FFmpeg检查 → 配置加载 → 启动后台线程 → 代理检测          │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                    主循环 (每3秒)                          │
│  读取 URL_config.ini → 去重 → 平台检测 → 创建录制线程     │
└─────────────────────────┬──────────────────────────────────┘
                          │
              ┌───────────▼───────────┐
              │   start_record 线程   │
              └───────────┬───────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                    等待直播开始                            │
│  每隔 delay_default 秒查询直播状态 (is_live)              │
└─────────────────────────┬──────────────────────────────────┘
                          │ is_live = True
┌─────────────────────────▼──────────────────────────────────┐
│                    获取直播流数据                          │
│  spider.get_*_stream_data() → stream.get_*_stream_url()   │
└─────────────────────────┬──────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────┐
│                    FFmpeg 录制                             │
│  构建命令 → 启动进程 → 监控状态 → 等待结束                │
└─────────────────────────┬──────────────────────────────────┘
                          │ 直播结束
┌─────────────────────────▼──────────────────────────────────┐
│                    录制完成处理                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │ TS 转 MP4   │  │ 推送通知    │  │ 执行自定义脚本      │ │
│  │ (可选)     │  │ (可选)     │  │ (可选)             │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────┬──────────────────────────────────┘
                          │
                          ▼
                   等待30秒后重新检测
                   (回到等待直播开始)
```

---

## 九、错误处理与恢复

### 9.1 动态并发调整 (main.py:298-325)

```python
error_window = []           # 错误率历史
error_window_size = 10      # 窗口大小
error_threshold = 5         # 错误率阈值 (50%)

# 错误太多 → 降低并发
if error_rate > error_threshold:
    max_request = max(1, max_request - 1)

# 错误减少 → 提高并发
elif error_rate < error_threshold / 2:
    max_request += 1
```

### 9.2 录制循环恢复 (main.py:1613-1639)

- 直播结束后 30 秒重新检测（防止卡顿漏录）
- 错误过多时延迟 60 秒
- 检测间隔添加 ±5 秒随机值（避免同时请求）

---

## 十、推送通知

### 10.1 支持的渠道 (msg_push.py)

- 微信 (WeChat)
- 钉钉 (DingTalk)
- 邮箱 (Email)
- Telegram
- Bark
- ntfy
- PushPlus

### 10.2 触发时机

- 直播开始时 (main.py:1098-1111)
- 直播结束时 (main.py:1076-1092)

---

## 十一、downloads 目录示例

当前录制的文件：

```
downloads/
└── 抖音直播/
    ├── Seven(国服老虎)/
    │   └── Seven(国服老虎)_2025-12-16_14-50-21_000.ts
    └── 王者荣耀Cc(国服老虎)/
        └── 王者荣耀Cc(国服老虎)_2025-12-16_14-50-22_000.ts
```

**文件命名规则**：`{主播名}_{日期}_{时间}_{分段序号}.{格式}`

---

## 十二、常用配置示例

### 录制 + 自动转 MP4

```ini
[Default]
video_save_type = ts
converts_to_mp4 = True
delete_origin_file = True
```

### 分段录制（每30分钟）

```ini
[Default]
split_video_by_time = True
split_time = 1800
```

### 按主播和日期分目录

```ini
[Default]
folder_by_author = True
folder_by_time = True
```
