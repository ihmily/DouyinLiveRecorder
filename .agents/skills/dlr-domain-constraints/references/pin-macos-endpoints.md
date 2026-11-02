# macOS 取数端点约束

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「构建产物、依赖与运行时基线」下的
> 「发布链运行时二进制必须 fail-closed 钉定」。约束变更以 AGENTS.md 为准。

## macOS 取数端点约束

- **必须是 evermeet 页面上的版本化直链**（`ffmpeg-<ver>.zip`、`ffprobe-<ver>.zip`），签名按**同名追加 `.sig`** 取（`ffmpeg-<ver>.zip.sig`）。
- **不得用 `getrelease/…` Download API**（含其 `…/zip/sig` 形态）：上游已于 2026-10-18 以「exorbitant abuse」为由整体 410 下架，页面原文 `This endpoint has been removed due to exorbitant abuse`。读数与取数命令见 `docs/agent-reference/measured-evidence.md`「2026-10-18 复测 · evermeet macOS 取数端点整体下架」。
- 旧形态还是**滚动别名**：签名只钉得住「谁签的」，钉不住「哪个版本」；改版本化直链后 URL 与签名对象双双不可变，代价与 Linux 月末标签同构——上游发新版不自动跟进，抬版要人工同步两支归档的版本号并重核指纹。
- 签名 URL 与产物 URL 的同构关系（`sig == artifact + ".sig"`）由 `tests/test_build_exe.py::test_gpg_config_shape_and_source_consistency` 机检；端点形态与「两支归档版本一致 / 两架构逐槽相等」由 `…::test_macos_ffmpeg_urls_point_at_immutable_artifacts` 机检。
- 该源站对高频取数返回 **429**（本机实测），而 `_download_file` 无重试：429 的错误体会被原样写成归档，此时签名档分支拿非 zip 数据去验签 → `_hard_fail` 终止，**不会**静默出包。**不得**为绕过 429 改成「下载失败即跳过验签」。
