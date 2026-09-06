#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 代理检测模块 - 检测系统代理配置，支持 Windows 和 Linux 系统

import os
import sys
from dataclasses import dataclass, field
from typing import cast

# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.utils 导出" 告警。
from loguru import logger


@dataclass(frozen=True)
class ProxyInfo:
    # 代理信息数据类
    ip: str = field(default="", repr=True)
    port: str = field(default="", repr=True)

    def __post_init__(self) -> None:
        # 初始化后验证数据有效性
        if (self.ip and not self.port) or (not self.ip and self.port):
            raise ValueError("IP or port cannot be empty")

        if self.ip and self.port:
            if not self.port.isdigit() or not (1 <= int(self.port) <= 65535):
                raise ValueError("Port must be a digit between 1 and 65535")

            # localhost 是本地代理的常见主机名，单独放行
            if self.ip.lower() == "localhost":
                return

            import re

            ip_pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
            if not re.match(ip_pattern, self.ip):
                domain_pattern = r"^([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,}$"
                if not re.match(domain_pattern, self.ip):
                    raise ValueError("Invalid IP address or domain format")


class ProxyDetector:
    # 系统代理检测器

    def __init__(self) -> None:
        # 初始化代理检测器
        self.__internet_settings = None
        if sys.platform.startswith("win"):
            import winreg

            self.__path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            try:
                # 仅需读取权限，避免非管理员用户因 KEY_ALL_ACCESS 而失败
                key_user = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                try:
                    self.__internet_settings = winreg.OpenKeyEx(key_user, self.__path, 0, winreg.KEY_READ)
                finally:
                    key_user.Close()
            except OSError as err:
                logger.warning("Failed to open proxy registry key: " + str(err))

    def __del__(self) -> None:
        # 析构时关闭注册表句柄，避免资源泄漏
        try:
            if self.__internet_settings is not None:
                self.__internet_settings.Close()
        except Exception:
            pass

    def get_proxy_info(self) -> ProxyInfo:
        # 获取代理信息
        if sys.platform.startswith("win"):
            ip, port = self._get_proxy_info_windows()
        else:
            ip, port = self._get_proxy_info_linux()
        return ProxyInfo(ip, port)

    def is_proxy_enabled(self) -> bool:
        # 检查代理是否启用
        if sys.platform.startswith("win"):
            return self._is_proxy_enabled_windows()
        return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> tuple[str, str]:
        # Windows 系统获取代理信息（内部方法）
        ip, port = "", ""
        if self._is_proxy_enabled_windows():
            if self.__internet_settings is None:
                return "", ""
            import winreg

            try:
                ip_port = cast(str, winreg.QueryValueEx(self.__internet_settings, "ProxyServer")[0])
                if ip_port:
                    # 兼容 "ip:port" 及多段代理配置（如 "http=ip:port;https=ip:port"）
                    first = ip_port.split(";")[0]
                    # 去掉多段代理的协议前缀（http=/https=/socks=），避免 "http=ip" 被误判为非法 IP
                    if "=" in first:
                        first = first.split("=", 1)[1]
                    if ":" in first:
                        ip, port = first.split(":", 1)
                    else:
                        ip = first
            except FileNotFoundError as err:
                logger.warning("No proxy information found: " + str(err))
            except Exception as err:
                logger.error("An error occurred: " + str(err))
        else:
            logger.debug("No proxy is enabled on the system")
        return ip, port

    def _is_proxy_enabled_windows(self) -> bool:
        # Windows 系统检查代理是否启用（内部方法）
        if self.__internet_settings is None:
            return False
        import winreg

        try:
            if cast(int, winreg.QueryValueEx(self.__internet_settings, "ProxyEnable")[0]) == 1:
                return True
        except FileNotFoundError as err:
            logger.warning("No proxy information found: " + str(err))
        except Exception as err:
            logger.error("An error occurred: " + str(err))
        return False

    @staticmethod
    def _get_proxy_info_linux() -> tuple[str, str]:
        # Linux 系统获取代理信息（内部方法）
        proxies = {"http": os.getenv("http_proxy"), "https": os.getenv("https_proxy"), "ftp": os.getenv("ftp_proxy")}
        ip = port = ""
        for _proto, proxy in proxies.items():
            if proxy:
                # 去掉末尾斜杠，避免 path 被误解析为端口
                proxy = proxy.rstrip("/")
                if "://" in proxy:
                    proxy = proxy.split("://", 1)[1]
                # 处理 user:pass@host:port 形式，取 @ 之后的部分
                if "@" in proxy:
                    proxy = proxy.split("@", 1)[1]
                if ":" in proxy:
                    ip, port = proxy.split(":", 1)
                    break
        return ip, port

    def _is_proxy_enabled_linux(self) -> bool:
        # Linux 系统检查代理是否启用（内部方法）
        proxies = {"http": os.getenv("http_proxy"), "https": os.getenv("https_proxy"), "ftp": os.getenv("ftp_proxy")}
        return any(proxy for proxy in proxies.values())
