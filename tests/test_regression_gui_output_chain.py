# tests/test_regression_gui_output_chain.py — CODE_REVIEW_2026-10-18 的行为锁。
#
# 为什么单独成文件：test_gui_qt_units.py / test_gui_qt_window.py 钉的是「模块单元」与「窗口外观/
# 接线」，而这三条都是**跨线程投递与模态重入**的通路锁，必须同时持有真窗（MainWindow）与真子进程。
# S-01 的教训正在于此：旧用例只直调 controller.drain()，「信号从未 emit、drain 无生产调用方」这种
# 整条链断开的形态在满屏绿色里过去了——本文件一律从**入口**（start_recording / 后台线程调
# _queue_log / 定时器链调 _watch_url_config）驱动，断在任何一环都会红。
#
# 变异验证（一次性改动当轮按字节还原并复跑本文件；2026-10-18 本机实测读数，六处变异全部转红、
# 还原后本文件 6 条 + test_gui_qt_settings_dialog.py 2 条全绿）：
#   · 拆掉 recorder._push 的 outputReady.emit → 2 failed, 4 passed（两条 S-01 用例同时红）；
#   · 跳过 _on_recorder_ended 的 reclaim_after_natural_end → 1 failed（EOF 用例：句柄未回收）；
#   · 把 _queue_log 改回直接 _log_timer.start() → 1 failed（M-11 用例：尾线程入队永不刷出）；
#   · 去掉 _watch_url_config 的重入守卫与 mtime 前置 → 3 failed（M-12 三条全红，弹窗堆叠）；
#   · 把重入守卫挪到 mtime 前置**之后** → 1 failed（询问期间的新改动被就地吃掉）；
#   · 拆掉 settings_dialog 的 hideEvent 停表 → test_gui_qt_settings_dialog.py 2 failed。

import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

import pytest

# 探测**真正要 import 的子模块**并显式放宽 exc_type（AGENTS.md「测试」节的 2026-10-18 CI 事故口径）：
# 只探测顶层 PySide6 时，缺 Qt 系统库的机器上紧随其后的 import 会以 collection error 中断整轮 pytest。
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 输出通路用例（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import i18n  # noqa: E402
from src.gui_qt.main_window import MainWindow  # noqa: E402

_CHILD_MARKER = "hello-from-child-process-4711"


def _fail_fast_box(*_args: object, **_kwargs: object) -> int:
    raise AssertionError("用例期间出现了预期外的模态弹窗")


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance  # type: ignore[return-value]


@pytest.fixture()
def window(app: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[MainWindow]:
    # 登记表还原与 test_gui_qt_window.py 的 window 夹具同源：Qt 顶层窗口在 QApplication 存活期间不会
    # 被释放，条目会一路残留到后续测试文件，而 tests/test_ui_i18n.py 是按「全局条数」断言的。
    from src import ui_i18n

    registry_snapshot = list(ui_i18n._ENTRIES)  # noqa: SLF001 - 测试还原全局登记表，与生产同模块
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    url_file = config_dir / "URL_config.ini"
    url_file.write_text("https://live.douyin.com/1234 原画 主播A\n", encoding="utf-8-sig")
    main_file = config_dir / "config.ini"
    main_file.write_text("[录制设置]\n循环时间(秒) = 60\n", encoding="utf-8-sig")
    # 任何意外弹窗都会把离屏用例钉在模态循环里，一律换成快速失败而不是放行。
    monkeypatch.setattr(QMessageBox, "warning", _fail_fast_box)
    monkeypatch.setattr(QMessageBox, "critical", _fail_fast_box)
    win = MainWindow(
        app_root=str(tmp_path),
        script_dir=str(tmp_path),
        url_config_file=str(url_file),
        main_config_file=str(main_file),
        downloads_dir=str(tmp_path / "downloads"),
    )
    win.apply_palette()
    yield win
    win._finalize_quit()  # noqa: SLF001 - 夹具收尾走生产退出序列（停三条链、关弹幕尾线程）
    win.deleteLater()
    app.processEvents()
    ui_i18n._ENTRIES[:] = registry_snapshot  # noqa: SLF001 - 同上


def _pump_until(app: QApplication, predicate: Callable[[], bool], timeout: float = 15.0) -> bool:
    # 必须泵事件循环：outputReady / logQueued 由工作线程 emit，跨线程连接是 Queued，
    # 没有事件循环运行时槽函数永远不会被投递（离屏测试里最容易误判成「没 emit」）。
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


# ─── S-01：读线程 → 队列 → 主线程的通路 ───


def test_recorder_child_output_reaches_terminal_window(app: QApplication, window: MainWindow) -> None:
    # 假的「录制子进程」：印一行就退出。从 start_recording 入口驱动，覆盖
    # Popen → 读线程批次 → _push 唤醒 → 主线程 drain → 画质解析 → 定时器刷终端整条链。
    window.recorder.build_record_command = lambda: [sys.executable, "-c", f"print('{_CHILD_MARKER}')"]  # type: ignore[method-assign]
    window.start_recording()
    reached = _pump_until(app, lambda: _CHILD_MARKER in window.logs_page.terminal.toPlainText())
    text = window.logs_page.terminal.toPlainText()
    assert reached, f"子进程输出没有到达日志页（S-01 断路回归）；当前终端内容：{text!r}"


def test_natural_eof_is_observed_and_process_handle_reclaimed(app: QApplication, window: MainWindow) -> None:
    # 自然 EOF（主播下播 / 子进程自行退出）必须：① 日志页打出结束行；② 界面回到待机；
    # ③ 进程句柄被回收，能再次开始录制。结束行按 i18n.tr() 后的形态比对：MainWindow.__init__ 会调
    # i18n.set_language() **热替换** i18n._tr，把 conftest 的恒等映射顶掉，于是宿主语言为英文时
    # 这行落进终端的是 "Recording process ended"，钉原文必红。
    window.recorder.build_record_command = lambda: [sys.executable, "-c", "print('bye-from-child')"]  # type: ignore[method-assign]
    window.start_recording()
    end_line = i18n.tr("录制进程已结束")
    settled = _pump_until(app, lambda: end_line in window.logs_page.terminal.toPlainText())
    text = window.logs_page.terminal.toPlainText()
    assert settled, f"EOF 哨兵无人消费：界面会永久停在「运行中」，弹幕监控线程也不退出；终端内容：{text!r}"
    assert window.recorder.pid() is None, "自然结束后 _process 未回收，下一次启动恒报 already_running"
    assert window.recorder.is_running() is False
    assert window.dashboard.start_btn.isEnabled() is True
    # 再启一次必须真的拉得起新会话（会话号递增），否则「无法连续录制」仍在。
    second = window.recorder.start()
    assert second[0] is True, f"自然结束后无法再次启动录制：{second[2]}"
    assert window.recorder.session_id() == 2
    _pump_until(app, lambda: not window.recorder.is_running() and window.recorder.pid() is None)


# ─── M-11：非 GUI 线程只能投递、不能启表 ───


def test_queue_log_from_worker_thread_flushes_by_itself(app: QApplication, window: MainWindow) -> None:
    # 生产里这条路径来自弹幕 tail 线程与画质解析：只有工作线程入队、主线程不再入队时日志仍要刷出，
    # 否则「这一批永远滞留」。先把刷新链打回休眠态（夹具构建窗口时托盘那条告警已把它启起来了）。
    window._log_timer.stop()  # noqa: SLF001 - 复现「主线程这一轮不启表」的生产形态
    window._pending_log_lines.clear()  # noqa: SLF001 - 同上，避免夹具残留批次替本用例刷出
    assert window._log_timer.isActive() is False, "日志刷新链是按需激活的休眠态"
    caught: list[BaseException] = []

    def _worker() -> None:
        try:
            window._queue_log("来自尾线程的一行日志", "warn")
        except BaseException as e:  # noqa: BLE001 - 线程内异常必须带回主线程断言，否则静默
            caught.append(e)

    thread = threading.Thread(target=_worker, name="worker-queue-log")
    thread.start()
    thread.join(timeout=5.0)
    # 审查 7.11：join(timeout=5.0) 返回不等于线程已退出。本用例锁的正是「工作线程只
    # 入队、不跨线程动 QTimer」——入队路径若改成同步等待主线程，线程会挂在 _queue_log 里，而 caught
    # 仍为空、后面的 flush 判据也可能被主线程别的路径替它满足，形成假绿。
    assert not thread.is_alive(), "worker-queue-log 未在 5s 内退出：_queue_log 阻塞在非 GUI 线程上，不得判绿"
    assert not caught, f"非 GUI 线程调用 _queue_log 不得抛错：{caught}"
    flushed = _pump_until(app, lambda: "来自尾线程的一行日志" in window.logs_page.terminal.toPlainText())
    assert window._log_timer.isActive() is True, "跨线程入队必须把刷新链唤醒（QTimer 只能在主线程启停）"
    assert flushed, "只有工作线程入队时日志批次滞留在缓冲里没刷出（M-11 回归）"


# ─── M-12：模态冲突框在定时器链里不得堆叠 ───


def _external_url_change(window: MainWindow, content: str, step: int) -> None:
    Path(window.url_config_file).write_text(content, encoding="utf-8-sig")
    # 显式推 mtime：文件系统 mtime 粒度粗，只靠写入时间差可能落在同一拍上，
    # 检测判据是 mtime，故用严格递增的时间戳保证「确实变了」。
    stamp = time.time() + step * 60.0
    os.utime(window.url_config_file, (stamp, stamp))


def _stacking_probe(
    target: MainWindow,
    asked: list[int],
    answer: int,
    on_enter: Callable[[], None] | None = None,
) -> Callable[..., int]:
    # 替身在被调用时就地再走一次本链，等价于「模态事件循环期间 _status_tick 又触发了一拍」。
    # 重入守卫失效时这里会一路递归下去（深度由 asked 上限兜住，别把解释器栈打爆）；守卫生效时
    # 第二次进入在弹窗之前就 return，asked 只会有一条。on_enter 用来模拟「弹窗期间又写了一次文件」。
    def _question(*_args: object, **_kwargs: object) -> int:
        asked.append(1)
        if on_enter is not None:
            on_enter()
        if len(asked) < 5:
            target._watch_url_config()  # noqa: SLF001 - 复现定时器链的再入
        return answer

    return _question


def test_url_config_conflict_asks_once_and_keeps_watching(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[int] = []
    monkeypatch.setattr(QMessageBox, "question", _stacking_probe(window, asked, int(QMessageBox.StandardButton.No)))
    window.config_page.set_content("# 我正在编辑、尚未保存的一行\n")
    _external_url_change(window, "https://live.douyin.com/9999 原画 主播Z\n", 1)
    window._watch_url_config()  # noqa: SLF001 - 由 _status_tick 定时器链驱动，测试直接驱动同一入口
    assert len(asked) == 1, f"一次外部改动问出了 {len(asked)} 个冲突框（M-12 弹窗堆叠回归）"
    # 作答「否」之后检测必须照常工作：无新改动不再问，有新改动必须再问。
    window._watch_url_config()
    assert len(asked) == 1, "mtime 已前置落位，无新改动时不该再问"
    _external_url_change(window, "https://live.douyin.com/8888 原画 主播Y\n", 2)
    window._watch_url_config()
    assert len(asked) == 2, "询问期间挂起检测，但作答后必须恢复监测"
    assert "live.douyin.com/8888" not in window.config_page.content(), "选「否」要保留用户的未保存编辑"


def test_url_config_change_during_modal_is_still_asked_after_answer(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 挂起检测不等于吃掉检测：弹窗期间录制进程又写了一次文件时，那一拍必须只被「挡住」而不被
    # 「确认」。守卫排在 mtime 前置之后的写法会把新 mtime 就地落进 _url_last_mtime，用户答完之后
    # 这条改动再也问不到——正是本条要拦的形态（改回那个顺序本条转红）。
    asked: list[int] = []
    _external_url_change(window, "https://live.douyin.com/5555 原画 主播V\n", 1)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        _stacking_probe(
            window,
            asked,
            int(QMessageBox.StandardButton.No),
            lambda: _external_url_change(window, "https://live.douyin.com/6666 原画 主播W\n", 2),
        ),
    )
    window.config_page.set_content("# 未保存的编辑\n")
    window._watch_url_config()
    assert len(asked) == 1, "询问期间的再入必须被守卫挡住，不得叠框"
    window._watch_url_config()
    assert len(asked) == 2, "弹窗期间的外部改动答完之后必须再问一次（挂起 ≠ 已确认）"


def test_url_config_conflict_yes_reloads_without_stacking(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[int] = []
    monkeypatch.setattr(QMessageBox, "question", _stacking_probe(window, asked, int(QMessageBox.StandardButton.Yes)))
    window.config_page.set_content("# 未保存的编辑\n")
    _external_url_change(window, "https://live.douyin.com/7777 原画 主播X\n", 3)
    window._watch_url_config()
    assert len(asked) == 1, "选「是」的路径同样不得叠框"
    assert "live.douyin.com/7777" in window.config_page.content(), "选「是」必须重新加载磁盘内容"
    window._watch_url_config()
    assert len(asked) == 1, "重新加载后 mtime 已同步，不应再次询问"
