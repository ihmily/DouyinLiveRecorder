# -*- coding: utf-8 -*-
# 控制台页：状态总览（大状态点 + 信息网格）、录制控制与快捷操作。
#
# 布局口径照搬设计稿的「卡片 + 12px 间距 + 右侧信息网格」，
# 大状态点取代旧版 Canvas 呼吸圆点（见 widgets.StatusDot），动画成本交给 Qt 时间线。
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import i18n
from src.ui_i18n import T, set_text

from ..theme import Palette
from ..widgets import Card, StatusDot, action_button, card_layout, connect_click


class DashboardPage(QWidget):
    # 信息网格的键与 _build_info_grid 的 items 一一对应：窗口层按这个顺序逐项写入
    # 周期刷新的值，缺项由 set_info 回落成 "-"，不至于让某一格停在上一语言的值上。
    INFO_KEYS: tuple[str, ...] = ("interval", "format", "tray", "time")

    def __init__(self, parent: QWidget | None = None) -> None:
        # 三张卡（状态 / 控制 / 快捷操作）自上而下堆叠，卡片本身不给 stretch：
        # 窗口拉高时卡片不跟着散开（设计稿是固定密度的列表）。
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)
        # 顶对齐不用 setAlignment(AlignTop)：对齐标志让布局按首轮 sizeHint 定高，而信息网格 /
        # 提示行的 sizeHint 随可用宽度变化，第二轮可能更矮，表现为卡片底部压住按钮 1~2px。
        # 末尾 addStretch 表达同一「顶部堆叠」语义，但把多余空间交还布局而不是钉死高度。

        # ── 状态总览卡 ──
        self.status_card = Card()
        status = QHBoxLayout()
        status.setContentsMargins(22, 22, 22, 22)
        status.setSpacing(18)
        # 呼吸动画只挂在状态点上：它是唯一的「心跳」信号源，
        # 顶栏与侧栏的小圆点各自另有一份，互不共用计时器（避免一处 stop 停掉全部）。
        self.dot = StatusDot(self.status_card)
        status.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        # 状态标题/副标题是运行态文案（窗口 _set_running_ui 经 set_status 按录制状态写入），
        # 刻意不进重译登记表（M-13，2026-10-18）：登记后 retranslate_all() 会把「录制中」打回
        # 初值「待机」，与侧栏/托盘互相矛盾。运行态标签不进登记表是仓库既有约定
        # （关键约定#16 / i18n 已知坑）；建时 tr() 取初值即可，切语言后由 _repopulate_static_texts
        # 按 recorder.is_running() 重驱 _set_running_ui，产生点的 tr() 自然取当前语言。
        self.status_title = QLabel(i18n.tr("待机"))
        title_font = self.status_title.font()
        title_font.setPointSize(20)
        title_font.setWeight(QFont.Weight.DemiBold)
        self.status_title.setFont(title_font)
        # 副标题同理：运行态文案，不进登记表（与下方 set_status 的注释同一判据）。
        self.status_sub = QLabel(i18n.tr("录制进程未运行"))
        self.status_sub.setObjectName("muted")
        text_col.addWidget(self.status_title)
        text_col.addWidget(self.status_sub)
        status.addLayout(text_col, 1)
        status.addStretch(1)
        self._info_labels = self._build_info_grid(status)
        card_layout(self.status_card).addLayout(status)
        root.addWidget(self.status_card)

        # ── 录制控制卡 ──
        self.control_card = Card()
        control = card_layout(self.control_card)
        self.control_title = QLabel()
        set_text(self.control_title, T("录制控制"))
        control_title_font = self.control_title.font()
        control_title_font.setWeight(QFont.Weight.DemiBold)
        self.control_title.setFont(control_title_font)
        control.addWidget(self.control_title)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        # 构造标签与 T() 同 msgid（三空格=与 Tk 遗留共用的既有目录键），理由见 main_window 侧栏同名注释。
        self.start_btn = action_button("▶   开始录制", "primary")
        set_text(self.start_btn, T("▶   开始录制"))
        self.stop_btn = action_button("⏹   停止录制", "danger")
        set_text(self.stop_btn, T("⏹   停止录制"))
        # 初始只有「开始」可点：停止按钮的可用性完全由 set_status 驱动，
        # 页面自身不推断运行态（推断就意味着第二份事实源）。
        self.stop_btn.setEnabled(False)
        self.hint = QLabel()
        set_text(self.hint, T("启动后将调用 main.py 循环监测 URL 配置中的直播间并自动录制"))
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        btn_row.addWidget(self.start_btn)
        btn_row.addWidget(self.stop_btn)
        btn_row.addWidget(self.hint, 1)
        control.addLayout(btn_row)
        root.addWidget(self.control_card)

        # ── 快捷操作卡 ──
        self.quick_card = Card()
        quick = card_layout(self.quick_card)
        self.quick_title = QLabel()
        set_text(self.quick_title, T("快捷操作"))
        quick_title_font = self.quick_title.font()
        quick_title_font.setWeight(QFont.Weight.DemiBold)
        self.quick_title.setFont(quick_title_font)
        quick.addWidget(self.quick_title)
        quick_row = QHBoxLayout()
        quick_row.setSpacing(10)
        self.open_dir_btn = action_button("📂   打开下载目录")
        set_text(self.open_dir_btn, T("📂   打开下载目录"))
        self.advanced_btn = action_button("⚙   高级设置")
        set_text(self.advanced_btn, T("⚙   高级设置"))
        quick_row.addWidget(self.open_dir_btn)
        quick_row.addWidget(self.advanced_btn)
        quick_row.addStretch(1)
        quick.addLayout(quick_row)
        root.addWidget(self.quick_card)
        # 顶对齐的实际手法：三张卡之后铺弹性空白，窗口拉高时仍是「卡片靠上、下方留白」
        root.addStretch(1)

    # 右侧信息网格（2×2），返回四个值标签供周期刷新改写。
    def _build_info_grid(self, parent: QHBoxLayout) -> dict[str, QLabel]:
        grid = QGridLayout()
        grid.setSpacing(14)
        # 两列等宽：不等宽时「循环检测 / 输出格式」的起点对不齐（列宽被最长值
        # 「2026-10-17 14:24:47」撑到 209px，左列只有 121px），视觉上像两套网格。
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        labels: dict[str, QLabel] = {}
        items = (
            ("interval", "循环检测", 0, 0),
            ("format", "输出格式", 0, 1),
            ("tray", "系统托盘", 1, 0),
            ("time", "当前时间", 1, 1),
        )
        for key, title, row, col in items:
            box = QVBoxLayout()
            # caption 与数值之间留 2px：原 0 间距让两行字贴着，截图里被读成「同一行挤在一起」
            box.setSpacing(2)
            caption = QLabel()
            set_text(caption, T(title))
            caption.setObjectName("muted")
            value = QLabel("-")
            value.setObjectName("statValue")
            box.addWidget(caption)
            box.addWidget(value)
            grid.addLayout(box, row, col)
            labels[key] = value
        parent.addLayout(grid)
        return labels

    def bind_actions(
        self,
        on_start: Callable[[], None],
        on_stop: Callable[[], None],
        on_open_dir: Callable[[], None],
        on_advanced: Callable[[], None],
    ) -> None:
        # 回调由窗口统一注入：页面不认识「录制控制器」，
        # 这是刻意的分层（页面只登记 widget，连接策略归窗口）。
        connect_click(self.start_btn, on_start)
        connect_click(self.stop_btn, on_stop)
        connect_click(self.open_dir_btn, on_open_dir)
        connect_click(self.advanced_btn, on_advanced)

    def set_status(self, running: bool, palette: Palette, status_title: str, status_sub: str) -> None:
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        # 运行态标题/副标题由窗口按当前录制状态写入，不进登记表（否则会被 retranslate 打回初值）
        self.status_title.setText(status_title)
        self.status_sub.setText(status_sub)
        self._paint_dot(running, palette)

    def set_info(self, values: dict[str, str]) -> None:
        # 按 _info_labels 遍历而不是按入参遍历：网格里的键是固定的，
        # 反过来遍历会让「这一轮没给的键」留在旧值上，看起来像刷新失效。
        for key, label in self._info_labels.items():
            label.setText(values.get(key, "-"))

    def _paint_dot(self, running: bool, palette: Palette) -> None:
        # 呼吸只在运行时开：待机时闪红点会被读成「有异常在发生」
        if running:
            self.dot.set_color(palette.token("success"), True)
        else:
            self.dot.set_color(palette.token("danger"), False)

    def apply_palette(self, palette: Palette, *, running: bool) -> None:
        # 主题切换后状态点要重画：QSS 管不到 StatusDot 的手绘内容。
        self._paint_dot(running, palette)
