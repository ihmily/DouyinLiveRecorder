---
name: ffmpeg-command-construction
description: >
  DouyinLiveRecorder 项目中 ffmpeg 命令构造与容器格式的硬约束。
  当修改或新增 ffmpeg 录制命令、保存类型分支、输入/输出参数构造、
  分段格式映射时使用此 Skill。触发词：ffmpeg、-reconnect、-segment_format、
  _build_ffmpeg_output_args、_build_ffmpeg_input_args、_run_ffmpeg_record、
  record_save_type、容器格式、FLV/TS/MP4/M4A/MKV。
---

# ffmpeg 命令构造与容器格式

> **约束事实源**: `AGENTS.md`「已知坑 → ffmpeg 命令构造与容器格式」章节。
> 本 Skill 提取高频复用内容供按需加载；约束变更以 AGENTS.md 为准。

## 何时加载

- 修改 `main.py::start_record` / `_build_ffmpeg_input_args` /
  `_build_ffmpeg_output_args` / `_build_record_output_path` /
  `_run_ffmpeg_record` / `_convert_after_record` 中的任何一个。
- 新增保存类型分支或输出格式。
- 涉及 `-reconnect*`、`-thread_queue_size`、`-segment_format`、`-headers`、
  `-tls_verify`、`-http_proxy` 等 ffmpeg 选项。
- 调试 ffmpeg 退出码异常、静默损坏、重连失效。

## 四个单一定义点（F-01 收官）

禁止回退成内联复制粘贴。所有平台分支必须经过以下函数：

1. **输入侧**: `_build_ffmpeg_input_args(real_url, user_agent, tuning, headers, tls_verify, proxy_address)`
   - 所有选项按 `-i` 锚点定位或插列表头，**禁裸数字下标**。
2. **输出路径**: `_build_record_output_path(...)`
   - 扩展名 / 分段时间戳格式 / `_%03d` / `_%02d` 全查表。
3. **执行骨架**: `_run_ffmpeg_record(...)` + 录后转码 `_convert_after_record(...)`
   - 五条保存类型分支只调这三个函数，禁各自写 try/except + check_subprocess。
4. **平台分发**: `_PLATFORM_RESOLVERS`（`(匹配器, 处理函数)` 表）+ `_PlatformResolveContext`
   - 表项顺序即优先级，**禁插 elif**。

回归锁：`tests/test_platform_dispatch.py` + `tests/test_start_record_command_golden.py`。

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

## `-segment_format` 查表约束

- **必须经 `SEGMENT_FORMAT_BY_SUFFIX` 查表**，禁止任何分支直接写字面量。
- 映射：`.ts→mpegts` / `.flv→flv` / `.mkv→matroska` / `.mp4→mp4` / `.m4a→ipod`。
- 音频兜底：`SEGMENT_FORMAT_BY_SUFFIX.get("." + extension, "ipod")`。
- 历史事故：TS 分支误写 `ipod` → HEVC `-c copy` 进 `ipod` 直接 `AVERROR(EINVAL)` 退出；
  H.264 不报错 exit 0 但把 MP4 内容写进 `.ts`（魔数 ftyp 非 0x47）静默损坏。
- **回归锁**: `tests/test_record_container.py`
  - 映射表内容 + AST 扫描「5 处取值全查表、无裸字面量」+ 查表键已注册 + 音频兜底 ipod。

## 新增 per-file 选项的判据

新增任何 per-file 选项前先用 `ffmpeg -h full` 分段标题确认归属（input 级 vs output 级）。

## 黄金命令比对

- `tests/test_start_record_command_golden.py`
  - `GOLDEN_REGEN=1` 重生成 `tests/golden/start_record_commands.json`，字节级比对。
  - 20 用例覆盖 5 路径 + m3u8 丢弃 `-reconnect_at_eof` + 头/代理注入 + 海外超时 + FLV-h265→TS + shopee 直下。

## 录制结果反馈（与命令构造交互部分）

- `check_subprocess` 须按 ffmpeg 退出码上报调度样本：
  - `rc==0` → `record_success(host_of(record_url))`
  - `rc!=0` → `record_error(...)`
  - **禁止轮末无条件 `record_success`**——稀释按 host 熔断统计。
- 快速失败须记入探针退避（`_FFMPEG_FAST_FAIL_SECONDS=20.0`）：
  - 解析 `-i` 后实际拉流地址调 `stream_select.mark_ffmpeg_reject(url, platform)`。
  - `platform` 不在 `_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)` 时静默无操作。
- 录制成功须撤销该地址探针退避（`clear_ffmpeg_reject`）：
  - 只清实际拉流成功的 FLV，HLS 退避不顺带清。

## 验证

### 项目级门禁（由 `python scripts/run_gates.py` 统一兜底，Skill 不重复）

- `black --check`、`isort --check-only`、`mypy`（含 `--platform linux` / `--platform win32`）、`check_annotations.py`

### 本领域专项检查

1. `pytest tests/test_ffmpeg_reconnect_args.py` — 全绿
2. `pytest tests/test_record_container.py` — 全绿
3. `pytest tests/test_start_record_command_golden.py` — 全绿
4. `pytest tests/test_platform_dispatch.py` — 全绿
5. `pytest tests/test_record_failure_feedback.py` — 全绿
6. AST 检查：grep 确认无 `-reconnect*` 出现在 `-i` 之后、无 `-segment_format` 裸字面量
