# tests/test_web_config.py - src/web_config.py 纯函数模块的安全不变量回归。
# 守护：换行注入防护（C3/C7）、密钥哈希往返与明文兼容、原子写不残留临时文件、
# 默认值含受信代理字段、画质选项的规范化/持久化、URL_config.ini 房间画质保序改写与主播名反查 URL。
# 全程纯函数 + tmp_path，不触网、不依赖全局 config。

import configparser
from pathlib import Path

import pytest

from src.web_config import (
    BUILTIN_QUALITIES,
    SENSITIVE_MASK,
    clamp_pbkdf2_iterations,
    find_room_url_by_anchor_name,
    format_url_line,
    hash_web_password,
    is_hashed_web_password,
    is_host_allowed,
    is_loopback_bind_host,
    is_origin_allowed,
    is_sensitive_item,
    normalize_quality_options,
    parse_url_config,
    read_config_safe,
    read_quality_options,
    read_web_config,
    update_config_line,
    update_room_quality,
    validate_config_target,
    validate_room_target,
    verify_web_password,
    write_quality_options,
)


class TestFormatUrlLine:
    # format_url_line 换行注入防护（C3）.

    # 守护 C3：quality 含换行视为注入攻击，format_url_line 须抛 ValueError（不写出污染行）。
    def test_quality_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality="高清\n# evil", name=None)

    def test_name_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality=None, name="主播\nxx")

    # 守护 C3：url 字段含换行拒绝（防止在房间列表文件里插入新行篡改配置）。
    def test_url_newline_rejected(self) -> None:
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1\n# evil", quality=None, name=None)

    # 正常路径：quality/name 均无换行时拼出 "quality,url,主播: name" 标准格式行。
    def test_normal_line(self) -> None:
        line = format_url_line("https://live.douyin.com/1", "超清", "小明")
        assert line == "超清,https://live.douyin.com/1,主播: 小明"


class TestValidateTargets:
    def test_newline_value_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_config_target("Web", "web_host", "127.0.0.1\nweb_port=9999")

    def test_newline_url_rejected(self) -> None:
        with pytest.raises(ValueError):
            validate_room_target("https://live.douyin.com/1\n# x", None)


class TestFormatUrlLineCarriesValidation:
    # 房间校验已**下沉**到 format_url_line（URL_config.ini 唯一写入口）。
    # 判据：把 web_api 里那些显式的 validate_room_target 调用全删掉，下面三条仍须抛错。

    def test_internal_target_rejected_by_formatter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError):
            format_url_line("http://127.0.0.1:8000/x?a=.flv")

    def test_arbitrary_scheme_rejected_by_formatter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError):
            format_url_line("file:///etc/passwd?a=.flv")

    def test_unknown_quality_rejected_by_formatter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError):
            format_url_line("https://live.douyin.com/1", quality="8K无敌")

    def test_default_and_empty_quality_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「原画」与空值是「移除画质段」的合法写法，不得被白名单误伤
        _stub_offline_dns(monkeypatch)
        assert format_url_line("https://live.douyin.com/1", "原画") == "https://live.douyin.com/1"
        assert format_url_line("https://live.douyin.com/1", "") == "https://live.douyin.com/1"


def _stub_offline_dns(monkeypatch: pytest.MonkeyPatch, table: dict[str, list[str] | OSError] | None = None) -> None:
    # 之后房间地址要过 socket.getaddrinfo。这里只替换「解析」这一步（网络层桩），
    # 回环/私网/保留/CGNAT 的分类与「任一结果内部即拒绝」的裁决全部走真实代码。
    # 表外域名默认解析到一个公网地址；需要构造「解析失败」的用例把值写成 OSError 实例。
    from src import web_config as wc

    mapping: dict[str, list[str] | OSError] = {"__default__": ["114.114.114.114"]}
    mapping.update(table or {})

    def _fake_resolve(host: str) -> list[str]:
        outcome = mapping.get(host, mapping["__default__"])
        if isinstance(outcome, OSError):
            raise outcome
        return outcome

    monkeypatch.setattr(wc, "_resolve_host_ips", _fake_resolve)


class TestRoomTargetInternalBlocklist:
    # 内网拦截旧实现是「字符串前缀黑名单」，报告实测 7 条载荷中 5 条放行
    # （十进制 2130706433、八进制 0177.0.0.1、带端口 IPv6 [fe80::1]:8080、
    # CGNAT 100.64.0.1、阿里云元数据 100.100.100.200）。
    # 现改为 ipaddress 语义 + DNS 解析双道判定。载荷均带 ?x=.m3u8 / ?a=.flv 尾巴，
    # 与报告一致（那正是命中 main.py 自定义流分支、把原地址送进 ffmpeg -i 的形态）。

    # 报告表格 + 等价形态扩展：以下全部必须 REJECTED
    BLOCKED_PAYLOADS: list[str] = [
        "http://127.0.0.1:8080/manager/x?a=.flv",
        "http://169.254.169.254/latest/meta-data/?x=.m3u8",
        "http://2130706433/x?a=.flv",
        "http://0177.0.0.1/x?a=.flv",
        "http://0x7f.0.0.1/x?a=.flv",
        "http://127.1/x?a=.flv",
        "http://[fe80::1]:8080/x?a=.flv",
        "http://[fd12::34]/x?a=.flv",
        "http://[::1]/x?a=.flv",
        "http://[::ffff:127.0.0.1]/x?a=.flv",
        "http://100.64.0.1/x?a=.flv",
        "http://100.100.100.200/latest/meta-data/?x=.m3u8",
        "http://10.1.2.3/x?a=.flv",
        "http://192.168.1.1:554/x?a=.flv",
        "http://172.16.5.4/x?a=.flv",
        "http://172.31.255.255/x?a=.flv",
        "http://0.0.0.0/x?a=.flv",
        "http://localhost:8000/x?a=.flv",
        "http://224.0.0.1/x?a=.flv",
        "http://metadata.google.internal/y?x=.m3u8",
        "http://my-room.local/x?a=.flv",
        "http://svc.cluster.internal/x?a=.flv",
        "http://box.svc.home.arpa/x?a=.flv",
        "http://attacker.localhost/x?a=.flv",
        "http://127-0-0-1.sslip.io/x?a=.flv",  # IP 编码进域名：靠解析结果识别
        "http://dual-stack.example.com/x?a=.flv",  # 公网 + 回环同时返回：任一内部即拒绝
        "http://intranet-only.example.com/x?a=.flv",  # 解析到 10.0.0.5 的域名
        "http://nowhere.example.com/x?a=.flv",  # 解析失败一律拒绝
        "file:///etc/passwd?a=.flv",
        "rtp://127.0.0.1/x?a=.flv",
    ]

    # 真实平台地址（回归护栏：收紧判定不许把可用房间一起砍掉）
    ALLOWED_PAYLOADS: list[str] = [
        "https://live.douyin.com/745964462470",
        "https://live.bilibili.com/123456",
        "https://www.huya.com/dank1ng",
        "https://www.douyu.com/36252",
        "https://www.twitch.tv/theshy",
        "https://www.youtube.com/@test/streams",
        "https://live.kuaishou.com/u/testuser",
        "https://91.popkon.tv/en/live/1234",
        "https://live.cctv.com/channel/sports",
        "http://121.229.0.10/live/a.m3u8",
        "http://[2408:8000:0:1::abcd]/live/a.m3u8",  # 公网 IPv6 直连地址（须按 RFC 带方括号）
    ]

    # 三个「靠解析才定罪/才放行」的域名解析桩（其余域名走默认公网地址）
    _DNS_TABLE: dict[str, list[str] | OSError] = {
        "127-0-0-1.sslip.io": ["127.0.0.1"],
        "dual-stack.example.com": ["8.8.8.8", "::1"],
        "intranet-only.example.com": ["10.0.0.5"],
        "nowhere.example.com": OSError("getaddrinfo failed"),
    }

    @pytest.mark.parametrize("url", BLOCKED_PAYLOADS)
    def test_internal_targets_rejected(self, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch, self._DNS_TABLE)
        with pytest.raises(ValueError):
            validate_room_target(url, None, None)

    @pytest.mark.parametrize("url", ALLOWED_PAYLOADS)
    def test_public_platform_targets_allowed(self, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判点是「不得因收紧内网名单而误伤真实平台」：解析结果固定为可路由公网地址，
        # 各平台此刻实际解析到什么 IP 不属于被测契约（那会让用例随 DNS 漂移）。
        _stub_offline_dns(monkeypatch, self._DNS_TABLE)
        validate_room_target(url, None, None)

    def test_cgnat_blocklist_is_explicit_because_3_14_drops_it(self) -> None:
        # 3.14 起 ipaddress 按 IANA 特别用途注册表判定：100.64.0.0/10 不算私网。
        # 本用例锁「显式网段名单」这一前提，将来若依赖 is_private 覆盖 CGNAT 即变红。
        import ipaddress

        assert not ipaddress.ip_address("100.64.0.1").is_private
        # 直接调分类函数：入参已是字面量地址，本就不需要 DNS
        from src.web_config import _internal_ip_reason

        assert _internal_ip_reason(ipaddress.ip_address("100.64.0.1")) is not None
        assert _internal_ip_reason(ipaddress.ip_address("100.100.100.200")) is not None

    def test_ipv4_aton_forms_normalized_to_loopback(self) -> None:
        # 缩写/非十进制形态必须在本层还原（不能「看起来不像 IP 就交给 DNS」）
        from src.web_config import _parse_ip_literal

        for text in ("2130706433", "0177.0.0.1", "0x7f000001", "127.1", "127.0.1"):
            addr = _parse_ip_literal(text)
            assert addr is not None and addr.is_loopback, f"{text} 未还原成回环地址: {addr}"

    def test_partial_or_namey_strings_are_not_ip_literals(self) -> None:
        from ipaddress import IPv4Address

        from src.web_config import _parse_ip_literal

        # a.b.c 是 inet_aton 的合法形态（末段独占剩余两字节），刻意保持同款语义：
        # 只拦「看起来像但越界/含非数字」的串，不做「少一段就当主机名」的宽松处理
        assert _parse_ip_literal("1.2.3") == IPv4Address("1.2.0.3")
        assert _parse_ip_literal("999.1.1.1") is None
        assert _parse_ip_literal("example.com") is None
        assert _parse_ip_literal("1.2.3.4.5") is None
        assert _parse_ip_literal("live.douyin.com") is None


class TestDnsRebindingBoundary:
    # 边界：本层只能校验「写入那一刻」的解析结果。
    # 该用例锁住这个事实（而不是假装能挡重绑定），提醒后续改动不要把它当完整防线。

    def test_ttl_zero_rebinding_passes_write_time_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src import web_config as wc

        answers: dict[str, list[str]] = {"host": ["114.114.114.114"]}
        monkeypatch.setattr(wc, "_resolve_host_ips", lambda host: list(answers["host"]))
        # 写入时公网 → 放行（无法预知录制时 ffmpeg 重新解析到什么）
        validate_room_target("http://evil.example.com/room?a=.flv")
        # 之后记录被改成回环：本层无从拦截，只能在出站网络层（egress 防火墙/代理）收口
        answers["host"] = ["127.0.0.1"]
        with pytest.raises(ValueError):
            validate_room_target("http://evil.example.com/room?a=.flv")


class TestHostAndLoopbackPolicy:
    # 该服务端名单口径（Host 头不再自证可信）。

    def test_loopback_forms(self) -> None:
        for host in ("127.0.0.1", "localhost", "::1", "[::1]", "127.0.0.53", "localhost:8000"):
            assert is_loopback_bind_host(host), host
        for host in ("0.0.0.0", "::", "192.168.1.10", "10.0.0.1", "", " panel.example.com "):
            assert not is_loopback_bind_host(host), host

    def test_allowed_hosts_and_public_ip_escape(self) -> None:
        cfg = {"web_host": "127.0.0.1", "web_allowed_hosts": ""}
        assert is_host_allowed("127.0.0.1:8000", cfg)
        assert is_host_allowed("localhost", cfg)
        assert is_host_allowed("testserver", cfg)  # 无点单标签名（内网 netbios / 测试桩）
        assert not is_host_allowed("attacker.tld:8000", cfg)
        assert not is_host_allowed("attacker.tld", cfg)
        # 绑到 0.0.0.0 的部署：以局域网 IP 访问仍放行（IP 字面量无法被 DNS 重绑定）
        wild = {"web_host": "0.0.0.0", "web_allowed_hosts": ""}
        assert is_host_allowed("192.168.1.20:8000", wild)
        assert not is_host_allowed("panel.attacker.example", wild)
        # 显式登记后放行（含 *. 后缀形态）
        named = {"web_host": "0.0.0.0", "web_allowed_hosts": "recorder.lan, *.home.example"}
        assert is_host_allowed("recorder.lan:8000", named)
        assert is_host_allowed("nas.home.example", named)
        assert not is_host_allowed("evil.home.example.other", named)


class TestOriginAllowedPolicy:
    # MID-N42 修复（CODE_REVIEW_2026-09-21）纯函数侧：Origin 与 Host 从此是两套名单。
    # HTTP 侧（谁被 403）见 tests/test_web_api.py::TestOriginSameHostAndPort；本类锁的是
    # 「期望集合如何由服务端状态推导」，并反向锁住 Host 那套规则没被顺带改掉
    # （合并成一套必然有一侧退化：Host 松了就丢该重绑定防线，Origin 紧了就砍掉反代入口）。

    # 显式注解：dict[str, object] 与判定函数的 Mapping[str, str | int | bool] 不兼容（mypy arg-type）
    _WILD: dict[str, str | int | bool] = {"web_host": "0.0.0.0", "web_port": 8000, "web_allowed_hosts": ""}
    _LOCAL: dict[str, str | int | bool] = {"web_host": "127.0.0.1", "web_port": 8000, "web_allowed_hosts": ""}

    def test_ip_and_dotless_escape_hatches_are_host_only(self) -> None:
        # 同一份 cfg（绑 0.0.0.0）：Host 侧放行 IP 字面量与无点单标签名，Origin 侧都不放行。
        assert is_host_allowed("192.168.1.47:8000", self._WILD)
        assert is_host_allowed("nas", self._WILD)
        assert not is_origin_allowed("http://192.168.1.47:8000", self._WILD, bind_host="0.0.0.0", bind_port=8000)
        assert not is_origin_allowed("http://nas:8000", self._WILD, bind_host="0.0.0.0", bind_port=8000)
        # 通配登记同样只对 Host 生效：同源是按「那一台主机」成立的，*.home.example 可被签发
        wildcard: dict[str, str | int | bool] = {
            "web_host": "0.0.0.0",
            "web_port": 8000,
            "web_allowed_hosts": "*.home.example",
        }
        assert is_host_allowed("nas.home.example", wildcard)
        assert not is_origin_allowed("http://nas.home.example:8000", wildcard, bind_host="0.0.0.0", bind_port=8000)

    def test_expected_pair_is_bind_host_and_bind_port(self) -> None:
        # 实际绑定 192.168.1.47:9000 时：该 host:port 同源；配置的 web_port=8000 不算；
        # 且 web_host 里写着什么都与判定无关（它可被 PUT /api/config 改写）。
        cfg: dict[str, str | int | bool] = {"web_host": "127.0.0.1", "web_port": 8000, "web_allowed_hosts": ""}
        assert is_origin_allowed("http://192.168.1.47:9000", cfg, bind_host="192.168.1.47", bind_port=9000)
        assert not is_origin_allowed("http://192.168.1.47:8000", cfg, bind_host="192.168.1.47", bind_port=9000)
        assert not is_origin_allowed("http://127.0.0.1:8000", cfg, bind_host="192.168.1.47", bind_port=9000)

    def test_loopback_family_requires_the_bound_port(self) -> None:
        # 回环族恒可（面板出厂入口就是 localhost/127.0.0.1/::1），但端口必须命中：
        # http://localhost:3000/ 是本机另一个 dev server，正是本条要拦的形态。
        for origin in ("http://localhost:8000", "http://127.0.0.1:8000", "http://[::1]:8000", "http://127.0.0.53:8000"):
            assert is_origin_allowed(origin, self._LOCAL, bind_host="127.0.0.1", bind_port=8000), origin
        for origin in ("http://localhost:3000", "http://127.0.0.1:80", "https://127.0.0.1", "http://localhost"):
            assert not is_origin_allowed(origin, self._LOCAL, bind_host="127.0.0.1", bind_port=8000), origin

    def test_registered_host_may_pin_its_own_port(self) -> None:
        named: dict[str, str | int | bool] = {
            "web_host": "0.0.0.0",
            "web_port": 8000,
            "web_allowed_hosts": "recorder.lan, nas.home.example:9443",
        }
        # 未写端口的登记项 → 仍要求等于实际绑定端口
        assert is_origin_allowed("http://recorder.lan:8000", named, bind_host="0.0.0.0", bind_port=8000)
        assert not is_origin_allowed("http://recorder.lan:9999", named, bind_host="0.0.0.0", bind_port=8000)
        # 写了端口的登记项 → 按登记端口判（反代入口端口与应用端口不同的合法部署）
        assert is_origin_allowed("https://nas.home.example:9443", named, bind_host="0.0.0.0", bind_port=8000)
        assert not is_origin_allowed("https://nas.home.example:8000", named, bind_host="0.0.0.0", bind_port=8000)
        # 全角逗号分隔同样生效（与 get_allowed_hosts / 推送侧的拆分口径同源）
        wide: dict[str, str | int | bool] = {
            "web_host": "0.0.0.0",
            "web_port": 8000,
            "web_allowed_hosts": "a.lan，b.lan:9443",
        }
        assert is_origin_allowed("http://a.lan:8000", wide, bind_host="0.0.0.0", bind_port=8000)
        assert is_origin_allowed("http://b.lan:9443", wide, bind_host="0.0.0.0", bind_port=8000)

    def test_testserver_sentinel_exemption_has_a_narrow_boundary(self) -> None:
        # 豁免只为 Starlette TestClient 的固定哨兵存在：仅「该名字 + 无显式端口」这一种组合。
        assert is_origin_allowed("http://testserver", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        assert not is_origin_allowed("http://testserver:9999", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        # 另一个无点单标签名不得搭车（否则等价于把 is_host_allowed 的第③条重新引进来）
        assert not is_origin_allowed("http://nas", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        assert not is_origin_allowed("http://192.168.1.47", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)

    def test_testserver_exemption_requires_pytest_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 哨兵豁免此前在**生产判定**里无条件生效（测试后门进生产——生产
        # 进程收到 Origin: http://testserver 即免端口放行）。现加 _running_under_pytest() 环境门：
        # 本用例把门桩成 False 模拟生产进程，豁免必须整体失效；而真实回环 + 正确端口的常规
        # 判定不受该门影响（防止把环境门做成「一切都不放行」）
        from src import web_config as wc

        assert is_origin_allowed("http://testserver", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        monkeypatch.setattr(wc, "_running_under_pytest", lambda: False)
        assert not is_origin_allowed("http://testserver", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        assert is_origin_allowed("http://127.0.0.1:8000", self._LOCAL, bind_host="127.0.0.1", bind_port=8000)

    @pytest.mark.parametrize(
        "origin",
        [
            "",
            "127.0.0.1:8000",  # 无 scheme
            "ftp://127.0.0.1:8000",  # 非 http(s)
            "http://127.0.0.1:0",  # 端口 0 非法
            "http://127.0.0.1:99999",  # 端口越界
            "http://127.0.0.1:notaport",  # 端口非数字
            "http:///127.0.0.1:8000",  # 空 authority
            "http://u:p@127.0.0.1:8000",  # Origin 不含 userinfo
            "http://127.0.0.1:8000/path",  # Origin 不含 path
        ],
    )
    def test_malformed_origin_is_denied(self, origin: str) -> None:
        # 畸形值一律判否（不给「解析器差异」留可利用空间）：判定结果不得依赖 urlparse 的宽容度。
        assert not is_origin_allowed(origin, self._LOCAL, bind_host="127.0.0.1", bind_port=8000)
        # 「http://127.0.0.1:8000/path」这种带 path 的形态：主机与端口都对，但浏览器不会这么发
        # → 按 Origin 契约判否（放行它等于接受任意以本站开头的字符串）
        # 注：本用例的 path 形态同时证明「拒绝来自 authority 严格解析」，与上一条的端口越界互不遮蔽。


class TestOutboundTargetConfigKeys:
    # MID-N45 修复（CODE_REVIEW_2026-09-21）纯函数侧：校验挂在
    # validate_config_target（config.ini 写侧唯一入口）上，故「端点忘了调」这一类失效不可能出现
    # ——这也是本类只经 validate_config_target 而不直接调私有实现的原因。

    def test_push_url_uses_room_url_judgement_core(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError) as excinfo:
            validate_config_target("推送配置", "ntfy推送地址", "http://127.0.0.1:6379/")
        assert "回环地址" in str(excinfo.value)
        # 缩写/映射形态同样要拦（与房间侧同一份判定内核，不是又一份前缀黑名单）
        for value in ("http://2130706433/", "http://[::ffff:127.0.0.1]/", "http://10.1.2.3/x"):
            with pytest.raises(ValueError):
                validate_config_target("推送配置", "钉钉推送接口链接", value)

    def test_every_comma_segment_is_judged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        ok = "https://oapi.dingtalk.com/robot/send"
        bad = "http://169.254.169.254/"
        for value in (f"{ok},{bad}", f"{bad},{ok}", f"{ok}，{bad}"):  # 含全角逗号形态
            with pytest.raises(ValueError):
                validate_config_target("推送配置", "bark推送接口链接", value)
        validate_config_target("推送配置", "bark推送接口链接", f"{ok},{ok}")

    def test_proxy_allows_local_forms_and_blocks_reserved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 代理地址是本机/内网常态（127.0.0.1:7890 是文档写法），故收口点在协议与保留类别：
        _stub_offline_dns(monkeypatch)
        for value in (
            "127.0.0.1:7890",
            "http://127.0.0.1:7890",
            "socks5://192.168.1.10:1080",
            "localhost:7890",
            "proxy:8080",  # 裸主机名:端口（compose 服务名写法）：归一后按 host 判定，不得误杀
            "http://user:pass@proxy.example.com:8080",  # 带凭据的公网代理
        ):
            validate_config_target("录制设置", "代理地址", value)
        for value in (
            "http://169.254.169.254:80/",
            "socks5://[fe80::1]:1080",
            "gopher://127.0.0.1:9876",
            "http://0.0.0.0:80",
        ):
            with pytest.raises(ValueError):
                validate_config_target("录制设置", "代理地址", value)

    def test_smtp_judged_by_hostname_not_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_offline_dns(monkeypatch)
        validate_config_target("推送配置", "smtp邮件服务器", "10.0.0.5")  # 内网邮件中继合法
        validate_config_target("推送配置", "smtp邮件服务器", "smtp.lan.example")
        for value in ("metadata", "169.254.169.254", "metadata.google.internal"):
            with pytest.raises(ValueError):
                validate_config_target("推送配置", "smtp邮件服务器", value)
        # 入参形态必须先钉住再判主机：URL 形态经 _strip_host_port 会变成一根认不出、
        # 也不是 IP 的怪串（冒号不止一个 → 端口不剥），从而蒙过全部网段判定。
        # 首尾空白不在此列——configparser 读值时本就会剥，写进去的已经是干净串。
        for value in ("http://127.0.0.1:6379/", "smtp a.example.com"):
            with pytest.raises(ValueError):
                validate_config_target("推送配置", "smtp邮件服务器", value)

    def test_key_matching_is_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # configparser 的 option 本就 casefold（AGENTS.md「配置键审计须先归一化大小写」）：
        # 只认规范写法等于给拉丁前缀的键留一条绕过路径（该同一形态）。
        _stub_offline_dns(monkeypatch)
        for key, value in (
            ("NTFY推送地址", "http://127.0.0.1:6379/"),
            ("BARK推送接口链接", "http://127.0.0.1:6379/"),
            ("微信推送接口链接", "http://169.254.169.254/"),
            ("SMTP邮件服务器", "metadata"),
        ):
            with pytest.raises(ValueError):
                validate_config_target("推送配置", key, value)

    def test_ordinary_keys_are_out_of_scope(self) -> None:
        # 反向护栏：白名单式按键判定，普通键的值长得像内网 URL 也必须能写
        # （否则这条防线会扩成「配置文件不能写某些字符串」的功能回归）。
        validate_config_target("录制设置", "HLS采集排除平台(逗号分隔)", "http://127.0.0.1:6379/")
        validate_config_target("录制设置", "自定义画质选项(逗号分隔)", "超清,高清")
        validate_config_target("推送配置", "ntfy推送地址", "")  # 空值 = 未配置，交由敏感键守卫处理

    def test_internal_target_switch_does_not_relax_metadata(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # 破例通道是「放开本机/内网自建服务」，不是「关掉整条校验」：
        # 云元数据端点、链路本地、0.0.0.0 在开关打开后仍必须拒绝。
        monkeypatch.setenv("DOUYIN_WEB_ALLOW_INTERNAL_TARGET", "1")
        validate_config_target("推送配置", "ntfy推送地址", "http://127.0.0.1:8080/topic")
        for value in ("http://169.254.169.254/", "http://[fe80::1]/x", "http://0.0.0.0/x", "http://100.64.0.1/x"):
            with pytest.raises(ValueError):
                validate_config_target("推送配置", "ntfy推送地址", value)


class TestPbkdf2IterationsClamp:
    # 迭代次数取自 config.ini（用户可编辑的存储串），旧实现原值喂给
    # hashlib.pbkdf2_hmac → 把 200k 改成 2e7 即让每次登录烧掉十几秒 CPU。

    def test_upper_bound(self) -> None:
        assert clamp_pbkdf2_iterations("999999999") == 1_000_000

    def test_lower_bound_is_module_default(self) -> None:
        # 低于默认值的哈希一律判失败：不给「把迭代数降级以放大爆破吞吐」留门
        assert clamp_pbkdf2_iterations("1") == 200_000
        assert clamp_pbkdf2_iterations("199999") == 200_000

    def test_normal_value_unchanged(self) -> None:
        assert clamp_pbkdf2_iterations("300000") == 300_000

    def test_garbage_returns_default(self) -> None:
        assert clamp_pbkdf2_iterations("not-a-number") == 200_000
        assert clamp_pbkdf2_iterations("") == 200_000
        assert clamp_pbkdf2_iterations(None) == 200_000

    def test_verify_does_not_amplify_cost(self) -> None:
        # 端到端：手工把存储串迭代数写成天文数字，校验须在上界内完成并判失败（不抛异常）
        assert verify_web_password("x", "pbkdf2_sha256$999999999999$c2FsdA==$aGFzaA==") is False

    def test_hash_roundtrip_still_verifies(self) -> None:
        # 归一不能把正常哈希一起判死：hash_web_password 走默认 200k
        hashed = hash_web_password("pw-123")
        assert is_hashed_web_password(hashed)
        assert verify_web_password("pw-123", hashed)
        assert not verify_web_password("pw-124", hashed)


class TestReadWebConfigAllowedHosts:
    def test_default_includes_allowed_hosts_key(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("", encoding="utf-8-sig")
        assert read_web_config(cfg)["web_allowed_hosts"] == ""


class TestUpdateConfigLine:
    def test_update_preserves_comments_and_cleans_tmp(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\n# 注释\nweb_host = 127.0.0.1\nweb_port = 8000\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "web_host", "0.0.0.0") is True
        text = cfg.read_text(encoding="utf-8-sig")
        assert "web_host = 0.0.0.0" in text
        assert "# 注释" in text
        # 原子写不应留下临时文件（C7）：精确匹配 .tmp 扩展名
        leftovers = [p.name for p in tmp_path.glob("*.tmp")]
        assert leftovers == [], f"原子写残留临时文件: {leftovers}"

    def test_missing_key_returns_false(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_host = 127.0.0.1\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "not_exist", "x") is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert update_config_line(tmp_path / "nope.ini", "Web", "web_host", "x") is False

    def test_duplicate_key_in_section_refuses_write(self, tmp_path: Path) -> None:
        # 手工编辑产生的重复键，旧实现只替换节内**首个**匹配行并返回 True，
        # 生效值却来自另一行（「面板提示已保存、行为未变」）。现匹配数 >1 → 拒绝写入：
        # 返回 False 且文件逐字不变——复用既有失败出口（web_api 转 404、write_quality_options
        # 报写失败），不新增第三种返回形态。反向半边：同名键在**其他节**出现不得算重复
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_port = 8000\nweb_port = 9000\n", encoding="utf-8-sig")
        before = cfg.read_bytes()
        assert update_config_line(cfg, "Web", "web_port", "8100") is False
        assert cfg.read_bytes() == before, "重复键被拒后文件仍被改写"
        cfg2 = tmp_path / "config2.ini"
        cfg2.write_text("[Web]\nweb_port = 8000\n[Other]\nweb_port = 9000\n", encoding="utf-8-sig")
        assert update_config_line(cfg2, "Web", "web_port", "8100") is True
        text2 = cfg2.read_text(encoding="utf-8-sig")
        assert "web_port = 8100" in text2 and "web_port = 9000" in text2

    def test_commented_duplicate_is_not_counted(self, tmp_path: Path) -> None:
        # 计数口径的边界：注释行（`#key = ...`）在真实替换判定里从不命中（行首 # 不匹配
        # 键模式），计数同样不得把它算进「重复」——否则「一实一注释」这份完全合法的存量配置
        # 会被整体拒绝写入
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\n# web_port = 8000\nweb_port = 9000\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Web", "web_port", "8100") is True
        assert "web_port = 8100" in cfg.read_text(encoding="utf-8-sig")

    def test_hash_in_value_reads_back_as_new_value(self, tmp_path: Path) -> None:
        # 读侧 configparser 未开启 inline_comment_prefixes，旧值里的
        # " #" 本就是值的一部分——二次更新后读回值必须**等于新值**，不得被旧尾注污染
        # （旧实现把 " #" 之后当注释拼回新值，平台 Cookie/含井号 token 因此静默失效）。
        parser = configparser.ConfigParser()
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Sec]\nkey = old #b\n", encoding="utf-8-sig")
        assert update_config_line(cfg, "Sec", "key", "new") is True
        parser.read(cfg, encoding="utf-8-sig")
        assert parser.get("Sec", "key") == "new", "无引号值含 ' #' 时尾串被当注释拼回新值"
        # 带引号且值含 " #"、无尾注的同型：闭合引号之前的一切都属值本身（该回落分支残留）
        cfg2 = tmp_path / "config2.ini"
        cfg2.write_text('[Sec]\nkey = "a #b"\n', encoding="utf-8-sig")
        assert update_config_line(cfg2, "Sec", "key", "new") is True
        parser2 = configparser.ConfigParser()
        parser2.read(cfg2, encoding="utf-8-sig")
        assert parser2.get("Sec", "key") == "new", "带引号值的 ' #' 被回落启发式二次污染"
        # 既有语义保持：引号值后的真注释仍原样保留
        cfg3 = tmp_path / "config3.ini"
        cfg3.write_text('[Sec]\nkey = "v" # 备注\n', encoding="utf-8-sig")
        assert update_config_line(cfg3, "Sec", "key", "new") is True
        text = cfg3.read_text(encoding="utf-8-sig")
        assert "key = new # 备注" in text


class TestAppendConfigLineReturn:
    # append_config_line 此前丢弃 _atomic_write_text 的布尔值、无条件
    # return True，而 update_config_line 已按该修正——补建分支（config.ini 缺 language 键、
    # 画质选项首次落盘）磁盘写失败仍报成功，set_language 的回滚与 write_quality_options 的
    # 失败回报全部失明。判据走「替换失败→补建」这条真实组合路径，不重新实现任何写入逻辑。

    def test_propagates_atomic_write_failure(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from src import web_config as wc
        from src.web_config import append_config_line, update_or_append_config_line

        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_host = 127.0.0.1\n", encoding="utf-8-sig")
        # 正向半边先跑：未打桩时同一输入必须 True（防止把修复做成「恒 False」的假绿对照）
        assert append_config_line(str(cfg), "Web", "language", "en_US") is True
        assert "language = en_US" in cfg.read_text(encoding="utf-8-sig")
        monkeypatch.setattr(wc, "_atomic_write_text", lambda _path, _text: False)
        assert append_config_line(str(cfg), "Web", "language2", "x") is False, "补建分支仍吞掉写失败"
        # update_or_append：缺键 → 替换失败 → 落补建分支 → 写失败必须传导为 False
        assert update_or_append_config_line(str(cfg), "Web", "language3", "y") is False

    # M-26②（CODE_REVIEW_2026-10-29）：update_config_line 对重复键拒绝写入，其 False 与
    # 「键不存在」同出口；update_or_append 若无条件追加，会把损坏文件再落第三行并回报成功。
    def test_duplicate_key_file_is_not_appended_again(self, tmp_path: Path) -> None:
        from src.web_config import update_or_append_config_line

        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_host = 1\nweb_host = 2\n", encoding="utf-8-sig")
        assert update_or_append_config_line(str(cfg), "Web", "web_host", "3") is False
        assert cfg.read_text(encoding="utf-8-sig").count("web_host") == 2


class TestVerifyWebPassword:
    def test_hash_roundtrip(self) -> None:
        hashed = hash_web_password("secret123")
        assert is_hashed_web_password(hashed)
        assert verify_web_password("secret123", hashed)
        assert not verify_web_password("wrong", hashed)

    # 兼容旧配置：未哈希的明文口令按相等直接放行（平滑迁移，不强制重设密码）。
    def test_plaintext_compat(self) -> None:
        assert verify_web_password("abc", "abc")

    def test_malformed_iterations_returns_false(self) -> None:
        # 手工改坏迭代次数不应抛异常导致登录接口 500（C12）
        bad = "pbkdf2_sha256$notanumber$c2FsdA==$aGFzaA=="
        assert verify_web_password("x", bad) is False

    # 边界：存储口令为空串时验证返回 False（不抛异常、不误判为通过）。
    def test_empty_stored_returns_false(self) -> None:
        assert verify_web_password("x", "") is False


class TestReadWebConfig:
    # 默认值不变量：空配置读出的默认值须含 web_trusted_proxy(空) 与 web_host(127.0.0.1 本地)；
    # 缺省绑定本地回环，避免误开公网。
    def test_defaults_include_trusted_proxy(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("", encoding="utf-8-sig")
        result = read_web_config(cfg)
        assert result["web_trusted_proxy"] == ""
        assert result["web_host"] == "127.0.0.1"

    # CODE_REVIEW_2026-10-29 S-04：三个读取点原先用 strict=True 解析器，config.ini 任一节出现
    # 重复键即抛 DuplicateOptionError；read_web_config 又处在 auth_middleware 的每请求路径上，
    # 一次配置损坏就让面板整体打不开（连 /health 都 500），用户无法经面板自救。
    def test_duplicate_keys_do_not_raise(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Web]\nweb_port = 8080\nweb_port = 9090\n", encoding="utf-8-sig")
        # 容错层口径与 configparser 自身内存态一致：后写覆盖前写
        assert read_web_config(cfg)["web_port"] == 9090

    def test_read_config_safe_duplicate_keys_do_not_raise(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[Cookie]\ncookie = a\ncookie = b\n", encoding="utf-8-sig")
        assert read_config_safe(cfg)["Cookie"]["cookie"] == SENSITIVE_MASK


class TestQualityOptions:
    # 画质选项的读/写/规范化：落地 config.ini [录制设置]，与 GUI/WEB 端共用。

    def test_normalize_drops_unknown_and_duplicates(self) -> None:
        # main.py 画质白名单外名称会被静默回退为「原画」，故选项必须仅取内置档位
        result = normalize_quality_options(["超清", "蓝光4M", "超清", "2K", "", " 流畅 "])
        assert result == ["超清", "蓝光4M", "流畅"]
        assert "2K" not in result  # 非法项剔除

    def test_normalize_falls_back_to_builtin_when_empty(self) -> None:
        # 全部非法/空 → 回退内置全集，避免下拉空空如也
        assert normalize_quality_options([]) == list(BUILTIN_QUALITIES)
        assert normalize_quality_options(["", "2K"]) == list(BUILTIN_QUALITIES)

    def test_read_missing_key_returns_builtin(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\n原画|超清|高清|标清|流畅 = 原画\n", encoding="utf-8-sig")
        assert read_quality_options(cfg) == list(BUILTIN_QUALITIES)

    # 同 S-04：画质读取点也必须容忍重复键（此前 strict=True 会抛 DuplicateOptionError，
    # 让 Web/GUI 的画质下拉在配置损坏时整片不可用）。
    def test_read_quality_options_tolerates_duplicate_keys(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[录制设置]\n自定义画质选项(逗号分隔) = 超清,流畅\n自定义画质选项(逗号分隔) = 高清\n",
            encoding="utf-8-sig",
        )
        assert read_quality_options(cfg) == ["高清"]

    def test_write_appends_when_key_missing_then_reads_back(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\nlanguage = zh_CN\n", encoding="utf-8-sig")
        result = write_quality_options(cfg, ["超清", "高清"])
        assert result == ["超清", "高清"]
        # 再次读取应拿到同样的列表（保留顺序）
        assert read_quality_options(cfg) == ["超清", "高清"]
        # 写入不应破坏节内其他键（language 原样保留）
        assert "language = zh_CN" in cfg.read_text(encoding="utf-8-sig")

    def test_write_updates_existing_key_in_place(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[录制设置]\n自定义画质选项(逗号分隔) = 超清,流畅\nlanguage = zh_CN\n",
            encoding="utf-8-sig",
        )
        write_quality_options(cfg, ["蓝光8M", "标清"])
        text = cfg.read_text(encoding="utf-8-sig")
        assert "自定义画质选项(逗号分隔) = 蓝光8M,标清" in text
        assert "language = zh_CN" in text  # 行级替换不应误伤

    def test_write_newline_in_options_rejected(self, tmp_path: Path) -> None:
        cfg = tmp_path / "config.ini"
        cfg.write_text("[录制设置]\n", encoding="utf-8-sig")
        with pytest.raises(ValueError):
            write_quality_options(cfg, ["超清\n# 注入"])


class TestUpdateRoomQuality:
    # update_room_quality：行级改写 URL_config.ini 中指定 URL 的画质段。
    # 守护：C3 换行注入防护、行格式约束（画质,URL[,主播: 名称]）、幂等性、URL 归一化匹配。

    def _write(self, path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8-sig")

    def test_add_quality_to_plain_url(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        # 格式: 画质,URL,主播: 名称（与需求示例一致）
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_change_existing_quality(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "蓝光8M,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_remove_quality_when_default(self, tmp_path: Path) -> None:
        # 默认画质（空字符串与「原画」）= 移除画质段，回落到全局默认
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "超清,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "https://live.douyin.com/1,主播: A\n"
        # 再用「原画」显式回落：幂等返回 False（已无画质段）
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "原画") is False

    def test_preserves_comment_prefix(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "# https://live.douyin.com/1,主播: 禁用\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is True
        assert url_cfg.read_text(encoding="utf-8-sig") == "# 超清,https://live.douyin.com/1,主播: 禁用\n"

    def test_idempotent_when_no_change(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "超清,https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "超清") is False
        # 同一画质段重复调用不修改文件
        assert url_cfg.read_text(encoding="utf-8-sig") == "超清,https://live.douyin.com/1,主播: A\n"

    def test_url_normalized_match(self, tmp_path: Path) -> None:
        # 配置行可能不带 scheme；写入端带 scheme 时也应能匹配到
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "live.douyin.com/1\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/1", "高清") is True
        assert "高清," in url_cfg.read_text(encoding="utf-8-sig")

    def test_no_match_returns_false(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1,主播: A\n")
        assert update_room_quality(url_cfg, "https://live.douyin.com/999", "超清") is False
        # 文件未修改
        assert url_cfg.read_text(encoding="utf-8-sig") == "https://live.douyin.com/1,主播: A\n"

    def test_newline_in_quality_rejected(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1\n")
        with pytest.raises(ValueError):
            update_room_quality(url_cfg, "https://live.douyin.com/1", "高清\n# evil")

    def test_atomic_write_no_leftover_tmp(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        self._write(url_cfg, "https://live.douyin.com/1\n")
        _ = update_room_quality(url_cfg, "https://live.douyin.com/1", "超清")
        leftovers = [p.name for p in tmp_path.glob("*.tmp")]
        assert leftovers == [], f"原子写残留临时文件: {leftovers}"


class TestFindRoomUrlByAnchorName:
    # find_room_url_by_anchor_name：按主播名反查直播间地址，供 GUI 画质切换写回使用。

    def test_exact_match(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        url_cfg.write_text(
            "https://live.douyin.com/1,主播: 香芋\nhttps://live.douyin.com/2,主播: 小Q\n",
            encoding="utf-8-sig",
        )
        assert find_room_url_by_anchor_name(url_cfg, "香芋") == "https://live.douyin.com/1"
        assert find_room_url_by_anchor_name(url_cfg, "小Q") == "https://live.douyin.com/2"

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        url_cfg = tmp_path / "URL_config.ini"
        url_cfg.write_text("https://live.douyin.com/1,主播: A\n", encoding="utf-8-sig")
        assert find_room_url_by_anchor_name(url_cfg, "不存在") == ""
        assert find_room_url_by_anchor_name(url_cfg, "") == ""


class TestSensitiveItemCaseInsensitive:
    # 「节白名单 + 键名正则」两道判定的强度必须同档——键名侧带
    # re.IGNORECASE，节名侧此前是大小写敏感的精确比较，于是把 [Cookie] 写成 [cookie]
    # 就整节跳出白名单（节内键名又不含凭据关键词、值也不是 URL 形态，两道兜底同时落空），
    # 凭据以明文回显给面板并进备份副本。判据取行为（值确实被掩码），不钉源码字面量。

    def test_variant_case_sections_are_sensitive(self) -> None:
        for section in ("cookie", "COOKIE", "Cookie", "cOoKiE", "authorization", "AUTHORIZATION"):
            assert is_sensitive_item(section, "douyin") is True, section
        # 中文节名 casefold 幂等，一并钉住「收紧口径」没有把它挤出判定
        assert is_sensitive_item("账号密码", "kuaishou") is True

    def test_non_sensitive_section_unchanged(self) -> None:
        # 反向边界（不得把收紧做成「整份配置都掩码」）：非白名单节 + 无凭据关键词的键仍明文可编辑；
        # 反向例外表（expiry/timeout/有效期/过期）也不得被节名口径牵连。
        assert is_sensitive_item("Web", "web_port") is False
        assert is_sensitive_item("web", "web_host") is False
        assert is_sensitive_item("录制设置", "推送超时时间") is False
        assert is_sensitive_item("Web", "web_token_expiry") is False

    def test_read_config_safe_masks_variant_sections(self, tmp_path: Path) -> None:
        # 端到端：面板读配置走的就是 read_config_safe，变体节名下的凭据必须回显为掩码。
        # 取值一律用脱敏样例（真实 cookie/口令不得出现在仓库里）。
        cfg = tmp_path / "config.ini"
        cfg.write_text(
            "[cookie]\ndouyin = sample-cookie-value\n[账号密码]\nkuaishou = sample-pw\n[Web]\nweb_port = 8000\n",
            encoding="utf-8",
        )
        safe = read_config_safe(cfg)
        assert safe["cookie"]["douyin"] == SENSITIVE_MASK
        assert safe["账号密码"]["kuaishou"] == SENSITIVE_MASK
        assert safe["Web"]["web_port"] == "8000"


class TestRoomUrlCommaRejectedOnWrite:
    # 写侧拒绝 URL 段含逗号（半角或全角）。两个读取侧（本模块 parse_url_config
    # 与 main.py 的房间行解析）都是 `re.split("[,，]")` **先切段再判形**，含逗号的地址一律在首个逗号
    # 处被截断后才进录制链——写侧放行等于「录入一条、生效另一条」，且 DELETE / PUT quality 按规范化
    # URL 精确匹配行，用户既看不出截断也改不动那一行。判据取 ValueError（与既有换行注入同形态）。

    def test_comma_in_url_rejected_by_validator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # DNS 一律桩住：_validate_room_url_target 对「无法解析的域名」同样抛 ValueError，
        # 不桩时本用例会被那条无关的第二 raiser 判成通过（变异验证实测：摘掉逗号守卫后
        # 三条用例仍全绿，正是这种假绿）。桩住后唯一 raiser 就是逗号守卫。
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError):
            validate_room_target("https://live.example.com/1?a=1,2")
        with pytest.raises(ValueError):
            validate_room_target("https://live.example.com/1?a=1，2")

    def test_comma_in_url_rejected_by_formatter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 唯一写入口的第二道：调用方漏调 validate_room_target 也写不出被截断的行（该同一理由）
        _stub_offline_dns(monkeypatch)
        with pytest.raises(ValueError):
            format_url_line("https://live.example.com/1?a=1,2")

    def test_comma_rejected_before_outbound_target_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 判据次序锁（同时是上面两条的归因见证）：把该域名解析写死成 OSError，
        # 若逗号裁决不在 DNS 之前，这里得到的就是「无法解析」文案而不是「含逗号」——
        # 两条 ValueError 靠文案区分，谁也不会替谁背锅。
        _stub_offline_dns(monkeypatch, {"live.example.com": OSError("unresolved")})
        with pytest.raises(ValueError, match="含逗号"):
            validate_room_target("https://live.example.com/1?a=1,2")

    def test_percent_encoded_comma_still_allowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向边界（不得把收紧做成「查询串里不许有逗号」）：URL 编码形态 %2C 不含裸逗号，
        # 照常写出且 normalize_url 不改动它
        _stub_offline_dns(monkeypatch)
        assert (
            format_url_line("https://live.example.com/1?a=1%2C2", "超清") == "超清,https://live.example.com/1?a=1%2C2"
        )

    def test_historical_comma_line_still_parses(self, tmp_path: Path) -> None:
        # 向后兼容：本轮**没有**改读取侧——老配置里已存在的含逗号行仍按旧的截断语义解析出来，
        # 既不抛异常也不整行丢弃（收紧只发生在新的写入上）。这条锁住「别顺手把读侧改成报错」，
        # 并把截断事实本身钉在测试里（name 段就是被切下来的尾段）。
        url_cfg = tmp_path / "URL_config.ini"
        url_cfg.write_text("https://live.example.com/7?a=1,2\n", encoding="utf-8-sig")
        rooms = parse_url_config(url_cfg)
        assert len(rooms) == 1
        assert rooms[0]["url"] == "https://live.example.com/7?a=1"
        assert rooms[0]["name"] == "2"
        assert rooms[0]["enabled"] is True
