# WP-B（docs/worklog/CODE_REVIEW_2026-09-29_2.md 的 M-1 / M-2）网络出站层回归锁。
#
# M-1 src/async_http.py：探针与 async_req 全线 follow_redirects=True，而内网/保留目标判定原先只作用于
#     **初始 URL**（MIN-2219 只堵了直连形态）。被攻陷/被 MITM 的平台可先回一个过得了校验的公网地址、
#     再 302 到 http://127.0.0.1:6379/ 或 http://169.254.169.254/，探针照样访问内网并把跳转后响应的
#     status_code / content-type 写进 debug 日志。现由 _build_client 给每支 AsyncClient 挂 response
#     事件钩子，逐跳复检 response.url（判定仍走 _internal_stream_target_reason，不复制第二份规则）。
# M-2 src/sync_http.py：sync_req 原先没有 scheme 白名单（async 侧早就有），而 urllib 默认 opener 注册着
#     FileHandler，于是 sync_req("file:///etc/passwd") 把本地文件当响应体返回。现入口过
#     utils.is_safe_http_url、两支 opener 按 http/https 白名单显式构造，abroad 分支补落地地址复核。
#
# 打桩边界：只替换网络层与 DNS seam——httpx 用 MockTransport 造重定向链、urllib 的读盘入口只做
# 观测（原样调用真实实现）。协议判定、内网判定、逐跳钩子、opener 的 handler 集合一律走真实代码。

import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from urllib.response import addinfourl

import httpx
import pytest
from loguru import logger

import src.async_http as async_http
import src.sync_http as sync_http
from src import web_config

# 与 tests/test_async_http.py / tests/test_regression_net.py 同一个 DNS seam：
# 起探针会按「本机解析结果」给直连目标定罪，用例必须与该 seam 隔离，否则无 DNS 环境下「公网源可达」
# 类用例会随机转红。内网目标一律写成 IP 字面量——判定不依赖解析，也就不受本桩影响。
_PUBLIC_IP = "93.184.216.34"
# 代理环境变量键（大小写各一份，与 tests/test_proxy.py 的 _PROXY_ENV_KEYS 同族写法）
_PROXY_ENV_KEYS = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")


@pytest.fixture(autouse=True)
def _hermetic_net(monkeypatch: pytest.MonkeyPatch) -> None:
    # ① DNS 钉成公网 IP。② NO_PROXY=* 而不只是逐个 delenv：httpx 的 get_environment_proxies() 走
    #    urllib.request.getproxies()，Windows 上 env 为空时会**回落到注册表**读系统代理；代理一旦挂进
    #    client._mounts，_transport_for_url 就不走 _transport，MockTransport 被静默绕过（纯假绿）。
    #    NO_PROXY=* 让 env 结果非空且 httpx 直接返回空代理表；逐个 delenv 同样保留。
    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_IP])
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NO_PROXY", "*")


def _capture_logs() -> tuple[list[str], int]:
    # 返回 (日志行, handler id)；调用方必须 logger.remove(handler_id)（同 net 回归文件的口径）。
    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    return lines, handler_id


def _install_mock_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> list[str]:
    # 返回「实际发出的请求 URL 列表」（按跳顺序）。钩子是 _build_client 挂上去的，所以客户端必须由
    # **真实的 _build_client** 造出来，只把最底层 transport 换成 MockTransport——有人删掉 event_hooks
    # 那一行，本文件 M-1 的用例必须全部变红（自建 AsyncClient 会把被测接线一起绕过，等于假绿）。
    seen: list[str] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    real_build = async_http._build_client

    def _build(proxy_addr: str | None, timeout: int, verify: bool, http2: bool) -> httpx.AsyncClient:
        client = real_build(proxy_addr, timeout, verify, http2)
        # typeshed 未声明、也无公开 setter。传了 proxy 时 httpx 会把代理传输装进 _mounts，
        # _transport_for_url 就不走 _transport；本文件只验判定链，故清空 mounts 让每跳落 MockTransport。
        client._mounts = {}
        client._transport = httpx.MockTransport(_record)
        return client

    monkeypatch.setattr(async_http, "_build_client", _build)
    return seen


def _redirect_chain(landing_target: str, *, after_landing: str = "") -> Callable[[httpx.Request], httpx.Response]:
    # 只造 httpx 的「3xx + Location」这一条行为，不做任何内网/协议判定（判定必须走生产代码）。
    # after_landing 用来验证「命中即停止跟随」：被拒之后绝不应再有下一跳。
    def _handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "edge.example.com":
            return httpx.Response(302, headers={"location": landing_target})
        if after_landing and request.url.host == "127.0.0.1":
            return httpx.Response(302, headers={"location": after_landing})
        # 落地跳回 200：没有逐跳防线时探针会据此判「可达」，回归因此可见
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="PONG")

    return _handler


class TestM1RedirectHopGuard:
    # M-1：逐跳复检（探针与 async_req 共用同一支钩子、同一个判定函数）.

    @pytest.mark.parametrize(
        "internal_target",
        [
            "http://127.0.0.1:6379/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5/live.m3u8",
            "http://192.168.1.7/live.m3u8",
            "http://100.64.0.1/live.m3u8",
            "http://[::1]:6379/",
        ],
    )
    async def test_redirect_landing_on_internal_is_unreachable(
        self, internal_target: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 核心回归：初始 URL 是公网（过得了入口判定与 MIN-2219），跳转后落在内网/保留目标
        # → 必须判**不可达**，而不是拿该跳的 200 当结论。
        seen = _install_mock_transport(monkeypatch, _redirect_chain(internal_target))
        assert await async_http.get_response_status("https://edge.example.com/live.m3u8") is False
        assert seen == ["https://edge.example.com/live.m3u8", internal_target]

    async def test_rejected_hop_stops_the_redirect_chain(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「命中即停止跟随」：被拒的那一跳之后不得再发第三跳，否则探针就成了 3xx 链上的跳板。
        seen = _install_mock_transport(
            monkeypatch,
            _redirect_chain("http://127.0.0.1:6379/", after_landing="https://after.example.com/x.m3u8"),
        )
        assert await async_http.get_response_status("https://edge.example.com/live.m3u8") is False
        assert "https://after.example.com/x.m3u8" not in seen, "被拒之后仍继续跟随重定向"

    async def test_hop_rejection_logs_warning_with_masked_landing_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 逐跳命中是**安全判定**，必须与 MIN-2219 初始地址同级别（warning）留线索，不能沉进「这个
        # CDN 节点不通」那条 debug；同时落地 URL 里的凭据必须被抹掉——httpx 把 Location 的 user:pass
        # 原样带进 response.url，而 logs 会轮转保留多份（＝凭据长期落盘）。
        lines, handler_id = _capture_logs()
        try:
            _install_mock_transport(monkeypatch, _redirect_chain("http://probe:s3cret@127.0.0.1:6379/"))
            assert await async_http.get_response_status("https://edge.example.com/live.m3u8") is False
        finally:
            logger.remove(handler_id)
        security_lines = [line for line in lines if "拒绝内网/保留目标" in line]
        assert len(security_lines) == 1, f"逐跳命中未按 warning 级安全判定落日志：{lines}"
        assert "WARNING" in security_lines[0]
        assert "重定向逐跳复检命中" in security_lines[0]
        assert "s3cret" not in security_lines[0], "落地 URL 的凭据进了日志"
        # 该跳响应的 content-type 不得作为「校验未通过」的细节被回显（内网端口观测口本体）
        assert not [line for line in lines if "text/plain" in line]

    async def test_public_to_public_redirect_still_reachable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁（防「顺手把重定向全禁」的退化）：公网→公网的合法链路必须照旧判可达，
        # 且确实走完了两跳——把逐跳判定写成「任何重定向都拒」也会让本用例变红。
        def _handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith("https://start.example.com"):
                return httpx.Response(302, headers={"location": "https://final.example.com/live.m3u8"})
            return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"})

        seen = _install_mock_transport(monkeypatch, _handler)
        assert await async_http.get_response_status("https://start.example.com/live.m3u8") is True
        assert seen == ["https://start.example.com/live.m3u8", "https://final.example.com/live.m3u8"]

    async def test_async_req_redirect_to_internal_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 同一支钩子也必须覆盖 async_req（M-1 里「各分支同样全线跟随重定向」那半）。
        # 返回契约不变：与网络异常同一条失败出口（空串），调用方按「本轮没拿到数据」处理。
        seen = _install_mock_transport(monkeypatch, _redirect_chain("http://127.0.0.1:6379/"))
        assert await async_http.async_req("https://edge.example.com/api") == ""
        assert seen == ["https://edge.example.com/api", "http://127.0.0.1:6379/"]

    async def test_async_req_post_branch_is_covered_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # POST(json=) 分支同样 follow_redirects=True。判定只有一处定义点、四条分支共用一支
        # 客户端 → 不必在每个分支各挂一次；漏挂的分支会安静地把内网响应当成业务数据返回。
        seen = _install_mock_transport(monkeypatch, _redirect_chain("http://169.254.169.254/"))
        assert await async_http.async_req("https://edge.example.com/gql", json_data={"a": 1}) == ""
        assert seen[-1] == "http://169.254.169.254/"

    async def test_stateful_client_carries_the_guard_as_well(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # return_cookies=True 走 _acquire_client 的独占分支（每次自建、不进缓存），那条分支同样调
        # _build_client → 钩子必须在。漏掉它等于给登录/取 token 路径留一个无人看守的重定向面。
        seen = _install_mock_transport(monkeypatch, _redirect_chain("http://127.0.0.1:6379/"))
        assert await async_http.async_req("https://edge.example.com/login", return_cookies=True) == {}
        assert seen[-1] == "http://127.0.0.1:6379/"

    async def test_guard_is_installed_on_every_built_client(self) -> None:
        # 接线点结构锁：钩子出自 _build_client（探针与 async_req 唯一的客户端来源）。这条与既有
        # 「单次选源复用 / 不做模块级全局 client 缓存 / 不关 keepalive / _get_client_lock 随循环重建」
        # 等约束互不冲突——只钉「每支构造出来的客户端都带着一个 response 钩子」。
        client = async_http._build_client(None, 10, True, False)
        try:
            assert len(client.event_hooks["response"]) == 1
            # request 钩子刻意不挂：本层逐跳复检口径是 response.url（见 _build_hop_guard 的残余风险
            # 登记）。多挂一支 request 钩子 = 每跳两次判定/两次 getaddrinfo，未取。
            assert client.event_hooks["request"] == []
        finally:
            await client.aclose()

    async def test_proxied_chain_still_judges_ip_literal_landing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 经代理出站时域名不按本机 DNS 定罪（MIN-2219 的既有豁免，逐跳复检必须继承，否则会把
        # 「境外域名本机被污染、代理却能解析」的合法流误杀）；但落地是 IP 字面量时两种情况都判。
        dns_calls: list[str] = []

        def _record_dns(host: str) -> list[str]:
            dns_calls.append(host)
            return [_PUBLIC_IP]

        monkeypatch.setattr(web_config, "_resolve_host_ips", _record_dns)
        seen = _install_mock_transport(monkeypatch, _redirect_chain("http://127.0.0.1:6379/"))
        assert (
            await async_http.get_response_status("https://edge.example.com/live.m3u8", proxy="http://127.0.0.1:1")
            is False
        )
        assert seen[-1] == "http://127.0.0.1:6379/"
        # 豁免仍然成立：公网域名那一跳没有按本机解析定罪（初始终址与中间跳都不查 DNS）
        assert dns_calls == []


def _file_url_of(tmp_path: Path) -> str:
    # 写一个真文件并把它的 file:// URI 交出去：断言「没读盘」必须作用在真实路径上，
    # 拿一个假路径当输入会让 FileHandler 因 OSError 失败、用例假绿。
    secret = tmp_path / "secret.txt"
    secret.write_text("TOPSECRET-CONTENT", encoding="utf-8")
    return secret.as_uri()


def _spy_file_handler_reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # 观测 urllib 的读盘入口（FileHandler.file_open，3.14 里它就是 open_local_file），**原样调用真实
    # 实现**、只登记被请求的路径：防线被摘掉时这里会记下真实路径、用例立刻变红。
    opened: list[str] = []
    real_file_open = urllib.request.FileHandler.file_open

    def _spy(self: urllib.request.FileHandler, req: urllib.request.Request) -> addinfourl:
        opened.append(req.full_url)
        return real_file_open(self, req)

    monkeypatch.setattr(urllib.request.FileHandler, "file_open", _spy)
    return opened


class TestM2SchemeWhitelistOnSyncReq:
    # M-2：sync_req 的 scheme 白名单.

    def test_file_uri_rejected_and_never_opened(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        file_url = _file_url_of(tmp_path)
        opened = _spy_file_handler_reads(monkeypatch)
        assert sync_http.sync_req(file_url) == ""
        assert opened == [], f"file:// 仍被读到磁盘: {opened}"

    def test_abroad_branch_also_rejects_file_uri(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # abroad=True 用的是 urllib.request.urlopen（进程全局默认 opener，仍带 FileHandler），
        # 入口白名单必须在它之前生效——否则「海外请求」这条分支就是白名单的绕道口。
        file_url = _file_url_of(tmp_path)
        opened = _spy_file_handler_reads(monkeypatch)
        # 替身只记录、不抛错：sync_req 的外层 except 会把任何异常吞成空串，side_effect 抛错
        # 反而会让「白名单被摘掉」的形态照样绿（假绿本体）。断言落在「有没有被调用」上。
        urlopen_spy = MagicMock()
        monkeypatch.setattr(sync_http.urllib.request, "urlopen", urlopen_spy)
        assert sync_http.sync_req(file_url, abroad=True) == ""
        assert opened == []
        urlopen_spy.assert_not_called()

    def test_entry_guard_runs_before_any_handler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 守卫顺序锁：把 opener 整个换成「什么都返回 200 + 文件内容」的替身，模拟「handler 白名单被
        # 摘掉」的形态。此时唯一还在起作用的防线就是入口 scheme 白名单。
        fake_resp = MagicMock()
        fake_resp.headers = {"Content-Encoding": ""}
        fake_resp.read.return_value = b"TOPSECRET-CONTENT"
        fake_resp.url = "file:///etc/passwd"
        opener_spy = MagicMock()
        opener_spy.open.return_value = fake_resp
        monkeypatch.setattr(sync_http, "_get_opener", lambda ssl_verify=None: opener_spy)
        assert sync_http.sync_req("file:///etc/passwd") == ""
        opener_spy.open.assert_not_called()

    def test_proxied_branch_rejects_before_touching_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 代理分支（requests.Session）同样受入口白名单保护：requests 自己虽然不会读文件，
        # 但「先建会话再报错」会让 InvalidSchema 被外层吞成空串，归因线索彻底消失。
        session_spy = MagicMock()
        monkeypatch.setattr(sync_http, "_session", lambda: session_spy)
        assert sync_http.sync_req("file:///etc/passwd", proxy_addr="127.0.0.1:7890") == ""
        session_spy.get.assert_not_called()
        session_spy.post.assert_not_called()

    def test_rejection_log_masks_credentials(self) -> None:
        # 拒绝路径的日志口径与 async 侧一致：URL 与异常文本都过 mask_credentials
        # （sync_req 外层 except 会对 {e} 再过一次，这里是双层脱敏的第一层）。
        lines, handler_id = _capture_logs()
        try:
            assert sync_http.sync_req("file://probe:s3cret@127.0.0.1/etc/passwd") == ""
        finally:
            logger.remove(handler_id)
        joined = "\n".join(lines)
        assert "s3cret" not in joined
        assert "file://***@127.0.0.1" in joined

    def test_normal_http_url_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：白名单不得把正常的 http/https 请求一起挡掉（否则 M-2 就成了新的漏录根因）。
        fake_resp = MagicMock()
        fake_resp.headers = {"Content-Encoding": ""}
        fake_resp.read.return_value = b"body"
        fake_resp.url = "https://api.example.com/live"
        opener_spy = MagicMock()
        opener_spy.open.return_value = fake_resp
        monkeypatch.setattr(sync_http, "_get_opener", lambda ssl_verify=None: opener_spy)
        assert sync_http.sync_req("https://api.example.com/live") == "body"
        opener_spy.open.assert_called_once()


class TestM2OpenerHandlerWhitelist:
    # M-2：两支预构建 opener 的 handler 集合（直接检查构造结果）.

    _ALLOWED_HANDLER_NAMES = {
        # 白名单外协议的统一拒绝口，必须保留（摘掉它 urllib 改抛别的形态，失败语义会漂移）
        "UnknownHandler",
        "HTTPHandler",
        "HTTPSHandler",
        "HTTPDefaultErrorHandler",
        # S-09：裸 HTTPRedirectHandler 换成带逐跳复核的子类——重定向落地地址原先只
        # 在 abroad 分支被事后核对，直连/代理两条路径可以直接 302 到 127.0.0.1 / 169.254.169.254。
        # 这里钉的是子类名：换成裸 HTTPRedirectHandler 即等于摘掉逐跳闸门，本锁当场变红。
        "_HopGuardRedirectHandler",
        "HTTPErrorProcessor",
        # 注意 ProxyHandler({})「不出现在 handlers 里」不是遗漏：CPython 的 OpenerDirector.add_handler
        # 只登记「贡献了某条协议方法链」的 handler，而空代理表的 ProxyHandler 只有 proxy_open（被当作
        # coincidental match 跳过）。[历史注] 旧写法 build_opener(no_proxy_handler) 同样是这个形态——正因没有
        # 任何 proxy handler 被登记，本地请求才不走系统代理。
    }

    @pytest.mark.parametrize("factory", [lambda: sync_http._opener_secure, sync_http._get_insecure_opener])
    def test_non_http_handlers_are_absent(self, factory: Callable[[], urllib.request.OpenerDirector]) -> None:
        # typeshed 没声明 OpenerDirector.handlers（运行时确有）→ 按同目录既有口径用 cast 收窄，
        # 不用三参 getattr（返回 Any|None，后面的 isinstance 过滤会一起失去检查）。
        handlers = cast("list[Any]", getattr(factory(), "handlers"))
        for banned in (urllib.request.FileHandler, urllib.request.FTPHandler, urllib.request.DataHandler):
            assert not any(isinstance(h, banned) for h in handlers), f"opener 上仍挂着 {banned.__name__}"
        assert {type(h).__name__ for h in handlers} == self._ALLOWED_HANDLER_NAMES

    def test_file_ftp_data_urls_refused_before_reading(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 行为锁（不只是「集合里没有」）：真实的 _opener_secure 遇到 file/ftp/data 必须抛
        # URLError('unknown url type')，一步都不读。跨 scheme 跳转走的正是这条同一入口。
        opened = _spy_file_handler_reads(monkeypatch)
        file_url = _file_url_of(tmp_path)
        for url in (file_url, "ftp://example.com/pub/x", "data:text/plain;base64,AAAA"):
            with pytest.raises(urllib.error.URLError) as excinfo:
                sync_http._opener_secure.open(url)
            assert "unknown url type" in str(excinfo.value.reason)
        assert opened == [], f"file:// 仍被读到磁盘: {opened}"

    def test_abroad_landing_on_file_url_is_discarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # abroad 分支的落地复核（该分支唯一可用的防线）：替身 urlopen 模拟「默认 opener 已经把
        # /etc/passwd 读回来了」的形态，sync_req 必须在把响应体交给调用方之前丢掉它，并关掉句柄。
        resp = MagicMock()
        resp.url = "file:///etc/passwd"
        resp.headers = {"Content-Encoding": ""}
        resp.read.return_value = b"root:x:0:0"
        monkeypatch.setattr(sync_http.urllib.request, "urlopen", MagicMock(return_value=resp))
        assert sync_http.sync_req("http://start.example.com/x", abroad=True) == ""
        resp.read.assert_not_called()
        resp.close.assert_called_once()

    def test_abroad_landing_on_http_url_still_returns_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：落地复核只针对非白名单协议，公网→公网（含 http→https）照旧返回响应体。
        resp = MagicMock()
        resp.url = "https://final.example.com/x"
        resp.headers = {"Content-Encoding": ""}
        resp.read.return_value = b"ok"
        monkeypatch.setattr(sync_http.urllib.request, "urlopen", MagicMock(return_value=resp))
        assert sync_http.sync_req("http://start.example.com/x", abroad=True) == "ok"
