# -*- coding: utf-8 -*-
# 高级设置：config.ini 全文编辑器。
#
# 为什么仍然整文件编辑而不是逐项控件：config.ini 的键会随版本增删（缺键补写也是录制进程的
# 行为之一），做成结构化表单就意味着每加一个键都要改 GUI，且「用户想改但表里没有」的情形
# 无法降级。旧的 tkinter 版已经是这个形态，本次只是换了对等物。
#
# MID-55 的两份基线（编辑器基线 + 磁盘快照）与保存前裁决逻辑全部保留：
# 录制进程会在运行期写回凭据、禁用 SSL 校验的平台清单与缺键补写，
# 跨进程没有锁可依赖，整文件写回只能靠显式检测 + 交用户裁决。
from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

import i18n

from .shared import config_change_verdict, normalize_editor_text, read_config_snapshot, save_text_to_file
from .widgets import fixed_font

# 5s 一次：录制进程写 config.ini（补键 / 回写凭据）不是高频动作，
# 再密就是纯空转，再疏则会让「外部已改」的提示迟到到用户已经改完。
_WATCH_INTERVAL_MS: int = 5000


class AdvancedSettingsDialog(QDialog):
    def __init__(self, parent: "object", config_file: str, log: "object") -> None:
        # log 用 object 收仄并在 _notify 里 callable() 判断：主窗口传的是 _queue_log，
        # 测试里传的是 None 或假函数，显式判 callable 比约定「必须给个函数」更难用错。
        super().__init__(parent)  # type: ignore[arg-type]
        self.config_file = config_file
        self._log = log
        self._baseline_content = ""
        self._disk_snapshot: str | None = None
        self._conflict_hint_shown = False

        self.setWindowTitle(i18n.tr("高级设置 - config.ini"))
        self.resize(820, 620)
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)

        self.title_label = QLabel(i18n.tr("配置文件内容 (config/config.ini)"))
        title_font = QFont(self.title_label.font())
        title_font.setWeight(QFont.Weight.DemiBold)
        self.title_label.setFont(title_font)
        root.addWidget(self.title_label)

        # 外部改动提示行：只给可见信号，不弹窗打断（保存时才要用户裁决）。
        self.hint_label = QLabel("")
        self.hint_label.setWordWrap(True)
        root.addWidget(self.hint_label)

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # 刻意不传 point_size：此处原本就没有设定值，字号继续由 QSS 的 px 供给（缩放档位要吃它）
        self.editor.setFont(fixed_font())
        root.addWidget(self.editor, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton(i18n.tr("取消"))
        self.save_btn = QPushButton(i18n.tr("保存配置"))
        self.save_btn.setObjectName("primary")
        self.cancel_btn.clicked.connect(self.reject)
        self.save_btn.clicked.connect(self.save_config)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        root.addLayout(btn_row)

        # 磁盘监听用 QTimer（Qt 的 timer 挂在窗体自己身上，窗体销毁自动停，
        # 不必像 Tk 那样保存 after id 并在 destroy 前手工 cancel）。
        # 补（M-15，2026-10-18）：「窗体销毁自动停」这条路本窗口实际走不到——对话框带 parent，
        # close/hide 不销毁 C++ 对象，所以启停还得自己按可见性管，见 hideEvent/showEvent。
        self._watch_timer = QTimer(self)
        self._watch_timer.setInterval(_WATCH_INTERVAL_MS)
        self._watch_timer.timeout.connect(self._watch_config_file)
        self._load_config()
        self._watch_timer.start()

    def _editor_content(self) -> str:
        # 归一后再比较：Windows 编辑器可能给出 CRLF，磁盘上是 LF，
        # 不归一会把「没改过」判成「改过」，进而凭空弹出冲突框。
        return normalize_editor_text(self.editor.toPlainText())

    # 随窗口可见性启停轮询（M-15）。
    # 为什么判 hide/show 而不是 accept/reject：accept()/reject() 只是 QDialog.done() →
    # hide()，而标题栏 X、parent.close()、窗口最小化到托盘后再关都只走 hide 这条路，
    # 挂在那两个方法上会漏掉一半关闭路径。
    # 后果（修复前）：对话框由主窗口传入 parent，Python/C++ 两侧都不会随 close 释放，
    # 于是 _watch_timer 在窗口已不可见后仍每 5s 读一遍 config.ini、并可能对不可见窗口
    # 弹 QMessageBox；主窗口每次 open 都 new 一个新实例（见 main_window.open_advanced_settings），
    # 开/关 N 轮就积累 N 个幽灵定时器。
    # 为什么选「停表」而不是「复用同一实例」：新建实例正是 `_load_config()` 重读磁盘、
    # 重建两份基线（编辑器基线 + 磁盘快照，MID-55）的时机，复用就得新增一条重开时的
    # 重载路径并改动那两套基线的语义——侵入更大，且复用后仍要把本停表写成 hide 钩子。
    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt 的重写点必须这个名
        self._watch_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt 的重写点必须这个名
        super().showEvent(event)
        if not self._watch_timer.isActive():
            self._watch_timer.start()

    def _load_config(self) -> None:
        import os

        content: str | None
        try:
            with open(self.config_file, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except FileNotFoundError:
            content = None
        except Exception as e:
            QMessageBox.critical(self, i18n.tr("错误"), i18n.tr("加载配置文件失败: {e}", e=e))
            return
        if content is None:
            content = i18n.tr("# 配置文件不存在，请新建")
            self.editor.setPlainText(content)
        else:
            self.editor.setPlainText(content)
        self._baseline_content = normalize_editor_text(content)
        try:
            self._disk_snapshot, _ = (
                read_config_snapshot(self.config_file) if os.path.exists(self.config_file) else (None, None)
            )
        except OSError:
            self._disk_snapshot = None
        self._conflict_hint_shown = False
        self.hint_label.setText("")

    def _watch_config_file(self) -> None:
        # 无未保存编辑时直接重加载（reload），有编辑时只挂提示行、不打断——
        # 弹窗打断会让用户正在改的内容和他看到的编辑器内容脱节。
        disk_now, _ = read_config_snapshot(self.config_file)
        if disk_now == self._disk_snapshot:
            return
        if (
            config_change_verdict(self._disk_snapshot, disk_now, self._editor_content(), self._baseline_content)
            == "reload"
        ):
            self._load_config()
            self._notify(i18n.tr("config.ini 已被外部修改，已重新加载到编辑器"))
        elif not self._conflict_hint_shown:
            self._conflict_hint_shown = True
            self.hint_label.setText(i18n.tr("config.ini 已被外部修改，而你有未保存的编辑；保存时会先询问是否覆盖"))

    def save_config(self) -> None:
        editor_text = self._editor_content()
        disk_now, _ = read_config_snapshot(self.config_file)
        if config_change_verdict(self._disk_snapshot, disk_now, editor_text, self._baseline_content) == "conflict":
            answer = QMessageBox.question(
                self,
                i18n.tr("配置文件已变更"),
                i18n.tr(
                    "config.ini 在你打开本窗口之后已被外部修改（录制进程可能刚写入凭据、"
                    "平台清单或补写了缺失键）。\n\n"
                    "点击「是」仍按当前编辑内容保存：外部改动会被覆盖；\n"
                    "点击「否」取消保存，可先复制外部改动或重新加载文件。"
                ),
            )
            # 取消保存时不 accept：窗口保持打开，用户的编辑内容还在，
            # 关掉窗口等于替他做了「丢弃编辑」的决定。
            if answer != QMessageBox.StandardButton.Yes:
                self.hint_label.setText(i18n.tr("已取消保存：外部改动未被覆盖，可重新打开高级设置加载最新内容"))
                return
        try:
            save_text_to_file(editor_text, self.config_file)
        except Exception as e:
            QMessageBox.critical(self, i18n.tr("错误"), i18n.tr("保存配置文件失败: {e}", e=e))
            return
        self._baseline_content = editor_text
        # 磁盘基线取「写完之后重读的那份」而不是编辑器文本：保存会补末尾换行，
        # 直接用 editor_text 会少一个 \n，下一轮据此误判成外部改动。
        self._disk_snapshot, _ = read_config_snapshot(self.config_file)
        self._conflict_hint_shown = False
        self._notify(i18n.tr("高级设置配置已保存"))
        self.accept()

    def _notify(self, message: str) -> None:
        if callable(self._log):
            self._log(message)

    def set_focus(self) -> None:
        # 由主窗口在「已有一个实例」时调用：把已开的那个提到前台，而不是再开一个
        self.show()
        self.raise_()
        self.activateWindow()
        self.setWindowState(Qt.WindowState.WindowActive)
