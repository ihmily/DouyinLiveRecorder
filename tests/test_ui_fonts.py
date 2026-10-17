# tests/test_ui_fonts.py — GUI 自选字体的回归锁（2026-10-17 新增）。
#
# 覆盖三件事：
#   ① SFNT name 表解析 —— 自己按字节规则读，UVT 容错的边界（坏文件要有确定性答案）；
#   ② 偏好读写 —— 经 src/web_config.update_or_append_config_line，与 ui_theme/ui_scale 同口径；
#   ③ 「可用性」判据 —— 这里最容易出错：Tk 的 families() 只枚举注册表里已安装的字体，
#      私有注册的自定义字体不在其中，缺字体时又静默回退（见 ui_fonts.family_resolves
#      的注释）。本文件的断言钉住「拿 Tk 解析结果和人造缺失族名做对照」这条唯一判据。
#
# 真机面（真实 Windows 字体文件 + 私有注册热应用）需要系统字体与 GDI，缺任一即 skip；
# 纯函数面无头可跑，Linux CI 也会执行（不留跳过口子）。

import struct
from pathlib import Path
from typing import Any

import pytest

from src import ui_fonts

_PROBE_FAMILY = "__dlr_missing_family_probe__"


def _build_sfnt(family: str, *, platform_lang_pairs: tuple[tuple[int, int], ...] = ((3, 1033),)) -> bytes:
    # 拼一个只含 name 表的最小 SFNT：只要能驱动被测解析器，不必是真能渲染的字体。
    records = b""
    strings = b""
    for platform_id, lang_id in platform_lang_pairs:
        raw = family.encode("utf-16-be")
        offset = len(strings)
        strings += raw
        records += struct.pack(">HHHHHH", platform_id, 1, lang_id, 1, len(raw), offset)
    name_table = struct.pack(">HHH", 0, len(platform_lang_pairs), 6 + 12 * len(platform_lang_pairs)) + records + strings
    head = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
    # 表目录项：(tag, checksum, offset, length)
    entry = b"name" + struct.pack(">III", 0, 12 + 16, len(name_table))
    return head + entry + name_table


class TestSfntFamilyName:
    # name 表是本模块唯一的信息来源：注册私有字体后 Tk 只认 family 名，名字读错
    # （读到 subfamily、或读不到）会让下拉里出现「Regular」这种样式名，或者直接选了不生效。
    # 这里的用例因此按「解析出了什么名字」逐一钉死。

    def test_reads_family_from_name_table(self, tmp_path: Path) -> None:
        path = tmp_path / "sample.ttf"
        path.write_bytes(_build_sfnt("Noto Sans CJK SC"))
        assert ui_fonts.sfnt_family_name(path) == "Noto Sans CJK SC"

    def test_prefers_family_over_style_records(self, tmp_path: Path) -> None:
        # nameID 1 = family、2 = subfamily：只有 nameID 1 能被采用（选错会让 UI 用样式名当下拉值）
        records = b""
        strings = b""
        for name_id, text in ((1, "SimHei"), (2, "Regular")):
            raw = text.encode("utf-16-be")
            records += struct.pack(">HHHHHH", 3, 1, 1033, name_id, len(raw), len(strings))
            strings += raw
        name_table = struct.pack(">HHH", 0, 2, 6 + 24) + records + strings
        head = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
        entry = b"name" + struct.pack(">III", 0, 28, len(name_table))
        path = tmp_path / "two_records.ttf"
        path.write_bytes(head + entry + name_table)
        assert ui_fonts.sfnt_family_name(path) == "SimHei"

    def test_bad_input_is_none_not_exception(self, tmp_path: Path) -> None:
        # 三条坏输入（文件不存在 / 非字体 / 空文件）都必须返回 None 而不是抛异常：
        # 调用面是「用户随便选了一个文件」的 GUI 路径，异常会中断整个导入流程，
        # 而 None 能让上层给出可读原因。权限问题同理，统一降级为 None。
        assert ui_fonts.sfnt_family_name(tmp_path / "gone.ttf") is None
        junk = tmp_path / "junk.ttf"
        junk.write_bytes(b"not a font at all")
        assert ui_fonts.sfnt_family_name(junk) is None
        empty = tmp_path / "empty.ttf"
        empty.write_bytes(b"")
        assert ui_fonts.sfnt_family_name(empty) is None

    def test_ttc_container_takes_first_font(self, tmp_path: Path) -> None:
        # .ttc 是「一个文件装多款字体」的集合：各字体的表偏移相对它自己的目录起算，
        # 按文件偏移去读会读到目录本身。取第一款是刻意的——GUI 没有「选第几款」的入口，
        # 而集合文件通常整套使用。
        inner = _build_sfnt("First Face")
        offset = 12 + 4
        data = b"ttcf" + struct.pack(">HHI", 1, 0, 1) + struct.pack(">I", offset) + inner
        path = tmp_path / "collection.ttc"
        path.write_bytes(data)
        assert ui_fonts.sfnt_family_name(path) == "First Face"

    def test_missing_name_table_returns_none(self, tmp_path: Path) -> None:
        # 脱壳/子集化字体常砍掉 name 表：拿不到名字就返回 None 由上层提示，而不是拿文件名
        # 当族名——文件名与 GDI 认可的族名毫无关系，那正是「选了没反应」的一半来源。
        head = b"\x00\x01\x00\x00" + struct.pack(">HHHH", 1, 0, 0, 0)
        entry = b"post" + struct.pack(">III", 0, 28, 4)
        path = tmp_path / "no_name.ttf"
        path.write_bytes(head + entry + b"\x00\x00\x00\x00")
        assert ui_fonts.sfnt_family_name(path) is None


class TestPreferenceIO:
    # 偏好读写必须经行级更新：config.ini 里与用户手写注释、相邻键共存，整文件覆写会把
    # 注释冲掉。这是本仓对配置文件的一致口径，字体这条新偏好不得例外。

    def test_roundtrip_family(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("# 注释要保留\r\n\r\n[GUI]\r\ngui_theme = light\r\n", encoding="utf-8", newline="\r\n")
        assert ui_fonts.load_font_preference(cfg) == ""
        assert ui_fonts.save_font_preference(cfg, "KaiTi") is True
        assert ui_fonts.load_font_preference(cfg) == "KaiTi"
        # 行级更新：原有注释与相邻键不得被重写掉
        text = cfg.read_text(encoding="utf-8")
        assert "# 注释要保留" in text
        assert "gui_theme = light" in text

    def test_roundtrip_file_and_clear(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[GUI]\r\n", encoding="utf-8", newline="\r\n")
        ui_fonts.save_font_preference(cfg, "", str(tmp_path / "x.ttf"))
        assert ui_fonts.load_font_preference(cfg) == ""
        assert ui_fonts.load_font_file_preference(cfg) == str(tmp_path / "x.ttf")

    def test_unreadable_config_is_empty_not_error(self, tmp_path: Path) -> None:
        # 配置损坏（含 UTF-8 解码失败）时按「没有偏好」处理：GUI 必须在任何配置形态下
        # 都能起来，起不来比用了默认字体严重得多。UI 层面的容错只认这一条。
        broken = tmp_path / "broken.ini"
        broken.write_bytes(b"\xff\xfe\x00garbage")
        assert ui_fonts.load_font_preference(broken) == ""
        assert ui_fonts.load_font_file_preference(broken) == ""


class TestAvailability:
    def test_presets_filtered_by_installed_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ui_fonts, "_installed_families", lambda root=None: frozenset({"SimSun", "Arial"}))
        names = ui_fonts.available_preset_families()
        # 每组只取第一个命中项：Rep 一个组出现两次（用户面对两个几乎同名的选项是噪声）
        assert names == ["SimSun", "Arial"]

    def test_presets_empty_when_enumeration_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ui_fonts, "_installed_families", lambda root=None: frozenset())
        assert ui_fonts.available_preset_families() == []

    def test_family_available_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ui_fonts, "_installed_families", lambda root=None: frozenset({"Segoe UI"}))
        assert ui_fonts.is_family_available("segoe ui") is True
        assert ui_fonts.is_family_available("Consolas") is False
        assert ui_fonts.is_family_available("") is False

    def test_family_resolves_compares_against_missing_probe(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判据本体：私有字体不在 families() 里但确实能用。这里替身 tkfont.Font，
        # 让它对任何名字都返回兜底族，只有我们「注册过的」名字返回自己的族名。
        seen: list[str] = []

        class _FakeFont:
            def __init__(self, root: Any = None, family: str = "", **_kwargs: Any) -> None:
                seen.append(family)
                self._family = family if family == "PrivateOne" else "FallbackUI"

            def actual(self) -> dict[str, Any]:
                return {"family": self._family}

        monkeypatch.setattr(ui_fonts.tkfont, "Font", _FakeFont)
        assert ui_fonts.family_resolves("PrivateOne") is True
        assert ui_fonts.family_resolves("NotInstalled") is False
        # 对照名字必须是那条人造缺失族名（换名字就失去「同口径兜底」的意义）
        assert ui_fonts._MISSING_FAMILY_PROBE in seen

    def test_family_resolves_swallows_tk_errors(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**_kwargs: Any) -> None:
            raise RuntimeError("bad display")

        monkeypatch.setattr(ui_fonts.tkfont, "Font", boom)
        assert ui_fonts.family_resolves("Anything") is False


class TestInstallAndRegister:
    # 导入链路的两道闸：格式过滤要给「为什么不行」而不是「导入成功但没变化」；
    # 落地复制要保证用户删掉原文件后下次启动还能用（否则观感就是掉了配置的 bug）。

    def test_unsupported_suffix_rejected(self, tmp_path: Path) -> None:
        src = tmp_path / "x.woff2"
        src.write_bytes(b"wOF2" + b"\x00" * 32)
        assert ui_fonts.install_font_file(src, tmp_path / "app") is None

    def test_supported_file_copied_into_store(self, tmp_path: Path) -> None:
        # 存进 config/fonts 而不是引用原路径：用户导完就删除源文件是常态，
        # 引用会造成「下次启动回落默认字体」，看起来像偏好被无故丢弃。
        src = tmp_path / "custom.ttf"
        src.write_bytes(_build_sfnt("Custom Face"))
        target = ui_fonts.install_font_file(src, tmp_path / "app")
        assert target is not None
        assert target.exists()
        assert target.parent.name == ui_fonts.FONT_STORE_DIRNAME
        # 原文件仍可读（复制语义），且解析出的 family 与源文件一致
        assert ui_fonts.sfnt_family_name(target) == "Custom Face"

    def test_filename_is_sanitized(self, tmp_path: Path) -> None:
        # 文件名来自用户的任意目录，可能带 Windows 非法字符或保留设备名；
        # 清洗后拼接才能保证复制在冻结 exe 与 cp936 控制台下都不炸。
        src = tmp_path / "font:with|weird*chars?.ttf"
        src.write_bytes(_build_sfnt("Weird"))
        target = ui_fonts.install_font_file(src, tmp_path / "app")
        assert target is not None
        assert ":" not in target.name and "|" not in target.name and "*" not in target.name

    def test_register_rejects_non_sfnt(self, tmp_path: Path) -> None:
        bad = tmp_path / "fake.ttf"
        bad.write_bytes(b"junk")
        assert ui_fonts.register_private_font(bad) is None

    def test_register_skips_already_installed_family(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        src = tmp_path / "in.ttf"
        src.write_bytes(_build_sfnt("SimSun"))
        monkeypatch.setattr(ui_fonts, "_installed_families", lambda root=None: frozenset({"SimSun"}))

        def _must_not_be_called(path: Any) -> str | None:  # pragma: no cover - 被调用即失败
            raise AssertionError("已安装字体不得再走 GDI 注册")

        monkeypatch.setattr(ui_fonts, "_get_gdi32", _must_not_be_called)
        assert ui_fonts.register_private_font(src) == "SimSun"

    @pytest.mark.skipif(
        not (Path(r"C:\Windows\Fonts\simhei.ttf").exists() or Path(r"C:\Windows\Fonts\simkai.ttf").exists()),
        reason="需要本机有一款 ttf 字体文件做真机验证",
    )
    def test_real_system_font_file_parses(self) -> None:
        # 真文件锁：解析器不能只认自己拼出来的样本
        for candidate in (r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simkai.ttf"):
            path = Path(candidate)
            if not path.exists():
                continue
            assert ui_fonts.sfnt_family_name(path), f"解析失败: {candidate}"
            break
