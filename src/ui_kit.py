# src/ui_kit.py
# GUI 控件层：tkinter.ttk 控件工厂 + Treeview 增量更新表格。
#
# 设计约束（与 ui_theme / ui_scale 同一条铁律）：
#   · **颜色一律不进工厂**：全部配色由 src/ui_theme.ThemeManager 注册的 ttk 变体样式
#     （Card.TFrame / Alt.TFrame / Success.TButton / Muted.TLabel / NavActive.TButton …）
#     从语义槽位派生，主题切换时由 ttk 全局样式统一重绘——任何控件不得绕过槽位直写颜色。
#     调用方以 variant 字符串选择样式。
#   · 终端配色是唯一例外：gui.Colors.TERMINAL_* 是刻意的主题无关常量（两种主题下均保持
#     深色终端风格），由 terminal_text() 以 tk 控件落地、调用方传色，不进槽位体系。
#   · 工厂签名对齐旧 CTk 惯用形态（text/command/font/values/set/get/configure(values=)），
#     但**不收 fg_color/hover_color 等颜色参数**；Menu.set()「只改显示值、不触发 command」的
#     语义由 readonly Combobox 的 <<ComboboxSelected>> 绑定保留（表格重建回设画质不会误写配置）。
#   · 监控表格用 DataTable 包 ttk.Treeview：按 key 差异化 insert()/delete()/item()/move()
#     的行级增量更新，取代旧实现「每轮 destroy + 重建」的整表闪烁与点击落空；每行「切换
#     画质」下拉用单元格 bbox 浮层 Combobox 实现（Treeview 本身不支持内嵌控件）。
#   · 只依赖 tkinter/ttk，零 customtkinter 引用；import 期零 Tk 对象（只有类定义与纯函数），
#     无头 Linux CI 可安全 import，`import gui` 链路不受影响。
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import Any, Final, Literal, cast, final

from src import ui_i18n
from src.ui_theme import is_valid_hex

# ─── 变体样式名（由 src/ui_theme.ThemeManager._build_ttk_settings 按当前主题 token 注册） ──

FRAME_STYLES: Final[dict[str | None, str]] = {
    # None = 卡片内/侧边栏的「透明」CTkFrame 惯例：默认样式底色 == surface，与父容器同色
    None: "TFrame",
    # 页面背景 / 状态胶囊（surface_alt）
    "alt": "Alt.TFrame",
    # 圆角卡片（surface 底 + border 边框，clam 的 solid relief）
    "card": "Card.TFrame",
    # 主色底（高级设置窗口标题栏）
    "primary": "Primary.TFrame",
}

LABEL_STYLES: Final[dict[str | None, str]] = {
    None: "TLabel",
    "muted": "Muted.TLabel",
    "primary": "Primary.TLabel",
    "success": "Success.TLabel",
    "danger": "Danger.TLabel",
    "on_primary": "OnPrimary.TLabel",
    "alt": "Alt.TLabel",
}

BUTTON_STYLES: Final[dict[str | None, str]] = {
    None: "TButton",
    "success": "Success.TButton",
    "danger": "Danger.TButton",
    "ghost": "Ghost.TButton",
    "nav": "Nav.TButton",
    "nav_active": "NavActive.TButton",
    "side_ghost": "SideGhost.TButton",
    "side_danger": "SideDanger.TButton",
}

# 侧边栏导航按钮的两种样式名（_show_page 切换选中态时按名 configure；带字体的按钮
# 经 font_style() 取派生名，切换时同样走它，避免落到无字体的基础变体上）。
NAV_STYLE: Final[str] = "Nav.TButton"
NAV_ACTIVE_STYLE: Final[str] = "NavActive.TButton"

# font_style() 的派生样式缓存：键 (基础变体样式名, 字体键, 尺寸档位)。
# 键里必须带档位段：换缩放后同名 Font 对象的 actual('size') 会变，但派生样式名若只按
# (base, 字体三元组) 缓存，就会在新档位下命中按旧 padding 配置出来的样式——表现为
# 「字号变大了但按钮内边距还是老样子」。档位由 set_scale_percent() 登记。
_FONT_STYLE_CACHE: dict[tuple[str, str, int], str] = {}

# 当前尺寸档位（百分比）。模块级单值而非参数传递：见 set_scale_percent 的注释。
_SCALE_PERCENT: int = 100


@final
class Frame(ttk.Frame):
    # CTkFrame 替身。variant 决定底色/边框（见 FRAME_STYLES）；CTk 的「transparent」
    # 由「默认样式底色 == 父容器底色」达成，主题切换随全局样式重绘。
    def __init__(self, master: tk.Misc, *, variant: str | None = None, **kwargs: Any) -> None:
        super().__init__(master, style=FRAME_STYLES[variant], **kwargs)


@final
class Label(ttk.Label):
    # CTkLabel 替身。variant 见 LABEL_STYLES；font/anchor/justify/wraplength 直传
    # （ttk.Label 的 -font 是控件级选项；wraplength 为设备像素，见 _bind_adaptive_wraplength）。
    # text 传 Translatable（ui_i18n.T）时：建时查表翻译 + 登记重译（语言热切换后由
    # retranslate_all 回填）；传普通 str 则原样透传（动态拼接文本不参与重译）。
    def __init__(self, master: tk.Misc, *, variant: str | None = None, **kwargs: Any) -> None:
        text = kwargs.get("text")
        if isinstance(text, ui_i18n.Translatable):
            ui_i18n.register(self, "text", text)
            kwargs["text"] = text.render()
        super().__init__(master, style=LABEL_STYLES[variant], **kwargs)


@final
class Button(ttk.Button):
    # CTkButton 替身。variant 见 BUTTON_STYLES；旧 CTk 的 fg_color/hover_color/text_color/
    # border_* 全部并入样式（主题切换自动跟随）。ttk 无像素级 height/width（前者由 padding
    # 撑起、后者按文本宽度自适应），调用方以 padding 控制体量。
    #
    # 字体经 font_style() 派生样式注入：ttk.Button 没有控件级 -font（Tk 9.0 实测
    # TclError: unknown option "-font"，ttk.Label/Combobox 则原生支持），按
    # 「变体样式 + 字体」缓存派生一枚样式名，静态配置与状态映射从基础变体显式复制。
    # text 传 Translatable（ui_i18n.T）时：建时查表翻译 + 登记重译（同 Label 的约定）。
    def __init__(self, master: tk.Misc, *, variant: str | None = None, **kwargs: Any) -> None:
        text = kwargs.get("text")
        if isinstance(text, ui_i18n.Translatable):
            ui_i18n.register(self, "text", text)
            kwargs["text"] = text.render()
        font = kwargs.pop("font", None)
        base_style = BUTTON_STYLES[variant]
        if font is None:
            super().__init__(master, style=base_style, **kwargs)
        else:
            super().__init__(master, style=font_style(base_style, font, master), **kwargs)
            # 记下基础变体名与字体对象：换缩放后派生样式要按**新**主题的 padding
            # 重新派生（见 restyle_fonts）。不记就只能靠样式名反解，而样式名带序号
            # 不可靠；字体也不能事后从控件读——ttk.Button 没有控件级 -font
            # （这正是本类需要派生样式的原因），读它必然 TclError。
            self._dlr_base_style = base_style
            self._dlr_font = font


def font_style(base: str, font: Any, widget: tk.Misc) -> str:
    # 返回「基础变体样式 + 字体 + 尺寸档位」的派生样式名（同字体同变体同档位共用）。
    # 派生名显式复制基础变体的静态配置与状态映射——不依赖 ttk 的点分回退语义
    # （实测 Tk 9.0 上 style.configure/map 跨段回退不可靠：布局可回落、选项未必）。
    # 键含档位：换缩放后基础变体的 padding 已变，沿用旧派生样式会让内边距与字号脱节。
    key = (base, _font_key(font), current_scale_percent())
    name = _FONT_STYLE_CACHE.get(key)
    if name is not None:
        return name
    name = f"DLRF{len(_FONT_STYLE_CACHE)}.{base}"
    style = ttk.Style(widget)
    base_config = style.configure(base) or {}
    style.configure(name, **cast("dict[str, Any]", base_config), font=font)
    base_map = style.map(base)
    if base_map:
        style.map(name, **cast("dict[str, Any]", base_map))
    _FONT_STYLE_CACHE[key] = name
    return name


def clear_font_style_cache() -> None:
    # 清空派生样式缓存。gui 在换缩放档位时调用：已存在的派生样式名是按旧档位生成的，
    # 继续复用会让新档位的按钮内边距停留在旧值。
    # 不删 ttk 侧旧样式：Tk 没有 theme/style 的删除 API，残留样式只占内存、不会被
    # theme_use 选中；强行用「唯一名递增」绕开只会让样式表无限增长。
    _FONT_STYLE_CACHE.clear()


def set_scale_percent(percent: int) -> None:
    # 登记当前尺寸档位（gui 在换缩放时调用）。font_style() 用它拼缓存键。
    # 独立成函数而不是让 font_style 接受参数：调用点有 30+ 处（每个 Button/Label 工厂），
    # 逐个传参会把「档位」这件事散到每个控件创建处，正是本仓要避免的散落状态。
    global _SCALE_PERCENT
    _SCALE_PERCENT = percent
    clear_font_style_cache()


def current_scale_percent() -> int:
    # 当前尺寸档位（未登记时为 100，即基准档）。
    return _SCALE_PERCENT


def restyle_fonts(root: tk.Misc) -> int:
    # 换缩放/换主题后，把所有「带字体的按钮」重新指向按**当前** ttk 主题派生的样式。
    # 返回重设的控件数（供测试断言，不为 0 即表示确实走到了这些控件）。
    #
    # 为什么必须逐控件重指：font_style 的派生样式在创建时**拷贝**了基础变体的 configure
    # （含 padding），换档后基础变体变了而按钮仍指着旧派生样式名，表现为「字号变大了、
    # 按钮内边距还是老样子」（85% 档尤其明显）。Tk 不会自动刷新引用者。
    # 遍历范围从 root 递归找 Button 实例；换档不重建控件树，不处理「中途被销毁」（TclError 兜住）。
    count = 0
    stack: list[tk.Misc] = [root]
    while stack:
        # cast 到 tk.Widget：typeshed 把 tk.Misc 上的 configure 收窄成不收 style的
        # 宽签名（Misc 是 tkinter 的共同基类，不承诺任何具体控件选项），而实际遍历
        # 到的都是 ttk.Button 实例。此处 cast 是「按调用方契约断言」，不是掩盖真错误。
        widget = cast(tk.Widget, stack.pop())
        base = getattr(widget, "_dlr_base_style", None)
        font = getattr(widget, "_dlr_font", None)
        if base is not None and font is not None:
            try:
                widget.configure(**{"style": font_style(base, font, widget)})
                count += 1
            except tk.TclError:
                # 控件已销毁（遍历途中被关掉）：跳过，不中断整棵树
                continue
        try:
            stack.extend(widget.winfo_children())
        except tk.TclError:
            continue
    return count


def _font_key(font: Any) -> str:
    # 字体的缓存键：tk.font.Font 取实际三元组，元组字体逐项拼接。
    if isinstance(font, tuple):
        return "|".join(str(part) for part in font)
    try:
        return f"{font.actual('family')}|{font.actual('size')}|{font.actual('weight')}"
    except Exception:
        return str(font)


@final
class Menu(ttk.Combobox):
    # CTkOptionMenu 替身：readonly Combobox（不可键入，仅下拉选择）。
    # 命令经 <<ComboboxSelected>> 绑定并回传**选中值**（对齐 CTkOptionMenu 的 command 签名）；
    # 继承的 .set() 只改显示值、不触发该虚拟事件——与旧 CTkOptionMenu.set() 语义一致。
    def __init__(
        self,
        master: tk.Misc,
        *,
        values: Sequence[str] | None = None,
        command: Callable[[str], None] | None = None,
        font: Any = None,
        width: int | None = None,
        **kwargs: Any,
    ) -> None:
        # CTk 的 height（控件像素高）在 ttk 无对应选项（体量由样式 padding 决定），
        # 刻意不透传；Combobox 自带的 -height 是「下拉列表行数」，语义不同，避免误用。
        kwargs.pop("height", None)
        init_kwargs: dict[str, Any] = {"values": list(values or []), "state": "readonly", **kwargs}
        if font is not None:
            init_kwargs["font"] = font
        if width is not None:
            init_kwargs["width"] = width
        super().__init__(master, **init_kwargs)
        if command is not None:
            self.bind("<<ComboboxSelected>>", lambda _event: command(self.get()))


@final
class EditorText(tk.Text):
    # CTkTextbox 替身（URL 配置编辑器 / 高级设置编辑器）：tk.Text + token 配色。
    # 既有调用面（get/insert/delete 与 "1.0"/tk.END 坐标）与 CTkTextbox 逐字兼容；
    # 主题切换时由 gui 经 restyle() 重上色（tk.Text 不参与 ttk 样式体系）。
    def __init__(
        self,
        master: tk.Misc,
        *,
        tokens: dict[str, str],
        font: Any,
        wrap: Literal["none", "char", "word"] = "none",
        pad_x: int = 10,
        pad_y: int = 8,
    ) -> None:
        # [阶段6] padx/pady 由调用方按缩放档位传入：tk.Text 的内边距是裸像素、不吃 ttk
        # 样式，写死会在大字号下把文字挤到边框上。
        super().__init__(
            master,
            # width=1：tk.Text 默认宽 80 字符，等宽字号下请求宽 ~720+ 逻辑像素，会把整窗
            # reqwidth 撑过 geometry——Tk grid 对超宽 slave 是裁切而非收缩，卡片右边框与
            # 右边距因此整段被切。实际宽度由调用方 pack(fill=BOTH, expand=True) 分配。
            width=1,
            wrap=wrap,
            font=font,
            bg=tokens["surface_alt"],
            fg=tokens["text"],
            insertbackground=tokens["text"],
            selectbackground=tokens["primary"],
            selectforeground=tokens["on_primary"],
            relief=tk.FLAT,
            bd=0,
            padx=pad_x,
            pady=pad_y,
            highlightthickness=1,
            highlightbackground=tokens["border"],
            highlightcolor=tokens["primary"],
            undo=True,
            # spacing1/spacing3：中文没有西文那样的降部空间，行距全交给字体默认 leading 时，
            # 纯中文日志/URL 行会挤成一片。上下各留 2px 余量；用像素而不用行倍数，是为了让
            # 85% 与 150% 档下的物理观感一致（倍数会随字号放大过头）。
            spacing1=2,
            spacing3=2,
        )

    # 主题切换后重上色（槽位取值随主题变化，tk.Text 必须显式跟随）。
    def restyle(self, tokens: dict[str, str]) -> None:
        self.configure(
            bg=tokens["surface_alt"],
            fg=tokens["text"],
            insertbackground=tokens["text"],
            selectbackground=tokens["primary"],
            selectforeground=tokens["on_primary"],
            highlightbackground=tokens["border"],
            highlightcolor=tokens["primary"],
        )


# ─── 过渡动效（Tk 能力边界内的实现） ─────────────────────────────────────
#
# Tk 没有 alpha 通道、没有圆角、没有阴影。本节只做 Tk 真正支持的两件事：
#   · 位移（place/geometry 插值）→ 页面滑入、弹窗缩放落位；
#   · 颜色插值（tag/Canvas 逐帧混色）→ 列表变化行高亮衰减。
# 不做「假装能淡入」：ttk 控件无 alpha，硬做只能靠截图覆盖，既慢又脏。
# 帧驱动一律经 src/ui_motion.MotionController.run_frames，off 档下这些函数直接落终态、不排 after。


def blend(color_a: str, color_b: str, ratio: float) -> str:
    # 两个 #RRGGBB 按 ratio 线性混色（ratio=0 取 a，=1 取 b，恰好返回 b）。
    # 与 gui._mix 同公式，单独保留是因为 ui_kit 不 import gui（反向依赖会成环），
    # 且这里的调用方在离屏测试里只需要纯函数。
    # M-83（2026-10-21）：入参必须先验形状再混色。旧实现两样都不校验——ratio 越界时
    # round(负权重通道) 拼出 "-1BEEF0" 一类畸形串，非法颜色喂给 tag_configure 是
    # **静默失败**（高亮衰减整段不可见且不留日志）；#RGB、命名色、带 alpha 的 8 位形态
    # 则让 int(x, 16) 当场抛 ValueError 打断调用方的每帧回调。颜色形状判定复用
    # src/ui_theme.is_valid_hex（本仓唯一的 #RRGGBB 口径，不在这里另立第二份正则），
    # ratio 一律钳回 [0,1]（终点语义不变，越界只可能是调用方算术错误，钳位是最小惊扰）。
    if not (is_valid_hex(color_a) and is_valid_hex(color_b)):
        # 任一侧非法就没有「正确混色结果」可言：回合法的那侧；两例都不合法时回中性黑，
        # 保证出口恒为 tag_configure 可用的 7 位串，坏输入不再沿调用链扩散。
        if is_valid_hex(color_a):
            return color_a
        if is_valid_hex(color_b):
            return color_b
        return "#000000"
    clamped = max(0.0, min(1.0, ratio))

    def _channel(offset: int) -> int:
        return round(
            int(color_a[offset : offset + 2], 16) * (1 - clamped) + int(color_b[offset : offset + 2], 16) * clamped
        )

    return f"#{_channel(1):02X}{_channel(3):02X}{_channel(5):02X}"


def slide_in(
    widget: tk.Misc,
    motion: Any,
    *,
    distance: int,
    duration_ms: int,
    job_key: str,
) -> None:
    # 页面滑入：先按 distance 偏移 place 到一侧，再逐帧插值回 0。
    #
    # 为什么用 place：grid/pack 的位置由布局器决定、不可逐步改，place 允许直接写 x。
    # 为什么终帧必须还原原布局信息而不是 place_forget：place_forget 把控件从**所有**几何
    # 管理器里摘掉——原本 grid 排的页面会直接消失（tkraise 只提层级、不给位置）。故过渡前
    # 抓一份原布局器信息、终帧原样写回；两者都没有（place 管理的控件）则保持 place 终态。
    saved = _capture_geometry(widget)

    def _settle() -> None:
        _restore_geometry(widget, saved)

    def _offset(progress: float) -> None:
        shift = round(distance * (1 - progress))
        try:
            # cast 到 tk.Widget：place/grid_info 等几何管理器方法在 typeshed 里
            # 挂在 Widget 上而 tk.Misc 不承诺（Misc 是 tkinter 的共同基类）。
            # 此处 cast 是「按调用方契约断言传入的是真实控件」，非掩盖真错误。
            cast(tk.Widget, widget).place(relx=0.0, rely=0.0, relwidth=1.0, relheight=1.0, x=shift)
        except tk.TclError:
            pass

    motion.run_frames(
        widget,
        job_key,
        _offset,
        duration_ms=duration_ms,
        frames=10,
        on_done=_settle,
    )


# 几何管理器信息的类型别名：grid_info/pack_info 都返回 dict[str, Any]。
_GeometryInfo = dict[str, Any]


def _capture_geometry(widget: tk.Misc) -> tuple[str, _GeometryInfo]:
    # 抓当前生效的几何管理器及其配置。返回 ("none", {}) 表示控件不由任何布局器管理
    # （调用方自己 place 的场景），此时 _restore_geometry 什么都不做。
    # 为什么要 cast 成宽 dict：grid_info/pack_info 的存根是「全部键必填」的 TypedDict，
    # 而 Tk 实际只返回用过的键；后续 grid_configure(**info) 读的也正是这些键。
    try:
        grid = cast("dict[str, Any]", cast(tk.Widget, widget).grid_info())
    except tk.TclError:
        grid = {}
    if grid:
        return ("grid", grid)
    try:
        packed = cast("dict[str, Any]", cast(tk.Widget, widget).pack_info())
    except tk.TclError:
        packed = {}
    if packed:
        return ("pack", packed)
    return ("none", {})


def _restore_geometry(widget: tk.Misc, saved: tuple[str, _GeometryInfo]) -> None:
    # 还原过渡前的布局配置。先 place_forget 摘掉过渡期借用的 place，再按原布局器
    # 写回——顺序不能反：grid_configure 在 place 生效时会被 place 压住。
    manager, info = saved
    if manager == "none":
        return
    try:
        target = cast(tk.Widget, widget)
        target.place_forget()
        if manager == "grid":
            target.grid_configure(**info)
        else:
            target.pack_configure(**info)
    except tk.TclError:
        # 控件已销毁（窗口关闭时 after 回调迟到）：无需还原，也不该抛
        pass


def scale_in_window(
    window: tk.Toplevel,
    motion: Any,
    *,
    start_scale: float,
    duration_ms: int,
    job_key: str,
) -> None:
    # 弹窗落位：从 start_scale 放大到 1.0（围绕窗口中心）。
    # 不做 alpha 淡入：Toplevel 的 -alpha 只在部分平台/窗口管理器下有效，跨平台不可靠。
    # 尺寸取 update_idletasks 后的真实值：窗口刚建时 winfo_width 可能还是 1，拿它当基准
    # 会把弹窗缩成一条线。
    try:
        window.update_idletasks()
        base_w = window.winfo_width()
        base_h = window.winfo_height()
    except tk.TclError:
        return
    if base_w <= 1 or base_h <= 1:
        return

    def _settle() -> None:
        try:
            window.geometry(f"{base_w}x{base_h}")
        except tk.TclError:
            pass

    def _resize(progress: float) -> None:
        factor = start_scale + (1.0 - start_scale) * progress
        width = max(1, round(base_w * factor))
        height = max(1, round(base_h * factor))
        try:
            # 保持几何中心不动：Tk 的 geometry 只认左上角，缩放时左上角会跟着漂，
            # 视觉上弹窗像从左上角「长」出来。补 -width/-height 让 Tk 自己居中。
            window.geometry(f"{width}x{height}-{window.winfo_rootx()}-{window.winfo_rooty()}")
        except tk.TclError:
            pass

    motion.run_frames(
        window,
        job_key,
        _resize,
        duration_ms=duration_ms,
        frames=8,
        on_done=_settle,
    )


def terminal_text(
    master: tk.Misc,
    *,
    font: Any,
    bg: str,
    fg: str,
    select_bg: str,
    pad_x: int = 12,
    pad_y: int = 10,
) -> tuple[tk.Frame, tk.Text]:
    # 终端风格日志区工厂（运行日志 / 实时弹幕流共用，替换两处逐字重复的构建段）。
    # 配色由调用方传入 gui.Colors.TERMINAL_*——刻意主题无关（见模块头「唯一例外」）。
    # 返回 (容器, 文本控件)：整体由调用方 pack/grid。内边距同样由调用方按缩放档位传入
    # （tk.Text 的 padx/pady 是裸像素、不吃 ttk 样式）。
    wrap = tk.Frame(master, bg=bg)
    text = tk.Text(
        wrap,
        # width=1：同 EditorText——默认 80 字符的请求宽会撑爆整窗 reqwidth，
        # 触发 Tk grid 右侧裁切；实际宽度由 pack(fill=BOTH, expand=True) 分配。
        width=1,
        wrap=tk.WORD,
        font=font,
        bg=bg,
        fg=fg,
        insertbackground="#FFFFFF",
        relief=tk.FLAT,
        bd=0,
        padx=pad_x,
        pady=pad_y,
        state=tk.DISABLED,
        selectbackground=select_bg,
        selectforeground="#FFFFFF",
        # 同 EditorText：中文行密集成块，日志行的默认行距偏紧，下方留 2px 行间余量
        # （上方不加：第一行顶部已有容器 pad_y，多给会让首行与标题显得偏离中轴）。
        spacing3=2,
    )
    scrollbar = ttk.Scrollbar(wrap, command=cast("Callable[..., None]", text.yview))
    text.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 4), pady=4)
    text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return wrap, text


# ─── DataTable：Treeview 增量更新表格 ──────────────────────────────────────────

# 表格行通用的「无标记」tag：调用方以 restyle_tags() 上色（空 tag 会让行继承
# Treeview 样式底色，显式 normal tag 才能拿到 token 底色与禁用行的差异化）。
TAG_NORMAL: Final[str] = "normal"


@final
class DataTable:
    # ttk.Treeview 增量更新表格（画质 / 弹幕监控页共用）。
    #
    # 为什么不是 destroy+重建：旧实现每轮数据变化整表销毁重建，鼠标按下与抬起之间行被
    # 销毁 → 点击落空，且重建期整表闪烁。Treeview 行是持久 Tk item，sync() 按 key 差异化
    # insert/delete/item/move，未变化的行零触碰。
    #
    # 行 id 直接用业务 key（主播名 / 房间名）：diff 与浮层编辑器都按它定位；tkinter 经 Tcl
    # 参数化调用传递，含空格的 key 安全（不得自行拼字符串进 Tcl）。
    # 列宽按 weight 比例分配树宽：<Configure> 触发重算（Treeview 不会随窗口等比拉伸列）。

    def __init__(self, master: tk.Misc, columns: Sequence[tuple[str, "str | ui_i18n.Translatable", int, str]]) -> None:
        # columns 元素：(列 id, 表头文案, 宽度权重, 锚点)，表头可为 Translatable（登记重译）；
        # 行高由 ui_theme 的 Treeview 样式统一给定（rowheight），不逐实例配置。
        self._columns: tuple[tuple[str, "str | ui_i18n.Translatable", int, str], ...] = tuple(columns)
        self._weights: tuple[int, ...] = tuple(c[2] for c in columns)
        self.tree = ttk.Treeview(
            master,
            columns=[c[0] for c in columns],
            show="headings",
            selectmode="none",
            takefocus=False,
        )
        for col_id, heading, _weight, anchor in columns:
            # heading 传 Translatable（ui_i18n.T）时：建时查表 + 按 heading:<col_id> 登记重译
            if isinstance(heading, ui_i18n.Translatable):
                ui_i18n.register(self.tree, f"heading:{col_id}", heading)
                heading_value: str = heading.render()
            else:
                heading_value = heading
            # anchor 形参用 str 携带（调用方写 "w"/"e"），Treeview 的存根是字面量联合，cast 收敛
            self.tree.heading(col_id, text=heading_value, anchor=cast("Any", anchor))
            self.tree.column(col_id, anchor=cast("Any", anchor), stretch=True, width=90)
        self.tree.bind("<Configure>", self._apply_proportional_widths, add="+")
        self._editor: ttk.Combobox | None = None
        self._editor_column: str | None = None
        self._editor_handlers: (
            tuple[Callable[[str], list[str]], Callable[[str], str], Callable[[str, str], None], Any] | None
        ) = None

    # 供调用方在主题切换 / 首建时配置行级 tag 颜色（如降级行、断连行）。
    def restyle_tags(self, tag_colors: dict[str, dict[str, Any]]) -> None:
        for tag, colors in tag_colors.items():
            self.tree.tag_configure(tag, **colors)

    # 按权重比例分配列宽（树首次布局与窗口变化时由 <Configure> 触发）。
    def _apply_proportional_widths(self, _event: object = None) -> None:
        width = self.tree.winfo_width()
        if width <= 1:
            return
        total = sum(self._weights)
        for col_id, _heading, weight, _anchor in self._columns:
            self.tree.column(col_id, width=max(40, int(width * weight / total)))

    # 行级增量同步。keys 顺序即展示顺序（调用方排好序）；values/tags 按 key 给出。
    # 只触碰「新增 / 消失 / 值或标记变化 / 顺序错位」的行——未变化行零重绘，这是
    # 「不再闪烁、点击不落空」的结构保证。
    # [阶段6] changed 返回本轮真正发生变化的行 key（新增 + 值/标记变化），供调用方
    # 做「变化行高亮衰减」反馈。返回空列表是常态（无变化轮），调用方据此零开销跳过。
    def sync(
        self,
        keys: Sequence[str],
        values: dict[str, tuple[str, ...]],
        tags: dict[str, tuple[str, ...]],
    ) -> list[str]:
        tree = self.tree
        existing = set(tree.get_children())
        desired = set(keys)
        for iid in existing - desired:
            tree.delete(iid)
        changed: list[str] = []
        for key in keys:
            # M-83（2026-10-21）：keys 是调用方给定的展示集合，values/tags 是两个独立字典，
            # 二者脱节时旧实现的 values[key] 直索引抛 KeyError——**整轮 sync 半途而废**：
            # 异常点之后的行不插入、顺序不收敛，表格停在旧数据上且没有任何日志。缺值行
            # 回退空元组照常落地（视觉上是一格空行），比整表失联可诊断得多。
            row_values = values.get(key, ())
            row_tags = tags.get(key, ())
            if key in existing:
                # changed 只记「这一行变了」这一次：旧实现值与标记两个分支各自 append(key)，
                # 两者同时变化的行会在返回值里出现两遍，调用方的变化行高亮对同一行叠两轮
                # 衰减动画（M-83）。行级增量语义不变——未变化行仍然零触碰。
                dirty = False
                if tuple(tree.item(key, "values")) != row_values:
                    tree.item(key, values=row_values)
                    dirty = True
                if tuple(tree.item(key, "tags") or ()) != row_tags:
                    tree.item(key, tags=row_tags)
                    dirty = True
                if dirty:
                    changed.append(key)
            else:
                tree.insert("", tk.END, iid=key, values=row_values, tags=row_tags)
                changed.append(key)
        # 顺序收敛：move 不重建控件，无闪烁；仅在现有顺序与目标不一致时逐行移到目标下标
        # （已就位则零 move 调用——「未变化轮零触碰」的判据覆盖顺序维度）。
        if list(tree.get_children()) != list(keys):
            for index, key in enumerate(keys):
                tree.move(key, "", index)
        return changed

    # 清空全部行（弹幕/画质数据整体重置时用；保持列宽与表头不动）。
    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())

    def highlight_rows(self, keys: Sequence[str], *, tag: str, colors: dict[str, Any]) -> None:
        # 「变化行高亮衰减」的单步：给指定行套上（或摘掉）一个临时背景色 tag。
        #
        # 颜色与节奏由调用方决定：DataTable 按设计不持有主题 token（tag 配色由 gui 经
        # restyle_tags 给），故「高亮成什么色、闪几帧、怎么衰减」都在调用方；本方法只提供
        # 「把颜色套到这些行上」这一条最小能力。衰减终点必须精确回到原色，否则行上会留一层
        # 永久色偏——这是本方法存在的全部理由。
        # tag_configure 对不存在的 tag 幂等（先 configure 再逐行挂），故每帧重复调用无副作用；
        # 调用方在末帧传 colors={} 即可摘除。
        self.tree.tag_configure(tag, **colors)
        for key in keys:
            if colors:
                current = tuple(self.tree.item(key, "tags") or ())
                if tag not in current:
                    self.tree.item(key, tags=(*current, tag))
            else:
                current = tuple(self.tree.item(key, "tags") or ())
                if tag in current:
                    self.tree.item(key, tags=tuple(t for t in current if t != tag))

    # 「单元格内下拉」编辑器（画质表「切换画质」列专用）：点击目标列时在该单元格
    # bbox 上浮一个 readonly Combobox，选中即回调 (行 key, 选中值) 并销毁，失焦即销毁。
    # values_for / initial_for 均以行 key 为实参（行数据由调用方在 sync 时缓存）。
    def bind_cell_editor(
        self,
        column_id: str,
        *,
        values_for: Callable[[str], list[str]],
        initial_for: Callable[[str], str],
        on_commit: Callable[[str, str], None],
        font: Any = None,
    ) -> None:
        self._editor_column = column_id
        self._editor_handlers = (values_for, initial_for, on_commit, font)
        self.tree.bind("<Button-1>", self._on_cell_press, add="+")

    def _dismiss_editor(self) -> None:
        if self._editor is not None:
            try:
                self._editor.destroy()
            except tk.TclError:
                pass
            self._editor = None

    def _on_cell_press(self, event: tk.Event) -> None:
        self._dismiss_editor()
        if self._editor_column is None or self._editor_handlers is None:
            return
        try:
            if self.tree.identify_region(event.x, event.y) != "cell":
                return
            column = self.tree.identify_column(event.x)
            col_index = int(column[1:]) - 1
        except ValueError, tk.TclError:
            return
        if col_index < 0 or col_index >= len(self._columns) or self._columns[col_index][0] != self._editor_column:
            return
        row_iid = self.tree.identify_row(event.y)
        if not row_iid:
            return
        bbox = self.tree.bbox(row_iid, column)
        if not bbox:
            # 行滚出可视区时 bbox 为空：本次点击按普通行处理（不弹编辑器）
            return
        values_for, initial_for, on_commit, font = self._editor_handlers
        editor = ttk.Combobox(self.tree, state="readonly", values=values_for(row_iid), font=font)
        editor.set(initial_for(row_iid))
        editor.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

        def _on_selected(_event: object) -> None:
            # 不写「lambda: (commit(...), dismiss())」形态——_dismiss_editor 无返回值，
            # mypy [func-returns-value] 拒绝把它放进取值表达式（同族坑第 5 处）。
            on_commit(row_iid, editor.get())
            self._dismiss_editor()

        editor.bind("<<ComboboxSelected>>", _on_selected)
        editor.bind("<FocusOut>", lambda _event: self._dismiss_editor())
        editor.focus_set()
        self._editor = editor
