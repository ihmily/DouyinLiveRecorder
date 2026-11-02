# 三类钉定边界与来源增删

> **约束事实源**: dlr-dev-playbook `references/known-pitfalls.md`「构建产物、依赖与运行时基线」下的
> 「发布链运行时二进制必须 fail-closed 钉定」及「三类钉定/校验互不覆盖」。
> 约束变更以 AGENTS.md 为准。

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
4. [2026-11-01] 在线来源层 `build_exe._PIN_SOURCE_TABLE` 为**第四处**：新增/更换下载源须同批登记或
   退役清单条目——清单 URL（过 `_pin_source_url_allowed` 的 https+主机白名单运行时门）、`trust` 档、
   advisory 槽的 `ADVISORY_ADOPT_ACK` 放行标记（逐槽显式登记，不得全局开关）、月末解析档的
   `asset_glob`（回退直链 basename 必须落在 glob 内，见 pin-linux-endpoints）。
- 归档内部层级一律经 `_extract_linux_ffmpeg_binaries()` 递归按名取件，**不得**写死 `bin/` 或平铺。
- 缺件必须 `SystemExit` 而非 `return False`。

## TOFU 基线（运行期自动安装）

- `src/ffmpeg_install.py` / `src/node_install.py` 首次安装先取上游官方公布哈希文档验。
- TOFU 退化为取不到时的显式降级并记 warning，不得反过来。
- Windows 运行期只有 gyan.dev 一条自动路径，蓝奏云兜底源已整体删除。
