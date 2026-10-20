# src/sync_http.py 同步 HTTP 客户端的回归锁。
# 全程 mock 底层 opener / 线程内 Session / urlopen，不触网；按 ssl_verify 与是否走代理分流两条实现路径，
# 断言覆盖编码分支（dict→表单 / 字符串 / json）、gzip 解压、重定向取 URL、错误返回空串且记日志等契约。
# 非代理路径 patch _get_opener，代理路径 patch 线程内 Session 工厂 _session，避免触网且精准命中实现层。

import gzip
import http.client
import json
import ssl
import urllib.request
from io import BytesIO
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from src.sync_http import (
    _get_insecure_opener,
    _get_opener,
    _opener_secure,
    _resolve_ssl_verify,
    session,
    sync_req,
)


def _opener_https_context(opener: urllib.request.OpenerDirector) -> ssl.SSLContext:
    # 取 opener 上那一支 HTTPSHandler 实际使用的 SSLContext。
    # 为什么要专门写这个小助手：urllib 的 build_opener() **总会**补齐默认 handler，
    # 所以「有没有 HTTPSHandler」区分不出两支 opener（安全支也带一支默认 context 的），
    # 真正有语义的判据是它挂的 context 校验不校验证书。
    # CPython 3.14 里该属性名是私有的 `_context`（更早版本为 `context`）——两个都试，
    # 都取不到即判失败而不是跳过，否则属性一改名这条锁就静默失效（又一处假绿）。
    # typeshed 没声明 OpenerDirector.handlers（运行时确有该属性）→ 用 cast 收窄，
    # 不用三参 getattr：后者返回 Any，会让后面的 isinstance 过滤一起失去检查。
    handlers = cast("list[object]", getattr(opener, "handlers"))
    https_handlers = [h for h in handlers if isinstance(h, urllib.request.HTTPSHandler)]
    assert len(https_handlers) == 1, f"opener 上应恰好一支 HTTPSHandler：{https_handlers}"
    handler = https_handlers[0]
    context: ssl.SSLContext | None = getattr(handler, "_context", None) or getattr(handler, "context", None)
    assert context is not None, "HTTPSHandler 上取不到 SSLContext（urllib 内部改名？需同步本用例）"
    return context


class TestGetOpener:
    # MID-2266 附带核对：两条用例原先只 `assert opener is not None`——把 _get_opener 的
    # 两个分支合并成「恒返回 insecure opener」也会同时全绿，等于没锁「按 ssl_verify 分流」
    # 这条安全不变量（F-12 的惰性降级面）。现按**对象同一性**断言命中的是哪一支 opener，
    # 并直接查各支 HTTPSHandler 实际挂上的 SSLContext.verify_mode。

    @patch("src.sync_http.config")
    # ssl_verify=True 须返回标准安全 opener，与默认生产环境一致
    def test_ssl_verify_true_returns_secure_opener(self, mock_config: MagicMock) -> None:
        mock_config.ssl_verify = True
        assert _get_opener() is _opener_secure, "全局要求校验证书时必须用安全 opener"
        context = _opener_https_context(_opener_secure)
        assert context.verify_mode == ssl.CERT_REQUIRED, "安全 opener 的 context 必须校验证书链"
        assert context.check_hostname is True, "安全 opener 的 context 必须校验主机名"

    @patch("src.sync_http.config")
    def test_ssl_verify_false_returns_insecure_opener(self, mock_config: MagicMock) -> None:
        mock_config.ssl_verify = False
        opener = _get_opener()
        assert opener is _get_insecure_opener(), "降级分支必须命中惰性构造的那一支（不得每次新建）"
        assert opener is not _opener_secure, "两分支返回同一对象即说明分流被合并（假绿本体）"
        # 惰性构造的 insecure opener 必须真的带上 CERT_NONE，否则「降级」只是换了个对象
        assert _opener_https_context(opener).verify_mode == ssl.CERT_NONE

    @patch("src.sync_http.config")
    def test_explicit_override_beats_global_switch(self, mock_config: MagicMock) -> None:
        # F-12 的单次覆盖语义：显式传值以该次调用为准，不被全局开关拖下水
        # （凭据类调用点可强制校验）。判据同样是对象同一性，不是「非 None」。
        mock_config.ssl_verify = False
        assert _get_opener(True) is _opener_secure
        mock_config.ssl_verify = True
        assert _get_opener(False) is _get_insecure_opener()


# sync_req 同步请求入口：按 ssl_verify 与是否走代理分流两条实现路径。
# 守卫编码分支、gzip 解压、重定向取 URL、错误返回空串且记日志等契约。
class TestSyncReq:
    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    # 正常 GET 路径：解码响应体返回字符串，且用后必须 close 一次释放连接
    def test_basic_get_request(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"hello world"
        mock_response.url = "http://example.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com")
        assert result == "hello world"
        mock_response.close.assert_called_once()

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_gzip_response(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # Content-Encoding=gzip 时必须透明解压出原文，调用方无需感知压缩
        # gzip 解压响应.
        mock_config.ssl_verify = True
        original_data = b"compressed content"
        compressed = gzip.compress(original_data)

        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": "gzip"}
        mock_response.read.return_value = compressed
        mock_response.url = "http://example.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com")
        assert result == "compressed content"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_redirect_url_returns_url(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # redirect_url=True 时返回重定向后的最终 URL
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.url = "http://redirected.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com", redirect_url=True)
        assert result == "http://redirected.com"

    # 代理分支走线程内复用的 Session（_session()），故 patch 该工厂函数而非 requests 模块本身。
    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_proxy_get_request(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 经 _session 工厂拿线程内 Session，断言 session.get 被调用一次且返回其 text
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        # M-18（2026-10-19）：代理分支改为 stream=True + iter_content 分块计数，响应体不再取
        # .text（requests 会先无上限地全量解码）。替身因此要给 iter_content 供块、并给出
        # headers（上限选择依赖 Content-Encoding）。
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"proxy response"]
        mock_response.url = "http://example.com"
        mock_session.get.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080")
        assert result == "proxy response"
        mock_session.get.assert_called_once()

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_proxy_post_request(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 同 test_proxy_get_request 经 _session 工厂，断言 session.post 被调用一次并返回其内容
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        # M-18（同 test_proxy_get_request）：体走 iter_content 分块交付
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"post response"]
        mock_response.url = "http://example.com"
        mock_session.post.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", data={"key": "val"})
        assert result == "post response"
        mock_session.post.assert_called_once()

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    # 代理 + redirect_url：返回重定向后的最终 URL
    def test_proxy_redirect_url(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        mock_response.url = "http://final.com"
        mock_session.get.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", redirect_url=True)
        assert result == "http://final.com"

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_proxy_post_with_json_data(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 带代理的 JSON POST 请求.
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        # M-18（同 test_proxy_get_request）：体走 iter_content 分块交付
        mock_response.headers = {}
        mock_response.iter_content.return_value = [b"json response"]
        mock_response.url = "http://example.com"
        mock_session.post.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", json_data={"a": 1})
        assert result == "json response"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_post_data_dict_encoding(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # dict 型 data 必须被 urlencode 为表单体（application/x-www-form-urlencoded）
        # dict 类型 data 被 URL 编码.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"ok"
        mock_response.url = "http://example.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com", data={"key": "value"})
        assert result == "ok"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_post_data_string_encoding(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # 字符串类型 data 被编码.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"ok"
        mock_response.url = "http://example.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com", data="raw_data")
        assert result == "ok"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    # json_data 须被 JSON 序列化后作为请求体发送
    def test_json_data_encoding(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # json_data 被 JSON 编码后发送.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"json ok"
        mock_response.url = "http://example.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com", json_data={"key": "val"})
        assert result == "json ok"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_http_error_400_returns_body(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # HTTP 400 错误返回响应体.
        mock_config.ssl_verify = True
        mock_error = MagicMock()
        mock_error.code = 400
        mock_error.read.return_value = b"bad request"
        mock_error.close = MagicMock()

        import urllib.error

        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.HTTPError(
            "http://example.com", 400, "Bad Request", http.client.HTTPMessage(), BytesIO(b"bad request")
        )
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com")
        assert "bad request" in result

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_http_error_400_oversized_body_hits_read_cap(
        self, mock_opener_fn: MagicMock, mock_config: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # M-03（2026-10-18 审查）回归锁：400 分支必须与成功路径同走 _read_capped——
        # 原实现 `e.read()` 无参全量读，超大 400 错误体直接威胁进程内存（对端给多少申请多少）。
        # 超限后的失败语义按既有契约收敛为空串 + 脱敏 error 日志（不得抛穿、不得截断放行）。
        # 上限经 monkeypatch 压低（不构造 8MB 真体）；变异验证（把 _read_capped 退回 e.read()）
        # 本用例必须转红。
        mock_config.ssl_verify = True
        monkeypatch.setattr("src.sync_http._MAX_RESPONSE_BYTES", 16)

        import urllib.error

        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.HTTPError(
            "http://example.com", 400, "Bad Request", http.client.HTTPMessage(), BytesIO(b"x" * 100)
        )
        mock_opener_fn.return_value = mock_opener

        with patch("src.sync_http.logger") as mock_logger:
            result = sync_req("http://example.com")
        assert result == ""
        assert any("sync_req 请求失败" in str(c.args) for c in mock_logger.error.call_args_list)

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    # URLError 不再伪装为响应体：返回空串并记录 warning/error 日志
    def test_url_error_returns_empty_and_logs(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # URLError 不再伪装为响应体：返回空串并记录错误日志.
        import urllib.error
        from unittest.mock import call

        mock_config.ssl_verify = True
        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.URLError("connection refused")
        mock_opener_fn.return_value = mock_opener

        with patch("src.sync_http.logger") as mock_logger:
            result = sync_req("http://example.com")
            # L-27（2026-10-19）：同一次失败现在只落**一条** error（最外层统一失败分支）。
            # 原实现在内层还有两条「记一条 + 原样上抛」，于是同一次请求固定产生
            # warning + error + error 三条日志；三条都只描述同一件事，纯属浪费轮转容量。
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_called_once()
        assert result == ""
        assert "connection refused" not in result

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_abroad_request(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # abroad=True 走 urlopen 分支
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"abroad ok"
        mock_response.url = "http://example.com"

        with patch("src.sync_http.urllib.request.urlopen", return_value=mock_response) as mock_urlopen:
            result = sync_req("http://example.com", abroad=True)
            assert result == "abroad ok"
            mock_urlopen.assert_called_once()

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_abroad_redirect_url(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # abroad=True 且 redirect_url=True：走 urlopen 并返回重定向后的 URL
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.url = "http://redirected.com"

        with patch("src.sync_http.urllib.request.urlopen", return_value=mock_response):
            result = sync_req("http://example.com", abroad=True, redirect_url=True)
            assert result == "http://redirected.com"

    @patch("src.sync_http.config")
    # opener 抛任意异常时须返回空串 + 记 error 日志，且不把异常文本当响应体泄漏
    def test_general_exception_returns_empty_and_logs(self, mock_config: MagicMock) -> None:
        # opener 抛任意异常时须返回空串 + 记 error 日志，且不得把异常文本当响应体泄漏
        # 一般异常被捕获：记录错误日志并返回空串，而非错误文本.
        mock_config.ssl_verify = True
        # 让 opener 抛异常
        with patch("src.sync_http._get_opener", side_effect=Exception("unexpected")):
            with patch("src.sync_http.logger") as mock_logger:
                result = sync_req("http://example.com")
                # 错误被记录（至少一次），且末尾不再以错误文本伪装响应体
                assert mock_logger.error.call_count >= 1
                assert any("sync_req 请求失败" in str(c.args) for c in mock_logger.error.call_args_list)
        assert result == ""
        assert "unexpected" not in result


# F-12：CERT_NONE 上下文 / opener 惰性化 + 单次请求 ssl_verify 覆盖。
# 契约：①不校验证书的对象只在真正需要时创建；②显式覆盖优先于控制面全局开关；
# ③覆盖值必须透传到 urllib 与 requests（代理）两条实现路径。
class TestSslVerifyScoping:
    @patch("src.sync_http.config")
    def test_resolve_ssl_verify_follows_global_when_no_override(self, mock_config: MagicMock) -> None:
        # 未指定覆盖时跟随控制面全局开关（向后兼容现状语义）
        mock_config.ssl_verify = True
        assert _resolve_ssl_verify(None) is True
        mock_config.ssl_verify = False
        assert _resolve_ssl_verify(None) is False

    def test_resolve_ssl_verify_override_wins(self) -> None:
        # 显式覆盖优先于全局开关：凭据类调用点可强制校验，不受全局降级影响
        assert _resolve_ssl_verify(True) is True
        assert _resolve_ssl_verify(False) is False

    def test_insecure_context_is_built_lazily_and_cached(self) -> None:
        # 惰性：未走到降级分支前不构造 CERT_NONE 上下文（import 期常驻是 F-12 的根因）
        import importlib

        import src.sync_http as sync_http_mod

        reloaded = importlib.reload(sync_http_mod)
        assert reloaded._ssl_context_insecure is None
        assert reloaded._opener_insecure is None
        ctx = reloaded._get_insecure_context()
        assert ctx.verify_mode is ssl.CERT_NONE
        assert ctx.check_hostname is False
        # 缓存：同一进程内重复取应为同一对象，避免每次请求重建上下文
        assert reloaded._get_insecure_context() is ctx

    @patch("src.sync_http.config")
    def test_get_opener_override_forces_secure_even_when_global_disabled(self, mock_config: MagicMock) -> None:
        # 全局关闭校验时，显式传 True 的调用仍须走安全 opener（控制面恒校验的落点）
        # 注意：上方惰性用例 reload 过本模块，模块级 _opener_secure 已换新对象，
        # 故此处按运行时属性取，不用 import 期绑定的名字（否则跨用例比较到旧对象）
        from src import sync_http as sync_http_mod

        mock_config.ssl_verify = False
        assert _get_opener(True) is sync_http_mod._opener_secure
        assert _get_opener() is sync_http_mod._get_insecure_opener()
        assert _get_opener(False) is not sync_http_mod._opener_secure

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_sync_req_forwards_override_to_opener(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # 覆盖值必须透传给 _get_opener，而不是被丢弃后退回全局开关
        mock_config.ssl_verify = False
        mock_response = MagicMock()
        mock_response.headers.get.return_value = None
        mock_response.read.return_value = b"ok"
        mock_opener_fn.return_value.open.return_value = mock_response
        sync_req("http://example.com", ssl_verify=True)
        mock_opener_fn.assert_called_once_with(True)
        mock_response.close.assert_called_once()

    @patch("src.sync_http.config")
    @patch("src.sync_http._session")
    def test_sync_req_forwards_override_to_proxied_session(
        self, mock_session_fn: MagicMock, mock_config: MagicMock
    ) -> None:
        # 代理路径走 requests.Session：verify 必须同为裁决后的值（两条路径口径一致）
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session.get.return_value.text = "ok"
        mock_session_fn.return_value = mock_session
        sync_req("http://example.com", proxy_addr="http://127.0.0.1:1", ssl_verify=False)
        _args, kwargs = mock_session.get.call_args
        assert kwargs["verify"] is False


# MID-27（2026-09-20）：代理地址归一必须与异步侧同址同语义。
# 配置项「代理地址」由 read_config_value 原样读入，用户普遍写裸 127.0.0.1:7890；
# 归一缺失时 requests 抛 InvalidSchema/InvalidURL，被外层 except 吞成空串
# ——本仓列为最难归因的失败形态（「开代理后 sync 解析全失败、async 正常」）。
class TestProxyAddrNormalization:
    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_bare_ip_port_gets_http_scheme(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 裸 ip:port 必须被补成 http://ip:port 再交给 requests
        mock_config.ssl_verify = True
        session_obj = MagicMock()
        session_obj.get.return_value.text = "ok"
        mock_session_fn.return_value = session_obj
        sync_req("http://example.com", proxy_addr="127.0.0.1:7890")
        _args, kwargs = session_obj.get.call_args
        assert kwargs["proxies"] == {"http": "http://127.0.0.1:7890", "https": "http://127.0.0.1:7890"}

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_prefixed_proxy_left_untouched(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 已带协议前缀（含 socks5）时不得二次补前缀
        mock_config.ssl_verify = True
        session_obj = MagicMock()
        session_obj.get.return_value.text = "ok"
        mock_session_fn.return_value = session_obj
        sync_req("http://example.com", proxy_addr="socks5://127.0.0.1:1080")
        _args, kwargs = session_obj.get.call_args
        assert kwargs["proxies"]["http"] == "socks5://127.0.0.1:1080"

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_proxy_post_branch_uses_normalized_addr(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # POST 分支同样归一（两条分支共用一次归一，不能只修 GET）
        mock_config.ssl_verify = True
        session_obj = MagicMock()
        session_obj.post.return_value.text = "ok"
        mock_session_fn.return_value = session_obj
        sync_req("http://example.com", proxy_addr="127.0.0.1:7890", data={"k": "v"})
        _args, kwargs = session_obj.post.call_args
        assert kwargs["proxies"]["https"] == "http://127.0.0.1:7890"

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_empty_proxy_stays_direct(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 空串代理视为未配置：仍走直连分支（handle_proxy_addr 返回 None）
        mock_config.ssl_verify = True
        sync_req("http://example.com", proxy_addr="")
        mock_session_fn.assert_not_called()


# MIN-08 的配套出口：需要状态码的调用点（Weverse 等凭据端点）经 session() 复用同一
# 线程级 Session，而不是绕过本模块直接 requests.post。
class TestSharedSessionAccessor:
    @patch("src.sync_http._session")
    def test_session_wrapper_delegates_to_thread_local_factory(self, mock_session_fn: MagicMock) -> None:
        expected = MagicMock()
        mock_session_fn.return_value = expected
        assert session() is expected
        mock_session_fn.assert_called_once()
