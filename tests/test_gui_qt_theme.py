# tests/test_gui_qt_theme.py — PySide6 窗口层设计令牌的契约锁。
#
# 锁：三份主题（浅/深/高对比）覆盖同一键集（漏一份即取到不存在的键而 KeyError）；
# accent/bg 等于设计稿 docs/gui-redesign/index.html 的 :root 取值（视觉事实源漂移即红）；
# QSS 必须带 objectName 选择器（否则会命中布局里所有同类控件）。
# 判据只读 theme 模块的纯数据（palette/build_stylesheet），不需要 QApplication。
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
    # 视觉事实源被删/改名即红：令牌不再「照着设计稿抄」，需重新确认来源。
    from src.gui_qt import DESIGN_SOURCE

    root = pathlib.Path(__file__).resolve().parents[1]
    assert (root / DESIGN_SOURCE).is_file(), f"设计稿缺失: {DESIGN_SOURCE}"


def test_unknown_theme_falls_back_to_light() -> None:
    # 配置里的主题值来自 config.ini，可能被手改成任意值：宁可显示浅色也不能起不来窗口。
    assert theme_module.palette("nonsense").token("accent") == LIGHT_ACCENT


def test_px_scales_with_factor() -> None:
    # 缩放只影响 px() 换算，令牌色值与键集不随缩放变化。
    pal = theme_module.palette(theme_module.THEME_LIGHT, scale=1.5)
    assert pal.px(10) == 15
    assert theme_module.palette(theme_module.THEME_LIGHT, scale=1.0).px(10) == 10


def test_stylesheet_uses_objectname_selectors() -> None:
    # 四个选择器覆盖卡片/导航按钮/侧栏/终端四个具名控件；漏一个就会退化到同类通配。
    sheet = theme_module.build_stylesheet(theme_module.palette(theme_module.THEME_LIGHT))
    for selector in ("QFrame#card", "QPushButton#nav", "QWidget#sidebar", "QTextEdit#terminal"):
        assert selector in sheet, f"QSS 缺选择器 {selector}：样式会命中其它同类控件"


def test_is_dark_only_for_dark_theme() -> None:
    assert theme_module.is_dark(theme_module.THEME_DARK) is True
    assert theme_module.is_dark(theme_module.THEME_LIGHT) is False


def test_palette_token_rejects_unknown_key() -> None:
    with pytest.raises(KeyError):
        theme_module.palette(theme_module.THEME_LIGHT).token("no_such_token")
