# Tests for src/spider.py 批次4修复 - 平台解析健壮性回归测试.
# 多数用例直接调用装饰器的 __wrapped__ 原函数，以便断言精确返回/异常，
# 不被 trace_error_decorator 的「吞异常返回未直播」掩盖。

import asyncio
import json
import subprocess
import threading
import types
from unittest.mock import AsyncMock, patch

import pytest

from src import spider as sp
from src.cookie_cache import clear as clear_cookie_cache


class TestVvxqiu:
    async def test_empty_playlist_response_not_live(self):
        raw = sp.get_vvxqiu_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=AsyncMock(side_effect=['{"data": {"anchorName": "N"}}', ""])):
            result = await raw("https://x/?roomId=123456")
        assert result["is_live"] is False
        assert "record_url" not in result

    async def test_missing_room_id_not_live_no_extra_request(self):
        raw = sp.get_vvxqiu_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=AsyncMock(return_value='{"data": {"anchorName": "N"}}')) as mock:
            result = await raw("https://h5p.vvxqiu.com/live")
        assert result["is_live"] is False
        assert mock.await_count == 1  # 房间号缺失时不再请求 m3u8

    async def test_live_when_playlist_found(self):
        raw = sp.get_vvxqiu_stream_url.__wrapped__
        with patch.object(
            sp,
            "async_req",
            new=AsyncMock(side_effect=['{"data": {"anchorName": "N"}}', "#EXTM3U\nhttps://cdn/x.m3u8"]),
        ):
            result = await raw("https://x/?roomId=123456")
        assert result["is_live"] is True
        assert result["m3u8_url"]


class TestMigu:
    @staticmethod
    def _basic_json() -> str:
        return json.dumps(
            {
                "body": {
                    "title": "T",
                    "detailPageTitle": "D",
                    "pId": "1",
                    "content": {"currentLive": "1"},
                    "urlInfo": {"url": "https://x.miguvideo.com/abc.m3u8"},
                }
            }
        )

    async def test_subprocess_failure_converts_to_program_error(self):
        # 此前 CalledProcessError 未被捕获；现转为 ProgramError 且 subprocess 带 30s 超时
        captured: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> types.SimpleNamespace:
            captured.update(kwargs)
            raise subprocess.CalledProcessError(1, ["node"])

        raw = sp.get_migu_stream_url.__wrapped__
        with (
            patch.object(sp, "async_req", new=AsyncMock(return_value=self._basic_json())),
            patch.object(sp.subprocess, "run", side_effect=fake_run),
        ):
            with pytest.raises(sp.ProgramError):
                await raw("https://x/123")
        assert captured.get("timeout") == 30

    async def test_redirect_failure_returns_not_live(self):
        async def fake_req(url: str, **kwargs: object) -> str:
            if kwargs.get("redirect_url"):
                return ""  # 重定向失败
            return self._basic_json()

        def fake_run(*args: object, **kwargs: object) -> types.SimpleNamespace:
            return types.SimpleNamespace(stdout="dd\n")

        raw = sp.get_migu_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=fake_req), patch.object(sp.subprocess, "run", new=fake_run):
            result = await raw("https://x/123")
        assert result["is_live"] is False
        assert "record_url" not in result

    async def test_title_none_no_crash(self):
        body_without_title = json.dumps(
            {
                "body": {
                    "pId": "1",
                    "content": {"currentLive": "1"},
                    "urlInfo": {"url": "https://x.miguvideo.com/abc.m3u8"},
                }
            }
        )

        async def fake_req(url: str, **kwargs: object) -> str:
            if kwargs.get("redirect_url"):
                return "https://x/real.m3u8"
            return body_without_title

        def fake_run(*args: object, **kwargs: object) -> types.SimpleNamespace:
            return types.SimpleNamespace(stdout="dd\n")

        raw = sp.get_migu_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=fake_req), patch.object(sp.subprocess, "run", new=fake_run):
            result = await raw("https://x/123")
        assert result["is_live"] is True
        assert result["anchor_name"] == ""  # title 为 None 时不再 TypeError


class TestFaceit:
    async def test_twitch_delegation_passes_proxy_and_cookies(self):
        async def fake_req(url: str, **kwargs: object) -> str:
            if "nicknames" in url:
                return '{"payload": {"id": "uid1"}}'
            return '{"payload": [{"userNickname": "N", "platformId": "tid1", "platform": "twitch"}]}'

        raw = sp.get_faceit_stream_data.__wrapped__
        with (
            patch.object(sp, "async_req", new=fake_req),
            patch.object(sp, "get_twitchtv_stream_data", new=AsyncMock(return_value={"is_live": True})) as mock_twitch,
        ):
            result = await raw("https://www.faceit.com/players/abc/stream", proxy_addr="http://p:1", cookies="c=1")
        assert result["is_live"] is True
        assert result["anchor_name"] == "N"
        mock_twitch.assert_awaited_once_with("https://www.twitch.tv/tid1", "http://p:1", "c=1")


class TestShopee:
    async def test_redirect_failure_uses_full_tld_suffix(self):
        # shopee.co.id 重定向失败时仍应拼出 live.shopee.co.id 而非 live.shopee.shopee
        seen_urls: list[str] = []

        async def fake_req(url: str, **kwargs: object) -> str:
            seen_urls.append(url)
            if kwargs.get("redirect_url"):
                return ""
            if "/session/" in url:
                return '{"data": null}'
            return "{}"

        raw = sp.get_shopee_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=fake_req):
            result = await raw("https://shopee.co.id/live")
        assert result["is_live"] is False
        session_url = [u for u in seen_urls if "/session/" in u][0]
        assert "live.shopee.co.id" in session_url

    async def test_malformed_url_returns_not_live(self):
        raw = sp.get_shopee_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=AsyncMock(return_value="")):
            result = await raw("not-a-url")
        assert result["is_live"] is False


class TestZhihu:
    async def test_no_drama_returns_not_live(self):
        raw = sp.get_zhihu_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=AsyncMock(return_value='{"drama": null}')) as mock:
            result = await raw("https://www.zhihu.com/people/abc")
        assert result == {"anchor_name": "", "is_live": False}
        assert mock.await_count == 1  # 未开播时不再继续请求


class TestWeibo:
    async def test_malformed_url_raises(self):
        raw = sp.get_weibo_stream_data.__wrapped__
        with pytest.raises(RuntimeError):
            await raw("https://weibo.com/12345")


class TestTwitcasting:
    async def test_malformed_url_raises(self):
        raw = sp.get_twitcasting_stream_url.__wrapped__
        with pytest.raises(RuntimeError):
            await raw("https://twitcasting.tv")


class TestLianjie:
    async def test_bad_webrtc_url_returns_not_live(self):
        room_json = json.dumps(
            {"data": {"nickname": "N", "isonline": 1, "defaultRoomTitle": "T", "videoUrl": "http://x/plain"}}
        )
        raw = sp.get_lianjie_stream_url.__wrapped__
        with patch.object(sp, "async_req", new=AsyncMock(return_value=room_json)):
            result = await raw("https://show.lailianjie.com/room1")
        assert result["is_live"] is False
        assert "record_url" not in result


class TestCacheLocks:
    def test_kuaishou_did_fetched_once_under_concurrency(self):
        # 多线程并发首轮请求只拉取一次（锁二次检查回归）
        sp._cached_kuaishou_did = ""
        clear_cookie_cache()  # 隔离统一 cookie 缓存单例，确保本测试真正发起拉取
        call_count = 0
        count_lock = threading.Lock()

        async def fake_req(**kwargs: object) -> dict[str, str]:
            nonlocal call_count
            with count_lock:
                call_count += 1
            await asyncio.sleep(0.05)
            return {"did": "abc", "didv": "def"}

        def run() -> None:
            asyncio.run(sp._ensure_kuaishou_did())

        # _ensure_kuaishou_did 现经统一 cookie 缓存(src.cookie_cache) 从快手主页拉取，
        # 通过传入本模块 async_req 作为 fetcher 复用缓存，故此处仍 patch sp.async_req
        with patch.object(sp, "async_req", new=fake_req):
            threads = [threading.Thread(target=run) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
        assert call_count == 1
        assert sp._cached_kuaishou_did == "did=abc; didv=def"

    def test_twitch_client_id_fetched_once_under_concurrency(self):
        sp._cached_twitch_client_id = ""
        call_count = 0
        count_lock = threading.Lock()

        async def fake_req(**kwargs: object) -> str:
            nonlocal call_count
            with count_lock:
                call_count += 1
            await asyncio.sleep(0.05)
            return '<html>"Client-ID" : "abcdefghijklmnopqrstuv"</html>'

        def run() -> None:
            asyncio.run(sp._ensure_twitch_client_id())

        with patch.object(sp, "async_req", new=fake_req):
            threads = [threading.Thread(target=run) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)
        assert call_count == 1
        assert sp._cached_twitch_client_id == "abcdefghijklmnopqrstuv"
