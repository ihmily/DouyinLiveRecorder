# tests/test_gui_qt_settings_dialog.py — 高级设置对话框「轮询随可见性启停」的行为锁（M-15）。
#
# 单独成文件：settings_dialog 的加载/保存/外部改动两条裁决路径在 tests/test_gui_qt_units.py，
# 本文件的判据是「窗口关闭之后不再有磁盘轮询」，需要真实 show/hide 事件，属对话框生命周期。
#
# 断链后果：对话框带 parent，close/accept/reject 只 hide、不销毁 C++ 对象，_watch_timer 在
# 窗口不可见后仍每 5s 读一遍 config.ini；主窗口每次打开都 new 一个实例
# （main_window.open_advanced_settings），开关 N 轮即积累 N 个幽灵定时器——无谓 IO + 日志噪声。
# 变异验证：拆掉 hideEvent 停表，本文件两条判据同时转红。

import os
import time
from pathlib import Path
from typing import Iterator

import pytest

# 探测真正要 import 的子模块并放宽 exc_type：PySide6 缺 Qt 系统库时失败发生在子模块 dlopen，
# 顶层包仍可导入，否则整轮 pytest 会以 collection error 中断（详见 test_gui_qt_units.py 头部）。
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过设置对话框用例（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui_qt.settings_dialog import AdvancedSettingsDialog  # noqa: E402

# 探针用的短间隔：判据是「关掉之后还轮询几次」，等 5s 一个节拍会把用例时间全花在睡等上。
# 只改 QTimer 实例的间隔，不改被测的启停逻辑，生产取值仍是 _WATCH_INTERVAL_MS。
_PROBE_INTERVAL_MS = 50


@pytest.fixture(scope="module")
def app() -> Iterator[QApplication]:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    yield instance  # type: ignore[misc]


def _dialog(tmp_path: Path) -> AdvancedSettingsDialog:
    config_file = tmp_path / "config.ini"
    config_file.write_text("[录制设置]\n循环时间(秒) = 60\n", encoding="utf-8-sig")
    dialog = AdvancedSettingsDialog(None, str(config_file), lambda msg, level="info": None)
    dialog._watch_timer.setInterval(_PROBE_INTERVAL_MS)  # noqa: SLF001 - 生命周期锁需触碰私有定时器
    return dialog


def _poll_count(app: QApplication, dialog: AdvancedSettingsDialog, seconds: float) -> int:
    # 把 timeout 槽换成计数器，数「窗口不可见期间本链真正触发了几次」。
    polls: list[int] = []
    dialog._watch_timer.timeout.disconnect()  # noqa: SLF001 - 同上，装探针
    dialog._watch_timer.timeout.connect(lambda: polls.append(1))  # noqa: SLF001 - 同上
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    return len(polls)


def test_watch_timer_follows_dialog_visibility(app: QApplication, tmp_path: Path) -> None:
    dialog = _dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        assert dialog._watch_timer.isActive() is True, "打开窗口必须恢复磁盘轮询（含 set_focus 的再 show）"
        dialog.hide()
        app.processEvents()
        assert dialog._watch_timer.isActive() is False, "窗口隐藏后定时器必须停（M-15）"
        dialog.show()
        app.processEvents()
        assert dialog._watch_timer.isActive() is True, "重新显示必须恢复轮询，否则外部改动再也不被检测"
    finally:
        dialog.close()


def test_closed_dialog_stops_polling_the_config_file(app: QApplication, tmp_path: Path) -> None:
    # reject()/accept()（取消 / 保存成功）只走到 hide，停表必须落在该公共路径上；
    # 随后用远长于间隔的窗口确认触发次数为零（修复前每 50ms 触发一次）。
    dialog = _dialog(tmp_path)
    try:
        dialog.show()
        app.processEvents()
        dialog.reject()
        app.processEvents()
        assert dialog._watch_timer.isActive() is False
        assert _poll_count(app, dialog, 0.4) == 0, "对话框已关闭却仍在轮询 config.ini"
    finally:
        dialog.close()
