# tests/test_gui_qt_units.py — src/gui_qt 里「不靠真窗也能驱动」的四个模块的单元锁。
#
# 为什么单独成文件而不是并进 test_gui_qt_window.py：那一份走的是「离屏真窗 + 行为断言」，
# 建一个 MainWindow 约 0.6s；而 shared / danmaku_monitor / recorder 的大部分是纯函数与
# 线程/进程逻辑，用假进程与假 JSONL 驱动更快也更能钉住边界（超时、脏数据、单飞闸门）。
# 逐模块覆盖率门禁（scripts/check_coverage.py）对 src/ 下新模块按 50% 下限判定，
# 本文件是 shared / danmaku_monitor / recorder / settings_dialog / app 五处读数的主要来源。
#
# 锁什么（都是旧 tkinter 版踩过、迁移期最容易丢的判据）：
#   · shared：外部数值容错、跨进程配置变更裁决（conflict/reload/unchanged 三态）；
#   · danmaku_monitor：逐事件防护（一条脏事件不得吃掉同批其余事件）+ stop_event 随线程新建；
#   · recorder：session_id 迟到回调、_stopping 复位早于会话校验、停止/退出共用单飞闸门；
#   · settings_dialog：外部改动后「有未保存编辑」与「无编辑」走两条不同路径。

import json
import os
import signal as signal_module
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from typing import Callable, Iterator

import pytest

pytest.importorskip("PySide6", reason="PySide6 未安装时跳过 Qt 窗口层用例（环境限制口径）")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import i18n  # noqa: E402
from src.gui_qt import app as app_module  # noqa: E402
from src.gui_qt import recorder as recorder_module  # noqa: E402
from src.gui_qt import shared  # noqa: E402
from src.gui_qt.danmaku_monitor import DanmakuMonitor  # noqa: E402
from src.gui_qt.recorder import RecorderController  # noqa: E402
from src.gui_qt.settings_dialog import AdvancedSettingsDialog  # noqa: E402


@pytest.fixture(scope="module")
def qt_app() -> Iterator[QApplication]:
    # 控制器与对话框都是 QObject/QWidget：PySide6 要求先有 QApplication 实例，
    # 否则部分路径（QMessageBox 静态构造）在离屏后端下直接崩。
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance  # type: ignore[misc]


# ─── shared：数值容错 ───


def test_as_float_as_int_fall_back_on_dirty_external_data() -> None:
    # 边车 JSONL 是外部可控数据：null / 空串 / 非数值串都必须回落默认值而不是抛
    assert shared.as_float(None) == 0.0
    assert shared.as_float("") == 0.0
    assert shared.as_float("abc", 1.5) == 1.5
    assert shared.as_float("1.5") == 1.5
    assert shared.as_int(None) == 0
    assert shared.as_int("x", 7) == 7
    assert shared.as_int("12") == 12
    # OverflowError 在列：JSON 的 Infinity 字面量经 float 再 int() 会抛它
    assert shared.as_int(float("inf"), 3) == 3


def test_quality_alert_expired_uses_time_ordering_not_quality_text() -> None:
    # 未降级永远不谈「过期」（否则会把正常房间反复清一遍）
    assert shared.quality_alert_expired({"downgraded": False}, 1e9) is False
    # alert_at 脏数据（非数值）按「很久以前」处理：宁可清掉可疑标记，也不要永久红着一行
    assert shared.quality_alert_expired({"downgraded": True, "alert_at": "x"}, 1e9) is True
    # alert_at <= 0 表示「还没有告警时刻」，不得判为已过期
    assert shared.quality_alert_expired({"downgraded": True, "alert_at": 0}, 1e9) is False
    assert shared.quality_alert_expired({"downgraded": True, "alert_at": 1e9 - 10}, 1e9) is False
    assert shared.quality_alert_expired({"downgraded": True, "alert_at": 1e9 - 10_000}, 1e9) is True


# ─── shared：配置变更裁决 ───


def test_config_change_verdict_three_states() -> None:
    baseline = "a = 1\n"
    assert shared.config_change_verdict(baseline, baseline, "a = 2\n", baseline) == "unchanged"
    # 磁盘改过、编辑器无改动：静默跟随磁盘（不打断正在看配置的用户）
    assert shared.config_change_verdict(baseline, "a = 9\n", "a = 1\n", baseline) == "reload"
    # 磁盘改过、编辑器也有改动：必须交用户裁决
    assert shared.config_change_verdict(baseline, "a = 9\n", "a = 2\n", baseline) == "conflict"
    # 「当时没读到」与任何已读到的内容都不相等
    assert shared.config_change_verdict(None, "a = 9\n", "a = 2\n", baseline) == "conflict"
    assert shared.config_change_verdict(baseline, None, "a = 2\n", baseline) == "conflict"
    assert shared.snapshots_equal(None, None) is True
    assert shared.snapshots_equal(None, "x") is False


def test_normalize_editor_text_strips_trailing_newlines() -> None:
    # 编辑器控件在末尾多给一个换行，基线必须同口径存，否则一行未改会被判成 conflict
    assert shared.normalize_editor_text("a\n\n") == "a"
    assert shared.normalize_editor_text("") == ""


def test_read_config_snapshot_and_atomic_save(tmp_path: Path) -> None:
    target = tmp_path / "config.ini"
    # 缺文件：(None, None) —— 与「读到了空串」区分开，后者是真实内容
    assert shared.read_config_snapshot(str(target)) == (None, None)
    shared.save_text_to_file("[录制设置]\n", str(target))
    content, mtime = shared.read_config_snapshot(str(target))
    assert content is not None and mtime is not None
    assert "录制设置" in content
    # 保存会补末尾换行：再存一次内容不变（幂等），否则下一轮会误判成外部改动
    shared.save_text_to_file(content, str(target))
    again, _ = shared.read_config_snapshot(str(target))
    assert again == content


def test_process_kill_hint_takes_first_non_empty_line() -> None:
    assert shared.process_kill_hint(None, b"") == ""
    # 字节字面量只能含 ASCII（本地化消息用 encode 产出），ASCII 一条已足够覆盖「取首个非空行」
    assert shared.process_kill_hint(b"\r\ninfo: no running task.\r\n") == "info: no running task."
    # 不可信文本走同一道脱敏口径
    assert "secret" not in shared.process_kill_hint(b"http://u:p@example.com/?token=secret")


def test_cleanup_process_tree_without_pid_only_logs() -> None:
    seen: list[str] = []
    shared.cleanup_process_tree(None, lambda msg, level="info": seen.append(msg))
    assert seen and "ffmpeg" in seen[0]


# ─── shared：状态行匹配 ───


def test_status_patterns_match_production_lines_under_pinned_language() -> None:
    # M-14：正则必须由 tr() 后的形态派生，故按语言组装；conftest 把 tr 钉成恒等映射，
    # 这里显式钉 zh_CN 让「模板 → 正则 → 命中真实状态行」整条链可被断言。
    previous = i18n.get_language()
    i18n.set_language("zh_CN")
    try:
        patterns = shared.status_patterns()
        assert patterns.recording is not None
        assert patterns.downgrade is not None
        match = patterns.recording.search("主播A[原画] 正在录制中 00:01:02")
        assert match is not None and match.group("recording_live") == "主播A"
        # F-06：主播名里的 [...] 不得被当成画质段边界，画质取最后一个 [...]
        tricky = patterns.recording.search("房间[测试][高清] 正在录制中 1")
        assert tricky is not None and tricky.group("qa") == "高清"
        down = patterns.downgrade.search("主播B 画质降级：设置 原画(OD) 实际 高清(HD)")
        assert down is not None and down.group("record_name") == "主播B"
        assert any(needle in "没有正在录制的直播 循环监测间隔时间：60秒" for needle in patterns.idle_needles)
    finally:
        i18n.set_language(previous)


def test_status_pattern_cache_is_per_language() -> None:
    # 缓存键是语言码：同一语言两次取到同一对象，换语言后不得复用（否则简中串被钉死）
    previous = i18n.get_language()
    i18n.set_language("zh_CN")
    try:
        assert shared.status_patterns() is shared.status_patterns()
    finally:
        i18n.set_language(previous)


# ─── danmaku_monitor ───


def _noop_log(message: str, level: str = "info") -> None:
    # 具名函数而不是 lambda：mypy 推不出「带默认实参的 lambda」的类型（[misc] 报不出来就红）
    return None


def _collecting_log(sink: list[tuple[str, str]]) -> Callable[[str, str], None]:
    def _log(message: str, level: str = "info") -> None:
        sink.append((message, level))

    return _log


def _write_jsonl(path: Path, events: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
            f.flush()


def test_danmaku_dispatch_covers_conn_msg_stats() -> None:
    monitor = DanmakuMonitor("unused.jsonl", _noop_log)
    monitor._dispatch({"ev": "conn", "room": "A", "state": "started", "platform": "抖音", "ts": None})
    monitor._dispatch({"ev": "conn", "room": "A", "state": "ready"})
    assert monitor.rooms_snapshot()["A"]["connected"] is True
    # stats 是权威来源：四个计数覆盖而非累加
    monitor._dispatch({"ev": "stats", "room": "A", "msg_total": None, "msg_rate": "3", "online": 5})
    room = monitor.rooms_snapshot()["A"]
    assert room["msg_total"] == 0, "null 计数必须回落 0 而不是抛"
    assert room["msg_rate"] == 3
    monitor._dispatch({"ev": "msg", "room": "A", "user": "u", "text": "hi", "type": "chat"})
    assert len(monitor.messages_snapshot()) == 1
    # dirty 是一次性消费标记
    assert monitor.consume_stats_dirty() is True
    assert monitor.consume_stats_dirty() is False
    assert monitor.consume_stream_dirty() is True
    monitor.clear()
    assert monitor.rooms_snapshot() == {} and monitor.messages_snapshot() == []
    monitor._dispatch({"ev": "conn", "room": "A", "state": "stopped"})
    assert "A" not in monitor.rooms_snapshot()


def test_danmaku_tail_loop_reads_file_and_survives_dirty_events(tmp_path: Path) -> None:
    logged: list[tuple[str, str]] = []
    jsonl = tmp_path / "logs" / "danmaku_monitor.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text("", encoding="utf-8")
    monitor = DanmakuMonitor(str(jsonl), _collecting_log(logged))
    monitor.start()
    try:
        # 一条脏事件（数值字段为 null）+ 两条完好事件：脏的必须只跳过自己
        _write_jsonl(jsonl, [{"ev": "stats", "room": "A", "msg_total": "oops"}])
        _write_jsonl(jsonl, [{"ev": "msg", "room": "A", "user": "u1", "text": "第一条", "type": "chat"}])
        _write_jsonl(jsonl, [{"ev": "msg", "room": "A", "user": "u2", "text": "第二条", "type": "gift"}])
        deadline = time.time() + 5.0
        while time.time() < deadline and len(monitor.messages_snapshot()) < 2:
            time.sleep(0.05)
        messages = monitor.messages_snapshot()
        assert [m.get("text") for m in messages] == ["第一条", "第二条"], "脏事件不得吃掉同批其余事件"
        # 坏 JSON 行与空行都被跳过，不留痕
        _write_jsonl(jsonl, [{"ev": "msg", "room": "A", "user": "u3", "text": "第三条", "type": "chat"}])
        with jsonl.open("a", encoding="utf-8") as f:
            f.write("{not json}\n\n")
        time.sleep(0.5)
        assert monitor.messages_snapshot()[-1].get("text") == "第三条"
    finally:
        monitor.stop()


def test_danmaku_stop_without_start_is_safe() -> None:
    # 未 start 就 stop（退出路径会走到）不得抛，也不得留下线程引用
    monitor = DanmakuMonitor("unused.jsonl", _noop_log)
    monitor.stop()
    assert monitor._thread is None


# ─── recorder ───


def _controller(tmp_path: Path) -> RecorderController:
    return RecorderController(
        urls_file=str(tmp_path / "URL_config.ini"),
        app_root=str(tmp_path),
        script_dir=str(tmp_path),
    )


def test_build_record_command_is_source_mode_outside_frozen(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    command = controller.build_record_command()
    assert command[-1].endswith("main.py")
    assert command[0] == sys.executable or command[0].endswith("python.exe")


def test_recorder_start_drains_batches_and_end_sentinel(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    # 假的「录制子进程」：印一行就退出，覆盖 Popen → 读线程 → 批次 → EOF 哨兵整条链
    controller.build_record_command = lambda: [sys.executable, "-c", "print('hello-from-child')"]  # type: ignore[method-assign]
    ok, pid, reason = controller.start()
    assert ok and pid is not None and reason == ""
    assert controller.is_running() is True
    deadline = time.time() + 10.0
    messages: list[tuple[str, str]] = []
    ended = False
    while time.time() < deadline:
        messages_part, ended_part, session = controller.drain()
        messages.extend(messages_part)
        if ended_part:
            ended = True
            assert session == controller.session_id()
            break
        time.sleep(0.05)
    assert ended, "子进程 EOF 后必须投出结束哨兵"
    assert any("hello-from-child" in line for line, _level in messages)
    # 哨兵消费过后队列清空
    assert controller.has_queue_data() is False


def test_recorder_stop_resets_flags_and_emits_ended(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path)
    # 假子进程跑长一点，让「停止」真的走上「发信号 → 等待退出」这条路径
    controller.build_record_command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]  # type: ignore[method-assign]
    seen_sessions: list[int] = []
    controller.ended.connect(lambda session: seen_sessions.append(int(session)))  # type: ignore[arg-type]
    _ok, pid, _reason = controller.start()
    assert controller.is_running() is True and pid is not None

    def _fake_ctrl_break(child_pid: int) -> bool:
        # 真发 CTRL_BREAK 会让本进程 FreeConsole/AttachConsole，pytest 的 stdout 会跟着丢；
        # 这里只取代「信号送达」这一步，等待与收尾路径仍是真的。
        try:
            os.kill(child_pid, signal_module.SIGTERM)
        except OSError:
            return False
        return True

    monkeypatch.setattr(recorder_module, "send_ctrl_break_to_child", _fake_ctrl_break)
    assert controller.stop_async() is True
    deadline = time.time() + 20.0
    # 必须泵事件循环：ended 由工作线程 emit，跨线程连接是 Queued，
    # 没有事件循环运行时槽函数永远不会被投递（离屏测试里最容易误判成「没 emit」）。
    while time.time() < deadline and (controller.is_stopping() or controller.is_running() or not seen_sessions):
        qt_app.processEvents()
        time.sleep(0.05)
    assert controller.is_stopping() is False, "_stopping 复位必须早于会话校验（MI-08）"
    assert controller.is_running() is False
    assert seen_sessions, "停止收尾必须 emit 会话号，否则 UI 不回弹"
    assert controller.stop_async() is False, "进程已清空后不得再排一次停止"


def test_start_rejected_while_stopping_in_flight(qt_app: QApplication, tmp_path: Path) -> None:
    # 停止窗口内禁止再次启动：直接置位断言（白盒但确定性）——用真线程抢这个窗口会写出
    # 时快时慢的用例，而这里要锁的是「闸门存在」而不是「时序」。
    controller = _controller(tmp_path)
    controller._stopping = True  # noqa: SLF001 - 单元测试直接置位，与生产同模块
    ok, pid, reason = controller.start()
    assert ok is False and pid is None and reason == "stopping"


def test_recorder_shutdown_without_process_still_calls_finish(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    finished = threading.Event()
    controller.shutdown_async(on_finished=finished.set)
    assert finished.wait(timeout=10.0), "退出路径必须回调主线程收尾，否则窗口永不销毁"


def test_send_stop_signal_and_wait_graceful_path(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path)
    # 真发 CTRL_BREAK 会让本进程 FreeConsole/AttachConsole，pytest 的 stdout 会跟着丢；
    # 这里只验证「信号 → 等待 → 优雅退出」的分支走向，控制台附着本身由 shared 单独守。
    monkeypatch.setattr(recorder_module, "send_ctrl_break_to_child", lambda pid: True)
    proc = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, text=True)
    try:
        assert controller._send_stop_signal_and_wait(proc) is True
        assert proc.poll() is not None
    finally:
        proc.wait(timeout=5)


def test_send_stop_signal_and_wait_hard_kill_path(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    controller = _controller(tmp_path)
    monkeypatch.setattr(recorder_module, "send_ctrl_break_to_child", lambda pid: False)

    class _Result:
        returncode = 0
        stdout = b""
        stderr = b""

    # 只替换被测模块里的 subprocess 名字（浅拷贝 shim），不改写 stdlib 模块本体：
    # test_test_hygiene 的 R1 锁把 monkeypatch.setattr(subprocess, "run", ...) 判为全进程生效的改写
    # （loguru enqueue 线程 / coverage 都会吃到假 run），必须走 shim 形态。
    subprocess_shim = types.SimpleNamespace(**vars(recorder_module.subprocess))
    subprocess_shim.run = lambda *a, **k: _Result()
    monkeypatch.setattr(recorder_module, "subprocess", subprocess_shim)
    proc = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, text=True)
    try:
        # 信号发不出去 → 走整树强杀，且不得宣称「ffmpeg 已由子进程清理」
        assert controller._send_stop_signal_and_wait(proc) is False
        assert proc.poll() is not None
    finally:
        proc.wait(timeout=5)


def test_stop_child_once_skips_when_process_already_gone(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, text=True)
    proc.wait(timeout=5)
    # 拿锁后复核 poll()：已退出的进程不得再发一遍信号（否则只是把日志刷脏）
    controller._stop_child_once(proc)
    assert controller.is_stopping() is False


def test_recorder_readonly_state_and_skip_note(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    assert controller.pid() is None
    assert controller.is_running() is False
    assert controller.is_stopping() is False
    assert controller.output_thread_alive() is False
    logs: list[str] = []
    controller.logRequested.connect(lambda msg, level="info": logs.append(msg))  # type: ignore[arg-type]
    controller.note_finish_skip()
    assert logs and "输出线程" in logs[0]


# ─── settings_dialog ───


def test_advanced_settings_dialog_loads_saves_and_follows_disk(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_file = tmp_path / "config.ini"
    config_file.write_text("[录制设置]\n循环时间(秒) = 60\n", encoding="utf-8-sig")
    dialog = AdvancedSettingsDialog(None, str(config_file), lambda msg: None)
    try:
        assert "循环时间(秒) = 60" in dialog._editor_content()
        dialog.editor.setPlainText("[录制设置]\n循环时间(秒) = 30\n")
        dialog.save_config()
        assert "循环时间(秒) = 30" in config_file.read_text(encoding="utf-8-sig")
        # 磁盘被外部改动且编辑器无改动 → 静默跟随磁盘（reload）
        config_file.write_text("[录制设置]\n循环时间(秒) = 90\n", encoding="utf-8-sig")
        dialog._watch_config_file()
        assert "循环时间(秒) = 90" in dialog._editor_content()
        # 有未保存编辑时不得覆盖：磁盘再被改一次才走到 conflict 分支（上一次已同步快照）
        dialog.editor.setPlainText("[录制设置]\n循环时间(秒) = 45\n")
        config_file.write_text("[录制设置]\n循环时间(秒) = 99\n", encoding="utf-8-sig")
        dialog._watch_config_file()
        assert dialog._conflict_hint_shown is True
        assert "循环时间(秒) = 45" in dialog._editor_content(), "有未保存编辑时外部改动不得覆盖编辑器"
        # 保存时命中 conflict 且用户选「否」→ 保持打开、不写盘
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.No)
        dialog.save_config()
        assert "循环时间(秒) = 99" in config_file.read_text(encoding="utf-8-sig")
    finally:
        dialog.close()


# ─── app：崩溃兜底 ───


def _run_main_with_stubs(monkeypatch: pytest.MonkeyPatch) -> tuple[dict[str, object], dict[str, object]]:
    # main() 的终点是 Qt 的事件循环入口（测试进程里真调即阻塞到退出），
    # 故把 QApplication 与 MainWindow 换成替身，锁的是**装配顺序与接线**而不是 Qt 行为：
    # 「最后一个窗口关闭即退出」必须关掉（托盘模式下窗口是隐藏的），崩溃钩子必须装上。
    class _FakeApp:
        def __init__(self, argv: list[str]) -> None:
            self.argv = list(argv)
            self.name = ""
            self.quit_on_last_window_closed = True

        def setApplicationName(self, name: str) -> None:
            self.name = name

        def setQuitOnLastWindowClosed(self, flag: bool) -> None:
            self.quit_on_last_window_closed = flag

        def exec(self) -> int:
            return 0

    class _FakeQApplication:
        # 替身要同时吃两种用法：被当类调用构造实例、以及 QApplication.<类方法>。
        # 只给一个工厂函数会让后者 AttributeError（app.py 首行就调它）。
        def __init__(self) -> None:
            self.instances: list[_FakeApp] = []

        @staticmethod
        def setHighDpiScaleFactorRoundingPolicy(policy: object) -> None:
            return None

        def __call__(self, argv: list[str]) -> _FakeApp:
            instance = _FakeApp(argv)
            self.instances.append(instance)
            return instance

    class _FakeWindow:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = dict(kwargs)
            self.palette_applied = False
            self.shown = False

        def apply_palette(self) -> None:
            self.palette_applied = True

        def show(self) -> None:
            self.shown = True

    created: list[_FakeWindow] = []

    def _window_factory(**kwargs: object) -> _FakeWindow:
        window = _FakeWindow(**kwargs)
        created.append(window)
        return window

    app_factory = _FakeQApplication()
    monkeypatch.setattr("PySide6.QtWidgets.QApplication", app_factory)
    monkeypatch.setattr("src.gui_qt.main_window.MainWindow", _window_factory)
    monkeypatch.setattr(sys, "excepthook", sys.__excepthook__)

    app_module.main()

    assert len(app_factory.instances) == 1 and len(created) == 1
    fake_app = app_factory.instances[0]
    window = created[0]
    app_state = {
        "name": fake_app.name,
        "quit_on_last_window_closed": fake_app.quit_on_last_window_closed,
    }
    window_state = {
        "palette_applied": window.palette_applied,
        "shown": window.shown,
        **window.kwargs,
    }
    return app_state, window_state


def test_main_wires_application_and_shows_window(monkeypatch: pytest.MonkeyPatch) -> None:
    app_state, window_state = _run_main_with_stubs(monkeypatch)
    assert app_state["quit_on_last_window_closed"] is False, "托盘模式下不得随最后一个窗口关闭而退出"
    assert app_state["name"] == "DouyinLiveRecorder"
    assert sys.excepthook is app_module._crash_sink
    assert window_state["palette_applied"] is True and window_state["shown"] is True
    # 源码运行：src/gui_qt/app.py 向上三级才是项目根，配置与下载目录都从它派生
    app_root = str(window_state["app_root"])
    assert os.path.isdir(os.path.join(app_root, "src"))
    assert window_state["main_config_file"] == os.path.join(app_root, "config", "config.ini")
    assert window_state["downloads_dir"] == os.path.join(app_root, "downloads")


def test_main_uses_internal_parent_as_app_root_when_frozen(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # 冻结后模块落在 exe 同级的 _internal/，而 config/ ffmpeg/ 等资源在它**父目录**：
    # 这条分支只差一次 basename 判定，走错了就是「冻结版读不到配置」。
    internal = tmp_path / "_internal"
    internal.mkdir()
    monkeypatch.setattr(app_module, "__file__", str(internal / "app.py"))
    _app_state, window_state = _run_main_with_stubs(monkeypatch)
    assert str(window_state["app_root"]) == str(tmp_path)


def test_crash_sink_writes_file_and_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # QMessageBox 在离屏后端下 exec() 会阻塞，故换成不弹窗的替身；
    # 被替掉的只是「弹窗」这一步，落盘那条路径仍是真的。
    class _Box:
        def setWindowTitle(self, _title: str) -> None:
            return None

        def setText(self, _text: str) -> None:
            return None

        def exec(self) -> int:
            return 0

    monkeypatch.setattr("PySide6.QtWidgets.QMessageBox", _Box)
    try:
        raise RuntimeError("boom-for-crash-sink")
    except RuntimeError as exc:
        app_module._crash_sink(type(exc), exc, exc.__traceback__)
    log_path = os.path.join(__import__("tempfile").gettempdir(), "dlr_gui_crash.log")
    assert os.path.isfile(log_path)
    with open(log_path, "r", encoding="utf-8") as f:
        assert "boom-for-crash-sink" in f.read()
