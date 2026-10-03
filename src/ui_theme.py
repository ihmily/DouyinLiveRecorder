# src/ui_theme.py
# GUI 主题层（阶段3：UI 现代化）：语义 token + 多主题 + ttk 主题注册 + 偏好持久化 + WCAG 对比度自证。
#
# 设计约束（提案 PROPOSAL_2026-09-29_ui-modernization §5.2）：
#   · 全部颜色经由语义槽位引用，任何主题不得绕过槽位直写控件颜色——多套主题由同一组
#     槽位派生，避免「每套主题各写一遍颜色」的漂移；对比度因此可以机检（见 CONTRAST_REQUIREMENTS）。
#   · 槽位清单 = 提案 §5.2 十二槽 + on_primary：深色/高对比主题下主按钮填充是亮蓝，按钮标签
#     需要近黑前景，`surface`（面板底色）在深色主题里兼作按钮前景的语义不成立，故单列一槽。
#     浅色主题 on_primary == surface（#FFFFFF），该槽在浅色下是中性的。
#   · 品牌色沿用现有 Colors 的品牌蓝色相：light 的 primary 取 #4358E8（同色相加深）——
#     原 #4F6DF5 与白色标签对比度实测 4.34:1，低于正文 AA 4.5:1；同 hue 加深后 5.53:1。
#   · 本模块不创建窗口、不依赖显示器：import 期只定义数据与纯函数，Tk 相关工作全部发生在
#     ThemeManager.apply(root) 调用期（无头 Linux CI 可安全 import，`import gui` 链路不受影响）。
#   · 持久化走 config.ini [GUI] gui_theme（键名无 configparser 分隔符 `=` / `:`），
#     写入经 src/web_config.update_or_append_config_line（缺节/缺键补建 + 行级注释保留 + 原子写），
#     刻意不使用 config_io.read_config_value——它写回时持 main.file_update_lock，与录制进程耦合，
#     GUI 进程不该把 [GUI] 键的补写混进录制引擎的锁体系。
from __future__ import annotations

import configparser
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, cast, final

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

# 三套主题的 token 取值。全部取值经 CONTRAST_REQUIREMENTS 机检达标
# （2026-09-29 迭代定稿，迭代脚本已删；tests/test_ui_theme.py 持续回归）。
THEMES: dict[str, dict[str, str]] = {
    "light": {
        "surface": "#FFFFFF",
        "surface_alt": "#F4F6FB",
        "border": "#848DA0",
        "on_primary": "#FFFFFF",
        "text": "#1E293B",
        "text_muted": "#5D6C84",
        "primary": "#4358E8",
        "primary_hover": "#3247C9",
        "success": "#15803D",
        "danger": "#DC2626",
        "warning": "#C2690A",
        "disabled_bg": "#E2E6EE",
        "disabled_fg": "#6E7686",
    },
    "dark": {
        "surface": "#171A23",
        "surface_alt": "#0F1117",
        "border": "#626C84",
        "on_primary": "#FFFFFF",
        "text": "#E2E8F0",
        "text_muted": "#8B93A7",
        "primary": "#4463F0",
        "primary_hover": "#5068F2",
        "success": "#15803D",
        "danger": "#DC2626",
        "warning": "#D97706",
        "disabled_bg": "#262B3A",
        "disabled_fg": "#7E8798",
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
#   4.5 = WCAG 1.4.3 正文 AA（按钮标签、正文、次级文字均按正文计——13px 未达 WCAG「大字」门槛）；
#   3.0 = WCAG 1.4.11 非文本（边框、状态色块、焦点环）+ 禁用态自加压（WCAG 豁免禁用控件，
#         这里仍取 3.0 自证，避免「禁用即随便灰」漂移）。
# 新增槽位/组合时先在此登记，再取色——机检是取色的前置门，不是事后核对。
# 阶段4 新增三对：primary/surface_alt（导航选中态 fg/bg）、on_primary/success、
# on_primary/danger（Success/Danger.TButton 的标签）。三者一律按正文 4.5 登记：
# 为此 light/dark 的 success 从 #16A34A 加深到 #15803D（白字 3.30→5.01，同阶段3 把
# primary 加深的先例；high_contrast 的 success=#4ADE80 配黑字 12.05、danger 两态
# 白字 4.83 / 黑字 7.57 均天然达标），gui.Colors.SUCCESS 同批同步取值。
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
    # [阶段5] CTk 外观模式（set/get_appearance_mode）随 customtkinter 依赖一并退役，
    # 「跟随系统」的探测依据由本函数承担：Windows 读注册表 AppsUseLightTheme（0=深色），
    # macOS 走 `defaults read -g AppleInterfaceStyle`（键缺失/命令失败 = 浅色），
    # 其余平台无统一口径按浅色兜底。任何探测失败一律回 "light"——探测只是
    # 「跟随系统」的默认值来源，绝不能让 GUI 起不来（无头 CI 也不会走到：仅 GUI 运行期调用）。
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


def _shade(color: str, ratio: float) -> str:
    # 把 #RRGGBB 向黑色方向压暗 ratio（0..1），返回同形态十六进制。
    # ttk 变体按钮（Success/Danger.TButton）的悬停色由此从基础槽位派生——
    # success/danger 没有配对的 *_hover 槽位，手写第二套色值必漂移。
    raw = color.lstrip("#")
    r, g, b = int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    return f"#{round(r * (1 - ratio)):02X}{round(g * (1 - ratio)):02X}{round(b * (1 - ratio)):02X}"


def load_theme_preference(config_file: str | Path) -> str:
    # 读取 [GUI] gui_theme。返回 "" 表示「未设置」（节/键缺失、值为空、值不在 THEME_IDS），
    # 调用方应回退到外观跟随（CTk appearance mode）而非 DEFAULT_THEME——用户没选过主题时
    # 保持升级前的跟随系统行为，只有显式选择过的偏好才覆盖它。
    parser = configparser.ConfigParser(interpolation=None)
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
    if theme_id not in THEME_IDS:
        raise ValueError(f"未知主题 id: {theme_id!r}（合法值: {THEME_IDS}）")
    return update_or_append_config_line(config_file, GUI_SECTION, THEME_KEY, theme_id)


# ttk 注册主题名前缀与基底主题。基底选 clam：ttk 内置主题里唯一在 Windows/Linux/macOS
# 三平台元素结构一致、且完整支持 configure/map 逐元素上色的主题；aqua/vista/xpnative
# 是平台私有引擎，theme_create 挂上去的配色大多被忽略。
_TTK_THEME_PREFIX = "dlr-"
_TTK_BASE_THEME = "clam"


@final
class ThemeManager:
    # 主题运行时状态：当前主题 id + ttk 主题注册。
    # select/apply 都幂等：select 对相同 id 短路（不重复写配置、不触发下游重绘），
    # apply 对已注册的 ttk 主题名跳过 theme_create（重复创建抛 TclError）。
    def __init__(self) -> None:
        self._theme_id = DEFAULT_THEME

    @property
    def theme_id(self) -> str:
        return self._theme_id

    def tokens(self) -> dict[str, str]:
        # 当前主题的 token 只读视图（拷贝返回，调用方改动不得反灌注册表）。
        return dict(THEMES[self._theme_id])

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
        # 把当前主题注册为 ttk 主题并启用，返回 ttk 主题名（"dlr-<id>"）。
        # 幂等：主题名已注册则只切 theme_use；重复 apply 同一主题无害。
        style = ttk.Style(root)
        name = _TTK_THEME_PREFIX + self._theme_id
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
        # selected、disabled/readonly——CTk 没有的状态机制正是本次换 ttk 的机制性收益，
        # 新增控件类型时在此登记，禁止在控件创建处散落配色。
        t = THEMES[self._theme_id]
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
                    "padding": (10, 5),
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
            # 派生（无 *_hover 槽位），白字对比度契约见 CONTRAST_REQUIREMENTS 的阶段4 注。
            "Success.TButton": {
                "configure": {
                    "background": t["success"],
                    "foreground": t["on_primary"],
                    "bordercolor": t["success"],
                    "lightcolor": t["success"],
                    "darkcolor": t["success"],
                    "focuscolor": t["on_primary"],
                    "padding": (10, 5),
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
                    "padding": (10, 5),
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
            # Ghost 变体：原「fg_color=transparent + border_width=1」的次级按钮
            # （重新读取 / 打开下载目录 / 取消 / 清空日志等），悬停浮到 surface_alt。
            "Ghost.TButton": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface"],
                    "darkcolor": t["surface"],
                    "focuscolor": t["primary"],
                    "padding": (10, 5),
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
            # 用 surface_alt 底 + primary 文字（阶段4 起导航选中不再走 CTk 颜色回写）。
            # anchor="w" 与 CTkButton(anchor=tk.W) 对齐：导航与侧栏动作按钮一律左对齐。
            "Nav.TButton": {
                "configure": {
                    "background": t["surface"],
                    "foreground": t["text_muted"],
                    "bordercolor": t["surface"],
                    "lightcolor": t["surface"],
                    "darkcolor": t["surface"],
                    "anchor": "w",
                    "focuscolor": t["text_muted"],
                    "padding": (12, 9),
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
                    "padding": (12, 9),
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
                    "padding": (12, 8),
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
                    "padding": (12, 8),
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
            "TEntry": {
                "configure": {
                    "fieldbackground": t["surface_alt"],
                    "foreground": t["text"],
                    "insertcolor": t["text"],
                    "bordercolor": t["border"],
                    "lightcolor": t["surface_alt"],
                    "darkcolor": t["surface_alt"],
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
                },
                "map": {
                    "fieldbackground": [("readonly", t["disabled_bg"]), ("disabled", t["disabled_bg"])],
                    "foreground": [("readonly", t["disabled_fg"]), ("disabled", t["disabled_fg"])],
                    "bordercolor": [("focus", t["primary"]), ("disabled", t["disabled_bg"])],
                },
            },
            "TNotebook": {"configure": {"background": t["surface_alt"], "bordercolor": t["border"]}},
            "TNotebook.Tab": {
                "configure": {"background": t["surface_alt"], "foreground": t["text_muted"], "padding": (12, 6)},
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
                    # 行高与旧 34px 行卡的信息密度对齐（默认 ~20px 过挤）
                    "rowheight": 32,
                },
                "map": {
                    # 行选中走 primary 填充 + on_primary 文字（对比度契约已覆盖该对）
                    "background": [("selected", t["primary"])],
                    "foreground": [("selected", t["on_primary"])],
                },
            },
            "Treeview.Heading": {
                "configure": {"background": t["surface"], "foreground": t["text_muted"], "padding": (6, 5)},
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
