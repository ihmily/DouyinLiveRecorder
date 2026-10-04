# -*- coding: utf-8 -*-
# GUI 控件层 i18n 接线设施：Translatable 标记 + 重译登记表。
#
# 为什么需要它：静态标签（按钮 / 卡片标题 / 表头 / 窗口标题）在控件创建时定型，
# 语言热切换（i18n.set_language）只影响之后经 tr() 查表的文案，已建控件的文本不会
# 自动跟随。本模块提供与 Qt retranslateUi 同构的机制——工厂层创建控件时查表翻译
# 并登记 (控件, 应用模式, 标记)，语言切换回调统一 retranslate_all() 回填当前语言值。
#
# 为什么不销毁重建窗口：Tk 下销毁重建会丢日志内容 / URL 编辑器内容 / 监控表格等
# 运行态，且挂在其上的 after 任务句柄会大面积 TclError；登记表回填零状态损失。
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
    # 工厂名取单字母：调用点形态 text=T("开始录制")，保持与原字面量调用同密度。
    return Translatable(msgid, **kwargs)


# 应用模式语义：
#   "text"            → widget.configure(text=...)（Button/Label 等常规文本选项）
#   "title"           → widget.title(...)（Tk 窗口标题是方法不是 configure 选项）
#   "heading:<col_id>" → widget.heading(col_id, text=...)（DataTable 的 Treeview 表头）
_LOCK = threading.Lock()
_ENTRIES: list[tuple["weakref.ref[object]", str, Translatable]] = []


def register(widget: object, mode: str, trans: Translatable) -> None:
    # 登记表持有控件弱引用：Toplevel 窗口随开随关，强引用会泄漏已销毁控件；
    # 同一 (控件, 模式) 重复登记（工厂与调用方都可能登记）以最后一次为准。
    ref = weakref.ref(widget)
    with _LOCK:
        _ENTRIES[:] = [entry for entry in _ENTRIES if not (entry[0] is ref and entry[1] == mode)]
        _ENTRIES.append((ref, mode, trans))


def apply_title(window: object, trans: Translatable) -> None:
    # Tk 窗口标题的接线入口（标题是方法不是 configure 选项）：登记 + 立即按当前语言设置。
    register(window, "title", trans)
    cast("Any", window).title(trans.render())


def registered_count() -> int:
    # 存活登记条数（含未回填状态），供测试与诊断；不做清理——清理只在 retranslate_all 走。
    with _LOCK:
        return sum(1 for entry in _ENTRIES if entry[0]() is not None)


def retranslate_all() -> int:
    # 回填全部存活控件的当前语言值并清理死亡引用；返回实际应用条数（测试判据）。
    # 线程约定：必须在 UI 线程调用（tkinter 非线程安全）。语言切换是菜单事件回调，
    # 天然在 UI 线程；测试用假控件对象亦走同一入口，不依赖真实 Tk。
    with _LOCK:
        snapshot = list(_ENTRIES)
    alive: list[tuple["weakref.ref[object]", str, Translatable]] = []
    applied = 0
    for ref, mode, trans in snapshot:
        widget = ref()
        if widget is None:
            continue
        alive.append((ref, mode, trans))
        value = trans.render()
        if mode == "title":
            # Tk 窗口标题走方法；tk.Wm.title(string=...) 返回值忽略（cast 收敛存根类型）
            cast("Any", widget).title(value)
        elif mode.startswith("heading:"):
            cast("Any", widget).heading(mode.split(":", 1)[1], text=value)
        else:
            cast("Any", widget).configure(**{mode: value})
        applied += 1
    with _LOCK:
        _ENTRIES[:] = alive
    return applied
