# -*- coding: utf-8 -*-
# 系统托盘（QSystemTrayIcon）。
#
# 用 Qt 自带托盘而非 pystray：QSystemTrayIcon 天然跑在主线程，不受 macOS NSApp 线程模型
# 限制，也不必额外引 pystray + Pillow 两条依赖（两入口托盘现已同为 Qt 实现）。
#
# 菜单四条动作项（显示 / 隐藏 / 设置 / 退出）覆盖「显示主界面 / 最小化到托盘 / 退出程序」
# 并补上托盘直达的「设置」；中间的状态项只作展示（禁用）。
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
    def __init__(self, parent: QObject | None, palette_tokens: dict[str, str], icon_file: str = "") -> None:
        self._tokens = palette_tokens
        # M-81（2026-10-21）：托盘图标随运行态变色，但 apply_palette 必须知道「现在在不在录」
        # 才能选对色——色值由外部注入、运行态由 set_running 记账，两个通道缺一不可。
        self._running = False
        # 用户导入的图标（ICO）：非空时**恒**压过自绘图标，运行态与主题切换都不再改它——
        # 自绘图标承担「状态 = 颜色」的语义，而导入图标是用户的品牌标识，被状态色覆盖等于
        # 「导入了却看不到」。加载失败即保持 None（回落到自绘），不记坏路径。
        self._custom_icon: QIcon | None = None
        self.icon = QSystemTrayIcon(parent)
        self.icon.setToolTip("DouyinLiveRecorder")
        self.icon.setIcon(self._render_icon(palette_tokens["danger"]))
        if icon_file:
            self.set_custom_icon(icon_file)
        self.menu = QMenu()
        self.show_action = QAction(i18n.tr("显示主窗口"), self.menu)
        self.hide_action = QAction(i18n.tr("隐藏主窗口"), self.menu)
        self.status_action = QAction(i18n.tr("未运行"), self.menu)
        self.status_action.setEnabled(False)
        self.settings_action = QAction(i18n.tr("设置"), self.menu)
        self.quit_action = QAction(i18n.tr("彻底退出"), self.menu)
        self.menu.addAction(self.show_action)
        self.menu.addAction(self.hide_action)
        self.menu.addAction(self.status_action)
        self.menu.addSeparator()
        self.menu.addAction(self.settings_action)
        self.menu.addAction(self.quit_action)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._on_activated)
        self._on_show_requested: Callable[[], None] | None = None

    # 四个回调顺序即菜单自上而下的动作项顺序（显示 / 隐藏 / 设置 / 退出）。
    # 「设置」不必先恢复主窗口：AdvancedSettingsDialog 是顶层 QDialog，父窗 hide() 后仍能
    # 独立 show()（2026-10-20 offscreen 实测）。
    def bind_actions(
        self,
        on_show: Callable[[], None],
        on_hide: Callable[[], None],
        on_quit: Callable[[], None],
        on_settings: Callable[[], None],
    ) -> None:
        # Qt 的 triggered 默认带 checked 形参，收仄成无参回调，
        # 以免每个 handler 为兼容它加 *args（会让注解失真）。
        self._on_show_requested = on_show
        self.show_action.triggered.connect(lambda _checked: on_show())
        self.hide_action.triggered.connect(lambda _checked: on_hide())
        self.settings_action.triggered.connect(lambda _checked: on_settings())
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
        # 部分 Linux 容器 / SSH X forwarding 下没有 XDG Session：控件构造得出来但
        # isSystemTrayAvailable 为 False。不能「假装在托盘」，否则用户最小化后窗口
        # 彻底消失且无法恢复。
        return bool(QSystemTrayIcon.isSystemTrayAvailable())

    def show(self) -> None:
        self.icon.show()

    def hide(self) -> None:
        self.icon.hide()

    def notify(self, message: str) -> None:
        self.icon.showMessage("DouyinLiveRecorder", message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def set_running(self, running: bool) -> None:
        self._running = running
        self.icon.setIcon(self._current_icon())
        self.status_action.setText(i18n.tr("录制中") if running else i18n.tr("未运行"))

    def apply_palette(self, tokens: dict[str, str]) -> None:
        # M-81（2026-10-21）：主题切换的唯一出口（MainWindow.apply_palette）此前不触托盘——
        # 图标颜色是构造时烧进去的一份 palette tokens 副本，换主题后托盘圆点与侧栏状态点
        # 从此分色（「一个状态 = 一种颜色」的一致性被打断）。定稿 = 接收新色表并按**当前
        # 运行态**立即重绘；只存字典不重绘等于把旧图标焊死，只重绘不存则下次 set_running
        # 又回到旧色。色值仍来自 src/gui_qt/theme.py 令牌，托盘层不自带任何配色常量。
        self._tokens = tokens
        self.icon.setIcon(self._current_icon())

    def retranslate(self) -> None:
        self.show_action.setText(i18n.tr("显示主窗口"))
        self.hide_action.setText(i18n.tr("隐藏主窗口"))
        self.settings_action.setText(i18n.tr("设置"))
        self.quit_action.setText(i18n.tr("彻底退出"))

    def set_custom_icon(self, path: str) -> bool:
        # 换成用户导入的图标（ICO）。失败一律保持现有图标并返回 False：空 QIcon 在 Windows 托盘区
        # 是一块看不见也点不到的空白，那比「图标没换」糟得多。path 为空串 = 清空导入、回到自绘。
        if not path:
            self._custom_icon = None
            self.icon.setIcon(self._current_icon())
            return True
        icon = QIcon(path)
        if icon.isNull():
            return False
        self._custom_icon = icon
        self.icon.setIcon(icon)
        return True

    def _current_icon(self) -> QIcon:
        # 图标出口：导入优先，否则按运行态自绘（见 __init__ 里 _custom_icon 的注释）。
        # 两条出口都必须给出非空 QIcon，故 isNull 兜底在这里再查一次（QIcon 可能在文件被删后失效）。
        custom = self._custom_icon
        if custom is not None and not custom.isNull():
            return custom
        return self._render_icon(self._tokens["success"] if self._running else self._tokens["danger"])

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
