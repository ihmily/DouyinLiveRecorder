# Tests for src/utils.py - utility function tests for coverage improvement.

import os
import tempfile
from pathlib import Path

import pytest

from src.utils import (
    check_disk_capacity,
    check_md5,
    dict_to_cookie_str,
    get_file_paths,
    get_query_params,
    handle_proxy_addr,
    jsonp_to_json,
    read_config_value,
    remove_duplicate_lines,
    remove_emojis,
    replace_url,
    update_config,
)


class TestDictToCookieStr:
    # Test dict_to_cookie_str.

    def test_empty_dict(self):
        assert dict_to_cookie_str({}) == ""

    def test_single_cookie(self):
        assert dict_to_cookie_str({"key": "value"}) == "key=value"

    def test_multiple_cookies(self):
        result = dict_to_cookie_str({"a": "1", "b": "2"})
        assert "a=1" in result
        assert "b=2" in result
        assert "; " in result


class TestCheckMd5:
    # Test check_md5.

    def test_returns_md5(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world", encoding="utf-8")
        result = check_md5(test_file)
        assert len(result) == 32
        assert result.isalnum()

    def test_same_content_same_md5(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("same content", encoding="utf-8")
        f2.write_text("same content", encoding="utf-8")
        assert check_md5(f1) == check_md5(f2)


class TestCheckDiskCapacity:
    # Test check_disk_capacity.

    def test_returns_positive_float(self, tmp_path):
        result = check_disk_capacity(str(tmp_path))
        assert isinstance(result, float)
        assert result > 0

    def test_with_show(self, tmp_path, capsys):
        result = check_disk_capacity(str(tmp_path), show=True)
        captured = capsys.readouterr()
        assert "Total" in captured.out
        assert "Free" in captured.out
        assert isinstance(result, float)


class TestRemoveDuplicateLines:
    # Test remove_duplicate_lines.

    def test_removes_duplicates(self, tmp_path):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline1\nline3\nline2\n", encoding="utf-8-sig")
        remove_duplicate_lines(test_file)
        content = test_file.read_text(encoding="utf-8-sig")
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 3
        assert "line1" in lines
        assert "line2" in lines
        assert "line3" in lines


class TestReadConfigValue:
    # Test read_config_value.

    def test_read_existing_key(self, tmp_path):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "section1", "key1")
        assert result == "value1"

    def test_read_missing_key(self, tmp_path, capsys):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "section1", "missing_key")
        assert result is None
        captured = capsys.readouterr()
        assert "does not exist" in captured.out

    def test_read_missing_section(self, tmp_path, capsys):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "missing_section", "key1")
        assert result is None
        captured = capsys.readouterr()
        assert "does not exist" in captured.out


class TestUpdateConfig:
    # Test update_config.

    def test_update_existing_key(self, tmp_path, capsys):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = old_value\n", encoding="utf-8-sig")
        update_config(config_file, "section1", "key1", "new_value")
        result = read_config_value(config_file, "section1", "key1")
        assert result == "new_value"
        captured = capsys.readouterr()
        assert "updated" in captured.out

    def test_update_missing_section(self, tmp_path, capsys):
        config_file = tmp_path / "config.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        update_config(config_file, "missing_section", "key1", "new_value")
        captured = capsys.readouterr()
        assert "does not exist" in captured.out


class TestGetFilePaths:
    # Test get_file_paths.

    def test_returns_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("world")
        result = get_file_paths(str(tmp_path))
        assert len(result) == 2
        assert any("a.txt" in p for p in result)
        assert any("b.txt" in p for p in result)

    def test_empty_directory(self, tmp_path):
        result = get_file_paths(str(tmp_path))
        assert result == []


class TestRemoveEmojis:
    # Test remove_emojis.

    def test_no_emojis(self):
        assert remove_emojis("hello world") == "hello world"

    def test_with_emojis(self):
        result = remove_emojis("hello \U0001f600 world")
        assert result == "hello  world"

    def test_replace_text(self):
        result = remove_emojis("hello \U0001f600", "[emoji]")
        assert result == "hello [emoji]"


class TestHandleProxyAddr:
    # Test handle_proxy_addr.

    def test_none_returns_none(self):
        assert handle_proxy_addr(None) is None

    def test_empty_returns_none(self):
        assert handle_proxy_addr("") is None

    def test_no_prefix_adds_http(self):
        assert handle_proxy_addr("127.0.0.1:8080") == "http://127.0.0.1:8080"

    def test_with_prefix_kept(self):
        assert handle_proxy_addr("https://proxy.com:1080") == "https://proxy.com:1080"


class TestJsonpToJson:
    # Test jsonp_to_json.

    def test_valid_jsonp(self):
        jsonp = 'callback({"key": "value"});'
        result = jsonp_to_json(jsonp)
        assert result == {"key": "value"}

    def test_dotted_callback_name(self):
        jsonp = 'a.b.callback({"a": 1});'
        result = jsonp_to_json(jsonp)
        assert result == {"a": 1}

    def test_no_callback_raises(self):
        with pytest.raises(Exception, match="No JSON data"):
            jsonp_to_json("not a jsonp string")


class TestReplaceUrl:
    # Test replace_url.

    def test_replace_exact_line(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("https://old.com/stream\nother line\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com/stream", "https://new.com/stream")
        content = f.read_text(encoding="utf-8-sig")
        assert "https://new.com/stream" in content

    def test_replace_inline(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("url = https://old.com/live\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com/live", "https://new.com/live")
        content = f.read_text(encoding="utf-8-sig")
        assert "https://new.com/live" in content

    def test_no_match_unchanged(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("unrelated content\n", encoding="utf-8-sig")
        replace_url(f, "https://old.com", "https://new.com")
        content = f.read_text(encoding="utf-8-sig")
        assert "unrelated content" in content


class TestGetQueryParams:
    # Test get_query_params.

    def test_all_params(self):
        result = get_query_params("https://example.com?a=1&b=2", None)
        assert "a" in result
        assert "b" in result

    def test_specific_param(self):
        result = get_query_params("https://example.com?a=1&b=2", "a")
        assert result == ["1"]

    def test_missing_param(self):
        result = get_query_params("https://example.com?a=1", "missing")
        assert result == []
