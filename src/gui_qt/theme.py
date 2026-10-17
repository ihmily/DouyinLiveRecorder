# -*- coding: utf-8 -*-
# GUI 窗口层（PySide6）设计令牌与样式表生成器。
#
# 为什么独立成 token 层而不是把颜色写死在各控件里：设计稿 docs/gui-redesign/index.html
# 的视觉语言（配色 / 圆角 / 阴影 / 缓动）全部定义在 :root 的 CSS 变量里，本模块把那套变量
# 搬成 Python 侧唯一事实源，QSS 由它渲染——主题切换只需要换一份 token 重生成 QSS，
# 不需要在任何控件上逐个 setStyleSheet（那必然出现「改了这边忘了那边」的中间态）。
#
# 选型说明（本轮的框架决策依据，勿删）：
#   - ttk 无法原生实现 18/24px 大圆角卡片与柔和投影：只能退成「方角卡片」或用 Canvas
#     自绘补形状，而自绘控件不参与布局系统的尺寸协商（2026-10-17 实测确认），与
#     「缩放档位要能吃 Alongside 各种语言标签宽度」的需求直接冲突；
#   - PySide6 的 QSS + QGraphicsDropShadowEffect 能 1:1 还原上面这四种效果，且
#     QTableView / QTextEdit 自带虚拟化与块上限，高吞吐场景（日志、弹幕）不需要
#     自建 rendering 节流；
#   - 代价是打包体积（Qt6 运行时）与 LGPL 动态链接分发约束，已在 docs/worklog/
#     PROPOSAL_2026-10-17_gui-pyside6-redesign.md 记录并获批准。
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# 主题 ID 与前 ttk 主题层（src/ui_theme.py）保持一致：config.ini [GUI] gui_theme
# 里已持久化的取值必须被两套实现都能识别，否则用户在旧版选过的主题换了窗口层就失效。
THEME_LIGHT: Final[str] = "light"
THEME_DARK: Final[str] = "dark"
THEME_HIGH_CONTRAST: Final[str] = "high_contrast"
THEME_IDS: Final[tuple[str, ...]] = (THEME_LIGHT, THEME_DARK, THEME_HIGH_CONTRAST)
# 「跟随系统」是哨兵 ID 而不是第三个状态：它不写进 config.ini（持久化的是空串），
# 只在下拉的 currentData 里流转，故此值必须不可能与真实主题 ID 撞上。
FOLLOW_SYSTEM_ID: Final[str] = "_follow_system_"

# 显示名在窗口层自持而不是复用 ui_theme 的 _THEME_LABELS：
# 那份是私有的、且服务于 ttk 的 ThemeManager，窗口层反向依赖它会把两套实现焊死。
THEME_LABELS: Final[dict[str, str]] = {
    THEME_LIGHT: "浅色",
    THEME_DARK: "深色",
    THEME_HIGH_CONTRAST: "高对比度",
}

# 圆角档位（设计稿 --radius-s/m/l/xl：8 / 12 / 18 / 24）
RADIUS_SM: Final[int] = 8
RADIUS_MD: Final[int] = 12
RADIUS_LG: Final[int] = 18
RADIUS_XL: Final[int] = 24

# 侧边栏与顶栏基准尺寸（设计稿 --sidebar-w: 272px / topbar 52px）
SIDEBAR_WIDTH: Final[int] = 272
TOPBAR_HEIGHT: Final[int] = 52

# 布局基准：设计稿 .chat-col 是 760px 居中内容列，这里用作页面的最大内容宽，
# 宽屏下避免统计卡片被拉得过长、表格列视觉失衡。
# 只作为上限使用（不强行居中）：桌面窗口的可用宽多数达不到两列布局的最低要求。
CONTENT_MAX_WIDTH: Final[int] = 760

# 动效时长（毫秒）：设计稿 --dur-fast .16s / --dur-med .28s
DUR_FAST: Final[int] = 160
DUR_MED: Final[int] = 280
# 缓动曲线：设计稿 spring cubic-bezier(.34,1.4,.44,1) 与 out cubic-bezier(.22,.8,.36,1)。
# 之所以做成字符串而不是直接引 QEasingCurve：本模块刻意不 import PySide6，
# 「纯数据 token 层」可被测试直接导入，不必先起一个 QApplication。
# QEasingCurve 不能直接吃 CSS 贝塞尔，用 Qt 提供的近似曲线（OutBack ≈ 回弹感，
# OutCubic ≈ 减速），并在 _EASING_BACK 里保留原曲线控制点注释供将来精确化。
EASE_OUT: Final[str] = "OutCubic"
EASE_SPRING: Final[str] = "OutBack"

# 令牌完整键集：新增令牌必须三份主题同时补齐，缺键会被
# tests/test_gui_qt_theme.py 的完整性契约直接判红。
TOKEN_KEYS: Final[tuple[str, ...]] = (
    "bg_app",
    "bg_sidebar",
    "bg_content",
    "bg_elevated",
    "bg_hover",
    "bg_active",
    "accent",
    "accent_hover",
    "accent_soft",
    "danger",
    "danger_soft",
    "success",
    "success_soft",
    "warn",
    "text_1",
    "text_2",
    "text_3",
    "border",
    "border_strong",
    "terminal_bg",
    "terminal_fg",
    "terminal_dim",
    "terminal_error",
    "terminal_warn",
    "terminal_select",
)

# 浅色令牌：逐值来自设计稿 :root[data-theme="light"]。
# terminal_* 五个键设计稿没有对应物——录制动线与日志页要用终端配色，而终端色必须
# **与主题无关**（原 ttk 版 Colors.TERMINAL_* 同为常量），否则深色主题下日志可读性
# 反而下降；这里仍按主题给一份是为了让切换主题时整体观感不撕裂。
_LIGHT: Final[dict[str, str]] = {
    "bg_app": "#f7f7f5",
    "bg_sidebar": "#f0efec",
    "bg_content": "#f7f7f5",
    "bg_elevated": "#ffffff",
    "bg_hover": "rgba(0,0,0,0.045)",
    "bg_active": "rgba(0,0,0,0.07)",
    "accent": "#c96442",
    "accent_hover": "#b5573a",
    "accent_soft": "rgba(201,100,66,0.10)",
    "danger": "#c0392b",
    "danger_soft": "rgba(192,57,43,0.10)",
    "success": "#2e8540",
    "success_soft": "rgba(46,133,64,0.12)",
    "warn": "#a86a1b",
    "text_1": "#1a1a1a",
    "text_2": "#5c5c5c",
    "text_3": "#9a9a9a",
    "border": "rgba(0,0,0,0.08)",
    "border_strong": "rgba(0,0,0,0.14)",
    "terminal_bg": "#1e1e24",
    "terminal_fg": "#e8e6e3",
    "terminal_dim": "#8a8a94",
    "terminal_error": "#ff8f6b",
    "terminal_warn": "#e8c37a",
    "terminal_select": "rgba(201,100,66,0.30)",
}

# 深色令牌：逐值来自设计稿 :root[data-theme="dark"]。
_DARK: Final[dict[str, str]] = {
    "bg_app": "#1b1b19",
    "bg_sidebar": "#171716",
    "bg_content": "#1b1b19",
    "bg_elevated": "#262624",
    "bg_hover": "rgba(255,255,255,0.05)",
    "bg_active": "rgba(255,255,255,0.09)",
    "accent": "#d97757",
    "accent_hover": "#e08a6c",
    "accent_soft": "rgba(217,119,87,0.14)",
    "danger": "#e05d5d",
    "danger_soft": "rgba(224,93,93,0.14)",
    "success": "#5fbf7c",
    "success_soft": "rgba(95,191,124,0.16)",
    "warn": "#dcb26a",
    "text_1": "#ececea",
    "text_2": "#a3a3a0",
    "text_3": "#6b6b68",
    "border": "rgba(255,255,255,0.08)",
    "border_strong": "rgba(255,255,255,0.16)",
    "terminal_bg": "#121216",
    "terminal_fg": "#e8e6e3",
    "terminal_dim": "#7a7a85",
    "terminal_error": "#ff9d7a",
    "terminal_warn": "#e8c37a",
    "terminal_select": "rgba(217,119,87,0.34)",
}

# 高对比度：保留旧 ttk 层的第三个主题 ID（用户可能已持久化），取值以「文本对比度优先」
# 为原则——纯黑纯白 + 高饱和 accent，供弱视用户使用。它不在设计稿里，故不与设计稿逐值对齐。
_HIGH_CONTRAST: Final[dict[str, str]] = {
    "bg_app": "#ffffff",
    "bg_sidebar": "#f2f2f2",
    "bg_content": "#ffffff",
    "bg_elevated": "#ffffff",
    "bg_hover": "rgba(0,0,0,0.10)",
    "bg_active": "rgba(0,0,0,0.16)",
    "accent": "#a13c1c",
    "accent_hover": "#8a2f13",
    "accent_soft": "rgba(161,60,28,0.16)",
    "danger": "#a1130a",
    "danger_soft": "rgba(161,19,10,0.14)",
    "success": "#155724",
    "success_soft": "rgba(21,87,36,0.16)",
    "warn": "#7d4a05",
    "text_1": "#000000",
    "text_2": "#202020",
    "text_3": "#4a4a4a",
    "border": "rgba(0,0,0,0.24)",
    "border_strong": "rgba(0,0,0,0.45)",
    "terminal_bg": "#000000",
    "terminal_fg": "#ffffff",
    "terminal_dim": "#c8c8c8",
    "terminal_error": "#ff8f6b",
    "terminal_warn": "#ffd479",
    "terminal_select": "rgba(255,255,255,0.28)",
}

# ID → 令牌表的唯一映射；三份主题的键集相等由 test_gui_qt_theme 的契约用例守住
_PALETTES: Final[dict[str, dict[str, str]]] = {
    THEME_LIGHT: _LIGHT,
    THEME_DARK: _DARK,
    THEME_HIGH_CONTRAST: _HIGH_CONTRAST,
}


@dataclass(frozen=True)
class Palette:
    # 一次 parsed 出来的主题上下文：ID + token 表 + 派生尺寸。
    # 不可变是刻意的：Qt 的样式是**全局**的，把 token 带来带去必须防止半途被改，
    # 否则「主题切换后部分控件仍是旧色」这类最难查的中间态就会出现。
    theme_id: str
    tokens: dict[str, str]
    scale: float

    def px(self, base: int | float) -> int:
        # max(1, ...)：0 半径/0 宽度的边框在 Qt 下会被解读成「无边框」而不是 1 像素，
        # 缩放档位很低时若算出 0，视觉上等于样式丢失。
        # 按缩放系数走一遍的量：设计的基准 pixel 值 × 用户缩放档。
        return max(1, round(base * self.scale))

    def token(self, key: str) -> str:
        # 未知键直接抛而不是回落空串：空颜色会让 QSS 静默吞掉整条声明，
        # 排查成本远高于启动期的一次 KeyError。
        value = self.tokens.get(key)
        if value is None:
            raise KeyError(f"未知设计令牌: {key!r}")
        return value


def palette(theme_id: str, scale: float = 1.0) -> Palette:
    # tokens 直接引用共享的 dict 而不 copy：Palette 是 frozen 且约定只读，
    # 每次切主题复制一份 26 键的 dict 在高频切换（拖拽缩放档）下是纯浪费。
    # 未知 ID 一律落回浅色：主题偏好来自 config.ini，可能被外部手写成任意值，
    # 宁可显示错的浅色也不能 KeyError 起不来窗口。
    tokens = _PALETTES.get(theme_id, _LIGHT)
    return Palette(theme_id=theme_id, tokens=tokens, scale=scale)


def is_dark(theme_id: str) -> bool:
    # 只有真·深色算深色：高对比度是白底黑字，按深色给它配反色图标会全看不见
    return theme_id == THEME_DARK


def build_stylesheet(pal: Palette) -> str:
    # 生成全窗单一 QSS。由调用方全局 setStyleSheet 一次生效，避免逐控件 setStyleSheet
    # 造成的层叠不确定（后设置者只覆盖父级的子集，且很难复现第二次）。
    t = pal.tokens
    s = pal.scale

    # 内层 px() 直接产出带单位的字符串：QSS 里每一处都要单位，
    # 逐个写 f"{pal.px(x)}px" 会让模板长到无法校对。
    def px(base: int | float) -> str:
        return f"{pal.px(base)}px"

    # objectName → 选择性子选择器：`QFrame#card` 而不是 `QFrame`（后者会命中布局里所有
    # Frame，包括 `QTableView` 的内嵌 frame）。Qt 的 QSS 不认 CSS 的 `#id` 与 `.class`
    # 双重用法，objectName 选择器是唯一的内置手段。
    #
    # [2026-10-17 截图回归] 底色不能再挂在 `QWidget` 通配选择器上：Qt 会把这条声明应用到
    # **所有** QWidget 子类，于是 QLabel / StatTile / EmptyState 这些本该透明的子控件
    # 各自被刷成 bg_app，在 bg_elevated 的白色卡片上留下一块块灰条灰块（红框截图的
    # 直接成因）。底色只由窗口级容器声明，其余子控件靠父级透出；文本/字体/选中色仍留在
    # QWidget 上，保证下沉到任意深度的控件都能继承一套排版基线。
    return f"""
QMainWindow, QDialog {{
    background: {t['bg_app']};
}}

QWidget {{
    color: {t['text_1']};
    font-size: {px(13.5)};
    selection-background-color: {t['accent_soft']};
    selection-color: {t['text_1']};
}}

QWidget#sidebar {{
    background: {t['bg_sidebar']};
    border-right: 1px solid {t['border']};
}}

QWidget#topbar {{
    background: {t['bg_content']};
    border-bottom: 1px solid {t['border']};
}}

QWidget#content {{
    background: {t['bg_content']};
}}

/* ── 卡片（设计稿 .card：radius 18 + shadow-m） ── */
QFrame#card {{
    background: {t['bg_elevated']};
    border: 1px solid {t['border']};
    border-radius: {px(RADIUS_LG)};
}}
QFrame#card:hover {{
    border-color: {t['border_strong']};
}}

/* ── 按钮 ── */
QPushButton {{
    background: {t['bg_elevated']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: {px(RADIUS_MD)};
    padding: {px(7)} {px(14)};
}}
QPushButton:hover {{
    border-color: {t['accent']};
    color: {t['accent']};
}}
QPushButton:pressed {{
    background: {t['bg_hover']};
}}
QPushButton:disabled {{
    color: {t['text_3']};
    border-color: {t['border']};
}}
QPushButton#primary {{
    background: {t['accent']};
    color: {t['bg_elevated']};
    border: 1px solid {t['accent']};
}}
QPushButton#primary:hover {{
    background: {t['accent_hover']};
    color: {t['bg_elevated']};
}}
QPushButton#primary:disabled {{
    background: {t['text_3']};
    border-color: {t['text_3']};
    color: {t['bg_elevated']};
}}
QPushButton#danger {{
    background: {t['bg_elevated']};
    color: {t['danger']};
    border: 1px solid {t['danger']};
}}
QPushButton#danger:hover {{
    background: {t['danger_soft']};
    color: {t['danger']};
}}
QPushButton#danger:disabled {{
    color: {t['text_3']};
    border-color: {t['border']};
}}
QPushButton#ghost {{
    background: transparent;
    border: 1px solid {t['border']};
}}
QPushButton#ghost:hover {{
    border-color: {t['accent']};
    background: {t['bg_hover']};
}}

/* ── 侧边栏导航项（设计稿 .history-item：8px 圆角、hover 浅底、active 略深） ── */
QPushButton#nav {{
    background: transparent;
    border: none;
    border-radius: {px(RADIUS_SM)};
    padding: {px(9)} {px(12)};
    text-align: left;
    color: {t['text_2']};
}}
QPushButton#nav:hover {{
    background: {t['bg_hover']};
    color: {t['text_1']};
}}
QPushButton#nav:checked {{
    background: {t['bg_active']};
    color: {t['text_1']};
    font-weight: 600;
}}

/* ── 输入类控件 ── */
QPlainTextEdit, QTextEdit {{
    background: {t['bg_elevated']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
    border-radius: {px(RADIUS_MD)};
    selection-background-color: {t['accent_soft']};
}}
QPlainTextEdit:focus, QTextEdit:focus {{
    border-color: {t['accent']};
}}
QLineEdit {{
    background: {t['bg_elevated']};
    border: 1px solid {t['border_strong']};
    border-radius: {px(RADIUS_MD)};
    padding: {px(6)} {px(10)};
}}
QComboBox {{
    background: {t['bg_elevated']};
    border: 1px solid {t['border_strong']};
    border-radius: {px(RADIUS_SM)};
    padding: {px(5)} {px(10)};
    /* 右侧给自绘箭头留位（widgets.ArrowComboBox 固定占 22px + 2px 内缩）：
       不留位时超长选项文本会钻到箭头下面，两者叠字。 */
    padding-right: {px(30)};
    min-height: {px(18)};
}}
QComboBox:hover {{
    border-color: {t['accent']};
}}
/* 原生 drop-down 一律收窄到 0：它的默认按钮底在纯白输入框上是一条可见白缝
   （截图红框处），而 QSS 接管后箭头又不会自己绘制。箭头改由 ArrowComboBox
   的 QLabel 承担，颜色与字号在这里统一。 */
QComboBox::drop-down {{
    width: 0px;
    border: none;
    background: transparent;
}}
QLabel#comboArrow {{
    color: {t['text_2']};
    font-size: {px(13)};
    background: transparent;
}}
QComboBox QAbstractItemView {{
    background: {t['bg_elevated']};
    border: 1px solid {t['border_strong']};
    selection-background-color: {t['accent_soft']};
    selection-color: {t['text_1']};
}}

/* ── 侧栏滚动区（导航 + 偏好设置）──
   侧栏内容的最小高度实测 719px，窗口最小高度却允许 620px：不设滚动时
   QVBoxLayout 会把品牌区与「导入字体…」按钮一起压扁（2026-10-17 截图里按钮只剩半高）。
   滚动区自身 minimumSizeHint 很小，因此由它吸收高度不足，其余区段保持设计尺寸。 */
QScrollArea#sidebarScroll {{
    background: transparent;
    border: none;
}}

QScrollArea#sidebarScroll > QWidget > QWidget {{
    background: transparent;
}}

/* ── 表格（画质 / 弹幕统计）：扁平化表头，无纵向网格线 ── */
QTableView {{
    background: {t['bg_elevated']};
    border: 1px solid {t['border']};
    border-radius: {px(RADIUS_MD)};
    gridline-color: {t['border']};
    selection-background-color: {t['accent_soft']};
    selection-color: {t['text_1']};
}}
QTableView::item {{
    padding: {px(4)} {px(8)};
}}
QHeaderView::section {{
    background: {t['bg_elevated']};
    color: {t['text_2']};
    border: none;
    border-bottom: 1px solid {t['border']};
    padding: {px(6)} {px(8)};
    font-weight: 600;
}}

/* ── 终端区（日志 / 弹幕流）：配色刻意不随主题（见上面 terminal_* 注释） ── */
QTextEdit#terminal, QPlainTextEdit#terminal {{
    background: {t['terminal_bg']};
    color: {t['terminal_fg']};
    border: 1px solid {t['border']};
    border-radius: {px(RADIUS_MD)};
    selection-background-color: {t['terminal_select']};
}}

/* ── 滚动条（设计稿 6px 细条 + 半透明滑块） ── */
QScrollBar:vertical {{
    background: transparent;
    width: {px(6)};
    margin: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: {px(6)};
    margin: 0;
}}
QScrollBar::handle {{
    background: {t['border_strong']};
    border-radius: {px(3)};
    min-height: {px(24)};
}}
QScrollBar::handle:hover {{
    background: {t['accent']};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ── 状态胶囊 / Toast ── */
QFrame#pill {{
    background: {t['bg_active']};
    border-radius: {px(RADIUS_MD)};
}}
QLabel#muted {{
    color: {t['text_2']};
}}
QLabel#dim {{
    color: {t['text_3']};
}}
QLabel#statValue {{
    font-weight: 650;
}}
QFrame#toast {{
    background: {t['text_1']};
    border-radius: {px(20)};
}}
QLabel#toastText {{
    color: {t['bg_app']};
    font-weight: 500;
    padding: {px(8)} {px(16)};
}}
QToolTip {{
    background: {t['bg_elevated']};
    color: {t['text_1']};
    border: 1px solid {t['border_strong']};
}}
"""
