# tests/test_gui_qt_label_parity.py
# 结构锁：Qt 侧「构造标签」与「T() 登记键」必须是同一个 msgid。
#
# 故障形态：`action_button("📥  最小化到托盘")` 后紧跟 `set_text(btn, T("最小化到托盘"))`，
# 启动回填与每次 retranslate_all() 都会把构造期文本覆盖成登记键的译文，emoji 前缀永久消失。
# 两处写法各写各的，单看任一行都像对的，只有比对二者才能看见。
#
# 判定取 AST 而不起 QApplication：真窗用例在本机有显示器时反以 skip 出现，而这条不变量
# 本身就是源码形态的，AST 判定不依赖显示器。

import ast
import pathlib
import re

from tests.test_i18n_catalog_coverage import _cached_catalog_key_sets

ROOT = pathlib.Path(__file__).resolve().parent.parent
QT_PKG = ROOT / "src" / "gui_qt"
_EMOJI = re.compile(r"[^\x00-\x7f一-鿿（）、，。：；「」％°]")

# 反向见证下限：至少 9 处「构造+登记」配对，其中至少 9 处带 emoji 前缀
# （只增不减，防止图标被整体剥掉）。
MIN_PAIRS = 9
MIN_EMOJI_PAIRS = 9


def _literal_str(node: ast.expr | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _call_name(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Call):
        return getattr(node.func, "id", None) or getattr(node.func, "attr", None)
    return None


def collect_label_pairs() -> list[tuple[str, str, tuple[str, str]]]:
    # 返回 [(相对路径, 控件属性名, (构造标签, T() 登记键))]：只有两类字面量都取到的站点才进结果。
    built: dict[str, dict[str, str]] = {}
    registered: dict[str, dict[str, str]] = {}
    for py in sorted(QT_PKG.rglob("*.py")):
        rel = py.relative_to(ROOT).as_posix()
        tree = ast.parse(py.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            # ① self.<attr> = action_button("字面量", ...) / QPushButton("字面量", ...)
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Attribute):
                target = node.targets[0]
                if (
                    isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and _call_name(node.value)
                    in (
                        "action_button",
                        "QPushButton",
                    )
                ):
                    assert isinstance(node.value, ast.Call)
                    label = _literal_str(node.value.args[0] if node.value.args else None)
                    if label is not None:
                        built.setdefault(rel, {})[target.attr] = label
            # ② set_text(self.<attr>, T("字面量"))
            if isinstance(node, ast.Call) and _call_name(node) == "set_text" and len(node.args) == 2:
                widget, mark = node.args
                if (
                    isinstance(widget, ast.Attribute)
                    and isinstance(widget.value, ast.Name)
                    and widget.value.id == "self"
                    and _call_name(mark) == "T"
                ):
                    assert isinstance(mark, ast.Call)
                    key = _literal_str(mark.args[0] if mark.args else None)
                    if key is not None:
                        registered.setdefault(rel, {})[widget.attr] = key
    pairs: list[tuple[str, str, tuple[str, str]]] = []
    for rel, marks in registered.items():
        for attr, key in marks.items():
            label = built.get(rel, {}).get(attr)
            if label is not None:
                pairs.append((rel, attr, (label, key)))
    return pairs


def test_qt_construct_labels_and_registered_msgids_are_the_same_key() -> None:
    pairs = collect_label_pairs()
    drift = [f"{rel}.{attr}: 构造={label!r} 登记键={key!r}" for rel, attr, (label, key) in pairs if label != key]
    assert (
        not drift
    ), (
        "Qt 控件的构造标签与 T() 键不一致，启动回填/retranslate_all() 会把构造期文本覆盖成登记键的译文"
        "（emoji 前缀因此消失）：\n" + "\n".join(drift)
    )
    emoji_pairs = [(rel, attr) for rel, attr, (label, _key) in pairs if _EMOJI.search(label)]
    assert (
        len(pairs) >= MIN_PAIRS
    ), f"配对口径失效（只找到 {len(pairs)} 处，下限 {MIN_PAIRS}）：工厂写法变了就同步改本判据，别放宽成「非空」"
    assert (
        len(emoji_pairs) >= MIN_EMOJI_PAIRS
    ), f"带 emoji 前缀的按钮配对少于 {MIN_EMOJI_PAIRS} 处——本轮恢复的图标又被整体剥掉了"


def test_qt_registered_label_keys_exist_in_all_catalogs() -> None:
    # 同源之外还得真有这条目：键写成目录里没有的形态时，运行时静默回退原文、四语都看不出来。
    key_sets = _cached_catalog_key_sets()
    offenders = []
    for rel, attr, (_label, key) in collect_label_pairs():
        absent = sorted(name for name, keys in key_sets.items() if key not in keys)
        if absent:
            offenders.append(f"{rel}.{attr} {key!r} 缺于 {absent}")
    assert not offenders, "Qt 静态标签的 msgid 未登记进全部目录：\n" + "\n".join(offenders)
