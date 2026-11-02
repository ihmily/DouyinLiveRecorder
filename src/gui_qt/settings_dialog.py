# -*- coding: utf-8 -*-
# 高级设置：config.ini 全文编辑器。
#
# 为什么仍整文件编辑而不是逐项控件：config.ini 的键会随版本增删（缺键补写也是录制进程的
# 行为之一），做成结构化表单则每加一个键都要改 GUI，「用户想改但表里没有」也无法降级。
#
# MID-55 的两份基线（编辑器基线 + 磁盘快照）与保存前裁决必须保留：录制进程会在运行期
# 写回凭据、禁用 SSL 校验的平台清单与缺键，跨进程没有锁可依赖，整文件写回只能靠
# 显式检测 + 交用户裁决。
from __future__ import annotations

import os

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

        # 磁盘监听用 QTimer。注意「窗体销毁自动停」在这里走不到：对话框带 parent，close/hide
        # 不销毁 C++ 对象，启停必须按可见性自己管（见 hideEvent/showEvent），否则每开一次
        # 窗口就留下一个每 5s 读盘的幽灵定时器（M-15）。
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
    # 为什么判 hide/show 而不是 accept/reject：accept()/reject() 只是 done() → hide()，而
    # 标题栏 X、parent.close()、最小化到托盘后再关都只走 hide 这条路。
    # 为什么停表而不是复用同一实例：新建实例正是 _load_config() 重读磁盘、重建两份基线
    # （编辑器基线 + 磁盘快照，MID-55）的时机，复用就得新增重开时的重载路径并改动基线语义。
    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt 的重写点必须这个名
        self._watch_timer.stop()
        super().hideEvent(event)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt 的重写点必须这个名
        super().showEvent(event)
        if not self._watch_timer.isActive():
            self._watch_timer.start()

    def reload_from_disk(self) -> None:
        # M-35：窗口被复用时（关闭后再次打开）必须重新读盘，否则显示的是上次的快照，
        # 保存时还会把中间的磁盘改动静默覆盖掉。
        self._load_config()

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
            # [2026-10-30 L-03 备案] read_config_snapshot（gui_qt/shared.py）内部已吞全部 OSError
            # （以 None 哨兵表示「当时没读到」），本分支按现契约不可达；保留作实现变更时的兜底。
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
