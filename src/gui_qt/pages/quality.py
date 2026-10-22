# -*- coding: utf-8 -*-
# 画质监控页：三块统计（总 / 正常 / 降级）+ 实时详情表 + 空状态。
#
# 表格选 QTableView + QStandardItemModel 而不是 QTableWidget：后者每格一个 item 控件，
# 画质页每轮可能同步几十行；model/view 下「未变化行不碰、只改内容」更容易做到零重建。
# 降级整行着色走逐 item 的 setForeground（等价于旧 tkinter 版 Treeview 的行级 tag 语义）；
# 「状态」列另用文字承载语义，不依赖颜色——深色主题与色弱场景下颜色不足以为凭。
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QTableView, QVBoxLayout, QWidget

import i18n
from src.ui_i18n import T, set_text

from ..quality_monitor import QualityMonitor
from ..theme import Palette
from ..widgets import Card, EmptyState, StatTile, action_button, card_layout, connect_click

# 列数与 _headers() 的标签个数必须相等：多出来的列会被 QStandardItemModel 静默丢弃
_COLUMN_COUNT: int = 6


class QualityPage(QWidget):
    def __init__(self, monitor: QualityMonitor, parent: QWidget | None = None) -> None:
        # 与弹幕页同构：只持有 monitor 引用做只读快照。画质解析发生在主线程
        # （数据模型侧刻意不加锁），因此这里取值也不会与写入竞争。
        super().__init__(parent)
        self._monitor = monitor
        # None 表示「尚未同步过」而不是「同步过且为空」：refresh() 的首轮若把空表
        # 当成「未变化」提前返回，表格与空状态会同时可见（2026-10-17 截图里表头
        # 与空态叠在一起），所以首轮必须无条件走一次 _sync_model + 可见性切换。
        self._last_rows: dict[str, tuple[str, ...]] | None = None
        self._palette: Palette | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        # ── 统计条 ──
        stats_card = Card(shadow=False)
        stats_row = QHBoxLayout(stats_card)
        stats_row.setContentsMargins(8, 8, 8, 8)
        # 三块统计标题是构建期定型的静态标签，必须走 set_text + T() 登记（构造标签与登记键
        # 同一 msgid），retranslate_all() 才按当前语言回填；数值面（set_value）是运行态、不进登记。
        # [历史注] 原只在建时 tr() 一次，切语言后停在旧语言（M-14，2026-10-18）。
        self.stat_total = StatTile(i18n.tr("录制直播间"))
        set_text(self.stat_total.title, T("录制直播间"))
        self.stat_ok = StatTile(i18n.tr("画质正常"))
        set_text(self.stat_ok.title, T("画质正常"))
        self.stat_down = StatTile(i18n.tr("画质降级"))
        set_text(self.stat_down.title, T("画质降级"))
        for tile in (self.stat_total, self.stat_ok, self.stat_down):
            stats_row.addWidget(tile)
        root.addWidget(stats_card)

        # ── 详情表 ──
        table_card = Card()
        body = card_layout(table_card, margin=16, spacing=10)
        self.card_title = QLabel()
        set_text(self.card_title, T("画质监控"))
        title_font = self.card_title.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        self.card_title.setFont(title_font)
        body.addWidget(self.card_title)

        self.table = QTableView()
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(False)
        self._model = QStandardItemModel(0, _COLUMN_COUNT, self)
        self.table.setModel(self._model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        body.addWidget(self.table, 1)

        # 空状态与表格叠放同容器、按需切换可见性：数据为空/非空每轮都可能翻转，
        # 走 QStackedWidget 切 index 会触发布局重算，setVisible 是更轻的形态。
        self.empty = EmptyState(
            i18n.tr("暂无录制中的直播间"),
            i18n.tr("启动录制后，将自动检测各直播间的实际画质是否与设置一致"),
        )
        # 空态标题/描述同样是构建期定型的静态标签（M-14）：登记进重译表，切语言后回填。
        set_text(self.empty.title, T("暂无录制中的直播间"))
        set_text(self.empty.description, T("启动录制后，将自动检测各直播间的实际画质是否与设置一致"))
        # 与表格互斥且各自吃满剩余高度：空状态无 stretch 时只拿到 sizeHint 高度，
        # wordWrap 描述仍会被压到单行（EmptyState 内已固定宽，这里补齐垂直空间）。
        body.addWidget(self.empty, 1)

        self.refresh_btn = action_button(i18n.tr("立即刷新"))
        # 按钮文案是静态标签：登记重译（M-14），构造标签与登记键同一 msgid。
        set_text(self.refresh_btn, T("立即刷新"))
        action_row = QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(self.refresh_btn)
        body.addLayout(action_row)
        root.addWidget(table_card)
        # 构造末尾先同步一次：窗口的状态链是 3s/10s 一轮，首轮之前表格与空状态
        # 都保持默认可见，用户看到的是「空表头 + 空态文字」叠在一起。
        self.refresh()

    def bind_actions(self, on_refresh: Callable[[], None]) -> None:
        # 立即刷新 = 强制走一次 refresh()：解析是同步的，不需要等下一个状态周期
        connect_click(self.refresh_btn, on_refresh)

    def retranslate_runtime(self) -> None:
        # 语言切换后的运行态重刷（M-14）：表头与「同等/降级/正常」单元格在产生点 tr()，
        # 但 refresh() 等值短路会让旧语言原地常驻——清掉缓存强制全量重建（统计数值与语言无关）。
        self._last_rows = None
        self.refresh()

    def refresh(self) -> None:
        data = self._monitor.snapshot()
        rows: dict[str, tuple[str, ...]] = {}
        for name in sorted(data):
            info = data[name]
            downgraded = bool(info.get("downgraded", False))
            actual = str(info.get("actual_quality", "")) or "—"
            alert_time = str(info.get("alert_time", "")) or "—"
            rows[name] = (
                name,
                str(info.get("set_quality", "—")),
                actual if downgraded else i18n.tr("同等"),
                i18n.tr("降级") if downgraded else i18n.tr("正常"),
                alert_time if downgraded else "—",
                str(info.get("alert_message", "")) or "—",
            )
        # 未变化则完全返回：每轮同步在未变化时不该触碰任何 item（避免闪烁与选中丢失）。
        # 首轮（_last_rows is None）不参与短路，否则空数据下永远进不到可见性切换。
        if self._last_rows is not None and rows == self._last_rows:
            return
        self._last_rows = rows
        self._sync_model(rows)
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))

        # 统计只看 downgraded 标记，不再读 actual_quality 文本：
        # 文本是展示用的（可能被 i18n 替换成「同等」），拿它当判据会在切语言后数错。
        total = len(rows)
        down_count = sum(1 for info in data.values() if info.get("downgraded"))
        self.stat_total.set_value(str(total))
        self.stat_ok.set_value(str(total - down_count))
        self.stat_down.set_value(str(down_count))

    def _headers(self) -> list[str]:
        # 每次同步都重设表头：语言切换后表头要跟着变，且成本就是六个字符串
        return [
            i18n.tr("直播间"),
            i18n.tr("设置画质"),
            i18n.tr("实际画质"),
            i18n.tr("状态"),
            i18n.tr("降级时刻"),
            i18n.tr("说明"),
        ]

    def _sync_model(self, rows: dict[str, tuple[str, ...]]) -> None:
        # 整表重建而非逐格 diff：画质页行数通常是个位数，
        # 按行 diff 省下的开销抵不上「行序变化时要重排」的复杂度。
        model = self._model
        model.setRowCount(len(rows))
        model.setHorizontalHeaderLabels(self._headers())
        palette: Palette | None = self._palette
        danger = QColor(palette.token("danger")) if palette is not None else QColor("#c0392b")
        text_dim = QColor(palette.token("text_2")) if palette is not None else QColor("#5c5c5c")
        downgraded_label = i18n.tr("降级")
        for row_index, values in enumerate(rows.values()):
            # 状态列已是 i18n 后的形态，据此判行色；不再回头查 monitor（snapshot 会附带
            # 清理副作用，且在 render 路径里二次取快照会让「脏标记」语义失真）。
            downgraded = values[3] == downgraded_label
            for col, value in enumerate(values):
                item = QStandardItem(value)
                item.setEditable(False)
                if downgraded:
                    item.setForeground(danger)
                elif col > 0:
                    item.setForeground(text_dim)
                model.setItem(row_index, col, item)

    def apply_palette(self, palette: Palette) -> None:
        # 记下 palette 供下次建 item 时取色，并立即按新主题重着色当前内容。
        self._palette = palette
        if self._last_rows:
            self._sync_model(self._last_rows)
