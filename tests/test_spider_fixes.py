# Tests for src/spider.py 批次4修复 - 平台解析健壮性回归测试.
# 多数用例直接调用装饰器的 __wrapped__ 原函数，以便断言精确返回/异常，
# 不被 trace_error_decorator 的「吞异常返回未直播」掩盖。
# 单测聚焦「解析失败/边界输入不得崩溃或误判开播」，覆盖 vvxqiu/migu/faceit/shopee/zhihu/weibo/twitcasting/lianjie 及并发取凭据。

import asyncio
import json
import subprocess
import threading
import types
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from src import spider as sp
from src.cookie_cache import clear as clear_cookie_cache


def _unwrap(func: object) -> Any:
    # 取 trace_error_decorator 装饰后的原函数：装饰器经 functools.wraps 保留
    # __wrapped__，但静态类型不可见，统一经 getattr 取用（返回 Any 以便直接调用）
    return cast(Any, getattr(func, "__wrapped__"))


# vvxqiu 解析：房间号缺失/播放列表空须判未直播，出现 m3u8 即判开播
# vvxqiu 解析：房间号缺失/播放列表空须判未直播，出现 m3u8 即判开播
class TestVvxqiu:
    # vvxqiu 解析：房间号缺失/播放列表空须判未直播，出现 m3u8 即判开播
    # 空播放列表响应（仅 anchorName 无 m3u8）须判未直播且不产出 record_url，避免误判开播
    async def test_empty_playlist_response_not_live(self) -> None:
        raw = _unwrap(sp.get_vvxqiu_stream_url)
        with patch.object(sp, "async_req", new=AsyncMock(side_effect=['{"data": {"anchorName": "N"}}', ""])):
            result = await raw("https://x/?roomId=123456")
        assert result["is_live"] is False
        assert "record_url" not in result

    # 房间号缺失时直接判未直播，且不得再发 m3u8 探测请求（省一次网络）
    # roomId 缺失时 vvxqiu 不应对空房间号发起第二次 m3u8 探测：省一次网络也避免对无效房间误判开播
    # roomId 缺失时 vvxqiu 不应对空房间号发起第二次 m3u8 探测：省一次网络也避免对无效房间误判开播
    async def test_missing_room_id_not_live_no_extra_request(self) -> None:
        raw = _unwrap(sp.get_vvxqiu_stream_url)
        with patch.object(sp, "async_req", new=AsyncMock(return_value='{"data": {"anchorName": "N"}}')) as mock:
            result = await raw("https://h5p.vvxqiu.com/live")
        assert result["is_live"] is False
        assert mock.await_count == 1  # 房间号缺失时不再请求 m3u8

    # 播放列表出现 m3u8 即判开播，并产出 m3u8_url 供后续选源
    # 出现 m3u8 即视为有效直播源；该用例守护「播放列表解析→开播判定」的映射不遗漏
    # 出现 m3u8 即视为有效直播源；该用例守护「播放列表解析→开播判定」的映射不遗漏
    async def test_live_when_playlist_found(self) -> None:
        raw = _unwrap(sp.get_vvxqiu_stream_url)
        with patch.object(
            sp,
            "async_req",
            new=AsyncMock(side_effect=['{"data": {"anchorName": "N"}}', "#EXTM3U\nhttps://cdn/x.m3u8"]),
        ):
            result = await raw("https://x/?roomId=123456")
        # 播放列表出现 m3u8 即判定开播，并产出 m3u8_url 供后续选源
        assert result["is_live"] is True
        assert result["m3u8_url"]


# migu 解析：node 脚本取重定向地址，须屏蔽 CalledProcessError、重定向失败判未直播、title 为 None 不崩
# migu 解析：node 脚本取重定向地址，须屏蔽 CalledProcessError、重定向失败判未直播、title 为 None 不崩
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

    # node 脚本执行失败（CalledProcessError）须转 domain ProgramError 而非抛出原始异常，且 subprocess 带 30s 超时防止 migu.js 卡死拖垮轮询
    # node 脚本执行失败（CalledProcessError）须转 domain ProgramError 而非抛出原始异常，且 subprocess 带 30s 超时防止 migu.js 卡死拖垮轮询
    async def test_subprocess_failure_converts_to_program_error(self) -> None:
        # 此前 CalledProcessError 未被捕获；现转为 ProgramError 且 subprocess 带 30s 超时
        captured: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> types.SimpleNamespace:
            captured.update(kwargs)
            raise subprocess.CalledProcessError(1, ["node"])

        raw = _unwrap(sp.get_migu_stream_url)
        with (
            patch.object(sp, "async_req", new=AsyncMock(return_value=self._basic_json())),
            patch.object(sp.subprocess, "run", side_effect=fake_run),
        ):
            with pytest.raises(sp.ProgramError):
                await raw("https://x/123")
        assert captured.get("timeout") == 30

    # migu.js 重定向解析失败（拿不到最终 m3u8 地址）→ 判未直播，不产出 record_url
    # migu.js 重定向解析失败（拿不到最终 m3u8 地址）→ 判未直播，不产出 record_url
    async def test_redirect_failure_returns_not_live(self) -> None:
        async def fake_req(url: str, **kwargs: object) -> str:
            if kwargs.get("redirect_url"):
                return ""  # 重定向失败
            return self._basic_json()

        def fake_run(*args: object, **kwargs: object) -> types.SimpleNamespace:
            # migu.js（2026-08 重写版）输出带 ddCalcu/sv 参数的完整地址（而非仅 ddCalcu 值）
            return types.SimpleNamespace(stdout="https://x.miguvideo.com/abc.m3u8&ddCalcu=dd&sv=119\n")

        raw = _unwrap(sp.get_migu_stream_url)
        with patch.object(sp, "async_req", new=fake_req), patch.object(sp.subprocess, "run", new=fake_run):
            result = await raw("https://x/123")
        # 重定向解析失败（拿不到最终 m3u8 地址）→ 判未直播，不产出 record_url
        assert result["is_live"] is False
        assert "record_url" not in result

    # body 缺 title 字段时不得 TypeError：title 当空串处理，守护「主播名可选」的逆向兼容
    # body 缺 title 字段时不得 TypeError：title 当空串处理，守护「主播名可选」的逆向兼容
    async def test_title_none_no_crash(self) -> None:
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

        raw = _unwrap(sp.get_migu_stream_url)
        with patch.object(sp, "async_req", new=fake_req), patch.object(sp.subprocess, "run", new=fake_run):
            result = await raw("https://x/123")
        assert result["is_live"] is True
        assert result["anchor_name"] == ""  # title 为 None 时不再 TypeError


class TestFaceit:
    # faceit 解析：委托 twitch 取流，须把代理与 cookie 透传给下游 twitch 解析
    async def test_twitch_delegation_passes_proxy_and_cookies(self) -> None:
        async def fake_req(url: str, **kwargs: object) -> str:
            if "nicknames" in url:
                return '{"payload": {"id": "uid1"}}'
            return '{"payload": [{"userNickname": "N", "platformId": "tid1", "platform": "twitch"}]}'

        raw = _unwrap(sp.get_faceit_stream_data)
        with (
            patch.object(sp, "async_req", new=fake_req),
            patch.object(sp, "get_twitchtv_stream_data", new=AsyncMock(return_value={"is_live": True})) as mock_twitch,
        ):
            result = await raw("https://www.faceit.com/players/abc/stream", proxy_addr="http://p:1", cookies="c=1")
        assert result["is_live"] is True
        assert result["anchor_name"] == "N"
        mock_twitch.assert_awaited_once_with("https://www.twitch.tv/tid1", "http://p:1", "c=1")


class TestShopee:
    # shopee 解析：重定向拼接须用完整 TLD 后缀，畸形/重定向失败 URL 须判未直播
    # 重定向拼接必须用完整 TLD 后缀；否则会出现 live.shopee.shopee 这类非法域名
    async def test_redirect_failure_uses_full_tld_suffix(self) -> None:
        # shopee.co.id 重定向失败时仍应拼出 live.shopee.co.id 而非 live.shopee.shopee
        seen_urls: list[str] = []

        async def fake_req(url: str, **kwargs: object) -> str:
            seen_urls.append(url)
            if kwargs.get("redirect_url"):
                return ""
            if "/session/" in url:
                return '{"data": null}'
            return "{}"

        raw = _unwrap(sp.get_shopee_stream_url)
        with patch.object(sp, "async_req", new=fake_req):
            result = await raw("https://shopee.co.id/live")
        assert result["is_live"] is False
        session_url = [u for u in seen_urls if "/session/" in u][0]
        assert "live.shopee.co.id" in session_url

    async def test_malformed_url_returns_not_live(self) -> None:
        raw = _unwrap(sp.get_shopee_stream_url)
        with patch.object(sp, "async_req", new=AsyncMock(return_value="")):
            result = await raw("not-a-url")
        # URL 解析失败必须判未直播而非抛异常（下游轮询可安全跳过该房间）
        assert result["is_live"] is False


# zhihu 解析：无 drama（未开播）即判未直播且不发多余请求。
class TestZhihu:
    # zhihu 无 drama（未开播）即判未直播且不发多余请求，避免空转探测浪费配额
    async def test_no_drama_returns_not_live(self) -> None:
        raw = _unwrap(sp.get_zhihu_stream_url)
        with patch.object(sp, "async_req", new=AsyncMock(return_value='{"drama": null}')) as mock:
            result = await raw("https://www.zhihu.com/people/abc")
        assert result == {"anchor_name": "", "is_live": False}
        assert mock.await_count == 1  # 未开播时不再继续请求


# weibo 解析：畸形 URL 必须抛 RuntimeError 而非静默返回，交由上层跳过
# weibo 解析：畸形 URL 必须抛 RuntimeError 而非静默返回，交由上层跳过
class TestWeibo:
    async def test_malformed_url_raises(self) -> None:
        raw = _unwrap(sp.get_weibo_stream_data)
        with pytest.raises(RuntimeError):
            await raw("https://weibo.com/12345")


class TestTwitcasting:
    # 非法 twitcasting URL（缺用户路径段）必须抛 RuntimeError 而非静默返回
    async def test_malformed_url_raises(self) -> None:
        raw = _unwrap(sp.get_twitcasting_stream_url)
        # 非法 twitcasting URL（缺用户路径段）必须抛 RuntimeError 而非静默返回
        with pytest.raises(RuntimeError):
            await raw("https://twitcasting.tv")


class TestLianjie:
    # WebRTC 房间但 videoUrl 非流地址须判未直播，而非用该地址尝试拉流
    async def test_bad_webrtc_url_returns_not_live(self) -> None:
        room_json = json.dumps(
            {"data": {"nickname": "N", "isonline": 1, "defaultRoomTitle": "T", "videoUrl": "http://x/plain"}}
        )
        raw = _unwrap(sp.get_lianjie_stream_url)
        with patch.object(sp, "async_req", new=AsyncMock(return_value=room_json)):
            result = await raw("https://show.lailianjie.com/room1")
        assert result["is_live"] is False
        # WebRTC 房间但 videoUrl 为非流地址（plain）须判未直播，而非尝试用该地址拉流
        assert "record_url" not in result


# 并发取凭据：快手 did / twitch client_id 在多线程首轮须各只拉取一次（锁二次检查）。
# 守卫统一 cookie 缓存接入后的并发去重不回退。
class TestCacheLocks:
    # 快手 did 经统一 cookie 缓存从主页拉取：并发首轮须仅一次网络，回归锁二次检查
    # 快手 did 经统一 cookie 缓存从主页拉取：并发首轮须仅一次网络，回归锁二次检查
    # 快手 did 经统一 cookie 缓存从主页拉取：并发首轮须仅一次网络，回归锁二次检查
    def test_kuaishou_did_fetched_once_under_concurrency(self) -> None:
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
                t.join(timeout=10)  # timeout=10 远大于 fake 的 0.05s 睡眠，仅作防死锁兜底
        assert call_count == 1
        assert sp._cached_kuaishou_did == "did=abc; didv=def"

    def test_twitch_client_id_fetched_once_under_concurrency(self) -> None:
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
