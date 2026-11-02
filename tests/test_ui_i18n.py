# -*- coding: utf-8 -*-
# src/ui_i18n.py 的回归锁：T 标记渲染、登记表回填、死亡引用清理、同控件覆盖、setText 接线。
# 为什么不依赖真实窗口：登记表只对控件做 setText 一个动作，
# 假控件对象即可全行为覆盖（真实控件集成由 tests/test_gui_qt_units.py 的窗口用例承担）。
#
# 变异敏感点（删掉对应生产实现必须转红）：
#   · T.render 改回常量返回 → 非恒等目录用例转红；
#   · register 的「同控件去重」删掉 → 同键覆盖用例转红（旧文案会在下一轮回填里复活）；
#   · retranslate_all 的死亡引用清理删掉 → 登记表随窗口开关无界增长。

import gc
import weakref

import pytest

import i18n
import src.ui_i18n as ui_i18n


class _FakeWidget:
    # 记录 setText 调用的最小替身：retranslate_all 对它只有 setText 一个动作面。
    def __init__(self) -> None:
        self.texts: list[str] = []

    def setText(self, value: str) -> None:
        self.texts.append(value)


def test_t_marker_renders_identity_under_pinned_catalog() -> None:
    # 恒等目录（conftest 固定）下 render 返回 msgid 本身、占位符由 kwargs 插值；
    # 两条断言分别锁「无占位符原样返回」与「占位符按当前语言模板插值」，
    # 后者同时是「render 走 i18n.tr 而不是 str.format 直拼」的最小见证。
    trans = ui_i18n.T("开始录制")
    assert trans.render() == "开始录制"
    assert ui_i18n.T("{name} 已连接", name="房间A").render() == "房间A 已连接"


def test_register_and_retranslate_applies_current_language(monkeypatch: pytest.MonkeyPatch) -> None:
    # 建时翻译 + 切换后回填的两段式：登记后 retranslate_all 立即生效，
    # 换非恒等目录再回填证明 render 每次都查**当前**目录——若实现改成建时把译文存进
    # 登记表（缓存译文），切换语言后回填的仍是旧语言，第二段断言转红。
    widget = _FakeWidget()
    ui_i18n.register(widget, ui_i18n.T("开始录制"))
    assert ui_i18n.retranslate_all() == 1
    assert widget.texts == ["开始录制"]

    # 语言切换后再回填：模拟非恒等翻译，证明 render 每次查当前目录而不是建时定格
    monkeypatch.setattr(i18n, "_tr", lambda text: f"[{text}]")
    assert ui_i18n.retranslate_all() == 1
    assert widget.texts[-1] == "[开始录制]"


def test_set_text_applies_immediately_and_registers() -> None:
    # set_text 是窗口层唯一接线入口：建时立即 setText，同时登记供后续回填。
    widget = _FakeWidget()
    ui_i18n.set_text(widget, ui_i18n.T("导入字体…"))
    assert widget.texts == ["导入字体…"]
    assert ui_i18n.retranslate_all() == 1
    assert widget.texts == ["导入字体…", "导入字体…"]


def test_retranslate_prunes_dead_widgets() -> None:
    # 弱引用 + 回填时清理：窗口随开随关，登记表若持强引用或从不清理，
    # 每开关一次窗口就永久多留一条（已销毁控件还会在回填时抛 RuntimeError 打断整轮回填）。
    # 断言「计数恰好回落 1」而不是「>= 0」：后者对「不清理」也成立，等于没锁。
    widget = _FakeWidget()
    ui_i18n.register(widget, ui_i18n.T("待 机"))
    ref = weakref.ref(widget)
    before = ui_i18n.registered_count()
    del widget
    gc.collect()
    assert ref() is None
    # 死亡引用被顺带清理：回填数不含死条目，登记表也不残留
    assert ui_i18n.retranslate_all() >= 0
    assert ui_i18n.registered_count() == before - 1


def test_same_widget_reregister_replaces() -> None:
    # 同一控件重复登记以最后一次为准：工厂与调用方都可能登记（例如构造后又
    # 手工改文本再登记），保留旧条目会让「最后一次登记的新文案」在下一轮回填里被覆盖回旧值。
    # 断言回填结果恰好只有新文案——两条都在时 count 会变 2，本用例转红。
    widget = _FakeWidget()
    ui_i18n.register(widget, ui_i18n.T("旧文案"))
    ui_i18n.register(widget, ui_i18n.T("新文案"))
    assert ui_i18n.retranslate_all() == 1
    assert widget.texts == ["新文案"]


def test_register_dedupe_holds_under_extra_weakrefs() -> None:
    # M-82 行为锁：同控件去重必须建立在 weakref 的**文档保证**（`==` 比较 referent）之上，
    # 而不是 CPython「同一 referent 的无回调 ref() 恒返回同一规范化对象」这一实现细节
    # （`is` 形态）。本用例把「去重被摘掉」的形态炸红——这才是 register 真正要守的契约：
    # 重复登记同一控件只占一格、旧文案不参与回填。带回调哨兵弱引用刻意留在
    # 现场：2026-10-21 实测（CPython 3.14）其存在与否都不改变 is/== 的判定结果。
    widget = _FakeWidget()
    sentinel = weakref.ref(widget, lambda _r: None)  # 外部带回调弱引用：多引用共存的取证面
    ui_i18n.register(widget, ui_i18n.T("旧文案"))
    ui_i18n.register(widget, ui_i18n.T("新文案"))
    assert sentinel() is widget
    assert ui_i18n.retranslate_all() == 1, "同控件去重失效：登记表随重复登记增长（M-82）"
    assert widget.texts == ["新文案"], "旧文案不得再参与回填"
