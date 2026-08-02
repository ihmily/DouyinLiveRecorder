"""Tests for src/utils.py module."""

from pathlib import Path

import pytest

from src.utils import (
    Color,
    check_md5,
    dict_to_cookie_str,
    generate_random_string,
    get_file_paths,
    get_query_params,
    handle_proxy_addr,
    jsonp_to_json,
    read_config_value,
    remove_duplicate_lines,
    remove_emojis,
    replace_url,
    trace_error_decorator,
    update_config,
)


class TestColor:
    """Test Color class."""

    def test_color_constants(self):
        """Test color constants are defined."""
        assert Color.RED == "\033[31m"
        assert Color.GREEN == "\033[32m"
        assert Color.RESET == "\033[0m"

    def test_print_colored(self, capsys):
        """Test colored print output."""
        Color.print_colored("test", Color.RED)
        captured = capsys.readouterr()
        assert "test" in captured.out
        assert Color.RED in captured.out


class TestTraceErrorDecorator:
    """Test trace_error_decorator."""

    def test_sync_function_success(self):
        """Test decorator with successful sync function."""

        @trace_error_decorator
        def success_func():
            return "success"

        assert success_func() == "success"

    def test_sync_function_exception(self):
        """Test decorator catches sync function exceptions."""

        @trace_error_decorator
        def error_func():
            raise ValueError("test error")

        result = error_func()
        assert result == {"is_live": False}

    @pytest.mark.asyncio
    async def test_async_function_success(self):
        """Test decorator with successful async function."""

        @trace_error_decorator
        async def async_success():
            return "async_success"

        result = await async_success()
        assert result == "async_success"

    @pytest.mark.asyncio
    async def test_async_function_exception(self):
        """Test decorator catches async function exceptions."""

        @trace_error_decorator
        async def async_error():
            raise ValueError("async error")

        result = await async_error()
        assert result == {"is_live": False}


class TestCheckMd5:
    """Test check_md5 function."""

    def test_check_md5(self, tmp_path):
        """Test MD5 calculation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        md5 = check_md5(test_file)
        assert len(md5) == 32
        assert md5.isalnum()


class TestDictToCookieStr:
    """Test dict_to_cookie_str function."""

    def test_dict_to_cookie_str(self):
        """Test cookie dict to string conversion."""
        cookies = {"key1": "value1", "key2": "value2"}
        result = dict_to_cookie_str(cookies)
        assert result == "key1=value1; key2=value2"

    def test_empty_dict(self):
        """Test empty cookie dict."""
        assert dict_to_cookie_str({}) == ""


class TestReadConfigValue:
    """Test read_config_value function."""

    def test_read_existing_value(self, tmp_path):
        """Test reading existing config value."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "section1", "key1")
        assert result == "value1"

    def test_read_nonexistent_section(self, tmp_path):
        """Test reading from non-existent section."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "section2", "key1")
        assert result is None

    def test_read_nonexistent_key(self, tmp_path):
        """Test reading non-existent key."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        result = read_config_value(config_file, "section1", "key2")
        assert result is None


class TestUpdateConfig:
    """Test update_config function."""

    def test_update_existing_value(self, tmp_path):
        """Test updating existing config value."""
        config_file = tmp_path / "test.ini"
        config_file.write_text("[section1]\nkey1 = value1\n", encoding="utf-8-sig")
        update_config(config_file, "section1", "key1", "new_value")
        result = read_config_value(config_file, "section1", "key1")
        assert result == "new_value"


class TestGetFilePaths:
    """Test get_file_paths function."""

    def test_get_file_paths(self, tmp_path):
        """Test getting file paths from directory."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        paths = get_file_paths(str(tmp_path))
        assert len(paths) == 3
        assert all(Path(p).is_absolute() for p in paths)


class TestRemoveEmojis:
    """Test remove_emojis function."""

    def test_remove_emojis(self):
        """Test emoji removal."""
        text = "Hello 😀 World 🌍"
        result = remove_emojis(text)
        assert result == "Hello  World "

    def test_remove_emojis_with_replacement(self):
        """Test emoji removal with replacement."""
        text = "Hello 😀 World"
        result = remove_emojis(text, replace_text="-")
        assert result == "Hello - World"

    def test_no_emojis(self):
        """Test text without emojis."""
        text = "Hello World"
        result = remove_emojis(text)
        assert result == "Hello World"


class TestRemoveDuplicateLines:
    """Test remove_duplicate_lines function."""

    def test_remove_duplicates(self, tmp_path):
        """Test duplicate line removal."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline1\nline3\nline2\n", encoding="utf-8-sig")
        remove_duplicate_lines(test_file)
        content = test_file.read_text(encoding="utf-8-sig")
        lines = content.strip().split("\n")
        assert len(lines) == 3
        assert "line1" in lines
        assert "line2" in lines
        assert "line3" in lines


class TestCheckDiskCapacity:
    """Test check_disk_capacity function."""

    def test_check_disk_capacity(self, tmp_path):
        """Test disk capacity check."""
        from src.utils import check_disk_capacity

        result = check_disk_capacity(tmp_path)
        assert isinstance(result, float)
        assert result > 0


class TestHandleProxyAddr:
    """Test handle_proxy_addr function."""

    def test_add_http_prefix(self):
        """Test adding http prefix."""
        result = handle_proxy_addr("127.0.0.1:8080")
        assert result == "http://127.0.0.1:8080"

    def test_keep_existing_http(self):
        """Test keeping existing http prefix."""
        result = handle_proxy_addr("http://127.0.0.1:8080")
        assert result == "http://127.0.0.1:8080"

    def test_keep_existing_https(self):
        """Test keeping existing https prefix."""
        result = handle_proxy_addr("https://proxy.com:8080")
        assert result == "https://proxy.com:8080"

    def test_keep_socks(self):
        """Test keeping socks prefix."""
        result = handle_proxy_addr("socks5://proxy.com:1080")
        assert result == "socks5://proxy.com:1080"

    def test_none_input(self):
        """Test None input."""
        result = handle_proxy_addr(None)
        assert result is None

    def test_empty_string(self):
        """Test empty string input."""
        result = handle_proxy_addr("")
        assert result is None


class TestGenerateRandomString:
    """Test generate_random_string function."""

    def test_generate_length(self):
        """Test generated string length."""
        result = generate_random_string(10)
        assert len(result) == 10

    def test_generate_characters(self):
        """Test generated string contains only uppercase and digits."""
        result = generate_random_string(100)
        assert all(c.isupper() or c.isdigit() for c in result)

    def test_different_lengths(self):
        """Test different lengths."""
        for length in [1, 5, 20, 50]:
            result = generate_random_string(length)
            assert len(result) == length


class TestJsonpToJson:
    """Test jsonp_to_json function."""

    def test_simple_jsonp(self):
        """Test simple JSONP conversion."""
        jsonp = 'callback({"key": "value"});'
        result = jsonp_to_json(jsonp)
        assert result == {"key": "value"}

    def test_jsonp_without_semicolon(self):
        """Test JSONP without semicolon."""
        jsonp = 'callback({"key": "value"})'
        result = jsonp_to_json(jsonp)
        assert result == {"key": "value"}

    def test_jsonp_with_dotted_callback(self):
        """Test JSONP with dotted callback name."""
        jsonp = 'a.b.c({"key": "value"});'
        result = jsonp_to_json(jsonp)
        assert result == {"key": "value"}

    def test_invalid_jsonp(self):
        """Test invalid JSONP raises exception."""
        with pytest.raises(Exception, match="No JSON data found"):
            jsonp_to_json("not a jsonp")


class TestReplaceUrl:
    """Test replace_url function."""

    def test_replace_exact_line(self, tmp_path):
        """Test replacing exact line match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("https://old.com\nother line\n", encoding="utf-8-sig")
        replace_url(test_file, "https://old.com", "https://new.com")
        content = test_file.read_text(encoding="utf-8-sig")
        assert "https://new.com" in content.splitlines()

    def test_replace_partial_line(self, tmp_path):
        """Test replacing partial line match."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("url = https://old.com\n", encoding="utf-8-sig")
        replace_url(test_file, "https://old.com", "https://new.com")
        content = test_file.read_text(encoding="utf-8-sig")
        assert "https://new.com" in content


class TestGetQueryParams:
    """Test get_query_params function."""

    def test_get_all_params(self):
        """Test getting all query parameters."""
        url = "https://example.com?key1=value1&key2=value2"
        result = get_query_params(url, None)
        assert "key1" in result
        assert "key2" in result
        assert result["key1"] == ["value1"]

    def test_get_specific_param(self):
        """Test getting specific parameter."""
        url = "https://example.com?key1=value1&key2=value2"
        result = get_query_params(url, "key1")
        assert result == ["value1"]

    def test_get_nonexistent_param(self):
        """Test getting non-existent parameter."""
        url = "https://example.com?key1=value1"
        result = get_query_params(url, "key2")
        assert result == []

    def test_multiple_values(self):
        """Test parameter with multiple values."""
        url = "https://example.com?key=value1&key=value2"
        result = get_query_params(url, "key")
        assert result == ["value1", "value2"]
