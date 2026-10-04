# tests/test_ui_theme.py — 阶段3 GUI 主题层回归锁。
#
# 覆盖 src/ui_theme.py 的四条不变量：
#   1) 注册表完整性：每套主题逐槽给出全部 token，且取值形态严格 #RRGGBB；
#   2) 对比度契约：CONTRAST_REQUIREMENTS 里每个 (前景, 背景) 对在三套主题下都达 WCAG 门槛
#      （正文 4.5 / 非文本与禁用 3.0）——「对比度机检」本体，提案阶段3 的成功判据；
#   3) 持久化：[GUI] gui_theme 缺失/非法回退「未设置」，合法值经 update_or_append 行级写回
#      且不破坏既有节与注释；
#   4) 切换幂等：select 同 id 短路（不产生重复配置行、配置字节不变），apply 重复注册
#      不抛 TclError 且 ttk 主题名稳定。
#
# 无头约束：除 TestApplyTtk 外全部用例不需要显示器，Linux CI 全量执行；
# TestApplyTtk 需要真实 Tk root，无显示环境（ubuntu CI 无 X server）跳过——
# 该用例在本机 Windows（有显示）常态化执行，跳过面只有这一条 Tk 集成用例。
# 判定「主题切换的 ttk 语义」不依赖该集成用例的部分（map 配置构造）在
# TestTtkSettings 里以纯数据断言覆盖，CI 仍然全量锁定。

import configparser
import re
import tkinter as tk
from collections.abc import Generator
from pathlib import Path
from tkinter import ttk
from typing import cast

import pytest

from src.ui_scale import ScaleProfile
from src.ui_theme import (
    CONTRAST_REQUIREMENTS,
    DEFAULT_THEME,
    THEME_IDS,
    THEMES,
    TOKEN_NAMES,
    ThemeManager,
    contrast_ratio,
    is_valid_hex,
    load_theme_preference,
    relative_luminance,
    save_theme_preference,
)


def _make_config(tmp_path: Path, body: str) -> Path:
    # 最小合法 config.ini：带 BOM（本仓 config.ini 模板带 UTF-8 BOM，读取侧必须 utf-8-sig）
    cfg = tmp_path / "config.ini"
    cfg.write_text(body, encoding="utf-8-sig")
    return cfg


class TestContrastMath:
    # WCAG 公式本体：用可手算的锚点值锁实现，防止公式改错后整套机检静默失真。
    def test_black_white_is_21(self) -> None:
        assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)

    def test_same_color_is_1(self) -> None:
        assert contrast_ratio("#4F6DF5", "#4F6DF5") == pytest.approx(1.0)

    def test_ratio_is_symmetric(self) -> None:
        # 前后景互换比值不变（WCAG 定义按较亮/较暗归一，与参数顺序无关）
        assert contrast_ratio("#1E293B", "#FFFFFF") == contrast_ratio("#FFFFFF", "#1E293B")

    def test_known_pair_value(self) -> None:
        # 锚点对：白字压品牌蓝 #4F6DF5 实测 4.34（低于 4.5，正是 light.primary 加深的原因）。
        # 数值固化防止公式实现漂移导致该决策依据失效而不自知。
        assert contrast_ratio("#FFFFFF", "#4F6DF5") == pytest.approx(4.34, abs=0.01)

    def test_relative_luminance_bounds(self) -> None:
        assert relative_luminance("#000000") == pytest.approx(0.0)
        assert relative_luminance("#FFFFFF") == pytest.approx(1.0)

    def test_invalid_hex_rejected(self) -> None:
        assert is_valid_hex("#FFFFFF") is True
        assert is_valid_hex("#FFF") is False
        assert is_valid_hex("FFFFFF") is False
        assert is_valid_hex("#GGGGGG") is False
        with pytest.raises(ValueError):
            relative_luminance("not-a-color")


class TestThemeRegistry:
    def test_theme_id_set(self) -> None:
        # 三套主题是提案假设 #3 的交付面；增删主题须显式改此锁
        assert THEME_IDS == ("light", "dark", "high_contrast")

    def test_every_theme_defines_every_token(self) -> None:
        for theme_id in THEME_IDS:
            tokens = THEMES[theme_id]
            assert set(tokens) == set(TOKEN_NAMES), f"{theme_id} 缺槽/多槽: {set(tokens) ^ set(TOKEN_NAMES)}"

    def test_token_values_are_strict_hex(self) -> None:
        for theme_id in THEME_IDS:
            for name, value in THEMES[theme_id].items():
                assert is_valid_hex(value), f"{theme_id}.{name} = {value!r} 不是 #RRGGBB"

    def test_hover_differs_from_rest(self) -> None:
        # hover 与常态同色则悬停反馈失效（阶段4 控件层的交互前提）
        for theme_id in THEME_IDS:
            tokens = THEMES[theme_id]
            assert tokens["primary_hover"] != tokens["primary"]
            assert tokens["disabled_fg"] != tokens["text"]

    def test_requirements_reference_known_slots(self) -> None:
        for fg, bg, _need in CONTRAST_REQUIREMENTS:
            assert fg in TOKEN_NAMES and bg in TOKEN_NAMES, f"对比度契约引用未知槽位: {fg}/{bg}"

    def test_default_theme_is_registered(self) -> None:
        assert DEFAULT_THEME in THEME_IDS


class TestContrastContract:
    # 提案成功标准「每套主题每个前景/背景 token 对的对比度机检通过」的本体。
    # 参数化逐对报告：CI 输出能直接指出是哪套主题哪个对失守。
    def test_all_pairs_all_themes(self) -> None:
        failures: list[str] = []
        for theme_id in THEME_IDS:
            tokens = THEMES[theme_id]
            for fg, bg, need in CONTRAST_REQUIREMENTS:
                ratio = contrast_ratio(tokens[fg], tokens[bg])
                if ratio < need:
                    failures.append(f"{theme_id}: {fg}({tokens[fg]}) on {bg}({tokens[bg]}) = {ratio:.2f} < {need}")
        assert not failures, "对比度契约失守:\n" + "\n".join(failures)

    def test_text_slots_use_aa_threshold(self) -> None:
        # 防线倒置锁：正文类槽位（text/text_muted/on_primary）对底色的门槛必须是 4.5，
        # 有人把 4.5 降成 3.0 会让机检形同虚设。
        text_slots = {"text", "text_muted", "on_primary"}
        for fg, _bg, need in CONTRAST_REQUIREMENTS:
            if fg in text_slots:
                assert need >= 4.5


class TestPersistence:
    def test_missing_file_is_unset(self, tmp_path: Path) -> None:
        assert load_theme_preference(tmp_path / "absent.ini") == ""

    def test_missing_section_and_key_is_unset(self, tmp_path: Path) -> None:
        cfg = _make_config(tmp_path, "[录制设置]\nlanguage = zh_CN\n")
        assert load_theme_preference(cfg) == ""

    def test_invalid_value_is_unset(self, tmp_path: Path) -> None:
        # 用户手改出未知值（neon）不得被当成主题，回退「未设置」而不是 DEFAULT_THEME
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

    def test_repeated_save_keeps_single_line(self, tmp_path: Path) -> None:
        # update 优先于 append：重复保存不得堆积重复键（configparser 读到重复 option 抛错）
        cfg = _make_config(tmp_path, "[录制设置]\n")
        for theme_id in ("light", "dark", "light"):
            assert save_theme_preference(cfg, theme_id) is True
        parser = configparser.ConfigParser(interpolation=None)
        parser.read(cfg, encoding="utf-8-sig")
        items = parser.items("GUI")
        assert len(items) == 1 and items[0] == ("gui_theme", "light")

    def test_value_case_insensitive_read(self, tmp_path: Path) -> None:
        # 用户手写 "DARK" 也能识别（读侧 strip+lower，与配置键大小写不敏感口径一致）
        cfg = _make_config(tmp_path, "[GUI]\ngui_theme = DARK\n")
        assert load_theme_preference(cfg) == "dark"


class TestSwitchIdempotency:
    def test_select_is_idempotent(self) -> None:
        manager = ThemeManager()
        assert manager.theme_id == DEFAULT_THEME
        assert manager.select("dark") == "dark"
        # 同 id 重复选择：返回值稳定、内部状态不变
        assert manager.select("dark") == "dark"
        assert manager.theme_id == "dark"

    def test_select_switches_and_validates(self) -> None:
        manager = ThemeManager()
        assert manager.select("high_contrast") == "high_contrast"
        assert manager.theme_id == "high_contrast"
        with pytest.raises(ValueError):
            manager.select("neon")
        # 非法选择不得污染内存态
        assert manager.theme_id == "high_contrast"

    def test_repeated_select_keeps_config_byte_identical(self, tmp_path: Path) -> None:
        # 幂等的可观察面：select 同 id + 重复持久化不得改写配置文件字节
        cfg = _make_config(tmp_path, "[录制设置]\n")
        assert save_theme_preference(cfg, "light") is True
        before = cfg.read_bytes()
        manager = ThemeManager()
        manager.select("light")
        assert save_theme_preference(cfg, "light") is True
        assert cfg.read_bytes() == before

    def test_tokens_snapshot_is_defensive_copy(self) -> None:
        manager = ThemeManager()
        manager.select("light")
        tokens = manager.tokens()
        tokens["surface"] = "#010203"
        assert manager.tokens()["surface"] == THEMES["light"]["surface"]


class TestTtkSettings:
    # 纯数据断言（无显示器）：ttk 配置由 token 派生且三态 map 在位——
    # 这是 CI 全量可锁的部分；真机 theme_create/theme_use 见 TestApplyTtk。
    def test_settings_cover_core_elements(self) -> None:
        manager = ThemeManager()
        for theme_id in THEME_IDS:
            manager.select(theme_id)
            settings = manager._build_ttk_settings()
            for element in (".", "TFrame", "TLabel", "TButton", "TEntry", "TCombobox", "Treeview"):
                assert element in settings, f"{theme_id} 缺元素 {element}"

    def test_button_states_map_all_declared(self) -> None:
        # 三态一致（提案诉求 2 的机制性答案）：hover/pressed、disabled 必须显式声明，
        # 缺失即回退到 Tcl 默认灰（正是 CTk 时代「状态表现不一致」的根源）。
        manager = ThemeManager()
        manager.select("dark")
        button_map = cast("dict[str, object]", manager._build_ttk_settings()["TButton"]["map"])
        assert {"background", "foreground", "bordercolor"} <= set(button_map)
        bg_states = {state for state, _value in cast("list[tuple[str, str]]", button_map["background"])}
        assert {"disabled", "pressed", "active"} <= bg_states

    def test_settings_values_come_from_current_tokens(self) -> None:
        manager = ThemeManager()
        manager.select("high_contrast")
        settings = manager._build_ttk_settings()
        tokens = manager.tokens()
        assert settings["TButton"]["configure"]["background"] == tokens["primary"]
        assert settings["TButton"]["configure"]["foreground"] == tokens["on_primary"]
        assert settings["."]["configure"]["background"] == tokens["surface"]

    def test_map_values_match_contract_pairs(self) -> None:
        # map 里上色的组合（常态填充/文字、禁用填充/文字）必须都在对比度契约里按槽位名登记过，
        # 且 map 实际取值等于当前主题对应槽位的值——防止「map 里随手填一对没机检的颜色」。
        registered = {(fg, bg) for fg, bg, _need in CONTRAST_REQUIREMENTS}
        assert ("on_primary", "primary") in registered
        assert ("disabled_fg", "disabled_bg") in registered
        manager = ThemeManager()
        for theme_id in THEME_IDS:
            manager.select(theme_id)
            tokens = THEMES[theme_id]
            settings = manager._build_ttk_settings()
            button_map = cast("dict[str, object]", settings["TButton"]["map"])
            bg_map = dict(cast("list[tuple[str, str]]", button_map["background"]))
            fg_map = dict(cast("list[tuple[str, str]]", button_map["foreground"]))
            assert bg_map["disabled"] == tokens["disabled_bg"]
            assert fg_map["disabled"] == tokens["disabled_fg"]
            assert settings["TButton"]["configure"]["background"] == tokens["primary"]
            assert settings["TButton"]["configure"]["foreground"] == tokens["on_primary"]


class TestApplyTtk:
    # 真实 Tk 集成（有显示环境才执行；无头 CI 跳过，见文件头说明）。
    @pytest.fixture()
    def tk_root(self) -> Generator[tk.Tk, None, None]:
        try:
            root = tk.Tk()
        except tk.TclError as e:
            pytest.skip(f"无显示环境，跳过 Tk 集成用例: {e}")
        root.withdraw()  # 不需要可见窗口，withdraw 掉避免闪烁
        yield root
        root.destroy()

    def test_apply_registers_and_uses_theme(self, tk_root: tk.Tk) -> None:
        manager = ThemeManager()
        manager.select("light")
        name = manager.apply(tk_root)
        style = ttk.Style(tk_root)
        # [阶段6] 主题名带尺寸档位段：theme_create 对同名第二次调用抛 TclError，
        # 换档位必须换名才能拿到新的 padding/rowheight。100% 是默认档位。
        assert name == "dlr-light@100"
        assert name in style.theme_names()
        assert style.theme_use() == name

    def test_apply_is_idempotent_and_switchable(self, tk_root: tk.Tk) -> None:
        manager = ThemeManager()
        manager.select("dark")
        manager.apply(tk_root)
        manager.apply(tk_root)  # 重复注册不得抛 TclError
        style = ttk.Style(tk_root)
        assert sum(1 for n in style.theme_names() if n.startswith("dlr-")) == 1
        manager.select("high_contrast")
        manager.apply(tk_root)
        assert style.theme_use() == "dlr-high_contrast@100"

    def test_scale_change_reregisters_under_new_name(self, tk_root: tk.Tk) -> None:
        # 换档位 ⇒ 换 ttk 主题名（这是 apply 能带上新 padding/rowheight 的唯一机制）。
        # 同时锁住「旧名残留但当前用的是新名」：Tk 不回收旧主题，测试只关心 theme_use。
        manager = ThemeManager()
        manager.select("light")
        base = manager.apply(tk_root)
        style = ttk.Style(tk_root)
        manager.set_scale(ScaleProfile(150))
        scaled = manager.apply(tk_root)
        assert scaled == "dlr-light@150"
        assert scaled != base
        assert style.theme_use() == scaled
        # 150% 档的行高必须严格大于 100% 档（否则缩放对表格无效）。
        # 读数走「切回该主题再 lookup 当前主题口径」——ttk 的 lookup 只认当前主题，
        # 拿主题名当 style 参数传会报 Invalid state name。
        style.theme_use(base)
        base_row = int(str(style.lookup("Treeview", "rowheight")))
        style.theme_use(scaled)
        assert int(str(style.lookup("Treeview", "rowheight"))) > base_row

    def test_button_colors_reach_ttk(self, tk_root: tk.Tk) -> None:
        # 端到端最小验证：token 经 theme_create 真正落到 ttk 查询口径
        manager = ThemeManager()
        manager.select("light")
        manager.apply(tk_root)
        style = ttk.Style(tk_root)
        tokens = THEMES["light"]
        assert re.match(r"^#[0-9A-Fa-f]{6}$", str(style.lookup("TButton", "background")) or "")
        assert str(style.lookup("TButton", "background")).upper() == tokens["primary"].upper()
