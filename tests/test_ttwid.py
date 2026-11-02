# src/ttwid.py 的回归锁：出口分列的 TTL 缓存、配置预置 ttwid 读取、拉取拼装、singleflight 并发去重与预热。

import asyncio
import configparser
import os
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.ttwid as ttwid_module
from src.cookie_cache import clear as clear_cookie_cache
from src.ttwid import _app_root, _cached_ttwid, _fetch_ttwid, _read_config_ttwid, get_ttwid, warmup_ttwid


@pytest.fixture(autouse=True)
def _isolate_ttwid_buckets(monkeypatch: pytest.MonkeyPatch) -> None:
    # 起快路读的是「按出口分列」的模块级 dict（_cached_ttwid_by_proxy）。
    # conftest 的逐用例重置只清镜像 `_cached_ttwid`，而本文件有用例会显式把镜像置成
    # 非空来验「TTL 内命中」，于是上一个用例留下的桶值会串进来（实测表现为拿到
    # "ttwid=from_config" 这种别的用例写的陈旧值）。这里整体换一只新 dict：
    # 用例内的写入都落在临时对象上，monkeypatch 撤销后真实模块 dict 保持干净、不外溢。
    monkeypatch.setattr(ttwid_module, "_cached_ttwid_by_proxy", {})
    monkeypatch.setattr(ttwid_module, "_ttwid_scopes", set())


def _prime_bucket(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
    proxy_addr: str | None = None,
    *,
    age: float = 0.0,
) -> None:
    # 构造「某出口已有缓存」的前置态：镜像与分桶成对写（与生产写入口 _cache_ttwid 同形），
    # 只写其中一个就是在测一个生产到不了的状态，快路的镜像判空前置也会被绕开。
    ttwid_module._cached_ttwid_by_proxy[proxy_addr or ""] = (value, time.monotonic() - age)
    monkeypatch.setattr(ttwid_module, "_cached_ttwid", value)


# _app_root 定位配置根目录：普通运行取脚本旁 config/，frozen 运行取可执行文件目录。
# 正确解析是后续所有配置读取的基础。
class TestAppRoot:
    def test_returns_string(self) -> None:
        result = _app_root()
        assert isinstance(result, str)
        assert len(result) > 0


# _read_config_ttwid 从 config.ini 读取预置 ttwid：须正确处理前缀、空值、缺失配置。
# 守卫"不写出空/重复前缀 ttwid"的脏数据。
class TestReadConfigTtwid:
    def test_no_config_returns_empty(self) -> None:
        # 配置目录不存在时须返回空串而非抛异常（首次运行 / 未填 ttwid 配置的常态）
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
        # 配置已带 ttwid= 前缀时不得重复拼接，否则会变成 "ttwid=ttwid=xyz789"
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = ttwid=xyz789\n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == "ttwid=xyz789"

    def test_empty_ttwid_returns_empty(self, tmp_path: Path) -> None:
        # ttwid 值为空（占位未填）必须返回空串，避免写出 "ttwid=" 空值被当成有效 cookie
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "config.ini"
        config_file.write_text("[Cookie]\nttwid = \n", encoding="utf-8-sig")
        with patch("src.ttwid._app_root", return_value=str(tmp_path)):
            result = _read_config_ttwid()
            assert result == ""


class TestFetchTtwid:
    @pytest.mark.asyncio
    async def test_success(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        # async_req 返回含 ttwid 的 cookies，须拼成 "ttwid=<value>" 并写入模块级缓存
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
        # 响应无 ttwid 字段（风控页/异常页）时必须返回空，而非拼出 "ttwid=" 空值伪装成有效
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
    @pytest.mark.asyncio
    async def test_cached_returns_directly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 后「非空」不再等于「永久有效」：命中必须同时满足「未过 TTL」，
        # 故此处要连获取时刻一起写（只写值 = 陈旧 = 应当重新拉取，见下方 TTL 用例）。
        # 后「值 + 时刻」存放在按出口分列的 dict 里，故用 _prime_bucket 成对写。
        _prime_bucket(monkeypatch, "ttwid=cached_value")
        result = await get_ttwid()
        assert result == "ttwid=cached_value"

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
    def test_success(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()
        # warmup 在程序启动时预取并缓存 ttwid，避免首帧录制才拉取造成开播延迟
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
            # get_ttwid 抛异常时 warmup 必须吞掉、不得冒泡
            warmup_ttwid()


class TestAppRootFrozen:
    # _app_root 的 frozen 分支（PyInstaller 冻结运行）仅在 sys.frozen=True 时执行，
    # 单测默认不触发，这里显式 patch 覆盖，避免该分支永久处于零覆盖。
    # frozen 模式须返回可执行文件所在目录，与开发态（脚本目录）区分
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
        # _cache_fetch_cookies 抛异常时须记 warning 并返回空，不冒泡影响录制启动
        with patch(
            "src.ttwid._cache_fetch_cookies",
            new_callable=AsyncMock,
            side_effect=Exception("net down"),
        ):
            result = await _fetch_ttwid()
            assert result == ""
        ttwid_module._cached_ttwid = ""


# get_ttwid 的并发去重语义：cookie_cache.singleflight（锁内零 await、等待者经 future
#   复用结果）保证并发 N 个 get_ttwid 只打一次 _fetch_ttwid、且所有调用方拿到同一份结果
#   （原实现用 _ttwid_lock 跨 await 持锁达到同一效果，代价是跨房间阻塞事件循环）。
#   若 singleflight 退化成各自拉取，fetch 次数会 >1，用例失败。
# [历史注] 早先以「假锁 acquire 恒 False」模拟锁竞争来覆盖兜底分支，
#   改用 singleflight 后「锁竞争」场景不存在、该旧断言已随之移除。
class TestGetTtwidSingleflight:
    @pytest.mark.asyncio
    async def test_concurrent_calls_fetch_once(self) -> None:
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()

        calls = 0

        async def _fake_fetch(proxy_addr: object = None) -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)  # 制造窗口，让并发调用都能进入等待队列
            return "ttwid=once"

        with (
            patch("src.ttwid._fetch_ttwid", new=_fake_fetch),
            patch("src.ttwid._read_config_ttwid", return_value=""),
        ):
            results = await asyncio.gather(*[get_ttwid() for _ in range(5)])

        assert calls == 1, f"singleflight 去重失效：_fetch_ttwid 被调用 {calls} 次"
        assert all(r == "ttwid=once" for r in results)
        ttwid_module._cached_ttwid = ""

    @pytest.mark.asyncio
    async def test_config_ttwid_bypasses_network(self) -> None:
        # 配置优先：用户手填 ttwid 时不进 singleflight，不发任何网络请求
        ttwid_module._cached_ttwid = ""
        clear_cookie_cache()

        async def _boom(proxy_addr: object = None) -> str:
            raise AssertionError("配置优先时不应发起网络请求")

        with (
            patch("src.ttwid._fetch_ttwid", new=_boom),
            patch("src.ttwid._read_config_ttwid", return_value="ttwid=from_config"),
        ):
            result = await get_ttwid()

        assert result == "ttwid=from_config"
        ttwid_module._cached_ttwid = ""


# ── ：模块全局 ttwid 的 TTL 与显式失效入口 ────────────────────────────
# 旧语义是「非空即永久返回」：抖音一旦作废 ttwid（风控常见形态），本进程不重启就
# 再也不重新获取，表现为抖音解析长期「HTTP 200 + 空响应体」，而 cookie_cache 的
# 30 分钟自愈在这层根本不参与判定（对照 src/room.py 的 sec_uid 缓存）。
class TestTtwidTtl:
    @pytest.mark.asyncio
    async def test_fresh_global_short_circuits_without_network(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _prime_bucket(monkeypatch, "ttwid=fresh")

        async def _boom(*args: object, **kwargs: object) -> str:
            raise AssertionError("TTL 内命中缓存不得再发网络请求")

        monkeypatch.setattr(ttwid_module, "_fetch_ttwid", _boom)
        assert await get_ttwid() == "ttwid=fresh"

    @pytest.mark.asyncio
    async def test_stale_global_triggers_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 超过 TTL 的缓存值必须被丢弃并重新拉取（这正是「被作废后自愈」的主路径）
        _prime_bucket(
            monkeypatch,
            "ttwid=stale",
            age=ttwid_module._TTWID_TTL_SECONDS + 1,
        )
        monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")
        clear_cookie_cache()

        async def _fetch(proxy_addr: object = None) -> str:
            return "ttwid=refreshed"

        monkeypatch.setattr(ttwid_module, "_fetch_ttwid", _fetch)
        assert await get_ttwid() == "ttwid=refreshed"
        assert ttwid_module._cached_ttwid == "ttwid=refreshed"
        # 重新缓存后要重新计时（否则每轮都判陈旧 → 退化成完全不缓存）
        assert time.monotonic() - ttwid_module._cached_ttwid_by_proxy[""][1] < 5

    @pytest.mark.asyncio
    async def test_invalidate_purges_global_and_both_cache_layers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 三层都要清：模块全局 / generic singleflight / 同网址 cookie 缓存。
        # 只清全局的话，下一轮 singleflight 命中同一份旧值——该描述的「失效只
        # 生效一半」，故本用例断言的是「作废后确实拿到了新的凭据」。
        monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")
        clear_cookie_cache()
        values = iter(["first", "second"])  # _fetch_ttwid 自己会拼 "ttwid=" 前缀
        calls: list[int] = []

        async def _fake_req(**kwargs: object) -> dict[str, str]:
            calls.append(1)
            return {"ttwid": next(values)}

        monkeypatch.setattr(ttwid_module, "async_req", _fake_req)

        assert await get_ttwid() == "ttwid=first"
        ttwid_module.invalidate_ttwid()
        assert ttwid_module._cached_ttwid == ""
        assert await get_ttwid() == "ttwid=second"
        assert len(calls) == 2, f"失效后未重新拉取（被下层缓存喂回旧值）: {calls}"

    def test_invalidate_is_safe_before_any_fetch(self) -> None:
        # 未拉取过时调用不得抛错（弹幕侧的失败处理路径可能先于任何成功获取）
        ttwid_module.invalidate_ttwid()
        assert ttwid_module._cached_ttwid == ""

    @pytest.mark.asyncio
    async def test_invalidate_accepts_proxy_addr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")
        clear_cookie_cache()
        cookies = {"ttwid": "with-proxy"}

        async def _fake_req(**kwargs: object) -> dict[str, str]:
            return cookies

        monkeypatch.setattr(ttwid_module, "async_req", _fake_req)
        assert await get_ttwid("127.0.0.1:10808") == "ttwid=with-proxy"
        ttwid_module.invalidate_ttwid("127.0.0.1:10808")
        assert "douyin_ttwid|127.0.0.1:10808" not in cc_generic_keys()
        cookies["ttwid"] = "with-proxy-2"
        assert await get_ttwid("127.0.0.1:10808") == "ttwid=with-proxy-2"


def cc_generic_keys() -> set[str]:
    import src.cookie_cache as cc_module

    return set(cc_module._generic_cache)
