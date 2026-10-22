# 故障文档：pytest 收尾崩溃被误报为「GUI 启动失败」（2026-09-23）

## 1. 问题概述

- **现象**：Windows 上弹出标题为「GUI 启动失败」的错误框，正文是一段 pytest 内部堆栈，末行
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa1 in position 486: invalid start byte`。
- **实质**：**没有任何 GUI 启动失败**。故障体是一次 `python -m pytest` 会话在**收尾停机**时抛出的
  未捕获异常；弹窗只是 `gui.py` 的进程级崩溃兜底把别人的异常按「GUI 启动」名义报了出来。
- **失败点**：pytest 会话全局 fd 捕获停机 → 读捕获临时文件 → 严格 UTF-8 解码失败 →
  `ExitStack.close()` 里重抛 → 一路穿出 `pytest_cmdline_main` → 进程级 `sys.excepthook`。
- **影响面**：本地（中文 Windows / cp936）门禁与全量 `pytest` 可能**整轮无结论**；更隐蔽的是它会先把
  某个**无关用例**判成 `FAILED` + `ERROR`，把排查引向被测代码。CI 在 ubuntu 上不复现。

## 2. 排查时间线

| 时间 | 动作 | 结论 |
| --- | --- | --- |
| 23:29 | 读取 `%TEMP%\douyin_recorder_gui_error.log` | 拿到堆栈**完整版**：入口是 `pytest/__main__.py:9 → _console_main:253`，即 `python -m pytest` 进程 |
| +5min | 比对 `.venv` 内 pytest 9.1.1 的 `capture.py` 行号 | 778/659/707/592 四个帧与安装版本逐字吻合，确认崩溃进程用的就是本机 `.venv` |
| +8min | 读 `FDCaptureBase.__init__` | 捕获包装器是 `EncodedFile(..., encoding="utf-8", errors="replace")`——**按此构造不可能抛解码错** |
| +12min | 探针 1：向 fd 2 写 GBK 后 `FDCapture.snap()` | `snap -> '����GBK'`，**不抛**。证明「能抛」必是运行期被改过 |
| +18min | 全仓搜 `reconfigure` / `TextIOWrapper` | 5 处显式带 `errors="replace"`；**2 处裸调**：`build_exe.py:1280`、`scripts/compile_po.py:136-137` |
| +22min | 探针 2：裸 `reconfigure(encoding="utf-8")` → `snap()` | `errors: replace → strict`，随后 `SNAP RAISED UnicodeDecodeError`；带 `errors="replace"` 的对照组**正常** |
| +30min | 查 `compile_po.py` 守卫 | 守卫条件是「编码不是 utf-8 才重配」，pytest 捕获下编码已是 utf-8 → **跳过**，排除 |
| +34min | 查 `tests/test_build_exe.py` | 544/558/570 三处在**进程内**调 `build_exe.main()` → 首句即 `_ensure_utf8_streams()` |
| +40min | 探针 3：测试内读 `capturemanager._global_capturing` | BEFORE `out/err.errors=replace` → 调用后 **AFTER 两者均 strict**（直接改写 pytest 对象） |
| +45min | 端到端复现（翻转 + fd 2 写 GBK） | 堆栈与截图**逐帧一致**（`wrap_session:372 → … → capture.py:592 → codecs:325`） |

## 3. 根因

### 3.1 症状层（为什么弹窗长这样）

- `gui.py:71-133` 的 `_install_crash_sink()` 在**模块导入期**（第 133 行）就无条件把
  `sys.excepthook` / `threading.excepthook` 换成自己的 `_dump`；
- `_dump` 在 `_gui_main_window_ready == False` 时弹**固定标题**「GUI 启动失败」（gui.py:113）；
- `tests/test_gui_monitor.py:32` 有 `import gui`，于是**任何**收集到该文件的 pytest 进程都被装上了这个
  「GUI 风味」的兜底。pytest 的未捕获异常因此被贴上「GUI 启动失败」的标签。

### 3.2 直接触发点

`build_exe.py:1272-1282`：

```
def _ensure_utf8_streams() -> None:
    os.environ["PYTHONUTF8"] = "1"
    for s in (sys.stdout, sys.stderr):
        reconfigure = getattr(s, "reconfigure", None)
        if callable(reconfigure):
            _ = reconfigure(encoding="utf-8")        # ← 没有 errors=
```

CPython 对 `TextIOWrapper.reconfigure` 的明确规定：**只给 `encoding='utf-8'` 而不给 `errors` 时，
`errors` 被重置为 `'strict'`**（即使原值不是 strict）。在 pytest 进程内，`sys.stdout/sys.stderr`
正是 fd 捕获的 `EncodedFile`（`errors='replace'`），于是被**就地**改成 strict——这是全局、不可逆的。

触发路径：`tests/test_build_exe.py:544/558/570` → `build_exe.main()`（build_exe.py:1288 首句）→
上述函数。**与该文件测试什么无关**，只要跑过这三条用例，整个 pytest 会话的捕获器就都变成 strict。

### 3.3 深层原因（为什么以前没炸）

strict 本身只是「上了膛」。真正的撞击需要第二个条件：**fd 1/2 上出现非 UTF-8 字节**。
Python 层的写入经 `EncodedFile` 编码为 UTF-8，不会产生非法字节；能产生的是**绕过 Python 编码层**的写入——
按 cp936 落盘的子进程（继承句柄、未重定向 stderr）、冻结 exe、或 C 库/系统工具的原始写。
中文 Windows 上 0xa1 / 0xd6 都是 GBK 双字节序列的首字节。

- 本地：cp936 环境，撞上就炸；
- CI：全部 `ubuntu-latest` + UTF-8 locale，子进程写 UTF-8 → 永远撞不上，所以长期绿。

同族前科已在本仓留下痕迹：`scripts/run_gates.py:104` 注释写着「与 `build_exe._ensure_utf8_streams`
同一手法（那里已因同样原因踩过一次）」——但 `run_gates.py` 补上了 `errors="replace"`，
`build_exe.py` 这处**漏补**，成为唯一无条件裸调点。

### 3.4 症状 vs 根因的区分

| 层次 | 内容 |
| --- | --- |
| 症状 | 「GUI 启动失败」弹窗（标题与故障无关）、pytest 无结论、无关用例被判 FAILED+ERROR |
| 直接触发点 | `build_exe._ensure_utf8_streams()` 裸 `reconfigure(encoding="utf-8")` 改写 pytest 捕获器 |
| 深层原因 | ① 同款「Windows 控制台 UTF-8 补丁」在 6 处各写一份，编码与错误策略口径不统一，漏一处即全局失守；② 全局流被就地改写后没有任何断言/恢复；③ GUI 崩溃兜底在导入期无条件劫持进程级钩子并固定用「GUI 启动失败」文案 |

## 4. 方案（未实施，供决策）

### 4.1 必做（一行级）

`build_exe.py:1280` 改为 `reconfigure(encoding="utf-8", errors="replace")`，与
`gui.py:247/265`、`main.py:59/76`、`web.py:36`、`scripts/run_gates.py:110`、
`scripts/douyin_live_recorder_standalone.py:95` 六处口径统一。
建议顺带把该函数抽成公共实现（或至少加注释指向 `run_gates.py` 的同款），避免出现第 7 处裸调。

### 4.2 建议（防再次发生）

- `tests/test_build_exe.py`：把 `_ensure_utf8_streams` 与 `run_pyinstaller` 等一样打桩，或在
  `tests/conftest.py` 加 autouse fixture，断言用例前后 `sys.stdout/stderr` 的 `(encoding, errors)`
  未变——把这类「悄悄改全局流」从「收尾崩一个无关堆栈」变成「当场点名用例」。
- `gui.py`：`_install_crash_sink()` 仅在 `__name__ == "__main__"` 时劫持进程级钩子；被当作模块导入时
  只落盘不弹窗、或改用中性标题（如「未捕获异常」）并在正文注明入口模块。`_bootstrap_error_sink`
  保持现状（它服务的是真正的 GUI 启动路径）。
- 可选：`tests/conftest.py` 按既有 `os.environ.setdefault("DOUYIN_*")` 同法加
  `setdefault("PYTHONIOENCODING", "utf-8")`，减少 cp936 子进程产生的非法字节。

### 4.3 影响范围与风险

- 改动 4.1：只影响「不可编码字符的显示降级为 `?`」，与 `run_gates.py` 既有取舍一致；不掩盖异常，
  不改变门禁判定。风险极低。
- 改动 4.2（打桩）：`tests/test_build_exe.py` 不再顺带验证该函数本身，但专项覆盖在
  `tests/test_run_gates.py:262/286` 已有同款实现；若想保留覆盖，改用「保存/恢复 (encoding, errors)」
  的 fixture 而非打桩。
- 改动 4.2（gui）：被导入时不再弹窗，`pythonw gui.py` / 冻结 exe 的启动期可观测性不受影响
  （那条路径仍是 `__main__`）；仅「把 gui 当库用」的场景失去弹窗，当前仓库无此用法。
- 遗留风险：写出 0xa1 的产出方若未定位，加 `errors="replace"` 后它仍会以 `�` 出现在日志/报告里
  （可读性损失），且同类编码问题可能在其他链路（录制日志、Web 面板）复现。

### 4.4 实施记录（2026-09-24 落地）

| # | 文档条目 | 处置 | 落点 |
| --- | --- | --- | --- |
| 4.1 | 必做 | **已实施** | `build_exe.py::_ensure_utf8_streams()` → `reconfigure(encoding="utf-8", errors="replace")`，并补「为什么」注释（CPython 规定 + 与 `run_gates` 同款实现的交叉引用） |
| 4.2-1 | 测试隔离 | **已实施**（取 fixture 方案） | `tests/conftest.py` 新增 autouse 守卫 `_guard_stdio_encoding_policy`：逐用例校对并在必要时复原 `sys.stdout/stderr` 的 `(encoding, errors)`，违约即当场失败并打印前后取值；`tests/test_build_exe.py` 新增 2 条回归锁 |
| 4.2-2 | GUI 兜底 | **已实施** | `gui.py:133` 的 `_install_crash_sink()` 改为 `if __name__ == "__main__":` 条件安装；脚本入口（含冻结 exe）行为不变 |
| 4.2-3 | `PYTHONIOENCODING` 默认注入 | **未实施（刻意）** | 见下方 |

- **未采纳「把 `_ensure_utf8_streams` 打桩」**：打桩会让三条 `main()` 用例失去对真实副作用路径的覆盖，
  也掩盖再次劣化；改为「守卫 fixture（防护）+ 专项回归锁（点名）」组合。
- **未采纳 4.2-3**：它只把非法字节变成合法字节而不消除产出方，等于把症状压进静默（与本仓
  「不得用 filter/降级让门禁变绿」口径冲突），且会改变子进程 stdio 这一被测面；待 0xa1 产出方定位后
  随该产出方一并处置。
- **未执行「抽成单一公共实现」**：6 处调用点横跨根入口 / scripts / standalone（含冻结 exe 敏感路径），
  收敛收益低于改动面风险；暂以注释显式交叉引用（`build_exe` ↔ `run_gates`）保证改一侧能被另一侧发现。

## 5. 验证（本次已完成，可复做）

1. **最小复现**（已实测）：
   `FDCapture(2).start()` → `os.write(2, "中文".encode("gbk"))` →
   `sys.stderr.reconfigure(encoding="utf-8")` → `cap.snap()` 抛 `UnicodeDecodeError`；
   把 `reconfigure` 换成带 `errors="replace"` 即返回 `'����GBK'`，不抛。
2. **翻转对象确证**（已实测）：用例内取
   `config.pluginmanager.getplugin("capturemanager")._global_capturing`，调用前后对比
   `out.tmpfile.errors` / `err.tmpfile.errors`：`replace` → `strict`。
3. **端到端复现**（已实测）：在真实测试中触发翻转 + 向 fd 2 写 GBK，堆栈与故障报告逐帧一致
   （仅字节值与偏移不同）。
4. **待补的定位**（0xa1 产出方）：翻转存在的前提下跑全量，记录**第一个**被点名的用例，再对该文件
   `-s` 观察控制台乱码来源；或临时 dump `global_capturing.err.tmpfile` 的原始字节（用
   `errors="replace"` 打印）以凭上下文认出产出方。
5. **修复后门禁读数（2026-09-24）**：`tests/test_build_exe.py` 63 passed；全量 `pytest`
   **3193 passed / 10 skipped / 0 警告**（`COVERAGE_FILE` 置仓库外）；`mypy` 无参跑 Success（156 文件）；
   `basedpyright` 0 errors / 0 warnings / 0 notes；`black --check` / `isort --check-only` unchanged；
   `scripts/check_annotations.py` rc=0（平均密度 23.6%）；`scripts/run_gates.py` 8/8（含 pytest warnings
   summary 兜底）；覆盖率门禁 `pytest --cov=src` 3193 passed / 10 skipped + `scripts/check_coverage.py`
   **42/42 PASSED**（总覆盖率 83.94%）。
6. **变异验证（证明「锁得住」而非「恰好绿」）**：把 `errors="replace"` 临时退回旧写法后立刻三条红——
   ① `test_ensure_utf8_streams_keeps_replace_error_policy`：`('replace','replace') -> ('strict','strict')`；
   ② `test_ensure_utf8_streams_passes_explicit_errors_replace`：`[{'encoding': 'utf-8'}, …]`；
   ③ 守卫 fixture 在 teardown 同步点名
   `sys.stdout: ('utf-8','replace') -> ('utf-8','strict')；sys.stderr: …`。恢复后全绿。

## 6. 经验教训

- **`reconfigure(encoding="utf-8")` 必须显式带 `errors`**，否则等于把错误处理器从 `replace` /
  `backslashreplace` 静默改成 `strict`。本仓已有 6 处正确写法，说明这是「重复实现导致的口径漂移」，
  不是知识缺口——收敛成单一实现才是根治。
- **测试进程里的全局对象不只属于测试**：`sys.stdout/stderr`、`sys.excepthook` 在 pytest 进程内是
  框架资产。用「生产代码打印/兜底」的写法在测试进程内运行，等于同时改了框架状态与自身行为。
- **共享 append 日志必须按「最后一条 = 本次」读**：`%TEMP%\douyin_recorder_gui_error.log` 会残留
  同日更早、甚至来自另一份工作副本（`D:\DouyinLiveRecorder`）的记录，本次就混着 7 条已过期的
  `_danmaku_tail_loop` 线程异常。
- **环境相关缺陷要用「CI 与本地差异」反推**：ci.yml 九个 job 全是 `ubuntu-latest`，UTF-8 locale
  天然不产生非法字节——这既是「长期绿」的原因，也是定位时的第一层线索。
- 堆栈里的 venv 路径别当成幻觉：`%TEMP%` 里机器写出的原文本（`.venv`）比弹窗渲染字体（点号几乎不可见）
  更可信。

## 7. 参考

- `build_exe.py:1272-1288`（裸 `reconfigure` 与调用点）、`tests/test_build_exe.py:544/558/570`
- `gui.py:71-133`（导入期 crash sink）、`gui.py:113` 与 `gui.py:3835`（「GUI 启动失败」文案）、
  `tests/test_gui_monitor.py:32`
- `scripts/run_gates.py:92-113`（同款实现 + 前科注释）、`scripts/compile_po.py:128-139`（带守卫的版本）
- `.venv/Lib/site-packages/_pytest/capture.py:495/592/659/707/778`、
  `.venv/Lib/site-packages/_pytest/main.py:359-373`、`_pytest/config/__init__.py:1217/229/253`
- CPython 文档 `io.TextIOWrapper.reconfigure`（`encoding='utf-8'` 未给 `errors` ⇒ `errors='strict'`）
- `%TEMP%\douyin_recorder_gui_error.log`（本次故障的完整堆栈实体）
