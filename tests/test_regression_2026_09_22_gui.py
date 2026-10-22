# tests/test_regression_2026_09_22_gui.py — 2026-09-22 批次（GUI / i18n / 推送）回归锁。
#
# 覆盖本轮「行为可见」修复的**失效形态**（编号见 CODE_REVIEW_2026-09-22.md 4.7 / 5.4）：
#   MID-2248  i18n.has_catalog 的判据必须是「真的装载得出非空映射」而非「文件存在」；PyYAML 缺失
#             的降级还要落一条 warning，否则用户视角是「切了繁体没生效且无提示」。
#   MID-2249  旧会话线程不得把**新会话**的 running 打成 False（自然 EOF 是三条收尾里最常走的一条，
#             此前唯独它裸写 self.running = False，竞态后永不回正且零日志）。
#   MID-2252  URL 页整文件写回前必须先读盘并与基线裁决（与高级设置窗口的 MID-55 同源）。
#   MIN-2247  messagebox 正文这类「提取器扫不到」的文案必须逐条登记，否则四语目录永远缺键。
#   MIN-2249  _cleanup_zombie_ffmpeg 判 returncode，非 0 不得记「已清理」。
#   MIN-2250  kernel32 一律 ctypes.WinDLL + 显式 argtypes/restype；恢复控制台失败须带 GetLastError。
#
# 为什么多数用例走**行为注入**而不是起真界面：LiveRecorderGUI 依赖 Tk 主循环，无头环境跑不了；
# 沿用 tests/test_danmaku_monitor.py 的 `object.__new__` 桩 + 真实方法驱动（桩只补状态字段、不重新
# 实现判定逻辑），结构性约束另以 AST 静态锁读取源码（同 test_gui_monitor.py 手法）。

import ast
import json
import pathlib
import re
import threading
import types
from typing import Any

import pytest

import i18n

ROOT = pathlib.Path(__file__).resolve().parents[1]
GUI_SOURCE = (ROOT / "gui.py").read_text(encoding="utf-8")
PENDING_GUI_JSON = ROOT / "_i18n_pending_gui.json"

gui = pytest.importorskip(
    "gui", reason="gui 导入失败时跳过 GUI 无头用例（环境限制口径；阶段5 起 gui 已不依赖 customtkinter)"
)


# 把 gui 模块里引用的 stdlib 名字换成浅拷贝替身：直接改 `gui.sys` / `gui.ctypes` 的**属性**
# 会波及全进程（AGENTS「patch stdlib 模块本体」条），换成 SimpleNamespace 后只影响 gui 模块内的查找。
def _shim(module: types.ModuleType, **overrides: Any) -> types.SimpleNamespace:
    base = {k: v for k, v in vars(module).items() if not k.startswith("__")}
    base.update(overrides)
    return types.SimpleNamespace(**base)


# 记录 gui._log 调用的桩实例（不触碰任何 Tk 对象）。
class _LogSpy:
    def __init__(self) -> None:
        self.lines: list[tuple[str, str]] = []
        self.process_pid = 4242

    def _log(self, message: str, level: str = "info") -> None:
        self.lines.append((message, level))

    def text(self) -> str:
        return "\n".join(f"[{lvl}] {msg}" for msg, lvl in self.lines)


class _RunResult:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# 抽出某文件里全部 `*.tr(常量模板)` 的模板（tr 的属性形式，如 i18n_module.tr / i18n.tr）。
def _tr_templates_from(source: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "tr"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            out.add(node.args[0].value)
    return out


# ─── MID-2249：会话过期的 EOF 不得改新会话状态 ────────────────
class TestStaleSessionCannotStopNewOne:
    def test_mark_session_stopped_only_for_current_session(self) -> None:
        # 真实方法驱动：session_id 已过期 → running 必须仍为 True（旧实现无条件置 False）。
        # running 是受 _process_lock 保护的 property，桩实例补齐这两个字段即可走真实 setter。
        stub = object.__new__(gui.LiveRecorderGUI)
        stub._session_id = 2
        stub._process_lock = threading.Lock()
        stub.running = True
        gui.LiveRecorderGUI._mark_session_stopped(stub, 1)
        assert stub.running is True, "旧会话（1）把新会话（2）的 running 打成了 False"

        # 同会话与 None（退出收尾本无「新会话」概念）两条路径必须照旧生效，不得收紧成「一律不改」。
        gui.LiveRecorderGUI._mark_session_stopped(stub, 2)
        assert stub.running is False
        stub.running = True
        gui.LiveRecorderGUI._mark_session_stopped(stub, None)
        assert stub.running is False

    def test_read_output_has_no_bare_running_assignment(self) -> None:
        # 静态锁：_read_output 的三条收尾（自然 EOF + 两个 except）必须同构地经
        # _mark_session_stopped(session_id)，体内不得再出现裸 self.running = False（自然 EOF 最常见）。
        tree = ast.parse(GUI_SOURCE)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_read_output")
        bare = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Attribute) and t.attr == "running" and isinstance(t.value, ast.Name)
                for t in node.targets
            )
        ]
        assert bare == [], f"_read_output 内仍有裸 self.running 赋值：{[b.lineno for b in bare]}"
        calls = [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_mark_session_stopped"
        ]
        assert len(calls) == 3, f"三条收尾应各有 1 次 _mark_session_stopped，实得 {len(calls)}"
        for call in calls:
            assert [ast.unparse(a) for a in call.args] == ["session_id"], "收尾必须带上会话代号，否则等于无条件置位"


# ─── MID-2248：has_catalog 判据 + PyYAML 缺失告警 ─────────────
@pytest.fixture
def restore_language_state() -> Any:
    saved = (i18n._current_language, i18n._tr, set(i18n._YAML_MISSING_WARNED))
    yield
    i18n._current_language, i18n._tr = saved[0], saved[1]
    i18n._YAML_MISSING_WARNED.clear()
    i18n._YAML_MISSING_WARNED.update(saved[2])


@pytest.mark.usefixtures("restore_language_state")
class TestCatalogMustBeLoadable:
    def test_missing_pyyaml_makes_zh_tw_have_no_catalog(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 旧判据是 (zh_TW.yaml).is_file() —— PyYAML 未装时文件在、目录装不出来，has_catalog 仍返回
        # True → _effective_language 不回退 → GUI 的「目录不可用，已回退」告警恒不触发（gui.py::
        # _on_language_change 的唯一判据就是 effective != lang_code），界面全是简中原文。
        i18n._YAML_MISSING_WARNED.clear()
        monkeypatch.setattr(i18n, "yaml", None)
        assert i18n.has_catalog("zh_TW") is False
        assert i18n.set_language("zh_TW") == i18n.FALLBACK_LANGUAGE
        assert i18n.get_language() == i18n.FALLBACK_LANGUAGE

    def test_broken_mo_also_counts_as_no_catalog(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 同一判据的第二形态：.mo 存在但损坏时 _load_mo_catalog 返回 None，
        # zh_CN 既无 .json 也无 .yaml → 必须判「无目录」，而不是装上恒等映射后对外宣称切换成功。
        monkeypatch.setattr(i18n, "_load_mo_catalog", lambda *a, **k: None)
        assert i18n.has_catalog("zh_CN") is False
        assert i18n.has_catalog("en_US") is True  # 反向护栏：不得收紧成「一律无目录」

    def test_missing_pyyaml_warns_once_per_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 该降级此前完全静默；补的 warning 必须**按路径去重**——语言判定发生在启动期与
        # main 主循环每轮热同步（≥30s 一轮），不去重会把同一条刷进日志、淹掉真实线索。
        i18n._YAML_MISSING_WARNED.clear()
        warnings: list[str] = []
        monkeypatch.setattr(i18n, "logger", types.SimpleNamespace(warning=lambda msg: warnings.append(str(msg))))
        monkeypatch.setattr(i18n, "yaml", None)
        for _ in range(3):
            assert i18n.has_catalog("zh_TW") is False
        assert len(warnings) == 1, f"应恰好提醒一次，实得 {len(warnings)} 次：{warnings}"
        assert "PyYAML" in warnings[0]


# ─── MIN-2249：清理 ffmpeg 必须判 returncode ──────────────────
class TestZombieCleanupJudgesReturnCode:
    def _drive(self, monkeypatch: pytest.MonkeyPatch, platform: str, results: list[_RunResult]) -> _LogSpy:
        spy = _LogSpy()
        calls: list[list[str]] = []

        def fake_run(argv: list[str], **kwargs: Any) -> _RunResult:
            calls.append(list(argv))
            assert kwargs.get("capture_output") is True, "清理工具必须捕获输出，否则非零提示进不了日志"
            assert not {"text", "encoding", "universal_newlines"} & set(kwargs), "判据只看 returncode，解码不得参与"
            return results[min(len(calls) - 1, len(results) - 1)]

        monkeypatch.setattr(gui, "sys", _shim(gui.sys, platform=platform))
        monkeypatch.setattr(gui, "subprocess", types.SimpleNamespace(run=fake_run))
        gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(spy, 4242)
        assert len(calls) >= 1, "未调用任何进程工具，说明本用例没驱动到真实分支"
        return spy

    def test_taskkill_rc_128_is_not_reported_as_cleaned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 失效形态：taskkill 找不到 PID 返回 128（提示写进 stdout），旧实现不看返回码即记
        # 「已清理」——「其实没杀掉」（权限不足 / PID 已复用 / taskkill 被策略禁用）与
        # 「杀成功了」在日志里完全同形，而这正是本函数存在的唯一目的。
        spy = self._drive(
            monkeypatch,
            "win32",
            [
                _RunResult(128, b"INFO: No tasks are running which match the specified criteria."),
                _RunResult(128, b"INFO: No tasks are running which match the specified criteria."),
            ],
        )
        text = spy.text()
        assert "已清理" not in text, f"rc=128 仍被记成已清理：{text}"
        assert "返回码 128" in text
        assert "未发现需要清理的 ffmpeg 进程" in text, "found 必须反映真实结果"
        assert "match the specified criteria" in text, "非 0 时须把工具自身的提示附上"

    def test_taskkill_rc_zero_reports_cleaned_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._drive(monkeypatch, "win32", [_RunResult(0), _RunResult(128)])
        text = spy.text()
        assert "已通过 taskkill 清理 PID 4242" in text
        assert "未发现需要清理的 ffmpeg 进程" not in text

    def test_pkill_rc_1_not_reported_as_cleaned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # POSIX 同形：pkill 无匹配返回 1（旧实现同样无条件记「已清理」，
        # 且 `if not found` 分支在 win32 上永不可达）。
        spy = self._drive(monkeypatch, "linux", [_RunResult(1), _RunResult(1)])
        text = spy.text()
        assert "已通过 pkill 清理" not in text
        assert "返回码 1" in text
        assert "未发现需要清理的 ffmpeg 进程" in text

    def test_kill_hint_takes_first_line_and_masks_credentials(self) -> None:
        # 提示只取第一行（日志不被多行工具输出撑坏），且一律过 mask_credentials：
        # 外部工具的文本不可信，万一代替 taskkill 的工具输出带 URL 也不至于把凭据落进 logs/gui.log。
        raw = b"first https://user:pass@host.example.com/x line\nsecond line\n"
        hint = gui._process_kill_hint(raw)
        assert hint.startswith("first ") and "\n" not in hint
        assert "user:pass" not in hint
        assert gui._process_kill_hint(b"", None) == ""
        assert gui._process_kill_hint(b"\n\n  \n") == ""

    def test_no_kill_call_reads_output_as_text(self) -> None:
        # 静态锁：本函数内所有 subprocess.run 一律按字节捕获（探测子进程输出口径）——中文 Windows
        # 的 GBK 本地化消息在 PYTHONUTF8=1 下会让 text=True 的 reader 线程解码抛错、判定语句 TypeError。
        tree = ast.parse(GUI_SOURCE)
        fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_cleanup_zombie_ffmpeg")
        runs = [
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "run"
        ]
        # [历史注] 原断言 `len(runs) == 4`：L-40（CODE_REVIEW_2026-10-02）删掉两段结构性无法命中的
        # 兜底过滤器（Windows PARENTPID / POSIX pkill -P 都只匹配 GUI 直接派生的 ffmpeg，而 ffmpeg
        # 的父进程恒为 main.py），扫描面从 4 降到 2。写死条数不表达任何判据，改为「非空反向见证 +
        # 逐个断言」：0 处即红，新增的第 N+1 处 run 由 ast.walk 自动纳入。
        assert runs, "未在 _cleanup_zombie_ffmpeg 内找到任何 subprocess.run（扫描口径失效即假绿）"
        for run in runs:
            keywords = {k.arg for k in run.keywords}
            assert "capture_output" in keywords
            assert not keywords & {"text", "encoding", "universal_newlines"}


# ─── MIN-2250：kernel32 声明与控制台恢复告警 ──────────────────
class _Sig:
    # 替身函数对象：只记录 argtypes / restype 被赋成了什么。
    def __init__(self) -> None:
        self.argtypes: object = None
        self.restype: object = None


class TestKernel32DeclaredAndConsoleRestoreWarns:
    def test_gui_has_no_windll_attribute_access(self) -> None:
        # 静态锁（走 AST，注释里提到旧写法不算命中）：新代码统一 ctypes.WinDLL。
        tree = ast.parse(GUI_SOURCE)
        hits = [
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, ast.Attribute)
            and n.attr == "windll"
            and isinstance(n.value, ast.Name)
            and n.value.id == "ctypes"
        ]
        assert hits == [], f"gui.py 仍在使用 ctypes.windll：{hits}"

    def test_get_gui_kernel32_declares_signatures(self, monkeypatch: pytest.MonkeyPatch) -> None:
        declared: dict[str, _Sig] = {}

        class _Dll:
            def __getattr__(self, name: str) -> _Sig:
                holder = declared.setdefault(name, _Sig())
                return holder

        built: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

        def fake_windll(*args: object, **kwargs: object) -> _Dll:
            built.append(("WinDLL", args, kwargs))
            return _Dll()

        fake_ctypes = types.SimpleNamespace(WinDLL=fake_windll, c_uint="c_uint", c_int="c_int", c_void_p="c_void_p")
        monkeypatch.setattr(gui, "ctypes", fake_ctypes)
        monkeypatch.setattr(gui, "sys", _shim(gui.sys, platform="win32"))
        monkeypatch.setattr(gui, "_GUI_KERNEL32", None)

        assert gui._get_gui_kernel32() is not None
        assert built and built[0][1] == ("kernel32",), "必须以 WinDLL('kernel32') 形态加载"
        # use_last_error=True 是「失败时能报出真实 GetLastError」的前提，缺了就只剩返回 0 可猜。
        assert built[0][2].get("use_last_error") is True
        # 本文件用到的每个入口都必须在这里统一声明签名（散在调用点 = 旧形态）。
        for name in (
            "GetConsoleWindow",
            "FreeConsole",
            "AttachConsole",
            "SetConsoleCtrlHandler",
            "GenerateConsoleCtrlEvent",
            "SetConsoleOutputCP",
            "SetConsoleCP",
        ):
            assert name in declared, f"{name} 未声明签名"
            assert declared[name].argtypes is not None, f"{name} 缺 argtypes"
            assert declared[name].restype is not None, f"{name} 缺 restype"
        # HWND 必须按指针宽度返回：默认 c_int 会截断 64 位句柄。
        assert declared["GetConsoleWindow"].restype == "c_void_p"

    def test_failed_console_restore_logs_last_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 行为注入：AttachConsole 一律失败 → 除返回 False 外必须留下一条带 GetLastError 的
        # warning。旧实现丢了返回值，此后本进程的 print / loguru 控制台 sink 全写向无效句柄，
        # 用户视角是「停止一次录制后 GUI 终端再也看不到日志」且全程零告警。
        warnings: list[str] = []
        attempts: list[int] = []

        class _K32:
            def GetConsoleWindow(self) -> int:
                return 0x7FF61234ABC0  # 64 位句柄形态：旧实现按默认 c_int 会被截断

            def FreeConsole(self) -> int:
                return 1

            def AttachConsole(self, target: int) -> int:
                attempts.append(int(target))
                return 0

        monkeypatch.setattr(gui, "_get_gui_kernel32", lambda: _K32())
        monkeypatch.setattr(
            gui,
            "ctypes",
            types.SimpleNamespace(
                get_last_error=lambda: 5,
                WINFUNCTYPE=lambda *a: (lambda func: func),
                c_bool=object,
                c_ulong=object,
            ),
        )
        monkeypatch.setattr(gui, "sys", _shim(gui.sys, platform="win32"))
        monkeypatch.setattr(gui, "logger", types.SimpleNamespace(warning=lambda msg: warnings.append(str(msg))))

        assert gui._send_ctrl_break_to_child(4321) is False
        assert attempts[:1] == [4321], "应先尝试挂到子进程控制台"
        assert gui._ATTACH_PARENT_PROCESS in attempts, "失败路径仍须尝试把自己的控制台挂回去"
        joined = "\n".join(warnings)
        assert "GetLastError=5" in joined, f"恢复失败必须带 GetLastError 落告警，实得：{joined!r}"

    def test_restore_skipped_when_process_had_no_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向护栏：pythonw / console=False 冻结 exe 本就没有控制台，
        # 此时不得报「恢复失败」——否则每次停止录制都刷一条无意义告警。
        warnings: list[str] = []
        attempts: list[int] = []

        class _K32:
            def GetConsoleWindow(self) -> int:
                return 0

            def FreeConsole(self) -> int:
                return 1

            def AttachConsole(self, target: int) -> int:
                attempts.append(int(target))
                return 0

        monkeypatch.setattr(gui, "_get_gui_kernel32", lambda: _K32())
        monkeypatch.setattr(
            gui,
            "ctypes",
            types.SimpleNamespace(
                get_last_error=lambda: 5, WINFUNCTYPE=lambda *a: (lambda func: func), c_bool=object, c_ulong=object
            ),
        )
        monkeypatch.setattr(gui, "sys", _shim(gui.sys, platform="win32"))
        monkeypatch.setattr(gui, "logger", types.SimpleNamespace(warning=lambda msg: warnings.append(str(msg))))

        assert gui._send_ctrl_break_to_child(4321) is False
        assert gui._ATTACH_PARENT_PROCESS not in attempts
        assert warnings == []


# ─── MID-2252：URL 页整文件写回前的冲突裁决 ──────────────────
class TestUrlSaveChecksDiskBeforeWriting:
    def test_url_save_config_goes_through_verdict(self) -> None:
        # 静态锁：录制子进程运行期确实在写 URL_config.ini（回写主播名 / 归一 URL / 注释风控房间），
        # 而 GUI 与它是两个进程，跨进程只剩「原子替换不会半写」。「丢失更新」只能落盘前显式检测 +
        # 交用户裁决，故接线不得回退成直接写文件。
        tree = ast.parse(GUI_SOURCE)
        saves = [
            n
            for n in ast.walk(tree)
            # ast.dump 把属性拆成 attr='url_config_file'，判「引用了哪个字段」要用 unparse 后的源码形态
            if isinstance(n, ast.FunctionDef) and n.name == "save_config" and "self.url_config_file" in ast.unparse(n)
        ]
        assert len(saves) == 1, f"URL 页 save_config 应唯一，实得 {len(saves)}"
        dumped = ast.dump(saves[0])
        assert "_read_config_snapshot" in dumped, "落盘前必须重读磁盘"
        assert "_config_change_verdict" in dumped, "必须复用与高级设置窗口同源的裁决"
        calls = [
            n
            for n in ast.walk(saves[0])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_config_change_verdict"
        ]
        assert calls, "裁决必须直接调用，不得另造一套并行判据"
        verdict_args = [ast.unparse(a) for a in calls[0].args]
        assert verdict_args[:2] == ["self._url_disk_snapshot", "disk_now"], f"基线/现值顺序错了：{verdict_args}"
        # 写文件必须发生在裁决之后（否则裁决形同虚设）。
        write_calls = [
            n
            for n in ast.walk(saves[0])
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_save_text_widget_to_file"
        ]
        assert write_calls and calls[0].lineno < write_calls[0].lineno


# ─── MIN-2247：对话框文案必须逐条登记 pending ─────────────────
def _messagebox_tr_templates() -> set[str]:
    # 抽 gui.py 里 messagebox.* 的全部 i18n.tr 模板实参（提取器扫不到这条路，AGENTS 已记载）。
    tree = ast.parse(GUI_SOURCE)
    out: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        func = node.func
        if not (isinstance(func.value, ast.Name) and func.value.id == "messagebox"):
            continue
        for arg in node.args:
            if (
                isinstance(arg, ast.Call)
                and isinstance(arg.func, ast.Attribute)
                and arg.func.attr == "tr"
                and arg.args
                and isinstance(arg.args[0], ast.Constant)
                and isinstance(arg.args[0].value, str)
            ):
                out.add(arg.args[0].value)
    return out


_BRACE_RE = re.compile("[{][^{}]*[}]")


def _four_catalogs() -> dict[str, dict[str, str]]:
    # 复用 i18n 自己的三个加载器读四语真实目录，不写第二套解析口径
    # （本仓反复登记过「两套解析不一致导致误判」的形态：配置键审计、.mo 头部字段索引）。
    cats = {
        "zh_CN": i18n._load_mo_catalog(i18n.locale_path, "zh_CN"),
        "en_US": i18n._load_json_catalog(pathlib.Path(i18n.locale_path) / "en_US.json"),
        "en_GB": i18n._load_json_catalog(pathlib.Path(i18n.locale_path) / "en_GB.json"),
        "zh_TW": i18n._load_yaml_catalog(pathlib.Path(i18n.locale_path) / "zh_TW.yaml"),
    }
    loaded: dict[str, dict[str, str]] = {}
    for lang_key, value in cats.items():
        # 逐语言断言而不是先算 broken 再 dict(v)：后者 mypy 仍视 value 为可空，
        # 前者让「目录缺件」与「类型收窄」共用同一个事实。
        assert value is not None, f"{lang_key} 语言目录加载失败或缺失（目录缺件 ≠ 用例可跳过）"
        loaded[lang_key] = dict(value)
    return loaded


class TestDialogStringsRegistered:
    def test_every_messagebox_template_is_registered(self) -> None:
        # 漏登记 = 假绿：门禁全绿、extract_i18n_strings 报「0 缺失」，但英文用户在「彻底退出 /
        # 没有直播间地址 / 冲突裁决」这些最需要看得懂的界面上只拿到简中。判据对象是四语目录本身，
        # 不是 _i18n_pending_gui.json——袋子只是并行修复期防撞车的一次性中转，以袋为准会让
        # 「袋子写过、目录没合」这种最真实的漏网形态一路绿到底。
        templates = _messagebox_tr_templates()
        assert templates, "未抽到任何 messagebox 模板，说明抽取判据已失效（勿改成恒真）"
        cats = _four_catalogs()
        missing = sorted(
            f"{msgid[:40]!r} <- {sorted(lang for lang, cat in cats.items() if msgid not in cat)}"
            for msgid in templates
            if any(msgid not in cat for cat in cats.values())
        )
        assert missing == [], f"对话框文案未并入四语目录：{missing}"
        for msgid in templates:
            for lang in ("en_US", "en_GB", "zh_TW"):
                assert cats[lang][msgid].strip(), f"{lang} 译文为空：{msgid[:40]!r}"

    def test_catalog_translations_keep_placeholders_and_line_counts(self) -> None:
        # MIN-2253：占位符对账此前只有「模板 vs 关键字实参」一条（源码侧），**没有任何一条**比较四
        # 份译文内部——本仓出过 zh_TW 把 {msg} 写成 {msg_2} 而调用方传 msg= 的事故，繁体下钉钉/微信/
        # Bark/PushPlus 的失败告警整条 KeyError 崩掉。MI-23 改成回退原文后，同类漂移只表现为「繁体
        # 用户看到的仍是简体」，与「该键本来没译」完全同形。全量目录级锁 780 键 × 3 语言
        # （2026-09-26 清理 Weverse 孤儿条目后由 783 降为 780），不依赖 pending 袋子是否存在。
        cats = _four_catalogs()
        keys = set(cats["zh_CN"]) & set(cats["en_US"]) & set(cats["en_GB"]) & set(cats["zh_TW"])
        assert keys, "四语目录键集为空"
        offenders: list[str] = []
        for msgid in sorted(keys):
            want = set(_BRACE_RE.findall(msgid))
            lines = len(msgid.splitlines())
            for lang in ("en_US", "en_GB", "zh_TW"):
                text = cats[lang][msgid]
                if set(_BRACE_RE.findall(text)) != want or len(text.splitlines()) != lines:
                    offenders.append(f"{lang}:{msgid[:50]!r}")
        assert offenders == [], f"译文与源串占位符/行数不一致（{len(offenders)} 条）：{offenders[:8]}"
