# -*- coding: utf-8 -*-
# 与设计稿组件一一对应的通用控件：Card（圆角+投影）、StatusDot（呼吸动画）、StatTile
# （统计块）、Toast（底部浮层）、EmptyState（空状态引导）、TerminalText（终端只读框+着色）。
#
# 为什么单独成一层：同一枚设计 Token 在五个页面里都要出现，集中在此才能「改设计只改一处」；
# 且 QSS 全局层叠，控件共用的 objectName（card / nav / primary / terminal）必须由唯一工厂
# 发放，散落各处必然有人写错名字。
#
# 线程约定：本模块全部控件只能在**主线程**构造与调用（Qt 硬约束，跨线程违反是 UB/崩溃而非
# 告警），跨线程一律走 Signal。
from __future__ import annotations

from typing import Callable, Final

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QPainter,
    QResizeEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .theme import DUR_MED, EASE_SPRING, Palette


class Card(QFrame):
    # 设计稿 .card（radius-l 18 + shadow-m）。Qt 的 QSS border-radius 只能画圆角轮廓，
    # **投影必须挂 QGraphicsDropShadowEffect**——这也是选 PySide6 的理由之一。
    # 投影不做默认全挂：effect 会增加合成成本，``shadow=True`` 只给静态内容卡片，列表类不挂。
    def __init__(self, parent: QWidget | None = None, *, shadow: bool = True) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        if shadow:
            effect = QGraphicsDropShadowEffect(self)
            effect.setBlurRadius(16)
            effect.setOffset(0, 4)
            effect.setColor(QColor(0, 0, 0, 40))
            self.setGraphicsEffect(effect)


def card_layout(card: Card, margin: int = 18, spacing: int = 12) -> QVBoxLayout:
    # 卡片布局统一：留白与间距走设计稿的 16/18/20 一族，集中一处便于整体调整。
    layout = QVBoxLayout(card)
    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)
    return layout


def nav_button(text: str, parent: QWidget | None = None) -> QPushButton:
    btn = QPushButton(text, parent)
    btn.setObjectName("nav")
    # autoExclusive=False：导航项是「单选」语义，但 Qt 的同组互斥会把 ``checked`` 状态
    # 交由 pressed 维护，与页面切换回调里显式 setChecked 的路径打架，这里自行维护。
    btn.setCheckable(True)
    btn.setAutoExclusive(False)
    return btn


def action_button(text: str, variant: str = "", parent: QWidget | None = None) -> QPushButton:
    # variant: "" 普通 / "primary" 强调 / "danger" 危险 / "ghost" 次要。
    btn = QPushButton(text, parent)
    if variant:
        btn.setObjectName(variant)
    return btn


class ArrowComboBox(QComboBox):
    # 带自绘箭头的下拉。不用 QSS 的 ::down-arrow 有三个硬伤：只定义 ::drop-down 而不给 image
    # 时 Qt 会连原生箭头一起丢掉；border 三角会被画成实心方块（2026-10-17 实测）；
    # image: url(...) 需外置资源，打包后路径与主题色难同步。
    # 改用 QLabel 叠一个 "▾"：字形跟随 DPI，颜色走 QSS 的 objectName 选择器，切主题无需重建
    # 控件。箭头设 WA_TransparentForMouseEvents，点击仍落到下拉本体。
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._arrow = QLabel("▾", self)
        self._arrow.setObjectName("comboArrow")
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._place_arrow()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._place_arrow()

    def _place_arrow(self) -> None:
        # 宽度与 QSS 的 padding-right 对齐：箭头区固定 22px，右侧留 2px 内缩，
        # 既不压住最长选项的省略号，也不会在窄下拉里被边框裁掉一半。
        width = 22
        self._arrow.setGeometry(max(0, self.width() - width - 2), 0, width, self.height())
        self._arrow.raise_()


class StatusDot(QWidget):
    # 设计稿 .dot-live：6px 圆点 + pulse 动画。用 QTimer + 手写 paintEvent 实现呼吸：
    # timer 挂在控件自身，销毁即自动停，不必像旧版那样手工保存并 cancel 五处定时器 id。
    # 不用 QPropertyAnimation 改色——QColor 不是可直接缓动的 Qt 属性，成本高于按需重绘。
    _SIZES: tuple[int, ...] = (10, 12, 14, 16, 14, 12)

    def __init__(self, parent: QWidget | None = None, base: int = 14) -> None:
        super().__init__(parent)
        self.setFixedSize(base + 6, base + 6)
        self._base = base
        self._color = QColor("#c0392b")
        self._index = 0
        self._animating = False
        self._timer = QTimer(self)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._tick)
        self.repaint()

    def set_color(self, color: str, animate: bool) -> None:
        self._color = QColor(color)
        if animate and not self._animating:
            self._animating = True
            self._timer.start()
        elif not animate and self._animating:
            self._animating = False
            self._timer.stop()
            self._index = 0
        self.update()

    def stop(self) -> None:
        # 退出收尾必须显式停组：Qt 的 timer 绑定父对象、父销毁时会停，
        # 但主窗口 destroy 期间可能有未决 timeout 正在排队，先停一轮更稳。
        self._timer.stop()
        self._animating = False

    def _tick(self) -> None:
        self._index = (self._index + 1) % len(self._SIZES)
        self.update()

    def paintEvent(self, event: object) -> None:
        # 手写绘制而不是 QLabel + QSS：后者每帧都要重建整份 stylesheet 才会变色，
        # 在高 DPI 与窗口 resize 期间是明显的热点，而 QPainter 一次 drawEllipse 就够。
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        diameter = self._SIZES[self._index] if self._animating else self._base
        offset = (self.width() - diameter) / 2
        color = self._color
        if self._animating:
            # 呼吸=亮度往返（与旧版 _mix(SUCCESS, #4ADE80, ratio) 同语义）
            phase = (self._index / (len(self._SIZES) - 1)) * 2
            ratio = phase if phase <= 1 else 2 - phase
            color = QColor(
                int(color.red() + (109 - color.red()) * ratio),
                int(color.green() + (222 - color.green()) * ratio),
                int(color.blue() + (128 - color.blue()) * ratio),
            )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(int(offset), int(offset), diameter, diameter)
        painter.end()


class StatTile(QWidget):
    # 统计块：标题（muted）+ 大字数值。设计稿没有这一族直接对应物，用是最接近的
    # .suggest 卡片骨架（圆角 + 強調数值）派生，保证视觉权重顺序一致。
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.title = QLabel(title)
        self.title.setObjectName("muted")
        self.value = QLabel("-")
        self.value.setObjectName("statValue")
        value_font = QFont(self.value.font())
        value_font.setPointSize(18)
        value_font.setWeight(QFont.Weight.DemiBold)
        self.value.setFont(value_font)
        layout.addWidget(self.title)
        layout.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class Toast(QFrame):
    # 设计稿 .toast：底部居中、0.28s 缓动淡入、2s 自动消失。
    # 「自动消失」用单次 QTimer 而不是 QPropertyAnimation + deleteLater 链：后者在快速连续
    # 多条 toast 时会出现动画对象与部件的拥有权竞态（后一条在前一条 deleteLater 之前到达）。
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel("")
        self._label.setObjectName("toastText")
        layout.addWidget(self._label)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)
        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(DUR_MED)
        self._anim.setEasingCurve(QEasingCurve.Type[EASE_SPRING])

    def show_message(self, message: str, parent_rect_height: int, parent_width: int) -> None:
        self._label.setText(message)
        self.adjustSize()
        self._timer.stop()
        x = (parent_width - self.width()) // 2
        y = parent_rect_height - self.height() - 90
        hidden = QPoint(x, y + 12)
        shown = QPoint(x, y)
        self.move(hidden)
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(hidden)
        self._anim.setEndValue(shown)
        self._anim.start()
        self._timer.start(2000)


class EmptyState(QWidget):
    # 设计稿 .empty：图标 + 标题 + 说明的空状态引导（本轮把这套视觉落到日志/弹幕页）。
    # 为什么不用 QStackedWidget 在表格和空态之间切换 visibility：数据为空/**非空**切换非常频繁
    # （1s 一轮），切换 index 会触发布局重算与表格 resize；直接 setVisible 更轻。
    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon = QLabel("🎬")
        icon_font = QFont(self.icon.font())
        icon_font.setPointSize(30)
        self.icon.setFont(icon_font)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel(title)
        title_font = QFont(self.title.font())
        title_font.setPointSize(17)
        title_font.setWeight(QFont.Weight.DemiBold)
        self.title.setFont(title_font)
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.description = QLabel(description)
        self.description.setObjectName("muted")
        self.description.setWordWrap(True)
        self.description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 必须是固定宽而不是最大宽（2026-10-17 截图回归）：wordWrap 的 QLabel 只在**宽度确定**
        # 时才能算出多行高度（heightForWidth），只设 maximumWidth 时父布局按单行 sizeHint 分配
        # 高度，描述会被裁掉两行（画质页实测 geo 18px / hint 36px，弹幕页 18px / 54px）。420px 是
        # 设计稿文本列宽，页面最小内容宽 548 留有余量，不会横向溢出。
        self.description.setFixedWidth(420)
        self.description.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.icon)
        layout.addSpacing(8)
        layout.addWidget(self.title)
        layout.addWidget(self.description)


class _LogHighlighter(QSyntaxHighlighter):
    # 日志等级着色：只认 [ERROR] / [WARN] 两个行内标记，不做整行正则扫描。
    # QSyntaxHighlighter 按文本块重排，ffmpeg 刷屏时每块都触发；find 比 re.search 少一个数量级开销。
    _LEVELS: tuple[tuple[str, str], ...] = (("[ERROR]", "error"), ("[WARN]", "warn"))

    def __init__(self, document: QTextDocument, palette: Palette) -> None:
        super().__init__(document)
        self._formats: dict[str, QTextCharFormat] = {}
        self._apply_tokens(palette)

    def _apply_tokens(self, palette: Palette) -> None:
        # 颜色一律取自 src/gui_qt/theme.py 的令牌（terminal_error/terminal_warn），
        # 不得在这里写死十六进制——整窗配色的事实源只有一处（Qt 硬约束①）。
        formats: dict[str, QTextCharFormat] = {}
        for level, key in (("error", "terminal_error"), ("warn", "terminal_warn")):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(palette.token(key)))
            formats[level] = fmt
        self._formats = formats

    def set_palette(self, palette: Palette) -> None:
        # 主题/缩放/字体切换后只换色表并重刷既有条目（M-16）：不新建实例——QSyntaxHighlighter
        # 以 document 为父对象，旧实例永不销毁且仍参与高亮，切 N 次就叠 N 个。
        self._apply_tokens(palette)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        for marker, level in self._LEVELS:
            index = text.find(marker)
            while index != -1:
                self.setFormat(index, len(marker), self._formats[level])
                index = text.find(marker, index + len(marker))


# 等宽字体工厂：QFont 的族名位只接受**单个** family，把 CSS 式的
# "Consolas, Menlo, Courier New, monospace" 整串塞进去等于请求一个不存在的族名。
# [实测 2026-10-17] 候选全缺时 Qt 按 styleHint=Monospace（枚举值 7）落进遗留别名 "Terminal"，
# 一轮构造打出两条告警：DirectWrite CreateFontFaceFromHDC() failed（Family="Terminal"）与
# "QFont::setPointSize: Point size <= 0 (-1)"。
# 唯一写法是按候选顺序取第一个本机真实存在的族名；全缺时交回平台的系统固定宽度字体
# （QFontDatabase.FixedFont 保证本机可用）。styleHint(Monospace) 只在候选命中后设置。
# point_size 留 None 的站点刻意不设定值、继续继承 QSS 的 px 字号（缩放档位要吃它）。
_FIXED_FONT_CANDIDATES: Final[tuple[str, ...]] = (
    "Consolas",
    "Menlo",
    "DejaVu Sans Mono",
    "Liberation Mono",
    "Courier New",
)


def fixed_font(point_size: int | None = None) -> QFont:
    installed = {name.casefold() for name in QFontDatabase.families()}
    matched = next((name for name in _FIXED_FONT_CANDIDATES if name.casefold() in installed), "")
    if matched:
        font = QFont(matched)
        font.setStyleHint(QFont.StyleHint.Monospace)
    else:
        font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if point_size is not None:
        font.setPointSize(point_size)
    return font


class TerminalText(QPlainTextEdit):
    # 终端只读框：等宽字 + 终端配色 + 行级着色 + 上限行自动截断。
    #
    # 用 QPlainTextEdit 而不是 QTextEdit：后者是富文本引擎，同量级行数下内存与布局成本高一个
    # 量级；日志页只需 append，且 maximumBlockCount 直接取代旧版手算的总行数裁剪。
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("terminal")
        self.setReadOnly(True)
        # 换行跟随控件宽度（WidgetWidth）：日志行普遍长于视口（平台状态行 / URL / 掩码占位），
        # NoWrap 只能横向滚动；WidgetWidth 下 Qt 在控件 resize 时对既有块自动重排折行，
        # 「窗口拖宽 → 折行变少」无需手动干预。长无空格串的断行点由 QPlainTextEdit 默认
        # wordWrapMode（WrapAtWordBoundaryOrAnywhere）承担，不必显式再设。
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setMaximumBlockCount(1000)
        self.setFont(fixed_font(11))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # 同一 document 只挂一个高亮器（M-16）：apply_highlighter 每次主题/缩放/字体切换
        # 都会被调到，这里持引用、首建之后一律走 set_palette 复用。
        self._highlighter: _LogHighlighter | None = None

    def apply_highlighter(self, palette: Palette) -> None:
        # 只建一次，后续仅更新色表并 rehighlight()，让既有条目按新主题重刷。
        # [历史注] 旧实现每次调用都新建高亮器，切 N 次主题叠 N 个（颜色错乱 + N 份重复高亮，M-16）。
        if self._highlighter is None:
            self._highlighter = _LogHighlighter(self.document(), palette)
        else:
            self._highlighter.set_palette(palette)

    def append_line(self, text: str) -> None:
        # 走光标在末尾插入而不是 appendPlainText：后者会强制新建段落并额外补一个换行，
        # 而调用方传入的行已经带 \n —— 用它会在日志里多出双倍空行。
        # M-81（2026-10-21）：textCursor() 返回的是**副本**，在副本上 move/insertText 只改
        # 文档、不改控件自己的光标——旧实现写完后控件仍停在插入前的位置，日志面板不跟随
        # 最新行（表现为「在录，日志页却定格不动」）。insertText 必须保留（appendPlainText
        # 的双换行老坑不回归），补的只是 setTextCursor 这一步，与弹幕页 _render_stream
        # 的同形态写法（cursor 定位末尾后 setTextCursor）对齐。
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text if text.endswith("\n") else text + "\n")
        self.setTextCursor(cursor)

    def sizeHint(self) -> QSize:
        return QSize(600, 320)


def connect_click(button: QPushButton, handler: Callable[[], None]) -> None:
    # 把 clicked(bool checked) 收仄成无参回调：QPushButton.clicked 总带一个 checked 形参,
    # 不收仄就得在每个 handler 上加 `*args`，那样 mypy 的 disallow_untyped_defs 会 loosen 掉形参考察。
    button.clicked.connect(lambda _checked: handler())
