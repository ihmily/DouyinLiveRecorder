# tests/test_ui_fonts.py — GUI 自选字体的回归锁。
#
# 覆盖两件事：
#   ① 偏好读写 —— 经 src/web_config.update_or_append_config_line，与 ui_theme/ui_scale 同口径；
#   ② 导入落盘 —— 格式过滤、复制到 config/fonts 的复制语义、文件名清洗与失败留痕。
#
# 字体枚举与「某族名能否解析」已由窗口层用 QFontDatabase 判定，本模块不再包含 Tk 面；
# 全部用例无头可跑（Linux CI 全量执行）。

import shutil
import types
from pathlib import Path
from typing import Any

import pytest

from src import ui_fonts
from src.logger import logger


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


class TestInstall:
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
        src.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 32)
        target = ui_fonts.install_font_file(src, tmp_path / "app")
        assert target is not None
        assert target.exists()
        assert target.parent.name == ui_fonts.FONT_STORE_DIRNAME
        # 复制语义：源文件仍在
        assert src.is_file()

    def test_filename_is_sanitized(self, tmp_path: Path) -> None:
        # 文件名来自用户选的任意位置，落进本地字体目录前必须清洗；但**夹具名本身要能在两端都建出来**：
        # 原夹具用 `font:with|weird*chars?.ttf`，Windows 把 `:` 解析成 `font` 的备用数据流，
        # 于是 exists()/is_file() 为真而 shutil.copy2 抛 FileNotFoundError [WinError 3] →
        # 被测函数按设计返回 None，用例变成「本机红、Linux CI 绿」的环境差异噪声（2026-10-17 实测）。
        # 非法字符那半边改由下面的纯函数用例覆盖——不碰文件系统，两端语义一致。
        src = tmp_path / "  my font  (v2) ..ttf"
        src.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 32)
        target = ui_fonts.install_font_file(src, tmp_path / "app")
        assert target is not None, "复制合法但名字不整洁的字体文件不该失败"
        assert target.exists()
        assert " " not in target.name and "(" not in target.name and ")" not in target.name
        assert target.suffix == ".ttf"
        assert src.is_file()

    def test_safe_filename_handles_platform_illegal_chars_pure(self) -> None:
        # 纯函数面：含 `:` `|` `*` `?` 的名字在 Windows 上根本建不出来，只能在字符串层面验清洗结果。
        cleaned = ui_fonts._safe_filename("font:with|weird*chars?.ttf")
        assert cleaned == "font_with_weird_chars_.ttf"
        for ch in r':|*?"<>\/':
            assert ch not in cleaned, f"清洗后仍残留非法字符 {ch!r}"
        # 幂等：清洗过的名字再过一遍不该变（否则重试/回填会不断改文件名）
        assert ui_fonts._safe_filename(cleaned) == cleaned

    def test_safe_filename_falls_back_when_name_has_no_content(self) -> None:
        # 空名与「只剩点和空格」的名字都必须给出可用名，不能让 store / "" 拼出目录路径
        assert ui_fonts._safe_filename("") == "custom_font.ttf"
        assert ui_fonts._safe_filename("...") == "custom_font.ttf"
        assert ui_fonts._safe_filename("  . .  ") == "custom_font.ttf"

    def test_safe_filename_prefixes_windows_reserved_device_names(self) -> None:
        # 保留设备名必须加前缀避开。注意判据是**字符串形态**、不是「本机一定写不进去」：
        # 2026-10-17 在 Windows 10.0.26300 实测 CON.ttf/AUX.ttf 经 Python 与 cmd 都能落成普通文件，
        # 但同一份名字在更早的 Windows 构建 / 资源管理器 / 未走 \?\ 前缀的 API 下语义不一致，
        # 而它会被写进 gui_font_file 持久化并跨机器读回（详见 ui_fonts._WIN_RESERVED_NAMES 注释）。
        # 大小写不敏感、且与扩展名无关：CON.ttf 的基名仍是 CON。
        for raw, want in (
            ("CON.ttf", "_CON.ttf"),
            ("nul.ttf", "_nul.ttf"),
            ("COM1.otf", "_COM1.otf"),
            ("LPT9.ttf", "_LPT9.ttf"),
            ("PRN", "_PRN"),
            ("AUX.ttf", "_AUX.ttf"),
        ):
            got = ui_fonts._safe_filename(raw)
            assert got == want, f"{raw} 应加下划线前缀避开保留名，实得 {got!r}"
            assert ui_fonts._safe_filename(got) == got, "前缀必须幂等，不能每次重试都叠一层下划线"
        # 边界三形：COM10/LPT10 不在保留集合内（MSDN 只保留 1..9，扩到两位数会误改合法文件名），
        # console/NULx/myCON 只是形似——按整段基名比对，不做子串匹配。
        for name in ("COM10.ttf", "LPT10.ttf", "console.ttf", "NULx.ttf", "myCON.ttf"):
            assert ui_fonts._safe_filename(name) == name, f"{name} 不该被改名"

    def test_install_font_file_logs_copy_failure_with_reason(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 钉的是「异常被吞成 None 且日志零行」这一形态：调用方拿 None 只能弹一句分类级提示，
        # 文件被占用 / 目标目录只读 / 磁盘满在 UI 上完全同形，唯一可归因的现场证据就是这行 warning。
        src = tmp_path / "good.ttf"
        src.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 32)

        def deny(_a: Any, _b: Any) -> None:
            raise PermissionError(13, "target directory is read-only")

        # 替身走被测模块命名空间的 shim：直接 patch shutil.copy2 会波及同进程其它会话与守护线程
        shim = types.SimpleNamespace(**vars(shutil))
        shim.copy2 = deny
        monkeypatch.setattr(ui_fonts, "shutil", shim)

        captured: list[str] = []
        handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
        try:
            assert ui_fonts.install_font_file(src, tmp_path / "app") is None
        finally:
            logger.remove(handler_id)
        joined = "\n".join(captured)
        assert "复制字体文件失败" in joined, f"失败必须留下一行原因，实得 {captured!r}"
        assert (
            "PermissionError" in joined
        ), "日志须含异常类型名：Windows 下部分异常的 str() 为空串，只打 {err} 会打出空白行"
        assert "good.ttf" in joined and "target directory is read-only" in joined
