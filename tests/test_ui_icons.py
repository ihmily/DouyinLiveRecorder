# -*- coding: utf-8 -*-
# tests/test_ui_icons.py — 图标（ICO）解析、校验、落盘与生效优先级的回归锁。
#
# 覆盖四件事：
#   ① ICO 头解析 —— 纯字节规则，坏文件必须有**确定性答案**（返回 None，绝不抛异常）：
#      图标是装饰性资源，解析期异常一旦穿透就是「换图标把程序搞崩」；
#   ② 分辨率准入 —— 16 是硬门槛（托盘按 16px 取样，缺则糊）、256 只提示（缺则放大发虚）。
#      两档混为一谈的后果是要么错杀合法图标，要么放任一个模糊托盘；
#   ③ 落盘与路径 —— 副本必须进 config/icons/（引用原路径会在用户删源文件后静默回落），
#      文件名清洗与字体同口径，相对路径按 app_root 解析；
#   ④ 生效优先级 —— 导入 > 内置 > 无，三入口（GUI 托盘 / Web 托盘 / favicon）共用这一个出口。
#
# 真机面（Qt 真的解出一个 ICO、托盘真的换图标）在 tests/test_gui_qt_units.py，
# 本文件全为纯函数与文件系统操作，无头可跑，Linux CI 也会执行。

import struct
from pathlib import Path

import pytest

from src import ui_icons

# 仓库内置图标（打包 exe 图标 + 运行时默认图标）。它不是测试夹具而是**被测物**：
# 换成单分辨率图标会让托盘或应用图标发虚，故在此钉死「必须含 16 与 256 两档」。
_REPO_ICON = Path(__file__).resolve().parent.parent / "assets" / "app.ico"


def _build_ico(sizes: tuple[int, ...]) -> bytes:
    # 拼一个只含目录项的 ICO：本模块的判据全在 ICONDIR 上，不需要真图像数据。
    # （真要驱动 Qt 解码的用例走 _REPO_ICON，见 tests/test_gui_qt_units.py。）
    header = b"\x00\x00\x01\x00" + struct.pack("<H", len(sizes))
    entries = b""
    for side in sizes:
        # 目录项：w(1) h(1) colors(1) reserved(1) planes(2) bpp(2) size(4) offset(4)
        # 宽高写 0 表示 256（协议规定），这也是 probe_ico_sizes 必须还原的口径
        encoded = 0 if side >= 256 else side
        entries += struct.pack("<BBBBHHII", encoded, encoded, 0, 0, 1, 32, 0, 0)
    return header + entries


class TestProbeIcoSizes:
    def test_reads_every_frame_size(self) -> None:
        assert ui_icons.probe_ico_sizes(_build_ico((16, 32, 256))) == ((16, 16), (32, 32), (256, 256))

    def test_zero_width_means_256(self) -> None:
        # 协议规定 0 = 256：读成 0 会让「没有 256 档」误判，进而拒掉合法图标
        assert ui_icons.probe_ico_sizes(_build_ico((256,))) == ((256, 256),)

    def test_non_ico_payload_is_rejected(self) -> None:
        assert ui_icons.probe_ico_sizes(b"\x89PNG\r\n\x1a\n" + b"x" * 32) is None

    def test_truncated_directory_is_rejected(self) -> None:
        # 目录项被截断时不得返回「半个目录」：那会让上层以为图标只有前几档
        data = _build_ico((16, 32, 256))
        assert ui_icons.probe_ico_sizes(data[:-8]) is None

    @pytest.mark.parametrize("count", [0, 64])
    def test_frame_count_bounds(self, count: int) -> None:
        # count=0 是空图标；count 超上限是损坏文件（上限存在的意义是防畸变循环）
        assert ui_icons.probe_ico_sizes(b"\x00\x00\x01\x00" + struct.pack("<H", count) + bytes(16)) is None

    def test_short_buffer_is_rejected(self) -> None:
        assert ui_icons.probe_ico_sizes(b"\x00\x00\x01\x00") is None


class TestValidateIconBytes:
    def test_full_multiresolution_icon_passes(self) -> None:
        check = ui_icons.validate_icon_bytes(_build_ico((16, 32, 256)))
        assert check.ok and check.code == ""

    def test_missing_tray_size_is_rejected(self) -> None:
        # 硬门槛：没有 16 档，托盘只能拿大图硬缩
        check = ui_icons.validate_icon_bytes(_build_ico((32, 256)))
        assert not check.ok
        assert check.code == "no_tray_size"

    def test_missing_app_size_only_warns(self) -> None:
        # 建议档：手头只有小图标的用户不该被完全挡在门外，提示即可
        check = ui_icons.validate_icon_bytes(_build_ico((16, 32)))
        assert check.ok
        assert check.code == "no_app_size"

    def test_empty_and_oversized_are_rejected(self) -> None:
        assert ui_icons.validate_icon_bytes(b"").code == "empty"
        # 体积先判：超大文件不该被送进结构解析
        big = b"\x00\x00\x01\x00" + struct.pack("<H", 1) + bytes(16)
        assert ui_icons.validate_icon_bytes(big, max_bytes=8).code == "too_large"

    def test_not_ico_is_rejected(self) -> None:
        assert ui_icons.validate_icon_bytes(b"\x89PNG" + b"x" * 32).code == "not_ico"

    def test_repo_icon_has_both_required_sizes(self) -> None:
        # 打包图标若是单分辨率，托盘或应用图标必有一处发虚，而这个故障期构建完全无声
        assert _REPO_ICON.is_file(), "assets/app.ico 缺失：打包产物将没有应用图标"
        check = ui_icons.validate_icon_bytes(_REPO_ICON.read_bytes())
        assert check.ok and check.code == ""
        assert ui_icons.TRAY_ICON_SIZE in {w for w, _h in check.sizes}
        assert ui_icons.APP_ICON_SIZE in {w for w, _h in check.sizes}


class TestInstallAndResolve:
    def test_install_writes_a_copy_under_config_icons(self, tmp_path: Path) -> None:
        target = ui_icons.install_icon_bytes(_build_ico((16, 256)), tmp_path, "app.ico")
        assert target is not None
        assert target.parent == tmp_path / "config" / "icons"
        assert target.is_file()

    def test_install_rejects_invalid_payload(self, tmp_path: Path) -> None:
        assert ui_icons.install_icon_bytes(b"not an icon", tmp_path) is None
        store = tmp_path / "config" / "icons"
        assert (not store.exists()) or not list(store.iterdir())

    def test_filename_is_sanitized_like_fonts(self, tmp_path: Path) -> None:
        # 与字体同一套清洗口径（ui_fonts.safe_filename）：分隔符变下划线、保留设备名加前缀
        target = ui_icons.install_icon_bytes(_build_ico((16, 256)), tmp_path, "my icon.ico")
        assert target is not None and target.name == "my_icon.ico"
        reserved = ui_icons.install_icon_bytes(_build_ico((16, 256)), tmp_path, "CON.ico")
        assert reserved is not None and reserved.name == "_CON.ico"

    def test_install_file_rejects_foreign_suffix(self, tmp_path: Path) -> None:
        src = tmp_path / "icon.png"
        src.write_bytes(_build_ico((16, 256)))
        # 内容合法但扩展名不是 .ico：导入环节只放行 ICO（见 ui_icons 文件头）
        assert ui_icons.install_icon_file(src, tmp_path) is None

    def test_install_file_copies_valid_icon(self, tmp_path: Path) -> None:
        src = tmp_path / "app.ico"
        src.write_bytes(_build_ico((16, 256)))
        target = ui_icons.install_icon_file(src, tmp_path)
        assert target is not None and target.read_bytes() == src.read_bytes()

    def test_resolve_accepts_absolute_and_relative_paths(self, tmp_path: Path) -> None:
        icon = tmp_path / "config" / "icons" / "app.ico"
        icon.parent.mkdir(parents=True)
        icon.write_bytes(b"x")
        assert ui_icons.resolve_icon_path(tmp_path, str(icon)) == icon
        assert ui_icons.resolve_icon_path(tmp_path, "config/icons/app.ico") == icon

    def test_resolve_returns_none_for_missing_or_blank(self, tmp_path: Path) -> None:
        assert ui_icons.resolve_icon_path(tmp_path, "") is None
        assert ui_icons.resolve_icon_path(tmp_path, "config/icons/gone.ico") is None


class TestPreferences:
    def test_roundtrip_write_then_read(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[GUI]\ngui_font =\n", encoding="utf-8-sig")
        assert ui_icons.load_icon_preference(cfg, ui_icons.GUI_SECTION, ui_icons.GUI_ICON_KEY) == ""
        assert ui_icons.save_icon_preference(cfg, ui_icons.GUI_SECTION, ui_icons.GUI_ICON_KEY, "config/icons/a.ico")
        assert ui_icons.load_icon_preference(cfg, ui_icons.GUI_SECTION, ui_icons.GUI_ICON_KEY) == "config/icons/a.ico"

    def test_read_is_tolerant_of_a_broken_config(self, tmp_path: Path) -> None:
        # 配置损坏绝不能让 GUI / Web 起不来：图标是装饰
        cfg = tmp_path / "config.ini"
        cfg.write_bytes(b"\xff\xfe broken bytes \x00")
        assert ui_icons.load_icon_preference(cfg, ui_icons.WEB_SECTION, ui_icons.WEB_ICON_KEY) == ""

    def test_two_sections_do_not_collide(self, tmp_path: Path) -> None:
        # GUI 与 Web 各有各的图标：面板上传的不该改桌面端，反之亦然
        cfg = tmp_path / "config.ini"
        cfg.write_text("[GUI]\n\n[Web]\n", encoding="utf-8-sig")
        _ = ui_icons.save_icon_preference(cfg, ui_icons.GUI_SECTION, ui_icons.GUI_ICON_KEY, "icons/gui.ico")
        _ = ui_icons.save_icon_preference(cfg, ui_icons.WEB_SECTION, ui_icons.WEB_ICON_KEY, "icons/web.ico")
        assert ui_icons.load_icon_preference(cfg, ui_icons.GUI_SECTION, ui_icons.GUI_ICON_KEY) == "icons/gui.ico"
        assert ui_icons.load_icon_preference(cfg, ui_icons.WEB_SECTION, ui_icons.WEB_ICON_KEY) == "icons/web.ico"


class TestCurrentIconPath:
    def test_imported_icon_wins_over_default(self, tmp_path: Path) -> None:
        imported = tmp_path / "config" / "icons" / "custom.ico"
        imported.parent.mkdir(parents=True)
        imported.write_bytes(_build_ico((16, 256)))
        default = tmp_path / "assets" / "app.ico"
        default.parent.mkdir(parents=True)
        default.write_bytes(_build_ico((16, 256)))
        assert ui_icons.current_icon_path(tmp_path, "config/icons/custom.ico") == imported

    def test_falls_back_to_default_when_config_is_stale(self, tmp_path: Path) -> None:
        # 用户删了导入的图标：不该留给调用方一个不存在的路径（那会让托盘变空白）
        default = tmp_path / "assets" / "app.ico"
        default.parent.mkdir(parents=True)
        default.write_bytes(_build_ico((16, 256)))
        assert ui_icons.current_icon_path(tmp_path, "config/icons/gone.ico") == default

    def test_none_when_nothing_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 仓库兜底根（源码树的 assets/）会让「tmp 里没有」仍命中仓库那份，
        # 故这里显式打断兜底，验证「真没有」时出口是 None（调用方据此回落自绘）
        monkeypatch.setattr(ui_icons, "default_icon_path", lambda _app_root: None)
        assert ui_icons.current_icon_path(tmp_path, "") is None


class TestDefaultIconPath:
    def test_prefers_app_root_over_module_relative(self, tmp_path: Path) -> None:
        # 冻结态 app_root 是 exe 同级目录（用户可见、可替换），必须压过包内那份
        local = tmp_path / ui_icons.DEFAULT_ICON_RELPATH
        local.parent.mkdir(parents=True)
        local.write_bytes(b"x")
        assert ui_icons.default_icon_path(tmp_path) == local

    def test_returns_path_or_none_only(self, tmp_path: Path) -> None:
        found = ui_icons.default_icon_path(tmp_path)
        assert found is None or isinstance(found, Path)
        if found is not None:
            assert found.is_file()


def test_icon_check_is_a_named_tuple_contract() -> None:
    # IconCheck 的字段顺序被 main_window._icon_reject_reason 与 web_api 消费：
    # 换成普通 tuple 会让 ok/code 读反（拒绝码被当成通过码），故在此钉住字段名与取值类型
    check = ui_icons.validate_icon_bytes(b"")
    assert isinstance(check.ok, bool) and isinstance(check.code, str)
    assert isinstance(check.sizes, tuple)
    assert (check.ok, check.code, check.sizes) == tuple(check)


def test_max_icon_bytes_is_sane() -> None:
    # 上限既要挡住恶意大文件，也不能挡住七档 ICO（内置那份 37KB：小档 BMP、大档 PNG）
    assert _REPO_ICON.is_file()
    assert len(_REPO_ICON.read_bytes()) < ui_icons.MAX_ICON_BYTES
    assert ui_icons.MAX_ICON_BYTES >= 64 * 1024


def test_repo_icon_frame_encoding_is_mixed_by_size() -> None:
    # 内置图标的帧编码是有意分档的：≤64 用 BMP 帧（Windows 资源管理器 / 旧 GDI 取小图时对 ICO 内的
    # PNG 帧有兼容瑕疵，16px 列表视图会偶发不显示），128/256 用 PNG 帧（BMP 的 256 档要 256KB，
    # 占整包 98%）。若某次「顺手重新生成」把全档统一成 PNG，肉眼看不出、构建也不报错，故在此钉住。
    data = _REPO_ICON.read_bytes()
    count = struct.unpack_from("<H", data, 4)[0]
    for i in range(count):
        width, _h, _c, _r, _p, _bpp, size, offset = struct.unpack_from("<BBBBHHII", data, 6 + i * 16)
        side = width or 256
        frame = data[offset : offset + size]
        assert len(frame) == size, f"{side}px 帧数据越界"
        is_png = frame[:4] == b"\x89PNG"
        # BMP 帧以 BITMAPINFOHEADER 的 biSize=40（小端 28 00 00 00）开头
        assert frame[:4] == struct.pack("<I", 40) or is_png, f"{side}px 帧既不是 BMP 也不是 PNG"
        assert is_png == (side >= 128), f"{side}px 帧编码不符「小档 BMP / 大档 PNG」的约定"


def test_public_helpers_never_raise_on_garbage(tmp_path: Path) -> None:
    # 汇总式守卫：任何垃圾输入都必须是「返回 None / 空串」，不得抛（图标不许挡启动）
    for data in (b"", b"\x00\x00\x01\x00", b"\xff" * 64):
        _ = ui_icons.probe_ico_sizes(data)
        _ = ui_icons.validate_icon_bytes(data)
        _ = ui_icons.install_icon_bytes(data, tmp_path)
    assert ui_icons.resolve_icon_path(tmp_path, "\x00bad") is None
