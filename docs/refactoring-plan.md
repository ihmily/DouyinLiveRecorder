# 录制管理重构计划

## 状态: ✅ 已完成 (2025-12-16)

## 目标

1. ✅ **实时分段处理**: 每个分段文件创建时立即处理（写入数据库、上传OSS），而非等待 FFmpeg 退出
2. ✅ **优雅退出**: SIGINT (Ctrl+C) 触发优雅退出，统一"录制结束"逻辑
3. ✅ **日志统一**: 所有 print 替换为 loguru logger

---

## 新架构设计

### 核心组件

```
┌─────────────────────────────────────────────────────────────┐
│                        main.py                               │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  SignalHandler  │    │      start_record()          │    │
│  │  - SIGINT/TERM  │    │  - 启动 FFmpeg              │    │
│  │  - 设置退出标志  │    │  - 创建 SegmentWatcher      │    │
│  │  - 通知所有录制  │    │  - 等待录制结束             │    │
│  └─────────────────┘    └──────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   src/storage/                               │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │ SegmentWatcher  │───▶│    RecordingManager          │    │
│  │ - 监控目录      │    │  - start_session()           │    │
│  │ - 检测新分段    │    │  - on_segment_created()      │    │
│  │ - 实时回调      │    │  - end_session()             │    │
│  └─────────────────┘    └──────────────────────────────┘    │
│                              │                               │
│                              ▼                               │
│                    ┌──────────────────┐                     │
│                    │   UploadWorker   │                     │
│                    │  - 后台上传队列   │                     │
│                    │  - 自动重试       │                     │
│                    └──────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
```

### SegmentWatcher 设计

```python
class SegmentWatcher:
    """实时监控分段文件创建"""

    def __init__(
        self,
        watch_dir: str,              # 监控目录
        filename_prefix: str,        # 文件名前缀 (anchor_name_date)
        file_extension: str,         # 文件扩展名 (.ts/.mp4)
        on_segment_created: Callable,  # 新分段回调
        poll_interval: float = 1.0   # 轮询间隔
    ):
        self._known_segments: set[str] = set()
        self._watcher_thread: Thread
        self._stop_event: Event

    def start(self) -> None:
        """启动监控线程"""

    def stop(self) -> None:
        """停止监控，返回最终分段列表"""

    def get_segments(self) -> list[str]:
        """获取所有已发现的分段"""
```

### 信号处理设计

```python
# 全局录制会话追踪
active_recordings: dict[str, RecordingContext] = {}

class RecordingContext:
    """单次录制的上下文"""
    session_id: int
    process: subprocess.Popen
    watcher: SegmentWatcher
    record_name: str

def graceful_shutdown(signum, frame):
    """优雅退出处理"""
    global exit_recording
    logger.info("收到退出信号，正在优雅退出...")
    exit_recording = True

    # 通知所有录制停止
    for ctx in active_recordings.values():
        if ctx.process.poll() is None:
            ctx.process.send_signal(signal.SIGINT)

    # 等待所有录制完成
    for ctx in active_recordings.values():
        ctx.process.wait(timeout=10)
        ctx.watcher.stop()

    # 等待上传队列清空
    if recording_manager:
        recording_manager.stop()
```

### 会话生命周期

```
录制开始
    │
    ├─ session_id = manager.start_session(anchor, platform, url)
    ├─ watcher = SegmentWatcher(dir, prefix, ext, callback)
    ├─ watcher.start()
    ├─ process = Popen(ffmpeg_command)
    │
    ▼
录制进行中 (循环)
    │
    ├─ SegmentWatcher 检测到新分段 _000.ts
    │   └─ callback: manager.on_segment_created(session_id, path, index=0)
    │       └─ 写入数据库 + 加入上传队列
    │
    ├─ SegmentWatcher 检测到新分段 _001.ts
    │   └─ callback: manager.on_segment_created(session_id, path, index=1)
    │
    ├─ ... 继续 ...
    │
    ▼
录制结束 (FFmpeg 退出 或 SIGINT)
    │
    ├─ watcher.stop()
    ├─ manager.end_session(session_id, segment_count)
    └─ 清理 active_recordings
```

---

## 实现步骤

### Phase 1: SegmentWatcher 模块 ✅
1. ✅ 创建 `src/storage/segment_watcher.py`
2. ✅ 实现目录轮询逻辑
3. ✅ 实现分段检测和回调

### Phase 2: RecordingManager 重构 ✅
1. ✅ 添加 `on_segment_created()` 方法（实时处理）
2. ✅ 修改 `start_session()` 支持预创建会话
3. ✅ 确保 `end_session()` 正确更新状态

### Phase 3: 信号处理重构 ✅
1. ✅ 注册 SIGINT 和 SIGTERM 处理器
2. ✅ 实现 `graceful_shutdown()`
3. ✅ 添加 `active_recordings` 追踪

### Phase 4: check_subprocess 重构 ✅
1. ✅ 创建 SegmentWatcher 而非等待结束后扫描
2. ✅ 启动时调用 `start_session()`
3. ✅ 结束时调用 `end_session()`
4. ✅ 移除结束后的分段扫描逻辑

### Phase 5: print 替换 ✅
1. ✅ 导入 logger
2. ✅ 替换所有 print() 为 logger.info/debug/warning/error
3. ✅ 替换所有 color_obj.print_colored() 为 logger

---

## 关键代码位置

| 文件 | 行号 | 修改内容 |
|------|------|----------|
| src/storage/segment_watcher.py | 新建 | SegmentWatcher 类 |
| src/storage/manager.py | 218-284 | 添加 on_segment_created() |
| src/storage/repository.py | 57-62 | 添加 update_session_segment_count() |
| main.py | 86-128 | graceful_shutdown() 信号处理 |
| main.py | 130-145 | RecordingContext 数据类 |
| main.py | 520-640 | 重构 check_subprocess() |
| main.py | 全文 | print/color_obj.print_colored → logger |

---

## 完成总结

### 新增文件
- `src/storage/segment_watcher.py` - 实时监控分段文件创建的 SegmentWatcher 类

### 修改文件
- `main.py` - 重构信号处理、check_subprocess、日志输出
- `src/storage/manager.py` - 添加 on_segment_created() 实时分段处理
- `src/storage/repository.py` - 添加 update_session_segment_count()
- `src/storage/__init__.py` - 导出 SegmentWatcher 和 SegmentInfo

### 关键变更
1. **SegmentWatcher**: 使用目录轮询实时检测新分段文件，通过回调触发数据库写入和 OSS 上传
2. **RecordingContext**: 数据类追踪活动录制会话，支持优雅退出时清理
3. **graceful_shutdown()**: 统一处理 SIGINT/SIGTERM，发送 SIGINT 给 FFmpeg，等待退出
4. **日志统一**: 所有 print() 和 color_obj.print_colored() 替换为 loguru logger
