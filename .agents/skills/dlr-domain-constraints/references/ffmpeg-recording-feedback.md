# 录制结果反馈（与命令构造交互部分）

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「ffmpeg 命令构造与容器格式」。
> 约束变更以 AGENTS.md 为准。

## 录制结果反馈

- `check_subprocess` 须按 ffmpeg 退出码上报调度样本：
  - `rc==0` → `record_success(host_of(record_url))`
  - `rc!=0` → `record_error(...)`
  - **禁止轮末无条件 `record_success`**——稀释按 host 熔断统计。
- 快速失败须记入探针退避（`_FFMPEG_FAST_FAIL_SECONDS=20.0`）：
  - 解析 `-i` 后实际拉流地址调 `stream_select.mark_ffmpeg_reject(url, platform)`。
  - `platform` 不在 `_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)` 时静默无行动。
- 录制成功须撤销该地址探针退避（`clear_ffmpeg_reject`）：
  - 只清实际拉流成功的 FLV，HLS 退避不顺带清。
