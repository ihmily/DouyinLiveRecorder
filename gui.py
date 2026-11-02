# -*- coding: utf-8 -*-
# GUI 入口（PySide6）：产品窗口层位于 src.gui_qt，本模块只负责进程级前置动作后转发。
#
# 保留本薄入口而不是把 [project.scripts] 直接指向 src.gui_qt.app 的原因：
#   · Docker / 打包 / 文档 / compose 均以 `python gui.py` 作为 GUI 入口，路径语义不变；
#   · GUI 父进程标记必须在**任何 src 导入之前**写入（src.logger 导入期即读取它决定文件
#     sink 归属，见 src/logger.py::GUI_PARENT_ENV），需要一个顶层脚本承担这一步；
#   · 窗口层延迟到 main() 内导入：Docker CLI 镜像屏蔽 PySide6 后，`import gui` 仍可成功。
from __future__ import annotations

import os

# GUI 父进程标记：必须先于任何 src 导入设置（顺序由
# tests/test_logger_gui_parent.py::test_gui_entry_sets_marker_before_src_import 锁定）。
os.environ["DLR_GUI_PARENT"] = "1"


def _show_bootstrap_error(text: str) -> None:
    # 窗口化运行（pythonw / PyInstaller console=False）下 stderr 为 None，启动期异常若只
    # raise 就表现为「无窗口、无报错」。这里尽力用 PySide6 弹一次错误框；Qt 自身不可用时
    # 没有可用的 GUI 工具包，只能依赖调用方落的盘（见 __main__ 分支）。
    try:
        from PySide6.QtWidgets import QMessageBox

        box = QMessageBox()
        box.setWindowTitle("GUI 启动失败")
        box.setIcon(QMessageBox.Icon.Critical)
        box.setText(text[-2000:])
        box.exec()
    except Exception:
        pass


def main() -> None:
    from src.gui_qt.app import main as _qt_main

    _qt_main()


if __name__ == "__main__":
    try:
        main()
    except Exception as _exc:
        import tempfile
        import traceback

        _text = "".join(traceback.format_exception(type(_exc), _exc, _exc.__traceback__))
        try:
            with open(os.path.join(tempfile.gettempdir(), "dlr_gui_crash.log"), "a", encoding="utf-8") as _f:
                _f.write(_text + "\n")
        except Exception:
            pass
        _show_bootstrap_error(_text)
        raise
