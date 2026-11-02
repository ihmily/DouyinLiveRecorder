# tests/test_gui_qt_units.py — src/gui_qt 里「不靠真窗也能驱动」的模块单元锁。
#
# 与 test_gui_qt_window.py 分工：那份走离屏真窗行为断言（建窗约 0.6s）；本文件用假进程与
# 假 JSONL 驱动 shared / danmaku_monitor / recorder / settings_dialog / app，更快且能钉住
# 超时、脏数据、单飞闸门等边界。scripts/check_coverage.py 对 src/ 新模块按 50% 下限判定，
# 本文件是上述五处读数的主要来源。
#
# 锁：shared 的数值容错与配置裁决三态；danmaku_monitor 的逐事件防护与 stop_event 随线程
# 新建；recorder 的 session_id 迟到回调、_stopping 复位早于会话校验、停止/退出单飞；
# settings_dialog 的 reload/conflict 两条路径；widgets.fixed_font 的单个 family 与首个
# 命中；TerminalText 高亮器单实例复用（M-16）与 WidgetWidth 自动换行（resize 随宽重排）；M-13/M-14 的真窗语言热切换——本文件
# 「不靠真窗」口径的刻意例外：登记表回填与「原地停旧语言」只有真控件树 + 真翻译目录
# 才测得出来（夹具与 test_gui_qt_window.py 同源，登记表按用例快照还原）。

import ast
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

# 按子模块探测并放宽 exc_type（CI 实测）：pytest 9.1 起 importorskip 的 exc_type
# 缺省为 ModuleNotFoundError，而缺 Qt 系统库时失败发生在 QtGui/QtWidgets 的 dlopen、顶层
# `import PySide6` 仍成功；紧随其后的 import 抛 ImportError 会被计为 collection error 并
# 中断整轮（实测 4337 collected / 2 errors）。环境没有 Qt 应走 skip，不该带走其余用例。
pytest.importorskip(
    "PySide6.QtGui", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 窗口层用例（环境限制口径）"
)
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 窗口层用例（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QFontDatabase, QSyntaxHighlighter  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPlainTextEdit, QSystemTrayIcon  # noqa: E402

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
        # tail 线程按文件顺序消费，「第三条」能落到末位即坏行已被跳过的行为见证。
        # 等待用 deadline 轮询而不是固定 sleep（MT-06：固定余量在 CI 高负载下会假红）。
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


# ─── recorder：i18n 迁移回归锁（AST 静态判据，零运行时依赖） ───
# M-04 回植：录制输出线程的 i18n 与脱敏两条锁曾在冲突解决时归零（生产实现健在，
# 从 f93c504 取回原用例）。


def test_recorder_log_messages_route_through_tr() -> None:
    # Qt 移植曾整批丢失 gui.py 的 tr() 迁移（已回填）：_log 首参一律经 i18n.tr 常量
    # 模板（占位符沿用目录登记的归一形态 {pid}/{path}/{err}/{type_name}），裸常量/裸 f-string
    # 在非 zh_CN 语言下永远渲染源文。判据只认「有价值的」首参——装饰线（"━" * 40 是 BinOp）
    # 与转发变量实参（Name）不在判据面内。模板是否登记进目录由 tests/test_i18n_migration.py
    # 的不变量③ runtime_templates_covered_by_catalog 跨仓把守，本用例只锁「调用形态」。
    source = (Path(__file__).resolve().parent.parent / "src" / "gui_qt" / "recorder.py").read_text(encoding="utf-8")
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_log"
            and node.args
        ):
            continue
        first = node.args[0]
        if isinstance(first, ast.JoinedStr):
            offenders.append(f"L{node.lineno}: 裸 f-string")
        elif isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value.strip():
            offenders.append(f"L{node.lineno}: 裸常量 {first.value!r}")
    assert not offenders, "recorder._log 存在绕过 tr() 的文案（移植丢失迁移的回归）: " + "; ".join(offenders)


def test_recorder_path_logging_masks_credentials() -> None:
    # 红线判据沿用「路径进日志前必须脱敏」的既有约束：「执行程序/工作目录」两条 {path}
    # 模板的 path= 实参必须是 mask_credentials(...) 调用。「未找到 console 解释器 {path}」
    # 刻意不在脱敏集合内——解释器位置属低敏诊断信息，不扩大红线范围。
    masked_msgids = ("执行程序: {path}", "工作目录: {path}")
    source = (Path(__file__).resolve().parent.parent / "src" / "gui_qt" / "recorder.py").read_text(encoding="utf-8")
    seen = 0
    for node in ast.walk(ast.parse(source)):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_log"
            and node.args
        ):
            continue
        for inner in ast.walk(node):
            if not (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "tr"
                and inner.args
                and isinstance(inner.args[0], ast.Constant)
                and isinstance(inner.args[0].value, str)
            ):
                continue
            template = inner.args[0].value
            if template not in masked_msgids:
                continue
            seen += 1
            path_kw = next((kw for kw in inner.keywords if kw.arg == "path"), None)
            masked = (
                path_kw is not None
                and isinstance(path_kw.value, ast.Call)
                and isinstance(path_kw.value.func, ast.Name)
                and path_kw.value.func.id == "mask_credentials"
            )
            assert masked, f"路径未经 mask_credentials 脱敏就进日志: {template!r}"
    # 反向见证：判据必须真的看见两条 {path} 日志点，否则「全部通过」只说明什么都没扫到
    assert seen == 2, f"路径日志点的枚举面失效（应恰好 2 处，实得 {seen}）"


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
    # 必须泵事件循环：ended 由工作线程 emit，跨线程连接是 Queued，没有事件循环时槽函数
    # 永不被投递（离屏测试里最容易误判成「没 emit」）。
    while time.time() < deadline and (controller.is_stopping() or controller.is_running() or not seen_sessions):
        qt_app.processEvents()
        time.sleep(0.05)
    assert controller.is_stopping() is False, "_stopping 复位必须早于会话校验（MI-08）"
    assert controller.is_running() is False
    assert seen_sessions, "停止收尾必须 emit 会话号，否则 UI 不回弹"
    assert controller.stop_async() is False, "进程已清空后不得再排一次停止"


def test_start_rejected_while_stopping_in_flight(qt_app: QApplication, tmp_path: Path) -> None:
    # 停止窗口内禁止再次启动：直接置位断言（白盒但确定性）——真线程抢窗口会写出时快时慢
    # 的用例，而这里要锁的是「闸门存在」而不是「时序」。
    controller = _controller(tmp_path)
    controller._stopping = True  # noqa: SLF001 - 单元测试直接置位，与生产同模块
    ok, pid, reason = controller.start()
    assert ok is False and pid is None and reason == "stopping"


def test_recorder_shutdown_without_process_still_calls_finish(qt_app: QApplication, tmp_path: Path) -> None:
    controller = _controller(tmp_path)
    finished = threading.Event()
    controller.shutdown_async(on_finished=finished.set)
    assert finished.wait(timeout=10.0), "退出路径必须回调主线程收尾，否则窗口永不销毁"


def test_stop_worker_body_with_vanished_process_still_emits_ended(qt_app: QApplication, tmp_path: Path) -> None:
    # M-79：「stop_async 已发起、按钮已按约定等 _on_recorder_ended 统一恢复，而句柄被
    # 自然 EOF 的 reclaim_after_natural_end 抢先清空」是两条通道并存的必然竞态。旧实现在
    # proc is None 分支只复位 _stopping 就 return、不 emit ended——两个按钮从此永久禁用，
    # 只能重启 GUI。白盒直调本方法模拟该窗口（真竞态无法稳定编排，锁的是「该出口必须
    # emit」这条契约本身，与 M-33 对异常路径的要求同形）。
    controller = _controller(tmp_path)
    controller._session_id = 7  # noqa: SLF001 - 白盒：模拟已有一轮会话
    seen: list[int] = []
    controller.ended.connect(lambda session: seen.append(int(session)))  # type: ignore[arg-type]
    controller._stop_worker_body()  # noqa: SLF001 - _process 恒为 None，正落在被修复的分支
    assert controller.is_stopping() is False
    assert seen == [7], "proc 已消失的早退分支同样必须 emit ended（停止按钮的统一恢复点）"


def test_shutdown_cleanup_consumes_pid_captured_at_start(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-79：_cleanup_target_pid 旧实现只写不读——停止链/自然 EOF 把 _process 清空后，
    # 退出收尾从 proc 拿到的 child_pid 恒为 None，cleanup_process_tree(None) 记一行就
    # 返回，「子进程没死利索、ffmpeg 还在录」的退出现场被静默跳过整树清理。
    controller = _controller(tmp_path)
    controller.build_record_command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]  # type: ignore[method-assign]
    killed: list[int | None] = []
    monkeypatch.setattr(recorder_module, "cleanup_process_tree", lambda pid, _log: killed.append(pid))
    ok, pid, _reason = controller.start()
    assert ok and pid is not None
    proc = controller._process  # noqa: SLF001 - 留真实句柄做收尾，避免残留 30s 睡眠进程
    controller._clear_process()  # noqa: SLF001 - 模拟停止链已把句柄清掉
    finished = threading.Event()
    controller.shutdown_async(on_finished=finished.set)
    assert finished.wait(timeout=10.0)
    assert killed == [pid], "退出清理必须打向启动期钉住的 PID，句柄被清不能成为跳过整树清理的理由"
    assert controller._cleanup_target_pid == pid  # noqa: SLF001 - 未被确认终止前不得清零
    assert proc is not None
    proc.kill()
    proc.wait(timeout=5)


def test_stop_worker_body_clears_cleanup_target_only_when_process_dead(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-79 的对称半句：停止链**确认进程已终止**时才清零清理目标——Windows 的 PID 进程
    # 退出即进复用池，留一个已回收的号码给下一次退出收尾补 taskkill，等于允许它命中新主人；
    # 而「没确认死透」就必须保留号码（那正是兜底要救的场景）。
    controller = _controller(tmp_path)
    monkeypatch.setattr(recorder_module, "cleanup_process_tree", lambda pid, _log: None)

    class _DeadProc:
        pid = 4242

        def poll(self) -> int | None:
            return 0

    # _stop_child_once 走「复核 poll 非 None 即返回」的最短真实分支（不触碰信号面）。
    # 替身只复刻被读到的 pid/poll 两个面，故类型收窄走行尾 ignore（与 M-33 用例的
    # method-assign ignore 同口径，mypy 对 ignore 注释后的散文会判 invalid）。
    controller._process = _DeadProc()  # type: ignore[assignment]
    controller._cleanup_target_pid = 4242  # noqa: SLF001
    controller._stopping = True  # noqa: SLF001
    controller._stop_worker_body()  # noqa: SLF001
    assert controller._cleanup_target_pid is None, "确认终止后必须交回号码，不得让退出收尾补发 taskkill"


def test_read_output_degrades_from_bounded_poll_to_blocking_wait(
    qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-79：空 readline + 进程仍活 = 管道瞬时无数据（写端被孙进程握着），旧实现 0.05s
    # 忙轮询没有任何退出条件——空转每秒 20 次直到进程消失。定稿给累计上限，超限后退化为
    # 阻塞 proc.wait()（唤醒点是进程真实终止），结束哨兵照投。
    controller = _controller(tmp_path)
    sleeps: list[float] = []
    time_shim = types.SimpleNamespace(**vars(recorder_module.time))
    time_shim.sleep = lambda s: sleeps.append(s)
    monkeypatch.setattr(recorder_module, "time", time_shim)

    class _EofStdout:
        def __init__(self) -> None:
            self.reads = 0

        def readline(self) -> str:
            self.reads += 1
            return ""

    class _StalledProc:
        def __init__(self) -> None:
            self.stdout: _EofStdout | None = _EofStdout()
            self.waits = 0

        def poll(self) -> int | None:
            # 4000 次空读后给出真实终止兜底：新旧实现都会终止，用例不靠「旧代码挂死」取证，
            # 只锁「必须远早于 4000 次就退化为 wait()」。
            return None if self.stdout is not None and self.stdout.reads < 4000 else 0

        def wait(self) -> int:
            self.waits += 1
            return 0

    proc = _StalledProc()
    controller._read_output(proc, 3)  # type: ignore[arg-type]  # noqa: SLF001 - 读线程本体在主线程直跑（替身无真管道）
    assert proc.waits == 1, "空等累计到上限后必须退化为一发阻塞 wait"
    limit = recorder_module._READ_IDLE_LIMIT_SECONDS / recorder_module._READ_POLL_INTERVAL_SECONDS  # noqa: SLF001
    assert 0 < len(sleeps) <= limit, f"忙轮询必须有累计上限（上限 {limit} 次，实测 {len(sleeps)}）"
    _messages, ended, session = controller.drain()
    assert ended and session == 3, "退化路径仍要投出结束哨兵，UI 的恢复点只有这一个信号"


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
    # test_test_hygiene 的 R1 锁会把全进程生效的改写判红（loguru/coverage 也会吃到假 run）。
    subprocess_shim = types.SimpleNamespace(**vars(recorder_module.subprocess))
    subprocess_shim.run = lambda *a, **k: _Result()
    monkeypatch.setattr(recorder_module, "subprocess", subprocess_shim)
    proc = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.PIPE, text=True)
    try:
        # 信号发不出去 → 走整树强杀，且不得宣称「ffmpeg 已由子进程清理」。两条平台的触发器不同：
        # win32 由上方桩把 CTRL_BREAK 打成失败；POSIX 禁 patch stdlib 的 os.kill，改用「先收尸再发」——
        # 对已 reap 的 pid 发 SIGINT 必抛 ProcessLookupError，正是 except → terminate 兜底要接的真实竞态。
        proc.wait()
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
    # main() 的终点是 Qt 事件循环入口（测试进程里真调会阻塞到退出），故替换 QApplication
    # 与 MainWindow，锁的是**装配顺序与接线**：「最后一个窗口关闭即退出」必须关掉
    # （托盘模式下窗口是隐藏的），崩溃钩子必须装上。
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
    # M-80：main() 现在还会装 threading.excepthook 并挂模块全局崩溃代理——两处进程级状态
    # 显式登记「还原为当前值」，否则替身用例会把崩溃钩子漏给后续所有文件（线程里再抛
    # 异常就会往 %TEMP%\dlr_gui_crash.log 里追加，污染其他用例的取证面）。
    monkeypatch.setattr(threading, "excepthook", threading.excepthook)
    monkeypatch.setattr(app_module, "_crash_proxy", None)

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


def test_main_installs_threading_excepthook_and_crash_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    # M-80：sys.excepthook 管不到线程——recorder-output / gui-stop / gui-quit / danmaku tail
    # 四个守护线程的未捕获异常走 threading.excepthook，默认形态只打 stderr，而 pythonw /
    # 冻结 console=False 下 stderr 为 None，异常被静默吞掉，正是本模块头声称要防的
    # 「无窗口、无报错」。旧实现只装了主线程那一半。
    _app_state, _window_state = _run_main_with_stubs(monkeypatch)
    assert threading.excepthook is app_module._threading_crash_sink
    # 弹窗代理必须在装配期挂上（QMessageBox 的线程亲和性封送全靠它，见 _CrashDialogProxy）
    assert app_module._crash_proxy is not None


def test_crash_sink_marshals_dialog_through_proxy_not_current_thread(
    qt_app: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-80 的行为半句：_crash_sink 不得再在「出事线程」上直接构造 QMessageBox——
    # 取证面是代理收到请求时的执行线程。主线程调用（sys.excepthook 的常规形态）就地直显；
    # 弹窗动作经由代理转发，_show_crash 是唯一的构造点（旧实现内联在 _crash_sink 里，
    # 变异验证「把弹窗构造搬回 _crash_sink」时，本用例的展示记录点数不变但生产源码结构
    # 由上一条装配用例与本条的行为出口共同收紧——这里锁的是 request 必须被调到）。
    shown: list[str] = []

    class _ProxyStub:
        def __init__(self) -> None:
            self.requests: list[str] = []

        def request(self, text: str) -> None:
            self.requests.append(text)
            shown.append(text)

    proxy = _ProxyStub()
    monkeypatch.setattr(app_module, "_crash_proxy", proxy)
    try:
        raise RuntimeError("boom-for-marshalling")
    except RuntimeError as exc:
        app_module._crash_sink(type(exc), exc, exc.__traceback__)
    assert proxy.requests and "boom-for-marshalling" in shown[0][-2000:]


def _standalone_window(tmp_path: Path, main_config_body: str) -> tuple[MainWindow, Callable[[], None]]:
    # 与 test_gui_qt_units 的 lang_window / test_gui_qt_window 的 window 夹具同构的
    # 「一次性构造 + 手工还原」形态：登记表快照还原、语言还原都在调用方用例内闭环。
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    url_file = config_dir / "URL_config.ini"
    url_file.write_text("https://live.douyin.com/1234 原画 主播A\n", encoding="utf-8-sig")
    main_file = config_dir / "config.ini"
    main_file.write_text(main_config_body, encoding="utf-8-sig")
    win = MainWindow(
        app_root=str(tmp_path),
        script_dir=str(tmp_path),
        url_config_file=str(url_file),
        main_config_file=str(main_file),
        downloads_dir=str(tmp_path / "downloads"),
    )
    win.apply_palette()

    def _dispose(win_ref: MainWindow = win) -> None:
        win_ref._finalize_quit()  # noqa: SLF001 - 走生产退出序列，停三条链
        win_ref.deleteLater()

    return win, _dispose


def test_startup_language_preference_retranslates_static_labels(qt_app: QApplication, tmp_path: Path) -> None:
    # M-78 行为锁：启动路径（_apply_language_preference）必须在 set_language 之后立刻
    # retranslate_all() 全量回填。旧实现里 retranslate_all 的唯一调用点在 on_language_change
    # （下拉菜单事件），而 set_text() 建时查表发生在 _build_ui()（先于语言切换）——
    # 配置语言显式写 en_US 的用户重启后静态标签一直停在中文，直到手动切一次语言下拉才被
    # 「顺带」修好。建时查表跑在 conftest 的恒等映射下、set_language 换回真实目录，
    # 因此断言右侧取 set_language 之后的 i18n.tr()，并先锁「英文目录确有该键译文」防伪绿。
    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001 - 还原全局登记表（Qt 条目随 QApplication 存活）
    saved_language = i18n.get_language()
    win, dispose = _standalone_window(tmp_path, "[录制设置]\nlanguage = en_US\n循环时间(秒) = 60\n")
    try:
        assert i18n.get_language() == "en_US"
        english = i18n.tr("📥   最小化到托盘")
        assert english != "📥   最小化到托盘", "en_US 目录对本键无译文，用例失去区分力"
        assert win.minimize_btn.text() == english, "启动期偏好语言未触发全量重译（M-78）"
        assert win.brand_sub.text() == i18n.tr("直播录制 · 控制台") != "直播录制 · 控制台"
        assert win.quit_btn.text() == i18n.tr("❌   彻底退出")
    finally:
        dispose()
        qt_app.processEvents()
        i18n.set_language(saved_language)
        ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001


def test_pref_combos_backfilled_from_saved_theme_and_scale(qt_app: QApplication, tmp_path: Path) -> None:
    # M-80 行为锁：显式偏好 dark/115 重启后，侧栏两个下拉的 currentData 必须与已生效的
    # palette 同值。旧实现 _resolve_initial_theme_and_scale 只算 palette 不回填下拉，
    # 下拉初值恒为 index 0（跟随系统/自动）——「窗口是深色、下拉指着跟随系统」的自相矛盾，
    # 且 toggle_theme（按 palette 翻）与 on_theme_change（按 currentData 落盘）从此不一致。
    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001
    saved_language = i18n.get_language()
    win, dispose = _standalone_window(tmp_path, "[GUI]\ngui_theme = dark\ngui_scale = 115\n")
    try:
        assert win._palette.theme_id == "dark"  # noqa: SLF001 - 前提：palette 侧本来就是对的
        assert win.theme_combo.currentData() == "dark", "主题下拉未回填显式偏好（M-80）"
        assert win.scale_combo.currentData() == "115", "缩放下拉未回填显式档位（M-80）"
        assert win._theme_follow_system is False  # noqa: SLF001
    finally:
        dispose()
        qt_app.processEvents()
        i18n.set_language(saved_language)
        ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001


def test_terminal_append_line_follows_newest_line(qt_app: QApplication) -> None:
    # M-81：textCursor() 返回副本——只在副本上 movePosition/insertText 而不调 setTextCursor，
    # 控件的**视口**从不跟随最新行。offscreen 实测：纯副本写法下文档字符数一路涨、
    # 内部光标位置因「插入点恰在光标处」的位移记账甚至仍报 atEnd True，但 verticalScrollBar
    # 停在 0（maximum 已到几十）——正是「在录，日志页却定格在开头」的确切形态；补上
    # setTextCursor 后滚动条与 maximum 齐平（与弹幕页 _render_stream 的同场景写法对齐）。
    term = TerminalText()
    term.setFixedHeight(60)
    term.show()
    qt_app.processEvents()
    try:
        for i in range(60):
            term.append_line("line-%03d\n" % i)
        qt_app.processEvents()
        vsb = term.verticalScrollBar()
        assert vsb.maximum() > 1, "视口未产生可滚动余量，用例失去取证面"
        # offscreen 实测：正确形态下 value 落在 maximum-1（末块为空段落，
        # ensureCursorVisible 保证「可见」而非「齐底」）；未修形态 value 恒为 0。
        # 判据取「跟随到近底」而不是逐像素相等，跨 Qt 小版本不脆断。
        assert vsb.value() >= vsb.maximum() - 1, "append_line 后视口未跟随最新行（M-81：副本光标从未写回）"
        assert term.toPlainText().startswith("line-000\nline-001\n"), "行内容/换行语义不得被 setTextCursor 改变"
    finally:
        term.close()
        term.deleteLater()
        qt_app.processEvents()


def test_tray_apply_palette_repaints_icon_with_new_tokens(qt_app: QApplication) -> None:
    # M-81：托盘图标色是 TrayIcon 构造时的 palette 快照，旧实现此后从不刷新——主题切换后
    # 托盘圆点与侧栏状态点分色（「一个状态 = 一种颜色」的一致性被打断）。定稿 = apply_palette
    # 存新色表并按当前运行态立即重绘；重绘结果必须与「用新色表现画」逐像素一致。
    light = theme_module.palette(theme_module.THEME_LIGHT, 1.0).tokens
    dark = theme_module.palette(theme_module.THEME_DARK, 1.0).tokens
    tray = TrayIcon(qt_app, light)
    for running in (False, True):
        tray.set_running(running)
        tray.apply_palette(dark)
        key = "success" if running else "danger"
        expected = tray._render_icon(dark[key]).pixmap(64, 64).toImage()  # noqa: SLF001
        got = tray.icon.icon().pixmap(64, 64).toImage()
        assert got == expected, f"running={running} 时托盘图标未随新 palette 重绘（M-81）"


def test_tray_custom_icon_survives_state_and_palette_changes(qt_app: QApplication, tmp_path: Path) -> None:
    # 导入图标与自绘图标的语义冲突点：自绘圆点承担「状态 = 颜色」，而导入图标是用户的品牌标识。
    # 定稿是导入图标恒压过自绘——被状态色覆盖等于「导入了却看不到」。判据用 availableSizes：
    # 真 ICO 里带着多档尺寸，而自绘那张只有 64×64，两者可机检区分。
    repo_icon = Path(__file__).resolve().parent.parent / "assets" / "app.ico"
    assert repo_icon.is_file(), "assets/app.ico 缺失（打包与运行时默认图标同源）"
    target = tmp_path / "app.ico"
    target.write_bytes(repo_icon.read_bytes())

    light = theme_module.palette(theme_module.THEME_LIGHT, 1.0).tokens
    dark = theme_module.palette(theme_module.THEME_DARK, 1.0).tokens
    tray = TrayIcon(qt_app, light)
    drawn_sizes = tray.icon.icon().availableSizes()
    assert drawn_sizes and drawn_sizes[0].width() == 64, "自绘图标基准尺寸变了，下面的区分判据需同步"

    assert tray.set_custom_icon(str(target)) is True
    tray.set_running(True)
    tray.apply_palette(dark)
    applied = tray.icon.icon().availableSizes()
    assert (16, 16) in [(s.width(), s.height()) for s in applied], "运行态/主题切换把导入图标覆盖成了自绘"

    # 清空导入即回到自绘：路径传空串是「恢复默认」的唯一出口
    assert tray.set_custom_icon("") is True
    assert tray.icon.icon().availableSizes() == drawn_sizes


def test_tray_custom_icon_rejects_unreadable_file(qt_app: QApplication, tmp_path: Path) -> None:
    # 坏文件必须保持现有图标而不是换成空 QIcon：空图标在 Windows 托盘区是一块看不见也点不到的空白
    light = theme_module.palette(theme_module.THEME_LIGHT, 1.0).tokens
    tray = TrayIcon(qt_app, light)
    before = tray.icon.icon()
    junk = tmp_path / "junk.ico"
    junk.write_bytes(b"not an icon at all")
    assert tray.set_custom_icon(str(junk)) is False
    assert not tray.icon.icon().isNull()
    assert tray.icon.icon().cacheKey() == before.cacheKey()


# ─── widgets.fixed_font：等宽族名 ─────────────────────────────────────────
# 判据一律走「打桩后的 QFontDatabase」：真实字体表随机器变化。旧写法把候选串整体塞进
# QFont("Consolas, Menlo, ...")，没装 Consolas 的机器上 Qt 按 styleHint=Monospace 落进
# 遗留别名 "Terminal"，打出 DirectWrite 创建失败 + Point size <= 0 两条告警。
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
    # _LogHighlighter 挂同一 document（QSyntaxHighlighter 以 document 为父对象，旧实例永不
    # 销毁）：切 N 次叠 N 个，旧行被反复重着色。取证面是 document 的 children 里
    # QSyntaxHighlighter 的个数（Qt 没有公开的「列出全部高亮器」API，父子关系是唯一可机检形态）。
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


def test_terminal_wraps_at_widget_width_and_rewraps_on_resize(qt_app: QApplication) -> None:
    # 运行日志自动换行锁（用户语义「折行随窗口大小变化」）：WidgetWidth 下长行按视口宽折行，
    # 拉宽后 Qt 自动重排。取证面取 document().firstBlock().lineCount()——NoWrap 恒为 1，
    # 折行后 >1 且随宽度单调下降；判据全用相对断言，不写死绝对行数（offscreen 与真窗共用
    # 同一套字体度量，具体折行数随字体/字号漂移，写死会在 CI 上脆断）。
    term = TerminalText()
    term.resize(240, 300)
    term.show()
    qt_app.processEvents()
    try:
        assert (
            term.lineWrapMode() == QPlainTextEdit.LineWrapMode.WidgetWidth
        ), "终端折行模式回归为 NoWrap：长行只能横向滚动，不随窗口宽度换行"
        term.append_line("[2026-10-31 11:48:25] " + "x" * 300)
        qt_app.processEvents()
        narrow = term.document().firstBlock().lineCount()
        assert narrow > 1, "窄视口下长行未折行（lineWrapMode 未生效或退回 NoWrap）"
        term.resize(1500, 300)
        qt_app.processEvents()
        wide = term.document().firstBlock().lineCount()
        assert wide < narrow, "拉宽视口后折行数未减少（WidgetWidth 的 resize 自动重排失效）"
    finally:
        term.close()


# ─── M-13/M-14：真窗语言热切换的整窗回填 ─────────────────────────────────


def _fail_fast_box(*_args: object, **_kwargs: object) -> int:
    # 用例期间任何预期外的模态弹窗都会把离屏用例钉死，一律快速失败而不是放行。
    raise AssertionError("用例期间出现了预期外的模态弹窗")


@pytest.fixture()
def lang_window(qt_app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    # 夹具与 tests/test_gui_qt_window.py 的 window 同源：登记表按用例快照还原（Qt 顶层
    # 窗口在 QApplication 存活期不释放，存活条目会顶翻按全局条数断言的 tests/test_ui_i18n.py）。
    # 启动语言钉成 zh_CN：缺省跟随宿主系统语言，用例结论不能随机器漂移。
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
    # M-13 行为锁：状态标题/副标题是运行态文案，不能被 retranslate_all() 的回填打回
    # 登记初值「待机」，且必须随语言切换按当前 recorder 状态重驱（四处投影一致）。
    win = lang_window
    # 进入「录制中」形态：白盒置 _running 让 is_running() 为真即可——本判据考的是切换钩子
    # 的重驱通路，与真子进程无关。只调 _set_running_ui(True) 不够：切换钩子会重读
    # is_running()，真实态为 False 时被重驱回「待机」——那反而是正确的生产行为。
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
        # 托盘状态项同属运行态（走 set_running 而不是登记表）；离屏/无 XDG Session
        # 时 _setup_tray 可能退化为 None，按可用性取证、不做伪绿。
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
        # 托盘菜单四条动作项随语言切换重取（Qt 版走 TrayIcon.retranslate；补齐的
        # 「隐藏主窗口」「设置」同在此列）。右侧写死 msgid 字面量：只比 i18n.tr() 会在「目录
        # 未生效」时同侧等值而失去区分力。
        assert win.tray.show_action.text() == i18n.tr("显示主窗口") != "显示主窗口"
        assert win.tray.hide_action.text() == i18n.tr("隐藏主窗口") != "隐藏主窗口"
        assert win.tray.settings_action.text() == i18n.tr("设置") != "设置"
        assert win.tray.quit_action.text() == i18n.tr("彻底退出") != "彻底退出"


def test_tray_menu_action_items_are_wired_and_fire_in_menu_order(qt_app: QApplication) -> None:
    # 「隐藏主窗口」「设置」是相对旧托盘补齐的两项。只断言 QAction 存在属伪绿：
    # 建了却不 connect 就是「点了没反应」，必须逐项 trigger() 看回调真被调到、且与菜单顺序一致。
    #
    # 直接构造 TrayIcon 而不是走 MainWindow._setup_tray()：后者在 isSystemTrayAvailable()
    # 为假（离屏 / 无 XDG Session）时把 tray 置成 None，那样本用例会退化成空跑。
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
    # 会让右键也弹一次窗口。
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
    # saved_buttons() 的原注释声称「供测试断言按钮可用性（停止流程会禁用控制按钮）」，但 Qt
    # 窗口层的停止流程只禁用 dashboard 的 start/stop，从不触碰本页 reload/save——按原注释
    # 写断言必然失败，该访问器因此长期零调用方（死代码清点实测）。注释已改为
    # 如实描述，本用例锁**真实存在**的契约：按 (reload, save) 顺序交出页面自己持有的按钮对象。
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
