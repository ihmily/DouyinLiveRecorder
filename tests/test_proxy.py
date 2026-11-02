# 保留字符时拼出结构错位的代理 URL（authority 被切成 path/query/fragment）。

import sys
from urllib.parse import unquote, urlsplit

import pytest
from pytest import MonkeyPatch

from src.proxy import ProxyDetector, ProxyInfo


class TestProxyInfo:
    # ProxyInfo 数据类的校验面。

    def test_empty_creation(self) -> None:
        info = ProxyInfo()
        assert info.ip == ""
        assert info.port == ""

    def test_valid_ip_port(self) -> None:
        info = ProxyInfo("192.168.1.1", "8080")
        assert info.ip == "192.168.1.1"
        assert info.port == "8080"

    def test_localhost_valid(self) -> None:
        info = ProxyInfo("localhost", "3128")
        assert info.ip == "localhost"
        assert info.port == "3128"

    def test_ip_without_port_raises(self) -> None:
        # 仅有 IPv4/域名无端口 → 抛异常（「填错了一半」的形态必须报错）。
        # ③ 之后唯一例外是 IPv6 字面量（见 test_bare_ipv6_without_port_ok）：旧注释承诺
        # 放行裸 IPv6、实现却被本条 raise 抢先命中，现已就地兑现。
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("192.168.1.1", "")

    def test_bare_ipv6_without_port_ok(self) -> None:
        # ③：裸 IPv6 + 空端口现在真的能通过（旧实现永远抛 ValueError）
        info = ProxyInfo("::1", "")
        assert info.ip == "::1"
        assert info.proxy_url == "http://[::1]"

    def test_port_without_ip_raises(self) -> None:
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("", "8080")

    def test_invalid_port_non_numeric(self) -> None:
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "abc")

    def test_invalid_port_out_of_range(self) -> None:
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "99999")

    def test_invalid_port_zero(self) -> None:
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "0")

    def test_invalid_ip_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid IP"):
            ProxyInfo("999.999.999.999", "8080")

    def test_valid_domain(self) -> None:
        # 合法域名作为代理地址.
        info = ProxyInfo("proxy.example.com", "8080")
        assert info.ip == "proxy.example.com"

    def test_invalid_domain_format(self) -> None:
        with pytest.raises(ValueError, match="Invalid IP"):
            ProxyInfo("inv@lid!", "8080")

    def test_port_boundary_low(self) -> None:
        info = ProxyInfo("10.0.0.1", "1")
        assert info.port == "1"

    def test_port_boundary_high(self) -> None:
        info = ProxyInfo("10.0.0.1", "65535")
        assert info.port == "65535"

    def test_frozen_dataclass(self) -> None:
        # 不可变数据类：对冻结实例赋值抛 AttributeError（FrozenInstanceError 的基类）。
        info = ProxyInfo("10.0.0.1", "8080")
        with pytest.raises(AttributeError):
            # 用 setattr 触发冻结保护，避免直接赋值依赖失效的 # type: ignore 抑制符
            setattr(info, "ip", "other")


# 代理相关环境变量：_get_proxy_info_linux / _is_proxy_enabled_linux 会读这些。测试统一用
# monkeypatch 逐个删/设，避开 patch.dict(os.environ) 整体快照回写时撞 Windows 32767 上限。
# ②：大小写两种形态都要清/设（实现同时读取两者）。：ftp_proxy / FTP_PROXY 仍在
# 清理清单（保证「本机设了 ftp 代理」可复现），但**不再是**实现的读取候选。
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


def _clear_proxy_env(monkeypatch: MonkeyPatch) -> None:
    # 清除所有代理相关环境变量，保证测试对机器环境无依赖。
    for key in _PROXY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


class TestProxyDetectorLinux:
    # ProxyDetector 的 Linux 平台方法。：_get_proxy_info_linux 的返回由 (ip, port) 元组
    # 改为 ProxyInfo——元组装不下凭据，而「认证代理无法还原完整地址」正是本条缺陷之一。

    def test_linux_get_proxy_info_with_auth(self, monkeypatch: MonkeyPatch) -> None:
        # 带认证信息的代理 URL：host/port 解析正确，且凭据被保留（不再被 split("@")[1] 丢弃）.
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://user:pass@proxy.example.com:3128/")
        info = ProxyDetector._get_proxy_info_linux()
        assert info.ip == "proxy.example.com"
        assert info.port == "3128"
        assert info.user == "user"
        assert info.password == "pass"
        # 可还原成 requests/httpx 直接可用的地址（认证代理不再丢失）
        assert info.proxy_url == "http://user:pass@proxy.example.com:3128"

    def test_linux_get_proxy_info_simple(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://10.0.0.1:8080")
        info = ProxyDetector._get_proxy_info_linux()
        assert info.ip == "10.0.0.1"
        assert info.port == "8080"
        assert info.proxy_url == "http://10.0.0.1:8080"

    def test_linux_get_proxy_info_https(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("https_proxy", "http://proxy.test:9090/")
        info = ProxyDetector._get_proxy_info_linux()
        # 取决于环境变量优先级
        assert isinstance(info.ip, str)
        assert isinstance(info.port, str)

    def test_linux_get_proxy_info_uppercase_only(self, monkeypatch: MonkeyPatch) -> None:
        # ②：只设大写 HTTP_PROXY（curl/requests 都认）时不得报「无代理」.
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:7890")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("127.0.0.1", "7890")
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is True

    def test_linux_get_proxy_info_all_proxy_fallback(self, monkeypatch: MonkeyPatch) -> None:
        # ②：只有 ALL_PROXY（无 http/https 形态）时也要能检出.
        # ⑤（附带）：本用例旧版只断言 ip/port，正好把 ② 的问题掩盖掉了——
        # socks5:// 被剥成裸 host:port 后 ip/port 看起来完全正确，只有 proxy_url
        # 才会暴露「协议被静默改写成 http://」。现按新语义补齐协议与还原地址的断言。
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("ALL_PROXY", "socks5://127.0.0.1:1080")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("127.0.0.1", "1080")
        assert info.scheme == "socks5"
        assert info.proxy_url == "socks5://127.0.0.1:1080"

    def test_linux_http_proxy_keeps_http_scheme(self, monkeypatch: MonkeyPatch) -> None:
        # 显式 http:// 与「缺省补 http://」两种来源都要还原成同一个可用地址
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:7890")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.scheme, info.proxy_url) == ("http", "http://127.0.0.1:7890")

    def test_linux_https_proxy_scheme_is_kept_too(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("https_proxy", "https://secure-proxy.example:3128")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.scheme) == ("secure-proxy.example", "https")
        assert info.proxy_url == "https://secure-proxy.example:3128"

    def test_proxy_url_brackets_bare_ipv6_host(self) -> None:
        # ③ 的连带项：无端口裸 IPv6 还原成 URL 时必须补方括号，
        # 否则 "http://::1:8080" 这类非法 authority 会让下游 requests/httpx 直接 InvalidURL
        assert ProxyInfo("::1", "8080").proxy_url == "http://[::1]:8080"
        assert ProxyInfo("[::1]", "8080").proxy_url == "http://[::1]:8080"

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows 环境变量大小写不敏感，无法同时存在两种形态")
    def test_linux_lowercase_wins_over_uppercase(self, monkeypatch: MonkeyPatch) -> None:
        # POSIX 惯例：小写优先于大写（两条取值不同时必须取小写那条）。
        # Windows 的进程环境块大小写不敏感，setenv("HTTP_PROXY") 会覆盖 setenv("http_proxy")，
        # 该优先级在 Windows 上不可观测 → 按平台跳过（CI 在 Linux 实际执行到）。
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://lower.example:1111")
        monkeypatch.setenv("HTTP_PROXY", "http://upper.example:2222")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("lower.example", "1111")

    def test_linux_bare_ipv6_no_port_is_not_picked(self, monkeypatch: MonkeyPatch) -> None:
        # 无端口的裸值不返回（ProxyInfo 校验要求 ip/port 成对），继续看下一个变量
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://10.0.0.1")
        monkeypatch.setenv("https_proxy", "http://10.0.0.2:8443")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("10.0.0.2", "8443")

    def test_linux_no_proxy(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        info = ProxyDetector._get_proxy_info_linux()
        assert info.ip == ""
        assert info.port == ""

    def test_linux_is_proxy_enabled_false(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is False

    def test_linux_is_proxy_enabled_true(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://proxy:8080")
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is True

    def test_ftp_proxy_alone_does_not_enable_proxy(self, monkeypatch: MonkeyPatch) -> None:
        # ①：只设 ftp_proxy 的机器不得被判 global_proxy=True。旧集合含 ftp_proxy →
        # 「已检测到系统代理」成立而实际取到的地址为空，9 个海外平台仍走「有代理」分支却直连境外，
        # 日志归因被彻底带偏。本仓出站请求全是 http/https，FTP 代理对本程序没有意义。
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("ftp_proxy", "ftp://10.0.0.9:21")
        monkeypatch.setenv("FTP_PROXY", "ftp://10.0.0.9:21")
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is False
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port, info.proxy_url) == ("", "", "")

    def test_read_set_excludes_ftp_proxy(self) -> None:
        # 结构锁：候选元组里不得再出现 ftp 形态（注释承诺与实现同源，见上文①）
        assert ProxyDetector._LINUX_PROXY_ENV_NAMES == ("http_proxy", "https_proxy", "all_proxy")

    def test_linux_proxy_with_trailing_slash(self, monkeypatch: MonkeyPatch) -> None:
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://proxy.example.com:8080/")
        info = ProxyDetector._get_proxy_info_linux()
        assert info.ip == "proxy.example.com"
        assert info.port == "8080"

    def test_linux_ipv6_bracket_env(self, monkeypatch: MonkeyPatch) -> None:
        # ①：环境变量里的 [:1]:8080 形态同样必须解析成功（IPv6 回环代理）.
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://[::1]:8080")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port) == ("[::1]", "8080")
        assert info.proxy_url == "http://[::1]:8080"


class TestSplitHostPort:
    # host/port/凭据拆解的形态表（Windows 注册表与环境变量两条路径共用同一实现）。
    @pytest.mark.parametrize(
        ("raw", "ip", "port", "user", "password"),
        [
            # 括号 IPv6（注册表 ProxyServer 的实际写法）：旧实现 split(":", 1) 会切成
            # ip="["、port=":1]:8080" → ProxyInfo 校验抛 ValueError
            ("[::1]:8080", "[::1]", "8080", "", ""),
            ("[2001:db8::1]:3128", "[2001:db8::1]", "3128", "", ""),
            # 裸 IPv6（无方括号）：整串作 ip，不误切成端口
            ("::1", "::1", "", "", ""),
            # 常规形态
            ("127.0.0.1:7890", "127.0.0.1", "7890", "", ""),
            ("proxy.example.com:3128", "proxy.example.com", "3128", "", ""),
            ("proxy.example.com", "proxy.example.com", "", "", ""),
            # 认证代理：凭据必须保留（旧实现 split("@", 1)[1] 直接丢弃）
            ("user:pass@10.0.0.1:8080", "10.0.0.1", "8080", "user", "pass"),
            ("user:pass@[::1]:8080", "[::1]", "8080", "user", "pass"),
            ("u2:p@ss@10.0.0.1:80", "10.0.0.1", "80", "u2", "p@ss"),
            ("name@10.0.0.1:80", "10.0.0.1", "80", "name", ""),
            ("", "", "", "", ""),
        ],
    )
    def test_shapes(self, raw: str, ip: str, port: str, user: str, password: str) -> None:
        assert ProxyDetector._split_host_port(raw) == (ip, port, user, password)

    def test_ipv6_bracket_proxy_info_validates(self) -> None:
        # 括号形态必须能通过 ProxyInfo 的校验分支（旧实现下该校验整块是死代码）
        info = ProxyInfo(*ProxyDetector._split_host_port("[::1]:8080"))
        assert info.ip == "[::1]"
        assert info.port == "8080"

    def test_credentials_not_in_repr(self) -> None:
        # 凭据不得随 repr 进日志（本仓凭据红线：logs 轮转保留多份＝凭据长期落盘）
        info = ProxyInfo("10.0.0.1", "8080", "user", "secret-pass")
        assert "secret-pass" not in repr(info)
        assert "user" not in repr(info)
        assert info.proxy_url == "http://user:secret-pass@10.0.0.1:8080"


# ── ：proxy_url 的 userinfo 必须 percent 编码 ──────────────────────────────
# 凭据按字面原文存进 ProxyInfo（_split_host_port 从不 unquote），直拼进 URL 时保留字符会重排结构：
# '#' 起 fragment、'?' 起 query、'/' 起 path，authority 整段被丢——实测 urlsplit('http://u:p#ss@10.0.0.1:8080')
# 交出 host='ss'、port=None。判据是「解回的用户名/口令与原文逐字相等且 host/port 不受影响」。
class TestProxyUrlPercentEncodesCredentials:
    @pytest.mark.parametrize(
        ("user", "password"),
        [
            ("u", "p@ss"),  # '@'：靠最后一个 @ 切分侥幸能用，仍属非法形态
            ("u", "pa/ss"),  # '/'：authority 之后被当 path
            ("u", "pa?ss"),  # '?'：被当 query
            ("u", "pa#ss"),  # '#'：被当 fragment
            ("bob", "p%40ss"),  # 字面 %40（safe='' 下不得被当转义序列）
            ("50%off", "50%off"),  # 用户名位同样含保留字符
            ("u ser", "a b"),  # 空白
            ("u:x", "x:y"),  # 冒号
        ],
    )
    def test_reserved_chars_survive_round_trip(self, user: str, password: str) -> None:
        info = ProxyInfo("10.0.0.1", "8080", user, password)
        url = info.proxy_url
        parts = urlsplit(url)
        assert parts.hostname == "10.0.0.1", f"host 被凭据里的保留字符带跑：{url}"
        assert parts.port == 8080
        assert not parts.path and not parts.query and not parts.fragment
        assert unquote(parts.username or "") == user
        assert unquote(parts.password or "") == password

    def test_reserved_chars_do_not_reach_the_authority_delimiters(self) -> None:
        # 分隔结构不能被动过：整条 URL 只允许出现一个 '@'（userinfo 与 host 的分界）
        url = ProxyInfo("proxy.example.com", "3128", "u", "p@ss/w#?%").proxy_url
        assert url.count("@") == 1
        assert url == "http://u:p%40ss%2Fw%23%3F%25@proxy.example.com:3128"

    def test_downstream_httpx_accepts_encoded_credentials(self) -> None:
        # 交付面实测：修复前 httpx.URL 对 'pa/ss' 直接抛 InvalidURL（'Invalid port: pa'）
        try:
            import httpx
        except ImportError:  # pragma: no cover - httpx 在运行时清单内
            pytest.skip("httpx 未安装")
        info = ProxyInfo("10.0.0.1", "8080", "u", "pa/ss?k#p%40")
        url = httpx.URL(info.proxy_url)
        assert url.host == "10.0.0.1"
        assert url.port == 8080
        assert url.password == "pa/ss?k#p%40"

    def test_env_var_with_reserved_chars_end_to_end(self, monkeypatch: MonkeyPatch) -> None:
        # 端到端：环境变量里字面写出的口令（含 '@'）经解析→还原，凭据仍能被正确解出
        _clear_proxy_env(monkeypatch)
        monkeypatch.setenv("http_proxy", "http://u:p@ss@proxy.example.com:3128")
        info = ProxyDetector._get_proxy_info_linux()
        assert (info.ip, info.port, info.user, info.password) == ("proxy.example.com", "3128", "u", "p@ss")
        assert info.proxy_url == "http://u:p%40ss@proxy.example.com:3128"
        assert unquote(urlsplit(info.proxy_url).password or "") == "p@ss"

    def test_no_credentials_url_shape_unchanged(self) -> None:
        # 无凭据形态不得被顺手改写（本仓另有 6 处用例逐字钉住 proxy_url 的字面形状）
        assert ProxyInfo("10.0.0.1", "8080").proxy_url == "http://10.0.0.1:8080"
        # 无 ip 才是「没有代理」；ip 空 + port 非空是 __post_init__ 刻意拒绝的半填形态
        assert ProxyInfo().proxy_url == ""
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("", "8080")
