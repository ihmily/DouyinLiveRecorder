# -*- coding: utf-8 -*-
# 弹幕监控页：房间统计表（连接状态 / 弹幕数 / 速率 / 礼物 / 人气）+ 实时弹幕流。
#
# 弹幕流为什么用 QTextEdit（富文本）而不是 QPlainTextEdit：三种消息类型（普通 / 礼物 / SC）
# 需要不同颜色，insertHtml 是成本最低的实现；300 条缓冲上限由 monitor 的 deque
# 保证（_MAX_MESSAGES），控件侧不再单独裁剪（「展示上限」只留一个事实源）。
from __future__ import annotations

import time
from typing import Callable

from PySide6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import i18n
from src.ui_i18n import T, set_text

from ..danmaku_monitor import DanmakuMonitor
from ..theme import Palette
from ..widgets import ArrowComboBox, Card, EmptyState, StatTile, action_button, card_layout, connect_click, fixed_font

# 列数必须与 _refresh_stats 里 setHorizontalHeaderLabels 的标签个数相等：
# 两边不一致时 QStandardItemModel 会静默丢掉多出来的列，是最难发现的一类错位。
_ROOM_COLUMNS: int = 8

# 三种消息色：礼物/SC 要能被一眼挑出来，普通弹幕走灰色。
# 这里刻意不读 palette 的 accent——弹幕流是内联 HTML，跟随主题会让「哪类消息」的
# 语义在深色主题下被弱化（灰字在深色底上比在浅色底上显眼得多）。
_GIFT_COLOR = "#d97757"
_SC_COLOR = "#e0a34a"
_DIM_COLOR = "#8a8a94"


class DanmakuPage(QWidget):
    def __init__(self, monitor: DanmakuMonitor, parent: QWidget | None = None) -> None:
        # 页面只持有 monitor 引用、不持有线程：tail 线程与 dirty 标记都在 monitor 内，
        # 页面是纯消费者，「刷新一次」只是读一份加锁快照，不碰后台写入中的共享状态。
        super().__init__(parent)
        self._monitor = monitor
        self._filter = ""
        self._last_stats: list[tuple[str, ...]] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 20)
        root.setSpacing(14)

        # 统计条不带投影：它紧贴页面上沿、与下方卡片间距很小，
        # 再叠一层阴影会让两块卡的边界糊在一起。
        stats_card = Card(shadow=False)
        stats_row = QHBoxLayout(stats_card)
        stats_row.setContentsMargins(8, 8, 8, 8)
        # 三块统计标题是构建期定型的静态标签，必须走 set_text + T() 登记（构造标签与登记键
        # 同一 msgid），retranslate_all() 才按当前语言回填；数值面（set_value）是运行态、不进登记。
        # [历史注] 原只在建时 tr() 一次，切语言后停在旧语言（M-14，2026-10-18）。
        self.stat_rooms = StatTile(i18n.tr("监控房间"))
        set_text(self.stat_rooms.title, T("监控房间"))
        self.stat_connected = StatTile(i18n.tr("已连接"))
        set_text(self.stat_connected.title, T("已连接"))
        self.stat_msgs = StatTile(i18n.tr("弹幕总数"))
        set_text(self.stat_msgs.title, T("弹幕总数"))
        for tile in (self.stat_rooms, self.stat_connected, self.stat_msgs):
            stats_row.addWidget(tile)
        root.addWidget(stats_card)

        table_card = Card()
        table_body = card_layout(table_card, margin=16, spacing=10)
        self.table_title = QLabel()
        set_text(self.table_title, T("房间统计"))
        title_font = self.table_title.font()
        title_font.setWeight(QFont.Weight.DemiBold)
        self.table_title.setFont(title_font)
        table_body.addWidget(self.table_title)

        # 只读 + 整行选中：统计表是看的数据，任何可编辑态都会让「刷新时覆盖用户输入」成为可能
        self.table = QTableView()
        self.table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._model = QStandardItemModel(0, _ROOM_COLUMNS, self)
        self.table.setModel(self._model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        # 垂直方向给 stretch 1：表格隐藏时由空状态吃满剩余高度，wordWrap 描述
        # 才有足够空间显示整段（否则只按单行 sizeHint 分配，文字被裁掉下半）。
        table_body.addWidget(self.table, 1)
        self.empty = EmptyState(
            i18n.tr("暂无弹幕监控数据"),
            i18n.tr("启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，支持弹幕的平台将显示实时弹幕"),
        )
        # 空态标题/描述是构建期定型的静态标签（M-14）：登记进重译表，切语言后回填。
        set_text(self.empty.title, T("暂无弹幕监控数据"))
        set_text(
            self.empty.description,
            T("启动录制并在 config.ini 开启「是否弹幕监控(是/否)」后，支持弹幕的平台将显示实时弹幕"),
        )
        table_body.addWidget(self.empty, 1)
        # 3:2 的高度配比与设计稿一致（房间统计在上、弹幕流在下）：
        # 不给 stretch 时两张卡按 sizeHint 抢空间，无数据时房间卡会被压到 200px 左右，
        # 空状态挤在中间看不出层次。
        root.addWidget(table_card, 3)

        stream_card = Card()
        stream_body = card_layout(stream_card, margin=16, spacing=10)
        head_row = QHBoxLayout()
        self.stream_title = QLabel()
        set_text(self.stream_title, T("实时弹幕"))
        stream_title_font = self.stream_title.font()
        stream_title_font.setWeight(QFont.Weight.DemiBold)
        self.stream_title.setFont(stream_title_font)
        head_row.addWidget(self.stream_title)
        head_row.addStretch(1)
        # 定最小宽：房间名长度差异极大，不定宽会让「清空」按钮随筛选内容左右跳
        self.filter_combo = ArrowComboBox()
        self.filter_combo.setMinimumWidth(160)
        self.filter_combo.currentTextChanged.connect(self._on_filter_changed)
        head_row.addWidget(self.filter_combo)
        self.clear_btn = action_button(i18n.tr("清空"))
        # 按钮文案是静态标签：登记重译（M-14），构造标签与登记键同一 msgid。
        set_text(self.clear_btn, T("清空"))
        head_row.addWidget(self.clear_btn)
        stream_body.addLayout(head_row)

        # NoWrap + 等宽：弹幕行长差异极大，软换行会让时间戳列参差不齐，没法扫读
        self.stream = QTextEdit()
        self.stream.setReadOnly(True)
        # 等宽候选与回退统一交回 fixed_font 工厂：硬写 setFontFamily("Consolas") 会在没装
        # 该字体的机器上产生字体告警。
        self.stream.setFont(fixed_font(11))
        self.stream.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        stream_body.addWidget(self.stream, 1)
        root.addWidget(stream_card, 2)
        # 与画质页同因：状态链首轮之前「空表头 + 空态」会同时可见，
        # 构造末尾强制同步一次把二者切到互斥状态，并让统计值从 "-" 落到 0。
        self._refresh_stats()

    def bind_actions(self, on_clear: Callable[[], None]) -> None:
        # 清空动作由主窗口注入（要连带清 monitor 缓冲），页面自己只认回调
        connect_click(self.clear_btn, on_clear)

    def retranslate_runtime(self) -> None:
        # 语言切换后的运行态重刷（M-14）：表头、「已连接/已断开」单元格与「全部房间」哨兵
        # 都在产生点 tr()，但 _refresh_stats 对行内容等值时短路返回，数据不变时旧语言原地常驻。
        # 清掉缓存强制整表重画：_sync_filter_options 会把旧语言哨兵换成新形态，选中的具体
        # 房间名（不译数据）原样保留；弹幕流行内标签（[礼物] 等）同在产生点 tr()，一并重绘。
        self._last_stats = None
        self._refresh_stats()
        self._render_stream()

    def _on_filter_changed(self, value: str) -> None:
        self._filter = "" if value == i18n.tr("全部房间") else value
        # 筛选变化后必须重绘：dirty 标记已被上一轮消费掉，否则用户改完筛选界面不动。
        self._render_stream()

    def refresh(self) -> None:
        # 两个 dirty 标记各自单独消费：弹幕流每秒都可能变，房间表只在连接/计数变化时变。
        # 合成一个标记会让「来一条弹幕就整表重画」——表重画比文本插入贵一个量级。
        if self._monitor.consume_stats_dirty():
            self._refresh_stats()
        if self._monitor.consume_stream_dirty():
            self._render_stream()

    def _refresh_stats(self) -> None:
        # 整表重画前先与上次的行做等值比较：状态链 3s/10s 一轮、每轮都调 refresh，
        # 数据没变就返回，避免每帧重建 QStandardItem 造成的无谓开销与选中态丢失。
        rooms = self._monitor.rooms_snapshot()
        rows: list[tuple[str, ...]] = []
        connected_count = 0
        total_msgs = 0
        # 按房间名排序而不是按加入顺序：房间集每次可能变，
        # 顺序不稳定会让「同一行是不是同一个房间」无从判断。
        for name in sorted(rooms):
            info = rooms[name]
            started = info.get("started_at", 0.0)
            try:
                started_text = time.strftime("%H:%M:%S", time.localtime(float(str(started)))) if started else "—"
            except ValueError, OverflowError:
                started_text = "--:--:--"
            connected = bool(info.get("connected"))
            connected_count += 1 if connected else 0
            total_msgs += int(str(info.get("msg_total", 0)) or 0)
            rows.append(
                (
                    name,
                    str(info.get("platform", "—")),
                    i18n.tr("已连接") if connected else i18n.tr("已断开"),
                    str(info.get("msg_total", 0)),
                    str(info.get("msg_rate", 0)),
                    str(info.get("gift_total", 0)),
                    str(info.get("online", 0)),
                    started_text,
                )
            )
        if rows == self._last_stats:
            return
        self._last_stats = rows

        model = self._model
        model.setRowCount(len(rows))
        model.setHorizontalHeaderLabels(
            [
                i18n.tr("房间"),
                i18n.tr("平台"),
                i18n.tr("状态"),
                i18n.tr("弹幕数"),
                i18n.tr("速率"),
                i18n.tr("礼物"),
                i18n.tr("人气"),
                i18n.tr("开始时间"),
            ]
        )
        # 断连房间整行置灰：让「还在表里但已经不弹了」与「正在弹」一眼可辨
        dim = QColor(_DIM_COLOR)
        for row_index, values in enumerate(rows):
            disconnected = values[2] == i18n.tr("已断开")
            for col, value in enumerate(values):
                item = QStandardItem(value)
                item.setEditable(False)
                if disconnected:
                    item.setForeground(dim)
                model.setItem(row_index, col, item)
        # 空状态与表格互斥显示（不是一个盖住另一个）：表格留着空的 header 行会被当成「有数据但全空」
        self.empty.setVisible(not rows)
        self.table.setVisible(bool(rows))

        self.stat_rooms.set_value(str(len(rows)))
        self.stat_connected.set_value(str(connected_count))
        self.stat_msgs.set_value(str(total_msgs))
        self._sync_filter_options(sorted(rooms))

    # 筛选下拉：房间列表变化时刷新选项；当前选择失效（房间已移除）回落到「全部房间」，
    # 且必须同步 _filter —— 否则界面显示「全部房间」而弹幕流被一个已不存在的房间名滤空，
    # 且用户无法自愈（重新选一次才恢复），这是 2026-09-12 审查 6.2 记过的故障形态。
    def _sync_filter_options(self, room_names: list[str]) -> None:
        all_label = i18n.tr("全部房间")
        wanted = [all_label, *room_names]
        current = self.filter_combo.currentText()
        if [self.filter_combo.itemText(i) for i in range(self.filter_combo.count())] != wanted:
            self.filter_combo.blockSignals(True)
            self.filter_combo.clear()
            self.filter_combo.addItems(wanted)
            if current in wanted:
                self.filter_combo.setCurrentText(current)
            else:
                self.filter_combo.setCurrentText(all_label)
                self._filter = ""
            self.filter_combo.blockSignals(False)

    def _render_stream(self) -> None:
        # 全量重绘而非增量追加：弹幕缓冲是 deque 且有上限，
        # 增量追加以「上一条画到哪」为准，一旦中间被筛选/清空打断就会错位或缺行。
        messages = self._monitor.messages_snapshot()
        self.stream.clear()
        shown = 0
        for msg in messages:
            room = str(msg.get("room", ""))
            if self._filter and room != self._filter:
                continue
            ts = msg.get("ts", 0.0)
            try:
                tstr = time.strftime("%H:%M:%S", time.localtime(float(str(ts)))) if ts else "--:--:--"
            except ValueError, OverflowError:
                tstr = "--:--:--"
            user = str(msg.get("user", ""))
            text = str(msg.get("text", ""))
            # 消息类型缺失时按普通弹幕处理：子进程写入的旧格式没有 type 字段
            mtype = str(msg.get("type", "chat"))
            if mtype == "gift":
                label, color = f"{i18n.tr('[礼物] ')}", _GIFT_COLOR
            elif mtype == "superChat":
                label, color = "[SC] ", _SC_COLOR
            else:
                label, color = "", _DIM_COLOR
            head = f'<span style="color:{_DIM_COLOR}">[{tstr}] [{_escape(room)}]</span> '
            body = f'<span style="color:{color}">{label}</span>'
            who = f"<b>{_escape(user)}</b>: " if user else ""
            self.stream.insertHtml(head + body + who + _escape(text) + "<br>")
            dropped = msg.get("dropped")
            if dropped:
                self.stream.insertHtml(
                    f'<span style="color:{_DIM_COLOR}">    （+{_escape(str(dropped))} '
                    f"{i18n.tr('条已省略')}）</span><br>"
                )
            shown += 1
        # 筛选后一条都没有时给一句提示，不然用户会分不清「没弹幕」和「筛选错了」
        if not shown:
            self.stream.insertHtml(f'<span style="color:{_DIM_COLOR}">{i18n.tr("暂无弹幕数据")}</span>')
        # 光标移到末尾而不是靠自动滚动：不这么做 insertHtml 后视口会停在顶部
        cursor = self.stream.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.stream.setTextCursor(cursor)

    def apply_palette(self, palette: Palette) -> None:
        # 弹幕流颜色由内联 HTML 决定（insertHtml 不读 QSS），主题 token 变化时重绘一次。
        _ = palette
        self._render_stream()


def _escape(text: str) -> str:
    # insertHtml 不做转义：房间名与弹幕正文是外部可控文本，
    # 不转义等于把 HTML 注入口子开在这个目录里。
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
