# 关键约定详情（#3–#16）

> 大部分约定按需查阅。`AGENTS.md` 根文件保留 #1（版本号）、#2（行宽）、#7（排除目录）摘要。
> 唯一事实源仍是 `AGENTS.md`。

---

3. **导入排序**: isort `black` profile，`known_first_party = ["src", "i18n"]`。
4. **运行时资源**: `config/`/`ffmpeg/`/`node/` 与 exe 同级，不进入 `_internal/`。
5. **JS 签名脚本**: 位于 `src/javascript/`，通过 `__file__` 定位，打包收入 `_internal/`。
6. **编码与注释风格**: 源文件 UTF-8、注释中文；注释统一 `#`（见「注释约定」），禁止 docstring（多行字符串字面量如 `SPEC_TEMPLATE` 合法保留）。
8. **停止录制流程日志归档**: 四个运行日志（`logs/streamget.log`/`PlayURL.log`/`danmaku_monitor.jsonl`/`web_console.log`）在停止录制时经 `src/log_archive.py::archive_runtime_logs` 改名归档。触发点两处：Web「停止录制」、进程退出 atexit。硬约束：Windows 句柄未关 rename 必抛 PermissionError，改名前须先关句柄。回归锁：`tests/test_log_archive.py`+`tests/test_web_api.py::TestRecordingToggle`。
9. **布尔配置项统一解析口径**: 一律走 `src/config_bool.py::parse_config_bool` + `src/config_io.py::read_config_bool`。识别集合：是/否、true/false、t/f、yes/no、y/n、on/off、1/0。回归锁：`tests/test_config_bool.py`+`tests/frontend/test_quality_ui.mjs`。
10. **出站下载源必须登记进可机检白名单**: 新出站下载点必须同时登记进 `tests/test_ffmpeg_install.py` 的 `DOWNLOAD_SOURCES` 与 `DOWNLOAD_MODULES`。TOFU 的源必须默认关闭。
11. **camelCase 凭据键必须同步脱敏表**: `utils._SECRET_KEYS` 新接入 camelCase 凭据参数必须同步该表并在 `TestMaskCredentialsCoverage` 增加值消失断言。
12. **修复类注释必须附可复核判据**: 注释写「回归锁：`tests/…::test_xxx`」时该用例必须真实存在且能因该修复被破坏而变红。
13. **跨模块字符串契约不得靠自然语言子串**: 比较对象一律取 `i18n.tr(...)` 后形态，不得直接拿简中常量。
14. **i18n 扫描盲区清单**: `scripts/extract_i18n_strings.py` 扫不到 ①`color_obj.print_colored(...)` ②`messagebox.show*` ③**推送正文**——三类新增用户可见文案必须手工补进四目录。盲区④⑤已有机检。
15. **启动期陈旧字节码缓存清理只在白名单根内、判定必须用源码内容哈希**: `src/startup_cleanup.py` 扫描根只有「程序目录顶层 + `src/` 下直接含 `.py` 的目录」。判定基线为 `sha256(相对路径 + 文件字节)`，**不得**退化为 `(size, mtime)`。
16. **界面语言接线**: 静态标签一律经 `src/ui_i18n.T()`；窗口标题走 `apply_title`；事件时文案在产生点 `i18n.tr()`。语言切换必须整窗回填。**不得翻译**：配置键名/节名、正则、稳定机器码 detail、安全黑名单。
