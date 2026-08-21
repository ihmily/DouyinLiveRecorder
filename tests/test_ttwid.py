# Tests for src/ttwid.py - ttwid module tests for coverage improvement.

import configparser
import os
import sys
from pathlib import Path
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

    def test_returns_string(self) -> None:
        result = _app_root()
        assert isinstance(result, str)
        assert len(result) > 0


class TestReadConfigTtwid:
    # Test _read_config_ttwid.

    def test_no_config_returns_empty(self) -> None:
        with patch("src.ttwid._app_root", return_value="/nonexistent/path"):
            result = _read_config_ttwid()
            assert result == ""

    def test_with_config_ttwid(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = abc123\n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == "ttwid=abc123"

    def test_with_config_already_prefixed(self, tmp_path: Path) -> None:
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = ttwid=xyz789\n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == "ttwid=xyz789"

    def test_empty_ttwid_returns_empty(self, tmp_path: Path) -> None:
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
    async def test_success(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        cookies = {"ttwid": "test_value_123"}
        with patch("src.ttwid.async_req", new_callable=AsyncMock, return_value=cookies):
            result = await _fetch_ttwid()
            assert result == "ttwid=test_value_123"
            assert ttwid_module._cached_ttwid == "ttwid=test_value_123"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_no_ttwid_in_cookies(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        cookies = {"other": "value"}
        with patch("src.ttwid.async_req", new_callable=AsyncMock, return_value=cookies):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_exception_returns_empty(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        with patch("src.ttwid.async_req", new_callable=AsyncMock, side_effect=Exception("net")):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""


class TestGetTtwid:
    # Test get_ttwid.

    @pytest.mark.asyncio
    async def test_cached_returns_directly(self) -> None:
        ttwid_module._cached_ttwid = "ttwid=cached_value"
        result = await get_ttwid()
        assert result == "ttwid=cached_value"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_reads_config_first(self) -> None:
        ttwid_module._cached_ttwid = ""
        with (
            patch("src.ttwid._read_config_ttwid", return_value="ttwid=from_config"),
            patch("src.ttwid._fetch_ttwid", new_callable=AsyncMock, return_value=""),
        ):
            result = await get_ttwid()
            assert result == "ttwid=from_config"
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_falls_back_to_fetch(self) -> None:
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

    def test_success(self) -> None:
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

    def test_exception_handled(self) -> None:
        with patch("src.ttwid.get_ttwid", new_callable=AsyncMock, side_effect=Exception("fail")):
            # Should not raise
            warmup_ttwid()


class TestAppRootFrozen:
    # _app_root 的 frozen 分支（PyInstaller 冻结运行）仅在 sys.frozen=True 时执行，
    # 单测默认不触发，这里显式 patch 覆盖，避免该分支永久处于零覆盖。
    def test_frozen_returns_exe_dir(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ttwid_module.sys, "frozen", True, raising=False)
        result = _app_root()
        assert isinstance(result, str)
        assert result == os.path.dirname(os.path.realpath(sys.executable))


class TestReadConfigTtwidBroadExcept:
    # _read_config_ttwid 的兜底 broad except：捕获非 configparser 的意外异常并返回 ""。
    def test_unexpected_exception_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BoomParser:
            def read(self, *args: object, **kwargs: object) -> list[str]:
                return []

            def get(self, *args: object, **kwargs: object) -> str:
                raise ValueError("unexpected")

        monkeypatch.setattr(ttwid_module.configparser, "RawConfigParser", _BoomParser)
        with patch("src.ttwid._app_root", return_value="/nonexistent"):
            assert _read_config_ttwid() == ""


class TestFetchTtwidException:
    # _fetch_ttwid 内部 _cache_fetch_cookies 抛异常时，须记 warning 并返回 ""（不冒泡）。
    @pytest.mark.asyncio
    async def test_cookie_fetch_raises_logs_warning(self) -> None:
        ttwid_module._cached_ttwid = ""
        with patch(
            "src.ttwid._cache_fetch_cookies",
            new_callable=AsyncMock,
            side_effect=Exception("net down"),
        ):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""


class TestGetTtwidContention:
    # get_ttwid 的锁竞争兜底分支：另一线程已持有锁时，本线程等待后兜底重试一次。
    # 该分支仅在高并发（多 room 独立线程）下可达，单测用假锁替换模块级 _ttwid_lock，
    # 令其 acquire(blocking=False) 恒返回 False 以模拟「锁已被其他线程持有」。
    @pytest.mark.asyncio
    async def test_contention_fallback_to_fetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ttwid_module._cached_ttwid = ""

        class _ContendedLock:
            # acquire 恒返回 False → 进入 get_ttwid 的锁竞争兜底分支
            def acquire(self, *args: object, **kwargs: object) -> bool:
                return False

            def release(self, *args: object, **kwargs: object) -> None:
                pass

            def __enter__(self) -> "_ContendedLock":
                return self

            def __exit__(self, *args: object) -> None:
                return None

        monkeypatch.setattr(ttwid_module, "_ttwid_lock", _ContendedLock())
        with patch("src.ttwid._fetch_ttwid", new_callable=AsyncMock, return_value="ttwid=contended"):
            result = await get_ttwid()
            assert result == "ttwid=contended"
        ttwid_module._cached_ttwid = ""
