# WP-J（2026-09-30，方案 1-A）同步流地址探针的内网收口回归锁。
#
# 背景（上一轮 M-1 在同步侧的补齐）：逐跳重定向复检当时只接在 src/async_http.py 的 _build_client
# 单点上，而 src/stream_select.py 的同步探针自建两支 httpx.Client（_validate_stream_url 的 owns_client
# 分支、select_source_url 的整轮共用分支），两处都 follow_redirects=True 却都不经 _build_client。
# 更前面的缺口是：同步侧连**初始 URL** 的内网/回环/云元数据判定都没有——internal_stream_target_reason
# 此前唯一的调用点是 async_http.get_response_status；stream_select 只有 _is_recordable_url 的协议
# **形态**白名单（挡 file:///concat:，挡不住 http://127.0.0.1:6379）。于是一个被劫持/被 MITM 的平台
# 接口回传内网地址，同步探针就照着去连，并把该跳的 status_code / content-type 回显进轮转日志
# （= 稳定的内网端口观测口，MIN-2219 的跳转形态）。
#
# 打桩边界（AGENTS「测试不得自实现被测逻辑（假绿）」）：只替换两处——
#   ① 传输层：httpx.MockTransport 造 3xx 链并登记实际发出的请求（判定链、钩子、退避、content-type
#      启发式、末位放行一律走真实生产代码）；
#   ② DNS seam：web_config._resolve_host_ips（src/async_http.py 的 _internal_stream_target_reason
#      注释里写明的唯一打桩口径，同 tests/test_regression_2026_09_29_wp_b_netguard.py 与
#      tests/test_regression_2026_09_22_net.py）。
# 本文件不重写任何内网判定规则；内网目标一律写成 IP 字面量，判定不依赖解析、不受本桩影响。
# 变异验证（摘掉生产实现，对应用例应变红）逐条做过：① 初始判定 ② 逐跳钩子 ③ 末位/退避不放行
# ④ _confirm_get_ok 与 _probe_hls_segment 的 except RedirectHopRejected: raise ⑤ _accept_source 的
# 落地复核，实跑读数见交付报告。

import ast
import inspect
import types
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, TypeGuard

import httpx
import pytest
from loguru import logger

import main  # noqa: F401  先完整初始化 main，打破 stream_select<->main 的循环导入
import src.stream_select as ss
from src import web_config

_STREAM_SELECT_PATH = Path(__file__).resolve().parent.parent / "src" / "stream_select.py"

# 与 tests/test_regression_2026_09_29_wp_b_netguard.py 同一个公网解析结果（示例 IP，只作 DNS seam
# 的返回值，不参与任何判定规则）。
_PUBLIC_IP = "93.184.216.34"
_M3U8_START = "https://edge.example.com/live.m3u8"
_FLV_START = "https://edge.example.com/live.flv"
_INTERNAL_M3U8 = "http://127.0.0.1:6379/live.m3u8"
_AFTER_LANDING = "https://after.example.com/x.m3u8"
_PROXY = "http://127.0.0.1:1"

# 各类内网/保留落点：回环、云元数据、RFC1918、链路本地、CGNAT、IPv6 回环，外加缩写 IPv4 的两种写法
# （127.1 的 inet_aton 形态与 2130706433 的十进制形态——它们同样不经解析）。
_INTERNAL_TARGETS = (
    _INTERNAL_M3U8,
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.5/live.m3u8",
    "http://192.168.1.7/live.m3u8",
    "http://100.64.0.1/live.m3u8",
    "http://[::1]:6379/live.m3u8",
    "http://127.1/live.m3u8",
    "http://2130706433/live.m3u8",
)

# 在 patch 生效前先存一份真构造器引用：ss.httpx 就是 httpx 本体，桩内再写 httpx.Client(...)
# 等于调用桩自己、直接递归（同 tests/test_stream_select.py 的 _REAL_SYNC_CLIENT 说明）。
_REAL_SYNC_CLIENT = httpx.Client


@pytest.fixture(autouse=True)
def _hermetic_probe_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # ① 探针节流与 CDN 退避都是模块级全局状态：逐用例清空，否则同 host 的第二个用例会真的 sleep、
    #    或命中上一条用例留下的退避条目（跨用例假失败）。
    # ② DNS seam 钉成公网 IP：生产判定对**非字面量**主机名要解析，无外网环境会 NXDOMAIN →
    #    「主机名无法解析」→ 反向锁用例（公网判可达）随机转红，且把「本机有没有 DNS」当成了被测行为。
    #    内网类断言一律用 IP 字面量，不经过这条 seam。
    monkeypatch.setattr(ss, "_throttle_probe", lambda _url: None)
    ss._probe_last_seen.clear()
    with ss._probe_backoff_lock:
        ss._probe_backoff.clear()
    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_IP])
    yield
    ss._probe_last_seen.clear()
    with ss._probe_backoff_lock:
        ss._probe_backoff.clear()


@pytest.fixture
def no_recheck_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    # 「隔 _recheck_delay() 重试一次再定罪」的用例用：只把间隔归零，重试语义完全保留。
    # 沿既有口径（tests/test_stream_select.py 用 patch("src.stream_select.time") 达到同样效果），
    # 这里收窄到单个属性，避免替换整个 time 模块波及全进程。
    monkeypatch.setattr(ss, "_recheck_delay", lambda: 0.0)


def _stub_dns(monkeypatch: pytest.MonkeyPatch, ips: list[str]) -> list[str]:
    # 把 DNS seam 换成「记录被查过的主机名 + 返回固定结果」的桩：代理豁免类用例要断言
    # 「有代理时一次都不查本机 DNS」（MIN-2219 的既有豁免必须被初始判定与逐跳钩子双双继承）。
    looked_up: list[str] = []

    def _resolve(host: str) -> list[str]:
        looked_up.append(host)
        return ips

    monkeypatch.setattr(web_config, "_resolve_host_ips", _resolve)
    return looked_up


def _capture_logs(level: str = "WARNING") -> tuple[list[str], int]:
    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level=level)
    return lines, handler_id


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[str]:
    # 返回「实际发出的请求 URL 列表」（按跳顺序，含被拒的那一跳）。
    # 为什么绕这一圈而不是在用例里自建客户端：钩子是 _probe_client 挂上去的，所以客户端必须由
    # **真实的 _probe_client** 造出来、只把最底层 transport 换成 MockTransport——有人删掉
    # event_hooks 那一行、或把某一处改回裸 httpx.Client(...)，本文件的逐跳用例必须全部变红
    # （自建客户端会把被测接线一起绕过，等于假绿）。
    seen: list[str] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    def _factory(*args: Any, **kwargs: Any) -> httpx.Client:
        client = _REAL_SYNC_CLIENT(*args, **kwargs)
        # typeshed 未声明、也无公开 setter（httpx 只允许构造期注入 transport，而 _probe_client 不接受
        # 该参数）。传了 proxy 时 httpx 会把代理传输装进 _mounts，_transport_for_url 就不走
        # _transport；本文件只验判定链，代理装配属 httpx 自身职责，清空 mounts 让每一跳都落到
        # MockTransport 上（同 tests/test_regression_2026_09_29_wp_b_netguard.py 的同名 helper）。
        client._mounts = {}
        client._transport = httpx.MockTransport(_record)
        return client

    # R1（tests/test_test_hygiene.py 的「禁改 stdlib/第三方模块本体」）不允许下面这种写法：
    # ss.httpx 就是全进程唯一的 httpx 模块对象，setattr 它的 Client 等于改 httpx.Client 本体，
    # 窗口内**任何别处**新建的 Client 都会拿到替身。改成 AGENTS 规定的 shim 形态——只替换
    # 被测模块命名空间里的 httpx 全局引用，真实 httpx 模块逐字不动，用例结束由 monkeypatch 还原。
    httpx_shim = types.SimpleNamespace(**vars(httpx))
    httpx_shim.Client = _factory
    monkeypatch.setattr(ss, "httpx", httpx_shim)
    return seen


def _redirect_handler(
    landing: str,
    *,
    landing_content_type: str = "application/vnd.apple.mpegurl",
    after_landing: str = "",
) -> Callable[[httpx.Request], httpx.Response]:
    # 只造 httpx 的「3xx + Location」与「200 + 流媒体 content-type」两条行为，不做任何内网/协议判定
    # （判定必须走生产代码）。落地跳刻意回 200 + 可播内容类型 + 正文：防线被摘掉时探针据此判「可达」，
    # 回归因此可见。
    def _handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(landing):
            if after_landing:
                return httpx.Response(302, headers={"location": after_landing})
            return httpx.Response(200, headers={"content-type": landing_content_type}, text="INTERNAL-PORT-CANARY")
        return httpx.Response(302, headers={"location": landing})

    return _handler


def _ok_handler(
    content_type: str = "video/x-flv",
    playlist_text: str = "",
) -> Callable[[httpx.Request], httpx.Response]:
    # 无反向场景用的「什么都通」handler：.m3u8 回播放列表正文，其余回流媒体 content-type。
    # 非 http(s) 协议一律抛 httpx.UnsupportedProtocol——真实 HTTPTransport 就是这么拒的
    # （MockTransport 本身不判协议，不照搬就会把 rtmp 用例测成「服务端答了 rtmp」的假形态）。
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.scheme not in ("http", "https"):
            raise httpx.UnsupportedProtocol(f"Request URL is in an unsupported protocol '{request.url.scheme}:'")
        if str(request.url).endswith(".m3u8"):
            return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"}, text=playlist_text)
        return httpx.Response(200, headers={"content-type": content_type}, text="OK")

    return _handler


class TestInitialUrlInternalTargetRejected:
    # ① 初始 URL 直指内网/回环/云元数据/缩写 IP：必须拒掉，且一个请求都不发。

    @pytest.mark.parametrize("internal_url", _INTERNAL_TARGETS)
    def test_internal_initial_url_rejected_and_no_request_sent(
        self, internal_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _install_mock_transport(monkeypatch, _ok_handler("application/vnd.apple.mpegurl"))
        assert ss._validate_stream_url(internal_url) is False
        assert seen == [], f"内网初始地址仍被探针发出: {seen}"

    @pytest.mark.parametrize("internal_url", _INTERNAL_TARGETS)
    def test_internal_initial_url_rejected_even_as_last_resort(
        self, internal_url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 末位候选的放行语义边界是「网络 / CDN 拒绝」（MID-19），内网目标不属此类：放行等于把
        # ffmpeg -i 指向回环/元数据端点。摘掉判定、或把命中后的 return False 并进末位放行，即红。
        seen = _install_mock_transport(monkeypatch, _ok_handler("application/vnd.apple.mpegurl"))
        assert ss._validate_stream_url(internal_url, last_resort=True) is False
        assert seen == []

    def test_internal_initial_url_rejected_before_backoff_release(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 退避 + 末位的组合原本会**无条件放行**给 ffmpeg（省 CDN 连接预算）。内网判定必须排在
        # _probe_in_backoff 之前，否则一条退避记录就把整条防线旁路掉。把判定挪到其后即红。
        seen = _install_mock_transport(monkeypatch, _ok_handler("application/vnd.apple.mpegurl"))
        ss._mark_probe_reject(_INTERNAL_M3U8, "虎牙直播")
        assert ss._probe_in_backoff(_INTERNAL_M3U8, "虎牙直播") is True
        assert ss._validate_stream_url(_INTERNAL_M3U8, platform="虎牙直播", last_resort=True) is False
        assert seen == []

    def test_rejection_is_warning_with_masked_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 安全判定必须 warning（不能沉进「这个 CDN 节点不通」的降级口径），且签名/鉴权串不得落盘
        # ——logs 轮转保留多份，凭据等于长期落盘。
        lines, handler_id = _capture_logs()
        try:
            _install_mock_transport(monkeypatch, _ok_handler())
            assert ss._validate_stream_url("http://127.0.0.1:6379/live.m3u8?wsAuth=SECRET-TOKEN") is False
        finally:
            logger.remove(handler_id)
        security_lines = [line for line in lines if "拒绝内网/保留目标" in line]
        assert len(security_lines) == 1, f"内网定罪未按 warning 级安全判定留痕: {lines}"
        assert "WARNING" in security_lines[0]
        assert "SECRET-TOKEN" not in security_lines[0], "签名/鉴权串必须脱敏"
        assert "***" in security_lines[0]

    def test_public_initial_url_still_probed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁（防「把判定写成一律拒绝」的退化）：公网初始地址照常发出探针并判可达
        # （HEAD 通过 → _confirm_get_ok 的 GET 复核，两跳都在 seen 里）。
        seen = _install_mock_transport(monkeypatch, _ok_handler())
        assert ss._validate_stream_url(_FLV_START) is True
        assert seen == [_FLV_START, _FLV_START]

    def test_rtmp_candidate_is_not_blocked_by_the_internal_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 初始判定用 internal_stream_target_reason 而**不是**带 scheme 白名单的
        # redirect_hop_rejection_reason：本模块的候选允许 rtmp/rtmps（MID-19 / _ALLOWED_STREAM_SCHEMES，
        # 斗鱼 rtmp 拼接、部分海外平台仍下发 rtmp），协议形态由 _is_recordable_url 把关。
        # 把初始判定写成「非 http(s) 即拒」会整体误杀 rtmp 候选——本条就是那条退化的见证。
        _install_mock_transport(monkeypatch, _ok_handler())
        rtmp = "rtmp://dylive.rtmp.douyucdn.cn/live/100rT.flv?wsAuth=1"
        assert ss._is_recordable_url(rtmp) is True
        assert ss.select_source_url({"flv_url": rtmp, "record_url": ""}) == rtmp


class TestRedirectHopRecheck:
    # ② 逐跳复检：公网初始地址 302 落到内网/保留目标必须判不可达，且该跳证据不得回流结论。

    @pytest.mark.parametrize("internal_target", _INTERNAL_TARGETS)
    def test_public_to_internal_redirect_is_unreachable(
        self, internal_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = _install_mock_transport(monkeypatch, _redirect_handler(internal_target))
        assert ss._validate_stream_url(_M3U8_START) is False
        assert seen == [_M3U8_START, internal_target]

    @pytest.mark.parametrize("internal_target", _INTERNAL_TARGETS)
    def test_public_to_internal_redirect_unreachable_even_as_last_resort(
        self, internal_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 末位候选同样不得因「探针异常」被放行——这正是钩子必须接进 except 链的意义
        # （见 tests/test_hop_guard_wiring_locks.py 的 AST 顺序锁）。
        seen = _install_mock_transport(monkeypatch, _redirect_handler(internal_target))
        assert ss._validate_stream_url(_M3U8_START, last_resort=True) is False
        assert seen == [_M3U8_START, internal_target]

    def test_rejected_hop_does_not_become_evidence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 落地跳刻意回 200 + video/mp2t + 金丝雀正文：没有逐跳防线时探针据此判「可达」，并把该跳的
        # status_code / content-type 写进 debug 日志（MIN-2219 的内网端口观测口本体）。
        lines, handler_id = _capture_logs(level="DEBUG")
        try:
            seen = _install_mock_transport(
                monkeypatch, _redirect_handler(_INTERNAL_M3U8, landing_content_type="video/mp2t")
            )
            assert ss._validate_stream_url(_M3U8_START) is False
        finally:
            logger.remove(handler_id)
        assert seen == [_M3U8_START, _INTERNAL_M3U8]
        joined = "\n".join(lines)
        assert "INTERNAL-PORT-CANARY" not in joined, "被拒那一跳的响应体不得回流"
        assert "video/mp2t" not in joined, "被拒那一跳的 content-type 不得作为校验细节被回显"

    def test_rejected_hop_stops_the_redirect_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 命中即停止跟随：被拒之后不得再发第三跳，否则探针就成了 3xx 链上的跳板。
        seen = _install_mock_transport(monkeypatch, _redirect_handler(_INTERNAL_M3U8, after_landing=_AFTER_LANDING))
        assert ss._validate_stream_url(_M3U8_START) is False
        assert seen == [_M3U8_START, _INTERNAL_M3U8], "被拒之后仍继续跟随重定向"

    def test_flv_get_recheck_hop_rejection_is_not_swallowed(
        self, monkeypatch: pytest.MonkeyPatch, no_recheck_sleep: None
    ) -> None:
        # _confirm_get_ok 的 except 语义是「异常（超时等）不推翻 HEAD 结论」，末位还直接 return True。
        # 内部控制流异常一旦被那条分支吞掉，就变成「公网 HEAD 通过 → 302 落在内网 → 探针判可用」。
        # 摘掉 _confirm_get_ok 里的 except RedirectHopRejected: raise 即红。
        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if request.method == "HEAD":
                return httpx.Response(200, headers={"content-type": "video/x-flv"})
            if url.startswith(_INTERNAL_M3U8):
                return httpx.Response(200, headers={"content-type": "video/x-flv"}, text="INTERNAL-PORT-CANARY")
            return httpx.Response(302, headers={"location": _INTERNAL_M3U8})

        seen = _install_mock_transport(monkeypatch, _handler)
        assert ss._validate_stream_url(_FLV_START, last_resort=True) is False
        # 三跳：HEAD 公网(200 video) → GET 复核(公网 302) → GET 落地内网（钩子在此命中）
        assert seen == [_FLV_START, _FLV_START, _INTERNAL_M3U8]

    def test_hls_playlist_get_hop_rejection_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # _probe_hls_segment 的**外层** except 口径同样是「解析异常 → 按列表可达处理」：
        # 播放列表 GET 自己 302 落到内网时必须原样上抛，否则列表层这条兜底就把内网地址判成可达。
        # 摘掉外层那条 except RedirectHopRejected: raise 即红（与分片层那条各自有锁）。
        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            playlist_body = "#EXTINF:4,\nsegment-0.ts\n"
            if request.method == "HEAD":
                return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})
            if url.startswith(_INTERNAL_M3U8):
                return httpx.Response(
                    200, headers={"content-type": "application/vnd.apple.mpegurl"}, text=playlist_body
                )
            return httpx.Response(302, headers={"location": _INTERNAL_M3U8})

        seen = _install_mock_transport(monkeypatch, _handler)
        assert ss._validate_stream_url(_M3U8_START, last_resort=True) is False
        # 三跳：HEAD 列表(200) → GET 列表(302) → GET 落地内网（钩子在此命中）
        assert seen == [_M3U8_START, _M3U8_START, _INTERNAL_M3U8]

    def test_hls_segment_hop_rejection_is_not_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 播放列表 200、分片 302 落到内网：_probe_hls_segment 内层 except 的口径是「探测异常 → 按列表
        # 可达处理」（2026-09-13 斗鱼 hw 事故定下的保守兜底），内部控制流异常必须原样上抛，否则这条
        # 兜底就把内网地址判成可用、末位还放行。摘掉那条 raise 即红。
        def _handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if request.method == "HEAD":
                return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})
            if url.startswith(_INTERNAL_M3U8):
                return httpx.Response(200, headers={"content-type": "video/mp2t"}, text="INTERNAL-PORT-CANARY")
            if url.endswith(".ts"):
                return httpx.Response(302, headers={"location": _INTERNAL_M3U8})
            return httpx.Response(
                200,
                headers={"content-type": "application/vnd.apple.mpegurl"},
                text="#EXTINF:4,\nsegment-0.ts\n",
            )

        seen = _install_mock_transport(monkeypatch, _handler)
        assert ss._validate_stream_url(_M3U8_START, last_resort=True) is False
        assert _INTERNAL_M3U8 in seen

    def test_public_to_public_redirect_still_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁（防「顺手把重定向一律禁掉」的退化）：公网→公网的合法链路必须照旧判可达——真实 CDN
        # （斗鱼 hw 鉴权跳转、虎牙 al 线路跳转）全走这条路，误杀即整轮放弃录制。
        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "start.example.com":
                return httpx.Response(302, headers={"location": "https://final.example.com/live.flv"})
            return httpx.Response(200, headers={"content-type": "video/x-flv"}, text="OK")

        seen = _install_mock_transport(monkeypatch, _handler)
        assert ss._validate_stream_url("https://start.example.com/live.flv") is True
        assert "https://final.example.com/live.flv" in seen


class TestProxyExemptionIsInherited:
    # ④ 带代理时沿用「不按本机 DNS 定罪」的既有豁免（MIN-2219），代理房间的行为不得改变。

    def test_proxied_domain_chain_never_consults_local_dns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 初始判定与逐跳钩子都必须继承豁免：域名不按本机解析结果定罪（境外域名本机被污染/查不到、
        # 代理却能解析的合法流不能被误杀——AGENTS「探针误杀可用源」反复强调的形态）。
        dns_calls = _stub_dns(monkeypatch, [_PUBLIC_IP])

        def _handler(request: httpx.Request) -> httpx.Response:
            if request.url.host == "start.example.com":
                return httpx.Response(302, headers={"location": "https://final.example.com/live.flv"})
            return httpx.Response(200, headers={"content-type": "video/x-flv"}, text="OK")

        seen = _install_mock_transport(monkeypatch, _handler)
        assert ss._validate_stream_url("https://start.example.com/live.flv", proxy_addr=_PROXY) is True
        assert "https://final.example.com/live.flv" in seen
        assert dns_calls == [], f"有代理时仍按本机 DNS 定罪（豁免未被继承）: {dns_calls}"

    def test_proxied_ip_literal_landing_still_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 但 IP 字面量两种情况都判——http 代理按绝对 URI 转发，回环/元数据经代理照样可达。
        dns_calls = _stub_dns(monkeypatch, [_PUBLIC_IP])
        seen = _install_mock_transport(monkeypatch, _redirect_handler(_INTERNAL_M3U8))
        assert ss._validate_stream_url(_M3U8_START, proxy_addr=_PROXY) is False
        assert seen == [_M3U8_START, _INTERNAL_M3U8]
        assert dns_calls == []

    def test_proxied_domain_that_resolves_private_is_not_convicted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 豁免的正向形态：域名解析到私网时，**有代理**必须放行给探针（真正建连的是代理侧）。
        # 把豁免写反（有代理也定罪）即红。
        _stub_dns(monkeypatch, ["10.0.0.5"])
        seen = _install_mock_transport(monkeypatch, _ok_handler())
        assert ss._validate_stream_url("https://cdn.example.com/live.flv", proxy_addr=_PROXY) is True
        assert seen == ["https://cdn.example.com/live.flv", "https://cdn.example.com/live.flv"]

    def test_without_proxy_domain_resolving_private_is_convicted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 同一 DNS 结果、无代理 → 本机解析=即将连接的地址 → 必须定罪且一个请求都不发。
        # 与上一条互为反向锁，钉住「豁免只豁免代理路径」。
        _stub_dns(monkeypatch, ["10.0.0.5"])
        seen = _install_mock_transport(monkeypatch, _ok_handler())
        assert ss._validate_stream_url("https://cdn.example.com/live.flv") is False
        assert seen == []


class TestSourceUrlHandoff:
    # ⑤ 交付 ffmpeg 前的落地复核：探针层判定挡不住「与本轮已探候选同址 → 复用结论并交由 ffmpeg」
    #    那条**零探针**分支。

    def test_internal_record_url_on_reuse_path_is_not_returned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _install_mock_transport(monkeypatch, _ok_handler("application/vnd.apple.mpegurl"))
        monkeypatch.setattr(main, "hls_collection_enabled", True)
        monkeypatch.setattr(main, "hls_collection_exclude_platforms", ())
        # record_url 与序列候选逐字相同 → 走 probed 复用分支（MID-18），一次探针都不发
        result = ss.select_source_url(
            {"m3u8_url": _INTERNAL_M3U8, "flv_url": "", "record_url": _INTERNAL_M3U8}, None, "斗鱼直播"
        )
        assert result is None, "内网 record_url 经「复用结论」分支被交给 ffmpeg -i"

    def test_public_selection_still_returns_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：落地复核不得把正常公网地址一起拒掉（否则这条防线自己就成了新的漏录根因）。
        _install_mock_transport(monkeypatch, _ok_handler())
        result = ss.select_source_url({"m3u8_url": "", "flv_url": _FLV_START, "record_url": ""})
        assert result == _FLV_START

    def test_no_internal_url_survives_the_round(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 收束断言：一轮选源里只要地址是内网，任何分支都不得返回非 None。
        _install_mock_transport(monkeypatch, _redirect_handler(_INTERNAL_M3U8))
        monkeypatch.setattr(main, "hls_collection_enabled", True)
        monkeypatch.setattr(main, "hls_collection_exclude_platforms", ())
        assert ss.select_source_url({"m3u8_url": _M3U8_START, "flv_url": _FLV_START, "record_url": ""}) is None


class TestProbeClientShape:
    # 工厂本身的形态：只加钩子，不改复用/keepalive/参数组合（AGENTS「HTTP 客户端复用与连接管理」）。

    def test_probe_client_builds_client_with_one_sync_response_hook(self) -> None:
        client = ss._probe_client(5, None, True)
        try:
            assert len(client.event_hooks["response"]) == 1
            # request 钩子刻意不挂：本层逐跳复检口径是 response.url（见 async_http._build_hop_guard 的
            # 残余风险登记）。多挂一支 request 钩子 = 每跳两次判定/两次 getaddrinfo，未取。
            assert client.event_hooks["request"] == []
            guard = client.event_hooks["response"][0]
            # 「为什么必须是两个工厂而不是一个」的行为见证：同步 Client 走裸 hook(response)，
            # 钩子若是协程函数则判定永不生效（返回的协程从未被 await，还会甩 RuntimeWarning）。
            assert not inspect.iscoroutinefunction(guard)
        finally:
            client.close()

    def test_sync_hook_rejects_internal_landing_when_invoked_directly(self) -> None:
        # 钩子语义锁：同步钩子被**直接调用**（不经 httpx）时也必须抛内部控制流异常。
        # 与上一条合起来钉住「同步形态工厂」而不是「异步形态被塞进来」——后者在这里表现为
        # 返回协程、不抛异常。钩子看的是 response.url，而 httpx 里它就是**发出这一跳的那个请求**
        # 的 URL（302 的 Location 由 httpx 变成下一跳的请求），故构造 request 时用落地地址。
        import src.async_http as async_http

        guard = async_http.build_sync_hop_guard(None)
        internal_response = httpx.Response(
            200, headers={"content-type": "video/mp2t"}, request=httpx.Request("GET", _INTERNAL_M3U8)
        )
        with pytest.raises(async_http.RedirectHopRejected):
            guard(internal_response)
        # 公网落地必须放行（反向锁，防「任何重定向都拒」把真实 CDN 整片误杀）
        public_response = httpx.Response(
            200,
            headers={"content-type": "video/x-flv"},
            request=httpx.Request("GET", "https://final.example.com/live.flv"),
        )
        assert guard(public_response) is None

    def test_async_guard_factory_still_returns_coroutine(self) -> None:
        # 两侧形态互不替换的最后一道锁：异步工厂仍返回协程函数（改成普通函数会让 AsyncClient
        # 的 `await hook(response)` 当场 TypeError）。
        import src.async_http as async_http

        assert inspect.iscoroutinefunction(async_http._build_hop_guard(None))


def _descendants(node: ast.AST) -> Iterator[ast.AST]:
    # 含嵌套函数在内的全部后代（与 tests/test_stream_select.py 的 _scope_nodes 相反，
    # 这里刻意要下沉——落地闸门 _accept_source 就是 select_source_url 内的嵌套函数）。
    for child in ast.iter_child_nodes(node):
        yield child
        yield from _descendants(child)


def _is_httpx_client_call(node: ast.AST) -> TypeGuard[ast.Call]:
    # 返回 TypeGuard 而非 bool：取到 .keywords 的结构锁需要 ast.Call 收窄，写 bool 会逼每个
    # 调用点各补一遍 isinstance（判据多出一份可漂移形态）。与 tests/test_stream_select.py 同口径。
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Client"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "httpx"
    )


def _is_probe_client_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_probe_client"


def _enclosing_functions(tree: ast.AST) -> dict[int, str]:
    # 返回 {id(node): 最内层所属函数名}——「只接一处」的漏接形态靠这个归属关系现形。
    owners: dict[int, str] = {}

    def _visit(node: ast.AST, current: str) -> None:
        for child in ast.iter_child_nodes(node):
            name = child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else current
            owners[id(child)] = name
            _visit(child, name)

    _visit(tree, "<module>")
    return owners


def _local_nodes(func: ast.FunctionDef) -> list[ast.AST]:
    # 函数体内、不进入嵌套函数定义（与 _scope_nodes 同口径，避免嵌套函数里的调用被算到外层）。
    out: list[ast.AST] = []
    stack: list[ast.AST] = [func]
    while stack:
        node = stack.pop()
        out.append(node)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            stack.append(child)
    return out


def _named_defs(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _hop_handler_linenos(func: ast.FunctionDef) -> tuple[list[int], list[int]]:
    # 返回该函数内 (except RedirectHopRejected 的行号, except Exception 的行号)。
    # PEP 758 的 `except A, B:` 是 ast.Tuple、`except X as e:` 的 except 类型仍是 ast.Name，
    # 故只看 ast.Name 形态即可（本仓宽 except 一律写 except Exception as e）。
    hop: list[int] = []
    broad: list[int] = []
    for node in _descendants(func):
        if not isinstance(node, ast.ExceptHandler) or not isinstance(node.type, ast.Name):
            continue
        if node.type.id == "RedirectHopRejected":
            hop.append(node.lineno)
        elif node.type.id == "Exception":
            broad.append(node.lineno)
    return hop, broad


class TestHopGuardWiringLocks:
    # ⑥ 结构锁（AST，不依赖执行）：两处自建 client 都挂了钩子、都过了初始判定、内部控制流异常
    #    在每个吞异常的出口之前放行。防后来者只接一处。

    def test_single_httpx_client_construction_inside_probe_client(self) -> None:
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        owners = _enclosing_functions(tree)
        constructions = [n for n in ast.walk(tree) if _is_httpx_client_call(n)]
        assert len(constructions) == 1, (
            f"本模块的 httpx.Client 构造必须收敛为 _probe_client 内唯一一处，实扫到 "
            f"{[owners.get(id(n), '?') for n in constructions]}"
        )
        assert owners.get(id(constructions[0])) == "_probe_client"

    def test_construction_passes_sync_hop_guard_hook(self) -> None:
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        call = next(n for n in ast.walk(tree) if _is_httpx_client_call(n))
        hook_kw = next((kw for kw in call.keywords if kw.arg == "event_hooks"), None)
        assert hook_kw is not None, "_probe_client 没把 event_hooks 交给 httpx.Client（逐跳复检静默失效）"
        dumped = ast.dump(hook_kw.value)
        assert "build_sync_hop_guard" in dumped, "response 钩子必须出自 async_http 的同步工厂（判定只有一个事实源）"
        assert "redirect_hop_rejection_reason" in ast.dump(tree) or "internal_stream_target_reason" in ast.dump(tree)

    def test_probe_client_is_called_from_both_probe_sites(self) -> None:
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        owners = _enclosing_functions(tree)
        sites = {owners.get(id(n), "<module>") for n in ast.walk(tree) if _is_probe_client_call(n)}
        assert sites == {
            "_validate_stream_url",
            "select_source_url",
        }, f"两处自建探针客户端必须都出自工厂（只接一处即本锁变红），实到: {sorted(sites)}"

    def test_factory_and_judgement_use_function_level_import_only(self) -> None:
        # 导入环约束：stream_select 有模块级 import main、main 又 from src.stream_select import ...，
        # 模块级出边会改变各模块的初始化顺序（依据见 src/async_http.py:518-521 的同名说明）。
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        assert not any(
            isinstance(n, (ast.Import, ast.ImportFrom))
            and ("async_http" in getattr(n, "module", "") or any("async_http" in a.name for a in n.names))
            for n in tree.body
        ), "src/stream_select.py 不得模块级 import src.async_http（本仓存在 stream_select↔main 导入环）"
        defs = _named_defs(tree)
        for name in (
            "_probe_client",
            "_validate_stream_url",
            "select_source_url",
            "_confirm_get_ok",
            "_probe_hls_segment",
        ):
            imported = [
                a.name
                for n in _descendants(defs[name])
                if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("async_http")
                for a in n.names
            ]
            assert imported, f"{name} 缺函数内 import（沿 async_http.py:518 的同一手法）"

    def test_hop_rejection_is_reraised_before_every_probe_swallowing_except(self) -> None:
        # 内部控制流异常一旦被 except Exception 吞掉，就落进「维持 HEAD 结论 / 按列表可达 / 退避放行」
        # 这些既有兜底——那几条分支会把内网落地判成可用甚至交给 ffmpeg。Python 按顺序匹配处理器，
        # 所以「存在」不够，必须**在前**。
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        defs = _named_defs(tree)
        for name in ("_confirm_get_ok", "_probe_hls_segment"):
            hop, broad = _hop_handler_linenos(defs[name])
            assert len(hop) == len(broad), f"{name}: 每条吞异常的 except Exception 都要配一条在前的 RedirectHopRejected"
            for hop_line, broad_line in zip(sorted(hop), sorted(broad)):
                assert (
                    hop_line < broad_line
                ), f"{name}: except RedirectHopRejected 写在 except Exception 之后（永不命中）"
        hop, broad = _hop_handler_linenos(defs["_validate_stream_url"])
        assert hop and broad, "_validate_stream_url 缺少 RedirectHopRejected / Exception 出口"
        assert min(hop) < min(broad), "_validate_stream_url: 内网落地异常被宽 except 抢先吞掉"

    def test_internal_gate_precedes_first_emit(self) -> None:
        # 「构造之后、发第一个请求之前」的初始判定，钉成行序判据：判定早于本作用域内第一次探针发出。
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        defs = _named_defs(tree)
        targets = {
            "_validate_stream_url": ("head",),
            "select_source_url": ("_validate_stream_url",),
        }
        for name, emit_names in targets.items():
            func = defs[name]
            # 判定调用允许落在嵌套函数里（select_source_url 的落地闸门就在 _accept_source 内），
            # 但发出点只算本作用域（嵌套函数的调用属另一个作用域的行序关系）
            judged = [
                n.lineno
                for n in _descendants(func)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in ("internal_stream_target_reason", "redirect_hop_rejection_reason")
            ]
            assert judged, f"{name}: 没有初始 URL 内网判定调用"
            emitted: list[int] = []
            for n in _local_nodes(func):
                if not isinstance(n, ast.Call):
                    continue
                if isinstance(n.func, ast.Attribute) and n.func.attr in emit_names:
                    emitted.append(n.lineno)
                elif isinstance(n.func, ast.Name) and n.func.id in emit_names:
                    emitted.append(n.lineno)
            assert emitted, f"{name}: 找不到探针发出点 {emit_names}，判据失效"
            assert min(judged) < min(emitted), f"{name}: 内网判定排在探针之后（被拒地址已经发出去了）"

    def test_accept_source_has_the_landing_gate(self) -> None:
        # 交付 ffmpeg 前的落地复核（_accept_source 内的第二道判定）——probed 复用分支零探针，
        # 只有这道闸门挡得住。摘掉它，tests 的 TestSourceUrlHandoff 与本条 AST 锁同时变红。
        tree = ast.parse(_STREAM_SELECT_PATH.read_text(encoding="utf-8-sig"))
        accept = _named_defs(tree)["_accept_source"]
        judged = [
            n.lineno
            for n in _descendants(accept)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id in ("internal_stream_target_reason", "redirect_hop_rejection_reason")
        ]
        assert judged, "select_source_url 的 _accept_source 没有落地复核（内网地址可经复用分支进 ffmpeg -i）"
        form_gate = [
            n.lineno
            for n in _descendants(accept)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_is_recordable_url"
        ]
        assert form_gate, "_accept_source 的形态白名单被删（两者管的东西不同，都要在）"

    def test_async_hop_guard_comment_no_longer_claims_sync_side_is_unwired(self) -> None:
        # 「更正考古」锁：async_http._build_hop_guard 里那条「同步探针侧仍未接线、属另一个文件的改动
        # 范围、不在这里顺手改」已被本次接线证伪——按 AGENTS 的例外条款，须改正原文并留一条带日期的
        # 历史注。这条锁防的是「代码接了、注释仍说不接线」的下一次会话误信形态。
        source = Path(__file__).resolve().parent.parent.joinpath("src", "async_http.py").read_text(encoding="utf-8")
        assert "build_sync_hop_guard" in source, "同步形态钩子工厂必须存在（判定只有一个事实源）"
        assert "不在这里顺手改" not in source, "证伪的「不在本次范围」陈述必须改正原文"
        assert "[历史注 2026-09-30" in source, "改正必须带日期的历史注"
