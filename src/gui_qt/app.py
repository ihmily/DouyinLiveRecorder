# -*- coding: utf-8 -*-
# Qt 应用装配与崩溃兜底。
#
# 崩溃 sink 走「落盘 + 弹窗」两条出口：窗口化运行（pythonw / PyInstaller console=False）
# 下 stderr 可能是 None，未捕获异常会被静默吞掉，表现为「启动后无窗口、无报错」。
from __future__ import annotations

import os
import sys
import tempfile
import threading
import traceback
from types import TracebackType
from typing import Any

# M-80（2026-10-21）：崩溃弹窗代理。QMessageBox 只能在 Qt 主线程构造/执行（Qt 线程亲和性），
# 而 _crash_sink 会被任意线程调起（四个守护线程 + 主线程槽异常）；旧实现直接在出事线程上
# 构造弹窗，轻则弹不出来、重则二次崩溃——兜底自己变成新故障源。代理在 main() 装配期（应用
# 已建、主线程）实例化并接管弹窗：worker 线程经信号跨线程投递（Queued）回主事件循环弹窗，
# 主线程则就地直显（启动期崩溃发生在 app.exec() 之前，事件循环还没跑起来，排队等于永远等
# 不到投递——那条窗口期正是「无窗口无报错」最难查的形态）。
_crash_proxy: Any | None = None


def _show_crash(text: str) -> None:
    # 兜底展示：代理缺失（main() 尚未装配完就崩）时只剩落盘那条出口，不得因弹窗缺失再抛。
    try:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        box.setWindowTitle("DouyinLiveRecorder")
        box.setText(text[-2000:])
        box.exec()
    except Exception:
        pass


def _crash_sink(exc_type: type[BaseException], exc: BaseException, tb: TracebackType | None) -> None:
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        path = os.path.join(tempfile.gettempdir(), "dlr_gui_crash.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass
    proxy = _crash_proxy
    if proxy is not None:
        try:
            proxy.request(text)
        except Exception:
            pass


def _threading_crash_sink(args: threading.ExceptHookArgs) -> None:
    # M-80：threading.excepthook 是**另一条钩子**，sys.excepthook 管不到线程。默认形态把
    # 线程未捕获异常打到 stderr——pythonw / 冻结 console=False 下 stderr 为 None，等于静默
    # 吞掉；recorder-output / gui-stop / gui-quit / danmaku tail 四个守护线程此前正处在这个
    # 裸奔面里。归并进与主线程同一出口（落盘 + 弹窗），语义为「异常至少留下痕」。
    # typeshed 把 ExceptHookArgs.exc_value 标为 Optional（钩子可在无异常对象的畸形入参下
    # 被调用）：None 时按「无可展示异常」处理，只落一条占位痕，不得让兜底钩子自己抛。
    exc = args.exc_value
    if exc is None:
        _crash_sink(args.exc_type, args.exc_type("<threading.excepthook: 无异常对象>"), args.exc_traceback)
        return
    _crash_sink(args.exc_type, exc, args.exc_traceback)


def main() -> None:
    from PySide6.QtCore import QObject, Qt, QThread, Signal
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:])
    app.setApplicationName("DouyinLiveRecorder")
    # 关掉「最后一个窗口关闭即退出」：最小化到托盘后窗口是隐藏的，
    # 若按默认语义，托盘弹出确认框的瞬间进程可能已经被判为可退出。
    app.setQuitOnLastWindowClosed(False)

    class _CrashDialogProxy(QObject):
        # 跨线程投递入口：requested 的接收方（本对象）在主线程构造，AutoConnection 按
        # 接收方线程亲和性自动升级为 Queued——emit 方在哪个线程都安全。
        requested = Signal(str)

        def __init__(self) -> None:
            super().__init__()
            self.requested.connect(_show_crash)

        def request(self, text: str) -> None:
            if QThread.currentThread() is self.thread():
                _show_crash(text)
            else:
                self.requested.emit(text)

    # 代理必须留在模块全局上持有引用：无父 QObject 不被 Qt 对象树收养，Python 侧一丢
    # 引用 C++ 对象即刻析构，钩子拿到的就是死代理。
    global _crash_proxy
    _crash_proxy = _CrashDialogProxy()
    sys.excepthook = _crash_sink
    threading.excepthook = _threading_crash_sink

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
