# -*- coding: utf-8 -*-
# 系统托盘（QSystemTrayIcon）。
#
# 为什么不再是 pystray：旧版为了 macOS 主线程模型额外拉了 pystray + Pillow 两条依赖，
# 而 Qt 自带 QSystemTrayIcon 且天然跑在主线程（没有 macOS 的 NSApp 线程限制问题）。
# pystray/Pillow 仍留在依赖清单里——Web 入口（src/web_tray.py）还用它，
# 两个入口的托盘实现互不通约，不是本轮能合并的面。
#
# 图标随运行态变色：仓库不放二进制图标 asset，这里用 QPainter 画一个带录制符号的圆，
# 与侧边栏圆点同色（保持「一个状态 = 一种颜色」的一致性）。
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

import i18n

_ICON_SIZE: int = 64


class TrayIcon:
    def __init__(self, parent: QObject | None, palette_tokens: dict[str, str]) -> None:
        self._tokens = palette_tokens
        self.icon = QSystemTrayIcon(parent)
        self.icon.setToolTip("DouyinLiveRecorder")
        self.icon.setIcon(self._render_icon(palette_tokens["danger"]))
        self.menu = QMenu()
        self.show_action = QAction(i18n.tr("显示主窗口"), self.menu)
        self.status_action = QAction(i18n.tr("未运行"), self.menu)
        self.status_action.setEnabled(False)
        self.quit_action = QAction(i18n.tr("彻底退出"), self.menu)
        self.menu.addAction(self.show_action)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self._on_show_requested: Callable[[], None] | None = None

    def bind_actions(self, on_show: Callable[[], None], on_quit: Callable[[], None]) -> None:
        # Qt 的 triggered 默认带 checked 形参，收仄成无参回调，
        # 以免每个 handler 为兼容它加 *args（会让注解失真）。
        self._on_show_requested = on_show
        self.show_action.triggered.connect(lambda _checked: on_show())
        self.quit_action.triggered.connect(lambda _checked: on_quit())
        self.icon.messageClicked.connect(lambda: on_show())

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.DoubleClick,
            QSystemTrayIcon.ActivationReason.Trigger,
        ):
            handler = self._on_show_requested
            if handler is not None:
                handler()

    def is_available(self) -> bool:
        # Qt 在无 XDG Session（部分 Linux 容器/SSH X forwarding）下 QSystemTrayIcon
        # 构造得出来但 isSystemTrayAvailable 为 False；不能「假装在托盘」，
        # 那样用户最小化后窗口彻底消失且无法恢复。
        return bool(QSystemTrayIcon.isSystemTrayAvailable())

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def notify(self, message: str) -> None:
        self.icon.showMessage("DouyinLiveRecorder", message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def set_running(self, running: bool) -> None:
        self.icon.setIcon(self._render_icon(self._tokens["success"] if running else self._tokens["danger"]))
        self.status_action.setText(i18n.tr("录制中") if running else i18n.tr("未运行"))

    def retranslate(self) -> None:
        self.show_action.setText(i18n.tr("显示主窗口"))
        self.quit_action.setText(i18n.tr("彻底退出"))

    def _render_icon(self, color: str) -> QIcon:
        pixmap = QPixmap(_ICON_SIZE, _ICON_SIZE)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor(color))
        painter.setBrush(QColor(color))
        painter.drawEllipse(4, 4, _ICON_SIZE - 8, _ICON_SIZE - 8)
        painter.setPen(QColor("#ffffff"))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(18, 18, _ICON_SIZE - 36, _ICON_SIZE - 36)
        painter.end()
        return QIcon(pixmap)
