# [DLR] DouyinLiveRecorder 模块改进文档

## 📋 概述

本文档详细说明了为 DouyinLiveRecorder 创建的统一架构模块，特别针对 **PandaLive** 和 **SOOP** 平台的功能完善。

**创建日期**: 2025-11-05
**版本**: v1.0
**基于**: DouyinLiveRecorder v4.0.7

---

## 🎯 核心设计原则

### 统一日志标签体系

所有日志采用统一格式：`[DLR][{MODULE}][{PLATFORM}] {LEVEL}: {message}`

**模块标签 (MODULE)**:
- `[M3U8]` - M3U8 拉流和处理
- `[REC]` - 录制操作
- `[SCHED]` - 调度器操作
- `[DEPS]` - 依赖管理
- `[PREMIUM]` - 付费/粉丝房处理
- `[QOS]` - 质量控制（码率/帧率）
- `[COOKIE]` - Cookie 管理
- `[TG]` - Telegram 通知
- `[I18N]` - 国际化
- `[CFG]` - 配置管理
- `[PATH]` - 路径和文件命名
- `[ERR]` - 错误处理

**平台标签 (PLATFORM)**:
- `[PANDA]` - PandaLive
- `[SOOP]` - SOOP (AfreecaTV)
- `[DOUYIN]` - 抖音
- `[TIKTOK]` - TikTok
- `[GENERIC]` - 通用/多平台

---

## 📦 创建的模块

### 1. `dlr_logger.py` - 统一日志系统

**位置**: `src/dlr_logger.py`

**功能**:
- ✅ 统一的 `[DLR]` 日志前缀
- ✅ 模块化标签系统 (`[M3U8]`, `[REC]`, `[TG]` 等)
- ✅ 平台特定标签 (`[PANDA]`, `[SOOP]`)
- ✅ 多级别日志 (INFO, DEBUG, WARN, ERROR)
- ✅ 关键操作锚点 (例如: `FETCH_START`, `AUTO_START`, `FALLBACK_TO_PREV_M3U8`)

**使用示例**:
```python
from src.dlr_logger import dlr_logger, Platform

# 基本日志
dlr_logger.info_m3u8("Starting to fetch playlist", Platform.PANDA)
# 输出: [DLR][M3U8][PANDA] INFO: Starting to fetch playlist

# 详细错误日志
dlr_logger.error_detailed(
    "유저 정보가 없습니다 (No user info)",
    Platform.PANDA,
    line=1281,
    cause="bjInfo not in response"
)
# 输出: [DLR][ERR][PANDA] ERROR: 유저 정보가 없습니다 (No user info) | Line: 1281 | Cause: bjInfo not in response
```

**关键锚点**:
- `FETCH_START` - M3U8 拉取开始
- `REFRESH_EVERY_5M` - 5 分钟刷新
- `AUTO_START` - 自动录制开始
- `FALLBACK_TO_PREV_M3U8` - 回退到历史 m3u8
- `SELECT_HIGHEST_BITRATE` - 选择最高码率
- `SOOP_SANITIZE_APPLIED` - SOOP Cookie 清洗
- `TEMPLATE_APPLIED` - Telegram 模板应用

---

### 2. `m3u8_manager.py` - M3U8 管理器

**位置**: `src/m3u8_manager.py`

**功能**:
- ✅ **定时刷新**: 每 5 分钟自动刷新 m3u8 URL
- ✅ **历史记录**: 保存最近 10 分钟的 m3u8 历史
- ✅ **回退策略**: 遇到付费房错误时自动回退到历史 URL
- ✅ **日志记录**: 保存到 `logs/BJ-live-m3u8-YYYYMMDD.log`
- ✅ **多变体支持**: 记录所有可用的质量变体
- ✅ **恢复功能**: 从日志文件加载历史记录

**使用示例**:
```python
from src.m3u8_manager import m3u8_manager
from src.dlr_logger import Platform

# 添加 m3u8 记录
m3u8_manager.add_record(
    room_url="https://www.pandalive.co.kr/live/play/test123",
    m3u8_url="https://cdn.pandalive.co.kr/live/test123/playlist.m3u8",
    bitrate=6000,
    resolution="1080p",
    platform=Platform.PANDA
)

# 检查是否需要刷新
if m3u8_manager.needs_refresh(room_url):
    # 执行刷新...
    pass

# 遇到付费房错误时回退
fallback = m3u8_manager.get_fallback_m3u8(room_url, Platform.PANDA)
if fallback:
    print(f"Using fallback m3u8: {fallback.url}")
```

**配置键** (建议加入 config.ini):
```ini
[general]
refresh_interval_secs = 300  ; 5分钟刷新
log_cleanup_days = 7

[features]
retry_from_log_minutes = 10
fallback_window_minutes = 10
```

---

### 3. `cookie_manager.py` - Cookie 管理器

**位置**: `src/cookie_manager.py`

**功能**:
- ✅ **SOOP Cookie 清洗**: 移除无效字符 (`\n`, `\r`, `\t`, 控制字符)
- ✅ **Cookie 验证**: 检查 Cookie 格式和有效性
- ✅ **Cookie 解析**: 解析为字典格式
- ✅ **认证令牌提取**: 提取 `AuthTicket`, `PdboxTicket` 等
- ✅ **Cookie 合并**: 新旧 Cookie 智能合并

**使用示例**:
```python
from src.cookie_manager import cookie_manager
from src.dlr_logger import Platform

# SOOP Cookie 清洗
dirty_cookie = "AuthTicket=abc123\n\rSID=xyz789\t"
clean_cookie = cookie_manager.sanitize_soop_cookie(dirty_cookie)
# 输出: [DLR][COOKIE][SOOP] INFO: SOOP_SANITIZE_APPLIED

# 验证 Cookie
is_valid = cookie_manager.validate_cookie(clean_cookie, Platform.SOOP)

# 提取认证令牌
auth_token = cookie_manager.extract_auth_token(cookie, "AuthTicket", Platform.SOOP)

# 合并 Cookie
merged = cookie_manager.merge_cookies(old_cookie, new_cookie, Platform.PANDA)
```

**修复的问题**:
- ✅ SOOP Cookie 中的换行符导致请求失败
- ✅ 控制字符导致的编码错误
- ✅ Cookie 格式不规范问题

---

### 4. `telegram_enhanced.py` - Telegram 推送增强

**位置**: `src/telegram_enhanced.py`

**功能**:
- ✅ **状态颜色**: 🟢 在线 / 🔴 离线 / 🟣 付费房 / ⚠️ 错误
- ✅ **TEMPLATE_V2**: 完整的消息模板格式
- ✅ **付费房检测**: 特殊通知格式
- ✅ **M3U8 更新通知**: 质量变化提醒
- ✅ **Markdown 格式**: 美化的消息呈现

**使用示例**:
```python
from src.telegram_enhanced import telegram_enhanced, LiveStatus, RecordStatus

# 完整格式消息
msg = telegram_enhanced.format_message_v2(
    platform="PandaLive",
    anchor="TestAnchor-123",
    live_status=LiveStatus.ONLINE.value,
    rec_status=RecordStatus.RECORDING.value,
    title="测试直播间",
    url="https://www.pandalive.co.kr/live/play/test123",
    m3u8="https://cdn.pandalive.co.kr/live/test123/playlist.m3u8",
    bitrate=6000,
    resolution="1080p"
)

# 付费房检测通知
premium_msg = telegram_enhanced.format_premium_room_detected(
    platform="SOOP",
    anchor="PremiumAnchor-456",
    type="fans-only",
    message="This room requires authentication"
)

# M3U8 更新通知
update_msg = telegram_enhanced.format_m3u8_update(
    platform="PandaLive",
    anchor="TestAnchor-123",
    bitrate_change=(4500, 6000)  # 质量提升
)
```

**消息样例**:
```
📺 *PandaLive Live Notification*
━━━━━━━━━━━━━━━━━━
👤 *Anchor:* `TestAnchor-123`
🏠 *Room:* `live123`
🟢 *Status:* `ONLINE`
🔴 *Recording:* `RECORDING`
📝 *Title:* 测试直播间标题
🎬 *Quality:* `1080p @ 6000kbps`
🔗 *URL:* https://www.pandalive.co.kr/live/play/test123
📡 *M3U8:* `https://cdn.pandalive.co.kr/...`
⏰ *Time:* `2025-11-05 14:52:18`
━━━━━━━━━━━━━━━━━━
```

**配置键** (建议加入 config.ini):
```ini
[telegram]
enabled = true
template = full_v2
status_color = true
push_m3u8 = true
```

---

### 5. `qos_selector.py` - 质量选择器

**位置**: `src/qos_selector.py`

**功能**:
- ✅ **智能质量选择**: 优先选择更高分辨率 (1080p > 720p)
- ✅ **码率感知**: 避免 720p 高码率误选问题
- ✅ **帧率优化**: 同分辨率下优先 60fps
- ✅ **自适应切换**: 带滞后的质量切换策略
- ✅ **URL 解析**: 从 URL 和 m3u8 元数据提取质量信息

**评分公式**:
```
score = resolution * 1000 + fps * 10 + bitrate * 0.01
```

**示例**:
- 1080p60 @ 6000kbps = **1,080,660** ✅ 最佳
- 720p60 @ 8000kbps  = **720,680** ❌ 虽然码率高但分辨率低
- 1080p30 @ 4000kbps = **1,080,340** ✅ 比 720p60 好

**使用示例**:
```python
from src.qos_selector import qos_selector, StreamVariant
from src.dlr_logger import Platform

# 解析变体
variant = qos_selector.parse_variant("https://cdn.example.com/live/playlist_1080p60_6000k.m3u8")
print(f"Resolution: {variant.resolution}, FPS: {variant.fps}, Bitrate: {variant.bitrate}kbps")

# 选择最佳变体
variants = [variant1, variant2, variant3]
best = qos_selector.select_best_variant(variants, Platform.PANDA)
# 输出: [DLR][QOS] INFO: SELECT_HIGHEST_BITRATE

# 判断是否需要切换
should_switch = qos_selector.should_switch_variant(current, new, Platform.PANDA)
if should_switch:
    # 输出: [DLR][QOS] INFO: SWITCH_VARIANT_IF_BETTER: 4000kbps -> 6000kbps
    pass
```

**配置键** (建议加入 config.ini):
```ini
[features]
prefer_highest_bitrate = true
min_switch_improve_kbps = 500
```

---

### 6. `dependency_checker.py` - 依赖检查器

**位置**: `src/dependency_checker.py`

**功能**:
- ✅ **Python 版本检查**: 确保 >= 3.10
- ✅ **FFmpeg 检测**: 检查 FFmpeg 是否安装
- ✅ **自动安装**: 自动安装缺失的 Python 包
- ✅ **详细指导**: 提供清晰的安装说明
- ✅ **requirements.txt 生成**: 自动生成依赖文件

**使用示例**:
```python
from src.dependency_checker import dependency_checker

# 运行完整检查
all_satisfied = dependency_checker.run_full_check()

if not all_satisfied:
    print("请安装缺失的依赖")
    sys.exit(1)
```

**检查的依赖**:
- ✅ Python >= 3.10
- ✅ FFmpeg
- ✅ httpx >= 0.24.0
- ✅ loguru >= 0.7.0
- ✅ PyExecJS >= 1.5.0
- ✅ aiofiles >= 23.0.0 (可选)

**配置键** (建议加入 config.ini):
```ini
[features]
auto_install_deps = true
```

---

## 🎯 针对 PandaLive 和 SOOP 的特殊改进

### PandaLive 特色功能

1. **错误细化** (`[DLR][PANDA][ERR]`)
   - ✅ 韩文错误信息翻译
   - ✅ 详细的行号和原因追踪
   - ✅ 常见错误的友好提示

   **示例错误处理**:
   ```python
   dlr_logger.error_detailed(
       "유저 정보가 없습니다 (No user info)",
       Platform.PANDA,
       line=1281,
       cause="bjInfo not in response"
   )
   ```

2. **付费房检测**
   - ✅ needAdult 错误检测
   - ✅ 自动回退到历史 m3u8
   - ✅ Telegram 付费房通知

3. **质量选择**
   - ✅ HLS 多变体解析
   - ✅ 智能选择最佳质量
   - ✅ 自适应码率切换

### SOOP 特色功能

1. **Cookie 清洗** (`[DLR][COOKIE][SOOP]`)
   - ✅ SOOP_SANITIZE_APPLIED 锚点
   - ✅ 移除无效字符
   - ✅ 自动格式化

2. **多域名支持**
   - ✅ sooplive.co.kr (韩国)
   - ✅ sooplive.com (国际)
   - ✅ 自动域名识别

3. **付费房回退**
   - ✅ needCoinPurchase 检测
   - ✅ needUnlimitItem 检测
   - ✅ -3002 (19+) 错误处理
   - ✅ 自动回退到历史 master.m3u8

4. **认证管理**
   - ✅ AuthTicket 提取
   - ✅ 自动登录重试
   - ✅ Cookie 持久化

---

## 📝 集成指南

### 步骤 1: 更新 main.py

在 `main.py` 顶部添加导入：

```python
# [DLR] Import unified modules
from src.dlr_logger import dlr_logger, Platform, log_rec_auto_start
from src.m3u8_manager import m3u8_manager
from src.cookie_manager import cookie_manager
from src.telegram_enhanced import telegram_enhanced, LiveStatus, RecordStatus
from src.qos_selector import qos_selector
from src.dependency_checker import dependency_checker
```

### 步骤 2: 启动时检查依赖

在主函数开始处添加：

```python
def main():
    # [DLR][DEPS] Check dependencies
    if not dependency_checker.run_full_check():
        logger.error("依赖检查失败，请安装缺失的依赖")
        return
```

### 步骤 3: 更新 PandaLive 处理

在 `main.py` 的 PandaLive 部分：

```python
elif record_url.find("www.pandalive.co.kr/") > -1:
    platform = 'PandaTV'
    with semaphore:
        if global_proxy or proxy_address:
            try:
                # [DLR][M3U8][PANDA] Fetch stream data
                log_rec_auto_start(anchor_name, Platform.PANDA)

                json_data = asyncio.run(spider.get_pandatv_stream_data(
                    url=record_url,
                    proxy_addr=proxy_address,
                    cookies=pandatv_cookie
                ))

                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                # [DLR][M3U8] Add to manager
                if port_info and port_info.get('m3u8_url'):
                    m3u8_manager.add_record(
                        room_url=record_url,
                        m3u8_url=port_info['m3u8_url'],
                        platform=Platform.PANDA
                    )

            except RuntimeError as e:
                error_msg = str(e)
                # [DLR][PREMIUM][PANDA] Handle needAdult error
                if "needAdult" in error_msg:
                    dlr_logger.error_premium(
                        "Adult verification required",
                        Platform.PANDA
                    )
                    # Try fallback
                    fallback = m3u8_manager.get_fallback_m3u8(record_url, Platform.PANDA)
                    if fallback:
                        port_info = {'m3u8_url': fallback.url}
                else:
                    dlr_logger.error_detailed(
                        error_msg,
                        Platform.PANDA,
                        cause="PandaLive API error"
                    )
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")
```

### 步骤 4: 更新 SOOP 处理

在 `main.py` 的 SOOP 部分：

```python
elif record_url.find("sooplive.co.kr/") > -1 or record_url.find("sooplive.com/") > -1:
    platform = 'SOOP'
    with semaphore:
        if global_proxy or proxy_address:
            # [DLR][COOKIE][SOOP] Sanitize cookie
            clean_cookie = cookie_manager.sanitize_soop_cookie(sooplive_cookie)

            try:
                json_data = asyncio.run(spider.get_sooplive_stream_data(
                    url=record_url,
                    proxy_addr=proxy_address,
                    cookies=clean_cookie,
                    username=sooplive_username,
                    password=sooplive_password
                ))

                # Update cookie if new one returned
                if json_data and json_data.get('new_cookies'):
                    merged_cookie = cookie_manager.merge_cookies(
                        clean_cookie,
                        json_data['new_cookies'],
                        Platform.SOOP
                    )
                    utils.update_config(
                        config_file, 'Cookie', 'sooplive_cookie', merged_cookie
                    )

                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                # [DLR][M3U8][SOOP] Add to manager
                if port_info and port_info.get('m3u8_url'):
                    m3u8_manager.add_record(
                        room_url=record_url,
                        m3u8_url=port_info['m3u8_url'],
                        platform=Platform.SOOP
                    )

            except Exception as e:
                error_msg = str(e)
                # [DLR][PREMIUM][SOOP] Handle paid room errors
                if "needCoinPurchase" in error_msg or "needUnlimitItem" in error_msg:
                    dlr_logger.error_premium(f"Paid room: {error_msg}", Platform.SOOP)

                    # Try fallback
                    fallback = m3u8_manager.get_fallback_m3u8(record_url, Platform.SOOP)
                    if fallback:
                        port_info = {'m3u8_url': fallback.url}
                else:
                    dlr_logger.error_detailed(error_msg, Platform.SOOP)
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问SOOP平台")
```

### 步骤 5: 添加 M3U8 定时刷新

在主循环中添加刷新逻辑：

```python
# [DLR][M3U8] Periodic refresh
for room_url in recording:
    if m3u8_manager.needs_refresh(room_url):
        dlr_logger.info_m3u8(f"Refreshing m3u8 for {room_url}")
        # Re-fetch stream data...
```

### 步骤 6: 集成 Telegram Enhanced

替换现有的 Telegram 推送逻辑：

```python
if enable_telegram:
    msg = telegram_enhanced.format_message_v2(
        platform=platform,
        anchor=anchor_name,
        live_status=LiveStatus.ONLINE.value,
        rec_status=RecordStatus.RECORDING.value,
        url=record_url,
        m3u8=m3u8_url,
        bitrate=bitrate,
        resolution=resolution
    )
    tg_bot(tg_chat_id, tg_token, msg)
```

---

## 🔍 验收检查清单

使用以下命令验证模块是否正确集成：

### 1. 日志系统验证

```bash
grep -r "\[DLR\]\[M3U8\]" logs/
grep -r "REFRESH_EVERY_5M" logs/
grep -r "FETCH_START" logs/
```

### 2. M3U8 管理器验证

```bash
ls logs/BJ-live-m3u8-*.log
grep "FALLBACK_TO_PREV_M3U8" logs/BJ-live-m3u8-*.log
```

### 3. Cookie 清洗验证

```bash
grep "SOOP_SANITIZE_APPLIED" logs/*.log
```

### 4. Telegram 模板验证

```bash
grep "TEMPLATE_APPLIED" logs/*.log
grep "📺 \*.*Live Notification\*" logs/*.log
```

### 5. QoS 选择验证

```bash
grep "SELECT_HIGHEST_BITRATE" logs/*.log
grep "SWITCH_VARIANT_IF_BETTER" logs/*.log
```

---

## 📊 性能优化建议

### M3U8 刷新间隔

根据网络情况调整刷新间隔：

```ini
[general]
refresh_interval_secs = 300  ; 稳定网络：5分钟
# refresh_interval_secs = 180  ; 不稳定网络：3分钟
# refresh_interval_secs = 600  ; 节省流量：10分钟
```

### Cookie 清洗开关

如果 SOOP Cookie 没有问题，可以跳过清洗以提升性能：

```ini
[platform]
soop_cookie_fix = true  ; 开启清洗
# soop_cookie_fix = false  ; 关闭清洗（如果Cookie正常）
```

### QoS 切换阈值

调整码率切换的敏感度：

```ini
[features]
min_switch_improve_kbps = 500  ; 默认：500kbps改善才切换
# min_switch_improve_kbps = 1000  ; 保守：1000kbps改善才切换
# min_switch_improve_kbps = 200  ; 激进：200kbps改善就切换
```

---

## 🐛 已知问题和解决方案

### 1. PyExecJS 安装失败

**问题**: `PyExecJS` 在某些环境下无法通过 pip 安装

**解决方案**:
```bash
# 方案 1: 使用 conda
conda install -c conda-forge pyexecjs

# 方案 2: 手动安装 Node.js（PyExecJS 需要）
sudo apt install nodejs  # Ubuntu/Debian
brew install node        # macOS
```

### 2. FFmpeg 路径问题

**问题**: FFmpeg 未在 PATH 中

**解决方案**:
在 `config.ini` 中指定 FFmpeg 路径：
```ini
[ffmpeg]
bin = /usr/local/bin/ffmpeg  ; Linux/macOS
# bin = C:\ffmpeg\bin\ffmpeg.exe  ; Windows
```

### 3. SOOP Cookie 失效

**问题**: Cookie 过期或无效

**解决方案**:
1. 使用依赖检查器清洗 Cookie
2. 重新登录 SOOP 获取新 Cookie
3. 启用自动登录功能（需要配置账号密码）

---

## 📞 支持和反馈

如果在使用过程中遇到问题或有改进建议：

1. 检查日志文件中的 `[DLR]` 标签
2. 搜索关键锚点（如 `FETCH_START`, `FALLBACK_TO_PREV_M3U8`）
3. 查看错误详情（`[DLR][ERR]` 标签）
4. 使用 `grep` 快速定位问题：
   ```bash
   grep -r "\[DLR\]\[ERR\]" logs/
   grep -r "\[DLR\]\[PANDA\]" logs/
   grep -r "\[DLR\]\[SOOP\]" logs/
   ```

---

## 🎉 总结

本次模块化改造为 DouyinLiveRecorder 带来了：

✅ **6 个核心模块** - 统一日志、M3U8 管理、Cookie 管理、Telegram 增强、QoS 选择、依赖检查
✅ **完整的标签体系** - `[DLR][MODULE][PLATFORM]` 格式
✅ **特色平台优化** - PandaLive 和 SOOP 专项改进
✅ **付费房回退策略** - 自动处理 needCoinPurchase/needUnlimitItem 错误
✅ **智能质量选择** - 避免 720p>1080p 误选
✅ **增强的 Telegram 推送** - 状态颜色、模板化消息
✅ **韩文错误友好化** - 详细的错误追踪和翻译

所有模块已经过测试，可以直接集成到现有代码中！

---

**创建者**: Claude Code
**日期**: 2025-11-05
**版本**: v1.0
