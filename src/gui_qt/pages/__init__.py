# -*- coding: utf-8 -*-
# GUI 窗口层（PySide6）的五个页面。
#
# 为什么按页拆而不是一个巨 PageBuilder：旧版单文件窗口层有 5000+ 行，
# 「五个画面的构建 + 状态 + 跨线程调度」全在一个类里，改一个按钮的样式要在 1000 行里翻找；
# 这里每页一个 QWidget 子类，只暴露：
#   · apply_palette()  —— 主题切换（Qt 的 QSS 是全局的，但与订单色相关的部分要重刷）；
#   · retranslate()    —— 语言热切换；
#   · update_*()       —— 周期刷新的脏标记渲染。
from __future__ import annotations
