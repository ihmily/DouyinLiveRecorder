# Tests for src/web_config.py - Web 面板配置纯函数模块（安全回归）.

from pathlib import Path

import pytest

from src.web_config import (
    format_url_line,
    hash_web_password,
    is_hashed_web_password,
    read_web_config,
    update_config_line,
    validate_config_target,
    validate_room_target,
    verify_web_password,
)


class TestFormatUrlLine:
    # format_url_line 换行注入防护（C3）.

    def test_quality_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality="高清\n# evil", name=None)

    def test_name_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality=None, name="主播\nxx")

    def test_url_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1\n# evil", quality=None, name=None)

    def test_normal_line(self) -> None:
        line = format_url_line("https://live.douyin.com/1", "超清", "小明")
        assert line == "超清,https://live.douyin.com/1,主播: 小明"


class TestValidateTargets:
    def test_newline_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_config_target("Web", "web_host", "127.0.0.1\nweb_port=9999")

    def test_newline_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_room_target("https://live.douyin.com/1\n# x", None)


class TestUpdateConfigLine:
    def test_update_preserves_comments_and_cleans_tmp(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\n# 注释\nweb_host = 127.0.0.1\nweb_port = 8000\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "web_host", "0.0.0.0") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "web_host = 0.0.0.0" in text
        assert "# 注释" in text
        # 原子写不应留下临时文件（C7）：精确匹配 .tmp 扩展名
        leftovers = [p.name for p in tmp_path.glob("*.tmp")]
        assert leftovers == [], f"原子写残留临时文件: {leftovers}"

    def test_missing_key_returns_false(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_host = 127.0.0.1\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "not_exist", "x") is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert update_config_line(tmp_path / "nope.ini", "Web", "web_host", "x") is False


class TestVerifyWebPassword:
    def test_hash_roundtrip(self) -> None:
        hashed = hash_web_password("secret123")
        assert is_hashed_web_password(hashed)
        assert verify_web_password("secret123", hashed)
        assert not verify_web_password("wrong", hashed)

    def test_plaintext_compat(self) -> None:
        assert verify_web_password("abc", "abc")

    def test_malformed_iterations_returns_false(self) -> None:
        # 手工改坏迭代次数不应抛异常导致登录接口 500（C12）
        bad = "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA=="
        assert verify_web_password("x", bad) is False

    def test_empty_stored_returns_false(self) -> None:
        assert verify_web_password("x", "") is False


class TestReadWebConfig:
    def test_defaults_include_trusted_proxy(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("", encoding="utf-8-sig")
        result = read_web_config(cfg)
        assert result["web_trusted_proxy"] == ""
        assert result["web_host"] == "127.0.0.1"
