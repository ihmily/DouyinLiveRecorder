# 验证 B站弹幕参数获取 get_bilibili_danmaku_info：
# - wbi 签名（nav 取 wbi_img -> mixinKey -> w_rid）注入到 getDanmuInfo 请求
# - room_init 短号转真实 room_id
# - 返回 BilibiliDanmaku.start 所需的参数字段
# 全程 mock async_req，不触网。

import asyncio
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
from src import spider
from src.stream_select import get_record_headers

# 真实 B站 wbi key 各 32 hex 字符（img_key + sub_key 共 64，混排表索引到 63）
_IMG_KEY = "abcdefghijklmnopqrstuvwxyz012345"
_SUB_KEY = "0123456789abcdefghijklmnopqrstuv"


@pytest.fixture(autouse=True)
def _reset_bili_buvid_cache() -> Iterator[None]:
    # buvid 为模块级进程缓存，测试前后清零复位，避免用例间及同会话其它测试相互污染
    spider._bili_buvid_cached = ""
    spider._bili_buvid_is_fallback = False
    yield
    spider._bili_buvid_cached = ""
    spider._bili_buvid_is_fallback = False


def test_get_record_headers_bilibili() -> None:
    # B站直播流缺 Referer 会被 bilivideo.com 拒 403，校验器/ffmpeg 需带 Referer
    # （Referer 是 B站防盗链必要头；与虎牙「必须不带 Referer」形成对照，见 test_stream_select）
    assert get_record_headers("B站直播", "https://live.bilibili.com/123") == {"referer": "https://live.bilibili.com/"}


def test_get_bilibili_danmaku_info_happy_path() -> None:
    # 四端点 mock 响应：room_init 短号转真实 room_id、nav 取 wbi 密钥、finger/sp 取 buvid、
    # getDanmuInfo 取弹幕 token 与 host_list；字段须与解析逻辑严格对应，否则断言失配。
    responses = {
        "room_init": '{"code":0,"data":{"room_id":763679,"uid":12345}}',
        "nav": '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}',
        "finger/sp": '{"code":0,"data":{"b_3":"buvid3-xyz","buvid":"buvid-abc"}}',
        "getDanmuInfo": '{"code":0,"data":{"token":"TOKEN123","host_list":['
        '{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443},'
        '{"host":"broadcastlv2.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}',
    }
    # captured 收集 getDanmuInfo 与 finger/sp 的真实请求 URL，用于校验 wbi 签名与端点路径。
    captured: dict[str, str] = {}

    # 按 URL 子串路由：顺序命中 room_init / nav / finger/sp / getDanmuInfo，其余返回空串。
    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        if "room_init" in url:
            return responses["room_init"]
        if "/nav" in url:
            return responses["nav"]
        if "finger/sp" in url:
            captured["spi_url"] = url
            return responses["finger/sp"]
        if "getDanmuInfo" in url:
            captured["url"] = url
            return responses["getDanmuInfo"]
        return ""

    # 冻结 time 为 1700000000：w_rid 签名依赖 wts 时间戳，固定值使签名可复现、断言稳定。
    with patch("src.spider.async_req", side_effect=fake_req), patch("src.spider.time") as t:
        t.time.return_value = 1700000000
        # 预期 w_rid（与函数内用同一冻结时间签名，验证签名路径可复现）
        expected = spider._sign_wbi({"id": "763679", "type": "0", "web_location": "444.8"}, _IMG_KEY, _SUB_KEY)
        result = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462", cookies="SESS=x"))

    assert result is not None
    assert result["room_id"] == 763679  # 短号 462 经 room_init 转为真实 room_id
    assert result["uid"] == 12345
    # token 来自 getDanmuInfo，是进房握手凭证；server_host 取 host_list 首元素（主弹幕服务器）。
    assert result["token"] == "TOKEN123"
    assert result["server_host"] == "broadcastlv.chat.bilibili.com"
    # host_list 为全部弹幕服务器（主+备），AUTH 失败或重连时按序切换。
    assert result["host_list"] == [
        "broadcastlv.chat.bilibili.com",
        "broadcastlv2.chat.bilibili.com",
    ]
    assert result["buvid"] == "buvid3-xyz"
    assert result["cookie"] == "SESS=x"
    # getDanmuInfo 请求必须带 wbi 签名
    assert f"w_rid={expected['w_rid']}" in captured["url"]
    assert "wts=1700000000" in captured["url"]
    # 官方端点为 /x/frontend/finger/spi：少写结尾 i（/finger/sp）会返回空 body（JSONDecodeError 根因）
    assert captured["spi_url"].endswith("/x/frontend/finger/spi")


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_get_bilibili_danmaku_info_spi_empty_uses_fallback_buvid() -> None:
    # 回归：spi 端点风控返回空响应体（200 + 空 body，_loads_dict 得 {}），
    # 旧逻辑会让 buvid 静默为空 -> 进房包带空 buvid -> 弹幕服务器硬断连。
    # 修复后：重试一次仍空则生成兜底 buvid3（uuid），保证非空。
    # 兜底 buvid 走 uuid 生成：需校验结果非空且为合法 uuid 格式（未注册标识也会被弹幕服务器软拒绝）。
    import uuid as _uuid

    responses = {
        "room_init": '{"code":0,"data":{"room_id":763679,"uid":12345}}',
        "nav": '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}',
        # finger/sp 两次都被 mock 成空（模拟风控空 body）
        "finger/sp": "",
        "getDanmuInfo": '{"code":0,"data":{"token":"TOKEN123","host_list":['
        '{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}',
    }

    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        for key in ("room_init", "nav", "finger/sp", "getDanmuInfo"):
            if key in url:
                return responses[key]
        return ""

    # 同时 mock 首页 Set-Cookie 备取（返回空）与冻结时间；spi 两跳空走 uuid 兜底路径。
    with (
        patch("src.spider.async_req", side_effect=fake_req),
        patch("src.spider._cache_fetch_cookies", new_callable=AsyncMock, return_value={}) as home_mock,
        patch("src.spider.time") as t,
    ):
        t.time.return_value = 1700000000
        result = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))

    assert result is not None
    # buvid 必须非空且为合法 uuid（兜底生成）；首页 Set-Cookie 备取也已尝试但为空
    assert result["buvid"]
    assert _uuid.UUID(cast(str, result["buvid"]))
    assert spider._bili_buvid_is_fallback is True
    assert home_mock.await_count == 1
    assert result["token"] == "TOKEN123"


def test_get_bilibili_danmaku_info_empty_danmu_returns_none() -> None:
    # getDanmuInfo 返回空 data（-352 风控等）应安全返回 None，而非抛异常
    responses = {
        "room_init": '{"code":0,"data":{"room_id":763679,"uid":12345}}',
        "nav": '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}',
        "finger/sp": '{"code":0,"data":{"b_3":"buvid3-xyz"}}',
        "getDanmuInfo": '{"code":-352,"message":"风控","data":null}',
    }

    # 路由同 happy_path；本例 getDanmuInfo 返回 code=-352（风控），data 为 null 触发空值分支。
    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        for key in ("room_init", "nav", "finger/sp", "getDanmuInfo"):
            if key in url:
                return responses[key]
        return ""

    with patch("src.spider.async_req", side_effect=fake_req), patch("src.spider.time") as t:
        t.time.return_value = 1700000000
        result = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))

    assert result is None


def test_bili_buvid_cached_across_calls() -> None:
    # buvid 为设备级标识：首次 spi 成功后进程内缓存，再次调用（不同房间）不再请求 spi
    nav_resp = (
        '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}'
    )
    danmu_resp = (
        '{"code":0,"data":{"token":"TOKEN123","host_list":'
        '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
    )
    spi_hits = {"count": 0}

    # 路由：finger/sp 命中即计数（验证缓存后不再请求）；room_init 按 URL 区分两房间号。
    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        if "finger/sp" in url:
            spi_hits["count"] += 1
            return '{"code":0,"data":{"b_3":"buvid3-once"}}'
        if "room_init" in url:
            room = "763679" if "id=462" in url else "3336696"
            return f'{{"code":0,"data":{{"room_id":{room},"uid":12345}}}}'
        if "/nav" in url:
            return nav_resp
        if "getDanmuInfo" in url:
            return danmu_resp
        return ""

    # 两次调用不同房间（462 / 3336696）：验证 buvid 进程内缓存使第二次不再请求 spi 端点。
    with patch("src.spider.async_req", side_effect=fake_req), patch("src.spider.time") as t:
        t.time.return_value = 1700000000
        r1 = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))
        r2 = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/3336696"))

    assert r1 is not None and r2 is not None
    assert spi_hits["count"] == 1  # 第二次调用复用缓存，不再打 spi
    assert r1["buvid"] == "buvid3-once"
    assert r2["buvid"] == "buvid3-once"


def test_bili_buvid_fallback_cached_across_calls() -> None:
    # spi 风控空 body：重试两次后生成兜底 UUID，兜底值同样缓存——再次调用不再打 spi
    nav_resp = (
        '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}'
    )
    danmu_resp = (
        '{"code":0,"data":{"token":"TOKEN123","host_list":'
        '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
    )
    spi_hits = {"count": 0}

    # 路由同前；finger/sp 两跳均空（风控），验证重试两次后转 uuid 且值被缓存跨调用复用。
    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        if "finger/sp" in url:
            spi_hits["count"] += 1
            return ""  # 模拟风控空 body
        if "room_init" in url:
            return '{"code":0,"data":{"room_id":763679,"uid":12345}}'
        if "/nav" in url:
            return nav_resp
        if "getDanmuInfo" in url:
            return danmu_resp
        return ""

    # 两次调用同房间：spi 空触发 uuid 兜底，兜底值同样缓存，第二次 0 次 spi 请求。
    with (
        patch("src.spider.async_req", side_effect=fake_req),
        patch("src.spider._cache_fetch_cookies", new_callable=AsyncMock, return_value={}),
        patch("src.spider.time") as t,
    ):
        t.time.return_value = 1700000000
        r1 = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))
        r2 = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))

    assert r1 is not None and r2 is not None
    assert spi_hits["count"] == 2  # 仅首次调用的两次重试，第二次调用 0 次
    assert r1["buvid"] == r2["buvid"]
    assert r1["buvid"]


# ---- 进房包 uid 回归（连接即断根因） ----
# 真机对照探针（房间 3336696）：join 包 uid=主播uid 时弹幕服务器 AUTH 后立刻 1006 断连，
# uid=0 时正常收到 AUTH_REPLY 与弹幕。get_bilibili_danmaku_info 返回的 uid 是主播 uid，
# 进房必须用观众自身 uid（匿名=0；cookie 含 DedeUserID 时取其值）。


class _FakeWs:
    # 捕获进房包字节的假 WebSocket
    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def send(self, data: bytes) -> None:
        self.sent.append(data)


def _join_body(args: dict) -> dict[str, object]:
    import json as _json

    from src.platforms.bilibili import BilibiliDanmaku

    client = BilibiliDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    client._args = args
    ws = _FakeWs()
    client._ws = ws  # type: ignore[assignment]
    asyncio.run(client._join_room())
    assert ws.sent, "进房包未发送"
    # 进房包帧头固定 16 字节（包长/头长/版本/op/seq），跳过帧头解析 JSON 载荷。
    body: dict[str, object] = _json.loads(ws.sent[0][16:].decode("utf-8"))
    return body


def test_join_room_uid_anonymous_is_zero() -> None:
    # 匿名（无 cookie）时 uid 必须为 0，即使 args 里带着主播 uid
    body = _join_body({"uid": 296732, "room_id": 3336696, "token": "TOKEN", "buvid": "x", "cookie": ""})
    assert body["uid"] == 0


def test_join_room_uid_from_dede_user_id_cookie() -> None:
    # 登录态 cookie 携带 DedeUserID 时作为观众 uid
    body = _join_body(
        {"uid": 296732, "room_id": 3336696, "token": "TOKEN", "buvid": "x", "cookie": "SESSDATA=a; DedeUserID=999888"}
    )
    assert body["uid"] == 999888


def test_join_room_uid_cookie_without_dede_is_zero() -> None:
    body = _join_body({"uid": 296732, "room_id": 3336696, "token": "TOKEN", "buvid": "x", "cookie": "SESSDATA=a"})
    assert body["uid"] == 0


# ---- buvid3 来源优先级回归（随机 UUID 未注册 → AUTH 软拒绝根因） ----


def test_buvid_prefers_cookie_over_spi() -> None:
    # 登录态 cookie 携带真实 buvid3（服务器注册过的设备标识）时必须优先提取使用，
    # 且不再请求 spi 端点——兜底生成的随机 UUID 未在 B站注册，弹幕服务器 AUTH 会软拒绝
    nav_resp = (
        '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}'
    )
    danmu_resp = (
        '{"code":0,"data":{"token":"TOKEN123","host_list":'
        '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
    )
    spi_hits = {"count": 0}

    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        if "finger/sp" in url:
            spi_hits["count"] += 1
            return '{"code":0,"data":{"b_3":"buvid3-from-spi"}}'
        if "room_init" in url:
            return '{"code":0,"data":{"room_id":763679,"uid":12345}}'
        if "/nav" in url:
            return nav_resp
        if "getDanmuInfo" in url:
            return danmu_resp
        return ""

    # cookie 携带真实注册 buvid3：必须优先提取并跳过 spi，避免用未注册 uuid 被 AUTH 软拒绝。
    cookie = "SESSDATA=x; buvid3=REAL-BUVID3-123; other=1"
    with patch("src.spider.async_req", side_effect=fake_req), patch("src.spider.time") as t:
        t.time.return_value = 1700000000
        result = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462", cookies=cookie))

    assert result is not None
    assert result["buvid"] == "REAL-BUVID3-123"
    assert spi_hits["count"] == 0  # cookie 已提供 buvid3，不再打 spi


# ---- AUTH_REPLY（operation=8）进房认证回归（软拒绝无感知根因） ----


class _FakeAuthWs:
    # 捕获 close 调用的假 WebSocket
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def _decode_auth_reply(payload: bytes) -> tuple[Any, Any]:
    import struct

    from src.platforms.bilibili import BilibiliDanmaku

    client = BilibiliDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    ws = _FakeAuthWs()
    client._ws = ws  # type: ignore[assignment]
    # 手工拼一条 B站弹幕协议帧：头部 >IHHII = (包长, 头长16, 协议版本1, operation=8 即 AUTH_REPLY,
    # 序列号1) + JSON 载荷。operation=8 是进房认证回包，用真帧喂 decode_message 才能走到认证分支。
    # 大端 > 与 B站 WS 协议严格一致；头长恒 16，载荷为 JSON 文本。
    frame = struct.pack(">IHHII", 16 + len(payload), 16, 1, 8, 1) + payload

    async def _run() -> None:
        client.decode_message(frame)
        await asyncio.sleep(0)  # 让 ensure_future 调度的 close 协程得到执行

    asyncio.run(_run())
    return client, ws


def test_auth_reply_ok_keeps_connection() -> None:
    # code=0 认证成功：不置停止标志、不断开连接
    # （对照组：验证失败路径才主动断开，成功路径不得误杀连接）
    client, ws = _decode_auth_reply(b'{"code":0}')
    assert client._stopped is False
    assert ws.closed is False


def test_auth_reply_failure_closes_connection() -> None:
    # code!=0 软拒绝：此前连接保持却不推弹幕且无任何感知；修复后主动断开并带原因退出，
    # 同时使 spider 侧 buvid 缓存失效（兜底 UUID 被拒后不可复用，下一轮重新获取）
    # AUTH 被拒：断言缓存失效钩子被调用一次（兜底 UUID 被软拒绝后不可复用，下一轮重新获取）。
    with patch("src.spider.invalidate_bili_buvid_cache") as inv:
        client, ws = _decode_auth_reply(b'{"code":-101,"message":"auth failed"}')
    assert client._stopped is True
    assert ws.closed is True
    inv.assert_called_once()


# ---- 首页 Set-Cookie 备取（spi 风控时的真实注册 buvid3 来源） ----


def test_buvid_from_homepage_setcookie_when_spi_empty() -> None:
    # spi 两跳均空（风控）：改走 www.bilibili.com 首页 Set-Cookie 获取真实注册 buvid3，
    # 优于随机 UUID（未注册标识会被弹幕服务器 AUTH 软拒绝）
    nav_resp = (
        '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/bfs/wbi/'
        + _IMG_KEY
        + '.png","sub_url":"https://i0.hdslb.com/bfs/wbi/'
        + _SUB_KEY
        + '.png"}}}'
    )
    danmu_resp = (
        '{"code":0,"data":{"token":"TOKEN123","host_list":'
        '[{"host":"broadcastlv.chat.bilibili.com","port":2243,"ws_port":2244,"wss_port":443}]}}'
    )

    async def fake_req(url: str, *args: object, **kwargs: object) -> str:
        if "finger/sp" in url:
            return ""  # spi 风控空 body
        if "room_init" in url:
            return '{"code":0,"data":{"room_id":763679,"uid":12345}}'
        if "/nav" in url:
            return nav_resp
        if "getDanmuInfo" in url:
            return danmu_resp
        return ""

    async def fake_home(url: str, *args: object, **kwargs: object) -> dict[str, str]:
        assert url == "https://www.bilibili.com/"
        return {"buvid3": "HOME-BUVID-777", "b_nut": "1721975923"}

    # 让 spi 两跳空、首页 Set-Cookie 返回真实 buvid3；验证优先采用首页值而非 uuid 兜底。
    with (
        patch("src.spider.async_req", side_effect=fake_req),
        patch("src.spider._cache_fetch_cookies", side_effect=fake_home),
        patch("src.spider.time") as t,
    ):
        t.time.return_value = 1700000000
        result = asyncio.run(spider.get_bilibili_danmaku_info("https://live.bilibili.com/462"))

    assert result is not None
    assert result["buvid"] == "HOME-BUVID-777"
    # 首页真实 buvid3 非兜底（fallback=False），避免误标为 uuid 兜底而触发无谓重取。
    assert spider._bili_buvid_is_fallback is False


def test_invalidate_bili_buvid_cache_clears_state() -> None:
    # AUTH 被拒后的失效钩子：缓存值与兜底标记一并清零，下一轮重新走真实获取链
    spider._bili_buvid_cached = "STALE-UUID"
    spider._bili_buvid_is_fallback = True
    spider.invalidate_bili_buvid_cache()
    assert spider._bili_buvid_cached == ""
    assert spider._bili_buvid_is_fallback is False


# ---- 认证看门狗（服务器不回 AUTH_REPLY 的静默拒绝形态） ----


def _watchdog_client() -> tuple[Any, Any]:
    from src.platforms.bilibili import BilibiliDanmaku

    client = BilibiliDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    ws = _FakeAuthWs()
    client._ws = ws  # type: ignore[assignment]
    return client, ws


def test_auth_watchdog_fires_without_reply() -> None:
    # 进房包发出后限时无 AUTH_REPLY(code=0)：按被拒处理——告警、断开、失效 buvid 缓存
    from src.platforms.bilibili import BilibiliDanmaku

    client, ws = _watchdog_client()

    # 将 _AUTH_TIMEOUT 压到 0.01s 加速触发看门狗（真实超时较长，单测不可等）；
    # 未收到任何 AUTH_REPLY 即按被拒处理。
    async def _run() -> None:
        with patch.object(BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01):
            await client._auth_watchdog(ws)
            await asyncio.sleep(0)  # 让 ensure_future 调度的 close 协程得到执行

    with patch("src.spider.invalidate_bili_buvid_cache") as inv:
        asyncio.run(_run())
    # 软拒绝路径：连接被标记停止并主动断开，buvid 缓存失效钩子恰好调用一次。
    assert client._stopped is True
    assert ws.closed is True
    inv.assert_called_once()


def test_auth_watchdog_noop_after_ok_reply() -> None:
    # 已收到 code=0 回应（_auth_ok=True）：看门狗不动作
    # （守护 _auth_ok 标志，防止成功进房后看门狗误触发断开）
    from src.platforms.bilibili import BilibiliDanmaku

    client, ws = _watchdog_client()
    client._auth_ok = True

    async def _run() -> None:
        with patch.object(BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01):
            await client._auth_watchdog(ws)
            await asyncio.sleep(0)

    with patch("src.spider.invalidate_bili_buvid_cache") as inv:
        asyncio.run(_run())
    assert client._stopped is False
    assert ws.closed is False
    inv.assert_not_called()


def test_auth_watchdog_stale_ws_noop() -> None:
    # 看门狗存活期间会话已切换 host（self._ws 已非本次进房的 ws）：旧看门狗作废
    from src.platforms.bilibili import BilibiliDanmaku

    client, ws = _watchdog_client()
    # 模拟 host 切换：看门狗存活期间 self._ws 已指向新会话，旧看门狗须识别并作废
    client._ws = _FakeAuthWs()  # type: ignore[assignment]  # 模拟切换到下一 host

    async def _run() -> None:
        with patch.object(BilibiliDanmaku, "_AUTH_TIMEOUT", 0.01):
            await client._auth_watchdog(ws)
            await asyncio.sleep(0)

    asyncio.run(_run())
    # 旧 host 看门狗识别到 self._ws 已切换，作废自身：不置停止、不断开新连接。
    assert client._stopped is False
    assert ws.closed is False
