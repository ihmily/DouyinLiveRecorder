# M-12 回归锁：main.py 的「弹幕录制平台(逗号分隔)」解析必须逐项 strip
# 并丢弃空项。
#
# 被测生产实现：main.py::main() 每轮配置重读里的
#   danmaku_platforms = [p.strip() for p in ...split(",") if p.strip()]
# 匹配点：main.py 的 `platform in danmaku_platforms`（_danmaku_active 分支，弹幕采集接线）。
#
# 为什么不 import main 驱动：该读取点内联在录制主循环的 try 块里、没有可注入的函数边界，为一条
# 配置读取重构 main() 会牵进整条录制链/线程模型，且 `import main` 在导入期会切整个进程的控制台码页。
# 故沿用本仓既有手法：按 AST 取出 main.py 里**那一条生产赋值语句原文**编译执行（同族做法见
# tests/test_regression_main.py::TestFlvConvertBeforeCommentEnd）。执行的是生产源码而非
# 测试自写的等价逻辑——把生产那行的 .strip() 删掉，本文件立即变红（已实跑变异验证）。

import ast
import configparser
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_FILE = REPO_ROOT / "main.py"
CONFIG_FILE = REPO_ROOT / "config" / "config.ini"
# utf-8-sig：与本仓其它直接读 main.py 源码的门禁用例同口径（BOM 存在时不污染首行 token）。
MAIN_SRC = MAIN_FILE.read_text(encoding="utf-8-sig")

_ASSIGNS: dict[str, list[ast.Assign]] | None = None


def _assign_nodes(name: str) -> list[ast.Assign]:
    # 一次性扫出 main.py 里所有「目标变量名 → 赋值语句」，供原文取用。
    global _ASSIGNS
    if _ASSIGNS is None:
        bucket: dict[str, list[ast.Assign]] = {}
        for node in ast.walk(ast.parse(MAIN_SRC)):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        bucket.setdefault(target.id, []).append(node)
        _ASSIGNS = bucket
    return _ASSIGNS.get(name, [])


def _assign_segment() -> str:
    # 取 main.py 里 danmaku_platforms 那条赋值语句的**原文**（含被括号包住的续行）。
    found = _assign_nodes("danmaku_platforms")
    assert found, "main.py 中找不到 danmaku_platforms 的赋值语句（M-12 修复形态已丢失）"
    assert len(found) == 1, f"danmaku_platforms 应只有一处赋值，实为 {len(found)} 处"
    segment = ast.get_source_segment(MAIN_SRC, found[0])
    assert segment is not None, "无法取到 danmaku_platforms 赋值语句原文"
    return segment


def _value_segment(name: str) -> str:
    found = _assign_nodes(name)
    assert found, f"main.py 中找不到 {name} 的赋值语句"
    segment = ast.get_source_segment(MAIN_SRC, found[0].value)
    assert segment is not None, f"无法取到 {name} 赋值右侧原文"
    return segment


def _parse(raw: str) -> list[str]:
    # 用生产表达式原文编译执行，只把左侧的输入字符串换成用例值。
    namespace: dict[str, Any] = {"danmaku_platforms_str": raw}
    exec(compile(_assign_segment(), "<danmaku_platforms>", "exec"), namespace)  # noqa: S102
    value: Any = namespace["danmaku_platforms"]
    assert isinstance(value, list), f"生产表达式应产出 list，实为 {type(value).__name__}"
    return [str(item) for item in value]


class TestProductionExpressionStrips:
    # 解析形态：带空格 / 全角逗号 / 空项混入的配置值必须解析成干净的平台名集合。

    def test_space_after_comma_is_stripped(self) -> None:
        # 面板/GUI 里最常见的手写法：半角逗号后带空格。
        assert _parse("斗鱼直播, B站直播") == ["斗鱼直播", "B站直播"]

    def test_full_width_comma_and_spaces(self) -> None:
        # 全角逗号（replace 归一）+ 项前后空格 + 尾随分隔符同时出现。
        assert _parse("斗鱼直播， B站直播 , 虎牙直播 ,") == ["斗鱼直播", "B站直播", "虎牙直播"]

    def test_empty_items_dropped(self) -> None:
        # 连续逗号/纯空格项不得留下空字符串元素（空元素会让平台名匹配与面板展示双双失真）。
        assert _parse("B站直播,,   ,虎牙直播") == ["B站直播", "虎牙直播"]

    def test_tab_and_newline_injected_items_stripped(self) -> None:
        # strip 覆盖制表符与换行（从 Excel/网页复制粘贴的常见污染形态）。
        assert _parse("\tB站直播\n, 抖音直播 ") == ["B站直播", "抖音直播"]

    def test_empty_string_gives_empty_list(self) -> None:
        # 边界：空配置值 → 空列表（原三元式的 else [] 分支，不得抛错）。
        assert _parse("") == []

    def test_shipped_default_unchanged(self) -> None:
        # 仓库脱敏基线模板里的默认值（无空格）解析结果必须逐项相等——本修复不得改默认语义。
        default = "斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV"
        assert _parse(default) == default.split(",")

    def test_shipped_config_ini_value_parses_cleanly(self) -> None:
        # 真机输入：仓库随附的 config/config.ini 里那一行的实际值（面板/GUI 就是往这里写）。
        # 读法与 CI 配置键审计同口径（utf-8-sig 剥 BOM、键名先归一小写）。
        parser = configparser.ConfigParser()
        parser.read(str(CONFIG_FILE), encoding="utf-8-sig")
        raw = parser.get("录制设置", "弹幕录制平台(逗号分隔)", fallback="")
        assert raw, f"{CONFIG_FILE.name} 里缺少「弹幕录制平台(逗号分隔)」键，本锁的观察点失效"
        parsed = _parse(raw)
        assert parsed and all(item == item.strip() and item for item in parsed), parsed
        # 基线模板应覆盖多个可采集弹幕的平台（数量随模板演进，这里只锁「解析非空且无空白项」）。
        assert len(parsed) == len(raw.replace("，", ",").split(",")), f"解析丢项/多出空项: {raw!r} -> {parsed}"

    def test_no_item_keeps_surrounding_whitespace(self) -> None:
        # 不变量口径：任何输入下产出的元素都不得带首尾空白（这条是「静默失效」的正身）。
        raw = " 斗鱼直播 ,B站直播\t, , 虎牙直播 ,,"
        parsed = _parse(raw)
        assert all(item == item.strip() and item for item in parsed), parsed


class TestMembershipHits:
    # 匹配点口径：main.py 用 `platform in danmaku_platforms` 精确比较，解析干净才能命中。

    def test_membership_after_strip(self) -> None:
        platforms = _parse("斗鱼直播, B站直播，虎牙直播 ")
        for platform in ("斗鱼直播", "B站直播", "虎牙直播"):
            assert platform in platforms, f"{platform} 未命中，弹幕会被静默关闭"

    def test_matching_predicate_exists_in_main(self) -> None:
        # 锁住「匹配点是精确成员判断」这条接线本身：一旦改成子串/模糊匹配，上面的 strip 用例
        # 就失去意义，本条会先变红提醒口径漂移。
        tree = ast.parse(MAIN_SRC)
        hit = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In):
                left = ast.unparse(node.left)
                rights = [ast.unparse(r) for r in node.comparators]
                if left == "platform" and "danmaku_platforms" in rights:
                    hit = True
        assert hit, "main.py 里找不到 `platform in danmaku_platforms` 匹配点（接线形态已变化，需复核本锁）"

    def test_production_expression_contains_strip(self) -> None:
        # 与上方行为锁互补的静态形态锁：赋值右侧必须同时出现「逐项 strip」与「空项过滤」。
        assert _value_segment("danmaku_platforms").count("strip()") >= 2, _value_segment("danmaku_platforms")

    def test_same_idiom_as_hls_exclude_list(self) -> None:
        # 对照实现同口径：HLS采集排除平台（hls_collection_exclude_platforms）本就是
        # [p.strip() for p in ... if p.strip()]，两处解析形态必须一致（AGENTS「与 HLS 列表同口径」）。
        # 只比 **右侧表达式**（左侧变量名本就不同），并把各自的输入字符串变量名归一后再比。
        def _normalized(name: str, source_var: str) -> str:
            seg = _value_segment(name)
            return "".join(seg.split()).replace(source_var, "S")

        danmaku = _normalized("danmaku_platforms", "danmaku_platforms_str")
        hls = _normalized("hls_collection_exclude_platforms", "hls_exclude_platforms_str")
        assert danmaku == hls, f"两处平台列表解析口径已分叉:\n danmaku={danmaku}\n hls     ={hls}"


@pytest.mark.parametrize("raw,expected", [("", []), ("B站直播", ["B站直播"])])
def test_parametrized_boundaries(raw: str, expected: list[str]) -> None:
    assert _parse(raw) == expected
