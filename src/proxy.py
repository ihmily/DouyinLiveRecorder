#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 代理检测模块 - 检测系统代理配置，支持 Windows 和 Linux 系统

import os
import sys
from dataclasses import dataclass, field
from .utils import logger


@dataclass(frozen=True)
class ProxyInfo:
    # 代理信息数据类
    ip: str = field(default="", repr=True)
    port: str = field(default="", repr=True)

    def __post_init__(self):
        # 初始化后验证数据有效性
        if (self.ip and not self.port) or (not self.ip and self.port):
            raise ValueError("IP or port cannot be empty")

        if self.ip and self.port:
            if not self.port.isdigit() or not (1 <= int(self.port) <= 65535):
                raise ValueError("Port must be a digit between 1 and 65535")
            
            import re
            ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            if not re.match(ip_pattern, self.ip):
                domain_pattern = r'^([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,}$'
                if not re.match(domain_pattern, self.ip):
                    raise ValueError("Invalid IP address or domain format")


class ProxyDetector:
    # 系统代理检测器
    
    def __init__(self):
        # 初始化代理检测器
        if sys.platform.startswith('win'):
            import winreg
            self.winreg = winreg
            self.__path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as key_user:
                self.__INTERNET_SETTINGS = winreg.OpenKeyEx(key_user, self.__path, 0, winreg.KEY_ALL_ACCESS)
        else:
            self.__is_windows = False

    def get_proxy_info(self) -> ProxyInfo:
        # 获取代理信息
        if sys.platform.startswith('win'):
            ip, port = self._get_proxy_info_windows()
        else:
            ip, port = self._get_proxy_info_linux()
        return ProxyInfo(ip, port)

    def is_proxy_enabled(self) -> bool:
        # 检查代理是否启用
        if sys.platform.startswith('win'):
            return self._is_proxy_enabled_windows()
        else:
            return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> tuple[str, str]:
        # Windows 系统获取代理信息（内部方法）
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
        # Windows 系统检查代理是否启用（内部方法）
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
        # Linux 系统获取代理信息（内部方法）
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
            'ftp': os.getenv('ftp_proxy')
        }
        ip = port = ""
        for proto, proxy in proxies.items():
            if proxy:
                if '://' in proxy:
                    proxy = proxy.split('://')[1]
                if ':' in proxy:
                    ip, port = proxy.split(':', 1)
                    break
        return ip, port

    def _is_proxy_enabled_linux(self) -> bool:
        # Linux 系统检查代理是否启用（内部方法）
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
            'ftp': os.getenv('ftp_proxy')
        }
        return any(proxy for proxy in proxies.values())
