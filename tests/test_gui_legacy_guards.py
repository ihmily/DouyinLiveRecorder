# tests/test_gui_legacy_guards.py —— 遗留 tkinter 路径（gui.py）七条审查项的回归锁。
#
# 覆盖 CODE_REVIEW_2026-10-21 的 M-71 / M-72 / M-73 / M-75 / M-76①②③ / M-77①②。
# 与同族文件的分工：tests/test_gui_tail_robustness.py 锁 after 自续期链「抛错仍续期」，
# 本文件锁的是**同一条链上的数据不丢**（M-71 批次不空转、M-73 哨兵不丢）；
# tests/test_regression_2026_10_18_root_entries.py 锁「确证复用即收手」（L-02 原格），
# 本文件 M-72 锁**判据读不出来**那一格——那是 L-02 留下的最后一个误杀口子。
#
# 桩口径（AGENTS 测试约定逐条对齐）：
#   * 不在模块顶层 import gui：gui.py 模块级写 os.environ["DLR_GUI_PARENT"]="1"，收集期导入
#     会把整会话的 src.logger 定成 GUI 父进程模式；故走**会话级**夹具，且用
#     MonkeyPatch.context + setenv 占位（delenv 只登记「删除前已存在的值」，恰好是要清掉的 "1"）。
#   * 只替「问操作系统这个号码现在是谁」的两处系统查询与 subprocess.run；判定链
#     （_reused_pid_* 的比对、_cleanup_zombie_ffmpeg 的分支、_config_change_verdict 的裁决、
#     _process_ended 的会话校验）一律走真实实现。
#   * 进程级 stdlib 替身一律经被测模块命名空间的 shim（types.SimpleNamespace(**vars(subprocess))）。
#   * 平台分流用 monkeypatch.setattr(sys, "platform", "win32") 强制走进 Windows 分支——不得 skipif，
#     否则 CI（ubuntu）上这条 Windows 专属防线的锁会静默消失。
#   * 线程用例 join 之后必须断言线程已退出（R10）。

import ast
import importlib
import queue
import subprocess
import sys
import threading
import time
import types
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

# gui.py 的两条导入期副作用（本文件唯一需要隔离的面）：模块级 os.environ["DLR_GUI_PARENT"]="1"
# 与 _fix_encoding() 就地 reconfigure 宿主 stdio（后者落在函数级夹具里会被 conftest 的
# _guard_stdio_encoding_policy 判成「用例改动了宿主编码策略」，故会话级）。
_GUI_PARENT_ENV = "DLR_GUI_PARENT"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_GUI_SOURCE = (_REPO_ROOT / "gui.py").read_text(encoding="utf-8")
_GUI_TREE = ast.parse(_GUI_SOURCE)


@pytest.fixture(scope="session", autouse=True)
def gui() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setenv(_GUI_PARENT_ENV, "")
        module = importlib.import_module("gui")
    yield module


def _method_body(source: str, tree: ast.Module, name: str) -> ast.FunctionDef:
    fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name), None)
    assert fn is not None, f"gui.py 里找不到 {name}（判据基准失效即假绿）"
    return fn


# ─── M-72：判据读不出来 → 不杀（退出兜底的最后一个误杀口子） ────────────────────


class _FakeCompleted:
    # subprocess.run 的返回形态：returncode 0 + 空字节流（判定一律按字节，不传 text=）。
    returncode = 0
    stdout = b""
    stderr = b""


def _cleanup_stub(gui: ModuleType, recorded_image: object, recorded_stamp: object, logs: list[Any]) -> Any:
    # object.__new__ 跳过 __init__（不建真窗），只注入 _cleanup_zombie_ffmpeg 触及的三面；
    # _child_image_name / _child_creation_stamp 用 setattr 而非裸赋值共享属性（AGENTS M-25）。
    app = object.__new__(gui.LiveRecorderGUI)
    setattr(app, "_child_image_name", recorded_image)
    setattr(app, "_child_creation_stamp", recorded_stamp)
    setattr(app, "_log", lambda message, level="info": logs.append((str(message), level)))
    return app


def _kill_runs(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    runs: list[list[str]] = []

    def _run(argv: Any, *args: Any, **kwargs: Any) -> _FakeCompleted:
        runs.append([str(item) for item in argv])
        return _FakeCompleted()

    shim = types.SimpleNamespace(**vars(subprocess))
    shim.run = _run
    monkeypatch.setattr(gui, "subprocess", shim)
    return runs


def test_indeterminate_creation_stamp_blocks_whole_tree_kill(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # M-72 的本体：源码运行态下 _child_image_name 恒为 python.exe（record_cmd[0] 就是解释器），
    # 映像名判据结构性失效；此时创建时间又读不出来（权限不足 / 号码已进复用池），旧形态
    # 按「无法判定即放行」继续 taskkill /F /T —— 打的是接手该号码的无关进程及其整棵子树。
    # 兜底的政策取向是宁可漏清不可误杀：漏清最多留一只孤儿 ffmpeg，误杀不可逆。
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(gui, "_win_pid_image_name", lambda pid: "")
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", lambda pid: None)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[Any] = []

    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, "python.exe", 123456, logs), 4242)

    assert runs == [], f"判据无法证明那个号码还是我们的进程，却发出了杀进程命令: {runs}"
    warns = [row for row in logs if row[1] == "warn"]
    assert len(warns) == 1, f"跳过强杀必须恰留一条可归因的告警（多于一条说明别处也在报错）: {logs}"
    assert "4242" in warns[0][0], f"告警必须点名 PID，否则用户无从判断漏清了哪一棵树: {warns[0][0]}"


def test_confirmed_same_process_still_cleans_the_tree(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向护栏一：两道判据都能读到且逐位相同（最常见路径）→ 整树强杀照发、一条 warn 都不该有。
    # 缺这一格，「无法判定即不杀」会被写成「一律不杀」，孤儿 ffmpeg 复活且无人发现。
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(gui, "_win_pid_image_name", lambda pid: "python.exe")
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", lambda pid: 123456)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[Any] = []

    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, "python.exe", 123456, logs), 4242)

    assert any("/T" in argv and "4242" in argv for argv in runs), f"确证未复用时必须照常清理: {runs}"
    assert [row for row in logs if row[1] == "warn"] == [], f"正常清理路径不应有告警: {logs}"


def test_no_expectation_recorded_does_not_narrow_cleanup(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 反向护栏二：从未登记过期望值（桩实例不跑 __init__ / 非 Windows / 启动那次读取也失败）时
    # 判据**完全不介入**，连一次系统查询都不该发起——那段 PID 复用窗口本不存在，
    # 把「读不到就不杀」扩大到这里等于凭空削掉兜底清理能力。
    monkeypatch.setattr(sys, "platform", "win32")
    probes: list[int] = []

    def _image_probe(pid: int) -> str:
        probes.append(pid)
        return ""

    def _stamp_probe(pid: int) -> int | None:
        probes.append(pid)
        return None

    monkeypatch.setattr(gui, "_win_pid_image_name", _image_probe)
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", _stamp_probe)
    runs = _kill_runs(gui, monkeypatch)
    logs: list[Any] = []

    gui.LiveRecorderGUI._cleanup_zombie_ffmpeg(_cleanup_stub(gui, "", None, logs), 4242)

    assert any("/T" in argv and "4242" in argv for argv in runs), f"未记录即不判定，照发清理: {runs}"
    assert probes == [], f"期望值缺席时不该发起任何进程查询: {probes}"


def test_reused_pid_same_image_verdict_matrix(gui: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    # 判定函数本体的四格矩阵：M-72 的全部语义收敛在这里，别处只读它的结论。
    # 摘掉「读不到 → 判已复用」那一支时，第三格立刻变 False（本用例即红）。
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", lambda pid: None)
    assert gui._reused_pid_same_image(None, 4242) is False, "期望值缺席也必须收手 = 收窄了清理能力"
    assert gui._reused_pid_same_image(123456, 4242) is True, "登记过期望值却读不到当前值必须按「已复用」收手"
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", lambda pid: 123456)
    assert gui._reused_pid_same_image(123456, 4242) is False
    monkeypatch.setattr(gui, "_win_pid_creation_stamp", lambda pid: 654321)
    assert gui._reused_pid_same_image(123456, 4242) is True


# ─── M-73：进程结束哨兵必须在 finally 里处理 ─────────────────────────────────────


class _RaisingText:
    # 渲染必抛的 tk.Text 替身（真实故障形态：log_text 已被销毁 / index 解析失败）。
    def config(self, **kwargs: Any) -> None:
        raise RuntimeError("log_text 已销毁")


def _queue_stub(gui: ModuleType) -> Any:
    stub = object.__new__(gui.LiveRecorderGUI)
    stub._log_queue = queue.Queue()
    stub._log_queue_lock = threading.Lock()
    stub._log_queue_has_data = True
    stub._log_flush_job_id = None
    stub.root = FakeRoot()
    stub._get_timestamp = lambda: "2026-10-21 00:00:00"
    stub._chain_warn_at = {}
    stub._log = lambda message, level="info": None
    return stub


class FakeRoot:
    # 只记「取消了哪个 id / 排了哪个回调」，不真跑 Tk：after_cancel 的实现属 Tk 解释器，
    # 本文件锁的是「id 有没有被记账、取消点在不在」。
    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.scheduled: list[tuple[int, str]] = []

    def after(self, delay: int, callback: Any) -> str:
        self.scheduled.append((int(delay), getattr(callback, "__name__", repr(callback))))
        return "job-%d" % len(self.scheduled)

    def after_cancel(self, job_id: str) -> None:
        self.cancelled.append(str(job_id))


def test_ended_sentinel_survives_render_failure(gui: ModuleType) -> None:
    # 渲染段一抛，异常被 _schedule_log_flush 的 except 吞掉；旧形态里 process_ended 排在渲染
    # **之后**、无 try/finally 隔离，于是「子进程已结束」这个结论随栈一起丢失——开始/停止
    # 按钮与状态灯永久停在「录制中」，且没有第二条路径会再送一次哨兵。
    ended: list[Any] = []
    stub = _queue_stub(gui)
    stub.log_text = _RaisingText()
    stub._process_ended = lambda session_id=None: ended.append(session_id)
    stub._log_queue.put([["一行日志", "info"]])
    stub._log_queue.put((7,))

    # 必须经 _schedule_log_flush 这条真实通路：直调 _drain_log_queue 会让异常抛给用例，
    # 恰好测不到「异常被上层吞掉之后哨兵还在不在」这个真实形态。
    gui.LiveRecorderGUI._schedule_log_flush(stub)

    assert ended == [7], f"渲染抛错时结束哨兵被丢弃（按钮会永久停在录制中）: {ended}"


def test_stale_session_sentinel_is_still_dropped_by_the_real_gate(gui: ModuleType) -> None:
    # finally 化的反向护栏一：挪动的是**时机**，不是判定。旧会话的迟到哨兵必须仍被真实
    # _process_ended 的会话校验丢弃——否则「渲染抛错 + 新会话已启动」会把新会话的
    # running/按钮打回未运行（用户视角：正在录的新会话显示成没录）。
    stub = _queue_stub(gui)
    stub.log_text = _RaisingText()
    stub._process_lock = threading.Lock()
    stub._running = True
    stub._process = object()
    stub._process_pid = 4242
    stub._session_id = 9
    stub._quitting = False
    stub._stopping = False
    stub.output_thread = None
    stub.start_btn = _RecordingWidget()
    stub.stop_btn = _RecordingWidget()
    stub._stop_danmaku_tail = lambda: None
    stub._set_status = lambda color, recording: None
    stub._update_status_bar = lambda: None
    stub._log_queue.put([["一行日志", "info"]])
    stub._log_queue.put((7,))

    gui.LiveRecorderGUI._schedule_log_flush(stub)

    assert stub._running is True, "旧会话的迟到哨兵把新会话的 running 打回了未运行"
    assert stub.start_btn.states == [] and stub.stop_btn.states == [], "旧会话哨兵不得触碰按钮状态"


def test_current_session_sentinel_completes_reset_after_render_failure(gui: ModuleType) -> None:
    # finally 化的正向对照：会话代号对上时，渲染抛错也照常完成收尾（按钮回到可点、running 置假）。
    # 与上一格成对——缺任一侧都说明 finally 只做了一半。
    stub = _queue_stub(gui)
    stub.log_text = _RaisingText()
    stub._process_lock = threading.Lock()
    stub._running = True
    stub._process = object()
    stub._process_pid = 4242
    stub._session_id = 7
    stub._quitting = False
    stub._stopping = False
    stub.output_thread = None
    stub.start_btn = _RecordingWidget()
    stub.stop_btn = _RecordingWidget()
    stub._stop_danmaku_tail = lambda: None
    stub._set_status = lambda color, recording: None
    stub._update_status_bar = lambda: None
    stub._log_queue.put([["一行日志", "info"]])
    stub._log_queue.put((7,))

    gui.LiveRecorderGUI._schedule_log_flush(stub)

    assert stub._running is False, "渲染抛错时结束收尾仍未完成（按钮会永久停在录制中）"
    assert stub.start_btn.states == ["normal"], stub.start_btn.states
    assert stub.stop_btn.states == ["disabled"], stub.stop_btn.states


class _RecordingWidget:
    def __init__(self) -> None:
        self.states: list[Any] = []

    def configure(self, **kwargs: Any) -> None:
        self.states.append(kwargs.get("state"))


def test_render_success_still_processes_sentinel_once(gui: ModuleType) -> None:
    # 对照组：健康路径不得被 finally 改动打乱——渲染成功时哨兵同样只处理一次、日志确实落控件。
    ended: list[Any] = []
    stub = _queue_stub(gui)
    stub.log_text = _RecordingText()
    stub._process_ended = lambda session_id=None: ended.append(session_id)
    stub._log_queue.put([["正常一行", "info"]])
    stub._log_queue.put((3,))

    gui.LiveRecorderGUI._drain_log_queue(stub)

    assert ended == [3], ended
    assert stub.log_text.inserted == ["[2026-10-21 00:00:00] 正常一行\n"], stub.log_text.inserted


class _RecordingText:
    def __init__(self) -> None:
        self.inserted: list[str] = []

    def config(self, **kwargs: Any) -> None:
        return None

    def insert(self, index: Any, text: Any, tag: Any = None) -> None:
        self.inserted.append(str(text))

    def index(self, *args: Any) -> str:
        return "10.0"

    def delete(self, *args: Any) -> None:
        return None

    def see(self, *args: Any) -> None:
        return None


# ─── M-71：输出线程的批次时间兜底 ────────────────────────────────────────────────


class _TrickleStdout:
    # 只给一行、此后恒「无数据」：真实管道上是 readline 阻塞，这里用短睡 + 回空串等价替代
    # （_read_output 对空串走「EOF 但进程仍在」那条分支，正是稳定期的真实形态）。
    def __init__(self, first_line: str) -> None:
        self._pending: str | None = first_line

    def readline(self) -> str:
        if self._pending is not None:
            line, self._pending = self._pending, None
            return line
        time.sleep(0.02)
        return ""


class _TrickleProc:
    def __init__(self, first_line: str) -> None:
        self.stdout = _TrickleStdout(first_line)
        self._stop = threading.Event()

    def poll(self) -> int | None:
        return 0 if self._stop.is_set() else None


def test_read_output_flushes_partial_batch_on_time(gui: ModuleType) -> None:
    # 稳定录制的房间约 120s 才输出一条状态行；只按「攒满 10 行」刷新的话日志页要空白约
    # 20 分钟，用户视角就是界面冻住（正常运行路径必然出现的失效）。
    # 兜底窗口在本用例里压到 0.05s（该常量本身就是被锁的对象）；反向证明由 poll 恒回 None
    # 提供——整段等待期间没有任何 EOF 收尾可以依赖，旧实现只能一直攒着。
    stub = object.__new__(gui.LiveRecorderGUI)
    stub._log_queue = queue.Queue()
    stub._log_queue_lock = threading.Lock()
    stub._log_queue_has_data = False
    stub._LOG_BATCH_FLUSH_SECONDS = 0.05
    stub._parse_quality_log = lambda line: None
    stub._mark_session_stopped = lambda session_id: None

    proc = _TrickleProc("主播[原画] 正在录制中 00:01:00\n")
    worker = threading.Thread(target=gui.LiveRecorderGUI._read_output, args=(stub, proc, 1), daemon=True)
    worker.start()
    batch: list[Any] = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            item = stub._log_queue.get_nowait()
        except queue.Empty:
            time.sleep(0.02)
            continue
        if isinstance(item, list):
            batch = list(item)
            break
    proc._stop.set()
    worker.join(timeout=10)
    assert not worker.is_alive(), "输出线程未随进程结束退出（join 超时即被测逻辑死锁）"

    assert batch == [("主播[原画] 正在录制中 00:01:00", "info")], f"半截批次从未按时间入队: {batch}"


# ─── M-76①：画质表的 last_seen 走本文件自定的容错口径 ───────────────────────────


class _FakeTable:
    def __init__(self) -> None:
        self.synced: list[Any] = []

    def sync(self, keys: Any, values: Any, tags: Any) -> list[str]:
        self.synced.append((list(keys), dict(values), dict(tags)))
        return []


class _FakeStat:
    def __init__(self) -> None:
        self.text = ""

    def configure(self, **kwargs: Any) -> None:
        self.text = str(kwargs.get("text", self.text))


def _quality_stub(gui: ModuleType) -> Any:
    stub = object.__new__(gui.LiveRecorderGUI)
    stub._quality_table = _FakeTable()
    stub._quality_lock = threading.Lock()
    stub._quality_data = {}
    stub._quality_last_displayed = {}
    stub._anchor_quality_map = {}
    stub._quality_row_setq = {}
    stub._highlight_changed_rows = lambda table, changed: None
    stub._show_quality_placeholder = lambda visible: None
    stub._q_stat_total = _FakeStat()
    stub._q_stat_ok = _FakeStat()
    stub._q_stat_down = _FakeStat()
    stub._chain_warn_at = {}
    stub._log = lambda message, level="info": None
    return stub


def test_update_quality_display_tolerates_dirty_last_seen(gui: ModuleType) -> None:
    # 本文件的数值字段容错口径是模块级 _as_float（定义处注释写明「唯一」），last_seen 这一处
    # 却写成 cast(float, info.get("last_seen", 0))：cast 运行期什么都不做，脏值一进减法就抛
    # TypeError，整轮刷新被 _warn_chain 吞成一句告警、画质表从此停在旧值上。
    stub = _quality_stub(gui)
    stub._quality_data = {
        "房间None": {"recording": True, "last_seen": None, "downgraded": False},
        "房间文本": {"recording": True, "last_seen": "不是数", "downgraded": False},
        "房间陈旧": {"recording": True, "last_seen": time.time() - 999, "downgraded": False},
        "房间新鲜": {"recording": True, "last_seen": time.time(), "downgraded": False},
    }

    gui.LiveRecorderGUI._update_quality_display(stub)

    # 脏值按 0 处理 = 早已超时 → 录制标记被清；健康值（刚刚）必须保留，
    # 否则这条容错就退化成「一律判超时」的同族假绿。
    assert stub._quality_data["房间None"]["recording"] is False
    assert stub._quality_data["房间文本"]["recording"] is False
    assert stub._quality_data["房间陈旧"]["recording"] is False
    assert stub._quality_data["房间新鲜"]["recording"] is True
    assert stub._quality_table.synced, "当轮刷新必须把表同步出去，不得停在旧值"


# ─── M-76②：编辑器读不到正文时返回哨兵，且绝不落盘 ──────────────────────────────


class _BrokenText:
    def get(self, *args: Any) -> str:
        raise RuntimeError("控件已销毁")


def test_editor_content_sentinel_routes_into_conflict_branch(gui: ModuleType) -> None:
    # 旧形态异常时回退 _baseline_content（等于宣称「没有未保存改动」），于是磁盘侧的外部改动
    # 可被判成 reload 并静默覆盖用户的编辑。哨兵含 NUL，不可能等于任何真实基线。
    win = object.__new__(gui.AdvancedSettingsWindow)
    win.config_text = _BrokenText()
    win._baseline_content = "旧的基线"

    editor_text = gui.AdvancedSettingsWindow._editor_content(win)

    assert editor_text == gui._EDITOR_CONTENT_UNREADABLE, repr(editor_text)
    assert editor_text != win._baseline_content
    verdict = gui._config_change_verdict("磁盘基线", "磁盘现在", editor_text, win._baseline_content)
    assert verdict == "conflict", f"哨兵没有落进既有 conflict 分支: {verdict}"


def test_save_config_never_writes_the_sentinel(
    gui: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # 关键反向护栏：磁盘与基线逐字一致时 _config_change_verdict 先回 "unchanged"、不进询问，
    # 不显式识别哨兵就会把含 NUL 的标记本身写进 config.ini（配置文件解析器再也读不回来）。
    # messagebox 必须打桩：守卫一旦回归，成功路径会弹**真模态框**，无头/无人值守的变异验证
    # 会就地挂死（本仓实测教训：这类用例要么打桩要么走子进程）。替身按 shim 口径挂到
    # 被测模块命名空间，不改 stdlib/tkinter 模块本体。
    monkeypatch.setattr(
        gui,
        "messagebox",
        types.SimpleNamespace(
            showinfo=lambda *args: None,
            showerror=lambda *args: None,
            askyesno=lambda *args: True,
        ),
    )
    target = tmp_path / "config.ini"
    original = "[录制设置]\nlanguage = zh_CN\n"
    target.write_text(original, encoding="utf-8-sig")
    hints: list[str] = []
    win = object.__new__(gui.AdvancedSettingsWindow)
    win.config_file = str(target)
    win.config_text = _BrokenText()
    win._baseline_content = original
    win._disk_snapshot = original
    win._set_hint = lambda text: hints.append(text)
    win._close = lambda: None
    win.log_callback = None

    gui.AdvancedSettingsWindow.save_config(win)

    assert target.read_text(encoding="utf-8-sig") == original, "哨兵被当成正文写进了配置文件"
    assert hints, "取消保存必须留下可见痕迹，否则用户以为已经保存成功"


# ─── M-76③：_load_config 的早退分支也要刷新「已保存」基线 ───────────────────────


class _EchoText:
    # tk.Text 替身：get 恒返回磁盘那份内容（早退分支的成立条件正是「编辑器 == 磁盘」）。
    def __init__(self, content: str) -> None:
        self._content = content

    def get(self, *args: Any) -> str:
        return self._content

    def delete(self, *args: Any) -> None:
        return None

    def insert(self, index: Any, text: Any) -> None:
        return None


def test_load_config_early_return_marks_saved_baseline(gui: ModuleType, tmp_path: Path) -> None:
    # 早退分支跳过 _mark_config_saved() 时，_config_baseline_content 停在更早的一版，
    # 「当前内容 != 基线」判脏恒真 → 退出确认与保存前反复弹同一句「有未保存更改」。
    url_file = tmp_path / "URL_config.ini"
    content = "原画,https://live.douyin.com/123456,主播: 甲"
    url_file.write_text(content, encoding="utf-8-sig")
    stub = object.__new__(gui.LiveRecorderGUI)
    stub.url_config_file = str(url_file)
    stub.config_text = _EchoText(content)
    # 基线故意留成早先的另一版：模拟「外部改动已被编辑器回填、基线却没跟上」的真实中间态。
    stub._config_baseline_content = "更早的一版内容"
    stub._url_disk_snapshot = ""
    stub._refresh_quality_context = lambda: None
    stub._last_url_config_mtime = 0.0
    stub._log = lambda message, level="info": None

    gui.LiveRecorderGUI._load_config(stub)

    assert (
        gui.LiveRecorderGUI._has_unsaved_config_edits(stub) is False
    ), "早退分支仍未刷新已保存基线（会反复弹未保存提示）"


# ─── M-77①：几何收敛不得重入完整事件循环 ────────────────────────────────────────


def test_settled_reqwidth_never_reenters_the_event_loop() -> None:
    # root.update() 会重入**整个**事件循环：本方法由 _setup_ui 末尾调用，那时 __init__ 后半段
    # 与 _load_config 都还没跑，重入等于把排队的用户事件与别的 after 回调打在半成品控件上。
    # 保留的是「迭代到读数稳定」这个判据（列宽重算挂在 <Configure> 上，单次读数拿到大窗旧值），
    # 触发方式换成 idle 结算 + 对两张表定向补发 <Configure>（event_generate 不消费排队事件）。
    fn = _method_body(_GUI_SOURCE, _GUI_TREE, "_settled_reqwidth")
    root_update = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "update"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "root"
    ]
    assert not root_update, "_settled_reqwidth 里不得出现 self.root.update()（重入事件循环）"
    idle = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "update_idletasks"
    ]
    assert idle, "_settled_reqwidth 必须用 update_idletasks() 结算几何"
    nudged = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_nudge_table_configure"
    ]
    assert nudged, "列宽重算必须仍有触发点，否则读数停在构建初期的旧值（右边框裁切回归）"
    # 有界采样：循环上界必须钉在形参 passes 上，不得改成 while True（MID-59 那条无界等待的同族形态）。
    loops = [node for node in ast.walk(fn) if isinstance(node, ast.For)]
    assert loops and all(ast.unparse(loop.iter) == "range(passes)" for loop in loops), "收敛循环必须是有界 for"


def test_table_configure_nudge_is_bounded_and_tolerant() -> None:
    # 定向补发的那一步：窗口尚未 realized 时 event_generate 抛 TclError，正是「还没有可算的树宽」，
    # 必须接住继续收敛；两张表都必须补（画质 + 弹幕），漏一张等于该页列宽永不落地。
    fn = _method_body(_GUI_SOURCE, _GUI_TREE, "_nudge_table_configure")
    generates = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "event_generate"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "<Configure>"
    ]
    assert generates, "_nudge_table_configure 必须补发 <Configure>"
    guarded = [node for node in ast.walk(fn) if isinstance(node, ast.Try)]
    assert guarded, "补发必须容错（未 realize / 已销毁的控件会抛 TclError）"


# ─── M-77②：一次性 after 的 id 必须记账并可取消 ─────────────────────────────────


def test_cancel_after_job_records_and_tolerates_failure(gui: ModuleType) -> None:
    stub = object.__new__(gui.LiveRecorderGUI)
    stub.root = FakeRoot()

    gui.LiveRecorderGUI._cancel_after_job(stub, None)
    assert stub.root.cancelled == [], "id 为空时不该发起任何取消"

    gui.LiveRecorderGUI._cancel_after_job(stub, "job-1")
    assert stub.root.cancelled == ["job-1"], stub.root.cancelled

    class _ThrowingRoot(FakeRoot):
        def after_cancel(self, job_id: str) -> None:
            raise RuntimeError("TclError：窗口已销毁")

    stub.root = _ThrowingRoot()
    gui.LiveRecorderGUI._cancel_after_job(stub, "job-2")  # 不得抛：取消结果无关紧要


def test_one_shot_after_jobs_are_recorded_and_cancelled() -> None:
    # 接线必须同时成立四处：主题延迟重取色「先取消上一支再记账」、对话框延迟 grab「先取消再记账」、
    # 对话框销毁路径取消、退出收尾两支都取消。只钉「谁被调用、返回值去了哪里」这一不变量，
    # 不钉行号也不钉文案（M-26 的教训：字面量文本锁会在契约反转后静默空洞成立）。
    def assignments(name: str, attr_name: str) -> list[ast.Assign]:
        fn = _method_body(_GUI_SOURCE, _GUI_TREE, name)
        return [
            node
            for node in ast.walk(fn)
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Attribute) and target.attr == attr_name for target in node.targets)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "after"
        ]

    def cancelled_attrs(name: str) -> set[object]:
        # 收集某方法内所有 _cancel_after_job(getattr(self, "<属性名>")) 的属性名。
        fn = _method_body(_GUI_SOURCE, _GUI_TREE, name)
        return {
            node.args[0].args[1].value
            for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_cancel_after_job"
            and node.args
            and isinstance(node.args[0], ast.Call)
            and isinstance(node.args[0].func, ast.Name)
            and node.args[0].func.id == "getattr"
            and len(node.args[0].args) > 1
            and isinstance(node.args[0].args[1], ast.Constant)
        }

    assert assignments("_on_theme_change", "_canvas_bg_job_id"), "主题切换的 after(50) 未记账 id"
    assert assignments("on_closing", "_close_dialog_grab_job_id"), "对话框的 after(100) 未记账 id"
    # 连点同一个菜单会排出两支 job：排新的一刻必须先取消旧的，否则「后一支在窗口销毁后触发」
    # 这条故障形态与不记账等价（M-77② 要收的是全部三个面，缺一面就漏一类误触发）。
    assert cancelled_attrs("_on_theme_change") == {"_canvas_bg_job_id"}, "主题切换未先取消上一支 job"
    assert cancelled_attrs("on_closing") == {"_close_dialog_grab_job_id"}, "对话框排 grab 时未先取消上一支 job"
    # 对话框的三条销毁路径（最小化 / 完全退出 / Escape）统一收口在 close_dialog，也必须取消。
    fn_close = _method_body(_GUI_SOURCE, _GUI_TREE, "on_closing")
    inner = [node for node in ast.walk(fn_close) if isinstance(node, ast.FunctionDef) and node.name == "close_dialog"]
    assert inner, "on_closing 的三条销毁路径未收口到 close_dialog"
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "after_cancel"
        or isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "_cancel_after_job"
        for node in ast.walk(inner[0])
    ), "close_dialog 必须取消尚未触发的延迟 grab"
    assert cancelled_attrs("_finalize_quit") == {
        "_canvas_bg_job_id",
        "_close_dialog_grab_job_id",
    }, "退出收尾漏取消一次性 job"


# ─── M-75：三条绝对路径进日志前必须过脱敏 ────────────────────────────────────────


_MASKED_PATH_MSGIDS = ("已打开下载目录: {path}", "执行程序: {path}", "工作目录: {path}")


def test_absolute_paths_are_masked_before_logging() -> None:
    # 同一文件对字体路径早已走 mask_credentials（那条红线的既有落点），这三处是同红线上的遗漏：
    # logs/gui.log 按大小轮转保留多份，未脱敏的路径等于长期落盘。
    # 判据走 AST：只认「tr 模板属于这三条、且 path= 实参是 mask_credentials(...) 调用」，
    # 不钉源码文本子串（M-26 的教训：字面量文本锁会在契约反转后静默空洞成立）。
    seen: dict[str, bool] = {msgid: False for msgid in _MASKED_PATH_MSGIDS}
    tr_count = 0
    for node in ast.walk(_GUI_TREE):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_log"):
            continue
        for inner in ast.walk(node):
            if not (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) and inner.func.attr == "tr"):
                continue
            if not (inner.args and isinstance(inner.args[0], ast.Constant)):
                continue
            template = inner.args[0].value
            if not isinstance(template, str) or template not in seen:
                continue
            tr_count += 1
            path_kw = next((kw for kw in inner.keywords if kw.arg == "path"), None)
            masked = (
                path_kw is not None
                and isinstance(path_kw.value, ast.Call)
                and isinstance(path_kw.value.func, ast.Name)
                and path_kw.value.func.id == "mask_credentials"
            )
            assert masked, f"路径未经 mask_credentials 脱敏就进日志: {template}"
            seen[template] = True
    # 反向见证：判据必须真的看见这三处，否则「全部通过」只说明什么都没扫到。
    assert tr_count == 3, f"三条路径日志点的枚举面失效（应恰好 3 处，实得 {tr_count}）: {seen}"
    assert all(seen.values()), f"有路径日志点不再调用 tr()，判据失去基准: {seen}"
