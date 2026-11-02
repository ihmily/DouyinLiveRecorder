# tests/test_ui_scale.py — src/ui_scale.py 的回归锁（GUI 缩放档位层）。
#
# 覆盖三条不变量：
#   1) 档位体系：SCALE_PRESETS 递增、不重复、覆盖 100%，且「自动」哨兵不在档位集合内；
#   2) 自动档：小屏降一档、任一维度不足即降档、正常屏取 100%；
#   3) 持久化：[GUI] gui_scale 缺失/非法回退「未设置」，合法值经 update_or_append
#      行级写回且不破坏既有节与注释。
#
# 字号派生 / 窗口几何已随 tkinter legacy GUI 退役删除；窗口尺寸由 Qt 布局系统承担。
# 全部用例无头（不建窗口）——Linux CI 全量执行。

import configparser
from pathlib import Path

from src.ui_scale import (
    AUTO_SCALE_ID,
    AUTO_SCALE_NORMAL,
    AUTO_SCALE_SMALL,
    GUI_SECTION,
    SCALE_KEY,
    SCALE_PRESETS,
    auto_scale_for_screen,
    is_valid_scale,
    load_scale_preference,
    parse_scale,
    save_scale_preference,
)


def _make_config(tmp_path: Path, body: str) -> Path:
    # 最小合法 config.ini：带 BOM（本仓 config.ini 模板带 UTF-8 BOM，读取侧必须 utf-8-sig）
    cfg = tmp_path / "config.ini"
    cfg.write_text(body, encoding="utf-8-sig")
    return cfg


class TestScalePresets:
    # 档位本身是「产品决策」，但有两条硬约束必须机检：递增 + 落在合法渲染区间
    def test_presets_are_increasing(self) -> None:
        assert list(SCALE_PRESETS) == sorted(SCALE_PRESETS)
        assert len(set(SCALE_PRESETS)) == len(SCALE_PRESETS), "档位不得重复"

    def test_presets_cover_100_percent(self) -> None:
        # 100% 必须是一个可选档：否则「恢复默认」在菜单里找不到
        assert 100 in SCALE_PRESETS

    def test_presets_within_readable_range(self) -> None:
        # 下限 85（再小侧栏导航会撞行）、上限 150（再大侧栏两列信息网格会挤成两行）
        assert min(SCALE_PRESETS) >= 85
        assert max(SCALE_PRESETS) <= 150

    def test_auto_sentinel_is_not_a_preset(self) -> None:
        # 「自动」是下拉里的哨兵项，不能被当成真实百分比写回
        assert AUTO_SCALE_ID not in {str(value) for value in SCALE_PRESETS}

    def test_is_valid_scale_only_admits_presets(self) -> None:
        assert is_valid_scale(100) is True
        assert is_valid_scale(70) is False
        assert is_valid_scale(200) is False


class TestAutoScale:
    def test_normal_screen_gets_100(self) -> None:
        assert auto_scale_for_screen(1920, 1080) == AUTO_SCALE_NORMAL

    def test_small_screen_downgrades(self) -> None:
        # 1366x768 装完整布局虽够，但任务栏/标题栏吃掉一部分后很紧
        assert auto_scale_for_screen(1366, 768) == AUTO_SCALE_SMALL

    def test_either_dimension_triggers_downgrade(self) -> None:
        # 只看宽会让竖屏小窗口用户拿到 100% 而横向溢出
        assert auto_scale_for_screen(1920, 700) == AUTO_SCALE_SMALL
        assert auto_scale_for_screen(1200, 1080) == AUTO_SCALE_SMALL

    def test_downgrade_happens_once(self) -> None:
        # 降档只做一次、不递归：避免在临界屏上反复横跳
        once = auto_scale_for_screen(1366, 768)
        assert once == AUTO_SCALE_SMALL
        assert once < AUTO_SCALE_NORMAL


class TestParseScale:
    def test_empty_is_unset(self) -> None:
        assert parse_scale("") == ""
        assert parse_scale("   ") == ""

    def test_valid_percent(self) -> None:
        assert parse_scale("115") == "115"
        assert parse_scale(" 130 ") == "130"

    def test_auto_sentinel(self) -> None:
        assert parse_scale(AUTO_SCALE_ID) == AUTO_SCALE_ID
        assert parse_scale("auto") == AUTO_SCALE_ID

    def test_garbage_is_unset(self) -> None:
        # 配置损坏绝不能让 GUI 起不来
        assert parse_scale("abc") == ""
        assert parse_scale("999") == ""
        assert parse_scale("115%") == ""

    def test_float_form_accepted(self) -> None:
        # 用户手改成 "115.0" 是常见写法，不该被当成垃圾丢掉
        assert parse_scale("115.0") == "115"


class TestPersistence:
    def test_missing_section_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[other]\nkey = value\n")
        assert load_scale_preference(str(cfg)) == ""

    def test_missing_key_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = light\n")
        assert load_scale_preference(str(cfg)) == ""

    def test_valid_value_round_trips(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\n")
        assert save_scale_preference(str(cfg), "130") is True
        assert load_scale_preference(str(cfg)) == "130"

    def test_auto_sentinel_round_trips(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[GUI]\n")
        assert save_scale_preference(str(cfg), AUTO_SCALE_ID) is True
        assert load_scale_preference(str(cfg)) == AUTO_SCALE_ID

    def test_illegal_value_on_disk_is_unset(self, tmp_path: Path) -> None:
        # 损坏的持久化值按「未设置」处理（调用方回落到自动档）
        cfg = _make_config(tmp_path, "[GUI]\ngui_scale = 99999\n")
        assert load_scale_preference(str(cfg)) == ""

    def test_write_preserves_other_keys_and_comments(self, tmp_path: Path) -> None:
        # 行级替换优先：不得整段重写 [GUI]（会把 gui_theme 等键与注释一起抹掉）
        cfg = _make_config(tmp_path, "[GUI]\n# 保留我\ngui_theme = dark\n")
        assert save_scale_preference(str(cfg), "115") is True
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(cfg, encoding="utf-8-sig")
        assert parser.has_section(GUI_SECTION)
        assert parser.get(GUI_SECTION, "gui_theme") == "dark"
        assert parser.get(GUI_SECTION, SCALE_KEY) == "115"
        assert "# 保留我" in cfg.read_text(encoding="utf-8-sig")

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        # 文件不存在时写回失败，调用方告警但不阻断内存态切换（与 gui_theme 同口径）
        assert save_scale_preference(str(tmp_path / "nope.ini"), "115") is False

    def test_corrupt_file_is_unset(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[GUI\nbroken", encoding="utf-8-sig")
        assert load_scale_preference(str(cfg)) == ""
