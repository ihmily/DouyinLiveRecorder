# -*- coding: utf-8 -*-
# GUI 窗口层（PySide6）包入口。刻意只暴露不与 Qt 绑定的常量，真正用到 Qt 的模块
# 由调用方按需 import——否则 `import src.gui_qt` 就会把整个 Qt 拉起来，
# 而 CLI/Web 两个入口根本不需要它（CI 的 static job 没装 PySide6 也能过 import 关）。
from __future__ import annotations

__all__ = ["DESIGN_SOURCE", "__version__"]

# 视觉事实源：本包所有设计令牌必须与这份设计稿的 :root 变量逐值对应，
# 令牌漂移由 tests/test_gui_qt_theme.py 的完整性契约拦截。
DESIGN_SOURCE: str = "docs/gui-redesign/index.html"

__version__: str = "1.0.0"
