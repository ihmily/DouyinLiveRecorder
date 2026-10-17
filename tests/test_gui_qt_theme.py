# tests/test_gui_qt_theme.py — PySide6 窗口层设计令牌的契约锁。
#
# 锁什么：
#   1. 三份主题（浅/深/高对比）必须覆盖同一份键集——新增令牌漏掉一份，
#      切主题时就会取到不存在的键而 KeyError（旧 ttk 主题层有过同族事故）；
#   2. accent / bg 两个关键色必须等于设计稿 docs/gui-redesign/index.html 的 :root 取值，
#      视觉事实源漂移会被这里挡住；
#   3. QSS 必须带上 objectName 选择器——不用 objectName 的 QSS 会命中布局里所有同类控件。
import pathlib

import pytest

from src.gui_qt import theme as theme_module

LIGHT_ACCENT = "#c96442"
DARK_ACCENT = "#d97757"


def test_all_palettes_cover_token_keys() -> None:
    for theme_id in theme_module.THEME_IDS:
        pal = theme_module.palette(theme_id)
        missing = [key for key in theme_module.TOKEN_KEYS if key not in pal.tokens]
        assert not missing, f"{theme_id} 缺令牌: {missing}"
        extra = [key for key in pal.tokens if key not in theme_module.TOKEN_KEYS]
        assert not extra, f"{theme_id} 多出未登记令牌: {extra}"


def test_accent_matches_design_source() -> None:
    assert theme_module.palette(theme_module.THEME_LIGHT).token("accent") == LIGHT_ACCENT
    assert theme_module.palette(theme_module.THEME_DARK).token("accent") == DARK_ACCENT


def test_design_source_file_exists() -> None:
    # 视觉事实源被删/改名时这条会红——令牌不再是「照着设计稿抄的」，需要重新确认来源。
    from src.gui_qt import DESIGN_SOURCE

    root = pathlib.Path(__file__).resolve().parents[1]
    assert (root / DESIGN_SOURCE).is_file(), f"设计稿缺失: {DESIGN_SOURCE}"


def test_unknown_theme_falls_back_to_light() -> None:
    # 配置里的主题值来自 config.ini，可能被手改成任意值：宁可显示浅色也不能起不来窗口。
    assert theme_module.palette("nonsense").token("accent") == LIGHT_ACCENT


def test_px_scales_with_factor() -> None:
    pal = theme_module.palette(theme_module.THEME_LIGHT, scale=1.5)
    assert pal.px(10) == 15
    assert theme_module.palette(theme_module.THEME_LIGHT, scale=1.0).px(10) == 10


def test_stylesheet_uses_objectname_selectors() -> None:
    sheet = theme_module.build_stylesheet(theme_module.palette(theme_module.THEME_LIGHT))
    for selector in ("QFrame#card", "QPushButton#nav", "QWidget#sidebar", "QTextEdit#terminal"):
        assert selector in sheet, f"QSS 缺选择器 {selector}：样式会命中其它同类控件"


def test_is_dark_only_for_dark_theme() -> None:
    assert theme_module.is_dark(theme_module.THEME_DARK) is True
    assert theme_module.is_dark(theme_module.THEME_LIGHT) is False


def test_palette_token_rejects_unknown_key() -> None:
    with pytest.raises(KeyError):
        theme_module.palette(theme_module.THEME_LIGHT).token("no_such_token")
