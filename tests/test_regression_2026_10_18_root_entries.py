# tests/test_regression_2026_10_18_root_entries.py —— CODE_REVIEW_2026-10-18 两条根目录入口
# 修复的回归锁（生产实现由别的包落地，本文件只锁行为，不改任何生产代码）。
#
# 覆盖两条：
#   L-01  web.py::_cap_web_console_log —— 后台模式启动侧把超限的 logs/web_console.log
#         就地截断为末尾若干 KB（起点强制对齐整行首），失败只留痕不阻断后台化；
#   L-02  gui.py 的 PID 复用防线 —— 退出链在 `taskkill /F /T` 之前先确认「这个号码现在还是
#         我们启动的那个映像」，只在**确证不同**时收手，取不到判据一律退回原无条件形态。
#
# 全部离线：不起 Web 服务、不建真窗、不联网；产物一律 tmp_path。
# 打桩边界（AGENTS「桩的是外部副作用，不是判定本身」）：
#   · web 侧只替换两个体积阈值常量（等价于「时间常量」那类可注入阈值），截断/对齐/返回值全走真实实现；
#   · gui 侧只替换 kernel32 的「打开进程 / 读映像全名 / 关句柄」三处系统入口与 subprocess.run，
#     `_win_pid_image_name` / `_reused_pid_image_pair` / `_cleanup_zombie_ffmpeg` 的判定链全部真实执行。
#
# Windows 专属分支**没有**用 skipif：CI 全跑在 ubuntu，若 skip 则这两格回归锁会静默消失
# （AGENTS「平台专属分支的测试不得靠 skipif 让 CI 跳过」）。gui.py 未把平台判定抽成模块级
# 常量、而它不归本包改，故按仓内既有做法 monkeypatch `sys.platform`（test_test_hygiene 的 R1
# 判据表刻意不含 sys：解释器状态标志、无替代手段，tests/test_i18n.py 已用同一形态），
# 再把 `_get_gui_kernel32` 换成替身，于是 win32 分支在 Linux 上真实执行。

import ast
import importlib
import os
import subprocess
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import web

# web.py 的导入期副作用只有 _fix_encoding()（就地 reconfigure 宿主 stdio）：模块顶层导入即落在
# pytest 收集期、早于 conftest 的函数级 stdio 快照，与 tests/test_web_background_gate_order.py
# 同形态，且它不往进程环境写任何东西，因此不需要 gui 那套会话级隔离。
_GUI_PARENT_ENV = "DLR_GUI_PARENT"


@pytest.fixture(scope="session", autouse=True)
def gui() -> Iterator[ModuleType]:
    # gui.py 的模块级副作用有两条：os.environ["DLR_GUI_PARENT"]="1" 与 _fix_encoding() 的 stdio
    # 重配置。逐例（函数级夹具）导入会让后者被 conftest 的函数级 stdio 守卫判成「用例改动了宿主
    # 进程编码策略」，收集期导入又把前者永久留给整个会话 —— 故两头都躲开：会话级导入 + 导入完
    # 立刻把标记还原成进入会话前的形态（手法与理由同 tests/test_gui_language_retranslate.py 的 MT-05）。
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setenv(_GUI_PARENT_ENV, "")
        module = importlib.import_module("gui")
    yield module


# ---------------------------------------------------------------------------
# L-01：web_console.log 的启动侧大小上限
# ---------------------------------------------------------------------------


def _set_limits(monkeypatch: pytest.MonkeyPatch, *, max_bytes: int, keep_bytes: int) -> None:
    # 体积阈值常量注入小值，免得为「超限」一格真写 2 MB+ 的文件（AGENTS 允许打桩的就是这类
    # 阈值/时间常量；截断、对齐、返回值三段逻辑一律走 web.py 真实实现）
    monkeypatch.setattr(web, "_WEB_CONSOLE_MAX_BYTES", max_bytes)
    monkeypatch.setattr(web, "_WEB_CONSOLE_KEEP_BYTES", keep_bytes)


def test_cap_web_console_log_leaves_under_limit_file_untouched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 形态①：未超限 → 返回 0 且文件逐字节不动（首次后台化 / 正常轮次不得被「收拢」误伤）
    path = tmp_path / "web_console.log"
    original = b"line one\nline two\n"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=len(original), keep_bytes=4)
    assert web._cap_web_console_log(str(path)) == 0
    assert path.read_bytes() == original, "未超限时一个字节都不许动"


def test_cap_web_console_log_drops_oldest_and_starts_at_line_head(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 形态②：超限 → 丢弃字节数 = 原大小 − 余量、余量不高于 keep、留下的必须从整行首开始
    # （起点落在某行中间会留下半行：事后按行匹配的排查脚本首行读到残缺内容，
    # 且被切断的多字节 UTF-8 序列会连解码都一起坏掉）
    lines = [f"L{i:03d} 一行\n".encode() for i in range(10)]
    original = b"".join(lines)
    size = len(original)
    line_len = len(lines[0])
    # 让「保留窗口的起点」正好落在第 4 行中间（size − keep = 3×行宽 + 2），
    # 于是对齐整行首这件事有活可干：不实现对齐的话，首行就是残缺的 L003 半行
    keep_bytes = size - (3 * line_len + 2)
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=size // 2, keep_bytes=keep_bytes)

    dropped = web._cap_web_console_log(str(path))
    kept = path.read_bytes()
    assert dropped == 4 * line_len, f"起点未对齐到整行首（丢 {dropped}，应丢 {4 * line_len} = 前 4 整行）"
    assert dropped == size - len(kept), f"返回值与实删字节数不一致: 返回 {dropped} / 实删 {size - len(kept)}"
    assert len(kept) <= keep_bytes, f"余量超过 keep 上限: {len(kept)} > {keep_bytes}"
    assert kept == original[4 * line_len :], "留下的内容不是原文件的整行后缀 → 丢的不是最早的整段"
    assert kept.startswith(lines[4]), f"首行不是从整行首开始（残缺头一行会污染按行匹配）: {kept[:20]!r}"


def test_cap_web_console_log_drops_whole_block_without_newline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 形态③：保留窗口内一个换行都没有（单条超长 print）→ 整块丢弃、余量归 0，
    # 上限优先于留痕（不得为「留一行」而把半行留在文件头）
    original = b"x" * 50
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=20, keep_bytes=10)
    assert web._cap_web_console_log(str(path)) == 50
    assert path.read_bytes() == b""


def test_cap_web_console_log_missing_file_returns_zero_without_creating_it(tmp_path: Path) -> None:
    # 形态④：文件不存在（首次后台化）→ 返回 0，且**不得**顺手创建这只文件
    # （创建即把「归档链路按 .name 找句柄」的契约提前绑到一个空文件上）
    path = tmp_path / "web_console.log"
    assert not path.exists()
    assert web._cap_web_console_log(str(path)) == 0
    assert not path.exists(), "取不到大小时不得创建文件"


def test_cap_web_console_log_failure_is_reported_and_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # 截断失败绝不阻断后台化（日志继续追加也远好过面板起不来），但必须留下一条可见告警，
    # 且返回 0 让调用方不去打「已丢弃 N KB」那句结论。
    # 判据只问「有没有留痕 + 文件是否原样 + 返回值」，不钉告警文案（M-26：文案会漂，字面锁会空转）。
    original = b"y" * 50
    path = tmp_path / "web_console.log"
    path.write_bytes(original)
    _set_limits(monkeypatch, max_bytes=20, keep_bytes=10)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise OSError(13, "Permission denied")

    # raising=False：web.py 里 `open` 是内建名、不是模块全局，替身只能以「新增全局名」的形态
    # 遮蔽到内建查找之前（teardown 由 monkeypatch 直接删掉这个新增名，不留残留）
    monkeypatch.setattr(web, "open", _boom, raising=False)
    assert web._cap_web_console_log(str(path)) == 0
    assert path.read_bytes() == original, "截断失败后不得留下半截内容"
    assert capsys.readouterr().out.strip() != "", "失败必须留痕（静默即等于把故障伪装成正常）"


def test_console_log_cap_is_called_before_the_append_stream_opens() -> None:
    # 调用点契约（见 web.py::_cap_web_console_log 的注释）：截断必须早于 `open(log_path, "a")`。
    # 此刻 sys.stdout/stderr 还是真实控制台、loguru 控制台 sink 也尚未 rebind，没有任何句柄握着
    # 这只文件；挪到重定向之后，Windows 下对未关句柄的文件做截断必抛 PermissionError，
    # 而这条链路完全静默（面板照常起、日志照常无界增长），只有结构锁看得见。
    tree = ast.parse(Path(web.__file__).read_text(encoding="utf-8"), filename=str(web.__file__))
    fn = next(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_enter_background_mode"
        ),
        None,
    )
    assert fn is not None, "web.py 里找不到 _enter_background_mode，本判据失去基准（不得当成通过）"
    cap_at: int | None = None
    open_at: int | None = None
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        called = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
        if called == "_cap_web_console_log":
            cap_at = node.lineno if cap_at is None else min(cap_at, node.lineno)
        elif (
            called == "open"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "a"
        ):
            open_at = node.lineno if open_at is None else min(open_at, node.lineno)
    assert cap_at is not None, "_enter_background_mode 里没有 _cap_web_console_log 调用（上限防线被摘）"
    assert open_at is not None, "_enter_background_mode 里找不到追加流 open(..., 'a')，判据失去基准"
    assert cap_at < open_at, f"截断调用（第 {cap_at} 行）没有早于追加流打开（第 {open_at} 行）"


# ---------------------------------------------------------------------------
# L-02：GUI 退出链的 PID 复用防线
# ---------------------------------------------------------------------------

# 超出任何真实 PID 上限的号码：替身按「OpenProcess 对已消失进程回 NULL」的形态处理
_DEAD_PID = 4_000_000_001


class _FakeKernel32:
    # kernel32 的三个入口替身：映像名由 pid→完整路径表给定；表里没有的 pid 返回 NULL(0)。
    # 只替「问操作系统这个号码现在是谁」这一处外部副作用，早返回 / 空串即放行 / 基名比对
    # 全部走 gui.py 真实代码。
    def __init__(self, image_paths: dict[int, str], *, query_ok: bool = True) -> None:
        self._image_paths = image_paths
        self._query_ok = query_ok
        self.opened: list[int] = []
        self.closed = 0

    def OpenProcess(self, access: int, inherit_handle: int, pid: int) -> int:
        self.opened.append(pid)
        return pid if pid in self._image_paths else 0

    def QueryFullProcessImageNameW(self, handle: int, flags: int, buffer: Any, size: Any) -> int:
        if not self._query_ok:
            return 0
        buffer.value = self._image_paths[int(handle)]
        return 1

    def CloseHandle(self, handle: int) -> int:
        self.closed += 1
        return 1


class _FakeCompleted:
    # taskkill/pkill 的返回形态：returncode 0 + 空 stdout/stderr（按字节，非 text=）
    returncode = 0
    stdout = b""
    stderr = b""


def _own_image_name() -> str:
    # 「我们自己启动的映像」：Windows 上就是 python.exe，ubuntu CI 上是 python3.x。
    # 判据只比基名，故取 sys.executable 的基名而不是硬写 "python.exe"——
    # 硬写在 CI 上会让「①同名→放行」这格实际判成「不同名」，整格退化。
    return os.path.basename(sys.executable).lower()


def _use_win32_kernel32(gui: ModuleType, monkeypatch: pytest.MonkeyPatch, k32: _FakeKernel32) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(gui, "_get_gui_kernel32", lambda: k32)


def _kill_runs(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    # 进程级 stdlib 替身一律走被测模块命名空间的 shim（AGENTS/MID-66）：
    # 直接 setattr(subprocess, "run", ...) 会把全进程唯一的 subprocess 本体换掉。
    runs: list[list[str]] = []

    def _run(argv: Any, *args: Any, **kwargs: Any) -> _FakeCompleted:
        runs.append([str(item) for item in argv])
        return _FakeCompleted()

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = _run
    monkeypatch.setattr(gui, "subprocess", shim)
    return runs


def test_pid_guard_passes_when_own_pid_still_runs_our_image(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 格①：自身 PID + 记录的映像名就是它 → 判「未复用」→ 放行（继续原有清理，不收窄能力）
    own = os.getpid()
    k32 = _FakeKernel32({own: sys.executable})
    _use_win32_kernel32(gui, monkeypatch, k32)
    assert gui._reused_pid_image_pair(_own_image_name(), own) is None
    assert k32.opened == [own]
    assert k32.closed == 1, "读过一次就必须关掉一次句柄（退出链上每漏一只都没有道理）"


def test_pid_guard_detects_reuse_and_reports_both_names(
    gui: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 格②：号码还在、但映像名确实不是我们启动的那个 → 判复用，并把「现占用者 / 期望者」一起带回去
    own = os.getpid()
    k32 = _FakeKernel32({own: str(tmp_path / "notepad.exe")})
    _use_win32_kernel32(gui, monkeypatch, k32)
    verdict = gui._reused_pid_image_pair(_own_image_name(), own)
    assert verdict is not None, "确证被别的映像接手时必须判成复用，否则整树强杀会打到无关进程"
    current, expected = verdict
    assert current == "notepad.exe"
    assert expected == _own_image_name()
    assert k32.closed == 1


def test_pid_guard_passes_for_dead_pid(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 格③：PID 已不存在（OpenProcess 回 NULL）→ 取不到判据 → 退回原无条件形态
    # （本来就没有活对象可误杀，而 taskkill 会自己返回 128、由 MIN-2249 如实记「未能清理」）
    k32 = _FakeKernel32({os.getpid(): sys.executable})
    _use_win32_kernel32(gui, monkeypatch, k32)
    assert gui._reused_pid_image_pair(_own_image_name(), _DEAD_PID) is None
    assert k32.closed == 0, "没拿到句柄就不该有关可关（不得凭空计数）"


def test_pid_guard_passes_and_asks_nothing_when_image_not_recorded(
    gui: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 格④：从未启动过录制核心（或桩实例不跑 __init__）→ 没有期望映像名 → 不判定。
    # 替身被摆成「真去读就会读出别的映像」，以此证明这里是**短路**而不是巧合放行。
    own = os.getpid()
    k32 = _FakeKernel32({own: str(tmp_path / "notepad.exe")})
    _use_win32_kernel32(gui, monkeypatch, k32)
    assert gui._reused_pid_image_pair("", own) is None
    assert k32.opened == [], "期望名缺席时不该发起任何系统调用"


def test_pid_guard_passes_when_image_name_query_fails(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 判据⑤（「权限不足 / 读不到一律退回原形态」那条兜底）：OpenProcess 成功但
    # QueryFullProcessImageNameW 失败 → 空串 → 不判复用，且句柄照样关掉。
    own = os.getpid()
    k32 = _FakeKernel32({own: sys.executable}, query_ok=False)
    _use_win32_kernel32(gui, monkeypatch, k32)
    assert gui._reused_pid_image_pair(_own_image_name(), own) is None
    assert k32.closed == 1


def _cleanup_stub(gui: ModuleType, recorded_image: str, logs: list[tuple[str, str]]) -> Any:
    # object.__new__ 跳过 __init__（不建真窗），只注入 _cleanup_zombie_ffmpeg 触及的三个面；
    # _child_image_name 用 setattr 而非裸赋值共享属性（桩实例私有，不涉还原）
    app = object.__new__(gui.LiveRecorderGUI)
    setattr(app, "_child_image_name", recorded_image)
    setattr(app, "_log", lambda message, level="info": logs.append((str(message), level)))
    return app


def test_cleanup_skips_whole_tree_kill_when_pid_is_confirmed_reused(
    gui: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 行为侧判据：确证复用 → 一次 taskkill 都不发（`/F /T` 打的是号码，接手者及其整棵子树
    # 都可能是无关进程），且必须留下一条能归因的告警（哪个 PID、现被谁占用、期望者是谁）。
    own = os.getpid()
    k32 = _FakeKernel32({own: str(tmp_path / "notepad.exe")})
    _use_win32_kernel32(gui, monkeypatch, k32)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[tuple[str, str]] = []
    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, _own_image_name(), logs), own)

    assert runs == [], f"PID 确证已被别的映像接手，仍发出了杀进程命令: {runs}"
    warns = [(message, level) for message, level in logs if level == "warn"]
    assert len(warns) == 1, f"跳过强杀必须恰留一条告警（多于一条说明别处也在报错）: {logs}"
    message = warns[0][0]
    assert str(own) in message and "notepad" in message, f"告警必须点名 PID 与现占用映像，否则无法归因: {message}"


def test_cleanup_still_kills_whole_tree_when_image_matches(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向护栏：映像名对得上（最常见路径）→ 整树强杀照发，且一条 warn 都不该有
    # （warn 缺席同时反向证明本函数没有靠「异常被外层 except 吞掉」凑出上一格的告警）
    own = os.getpid()
    k32 = _FakeKernel32({own: sys.executable})
    _use_win32_kernel32(gui, monkeypatch, k32)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[tuple[str, str]] = []
    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, _own_image_name(), logs), own)

    assert any("/T" in argv and str(own) in argv for argv in runs), f"未复用时必须照常清理: {runs}"
    assert [level for _, level in logs if level == "warn"] == [], f"正常清理路径不应有告警: {logs}"


def test_cleanup_still_kills_whole_tree_when_nothing_recorded(
    gui: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 反向护栏：没记录过期望映像名 → 判据不介入，原有的清理能力不得被凭空收窄
    own = os.getpid()
    k32 = _FakeKernel32({own: str(tmp_path / "notepad.exe")})
    _use_win32_kernel32(gui, monkeypatch, k32)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[tuple[str, str]] = []
    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, "", logs), own)

    assert any("/T" in argv and str(own) in argv for argv in runs), f"未记录即不判定，照发清理: {runs}"
    assert k32.opened == [], "未记录时期望名缺席，判据连读映像都不该发起"
