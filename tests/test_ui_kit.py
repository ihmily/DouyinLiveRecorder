# tests/test_ui_kit.py —— src/ui_kit.py 的回归锁（阶段4 GUI 控件层）。
#
# 组织：DataTable.sync 的行级增量语义是本模块的核心安全不变量（「不再闪烁、点击不落空」的
# 结构保证），用假 Treeview 记录调用面无头锁住——未变化行零触碰 / 只改差异行 / 顺序收敛，
# 删掉生产实现任一条判据必须转红（变异验证）。工厂与浮层单元格编辑器的真实 Tk 行为走
# 真窗用例（无显示环境 skip，与 tests/test_ui_theme.py 的 TestApplyTtk 同一口径）。
#
# 替身口径：DataTable 只依赖注入的 tree 对象，不建窗；替身只复刻 sync 用到的那一小片
# Treeview 协议（get_children/insert/delete/item/move），不模拟其余行为。

import ast
import tkinter as tk
from collections.abc import Generator
from pathlib import Path

import pytest

from src.ui_kit import DataTable

ROOT = Path(__file__).resolve().parents[1]

_COLUMNS = [
    ("name", "主播名称", 3, "w"),
    ("set_quality", "设置画质", 1, "w"),
    ("switch", "切换画质", 2, "w"),
]


class FakeTree:
    # 只复刻 DataTable.sync/clear 用到的 Treeview 协议切片，并记录每次变更调用。
    def __init__(self) -> None:
        self.rows: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
        self.order: list[str] = []
        self.calls: list[tuple[str, str]] = []

    def get_children(self) -> list[str]:
        return list(self.order)

    def delete(self, *iids: str) -> None:
        for iid in iids:
            self.rows.pop(iid, None)
            self.order.remove(iid)
            self.calls.append(("delete", iid))

    def insert(self, _parent: str, _index: str, iid: str, values: tuple[str, ...], tags: tuple[str, ...]) -> None:
        self.rows[iid] = (tuple(values), tuple(tags))
        self.order.append(iid)
        self.calls.append(("insert", iid))

    def item(self, iid: str, field: str | None = None, **kwargs: object) -> object:
        # setter 形态（tree.item(iid, values=..., tags=...)）：更新并记录变更调用
        if kwargs:
            values, tags = self.rows[iid]
            if "values" in kwargs:
                values = tuple(kwargs["values"])  # type: ignore[arg-type]
            if "tags" in kwargs:
                tags = tuple(kwargs["tags"])  # type: ignore[arg-type]
            self.rows[iid] = (values, tags)
            self.calls.append(("item", iid))
            return None
        values, tags = self.rows[iid]
        if field == "values":
            return list(values)
        if field == "tags":
            return list(tags)
        raise AssertionError(f"unexpected item() access: {field}")

    def move(self, iid: str, _parent: str, index: int) -> None:
        self.order.remove(iid)
        self.order.insert(index, iid)
        self.calls.append(("move", iid))


def _make_table() -> tuple[DataTable, FakeTree]:
    tree = FakeTree()
    table = DataTable.__new__(DataTable)
    # 绕过 __init__（它要真 Tk 建 Treeview）：只装配 sync/clear 用到的字段——
    # 与 tests/test_gui_tail_robustness.py 的 object.__new__ 桩同一口径。
    table.tree = tree  # type: ignore[assignment]
    table._columns = tuple(_COLUMNS)
    table._weights = tuple(c[2] for c in _COLUMNS)
    table._editor = None
    table._editor_column = None
    table._editor_handlers = None
    return table, tree


_ROWS = {
    "A": ("主播A", "原画", ""),
    "B": ("主播B", "高清", ""),
}

# 行 key 带空格（「序号N 主播名」的真实形态）：Treeview iid 含空格必须安全——
# tkinter 经 Tcl 参数化调用传递，若有人改回「自行拼字符串进 Tcl」的写法这里当场炸。
_ROWS_SPACED_KEY = "序号1 主播A"


def _rows_of(**overrides: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    rows: dict[str, tuple[str, ...]] = {k: v for k, v in _ROWS.items()}
    rows.update(overrides)
    return rows


class TestSyncIncremental:
    # 增量语义六格：本类的每条判据都对应 sync 的一个差异分支（插入/零触碰/单行更新/
    # 标记更新/删除/顺序收敛），变异验证把 sync 改回「整表删除重建」时须整体转红。

    def test_inserts_new_rows_in_order(self) -> None:
        table, tree = _make_table()
        # 首轮全量插入：调用面只允许 insert（不允许以 delete 兜底）
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        assert tree.order == ["A", "B"]
        assert tree.rows["A"] == (_ROWS["A"], ("normal",))
        assert all(kind == "insert" for kind, _ in tree.calls)

    def test_insert_with_spaced_key(self) -> None:
        # 生产键是「序号N 主播名」（含空格）：以空格 key 走一遍插入+更新
        table, tree = _make_table()
        table.sync([_ROWS_SPACED_KEY], {_ROWS_SPACED_KEY: _ROWS["A"]}, {_ROWS_SPACED_KEY: ("normal",)})
        assert tree.order == [_ROWS_SPACED_KEY]
        table.sync([_ROWS_SPACED_KEY], {_ROWS_SPACED_KEY: _ROWS["B"]}, {_ROWS_SPACED_KEY: ("normal",)})
        assert ("item", _ROWS_SPACED_KEY) in tree.calls

    def test_unchanged_rows_are_never_touched(self) -> None:
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        # 核心判据：无变化轮零触碰（旧实现每轮 destroy+重建正败于此）
        assert tree.calls == [], f"未变化轮不应有任何变更调用: {tree.calls}"

    def test_only_changed_row_is_updated(self) -> None:
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.sync(["A", "B"], _rows_of(B=("主播B", "超清", "")), {"A": ("normal",), "B": ("normal",)})
        assert ("item", "B") in tree.calls
        assert all(iid == "B" for _kind, iid in tree.calls), f"更新波及了无关行: {tree.calls}"
        assert tree.rows["B"][0] == ("主播B", "超清", "")

    def test_tag_change_is_updated(self) -> None:
        # 标记（降级/断连行着色载体）变化也要走 item() 更新，而不是重建行
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.sync(["A", "B"], _rows_of(), {"A": ("downgraded",), "B": ("normal",)})
        assert ("item", "A") in tree.calls
        assert tree.rows["A"][1] == ("downgraded",)

    def test_removed_row_is_deleted(self) -> None:
        # 消失行必须走 delete 且只删该行——「停止录制后旧行残留」是旧实现同族缺陷面
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.sync(["A"], _rows_of(A=_ROWS["A"]), {"A": ("normal",)})
        assert tree.calls == [("delete", "B")]
        assert tree.order == ["A"]

    def test_reorder_converges_without_rebuild(self) -> None:
        # 顺序收敛只允许 move（行对象不动）：destroy+重建顺序的写法在这里当场红
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.sync(["B", "A"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        assert tree.order == ["B", "A"]
        assert all(kind != "delete" and kind != "insert" for kind, _ in tree.calls), "顺序收敛不得重建行"

    def test_clear_removes_all_rows(self) -> None:
        # clear() 供「停止录制清空重开」路径使用：只清行，不得动列宽/表头（由列配置承载）
        table, tree = _make_table()
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        tree.calls.clear()
        table.clear()
        assert tree.order == [] and tree.rows == {}
        assert tree.calls and all(kind == "delete" for kind, _ in tree.calls)

    def test_missing_values_key_does_not_abort_sync(self) -> None:
        # M-83 行为锁①：keys 是展示集合、values/tags 是两个独立字典，三者脱节在热更新
        # 竞态里是真实可发生的形态。旧实现 values[key] 直索引抛 KeyError——**整轮 sync
        # 半途而废**：异常点之后的行不插入、删除与顺序收敛都不执行，表格静默停在旧数据
        # 上且日志一条没有（比缺一格难看的数据严重得多）。定稿 values.get(key, ())：
        # 缺值行落空元组照常存在，其余行完整同步。
        table, tree = _make_table()
        changed = table.sync(["A", "B"], {"A": _ROWS["A"]}, {})
        assert tree.order == ["A", "B"], "缺值行不得带走整轮同步"
        assert tree.rows["B"] == ((), ())
        assert changed == ["A", "B"]
        # 后续轮次仍能被同一 key 正常接管（空行不是终态）
        table.sync(["A", "B"], _rows_of(), {"A": ("normal",), "B": ("normal",)})
        assert tree.rows["B"][0] == _ROWS["B"]

    def test_row_with_both_value_and_tag_change_counts_once(self) -> None:
        # M-83 行为锁②：changed 的语义是「这一行变了」，不是「变了几个字段」。旧实现值
        # 分支与标记分支各自 append(key)，两者同变的行在返回值里出现两遍——调用方的
        # 「变化行高亮衰减」会对同一行叠两轮动画。行级增量语义不得回退（未变化行零触碰
        # 由 test_unchanged_rows_are_never_touched 守着）。
        table, tree = _make_table()
        table.sync(["A"], _rows_of(A=_ROWS["A"]), {"A": ("normal",)})
        changed = table.sync(["A"], _rows_of(A=_ROWS["B"]), {"A": ("downgraded",)})
        assert changed == ["A"], "值与标记同时变化时 changed 必须去重"


class TestSourceLocks:
    def test_sync_defined_once_with_no_destroy_rebuild(self) -> None:
        # 结构锁（行为锁的兜底）：sync 的实现里不得出现「全部删除再重建」的形态——
        # 行为锁锁调用面，这把锁防止未来重构把「delete(*children) + 全量 insert」带回来
        import src.ui_kit as uk

        src = Path(uk.__file__).read_text(encoding="utf-8")
        fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "sync")
        seg = ast.get_source_segment(src, fn)
        assert seg, "sync 源码段提取失败"
        assert "delete(*" not in seg, "sync 不得整表删除重建"
        assert seg.count("tree.insert") == 1 and seg.count("tree.item(") >= 1


class TestRealWindowWidgets:
    # 真窗用例（无显示环境 skip，与本文件唯一 skip 面）：浮层编辑器与派生样式依赖真实
    # Tcl 事件循环，无头环境无法等价驱动；tk_root fixture 形态取
    # tests/test_ui_theme.py::TestApplyTtk.tk_root。
    # [历史注 MT-12 2026-10-18] 此前「无显示即 skip」是空头承诺：三条用例裸 tk.Tk()，
    # 无显示器时抛 TclError 以 ERROR 形态进门禁、把「没显示设备」伪装成「代码回归」，故补 fixture。
    # 与 AGENTS「平台专属分支的测试不得靠 skipif 让 CI 跳过」不冲突：那条禁的是按
    # sys.platform 跳过**代码分支**（Windows/POSIX 两侧逻辑都得在 CI 真跑），本处缺的是
    # **显示设备**本身；CI 侧仍由 xvfb-run 提供虚拟显示让这些用例常态执行（见 ci.yml 的
    # 「Install ffmpeg + xvfb + Qt runtime libs (apt)」与「pytest 全程跑在 xvfb 下」两步，
    # 其注释已把 test_ui_kit 的真窗用例列为常态执行面），skip 只兜无 xvfb 的裸环境。
    # 与范本的唯一差异：**不 withdraw**——bbox 取单元格几何、event_generate 打真实事件，
    # 都要求窗体真正映射过；隐藏根窗后 winfo 宽度退化为 1，用例会以「目标单元格不可见」误红。
    @pytest.fixture()
    def tk_root(self) -> Generator[tk.Tk, None, None]:
        try:
            root = tk.Tk()
        except tk.TclError as e:
            pytest.skip(f"无显示环境，跳过 Tk 真窗用例: {e}")
        yield root
        root.destroy()

    _COLUMNS_GUI = [
        ("name", "主播名称", 3, "w"),
        ("set_quality", "设置画质", 1, "w"),
        ("switch", "切换画质", 2, "w"),
    ]

    def _build(self, root: object) -> tuple[DataTable, list[tuple[str, str]]]:
        from src.ui_kit import font_style  # 真窗分支内导入（无显示环境 skip 前不触碰 Tk）

        table = DataTable(root, self._COLUMNS_GUI)  # type: ignore[arg-type]
        table.tree.pack()
        commits: list[tuple[str, str]] = []
        table.bind_cell_editor(
            "switch",
            # 值/初值/提交全部以行 key 为实参——与 gui._quality_row_setq 的缓存口径一致
            values_for=lambda key: ["默认画质", "高清", "原画"],
            initial_for=lambda key: "高清",
            on_commit=lambda key, value: commits.append((key, value)),
        )
        root.update()  # type: ignore[attr-defined]
        return table, commits

    def test_cell_editor_opens_and_commits(self, tk_root: tk.Tk) -> None:
        # 点击「切换画质」列 → 单元格 bbox 上浮 readonly 下拉，初值 = 该行当前画质；
        # 选中即按 (行, 选中值) 提交并销毁；这两步合起来锁「点击不落空」的新实现面
        table, commits = self._build(tk_root)
        table.sync(
            ["A", "B"],
            {"A": ("主播A", "高清", ""), "B": ("主播B", "原画", "")},
            {"A": ("normal",), "B": ("normal",)},
        )
        tk_root.update()
        bbox = table.tree.bbox("A", "#3")
        assert bbox, "目标单元格不可见，无法驱动浮层编辑器"
        x, y = bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2
        table.tree.event_generate("<Button-1>", x=x, y=y)
        tk_root.update()
        assert table._editor is not None, "点击「切换画质」列未弹出浮层编辑器"
        assert table._editor.get() == "高清", "浮层编辑器初值应为该行当前画质"
        # 选中即提交并销毁（模拟用户在下拉里选「原画」）
        table._editor.set("原画")
        table._editor.event_generate("<<ComboboxSelected>>")
        tk_root.update()
        assert commits == [("A", "原画")], f"提交回调未按 (行, 选中值) 触发: {commits}"
        assert table._editor is None, "选中后浮层编辑器应销毁"

    def test_font_style_derives_and_caches(self, tk_root: tk.Tk) -> None:
        from tkinter import ttk

        import src.ui_kit as uk

        style = ttk.Style(tk_root)
        style.configure("Prov.TButton", background="#123456")
        style.map("Prov.TButton", background=[("active", "#234567")])
        name1 = uk.font_style("Prov.TButton", ("Arial", 20), tk_root)
        name2 = uk.font_style("Prov.TButton", ("Arial", 20), tk_root)
        assert name1 == name2, "同 (变体, 字体) 必须复用同一派生样式"
        assert name1.endswith(".Prov.TButton")
        derived_cfg = style.configure(name1)
        assert derived_cfg is not None and "font" in derived_cfg, "派生样式必须注入字体"
        assert derived_cfg.get("background") == "#123456", "派生样式必须继承基础变体静态配置"
        derived_map = style.map(name1)
        assert derived_map.get("background") == [("active", "#234567")], "派生样式必须继承基础变体状态映射"
        # 与基础变体不同字体的另一枚派生样式
        name3 = uk.font_style("Prov.TButton", ("Arial", 12), tk_root)
        assert name3 != name1

    def test_translatable_text_registers_and_retranslates(
        self, tk_root: tk.Tk, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # T()（ui_i18n.Translatable）经工厂「建时查表 + 登记重译」：语言切换后
        # retranslate_all 回填当前语言值。删掉工厂里的 register 调用本用例必须转红（变异验证）。
        import i18n
        import src.ui_kit as uk
        from src import ui_i18n

        label = uk.Label(tk_root, text=ui_i18n.T("待 机"))
        button = uk.Button(tk_root, text=ui_i18n.T("开始录制"))
        assert label.cget("text") == "待 机"
        assert button.cget("text") == "开始录制"
        # 非恒等翻译：证明重译走 tr 查表（每次渲染取当前目录），而不是建时定格
        monkeypatch.setattr(i18n, "_tr", lambda text: f"<<{text}>>")
        applied = ui_i18n.retranslate_all()
        assert applied >= 2, "两个控件都必须登记在册"
        assert label.cget("text") == "<<待 机>>"
        assert button.cget("text") == "<<开始录制>>"
        # 普通 str 文本不登记：切语言不得被改写
        plain = uk.Label(tk_root, text="DouyinLiveRecorder")
        assert ui_i18n.retranslate_all() >= 2
        assert plain.cget("text") == "DouyinLiveRecorder"
