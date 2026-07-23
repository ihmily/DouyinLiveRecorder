# tests/test_web_config.py
from pathlib import Path

from src.web_config import (
    parse_url_config,
    format_url_line,
    normalize_url,
    read_web_config,
    read_config_safe,
    SENSITIVE_SECTIONS,
    SENSITIVE_MASK,
)


def test_parse_url_config_basic(tmp_url_config: Path):
    rooms = parse_url_config(tmp_url_config)
    assert len(rooms) == 5
    enabled = [r for r in rooms if r["enabled"]]
    disabled = [r for r in rooms if not r["enabled"]]
    assert len(enabled) == 4
    assert len(disabled) == 1
    by_url = {r["url"]: r for r in enabled}
    assert by_url["https://live.douyin.com/123"]["quality"] == "原画"
    assert by_url["https://live.bilibili.com/456"]["quality"] == "超清"
    assert by_url["https://www.douyu.com/012"]["quality"] == "高清"
    assert by_url["https://www.douyu.com/012"]["name"] == "测试主播"
    assert by_url["https://www.huya.com/001"]["quality"] == "超清"
    assert by_url["https://www.huya.com/001"]["name"] == "全角测试"
    assert disabled[0]["url"] == "https://www.huya.com/789"
    assert disabled[0]["enabled"] is False


def test_parse_url_config_normalizes_missing_scheme(tmp_path: Path):
    p = tmp_path / "URL_config.ini"
    p.write_text("live.douyin.com/999\n", encoding="utf-8")
    rooms = parse_url_config(p)
    assert rooms[0]["url"] == "https://live.douyin.com/999"


def test_format_url_line_url_only():
    assert format_url_line("https://live.douyin.com/123") == "https://live.douyin.com/123"


def test_format_url_line_with_quality():
    assert format_url_line("https://live.bilibili.com/456", "超清") == "超清,https://live.bilibili.com/456"


def test_format_url_line_default_quality_omitted():
    assert format_url_line("https://live.douyin.com/1", "原画") == "https://live.douyin.com/1"


def test_format_url_line_with_name():
    assert format_url_line("https://www.douyu.com/12", "高清", "测试主播") == \
        "高清,https://www.douyu.com/12,主播: 测试主播"


def test_format_url_line_normalizes_missing_scheme():
    assert format_url_line("live.douyin.com/9") == "https://live.douyin.com/9"


def test_normalize_url_strips_query_for_clean_host():
    # clean host 的 query 应被去除
    assert normalize_url("https://live.douyin.com/123?foo=bar") == "https://live.douyin.com/123"
    # 非 clean host 的 query 应保留
    assert normalize_url("https://www.douyu.com/012?a=1") == "https://www.douyu.com/012?a=1"


def test_read_web_config_defaults(tmp_config_ini):
    cfg = read_web_config(tmp_config_ini)
    assert cfg["web_host"] == "0.0.0.0"
    assert cfg["web_port"] == 8000
    assert cfg["web_auth_enable"] is False
    assert cfg["web_password"] == ""
    assert cfg["web_token_expiry"] == 86400


def test_read_web_config_missing_section(tmp_path):
    p = tmp_path / "empty.ini"
    p.write_text("[其他]\nkey = val\n", encoding="utf-8")
    cfg = read_web_config(p)
    assert cfg["web_port"] == 8000
    assert cfg["web_auth_enable"] is False


def test_read_config_safe_masks_sensitive(tmp_config_ini):
    sections = read_config_safe(tmp_config_ini)
    assert sections["录制设置"]["循环时间(秒)"] == "300"
    assert sections["Cookie"]["抖音cookie"] == SENSITIVE_MASK
    assert sections["账号密码"]["sooplive账号"] == ""
