# -*- encoding: utf-8 -*-
# WP-A / S-1（严重）：Shopee 短链落地页的凭据外泄 + 内网 SSRF 回归锁。
#
# 病史（docs/worklog/CODE_REVIEW_2026-09-29_2.md 的 S-1，与已定稿的小红书 SEV-2214 同型）：
# get_shopee_stream_url 在「非直链且非店铺主页」分支用 async_req(redirect_url=True) 解短链，
# 解出的落地页 URL 由**响应**决定并直接替换 url；随后 host_suffix 由裸字符串切分得出、
# 拼成 api_host=https://live.shopee.{host_suffix}，再对它发三次请求（ongoing / replay_list /
# session），而 headers 里挂着调用方经 [Cookie] shopee_cookie 透传的登录态。
# 于是恶意落地页 https://live.shopee.evil.com 或 https://live.shopee.sg@127.0.0.1/ 两条载荷
# 都能成立：前者把 Cookie 送出外网，后者把请求打进回环/云元数据。
#
# 本文件锁的是**行为**（实际发出去的 URL 与 headers），不是在测试里再实现一遍白名单：
# 网络层用 monkeypatch.setattr 换成打桩 async_req（自动还原，进程内不留桩），
# DNS 那一 seam 用 monkeypatch.setattr 换 web_config._host_internal_reason；
# 而内网/回环/元数据字面量那几条一律走**真实**判据（它们不经 DNS，离线即可定罪）。
#
# 判据分层（与 src/spider.py 的三道闸一一对应）：
#   ① 落地页 host 域族白名单 _shopee_is_allowed_host（含 userinfo/@ 拒绝）；
#   ② 落地页内网判定 web_config._host_internal_reason；
#   ③ 构造结果 api_host 再过一次白名单（校验的是要发出去的那个 host，不是输入）。

import urllib.parse
from typing import Any

import pytest

from src import spider as sp
from src import web_config


def _as_str(value: object) -> str:
    # 替身记下的字段类型是 Any（打桩层的返回值本来就异构），收敛成 str 再比较，
    # 免得断言里出现 NoneType 与 str 的隐式比较。
    return value if isinstance(value, str) else ""


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class _ReqSpy:
    # async_req 的打桩替身：记下每次**实际发出**的 URL 与 headers。
    # headers 存快照副本——被测函数会在判定后就地 pop('Cookie')，
    # 只存引用的话断言看到的是「事后被改过的那份」，抓不到发出去那一刻的内容。

    def __init__(self, landing: str | None = None, body: str = '{"data": null}') -> None:
        self.landing = landing
        self.body = body
        self.sent: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        url = _as_str(kwargs.get("url") or (args[0] if args else ""))
        headers = kwargs.get("headers") or {}
        self.sent.append(
            {
                "url": url,
                "headers": dict(_as_dict(headers)),
                "redirect": bool(kwargs.get("redirect_url")),
            }
        )
        if kwargs.get("redirect_url"):
            return self.landing if self.landing is not None else ""
        return self.body

    @property
    def urls(self) -> list[str]:
        return [_as_str(item["url"]) for item in self.sent]

    def credentialed(self) -> list[dict[str, Any]]:
        return [item for item in self.sent if _as_dict(item["headers"]).get("Cookie")]

    def followups(self) -> list[dict[str, Any]]:
        # 「跳转之后」的那批请求：不带 redirect_url 标志，正是可能外送凭据的 ongoing/replay/session。
        return [item for item in self.sent if not item["redirect"]]


class _LoggerSpy:
    # logger 替身：只按级别收集文本，供「不可信分支必须落 warning」一类断言。
    # 不在这里重做级别分档逻辑，避免把被测代码的告警口径搬进测试。

    def __init__(self) -> None:
        self.msgs: list[tuple[str, str]] = []

    def _record(self, level: str, message: object) -> None:
        self.msgs.append((level, str(message)))

    def debug(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("debug", message)

    def info(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("info", message)

    def success(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("success", message)

    def warning(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("warning", message)

    def error(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("error", message)

    def critical(self, message: object, *args: object, **kwargs: object) -> None:
        self._record("critical", message)

    def messages(self, level: str) -> list[str]:
        return [text for lv, text in self.msgs if lv == level]


# ── 纯函数层：白名单判据本身 ──────────────────────────────────────────────


class TestShopeeHostAllowlistPredicate:
    def test_family_hosts_allowed(self) -> None:
        # 官方站点直链与短链宿主：精确等于与「. 后缀」两种形态都要放行
        assert sp._shopee_is_allowed_host("https://shopee.sg/live/1")
        assert sp._shopee_is_allowed_host("https://live.shopee.co.id/share?session=1")
        assert sp._shopee_is_allowed_host("https://live.shopee.com.my/x")
        assert sp._shopee_is_allowed_host("https://s.shp.ee/abc")

    def test_suffix_spoofing_rejected(self) -> None:
        # 裸 endswith 的漏网形态：evil-shopee.sg / shopee.sg.evil.com / notshopee.sg
        assert not sp._shopee_is_allowed_host("https://evil-shopee.sg/x")
        assert not sp._shopee_is_allowed_host("https://shopee.sg.evil.com/x")
        assert not sp._shopee_is_allowed_host("https://notshopee.sg/x")
        assert not sp._shopee_is_allowed_host("https://shopee.co.id.evil.com/x")

    def test_userinfo_at_form_rejected(self) -> None:
        # S-1 的绕过载荷：urlparse 把 hostname 解成 @ **之后**的那一段（= 真实连接目标），
        # 于是「字面看着像官方域」在这条输入上不成立，含 @ 的 netloc 必须整条拒掉。
        assert not sp._shopee_is_allowed_host("https://live.shopee.sg@127.0.0.1/share?session=1")
        assert not sp._shopee_is_allowed_host("https://live.shopee.sg@169.254.169.254/x")
        assert not sp._shopee_is_allowed_host("https://anything:pw@shopee.sg/x")

    def test_empty_and_malformed_rejected(self) -> None:
        assert not sp._shopee_is_allowed_host("")
        assert not sp._shopee_is_allowed_host("not-a-url")
        assert not sp._shopee_is_allowed_host("https://")
        # 非法 IPv6 字面量让 urlparse 抛 ValueError：必须是「拒」而不是炸
        assert not sp._shopee_is_allowed_host("http://[::1")


class TestShopeeHostSuffixFromHostname:
    # MI-16 / SEV-06 的既有形态必须逐字不变（这四条与 tests/test_spider_fixes.py 的同源断言一致）。
    # 本轮把实现从「按 / 切 authority」换成「urlparse().hostname」——换法本身不许改变正常输入的结果。
    def test_normal_hosts_keep_suffix(self) -> None:
        assert sp._shopee_host_suffix("https://live.shopee.sg/share?from=live&session=802458") == "sg"
        assert sp._shopee_host_suffix("https://live.shopee.co.id/live/123") == "co.id"
        assert sp._shopee_host_suffix("https://live.shopee.com.my/foo") == "com.my"
        assert sp._shopee_host_suffix("https://shopee.co.id/live") == "co.id"

    def test_userinfo_and_port_are_stripped(self) -> None:
        # 旧实现在这里会得到 ":8443" / "user:pass@live.shopee.sg" 这类片段，
        # 拼出的 api_host 与实际连接主机不是同一台（白名单与连接目标错位）。
        assert sp._shopee_host_suffix("https://live.shopee.sg:8443/share?session=1") == "sg"
        assert sp._shopee_host_suffix("https://u:p@live.shopee.co.id/x") == "co.id"

    def test_hostile_host_yields_poisoned_suffix(self) -> None:
        # 这一条是给第三道闸准备的证据链：host_suffix 确实能被投毒成 evil.com，
        # 所以「只看输入」的前两道闸挡不住，必须校验构造结果。
        assert sp._shopee_host_suffix("https://live.shopee.evil.com/share?session=1") == "evil.com"

    def test_malformed_input_falls_back_to_com(self) -> None:
        # 与旧实现的 IndexError 分支同口径（回 "com"），只是触发条件换成 hostname 取不到
        assert sp._shopee_host_suffix("not-a-url") == "com"
        assert sp._shopee_host_suffix("http://[::1") == "com"


# ── 第一道闸：落地页域族白名单 ────────────────────────────────────────────


async def test_landing_outside_family_is_dropped_and_credentials_are_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 失效形态（删掉修复即变红）：短链解出 evil.example.com 后仍用同一份含 Cookie 的 headers
    # 继续请求 → 用户 Shopee 登录态外送。
    # 修复后：跳转被丢弃、保留用户自己填的原始 url；后续请求一律不带 Cookie。
    spy = _ReqSpy(landing="https://evil.example.com/steal?session=88")
    logger = _LoggerSpy()
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)

    result = await sp.get_shopee_stream_url("https://shopee.sg/live/1?session=777", cookies="SHOPEE_SESS=SECRET")

    assert result["is_live"] is False
    # ① 绝不允许对 evil.example.com 发任何请求（无论带不带凭据）
    assert not any("evil.example.com" in u for u in spy.urls), spy.urls
    # ② 保留原始地址：后续请求按**原始** host 拼出的 api_host 发出，而不是按响应指定的 host
    followups = spy.followups()
    assert followups, f"跳转被丢弃后应仍按原始地址继续解析: {spy.sent}"
    assert _as_str(followups[0]["url"]).startswith("https://live.shopee.sg/")
    assert "/api/v1/session/777" in _as_str(followups[0]["url"])
    # ③ 后续请求不带 Cookie；而**第一个**请求（对用户自填短链宿主的跳转探测）仍带 Cookie——
    #    原请求的 host 是用户自己填的，剥它只会把可用房间变成不可用（与小红书同口径）。
    assert all(item["redirect"] for item in spy.credentialed()), spy.sent
    assert "Cookie" not in _as_dict(followups[0]["headers"])
    assert _as_dict(spy.sent[0]["headers"]).get("Cookie") == "SHOPEE_SESS=SECRET"
    # ④ 不可信分支必须留 warning，且落日志的 URL 已过脱敏
    warnings = logger.messages("warning")
    assert any("Shopee" in m and "非白名单主机" in m for m in warnings), warnings


async def test_internal_ip_literal_landings_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # 内网/回环/链路本地（云元数据）落地页：一律被拒，既发不出请求、也不带凭据。
    # 这四条 host 不在 Shopee 域族内，由**第一道闸**当场定罪；第二道闸（真实内网判据）
    # 对「族内域名解析到内网」的形态单独见 test_allowlisted_landing_that_resolves_internal_is_rejected。
    # 这里刻意不打桩 web_config 的任何东西——保持真实判据在场。
    originals = (
        "http://127.0.0.1:8080/share?session=1",
        "http://169.254.169.254/latest/meta-data/?session=1",
        "http://0177.0.0.1/share?session=1",  # inet_aton 八进制缩写形态（前缀黑名单的经典绕过载荷）
        "http://[::1]/share?session=1",
    )
    for landing in originals:
        spy = _ReqSpy(landing=landing)
        logger = _LoggerSpy()
        monkeypatch.setattr(sp, "async_req", spy)
        monkeypatch.setattr(sp, "logger", logger)

        result = await sp.get_shopee_stream_url("https://shopee.sg/live/1?session=777", cookies="SHOPEE_SESS=SECRET")

        assert result["is_live"] is False, landing
        # 落地页的 host 一次都不该出现在实际请求里（回环/元数据端口观测口被封掉）
        landing_host = _as_str(urllib.parse.urlparse(landing).hostname)
        assert landing_host, landing
        assert not any(landing_host in _as_str(urllib.parse.urlparse(u).hostname or "") for u in spy.urls), (
            landing,
            spy.urls,
        )
        # 只有「对用户自填地址的跳转探测」这一支允许带凭据
        assert all(item["redirect"] for item in spy.credentialed()), (landing, spy.sent)
        assert any("非白名单主机" in m for m in logger.messages("warning")), (landing, logger.msgs)


async def test_allowlisted_landing_that_resolves_internal_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 只查后缀会放行的形态：落地页 host 落在 Shopee 域族内，但 DNS 解析到内网
    # （被劫持的解析，或 sslip.io 这类把 IP 编码进域名的服务）。第二道闸必须接住它。
    spy = _ReqSpy(landing="https://live.shopee.sg/share?session=4242")
    logger = _LoggerSpy()
    seen_hosts: list[str] = []

    def _internal(host: str, **kwargs: object) -> str:
        seen_hosts.append(host)
        return "解析到内网地址 127.0.0.1"

    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)
    # 打的是 DNS 这一 seam，不是重新实现判据：本条要证明的是「第二道闸接进了流程、
    # 且拒绝即丢弃跳转」，而真实函数在 CI 上要么走 DNS、要么依赖解析结果。
    monkeypatch.setattr(web_config, "_host_internal_reason", _internal)

    result = await sp.get_shopee_stream_url("https://shopee.sg/live/1?session=777", cookies="SHOPEE_SESS=SECRET")

    assert result["is_live"] is False
    assert seen_hosts == ["live.shopee.sg"], f"内网判据未被以落地页 host 调用: {seen_hosts}"
    assert not any("session/4242" in u for u in spy.urls), spy.urls
    followups = spy.followups()
    assert _as_str(followups[0]["url"]) == "https://live.shopee.sg/api/v1/session/777", spy.urls
    assert "Cookie" not in _as_dict(followups[0]["headers"])
    assert any("不可信" in m for m in logger.messages("warning")), logger.messages("warning")


# ── 第三道闸：校验构造结果（api_host）─────────────────────────────────────


async def test_poisoned_host_suffix_blocked_by_api_host_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # 载荷：live.shopee.evil.com 形态的直链（main.py 的 "live.shopee" 分发键按子串命中，
    # 所以这条地址确实会被路由进本函数）。host_suffix = "evil.com" →
    # api_host = https://live.shopee.evil.com 归攻击者的 DNS 所有。
    # 前两道闸只看输入，此处必须按**构造结果**再判一次：不过即按未开播早退、零请求外发。
    spy = _ReqSpy()
    logger = _LoggerSpy()
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)

    result = await sp.get_shopee_stream_url(
        "https://live.shopee.evil.com/share?session=123", cookies="SHOPEE_SESS=SECRET"
    )

    assert result["is_live"] is False
    assert spy.sent == [], f"host_suffix 被投毒后仍发出了请求: {spy.sent}"
    warnings = logger.messages("warning")
    assert any("白名单" in m for m in warnings), warnings
    # 告警文本只带构造出来的 host，绝不带 headers 里的凭据
    assert all("SHOPEE_SESS" not in m for m in warnings), warnings


async def test_api_host_gate_blocks_poisoned_suffix_arriving_via_landing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 同一道闸的第二种到达方式：原始地址就是被投毒的 host（含 uid 的店铺主页形态）。
    # 跳转分支不触发（url 里有 "uid"），api_host 直接由这条地址的 host 切出来 → 仍须零请求。
    spy = _ReqSpy(landing="https://shopee.evil.co/x?session=5")
    logger = _LoggerSpy()
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)

    result = await sp.get_shopee_stream_url("https://live.shopee.evil.co/share?uid=1", cookies="SHOPEE_SESS=SECRET")

    assert result["is_live"] is False
    assert spy.sent == [], spy.sent
    assert any("白名单" in m for m in logger.messages("warning")), logger.msgs


# ── 反向护栏：合法路径不受损 ─────────────────────────────────────────────


async def test_legit_landing_keeps_credentials_and_records(monkeypatch: pytest.MonkeyPatch) -> None:
    # 三道闸不得把正常短链一起挡掉：合法域族落地页 → 采纳跳转、后续请求继续带 Cookie、
    # 并正常拿到流地址（is_live True）。
    body = (
        '{"data": {"session": {"uid": "9", "nickname": "主播名", "status": 1,'
        ' "play_url": "https://live.shopee.co.id/1.flv", "title": "T"}}}'
    )
    spy = _ReqSpy(landing="https://live.shopee.co.id/share?session=4242", body=body)
    logger = _LoggerSpy()
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)
    # 只替 DNS seam（真实函数这里要解析域名，CI 离线恒判「无法解析」）：
    # 白名单、凭据收口、api_host 闸三条判据全部走真实实现。
    monkeypatch.setattr(web_config, "_host_internal_reason", lambda host, **kwargs: None)

    result = await sp.get_shopee_stream_url("https://shopee.sg/live/1?session=777", cookies="SHOPEE_SESS=SECRET")

    assert result["is_live"] is True
    assert result["anchor_name"] == "主播名"
    assert result["record_url"] == "https://live.shopee.co.id/1.flv"
    followups = spy.followups()
    assert _as_str(followups[0]["url"]) == "https://live.shopee.co.id/api/v1/session/4242", spy.urls
    assert _as_dict(followups[0]["headers"]).get("Cookie") == "SHOPEE_SESS=SECRET"
    assert logger.messages("warning") == [], f"合法链路不该刷安全告警: {logger.msgs}"


async def test_direct_live_shopee_link_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    # 直链形态（含 live.shopee、不含 uid）本就不进跳转分支：零安全告警、按 session 正常请求。
    # 这条同时守住 MIN-2211 的既有语义——未开播轮次刻意保持静默（不刷 warning/error）。
    spy = _ReqSpy(body='{"data": null}')
    logger = _LoggerSpy()
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", logger)

    result = await sp.get_shopee_stream_url("https://live.shopee.sg/share?session=802458", cookies="C=1")

    assert result["is_live"] is False
    assert spy.urls == ["https://live.shopee.sg/api/v1/session/802458"], spy.urls
    assert spy.sent[0]["redirect"] is False
    assert _as_dict(spy.sent[0]["headers"]).get("Cookie") == "C=1"


# ── 顺带收口：uid / session 拼进查询串与路径段的编码（S-1 ⑤）───────────────


async def test_uid_query_value_is_percent_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    # 未编码时 uid="1&limit=999" 会在 ongoing 接口上**新增一个查询参数**（参数走私）。
    spy = _ReqSpy(body='{"data": null}')
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", _LoggerSpy())

    await sp.get_shopee_stream_url("https://live.shopee.sg/share?uid=1%26limit%3D999", cookies="C=1")

    ongoing = [u for u in spy.urls if "/live/ongoing" in u]
    assert ongoing, spy.urls
    assert "uid=1%26limit%3D999" in ongoing[0], ongoing[0]
    assert "limit=999" not in ongoing[0], ongoing[0]


async def test_session_path_segment_is_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    # session_id 落在路径段上：未编码的 "8/../health" 会改写请求行本身。
    spy = _ReqSpy(body='{"data": null}')
    monkeypatch.setattr(sp, "async_req", spy)
    monkeypatch.setattr(sp, "logger", _LoggerSpy())

    await sp.get_shopee_stream_url("https://live.shopee.sg/share?session=8%2F..%2Fhealth", cookies="C=1")

    assert spy.urls == ["https://live.shopee.sg/api/v1/session/8%2F..%2Fhealth"], spy.urls
