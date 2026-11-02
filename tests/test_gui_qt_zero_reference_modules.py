# tests/test_gui_qt_zero_reference_modules.py — M-102 零引用模块补冒烟。
#
# 报告实测：`src/gui_qt/pages/runlog.py` 与 `src/gui_qt/quality_monitor.py` 被 0 个测试文件引用，
# 于是这两个模块可以整段重写而不触发任何红灯，逐模块覆盖闸又依赖 coverage.json（该文件陈旧即
# 失效）。本文件补足「导入 + 构造 + 一条行为断言」的最小面：
#   · QualityMonitor 不依赖 Qt，走纯逻辑断言（reset / has_data / 未匹配行不建条目）；
#   · LogsPage 是 QWidget，按本仓 Qt 用例惯例先 importorskip 子模块再用离屏后端构造。
# 刻意不在此复制 test_gui_qt_units.py 的夹具：那份是真窗行为锁，本文件只管「有人引用它」。

import os

import pytest

# 按子模块探测并放宽 exc_type（CI 实测）：缺 Qt 系统库时失败点在 QtWidgets 的 dlopen，
# exc_type 缺省的 ModuleNotFoundError 抓不到，会被计成 collection error 并中断整轮。
pytest.importorskip(
    "PySide6.QtWidgets", exc_type=ImportError, reason="PySide6 / Qt 系统库不可用时跳过 Qt 控件冒烟（环境限制口径）"
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui_qt.pages import runlog as runlog_module  # noqa: E402
from src.gui_qt.quality_monitor import QualityMonitor  # noqa: E402


def test_quality_monitor_starts_empty_and_reset_clears_state() -> None:
    monitor = QualityMonitor()
    assert monitor.has_data() is False
    # 无数据的实例 reset 不得抛（reset 走 dict.clear 而非重建，重复调用安全）
    monitor.reset()
    assert monitor.has_data() is False


def test_quality_monitor_ignores_lines_that_match_no_status_pattern() -> None:
    monitor = QualityMonitor()
    captured: list[tuple[str, str]] = []
    # 一行既非「录制中」也非「画质降级」的普通日志：不得建条目，否则 has_data() 恒真、
    # 画质面板会为无关房间常驻一行红。
    monitor.parse_line(
        "2026-10-21 00:00:00 | INFO | x - 与画质无关的一行",
        lambda message, level: captured.append((message, level)),
        "00:00:00",
    )
    assert monitor.has_data() is False
    assert captured == []


@pytest.fixture(scope="module")
def qt_app() -> object:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_logs_page_constructs_and_clear_empties_terminal(qt_app: object) -> None:
    # 构造期即完成标题/终端/清空按钮的装配与首次翻译；构造成功即证明该页未与已删除的
    # 控件 API 脱钩（它此前 0 引用，控件层改名只有这条用例能挡住）。
    page = runlog_module.LogsPage()
    assert page.terminal is not None
    page.terminal.setPlainText("a\nb\n")
    assert page.terminal.toPlainText().strip() != ""
    page.clear()
    assert page.terminal.toPlainText().strip() == ""
