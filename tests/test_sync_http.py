# src/sync_http.py 同步 HTTP 客户端的回归锁。
# 全程 mock 底层 opener / 线程内 Session / urlopen，不触网；按 ssl_verify 与是否走代理分流两条实现路径，
# 断言覆盖编码分支（dict→表单 / 字符串 / json）、gzip 解压、重定向取 URL、错误返回空串且记日志等契约。
# 非代理路径 patch _get_opener，代理路径 patch 线程内 Session 工厂 _session，避免触网且精准命中实现层。

import contextlib
import gzip
import http.client
import http.server
import json
import ssl
import threading
import types
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from io import BytesIO
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.sync_http import _get_insecure_opener, _get_opener, _opener_secure, _resolve_ssl_verify, session, sync_req


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
    # 附带核对：两条用例原先只 `assert opener is not None`——把 _get_opener 的
    # 两个分支合并成「恒返回 insecure opener」也会同时全绿，等于没锁「按 ssl_verify 分流」
    # 这条安全不变量（该惰性降级面）。现按**对象同一性**断言命中的是哪一支 opener，
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
        # 单次覆盖语义：显式传值以该次调用为准，不被全局开关拖下水
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
        # 代理分支改为 stream=True + iter_content 分块计数，响应体不再取
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
        # （同 test_proxy_get_request）：体走 iter_content 分块交付
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
        # （同 test_proxy_get_request）：体走 iter_content 分块交付
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
        # 回归锁：400 分支必须与成功路径同走 _read_capped——
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
            # 同一次失败现在只落**一条** error（最外层统一失败分支）。
            # 原实现在内层还有两条「记一条 + 原样上抛」，于是同一次请求固定产生
            # warning + error + error 三条日志；三条都只描述同一件事，纯属浪费轮转容量。
            mock_logger.warning.assert_not_called()
            mock_logger.error.assert_called_once()
        assert result == ""
        assert "connection refused" not in result

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    # residual：落地复核现在也走 DNS 判定链（_redirect_hop_rejection_reason 内含
    # internal_stream_target_reason），故这两条用例统一挂 _public_dns seam，不再依赖本机真实解析——
    # 「redirected.com」这类名字在无外网环境解析失败会被判「主机名无法解析」而拒绝，属判定生效而非回归。
    def test_abroad_request(self, mock_opener_fn: MagicMock, mock_config: MagicMock, _public_dns: None) -> None:
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
    def test_abroad_redirect_url(self, mock_opener_fn: MagicMock, mock_config: MagicMock, _public_dns: None) -> None:
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


# CERT_NONE 上下文 / opener 惰性化 + 单次请求 ssl_verify 覆盖。
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
        # 惰性：未走到降级分支前不构造 CERT_NONE 上下文（import 期常驻是该根因）
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


# 代理地址归一必须与异步侧同址同语义。
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


# 配套出口：需要状态码的调用点（Weverse 等凭据端点）经 session() 复用同一
# 线程级 Session，而不是绕过本模块直接 requests.post。
class TestSharedSessionAccessor:
    @patch("src.sync_http._session")
    def test_session_wrapper_delegates_to_thread_local_factory(self, mock_session_fn: MagicMock) -> None:
        expected = MagicMock()
        mock_session_fn.return_value = expected
        assert session() is expected
        mock_session_fn.assert_called_once()


# ─────────────────────────────────────────────────────────────
# （CODE_REVIEW 2026-10-21）：同步通道的内网闸门
# ─────────────────────────────────────────────────────────────
# 判据复用 async_http.internal_stream_target_reason（唯一事实源），本组只锁「有没有接上」与
# 「接在哪条路径上」，不复刻内网名单。打桩边界与 wp_b_netguard 同口径：只钉 DNS seam
# （web_config._resolve_host_ips），判定、handler、opener 一律走真实代码；内网目标一律写成
# IP 字面量，判定不依赖解析。断言落在「出站请求有没有发出」上——替身抛错会被外层统一 except
# 吞成空串，反而让「闸门被摘掉」的形态照样绿。
#
# 逐跳复核的端到端形态走本地 http.server（真实 opener、真 HTTPHandler + 真守卫 handler）：
# 判据是「服务器有没有收到第二跳」，而不是某个替身被调用了几次。入口地址写 127.0.0.1，但入口
# 闸门会先把它拒掉（入口与逐跳本来就是两层），故本组用例里把 _redirect_hop_rejection_reason
# 包一层：入口那次判定直接放行，**落地那次照旧走生产判定**——这样才测得到逐跳这一层。
_LOCAL_PUBLIC_IP = "93.184.216.34"


class _RedirectServer:
    def __init__(self, location: str) -> None:
        self.location = location
        self.landing_hits = 0
        self.request_paths: list[str] = []


@contextlib.contextmanager
def _running_redirect(location: str) -> Iterator[tuple[str, _RedirectServer]]:
    # 产出 (入口地址, 服务器状态)；location 里的 {port} 占位符按实际端口展开。
    state = _RedirectServer(location)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定名
            state.request_paths.append(self.path)
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", state.location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            state.landing_hits += 1
            body = b"LANDING-BODY"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *_args: object) -> None:
            # 形参名沿用基类签名（basedpyright reportIncompatibleMethodOverride 要求）；
            # 这里只是静音测试服务的访问日志，不格式化。
            return None

    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = int(server.server_address[1])
    state.location = location.format(port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/start", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)
        # 并发用例口径：join 之后必须断言线程真的退出了（AGENTS「测试编写强制约定」）
        assert not thread.is_alive()


@pytest.fixture
def _public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    from src import web_config

    monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_LOCAL_PUBLIC_IP])


@pytest.fixture
def _bypass_entry_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    # 只让**入口**那次判定放行；落地那次仍调生产判定（见文件上方的说明）。
    import src.sync_http as sync_http_mod

    real = cast(Callable[[str], "str | None"], vars(sync_http_mod)["_redirect_hop_rejection_reason"])
    seen: list[str] = []

    def _gate(url: str) -> str | None:
        seen.append(url)
        # 入口是第一个被判定的地址：放行它，后续（重定向落地）走真实判定
        if len(seen) == 1:
            return None
        return real(url)

    monkeypatch.setattr(sync_http_mod, "_redirect_hop_rejection_reason", _gate)


def _assert_direct_target_refused(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # 直连路径：opener.open 一个字节都不发（不是「发了再丢」，也不是「读完再删」）。
    fake_resp = MagicMock()
    fake_resp.headers = {"Content-Encoding": ""}
    fake_resp.read.return_value = b"INTERNAL-SERVICE-BODY"
    fake_resp.url = url
    opener_spy = MagicMock()
    opener_spy.open.return_value = fake_resp
    monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
    with patch("src.sync_http.logger") as mock_logger:
        assert sync_req(url) == ""
    opener_spy.open.assert_not_called()
    fake_resp.read.assert_not_called()
    assert "sync_req 请求失败" in str(mock_logger.error.call_args_list), "拒绝路径必须落既有失败分支"


class TestSyncReqInternalTargetGate:
    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:6379/",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5:8080/api",
            "http://[::1]:11211/",
            "http://metadata.google.internal/computeMetadata/v1/",
        ],
    )
    def test_direct_call_refuses_internal_targets_before_sending(
        self, url: str, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _assert_direct_target_refused(url, monkeypatch)

    def test_dns_resolved_internal_name_is_refused(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        # 域名形态：判定必须走本机解析结果（与异步侧同一条 internal_stream_target_reason 路径），
        # 不能在「看起来是域名」这一步就放行。
        from src import web_config

        monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: ["127.0.0.1"])
        _assert_direct_target_refused("http://intranet.example.com/redis", monkeypatch)

    def test_proxied_branch_refuses_before_touching_session(
        self, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 代理分支同样受保护：否则「配了代理」就成了闸门的绕道口，且 http 代理按绝对 URI 转发，
        # 回环目标经代理照样可达。判据是「Session 拿到请求没有」。
        session_spy = MagicMock()
        monkeypatch.setattr("src.sync_http._session", lambda: session_spy)
        assert sync_req("http://127.0.0.1:6379/", proxy_addr="127.0.0.1:7890") == ""
        session_spy.get.assert_not_called()
        session_spy.post.assert_not_called()

    def test_public_host_still_works(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：闸门不得把正常公网请求一起挡掉（否则该就成了新的漏录根因）。
        fake_resp = MagicMock()
        fake_resp.headers = {"Content-Encoding": ""}
        fake_resp.read.return_value = b"body"
        fake_resp.url = "https://api.example.com/live"
        opener_spy = MagicMock()
        opener_spy.open.return_value = fake_resp
        monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
        assert sync_req("https://api.example.com/live") == "body"
        opener_spy.open.assert_called_once()

    def test_rejection_log_masks_credentials(self, _public_dns: None) -> None:
        # 用项目 logger（src/logger.py）而非 `from loguru import logger as X`：全仓钉了
        # 「不得给 logger 起别名」的形态锁，别名会同时绕过 i18n 门禁。
        from src.logger import logger

        lines: list[str] = []
        handler_id = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
        try:
            assert sync_req("http://s3cret-token@127.0.0.1:6379/") == ""
        finally:
            logger.remove(handler_id)
        joined = "\n".join(lines)
        assert "s3cret-token" not in joined
        assert "127.0.0.1" in joined, "拒绝必须留线索，不能静默吞掉"


class TestSyncReqRedirectHopGate:
    # 逐跳复核：落地地址必须过同一份判据，且拦断发生在**发起下一跳之前**。

    @pytest.mark.parametrize(
        "location",
        [
            "http://127.0.0.1:{port}/next",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.5:8080/api",
            "file:///etc/passwd",
        ],
    )
    def test_redirect_to_internal_target_never_reaches_it(
        self, location: str, _public_dns: None, _bypass_entry_gate: None
    ) -> None:
        with _running_redirect(location) as (entry, server):
            with patch("src.sync_http.logger") as mock_logger:
                assert sync_req(entry) == ""
            # 第二跳一个请求都没发：既不是「发了再丢响应」，也不是「读完再删」
            assert server.landing_hits == 0
            assert server.request_paths == ["/start"]
            assert "sync_req 请求失败" in str(mock_logger.error.call_args_list)

    def test_redirect_to_public_url_still_followed(
        self, monkeypatch: pytest.MonkeyPatch, _bypass_entry_gate: None
    ) -> None:
        # 反向锁：白名单内的落地地址照旧跟随，响应体照旧交给调用方——闸门不得误杀正常跳转。
        # 落地写公网域名、DNS seam 返回公网 IP，再把真正的建连（HTTPConnection.connect）钉到本机
        # 服务器：这样「判定放行」与「真的按落地地址去连」同时成立，用例仍然不出网。
        from src import web_config

        real_connect = http.client.HTTPConnection.connect
        connected: list[str] = []

        def _connect(self: http.client.HTTPConnection) -> None:
            connected.append(str(self.host))
            # setattr 而非直赋：mypy 的 method-assign 禁止对类属性方法直接赋值。
            setattr(http.client.HTTPConnection, "connect", real_connect)  # 只改写真正那一跳
            try:
                self.host, self.port = "127.0.0.1", int(target_port[0])
                real_connect(self)
            finally:
                setattr(http.client.HTTPConnection, "connect", _connect)

        target_port = [0]
        with _running_redirect("http://cdn.example.com:{port}/next") as (entry, server):
            target_port[0] = int(server.location.rsplit(":", 1)[1].split("/")[0])
            monkeypatch.setattr(web_config, "_resolve_host_ips", lambda host: [_LOCAL_PUBLIC_IP])
            monkeypatch.setattr(http.client.HTTPConnection, "connect", _connect)
            assert sync_req(entry) == "LANDING-BODY"
            assert connected[-1] == "cdn.example.com", connected
            assert server.landing_hits == 1

    def test_guard_handler_itself_refuses_internal_landing(self, _public_dns: None) -> None:
        # 直接作用在生产 handler 类上（不经 sync_req）：落地地址命中内网/非白名单协议即抛
        # URLError，且异常文本已脱敏。
        import src.sync_http as sync_http_mod

        handler = sync_http_mod._HopGuardRedirectHandler()
        req = urllib.request.Request("https://start.example.com/x")
        # fp / headers 只在放行路径上被 super().redirect_request 使用；拒绝路径不读它们，
        # 但形参类型要求具体对象，故给真实替身而非 None。
        fp = BytesIO(b"")
        headers = http.client.HTTPMessage()
        for landing in ("http://127.0.0.1:6379/", "file:///etc/passwd", "http://169.254.169.254/x"):
            with pytest.raises(urllib.error.URLError) as excinfo:
                handler.redirect_request(req, fp, 302, "Found", headers, landing)
            assert "重定向逐跳复核拒绝落地目标" in str(excinfo.value)
        with pytest.raises(urllib.error.URLError) as masked:
            handler.redirect_request(req, fp, 302, "Found", headers, "http://u:s3cret@127.0.0.1/x")
        assert "s3cret" not in str(masked.value)

    def test_handler_is_registered_on_both_openers(self) -> None:
        # 结构锁：两支预构建 opener 挂的必须是守卫子类，裸 HTTPRedirectHandler 不得回归。
        for opener in (_opener_secure, _get_insecure_opener()):
            handlers = cast("list[object]", getattr(opener, "handlers"))
            assert not any(
                type(h) is urllib.request.HTTPRedirectHandler for h in handlers
            ), "opener 上仍挂着裸 HTTPRedirectHandler（逐跳闸门被摘掉）"
            assert any(type(h).__name__ == "_HopGuardRedirectHandler" for h in handlers)


# ─────────────────────────────────────────────────────────────
# 代理分支 stream=True 的响应必须关闭
# ─────────────────────────────────────────────────────────────
# 原先 redirect_url 提前 return / 读体抛错两条出口都不 close()，连接只能等 urllib3 的 GC 收尸。
# 判据只有一条：无论走哪条出口，响应对象的 close() 都必须被调用一次。
class TestProxyStreamResponseIsClosed:
    def _wire(self, monkeypatch: pytest.MonkeyPatch, response: MagicMock) -> MagicMock:
        session_obj = MagicMock()
        session_obj.get.return_value = response
        session_obj.post.return_value = response
        monkeypatch.setattr("src.sync_http._session", lambda: session_obj)
        return session_obj

    def test_redirect_url_path_closes_response(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        response = MagicMock()
        response.url = "http://final.example.com/x"
        self._wire(monkeypatch, response)
        assert sync_req("http://example.com", proxy_addr="http://proxy:8080", redirect_url=True) == (
            "http://final.example.com/x"
        )
        response.close.assert_called_once()

    def test_body_read_path_closes_response(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        response = MagicMock()
        response.headers = {}
        response.iter_content.return_value = [b"ok"]
        self._wire(monkeypatch, response)
        assert sync_req("http://example.com", proxy_addr="http://proxy:8080") == "ok"
        response.close.assert_called_once()

    def test_cap_violation_still_closes_response(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        # 超限是「读体抛错」的典型形态：此时也必须关连接，否则大响应被逐出引用后连接长期占着。
        monkeypatch.setattr("src.sync_http._MAX_RESPONSE_BYTES", 4)
        response = MagicMock()
        response.headers = {}
        response.iter_content.return_value = [b"0123456789"]
        self._wire(monkeypatch, response)
        assert sync_req("http://example.com", proxy_addr="http://proxy:8080") == ""
        response.close.assert_called_once()


# ─────────────────────────────────────────────────────────────
# json_data 静默退化成 GET
# ─────────────────────────────────────────────────────────────
# 原实现只对 dict/list 生效，传 str/int/bool 时请求体被静默丢弃、请求退化成 GET；与 async 侧
# 「data/json_data 同传显式拒绝」同口径后，编程错误一律在发请求前冒出来（不伪装成网络失败）。
class TestJsonDataShapeIsRejected:
    @pytest.mark.parametrize("json_data", ["raw", 1, True, 1.5])
    def test_unsupported_json_data_shape_raises_before_sending(
        self, json_data: object, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        opener_spy = MagicMock()
        monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
        with pytest.raises(ValueError, match="json_data"):
            sync_req("http://example.com", json_data=cast("Any", json_data))
        opener_spy.open.assert_not_called()

    def test_unsupported_shape_raises_on_proxied_branch_too(
        self, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session_spy = MagicMock()
        monkeypatch.setattr("src.sync_http._session", lambda: session_spy)
        with pytest.raises(ValueError, match="json_data"):
            sync_req("http://example.com", proxy_addr="http://proxy:8080", json_data=cast("Any", "raw"))
        session_spy.get.assert_not_called()
        session_spy.post.assert_not_called()

    def test_data_and_json_data_together_raises(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        opener_spy = MagicMock()
        monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
        with pytest.raises(ValueError, match="data 与 json_data"):
            sync_req("http://example.com", data={"a": "1"}, json_data={"b": 2})
        opener_spy.open.assert_not_called()

    @pytest.mark.parametrize("json_data", [{"a": 1}, [1, 2], {}, []])
    def test_supported_shapes_still_post_json_body(
        self, json_data: object, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 反向锁：dict/list（含空容器）照旧序列化成 JSON 请求体，不得被收紧成「一律拒绝」。
        captured: dict[str, object] = {}
        fake_resp = MagicMock()
        fake_resp.headers = {"Content-Encoding": ""}
        fake_resp.read.return_value = b"ok"
        fake_resp.url = "http://example.com"

        def _open(req: urllib.request.Request, timeout: object = None) -> MagicMock:
            captured["data"] = req.data
            return fake_resp

        opener_spy = MagicMock()
        opener_spy.open.side_effect = _open
        monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
        assert sync_req("http://example.com", json_data=cast("Any", json_data)) == "ok"
        assert captured["data"] == json.dumps(json_data).encode("utf-8")


# ─────────────────────────────────────────────────────────────
# 残余：abroad 分支落地复核升级为与入口/逐跳同一份判据
# ─────────────────────────────────────────────────────────────
# _HopGuardRedirectHandler 只挂在本模块自建的两支 opener 上；abroad 分支经进程全局默认 opener，
# 原判据只有 _reject_unsafe_scheme（协议形态白名单）——公网 URL 302 到 http://169.254.169.254/
# 协议合法照样放行，元数据正文原样返回调用方（稳定 SSRF 回显）。修复后落地改跑
# _redirect_hop_rejection_reason（scheme 白名单 + async_http.internal_stream_target_reason，
# 判据唯一事实源，本组不复刻内网名单）。
# 变异验证锚点：把该分支退回 _reject_unsafe_scheme(_resp.url, "重定向落地")，前三条参数化必红
# （file:// 那条照旧绿——正是「旧判据只挡协议、不挡内网」的见证）。
class TestAbroadLandingInternalGate:
    @pytest.mark.parametrize(
        "landing_url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:6379/",
            "http://10.0.0.5:8080/api",
            "http://[::1]:11211/",
            "file:///etc/passwd",
        ],
    )
    def test_abroad_landing_on_internal_target_returns_empty_not_body(
        self, landing_url: str, _public_dns: None
    ) -> None:
        # 替身只钉 urlopen（落地是它返回的最终 URL）：判据、异常收口、close 全走生产代码。
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"INTERNAL-LANDING-CANARY"
        mock_response.url = landing_url
        with patch("src.sync_http.urllib.request.urlopen", return_value=mock_response):
            result = sync_req("https://start.example.com/live", abroad=True)
        assert result == "", "落地内网/保留目标的正文仍被返回给调用方（SSRF 回显）"
        mock_response.read.assert_not_called()
        # 拒绝必须经 finally 关连接（写在内层 try 第一条的意义）
        mock_response.close.assert_called_once()

    def test_abroad_landing_on_public_target_still_returns_body(self, _public_dns: None) -> None:
        # 反向锁：协议合法且解析为公网的落地照旧交付正文——闸门不得误杀境外正常请求。
        mock_response = MagicMock()
        mock_response.headers = {"Content-Encoding": ""}
        mock_response.read.return_value = b"public body"
        mock_response.url = "https://cdn.example.com/final"
        with patch("src.sync_http.urllib.request.urlopen", return_value=mock_response):
            assert sync_req("https://start.example.com/live", abroad=True) == "public body"


# ─────────────────────────────────────────────────────────────
# 残余：直连分支的 JSON 请求体必须带 Content-Type
# ─────────────────────────────────────────────────────────────
# 代理分支交给 requests 的 json= 序列化并自动补 application/json；直连分支自行 json.dumps，
# 而 urllib.Request 从不补头——修复前服务端按 form/text 解析 JSON body，与代理分支行为分叉。
# 判据：json_data 生效且调用方未自供 Content-Type（大小写不敏感）时显式合并；自供则尊重原值。
class TestJsonDataContentTypeHeader:
    def _captured_request(self, monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> urllib.request.Request:
        # 经真实 sync_req 直连链路构造 Request，只把 opener 换成记录替身（一个字节都不出网）。
        captured: dict[str, urllib.request.Request] = {}
        fake_resp = MagicMock()
        fake_resp.headers = {"Content-Encoding": ""}
        fake_resp.read.return_value = b"ok"
        fake_resp.url = "http://example.com"

        def _open(req: urllib.request.Request, timeout: object = None) -> MagicMock:
            captured["req"] = req
            return fake_resp

        opener_spy = MagicMock()
        opener_spy.open.side_effect = _open
        monkeypatch.setattr("src.sync_http._get_opener", lambda ssl_verify=None: opener_spy)
        assert sync_req("http://example.com", **kwargs) == "ok"
        return captured["req"]

    @staticmethod
    def _lower_headers(req: urllib.request.Request) -> dict[str, str]:
        # urllib 的 Request.add_header 会把键 capitalize（"Content-type"），统一转小写再断言，
        # 顺带锁「不论调用方键形怎么写都不重复追加」。
        return {key.lower(): value for key, value in req.header_items()}

    def test_json_data_adds_content_type_when_absent(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        req = self._captured_request(monkeypatch, json_data={"a": 1})
        assert self._lower_headers(req).get("content-type") == "application/json"

    def test_caller_supplied_content_type_is_not_overridden(
        self, _public_dns: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 键形刻意用「content-TYPE」混写：判据必须大小写不敏感，否则会出现两支 Content-Type。
        req = self._captured_request(
            monkeypatch, json_data={"a": 1}, headers={"content-TYPE": "application/json; charset=utf-8"}
        )
        assert self._lower_headers(req)["content-type"] == "application/json; charset=utf-8"

    def test_plain_get_gets_no_content_type(self, _public_dns: None, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：无 json_data 时不得凭空补头（GET 带 application/json 是新的污染面）。
        req = self._captured_request(monkeypatch)
        assert "content-type" not in self._lower_headers(req)


# ─────────────────────────────────────────────────────────────
# 残余：线程级 Session 的有界确定性回收
# ─────────────────────────────────────────────────────────────
# 修复前 Session 只在 atexit 关闭，已结束房间线程的连接池要等 GC（非确定性）；现在 _session()
# 每次进入先关闭+摘除「所属线程已不再存活」的登记条目，登记表另有硬上限（达上限时新 Session
# 不登记、退回 WeakSet/atexit 既有路径，绝不回收活线程在用的连接池）。
# 替身只挂 src.sync_http.requests（shim 形态，不动 requests 本体，AGENTS 打桩口径），
# thread-local 复用、登记、回收判据全部走真实 _session。
class TestThreadSessionReclaim:
    class _FakeSession:
        # 最小面：可弱引用、close 可观测。连接池释放由 Session.close() 的语义本身负责，不归本锁。
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    def _install_fake_requests(self, monkeypatch: pytest.MonkeyPatch, created: list[Any]) -> None:
        shim = types.SimpleNamespace(**vars(requests))

        def _factory() -> Any:
            session = TestThreadSessionReclaim._FakeSession()
            created.append(session)
            return session

        shim.Session = _factory
        monkeypatch.setattr("src.sync_http.requests", shim)

    def test_dead_thread_session_is_closed_on_next_session_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.sync_http as sync_http_mod

        created: list[Any] = []
        self._install_fake_requests(monkeypatch, created)
        holder: dict[str, Any] = {}

        def _worker(tag: str) -> None:
            holder[tag] = sync_http_mod._session()

        t1 = threading.Thread(target=_worker, args=("first",), name="dlr-reclaim-t1")
        t1.start()
        t1.join(timeout=15)
        # 并发用例约定：join 之后必须断言线程真退出（R10）
        assert not t1.is_alive()
        first = holder["first"]
        assert first.closed is False, "仍存活的线程 Session 不得被关闭"

        t2 = threading.Thread(target=_worker, args=("second",), name="dlr-reclaim-t2")
        t2.start()
        t2.join(timeout=15)
        assert not t2.is_alive()
        # 回收触发点是「下一次进入 _session()」，不是线程退出时刻
        assert first.closed is True, "已结束线程的 Session 未在下一次 _session() 入口被关闭"
        assert holder["second"].closed is False
        # 判据按「对象是否仍在登记表」而非「ident 是否已被摘除」：OS 线程 ident 可能被复用
        # （t2 恰好拿到 t1 的 ident），按 ident 断言会造出概率性假红。
        registered = [sess for _owner, sess in sync_http_mod._thread_sessions.values()]
        assert first not in registered

    def test_registry_hard_bound_skips_registration_when_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.sync_http as sync_http_mod

        created: list[Any] = []
        self._install_fake_requests(monkeypatch, created)
        with sync_http_mod._thread_sessions_lock:
            sync_http_mod._thread_sessions.clear()
        monkeypatch.setattr(sync_http_mod, "_MAX_TRACKED_SESSIONS", 1)

        holder: dict[str, Any] = {}
        ready = threading.Event()
        release = threading.Event()

        def _blocker() -> None:
            # 保持存活直至被放行：让登记表在它注册后确实处于「满且无可回收」状态
            holder["blocker"] = sync_http_mod._session()
            ready.set()
            release.wait(timeout=15)

        def _latecomer() -> None:
            holder["latecomer"] = sync_http_mod._session()

        t_blocker = threading.Thread(target=_blocker, name="dlr-bound-blocker")
        t_blocker.start()
        assert ready.wait(timeout=10), "blocker 线程未完成 Session 登记"
        t_late = threading.Thread(target=_latecomer, name="dlr-bound-latecomer")
        t_late.start()
        t_late.join(timeout=15)
        assert not t_late.is_alive()
        values = [sess for _owner, sess in sync_http_mod._thread_sessions.values()]
        assert len(values) <= 1, "登记表超出硬上限（_MAX_TRACKED_SESSIONS 不生效）"
        assert holder["blocker"] in values
        # 未登记 ≠ 不可用：达上限时 Session 照常返回，且仍被 WeakSet（atexit 路径）覆盖
        assert holder["latecomer"] not in values
        assert holder["latecomer"] in sync_http_mod._all_sessions
        release.set()
        t_blocker.join(timeout=15)
        assert not t_blocker.is_alive()
        with sync_http_mod._thread_sessions_lock:
            sync_http_mod._thread_sessions.clear()

    def test_session_is_reused_within_thread_and_never_shared_across_threads(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.sync_http as sync_http_mod

        created: list[Any] = []
        self._install_fake_requests(monkeypatch, created)
        holder: dict[str, Any] = {}

        def _worker(tag: str) -> None:
            holder[f"{tag}_a"] = sync_http_mod._session()
            holder[f"{tag}_b"] = sync_http_mod._session()

        t1 = threading.Thread(target=_worker, args=("t1",), name="dlr-perthread-t1")
        t1.start()
        t1.join(timeout=15)
        assert not t1.is_alive()
        t2 = threading.Thread(target=_worker, args=("t2",), name="dlr-perthread-t2")
        t2.start()
        t2.join(timeout=15)
        assert not t2.is_alive()
        assert holder["t1_a"] is holder["t1_b"], "同线程两次 _session() 必须复用同一实例"
        assert holder["t2_a"] is not holder["t1_a"], "Session 不得跨线程共享（thread-local 原规则）"
        assert len(created) == 2, "复用即每线程只新建一次；回收/登记不得改成每请求新建"
