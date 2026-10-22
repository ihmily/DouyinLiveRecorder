# src/ui_theme.py
# GUI 主题层：语义 token + 多主题 + ttk 主题注册 + 偏好持久化 + WCAG 对比度自证。
#
# 设计约束（「一切走语义槽位」铁律）：
#   · 全部颜色经由语义槽位引用，任何主题不得绕过槽位直写控件颜色——多套主题由同一组槽位
#     派生，避免「每套主题各写一遍颜色」的漂移；对比度因此可以机检（见 CONTRAST_REQUIREMENTS）。
#   · 槽位清单 = 十二槽 + on_primary：深色/高对比主题下主按钮填充是亮色，按钮标签需要反色
#     前景，`surface`（面板底色）在深色主题里兼作按钮前景的语义不成立，故单列一槽；
#     浅色主题 on_primary == surface（#FFFFFF），该槽在浅色下是中性的。
#   · 品牌色为暖赭橙（对齐 docs/gui-redesign 设计语言）：light primary #B5573A（白字 4.78:1）、
#     dark primary #B85A3F（白字 4.59:1），深色 hover 取更暗的 #A8502F——深色主题下 hover 若
#     调亮会跌破白字 4.5 契约。[历史注] 更早的品牌蓝 #4F6DF5 白字仅 4.34:1，曾加深为 #4358E8。
#   · 本模块不创建窗口、不依赖显示器：import 期只定义数据与纯函数，Tk 相关工作全部发生在
#     ThemeManager.apply(root) 调用期（无头 Linux CI 可安全 import，`import gui` 链路不受影响）。
#   · 持久化走 config.ini [GUI] gui_theme（键名无 configparser 分隔符 `=` / `:`），写入经
#     src/web_config.update_or_append_config_line（缺节/缺键补建 + 行级注释保留 + 原子写），
#     刻意不用 config_io.read_config_value：它写回时持 main.file_update_lock，与录制进程耦合。
#   · 颜色之外的**尺寸**统一由 src/ui_scale.ScaleProfile 派生：ttk 的 padding、Treeview 的
#     rowheight 不再写死像素，而取 scale.px()/scale.padding()/scale.row_height()。
from __future__ import annotations

import configparser
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Final, cast, final

from src.config_read import tolerant_config_parser
from src.ui_scale import (
    CONTROL_PADDING,
    CONTROL_PADDING_COMPACT,
    CONTROL_PADDING_NAV,
    CONTROL_PADDING_ROW,
    FONT_FAMILY,
    ScaleProfile,
)
from src.web_config import update_or_append_config_line

# 语义槽位全集：每套主题必须逐槽给出（tests/test_ui_theme.py 的注册表完整性锁强制）。
TOKEN_NAMES: tuple[str, ...] = (
    "surface",
    "surface_alt",
    "border",
    "on_primary",
    "text",
    "text_muted",
    "primary",
    "primary_hover",
    "success",
    "danger",
    "warning",
    "disabled_bg",
    "disabled_fg",
)

# 主题 id 全集（持久化值即 id 原文，故必须是安全的配置值：无空格无分隔符）。
THEME_IDS: tuple[str, ...] = ("light", "dark", "high_contrast")

# 用户配置缺失/非法时的回退主题。选 dark 而非 light：运行日志与弹幕终端本就是深色底
# （Colors.TERMINAL_BG），dark 主题下与既有视觉的跳变最小。
DEFAULT_THEME = "dark"

# 三套主题的 token 取值。全部取值经 CONTRAST_REQUIREMENTS 机检达标（tests/test_ui_theme.py 持续回归）。
THEMES: dict[str, dict[str, str]] = {
    # 暖中性 + 赭橙主色（设计语言见 docs/gui-redesign）。border 不得取浅灰：
    # CONTRAST_REQUIREMENTS 强制 border 对两种底 ≥3.0（非文本 WCAG 1.4.11），故浅色主题边框落到
    # 暖灰 #7A766F 一档；成功/危险/警告语义色沿用原值（对比度契约已锁定，改版只动品牌色与中性色）。
    "light": {
        "surface": "#FFFFFF",
        "surface_alt": "#F7F7F5",
        "border": "#7A766F",
        "on_primary": "#FFFFFF",
        "text": "#1A1A1A",
        "text_muted": "#5C5C5C",
        "primary": "#B5573A",
        "primary_hover": "#9C4A2C",
        "success": "#15803D",
        "danger": "#DC2626",
        "warning": "#C2690A",
        "disabled_bg": "#E8E5E0",
        "disabled_fg": "#6E6A63",
    },
    "dark": {
        "surface": "#262624",
        "surface_alt": "#1B1B19",
        "border": "#8F8B84",
        "on_primary": "#FFFFFF",
        "text": "#ECECEA",
        "text_muted": "#A3A3A0",
        "primary": "#B85A3F",
        "primary_hover": "#A8502F",
        "success": "#15803D",
        "danger": "#DC2626",
        "warning": "#D97706",
        "disabled_bg": "#33322F",
        "disabled_fg": "#8F8B84",
    },
    "high_contrast": {
        "surface": "#000000",
        "surface_alt": "#111111",
        "border": "#FFFFFF",
        "on_primary": "#000000",
        "text": "#FFFFFF",
        "text_muted": "#D0D4DC",
        "primary": "#A9BCFF",
        "primary_hover": "#C3D2FF",
        "success": "#4ADE80",
        "danger": "#FF6B6B",
        "warning": "#FFB224",
        "disabled_bg": "#1F1F1F",
        "disabled_fg": "#A8A8A8",
    },
}

# 对比度契约（机检判据）：(前景槽位, 背景槽位, 最低比值)。
#   4.5 = WCAG 1.4.3 正文 AA（按钮标签、正文、次级文字均按正文计——13px 未达「大字」门槛）；
#   3.0 = WCAG 1.4.11 非文本（边框、状态色块、焦点环）+ 禁用态自加压（WCAG 豁免禁用控件，
#         这里仍取 3.0 自证，避免「禁用即随便灰」漂移）。
# 新增槽位/组合时先在此登记，再取色——机检是取色的前置门，不是事后核对。
# 已含三对按钮标签组合：primary/surface_alt（导航选中态 fg/bg）、on_primary/success、
# on_primary/danger，一律按正文 4.5 登记；为此 light/dark 的 success 加深到 #15803D
# （白字 3.30→5.01），high_contrast 的 success=#4ADE80 配黑字 12.05、danger 两态白字 4.83 /
# 黑字 7.57 均天然达标），gui.Colors.SUCCESS 同批同步取值。
CONTRAST_REQUIREMENTS: tuple[tuple[str, str, float], ...] = (
    ("text", "surface", 4.5),
    ("text", "surface_alt", 4.5),
    ("text_muted", "surface", 4.5),
    ("text_muted", "surface_alt", 4.5),
    ("on_primary", "primary", 4.5),
    ("on_primary", "primary_hover", 4.5),
    ("primary", "surface", 3.0),
    ("primary", "surface_alt", 3.0),
    ("on_primary", "success", 4.5),
    ("on_primary", "danger", 4.5),
    ("success", "surface", 3.0),
    ("danger", "surface", 3.0),
    ("warning", "surface", 3.0),
    ("success", "surface_alt", 3.0),
    ("danger", "surface_alt", 3.0),
    ("warning", "surface_alt", 3.0),
    ("border", "surface", 3.0),
    ("border", "surface_alt", 3.0),
    ("disabled_fg", "disabled_bg", 3.0),
)

_HEX_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")

# 持久化落点：config.ini [GUI] gui_theme（提案假设 #2，用户未要求独立文件）。
GUI_SECTION = "GUI"
THEME_KEY = "gui_theme"


def is_valid_hex(color: str) -> bool:
    # 严格 #RRGGBB：tk 颜色语法还接受 #RGB / 颜色名，这里刻意收窄——token 只允许
    # 六位十六进制，保证对比度计算与 ttk configure 都拿到确定形态。
    return _HEX_PATTERN.match(color) is not None


def detect_system_appearance() -> str:
    # 探测操作系统明暗偏好，返回主题 id（"light" 或 "dark"）。
    # Windows 读注册表 AppsUseLightTheme（0=深色）；macOS 走 `defaults read -g AppleInterfaceStyle`
    # （键缺失/命令失败 = 浅色）；其余平台无统一口径按浅色兜底。任何探测失败一律回 "light"——
    # 探测只是「跟随系统」的默认值来源，绝不能让 GUI 起不来（仅 GUI 运行期调用）。
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) != 0 else "dark"
        except OSError:
            # 键不存在 / 权限不足：按浅色兜底（企业策略锁定的机器上注册表读取可能被拒）
            return "light"
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                timeout=2,
            )
            return "dark" if result.returncode == 0 else "light"
        except OSError, subprocess.TimeoutExpired:
            return "light"
    return "light"


def _linearize(channel: int) -> float:
    # sRGB → 线性 RGB（WCAG 相对亮度公式的逐通道步骤；0.03928 是 8bit 分段阈值）。
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    # WCAG 2.x 相对亮度：R/G/B 分别按 0.2126/0.7152/0.0722 加权。
    if not is_valid_hex(color):
        raise ValueError(f"非法颜色值（须为 #RRGGBB）: {color!r}")
    raw = color.lstrip("#")
    r = _linearize(int(raw[0:2], 16))
    g = _linearize(int(raw[2:4], 16))
    b = _linearize(int(raw[4:6], 16))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float:
    # WCAG 对比度：(较亮亮度 + 0.05) / (较暗亮度 + 0.05)，值域 [1.0, 21.0]。
    # 0.05 的偏置保证纯黑（亮度 0）参与比较时分母不为零。
    lum_fg = relative_luminance(fg)
    lum_bg = relative_luminance(bg)
    lighter = max(lum_fg, lum_bg)
    darker = min(lum_fg, lum_bg)
    return (lighter + 0.05) / (darker + 0.05)


# 变体按钮悬停/按下的压暗比例（唯一取值点）。裸写 0.18 六处的读者无法判断它是不是
# 同一份口径；提为具名常量后「悬停色偏深一点」只剩一个落点（L-02 / L-05）。
_HOVER_SHADE_RATIO: Final[float] = 0.18


def _shade(color: str, ratio: float) -> str:
    # 把 #RRGGBB 向黑色方向压暗 ratio（0..1），返回同形态十六进制。
    # ttk 变体按钮（Success/Danger.TButton）的悬停色由此从基础槽位派生——
    # success/danger 没有配对的 *_hover 槽位，手写第二套色值必漂移。
    raw = color.lstrip("#")
    r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return f"#{round(r * (1 - ratio)):02X}{round(g * (1 - ratio)):02X}{round(b * (1 - ratio)):02X}"


def load_theme_preference(config_file: str | Path) -> str:
    # 读取 [GUI] gui_theme。返回 "" 表示「未设置」（节/键缺失、值为空、值不在 THEME_IDS），
    # 调用方应回退到 detect_system_appearance() 而非 DEFAULT_THEME——用户没选过主题时保持
    # 跟随系统行为，只有显式选择过的偏好才覆盖它。
    parser = tolerant_config_parser()
    try:
        parser.read(config_file, encoding="utf-8-sig")
    except OSError, configparser.Error:
        # 损坏/不可读的配置按「未设置」处理：主题选择永远不能阻断 GUI 启动
        return ""
    if not parser.has_section(GUI_SECTION):
        return ""
    raw = parser.get(GUI_SECTION, THEME_KEY, fallback="").strip().lower()
    return raw if raw in THEME_IDS else ""


def save_theme_preference(config_file: str | Path, theme_id: str) -> bool:
    # 持久化主题偏好。经 update_or_append_config_line：行级替换优先、缺键/缺节补建，
    # 注释与节顺序保留、原子写。False = 文件不存在等不可写情形，调用方告警但不阻断内存态切换。
    # "" 是「清空显式偏好 = 跟随系统」的哨兵：与 load_theme_preference 返回 ""（未设置）同一口径，
    # 也与 save_scale_preference 接受 ""（=自动）一致。gui 选「跟随系统」时落空值而非删键，
    # 既保留注释与节顺序，又让下次启动 load 回退到外观跟随。其余未知 id 仍按编程错误拦截。
    if theme_id not in ("", *THEME_IDS):
        raise ValueError(f"未知主题 id: {theme_id!r}（合法值: {THEME_IDS}）")
    return update_or_append_config_line(config_file, GUI_SECTION, THEME_KEY, theme_id)


# ttk 注册主题名前缀与基底主题。基底选 clam：ttk 内置主题里唯一在 Windows/Linux/macOS
# 三平台元素结构一致、且完整支持 configure/map 逐元素上色的主题；aqua/vista/xpnative
# 是平台私有引擎，theme_create 挂上去的配色大多被忽略。
_TTK_THEME_PREFIX = "dlr-"
_TTK_BASE_THEME = "clam"


@final
class ThemeManager:
    # 主题运行时状态：当前主题 id + 当前尺寸档位 + ttk 主题注册。
    # select/apply 都幂等：select 对相同 id 短路（不重复写配置、不触发下游重绘），
    # apply 对已注册的 ttk 主题名跳过 theme_create（重复创建抛 TclError）。
    #
    # 尺寸档位（ScaleProfile）与主题 id 同为 apply 的输入，ttk 主题名带上档位段
    # （"dlr-light@115"）。这一条是必需的：同一主题名下 theme_create 只能成功一次，换档位后
    # 若沿用旧名就拿不到新的 padding/rowheight，而 Tk 没有「更新已注册主题」的 API，只能换名
    # 重注册。旧主题名残留在 style.theme_names() 里是无害的（Tk 不回收，占用可忽略）。
    def __init__(self, scale: "ScaleProfile | None" = None) -> None:
        self._theme_id = DEFAULT_THEME
        self._scale = scale if scale is not None else ScaleProfile(100)

    @property
    def theme_id(self) -> str:
        return self._theme_id

    @property
    def scale(self) -> "ScaleProfile":
        # 当前尺寸档位。gui 侧改动字号/间距一律读它，不各自缓存（散落缓存必然漂移）。
        return self._scale

    def tokens(self) -> dict[str, str]:
        # 当前主题的 token 只读视图（拷贝返回，调用方改动不得反灌注册表）。
        return dict(THEMES[self._theme_id])

    def set_scale(self, scale: "ScaleProfile") -> "ScaleProfile":
        # 切换尺寸档位（内存态），返回新 profile 供调用方触发控件重排。
        # 不做幂等短路：ScaleProfile 不可变且实现了 __eq__，同值时替换等价于无操作；
        # apply() 仍需重跑（ttk 主题名带档位段，同名重注册被守卫跳过，无副作用）。
        self._scale = scale
        return self._scale

    def ttk_theme_name(self) -> str:
        # 当前应使用的 ttk 主题名。独立成方法是为了让测试能在不建窗的情况下
        # 断言「换档位 ⇒ 换名」这条幂等契约（theme_create 对同名第二次调用抛 TclError）。
        return f"{_TTK_THEME_PREFIX}{self._theme_id}@{self._scale.percent}"

    def select(self, theme_id: str) -> str:
        # 切换当前主题（内存态）。未知 id 抛 ValueError——调用链里 id 来自 THEME_IDS
        # 白名单（菜单映射 / load_theme_preference），走到这里还是未知值属编程错误，
        # 静默回退会把「显示名映射漂移」藏起来。
        if theme_id not in THEME_IDS:
            raise ValueError(f"未知主题 id: {theme_id!r}（合法值: {THEME_IDS}）")
        if theme_id == self._theme_id:
            # 幂等短路：重复选择同主题不做任何事（含持久化），下游无需自行去重
            return self._theme_id
        self._theme_id = theme_id
        return self._theme_id

    def apply(self, root: tk.Misc) -> str:
        # 把当前主题注册为 ttk 主题并启用，返回 ttk 主题名（"dlr-<id>@<scale>"）。
        # 幂等：主题名已注册则只切 theme_use；重复 apply 同一组合无害。
        style = ttk.Style(root)
        name = self.ttk_theme_name()
        if name not in style.theme_names():
            # typeshed 把 settings 收窄成 _ThemeSettingsValue TypedDict；本构造器返回结构等价的
            # 宽松形状（configure: dict[str, object] / map: list[tuple[str, str]]），cast 收敛给存根
            style.theme_create(name, _TTK_BASE_THEME, settings=cast(Any, self._build_ttk_settings()))
        style.theme_use(name)
        # ttk Combobox 的下拉弹层是独立的 tk Listbox，不吃 ttk 样式——走全局 option DB
        # 上色（重复 option_add 幂等）；列表项字体跟随系统默认，只收敛配色。
        root.option_add("*TCombobox*Listbox.background", THEMES[self._theme_id]["surface"])
        root.option_add("*TCombobox*Listbox.foreground", THEMES[self._theme_id]["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", THEMES[self._theme_id]["primary"])
        root.option_add("*TCombobox*Listbox.selectForeground", THEMES[self._theme_id]["on_primary"])
        return name

    def _build_ttk_settings(self) -> dict[str, dict[str, dict[str, object]]]:
        # 由当前主题 token 派生 ttk 元素配色。三态统一走 map：hover/active/pressed、
        # selected、disabled/readonly——ttk 的状态机制正是换掉 CTk 的机制性收益，新增控件
        # 类型时在此登记，禁止在控件创建处散落配色。padding / rowheight / 表格字体同时经
        # self._scale 派生，故换档位必须重注册主题（见类注释「主题名带档位段」）。
        t = THEMES[self._theme_id]
        s = self._scale
        # 表格字体走样式级配置：Treeview 的行文字与表头是唯一需要在样式里定字体的
        # 两类（其余控件的字体由 ui_kit.font_style 以派生样式注入）。表头比行文字
        # 重一档 bold —— 表头是分组标签，行文字是数据，视觉权重必须能分开。
        row_font = (FONT_FAMILY, s.pt("label"), "normal")
        head_font = (FONT_FAMILY, s.pt("body"), "bold")
        # 控件体量分档：主按钮常规、ghost 次级按钮紧凑、导航项最大（触控友好）。
        pad_main = s.padding(CONTROL_PADDING)
        pad_compact = s.padding(CONTROL_PADDING_COMPACT)
        pad_nav = s.padding(CONTROL_PADDING_NAV)
        pad_row = s.padding(CONTROL_PADDING_ROW)
        return {
            # "." 是 ttk 全局兜底：未单独登记的元素从这里继承底色/前景/选区/光标色
            ".": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface_alt"],
                    "darkcolor": t["border"],
                    "troughcolor": t["surface_alt"],
                    "focuscolor": t["primary"],
                    "selectbackground": t["primary"],
                    "selectforeground": t["on_primary"],
                    "insertcolor": t["text"],
                }
            },
            "TFrame": {"configure": {"background": t["surface"]}},
            # 页面背景 / 状态胶囊：surface_alt（gui 的 Colors.BG_* 同槽）
            "Alt.TFrame": {"configure": {"background": t["surface_alt"]}},
            # 圆角卡片：surface 底 + border 描边（clam 的 Frame 支持 solid relief 画边）
            "Card.TFrame": {
                "configure": {
                    "background": t["surface"],
                    "bordercolor": t["border"],
                    "relief": "solid",
                    "borderwidth": 1,
                }
            },
            # 主色底（高级设置窗口标题栏），配 OnPrimary.TLabel 反色文字
            "Primary.TFrame": {"configure": {"background": t["primary"]}},
            "TLabel": {"configure": {"background": t["surface"], "foreground": t["text"]}},
            # Alt.TLabel：落在 surface_alt 底上的正文标签（状态胶囊内）。
            "Alt.TLabel": {"configure": {"background": t["surface_alt"], "foreground": t["text"]}},
            "Muted.TLabel": {"configure": {"background": t["surface"], "foreground": t["text_muted"]}},
            # 统计值 / 状态文字的着色变体（对比度契约已含 primary/success/danger vs surface 3.0）
            "Primary.TLabel": {"configure": {"background": t["surface"], "foreground": t["primary"]}},
            "Success.TLabel": {"configure": {"background": t["surface"], "foreground": t["success"]}},
            "Danger.TLabel": {"configure": {"background": t["surface"], "foreground": t["danger"]}},
            # 主色底上的反色标签（高级设置窗口标题栏）
            "OnPrimary.TLabel": {"configure": {"background": t["primary"], "foreground": t["on_primary"]}},
            "TButton": {
                "configure": {
                    "background": t["primary"],
                    "foreground": t["on_primary"],
                    "bordercolor": t["primary"],
                    "lightcolor": t["primary"],
                    "darkcolor": t["primary"],
                    "focuscolor": t["on_primary"],
                    "padding": pad_main,
                },
                "map": {
                    # 悬停与按下共用 hover 深色：clam 的 active 状态同时覆盖鼠标悬停与键盘焦点
                    "background": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", t["primary_hover"]),
                        ("active", t["primary_hover"]),
                    ],
                    "foreground": [("disabled", t["disabled_fg"])],
                    "bordercolor": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", t["primary_hover"]),
                        ("active", t["primary_hover"]),
                    ],
                },
            },
            # Success/Danger 变体按钮：开始/停止录制、退出确认。悬停色由 _shade 从基础槽位
            # 派生（无 *_hover 槽位），白字对比度契约见 CONTRAST_REQUIREMENTS 的登记项。
            "Success.TButton": {
                "configure": {
                    "background": t["success"],
                    "foreground": t["on_primary"],
                    "bordercolor": t["success"],
                    "lightcolor": t["success"],
                    "darkcolor": t["success"],
                    "focuscolor": t["on_primary"],
                    "padding": pad_main,
                },
                "map": {
                    "background": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", _shade(t["success"], 0.18)),
                        ("active", _shade(t["success"], 0.18)),
                    ],
                    "foreground": [("disabled", t["disabled_fg"])],
                    "bordercolor": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", _shade(t["success"], 0.18)),
                        ("active", _shade(t["success"], 0.18)),
                    ],
                },
            },
            "Danger.TButton": {
                "configure": {
                    "background": t["danger"],
                    "foreground": t["on_primary"],
                    "bordercolor": t["danger"],
                    "lightcolor": t["danger"],
                    "darkcolor": t["danger"],
                    "focuscolor": t["on_primary"],
                    "padding": pad_main,
                },
                "map": {
                    "background": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", _shade(t["danger"], 0.18)),
                        ("active", _shade(t["danger"], 0.18)),
                    ],
                    "foreground": [("disabled", t["disabled_fg"])],
                    "bordercolor": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", _shade(t["danger"], 0.18)),
                        ("active", _shade(t["danger"], 0.18)),
                    ],
                },
            },
            # Ghost 变体：次级动作按钮（重新读取 / 打开下载目录 / 取消 / 清空日志等），
            # 悬停浮到 surface_alt，体量比主按钮小一档。
            "Ghost.TButton": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface"],
                    "darkcolor": t["surface"],
                    "focuscolor": t["primary"],
                    "padding": pad_compact,
                },
                "map": {
                    "background": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", t["surface_alt"]),
                        ("active", t["surface_alt"]),
                    ],
                    "foreground": [("disabled", t["disabled_fg"])],
                    "bordercolor": [("active", t["primary"]), ("disabled", t["disabled_bg"])],
                },
            },
            # 侧边栏导航：未选中 muted 文字、悬停浮 surface_alt；选中态（NavActive）
            # 用 surface_alt 底 + primary 文字。
            # anchor="w"：导航与侧栏动作按钮一律左对齐。
            "Nav.TButton": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text_muted"],
                    "bordercolor": t["surface"],
                    "lightcolor": t["surface"],
                    "darkcolor": t["surface"],
                    "anchor": "w",
                    "focuscolor": t["text_muted"],
                    "padding": pad_nav,
                },
                "map": {
                    "background": [("pressed", t["surface_alt"]), ("active", t["surface_alt"])],
                    "foreground": [("disabled", t["disabled_fg"])],
                },
            },
            "NavActive.TButton": {
                "configure": {
                    "background": t["surface_alt"],
                    "foreground": t["primary"],
                    "bordercolor": t["surface_alt"],
                    "lightcolor": t["surface_alt"],
                    "darkcolor": t["surface_alt"],
                    "anchor": "w",
                    "focuscolor": t["primary"],
                    "padding": pad_nav,
                },
                "map": {
                    "background": [("pressed", t["surface_alt"]), ("active", t["surface_alt"])],
                    "foreground": [("disabled", t["disabled_fg"])],
                },
            },
            "SideGhost.TButton": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface"],
                    "darkcolor": t["surface"],
                    "anchor": "w",
                    "focuscolor": t["text"],
                    "padding": pad_nav,
                },
                "map": {
                    "background": [("pressed", t["surface_alt"]), ("active", t["surface_alt"])],
                    "foreground": [("disabled", t["disabled_fg"])],
                    "bordercolor": [("active", t["primary"])],
                },
            },
            "SideDanger.TButton": {
                "configure": {
                    "background": t["danger"],
                    "foreground": t["on_primary"],
                    "bordercolor": t["danger"],
                    "lightcolor": t["danger"],
                    "darkcolor": t["danger"],
                    "anchor": "w",
                    "focuscolor": t["on_primary"],
                    "padding": pad_nav,
                },
                "map": {
                    "background": [
                        ("disabled", t["disabled_bg"]),
                        ("pressed", _shade(t["danger"], 0.18)),
                        ("active", _shade(t["danger"], 0.18)),
                    ],
                    "foreground": [("disabled", t["disabled_fg"])],
                },
            },
            # 输入类控件原先无 padding（文字贴边），故补 pad_row 与行内浮层同档
            "TEntry": {
                "configure": {
                    "fieldbackground": t["surface_alt"],
                    "foreground": t["text"],
                    "insertcolor": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface_alt"],
                    "darkcolor": t["surface_alt"],
                    "padding": pad_row,
                },
                "map": {
                    "fieldbackground": [("disabled", t["disabled_bg"])],
                    "foreground": [("disabled", t["disabled_fg"])],
                    # 聚焦边框升为主色：非文本 3:1 已达标（primary vs surface_alt），
                    # 键盘焦点位置因此可辨（WCAG 2.4.7）
                    "bordercolor": [("focus", t["primary"]), ("disabled", t["disabled_bg"])],
                    "lightcolor": [("focus", t["primary"])],
                    "darkcolor": [("focus", t["primary"])],
                },
            },
            "TCombobox": {
                "configure": {
                    "fieldbackground": t["surface_alt"],
                    "background": t["surface_alt"],
                    "foreground": t["text"],
                    "arrowcolor": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface_alt"],
                    "darkcolor": t["surface_alt"],
                    "padding": pad_row,
                },
                "map": {
                    "fieldbackground": [("readonly", t["disabled_bg"]), ("disabled", t["disabled_bg"])],
                    "foreground": [("readonly", t["disabled_fg"]), ("disabled", t["disabled_fg"])],
                    "bordercolor": [("focus", t["primary"]), ("disabled", t["disabled_bg"])],
                },
            },
            "TNotebook": {"configure": {"background": t["surface_alt"], "bordercolor": t["border"]}},
            "TNotebook.Tab": {
                "configure": {
                    "background": t["surface_alt"],
                    "foreground": t["text_muted"],
                    "padding": (s.px(12), s.px(6)),
                },
                "map": {
                    "background": [("selected", t["surface"])],
                    "foreground": [("selected", t["text"]), ("active", t["text"])],
                },
            },
            "Treeview": {
                "configure": {
                    "background": t["surface_alt"],
                    "fieldbackground": t["surface_alt"],
                    "foreground": t["text"],
                    "bordercolor": t["border"],
                    # 行高与旧 34px 行卡的信息密度对齐（默认 ~20px 过挤）；改由 scale 派生并带下限
                    # ——行高不同步放大会让大字号文字上下缘贴边（85% 档尤其明显）
                    "rowheight": s.row_height(),
                    "font": row_font,
                },
                "map": {
                    # 行选中走 primary 填充 + on_primary 文字（对比度契约已覆盖该对）
                    "background": [("selected", t["primary"])],
                    "foreground": [("selected", t["on_primary"])],
                },
            },
            "Treeview.Heading": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text_muted"],
                    "padding": (s.px(6), s.px(5)),
                    "font": head_font,
                },
                "map": {"foreground": [("active", t["text"])], "background": [("active", t["surface"])]},
            },
            "Vertical.TScrollbar": {
                "configure": {
                    "background": t["surface_alt"],
                    "troughcolor": t["surface_alt"],
                    "bordercolor": t["border"],
                    "arrowcolor": t["text_muted"],
                },
                "map": {"background": [("active", t["border"])], "arrowcolor": [("active", t["text"])]},
            },
            "Horizontal.TScrollbar": {
                "configure": {
                    "background": t["surface_alt"],
                    "troughcolor": t["surface_alt"],
                    "bordercolor": t["border"],
                    "arrowcolor": t["text_muted"],
                },
                "map": {"background": [("active", t["border"])], "arrowcolor": [("active", t["text"])]},
            },
            "TCheckbutton": {
                "configure": {"background": t["surface"], "foreground": t["text"]},
                "map": {"foreground": [("disabled", t["disabled_fg"])]},
            },
            "TRadiobutton": {
                "configure": {"background": t["surface"], "foreground": t["text"]},
                "map": {"foreground": [("disabled", t["disabled_fg"])]},
            },
            "TProgressbar": {
                "configure": {
                    "background": t["primary"],
                    "troughcolor": t["surface_alt"],
                    "bordercolor": t["border"],
                    "lightcolor": t["primary"],
                    "darkcolor": t["primary"],
                }
            },
            "TSeparator": {"configure": {"background": t["border"]}},
            "TScale": {
                "configure": {"background": t["surface"], "troughcolor": t["surface_alt"], "bordercolor": t["border"]}
            },
        }
