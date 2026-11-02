# -*- coding: utf-8 -*-
# URL 配置页：整文件编辑器 + 重新读取 / 保存。
#
# 为什么是「整文件编辑」而不是结构化表格：URL_config.ini 的行格式是「URL + 空格 + 画质段
# + 空格 + 主播名」，画质段可空、主播名含空格；GUI 侧再做一遍 parser 就会与
# config_io / web_config 的解析口径分叉，编辑原文本是唯一不漂移的形态。
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from src.ui_i18n import T, set_text

from ..theme import Palette
from ..widgets import Card, action_button, card_layout, connect_click, fixed_font


class ConfigPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        # 页面只暴露 content()/set_content() 两个口子：保存前的跨进程冲突裁决
        # 需要「磁盘基线 vs 编辑器内容」两方，这个裁决权刻意留在窗口层。
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        card = Card()
        body = card_layout(card, margin=16, spacing=10)
        self.card_title = QLabel()
        set_text(self.card_title, T("URL 配置编辑区 (config/URL_config.ini)"))
        title_font = self.card_title.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        self.card_title.setFont(title_font)
        body.addWidget(self.card_title)

        self.editor = QPlainTextEdit()
        self.editor.setFont(fixed_font(11))
        # 不换行：URL 行被软换行后再保存，会引入实际不存在的换行符语义。
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        body.addWidget(self.editor, 1)

        self.hint = QLabel()
        set_text(self.hint, T("每行一个直播链接，支持 # 开头的注释行；外部修改文件后将自动重新加载"))
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        body.addWidget(self.hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        # 构造标签与 T() 同 msgid（三空格=与 Tk 遗留共用的既有目录键），理由见 main_window 侧栏同名注释。
        self.reload_btn = action_button("🔄   重新读取")
        set_text(self.reload_btn, T("🔄   重新读取"))
        self.save_btn = action_button("💾   保存 URL 配置", "primary")
        set_text(self.save_btn, T("💾   保存 URL 配置"))
        btn_row.addWidget(self.reload_btn)
        btn_row.addWidget(self.save_btn)
        body.addLayout(btn_row)
        root.addWidget(card)

    def bind_actions(self, on_reload: Callable[[], None], on_save: Callable[[], None]) -> None:
        # 重新读取也要走窗口：它会连带刷新磁盘基线，页面自己读文件会让基线漂移
        connect_click(self.reload_btn, on_reload)
        connect_click(self.save_btn, on_save)

    def content(self) -> str:
        # toPlainText() 在部分存根下推成 Any，显式 str() 收敛返回类型。
        return str(self.editor.toPlainText())

    def set_content(self, text: str) -> None:
        # 整篇替换而非增量 diff：配置是整文件读写的，增量只会引入「哪一段该保留」的歧义
        self.editor.setPlainText(text)

    def apply_palette(self, palette: Palette) -> None:
        # 编辑器配色全走 QSS（objectName 选择器），本页无手绘元素，故只做完整性对齐。
        _ = palette

    def saved_buttons(self) -> tuple[QPushButton, QPushButton]:
        # 供测试取用本页两个控制按钮（顺序 = 重新读取、保存）。非业务路径。
        # 窗口停止流程只禁用 dashboard 的 start/stop 两键，从不触碰本页按钮，故「停止时禁用
        # 本页按钮」的断言必然失败；要那样做得先在 main_window 停止分支接线，断言补进
        # tests/test_gui_qt_units.py::test_config_page_saved_buttons_exposes_both_control_buttons。
        # [2026-10-20 更正] 原注释称「供测试断言按钮可用性（停止流程会禁用控制按钮）」，前提不成立。
        return self.reload_btn, self.save_btn
