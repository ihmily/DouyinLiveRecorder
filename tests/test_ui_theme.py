# tests/test_ui_theme.py — GUI 主题偏好层回归锁。
#
# 覆盖 src/ui_theme.py 的两条不变量：
#   1) 主题 id 白名单与窗口层一致（持久化取值必须两套实现都识别）；
#   2) 持久化：[GUI] gui_theme 缺失/非法回退「未设置」，合法值经 update_or_append 行级写回
#      且不破坏既有节与注释；"" 是「清空显式偏好 = 跟随系统」的哨兵。
#
# 颜色 token / QSS / 对比度契约的事实源是 src/gui_qt/theme.py，对应回归锁在
# tests/test_gui_qt_theme.py；本模块不 import 任何 GUI 工具包，全部用例无头可跑。

import configparser
from pathlib import Path

import pytest

from src.ui_theme import (
    GUI_SECTION,
    THEME_IDS,
    load_theme_preference,
    save_theme_preference,
)


def _make_config(tmp_path: Path, body: str) -> Path:
    # 最小合法 config.ini：带 BOM（本仓 config.ini 模板带 UTF-8 BOM，读取侧必须 utf-8-sig）
    cfg = tmp_path / "config.ini"
    cfg.write_text(body, encoding="utf-8-sig")
    return cfg


class TestThemeRegistry:
    def test_theme_id_set(self) -> None:
        # 三套主题是持久化契约的一部分；增删主题须显式改此锁，并同步 src/gui_qt/theme.py
        assert THEME_IDS == ("light", "dark", "high_contrast")


class TestPersistence:
    def test_missing_file_is_unset(self, tmp_path: Path) -> None:
        assert load_theme_preference(tmp_path / "absent.ini") == ""

    def test_missing_section_and_key_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[录制设置]\nlanguage = zh_CN\n")
        assert load_theme_preference(cfg) == ""

    def test_invalid_value_is_unset(self, tmp_path: Path) -> None:
        # 用户手改出未知值（neon）不得被当成主题，回退「未设置」而不是任何默认主题
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = neon\n")
        assert load_theme_preference(cfg) == ""

    def test_valid_value_roundtrip(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[录制设置]\nlanguage = zh_CN\n")
        assert save_theme_preference(cfg, "dark") is True
        assert load_theme_preference(cfg) == "dark"
        assert save_theme_preference(cfg, "high_contrast") is True
        assert load_theme_preference(cfg) == "high_contrast"

    def test_save_creates_gui_section(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[录制设置]\nlanguage = zh_CN\n")
        assert save_theme_preference(cfg, "light") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "[GUI]" in text and "gui_theme = light" in text

    def test_save_preserves_comments_and_sections(self, tmp_path: Path) -> None:
        # update_or_append 的行级承诺：注释与既有节原样保留（画质/语言写回同源口径）
        cfg = _make_config(tmp_path, "# 顶部注释\n[录制设置]\n# 语言键注释\nlanguage = zh_CN\n")
        assert save_theme_preference(cfg, "dark") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "# 顶部注释" in text and "# 语言键注释" in text
        assert "[录制设置]" in text and "language = zh_CN" in text

    def test_save_rejects_unknown_id(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[录制设置]\n")
        with pytest.raises(ValueError):
            save_theme_preference(cfg, "neon")

    def test_save_empty_clears_preference(self, tmp_path: Path) -> None:
        # "" 是「跟随系统 / 清空显式偏好」的哨兵：save 必须接受并落空值，
        # 与 load_theme_preference 返回 ""（未设置）同一口径、与 save_scale_preference
        # 接受 ""（=自动）一致。窗口层选「跟随系统」时走这条路径。
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = dark\n")
        assert save_theme_preference(cfg, "") is True
        # 读侧把空值按「未设置」处理 → 下次启动回退到外观跟随
        assert load_theme_preference(cfg) == ""
        text = cfg.read_text(encoding="utf-8-sig")
        assert "gui_theme =" in text  # 落空值而非删键，保留键名与节顺序

    def test_repeated_save_keeps_single_line(self, tmp_path: Path) -> None:
        # update 优先于 append：重复保存不得堆积重复键（configparser 读到重复 option 抛错）
        cfg = _make_config(tmp_path, "[录制设置]\n")
        for theme_id in ("light", "dark", "light"):
            assert save_theme_preference(cfg, theme_id) is True
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(cfg, encoding="utf-8-sig")
        items = parser.items(GUI_SECTION)
        assert len(items) == 1 and items[0] == ("gui_theme", "light")

    def test_value_case_insensitive_read(self, tmp_path: Path) -> None:
        # 用户手写 "DARK" 也能识别（读侧 strip+lower，与配置键大小写不敏感口径一致）
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = DARK\n")
        assert load_theme_preference(cfg) == "dark"
