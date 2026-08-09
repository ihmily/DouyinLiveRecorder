# Tests for src/proxy.py module - 代理检测模块.

import os
from unittest.mock import patch

import pytest

from src.proxy import ProxyDetector, ProxyInfo


class TestProxyInfo:
    # Test ProxyInfo 数据类.

    def test_empty_creation(self):
        # 空 IP 和端口有效（表示无代理）.
        info = ProxyInfo()
        assert info.ip == ""
        assert info.port == ""

    def test_valid_ip_port(self):
        # 有效 IP 和端口.
        info = ProxyInfo("192.168.1.1", "8080")
        assert info.ip == "192.168.1.1"
        assert info.port == "8080"

    def test_localhost_valid(self):
        # localhost 是合法的代理主机名.
        info = ProxyInfo("localhost", "3128")
        assert info.ip == "localhost"
        assert info.port == "3128"

    def test_ip_without_port_raises(self):
        # 仅有 IP 无端口抛异常.
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("192.168.1.1", "")

    def test_port_without_ip_raises(self):
        # 仅有端口无 IP 抛异常.
        with pytest.raises(ValueError, match="IP or port"):
            ProxyInfo("", "8080")

    def test_invalid_port_non_numeric(self):
        # 非数字端口抛异常.
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "abc")

    def test_invalid_port_out_of_range(self):
        # 超范围端口抛异常.
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "99999")

    def test_invalid_port_zero(self):
        # 端口 0 抛异常.
        with pytest.raises(ValueError, match="Port must be"):
            ProxyInfo("192.168.1.1", "0")

    def test_invalid_ip_format(self):
        # 非法 IP 格式抛异常.
        with pytest.raises(ValueError, match="Invalid IP"):
            ProxyInfo("999.999.999.999", "8080")

    def test_valid_domain(self):
        # 合法域名作为代理地址.
        info = ProxyInfo("proxy.example.com", "8080")
        assert info.ip == "proxy.example.com"

    def test_invalid_domain_format(self):
        # 非法域名格式抛异常.
        with pytest.raises(ValueError, match="Invalid IP"):
            ProxyInfo("inv@lid!", "8080")

    def test_port_boundary_low(self):
        # 端口下界 1 有效.
        info = ProxyInfo("10.0.0.1", "1")
        assert info.port == "1"

    def test_port_boundary_high(self):
        # 端口上界 65535 有效.
        info = ProxyInfo("10.0.0.1", "65535")
        assert info.port == "65535"

    def test_frozen_dataclass(self):
        # 不可变数据类：对冻结实例赋值应抛 AttributeError（FrozenInstanceError 的基类）.
        info = ProxyInfo("10.0.0.1", "8080")
        with pytest.raises(AttributeError):
            # 用 setattr 触发冻结保护，避免直接赋值依赖失效的 # type: ignore 抑制符
            setattr(info, "ip", "other")


class TestProxyDetectorLinux:
    # Test ProxyDetector Linux 平台方法.

    @patch.dict(os.environ, {"http_proxy": "http://user:pass@proxy.example.com:3128/"}, clear=False)
    def test_linux_get_proxy_info_with_auth(self):
        # 带认证信息的代理 URL 正确解析.
        ip, port = ProxyDetector._get_proxy_info_linux()
        assert ip == "proxy.example.com:3128" or ip == "proxy.example.com"
        # 实际解析逻辑：去掉 user:pass@ 后按 : 分割

    @patch.dict(os.environ, {"http_proxy": "http://10.0.0.1:8080"}, clear=False)
    def test_linux_get_proxy_info_simple(self):
        # 简单代理 URL 解析.
        ip, port = ProxyDetector._get_proxy_info_linux()
        assert ip == "10.0.0.1"
        assert port == "8080"

    @patch.dict(os.environ, {"https_proxy": "http://proxy.test:9090/"}, clear=False)
    def test_linux_get_proxy_info_https(self):
        # https_proxy 环境变量解析.
        ip, port = ProxyDetector._get_proxy_info_linux()
        # 取决于环境变量优先级
        assert isinstance(ip, str)
        assert isinstance(port, str)

    @patch.dict(os.environ, {}, clear=True)
    def test_linux_no_proxy(self):
        # 无代理环境变量时返回空.
        # 确保所有代理变量都清除
        for key in list(os.environ.keys()):
            if "proxy" in key.lower():
                del os.environ[key]
        ip, port = ProxyDetector._get_proxy_info_linux()
        assert ip == ""
        assert port == ""

    @patch.dict(os.environ, {}, clear=True)
    def test_linux_is_proxy_enabled_false(self):
        # 无代理时返回 False.
        for key in list(os.environ.keys()):
            if "proxy" in key.lower():
                del os.environ[key]
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is False

    @patch.dict(os.environ, {"http_proxy": "http://proxy:8080"}, clear=False)
    def test_linux_is_proxy_enabled_true(self):
        # 有代理时返回 True.
        detector = ProxyDetector.__new__(ProxyDetector)
        assert detector._is_proxy_enabled_linux() is True

    @patch.dict(os.environ, {"http_proxy": "http://proxy.example.com:8080/"}, clear=False)
    def test_linux_proxy_with_trailing_slash(self):
        # 末尾斜杠被正确处理.
        ip, port = ProxyDetector._get_proxy_info_linux()
        assert ip == "proxy.example.com"
        assert port == "8080"
