# src/ui_kit.py
# GUI 控件层（阶段4：UI 现代化）：CTk 兼容工厂 → tkinter.ttk 映射 + Treeview 增量更新表格。
#
# 设计约束（提案 PROPOSAL_2026-09-29_ui-modernization §3.3/§5.3 + 工作日志 §2.4）：
#   · **颜色一律不进工厂**：全部配色由 src/ui_theme.ThemeManager 注册的 ttk 变体样式
#     （Card.TFrame / Alt.TFrame / Success.TButton / Muted.TLabel / NavActive.TButton …）
#     从语义槽位派生，主题切换时由 ttk 全局样式统一重绘——任何控件不得绕过槽位直写颜色
#     （与 ui_theme 头注释同一条铁律）。调用方以 variant 字符串选择样式。
#   · 终端配色是唯一例外：gui.Colors.TERMINAL_* 是刻意的主题无关常量（两种主题下均保持
#     深色终端风格），由 terminal_text() 以 tk 控件落地、调用方传色，不进槽位体系。
#   · 工厂签名对齐 CustomTkinter 惯用形态（text/command/font/values/set/get/
#     configure(values=)），但**不收 fg_color/hover_color 等 CTk 颜色参数**；
#     CTkOptionMenu.set() 「只改显示值、不触发 command」的语义由 readonly Combobox
#     的 <<ComboboxSelected>> 绑定逐字保留（表格重建回设画质不会误写配置）。
#   · 监控表格用 DataTable 包 ttk.Treeview：按 key 差异化 insert()/delete()/item()/move()
#     的行级增量更新，取代旧 CTkScrollableFrame「每轮 destroy + 重建」的整表闪烁与点击落空
#     （提案 §3.3 的机制性收益）；每行「切换画质」下拉用单元格 bbox 浮层 Combobox 实现
#     （tkinter 官方 editable-cell recipe，Treeview 本身不支持内嵌控件）。
#   · [阶段5] customtkinter 依赖已整体摘除：本模块与 gui.py 均只依赖 tkinter/ttk，
#     零 CTk 引用（历史注：阶段4 期间与 CTk 共存过，逐页回退能力随摘除终止）。
#   · import 期零 Tk 对象（只有类定义与纯函数）：无头 Linux CI 可安全 import，
#     `import gui` 链路不受影响。
from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence
from tkinter import ttk
from typing import Any, Final, Literal, cast, final

from src import ui_i18n

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

# font_style() 的派生样式缓存：键 (基础变体样式名, 字体键)。
_FONT_STYLE_CACHE: dict[tuple[str, str], str] = {}


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
    # CTkButton 替身。variant 见 BUTTON_STYLES；CTk 的 fg_color/hover_color/text_color/
    # border_* 全部并入样式（主题切换自动跟随）。ttk 无像素级 height/width（前者由
    # padding 撑起、后者按文本宽度自适应），调用方以 padding 控制体量。
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


def font_style(base: str, font: Any, widget: tk.Misc) -> str:
    # 返回「基础变体样式 + 字体」的派生样式名（按 (base, font) 缓存，同字体同变体共用）。
    # 派生名显式复制基础变体的静态配置与状态映射——不依赖 ttk 的点分回退语义
    # （实测 Tk 9.0 上 style.configure/map 跨段回退行为不可靠，布局可回落、选项未必）。
    key = (base, _font_key(font))
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


def _font_key(font: Any) -> str:
    # 字体的缓存键：tk.font.Font（含 CTkFont）取实际三元组，元组字体逐项拼接。
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
    # 继承的 .set() 只改显示值、不触发该虚拟事件——与 CTkOptionMenu.set() 语义一致。
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
        self, master: tk.Misc, *, tokens: dict[str, str], font: Any, wrap: Literal["none", "char", "word"] = "none"
    ) -> None:
        super().__init__(
            master,
            wrap=wrap,
            font=font,
            bg=tokens["surface_alt"],
            fg=tokens["text"],
            insertbackground=tokens["text"],
            selectbackground=tokens["primary"],
            selectforeground=tokens["on_primary"],
            relief=tk.FLAT,
            bd=0,
            padx=10,
            pady=8,
            highlightthickness=1,
            highlightbackground=tokens["border"],
            highlightcolor=tokens["primary"],
            undo=True,
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


def terminal_text(
    master: tk.Misc,
    *,
    font: Any,
    bg: str,
    fg: str,
    select_bg: str,
) -> tuple[tk.Frame, tk.Text]:
    # 终端风格日志区工厂（运行日志 / 实时弹幕流共用，替换两处逐字重复的构建段）。
    # 配色由调用方传入 gui.Colors.TERMINAL_*——刻意主题无关（见模块头「唯一例外」）。
    # 返回 (容器, 文本控件)：容器承载右侧 ttk 滚动条 + 左侧 Text，整体由调用方 pack/grid。
    wrap = tk.Frame(master, bg=bg)
    text = tk.Text(
        wrap,
        wrap=tk.WORD,
        font=font,
        bg=bg,
        fg=fg,
        insertbackground="#FFFFFF",
        relief=tk.FLAT,
        bd=0,
        padx=12,
        pady=10,
        state=tk.DISABLED,
        selectbackground=select_bg,
        selectforeground="#FFFFFF",
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
    # 为什么不是 destroy+重建：旧 CTkScrollableFrame 实现每轮数据变化整表销毁重建，
    # 鼠标按下与抬起之间行被销毁 → 点击落空；重建期整表闪烁。Treeview 行是持久的
    # Tk item，sync() 按 key 差异化 insert/delete/item/move，未变化的行零触碰。
    #
    # 行 id 直接用业务 key（主播名 / 房间名）：diff 与浮层编辑器都按它定位；
    # tkinter 经 Tcl 参数化调用传递，含空格的 key 安全（不得自行拼字符串进 Tcl）。
    #
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
    def sync(
        self,
        keys: Sequence[str],
        values: dict[str, tuple[str, ...]],
        tags: dict[str, tuple[str, ...]],
    ) -> None:
        tree = self.tree
        existing = set(tree.get_children())
        desired = set(keys)
        for iid in existing - desired:
            tree.delete(iid)
        for key in keys:
            row_values = values[key]
            row_tags = tags.get(key, ())
            if key in existing:
                if tuple(tree.item(key, "values")) != row_values:
                    tree.item(key, values=row_values)
                if tuple(tree.item(key, "tags") or ()) != row_tags:
                    tree.item(key, tags=row_tags)
            else:
                tree.insert("", tk.END, iid=key, values=row_values, tags=row_tags)
        # 顺序收敛：move 不重建控件，无闪烁；仅在现有顺序与目标不一致时逐行移到目标下标
        # （已就位则零 move 调用——「未变化轮零触碰」的判据覆盖顺序维度）。
        if list(tree.get_children()) != list(keys):
            for index, key in enumerate(keys):
                tree.move(key, "", index)

    # 清空全部行（弹幕/画质数据整体重置时用；保持列宽与表头不动）。
    def clear(self) -> None:
        self.tree.delete(*self.tree.get_children())

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
