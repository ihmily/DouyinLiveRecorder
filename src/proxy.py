import os
import sys
from dataclasses import dataclass, field
from .utils import logger


@dataclass(frozen=True)
class ProxyInfo:
    ip: str = field(default="", repr=True)
    port: str = field(default="", repr=True)

    def __post_init__(self):
        if (self.ip and not self.port) or (not self.ip and self.port):
            raise ValueError("IP or port cannot be empty")

        if (self.ip and self.port):
            # 验证端口格式
            if not self.port.isdigit() or not (1 <= int(self.port) <= 65535):
                raise ValueError("Port must be a digit between 1 and 65535")
            
            # 验证 IP 地址格式
            import re
            ip_pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
            if not re.match(ip_pattern, self.ip):
                # 检查是否是域名
                domain_pattern = r'^([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,}$'
                if not re.match(domain_pattern, self.ip):
                    raise ValueError("Invalid IP address or domain format")


class ProxyDetector:
    def __init__(self):
        if sys.platform.startswith('win'):
            import winreg
            self.winreg = winreg
            self.__path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
            with winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER) as key_user:
                self.__INTERNET_SETTINGS = winreg.OpenKeyEx(key_user, self.__path, 0, winreg.KEY_ALL_ACCESS)
        else:
            self.__is_windows = False

    def get_proxy_info(self) -> ProxyInfo:
        if sys.platform.startswith('win'):
            ip, port = self._get_proxy_info_windows()
        else:
            ip, port = self._get_proxy_info_linux()
        return ProxyInfo(ip, port)

    def is_proxy_enabled(self) -> bool:
        if sys.platform.startswith('win'):
            return self._is_proxy_enabled_windows()
        else:
            return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> tuple[str, str]:
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
        # 直接检查环境变量是否存在
        proxies = {
            'http': os.getenv('http_proxy'),
            'https': os.getenv('https_proxy'),
            'ftp': os.getenv('ftp_proxy')
        }
        return any(proxy for proxy in proxies.values())
