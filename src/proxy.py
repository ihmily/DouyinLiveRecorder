#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
代理检测模块

该模块用于检测系统代理配置，支持 Windows 和 Linux 系统。

功能：
- 检测代理是否启用
- 获取代理服务器地址和端口
- 验证代理地址格式验证

Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-2025
"""
import os
import sys
from dataclasses import dataclass, field
from .utils import logger


@dataclass(frozen=True)
class ProxyInfo:
    """代理信息数据类
    
    存储代理服务器的 IP 地址和端口号
    
    属性:
        ip: 代理服务器 IP 地址或域名
        port: 代理服务器端口号
    
    验证:
        - IP 和端口必须同时存在或同时为空
        - 端口必须是 1-65535 之间的数字
        - IP 必须是合法的 IPv4 地址或域名格式
    """
    ip: str = field(default="", repr=True)
    port: str = field(default="", repr=True)

    def __post_init__(self):
        """初始化后验证数据有效性"""
        # 验证 IP 和端口必须成对出现
        if (self.ip and not self.port) or (not self.ip and self.port):
            raise ValueError("IP or port cannot be empty")

        # 验证格式（仅当两者都存在时
        if (self.ip and self.port):
            # 验证端口格式
            if not self.port.isdigit() or not (1 <= int(self.port) <= 65535):
                raise ValueError("Port must be a digit between 1 and 65535")
            
            # 验证 IP 地址格式
            import re
            ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            if not re.match(ip_pattern, self.ip):
                # 如果不是 IP 格式，检查是否是域名
                domain_pattern = r'^([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,}$'
                if not re.match(domain_pattern, self.ip):
                    raise ValueError("Invalid IP address or domain format")


class ProxyDetector:
    """系统代理检测器
    
    根据操作系统自动检测系统代理配置
    
    支持平台:
        - Windows: 通过注册表检测
        - Linux: 通过环境变量检测
    """
    
    def __init__(self):
        """初始化代理检测器"""
        if sys.platform.startswith('win'):
            # Windows 系统：通过注册表检测
            import winreg
            self.winreg = winreg
            self.__path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            # 打开注册表键
            with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as key_user:
                self.__INTERNET_SETTINGS = winreg.OpenKeyEx(key_user, self.__path, 0, winreg.KEY_ALL_ACCESS)
        else:
            # 非 Windows 系统
            self.__is_windows = False

    def get_proxy_info(self) -> ProxyInfo:
        """获取代理信息
        
        返回:
            ProxyInfo: 包含代理 IP 和端口的对象
        """
        if sys.platform.startswith('win'):
            ip, port = self._get_proxy_info_windows()
        else:
            ip, port = self._get_proxy_info_linux()
        return ProxyInfo(ip, port)

    def is_proxy_enabled(self) -> bool:
        """检查代理是否启用
        
        返回:
            bool: 如果代理启用返回 True，否则返回 False
        """
        if sys.platform.startswith('win'):
            return self._is_proxy_enabled_windows()
        else:
            return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> tuple[str, str]:
        """Windows 系统获取代理信息（内部方法）
        
        返回:
            tuple[str, str]: (IP地址, 端口号
        """
        ip, port = "", ""
        if self._is_proxy_enabled_windows():
            try:
                ip_port = self.winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyServer")[0]
                if ip_port:
                    ip, port = ip_port.split(":")
            except FileNotFoundError as err:
                logger.warning("No proxy information found: " + str(err))
            except Exception as err:
                logger.error("An error occurred: " + str(err))
        else:
            logger.debug("No proxy is enabled on the system")
        return ip, port

    def _is_proxy_enabled_windows(self) -> bool:
        """Windows 系统检查代理是否启用（内部方法）
        
        返回:
            bool: 代理是否启用
        """
        try:
            if self.winreg.QueryValueEx(self.__INTERNET_SETTINGS, "ProxyEnable")[0] == 1:
                return True
        except FileNotFoundError as err:
            logger.warning("No proxy information found: " + str(err))
        except Exception as err:
            logger.error("An error occurred: " + str(err))
        return False

    @staticmethod
    def _get_proxy_info_linux() -> tuple[str, str]:
        """Linux 系统获取代理信息（内部方法）
        
        返回:
            tuple[str, str]: (IP地址, 端口号)
        """
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
            'ftp': os.getenv('ftp_proxy')
        }
        ip = port = ""
        for proto, proxy in proxies.items():
            if proxy:
                # 处理代理 URL 格式，例如 http://ip:port
                if '://' in proxy:
                    proxy = proxy.split('://')[1]
                # 分割 IP 和端口
                if ':' in proxy:
                    ip, port = proxy.split(':', 1)
                    break
        return ip, port

    def _is_proxy_enabled_linux(self) -> bool:
        """Linux 系统检查代理是否启用（内部方法）
        
        返回:
            bool: 代理是否启用
        """
        # 直接检查环境变量是否存在
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
            'ftp': os.getenv('ftp_proxy')
        }
        return any(proxy for proxy in proxies.values())
