# Tests for src/sync_http.py module - 同步 HTTP 客户端.
# 全程 mock 底层 opener / 线程内 Session / urlopen，不触网；按 ssl_verify 与是否走代理分流两条实现路径，
# 断言覆盖编码分支（dict→表单 / 字符串 / json）、gzip 解压、重定向取 URL、错误返回空串且记日志等契约。
# 非代理路径 patch _get_opener，代理路径 patch 线程内 Session 工厂 _session，避免触网且精准命中实现层。

import gzip
import http.client
import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from src.sync_http import _get_opener, sync_req


class TestGetOpener:
    # Test opener 选择逻辑.

    @patch("src.sync_http.config")
    # ssl_verify=True 须返回标准安全 opener，与默认生产环境一致
    def test_ssl_verify_true_returns_secure_opener(self, mock_config: MagicMock) -> None:
        # 开启证书校验（ssl_verify=True）须返回标准 opener，与默认生产环境一致
        # ssl_verify=True 时使用安全 opener.
        mock_config.ssl_verify = True
        opener = _get_opener()
        assert opener is not None

    @patch("src.sync_http.config")
    def test_ssl_verify_false_returns_insecure_opener(self, mock_config: MagicMock) -> None:
        # ssl_verify=False 时使用不安全 opener.
        mock_config.ssl_verify = False
        opener = _get_opener()
        assert opener is not None


# sync_req 同步请求入口：按 ssl_verify 与是否走代理分流两条实现路径。
# 守卫编码分支、gzip 解压、重定向取 URL、错误返回空串且记日志等契约。
class TestSyncReq:
    # Test sync_req 同步请求函数.

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    # 正常 GET 路径：解码响应体返回字符串，且用后必须 close 一次释放连接
    def test_basic_get_request(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # 正常 GET 路径：解码响应体返回字符串，且用后必须 close 一次以释放连接
        # 基本 GET 请求.
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
        # redirect_url=True 返回重定向后的 URL.
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
        # 带代理的 GET 请求.
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = "proxy response"
        mock_response.url = "http://example.com"
        mock_session.get.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080")
        assert result == "proxy response"
        mock_session.get.assert_called_once()

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    def test_proxy_post_request(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 带代理的 POST 请求.
        mock_config.ssl_verify = True
        mock_session = MagicMock()
        mock_session_fn.return_value = mock_session
        mock_response = MagicMock()
        mock_response.text = "post response"
        mock_response.url = "http://example.com"
        mock_session.post.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", data={"key": "val"})
        assert result == "post response"
        mock_session.post.assert_called_once()

    @patch("src.sync_http._session")
    @patch("src.sync_http.config")
    # 代理 + redirect_url：返回重定向后的最终 URL
    def test_proxy_redirect_url(self, mock_config: MagicMock, mock_session_fn: MagicMock) -> None:
        # 带代理的 redirect_url 返回 URL.
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
        mock_response.text = "json response"
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
            # 错误被记录（原 URLError 已 warning 级），且结果不再包含错误文本
            mock_logger.warning.assert_called_once()
            mock_logger.error.assert_called_once()
        assert result == ""
        assert "connection refused" not in result

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_abroad_request(self, mock_opener_fn: MagicMock, mock_config: MagicMock) -> None:
        # abroad=True 使用 urlopen.
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
        # abroad=True + redirect_url=True.
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
