# tests/test_gui_language_retranslate.py —— GUI 语言热切换的界面重译回归锁。
#
# 背景：静态标签（ui_kit 工厂 + ui_i18n.T 登记表）在语言切换后必须整体回填。
# 本文件锁住 _on_language_change 的四条行为：
#   ① 调 retranslate_all（登记表回填）；② 哨兵值（默认画质/全部房间）按 tr 后形态重置；
#   ③ 动态面（状态栏/画质/弹幕）刷新与托盘菜单重建被触发；④ language 写回 config.ini。
# 全部经「无头桩实例」（object.__new__ 跳过 __init__，只注入本链路所需属性）——
# 与 tests/test_gui_monitor.py 的桩口径一致，不建真实 Tk 窗口。

import configparser
from pathlib import Path
from typing import Any

import pytest

import gui
import i18n


def _make_stub(tmp_path: Path, calls: list[str]) -> Any:
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


def test_language_change_retranslates_and_resets_sentinels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    app = _make_stub(tmp_path, calls)

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


def test_language_change_triggers_tray_menu_rebuild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    app = _make_stub(tmp_path, calls)

    class _Tray:
        def rebuild_menu(self) -> None:
            calls.append("tray_rebuild")

    setattr(app, "system_tray", _Tray())
    monkeypatch.setattr(gui, "retranslate_all", lambda: 0)
    saved = i18n.get_language()
    try:
        gui.LiveRecorderGUI._on_language_change(app, "English (US)")
    finally:
        i18n.set_language(saved)
    assert "tray_rebuild" in calls, "托盘菜单文本构建期定型，语言切换后必须整体重建"


def test_retranslate_failure_does_not_block_language_writeback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 重译异常不得吞掉 config 写回（两段 try 相互独立）；仅留一条 warn 日志
    calls: list[str] = []
    app = _make_stub(tmp_path, calls)

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
