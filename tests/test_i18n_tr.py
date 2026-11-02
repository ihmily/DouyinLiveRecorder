# -*- coding: utf-8 -*-
# i18n.tr() 回归：先查表再插值。
#
# 顺序不可交换：f"[{record_name}] xxx" 会先被求值成 "[房间A] xxx"，而目录的 msgid 是带占位符
# 的模板，查表必 miss、翻译静默退化为原文。故调用方一律传模板 + kwargs，由 tr() 用模板查表、
# 命中后再 .format(**kwargs)。

from types import SimpleNamespace

import i18n


def test_tr_passes_through_when_no_translation() -> None:
    # 未命中目录：原文模板照常 format 插值
    assert i18n.tr("plain text {x}", x=1) == "plain text 1"


def test_tr_with_placeholder_passes_through_correctly() -> None:
    # 含占位符且目录无译文：仍能正常 format
    assert i18n.tr("[{room}] hello", room="A") == "[A] hello"


def test_tr_with_format_expression_via_kwarg() -> None:
    # {type(e).__name__} 不是合法 format 占位符：调用方须预求值后按名传入
    try:
        raise ValueError("boom")
    except ValueError as e:
        out = i18n.tr("caught {type_name}: {e}", type_name=type(e).__name__, e=e)
    assert out == "caught ValueError: boom"


def test_tr_missing_kwarg_falls_back_to_template() -> None:
    # 占位符缺对应 kwarg 时降级为原文模板、不抛异常：tr() 调用点大量位于 except 分支，
    # 译文又是外部可编辑数据（译者可能把 {e} 写成 {err}），二次异常会顶掉原始异常、
    # 把「网络失败」升级成崩溃。拼写错误靠日志里未插值的花括号识别。
    # [历史注] 旧用例断言「必须 KeyError」，锁的正是这条会二次崩溃的前提。
    assert i18n.tr("hello {name}") == "hello {name}"


def test_tr_translates_then_formats() -> None:
    # 命中译文后占位符按 .format 二次插值
    saved = i18n._tr
    try:
        i18n._tr = lambda template: {
            "Hello {name}, you are {age}": "你好 {name},你 {age} 岁",
        }.get(template, template)
        out = i18n.tr("Hello {name}, you are {age}", name="张三", age=18)
        assert out == "你好 张三,你 18 岁"
    finally:
        i18n._tr = saved


def test_tr_does_not_match_substituted_form() -> None:
    # 反向锁：已插值的字符串查带占位符的目录键必须 miss（即旧实现的「翻译静默失效」形态）
    saved = i18n._tr
    try:
        i18n._tr = lambda template: {
            "[{record_name}] template": "已翻译",
        }.get(template, template)
        out_runtime = i18n.tr("[房间A] template")  # 已插值形态
        # 目录里只有模板键 "[{record_name}] template"，插值后的串查不到
        assert out_runtime == "[房间A] template"
    finally:
        i18n._tr = saved


# ---------------------------------------------------------------------------
# M-19：tr() 的「永不抛」还须覆盖**值侧**失败——占位符语法合法，但实参为 None 时
# str.format 抛 AttributeError（{x.y}）或 TypeError（{x:d}）。危害同 MI-23：except 分支内
# 二次异常顶掉原始异常、掩盖真实故障。以下用例是该缺口的回归锁。
# 注：conftest 的 _pin_identity_translation 把 _tr 钉成恒等映射，故默认路径是「恒等 +
# 原文都格式化失败 → 返回裸模板」；需要「译文命中」时按本文件惯例临时替换 i18n._tr。


def test_tr_attribute_error_placeholder_degrades_to_template() -> None:
    # x=None 时 {x.y} 抛 AttributeError（NoneType 无属性 y）：恒等/原文两级都失败 → 裸模板
    assert i18n.tr("value {x.y}", x=None) == "value {x.y}"


def test_tr_type_error_format_spec_degrades_to_template() -> None:
    # x=None 时 {x:d} 抛 TypeError（NoneType.__format__ 不收该格式符）：同上 → 裸模板
    assert i18n.tr("count {x:d}", x=None) == "count {x:d}"


def test_tr_attribute_error_falls_back_to_original_template() -> None:
    # 降级顺序不可反转：译文多出 {a.b}（译者手滑）而原文没有该占位符，先试原文才仍能正常插值
    saved = i18n._tr
    try:
        i18n._tr = lambda template: "详情 {a.b} {name}" if template == "detail {name}" else template
        assert i18n.tr("detail {name}", a=None, name="A") == "detail A"
    finally:
        i18n._tr = saved


def test_tr_type_error_falls_back_to_original_template() -> None:
    # 同上一条，失败类型换成 TypeError。两条一起锁住「AttributeError/TypeError 与 KeyError
    # 走同一套两级降级」，而不是被新增的 except 分支直接吞成裸模板。
    saved = i18n._tr
    try:
        i18n._tr = lambda template: "年龄 {age:d}" if template == "age {age}" else template
        assert i18n.tr("age {age}", age=None) == "age None"
    finally:
        i18n._tr = saved


def test_tr_valid_attribute_and_format_spec_still_interpolate() -> None:
    # 反向锁：扩异常元组不得把合法的属性/格式占位符一并吞掉，降级只在异常时发生
    obj = SimpleNamespace(y=7)
    assert i18n.tr("row {x.y}", x=obj) == "row 7"
    assert i18n.tr("n {x:d}", x=5) == "n 5"


def test_tr_missing_key_degradation_path_unchanged() -> None:
    # M-19 只加异常类型、不改语义：缺 kwarg 仍走 KeyError 支路，输出形态与新增两种异常一致
    assert i18n.tr("hello {name}", name="A") == "hello A"
    assert i18n.tr("hello {name}") == "hello {name}"
    assert i18n.tr("hello {name}", name=None) == "hello None"
