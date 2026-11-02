# -*- coding: utf-8 -*-
# GUI 静态文本 i18n 接线设施：Translatable 标记 + 重译登记表。
#
# 为什么需要它：静态标签（按钮 / 卡片标题 / 窗口标题）在控件创建时定型，
# 语言热切换（i18n.set_language）只影响之后经 tr() 查表的文案，已建控件的文本不会
# 自动跟随。本模块提供与 Qt retranslateUi 同构的机制——创建控件时查表翻译并登记
# (控件, 标记)，语言切换回调统一 retranslate_all() 回填当前语言值。
#
# 为什么不销毁重建窗口：销毁重建会丢日志内容 / URL 编辑器内容 / 监控表格等运行态，
# 登记表回填零状态损失。
#
# 适用边界：只有「构建期定型、生命周期跨语言切换」的控件文本才走 T() 登记；
# 事件时文案（日志行 / 提示条 / HTTP detail / 表格行内状态 token）在产生点直接
# i18n.tr() 即可，下次产生自然是新语言，不进登记表。

import threading
import weakref
from typing import Any, cast

import i18n


# 标记类：携带 msgid 与插值实参，工厂据此「建时翻译 + 登记重译」。
# 刻意不继承 str——避免被当成普通文本透传后漏登记；类型不匹配会在工厂判定处显式分流。
class Translatable:
    __slots__ = ("msgid", "kwargs")

    def __init__(self, msgid: str, **kwargs: object) -> None:
        self.msgid = msgid
        self.kwargs = kwargs

    # 每次渲染都查当前目录：目录缺失时 i18n.tr 回退原文，zh_CN 恒等，不会抛错。
    def render(self) -> str:
        return i18n.tr(self.msgid, **self.kwargs)


def T(msgid: str, **kwargs: object) -> Translatable:
    # 工厂名取单字母：调用点形态 set_text(btn, T("开始录制"))，保持与原字面量调用同密度。
    return Translatable(msgid, **kwargs)


_LOCK = threading.Lock()
_ENTRIES: list[tuple["weakref.ref[object]", Translatable]] = []


def register(widget: object, trans: Translatable) -> None:
    # 登记表持有控件弱引用：窗口随开随关，强引用会泄漏已销毁控件；
    # 同一控件重复登记（工厂与调用方都可能登记）以最后一次为准。
    ref = weakref.ref(widget)
    with _LOCK:
        # M-82（2026-10-21）：去重判定 `entry[0] is ref` 改为 `==`。先更正审查断言：
        # 「新 weakref 对象使 is 恒假」在 CPython 上**不成立**——3.14 实测对同一 referent 的
        # 无回调 ref() 恒返回同一个规范化对象（即便中途存在带回调的其他弱引用，见
        # tests/test_ui_i18n.py 的哨兵用例），所以旧写法在本解释器上碰巧能去重。
        # 但那是 CPython 的实现细节，weakref 文档只承诺「referent 皆存活时 == 相等、
        # 已死则互不相等」：换独立实现（PyPy 等）、ref 类型被子类化、或未来解释器取消
        # 规范化复用，`is` 形态的去重就会**静默失效**——登记表随重复登记无界增长、
        # retranslate_all 对同一控件重复回填。`==` 把契约钉回文档保证的形态，
        # 「同一控件以最后一次为准」的原语义不变。
        _ENTRIES[:] = [entry for entry in _ENTRIES if entry[0] != ref]
        _ENTRIES.append((ref, trans))


# Qt 文本接线入口：登记 + 立即按当前语言设置。
def set_text(widget: object, trans: Translatable) -> None:
    register(widget, trans)
    cast("Any", widget).setText(trans.render())


def registered_count() -> int:
    # 存活登记条数（含未回填状态），供测试与诊断；不做清理——清理只在 retranslate_all 走。
    with _LOCK:
        return sum(1 for entry in _ENTRIES if entry[0]() is not None)


def retranslate_all() -> int:
    # 回填全部存活控件的当前语言值并清理死亡引用；返回实际应用条数（测试判据）。
    # 线程约定：必须在 UI 线程调用（Qt 控件有线程亲和性）。语言切换是菜单事件回调，
    # 天然在 UI 线程；测试用假控件对象亦走同一入口，不依赖真实窗口。
    with _LOCK:
        snapshot = list(_ENTRIES)
    alive: list[tuple["weakref.ref[object]", Translatable]] = []
    applied = 0
    for ref, trans in snapshot:
        widget = ref()
        if widget is None:
            continue
        try:
            cast("Any", widget).setText(trans.render())
        except RuntimeError:
            # Qt 的控件被 C++ 侧销毁后，Python 包装对象**仍然存活**（弱引用不会失效），
            # 任何属性访问都抛 RuntimeError("Internal C++ object already deleted")。
            # 不接住这个异常，一条死条目就会让整轮回填在半途崩掉，剩下的控件全都停在
            # 旧语言上（表现为「切完语言一半没变」）。判定为死条目并剔除。
            continue
        alive.append((ref, trans))
        applied += 1
    with _LOCK:
        _ENTRIES[:] = alive
    return applied
