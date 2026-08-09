# Tests for src/sync_http.py module - 同步 HTTP 客户端.

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
    def test_ssl_verify_true_returns_secure_opener(self, mock_config):
        # ssl_verify=True 时使用安全 opener.
        mock_config.ssl_verify = True
        opener = _get_opener()
        assert opener is not None

    @patch("src.sync_http.config")
    def test_ssl_verify_false_returns_insecure_opener(self, mock_config):
        # ssl_verify=False 时使用不安全 opener.
        mock_config.ssl_verify = False
        opener = _get_opener()
        assert opener is not None


class TestSyncReq:
    # Test sync_req 同步请求函数.

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_basic_get_request(self, mock_opener_fn, mock_config):
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
    def test_gzip_response(self, mock_opener_fn, mock_config):
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
    def test_redirect_url_returns_url(self, mock_opener_fn, mock_config):
        # redirect_url=True 返回重定向后的 URL.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.url = "http://redirected.com"

        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_response
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com", redirect_url=True)
        assert result == "http://redirected.com"

    @patch("src.sync_http.requests")
    @patch("src.sync_http.config")
    def test_proxy_get_request(self, mock_config, mock_requests):
        # 带代理的 GET 请求.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.text = "proxy response"
        mock_response.url = "http://example.com"
        mock_requests.get.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080")
        assert result == "proxy response"
        mock_requests.get.assert_called_once()

    @patch("src.sync_http.requests")
    @patch("src.sync_http.config")
    def test_proxy_post_request(self, mock_config, mock_requests):
        # 带代理的 POST 请求.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.text = "post response"
        mock_response.url = "http://example.com"
        mock_requests.post.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", data={"key": "val"})
        assert result == "post response"
        mock_requests.post.assert_called_once()

    @patch("src.sync_http.requests")
    @patch("src.sync_http.config")
    def test_proxy_redirect_url(self, mock_config, mock_requests):
        # 带代理的 redirect_url 返回 URL.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.url = "http://final.com"
        mock_requests.get.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", redirect_url=True)
        assert result == "http://final.com"

    @patch("src.sync_http.requests")
    @patch("src.sync_http.config")
    def test_proxy_post_with_json_data(self, mock_config, mock_requests):
        # 带代理的 JSON POST 请求.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.text = "json response"
        mock_response.url = "http://example.com"
        mock_requests.post.return_value = mock_response

        result = sync_req("http://example.com", proxy_addr="http://proxy:8080", json_data={"a": 1})
        assert result == "json response"

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_post_data_dict_encoding(self, mock_opener_fn, mock_config):
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
    def test_post_data_string_encoding(self, mock_opener_fn, mock_config):
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
    def test_json_data_encoding(self, mock_opener_fn, mock_config):
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
    def test_http_error_400_returns_body(self, mock_opener_fn, mock_config):
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
    def test_url_error_raises(self, mock_opener_fn, mock_config):
        # URLError 被重新抛出.
        import urllib.error

        mock_config.ssl_verify = True
        mock_opener = MagicMock()
        mock_opener.open.side_effect = urllib.error.URLError("connection refused")
        mock_opener_fn.return_value = mock_opener

        result = sync_req("http://example.com")
        # URLError 被捕获后转为 str
        assert "connection refused" in result

    @patch("src.sync_http.config")
    @patch("src.sync_http._get_opener")
    def test_abroad_request(self, mock_opener_fn, mock_config):
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
    def test_abroad_redirect_url(self, mock_opener_fn, mock_config):
        # abroad=True + redirect_url=True.
        mock_config.ssl_verify = True
        mock_response = MagicMock()
        mock_response.url = "http://redirected.com"

        with patch("src.sync_http.urllib.request.urlopen", return_value=mock_response):
            result = sync_req("http://example.com", abroad=True, redirect_url=True)
            assert result == "http://redirected.com"

    @patch("src.sync_http.config")
    def test_general_exception_returns_error_string(self, mock_config):
        # 一般异常被捕获并返回错误字符串.
        mock_config.ssl_verify = True
        # 让 opener 抛异常
        with patch("src.sync_http._get_opener", side_effect=Exception("unexpected")):
            result = sync_req("http://example.com")
            assert "unexpected" in result
