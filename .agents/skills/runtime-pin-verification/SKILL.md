---
name: runtime-pin-verification
description: >
  DouyinLiveRecorder 项目中运行时二进制（ffmpeg/node）钉定与完整性验证的硬约束。
  当修改 build_exe.py 的钉定哈希、新增/删除下载源、修改 check_runtime_pins.py、
  或涉及发布链运行时二进制获取时使用此 Skill。
  触发词：_PINNED_RUNTIME_SHA256、--require-pinned、check_runtime_pins、
  ffmpeg 下载、node 下载、TOFU、GPG 验签、_is_pinned、_slot_is_gated、
  DLR_RUNTIME_SHA256、releases/tags。
---

# 运行时钉定验证

> **约束事实源**: `AGENTS.md`「已知坑 → 构建产物、依赖与运行时基线」下的
> 「发布链运行时二进制必须 fail-closed 钉定」及「三类钉定/校验互不覆盖」。
> 本 Skill 提取高频复用内容供按需加载；约束变更以 AGENTS.md 为准。

## 何时加载

- 修改 `build_exe.py` 的 `_PINNED_RUNTIME_SHA256` / `_FFMPEG_DOWNLOAD_URLS` /
  `_is_pinned()` / `_slot_is_gated()` / `--require-pinned`。
- 修改 `scripts/check_runtime_pins.py`。
- 新增/删除/替换 ffmpeg 或 node 的下载源。
- 修改 `src/ffmpeg_install.py` / `src/node_install.py` 的 TOFU 逻辑。
- 涉及发布链中运行时二进制的获取、校验、分发。

## 三层防线（发布期运行时二进制，SEV-10）

### 第一层：钉定哈希

- `build_exe.py` 的 `_PINNED_RUNTIME_SHA256`（按 `<os>-<arch>` 分列，槽位 ffmpeg/node）。
- 「已钉定」唯一判据是 `_is_pinned()` 形状：**64 位小写十六进制**。
- 占位/空串/截断一律未钉定。
- **不得为让 CI 绿回填本地自算哈希**（那是固化「构建机已中毒」）。

### 第二层：强制校验门

- `--require-pinned`（CI 因 `GITHUB_ACTIONS=true` 自动开）。
- 缺钉定即在下载前 `SystemExit`（继承 `BaseException` 吞不掉）。
- `slot` 是必填关键字参数（漏传会静默降级为无校验下载）。

### 第三层：静态校验脚本

- `scripts/check_runtime_pins.py`（`--strict` 由 build-release.yml prepare job 执行）。
- 表为空/缺平台/缺槽位一律 rc=2。
- 「算满足」两档的唯一口径是 `build_exe._slot_is_gated()`：
  - 64 位十六进制官方哈希；或
  - **官方签名档**（取值 = `OFFICIAL_SIGNATURE_PIN`，且该槽在 `_RUNTIME_GPG_SIGNATURES` 确有登记、指纹为 40 位十六进制）。
  - **标记本身绝不构成放行**。

## 官方签名档

- 属第一层内部的第二种满足方式，**不是新增一个面**。
- 该槽没有公布哈希时验签即**唯一判据**。
- 验签调用点**不得**留在「哈希已过」的分支里（否则该档在真实构建路径上永不可达）。
- 回归锁：`tests/test_build_exe.py::test_signature_mode_slot_downloads_and_actually_verifies`。
- macOS 两槽 ffmpeg 走官方签名档（evermeet 不公布哈希，验签即该槽唯一判据）。

## Linux 取数端点约束

- **必须是 `releases/tags/<月末 autobuild 标签>`，不得用 `releases/latest` 或日更 autobuild 标签**。
- `latest` 是滚动别名（同名资产被上游重发即换 digest）。
- 日更标签上游只保留约两周（钉它等于预埋一次 404）。
- 月末标签才是 URL 与 digest 双双不可变的组合。
- 回归锁：`tests/test_build_exe.py::test_linux_ffmpeg_urls_pin_an_immutable_release_tag`。

## 三类钉定/校验互不覆盖

| 类别 | 范围 | 事实源 |
| --- | --- | --- |
| ① 发布期运行时二进制 | `build_exe._PINNED_RUNTIME_SHA256` + `--require-pinned` | 含官方签名档（① 内部第二种方式） |
| ② 运行期自动安装 | `src/ffmpeg_install.py` / `src/node_install.py` 的 TOFU 基线 | 首次安装取上游官方公布哈希文档验 |
| ③ 签名脚本层 | `src/javascript/*.js` 与远程 `mgprtcl.wasm` | `src/utils.py::_JS_SHA256_EXPECTED` |

- 第 4 类 `SOURCE_BUILD_PROVENANCE` 仅用于 CI 自源码构建、上游本无公布值的产物。
- 任何新增「远程获取并在子进程/本进程内执行的代码」都必须落进上述三类之一。

## 发布面 ffmpeg 来源增删（三处同改）

1. `build_exe._FFMPEG_DOWNLOAD_URLS`（按运行时键一条，与 `_PINNED_RUNTIME_SHA256` 键同构）。
2. 该键的钉定取值或签名档标记。
3. `tests/test_build_exe.py::_ALLOWED_HOSTS` 主机白名单。
   - 退役的主机要**移出**清单。
- 归档内部层级一律经 `_extract_linux_ffmpeg_binaries()` 递归按名取件，**不得**写死 `bin/` 或平铺。
- 缺件必须 `SystemExit` 而非 `return False`。

## TOFU 基线（运行期自动安装）

- `src/ffmpeg_install.py` / `src/node_install.py` 首次安装先取上游官方公布哈希文档验。
- TOFU 退化为取不到时的显式降级并记 warning，不得反过来。
- Windows 运行期只有 gyan.dev 一条自动路径，蓝奏云兜底源已整体删除。

## 验证清单

1. `python scripts/check_runtime_pins.py --strict` — rc=0
2. `pytest tests/test_build_exe.py` — 全绿（钉定/签名/主机白名单/不可变标签）
3. `pytest tests/test_ffmpeg_install.py` — 全绿（TOFU/下载源白名单）
4. `grep -n "_ALLOWED_HOSTS" tests/test_build_exe.py` — 确认退役主机已移出
5. `grep -n "releases/latest" tests/test_build_exe.py` — 确认无 `/releases/download/latest/`
