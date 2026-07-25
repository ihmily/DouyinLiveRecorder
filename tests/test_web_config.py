# tests/test_web_config.py
from pathlib import Path

from src.web_config import (
    parse_url_config,
    format_url_line,
    normalize_url,
    read_web_config,
    read_config_safe,
    update_config_line,
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
    assert cfg["web_show_console"] is True


def test_read_web_config_show_console_false(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(
        "[Web]\nweb_show_console = false\n",
        encoding="utf-8",
    )
    cfg = read_web_config(p)
    assert cfg["web_show_console"] is False


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


def test_read_config_safe_masks_web_password(tmp_config_ini):
    # tmp_config_ini has [Web] web_password = (empty) by default; set a value first
    import configparser
    p = configparser.ConfigParser(interpolation=None)
    p.read(tmp_config_ini, encoding="utf-8")
    p.set("Web", "web_password", "secret123")
    with open(tmp_config_ini, "w", encoding="utf-8") as f:
        p.write(f)
    sections = read_config_safe(tmp_config_ini)
    assert sections["Web"]["web_password"] == "***"
    # other Web keys NOT masked
    assert sections["Web"]["web_port"] == "8000"
    assert sections["Web"]["web_host"] == "0.0.0.0"


def _write_ini_with_comments(path: Path) -> None:
    path.write_text(
        "# 顶层注释：录制设置\n"
        "[录制设置]\n"
        "循环时间(秒) = 300  ; 行内注释\n"
        "# 画质默认值\n"
        "原画|超清|高清|标清|流畅 = 原画\n"
        "\n"
        "; Web 节注释\n"
        "[Web]\n"
        "web_host = 0.0.0.0\n"
        "web_port = 8000\n",
        encoding="utf-8",
    )


def test_update_config_line_replaces_value(tmp_path: Path):
    p = tmp_path / "config.ini"
    _write_ini_with_comments(p)
    ok = update_config_line(str(p), "录制设置", "循环时间(秒)", "777")
    assert ok is True
    text = p.read_text(encoding="utf-8-sig")
    # 值已变更
    assert "循环时间(秒) = 777" in text
    # 其他键未受影响
    assert "原画|超清|高清|标清|流畅 = 原画" in text
    assert "web_port = 8000" in text
    # 旧值不再出现
    assert "循环时间(秒) = 300" not in text


def test_update_config_line_preserves_comments(tmp_path: Path):
    p = tmp_path / "config.ini"
    _write_ini_with_comments(p)
    update_config_line(str(p), "Web", "web_port", "9000")
    text = p.read_text(encoding="utf-8-sig")
    # 顶层注释保留
    assert "# 顶层注释：录制设置" in text
    # 行内注释保留
    assert "循环时间(秒) = 300  ; 行内注释" in text
    # 节内独立注释保留
    assert "# 画质默认值" in text
    assert "; Web 节注释" in text
    # 空行保留（原画行与 ; Web 节注释 之间的空行）
    assert "原画|超清|高清|标清|流畅 = 原画\n\n; Web 节注释" in text
    # 新值生效
    assert "web_port = 9000" in text


def test_update_config_line_missing_section_returns_false(tmp_path: Path):
    p = tmp_path / "config.ini"
    _write_ini_with_comments(p)
    original = p.read_text(encoding="utf-8")
    ok = update_config_line(str(p), "不存在的节", "循环时间(秒)", "777")
    assert ok is False
    # 文件未被改写
    assert p.read_text(encoding="utf-8-sig") == original


def test_update_config_line_missing_key_returns_false(tmp_path: Path):
    p = tmp_path / "config.ini"
    _write_ini_with_comments(p)
    original = p.read_text(encoding="utf-8")
    ok = update_config_line(str(p), "录制设置", "不存在的键", "777")
    assert ok is False
    # 文件未被改写
    assert p.read_text(encoding="utf-8-sig") == original


def test_update_config_line_missing_file_returns_false(tmp_path: Path):
    p = tmp_path / "nope.ini"
    assert update_config_line(str(p), "录制设置", "循环时间(秒)", "777") is False


def test_update_config_line_preserves_inline_comment(tmp_path: Path):
    p = tmp_path / "config.ini"
    p.write_text(
        "[Web]\nweb_password = oldpass ; 这是一个注释\nweb_port = 8000\n",
        encoding="utf-8",
    )
    ok = update_config_line(p, "Web", "web_password", "newpass")
    assert ok is True
    content = p.read_text(encoding="utf-8")
    # 值已更新
    assert "web_password = newpass" in content
    # 行内注释保留
    assert "; 这是一个注释" in content
    # 其他行不动
    assert "web_port = 8000" in content


def test_update_config_line_preserves_hash_inline_comment(tmp_path):
    p = tmp_path / "config.ini"
    p.write_text(
        "[Web]\nweb_host = 0.0.0.0 # 监听所有接口\nweb_port = 8000\n",
        encoding="utf-8",
    )
    ok = update_config_line(p, "Web", "web_host", "127.0.0.1")
    assert ok is True
    content = p.read_text(encoding="utf-8")
    assert "web_host = 127.0.0.1 # 监听所有接口" in content
    assert "web_port = 8000" in content


def test_update_config_line_value_without_comment_unchanged_behavior(tmp_path: Path):
    p = tmp_path / "config.ini"
    p.write_text("[录制设置]\n循环时间(秒) = 300\n", encoding="utf-8")
    ok = update_config_line(p, "录制设置", "循环时间(秒)", "60")
    assert ok is True
    assert "循环时间(秒) = 60\n" == p.read_text(encoding="utf-8").splitlines(keepends=True)[1]
