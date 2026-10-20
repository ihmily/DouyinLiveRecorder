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
#   · widgets.fixed_font：等宽族名只能是**单个** family、按候选取本机第一个命中的，
#     候选全缺时交回系统固定宽度字体（2026-10-17 用户日志的两条字体告警即出自旧写法）。
#   · widgets.TerminalText.apply_highlighter：高亮器对同一 document 单实例复用（M-16）。
#   · 真窗语言热切换（M-13/M-14）：本文件头注「不靠真窗」口径的**刻意例外**——
#     「登记表回填把运行态打回初值」「静态标签原地停旧语言」两类形态只有真控件树 +
#     真翻译目录才测得出来，假控件对象走不了 set_text→setText 的 Qt 面；
#     夹具与 tests/test_gui_qt_window.py 同源（登记表按用例快照还原，防存活条目
#     留给按全局条数断言的 tests/test_ui_i18n.py）。

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

# 为什么是「按子模块探测 + 显式放宽 exc_type」（2026-10-18 CI 实测事故）：
# pytest 9.1 起 importorskip 的 exc_type 缺省值由 ImportError 改为 ModuleNotFoundError
# （见 _pytest.outcomes.importorskip 的 docstring：`Defaults to ModuleNotFoundError when not
# given`），而 PySide6 缺 Qt 系统库时失败发生在 **QtGui / QtWidgets 子模块的 dlopen**
# （ubuntu runner 无 libEGL.so.1），顶层 `import PySide6` 照样成功。于是只看顶层包时这一行
# 恒成立，紧随其后的 `from PySide6.QtGui import ...` 抛 ImportError —— 模块级 import 期异常
# 会被 pytest 计为 collection error 并 **中断整轮**（实测 4337 collected / 2 errors →
# Interrupted，exit code 2，其余用例一条没跑、覆盖率与逐模块门禁全部拿不到数据）。
# 故此处直接探测真正要 import 的子模块，并把 exc_type 放宽到 ImportError：环境真的没有 Qt
# 时应走 skip 通道，而不是把整轮 pytest 打成 Interrupted。
pytest.importorskip(
    "PySide6.QtGui", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 窗口层用例（环境限制口径）"
)
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 窗口层用例（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QSyntaxHighlighter  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QSystemTrayIcon  # noqa: E402

import i18n  # noqa: E402
from src import ui_i18n  # noqa: E402
from src.gui_qt import app as app_module  # noqa: E402
from src.gui_qt import recorder as recorder_module  # noqa: E402
from src.gui_qt import shared  # noqa: E402
from src.gui_qt import theme as theme_module  # noqa: E402
from src.gui_qt import widgets as widgets_module  # noqa: E402
from src.gui_qt.danmaku_monitor import DanmakuMonitor  # noqa: E402
from src.gui_qt.main_window import MainWindow  # noqa: E402
from src.gui_qt.recorder import RecorderController  # noqa: E402
from src.gui_qt.settings_dialog import AdvancedSettingsDialog  # noqa: E402
from src.gui_qt.tray import TrayIcon  # noqa: E402
from src.gui_qt.widgets import TerminalText, fixed_font  # noqa: E402


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
        # 坏 JSON 行与空行都被跳过、不留痕。写入顺序刻意把坏行放在「第三条」之前：
        # tail 线程按文件顺序消费，「第三条」能落到末位，本身就是坏行已被跳过且线程
        # 仍活着的**行为见证**——不再用固定 sleep 赌时序（MT-06：轮询周期 0.3s 配
        # sleep(0.5) 在 CI 高负载下余量不足，偶发假红）。等待改用本文件上半段同款
        # 的 deadline 轮询（5s 上限），不另发明第二套等待工具。
        with jsonl.open("a", encoding="utf-8") as f:
            f.write("{not json}\n\n")
        _write_jsonl(jsonl, [{"ev": "msg", "room": "A", "user": "u3", "text": "第三条", "type": "chat"}])
        deadline = time.time() + 5.0
        while time.time() < deadline and monitor.messages_snapshot()[-1].get("text") != "第三条":
            time.sleep(0.05)
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


# ─── widgets.fixed_font：等宽族名 ─────────────────────────────────────────
# 判据一律走「打桩后的 QFontDatabase」：真实字体表随机变化（装了 Consolas 的机器上旧写法
# QFont("Consolas, Menlo, Courier New, monospace") 侥幸命中，没装的那台机器上 Qt 按
# styleHint=Monospace（枚举值 7，与用户日志里 styleHint=7 对上）落进遗留别名表里的
# "Terminal"，打出 DirectWrite 创建失败 + QFont::setPointSize: Point size <= 0 (-1) 两条告警）。
# 不打桩的用例在 CI 上既可能全绿也可能全红，钉不住任何东西。


def test_fixed_font_uses_one_family_and_first_hit(qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda: ["Menlo", "Noto Mono"]))
    font = fixed_font(11)
    # 本机没有 Consolas 才轮到候选表第二项 Menlo；族名位始终是**单个** family
    assert font.family() == "Menlo"
    assert "," not in font.family()
    assert font.styleHint() == QFont.StyleHint.Monospace
    assert font.pointSize() == 11


def test_fixed_font_family_match_is_case_insensitive(qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    # 字体表里的大小写随平台/字体而异，匹配须忽略大小写，而返回的仍是候选表里的规范拼写
    monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda: ["consolas"]))
    assert fixed_font().family() == "Consolas"
    # 不传 point_size 的站点刻意不设值：字号继续跟着 app/QSS 走（界面缩放档位要吃这条）。
    # 判据与「同族名、未经工厂处理」的裸 QFont 对照，避免把 Qt 自身的默认值写进断言里
    # （那会随平台字体表变化而红）。
    assert fixed_font().pointSize() == QFont("Consolas").pointSize()
    assert fixed_font(11).pointSize() == 11


def test_fixed_font_falls_back_to_system_fixed_font(qt_app: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(QFontDatabase, "families", staticmethod(lambda: ["Zzz Not A Match"]))
    marker = QFont("DlrMarkerMono")
    monkeypatch.setattr(QFontDatabase, "systemFont", staticmethod(lambda _font: marker))
    got = fixed_font(9)
    # 候选全缺时不再猜名字（旧写法正是在这一步落到 "Terminal"），改交平台的系统固定宽度字体
    assert got.family() == "DlrMarkerMono"
    assert got.pointSize() == 9


# ─── widgets.TerminalText.apply_highlighter：单实例复用（M-16） ───────────


def test_apply_highlighter_attaches_once_and_only_recolors(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-16 行为锁：主题/缩放/字体切换每次都走 apply_highlighter，旧实现在此处新建
    # _LogHighlighter 挂同一 document——QSyntaxHighlighter 以 document 为父对象，
    # 旧实例永不销毁且继续参与高亮：切 N 次叠 N 个，旧行被旧配色反复重着色、
    # 全文档重复高亮 N 份开销。取证面是 document 的 children 里 QSyntaxHighlighter
    # 的个数（Qt 没有公开的「列出全部高亮器」API，父子关系是唯一可机检形态）。
    term = TerminalText()
    rehighlighted: list[int] = []
    # 桩在类层而不是实例层（PySide6 对象上逐实例改写 C++ 方法不可靠）；monkeypatch 还原。
    monkeypatch.setattr(widgets_module._LogHighlighter, "rehighlight", lambda self: rehighlighted.append(1))
    light = theme_module.palette(theme_module.THEME_LIGHT, 1.0)
    dark = theme_module.palette(theme_module.THEME_DARK, 1.0)
    term.apply_highlighter(light)
    assert term._highlighter is not None  # noqa: SLF001 - 白盒确认首建已挂载
    term.append_line("[ERROR] 旧行留在文档里\n")
    term.apply_highlighter(dark)
    term.apply_highlighter(light)
    term.apply_highlighter(dark)
    stacked = [child for child in term.document().children() if isinstance(child, QSyntaxHighlighter)]
    assert len(stacked) == 1, f"切了 4 次主题后 document 上挂着 {len(stacked)} 个高亮器（M-16 回归：旧实例未复用）"
    assert stacked[0] is term._highlighter  # noqa: SLF001 - 复用中的实例就是自持的那一个
    # 复用不得停在首建配色：色表必须跟随最新 palette（否则「主题切换对终端永久失效」，
    # 而且颜色必须仍取自 theme.py 令牌而不是控件上写死的十六进制）。
    expected = QColor(dark.token("terminal_error")).name()
    assert term._highlighter._formats["error"].foreground().color().name() == expected  # noqa: SLF001
    # 首建不重刷（空文档重刷等于白扫），此后每次 set_palette 恰好一次 rehighlight（旧行重着色）。
    assert rehighlighted == [
        1,
        1,
        1,
    ], "每次切换主题必须且只能触发一次 rehighlight：去掉它旧行停在旧配色，多触发是重复开销"


# ─── M-13/M-14：真窗语言热切换的整窗回填 ─────────────────────────────────


def _fail_fast_box(*_args: object, **_kwargs: object) -> int:
    # 用例期间任何预期外的模态弹窗都会把离屏用例钉死，一律快速失败而不是放行。
    raise AssertionError("用例期间出现了预期外的模态弹窗")


@pytest.fixture()
def lang_window(qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    # 夹具与 tests/test_gui_qt_window.py 的 window 同源：登记表按用例快照还原
    # （Qt 顶层窗口在 QApplication 存活期不释放，不还原会把存活条目留给
    # 按全局条数断言的 tests/test_ui_i18n.py）。启动语言钉成 zh_CN：
    # 解析缺省会跟随宿主系统语言，用例结论不能随机器漂移。
    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001 - 测试还原全局登记表，与生产同模块
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    url_file = config_dir / "URL_config.ini"
    url_file.write_text("https://live.douyin.com/1234 原画 主播A\n", encoding="utf-8-sig")
    main_file = config_dir / "config.ini"
    main_file.write_text("[录制设置]\nlanguage = zh_CN\n循环时间(秒) = 60\n", encoding="utf-8-sig")
    monkeypatch.setattr(QMessageBox, "warning", _fail_fast_box)
    monkeypatch.setattr(QMessageBox, "critical", _fail_fast_box)
    saved_language = i18n.get_language()
    win = MainWindow(
        app_root=str(tmp_path),
        script_dir=str(tmp_path),
        url_config_file=str(url_file),
        main_config_file=str(main_file),
        downloads_dir=str(tmp_path / "downloads"),
    )
    win.apply_palette()
    assert i18n.get_language() == "zh_CN"
    yield win
    win._finalize_quit()  # noqa: SLF001 - 夹具收尾走生产退出序列（停三条链、关弹幕尾线程）
    win.deleteLater()
    qt_app.processEvents()
    i18n.set_language(saved_language)
    ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001 - 同上


def _switch_to_en_us(win: MainWindow) -> None:
    index = win.language_combo.findData("en_US")
    assert index >= 0, "语言下拉必须含 en_US，否则本组判据失去取证面"
    win.language_combo.setCurrentIndex(index)
    assert i18n.get_language() == "en_US"


def test_running_status_text_survives_retranslate_and_follows_language(
    qt_app: QApplication, lang_window: MainWindow
) -> None:
    # M-13 行为锁：状态标题/副标题是运行态文案，既不能被 retranslate_all() 的回填打回
    # 登记初值「待机」，也必须随语言切换按当前 recorder 状态重驱（四处投影一致）。
    win = lang_window
    # 进入「录制中」形态：白盒置 _running 让 is_running() 为真即可——本判据考的是切换钩子
    # 的重驱通路，与真子进程无关。只调 _set_running_ui(True) 不够：切换钩子会**重读**
    # is_running() 决定形态，真实态为 False 时被重驱回「待机」，那反而是正确的生产行为。
    win.recorder._running = True  # noqa: SLF001 - 单元测试直接置位，与生产同模块
    win._set_running_ui(True)  # noqa: SLF001 - 直接驱动唯一运行态出口
    title_zh = win.dashboard.status_title.text()
    assert title_zh == i18n.tr("录制中")
    # 判据一：单纯回填不得动运行态文案——旧实现把 status_title 登记进表，这一步就会把它
    # 打回「待机」（与侧栏/托盘矛盾的确切形态）。
    ui_i18n.retranslate_all()
    assert (
        win.dashboard.status_title.text() == title_zh
    ), "运行态状态标题被登记进了重译表：retranslate_all() 会把「录制中」打回登记初值「待机」（M-13）"
    # 判据二：切语言后运行态按当前 recorder 状态重驱（recorder 未真起进程，但 _running
    # 由 _set_running_ui 的入参驱动，这里保持「录制中」投影不变即可取证）。
    _switch_to_en_us(win)
    assert win.dashboard.status_title.text() == i18n.tr("录制中") != title_zh
    assert win.dashboard.status_sub.text() == i18n.tr("录制进程运行中 (PID: {pid})", pid=win.recorder.pid())
    assert win.sidebar_status.text() == i18n.tr("运行中") != "运行中"
    assert win.status_chip.text() == i18n.tr("运行中")
    if win.tray is not None:
        # 托盘状态项同属运行态（走 set_running 而不是登记表）；离屏/无 XDG Session 的
        # 机器上 _setup_tray 可能退化为 None，此处按可用性取证、不做伪绿。
        assert win.tray.status_action.text() == i18n.tr("录制中") != "录制中"


def test_static_labels_and_derived_title_follow_language_switch(qt_app: QApplication, lang_window: MainWindow) -> None:
    # M-14 行为锁：offscreen 真建页面读 text()——导航按钮（带 emoji 键）、品牌副标题、
    # 偏好说明标签、导入字体按钮、两张监控页的统计标题/空态/按钮，以及由导航文本派生的
    # 顶栏页标题，切语言后全部必须按当前目录重取；登记遗漏的形态是「原地停在旧语言」。
    win = lang_window
    before = {
        "nav_quality": win._nav_buttons["quality"].text(),  # noqa: SLF001 - 白盒读取导航按钮
        "nav_dashboard": win._nav_buttons["dashboard"].text(),  # noqa: SLF001
        "brand": win.brand_sub.text(),
        "import_font": win.import_font_btn.text(),
        "page_title": win.page_title.text(),
        "stat_total": win.quality_page.stat_total.title.text(),
        "stat_ok": win.quality_page.stat_ok.title.text(),
        "stat_down": win.quality_page.stat_down.title.text(),
        "empty_title": win.quality_page.empty.title.text(),
        "empty_desc": win.quality_page.empty.description.text(),
        "refresh": win.quality_page.refresh_btn.text(),
        "stat_rooms": win.danmaku_page.stat_rooms.title.text(),
        "stat_connected": win.danmaku_page.stat_connected.title.text(),
        "stat_msgs": win.danmaku_page.stat_msgs.title.text(),
        "dm_empty_title": win.danmaku_page.empty.title.text(),
        "dm_empty_desc": win.danmaku_page.empty.description.text(),
        "clear": win.danmaku_page.clear_btn.text(),
    }
    # 取证面自检：zh_CN 下这些文本就是源文；若宿主目录意外恒等，切换后「不变」无法区分
    # 「登记有效」与「根本没生效」——先证明英文目录对这些键确有译文。
    _switch_to_en_us(win)
    assert i18n.tr("🎯  画质监控") != before["nav_quality"], "英文目录未生效，本用例的区分力失效"
    assert win._nav_buttons["quality"].text() == i18n.tr("🎯  画质监控") != before["nav_quality"]  # noqa: SLF001
    assert win.brand_sub.text() == i18n.tr("直播录制 · 控制台") != before["brand"]
    assert win.import_font_btn.text() == i18n.tr("导入字体…") != before["import_font"]
    # 顶栏页标题是派生面（不进登记表）：必须等于「当前激活导航项」去掉 emoji 前缀后的形态。
    assert (
        win.page_title.text() == win._nav_buttons["dashboard"].text().split("  ")[-1] != before["page_title"]
    )  # noqa: SLF001
    assert win.quality_page.stat_total.title.text() == i18n.tr("录制直播间") != before["stat_total"]
    assert win.quality_page.stat_ok.title.text() == i18n.tr("画质正常") != before["stat_ok"]
    assert win.quality_page.stat_down.title.text() == i18n.tr("画质降级") != before["stat_down"]
    assert win.quality_page.empty.title.text() == i18n.tr("暂无录制中的直播间") != before["empty_title"]
    assert (
        win.quality_page.empty.description.text()
        == i18n.tr("启动录制后，将自动检测各直播间的实际画质是否与设置一致")
        != before["empty_desc"]
    )
    assert win.quality_page.refresh_btn.text() == i18n.tr("立即刷新") != before["refresh"]
    assert win.danmaku_page.stat_rooms.title.text() == i18n.tr("监控房间") != before["stat_rooms"]
    assert win.danmaku_page.stat_connected.title.text() == i18n.tr("已连接") != before["stat_connected"]
    assert win.danmaku_page.stat_msgs.title.text() == i18n.tr("弹幕总数") != before["stat_msgs"]
    assert win.danmaku_page.empty.title.text() == i18n.tr("暂无弹幕监控数据") != before["dm_empty_title"]
    assert (
        win.danmaku_page.empty.description.text()
        == i18n.tr("启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，支持弹幕的平台将显示实时弹幕")
        != before["dm_empty_desc"]
    )
    assert win.danmaku_page.clear_btn.text() == i18n.tr("清空") != before["clear"]
    # 侧栏偏好说明标签（objectName=dim，add_setting 建时定型）：四组 caption 整体换语言。
    dim_texts = {lb.text() for lb in win.findChildren(QLabel) if lb.objectName() == "dim"}
    assert dim_texts == {
        i18n.tr("界面主题"),
        i18n.tr("界面缩放"),
        i18n.tr("语言 Language"),
        i18n.tr("界面字体"),
    }, "侧栏偏好说明标签必须随重译登记表换语言（M-14）"
    if win.tray is not None:
        # 托盘菜单四条动作项随语言切换重取（旧 pystray 版靠 rebuild_menu 整体重建菜单，
        # Qt 版走 TrayIcon.retranslate）；2026-10-20 补齐的「隐藏主窗口」「设置」同在此列。
        # 右侧写死 msgid 字面量：只比 i18n.tr() 会在「目录未生效」时同侧等值而失去区分力。
        assert win.tray.show_action.text() == i18n.tr("显示主窗口") != "显示主窗口"
        assert win.tray.hide_action.text() == i18n.tr("隐藏主窗口") != "隐藏主窗口"
        assert win.tray.settings_action.text() == i18n.tr("设置") != "设置"
        assert win.tray.quit_action.text() == i18n.tr("彻底退出") != "彻底退出"


def test_tray_menu_action_items_are_wired_and_fire_in_menu_order(qt_app: QApplication) -> None:
    # 「隐藏主窗口」「设置」是 2026-10-20 相对旧 pystray 托盘补齐的两项（旧版菜单只有
    # 显示主界面 / 最小化到托盘 / 退出程序）。只断言 QAction 存在属伪绿——建了却不 connect
    # 的形态就是「点了没反应」，必须逐项 trigger() 看回调真被调到、且与菜单顺序一致。
    #
    # 直接构造 TrayIcon 而不是走 MainWindow._setup_tray()：后者在 isSystemTrayAvailable()
    # 为假（离屏 / 无 XDG Session）时把 tray 置成 None，那样本用例会退化成空跑，
    # 正是本仓反对的假绿面。
    tokens = theme_module.palette("light").tokens
    tray = TrayIcon(qt_app, tokens)
    fired: list[str] = []
    tray.bind_actions(
        lambda: fired.append("show"),
        lambda: fired.append("hide"),
        lambda: fired.append("quit"),
        lambda: fired.append("settings"),
    )
    # 菜单自上而下的**动作项**（状态项是纯展示、分隔符不是动作，两者都不进）
    assert [a.text() for a in tray.menu.actions() if a.isEnabled() and not a.isSeparator()] == [
        i18n.tr("显示主窗口"),
        i18n.tr("隐藏主窗口"),
        i18n.tr("设置"),
        i18n.tr("彻底退出"),
    ]
    # 状态项必须保持禁用：可点却无动作的菜单项是旧版没有的退化形态
    assert tray.status_action.isEnabled() is False
    for action in (tray.show_action, tray.hide_action, tray.settings_action, tray.quit_action):
        action.trigger()
    assert fired == ["show", "hide", "settings", "quit"]

    # 左键单击 / 双击同归「显示主窗口」；右键（Context）交给上下文菜单，在这里一并处理
    # 会让右键也弹一次窗口（旧版 pystray 的 MenuItem(default=True) 即同一语义）。
    fired.clear()
    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)  # noqa: SLF001 - 单元锁直驱私有回调
    tray._on_activated(QSystemTrayIcon.ActivationReason.DoubleClick)  # noqa: SLF001
    tray._on_activated(QSystemTrayIcon.ActivationReason.Context)  # noqa: SLF001
    assert fired == ["show", "show"]


def test_monitor_table_headers_and_filter_sentinel_follow_language_switch(
    qt_app: QApplication, lang_window: MainWindow
) -> None:
    # M-14 运行态重刷锁：两张监控表的表头与「全部房间」哨兵都在产生点 tr()，
    # refresh 对行内容等值时短路返回——语言切换后若不清上一轮缓存强制重画，旧语言原地常驻。
    win = lang_window
    assert win.danmaku_page.filter_combo.itemText(0) == "全部房间"
    _switch_to_en_us(win)
    assert str(win.danmaku_page.filter_combo.itemText(0)) == i18n.tr("全部房间") != "全部房间"
    # 表头随当前语言（model 层取证，不依赖控件可见性）。
    dm_header0 = str(win.danmaku_page._model.headerData(0, Qt.Orientation.Horizontal))  # noqa: SLF001
    assert dm_header0 == i18n.tr("房间") != "房间"
    qm_header0 = str(win.quality_page._model.headerData(0, Qt.Orientation.Horizontal))  # noqa: SLF001
    assert qm_header0 == i18n.tr("直播间") != "直播间"


def test_config_page_saved_buttons_exposes_both_control_buttons(qt_app: QApplication) -> None:
    # saved_buttons() 原注释声称「供测试断言按钮可用性（停止流程会禁用控制按钮）」，但 Qt 窗口层
    # 的停止流程只禁用 dashboard 的 start/stop 两键（src/gui_qt/main_window.py 的
    # `self.dashboard.start_btn.setEnabled(False)` 一段），从不触碰本页的 reload/save —— 按原注释
    # 写断言必然失败，于是该访问器长期零调用方（2026-10-20 死代码清点实测）。注释已按 AGENTS.md
    # 关键约定 #12 改成如实描述，本用例锁**真实存在**的契约：按 (reload, save) 顺序原样交出页面
    # 自己持有的那两个按钮对象——顺序反转、或换成另建的等价控件，都会让身份断言变红。
    from src.gui_qt.pages.config import ConfigPage

    # 建过 Qt 控件的测试文件必须还原 ui_i18n 登记表：ConfigPage 经 set_text 登记 4 条静态标签，
    # 存活条目会留给后面按「全局条数」断言的 tests/test_ui_i18n.py（与本文件 lang_window 夹具同法）。
    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001 - 测试还原全局登记表，与生产同模块
    try:
        page = ConfigPage()
        try:
            reload_btn, save_btn = page.saved_buttons()
            assert reload_btn is page.reload_btn, "首位必须是「重新读取」按钮本体"
            assert save_btn is page.save_btn, "次位必须是「保存 URL 配置」按钮本体"
            # 构建期两键均为可用态：这是当前真实行为（无任何流程禁用它们），不是「停止后仍可用」的断言。
            assert (reload_btn.isEnabled(), save_btn.isEnabled()) == (True, True)
        finally:
            page.deleteLater()
            qt_app.processEvents()
    finally:
        ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001 - 同上
