# 2026-09-22/23 网络与代理层回归锁（MID-2233 / MIN-2216~2222）。
#
# 覆盖面（每条都对应一个「实测确认未修」的条目）：src/proxy.py 的 MID-2233 ①②③④；
# src/ttwid.py 的 MIN-2220（ttwid 跨出口串用）/ MIN-2222（空异常文本）；src/async_http.py 的
# MIN-2216(async 侧) / MIN-2217 / MIN-2218 / MIN-2219 / MIN-2221。
#
# 打桩边界：只替换网络层与依赖构造（httpx 客户端 / _build_client / DNS seam / winreg），判定逻辑
# （分桶缓存、内网定罪、warn-once、锁重入）一律走真实代码。每条锁都做过「删掉生产实现就该失败」
# 的变异验证。
import asyncio
import gc
import pathlib
import socket
import sys
import threading
import types
from typing import Any

import httpx
import pytest
from loguru import logger

import src.async_http as async_http
import src.ttwid as ttwid_module
from src import web_config
from src.async_http import _client_cache, _client_cache_lock, _close_all_clients, async_req, get_response_status
from src.cookie_cache import clear as clear_cookie_cache
from src.proxy import ProxyDetector, ProxyInfo

# ---------------------------------------------------------------------------
# 公共设施
# ---------------------------------------------------------------------------

# 与 tests/conftest.py 的 _clean_credential_caches 同一 seam：ttwid 的下层 cookie 缓存
# 会跨用例残留，涉及 ttwid 的用例统一清一遍，使本文件不依赖执行顺序。
_PUBLIC_IP = "93.184.216.34"


def _capture_logs(level: str = "DEBUG") -> tuple[list[str], int]:
    # 返回 (收集到的日志行, handler id)；调用方必须 logger.remove(handler_id)。
    lines: list[str] = []
    handler_id = logger.add(lambda message: lines.append(str(message)), level=level)
    return lines, handler_id


@pytest.fixture()
def _stub_dns_public(monkeypatch: pytest.MonkeyPatch) -> None:
    # MIN-2219 的 DNS seam（web_config._resolve_host_ips 的注释明确它是为用例留的口子）：
    # 把「域名解析结果」钉成一个公网 IP，使直连判定不依赖真实 DNS/网络。
    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_PUBLIC_IP])


@pytest.fixture()
def _clean_ttwid(monkeypatch: pytest.MonkeyPatch) -> None:
    # 分桶缓存与镜像成对重置。conftest 只清镜像（_cached_ttwid），这里再清桶并把
    # 「配置里的 ttwid」置空——否则开发者本机填过 ttwid 时 get_ttwid 会短路走配置分支。
    monkeypatch.setattr(ttwid_module, "_cached_ttwid", "")
    monkeypatch.setattr(ttwid_module, "_cached_ttwid_at", 0.0)
    monkeypatch.setattr(ttwid_module, "_cached_ttwid_by_proxy", {})
    monkeypatch.setattr(ttwid_module, "_ttwid_scopes", set())
    monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "")
    clear_cookie_cache()


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, fetch: Any) -> None:
    # 只打桩「真实拉取」这一层，get_ttwid 的快路/分桶逻辑仍走真实代码。
    monkeypatch.setattr(ttwid_module, "_fetch_ttwid", fetch)


class _FakeClient:
    # httpx.AsyncClient 的最小替身：只暴露缓存/关闭路径用到的成员。
    # 用真 AsyncClient 会把「是否跨循环 await」变成时序竞态，而本文件断言的是调用次数。
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False
        self.aclose_calls = 0

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def aclose(self) -> None:
        self.aclose_calls += 1
        self.closed = True


class _StubResponse:
    def __init__(self, text: str = "", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.url = "https://final.example.com/x"
        self.headers: dict[str, str] = {}
        self.cookies = _StubCookies()


class _StubCookies:
    def items(self) -> list[tuple[str, str]]:
        return []


class RecordingClient:
    # 只记录参数、不发网络：断言「传给 httpx 的关键字」，不重实现 httpx 的行为。
    def __init__(self, status_code: int = 200, text: str = "ok") -> None:
        self.post_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.head_calls: list[dict[str, Any]] = []
        self._status_code = status_code
        self._text = text
        self.is_closed = False
        self._error: BaseException | None = None

    def fail_with(self, exc: BaseException) -> "RecordingClient":
        self._error = exc
        return self

    async def post(self, url: str, **kwargs: Any) -> _StubResponse:
        if self._error is not None:
            raise self._error
        self.post_calls.append(kwargs)
        return _StubResponse(self._text, self._status_code)

    async def get(self, url: str, **kwargs: Any) -> _StubResponse:
        if self._error is not None:
            raise self._error
        self.get_calls.append({"url": url, **kwargs})
        return _StubResponse(self._text, self._status_code)

    async def head(self, url: str, **kwargs: Any) -> _StubResponse:
        if self._error is not None:
            raise self._error
        self.head_calls.append({"url": url, **kwargs})
        return _StubResponse(self._text, self._status_code)

    async def aclose(self) -> None:
        self.is_closed = True


def _client_provider(client: Any) -> Any:
    async def _get(*args: Any, **kwargs: Any) -> Any:
        return client

    return _get


# ---------------------------------------------------------------------------
# MID-2233 ①：ftp_proxy 不得被当成本程序的可用代理
# ---------------------------------------------------------------------------

_PROXY_ENV_KEYS = (
    "http_proxy",
    "HTTP_PROXY",
    "https_proxy",
    "HTTPS_PROXY",
    "ftp_proxy",
    "FTP_PROXY",
    "all_proxy",
    "ALL_PROXY",
)


def _clear_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # 逐个删而不是 patch.dict(os.environ)：后者无论 clear 取值都会整体快照/写回，
    # harness 注入的 MCP 配置一超 Windows 32767 上限就抛 ValueError（AGENTS 硬约定）。
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestMid2233FtpProxy:
    def test_ftp_proxy_only_is_not_a_system_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("ftp_proxy", "http://10.9.9.9:2121")
        detector = ProxyDetector.__new__(ProxyDetector)
        # 判定与取值两个口径必须同时为「无代理」：只修一边会重新出现
        # 「global_proxy=True 但拿不到地址」的假象（本条目的立论形态）
        assert detector._is_proxy_enabled_linux() is False
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port, info.proxy_url) == ("", "", "")

    def test_ftp_proxy_does_not_shadow_http_proxy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("ftp_proxy", "http://10.9.9.9:2121")
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:7890")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("127.0.0.1", "7890")
        assert ProxyDetector.__new__(ProxyDetector)._is_proxy_enabled_linux() is True

    def test_ftp_proxy_not_in_the_read_set_at_all(self) -> None:
        # 结构锁：候选集合里不允许再出现 ftp（改回元组即红，防「注释说不要、代码还留着」）
        assert not any("ftp" in name.lower() for name in ProxyDetector._LINUX_PROXY_ENV_NAMES)


# ---------------------------------------------------------------------------
# MID-2233 ②：代理自身的 scheme 必须保留
# ---------------------------------------------------------------------------


class TestMid2233Scheme:
    def test_all_proxy_socks5_scheme_survives_to_proxy_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("127.0.0.1", "1080")
        assert info.scheme == "socks5"
        # 旧实现恒补 http:// → socks 端口被当 HTTP 代理用，表现为「配了代理全平台异常」
        assert info.proxy_url == "socks5://127.0.0.1:1080"

    def test_socks5h_and_https_schemes_are_recognised(self) -> None:
        assert ProxyDetector._split_scheme("socks5h://u:1") == ("socks5h", "u:1")
        assert ProxyDetector._split_scheme("HTTPS://u:1") == ("https", "u:1")

    def test_credentials_and_scheme_combine(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("all_proxy", "socks5://bob:s3cret@proxy.example.com:1080/")
        info = ProxyDetector._get_proxy_info_linux()
        assert info.proxy_url == "socks5://bob:s3cret@proxy.example.com:1080"
        # 凭据不得随 repr 进轮转日志（本仓凭据红线）
        assert "s3cret" not in repr(info) and "bob" not in repr(info)

    def test_unknown_scheme_is_stripped_not_turned_into_a_protocol(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # "foo://bar" 旧实现剥掉前缀后得 ip="bar"、port="" → 该候选被跳过。新实现若把它当协议、
        # 或原样留着前缀，_split_host_port 会切成 port="//bar" → ProxyInfo 抛 ValueError → 整个系统
        # 代理检测被 main.py 的 except 吞掉，故必须保持「宽容剥掉、继续看下一个变量」。
        scheme, hostport = ProxyDetector._split_scheme("foo://bar")
        assert scheme == "" and hostport == "bar"
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("all_proxy", "foo://bar")
        info = ProxyDetector._get_proxy_info_linux()  # 不得抛
        assert (info.ip, info.port, info.scheme) == ("", "", "")

    def test_scheme_defaults_to_http_when_absent(self) -> None:
        info = ProxyInfo("10.0.0.1", "3128")
        assert info.scheme == ""
        assert info.proxy_url == "http://10.0.0.1:3128"

    def test_linux_bare_value_still_has_no_scheme(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "127.0.0.1:7890")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.scheme, info.proxy_url) == ("", "http://127.0.0.1:7890")


# ---------------------------------------------------------------------------
# MID-2233 ③：裸 IPv6 无端口要真的能通过校验（旧注释承诺过、实现从未兑现）
# ---------------------------------------------------------------------------


class TestMid2233BareIpv6:
    def test_bare_ipv6_without_port_constructs(self) -> None:
        info = ProxyInfo("::1", "")
        assert info.ip == "::1" and info.port == ""
        # proxy_url 必须补方括号，否则 "http://::1" 是非法 authority（下游 InvalidURL）
        assert info.proxy_url == "http://[::1]"

    def test_bracketed_ipv6_without_port_constructs(self) -> None:
        assert ProxyInfo("[::1]", "").proxy_url == "http://[::1]"

    def test_registry_shape_bare_ipv6_end_to_end(self) -> None:
        # MIN-20① 的整块「IPv6 放行分支」此前是死代码：注册表存 "::1" 时
        # _split_host_port 交出 port=""，ProxyInfo 直接 raise。现在该形态可用。
        ip, port, user, password = ProxyDetector._split_host_port("::1")
        info = ProxyInfo(ip, port, user, password)
        assert info.ip == "::1" and info.port == ""
        assert info.proxy_url == "http://[::1]"

    def test_compressed_ipv6_forms_accepted(self) -> None:
        for raw in ("2001:db8::1", "::", "fe80::1%eth0"):
            assert ProxyInfo(raw, "").proxy_url == f"http://[{raw}]"

    def test_ipv4_or_domain_without_port_still_raises(self) -> None:
        # 收窄只针对 IPv6 字面量：IPv4/域名缺端口仍是「填错了一半」，必须报错
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("192.168.1.1", "")
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("proxy.example.com", "")

    def test_port_without_ip_still_raises(self) -> None:
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("", "8080")

    def test_colon_host_that_is_not_ipv6_still_raises(self) -> None:
        # 含冒号但不是合法 IPv6 字面量（"gg:gg"）不得被新分支放过
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("gg:gg", "")

    def test_ipv6_with_port_still_validates_the_port(self) -> None:
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("::1", "abc")


# ---------------------------------------------------------------------------
# MID-2233 ④：ProxyInfo.proxy_url 无生产消费点 —— 登记为残留，不得留「已修」陈述
# ---------------------------------------------------------------------------


class TestMid2233ResidualRegistered:
    def test_module_registers_the_no_consumer_residual(self) -> None:
        # 源码级锁：src/proxy.py 必须显式写明「user/password/scheme/proxy_url 无生产消费点」，
        # 且不得再出现「MIN-20③ 已修好认证代理」这类被证伪的陈述。判据用「必须出现登记语」而非
        # 「必须不出现某个词」，避免误伤历史注。
        text = (pathlib.Path(__file__).resolve().parents[1] / "src" / "proxy.py").read_text(encoding="utf-8")
        assert "没有任何生产消费点" in text, "MID-2233④ 的残留登记被删除：会重新出现「已修」的错误陈述"
        assert "代理地址" in text, "登记里必须写明真正下发的是 config.ini「代理地址」这条独立链路"
        # 主会话接上消费点后应改这条断言（删除登记语即为「已闭合」的信号）
        assert "main.py" in text


# ---------------------------------------------------------------------------
# MIN-2222：异常日志必须带类型名（Windows 下 socket.timeout 的 str() 为空）
# ---------------------------------------------------------------------------


class TestMin2222TypeNameInLogs:
    def test_windows_proxy_error_log_carries_exception_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 注入假 winreg：门禁跑在 Linux，直接 import winreg 会失败；
        # 用 sys.modules 塞替身可让这条 Windows 路径跨平台都验到（不是 skip，避免 CI 无覆盖）。
        boom = socket.timeout()  # str() == '' —— 正是「空白日志尾巴」的真实形态
        fake = types.SimpleNamespace(QueryValueEx=lambda *a, **k: (_ for _ in ()).throw(boom))
        monkeypatch.setitem(sys.modules, "winreg", fake)
        detector = ProxyDetector.__new__(ProxyDetector)
        # 名称改写后的私有属性只能这样赋值：直接写 detector._ProxyDetector__internet_settings
        # 会被 mypy 判「类里没有这个属性」（它确实不在类体里出现，只在方法内被引用）
        setattr(detector, "_ProxyDetector__internet_settings", object())
        lines, handler_id = _capture_logs("DEBUG")
        try:
            assert isinstance(detector._get_proxy_info_windows(), ProxyInfo)
            assert detector._is_proxy_enabled_windows() is False
        finally:
            logger.remove(handler_id)
        # 只看异常分支留下的行：「系统未启用代理」那条 debug 不带异常是正确行为，
        # 对它断言类型名会是假红（也说明观察点选错了）。
        error_lines = [line for line in lines if "读取系统代理时发生错误" in line or "未找到代理信息" in line]
        assert error_lines, "未捕获到异常分支日志，本用例的观察点失效（假绿）"
        for line in error_lines:
            assert "socket.timeout" in line or "TimeoutError" in line, f"缺异常类型名 → 空白告警: {line}"

    @pytest.mark.asyncio
    async def test_ttwid_fetch_failure_logs_type_name(self, _clean_ttwid: None) -> None:
        async def _boom(**kwargs: Any) -> dict[str, str]:
            raise socket.timeout()

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ttwid_module, "_cache_fetch_cookies", _boom)
        try:
            lines, handler_id = _capture_logs("WARNING")
            try:
                assert await ttwid_module._fetch_ttwid() == ""
            finally:
                logger.remove(handler_id)
        finally:
            monkeypatch.undo()
        assert lines, "未捕获到 warning，本用例的观察点失效（假绿）"
        assert "自动获取抖音 ttwid 失败" in lines[0]
        assert "socket.timeout" in lines[0] or "TimeoutError" in lines[0], lines[0]

    def test_warmup_failure_logs_type_name(self) -> None:
        async def _boom(*args: Any, **kwargs: Any) -> str:
            raise socket.timeout()

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ttwid_module, "get_ttwid", _boom)
        try:
            lines, handler_id = _capture_logs("WARNING")
            try:
                ttwid_module.warmup_ttwid()
            finally:
                logger.remove(handler_id)
        finally:
            monkeypatch.undo()
        assert lines and ("socket.timeout" in lines[0] or "TimeoutError" in lines[0]), lines


# ---------------------------------------------------------------------------
# MIN-2220：ttwid 快路必须按出口分列
# ---------------------------------------------------------------------------


class TestMin2220PerProxyCache:
    @pytest.mark.asyncio
    async def test_direct_value_is_not_reused_by_proxied_call(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetched: list[str | None] = []

        async def _fetch(proxy_addr: str | None = None) -> str:
            fetched.append(proxy_addr)
            return f"ttwid=from-{proxy_addr or 'direct'}"

        _patch_fetch(monkeypatch, _fetch)
        assert await ttwid_module.get_ttwid() == "ttwid=from-direct"
        # 旧实现在这里直接返回 _cached_ttwid（直连那份），代理出口永远拿不到自己的值
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=from-http://p:1"
        assert fetched == [None, "http://p:1"]

    @pytest.mark.asyncio
    async def test_proxied_value_is_not_reused_by_direct_call(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 反方向同样必须独立（旧实现「谁先成功谁定调」，两个方向都串）
        n = 0

        async def _fetch(proxy_addr: str | None = None) -> str:
            nonlocal n
            n += 1
            return f"ttwid=v{n}"

        _patch_fetch(monkeypatch, _fetch)
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=v1"
        assert await ttwid_module.get_ttwid() == "ttwid=v2"

    @pytest.mark.asyncio
    async def test_same_proxy_hits_bucket_without_network(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[int] = []

        async def _fetch(proxy_addr: str | None = None) -> str:
            calls.append(1)
            return "ttwid=once"

        _patch_fetch(monkeypatch, _fetch)
        assert await ttwid_module.get_ttwid("socks5://1.2.3.4:1080") == "ttwid=once"
        assert await ttwid_module.get_ttwid("socks5://1.2.3.4:1080") == "ttwid=once"
        assert len(calls) == 1, "同一出口 TTL 内应命中分桶缓存"

    @pytest.mark.asyncio
    async def test_stale_bucket_is_dropped_and_refetched(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # MID-33 的 TTL 判定按出口各算各的：陈旧桶必须被**删除**并向下走，而不是「非空即返回」。
        # 这里只验本层可观察行为（桶被删 + 又填回新时刻），下层 singleflight 的过期联动由
        # tests/test_ttwid.py 既有用例覆盖。
        import time as _time

        calls: list[int] = []

        async def _fetch(proxy_addr: str | None = None) -> str:
            calls.append(1)
            return "ttwid=refreshed"

        _patch_fetch(monkeypatch, _fetch)
        stale_at = _time.monotonic() - ttwid_module._TTWID_TTL_SECONDS - 1
        # 直接构造「桶里有一个过期值」的前置态（_cached_ttwid 镜像由 _clean_ttwid 托管并自动还原）
        ttwid_module._cached_ttwid_by_proxy[""] = ("ttwid=stale", stale_at)
        monkeypatch.setattr(ttwid_module, "_cached_ttwid", "ttwid=stale")
        await ttwid_module.get_ttwid()
        assert ttwid_module._cached_ttwid_by_proxy[""][1] > stale_at, "陈旧桶未被刷新"
        assert len(calls) == 1, f"陈旧桶应向下取一次，实得 {calls}"

    @pytest.mark.asyncio
    async def test_invalidate_clears_every_bucket(self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []

        async def _fetch(proxy_addr: str | None = None) -> str:
            calls.append(1)
            return f"ttwid=v{len(calls)}"

        _patch_fetch(monkeypatch, _fetch)
        assert await ttwid_module.get_ttwid() == "ttwid=v1"
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=v2"
        ttwid_module.invalidate_ttwid()
        # 被拒的是「这支凭据」，各桶可能来自同一次 set-cookie → 整体作废
        assert await ttwid_module.get_ttwid() == "ttwid=v3"
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=v4"

    @pytest.mark.asyncio
    async def test_external_mirror_reset_disables_fast_path(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # tests/conftest.py 的逐用例重置只写 `_cached_ttwid = ""`，不提供清桶的入口。镜像为空必须
        # 能挡住快路，否则上一个用例的桶值会串进下一个用例（跨用例串号）。
        async def _fetch(proxy_addr: str | None = None) -> str:
            return "ttwid=fresh"

        _patch_fetch(monkeypatch, _fetch)
        assert await ttwid_module.get_ttwid() == "ttwid=fresh"
        monkeypatch.setattr(ttwid_module, "_cached_ttwid", "")
        assert ttwid_module._cached_ttwid_by_proxy != {}, "前置条件：桶里确实还留着值"
        assert await ttwid_module.get_ttwid() == "ttwid=fresh"

    @pytest.mark.asyncio
    async def test_fetch_failure_does_not_leak_another_proxies_value(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 旧 _fetch_ttwid 失败时 `return _cached_ttwid`，等于把直连那份递给代理出口——
        # MIN-2220 的另一个入口，快路分桶挡不住它，必须单独锁。
        async def _ok(proxy_addr: str | None = None) -> str:
            return "ttwid=direct-only"

        _patch_fetch(monkeypatch, _ok)
        assert await ttwid_module.get_ttwid() == "ttwid=direct-only"

        async def _fail(proxy_addr: str | None = None) -> str:
            raise socket.timeout()

        _patch_fetch(monkeypatch, _fail)
        assert await ttwid_module.get_ttwid("http://p:1") == ""

    @pytest.mark.asyncio
    async def test_config_ttwid_writes_the_requesting_bucket(
        self, _clean_ttwid: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 用户手填值仍走「配置优先」，但写入要带上本次出口，否则快路读不到、每轮重读配置
        async def _boom(proxy_addr: str | None = None) -> str:
            raise AssertionError("配置优先时不该发网络请求")

        _patch_fetch(monkeypatch, _boom)
        monkeypatch.setattr(ttwid_module, "_read_config_ttwid", lambda: "ttwid=user-set")
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=user-set"
        assert await ttwid_module.get_ttwid("http://p:1") == "ttwid=user-set"
        assert ttwid_module._cached_ttwid_by_proxy["http://p:1"][0] == "ttwid=user-set"


# ---------------------------------------------------------------------------
# MIN-2218：异步 POST 必须跟随重定向；data 与 json 同传必须显式报错
# ---------------------------------------------------------------------------


class TestMin2218PostRedirects:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"data": b"binary"},
            {"data": "raw body"},
            {"data": {"k": "v"}},
            {"json_data": {"k": "v"}},
            {"json_data": [1, 2]},
        ],
    )
    async def test_every_post_shape_follows_redirects(self, kwargs: dict[str, Any]) -> None:
        # 三条 POST 分支（bytes/str、dict|None、只传 json_data）都必须带 follow_redirects
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            assert await async_req("https://api.example.com", **kwargs) == "ok"
        finally:
            monkeypatch.undo()
        assert client.post_calls, "POST 未发生，用例前提不成立"
        for call in client.post_calls:
            assert call.get("follow_redirects") is True, f"POST 分支缺 follow_redirects: {call}"

    @pytest.mark.asyncio
    async def test_get_shape_still_follows_redirects(self) -> None:
        # GET 分支原本就有，别在补 POST 时把它改掉
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            await async_req("https://api.example.com")
        finally:
            monkeypatch.undo()
        assert client.get_calls and client.get_calls[0].get("follow_redirects") is True

    @pytest.mark.asyncio
    async def test_data_and_json_together_is_a_hard_error(self) -> None:
        # 同传在 httpx 下是「content 赢、json 被静默丢弃」（实测 body 就是传入的 bytes），
        # 故必须显式拒绝；且**不能**被 async_req 的 except 吞成空串——那是网络故障的契约。
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            with pytest.raises(ValueError, match="json_data"):
                await async_req("https://api.example.com", data="body", json_data={"a": 1})
        finally:
            monkeypatch.undo()
        assert client.post_calls == [], "同传必须在发请求之前就被拦下"


# ---------------------------------------------------------------------------
# MIN-2216（async 侧）：缺依赖不得伪装成「200 + 空响应体 = 疑似风控」
# ---------------------------------------------------------------------------


class TestMin2216DependencyMissing:
    @pytest.mark.asyncio
    async def test_missing_h2_warns_once_with_install_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # httpx 0.28.1 实测：AsyncClient(http2=True) 在构造期抛 ImportError（不是 RuntimeError）
        err = ImportError(
            "Using http2=True, but the 'h2' package is not installed. "
            "Make sure to install httpx using `pip install httpx[http2]`."
        )

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise err

        monkeypatch.setattr(async_http, "_build_client", _boom)
        monkeypatch.setattr(async_http, "_dep_warned", set())
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        lines, handler_id = _capture_logs("DEBUG")
        try:
            first = await async_req("https://live.douyin.com/123")
            second = await async_req("https://live.douyin.com/123")
        finally:
            logger.remove(handler_id)
        assert first == "" and second == "", "返回契约不变（调用方按空响应处理）"
        hits = [line for line in lines if "缺少可选依赖" in line]
        assert len(hits) == 1, f"必须 warn-once，实得 {len(hits)} 条: {hits}"
        assert "h2" in hits[0] and "pip install httpx[http2]" in hits[0], hits[0]
        assert any("已告警过" in line for line in lines), "第二条应降级为 debug 而非静默丢弃"

    @pytest.mark.asyncio
    async def test_missing_socksio_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        err = ImportError("Using SOCKS proxy, but the 'socksio' package is not installed.")

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise err

        monkeypatch.setattr(async_http, "_build_client", _boom)
        monkeypatch.setattr(async_http, "_dep_warned", set())
        lines, handler_id = _capture_logs("WARNING")
        try:
            result = await async_req("https://www.tiktok.com/@x", return_cookies=True, include_cookies=True)
        finally:
            logger.remove(handler_id)
        # return_cookies 形态的失败契约是 ("", {})，不能被新分支改坏
        assert result == ("", {})
        assert lines and "socksio" in lines[0] and "httpx[socks]" in lines[0], lines

    @pytest.mark.asyncio
    async def test_module_not_found_is_also_a_dependency_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        err = ModuleNotFoundError("No module named 'h2'")
        err.name = "h2"

        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise err

        monkeypatch.setattr(async_http, "_build_client", _boom)
        monkeypatch.setattr(async_http, "_dep_warned", set())
        lines, handler_id = _capture_logs("WARNING")
        try:
            assert await async_req("https://example.com") == ""
        finally:
            logger.remove(handler_id)
        assert lines and "h2" in lines[0], lines

    @pytest.mark.asyncio
    async def test_runtime_error_from_httpx_old_shape_is_covered(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 旧版 httpx 的 h2 检查抛 RuntimeError；本仓把它归同一类（列在 except 元组里）
        def _boom(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("Using http2=True, but the 'h2' package is not installed")

        monkeypatch.setattr(async_http, "_build_client", _boom)
        monkeypatch.setattr(async_http, "_dep_warned", set())
        lines, handler_id = _capture_logs("WARNING")
        try:
            assert await async_req("https://example.com") == ""
        finally:
            logger.remove(handler_id)
        assert lines and "RuntimeError" in lines[0], lines

    @pytest.mark.asyncio
    async def test_ordinary_network_error_stays_debug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：ConnectError 之类不得被新分支提成 warning（否则每轮重试都刷屏）
        client = RecordingClient().fail_with(httpx.ConnectError("connection refused"))
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http, "_dep_warned", set())
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        lines, handler_id = _capture_logs("WARNING")
        try:
            assert await async_req("https://example.com") == ""
        finally:
            logger.remove(handler_id)
        assert lines == [], f"网络异常不应升到 warning: {lines}"

    @pytest.mark.asyncio
    async def test_real_httpx_h2_absence_is_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 端到端：本机 venv 的 h2 处于「dist-info 在、包目录空」的破损态（find_spec 返 None），
        # 故开发机与 CI 都会真的走到新分支。不打桩 _build_client，让真 httpx 自己报错。
        import importlib.util

        spec = importlib.util.find_spec("h2")
        if spec is not None and spec.origin is not None:
            pytest.skip("本机 h2 可用，构造期不会抛缺依赖异常")
        monkeypatch.setattr(async_http, "_dep_warned", set())
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        with _client_cache_guard():
            lines, handler_id = _capture_logs("WARNING")
            try:
                assert await async_req("https://live.douyin.com/123", http2=True) == ""
            finally:
                logger.remove(handler_id)
        assert any("h2" in line for line in lines), f"真实缺包未被新分支捕获: {lines}"


class _client_cache_guard:
    # 用后即清：本用例不 mock 客户端，真 AsyncClient 会进模块级缓存。
    def __enter__(self) -> None:
        with _client_cache_lock:
            _client_cache.clear()

    def __exit__(self, *args: Any) -> None:
        with _client_cache_lock:
            _client_cache.clear()


# ---------------------------------------------------------------------------
# MIN-2217：进程退出清理绝不跨线程/跨循环 await aclose
# ---------------------------------------------------------------------------


class TestMin2217CloseAllClientsOwnership:
    def test_foreign_thread_client_is_only_dropped(self) -> None:
        loop_a = asyncio.new_event_loop()
        ready = threading.Event()
        holder: dict[str, Any] = {}

        def _worker() -> None:
            async def _make() -> Any:
                return await async_http._get_client(None, 10, True, False)

            holder["client"] = loop_a.run_until_complete(_make())
            ready.set()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("httpx.AsyncClient", _FakeClient)
            with _client_cache_lock:
                _client_cache.clear()
            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            assert ready.wait(timeout=15)
            thread.join(timeout=15)
            # 审查 7.11（2026-10-18）：join(timeout=15) 返回不等于线程已退出。本用例后面几条判据读的
            # 是「线程 A 建的那份客户端有没有被主线程 await 关闭」，线程挂死时 holder 里已有值、断言
            # 照样全绿，且 daemon 线程会带着未结束的 run_until_complete 活到进程结束。
            assert not thread.is_alive(), "线程 A 未在 15s 内退出：客户端创建链挂死，不得判绿"
            foreign: _FakeClient = holder["client"]
            assert foreign.aclose_calls == 0, "前置条件：创建时不该顺手关闭"
            try:
                # 主线程收尾：旧实现会无条件 await 线程 A 建的那份连接池
                asyncio.run(_close_all_clients())
            finally:
                with _client_cache_lock:
                    remaining = dict(_client_cache)
                    _client_cache.clear()
            assert remaining == {}, "缓存必须整体清空"
            assert foreign.aclose_calls == 0, "跨线程客户端被 await aclose（2026-09-04 禁止的形态）"
            assert not foreign.closed
        loop_a.close()

    def test_same_thread_same_loop_client_is_closed(self) -> None:
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("httpx.AsyncClient", _FakeClient)
            with _client_cache_lock:
                _client_cache.clear()

            async def _scenario() -> Any:
                client = await async_http._get_client(None, 10, True, False)
                await _close_all_clients()
                return client

            client: _FakeClient = asyncio.run(_scenario())
        assert client.closed and client.aclose_calls == 1
        assert _client_cache == {}

    def test_stale_same_loop_client_is_closed_in_place(self) -> None:
        # 反向确认「同循环同线程」这条淘汰路径仍然生效：缓存里放一支已关闭的旧值，
        # 二次获取必须换实例并 await 旧的那支（这里旧值已被关闭，await 它只是幂等）。
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("httpx.AsyncClient", _FakeClient)
            with _client_cache_lock:
                _client_cache.clear()

            async def _scenario() -> tuple[Any, Any]:
                first = await async_http._get_client(None, 10, True, False)
                await first.aclose()
                second = await async_http._get_client(None, 10, True, False)
                return first, second

            first, second = asyncio.run(_scenario())
        assert first is not second

    def test_no_unraisable_never_awaited_warning(self) -> None:
        # 「改了可能引入告警」这条的取证：捕获 sys.unraisablehook，任何 "was never awaited" /
        # "Task was destroyed" 都算回归（pytest 的 warnings summary 依赖 GC 时机，这里做确定性断言）。
        records: list[Any] = []
        old_hook = sys.unraisablehook
        sys.unraisablehook = records.append
        try:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("httpx.AsyncClient", _FakeClient)
                with _client_cache_lock:
                    _client_cache.clear()

                async def _scenario() -> None:
                    for i in range(3):
                        await async_http._get_client(f"http://p{i}:1", 10, True, False)
                    await _close_all_clients()

                for _ in range(3):
                    asyncio.run(_scenario())
            gc.collect()
        finally:
            sys.unraisablehook = old_hook
        bad = [str(r) for r in records if "never awaited" in str(r) or "Task was destroyed" in str(r)]
        assert bad == [], f"出现未 awaited 协程告警: {bad}"


# ---------------------------------------------------------------------------
# MIN-2221：信号处理器可在临界区内重入本锁
# ---------------------------------------------------------------------------


class TestMin2221LockReentrancy:
    def test_close_all_clients_sync_is_safe_inside_the_lock(self) -> None:
        # 复现「主线程正持有 _client_cache_lock 时收到 SIGINT → safe_exit → close_all_clients_sync
        # 再取同一把锁」：非重入锁下即同线程自死锁（Ctrl+C 后既不退出也不报错）。放独立线程 +
        # join 超时来验，超时即判失败——绝不在主线程死等。
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("httpx.AsyncClient", _FakeClient)
            with _client_cache_lock:
                _client_cache.clear()
            outcome: list[str] = []

            def _run() -> None:
                with _client_cache_lock:
                    async_http.close_all_clients_sync()
                outcome.append("done")

            thread = threading.Thread(target=_run, daemon=True)
            thread.start()
            thread.join(timeout=10)
        assert outcome == ["done"], "同线程重入本锁被阻塞 → MIN-2221 的自死锁形态回归"
        assert not thread.is_alive()


# ---------------------------------------------------------------------------
# MIN-2219：探针不得成为内网端口探测的观测口
# ---------------------------------------------------------------------------


class TestMin2219InternalTargetGuard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:6379/",
            "http://127.0.0.1:22/live.m3u8",
            "http://localhost:8000/x.m3u8",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]:6379/",
            "http://0x7f.0.0.1:6379/",  # inet_aton 缩写形态：同一目标，必须同判
            "http://2130706433:6379/",  # 同一 127.0.0.1 的十进制写法
            "http://10.0.0.5/x.m3u8",  # 私网
            "http://192.168.1.7/x.m3u8",  # 私网
            "http://100.64.0.1/x.m3u8",  # CGNAT
            "http://0.0.0.0:6379/",
            "http://metadata/x",
            "http://foo.internal/x",
        ],
    )
    async def test_internal_targets_rejected_without_any_request(self, url: str, _stub_dns_public: None) -> None:
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            assert await get_response_status(url) is False
        finally:
            monkeypatch.undo()
        assert client.head_calls == [] and client.get_calls == [], f"内网目标仍被探测: {client.head_calls}"

    @pytest.mark.asyncio
    async def test_dns_rebinding_to_loopback_is_rejected_for_direct_probes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 直连时「本机解析结果」就是即将连接的地址，故域名形态也要判（与写入侧同一口径）
        monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: ["127.0.0.1"])
        client = RecordingClient()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(async_http, "_get_client", _client_provider(client))
            mp.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
            assert await get_response_status("https://evil-cdn.example/live.m3u8") is False
        assert client.head_calls == []

    @pytest.mark.asyncio
    async def test_proxied_domain_is_not_judged_by_local_dns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁（本条刻意保留的唯一差异）：走代理时本机解析与落地目标无关。若也按本机 DNS 定罪，
        # 「本机 DNS 被污染/查不到、代理却能解析」的境外流会被整批判不可达——即「探针误杀可用源」。
        monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: ["127.0.0.1"])
        client = RecordingClient()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(async_http, "_get_client", _client_provider(client))
            assert await get_response_status("https://www.tiktok.com/@a", proxy="http://127.0.0.1:7890") is True
        assert len(client.head_calls) == 1

    @pytest.mark.asyncio
    async def test_proxied_ip_literal_is_still_rejected(self) -> None:
        # 经 http 代理时绝对 URI 仍会被转发到回环/元数据，故 IP 字面量不受上面的豁免影响
        client = RecordingClient()
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(async_http, "_get_client", _client_provider(client))
            assert await get_response_status("http://169.254.169.254/x", proxy="http://127.0.0.1:7890") is False
        assert client.head_calls == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url", ["https://hw3.douyucdn2.cn/live/a.m3u8", "https://alicdn.example/x.flv"])
    async def test_public_stream_targets_still_probe_normally(self, url: str, _stub_dns_public: None) -> None:
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        try:
            assert await get_response_status(url) is True
        finally:
            monkeypatch.undo()
        assert len(client.head_calls) == 1

    @pytest.mark.asyncio
    async def test_rejection_is_logged_as_warning_and_masked(self, _stub_dns_public: None) -> None:
        url = "http://127.0.0.1:6379/live.m3u8?wsAuth=SECRET-TOKEN"
        client = RecordingClient()
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(async_http, "_get_client", _client_provider(client))
        monkeypatch.setattr(async_http.utils, "handle_proxy_addr", lambda x: None)
        lines, handler_id = _capture_logs("WARNING")
        try:
            assert await get_response_status(url) is False
        finally:
            # 必须成对撤销：本文件用的是 `pytest.MonkeyPatch()` 手工实例（不是夹具），pytest 不会
            # 自动还原它。漏掉 undo() 时，这里对 `handle_proxy_addr` 的空返回补丁会永久留在进程里——
            # async_http.utils 与 src/sync_http.py 共用同一个 src.utils，同会话后续的 sync_http 代理
            # 用例会拿不到 proxy_addr、静默落到 urllib 直连分支，真的向 example.com 发出未打桩请求。
            monkeypatch.undo()
            logger.remove(handler_id)
        assert lines, "内网定罪属安全判定，必须留 warning（debug 级会被当成普通不可达）"
        joined = "".join(lines)
        assert "SECRET-TOKEN" not in joined, "签名/鉴权串必须脱敏"
        assert "***" in joined

    @pytest.mark.asyncio
    async def test_reuse_of_the_shared_criterion_is_static(self) -> None:
        # 判据必须来自 web_config，不得在 async_http 里另立一份内网规则（口径分叉即缺口）。
        text = (pathlib.Path(__file__).resolve().parents[1] / "src" / "async_http.py").read_text(encoding="utf-8")
        assert "web_config._host_internal_reason" in text
        assert "web_config._parse_ip_literal" in text, "IP 字面量分支也要走同一份判据"
        # 本模块不得自带第二套 ipaddress/网段常量——那才是真的「两处口径不一致」
        assert "import ipaddress" not in text
        assert "169.254" not in text.split("_internal_stream_target_reason")[0], "内网常量不得在本模块另立"
