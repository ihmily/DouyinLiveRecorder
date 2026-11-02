# `-reconnect*` 与 `-thread_queue_size` 位置约束

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「ffmpeg 命令构造与容器格式」。
> 约束变更以 AGENTS.md 为准。

## `-reconnect*` 硬约束

- **位置**: 必须在 `-i` **之前**，且每个选项紧跟取值。
  - 写在 `-i` 之后 → 被划入输出组 → ffmpeg 静默接受但不应用 → 重连完全失效。
- **HLS 输入必须移除 `-reconnect_at_eof`**:
  - `if ".m3u8" in url: del`
  - m3u8 播放列表 HTTP 响应结束即 EOF，该选项让 http 层无限重连，hls demuxer 永远等不到媒体段。
  - main.py 与 standalone 共三处定义点同步。
- **回归锁**: `tests/test_ffmpeg_reconnect_args.py`
  - AST 锁「每 `-reconnect*` 紧跟字面量值」+「全在 `-i` 之前」。
  - `TestReconnectAtEofDroppedForHls`。

## `-thread_queue_size` 位置约束

- **只能位于 `-i` 之后**（2026-09-23 事故）。
- 放错侧 → `Option thread_queue_size ... cannot be applied to input url` → 退出码 -22 → 录制 100% 失败。
- 回归锁：`tests/test_ffmpeg_reconnect_args.py::TestOutputOnlyOptionsFollowInputFlag`。

## 新增 per-file 选项的判据

新增任何 per-file 选项前先用 `ffmpeg -h full` 分段标题确认归属（input 级 vs output 级）。
