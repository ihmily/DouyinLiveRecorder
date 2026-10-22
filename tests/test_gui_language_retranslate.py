# tests/test_gui_language_retranslate.py —— GUI 语言热切换的界面重译回归锁。
#
# 背景：静态标签（ui_kit 工厂 + ui_i18n.T 登记表）在语言切换后必须整体回填。
# 本文件锁住 _on_language_change 的四条行为：
#   ① 调 retranslate_all（登记表回填）；② 哨兵值（默认画质/全部房间）按 tr 后形态重置；
#   ③ 动态面（状态栏/画质/弹幕）刷新与托盘菜单重建被触发；④ language 写回 config.ini。
# 全部经「无头桩实例」（object.__new__ 跳过 __init__，只注入本链路所需属性）——
# 与 tests/test_gui_monitor.py 的桩口径一致，不建真实 Tk 窗口。

import ast
import configparser
import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import i18n

# gui.py 的两条导入期副作用（本文件唯一需要隔离的面）：模块级写 os.environ["DLR_GUI_PARENT"]="1"，
# 以及 _fix_encoding() 就地 reconfigure 宿主进程的 stdout/stderr 编码策略。
_GUI_PARENT_ENV = "DLR_GUI_PARENT"


@pytest.fixture(scope="session", autouse=True)
def gui() -> Iterator[ModuleType]:
    # MT-05（2026-10-18 审查）：模块顶层 `import gui` 会让 gui.py 的 os.environ["DLR_GUI_PARENT"]="1"
    # 发生在 pytest **收集期**且永不还原——子集运行时，凡在本文件之后才首次导入 src.logger 的文件都会
    # 整会话进入 GUI 父进程模式（不再创建 streamget.log / PlayURL.log），并随 env 泄入本会话拉起的
    # 每一个子进程（同 tests/test_gui_monitor.py 文件头的定性）。故导入挪进夹具 + 导入完立刻还原标记；
    # src.logger 的归属判定只在导入期读一次，conftest 的 autouse 夹具又早已导入过 src，故不触及
    # reload 形态的用例（tests/test_logger_gui_parent.py 自己逐例 setenv/delenv）。
    # 为什么是**会话级**：gui._fix_encoding() 会就地 reconfigure 宿主 stdio，落在函数级夹具里会被
    # conftest 的 _guard_stdio_encoding_policy（函数级快照）判成「用例改动了宿主编码策略」
    # （2026-10-18 实测 1 error）；会话级夹具跑在任何函数级快照之前，这条副作用因此归位到「导入期」。
    # 还原为什么走 context + setenv 占位而不是 delenv：monkeypatch.delenv 只登记「删除前已存在的值」
    # 并在 undo 时原样写回——恰好是要清掉的 "1"；先 setenv 空串才会登记 NOTSET，让 undo 走 del 分支，
    # 键才真的从进程环境里消失（上游若已污染则按原值还原，不归本文件管）。
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setenv(_GUI_PARENT_ENV, "")
        module = importlib.import_module("gui")
    yield module


def _make_stub(tmp_path: Path, calls: list[str], gui: ModuleType) -> Any:
    # 桩：只注入 _on_language_change 触及的属性/方法；所有可观测行为记进 calls
    app = object.__new__(gui.LiveRecorderGUI)
    cfg = tmp_path / "config.ini"
    cfg.write_text("[录制设置]\nlanguage = zh_CN\n", encoding="utf-8-sig")
    setattr(app, "_language_codes", {"English (US)": "en_US"})
    setattr(app, "main_config_file", str(cfg))
    setattr(app, "_quality_default_label", "STALE-SENTINEL")
    setattr(app, "_danmaku_filter", "STALE-SENTINEL")
    setattr(app, "system_tray", None)
    setattr(app, "_log", lambda message, level="info": calls.append(f"log:{message}"))
    setattr(app, "_refresh_quality_context", lambda: calls.append("quality_ctx"))
    setattr(app, "_update_status_bar", lambda: calls.append("status"))
    setattr(app, "_update_quality_display", lambda: calls.append("quality"))
    setattr(app, "_update_danmaku_display", lambda: calls.append("danmaku"))
    return app


def test_language_change_retranslates_and_resets_sentinels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gui: ModuleType
) -> None:
    calls: list[str] = []
    app = _make_stub(tmp_path, calls, gui)

    # 语言切换回调里必须调 retranslate_all（登记表回填入口）；间谍记录调用并返回计数 0
    def _spy_retranslate() -> int:
        calls.append("retranslate")
        return 0

    monkeypatch.setattr(gui, "retranslate_all", _spy_retranslate)
    saved = i18n.get_language()
    try:
        gui.LiveRecorderGUI._on_language_change(app, "English (US)")
        # 哨兵必须按 tr 后形态重置（关键约定#13）：断言它等于当前目录下 tr(源文) 的返回值、
        # 且已不等于源文——裸字面量赋值（或忘了重置）这两种改法都会让下面的断言转红。
        # 断言在恢复语言之前求值（set_language 重建 _tr，恢复后再算会得到源文）。
        expected_default = i18n.tr("默认画质")
        expected_all_rooms = i18n.tr("全部房间")
        assert expected_default != "默认画质", "替身目录必须已生效（否则本断言的区分力失效）"
        assert app._quality_default_label == expected_default
        assert app._danmaku_filter == expected_all_rooms
    finally:
        i18n.set_language(saved)

    assert "retranslate" in calls, "语言切换必须调 retranslate_all 回填静态标签"
    # 动态面刷新链：画质上下文 + 状态栏 + 画质表 + 弹幕表
    assert {"quality_ctx", "status", "quality", "danmaku"} <= set(calls)
    # 语言写回 config.ini（生效码）
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(app.main_config_file, encoding="utf-8-sig")
    assert cfg["录制设置"]["language"] == "en_US"


# [2026-10-20] 原 test_language_change_triggers_tray_menu_rebuild 已随遗留 pystray 托盘退役删除；
# 「语言切换后托盘菜单文本必须跟着换」由 tests/test_gui_qt_units.py 的托盘四条动作项断言接管
# （Qt 版走 TrayIcon.retranslate()，不整体重建）。本文件剩余用例仍钉在 tkinter 版 LiveRecorderGUI。


def test_retranslate_failure_does_not_block_language_writeback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, gui: ModuleType
) -> None:
    # 重译异常不得吞掉 config 写回（两段 try 相互独立）；仅留一条 warn 日志
    calls: list[str] = []
    app = _make_stub(tmp_path, calls, gui)

    def _boom() -> int:
        raise RuntimeError("retranslate boom")

    monkeypatch.setattr(gui, "retranslate_all", _boom)
    saved = i18n.get_language()
    try:
        gui.LiveRecorderGUI._on_language_change(app, "English (US)")
    finally:
        i18n.set_language(saved)
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(app.main_config_file, encoding="utf-8-sig")
    assert cfg["录制设置"]["language"] == "en_US"
    assert any(str(c).startswith("log:") for c in calls), "重译失败必须留痕（不得静默）"


def test_gui_is_not_imported_at_module_level() -> None:
    # MT-05 的自锁：本文件一旦把 `import gui` 放回模块顶层，那条 os.environ["DLR_GUI_PARENT"]="1"
    # 就又回到 **收集期**（会话级夹具记录的「进入前形态」届时已被写脏，行为面判据反而看不出来），
    # 而三条行为用例对此完全无感——只能由这条 AST 锁当场点名。判据只问「顶层有没有 gui 的 import
    # 语句」这一不变量，不钉任何变量名或文案，改写法（as / from）仍在判据内。
    tree = ast.parse(Path(__file__).resolve().read_text(encoding="utf-8"), filename=str(__file__))
    top_level = [
        node
        for node in tree.body
        if isinstance(node, ast.Import | ast.ImportFrom)
        and any(alias.name.split(".")[0] == "gui" for alias in node.names)
    ]
    assert not top_level, (
        f"本文件模块顶层出现了 gui 的 import（第 {[node.lineno for node in top_level]} 行）："
        "gui.py 会在收集期就把 DLR_GUI_PARENT 写进整个会话（见 gui fixture 的 MT-05 说明），"
        "必须保持「导入只发生在会话级夹具内」"
    )
