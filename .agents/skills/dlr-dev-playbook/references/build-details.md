# 打包与冒烟测试详情

> 打包（`build_exe.py`）或查产物体积时才需要读本节。
> 唯一事实源仍是 `AGENTS.md`；本文件展开详细背景。

## 打包与冒烟测试语义（build_exe.py）

- 打包入口一次产出 CLI / GUI / Web 三个 exe + 共享 `_internal/`（`.github/workflows/build-release.yml` 的 build job 逐平台跑 `--smoke`；平台数与 runner 标签以 ci-workflow.md 的「发布矩阵为四平台」条目为唯一事实源）。
- 冒烟判定：`FATAL_MARKERS = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError")`；`_finish()` 仅当进程已退出且输出含 FATAL_MARKERS 才判失败（进程存活时 Traceback 视为良性）；GUI 冒烟用 `ignore_patterns=("Failed to dock icon",)` 忽略 headless 良性堆栈。

## 产物体积门禁（2026-09-24 定稿）

- **度量侧唯一入口**: `python scripts/report_bundle_size.py dist/DouyinLiveRecorder`（`--top N`/`--json F`/`--compare F`/`--strict`）。体积结论**只以本机实跑为准**，不估算。
- **排除侧唯一入口**: `build_exe.py` 的 `BLOAT_EXCLUDES` 由 `SPEC_TEMPLATE` 生成 `excludes_bloat` 挂在**三个** Analysis 上（必须三处都挂，否则合并去重后等于没排）。新增排除项准入：① 指出运行期不可达；② 复测体积；③ 本地 `--smoke --no-runtime` 三入口通过。判据是「不可达」不是「看着没用」。
- **已知体积大头（固定成本，不可删）**: `python314.dll`、`libcrypto`/`libssl`（HTTPS）、Tcl/Tk（GUI）三项一律按固定成本对待。逐文件 MB 读数见 [体积读数]；新合计须本机复测后填写。
- **已评估未采纳（勿重复提议）**: ① `strip=True`——Windows 无 strip 可执行文件；② `upx=True`——提高杀软误报率，本产物未签名。

[体积读数]: docs/agent-reference/measured-evidence.md#产物体积大头读数
