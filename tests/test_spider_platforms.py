# src/spider.py 2026-09-20 批次修复（SEV-07、MID-33 spider 半边、MID-40..50）的离线回归用例。
# 2026-09-21 追加 SEV-N02（popkontv token 双 "Bearer " 前缀）回归锁，见文件末尾同名小节。
# 原则（AGENTS「测试不得自实现被测逻辑」）：只打桩 HTTP 层（src.spider.async_req / httpx /
# get_token_js 等边界），解析逻辑一律走真实代码；断言以「删掉生产修复就会变红」为判据。

import asyncio
import json
import time
import types
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from src import cookie_cache
from src import spider as sp
from src.spider import (
    get_baidu_stream_data,
    get_bilibili_stream_data,
    get_douyu_info_data,
    get_douyu_stream_data,
    get_popkontv_stream_url,
    get_twitcasting_stream_url,
)


def _unwrap(func: object) -> Any:
    # 取装饰器保留的 __wrapped__ 原函数，断言精确返回/异常（同 test_spider_fixes 口径）
    return cast(Any, getattr(func, "__wrapped__"))


@pytest.fixture(autouse=True)
def _pin_identity_translation() -> Iterator[None]:
    # i18n.tr 在测试环境按 msgid 直通（仅替换占位符），使日志断言不受目录翻译影响；
    # 若某条文案尚未登记，tr 会回落原 msgid——两种路径下断言的都是「中文 msgid 正文」。
    import i18n as i18n_mod

    original_tr = i18n_mod.tr

    def _identity(template: str, **kw: object) -> str:
        text = template
        for key, value in kw.items():
            text = text.replace("{" + key + "}", str(value))
        return text

    i18n_mod.tr = _identity
    yield
    i18n_mod.tr = original_tr


def _fake_logger() -> types.SimpleNamespace:
    # 捕获 sp.logger.<level>(msg) 的 message 文本，供「日志须留下线索」类断言
    msgs: list[str] = []
    sink = Mock(side_effect=lambda msg, *a, **k: msgs.append(str(msg)))
    return types.SimpleNamespace(
        msgs=msgs,
        warning=sink,
        error=sink,
        info=Mock(),
        debug=Mock(),
        success=Mock(),
        exception=sink,
        trace=Mock(),
        log=sink,
    )


# ── SEV-07：两个 login_* 的兜底装饰器与返回契约错配 ──────────────────────────────


class TestSev07LoginContracts:
    # 判据（AGENTS 变异验证）：删掉 spider 里任何一处 _or_none 改造或调用点判空，
    # 本组至少一条断言变红——失败值一旦回到 dict，None 断言与 RuntimeError 类型断言互斥失效。
    async def test_login_popkontv_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # E4010/网络异常等登录失败路径：装饰契约必须是 None（而非 {"is_live": False} dict）。
        # dict 形态会让调用点元组解包抛 ValueError 并被二次吞没（报告实测形态）。
        class _BoomClient:
            def __init__(self, *args: object, **kwargs: object) -> None:
                pass

            async def __aenter__(self) -> "_BoomClient":
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

            async def post(self, *args: object, **kwargs: object) -> None:
                raise httpx.ConnectError("popkontv unreachable")

        shim = types.SimpleNamespace(**vars(httpx))
        shim.AsyncClient = _BoomClient
        monkeypatch.setattr(sp, "httpx", shim)
        result = await sp.login_popkontv("user1", "password123456")
        assert result is None

    async def test_login_twitcasting_failure_returns_none(self) -> None:
        # 抓页拿不到 cs_session_id → ValueError → 契约必须是 None；
        # dict 兜底值恒真、会被调用方当成 Cookie 写进请求头。
        with patch.object(sp, "async_req", new=AsyncMock(return_value="<html>no form</html>")):
            result = await sp.login_twitcasting("twitter", "user", "pass")
        assert result is None

    async def test_popkontv_caller_guards_none_before_unpack(self) -> None:
        # 调用点契约（CR-12）：login 返回 None 时须抛可动作 RuntimeError，
        # 而不是对 None/dict 解包抛 TypeError/ValueError 后被外层装饰器二次吞掉。
        raw = _unwrap(get_popkontv_stream_url)
        room_info = ["2026", "P-00001", "sign1", 1, 0]
        with (
            patch.object(sp, "get_popkontv_stream_data", new=AsyncMock(return_value=("anchor1", room_info))),
            patch.object(sp, "async_req", new=AsyncMock(return_value='{"statusCd":"E5000","statusMsg":"x"}')),
            patch.object(sp, "login_popkontv", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(RuntimeError, match="popkontv login failed"):
                await raw(
                    "https://www.popkontv.com/live/view?castId=1&partnerCode=P-00001",
                    username="user1",
                    password="password12345",
                )

    async def test_twitcasting_caller_rejects_non_str_cookie(self) -> None:
        # isinstance str 断言：旧 dict 兜底形态（{"is_live": False}）绝不能写进 Cookie 头；
        # 现在应在写入前抛 RuntimeError（旧实现：真值判断放行 → get_data 抛 ValueError）。
        raw = _unwrap(get_twitcasting_stream_url)
        with (
            patch.object(sp, "login_twitcasting", new=AsyncMock(return_value={"is_live": False})),
            patch.object(sp, "async_req", new=AsyncMock(return_value="<html/>")),
        ):
            with pytest.raises(RuntimeError, match="TwitCasting login failed"):
                await raw("https://twitcasting.tv/someanchor?login=true")

    async def test_twitcasting_str_cookie_written_to_header(self) -> None:
        # 正向对照：str 形态登录结果照常写入 Cookie 头（isinstance 断言不得误伤正常路径）。
        raw = _unwrap(get_twitcasting_stream_url)
        seen_headers: list[dict[str, str]] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            headers = kwargs.get("headers")
            if isinstance(headers, dict):
                seen_headers.append(cast(dict[str, str], headers))
            return "<html>no parse</html>"

        with (
            patch.object(sp, "login_twitcasting", new=AsyncMock(return_value="tc_ss=abc")),
            patch.object(sp, "async_req", new=fake_req),
        ):
            with pytest.raises(ValueError):
                await raw("https://twitcasting.tv/someanchor?login=true")
        # 登录成功后紧取的页面请求必须带 str Cookie
        assert any(h.get("Cookie") == "tc_ss=abc" for h in seen_headers)


# ── MID-40：buvid 失效须同时清通用 singleflight 缓存 ─────────────────────────────


class TestMid40BuvidInvalidation:
    # singleflight 通用缓存（TTL 30min）是「被拒值复活」的载体：这里用真实 cookie_cache
    # 实例（只 clear 隔离、不打桩）证明失效钩子确实触达 invalidate_generic，而非仅改全局。
    @staticmethod
    def _seed(key: str, value: object) -> None:
        async def _factory() -> object:
            return value

        async def _go() -> None:
            await cookie_cache.singleflight(key=key, factory=_factory, timeout=5, cache_falsy=True)

        asyncio.run(_go())

    def _refetch_count(self, key: str) -> int:
        calls = {"n": 0}

        async def _factory() -> object:
            calls["n"] += 1
            return ("FRESH", False)

        async def _go() -> None:
            await cookie_cache.singleflight(key=key, factory=_factory, timeout=5, cache_falsy=True)

        asyncio.run(_go())
        return calls["n"]

    def test_invalidate_purges_generic_default_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cookie_cache.clear()
        self._seed("bili_buvid3|", ("REJECTED-UUID", True))
        monkeypatch.setattr(sp, "_bili_buvid_cached", "REJECTED-UUID")
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "")
        sp.invalidate_bili_buvid_cache()
        # 若只清模块全局，重跑 singleflight 会命中缓存里的被拒 UUID（calls==0）
        assert self._refetch_count("bili_buvid3|") == 1

    def test_invalidate_purges_proxy_key_via_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cookie_cache.clear()
        self._seed("bili_buvid3|http://p:8080", ("REJECTED-UUID", True))
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "other-proxy")
        sp.invalidate_bili_buvid_cache(proxy_addr="http://p:8080")
        assert self._refetch_count("bili_buvid3|http://p:8080") == 1

    def test_invalidate_purges_proxy_key_via_recorded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # platforms/bilibili.py 的调用点是**无参**的——必须靠缓存写入时记录的代理清对键
        cookie_cache.clear()
        self._seed("bili_buvid3|http://q:3128", ("REJECTED-UUID", True))
        monkeypatch.setattr(sp, "_bili_buvid_cached", "REJECTED-UUID")
        monkeypatch.setattr(sp, "_bili_buvid_cached_proxy", "http://q:3128")
        sp.invalidate_bili_buvid_cache()
        assert self._refetch_count("bili_buvid3|http://q:3128") == 1


# ── MID-41：抖音 APP 路径 ORIGIN 候选取 pull_datas 刚解析结果 ─────────────────────


class TestMid41DouyinAppOrigin:
    # 本用例是「codec 标注来源」的行为锁：stale(pull_data,h264) 与 fresh(pull_datas,h265) 故意
    # 不同源，任何退回从 pull_data 取值的改法都会让 &codec= 断言变红（-c copy 安全性判据）。
    async def test_origin_candidate_and_codec_from_pull_datas(self) -> None:
        fresh = {
            "sdk_params": json.dumps({"VCodec": "h265"}),
            "hls": "https://p/orig.m3u8",
            "flv": "https://p/orig.flv",
        }
        stale = {
            "sdk_params": json.dumps({"VCodec": "h264"}),
            "hls": "https://p/stale.m3u8",
            "flv": "https://p/stale.flv",
        }
        app_resp = json.dumps(
            {
                "status_code": 0,
                "data": {
                    "room": {
                        "status": 2,
                        "owner": {"nickname": "N"},
                        "stream_url": {
                            # 现代响应：pull_datas 携带真实候选；pull_data 存在但内容是旧线路，
                            # 原实现从 pull_data 取地址+codec → ORIGIN 丢失或 codec 标注错位。
                            "live_core_sdk_data": {
                                "pull_data": {"stream_data": json.dumps({"data": {"origin": {"main": stale}}})}
                            },
                            "pull_datas": {"F": {"stream_data": json.dumps({"data": {"origin": {"main": fresh}}})}},
                            "hls_pull_url_map": {"FULL_HD1": "https://p/fhd.m3u8"},
                            "flv_pull_url": {"FULL_HD1": "https://p/fhd.flv"},
                        },
                    }
                },
            }
        )
        raw = _unwrap(sp.get_douyin_app_stream_data)
        with (
            patch.object(sp, "get_sec_user_id", new=AsyncMock(return_value=("745964462470", "MS4wLjABAAAA_sec"))),
            patch.object(sp, "_ensure_ttwid", new=AsyncMock(return_value="ttwid=x")),
            patch.object(sp, "async_req", new=AsyncMock(return_value=app_resp)),
        ):
            result = await raw("https://v.douyin.com/iQLgKSj/")
        stream_url = cast(dict[str, object], result["stream_url"])
        flv_map = cast(dict[str, object], stream_url["flv_pull_url"])
        hls_map = cast(dict[str, object], stream_url["hls_pull_url_map"])
        # codec=h265 标注必须来自 pull_datas 的 VCodec（决定 _is_h265 与 -c copy 安全性）
        assert flv_map["ORIGIN"] == "https://p/orig.flv&codec=h265"
        assert hls_map["ORIGIN"] == "https://p/orig.m3u8&codec=h265"


# ── MID-42：花椒 encode 与消费字段自洽 + 判空 ────────────────────────────────────


class TestMid42Huajiao:
    # 花椒为 only_flv 直下平台（main.py 直接下载 flv_url），地址编码器与容器 codec 标注错配
    # 没有 ffmpeg 报错兜底，只能靠本组用例锁「encode 参数 -> 消费字段 -> 无 h265 假标记」。
    _FEED = json.dumps(
        {
            "errmsg": "",
            "data": {
                "creatime": "1",
                "author": {"nickname": "N", "uid": "u1"},
                "feed": {"title": "T", "sn": "s1", "relateid": "999"},
            },
        }
    )

    async def test_requests_h264_for_h264_url(self) -> None:
        raw = _unwrap(sp.get_huajiao_stream_url)
        seen: list[str] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            url = kwargs.get("url") or (args[0] if args else "")
            seen.append(str(url))
            if kwargs.get("redirect_url"):
                return "https://www.huajiao.com/l/999"
            if "getFeedInfo" in str(url):
                return self._FEED
            return '{"data": {"h264_url": "http://x/h264.flv"}}'

        with patch.object(sp, "async_req", new=fake_req):
            result = await raw("https://v.huajiao.com/x/AAAA")
        substream = [u for u in seen if "substream" in u][0]
        # 请求参数与消费字段编码器必须一致：要么 h264+h264_url，要么 h265 且补 &codec=h265。
        # 本实现取前者（改动最小、不依赖未实测字段）。
        assert "encode=h264" in substream
        assert result["flv_url"] == "http://x/h264.flv"
        assert result["is_live"] is True

    async def test_missing_h264_url_logs_and_returns_not_live(self) -> None:
        raw = _unwrap(sp.get_huajiao_stream_url)
        fake = _fake_logger()

        async def fake_req(*args: object, **kwargs: object) -> str:
            url = kwargs.get("url") or (args[0] if args else "")
            if kwargs.get("redirect_url"):
                return "https://www.huajiao.com/l/999"
            if "getFeedInfo" in str(url):
                return self._FEED
            return '{"data": {}}'  # 改版/WAF 页形态：缺 h264_url

        with patch.object(sp, "async_req", new=fake_req), patch.object(sp, "logger", fake):
            result = await raw("https://v.huajiao.com/x/AAAA")
        assert result["is_live"] is False
        assert any("h264_url" in m for m in fake.msgs)


# ── MID-43：淘宝 broadCaster 是对象，anchor_name 必须是 str ───────────────────────


class TestMid43Taobao:
    # anchor_name 的类型契约：main.py 会对它做 clean_name(...).strip()，非 str 直接 AttributeError；
    # 且该轮 record_success 已上报（熔断样本被污染），故必须回 str、宁可空串。
    @staticmethod
    def _jsonp(broadcaster: object) -> str:
        return (
            "mtopjsonp1("
            + json.dumps(
                {
                    "ret": ["SUCCESS::调用成功"],
                    "data": {
                        "broadCaster": broadcaster,
                        "streamStatus": "0",
                        "title": "T",
                        "liveUrlList": [],
                    },
                },
                ensure_ascii=False,
            )
            + ")"
        )

    async def _anchor(self, broadcaster: object) -> object:
        raw = _unwrap(sp.get_taobao_stream_url)
        resp: tuple[str, dict[str, str]] = (self._jsonp(broadcaster), {})
        with patch.object(sp, "async_req", new=AsyncMock(return_value=resp)):
            result = await raw("https://h5.m.taobao.com/taolive/video.html?id=a&liveId=500123")
        return result["anchor_name"]

    async def test_broadcaster_dict_extracts_account_name(self) -> None:
        # dict 形态：取 accountName（缺失回 nick），**不得把对象塞进 anchor_name**
        # —— 旧实现 cast(str, dict) 运行时仍是 dict，main.py 的 clean_name(dict).strip() 必抛。
        assert await self._anchor({"accountName": "店铺主播", "nick": "nick1"}) == "店铺主播"
        assert await self._anchor({"nick": "nick1"}) == "nick1"

    async def test_broadcaster_str_passthrough(self) -> None:
        assert await self._anchor("旧形态名字") == "旧形态名字"

    async def test_broadcaster_other_type_falls_back_empty(self) -> None:
        for weird in ({"no_name": 1}, 123, None):
            assert await self._anchor(weird) == ""


# ── MID-44：winktv bj_info 判空后再解包 ───────────────────────────────────────────


class TestMid44Winktv:
    # _or_none 被调方的判空属于调用点责任（CR-12）；断言同时区分新旧形态：
    # 旧实现抛 TypeError → 装饰器兜底 {"is_live": False}（缺 anchor_name 键）。
    async def test_none_bj_info_returns_not_live(self) -> None:
        raw = _unwrap(sp.get_winktv_stream_data)
        with patch.object(sp, "get_winktv_bj_info", new=AsyncMock(return_value=None)):
            result = await raw("https://www.winktv.co.kr/testuser")
        # 旧实现直接解包 None → TypeError → 被自身装饰器吞成 {"is_live": False}（无 anchor_name 键）
        assert result == {"anchor_name": "", "is_live": False}


# ── MID-45：查询参数位于串尾的正则形态 ────────────────────────────────────────────


class TestMid45TailParams:
    # 串尾参数形态是「用户手工删参数 / 平台短分享链」的常见产出，正则必须有 $ 出口；
    # 与 MI-17 已收口的 rid=/castId= 同口径，防止下一个平台抄错写法。
    async def test_baidu_room_id_at_end_of_string(self) -> None:
        with patch.object(sp, "async_req", new=AsyncMock(return_value='{"data": {}}')):
            result = await get_baidu_stream_data(
                "https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377"
            )
        # 旧正则 "room_id=(.*?)&" 恒不中 → 装饰器兜底无 anchor_name 键
        assert result["anchor_name"] == ""
        assert result["is_live"] is False

    async def test_popkon_mcid_at_end_of_string(self) -> None:
        raw = _unwrap(sp.get_popkontv_stream_data)
        responses = ['{"data": {"broadCastList": []}}', "<html/>", "<html no next data/>"]
        with patch.object(sp, "async_req", new=AsyncMock(side_effect=list(responses))):
            result = await raw("https://www.popkontv.com/channel/notices?mcid=ABC123")
        assert result is not None
        anchor_name, room_info = result
        assert "ABC123" in anchor_name
        assert room_info is None


# ── MID-46：TikTok 内置游客 cookie 失效须给可动作告警 ─────────────────────────────


class TestMid46TiktokGuestCookie:
    # 告警只在「解析失败 且 用的内置缺省」交集处出现：两条件各自单独成立都不许告警，
    # 否则用户配了新 cookie 仍被过期提示刷屏（第二条用例即防这个反向回归）。
    async def test_builtin_guest_failure_warns_with_config_hint(self) -> None:
        fake = _fake_logger()
        with (
            patch.object(sp, "logger", fake),
            patch.object(sp, "_read_tiktok_guest_cookie", return_value=sp._TIKTOK_BUILTIN_GUEST_COOKIE),
            patch.object(sp, "async_req", new=AsyncMock(return_value="<html>no SIGI</html>")),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            result = await sp.get_tiktok_stream_data("https://www.tiktok.com/@x/live")
        assert result == {"is_live": False}
        assert any("tiktok_guest_cookie" in m for m in fake.msgs)

    async def test_no_warning_when_override_configured(self) -> None:
        fake = _fake_logger()
        with (
            patch.object(sp, "logger", fake),
            patch.object(sp, "_read_tiktok_guest_cookie", return_value="fresh-cookie"),
            patch.object(sp, "async_req", new=AsyncMock(return_value="<html>no SIGI</html>")),
            patch("src.spider.asyncio.sleep", new_callable=AsyncMock),
        ):
            await sp.get_tiktok_stream_data("https://www.tiktok.com/@x/live")
        assert not any("tiktok_guest_cookie" in m for m in fake.msgs)


# ── MID-47：SOOP 全球版相对清单行须 urljoin（原拼出缺斜杠非法地址并进 record_url）──


class TestMid47SoopGlobal:
    # 断言整条 URL 而非子串：缺斜杠形态（...com1080/...）同样包含 "1080/index.m3u8"，
    # 弱断言会放走本项要修的确切缺陷。
    async def test_relative_manifest_lines_absolutized(self) -> None:
        raw = _unwrap(sp.get_sooplive_stream_data)
        responses = [
            '{"data": {"streamerChannelInfo": {"nickname": "N", "channelId": "C"}}}',
            '{"data": {"isStream": true, "title": "T"}}',
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\n1080/index.m3u8\n",
        ]
        with patch.object(sp, "async_req", new=AsyncMock(side_effect=list(responses))):
            result = await raw("https://www.sooplive.com/abc")
        play_list = cast(list[str], result["play_url_list"])
        # 旧实现 "/".join(m3u8.split("/")[0:3]) 无尾斜杠 → ...sooplive.com1080/index.m3u8
        assert play_list == ["https://global-media.sooplive.com/live/abc/1080/index.m3u8"]


# ── MID-48（定向批次）：betard / bilibili playUrl / twitch GQL ────────────────────


class TestMid48JsonHardening:
    # 本组验证的是「日志线索存在性」而非返回值——裸 json.loads 与 _loads_dict 的最终对外
    # 表现都是未开播，唯一可回归锁定的差异就是 warn 行与回退链是否走到（await_count）。
    async def test_douyu_betard_missing_room_logs_distinguishing_warning(self) -> None:
        fake = _fake_logger()
        with (
            patch.object(sp, "logger", fake),
            patch.object(sp, "async_req", new=AsyncMock(return_value='{"error": "anti-crawler"}')),
        ):
            result = await get_douyu_info_data("https://www.douyu.com/12345?rid=12345")
        assert result == {"is_live": False}
        assert any("betard" in m for m in fake.msgs)  # 旧实现无任何线索

    async def test_douyu_betard_empty_response_distinguished(self) -> None:
        fake = _fake_logger()
        with (
            patch.object(sp, "logger", fake),
            patch.object(sp, "async_req", new=AsyncMock(return_value="")),
        ):
            result = await get_douyu_info_data("https://www.douyu.com/12345?rid=12345")
        assert result == {"is_live": False}
        # MID-2214：空响应必须与「缺 room 字段」区分（文案经 i18n.tr，故断言其中的区分性短语）
        assert any("空响应" in m for m in fake.msgs)

    async def test_bilibili_waf_response_reaches_v2_fallback(self) -> None:
        # playUrl 返回 WAF 页：_loads_dict 回 {} → code 判定落入 getRoomPlayInfo 回退分支。
        # 旧实现 json.loads 抛错 → 装饰器吞成 {"is_live": False}，回退链永不执行。
        fallback = '{"data": {"live_status": 0, "playurl_info": {}}}'
        with patch.object(sp, "async_req", new=AsyncMock(side_effect=["<html>WAF</html>", fallback])) as mock:
            result = await get_bilibili_stream_data("https://live.bilibili.com/12345")
        assert result is None
        assert mock.await_count == 2

    async def test_twitch_gql_errors_array_raises_with_clue(self) -> None:
        fake = _fake_logger()
        with (
            patch.object(sp, "logger", fake),
            patch.object(sp, "_ensure_twitch_client_id", new=AsyncMock(return_value="cid123")),
            patch.object(sp, "async_req", new=AsyncMock(return_value='[{"errors": [{"message": "rejected"}]}]')),
        ):
            with pytest.raises(RuntimeError, match="Twitch GQL errors"):
                await sp.get_twitchtv_room_info("https://www.twitch.tv/someone", token="tk")
        assert any("rejected" in m for m in fake.msgs)

    async def test_twitch_empty_client_id_sends_no_request(self) -> None:
        # Client-Id 拉取失败不得再照发 `Client-Id: ""`（必然失败且无日志的组合）
        with (
            patch.object(sp, "_ensure_twitch_client_id", new=AsyncMock(return_value="")),
            patch.object(sp, "async_req", new=AsyncMock(return_value="[]")) as mock,
        ):
            with pytest.raises(RuntimeError, match="Client-Id"):
                await sp.get_twitchtv_room_info("https://www.twitch.tv/someone", token="tk")
        assert mock.await_count == 0


# ── MID-49：斗鱼取流 POST 体不得手工拼接 ──────────────────────────────────────────


class TestMid49DouyuPostBody:
    # data 必须是 dict 交给 async_http 统一编码：str 形态即回到手工拼接（本报告事故形态）。
    # 缺 enc_data 用 await_count==0 锁「不发注定失败的请求」，比断言返回值更能抓回归。
    async def test_body_sent_as_dict_and_values_preserved(self) -> None:
        # enc_data 为 base64 产物，含 & = + % 时手工拼接会破坏表单字段结构；
        # 必须整体作为 dict 交给 async_http 的统一 urlencoded 分支。
        sign = {"enc_data": "abc+def&g=h%20i", "did": "d1", "ts": 123, "auth": "a1"}
        with (
            patch.object(sp, "get_token_js", new=AsyncMock(return_value=sign)),
            patch.object(sp, "async_req", new=AsyncMock(return_value='{"error": 0, "data": {}}')) as mock,
        ):
            result = await get_douyu_stream_data("12345")
        assert result == {"error": 0, "data": {}}
        assert mock.await_args is not None  # 真实拉流请求必须已发出
        sent = mock.await_args.kwargs["data"]
        assert isinstance(sent, dict)
        assert sent["enc_data"] == "abc+def&g=h%20i"  # 未被手工拼接截断
        assert mock.await_args.kwargs["headers"]["Content-Type"] == "application/x-www-form-urlencoded"

    async def test_missing_enc_data_returns_empty_without_request(self) -> None:
        # 缺 enc_data 时不得发字面量 enc_data=None（被伪装成「无流」），直接回 {} 走取流失败告警
        sign = {"did": "d1", "ts": 123, "auth": "a1"}
        with (
            patch.object(sp, "get_token_js", new=AsyncMock(return_value=sign)),
            patch.object(sp, "async_req", new=AsyncMock(return_value="x")) as mock,
        ):
            result = await get_douyu_stream_data("12345")
        assert result == {}
        assert mock.await_count == 0


# ── MID-50：写死会话/参数的覆盖入口与 UA 同源 ─────────────────────────────────────


class TestMid50OverridesAndUa:
    # 覆盖入口三级优先（env > config > 内置）与 F-10/CR-12 模式逐字对齐；usher 参数断言
    # 直接查最终 URL，避免有人改 params dict 后又在拼接处重新引入双重编码。
    async def test_xhs_sid_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("XHS_SESSION_SID", "session.custom123")
        raw = _unwrap(sp.get_xhs_stream_url)
        captured: dict[str, str] = {}

        async def fake_req(*args: object, **kwargs: object) -> str:
            headers = kwargs.get("headers")
            if isinstance(headers, dict) and not captured:
                captured.update(cast(dict[str, str], headers))
            return "<html></html>"

        with patch.object(sp, "async_req", new=fake_req):
            await raw("https://www.xiaohongshu.com/user/profile/test123")
        assert captured["xy-common-params"] == "platform=iOS&sid=session.custom123"

    async def test_xhs_sid_builtin_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("XHS_SESSION_SID", raising=False)
        monkeypatch.setattr(sp.utils, "read_ini_value", lambda *a, **k: None)
        assert sp._read_xhs_sid() == sp._XHS_BUILTIN_SESSION_SID

    async def test_xhs_sid_config_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 三级覆盖：env > config.ini [Cookie] xhs_session_sid > 内置缺省（与 F-10/CR-12 同模式）
        monkeypatch.delenv("XHS_SESSION_SID", raising=False)
        monkeypatch.setattr(sp.utils, "read_ini_value", lambda *a, **k: " session.cfg ")
        assert sp._read_xhs_sid() == "session.cfg"

    async def test_twitch_usher_params_ua_consistent_and_single_encoded(self) -> None:
        raw = _unwrap(sp.get_twitchtv_stream_data)
        responses = [
            # PlaybackAccessToken（单查询，dict 响应）
            '{"data": {"streamPlaybackAccessToken": {"value": "tk", "signature": "sg"}}}',
            # ChannelShell（批量查询，list 响应，在 get_twitchtv_room_info 内发出）
            '[{"data": {"userOrError": {"login": "usr", "displayName": "D", "stream": {"id": 1}}}}]',
            # usher 主清单（get_play_url_list 拉取）
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nhttps://a/720p.m3u8\n",
        ]
        with (
            patch.object(sp, "_ensure_twitch_client_id", new=AsyncMock(return_value="cid123")),
            patch.object(sp, "async_req", new=AsyncMock(side_effect=list(responses))),
        ):
            result = await raw("https://www.twitch.tv/someone")
        # m3u8_url 即拼出来的 usher 地址，参数正确性直接在其中断言
        m3u8 = str(result["m3u8_url"])
        assert "browser_version=148.0" in m3u8  # 与 UA rv:148.0 同源（旧值 124.0 自相矛盾）
        assert "os_version=NT%2010.0" in m3u8  # 单次编码（旧实现双重编码成 NT%252010.0）
        assert "%2520" not in m3u8


# ── MID-33（spider 半边）：模块级凭据全局补 TTL 与失效钩子 ────────────────────────


class TestMid33CredentialTtl:
    # TTL 判定与失效钩子都走真实 cookie_cache 实例；「fresh 短路」用例断言 async_req 被
    # 打桩为必炸 Mock——误把 TTL 改成永久有效或每次重取都会在这里现形。
    def test_kuaishou_did_ttl_expiry_forces_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cookie_cache.clear()
        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=old")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic() - 4000.0)  # > 30min

        async def fake_fetch_cookies(**kwargs: object) -> dict[str, str]:
            return {"did": "new", "didv": ""}

        monkeypatch.setattr(sp, "async_req", fake_fetch_cookies)
        got = asyncio.run(sp._ensure_kuaishou_did())
        # 旧行为：全局非空即永久返回被作废的旧 did，不重启进程永不自愈
        assert got == "did=new"
        assert sp._cached_kuaishou_did_ts == pytest.approx(time.monotonic(), abs=5)

    def test_kuaishou_did_fresh_cache_short_circuits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=fresh")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic())
        with patch.object(sp, "async_req", new=Mock(side_effect=AssertionError("must not refetch"))):
            assert asyncio.run(sp._ensure_kuaishou_did()) == "did=fresh"

    def test_twitch_client_id_ttl_expiry_forces_refetch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cookie_cache.clear()
        monkeypatch.setattr(sp, "_cached_twitch_client_id", "stale_client_id_value1")
        monkeypatch.setattr(sp, "_cached_twitch_client_id_ts", time.monotonic() - 4000.0)
        html = '<html>"Client-ID" : "freshclientid000000000000"</html>'
        monkeypatch.setattr(sp, "async_req", AsyncMock(return_value=html))
        got = asyncio.run(sp._ensure_twitch_client_id())
        assert got == "freshclientid000000000000"

    def test_invalidate_hooks_clear_global_and_generic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cookie_cache.clear()

        async def _seed() -> None:
            async def _factory() -> str:
                return "did=one"

            await cookie_cache.singleflight(key="kuaishou_did|", factory=_factory, timeout=5)
            await cookie_cache.singleflight(key="twitch_client_id|", factory=_factory, timeout=5)

        asyncio.run(_seed())
        monkeypatch.setattr(sp, "_cached_kuaishou_did", "did=one")
        monkeypatch.setattr(sp, "_cached_kuaishou_did_ts", time.monotonic())
        monkeypatch.setattr(sp, "_cached_twitch_client_id", "did=one")
        monkeypatch.setattr(sp, "_cached_twitch_client_id_ts", time.monotonic())
        sp.invalidate_kuaishou_did_cache()
        sp.invalidate_twitch_client_id_cache()
        assert sp._cached_kuaishou_did == "" and sp._cached_kuaishou_did_ts == 0.0
        assert sp._cached_twitch_client_id == "" and sp._cached_twitch_client_id_ts == 0.0

        # 通用缓存也被清：重新 singleflight 必然再次执行 factory（若只清全局，这里会命中旧值）
        calls = {"n": 0}

        async def _refetch() -> None:
            async def _factory() -> str:
                calls["n"] += 1
                return "did=two"

            await cookie_cache.singleflight(key="kuaishou_did|", factory=_factory, timeout=5)
            await cookie_cache.singleflight(key="twitch_client_id|", factory=_factory, timeout=5)

        asyncio.run(_refetch())
        assert calls["n"] == 2


# ── SEV-N02：popkontv 落盘 token 的双 "Bearer " 前缀 ──────────────────────────────


class TestSevN02PopkonBearerPrefix:
    # 归因判据（本工作区不做「改坏生产实现再跑」的变异验证，改用只有新逻辑能过的输入）：
    #   - 落盘侧未改成裸值 → test_refreshed_token_is_stored_bare 的第一条断言变红；
    #   - 读取侧未剥前缀 → 后两条（以落盘原值 / 已被旧版本写坏的存量值再进入时，
    #     Authorization 恰含一个前缀）变红。
    # 只打桩传输层（async_req / login_popkontv / get_popkontv_stream_data），
    # 前缀归一、长度 640 校验、statusCd 分支与 new_token 回传全部走真实代码。
    _TOKEN = "K" * 640  # 登录接口真实返回的 token 固定 640 字符（spider 的长度校验即以此为准）
    _E5000 = '{"statusCd":"E5000","statusMsg":"token expired"}'
    _OK = '{"statusCd":"L0000","statusMsg":"ok","data":{"castHlsUrl":"https://p/h.m3u8"}}'
    _URL = "https://www.popkontv.com/live/view?castId=cast1&partnerCode=P-00001"

    async def _call(self, access_token: str, bodies: list[str]) -> tuple[dict[str, object], list[str]]:
        # 返回 (解析结果, 每次请求实际发出的 Authorization)，桩响应按顺序取用
        raw = _unwrap(get_popkontv_stream_url)
        room_info = ["20260921", "P-00002", "cast1", 1, 0]
        queue = list(bodies)
        sent_auth: list[str] = []

        async def fake_req(*args: object, **kwargs: object) -> str:
            header = kwargs.get("headers")
            if isinstance(header, dict):
                auth = cast("dict[str, str]", header).get("Authorization")
                if auth:
                    sent_auth.append(auth)
            assert queue, "async_req 桩响应已用尽（说明解析链路多发了请求）"
            return queue.pop(0)

        with (
            patch.object(sp, "get_popkontv_stream_data", new=AsyncMock(return_value=("anchor1", room_info))),
            patch.object(sp, "login_popkontv", new=AsyncMock(return_value=(self._TOKEN, "P-00002"))),
            patch.object(sp, "async_req", new=fake_req),
            patch.object(sp, "logger", _fake_logger()),
        ):
            result = await raw(self._URL, access_token=access_token, username="user1", password="password125")
        return cast("dict[str, object]", result), sent_auth

    async def test_refreshed_token_is_stored_bare(self) -> None:
        # 首轮票据失效（E5000）→ 自动登录刷新：回传给 main.py 落盘的值必须是裸 token，
        # 而**请求头**仍要带 Bearer 前缀（两者只能有一处带前缀，否则下一轮必成双前缀）。
        result, sent_auth = await self._call("", [self._E5000, self._OK])
        assert result["new_token"] == self._TOKEN
        assert "Bearer" not in str(result["new_token"]), "落盘值自带前缀 → 下一轮读回即成双前缀"
        assert sent_auth[-1] == f"Bearer {self._TOKEN}"

    async def test_stored_value_reused_yields_single_prefix(self) -> None:
        # 闭环断言：把上一轮落盘的原值当作 access_token 传回（main.py 正是
        # read_config_value([Authorization] popkontv_token) → access_token），必须只一个前缀。
        result, _ = await self._call("", [self._E5000, self._OK])
        _, sent_auth = await self._call(str(result["new_token"]), [self._OK])
        assert sent_auth == [f"Bearer {self._TOKEN}"]
        assert sent_auth[0].count("Bearer ") == 1

    async def test_legacy_prefixed_config_self_heals(self) -> None:
        # 存量配置自愈（归因用例）：旧版本已把 "Bearer <token>" 整体写进 popkontv_token，
        # 读取侧必须剥掉既有前缀，否则发出 "Bearer Bearer <token>" → 服务端判失效 →
        # 每个检测轮次重跑一次明文账号密码登录。不得要求用户手工改配置文件。
        _, sent_auth = await self._call(f"Bearer   {self._TOKEN}  ", [self._OK])
        assert sent_auth == [f"Bearer {self._TOKEN}"]
        assert sent_auth[0].count("Bearer ") == 1


# ── M-05：popkontv mc_isPrivate 的形态判定（CODE_REVIEW_2026-10-02）────────────────


class TestPopkontvIsPrivateParsing:
    # 开播判定链上 mc_isPrivate 有三种现实下发形态：JSON 数字 0/1、JSON 布尔 false/true、
    # 字符串 "0"/"1"。旧实现 `int(cast(str, is_private))` 只对第一种成立——布尔经 str() 成
    # "True" 后 int() 抛 ValueError，被兜底装饰器吞成 {"is_live": False}，开播房间恒判未开播。
    # 变异判据：判定改成裸真值 `if is_private` → 字符串 "0" 的用例变红（bool("0") 是 True，
    # 公开房间被误判私有而整轮报错）；判定改回 int(str(...)) → 布尔与 "true"/"false" 变红。
    # 只打桩传输层（async_req / login_popkontv / get_popkontv_stream_data），
    # parse_config_bool 归一、statusCd 分支与结果组装一律走真实代码。
    _TOKEN = "K" * 640
    _OK = '{"statusCd":"L0000","statusMsg":"ok","data":{"castHlsUrl":"https://p/h.m3u8"}}'
    _URL = "https://www.popkontv.com/live/view?castId=cast1&partnerCode=P-00001"

    async def _resolve(self, is_private: object) -> tuple[dict[str, object] | None, str]:
        # 返回 (解析结果, 异常消息)：非私有形态应正常出流，私有形态应抛「private room」提示。
        raw = _unwrap(get_popkontv_stream_url)
        room_info = ["20260921", "P-00002", "cast1", 1, is_private]
        with (
            patch.object(sp, "get_popkontv_stream_data", new=AsyncMock(return_value=("anchor1", room_info))),
            patch.object(sp, "login_popkontv", new=AsyncMock(return_value=(self._TOKEN, "P-00002"))),
            patch.object(sp, "async_req", new=AsyncMock(return_value=self._OK)),
            patch.object(sp, "logger", _fake_logger()),
        ):
            try:
                result = await raw(self._URL, access_token=self._TOKEN, username="user1", password="password125")
            except Exception as exc:
                return None, f"{type(exc).__name__}: {exc}"
        return cast("dict[str, object]", result), ""

    @pytest.mark.parametrize("is_private", [0, "0", False, "", "false", None])
    async def test_public_room_forms_are_not_private(self, is_private: object) -> None:
        result, err = await self._resolve(is_private)
        assert err == "", f"公开房间形态 {is_private!r} 被判成私有/失败: {err}"
        assert result is not None and result.get("m3u8_url") == "https://p/h.m3u8"

    @pytest.mark.parametrize("is_private", [1, "1", True, "true"])
    async def test_private_room_forms_demand_password(self, is_private: object) -> None:
        # URL 不带 pwd：私有房必须给出「配置密码后重试」的可动作错误，而不是静默未开播。
        result, err = await self._resolve(is_private)
        assert result is None and "private room" in err, f"私有形态 {is_private!r} 未判定为私有: {err!r}"
