# tests/test_ui_scale.py — src/ui_scale.py 的回归锁（阶段6 GUI 度量层）。
#
# 覆盖四条不变量：
#   1) 档位体系：SCALE_PRESETS 递增、每档在合法区间内；ScaleProfile 对非法输入夹取；
#   2) 字号体系：TYPE_SCALE 每档**负数点值**（正数像素不随 DPI 缩放，是本仓的 bug 形态）、
#      相邻档位单调递增、缩放后单调不减、未知 token 抛 KeyError（不静默给默认值）；
#   3) 尺寸 clamp：窗口四值不得超过屏幕可用区（低分辨率屏的核心诉求），
#      minsize 不得大于 geometry（否则 Tk 会把窗口撑到 minsize，用户看到的第一眼
#      尺寸就不是我们算的那个）；屏幕尺寸不可得时不做 clamp 但也不崩；
#   4) 持久化：[GUI] gui_scale 缺失/非法回退「未设置」，合法值经 update_or_append
#      行级写回且不破坏既有节与注释。
#
# 全部用例无头（不建 Tk 窗口）——Linux CI 全量执行。

import configparser
from pathlib import Path

import pytest

from src.ui_scale import (
    AUTO_SCALE_ID,
    AUTO_SCALE_NORMAL,
    AUTO_SCALE_SMALL,
    GUI_SECTION,
    SCALE_KEY,
    SCALE_PRESETS,
    SPACING,
    TREE_ROW_HEIGHT,
    TREE_ROW_HEIGHT_MIN,
    TYPE_SCALE,
    ScaleProfile,
    auto_scale_for_screen,
    clamp_scale,
    is_valid_scale,
    load_scale_preference,
    parse_scale,
    save_scale_preference,
)


def _make_config(tmp_path: Path, body: str) -> Path:
    # 最小合法 config.ini：带 BOM（本仓config.ini 模板带 UTF-8 BOM，读取侧必须 utf-8-sig）
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
        # 下限 85（再小导航 10 字会撞行）、上限 150（再大侧栏两列信息网格会挤成两行）
        assert min(SCALE_PRESETS) >= 85
        assert max(SCALE_PRESETS) <= 150

    def test_every_preset_builds_profile(self) -> None:
        for percent in SCALE_PRESETS:
            assert ScaleProfile(percent).percent == percent


class TestClamp:
    def test_in_range_unchanged(self) -> None:
        assert clamp_scale(100) == 100
        assert clamp_scale(150) == 150

    def test_out_of_range_clamped(self) -> None:
        # 用户手改config.ini 可能写入 5或 5000；不夹会得到不可读界面或撑爆布局
        assert clamp_scale(5) == 70
        assert clamp_scale(5000) == 200
        assert clamp_scale(-100) == 70

    def test_profile_clamps_on_construction(self) -> None:
        # 构造出的对象必须永远合法，下游的 pt()/px() 不必各自防守
        assert ScaleProfile(9999).percent == 200
        assert ScaleProfile(-5).percent == 70

    def test_is_valid_scale_only_admits_presets(self) -> None:
        assert is_valid_scale(100) is True
        # 70/200 是 clamp 的应急区间，可用于渲染但**不出现在菜单里**
        assert is_valid_scale(70) is False
        assert is_valid_scale(200) is False


class TestTypeScale:
    # 字号体系的核心机检：必须是负数点值
    def test_all_tokens_declared(self) -> None:
        # 这几档是 gui.Fonts 的具名方法的唯一来源，缺一个就有调用点拿不到字号
        for token in ("caption", "body", "label", "stat", "heading", "title", "display", "mono"):
            assert token in TYPE_SCALE, f"缺字号档: {token}"

    def test_sizes_are_strictly_negative(self) -> None:
        # 正数是屏幕像素、不随 tk scaling 跨 DPI 缩放——本仓视之为 bug 形态。
        # 数值固化防止有人「顺手改成正数试试」。
        for token, value in TYPE_SCALE.items():
            assert value > 0, f"{token} 的基准值应为正的点值，符号由 pt() 统一加负号"

    def test_pt_returns_negative(self) -> None:
        profile = ScaleProfile(100)
        for token in TYPE_SCALE:
            if token == "mono":
                continue  # mono 有独立的 mono_pt()
            assert profile.pt(token) < 0, f"{token} 必须产出负数点值"

    def test_pt_is_monotonic_across_tokens(self) -> None:
        # 层级必须严格递增，否则「辅助文字比正文大」这种倒挂会静默发生
        profile = ScaleProfile(100)
        ordered = ["caption", "label", "body", "heading", "stat", "title", "display"]
        sizes = [abs(profile.pt(t)) for t in ordered]
        assert sizes == sorted(sizes)
        assert len(set(sizes)) == len(sizes), f"档位字号必须互不相同，实际: {sizes}"

    def test_caption_not_smaller_than_10pt_at_100(self) -> None:
        # 辅助文字是全窗最小的字；低于 10pt 在 1080p笔记本上就开始糊
        assert abs(ScaleProfile(100).pt("caption")) >= 10

    def test_unknown_token_raises(self) -> None:
        # 静默给默认值会把「拼错的token」藏成「某处字号莫名不对」
        with pytest.raises(KeyError):
            ScaleProfile(100).pt("no-such-token")

    def test_unknown_spacing_raises(self) -> None:
        with pytest.raises(KeyError):
            ScaleProfile(100).spacing("no-such-token")

    def test_spacing_covers_defined_tokens(self) -> None:
        for token in SPACING:
            assert ScaleProfile(100).spacing(token) > 0

    def test_mono_pt_scales_gently(self) -> None:
        # 等宽字随缩放放大（不放大就等于「等宽不缩放」，与比例字体不同步），
        # 但因基准乘了 MONO_SCALE_FACTOR 而**始终小于同档正文**——等宽字符变宽
        # 会让一行能装的列数骤减（日志/URL 编辑器是逐行阅读场景）。
        for percent in SCALE_PRESETS:
            profile = ScaleProfile(percent)
            assert abs(profile.mono_pt()) < abs(profile.pt("body")), f"{percent}% 档等宽未小于正文"
        big = abs(ScaleProfile(150).mono_pt())
        base = abs(ScaleProfile(100).mono_pt())
        assert big > base, "等宽字号也必须随缩放变大"


class TestScaleGrowth:
    # 缩放的单调性：档位越高，字号与间距都不得变小
    def test_pt_never_shrinks_with_scale(self) -> None:
        previous = 0
        for percent in SCALE_PRESETS:
            size = abs(ScaleProfile(percent).pt("body"))
            assert size >= previous, f"{percent}% 档的正文比上一档更小"
            previous = size

    def test_px_never_shrinks_with_scale(self) -> None:
        previous = 0
        for percent in SCALE_PRESETS:
            value = ScaleProfile(percent).px(16)
            assert value >= previous
            previous = value

    def test_px_at_least_one(self) -> None:
        # 4px * 0.85 舍入会得 3；更极端的输入（如 px(1)）不得归零
        assert ScaleProfile(85).px(4) >= 1
        assert ScaleProfile(70).px(1) >= 1

    def test_row_height_has_floor(self) -> None:
        # 行高下限存在的理由：85% 档下 32*0.85=27px，单行文字上下缘贴边、行间无分隔感
        assert ScaleProfile(85).row_height() == TREE_ROW_HEIGHT_MIN
        assert ScaleProfile(150).row_height() > TREE_ROW_HEIGHT
        # 每一档都不得低于下限
        for percent in SCALE_PRESETS:
            assert ScaleProfile(percent).row_height() >= TREE_ROW_HEIGHT_MIN

    def test_padding_scales_both_axes(self) -> None:
        base = ScaleProfile(100).padding((12, 7))
        big = ScaleProfile(150).padding((12, 7))
        assert big[0] > base[0]
        assert big[1] > base[1]


class TestWindowClamp:
    # 低分辨率屏的核心诉求：放大不得把窗口开出屏幕
    def test_fits_small_screen(self) -> None:
        # 150% 档在 1366x768 上必须被压回屏幕内
        width, height, min_w, min_h = ScaleProfile(150).window_size(1366, 768)
        assert width <= 1366
        assert height <= 768
        assert min_w <= width
        assert min_h <= height

    def test_minsize_never_exceeds_geometry(self) -> None:
        # minsize > geometry 时 Tk 会把窗口撑到 minsize，用户第一眼看到的尺寸
        # 就不是我们算的那个（表现为「明明设了 1120x740，开出来却更大」）
        for percent in SCALE_PRESETS:
            _w, _h, min_w, min_h = ScaleProfile(percent).window_size(1280, 720)
            assert min_w <= ScaleProfile(percent).px(1120)
            assert min_h <= ScaleProfile(percent).px(740)
            # 小屏上clamp 后仍须自洽
            _w2, _h2, min_w2, min_h2 = ScaleProfile(percent).window_size(1280, 720)
            assert min_w2 <= _w2 and min_h2 <= _h2

    def test_large_screen_gets_full_size(self) -> None:
        # 4K 屏上不该被 clamp：100% 档就是 1120x740
        width, height, _min_w, _min_h = ScaleProfile(100).window_size(3840, 2160)
        assert width == 1120
        assert height == 740

    def test_unknown_screen_size_does_not_crash(self) -> None:
        # 无头/异常环境读不到屏幕尺寸：宁可能开大一点，也不要因为探测失败就拒绝启动
        width, height, min_w, min_h = ScaleProfile(100).window_size(0, 0)
        assert width == 1120 and height == 740
        assert min_w == 920 and min_h == 620

    def test_sidebar_scales(self) -> None:
        assert ScaleProfile(150).sidebar_width() > ScaleProfile(100).sidebar_width()
        assert ScaleProfile(85).sidebar_width() < ScaleProfile(100).sidebar_width()


class TestAutoScale:
    def test_normal_screen_gets_100(self) -> None:
        assert auto_scale_for_screen(1920, 1080) == AUTO_SCALE_NORMAL

    def test_small_screen_downgrades(self) -> None:
        # 1366x768 装1120x740 虽够，但浏览器/任务栏吃掉一部分后很紧
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
        cfg = _make_config(
            tmp_path,
            "[GUI]\n# 保留我\n gui_theme = dark\n" if False else "[GUI]\n# 保留我\ngui_theme = dark\n",
        )
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
