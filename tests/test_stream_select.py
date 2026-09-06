# 验证流地址校验的末位候选（last_resort）放行语义：
# - 斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁用 HEAD 方法），ffmpeg 实际 GET 拉流正常；
# - 末位候选（无备选可回退）稳定拒绝也仅告警放行，交由 ffmpeg 定夺；
# - 非末位候选仍判不可达，由上层回退下一候选。
# 另覆盖虎牙探针退避：CDN 限流（连续 403）时跳过探针、末位直接放行 ffmpeg。
# 全程 mock httpx.Client，不触网。

from __future__ import annotations

import time
from typing import Iterator, Literal
from unittest.mock import patch

import pytest

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
import src.stream_select as ss
from src.stream_select import (
    _mark_probe_reject,
    _probe_backoff,
    _probe_backoff_key,
    _probe_backoff_lock,
    _probe_in_backoff,
    _recheck_delay,
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


_FLV_URL = "https://hw3.douyucdn2.cn/live/12828016rSWtjVdN.flv?wsAuth=abc&token=web-h5"


class _FakeResponse:
    def __init__(self, status_code: int, content_type: str) -> None:
        self.status_code = status_code
        self.headers = {"content-type": content_type} if content_type else {}


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

    # headers 由生产代码逐请求传入（客户端在多候选间复用，不能再挂 client 级头）
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
    # 对照：B站仍依赖 Referer，确保本次改动未误伤其它平台。
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
    class _C(_M3u8ProbeClient):
        get_calls = 0

        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> "_C":
            return self

        def __exit__(self, *_args: object) -> Literal[False]:
            return False

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
    assert cls.get_calls == 2


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
    # FLV 为 h265 不可用时，HLS 即最后机会：恒为 last_resort
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch("src.stream_select._validate_stream_url", return_value=False) as mock_v,
    ):
        result = select_source_url(
            {"m3u8_url": "https://x/a.m3u8", "flv_url": "https://x/a.flv?codec=h265", "record_url": ""}
        )
    assert result is None  # mock 恒 False：h265 分支放弃；真实校验器在末位会放行（见上方用例）
    assert mock_v.call_args.kwargs.get("last_resort") is True


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
    class _CountingClient:
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
    assert cls2.get_calls == 1


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
    # 排除平台连带失效 h265-FLV → HLS 切换：h265 FLV 无法 copy 录制、HLS 又被排除
    # 剔除 → 与关闭 HLS 采集同义，本轮无可用候选返回 None
    with (
        patch.object(main, "hls_collection_enabled", True),
        patch.object(main, "hls_collection_exclude_platforms", ["斗鱼直播"]),
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
