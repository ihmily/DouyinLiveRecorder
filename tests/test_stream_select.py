# 本文件锁住 src/stream_select.py 选源层的探针与选序行为，按主题分块；全程 mock httpx.Client，不触网。
# ① 流地址校验的末位候选（last_resort）放行语义：
# - 斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁用 HEAD 方法），ffmpeg 实际 GET 拉流正常；
# - 末位候选（无备选可回退）稳定拒绝也仅告警放行，交由 ffmpeg 定夺；
# - 非末位候选仍判不可达，由上层回退下一候选。
# 另覆盖虎牙探针退避：CDN 限流（连续 403）时跳过探针、末位直接放行 ffmpeg。
# ② 档位与形态：
# - MID-19 交给 ffmpeg -i 的地址必须过协议+形态白名单（rtmp 合法、file:///concat:/相对路径/
#   以 - 开头一律丢弃且不享受末位放行）；
# - MID-18 record_url 通道同受「HLS 整组剔除」约束（排除平台下 m3u8 record_url 零探针），
#   且与序列候选同址时复用本轮结论、不重复烧 CDN 连接预算；
# - MIN-02 分片被拒的退避键必须是播放列表 URL（分片键是永不被读的死条目）；
# - MIN-03 master playlist 按 BANDWIDTH 探最高变体（顺序不可信，防「证明低档、实拉高档」假绿）。
# ③ 代理归一与降级（SEV-N05）：
# - 两处 httpx.Client 构造点的 proxy 实参必须经 utils.handle_proxy_addr 归一（裸 ip:port →
#   http:// 前缀、空串 → None），否则选源每轮抛穿房间线程；
# - 探针客户端构造失败须降级为「本轮无可用探针客户端」+ 末位放行，不得抛穿、不得放弃本轮；
# - 同一裸 ip:port 下同步选源与异步 get_response_status 必须得到同一 proxy 结论
#   （判据用真实 httpx 各构造一次客户端来验契约，全程不发请求，仍不触网）。
# ④ 机检类锁（不依赖执行）：MID-N32 的 url= 脱敏扫描、SEV-N05 的 proxy 归一 AST 扫描。
# ⑤ WP-J 同步探针内网收口的**接线形态**锁：
# - 两处自建探针客户端一律出自 _probe_client 工厂、且都带上恰一支 response 逐跳复检钩子
#   （行为侧由 _ProxyContractClient 记录实参形状，结构侧由 AST 锁兜住「后来者只接一处」）；
# - SEV-N05 的 proxy 归一判据随构造点收敛平移到「_probe_client 调用点的 proxy_addr 实参」，
#   语义不变（值必须在同一作用域内、使用之前由 utils.handle_proxy_addr 得到）；
# - 内网判定必须早于探针发出点、async_http 只能函数内 import（本仓存在 stream_select↔main 导入环）、
#   内部控制流异常必须在每个「发探针 + except Exception」的 try 里排在宽 except 之前。
# 判定链本身的正反用例（内网初始 URL / 公网→内网跳转 / 公网→公网反向锁 / 代理豁免 / 末位不放行）
# 在 tests/test_sync_probe_internal_guard.py，不在本文件重复。

from __future__ import annotations

import ast
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, Iterator, Literal, TypeGuard, cast
from unittest.mock import patch

import httpx
import pytest
from loguru import logger

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
import src.async_http as async_http
import src.stream_select as ss
from src import web_config
from src.async_http import get_response_status
from src.stream_select import (
    _hls_selection_config,
    _is_recordable_url,
    _mark_probe_reject,
    _pick_master_variant,
    _probe_backoff,
    _probe_backoff_key,
    _probe_backoff_lock,
    _probe_in_backoff,
    _recheck_delay,
    _same_origin_flv,
    _throttle_probe,
    _validate_stream_url,
    get_record_headers,
    select_source_url,
)


@pytest.fixture(autouse=True)
def no_probe_throttle(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # 探针节流是模块级全局状态（按 host 记录上次探针时刻）：单测多次调用同 host 探针
    # 会触发真实 sleep 拖慢测试；且部分用例 patch 整个 time 模块（time.time 为
    # MagicMock），节流的时间差比较会炸——统一将 _validate_stream_url 内的节流
    # 置为 no-op（节流专项测试自行恢复真实实现），并清空全局记录隔离用例。
    monkeypatch.setattr(ss, "_throttle_probe", lambda _url: None)
    ss._probe_last_seen.clear()
    yield
    ss._probe_last_seen.clear()


# 与 tests/test_regression_wp_b_netguard.py / tests/test_regression_net.py
# 同一个公网解析结果（示例 IP，仅作 DNS seam 的返回值，不参与任何判定规则）。
_PUBLIC_DNS_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _stub_dns_public(monkeypatch: pytest.MonkeyPatch) -> None:
    # WP-J 之后，_validate_stream_url 的探针入口与交付 ffmpeg 前的落地复核
    # 都会调 web_config._host_internal_reason，而它对**非 IP 字面量**的主机名要走 DNS seam
    # _resolve_host_ips。本文件的用例地址是合成域名（x / a.cdn / dylive.rtmp.douyucdn.cn），真解析在
    # 无外网/无 DNS 的环境里抛 OSError → 「主机名无法解析」→ 候选被判不可达，于是用例把「本机有没有
    # DNS」当成了被测行为（无网 CI 上整片转红，且跨文件顺序相关）。
    # 打桩口径沿用 async_http._internal_stream_target_reason 注释里写明的唯一 seam
    # （monkeypatch src.web_config._resolve_host_ips），与上述两个既有文件同一处、同一个取值。
    # 内网/保留目标类断言一律写成 IP 字面量——判定不依赖解析，也就不受本桩影响
    # （专项用例见 tests/test_sync_probe_internal_guard.py）。
    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_DNS_IP])


_FLV_URL = "https://hw3.douyucdn2.cn/live/12828016rSWtjVdN.flv?wsAuth=abc&token=web-h5"


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str, text: str = "") -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type} if content_type else {}
        # HLS 分片层探测需要读取播放列表正文（_probe_hls_segment 解析分片行）；
        # 缺省空串使未显式给出正文的旧用例落回「解析不出分片→保守放行」语义。
        self.text = text
        # L-11：探针读取正文改走 _bounded_probe_get 的
        # 流式形态（带字节上限），本桩因此要能当「流式响应」用（上下文协议 + iter_bytes）。
        # 刻意把正文**整段一次**交出、不在本桩里重实现「读满上限即断」的上界行为——
        # 那条不变量由下方两条 _ChunkCountingStream / 真实 httpx + MockTransport 用例钉
        # （测试不得自实现被测逻辑）。
        self.encoding = "utf-8"

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False

    def iter_bytes(self, _chunk_size: int | None = None) -> Iterator[bytes]:
        yield (self.text or "").encode("utf-8")


class _StreamAsGet:
    # L-11：生产侧四处探针读取统一走 client.stream(...)（见 src/stream_select.py 的
    # _bounded_probe_get）。假客户端用本 mixin 把**既有 get 的语义**原样暴露成流式形态——
    # 同一份状态码/头/正文、同一个调用计数器与同一份请求头记录，因此旧用例里
    # 「GET 调了几次 / 带了什么头」的断言逐字不变（改的只是调用入口的形态，不是判定）。
    def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
        raise NotImplementedError  # 由混入方实现

    def stream(
        self, method: str, url: str, headers: dict | None = None, follow_redirects: bool = True
    ) -> _FakeResponse:
        assert method == "GET", method
        return self.get(url, headers=headers, follow_redirects=follow_redirects)


class _M3u8ProbeClient:
    # 仅用于在类型层暴露 get_calls（运行时由嵌套子类重置为 0），
    # 使 _m3u8_client_cls 的返回类型可被 mypy 解析、调用方 cls.get_calls 合法。
    get_calls: int = 0


class _FakeHead405HtmlClient:
    # 模拟斗鱼 hw CDN：HEAD 一律 405（禁用 HEAD 方法）+ 错误页 content-type
    head_status = 405
    head_content_type = "text/html"

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> "_FakeHead405HtmlClient":
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False

    # _validate_stream_url 的 finally 会对自建客户端调用 close()：假客户端必须提供，
    # 否则每个用例都触发一次被吞掉的 AttributeError 调试日志（噪音，非断言失败）。
    def close(self) -> None:
        pass

    # 形参签名须与 httpx.Client.head 兼容（生产代码逐请求传 UA / Referer / Cookie），桩刻意忽略它——
    # 「客户端复用后业务头必须逐请求下发」由
    # test_select_source_url_shares_one_client_and_sends_headers_per_request 真断言，不在本桩里。
    def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
        return _FakeResponse(self.head_status, self.head_content_type)


class _FakeHead405NoTypeClient(_FakeHead405HtmlClient):
    # HEAD 405 且无 content-type：走尾部"非 200 且无法识别"分支
    head_content_type = ""


def test_huya_record_headers_has_no_referer() -> None:
    # 虎牙 CDN 现已反向校验：携带 Referer(https://www.huya.com/) 的请求一律 403，
    # 不携带 Referer 时 HS 线路 GET 200 正常拉流。故 get_record_headers 对虎牙不得下发
    # Referer（无论是否配置 cookie），否则校验/ffmpeg 两端均被 CDN 拒。
    headers = get_record_headers("虎牙直播", "http://hs.hls.huya.com/src/x.m3u8")
    assert headers is None or "referer" not in (headers or {})
    # 对照组：B站仍必须带 Referer——若实现被改成「全局去掉 Referer」，只有这一条会红。
    bili = get_record_headers("B站直播", "http://bili.hls/x.m3u8")
    assert bili is not None and bili.get("referer", "").startswith("https://live.bilibili.com")


def test_last_resort_text_html_released() -> None:
    # 末位候选：405+text/html 稳定拒绝也放行给 ffmpeg（探针与 ffmpeg 客户端指纹不同）
    with patch("src.stream_select.httpx.Client", _FakeHead405HtmlClient):
        assert _validate_stream_url(_FLV_URL, last_resort=True) is True


def test_non_last_resort_text_html_rejected() -> None:
    # 非末位候选：判不可达，交由上层回退下一候选（FLV→record_url）
    with patch("src.stream_select.httpx.Client", _FakeHead405HtmlClient):
        assert _validate_stream_url(_FLV_URL, last_resort=False) is False


def test_last_resort_odd_status_released() -> None:
    # 末位候选：非 200 且无法识别 content-type（空）同样仅告警放行
    with patch("src.stream_select.httpx.Client", _FakeHead405NoTypeClient):
        assert _validate_stream_url(_FLV_URL, last_resort=True) is True


def test_non_last_resort_odd_status_rejected() -> None:
    with patch("src.stream_select.httpx.Client", _FakeHead405NoTypeClient):
        assert _validate_stream_url(_FLV_URL, last_resort=False) is False


# ---- m3u8 Range-GET 探针重试（斗鱼 hw CDN 毫秒连击探针偶发 403 误杀） ----


def _m3u8_client_cls(get_statuses: list[int], get_types: list[str]) -> type[_M3u8ProbeClient]:
    # 构造 HEAD=405+text/html、Range-GET 按序返回预设状态码的假客户端；
    # get_calls 为类级计数器，供断言重试次数
    class _C(_M3u8ProbeClient, _StreamAsGet):
        get_calls = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_C":
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

        # 见 _FakeHead405HtmlClient.close 说明：避免 finally 关闭自建客户端时的噪音日志。
        def close(self) -> None:
            pass

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            return _FakeResponse(405, "text/html")

        def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
            i = min(_C.get_calls, len(get_statuses) - 1)
            resp = _FakeResponse(get_statuses[i], get_types[i])
            _C.get_calls += 1
            return resp

    return _C


_M3U8_URL = "https://hw3.douyucdn2.cn/live/12828016rSWtjVdN.m3u8?wsAuth=abc&token=web-h5"


def test_m3u8_range_get_retry_passes() -> None:
    # 首次 Range-GET 403（连击探针被 CDN 防护偶发拒绝），隔 0.8s 重试即 206：判可用
    cls = _m3u8_client_cls([403, 206], ["text/html", "application/vnd.apple.mpegurl"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL) is True
    # 3 次 GET = 2 次 Range-GET（403→206 重试）+ 1 次 HLS 分片层探测的播放列表 GET
    # （斗鱼 hw 事故修复：列表 200/206 后必须再探分片，见 _probe_hls_segment）。
    # 本用例假客户端未给播放列表正文（_FakeResponse.text 为空），分片探测解析不出分片即保守放行。
    assert cls.get_calls == 3


def test_m3u8_range_get_still_403_rejected() -> None:
    # 两次 Range-GET 均 403（稳定拒绝）且非末位：判不可达，回退 FLV
    cls = _m3u8_client_cls([403, 403], ["text/html", "text/html"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL, last_resort=False) is False
    assert cls.get_calls == 2


def test_m3u8_range_get_404_no_retry() -> None:
    # 404 非探针误杀类拒绝：不重试，单次探测即定罪
    cls = _m3u8_client_cls([404, 200], ["text/html", "text/html"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL) is False
    assert cls.get_calls == 1


def test_m3u8_last_resort_released() -> None:
    # 两次 Range-GET 均 403 且为末位候选：仅告警放行给 ffmpeg
    cls = _m3u8_client_cls([403, 403], ["text/html", "text/html"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL, last_resort=True) is True


# ---- HLS 分片层探测（斗鱼 hw CDN 事故回归） ----
# 事故：m3u8 列表层恒 200（CDN 动态合成，列表层无风控），但边缘 slice 节点上所有 .ts
# 分片 404 —— 旧校验「列表 200 即可达」假绿放行 m3u8，ffmpeg 逐分片 404、零视频产出，
# 而斗鱼弹幕走独立 WebSocket（只需 room_id）照常落 SRT，生产表现即「只出弹幕、无视频」。
# 修复目标：分片层探到 404 时必须否掉 m3u8、回退同 token 的可用 FLV。

_HLS_MASTER_BODY = (
    "#EXTM3U\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=2000000,RESOLUTION=1280x720\n"
    "https://f19c.livehwc4.com/hw3a.douyucdn2.cn/live/x.m3u8?sub_m3u8=true\n"
)
_HLS_MEDIA_BODY = (
    "#EXTM3U\n"
    "#EXT-X-VERSION:3\n"
    "#EXTINF:4.000,\n"
    "x_dy_0.ts?vhost=a&edge_slice=true\n"
    "#EXTINF:4.000,\n"
    "x_dy_5.ts?vhost=a&edge_slice=true\n"
)


class _FakeStream:
    # 仅实现 _confirm_get_ok 读取的 status_code（流式 GET 复核）
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def __enter__(self) -> "_FakeStream":
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False


def _hls_segment_client_cls(segment_status: int, media_body: str = _HLS_MEDIA_BODY) -> type:
    # 假客户端：HEAD 恒 200+mpegurl（进 m3u8 分片探测分支），播放列表按 URL 返回
    # master/媒体正文，媒体分片返回预设状态码（404=事故形态 / 200=健康）。
    class _C(_StreamAsGet):
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_C":
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

        def close(self) -> None:
            pass

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            return _FakeResponse(200, "application/vnd.apple.mpegurl")

        def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
            if url == _M3U8_URL:
                return _FakeResponse(200, "application/vnd.apple.mpegurl", text=_HLS_MASTER_BODY)
            if "sub_m3u8" in url:
                return _FakeResponse(200, "application/vnd.apple.mpegurl", text=media_body)
            return _FakeResponse(segment_status, "video/mp2t")

    return _C


def test_hls_segment_404_rejects_playlist() -> None:
    # 事故形态：列表 200 + 分片 404 → 判列表假绿不可达（非末位候选交由上层回退 FLV）
    cls = _hls_segment_client_cls(404)
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=False) is False


def test_hls_segment_200_stays_reachable() -> None:
    # 对照：分片真可达（200）→ 维持列表可达结论
    cls = _hls_segment_client_cls(200)
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=False) is True


def test_hls_segment_404_last_resort_released() -> None:
    # 末位候选（无备选可回退）：分片 404 也仅告警放行给 ffmpeg（探针≠ffmpeg 客户端指纹）
    cls = _hls_segment_client_cls(404)
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=True) is True


def test_hls_empty_media_playlist_conservative_pass() -> None:
    # 保守原则：媒体列表为空（未推流/直播刚结束）解析不出分片 → 维持列表可达，不误杀可用源
    cls = _hls_segment_client_cls(404, media_body="#EXTM3U\n#EXT-X-VERSION:3\n")
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=False) is True


# ---- S-04：正文派生地址的安全拒绝不得被末位放行/同址复用翻回 ----
# 事故形态：被劫持或被 MITM 的播放列表正文写 `http://127.0.0.1:6379/x.ts`（或云元数据地址），
# 旧实现把安全闸拒绝编码成 `return False`，与「分片 404 不可达」不可区分，于是被两处兜底翻回 True：
#   ① `_validate_stream_url` 的 last_resort 分支（末位候选「仍交由 ffmpeg 尝试」）；
#   ② `select_source_url` 的 record_url 同址复用分支（只要探过就交付，不看结论）。
# 修法是把安全拒绝改成内部控制流异常 + 单独的 security_rejected 集合，两条用例各锁一条。
_INTERNAL_SEGMENT_BODY = "#EXTM3U\n" "#EXT-X-VERSION:3\n" "#EXTINF:4.000,\n" "http://127.0.0.1:6379/x.ts\n"


def test_internal_segment_rejects_even_at_last_resort() -> None:
    # ① 末位候选（last_resort=True）不得把「正文分片指向内网」翻回可达
    cls = _hls_segment_client_cls(200, media_body=_INTERNAL_SEGMENT_BODY)
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=True) is False


def test_select_source_url_rejects_record_url_same_as_internal_m3u8() -> None:
    # ② record_url 与 m3u8_url 同址（抖音 / TikTok / 网易CC 的常态形态）且正文分片指向内网：
    # 同址复用分支必须拒绝交付，整轮判定为无可用源。
    cls = _hls_segment_client_cls(200, media_body=_INTERNAL_SEGMENT_BODY)
    stream_info = {"m3u8_url": _M3U8_URL, "flv_url": "", "record_url": _M3U8_URL}
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", cls),
    ):
        assert select_source_url(stream_info, platform="斗鱼直播") is None


class _HlsDeadFlvLiveClient(_StreamAsGet):
    # 端到端选源假客户端：m3u8 分片 404（事故形态），FLV 的 HEAD/GET 均 200（可用）
    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    def __enter__(self) -> _HlsDeadFlvLiveClient:
        return self

    def __exit__(self, *_args: object) -> Literal[False]:
        return False

    def close(self) -> None:
        pass

    def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
        if ".m3u8" in url.lower():
            return _FakeResponse(200, "application/vnd.apple.mpegurl")
        return _FakeResponse(200, "video/x-flv")

    def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
        if url == _M3U8_URL:
            return _FakeResponse(200, "application/vnd.apple.mpegurl", text=_HLS_MASTER_BODY)
        if "sub_m3u8" in url:
            return _FakeResponse(200, "application/vnd.apple.mpegurl", text=_HLS_MEDIA_BODY)
        # L-11 之后 _confirm_get_ok（FLV GET 复核）与 m3u8 Range-GET 都经 stream()→本方法：
        # FLV 必须与类注释一致地回 200（可用），否则「HLS 死、FLV 活」这条端到端锁会被
        # 假客户端自己的形态打弯。分片（.ts）保持 404 = 事故形态。
        if ".flv" in url.lower():
            return _FakeResponse(200, "video/x-flv")
        return _FakeResponse(404, "video/mp2t")


def test_select_source_url_falls_back_to_flv_when_hls_segments_dead() -> None:
    # 端到端：斗鱼 m3u8 分片全 404 → select_source_url 否掉 m3u8、回退同 token 的可用 FLV。
    # 这正是「只出弹幕 SRT、无视频」的修复目标：最终拿到能真正拉流的地址。
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", _HlsDeadFlvLiveClient),
    ):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": _FLV_URL, "record_url": _FLV_URL}, platform=None)
    assert result == _FLV_URL


# ---- 同源候选（HLS 由 FLV 按扩展名替换而来，共享 token） ----


def test_same_origin_flv_matches_extension_swapped_candidate() -> None:
    # 斗鱼形态：FLV 直链按 .flv→.m3u8 替换后下发，二者共享 wsAuth → 视为同源候选
    assert _same_origin_flv(_M3U8_URL, [_FLV_URL]) == _FLV_URL


def test_same_origin_flv_none_when_no_counterpart() -> None:
    other = "https://hw3.douyucdn2.cn/live/other.flv?wsAuth=abc&token=web-h5"
    assert _same_origin_flv(_M3U8_URL, [other]) is None
    # 非 m3u8 入参不参与同源判定
    assert _same_origin_flv(_FLV_URL, [_FLV_URL]) is None


def test_same_origin_flv_ignores_query_difference() -> None:
    # 同源判定只比对「?」之前的路径：token 等查询参数差异不影响同源识别
    stale = "https://hw3.douyucdn2.cn/live/12828016rSWtjVdN.flv?wsAuth=old&token=old"
    assert _same_origin_flv(_M3U8_URL, [stale]) == stale


def test_select_source_url_logs_same_origin_flv_fallback() -> None:
    # 端到端观测：HLS 分片假绿 → 记一条「回退同 token 的 FLV 源」，便于巡检确认已按预期回退
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", _HlsDeadFlvLiveClient),
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": _FLV_URL, "record_url": _FLV_URL}, platform=None)
    assert result == _FLV_URL
    assert any("同 token 的 FLV" in str(call.args[0]) for call in warn.call_args_list)


# ---- 选源结论观测（观测增强） ----


def test_select_source_url_logs_choice_on_pick() -> None:
    # 选定源时记「选源结论」单行日志（platform/kind/url），一眼确认 ffmpeg 拉的是 HLS 还是 FLV
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", _HlsDeadFlvLiveClient),
        patch("src.stream_select.logger.debug") as dbg,
    ):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": _FLV_URL, "record_url": _FLV_URL}, platform=None)
    assert result == _FLV_URL
    assert any("选源结论" in str(call.args[0]) for call in dbg.call_args_list)


def test_select_source_url_logs_no_usable_source() -> None:
    # 全部候选不可达且无 record_url 兜底 → 补一条可检索的收束结论
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", return_value=False),
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url({"m3u8_url": "https://x/a.m3u8", "flv_url": "", "record_url": ""})
    assert result is None
    assert any("本轮无可用源" in str(call.args[0]) for call in warn.call_args_list)


# ---- HLS 采集配置兜底（缺失 / 类型异常时回退安全默认） ----


def test_hls_selection_config_defaults_on_missing_globals(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(main, "hls_collection_enabled", raising=False)
    monkeypatch.delattr(main, "hls_collection_exclude_platforms", raising=False)
    assert _hls_selection_config() == (True, ())


def test_hls_selection_config_normalizes_comma_string(monkeypatch: pytest.MonkeyPatch) -> None:
    # 兼容「逗号分隔字符串」形态（中英文逗号 + 空白），与 main() 的解析同语义
    monkeypatch.setattr(main, "hls_collection_enabled", False)
    monkeypatch.setattr(main, "hls_collection_exclude_platforms", "虎牙直播， 斗鱼 ,")
    assert _hls_selection_config() == (False, ("虎牙直播", "斗鱼"))


def test_hls_selection_config_ignores_invalid_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main, "hls_collection_enabled", True)
    monkeypatch.setattr(main, "hls_collection_exclude_platforms", 12345)
    assert _hls_selection_config() == (True, ())


def test_select_source_url_survives_missing_hls_config(monkeypatch: pytest.MonkeyPatch) -> None:
    # 配置全局缺失时不再抛 AttributeError 中断选源，按安全默认（启用 HLS）正常完成选源
    monkeypatch.delattr(main, "hls_collection_enabled", raising=False)
    monkeypatch.delattr(main, "hls_collection_exclude_platforms", raising=False)
    with patch("src.stream_select.httpx.Client", _HlsDeadFlvLiveClient):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": _FLV_URL, "record_url": _FLV_URL}, platform=None)
    assert result == _FLV_URL


# ---- select_source_url 的 HLS 末位判定 ----


def test_select_source_url_hls_only_is_last_resort() -> None:
    # HLS 为唯一候选（无 FLV/record_url）：校验须以 last_resort=True 进行
    # （稳定拒绝时由真实校验器内部告警放行，见 test_m3u8_last_resort_released；
    # 此处 mock 恒 False 仅验证末位传参，故 select_source_url 走回退链后返回 None）
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", return_value=False) as mock_v,
    ):
        result = select_source_url({"m3u8_url": "https://x/a.m3u8", "flv_url": "", "record_url": ""})
    assert result is None
    assert mock_v.call_args.kwargs.get("last_resort") is True


def test_select_source_url_hls_with_fallback_not_last_resort() -> None:
    # 存在 FLV 备选：HLS 非末位，校验失败正常回退 FLV
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", return_value=True) as mock_v,
    ):
        result = select_source_url({"m3u8_url": "https://x/a.m3u8", "flv_url": "https://x/a.flv"})
    assert result == "https://x/a.m3u8"
    assert mock_v.call_args.kwargs.get("last_resort") is False


def test_select_source_url_h265_flv_hls_is_last_resort() -> None:
    # FLV 为 h265 不可用时，HLS 即最后机会：恒为 last_resort。
    # 保存格式钉为 FLV（不支持 HEVC 直拷）——TS/MKV/MP4 下 h265 已放宽进常规
    # 序列（见下方放宽矩阵），本用例锁的是「不支持格式下 h265 仍被剔除」的语义
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "video_save_type", "FLV"),
        patch("src.stream_select._validate_stream_url", return_value=False) as mock_v,
    ):
        result = select_source_url(
            {"m3u8_url": "https://x/a.m3u8", "flv_url": "https://x/a.flv?codec=h265", "record_url": ""}
        )
    assert result is None  # mock 恒 False：h265 分支放弃；真实校验器在末位会放行（见上方用例）
    assert mock_v.call_args.kwargs.get("last_resort") is True


def test_select_source_url_h265_flv_falls_back_to_h264_from_list() -> None:
    # 抖音原画 hevc 房死锁回归锁（端到端选源）：flv_url 为 h265、保存格式不支持
    # HEVC 直拷（钉 FLV）时被 h265 过滤剔除，stream.py 保留的 h264 原画地址进 flv_url_list。
    # HLS 关闭时 HLS 组与 record_url（m3u8）一并禁用，序列 [h265, h264] 过滤后应选中
    # h264 备选，而不是「本轮无可用源」。
    h264 = "https://flv.example.com/a.flv"
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch.object(main, "video_save_type", "FLV"),
        patch("src.stream_select._validate_stream_url", return_value=True) as mock_v,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": "https://flv.example.com/a.flv?codec=h265",
                "flv_url_list": [h264],
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result == h264
    # h265 主候选在过滤阶段即被剔除、不得进入校验；备选是唯一被校验的地址
    assert [c.args[0] for c in mock_v.call_args_list] == [h264]


def test_select_source_url_h265_only_without_fallback_yields_none() -> None:
    # 对照组（修复前形态）：flv_url 为 h265 且无 flv_url_list 备选、HLS 关闭、保存格式不支持
    # HEVC 直拷（钉 FLV）时，过滤后零可用候选且 record_url（m3u8）被连带禁用 → 本轮无可用源。
    # 锁住「不支持格式 + 无备选时不得凭空放行 h265」的语义（TS/MKV/MP4 放行见下方放宽矩阵）。
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch.object(main, "video_save_type", "FLV"),
        patch("src.stream_select._validate_stream_url", return_value=True) as mock_v,
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": "https://flv.example.com/a.flv?codec=h265",
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result is None
    assert mock_v.call_count == 0
    assert any("h265 编码候选" in str(c.args[0]) for c in warn.call_args_list)
    assert any("本轮无可用源" in str(c.args[0]) for c in warn.call_args_list)


# ---- h265 候选按保存格式放行（放宽：_h265_copy_format_supported） ----


@pytest.mark.parametrize("fmt", ["TS", "ts", "MKV", "MP4"])
def test_select_source_url_h265_usable_when_copy_supported(fmt: str) -> None:
    # TS/MKV/MP4 容器可直拷 HEVC：h265 主候选进常规序列并按序选中，不再先剔除。
    # 大小写混合入参覆盖 main() 配置归一化前后两种形态（归一后大写、模块默认值小写）
    h265 = "https://flv.example.com/a.flv?codec=h265"
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch.object(main, "video_save_type", fmt),
        patch("src.stream_select._validate_stream_url", return_value=True) as mock_v,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": h265,
                "flv_url_list": ["https://flv.example.com/a.flv"],
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result == h265
    # h265 主候选首个被校验并选中；h264 备选不再被消耗
    assert [c.args[0] for c in mock_v.call_args_list] == [h265]


@pytest.mark.parametrize("fmt", ["FLV", "MP3", "M4A音频", "webm", ""])
def test_select_source_url_h265_still_dropped_when_copy_unsupported(fmt: str) -> None:
    # 不支持直拷的保存格式（FLV 容器 / 纯音频 / 域外取值）保持剔除语义，
    # 落到 stream.py 保留的 h264 原画备选——与上方支持格式的矩阵互为对照
    h264 = "https://flv.example.com/a.flv"
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch.object(main, "video_save_type", fmt),
        patch("src.stream_select._validate_stream_url", return_value=True) as mock_v,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": "https://flv.example.com/a.flv?codec=h265",
                "flv_url_list": [h264],
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result == h264
    # h265 在过滤阶段被剔除、零探针；备选是唯一被校验的地址
    assert [c.args[0] for c in mock_v.call_args_list] == [h264]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TS", True),
        ("ts", True),
        (" MKV ", True),
        ("MP4", True),
        ("FLV", False),
        ("MP3", False),
        ("MP3音频", False),
        ("M4A音频", False),
        ("", False),
        (None, False),
        (123, False),
    ],
)
def test_h265_copy_format_supported_matrix(monkeypatch: pytest.MonkeyPatch, raw: object, expected: bool) -> None:
    # 容器可行性判定矩阵：大小写/空白鲁棒（覆盖 main() 归一化前后形态），
    # 域外取值与类型异常一律按「不支持」的保守语义
    monkeypatch.setattr(main, "video_save_type", raw)
    assert ss._h265_copy_format_supported() is expected


def test_h265_copy_format_supported_missing_global(monkeypatch: pytest.MonkeyPatch) -> None:
    # main 全局缺失（启动早期/测试替身）：按「不支持」保守回退，与 _hls_selection_config 同型
    monkeypatch.delattr(main, "video_save_type", raising=False)
    assert ss._h265_copy_format_supported() is False


# ---- HLS 配置静默丢弃的观测 ----


def test_select_source_url_warns_dropped_hls_when_no_source() -> None:
    # HLS 组被配置静默剔除 + 其余候选全灭 → 无源结论前必须点名「m3u8 被配置丢弃」并给
    # 恢复开关指引——这是此前唯一零日志的选源成因（死锁房的排查盲区）
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch("src.stream_select._validate_stream_url", return_value=False),
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": "https://flv.example.com/a.flv",
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result is None
    dropped = [str(c.args[0]) for c in warn.call_args_list if "静默丢弃" in str(c.args[0])]
    assert len(dropped) == 1
    assert "1 条" in dropped[0] and "是否启用HLS采集" in dropped[0]


def test_no_dropped_hls_warning_when_source_found() -> None:
    # HLS 被配置丢弃但 FLV 可用（健康轮）：不得打「静默丢弃」告警——观测只跟随失败轮
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch("src.stream_select._validate_stream_url", return_value=True),
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hls.example.com/a.m3u8?codec=h264",
                "flv_url": "https://flv.example.com/a.flv",
                "record_url": "https://hls.example.com/a.m3u8?codec=h264",
            },
            platform="抖音直播",
        )
    assert result == "https://flv.example.com/a.flv"
    assert not [c.args[0] for c in warn.call_args_list if "静默丢弃" in str(c.args[0])]


def test_select_source_url_m3u8_list_picks_first_reachable() -> None:
    # 虎牙多 CDN 候选：index0 的 AL/TX 离线（校验 False），HS 候选可达（校验 True）。
    # select_source_url 应跳过离线候选、选中首个可达的 HLS（HS），而非固定取 m3u8_url 主源。
    dead = "http://al.hls.huya.com/src/s.m3u8?wsSecret=dead"
    hs = "http://hs.hls.huya.com/src/s.m3u8?wsSecret=live"

    def _validate(url: str, **kwargs: object) -> bool:
        return url == hs

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate) as mock_v,
    ):
        result = select_source_url({"m3u8_url": dead, "m3u8_url_list": [dead, hs], "flv_url": "", "record_url": ""})
    assert result == hs
    # 离线候选先被校验（False），随后 HS 候选被校验（True）并选中
    assert mock_v.call_count == 2


def test_select_source_url_m3u8_list_all_dead_falls_back_to_flv() -> None:
    # 全部 HLS 候选离线时，应回退 FLV 候选（而非卡在死 HLS 上整轮放弃）。
    dead_hls = ["http://al.hls.huya.com/src/s.m3u8?wsSecret=1", "http://tx.hls.huya.com/src/s.m3u8?wsSecret=2"]
    flv = "http://hs.flv.huya.com/src/s.flv?wsSecret=live"

    def _validate(url: str, **kwargs: object) -> bool:
        return url == flv

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate) as mock_v,
    ):
        result = select_source_url(
            {"m3u8_url": dead_hls[0], "m3u8_url_list": dead_hls, "flv_url": flv, "record_url": ""}
        )
    assert result == flv
    # 两条 HLS 候选均被校验（均 False）后回退 FLV
    assert mock_v.call_count == 3


def test_select_source_url_shares_one_client_and_sends_headers_per_request() -> None:
    # 一次选源内多个候选的探针必须共用同一支 httpx.Client：原实现每个候选各建一支，
    # 虎牙 4 条 CDN 线路即 4 次 SSLContext / 连接池重建（实测构造约 6.7ms/次）；
    # 单候选约 0.77ms vs 新建 Client + 单次探针约 15.9ms。
    # 配套前提：客户端复用后 UA / Referer / Cookie 不能再挂 client 级（否则各候选互相污染），
    # 必须逐请求下发——本例同时断言每个请求都带齐录制所需的三个头。
    class _CountingClient(_StreamAsGet):
        instantiated = 0
        close_calls = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            _CountingClient.instantiated += 1
            # 客户端级不得再带业务头：录制头一律走请求级
            assert "headers" not in kwargs, "客户端复用后业务头只能逐请求传入"

        def close(self) -> None:
            _CountingClient.close_calls += 1

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            seen_headers.append(dict(headers or {}))
            return _FakeResponse(404, "text/html")

        def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
            seen_headers.append(dict(headers or {}))
            return _FakeResponse(404, "text/html")

    seen_headers: list[dict[str, str]] = []
    hls_a = "https://a.cdn/live/1.m3u8"
    hls_b = "https://a.cdn/live/2.m3u8"
    flv = "https://a.cdn/live/1.flv"
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", _CountingClient),
    ):
        result = select_source_url(
            {"m3u8_url": hls_a, "m3u8_url_list": [hls_a, hls_b], "flv_url": flv, "record_url": ""},
            platform="B站直播",
            cookies="buvid3=abc",
        )
    # 末位 FLV 稳定拒绝仍放行给 ffmpeg（既有 last_resort 语义，非本次改动）
    assert result == flv
    # 5 次探针（2 条 HLS 各 HEAD+Range-GET，1 条 FLV 仅 HEAD）只构造了 1 支客户端
    assert len(seen_headers) == 5
    assert _CountingClient.instantiated == 1
    # 选源结束必须关闭，避免常驻连接占用 CDN 连接预算（与 ffmpeg 争抢）
    assert _CountingClient.close_calls == 1
    # 每个请求都带齐录制头：客户端复用不得丢失 UA / Referer / Cookie
    assert seen_headers, "探针必须携带请求头"
    for h in seen_headers:
        assert h.get("referer", "").startswith("https://live.bilibili.com")
        assert h.get("cookie") == "buvid3=abc"
        assert h.get("User-Agent")


# ---- 虎牙探针退避：CDN 限流（连续 403）时跳过探针，ffmpeg 独享连接预算 ----
#
# 虎牙 aldirect CDN 对同一路径短时间连续连接限流：每轮「HLS 3 连探针 + FLV 2~3 连探针 +
# ffmpeg」烧光预算，表现为校验 200 后 ffmpeg 立即 403（实测日志）。退避窗口内不发探针：
# 非末位候选回退下一候选，末位候选直接放行给 ffmpeg。

_HUYA_M3U8_URL = (
    "http://aldirect.hls.huya.com/huyalive/288806-288806-5332-456-10057-A-0-1.m3u8?wsSecret=abc&wsTime=6a8455d0"
)
_HUYA_FLV_URL = (
    "http://aldirect.flv.huya.com/huyalive/288806-288806-5332-456-10057-A-0-1.flv?wsSecret=abc&wsTime=6a8455d0"
)


@pytest.fixture()
def clear_probe_backoff() -> Iterator[None]:
    # 退避表是模块级状态：用例前后清空，避免跨用例污染
    with _probe_backoff_lock:
        _probe_backoff.clear()
    yield
    with _probe_backoff_lock:
        _probe_backoff.clear()


def test_huya_stable_403_marks_backoff_then_skips_probe(clear_probe_backoff: None) -> None:
    # 第 1 轮：HLS 探针全 403（稳定拒绝）→ 判不可达并记入退避
    cls = _m3u8_client_cls([403, 403], ["text/html", "text/html"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time.sleep"):
        assert _validate_stream_url(_HUYA_M3U8_URL, platform="虎牙直播", last_resort=False) is False
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True

    # 第 2 轮（退避窗口内）：零探针直接判失败回退（fake 客户端不应被实例化）
    class _NoProbeClient:
        instantiated = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            _NoProbeClient.instantiated += 1

    with patch("src.stream_select.httpx.Client", _NoProbeClient):
        assert _validate_stream_url(_HUYA_M3U8_URL, platform="虎牙直播", last_resort=False) is False
    assert _NoProbeClient.instantiated == 0


def test_huya_backoff_last_resort_released_without_probe(clear_probe_backoff: None) -> None:
    # 退避中的末位候选（无备选）：直接放行给 ffmpeg，不发探针（省下连接预算）
    _mark_probe_reject(_HUYA_FLV_URL, "虎牙直播")

    class _NoProbeClient:
        instantiated = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            _NoProbeClient.instantiated += 1

    with patch("src.stream_select.httpx.Client", _NoProbeClient):
        assert _validate_stream_url(_HUYA_FLV_URL, platform="虎牙直播", last_resort=True) is True
    assert _NoProbeClient.instantiated == 0


def test_huya_transient_flv_403_marks_backoff(clear_probe_backoff: None) -> None:
    # FLV「HEAD 200 + GET 复核先 403 后 200」：校验通过（重试救回），但偶发 403 仍是
    # 限流证据 → 记入退避，下一轮让 ffmpeg 直连（实测该形态下 ffmpeg 立即 403）
    class _FlvTransient403Client:
        get_codes = [403, 200]

        def __init__(self, *args: object, **kwargs: object) -> None:
            self._calls = 0

        def __enter__(self) -> "_FlvTransient403Client":
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            return _FakeResponse(200, "video/x-flv")

        def stream(
            self, method: str, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True
        ) -> "_StreamCtx":
            code = self.get_codes[min(self._calls, len(self.get_codes) - 1)]
            self._calls += 1
            return _StreamCtx(_FakeResponse(code, ""))

    class _StreamCtx:
        def __init__(self, resp: _FakeResponse) -> None:
            self._resp = resp

        def __enter__(self) -> _FakeResponse:
            return self._resp

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

    with patch("src.stream_select.httpx.Client", _FlvTransient403Client), patch("src.stream_select.time.sleep"):
        assert _validate_stream_url(_HUYA_FLV_URL, platform="虎牙直播", last_resort=True) is True
    assert _probe_in_backoff(_HUYA_FLV_URL, "虎牙直播") is True


def test_backoff_key_ignores_query_token(clear_probe_backoff: None) -> None:
    # 虎牙每轮解析返回新 token（query 变化）但路径稳定：退避键须按 host+路径聚合跨轮命中
    _mark_probe_reject(_HUYA_M3U8_URL, "虎牙直播")
    fresh_token_url = _HUYA_M3U8_URL.replace("wsSecret=abc", "wsSecret=newsecret")
    assert _probe_backoff_key(fresh_token_url) == _probe_backoff_key(_HUYA_M3U8_URL)
    assert _probe_in_backoff(fresh_token_url, "虎牙直播") is True


def test_mark_ffmpeg_reject_marks_backoff(clear_probe_backoff: None) -> None:
    # ffmpeg 录制失败侧的反馈入口（check_subprocess 快速失败时调用）：
    # 与探针侧 _mark_probe_reject 同语义——按 host+路径记入退避（跨轮新 token 命中），
    # 平台不在退避名单（斗鱼）时为无操作
    ss.mark_ffmpeg_reject(_HUYA_M3U8_URL, "虎牙直播")
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True
    fresh_token_url = _HUYA_M3U8_URL.replace("wsSecret=abc", "wsSecret=next-round")
    assert _probe_in_backoff(fresh_token_url, "虎牙直播") is True

    ss.mark_ffmpeg_reject(_FLV_URL, "斗鱼直播")
    assert _probe_in_backoff(_FLV_URL, "斗鱼直播") is False


def test_backoff_expires_after_window(clear_probe_backoff: None) -> None:
    # 超过退避窗口后恢复正常探针（限流解除/主播重新开播时走正常校验）。
    # 窗口已由固定 60s 改为动态值（≥ 主循环间隔），故按当前窗口计算过期时刻
    _mark_probe_reject(_HUYA_M3U8_URL, "虎牙直播")
    with _probe_backoff_lock:
        _probe_backoff[_probe_backoff_key(_HUYA_M3U8_URL)] = time.time() - (ss._probe_backoff_window() + 1.0)
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is False
    # 窗口内仍命中：刚记入的退避必须被下一轮观测到
    _mark_probe_reject(_HUYA_M3U8_URL, "虎牙直播")
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True


def test_backoff_window_covers_main_loop_interval(monkeypatch: pytest.MonkeyPatch, clear_probe_backoff: None) -> None:
    # 回归核心：退避窗口必须 ≥ 一个主循环周期，否则「ffmpeg 快速失败 → 下轮跳过该线路」
    # 的闭环恒不成立。原实现固定 60s，而 main.delay_default 默认 120s —— ffmpeg 1~2s 内
    # 403 被记入退避后，下一轮 T+124s 才到，早已超出窗口，于是又去撞同一条死线路
    # （实测虎牙 880214：两轮日志中「CDN 探针退避中」告警从未出现，房间假绿死循环）。
    monkeypatch.setattr(main, "delay_default", 120)
    window = ss._probe_backoff_window()
    assert window > 120.0 + 5.0  # 覆盖默认间隔 + 抖动
    # 模拟实测节奏：T 记入退避 → T+124s（间隔 120s + 抖动 4s）下一轮到达时仍须命中
    ss.mark_ffmpeg_reject(_HUYA_M3U8_URL, "虎牙直播")
    with _probe_backoff_lock:
        _probe_backoff[_probe_backoff_key(_HUYA_M3U8_URL)] = time.time() - 124.0
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True
    # 错误窗口满 5 次时 main.py 还会再 +60s（间隔 ~185s），最坏节奏同样须覆盖
    with _probe_backoff_lock:
        _probe_backoff[_probe_backoff_key(_HUYA_M3U8_URL)] = time.time() - 185.0
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True
    # 循环间隔被用户调小时窗口随之回落（不应按最大值锁死）
    monkeypatch.setattr(main, "delay_default", 30)
    assert ss._probe_backoff_window() == 30.0 + ss._PROBE_BACKOFF_INTERVAL_MARGIN
    assert ss._probe_backoff_window() < window


def test_clear_ffmpeg_reject_removes_backoff(clear_probe_backoff: None) -> None:
    # 录制成功侧的反馈入口（与 mark_ffmpeg_reject 对称）：地址实际拉流成功后撤销退避，
    # 避免窗口内明明已恢复的线路继续被跳过、白白回退到次优线路
    ss.mark_ffmpeg_reject(_HUYA_M3U8_URL, "虎牙直播")
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is True
    ss.clear_ffmpeg_reject(_HUYA_M3U8_URL, "虎牙直播")
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is False
    # 跨轮新 token（query 变化）同样命中，与写入侧同键
    ss.mark_ffmpeg_reject(_HUYA_M3U8_URL, "虎牙直播")
    ss.clear_ffmpeg_reject(_HUYA_M3U8_URL.replace("wsSecret=abc", "wsSecret=new"), "虎牙直播")
    assert _probe_in_backoff(_HUYA_M3U8_URL, "虎牙直播") is False
    # 平台不在退避名单（斗鱼）时为无操作，不误伤
    ss.clear_ffmpeg_reject(_FLV_URL, "斗鱼直播")
    assert _probe_in_backoff(_FLV_URL, "斗鱼直播") is False


def test_non_backoff_platform_keeps_retry_semantics(clear_probe_backoff: None) -> None:
    # 斗鱼不在退避名单：稳定 403 不记退避，下一轮仍正常探针（保住「重试一次再定罪」
    # 与 HLS-first 语义，不因负缓存跳过导致回退 FLV 的回归）
    cls = _m3u8_client_cls([403, 403], ["text/html", "text/html"])
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL, platform="斗鱼直播", last_resort=False) is False
    assert _probe_in_backoff(_M3U8_URL, "斗鱼直播") is False

    cls2 = _m3u8_client_cls([206, 206], ["application/vnd.apple.mpegurl"] * 2)
    with patch("src.stream_select.httpx.Client", cls2), patch("src.stream_select.time"):
        assert _validate_stream_url(_M3U8_URL, platform="斗鱼直播", last_resort=False) is True
    # 2 次 GET = 1 次 Range-GET（206 首次即通过）+ 1 次分片层探测的播放列表 GET
    # （斗鱼 hw 事故修复新增的一跳，见上方 test_m3u8_range_get_retry_passes）。
    assert cls2.get_calls == 2


def test_select_source_url_huya_backoff_round_straight_to_ffmpeg(clear_probe_backoff: None) -> None:
    # 复刻实测日志第 2 轮形态：HLS/FLV 均因 403 进入退避 → select_source_url
    # 零探针直接放行序列末位候选给 ffmpeg（独享连接预算，403 失败循环自愈）。
    # 虎牙为 FLV-first（FLV → HLS），序列末位是 HLS——两者均在退避中、都不可信时
    # 放行谁皆属「交由 ffmpeg 定夺」，核心不变式是零探针。
    _mark_probe_reject(_HUYA_M3U8_URL, "虎牙直播")
    _mark_probe_reject(_HUYA_FLV_URL, "虎牙直播")

    class _NoProbeClient:
        # 客户端对象会被构造一次（select_source_url 整轮共用一支），但不得发出任何探针：
        # 退避的意义是不消耗 CDN 连接预算，故断言的是「探针请求数 == 0」而非「构造数 == 0」
        probe_calls = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            _NoProbeClient.probe_calls += 1
            return _FakeResponse(200, "video/x-flv")

        def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
            _NoProbeClient.probe_calls += 1
            return _FakeResponse(200, "application/vnd.apple.mpegurl")

        def stream(self, method: str, url: str, **kwargs: object) -> object:
            _NoProbeClient.probe_calls += 1
            raise AssertionError("退避窗口内不应发出任何探针")

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select.httpx.Client", _NoProbeClient),
    ):
        result = select_source_url(
            {"m3u8_url": _HUYA_M3U8_URL, "flv_url": _HUYA_FLV_URL, "record_url": ""},
            platform="虎牙直播",
        )
    assert result == _HUYA_M3U8_URL
    assert _NoProbeClient.probe_calls == 0


def test_huya_flv_first_prefers_flv_on_cold_start(clear_probe_backoff: None) -> None:
    # 修复冷启动假绿：虎牙 HLS 三条 CDN 线路（hs/tx/al）冷启动探针假绿——探针 200/206
    # 而 ffmpeg 打开即 403（实测两房间复现，每次冷启动损失约 2 分钟），FLV 则每轮稳定可用
    # （最长连录 6 分钟）。FLV-first 下首个被校验的必须是 FLV，且 FLV 可达时不再触碰 HLS。
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return url == _HUYA_FLV_URL

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {"m3u8_url": _HUYA_M3U8_URL, "flv_url": _HUYA_FLV_URL, "record_url": ""},
            platform="虎牙直播",
        )
    assert result == _HUYA_FLV_URL
    assert probed == [_HUYA_FLV_URL]  # HLS 探针一次都不发


def test_huya_flv_failed_falls_back_to_hls(clear_probe_backoff: None) -> None:
    # FLV-first 不砍回退链：FLV 校验失败后仍按序尝试 HLS
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return url == _HUYA_M3U8_URL

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {"m3u8_url": _HUYA_M3U8_URL, "flv_url": _HUYA_FLV_URL, "record_url": ""},
            platform="虎牙直播",
        )
    assert result == _HUYA_M3U8_URL
    assert probed == [_HUYA_FLV_URL, _HUYA_M3U8_URL]


def test_douyu_keeps_hls_first(clear_probe_backoff: None) -> None:
    # 斗鱼绝不 FLV-first：游客态 FLV 长连接约 70 秒被 CDN 掐断，必须 HLS 优先
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return True

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hw3.douyucdn2.cn/live/x.m3u8?wsAuth=1",
                "flv_url": "https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1",
                "record_url": "",
            },
            platform="斗鱼直播",
        )
    assert result == "https://hw3.douyucdn2.cn/live/x.m3u8?wsAuth=1"
    assert probed == [result]  # 首个被校验的是 HLS（顺序断言）


# ---- HLS 采集排除列表：命中平台无视「是否启用HLS采集」配置、恒走 FLV ----


def test_excluded_platform_ignores_hls_and_uses_flv(clear_probe_backoff: None) -> None:
    # 核心语义：HLS 采集开（=是）+ 平台在排除列表 → 无视 HLS 配置，FLV 被选中，
    # 且 HLS 探针一次都不发（HLS 候选整组剔除，而非降序回退）
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return True

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hw3.douyucdn2.cn/live/x.m3u8?wsAuth=1",
                "flv_url": "https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1",
                "record_url": "",
            },
            platform="斗鱼直播",
        )
    assert result == "https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1"
    assert probed == [result]  # 仅 FLV 被校验（顺序+唯一性断言）


def test_excluded_platform_flv_failed_never_falls_back_to_hls(clear_probe_backoff: None) -> None:
    # 「始终走 FLV」的强化语义：排除平台 FLV 校验失败时不得回退 HLS（与 FLV-first
    # 平台仅调序、保留 HLS 回退不同），按常规监测间隔等待下一轮
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return False

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hw3.douyucdn2.cn/live/x.m3u8?wsAuth=1",
                "flv_url": "https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1",
                "record_url": "",
            },
            platform="斗鱼直播",
        )
    assert result is None
    # 仅 FLV 被校验：FLV 失败后 HLS 从未被探测（候选已在序列构建时剔除）
    assert probed == ["https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1"]


def test_excluded_platform_hls_only_no_fallback_warns(clear_probe_backoff: None) -> None:
    # 排除平台仅有 HLS 源：与全局关闭 HLS 采集同义（等效于对该平台关闭），
    # 必须告警并放弃本轮，且恢复指引指向排除列表而非 HLS 开关
    info: dict[str, object] = {"anchor_name": "坤记喜事多", "m3u8_url": "https://x/abc.m3u8", "record_url": ""}
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
        patch("src.stream_select.logger.warning") as warn,
    ):
        result = select_source_url(info, platform="斗鱼直播")
    assert result is None
    assert any("排除列表" in str(c.args[0]) for c in warn.call_args_list)


def test_non_excluded_platform_keeps_hls_priority(clear_probe_backoff: None) -> None:
    # 对照：列表外平台不受排除列表影响，HLS 采集开时仍 HLS 优先（顺序断言）
    probed: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        probed.append(url)
        return True

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://hs.hls.huya.com/src/x.m3u8",
                "flv_url": "https://hw.flv.huya.com/src/x.flv",
                "record_url": "",
            },
            platform="虎牙直播",
        )
    # 虎牙为 FLV-first 平台且不在排除列表：仍按 FLV → HLS 既有顺序（不受列表影响）
    assert result == "https://hw.flv.huya.com/src/x.flv"
    assert probed == [result]


def test_excluded_platform_h265_flv_not_switched_to_hls(clear_probe_backoff: None) -> None:
    # 排除平台连带失效 h265-FLV → HLS 切换：保存格式不支持 HEVC 直拷（钉 FLV）时 h265 FLV
    # 仍被剔除、HLS 又被排除剔除 → 与关闭 HLS 采集同义，本轮无可用候选返回 None。
    # [历史注 2026-10-01] 原注释「h265 FLV 无法 copy 录制」已按容器可行性收窄（TS/MKV/MP4
    # 放行，见放宽矩阵用例），本用例改为显式钉 FLV 维持原判据。
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
        patch.object(main, "video_save_type", "FLV"),
        patch("src.stream_select._validate_stream_url", return_value=True),
    ):
        result = select_source_url(
            {
                "flv_url": "https://hw1a.douyucdn2.cn/live/x.flv?wsAuth=1&codec=h265",
                "m3u8_url": "https://hw3.douyucdn2.cn/live/x.m3u8?wsAuth=1",
                "record_url": "",
            },
            platform="斗鱼直播",
        )
    assert result is None


# ---- 探针节流与重试抖动：降低风控误触发 ----
#
# 固定间隔探针（0.8s 恒定重试）与同 host 毫秒级连击探针都是机器人节奏指纹，
# 风控按节奏识别后对后续连接（含 ffmpeg 拉流）误触发 403。节流 + 抖动将其打散。


def test_recheck_delay_in_range_with_jitter() -> None:
    # 重试间隔 = 基准 0.8s + 0~0.7s 随机抖动：多次采样均落在 [0.8, 1.5) 且出现不同值
    # （恒定返回 0.8 说明抖动失效，节奏指纹回归）
    samples = {_recheck_delay() for _ in range(50)}
    assert all(0.8 <= d < 1.5 for d in samples)
    assert len(samples) > 1


def test_throttle_probe_gaps_same_host(monkeypatch: pytest.MonkeyPatch) -> None:
    # 同 host 相邻两次探针：首次不等待，紧随的第二次补足最小间隔（sleep 被调用且 > 0）
    # （直接调用 from-import 的真实 _throttle_probe，绕过 autouse 的 no-op 替换）
    monkeypatch.setattr(ss, "_PROBE_MIN_HOST_INTERVAL", 0.35)
    monkeypatch.setattr(ss, "_PROBE_THROTTLE_JITTER", 0.0)
    sleeps: list[float] = []
    with patch("src.stream_select.time.sleep", side_effect=lambda s: sleeps.append(s)):
        _throttle_probe(_FLV_URL)
        assert sleeps == []  # 首次探针不等待
        _throttle_probe(_FLV_URL)
    assert len(sleeps) == 1 and sleeps[0] > 0


def test_throttle_probe_different_hosts_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    # 不同 host 互不影响：A host 刚探过，B host 首次探针不等待
    monkeypatch.setattr(ss, "_PROBE_MIN_HOST_INTERVAL", 0.35)
    monkeypatch.setattr(ss, "_PROBE_THROTTLE_JITTER", 0.0)
    sleeps: list[float] = []
    with patch("src.stream_select.time.sleep", side_effect=lambda s: sleeps.append(s)):
        _throttle_probe(_FLV_URL)
        _throttle_probe(_HUYA_FLV_URL)
    assert sleeps == []


def test_throttle_enforced_before_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    # _validate_stream_url 发出探针前先节流：同 host 紧邻的第二次校验会先 sleep 补隔
    # （autouse fixture 已把 ss._throttle_probe 换成 no-op，此处恢复真实实现）
    monkeypatch.setattr(ss, "_throttle_probe", _throttle_probe)
    monkeypatch.setattr(ss, "_PROBE_MIN_HOST_INTERVAL", 0.35)
    monkeypatch.setattr(ss, "_PROBE_THROTTLE_JITTER", 0.0)
    sleeps: list[float] = []
    with patch("src.stream_select.time.sleep", side_effect=lambda s: sleeps.append(s)):
        cls = _m3u8_client_cls([206, 206], ["application/vnd.apple.mpegurl"] * 2)
        with patch("src.stream_select.httpx.Client", cls):
            assert _validate_stream_url(_M3U8_URL) is True  # 首次：不节流、探针 200 通过
            assert _validate_stream_url(_M3U8_URL) is True  # 第二次：先节流再探针
    assert len(sleeps) == 1 and sleeps[0] > 0


# ---- MID-19：交给 ffmpeg -i 的地址必须过形态白名单 ----


def test_is_recordable_url_shape_matrix() -> None:
    # 合法：http/https 与 rtmp/rtmps（斗鱼 rtmp 拼接是合法用例，不能简单要求 http(s)）
    assert _is_recordable_url("https://hw3.douyucdn2.cn/live/x.flv?wsAuth=1") is True
    assert _is_recordable_url("http://hs.hls.huya.com/src/x.m3u8") is True
    assert _is_recordable_url("rtmp://dylive.rtmp.douyucdn.cn/live/100rT.flv?wsAuth=1") is True
    assert _is_recordable_url("rtmps://a.example.com/live/x.flv") is True
    assert _is_recordable_url("HTTPS://EXAMPLE.COM/a.flv") is True
    # 非法：本地文件 / ffmpeg concat 协议 / 相对路径 / 缺主机名 / 空串 / 以 - 开头 / 非白名单协议
    assert _is_recordable_url("file:///etc/passwd") is False
    assert _is_recordable_url("concat:http://a/x.flv|http://b/y.flv") is False
    assert _is_recordable_url("/path/x.m3u8") is False
    assert _is_recordable_url("http://") is False
    assert _is_recordable_url("") is False
    assert _is_recordable_url("-i /etc/passwd") is False
    assert _is_recordable_url("ftp://host/x.flv") is False
    assert _is_recordable_url("https://host:badport/x.flv") is False


def test_select_source_url_never_returns_malformed_addresses() -> None:
    # 探针判定之外还必须过形态闸门：平台 JSON 被劫持时，「探针异常但末位可用」的放行语义
    # 不得把 file:/// 、相对路径、以 - 开头的串交给 ffmpeg -i。
    bad_urls = [
        "file:///etc/passwd",
        "concat:http://a/x.flv|http://b/y.flv",
        "/path/x.m3u8",
        " -i /etc/passwd",
        "ftp://host/x.flv",
    ]
    for bad in bad_urls:
        with (
            patch.object(main, "hls_collection_enabled", True),
            patch("src.stream_select._validate_stream_url", return_value=True),
            patch("src.stream_select.logger.warning") as warn,
        ):
            assert select_source_url({"flv_url": bad, "record_url": ""}) is None, bad
        assert any("形态不合规" in str(c.args[0]) for c in warn.call_args_list), bad


def test_select_source_url_allows_rtmp_candidate() -> None:
    # 对照：rtmp:// 是合法形态（斗鱼），必须照常选用
    url = "rtmp://dylive.rtmp.douyucdn.cn/live/100rT.flv?wsAuth=1"
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", return_value=True),
    ):
        assert select_source_url({"flv_url": url}) == url


def test_malformed_record_url_dropped_without_probe_and_frees_last_resort() -> None:
    # 畸形 record_url 连探针都不发；且它不再构成「还有回退档」的假象，
    # 于是真正的末位候选（FLV）拿到 last_resort 资格。
    calls: list[tuple[str, bool]] = []

    def _validate(url: str, **kwargs: object) -> bool:
        calls.append((url, bool(kwargs.get("last_resort"))))
        return False

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url({"flv_url": "https://x/a.flv", "record_url": "file:///etc/passwd"})
    assert result is None
    assert calls == [("https://x/a.flv", True)]


# ---- MID-18：record_url 通道同受 HLS 整组剔除约束，且不与已探候选重复烧探针 ----


def test_excluded_platform_record_url_m3u8_emits_zero_hls_probes() -> None:
    # 「HLS采集排除平台」的定稿语义是整组剔除、HLS 探针一次都不发。
    # 抖音/TikTok/网易CC 的 record_url 本身就是 m3u8：原实现在 FLV 校验失败后
    # 仍会对它照发 HEAD/Range-GET/分片探测、且 last_resort=True 拒绝也放行。
    calls: list[str] = []

    def _validate(url: str, **kwargs: object) -> bool:
        calls.append(url)
        return False

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["抖音直播"]),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url(
            {
                "m3u8_url": "https://d.example.com/a.m3u8",
                "flv_url": "https://d.example.com/a.flv",
                "record_url": "https://other.example.com/b.m3u8",
            },
            platform="抖音直播",
        )
    assert result is None
    # 只有 FLV 被探测：HLS 候选组与 m3u8 形态的 record_url 通道都零探针
    assert calls == ["https://d.example.com/a.flv"]


def test_hls_disabled_record_url_m3u8_warns_and_abandons() -> None:
    # 全局关闭 HLS 采集 + 仅有 m3u8（record_url 也是 m3u8）：必须走「无 FLV/record_url 可回退」
    # 的显式告警，而不是静默去探 record_url
    info: dict[str, object] = {
        "anchor_name": "只下发 HLS 的房间",
        "m3u8_url": "https://x/a.m3u8",
        "record_url": "https://x/a.m3u8",
    }
    with (
        patch.object(main, "hls_collection_enabled", False),
        patch("src.stream_select._validate_stream_url") as validate,
        patch("src.stream_select.logger.warning") as warn,
    ):
        assert select_source_url(info, platform="抖音直播") is None
    validate.assert_not_called()
    assert any("HLS 采集未启用" in str(c.args[0]) for c in warn.call_args_list)


def test_record_url_same_as_candidate_is_probed_only_once() -> None:
    # 虎牙/斗鱼的 record_url 与序列内候选逐字相同：原实现在选源结束前把同一地址完整再探
    # 一次（HEAD + GET 复核 / Range-GET + 分片），正面消耗该 CDN 的连接预算——
    # 正是探针退避机制要消除的行为。现复用本轮结论。
    flv = "https://hw1a.douyucdn2.cn/live/100rPCLP.flv?wsAuth=abc"
    calls: list[tuple[str, bool]] = []

    def _validate(url: str, **kwargs: object) -> bool:
        calls.append((url, bool(kwargs.get("last_resort"))))
        return False

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url({"flv_url": flv, "record_url": flv}, platform="斗鱼直播")
    assert calls == [(flv, False)]  # 同一地址只发一轮探针
    # 末位放行语义不变：探针拒绝 ≠ ffmpeg 不可拉流，record_url 档仍交由 ffmpeg 定夺
    assert result == flv


def test_record_url_different_from_candidates_still_probed_as_last_resort() -> None:
    # 对照：record_url 与候选不同址时，仍按原逻辑单独探测（末位放行）
    calls: list[tuple[str, bool]] = []

    def _validate(url: str, **kwargs: object) -> bool:
        calls.append((url, bool(kwargs.get("last_resort"))))
        return url.endswith("b.flv")

    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", side_effect=_validate),
    ):
        result = select_source_url({"flv_url": "https://x/a.flv", "record_url": "https://x/b.flv"})
    assert calls == [("https://x/a.flv", False), ("https://x/b.flv", True)]
    assert result == "https://x/b.flv"


# ---- MIN-02 / MIN-03：HLS 分片层探测的退避键与变体选择 ----


class _PlaylistProbeClient:
    # 仅用于在类型层暴露 requested（运行时由每次构造的嵌套子类共享），
    # 使 _media_playlist_client 的返回类型可被 mypy 解析、调用方 cls.requested 合法
    # ——与上面 _M3u8ProbeClient.get_calls 同一手法。
    requested: list[str] = []


def _media_playlist_client(seg_status: int, playlist_text: str = _HLS_MEDIA_BODY) -> type[_PlaylistProbeClient]:
    # HEAD 恒 200+mpegurl；顶层播放列表返回 playlist_text，其下的 .m3u8（master 变体 /
    # 子列表）一律返回媒体列表正文；非 .m3u8（即分片）返回给定状态码
    class _C(_PlaylistProbeClient, _StreamAsGet):
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_C":
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

        def close(self) -> None:
            pass

        def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
            return _FakeResponse(200, "application/vnd.apple.mpegurl")

        def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
            _C.requested.append(url)
            if url == _M3U8_URL:
                return _FakeResponse(200, "application/vnd.apple.mpegurl", text=playlist_text)
            if url.endswith(".m3u8"):
                return _FakeResponse(200, "application/vnd.apple.mpegurl", text=_HLS_MEDIA_BODY)
            return _FakeResponse(seg_status, "video/mp2t")

    return _C


def test_segment_reject_marks_backoff_under_playlist_key(clear_probe_backoff: None) -> None:
    # MIN-02：分片被 401/403 拒绝时，退避键必须是**播放列表 URL**（查询侧用的就是它）。
    # 原实现记成分片 URL（每轮随列表滑动）→ 写入的条目永不被读到、只被自身过期回收，
    # 「分片被拒 → 下轮跳过该线路探针」在分片层完全没落地。
    cls = _media_playlist_client(403)
    cls.requested = []
    with patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time.sleep"):
        assert _validate_stream_url(_M3U8_URL, platform="虎牙直播", last_resort=False) is False
    seg_url = next(u for u in cls.requested if ".ts?" in u)
    assert seg_url != _M3U8_URL
    assert _probe_in_backoff(_M3U8_URL, "虎牙直播") is True  # 播放列表键命中
    assert _probe_in_backoff(seg_url, "虎牙直播") is False  # 分片键不再是永不被读的死条目


_HLS_MASTER_ASCENDING = (
    "#EXTM3U\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=400000,RESOLUTION=640x360\n"
    "https://low.example.com/360.m3u8\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=6000000,RESOLUTION=1920x1080\n"
    "https://high.example.com/1080.m3u8\n"
)


def test_pick_master_variant_prefers_highest_bandwidth() -> None:
    # MIN-03：变体顺序不可信（不少生成器升序列出，最低档在前）。按 BANDWIDTH 取最高档，
    # 与 ffmpeg hls demuxer 的实际起拉档位对齐——否则「证明最低档可取、实际拉最高档」，
    # 正是斗鱼 hw 假绿事故从列表层挪到变体层的形态。
    assert _pick_master_variant(_HLS_MASTER_ASCENDING, _M3U8_URL) == "https://high.example.com/1080.m3u8"
    # 降序输入同样取最高（结果与出现顺序无关）
    descending = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=6000000\n"
        "https://high.example.com/1080.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=400000\n"
        "https://low.example.com/360.m3u8\n"
    )
    assert _pick_master_variant(descending, _M3U8_URL) == "https://high.example.com/1080.m3u8"
    # 全部缺 BANDWIDTH：按出现序取首个（保持旧行为）
    no_bw = "#EXTM3U\n#EXT-X-STREAM-INF:RESOLUTION=640x360\nlow.m3u8\n#EXT-X-STREAM-INF:x\nhigh.m3u8\n"
    assert _pick_master_variant(no_bw, "https://h/p.m3u8") == "https://h/low.m3u8"
    # 只有标签行、没有变体 URL → None（调用方保守放行）
    assert _pick_master_variant("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=100\n", _M3U8_URL) is None
    # I-FRAME 变体行不参与（它没有后继 URL 行）
    assert _pick_master_variant("#EXTM3U\n#EXT-X-I-FRAME-STREAM-INF:BANDWIDTH=999999,URI=i.m3u8\n", _M3U8_URL) is None


def test_master_playlist_probes_highest_bandwidth_variant() -> None:
    # 端到端：升序 master playlist 必须探最高带宽变体的分片，低档一次都不碰
    cls = _media_playlist_client(200, playlist_text=_HLS_MASTER_ASCENDING)
    cls.requested = []
    with patch("src.stream_select.httpx.Client", cls):
        assert _validate_stream_url(_M3U8_URL, last_resort=False) is True
    assert "https://high.example.com/1080.m3u8" in cls.requested
    assert not any("360.m3u8" in u for u in cls.requested), "最低档变体不应被探测"
    # 分片探测落在所选高档变体目录下
    assert any(u.startswith("https://high.example.com/") and ".ts?" in u for u in cls.requested)


# ---------------------------------------------------------------------------
# L-11 探针读取响应体必须有上限（CODE_REVIEW_2026-10-18）
# 事故形态：四处探针此前一律走 client.get()，httpx 会把响应体**一次性读满**才返回。
# Range: bytes=0-0 只是「请求」，不遵守 Range 的边缘节点会把 .ts 当整段流媒体一直发，
# 于是每个房间线程每轮选源都能吃进任意大的 body（80+ 房间并发＝无界内存，且零日志线索）。
# 现统一走 src/stream_select._bounded_probe_get：流式打开、状态码/头照旧，
# · 两跳 Range-GET（可达性判定）正文一个字节都不读；
# · 播放列表/变体列表两跳只读到 _PROBE_BODY_LIMIT 即断。
# 这三条用例一律用**真实 httpx + MockTransport**（打桩口径同
# tests/test_sync_probe_internal_guard.py::_install_mock_transport：客户端仍由生产工厂
# _probe_client 造出来、只把最底层 transport 换掉），因为「读到上限即断开」对假客户端
# 没有可观测后果——假响应的正文是一次交出的整块。测试不重写任何判定规则。

_L11_CHUNK = b"z" * 4096
_L11_ENDLESS_CHUNKS = 4000  # ≈16 MB：模拟「不遵守 Range、永不到头」的边缘节点形态


class _CountingStream(httpx.SyncByteStream):
    # 分块递送的大 body，并记下**被拉走**的字节数。生产侧早断 → 这个数就停在上限附近；
    # 摘掉上界的那次变异（把 break 换成 no-op）会让它一路逼近 16 MB —— 这条尺子就是那把锁。
    def __init__(self, first_chunk: bytes | None = None) -> None:
        self.pulled = 0
        self._first = first_chunk

    def __iter__(self) -> Iterator[bytes]:
        if self._first is not None:
            self.pulled += len(self._first)
            yield self._first
        for _ in range(_L11_ENDLESS_CHUNKS):
            self.pulled += len(_L11_CHUNK)
            yield _L11_CHUNK

    def close(self) -> None:
        return None


def _l11_install_transport(monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]) -> None:
    # 浅拷贝 httpx 成 shim、只替换被测模块命名空间里的引用（R1：禁改第三方/stdlib 模块本体）
    httpx_shim = types.SimpleNamespace(**vars(httpx))

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        client = _REAL_SYNC_CLIENT(*args, **kwargs)
        # 传了 proxy 时 httpx 会把代理传输装进 _mounts；清空让每一跳都落到 MockTransport 上
        client._mounts = {}
        client._transport = httpx.MockTransport(handler)
        return client

    httpx_shim.Client = _factory
    monkeypatch.setattr(ss, "httpx", httpx_shim)


def test_probe_range_get_never_reads_an_oversized_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 判定不变式：两跳 Range-GET（m3u8 列表本身 + 媒体分片）拿到的 body 从 8 字节变成 16 MB，
    # 校验结论必须逐字相同（都判可达）；且这一体**根本没被读过**。
    pulled: dict[str, _CountingStream] = {}

    def _make_handler(oversize: bool) -> Callable[[httpx.Request], httpx.Response]:
        def _handler(request: httpx.Request) -> httpx.Response:
            if request.method == "HEAD":
                # 斗鱼 hw CDN 的真实形态：禁用 HEAD（405 + 错误页 content-type）→ 走 Range-GET 探测，
                # 于是「列表 Range-GET」这一跳真的会被发出（HEAD 直接 200 时该跳会被整段绕过）
                return httpx.Response(405, headers={"content-type": "text/html"})
            if request.headers.get("range") == "bytes=0-0":
                role = "playlist_range" if str(request.url) == _M3U8_URL else "segment"
                if oversize:
                    stream = _CountingStream()
                    pulled[role] = stream
                    return httpx.Response(200, headers={"content-type": "video/mp2t"}, stream=stream)
                return httpx.Response(200, headers={"content-type": "video/mp2t"}, text="ok")
            # 播放列表一跳恒给正常正文（本条只管 Range-GET 这一族的读取形态）
            return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"}, text=_HLS_MEDIA_BODY)

        return _handler

    verdicts: list[bool] = []
    for oversize in (False, True):
        pulled.clear()
        _l11_install_transport(monkeypatch, _make_handler(oversize))
        verdicts.append(_validate_stream_url(_M3U8_URL, last_resort=False))
        if oversize:
            assert set(pulled) == {"playlist_range", "segment"}, pulled
            assert pulled["playlist_range"].pulled == 0, "列表 Range-GET 这一跳仍在读正文"
            assert pulled["segment"].pulled == 0, "分片 Range-GET 这一跳仍在读正文"
    assert verdicts == [True, True], verdicts


def test_probe_playlist_read_stops_at_the_body_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    # 播放列表一跳要读正文解析分片行，但真实列表远小于上限：读到 _PROBE_BODY_LIMIT 即断开，
    # 之后一节都不再拉。把上界换成 no-op 的那次变异会让 pulled 逼近 16 MB，本条转红。
    pulled: dict[str, _CountingStream] = {}
    header = _HLS_MEDIA_BODY.encode("utf-8")

    def _handler(request: httpx.Request) -> httpx.Response:
        if request.method == "HEAD":
            return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})
        if request.headers.get("range") == "bytes=0-0":
            return httpx.Response(200, headers={"content-type": "video/mp2t"}, text="ok")
        stream = _CountingStream(header)
        pulled["playlist"] = stream
        return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"}, stream=stream)

    _l11_install_transport(monkeypatch, _handler)
    # 超限正文的判定结论与小正文一致（可达）：上界只截掉解析用不到的尾部
    assert _validate_stream_url(_M3U8_URL, last_resort=False) is True
    limit = ss._PROBE_BODY_LIMIT
    assert limit <= pulled["playlist"].pulled <= limit + len(_L11_CHUNK), pulled["playlist"].pulled


def test_bounded_probe_get_contract_with_fake_client() -> None:
    # helper 自身的最小契约（不走网络）：read_body=False 时正文恒为空串、状态码与头原样带回；
    # read_body=True 时正文按上限截断。两跳 Range-GET 的「不读正文」由此钉死，
    # 不依赖上面两条真传输用例的分支顺序。
    body = "#EXTM3U\n" + "a" * 5000

    class _Client:
        def stream(self, method: str, url: str, headers: dict | None = None, follow_redirects: bool = True) -> Any:
            assert method == "GET" and url == "https://x/y.m3u8"
            return _FakeResponse(206, "application/vnd.apple.mpegurl", text=body)

    got = ss._bounded_probe_get(
        cast(httpx.Client, _Client()), "https://x/y.m3u8", {"Range": "bytes=0-0"}, read_body=False
    )
    assert got.status_code == 206 and got.text == ""
    assert got.headers.get("content-type") == "application/vnd.apple.mpegurl"

    full = ss._bounded_probe_get(cast(httpx.Client, _Client()), "https://x/y.m3u8", {}, body_limit=1024)
    assert full.text == body[:1024], len(full.text)
    assert full.status_code == 206


# ---------------------------------------------------------------------------
# MID-N32 机检回归锁（CODE_REVIEW_2026-09-21）
# src/stream_select.py 中 logger.* 调用（含其嵌套的 i18n.tr 模板实参）里所有
# url=<实参> 关键字都必须包 utils.mask_credentials(...)：流直链的查询侧挂有
# 斗鱼 wsAuth / 抖音 signature 等凭据，裸传即明文落进 logs/streamget.log
# （300 KB 轮转保留多份并可能被归档外发）。MID-N32 修复前实测 24 处已包、
# 5 处 HLS 探测日志裸传。占位符名一律保持 {url} 不变——改占位符名等于新增
# 四语 msgid，须由 i18n 侧收口，不在本锁职责内。
# 结构参照 tests/test_i18n_migration.py::test_gate_predicate_sees_concatenated_fstring：
# 判据本体抽成函数，全文件扫描与判据自检用例共用，防止门禁自身假绿。

_LOGGER_METHODS = {"debug", "info", "success", "warning", "error", "critical", "exception", "trace", "log"}
_STREAM_SELECT_PATH = Path(__file__).resolve().parent.parent / "src" / "stream_select.py"


def _is_mask_credentials_call(node: ast.AST) -> bool:
    # 匹配 utils.mask_credentials(...)：utils 经 `from src import utils` 模块级导入，
    # stream_select.py 内没有对该名字的局部遮蔽或别名（与文件里其余已包掩码的写法同形）
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "mask_credentials"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "utils"
    )


def _bare_url_kwarg_linenos(src: str) -> list[int]:
    # 判据本体：对每个 logger.<已知方法>(...) 调用，递归其**整个实参子树**
    # （MID-N32 的 5 处均为嵌套在 i18n.tr 里的多行 keyword，只扫顶层会漏），
    # 凡关键字名为 url 且实参不是 utils.mask_credentials(...) 调用即判违规。
    # 字符串常量豁免：写死的样例地址不携带用户会话凭据，包掩码反而是噪音。
    offenders: list[int] = []
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr in _LOGGER_METHODS
            and isinstance(func.value, ast.Name)
            and func.value.id == "logger"
        ):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.keyword) and sub.arg == "url":
                if isinstance(sub.value, ast.Constant):
                    continue
                if not _is_mask_credentials_call(sub.value):
                    offenders.append(sub.value.lineno)
    return sorted(offenders)


def test_stream_select_all_url_logger_kwargs_masked() -> None:
    # ① 全文件机检：不允许任何裸传 url=<变量>（新增一处裸传即变红）
    src = _STREAM_SELECT_PATH.read_text(encoding="utf-8-sig")
    offenders = _bare_url_kwarg_linenos(src)
    detail = ", ".join(f"src/stream_select.py:{ln}" for ln in offenders)
    assert not offenders, f"以下 url= 实参未经 utils.mask_credentials 脱敏（MID-N32 回归）：{detail}"


def test_mask_gate_predicate_sees_bare_url_kwarg() -> None:
    # ② 判据自检（防门禁假绿）：把 _bare_url_kwarg_linenos 退回「只扫 logger 顶层
    # keywords」会让本用例变红——违规必须真的抓得到
    bare_nested = (
        "logger.debug(\n"
        "    i18n.tr(\n"
        "        '探测解析异常: {url}',\n"
        "        url=playlist_url,\n"
        "    )\n"
        ")\n"
    )
    assert _bare_url_kwarg_linenos(bare_nested) == [4], "门禁漏抓：嵌套在 tr() 里的裸传 url= 必须命中"
    assert _bare_url_kwarg_linenos("logger.warning(i18n.tr('回退: {url}', url=same_origin))\n") == [1]
    # 反向：已包掩码与常量样例地址不得误报（否则全文件扫描会被文件里既有的合法写法整体打成红）
    masked = "logger.warning(i18n.tr('回退: {url}', url=utils.mask_credentials(same_origin)))\n"
    assert _bare_url_kwarg_linenos(masked) == []
    assert _bare_url_kwarg_linenos("logger.warning(i18n.tr('固定样例: {url}', url='https://x/y.m3u8'))\n") == []


# ---------------------------------------------------------------------------
# SEV-N05 回归锁（CODE_REVIEW_2026-09-21）
# 两处探针客户端构造（select_source_url 的整轮共用客户端、_validate_stream_url 的自建客户端）
# 的 proxy 实参必须先经 utils.handle_proxy_addr 归一：配置项「代理地址」允许裸 ip:port 写法
# （见 src/utils.py handle_proxy_addr 与 _PROXY_CREDENTIAL_RE 注释），且「代理开关打开但地址
# 留空」是合法形态（main.py 原样透传成 ""），而 venv httpx 0.28 的 Client(proxy=...) 只认带
# scheme 的地址——裸串与空串一律抛 ValueError: Unknown scheme for proxy URL（仅 None 正常）。
# 归一缺失的后果不是「校验判不可达」而是**抛穿房间线程**：解析成功却每轮炸在选源，房间永不进
# 入录制链，并持续向按 host 的熔断器投失败样本。
# 判据取自 httpx 本体而非本文件自实现：桩在 __init__ 里用真实 httpx 构造一次（不发任何请求），
# 因此「漏归一」在用例里表现为真抛错，而不是自己写一份 handle_proxy_addr 再断言它自己。

_BARE_PROXY = "127.0.0.1:7890"
_NORMALIZED_PROXY = "http://127.0.0.1:7890"

# patch("src.stream_select.httpx.Client", ...) 换掉的其实是**全局 httpx 模块**上的属性
# （src.stream_select.httpx 就是 httpx 本体），所以桩内再写 httpx.Client(...) 等于调用桩自己、
# 直接递归到 RecursionError。判据要用「真构造器」，只能在补丁生效前（import 期）先存一份引用。
_REAL_SYNC_CLIENT = httpx.Client
_REAL_ASYNC_CLIENT = httpx.AsyncClient


class _ProxyContractClient(_StreamAsGet):
    # 记录每支探针客户端收到的 proxy 实参，并立刻交给真实 httpx 判一次契约（构造后即关闭）。
    # HEAD 200 + mpegurl、正文为空 → _probe_hls_segment 解析不出分片、保守放行，故首候选即通过。
    # WP-J：形参签名必须跟住 src/stream_select.py 的 _probe_client —— 它现在多传一个
    # event_hooks（逐跳复检钩子）。这里既记录钩子条数（供「两处自建都挂上了钩子」的行为锁断言），
    # 也把 event_hooks 一并交给**真实** httpx 构造：桩若把实参形状写错，真 httpx 会当场抛错，
    # 契约仍由 httpx 本体判定、不在本文件自实现。
    proxies: list[str | None] = []
    response_hook_counts: list[int] = []
    instantiated = 0
    close_calls = 0

    def __init__(
        self,
        *,
        timeout: int = 10,
        proxy: str | None = None,
        verify: bool = True,
        # 实参类型必须与 httpx.Client 的 event_hooks 声明兼容（typeshed 要 Mapping[str, list[Callable]]，
        # 写 list[object] 会在下一行透传给真客户端时报 arg-type）；Any 只用于这一处打桩签名，
        # 判据本身仍走 ast 收窄。
        event_hooks: dict[str, list[Any]] | None = None,
    ) -> None:
        _ProxyContractClient.instantiated += 1
        _ProxyContractClient.proxies.append(proxy)
        _ProxyContractClient.response_hook_counts.append(len((event_hooks or {}).get("response") or []))
        real = _REAL_SYNC_CLIENT(timeout=timeout, proxy=proxy, verify=verify, event_hooks=event_hooks)
        real.close()

    def close(self) -> None:
        _ProxyContractClient.close_calls += 1

    def head(self, url: str, headers: dict[str, str] | None = None, follow_redirects: bool = True) -> _FakeResponse:
        return _FakeResponse(200, "application/vnd.apple.mpegurl")

    def get(self, url: str, headers: dict | None = None, follow_redirects: bool = True) -> _FakeResponse:
        return _FakeResponse(200, "application/vnd.apple.mpegurl")


def _reset_proxy_contract_client() -> None:
    # 类级计数/记录会跨用例累积，逐用例显式重置（不复用其它用例的假客户端类，避免互相污染）
    _ProxyContractClient.proxies = []
    _ProxyContractClient.response_hook_counts = []
    _ProxyContractClient.instantiated = 0
    _ProxyContractClient.close_calls = 0


def test_select_source_url_bare_proxy_addr_normalized_before_construct() -> None:
    # 裸 ip:port：整轮共用客户端必须以 http:// 前缀构造（探针确实走代理），且不得抛 ValueError
    _reset_proxy_contract_client()
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", []),
        patch("src.stream_select.httpx.Client", _ProxyContractClient),
    ):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": "", "record_url": ""}, _BARE_PROXY, "B站直播")
    assert result == _M3U8_URL, "归一后选源须正常返回首候选（修复前此处抛穿 ValueError）"
    # 传给 httpx.Client 的必须是带 scheme 的地址
    assert _ProxyContractClient.proxies == [_NORMALIZED_PROXY]
    # AGENTS「探针客户端复用作用域 = 单次选源、finally 关闭」不得回退：一支、关一次
    assert _ProxyContractClient.instantiated == 1
    assert _ProxyContractClient.close_calls == 1
    # WP-J：构造点收敛到 _probe_client 后，整轮共用客户端必须带上恰一支 response 逐跳复检钩子
    assert _ProxyContractClient.response_hook_counts == [1], "select_source_url 的客户端未挂逐跳复检钩子"


def test_select_source_url_empty_proxy_addr_becomes_none() -> None:
    # 「代理开关打开但地址留空」形态：归一为 None（= 不使用代理），不得把 "" 交给 httpx
    _reset_proxy_contract_client()
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", []),
        patch("src.stream_select.httpx.Client", _ProxyContractClient),
    ):
        result = select_source_url({"m3u8_url": _M3U8_URL, "flv_url": "", "record_url": ""}, "", "B站直播")
    assert result == _M3U8_URL
    assert _ProxyContractClient.proxies == [None]
    # WP-J：整轮共用客户端（复用分支）同样必须带逐跳复检钩子
    assert _ProxyContractClient.response_hook_counts == [1], "select_source_url 的客户端未挂逐跳复检钩子"


def test_validate_stream_url_self_built_client_normalizes_proxy() -> None:
    # 第二处构造点（_validate_stream_url 自建客户端，client=None 路径）同样必须归一
    _reset_proxy_contract_client()
    with patch("src.stream_select.httpx.Client", _ProxyContractClient):
        assert _validate_stream_url(_M3U8_URL, proxy_addr=_BARE_PROXY, last_resort=True) is True
    assert _ProxyContractClient.proxies == [_NORMALIZED_PROXY]
    assert _ProxyContractClient.close_calls == 1, "自建客户端由 owns_client 语义自行关闭"
    # WP-J：自建分支也必须带恰一支 response 钩子（两处自建形态一致，漏一处即只接了一半）
    assert _ProxyContractClient.response_hook_counts == [1], "_validate_stream_url 自建客户端未挂逐跳复检钩子"


class _AlwaysFailingClient:
    # 归一之后仍可能被 httpx 拒收（带 scheme 但 httpx 不认，如 ftp://…；或入参类型异常）：
    # 构造失败必须降级为「本轮无可用探针客户端」，而不是抛穿、也不是判成「所有候选不可达」
    instantiated = 0

    def __init__(self, *args: object, **kwargs: object) -> None:
        _ = args, kwargs
        _AlwaysFailingClient.instantiated += 1
        raise ValueError("Unknown scheme for proxy URL")


def test_probe_client_construction_failure_degrades_to_last_resort_release(clear_probe_backoff: None) -> None:
    # 虎牙为 FLV-first，故序列为 FLV → HLS，末位是 HLS 候选（交由 ffmpeg 定夺）
    _AlwaysFailingClient.instantiated = 0
    flv = "http://aldirect.flv.huya.com/huyalive/x.flv?wsSecret=abc"
    hls_a = "http://aldirect.hls.huya.com/huyalive/x.m3u8?wsSecret=abc"
    hls_b = "http://tx.hls.huya.com/huyalive/y.m3u8?wsSecret=abc"
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING")
    try:
        with (
            patch.object(main, "hls_collection_enabled", True),
            patch.object(main, "hls_collection_exclude_platforms", []),
            patch("src.stream_select.httpx.Client", _AlwaysFailingClient),
        ):
            result = select_source_url(
                {"m3u8_url_list": [hls_a, hls_b], "flv_url": flv, "record_url": ""},
                _BARE_PROXY,
                "虎牙直播",
            )
    finally:
        logger.remove(handler_id)
    # ① 不抛穿房间线程（上一行调用即「修复前会抛 ValueError」的现场）
    # ② 不返回「本轮无可用源」的 None：末位候选按既有 last_resort 口径放行给 ffmpeg
    assert result == hls_b
    # ③ 整轮共用客户端失败后各候选改走 _validate_stream_url 既有的自建路径（未新增分支）
    assert _AlwaysFailingClient.instantiated >= 1
    # ④ 降级不是静默吞异常：逐候选各记一条「流地址校验异常」WARNING
    assert sum(1 for c in captured if "流地址校验异常: " in c) == 3
    # ⑤ 一个探针都没发出去 → 不得把可用线路误记进 CDN 退避表（那才会放大成后续轮次的假红）
    for cand in (flv, hls_a, hls_b):
        assert _probe_in_backoff(cand, "虎牙直播") is False


class _ProxyContractAsyncClient:
    # 异步侧（async_http.get_response_status → _build_client）的同型桩：只记录 proxy 实参，
    # 契约判定放在用例里用真实 httpx.AsyncClient 做一次（构造 + aclose，不发请求）。
    proxies: list[str | None] = []
    is_closed = False

    def __init__(self, *args: object, proxy: str | None = None, **kwargs: object) -> None:
        _ = args, kwargs
        _ProxyContractAsyncClient.proxies.append(proxy)

    async def head(self, url: str, **kwargs: object) -> _FakeResponse:
        _ = url, kwargs
        return _FakeResponse(200, "application/vnd.apple.mpegurl")


async def test_bare_proxy_addr_reaches_sync_and_async_probe_with_same_value() -> None:
    # AGENTS「同步/异步校验器的 proxy / verify / UA 三者必须一致」：同一个裸 ip:port 配置值，
    # 两侧都必须归一成同一 http:// 地址、都不抛 ValueError。异步侧原本就归一（async_http:365），
    # 本用例锁住「同步侧改完仍然与它同结论」，防止将来只改一侧又造成口径分叉。
    _reset_proxy_contract_client()
    _ProxyContractAsyncClient.proxies = []
    async_http._client_cache.clear()  # 桩客户端不得泄漏进模块级缓存（键含事件循环）
    try:
        with patch("src.stream_select.httpx.Client", _ProxyContractClient):
            assert select_source_url({"m3u8_url": _M3U8_URL, "flv_url": "", "record_url": ""}, _BARE_PROXY, "B站直播")
        with patch("src.async_http.httpx.AsyncClient", _ProxyContractAsyncClient):
            assert await get_response_status(_M3U8_URL, proxy=_BARE_PROXY, platform="B站直播") is True
        # 真机契约：异步侧拿到的取值 httpx 自己也认（构造 + aclose，不发请求）
        real = _REAL_ASYNC_CLIENT(proxy=_ProxyContractAsyncClient.proxies[0])
        await real.aclose()
    finally:
        async_http._client_cache.clear()
    assert _ProxyContractClient.proxies == [_NORMALIZED_PROXY]
    assert _ProxyContractAsyncClient.proxies == [_NORMALIZED_PROXY]


# 静态回退侦测（与本文件 MID-N32 机检、tests/test_ffmpeg_reconnect_args.py 同一手法）：
# 运行期断言只覆盖「探针客户端被真的构造」的调用形态；一旦有人把归一行整条删掉、或把某个新
# 构造点写成裸传，而该路径当前没有运行期用例走到，锁就瞎了。AST 判据不依赖执行，直接把
# 「每个 httpx.Client 构造点的 proxy= 都经 handle_proxy_addr」钉成机检。
#   [WP-J 形态变更] 两处裸 httpx.Client(...) 已收敛为 src/stream_select.py 的 _probe_client
#   工厂（唯一的 httpx.Client 构造点）+ 两个调用点。归一约束随之从「构造点的 proxy=」平移到
#   「_probe_client 调用点的 proxy_addr 实参」——语义完全等价（值仍必须在同一作用域内、使用之前由
#   utils.handle_proxy_addr 得到），且工厂自身那次 httpx.Client(proxy=proxy_addr) 的 proxy 来自形参、
#   由「调用点必须归一」间接保证，故工厂内不重复判（否则唯一合法构造会被误报）。
def _is_handle_proxy_addr_call(node: ast.AST) -> bool:
    # 匹配 utils.handle_proxy_addr(...)：utils 经 `from src import utils` 模块级导入
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "handle_proxy_addr"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "utils"
    )


def _is_httpx_client_call(node: ast.AST) -> TypeGuard[ast.Call]:
    # 匹配 httpx.Client(...) 构造（异步侧的 AsyncClient 不在本模块，不属本锁职责）。
    # 返回 TypeGuard 而不是 bool：收窄后 ast.walk 的产物可直接取 .keywords，判据仍由本函数
    # 单点定义；写 bool 会逼每个调用点各补一遍 isinstance，反而多出三处可漂移的判据。
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Client"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
    )


def _is_probe_client_call(node: ast.AST) -> bool:
    # 匹配 _probe_client(...)——WP-J 之后本模块探针客户端的唯一构造入口
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_probe_client"


# 本模块「发出一次探针请求」的全部形态。
# L-11 新增 _bounded_probe_get：探针读取正文统一收进
# 这个带字节上限的流式入口之后，「发探针」在 AST 里不再只表现为 client.head/get/stream 三种
# 属性调用。判据本体必须跟着形态走——否则下面 (b)/(d) 两条结构锁的扫描面会静默变空
# （(d) 自带「判据没扫到任何 try 即失效」的反向见证，正是为这种漂移准备的）。
_PROBE_CLIENT_METHODS = {"head", "get", "stream"}


def _is_probe_emit(node: ast.AST) -> TypeGuard[ast.Call]:
    # 返回 TypeGuard 而非 bool：下面 (b) 的 min(n.lineno ...) 需要 ast.Call 收窄，
    # 写 bool 会让产物退化成 list[AST] 并当场 mypy attr-defined（判据多出一份可漂移形态）。
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return (
            node.func.attr in _PROBE_CLIENT_METHODS
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in {"client", "probe_client"}
        )
    # 函数形态：_bounded_probe_get(client, url, …)
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_bounded_probe_get"


def _probe_client_proxy_argument(call: ast.Call) -> ast.expr | None:
    # 取 _probe_client 调用点的 proxy 实参：本模块两处都按**位置**传（第 2 个形参 proxy_addr），
    # 但关键字传法同样合法，两种都得认——只按 keyword 找会让位置实参悄悄逃过门禁（假绿）。
    for keyword in call.keywords:
        if keyword.arg == "proxy_addr":
            return keyword.value
    if len(call.args) >= 2:
        return call.args[1]
    return None


def _scope_nodes(root: ast.AST) -> Iterator[ast.AST]:
    # 单层作用域遍历：进入模块体/函数体，但**不**下沉进任何函数定义（那属另一个作用域，
    # 否则同一次构造会被模块与函数各数一遍，既虚增总数、又让「别的函数里归过一」洗白违规）
    stack: list[ast.AST] = [root]
    while stack:
        node = stack.pop()
        yield node
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            stack.append(child)


def _unnormalized_proxy_constructions(src: str) -> tuple[list[int], int, int]:
    # 返回 (违规点行号, 扫描到的 httpx.Client 构造总数, 扫描到的 _probe_client 调用点总数)。
    # 判据：proxy 实参要么内联 utils.handle_proxy_addr(...)，要么是**同一作用域内、使用之前**由它
    # 赋过值的名字。未传 proxy 的构造即直连，不构成违规（但会被总数计数暴露给调用方断言）。
    offenders: list[int] = []
    total = 0
    probe_calls_total = 0
    tree = ast.parse(src)
    scopes: list[ast.AST] = [tree]
    scopes.extend(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))
    for scope in scopes:
        # 工厂定义体内的 httpx.Client 只作计数、不作归一判定（理由见上方 WP-J 形态变更注）
        in_factory = isinstance(scope, ast.FunctionDef) and scope.name == "_probe_client"
        normalized_at: dict[str, int] = {}
        constructions: list[ast.Call] = []
        factory_uses: list[ast.Call] = []
        for node in _scope_nodes(scope):
            if isinstance(node, ast.Assign) and _is_handle_proxy_addr_call(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        normalized_at[target.id] = node.lineno
            elif isinstance(node, ast.Call) and _is_httpx_client_call(node):
                constructions.append(node)
            elif isinstance(node, ast.Call) and _is_probe_client_call(node):
                factory_uses.append(node)
        for call in constructions:
            if in_factory:
                continue
            proxy_kw = next((kw for kw in call.keywords if kw.arg == "proxy"), None)
            if proxy_kw is None:
                continue
            value = proxy_kw.value
            if _is_handle_proxy_addr_call(value):
                continue
            if isinstance(value, ast.Name) and normalized_at.get(value.id, 10**9) < call.lineno:
                continue
            offenders.append(call.lineno)
        for call in factory_uses:
            # 变量名与上一循环的 value 分开：_probe_client_proxy_argument 的返回类型是
            # ast.expr | None，复用同一个名字会让 mypy 按首循环的 ast.expr 收窄后报 assignment 冲突。
            factory_value = _probe_client_proxy_argument(call)
            if factory_value is None:
                # 调用点没给 proxy 实参：本模块两处构造都**应当**显式透传归一后的代理地址，
                # 漏写一律记违规（不得被「直连豁免」洗白）
                offenders.append(call.lineno)
                continue
            if _is_handle_proxy_addr_call(factory_value):
                continue
            if isinstance(factory_value, ast.Constant) and factory_value.value is None:
                continue  # 显式直连（字面量 None），不构成「裸传未归一的配置值」形态
            if isinstance(factory_value, ast.Name) and normalized_at.get(factory_value.id, 10**9) < call.lineno:
                continue
            offenders.append(call.lineno)
        total += len(constructions)
        probe_calls_total += len(factory_uses)
    return sorted(offenders), total, probe_calls_total


def test_all_probe_client_constructions_normalize_proxy_addr() -> None:
    # ① 全文件机检：两处构造点都必须归一（新增第三处裸传即变红）
    src = _STREAM_SELECT_PATH.read_text(encoding="utf-8-sig")
    offenders, total, probe_calls = _unnormalized_proxy_constructions(src)
    detail = ", ".join(f"src/stream_select.py:{ln}" for ln in offenders)
    assert (
        not offenders
    ), f"以下 httpx.Client 构造点 / _probe_client 调用点的 proxy 未经 utils.handle_proxy_addr 归一（SEV-N05 回归）：{detail}"
    # 扫描面非空自检：总数为 0 说明判据失效（或构造被搬去别处），绿灯不能是「什么都没查」
    # WP-J：httpx.Client 构造收敛为 _probe_client 内唯一一处；调用点必须是两处（选源共用 + 校验自建），
    # 少一处即「另一处又变回裸构造」的静默漏接形态。
    assert total == 1, f"预期本模块恰有 1 处 httpx.Client 构造（_probe_client 工厂内），实扫到 {total} 处"
    assert probe_calls == 2, f"预期两处探针客户端都出自 _probe_client，实扫到 {probe_calls} 处调用"


def test_probe_client_wiring_and_gate_coverage() -> None:
    # ② WP-J 结构锁：两处自建 client 都挂上了逐跳钩子、且都过了初始 URL 内网判定（AST 断言，
    # 防后来者只接一处）。判据全部取自生产代码的 AST，不在测试里重写一遍规则。
    src = _STREAM_SELECT_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(src)
    funcs = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    # (a) 唯一的 httpx.Client 构造必须落在 _probe_client 内，并带上 event_hooks={"response": [...]}
    factory = funcs["_probe_client"]
    constructions = [n for n in ast.walk(factory) if _is_httpx_client_call(n)]
    assert len(constructions) == 1, "探针客户端构造必须收敛为 _probe_client 内唯一一处"
    hook_kw = next((kw for kw in constructions[0].keywords if kw.arg == "event_hooks"), None)
    assert hook_kw is not None, "_probe_client 未把 event_hooks 传给 httpx.Client（逐跳复检静默失效）"
    hook_dict = hook_kw.value
    assert isinstance(hook_dict, ast.Dict)
    response_hooks: ast.expr | None = None
    for key, value in zip(hook_dict.keys, hook_dict.values):
        if isinstance(key, ast.Constant) and key.value == "response":
            response_hooks = value
    assert response_hooks is not None, "event_hooks 里没有 response 键（逐跳复检挂在别的钩子上＝没挂）"
    assert isinstance(response_hooks, ast.List) and len(response_hooks.elts) == 1
    guard_call = response_hooks.elts[0]
    assert isinstance(guard_call, ast.Call) and isinstance(guard_call.func, ast.Name)
    assert (
        guard_call.func.id == "build_sync_hop_guard"
    ), "response 钩子必须出自 async_http 的同步工厂 build_sync_hop_guard（判定只有一份事实源）"

    # (b) 两处使用 client 的路径都在**发出第一个请求之前**过了初始 URL 内网判定：
    #     · 自建分支（_validate_stream_url）：判定早于本函数内的第一次探针发出
    #       （形态见 _is_probe_emit：client.head/get/stream 与 _bounded_probe_get 都算）
    #     · 复用分支（select_source_url）：判定早于第一次把地址交给探针/ffmpeg 的 _validate_stream_url
    #       与 _accept_source 调用点
    for name in ("_validate_stream_url", "select_source_url"):
        body = funcs[name]
        judged = [
            n
            for n in ast.walk(body)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("internal_stream_target_reason", "redirect_hop_rejection_reason")
        ]
        assert judged, f"{name} 内没有初始 URL 内网判定（internal_stream_target_reason）"
        emitted = [n for n in ast.walk(body) if _is_probe_emit(n)] + [
            n
            for n in ast.walk(body)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_validate_stream_url"
        ]
        assert emitted, f"{name} 内找不到探针发出点，判据（判定必须早于探针）失效"
        assert min(n.lineno for n in judged) < min(
            n.lineno for n in emitted
        ), f"{name}: 内网判定排在探针之后——被拒的地址已经发出去了"

    # (c) 判定与钩子都来自 async_http 的同一份实现，且一律走**函数内 import**
    #     （模块级出边会改变 stream_select↔main 这条既有导入环的初始化顺序，见 async_http.py:518-521）
    assert not any(
        isinstance(n, ast.ImportFrom) and (n.module or "").endswith("async_http") for n in tree.body
    ), "stream_select 不得在模块级 import async_http（本仓存在 stream_select↔main 导入环）"
    for name in ("_probe_client", "_validate_stream_url", "select_source_url", "_confirm_get_ok", "_probe_hls_segment"):
        imports = [
            n
            for n in ast.walk(funcs[name])
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("async_http")
        ]
        assert imports, f"{name} 缺函数内 import from src.async_http"

    # (d) 内部控制流异常必须在每个「发探针 + 用 except Exception 吞异常」的 try 里被单独放行，
    #     且排在宽 except **之前**（Python 按顺序匹配处理器，写反了等于没写）——否则它会落进
    #     except Exception 分支、被「维持 HEAD 结论 / 按列表可达 / 末位放行」的既有语义吃回去。
    for name in ("_validate_stream_url", "_confirm_get_ok", "_probe_hls_segment"):
        guarded = 0
        for tr in [n for n in ast.walk(funcs[name]) if isinstance(n, ast.Try)]:
            emits = [n for stmt in tr.body for n in ast.walk(stmt) if _is_probe_emit(n)]
            kinds = [
                h.type.id if isinstance(h.type, ast.Name) else "?"
                for h in tr.handlers
                if isinstance(h.type, (ast.Name, ast.Tuple))
            ]
            broad_at = next((i for i, k in enumerate(kinds) if k == "Exception"), None)
            hop_at = next((i for i, k in enumerate(kinds) if k == "RedirectHopRejected"), None)
            if emits and broad_at is not None:
                guarded += 1
                assert (
                    hop_at is not None
                ), f"{name}: 有一段既发探针又用 except Exception 吞异常的 try 没有 except RedirectHopRejected 分支"
                assert hop_at < broad_at, f"{name}: except RedirectHopRejected 写在 except Exception 之后（永不命中）"
        assert guarded >= 1, f"{name}: 判据没扫到任何「发探针且吞异常」的 try，本条锁已失效"


def test_proxy_normalization_gate_predicate_sees_unnormalized_construction() -> None:
    # ③ 判据正/反向自检（防门禁自身假绿）：删掉归一行、归一发生在构造之后都必须被抓到；
    # 内联归一、构造前归一、以及不传 proxy 的直连构造不得误报
    bare = "def f(url, proxy_addr):\n    c = httpx.Client(timeout=5, proxy=proxy_addr, verify=True)\n"
    assert _unnormalized_proxy_constructions(bare) == ([2], 1, 0)
    too_late = (
        "def f(url, proxy_addr):\n"
        "    c = httpx.Client(proxy=proxy_addr)\n"
        "    proxy_addr = utils.handle_proxy_addr(proxy_addr)\n"
    )
    assert _unnormalized_proxy_constructions(too_late) == ([2], 1, 0)
    inlined = "def f(url, proxy_addr):\n    c = httpx.Client(proxy=utils.handle_proxy_addr(proxy_addr))\n"
    assert _unnormalized_proxy_constructions(inlined) == ([], 1, 0)
    normalized_first = (
        "def f(url, proxy_addr):\n"
        "    proxy_addr = utils.handle_proxy_addr(proxy_addr)\n"
        "    c = httpx.Client(proxy=proxy_addr)\n"
    )
    assert _unnormalized_proxy_constructions(normalized_first) == ([], 1, 0)
    no_proxy = "def f(url):\n    c = httpx.Client(timeout=5, verify=True)\n"
    assert _unnormalized_proxy_constructions(no_proxy) == ([], 1, 0)
    # WP-J 新增：_probe_client 调用点的 proxy 同样必须归一，位置实参与关键字实参两种传法都要抓得到；
    # 「漏写 proxy 实参」必须变红，而「显式传字面量 None」= 直连、属合法形态（不得误报）
    factory_bare_positional = "def f(url, proxy_addr):\n" "    c = _probe_client(5, proxy_addr, True)\n"
    assert _unnormalized_proxy_constructions(factory_bare_positional) == ([2], 0, 1)
    factory_bare_keyword = "def f(url, proxy_addr):\n" "    c = _probe_client(5, proxy_addr=proxy_addr, verify=True)\n"
    assert _unnormalized_proxy_constructions(factory_bare_keyword) == ([2], 0, 1)
    factory_missing_proxy = "def f(url, timeout, verify):\n    c = _probe_client(timeout, verify=verify)\n"
    assert _unnormalized_proxy_constructions(factory_missing_proxy) == ([2], 0, 1)
    factory_normalized = (
        "def f(url, proxy_addr):\n"
        "    proxy_addr = utils.handle_proxy_addr(proxy_addr)\n"
        "    c = _probe_client(5, proxy_addr, True)\n"
    )
    assert _unnormalized_proxy_constructions(factory_normalized) == ([], 0, 1)
    factory_explicit_none = "def f(url):\n    c = _probe_client(5, None, True)\n"
    assert _unnormalized_proxy_constructions(factory_explicit_none) == ([], 0, 1)
    # 工厂定义体内那次「proxy 来自形参」的构造不得被误报（否则唯一合法构造恒红）
    factory_body = (
        "def _probe_client(timeout, proxy_addr, verify):\n"
        "    return httpx.Client(timeout=timeout, proxy=proxy_addr, verify=verify)\n"
    )
    assert _unnormalized_proxy_constructions(factory_body) == ([], 1, 0)
