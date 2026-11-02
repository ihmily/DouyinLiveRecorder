# `-segment_format` 查表与容器格式约束

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「ffmpeg 命令构造与容器格式」。
> 约束变更以 AGENTS.md 为准。

## `-segment_format` 查表约束

- **必须经 `SEGMENT_FORMAT_BY_SUFFIX` 查表**，禁止任何分支直接写字面量。
- 映射：`.ts→mpegts` / `.flv→flv` / `.mkv→matroska` / `.mp4→mp4` / `.m4a→ipod`。
- 音频兜底：`SEGMENT_FORMAT_BY_SUFFIX.get("." + extension, "ipod")`。
- 历史事故：TS 分支误写 `ipod` → HEVC `-c copy` 进 `ipod` 直接 `AVERROR(EINVAL)` 退出；
  H.264 不报错 exit 0 但把 MP4 内容写进 `.ts`（魔数 ftyp 非 0x47）静默损坏。
- **回归锁**: `tests/test_record_container.py`
  - 映射表内容 + AST 扫描「5 处取值全查表、无裸字面量」+ 查表键已注册 + 音频兜底 ipod。
