# -*- coding: utf-8 -*-
# Qt 应用装配与崩溃兜底。
#
# 为什么保留 tkinter 版那套「落盘 + 弹窗」的崩溃 sink：窗口化运行（pythonw / PyInstaller
# console=False）下 stderr 可能是 None，未捕获异常会被静默吞掉，
# 表现为「启动后无窗口、无报错」——用户完全无从反馈。
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from types import TracebackType


def _crash_sink(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        path = os.path.join(tempfile.gettempdir(), "dlr_gui_crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    try:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        box.setWindowTitle("DouyinLiveRecorder")
        box.setText(text[-2000:])
        box.exec()
    except Exception:
        pass


def main() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:])
    app.setApplicationName("DouyinLiveRecorder")
    # 关掉「最后一个窗口关闭即退出」：最小化到托盘后窗口是隐藏的，
    # 若按默认语义，托盘弹出确认框的瞬间进程可能已经被判为可退出。
    app.setQuitOnLastWindowClosed(False)
    sys.excepthook = _crash_sink

    from .main_window import MainWindow

    # 冻结后 GUI 模块位于 exe 同级的 _internal/，而 config/ ffmpeg/ node/ downloads/
    # 等运行时资源保持在 exe 同级目录（_internal 的父目录）。
    this_dir = os.path.dirname(os.path.abspath(__file__))
    if os.path.basename(os.path.normpath(this_dir)) == "_internal":
        app_root = os.path.dirname(this_dir)
    else:
        # 源码运行：this_dir 是 src/gui_qt，向上两级才是项目根（src/gui_qt → src → 根）。
        # 取三级会落到项目根的**父目录**（D:\ 一类），config/ 与 downloads/ 随之全部错位。
        app_root = os.path.dirname(os.path.dirname(this_dir))
    window = MainWindow(
        app_root=app_root,
        script_dir=app_root,
        url_config_file=os.path.join(app_root, "config", "URL_config.ini"),
        main_config_file=os.path.join(app_root, "config", "config.ini"),
        downloads_dir=os.path.join(app_root, "downloads"),
    )
    window.apply_palette()
    window.show()
    app.exec()
