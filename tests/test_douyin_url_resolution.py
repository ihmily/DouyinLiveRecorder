"""Tests for Douyin URL resolution across the 5 supported URL formats.

Formats under test (see user request):
  1. https://live.douyin.com/745964462470            (网页端主播直播间)
  2. https://v.douyin.com/iQFeBnt/                  (app端主播直播间)
  3. https://live.douyin.com/yall1102               (抖音号拼接, 支持 VR)
  4. https://v.douyin.com/CeiU5cbX                  (app端主播主页)
  5. https://www.douyin.com/user/MS4w...            (网页端主播主页)
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src import room, spider
from src.room import UnsupportedUrlError, extract_sec_user_id


@pytest.fixture(autouse=True)
def _clear_sec_uid_cache():
    # 进程级 sec_user_id->抖音号 缓存在测试间共享（同进程），清空以避免跨用例污染
    room._SEC_UID_UNIQUE_CACHE.clear()
    yield
    room._SEC_UID_UNIQUE_CACHE.clear()


SEC_UID = "MS4wLjABAAAASGMSxxCNSLh6Obfutqd_VtTnfp0cLgfhAeT9kpJb9Ar8D9_WMFSez95isGmiKAKm"


# ---------------------------------------------------------------------------
# 测试替身：模拟 httpx.AsyncClient
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, url: str = "", text: str = "", json_data: object = None, json_raises: bool = False):
        self.url = url
        self.text = text
        self._json_data = json_data
        self._json_raises = json_raises

    def json(self) -> object:
        if self._json_raises:
            # 抖音风控对旧移动端 UA 返回 HTTP 200 但空响应体，json() 会抛错
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._json_data


class _FakeClient:
    """记录所有请求，并按 handler 返回预设响应。"""

    def __init__(self, handler):
        self._handler = handler
        self.requests: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> bool:
        return False

    async def get(self, url, headers=None, follow_redirects=False):
        self.requests.append((url, dict(headers or {})))
        return self._handler(url)


def _patch_client(handler):
    """把 src.room 中的 httpx.AsyncClient 替换为返回 _FakeClient 的工厂。"""
    client = _FakeClient(handler)
    return client, patch("src.room.httpx.AsyncClient", lambda **_kwargs: client)


# ---------------------------------------------------------------------------
# 1) sec_user_id 提取
# ---------------------------------------------------------------------------


class TestExtractSecUserId:
    """主页链接 -> sec_user_id 的提取，覆盖三种真实形态。"""

    def test_web_user_page(self):
        """格式 5：网页端主页路径。"""
        assert extract_sec_user_id(f"https://www.douyin.com/user/{SEC_UID}") == SEC_UID

    def test_share_user_page_with_query(self):
        """格式 4：v.douyin.com 短链重定向后的 iesdouyin 分享页（带大量查询参数）。"""
        url = f"https://www.iesdouyin.com/share/user/{SEC_UID}?from_aid=1128&sec_uid={SEC_UID}&from_ssr=1"
        assert extract_sec_user_id(url) == SEC_UID

    def test_trailing_slash_not_empty(self):
        """回归：原 rsplit('/') 实现遇到尾斜杠会取到空串。"""
        assert extract_sec_user_id(f"https://www.douyin.com/user/{SEC_UID}/") == SEC_UID

    def test_sec_uid_query_param_preferred(self):
        """路径无法识别时，回退到 sec_uid 查询参数。"""
        assert extract_sec_user_id(f"https://www.douyin.com/share?sec_uid={SEC_UID}&x=1") == SEC_UID


# ---------------------------------------------------------------------------
# 2) get_unique_id —— 主页链接解析为抖音号
# ---------------------------------------------------------------------------


class TestGetUniqueId:
    """主页链接 -> 抖音号，主路径为 JSON 接口，HTML 为兜底。"""

    @pytest.mark.asyncio
    async def test_resolves_via_json_api(self):
        """主路径：JSON 接口返回 unique_id。"""

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_data={"status_code": 0, "user_info": {"unique_id": "47884081925"}})
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            result = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        assert result == "47884081925"
        # 不应再去抓已失效的分享页 HTML
        assert not any("/share/user/" in url for url, _ in client.requests)

    @pytest.mark.asyncio
    async def test_json_api_uses_desktop_ua(self):
        """回归：接口对 UA 敏感，旧移动端 UA 会被风控返回空响应体，必须用桌面端 UA。"""

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_data={"user_info": {"unique_id": "47884081925"}})
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            _ = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        api_headers = next(h for url, h in client.requests if "/web/api/v2/user/info/" in url)
        assert api_headers["User-Agent"] == room.DESKTOP_UA
        assert "Android" not in api_headers["User-Agent"]

    @pytest.mark.asyncio
    async def test_falls_back_to_short_id_when_unique_id_empty(self):
        """部分账号未设置抖音号，unique_id 为空时退回 short_id。"""

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_data={"user_info": {"unique_id": "", "short_id": "123456"}})
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        _client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            result = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        assert result == "123456"

    @pytest.mark.asyncio
    async def test_falls_back_to_html_when_api_returns_empty_body(self):
        """接口被风控返回空响应体时，降级到分享页 HTML 正则。"""

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_raises=True)
            if "/share/user/" in url:
                return _FakeResponse(url=url, text='{"unique_id":"legacy_id","verification_type":1}')
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        _client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            result = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        assert result == "legacy_id"

    @pytest.mark.asyncio
    async def test_raises_when_both_paths_fail(self):
        """接口与 HTML 均失败时抛出可读错误，而非静默返回 None。"""

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_raises=True)
            if "/share/user/" in url:
                return _FakeResponse(url=url, text="<html><body></body></html>")
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        _client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            with pytest.raises(RuntimeError, match="Could not resolve unique_id"):
                _ = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

    @pytest.mark.asyncio
    async def test_reflow_url_raises_unsupported(self):
        """重定向到 reflow/（直播间分享码）时交回 get_sec_user_id 处理。"""

        def handler(url: str):
            return _FakeResponse(url="https://webcast.amemv.com/webcast/reflow/7318293442?sec_user_id=MS4w")

        _client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            with pytest.raises(UnsupportedUrlError):
                _ = await room.get_unique_id("https://v.douyin.com/iQFeBnt/")

    @pytest.mark.asyncio
    async def test_module_headers_not_mutated(self):
        """回归：不得就地修改模块级共享 HEADERS（多线程下会互相污染）。"""
        original = dict(room.HEADERS)

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                return _FakeResponse(url=url, json_data={"user_info": {"unique_id": "47884081925"}})
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        _client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            _ = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        assert room.HEADERS == original

    @pytest.mark.asyncio
    async def test_cache_eliminates_repeat_api_request(self):
        """优化：同一 sec_user_id 在轮询中重复解析时，第二次应命中进程级缓存、不再请求 iesdouyin 接口。"""
        call_count = {"api": 0}

        def handler(url: str):
            if "/web/api/v2/user/info/" in url:
                call_count["api"] += 1
                return _FakeResponse(url=url, json_data={"user_info": {"unique_id": "47884081925"}})
            return _FakeResponse(url=f"https://www.douyin.com/user/{SEC_UID}")

        client, client_patch = _patch_client(handler)
        with client_patch, patch("src.room._ensure_douyin_ttwid", new_callable=AsyncMock, return_value="ttwid=fake"):
            first = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")
            second = await room.get_unique_id(f"https://www.douyin.com/user/{SEC_UID}")

        assert first == second == "47884081925"
        # 第二次解析命中缓存：iesdouyin 接口仅被请求一次
        assert call_count["api"] == 1


# ---------------------------------------------------------------------------
# 3) get_douyin_web_stream_data —— 格式 1 (数字房间) & 格式 3 (抖音号, VR)
# ---------------------------------------------------------------------------


class TestGetDouyinWebStreamData:
    """测试网页端接口，覆盖数字房间号与抖音号（VR）两种 live.douyin.com 形态。"""

    @pytest.mark.asyncio
    async def test_numeric_room_id_uses_web_enter_api(self):
        """格式 1：数字房间号直接走 web/enter API 并返回房间数据。"""
        api_json = (
            '{"status_code":0,"data":{"data":[{"status":4,"id":"745964462470"}],' '"user":{"nickname":"数字房间主播"}}}'
        )
        mock_req = AsyncMock(side_effect=[api_json])
        with patch("src.spider.async_req", mock_req):
            result = await spider.get_douyin_web_stream_data(
                "https://live.douyin.com/745964462470", cookies="ttwid=fake"
            )
        assert result.get("anchor_name") == "数字房间主播"
        called_url = mock_req.call_args.kwargs["url"]
        assert "web_rid=745964462470" in called_url

    @pytest.mark.asyncio
    async def test_douyin_number_passed_directly_as_web_rid(self):
        """格式 3：web/enter 接口直接接受抖音号，不应发起额外的重定向解析请求。"""
        api_json = '{"status_code":0,"data":{"data":[{"status":4,"id":"745964462470"}],"user":{"nickname":"VR主播"}}}'
        mock_req = AsyncMock(side_effect=[api_json])
        with patch("src.spider.async_req", mock_req):
            result = await spider.get_douyin_web_stream_data("https://live.douyin.com/yall1102", cookies="ttwid=fake")

        assert result.get("anchor_name") == "VR主播"
        # 仅一次请求（web/enter），且直接使用抖音号作为 web_rid
        assert mock_req.await_count == 1
        assert "web_rid=yall1102" in mock_req.call_args.kwargs["url"]

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped_from_web_rid(self):
        """URL 末尾斜杠不应混入 web_rid。"""
        api_json = '{"status_code":0,"data":{"data":[{"status":4}],"user":{"nickname":"主播"}}}'
        mock_req = AsyncMock(side_effect=[api_json])
        with patch("src.spider.async_req", mock_req):
            _ = await spider.get_douyin_web_stream_data("https://live.douyin.com/yall1102/", cookies="ttwid=fake")
        assert "web_rid=yall1102&" in mock_req.call_args.kwargs["url"] + "&"

    @pytest.mark.asyncio
    async def test_web_api_10002_retries_then_succeeds_without_html_fallback(self):
        """web/enter 首次返回 10002（瞬时风控）→ 静默重试成功 → 不触发 HTML 回退、不刷 WARNING。"""
        fail_json = json.dumps({"status_code": 10002, "status_msg": "unknown error", "data": {}})
        ok_json = json.dumps(
            {
                "status_code": 0,
                "data": {
                    "data": [{"status": 4}],
                    "user": {"nickname": "重试成功主播"},
                },
            }
        )
        mock_req = AsyncMock(side_effect=[fail_json, ok_json])
        with (
            patch("src.spider.async_req", mock_req),
            # HTML 兜底路径应完全不被触发
            patch("src.spider._extract_room_data_from_html", return_value=None) as mock_html,
        ):
            result = await spider.get_douyin_web_stream_data(
                "https://live.douyin.com/745964462470", cookies="ttwid=fake"
            )

        # 重试成功返回，未走 HTML 兜底
        assert result.get("anchor_name") == "重试成功主播"
        assert mock_html.called is False
        # 仅两次 API 调用（首次失败 + 重试成功），无额外 HTML 抓取
        assert mock_req.await_count == 2


# ---------------------------------------------------------------------------
# 4) get_douyin_app_stream_data —— 格式 2 (app直播间) & 格式 4/5 (主播主页)
# ---------------------------------------------------------------------------


class TestGetDouyinAppStreamData:
    """测试 app 端接口，覆盖直播间分享码与主播主页两种形态。"""

    @pytest.mark.asyncio
    async def test_app_live_room_via_sec_user_id(self):
        """格式 2：v.douyin.com 直播间分享码经 get_sec_user_id 走 reflow API。"""
        reflow_json = '{"status_code":0,"data":{"room":{"owner":{"nickname":"app直播间主播"},"status":4}}}'
        mock_req = AsyncMock(return_value=reflow_json)

        async def fake_sec_user_id(url, **kwargs):
            return ("7318293442", "MS4wLjABAAAA_sec")

        with (
            patch("src.spider.async_req", mock_req),
            patch("src.spider.get_sec_user_id", side_effect=fake_sec_user_id),
        ):
            result = await spider.get_douyin_app_stream_data("https://v.douyin.com/iQFeBnt/", cookies="ttwid=fake")
        assert result.get("anchor_name") == "app直播间主播"

    @pytest.mark.asyncio
    async def test_app_homepage_via_unique_id_fallback(self):
        """格式 4：v.douyin.com 主播主页 → get_sec_user_id 失败 → get_unique_id → 网页解析。"""
        room_data = {"anchor_name": "主页主播", "status": 4}

        async def fake_sec_user_id(url, **kwargs):
            raise UnsupportedUrlError("no reflow")

        with (
            patch("src.spider.get_sec_user_id", side_effect=fake_sec_user_id) as mock_sec,
            patch("src.spider.get_unique_id", new_callable=AsyncMock, return_value="47884081925"),
            patch("src.spider.get_douyin_web_stream_data", new_callable=AsyncMock, return_value=room_data) as mock_web,
        ):
            result = await spider.get_douyin_app_stream_data("https://v.douyin.com/CeiU5cbX", cookies="ttwid=fake")

        assert result.get("anchor_name") == "主页主播"
        # 解析出的抖音号应被拼接成 live.douyin.com 直播间地址
        assert mock_web.call_args.args[0] == "https://live.douyin.com/47884081925"
        # 回归：主页路径必须透传 cookies，否则代理/Cookie 配置会在此静默丢失
        #       （get_douyin_web_stream_data 的形参顺序为 url, proxy_addr, cookies）
        assert mock_web.call_args.args[2] == "ttwid=fake"
        # v.douyin.com 主页本就会被 get_sec_user_id 拒绝，此处应只探测一次后走主页解析
        assert mock_sec.await_count == 1

    @pytest.mark.asyncio
    async def test_web_user_page_via_unique_id_fallback(self):
        """格式 5：www.douyin.com/user/<sec_user_id> 直接经主页解析，跳过必然失败的 get_sec_user_id 探测。"""
        room_data = {"anchor_name": "用户页主播", "status": 4}

        with (
            patch("src.spider.get_sec_user_id", new_callable=AsyncMock) as mock_sec,
            patch("src.spider.get_unique_id", new_callable=AsyncMock, return_value="47884081925"),
            patch("src.spider.get_douyin_web_stream_data", new_callable=AsyncMock, return_value=room_data) as mock_web,
        ):
            result = await spider.get_douyin_app_stream_data(
                f"https://www.douyin.com/user/{SEC_UID}", cookies="ttwid=fake"
            )
        assert result.get("anchor_name") == "用户页主播"
        # 优化点：网页端主页链接不会重定向到 reflow 直播间页，应直接走主页解析，
        # 不应调 get_sec_user_id（旧逻辑会白下载一次主页 HTML 并抛 UnsupportedUrlError）。
        assert mock_sec.await_count == 0
        # 解析出的抖音号应被拼接成 live.douyin.com 直播间地址
        assert mock_web.call_args.args[0] == "https://live.douyin.com/47884081925"
        # 回归：主页路径必须透传 cookies
        assert mock_web.call_args.args[2] == "ttwid=fake"
