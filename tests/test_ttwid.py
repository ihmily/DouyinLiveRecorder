# Tests for src/ttwid.py - ttwid module tests for coverage improvement.

import configparser
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.ttwid as ttwid_module
from src.cookie_cache import clear as clear_cookie_cache
from src.ttwid import (
    _app_root,
    _cached_ttwid,
    _fetch_ttwid,
    _read_config_ttwid,
    get_ttwid,
    warmup_ttwid,
)


class TestAppRoot:
    # Test _app_root.

    def test_returns_string(self):
        result = _app_root()
        assert isinstance(result, str)
        assert len(result) > 0


class TestReadConfigTtwid:
    # Test _read_config_ttwid.

    def test_no_config_returns_empty(self):
        with patch("src.ttwid._app_root", return_value="/nonexistent/path"):
            result = _read_config_ttwid()
            assert result == ""

    def test_with_config_ttwid(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = abc123\n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == "ttwid=abc123"

    def test_with_config_already_prefixed(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = ttwid=xyz789\n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == "ttwid=xyz789"

    def test_empty_ttwid_returns_empty(self, tmp_path):
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = \n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == ""


class TestFetchTtwid:
    # Test _fetch_ttwid.

    @pytest.mark.asyncio
    async def test_success(self):
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        cookies = {"ttwid": "test_value_123"}
        with patch("src.ttwid.async_req", new_callable=AsyncMock, return_value=cookies):
            result = await _fetch_ttwid()
            assert result == "ttwid=test_value_123"
            assert ttwid_module._cached_ttwid == "ttwid=test_value_123"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_no_ttwid_in_cookies(self):
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        cookies = {"other": "value"}
        with patch("src.ttwid.async_req", new_callable=AsyncMock, return_value=cookies):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self):
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        with patch("src.ttwid.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""


class TestGetTtwid:
    # Test get_ttwid.

    @pytest.mark.asyncio
    async def test_cached_returns_directly(self):
        ttwid_module._cached_ttwid = "ttwid=cached_value"
        result = await get_ttwid()
        assert result == "ttwid=cached_value"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_reads_config_first(self):
        ttwid_module._cached_ttwid = ""
        with (
            patch("src.ttwid._read_config_ttwid", return_value="ttwid=from_config"),
            patch("src.ttwid._fetch_ttwid", new_callable=AsyncMock, return_value=""),
        ):
            result = await get_ttwid()
            assert result == "ttwid=from_config"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_falls_back_to_fetch(self):
        ttwid_module._cached_ttwid = ""
        with (
            patch("src.ttwid._read_config_ttwid", return_value=""),
            patch("src.ttwid._fetch_ttwid", new_callable=AsyncMock, return_value="ttwid=fetched"),
        ):
            result = await get_ttwid()
            assert result == "ttwid=fetched"
        ttwid_module._cached_ttwid = ""


class TestWarmupTtwid:
    # Test warmup_ttwid.

    def test_success(self):
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        # warmup_ttwid calls asyncio.run(get_ttwid()), which internally calls _fetch_ttwid
        # and sets _cached_ttwid. We mock async_req to control _fetch_ttwid's behavior.
        cookies = {"ttwid": "warm_value"}
        with (
            patch("src.ttwid.async_req", new_callable=AsyncMock, return_value=cookies),
            patch("src.ttwid._read_config_ttwid", return_value=""),
        ):
            warmup_ttwid()
            assert ttwid_module._cached_ttwid == "ttwid=warm_value"
        ttwid_module._cached_ttwid = ""

    def test_exception_handled(self):
        with patch("src.ttwid.get_ttwid", new_callable=AsyncMock, side_effect=Exception("fail")):
            # Should not raise
            warmup_ttwid()
