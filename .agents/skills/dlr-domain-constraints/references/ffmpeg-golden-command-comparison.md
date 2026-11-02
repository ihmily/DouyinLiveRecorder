# 黄金命令比对

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「ffmpeg 命令构造与容器格式」。
> 约束变更以 AGENTS.md 为准。

## 黄金命令比对

- `tests/test_start_record_command_golden.py`
  - `GOLDEN_REGEN=1` 重生成 `tests/golden/start_record_commands.json`，字节级比对。
  - 20 用例覆盖 5 路径 + m3u8 丢弃 `-reconnect_at_eof` + 头/代理注入 + 海外超时 + FLV-h265→TS + shopee 直下。
