# -*- coding: utf-8 -*-
# 运行日志页：终端风格只读框 + 清空按钮。
#
# 文件名刻意叫 runlog 而不是 logs：pyproject 的 [tool.mypy].exclude 含裸名 `logs`（本意是排除
# 运行期产物目录），裸名按子串匹配会把 .../pages/logs.py 从无参 mypy 的扫描面里静默剔除。
#
# 行上限由 widgets.TerminalText 的 maximumBlockCount(1000) 承担：Qt 在 append 时自动
# 从文档头裁旧块；改由 Qt 托管是因为旧 tkinter 版「每次插入后算行号再 delete」每批都要
# 一次全文行号换算，ffmpeg 刷屏时肉眼可见地拖慢。
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.ui_i18n import T, set_text

from ..theme import Palette
from ..widgets import Card, TerminalText, action_button, card_layout, connect_click


class LogsPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        # 本页只负责承载终端控件，不覆盖滚动策略：行上限裁剪的唯一事实源在
        # widgets.TerminalText（maximumBlockCount）。
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        card = Card()
        body = card_layout(card, margin=16, spacing=10)
        self.card_title = QLabel()
        set_text(self.card_title, T("运行日志 (main.py 输出)"))
        title_font = self.card_title.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        self.card_title.setFont(title_font)
        body.addWidget(self.card_title)

        self.terminal = TerminalText()
        body.addWidget(self.terminal, 1)

        hint_row = QHBoxLayout()
        self.hint = QLabel()
        set_text(self.hint, T("日志超过行数上限将自动截断"))
        self.hint.setObjectName("muted")
        hint_row.addWidget(self.hint)
        hint_row.addStretch(1)
        self.clear_btn = action_button("🗑   清空日志")
        set_text(self.clear_btn, T("🗑   清空日志"))
        hint_row.addWidget(self.clear_btn)
        body.addLayout(hint_row)
        root.addWidget(card)

    def bind_actions(self, on_clear: Callable[[], None]) -> None:
        connect_click(self.clear_btn, on_clear)

    def clear(self) -> None:
        # 只清控件缓冲，不动 _pending_log_lines：正在途中的批次仍应照常落进来
        self.terminal.clear()

    def apply_palette(self, palette: Palette) -> None:
        # 终端色是固定的一套 token，主题切换后让既有高亮器按新色重刷当前与后续的行。
        # 高亮器由 TerminalText 单实例复用、只更新色表 + rehighlight：每次新建会挂同一
        # document 而旧实例不销毁（CODE_REVIEW_2026-10-18 M-16 的泄漏本体）。
        self.terminal.apply_highlighter(palette)
