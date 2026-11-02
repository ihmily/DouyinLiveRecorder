# -*- coding: utf-8 -*-
# 2026-09-22 审查报告 / 组 E（src/spider.py + src/platforms/bilibili.py）修复的回归锁。
#
# 判据一律落在「失效形态本身」而不是「调用了某个函数」：
#   快手 playUrls 只含 h265 / "h264": null 时必须仍判开播并给出 h265 候选；
#   畅聊/音播 liveID 为 int 必须拼出正确地址、缺失必须判无源且留线索；
#   小红书 xhslink 跳转到外部 host 时不得携带 Cookie / xy-common-params；
#   getDanmuInfo 返回 evil.example.com 时不得建连、且不发 Cookie；
#   微博 / Look 只给 HLS 或只给 FLV 时必须判开播且 record_url 为该路；
#   斗鱼 betard 告警必须是 i18n.tr 模板（拼接形态提取器看不见，判据见用例内注释）；
#   斗鱼签名：enc_time="2" 解析为 2；上界一律夹到 32（用例取 1000 让「漏夹」可判定而不挂死）；
#             缺 rand_str / key 时返回 {} 并留 warning；
#   抖音 HTML 兜底成功后不得对同一 url 二次抓取；
#   buvid spi 空结果重试前必须有一次 await sleep（零间隔连击被判红）；
#   百度 data 取稳定键名 room_id 而非首个键。
#
# 原则：只打桩传输层（spider.async_req / WsClient），_loads_dict、_dig 系列、_warn_api_abnormal
# 与各平台解析逻辑一律走真实代码。

import asyncio
import contextlib
import types
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src import spider as sp

WAF_HTML = "<html><head><title>Access Protected</title></head><body>cf-browser-verification</body></html>"


def _asyncio_shim(**overrides: Any) -> types.SimpleNamespace:
    # 旧写法 patch.object(sp.asyncio, "sleep", …) 的容器是全进程唯一
    # 的 asyncio **模块本体**，替身窗口内 loguru 边车、pytest-asyncio 循环与其它协程的 sleep 一并被换掉。
    # 按仓库口径改为浅拷贝命名空间 + 只覆盖所需属性，再绑到**被测模块自己的 asyncio 引用**上。
    shim = types.SimpleNamespace(**vars(asyncio))
    for name, value in overrides.items():
        setattr(shim, name, value)
    return shim


def _fake_logger() -> types.SimpleNamespace:
    # 捕获 sp.logger.<level>(msg) 的文本（warning 是本文件「留线索」的判据级别）。
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


def _fake_req(payloads: dict[str, Any], default: str = WAF_HTML) -> AsyncMock:
    # 按 URL 子串路由的 async_req 替身；值可为 str 或 list（同 URL 多次请求依次取用）。
    queue: dict[str, list[Any]] = {
        key: (value if isinstance(value, list) else [value]) for key, value in payloads.items()
    }

    async def _req(*args: object, **kwargs: object) -> Any:
        url = str(kwargs.get("url") or (args[0] if args else ""))
        for key, items in queue.items():
            if key in url:
                assert items, f"{key} 的桩响应已用尽（说明解析链路多发了请求）"
                return items.pop(0)
        return default

    return AsyncMock(side_effect=_req)


# ────────────────────────────────────────────────────────────
# 快手 playUrls 的 codec 键遍历


# 快手页面把 playUrls 内联在 __INITIAL_STATE__ 里：正则 `(\{"liveStream".*?),"gameInfo`
# 抠出被 "gameInfo" 截断的内联串，再补一个右花括号收尾。故 payload 必须正好是
# `{"liveStream":{...}` 形态（其后紧跟 `,"gameInfo"`）。
def _kuaishou_html(play_urls_json: str) -> str:
    json_body = '{"liveStream":{"playUrls":' + play_urls_json + "}"
    return "<html><script>window.__INITIAL_STATE__=" + json_body + ',"gameInfo":{}};(function(){var s;</script></html>'


_H264_PLAYURLS = '{"h264":{"adaptationSet":{"representation":[{"url":"https://cdn/h264.flv"}]}}}'
_H265_ONLY_PLAYURLS = '{"h265":{"adaptationSet":{"representation":[{"url":"https://cdn/h265.flv"}]}}}'
_H264_NULL_PLAYURLS = '{"h264":null,"h265":{"adaptationSet":{"representation":[{"url":"https://cdn/h265.flv"}]}}}'


class TestKuaishouPlayUrlsCodec:
    @pytest.mark.asyncio
    async def test_h265_only_still_live_with_candidate(self) -> None:
        # 失效形态①：HEVC-only 房间只含 h265 键。旧实现落入「20241128 已失效」的 list 死分支
        # → 候选恒 [] → is_live 保持 False 且零日志。修复后必须判开播并给出 h265 候选。
        with patch.object(sp, "async_req", new=_fake_req({"live.kuaishou.com": _kuaishou_html(_H265_ONLY_PLAYURLS)})):
            result = await sp.get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
        assert result["is_live"] is True
        assert result["flv_url_list"] == [{"url": "https://cdn/h265.flv"}]

    @pytest.mark.asyncio
    async def test_h264_null_falls_back_to_h265(self) -> None:
        # 失效形态②："h264": null。旧实现 `"adaptationSet" not in None` 抛 TypeError →
        # 被 @trace_error_decorator 吞成未开播。修复后必须跳过 null 候选、落到 h265。
        with patch.object(sp, "async_req", new=_fake_req({"live.kuaishou.com": _kuaishou_html(_H264_NULL_PLAYURLS)})):
            result = await sp.get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
        assert result["is_live"] is True
        assert result["flv_url_list"] == [{"url": "https://cdn/h265.flv"}]

    @pytest.mark.asyncio
    async def test_h264_preferred_over_h265(self) -> None:
        # codec 优先级：h264 与 h265 同时存在时取 h264（与仓内其它平台 h264 优先的口径一致）。
        both = (
            '{"h264":{"adaptationSet":{"representation":[{"url":"https://cdn/h264.flv"}]}},'
            '"h265":{"adaptationSet":{"representation":[{"url":"https://cdn/h265.flv"}]}}}'
        )
        with patch.object(sp, "async_req", new=_fake_req({"live.kuaishou.com": _kuaishou_html(both)})):
            result = await sp.get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
        assert result["flv_url_list"] == [{"url": "https://cdn/h264.flv"}]

    @pytest.mark.asyncio
    async def test_representation_missing_is_empty_not_none(self) -> None:
        # 不对称修复：representation 缺失时不得把 None 与 is_live=True 一起返回（上层遍历候选会炸）。
        # 两个 codec 都缺 representation → 无候选，按无源返回并留线索。
        logger = _fake_logger()
        body = _kuaishou_html('{"h264":{"adaptationSet":{}}}')
        with (
            patch.object(sp, "async_req", new=_fake_req({"live.kuaishou.com": body})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_kuaishou_stream_data("https://live.kuaishou.com/u/testuser")
        assert result["is_live"] is False
        assert "flv_url_list" not in result
        assert any("playUrls" in m for m in logger.msgs), f"无候选时应留线索: {logger.msgs}"


# ────────────────────────────────────────────────────────────
# 畅聊 / 音播 liveID 判空与 str() 拼接


# 直播间页 var config 片段（get_live_domain 用 _loads_dict 解析后抠 flv/hls 域名），
# 故必须是合法 JSON（双引号）。
def _changliao_page(flv_domain: str, hls_domain: str) -> str:
    return (
        "var config = "
        + '{"domainpullstream_flv":"'
        + flv_domain
        + '","domainpullstream_hls":"'
        + hls_domain
        + '"}'
        + ";config.webskins"
    )


class TestChangliaoYinboLiveId:
    # liveID 在真实响应里是**数字**（同接口族的流星用例 test_spider_hardening.py 已记录该事实）。
    @pytest.mark.asyncio
    async def test_changliao_int_live_id_yields_real_address(self) -> None:
        api = '{"data":{"roomInfo":{"nickname":"畅聊主播","live_stat":1,"liveID":987654321}}}'
        payloads = {
            "live.ashx": api,
            "wap.tlclw.com/12345": _changliao_page("https://flv.example", "https://hls.example"),
        }
        with patch.object(sp, "async_req", new=_fake_req(payloads)):
            result = await sp.get_changliao_stream_url("https://wap.tlclw.com/12345")
        assert result["is_live"] is True
        # 旧实现 _dig_str 把 int 变空串 → 拼出 "https://flv.example/.flv" 这种只有域名的坏地址
        assert result["flv_url"] == "https://flv.example/987654321.flv"
        assert result["m3u8_url"] == "https://hls.example/987654321.m3u8"
        assert result["record_url"] == "https://flv.example/987654321.flv"

    @pytest.mark.asyncio
    async def test_changliao_missing_live_id_is_offline_with_clue(self) -> None:
        logger = _fake_logger()
        api = '{"data":{"roomInfo":{"nickname":"畅聊主播","live_stat":1}}}'
        payloads = {
            "live.ashx": api,
            "wap.tlclw.com/12345": _changliao_page("https://flv.example", "https://hls.example"),
        }
        with (
            patch.object(sp, "async_req", new=_fake_req(payloads)),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_changliao_stream_url("https://wap.tlclw.com/12345")
        # 旧实现：liveID 缺失仍无条件 is_live=True 并交出坏地址 → 两路候选全失败、每轮空烧请求
        assert result["is_live"] is False
        assert "flv_url" not in result
        assert any("liveID" in m for m in logger.msgs), f"缺 liveID 应留线索: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_yinbo_int_live_id_yields_real_address(self) -> None:
        api = '{"data":{"roomInfo":{"nickname":"音播主播","live_stat":1,"liveID":555}}}'
        page = _changliao_page("https://flv.yb", "https://hls.yb")
        payloads = {"live.ashx": api, "wap.ybw1666.com/800005143": page}
        with patch.object(sp, "async_req", new=_fake_req(payloads)):
            result = await sp.get_yinbo_stream_url("https://wap.ybw1666.com/800005143")
        assert result["is_live"] is True
        assert result["flv_url"] == "https://flv.yb/555.flv"
        assert result["m3u8_url"] == "https://hls.yb/555.m3u8"

    @pytest.mark.asyncio
    async def test_yinbo_missing_live_id_is_offline_with_clue(self) -> None:
        logger = _fake_logger()
        api = '{"data":{"roomInfo":{"nickname":"音播主播","live_stat":1}}}'
        page = _changliao_page("https://flv.yb", "https://hls.yb")
        payloads = {"live.ashx": api, "wap.ybw1666.com/800005143": page}
        with (
            patch.object(sp, "async_req", new=_fake_req(payloads)),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_yinbo_stream_url("https://wap.ybw1666.com/800005143")
        assert result["is_live"] is False
        assert any("liveID" in m for m in logger.msgs), f"缺 liveID 应留线索: {logger.msgs}"


# ────────────────────────────────────────────────────────────
# 小红书 xhslink 跳转后的凭据收口


class TestXhsRedirectCredentialContainment:
    @pytest.mark.asyncio
    async def test_external_redirect_drops_cookie_and_common_params(self) -> None:
        # 失效形态：xhslink 解出 evil.example.com 后仍用同一份 headers 再请求 → 凭据外泄。
        # 修复后：外部 host 的跳转被忽略；对落地页**不发起**带凭据的请求。
        sent: list[dict[str, object]] = []

        async def _req(*args: object, **kwargs: object) -> Any:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            sent.append({"url": url, "headers": kwargs.get("headers") or {}})
            if kwargs.get("redirect_url"):
                return "https://evil.example.com/steal"
            return ""

        with patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)):
            await sp.get_xhs_stream_url("https://xhslink.com/o/abc", cookies="SESSDATA=SECRET")

        # 不得向 evil.example.com 发起任何请求（那正是凭据被递送的目标）
        assert not any("evil.example.com" in cast(str, s["url"]) for s in sent), f"凭据被送往外部主机: {sent}"

    @pytest.mark.asyncio
    async def test_allowlisted_host_that_resolves_internal_is_rejected(self) -> None:
        # 失效形态：落地页 host 通过了「域族后缀」这一道闸，但 DNS 解析到内网/回环/云元数据（如
        # xiaohongshu.com→127.0.0.1）。仅查后缀会放行，于是把用户 Cookie 送给内网目标；修复后
        # 必须再过一次 web_config._host_internal_reason。
        sent: list[dict[str, object]] = []

        async def _req(*args: object, **kwargs: object) -> Any:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            sent.append({"url": url, "headers": kwargs.get("headers") or {}})
            if kwargs.get("redirect_url"):
                return "https://www.xiaohongshu.com/livestream/123"
            return "<html></html>"

        with (
            patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)),
            patch.object(sp.web_config, "_host_internal_reason", return_value="解析到内网地址 127.0.0.1"),
        ):
            await sp.get_xhs_stream_url("https://xhslink.com/o/abc", cookies="SESSDATA=SECRET")

        # 内网落地页必须被丢弃：不得对**该落地页**发起请求（凭据不外送）。
        # 丢弃后 url 回落到原始 xhslink 短链（其 host 由用户填写、可信），故 rstrip 精确匹配落地页前缀。
        assert not any(
            cast(str, s["url"]).startswith("https://www.xiaohongshu.com/livestream/") for s in sent
        ), f"内网落地页被请求: {sent}"

    @pytest.mark.asyncio
    async def test_allowed_redirect_keeps_cookie(self) -> None:
        # 合法 xiaohongshu.com 落地页：正常继续（第二次请求带 Cookie）。
        sent: list[dict[str, object]] = []

        async def _req(*args: object, **kwargs: object) -> Any:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            sent.append({"url": url, "headers": kwargs.get("headers") or {}})
            if kwargs.get("redirect_url"):
                return "https://www.xiaohongshu.com/livestream/123"
            return "<html></html>"

        with patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)):
            await sp.get_xhs_stream_url("https://xhslink.com/o/abc", cookies="SESSDATA=SECRET")

        landing = [s for s in sent if "www.xiaohongshu.com" in cast(str, s["url"])]
        assert landing, f"合法落地页应被请求: {sent}"
        assert cast(dict[str, str], landing[0]["headers"]).get("Cookie") == "SESSDATA=SECRET"


# ────────────────────────────────────────────────────────────
# B站弹幕 WS host 白名单


class TestBiliDanmakuHostAllowlist:
    def test_helper_rejects_non_official_domains(self) -> None:
        from src.platforms.bilibili import _bili_danmaku_host_allowed

        assert _bili_danmaku_host_allowed("broadcastlv.chat.bilibili.com")
        assert _bili_danmaku_host_allowed("broadcastlv2.chat.bilibili.com")
        # 后缀伪装不得放行（裸 endswith 会误判 notbilibili.com）
        assert not _bili_danmaku_host_allowed("evil.example.com")
        assert not _bili_danmaku_host_allowed("notbilibili.com")
        assert not _bili_danmaku_host_allowed("bilibili.com.evil.com")
        assert not _bili_danmaku_host_allowed("")

    @pytest.mark.asyncio
    async def test_evil_host_never_connected_and_no_cookie(self) -> None:
        # 失效形态：getDanmuInfo 返回的 host 被直接用作 WS 主机，连接时带上登录 Cookie。
        # 修复后：evil.example.com 被跳过、不建连，且绝不把 Cookie 发给它。
        from src.platforms.bilibili import BilibiliDanmaku

        connected: list[dict[str, object]] = []

        class _FakeWs:
            def __init__(self, **kwargs: object) -> None:
                connected.append(dict(kwargs))

            async def connect(self) -> None:
                return None

        d = BilibiliDanmaku()
        with patch("src.platforms.bilibili.WsClient", _FakeWs):
            await d.start(
                {
                    "server_host": "evil.example.com",
                    "host_list": ["evil.example.com", "broadcastlv.chat.bilibili.com"],
                    "room_id": 1,
                    "token": "TOKEN",
                    "buvid": "B",
                    "cookie": "SESSDATA=SECRET",
                }
            )

        # 不得向 evil.example.com 建连
        assert not any("evil.example.com" in cast(str, c.get("url", "")) for c in connected), connected
        # 唯一建连目标（若有）是白名单内的官方域
        for c in connected:
            assert cast(str, c.get("url", "")).startswith("wss://broadcastlv.chat.bilibili.com/")

    @pytest.mark.asyncio
    async def test_all_hosts_untrusted_degrades_without_connect(self) -> None:
        # 全部候选不可信时降级（不建连、不发凭据），而非退回去连不可信 host。
        from src.platforms.bilibili import BilibiliDanmaku

        connected: list[dict[str, object]] = []
        closed: list[str] = []

        class _FakeWs:
            def __init__(self, **kwargs: object) -> None:
                connected.append(dict(kwargs))

            async def connect(self) -> None:
                return None

        d = BilibiliDanmaku(on_close=lambda reason: closed.append(reason))
        with patch("src.platforms.bilibili.WsClient", _FakeWs):
            await d.start(
                {
                    "server_host": "evil.example.com",
                    "host_list": ["evil.example.com"],
                    "room_id": 1,
                    "token": "T",
                    "cookie": "SESSDATA=SECRET",
                }
            )
        assert connected == []
        assert closed, "全部 host 不可信时应通过 on_close 通知降级"


# ────────────────────────────────────────────────────────────
# 微博 / Look 单路源判开播


class TestSingleStreamSource:
    @pytest.mark.asyncio
    async def test_weibo_hls_only_is_live(self) -> None:
        # 失效形态：只下发 HLS 时 `not flv_url` 为真 → 每轮判未开播（静默、无线索）。
        # 修复后：判开播。HLS 走 m3u8 主通道，无需 record_url（两路齐备时的结构保持不变）。
        body = (
            '{"data":{"user_info":{"name":"微博主播"},"item":{"status":1,"desc":"标题",'
            '"stream_info":{"pull":{"live_origin_hls_url":"https://wb/a.m3u8"}}}}}'
        )
        with patch.object(sp, "async_req", new=_fake_req({"live_id=1": body})):
            result = await sp.get_weibo_stream_data("https://weibo.com/l/show/1")
        assert result["is_live"] is True
        # 第一组候选即真实下发的那一路；第二组是去画质后缀的兜底候选，此处样本无后缀故不同。
        candidates = cast(list[dict[str, str]], result["play_url_list"])
        assert candidates[0] == {"m3u8_url": "https://wb/a.m3u8", "flv_url": ""}

    @pytest.mark.asyncio
    async def test_weibo_flv_only_is_live(self) -> None:
        # 纯 FLV：无 HLS → 无 m3u8 主通道，必须补 record_url 承载该路，否则上层取不到流。
        body = (
            '{"data":{"user_info":{"name":"微博主播"},"item":{"status":1,"desc":"标题",'
            '"stream_info":{"pull":{"live_origin_flv_url":"https://wb/a.flv"}}}}}'
        )
        with patch.object(sp, "async_req", new=_fake_req({"live_id=1": body})):
            result = await sp.get_weibo_stream_data("https://weibo.com/l/show/1")
        assert result["is_live"] is True
        assert result["record_url"] == "https://wb/a.flv"

    @pytest.mark.asyncio
    async def test_look_hls_only_is_live(self) -> None:
        body = (
            '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":1,'
            '"roomInfo":{"liveType":2,"title":"t","liveUrl":{"hlsPullUrl":"http://lookcdn/a.m3u8"}}}}'
        )
        with patch.object(sp, "async_req", new=_fake_req({"room/get/v3": body})):
            result = await sp.get_looklive_stream_url("https://look.163.com/live?id=32108888")
        assert result["is_live"] is True
        assert result["record_url"] == "http://lookcdn/a.m3u8"

    @pytest.mark.asyncio
    async def test_look_flv_only_is_live(self) -> None:
        body = (
            '{"code":200,"data":{"anchor":{"nickName":"Look主播"},"liveStatus":1,'
            '"roomInfo":{"liveType":2,"title":"t","liveUrl":{"httpPullUrl":"http://lookcdn/a.flv"}}}}'
        )
        with patch.object(sp, "async_req", new=_fake_req({"room/get/v3": body})):
            result = await sp.get_looklive_stream_url("https://look.163.com/live?id=32108888")
        assert result["is_live"] is True
        assert result["record_url"] == "http://lookcdn/a.flv"


# ────────────────────────────────────────────────────────────
# 斗鱼 betard 告警的 i18n 形态（AST 判据）


class TestDouyuBetardLogI18n:
    def test_betard_warning_uses_tr_template(self) -> None:
        # 失效形态：用字符串拼接做首参 → 提取器（只看 JoinedStr / 常量）收不到该 msgid。
        # 判据：betard 分支里必须存在一个以 i18n.tr(...) 为首参、msgid 含 rid/reason 的 logger.warning。
        import ast
        import io

        src = io.open(sp.__file__, encoding="utf-8").read()
        tree = ast.parse(src)
        found = False
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "warning"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            # i18n.tr("斗鱼 betard 响应异常: rid={rid} reason={reason}", ...)
            if not (
                isinstance(first, ast.Call)
                and isinstance(first.func, ast.Attribute)
                and first.func.attr == "tr"
                and first.args
                and isinstance(first.args[0], ast.Constant)
                and isinstance(first.args[0].value, str)
            ):
                continue
            if "斗鱼 betard" in first.args[0].value and "{rid}" in first.args[0].value:
                found = True
                break
        assert found, "斗鱼 betard 告警必须用 i18n.tr 模板做首参（不得字符串拼接）"


# ────────────────────────────────────────────────────────────
# 斗鱼签名参数容错与 enc_time 上界


class TestDouyuSignHardening:
    def _patch(self, enc_key_json: str) -> Any:
        key_url_body = '{"error":0,"data":' + enc_key_json + "}"
        # md5 迭代次数 = enc_time + 1（最后一次固定追加 sign_str）。统计调用次数即可反推 enc_time。
        return patch.object(sp, "async_req", new=_fake_req({"getEncryption": key_url_body}))

    @pytest.mark.asyncio
    async def test_enc_time_string_two_parsed_as_two(self) -> None:
        # 失效形态：enc_time 以字符串 "2" 下发 → 旧实现退化为 0 次迭代 → auth 必被拒且零日志。
        calls = {"n": 0}
        real_md5 = sp.md5

        def _counting_md5(data: str) -> str:
            calls["n"] += 1
            return real_md5(data)

        body = '{"rand_str":"RS","key":"K","enc_time":"2","enc_data":"ED"}'
        with self._patch(body), patch.object(sp, "md5", _counting_md5):
            result = await sp.get_token_js("123", "did")
        assert result.get("auth"), result
        # 2 次迭代 + 结尾 1 次 = 3 次
        assert calls["n"] == 3, f"字符串 \"2\" 必须解析成 2（实际 md5 调用 {calls['n']} 次）"

    @pytest.mark.asyncio
    async def test_enc_time_huge_clamped_to_32(self) -> None:
        # 失效形态：enc_time 是响应驱动的无上界值 → 无上限 md5 链阻塞房间事件循环。取值 1000
        # （而非 10**9）是为了让「漏夹上界」表现为可判定的红（1001 次调用）而不是把用例挂死。
        calls = {"n": 0}
        real_md5 = sp.md5

        def _counting_md5(data: str) -> str:
            calls["n"] += 1
            return real_md5(data)

        body = '{"rand_str":"RS","key":"K","enc_time":1000,"enc_data":"ED"}'
        with self._patch(body), patch.object(sp, "md5", _counting_md5):
            result = await sp.get_token_js("123", "did")
        assert result.get("auth"), result
        # 夹到 32 → 32 + 1 = 33 次
        assert calls["n"] == 33, f"enc_time 必须夹到 32（实际 md5 调用 {calls['n']} 次）"

    @pytest.mark.asyncio
    async def test_missing_rand_str_or_key_returns_empty_with_warning(self) -> None:
        logger = _fake_logger()
        body = '{"rand_str":"RS","enc_time":0,"enc_data":"ED"}'  # 缺 key
        with self._patch(body), patch.object(sp, "logger", logger):
            result = await sp.get_token_js("123", "did")
        assert result == {}
        assert any("rand_str" in m for m in logger.msgs), f"缺 key 应留线索: {logger.msgs}"


# ────────────────────────────────────────────────────────────
# 抖音 HTML 兜底成功后不重复抓取


class TestDouyinNoDuplicateFetch:
    @pytest.mark.asyncio
    async def test_html_fallback_html_reused_for_hevc(self) -> None:
        # 失效形态：兜底成功后仍对**同一 url** 再抓一次只为取 hevc_flv_url（每轮多下载约 1MB）。
        # 判据：兜底路径下，对该房间 HTML url 的请求次数必须为 1（而非 2）。
        room_url = "https://live.douyin.com/123456"
        html_hits = {"n": 0}
        hevc_html = '<script>{"flv": "https://pull-flv-l1.douyincdn.com/stream-1234567890.flv?only_audio=0"}</script>'

        async def _req(*args: object, **kwargs: object) -> Any:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            if "webcast/room/web/enter" in url:
                return ""  # 两次都空 → 触发 HTML 兜底
            if url == room_url:
                html_hits["n"] += 1
                # 内联 room 数据里 status=2（开播）且有 stream_url，使后续走 hevc 提取
                return hevc_html
            return ""

        room_data = {
            "status": 2,
            "anchor_name": "A",
            "stream_url": {"live_core_sdk_data": {"pull_data": {"stream_data": '{"data":{"origin":{"main":{}}}}'}}},
        }
        with (
            patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)),
            patch.object(sp, "_extract_room_data_from_html", return_value=room_data),
            patch.object(sp, "extract_douyin_hevc_flv_url", return_value="https://hevc.flv"),
        ):
            await sp.get_douyin_web_stream_data(room_url, cookies="ttwid=x")

        assert html_hits["n"] == 1, f"兜底 HTML 应只抓一次并复用（实际 {html_hits['n']} 次）"


# ────────────────────────────────────────────────────────────
# buvid spi 重试前有抖动退避


class TestBiliSpiRetryBackoff:
    @pytest.mark.asyncio
    async def test_spi_empty_retry_sleeps_between_attempts(self) -> None:
        # 失效形态：两次请求**零间隔**连击 spi —— CDN 探针侧有 _throttle_probe 限速，spi 这一路
        # 没有，固定节奏本身就是风控指纹；且「200 + 空 body」下 async_req 与 _loads_dict 都不抛，
        # 旧代码挂在 except 上的重试/告警永不执行，真正需要归因的「两跳皆空」反而零日志。
        # 判据：空结果重试前必须 await asyncio.sleep（>0；生产取 0.5~1.0 的抖动区间）。
        body_room = '{"code":0,"data":{"room_id":1,"uid":2}}'
        body_nav = '{"code":0,"data":{"wbi_img":{"img_url":"https://i0.hdslb.com/x/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.png","sub_url":"https://i0.hdslb.com/x/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png"}}}'
        payloads = {"room_init": body_room, "nav": body_nav, "finger/spi": ""}

        slept: list[float] = []
        real_sleep = asyncio.sleep  # 反向见证基准：替身窗口结束后 stdlib 本体必须仍是这一支

        async def _rec_sleep(delay: float, *a: object, **k: object) -> None:
            slept.append(float(delay))
            # 不真的睡，避免拖慢用例；记录参数即可判定「有退避」
            return None

        # 落点由 sp.asyncio 改成 sp 命名空间里的 asyncio 引用位（shim 见文件头）：
        # 旧形态的宿主是全进程唯一的 asyncio 本体，窗口内 loguru 边车与任何其它协程的 sleep 一并被换桩。
        with (
            patch.object(sp, "async_req", new=_fake_req(payloads)),
            patch.object(sp, "_cache_fetch_cookies", new=AsyncMock(return_value={})),
            patch.object(sp, "asyncio", new=_asyncio_shim(sleep=_rec_sleep)),
        ):
            # 反向见证必须落在窗口**内**才有判定力：此刻 sp.asyncio 是 shim、而 stdlib asyncio
            # 本体的 sleep 仍要是真实现。旧写法（容器为 sp.asyncio）在这一行必红——它改的正是本体。
            assert asyncio.sleep is real_sleep, "asyncio 本体被替换：shim 形态失效，泄漏面回到全进程协程"
            await sp.get_bilibili_danmaku_info("https://live.bilibili.com/462")

        # 至少一次正数退避（抖动区间 0.5~1.0），证明不是零间隔连击
        assert any(0.4 < d <= 1.0 for d in slept), f"spi 空结果重试前应有抖动退避，实际 sleep: {slept}"


# ────────────────────────────────────────────────────────────
# 百度 data 取稳定键名


class TestBaiduStableKey:
    @pytest.mark.asyncio
    async def test_uses_room_id_key_not_first_key(self) -> None:
        # 失效形态：取 data 的首个键。若响应里先出现别的键（如 "extra"），会取错对象。
        # 修复后按稳定键名 room_id 取值。
        import json as _json

        body = _json.dumps(
            {
                "data": {
                    "extra": {"status": "1"},
                    "9175031377": {
                        "status": "0",
                        "host": {"name": "百度主播"},
                        "video": {"title": "带货直播", "url_clarity_list": [{"urls": {"flv": "https://f/abc.flv"}}]},
                    },
                }
            },
            ensure_ascii=False,
        )
        with patch.object(sp, "async_req", new=_fake_req({"searchbox": body})):
            result = await sp.get_baidu_stream_data(
                "https://live.baidu.com/m/media/pclive/pchome/live.html?room_id=9175031377"
            )
        # extra 的 status="1" 未开播；room_id 的 status="0" 开播 → 按稳定键取必须判开播
        assert result["is_live"] is True
        assert result["anchor_name"] == "百度主播"
        assert result["play_url_list"] == ["https://hls.liveshow.bdstatic.com/live/abc.m3u8"]


# ────────────────────────────────────────────────────────────
# CODE_REVIEW_2026-09-22.md §5.1「平台解析与网络层」轻微项（与上文同号条目
# 来自不同分组，故每条在类注释里写明报告出处与失效形态）：
#   虎牙字母房间号反查须剥引号 + 判 isdigit，非数字一律早抛「请用数字房间号」；
#   虎牙候选：HLS 地址不得由 FLV 票据裁决（只下发 HLS 票据的房间须给出 HLS 候选）；
#   斗鱼 websec：enc_time 缺失/非数值须与 rand_str/key 同走 warning + return {}；
#   SOOP bj_id 三处共用 _soop_bj_id_from_url（/play/<bj> 形态不得取到 "play"）；
#   Shopee 无 session 时不得请求 /session/None，更不得每轮刷 ERROR；
#   连接直播 videoUrl 不带查询串时归因 + 按未开播返回；
#   Faceit 缺 /stream 段须抛可读 ValueError 而非 IndexError；
#   淘宝 SUCCESS 改判前缀 + data 走 _dig；
#   ShowRoom 命中 hls_all 但 url 为空不得返回 {is_live: True, m3u8_url: ""}。


def _raw(func: object) -> Any:
    # 取 trace_error_decorator 装饰前的原函数：这些用例的判据是「抛什么错 / 发不发请求」，
    # 装饰器会把异常统一吞成 {"is_live": False}，正好掩盖要锁的失效形态。
    return cast(Any, getattr(func, "__wrapped__"))


def _recording_req(bodies: dict[str, str], seen: list[str], default: str = "") -> AsyncMock:
    # 与 _fake_req 同一路由口径，但**记录每次请求的完整 URL**：/2210/2211 的判据都在
    # 「发出去的 URL/表单取值」上，只看返回值无法区分 roomid=6030242 与 %226030242%22。
    async def _req(*args: object, **kwargs: object) -> str:
        url = str(kwargs.get("url") or (args[0] if args else ""))
        seen.append(url)
        for key, body in bodies.items():
            if key in url:
                return body
        return default

    return AsyncMock(side_effect=_req)


def _huya_req(page_body: str, api_body: str, seen: list[str]) -> AsyncMock:
    # 虎牙两跳：字母房间号先抓**房间页**（URL 即用户填的地址），再打 mp.huya.com 小程序接口。
    # 页请求按「非 cache.php」路由，避免为此给房间 URL 再编一个桩键。
    async def _req(*args: object, **kwargs: object) -> str:
        url = str(kwargs.get("url") or (args[0] if args else ""))
        seen.append(url)
        return api_body if "cache.php" in url else page_body

    return AsyncMock(side_effect=_req)


# ────────────────────────────────────────────────────────────
# 虎牙小程序接口

_HUYA_OFF = '{"data": {"profileInfo": {"nick": "虎牙主播"}, "realLiveStatus": "OFF"}}'


def _huya_on(entries: str) -> str:
    return (
        '{"data": {"profileInfo": {"nick": "虎牙主播"}, "realLiveStatus": "ON",'
        ' "stream": {"baseSteamInfoList": [' + entries + "]}}}"
    )


class TestHuyaLetterRoomId:
    @pytest.mark.asyncio
    async def test_quoted_profile_room_strips_quotes_before_request(self) -> None:
        # 失效形态：页面内联 "ProfileRoom":"6030242"（字符串形态）时非贪婪捕获连引号一起收下
        # → roomid=%226030242%22 → 接口恒返回空房间，所有字母号虎牙房间静默按未开播。
        seen: list[str] = []
        page = 'var h = {"ProfileRoom":"6030242","sPrivateHost":true};'
        with patch.object(sp, "async_req", new=_huya_req(page, _HUYA_OFF, seen)):
            result = await sp.get_huya_app_stream_url("https://www.huya.com/abcroom")
        assert result["is_live"] is False
        api_calls = [u for u in seen if "cache.php" in u]
        assert api_calls, f"字母号未走反查+小程序接口: {seen}"
        assert "roomid=6030242" in api_calls[0], api_calls[0]
        assert "%22" not in api_calls[0], f"引号被当成房间号的一部分发出去了: {api_calls[0]}"

    @pytest.mark.asyncio
    async def test_numeric_profile_room_still_resolved(self) -> None:
        # 数字形态（无引号）是页面的另一形态，剥引号必须幂等、不得把它打回未开播。
        seen: list[str] = []
        page = 'var h = {"ProfileRoom":6030242,"sPrivateHost":true};'
        with patch.object(sp, "async_req", new=_huya_req(page, _HUYA_OFF, seen)):
            await sp.get_huya_app_stream_url("https://www.huya.com/abcroom")
        assert any("roomid=6030242" in u for u in seen), seen

    @pytest.mark.asyncio
    async def test_letter_room_without_profile_field_raises_and_skips_api(self) -> None:
        # 页面改版取不到 ProfileRoom：必须早抛「请使用数字房间号链接」，不得再打小程序接口。
        seen: list[str] = []
        page = "页面改版后内联结构里再无 ProfileRoom 字段"
        with patch.object(sp, "async_req", new=_huya_req(page, _HUYA_OFF, seen)):
            with pytest.raises(Exception, match="room_number"):
                await _raw(sp.get_huya_app_stream_url)("https://www.huya.com/abcroom")
        assert not any("cache.php" in u for u in seen), f"反查失败仍发了接口请求: {seen}"

    @pytest.mark.asyncio
    async def test_non_digit_room_id_raises_without_any_request(self) -> None:
        # 「非数字/空串一律早抛」的最小形态：末段无字母（不走反查分支）也不是纯数字。
        # 旧实现对它照发 cache.php 请求；URL 以 / 结尾时 room_id 更是空串也照发。
        seen: list[str] = []
        page = ""
        with patch.object(sp, "async_req", new=_huya_req(page, _HUYA_OFF, seen)):
            with pytest.raises(Exception, match="room_number"):
                await _raw(sp.get_huya_app_stream_url)("https://www.huya.com/12-34/")
        assert seen == [], f"非数字房间号仍发出了请求: {seen}"

    @pytest.mark.asyncio
    async def test_trailing_slash_numeric_room_still_requested(self) -> None:
        # rstrip("/") 的行为锁：同一房间带尾斜杠与不带尾斜杠必须走同一个 roomid。
        seen: list[str] = []
        page = ""
        with patch.object(sp, "async_req", new=_huya_req(page, _HUYA_OFF, seen)):
            await sp.get_huya_app_stream_url("https://www.huya.com/6030242/")
        assert seen and "roomid=6030242" in seen[0], seen

    def test_letter_room_regex_matches_twin_copy(self) -> None:
        # 反向漂移防线：主实现的正则串与孪生副本 scripts/douyin_live_recorder_standalone.py 的
        # _HUYA_PROFILE_ROOM_RE 必须逐字一致。用 AST 取字符串常量而非扫源码文本（两处的引号/转义
        # 形态不同，文本比对会自欺）。
        import ast
        from pathlib import Path

        root = Path(sp.__file__).resolve().parent.parent

        def patterns(path: Path) -> set[str]:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            return {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and "ProfileRoom" in node.value
            }

        main_patterns = patterns(root / "src" / "spider.py")
        twin_patterns = patterns(root / "scripts" / "douyin_live_recorder_standalone.py")
        assert main_patterns, "主实现里找不到 ProfileRoom 正则常量"
        assert main_patterns == twin_patterns, f"两副本正则串不一致: {main_patterns} != {twin_patterns}"


class TestHuyaHlsOnlyCandidate:
    @pytest.mark.asyncio
    async def test_hls_only_ticket_still_yields_hls_candidate(self) -> None:
        # 失效形态：整条 entry 的有效性由 **FLV 票据** 裁决，而 HLS 地址只依赖 sHlsUrl +
        # sHlsAntiCode → 只下发 HLS 票据的房间连 HLS 候选都被砍掉，全部线路如此即「在播但零候选」。
        entries = '{"sCdnType":"AL","sStreamName":"n1","sHlsUrl":"http://al.hls.example.com","sHlsAntiCode":"a=1"}'
        with patch.object(sp, "async_req", new=_huya_req("", _huya_on(entries), [])):
            result = await sp.get_huya_app_stream_url("https://www.huya.com/12345")
        assert result["is_live"] is True
        assert result["m3u8_url"] == "http://al.hls.example.com/n1.m3u8?a=1", result
        assert not result["flv_url"], result
        assert result["record_url"] is None, result
        assert result["m3u8_url_list"] == ["http://al.hls.example.com/n1.m3u8?a=1"]
        assert result["flv_url_list"] == []

    @pytest.mark.asyncio
    async def test_flv_only_ticket_still_yields_flv_and_record(self) -> None:
        entries = '{"sCdnType":"HS","sStreamName":"n2","sFlvUrl":"http://hs.flv.example.com","sFlvAntiCode":"f=1"}'
        with patch.object(sp, "async_req", new=_huya_req("", _huya_on(entries), [])):
            result = await sp.get_huya_app_stream_url("https://www.huya.com/12345")
        assert result["flv_url"] == "http://hs.flv.example.com/n2.flv?f=1", result
        assert result["record_url"] == "http://hs.flv.example.com/n2.flv?f=1", result
        assert not result["m3u8_url"], result

    @pytest.mark.asyncio
    async def test_entry_without_any_ticket_is_not_added_as_empty_candidate(self) -> None:
        # 放宽判据后必须补回这条：两路票据皆缺的 entry 不得进候选，否则会返回
        # 「is_live=True 且 m3u8_url/flv_url 全空」的坏候选（每轮白烧探针）。
        entries = '{"sCdnType":"AL","sStreamName":"n3"}'
        with patch.object(sp, "async_req", new=_huya_req("", _huya_on(entries), [])):
            result = await sp.get_huya_app_stream_url("https://www.huya.com/12345")
        assert result == {"anchor_name": "虎牙主播", "is_live": True}, result


# ────────────────────────────────────────────────────────────
# 后半：斗鱼 websec 的 enc_time 缺失/非数值


class TestDouyuWebsecEncTime:
    def _patch(self, enc_key_json: str) -> Any:
        body = '{"error":0,"data":' + enc_key_json + "}"
        return patch.object(sp, "async_req", new=_fake_req({"getEncryption": body}))

    @pytest.mark.asyncio
    async def test_missing_enc_time_warns_and_returns_empty(self) -> None:
        # 失效形态：原 `enc_key.get("enc_time", 0)` + `except: enc_time = 0` 让「缺字段」静默退化成 0
        # 次迭代——产出的 auth 必被服务端拒，调用方只见「无流」，与函数注释承诺的「三字段任一缺失
        # 即 warning 并 return {}」相反。
        logger = _fake_logger()
        body = '{"rand_str":"RS","key":"K","enc_data":"ED"}'
        with self._patch(body), patch.object(sp, "logger", logger):
            result = await sp.get_token_js("123", "did")
        assert result == {}
        assert any("enc_time" in m for m in logger.msgs), f"enc_time 缺失未留线索: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_non_numeric_enc_time_warns_and_returns_empty(self) -> None:
        logger = _fake_logger()
        body = '{"rand_str":"RS","key":"K","enc_time":"abc","enc_data":"ED"}'
        with self._patch(body), patch.object(sp, "logger", logger):
            result = await sp.get_token_js("123", "did")
        assert result == {}
        assert any("enc_time" in m for m in logger.msgs), f"enc_time 非数值未留线索: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_explicit_zero_enc_time_is_silent_success(self) -> None:
        # 反向防线：enc_time **确为 0** 是合法取值（0 次迭代 + 末次签名），
        # 不得被上面的「缺失即告警」一起打死，也不得刷日志。
        logger = _fake_logger()
        body = '{"rand_str":"RS","key":"K","enc_time":0,"enc_data":"ED"}'
        with self._patch(body), patch.object(sp, "logger", logger):
            result = await sp.get_token_js("123", "did")
        assert result.get("auth"), result
        assert logger.msgs == [], f"正常签名轮刷了日志: {logger.msgs}"


# ────────────────────────────────────────────────────────────
# SOOP bj_id 的取段


class TestSoopBjIdFromUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            # 旧段数启发式对这条命中 len<6 分支、取到字面量 "play" → /live/play/master.m3u8 永久失败
            ("https://www.sooplive.co.kr/play/oul282", "oul282"),
            ("https://www.sooplive.co.kr/channel/oul282", "oul282"),
            ("https://www.sooplive.com/live/oul282", "oul282"),
            # 旧实现同结果的两条，不得因修复而回归
            ("https://play.sooplive.co.kr/oul282/249469582", "oul282"),
            ("https://www.sooplive.co.kr/oul282", "oul282"),
            # 尾斜杠/查询串不参与切段（旧写法在 ≥6 段分支上会取到空串）
            ("https://www.sooplive.co.kr/play/oul282/", "oul282"),
            ("https://www.sooplive.co.kr/play/oul282?bno=249469582", "oul282"),
            ("https://www.sooplive.co.kr", ""),  # 畸形：回空串交由调用方既有分支处理，不抛错
        ],
    )
    def test_bj_id_by_url_form(self, url: str, expected: str) -> None:
        assert sp._soop_bj_id_from_url(url) == expected

    def test_three_call_sites_share_one_implementation(self) -> None:
        # 同一条启发式此前在 get_sooplive_tk / _fetch_web_stream_data_global /
        # get_sooplive_stream_data 各复制一份（改一处漏两处），锁住「只剩一处实现」。
        import re
        from pathlib import Path

        src = Path(sp.__file__).read_text(encoding="utf-8")
        assert len(re.findall(r"^\s*bj_id = _soop_bj_id_from_url\(url\)$", src, re.M)) == 3, "三处调用点未共用辅助函数"
        assert "split_url[3] if len(split_url) < 6" not in src, "段数启发式复活"

    @pytest.mark.asyncio
    async def test_play_form_reaches_api_with_real_bjid(self) -> None:
        seen: list[str] = []
        captured: dict[str, object] = {}
        body = '{"result":"01","CHANNEL":{"BJNICK":"N","BJID":"oul282","BNO":249469582}}'

        async def _req(*args: object, **kwargs: object) -> str:
            url = str(kwargs.get("url") or (args[0] if args else ""))
            seen.append(url)
            captured["data"] = kwargs.get("data")
            return body

        with patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)):
            await _raw(sp.get_sooplive_tk)("https://www.sooplive.co.kr/play/oul282", rtype="info")
        assert "bjid=oul282" in seen[0], seen
        form = cast("dict[str, object]", captured["data"])
        assert form["bid"] == "oul282", form


# ────────────────────────────────────────────────────────────
# Shopee 无 session


class TestShopeeMissingSession:
    @pytest.mark.asyncio
    async def test_no_session_sends_no_request_and_logs_nothing(self) -> None:
        # 失效形态：session_id 为 None 时照发 /api/v1/session/None（白发一次请求），随后每轮（默认
        # 120s）输出一条 **ERROR** 叫用户「更换房间地址」——地址没问题、只是没开播，正踩「正常轮次
        # 刻意静默，否则真线索被淹掉」的口径。
        seen: list[str] = []
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_recording_req({}, seen)),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_shopee_stream_url("https://live.shopee.sg/share?from=live")
        assert result["is_live"] is False
        assert seen == [], f"无 session 仍发了请求: {seen}"
        assert logger.msgs == [], f"未开播轮次刷了 ERROR/WARNING: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_envelope_without_data_still_errors(self) -> None:
        # ERROR 只保留给「确实拉到会话信封、里面却没有 data」这一确定失效形态。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"/session/": '{"message":"bad session"}'})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_shopee_stream_url("https://live.shopee.sg/share?session=802458")
        assert result["is_live"] is False
        assert any("please update the address" in m for m in logger.msgs), logger.msgs

    @pytest.mark.asyncio
    async def test_empty_response_warns_without_error(self) -> None:
        # 空响应（风控/网络）归因走 _warn_api_abnormal，不该冒领「地址失效」这条 ERROR。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"/session/": ""})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_shopee_stream_url("https://live.shopee.sg/share?session=802458")
        assert result["is_live"] is False
        assert not any("please update the address" in m for m in logger.msgs), logger.msgs
        assert any("Shopee session" in m for m in logger.msgs), logger.msgs


# ────────────────────────────────────────────────────────────
# 连接直播 videoUrl 无查询串


class TestLianjieQuerylessVideoUrl:
    def _body(self, video_url: str) -> str:
        return (
            '{"data": {"nickname": "连接主播", "isonline": 1, "defaultRoomTitle": "T",'
            ' "videoUrl": "' + video_url + '"}}'
        )

    @pytest.mark.asyncio
    async def test_queryless_webrtc_returns_not_live_with_clue(self) -> None:
        # 失效形态：flv/m3u8 全靠 `replace("?", ".flv?")` 插后缀，videoUrl 不带 ? 时三个地址字段
        # 同指原始无扩展路径 → stream_select 无从判容器、ffmpeg 每轮失败，而 is_live=True 把这一轮
        # 记成**成功解析样本**，熔断统计看不出线路已坏。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"getRoomInfo": self._body("webrtc://cdn/live/r1")})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_lianjie_stream_url("https://www.lailianjie.com/r1")
        assert result["is_live"] is False
        assert "flv_url" not in result and "m3u8_url" not in result, result
        assert any("videoUrl" in m for m in logger.msgs), f"缺归因线索: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_webrtc_with_query_still_builds_suffixed_urls(self) -> None:
        # 正常形态不得受影响：后缀插在查询串**之前**，且成功路径零告警。
        logger = _fake_logger()
        with (
            patch.object(sp, "async_req", new=_fake_req({"getRoomInfo": self._body("webrtc://cdn/live/r1?token=x")})),
            patch.object(sp, "logger", logger),
        ):
            result = await sp.get_lianjie_stream_url("https://www.lailianjie.com/r1")
        assert result["is_live"] is True
        assert result["flv_url"] == "https://cdn/live/r1.flv?token=x", result
        assert result["m3u8_url"] == "https://cdn/live/r1.m3u8?token=x", result
        assert logger.msgs == [], logger.msgs


# ────────────────────────────────────────────────────────────
# Faceit 昵称提取


class TestFaceitNicknameExtraction:
    @pytest.mark.asyncio
    async def test_profile_page_without_stream_raises_readable_error(self) -> None:
        # 用户粘贴不带 /stream 的资料页：旧写法 findall(...)[0] 抛 IndexError，日志只剩一行
        # "IndexError … in get_faceit_stream_data"，与本文件其余「if not m: raise ValueError(...)」
        # 的可读线索不同。
        seen: list[str] = []
        with patch.object(sp, "async_req", new=_recording_req({}, seen)):
            with pytest.raises(ValueError, match="Failed to find faceit nickname"):
                await _raw(sp.get_faceit_stream_data)("https://www.faceit.com/zh/players/testuser")
        assert seen == [], f"昵称都没取到就发了请求: {seen}"

    @pytest.mark.asyncio
    async def test_stream_url_still_extracted(self) -> None:
        # 反向防线：带 /stream 的正规链接不得被判成「取不到昵称」。
        with patch.object(sp, "async_req", new=_fake_req({"nicknames": '{"payload": {"id": 7}}'})):
            result = await _raw(sp.get_faceit_stream_data)("https://www.faceit.com/zh/players/testuser/stream")
        assert result == {"anchor_name": "", "is_live": False}, result


# ────────────────────────────────────────────────────────────
# 淘宝 SUCCESS 分支


class TestTaobaoSuccessParsing:
    TICKET = "f7e0d3a4b5c6d7e8f9a0b1c2d3e4f5a6_1777000000000"
    URL = "https://h5.m.taobao.com/taolive/video.html?id=a&liveId=500123"

    @staticmethod
    def _jsonp(ret_msg: str, data: dict[str, object] | None) -> str:
        import json as _json

        obj: dict[str, object] = {"ret": [ret_msg]}
        if data is not None:
            obj["data"] = data
        return "mtopjsonp1(" + _json.dumps(obj, ensure_ascii=False) + ")"

    async def _call(self, body: str, logger: types.SimpleNamespace) -> Any:
        # 只打桩传输层：JSONP 解析、票据判定、签名与轮次控制一律走真实代码。
        # 响应的 Set-Cookie 给空 dict（真实形态只含响应票据），避免顺带回写配置文件。
        async def _req(*args: object, **kwargs: object) -> tuple[str, dict[str, str]]:
            return body, {}

        with (
            patch.object(sp, "async_req", new=AsyncMock(side_effect=_req)),
            patch.object(sp, "logger", logger),
        ):
            return await sp.get_taobao_stream_url(self.URL, cookies=f"unb=1; _m_h5_tk={self.TICKET}")

    _LIVE_DATA: dict[str, object] = {
        "broadCaster": {"accountName": "测试店铺"},
        "streamStatus": "1",
        "title": "T",
        "liveUrlList": [{"definition": "hd", "flvUrl": "https://f/hd.flv"}],
    }

    @pytest.mark.asyncio
    async def test_success_with_changed_suffix_still_parsed(self) -> None:
        # 失效形态：`ret == ["SUCCESS::调用成功"]` 全等比较把 :: 后的文案当成契约的一部分，
        # 淘宝改文案（该后缀本就随版本变过）即整体判成非 SUCCESS → 持续「拿不到流」且无日志。
        result = await self._call(self._jsonp("SUCCESS::新的文案", self._LIVE_DATA), _fake_logger())
        assert result["is_live"] is True, result
        assert result["anchor_name"] == "测试店铺", result

    @pytest.mark.asyncio
    async def test_success_without_data_warns_and_returns_offline(self) -> None:
        # 失效形态：`json_data["data"]` 裸索引（该口径在本文件的最后一处残留）抛 KeyError
        # 被装饰器吞成「未开播」，既无归因也丢掉了 anchor_name 字段。
        logger = _fake_logger()
        result = await self._call(self._jsonp("SUCCESS::调用成功", None), logger)
        assert result == {"anchor_name": "", "is_live": False}, result
        assert any("livedetail" in m for m in logger.msgs), f"缺归因线索: {logger.msgs}"

    @pytest.mark.asyncio
    async def test_non_success_still_falls_through_to_retry(self) -> None:
        # 反向防线：前缀判定不得把「非 SUCCESS」也放进来（令牌过期类文案仍要走第二轮换票）。
        logger = _fake_logger()
        result = await self._call(self._jsonp("FAIL_SYS_TOKEN_EXOIRED::令牌过期", self._LIVE_DATA), logger)
        assert result["is_live"] is False, result


# ────────────────────────────────────────────────────────────
# ShowRoom 的 hls_all 空 url


class TestShowroomHlsAllEmptyUrl:
    _LIVE = '{"room_name": "SR主播", "live_status": 2}'

    def _streams(self, entries: str) -> str:
        return '{"streaming_url_list": [' + entries + "]}"

    async def _call(
        self, stream_body: str, logger: types.SimpleNamespace, playlist: list[str] | None = None
    ) -> dict[str, object]:
        payloads = {"live_info": self._LIVE, "streaming_url": stream_body}
        with (
            patch.object(sp, "async_req", new=_fake_req(payloads)),
            patch.object(sp, "logger", logger),
            patch.object(sp, "get_play_url_list", new=AsyncMock(return_value=playlist or [])),
        ):
            return cast("dict[str, object]", await sp.get_showroom_stream_data(self.URL))

    URL = "https://www.showroom-live.com/room/profile?room_id=123"

    @pytest.mark.asyncio
    async def test_hls_all_with_empty_url_is_not_live(self) -> None:
        # 失效形态：is_live 在 live_status==2 处已无条件置 True，而 m3u8_url 先于判空被赋值 →
        # 返回 {is_live: True, m3u8_url: ""}，坏候选进选源、每轮白烧探针。
        result = await self._call(self._streams('{"type": "hls_all", "url": ""}'), _fake_logger())
        assert result["is_live"] is False, result
        assert "m3u8_url" not in result, result

    @pytest.mark.asyncio
    async def test_no_hls_all_entry_is_not_live_with_clue(self) -> None:
        # 列表里根本没有 hls_all（改版换了 type 名）同属「拿不到任何线路」，须复用同一条告警。
        logger = _fake_logger()
        result = await self._call(self._streams('{"type": "http_loop", "url": "https://cdn/x.m3u8"}'), logger)
        assert result["is_live"] is False, result
        assert any("ShowRoom streaming_url" in m for m in logger.msgs), logger.msgs

    @pytest.mark.asyncio
    async def test_success_path_unchanged_and_silent(self) -> None:
        logger = _fake_logger()
        result = await self._call(
            self._streams('{"type": "hls_all", "url": "https://cdn/a/1080.m3u8"}'),
            logger,
            playlist=["720/index.m3u8", "https://cdn2/b.m3u8"],
        )
        assert result["is_live"] is True, result
        assert result["m3u8_url"] == "https://cdn/a/1080.m3u8", result
        # 相对行走 urljoin、绝对行原样，最后统一降级 http（既有硬约定，不得回退）
        assert result["play_url_list"] == ["http://cdn/a/720/index.m3u8", "http://cdn2/b.m3u8"], result
        assert logger.msgs == [], logger.msgs
