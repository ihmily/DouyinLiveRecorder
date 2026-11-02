#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 代理检测模块 - 检测系统代理配置：Windows 读注册表 Internet Settings，其余平台（Linux/macOS）读环境变量

import ipaddress
import os
import re
import sys
from dataclasses import dataclass, field
from typing import cast
from urllib.parse import quote

# loguru 的 logger 为模块级单例，src.logger 对其做过的配置在此同样生效；
# 直接从此处导入可避免基于 basedpyright 的 "未从 src.utils 导出" 告警。
from loguru import logger

# 本模块日志统一走 i18n（原先 5 处为裸英文 + 字符串拼接，
# 在中文/繁体/英式目录下无法翻译，与仓库其它模块的日志口径不一致）
import i18n

# 代理自身的协议白名单：注册表/环境变量里出现的 scheme 只有这几种有意义（curl / wget /
# requests / httpx 所认集合的并集）；其余形态（"proxy-protocol://" 之类）一律按「没有 scheme」
# 处理——把垃圾串拼进 proxy_url 只会变成下游更难归因的 InvalidURL。
_PROXY_SCHEMES = frozenset(("http", "https", "socks5", "socks5h", "socks4", "socks4a"))


def _is_ip_literal_without_port(value: str) -> bool:
    # 判定「IPv6 字面量」（裸写 "::1"/"2001:db8::1"，或带方括号 "[::1]"）。单独放行「无端口」
    # 是因为 IPv6 主机在 URL 里**必须**写 [..]，注册表却常存裸写无端口的 "::1"（用户填了一半）。
    # 判定用 ipaddress 而非正则：缩写/zone 形态（::、2001:db8::1、fe80::1%eth0）正则容易漏，
    # 且与仓内其它内网判定同口径。不放行它会落进下面「IP or port cannot be empty」的 raise，
    # 该异常被 main.py 外层 except 吞成一行 print → global_proxy 仍为 True 却拿不到地址。
    stripped = value.strip().strip("[]")
    if ":" not in stripped:
        return False
    try:
        return isinstance(ipaddress.ip_address(stripped.split("%", 1)[0]), ipaddress.IPv6Address)
    except ValueError:
        return False


@dataclass(frozen=True)
class ProxyInfo:
    ip: str = field(default="", repr=True)
    port: str = field(default="", repr=True)
    # 认证代理的凭据单独承载（原实现在解析处 split("@", 1)[1] 把凭据直接丢弃，ProxyInfo 只剩
    # ip/port，上层无法还原可用地址）。repr=False：该 dataclass 会被 print / 记进日志，
    # 凭据不得跟着进轮转日志文件。
    user: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    # 代理**自身**的协议（来自 all_proxy=socks5://… 的 scheme，或注册表里显式写出的
    # "socks5://ip:port"）；空串表示来源未给协议。旧实现在解析处就把 scheme 丢掉、proxy_url 又
    # 恒补 http://，于是 socks 代理被静默改写成 HTTP 语义——socks 端口不认 HTTP CONNECT，
    # 表现为「配了代理却全平台网络异常」，而日志看不出协议被换过。
    scheme: str = field(default="", repr=True)

    @property
    def proxy_url(self) -> str:
        # 还原可直接交给 requests/httpx 的代理地址（含凭据、保留原协议）；无 ip 时返回空串，
        # 来源未给协议时补 http://。本函数**只负责拼 URL**：地址归一的唯一落点仍是
        # utils.handle_proxy_addr（构造客户端之前那一处），不在这里重复补前缀或改大小写。
        if not self.ip:
            return ""
        # user/password 必须 percent 编码再拼进 userinfo：直拼时密码含保留字符会生成**结构错位**的
        # 代理 URL（实测 http://u:p#ss@10.0.0.1:8080 被 urlsplit 判成 host='ss' + fragment），
        # 下游 httpx 直接抛 InvalidURL（"Invalid port: 'pa'"）——表现为「配了认证代理却全平台连不
        # 上」，而 repr 不带凭据，日志里看不出是编码问题。safe="" 的判据是「分隔结构一律不能被
        # 动过」：userinfo 段里 @ : / ? # 与 % 全部转义。本模块契约是 user/password 存**字面原文**
        # （_split_host_port 从不 unquote），实测 8 种取值（p@ss / p%40ss / pa/ss / pa#ss / pa?ss /
        # 50%off / p:ss / p%）经 safe="" 编码后 httpx 解出的 password 与原文逐字相等。
        auth = f"{quote(self.user, safe='')}:{quote(self.password, safe='')}@" if self.user else ""
        # IPv6 必须包方括号，否则 "http://::1:8080" 是非法 authority（下游按 InvalidURL 失败）
        host = self.ip if self.ip.startswith("[") or ":" not in self.ip else f"[{self.ip}]"
        prefix = f"{self.scheme}://" if self.scheme else "http://"
        return f"{prefix}{auth}{host}:{self.port}" if self.port else f"{prefix}{auth}{host}"

    # ── 残留登记：本组字段（user / password / scheme / proxy_url）在本仓**没有任何生产消费点** ──
    #   ① main.py 的代理检测块只读 ip/port 两字段用于打印 System Proxy；
    #   ② 真正下发给 spider/stream 的 proxy_addr 取自 config.ini「录制设置/代理地址」
    #      （main.py 的 proxy_addr_bak），与系统代理检测是两条互不相通的链路；
    #   ③ src/ 下其余模块不 import 本模块。
    # 故「认证代理无法还原完整地址」只在**解析层**已修，**生效层**未闭合：系统代理带凭据/带
    # socks 协议时，录制链路依然收不到它。接上它需要改 main.py，因此只在此显式登记，不留
    # 「已修好」的错误陈述（L-10：注释声强于实现比没有注释更危险）。
    # [历史注 2026-10-21] 本条登记语为 `没有任何生产消费点` 的逐字形态被
    # tests/test_regression_net.py::TestMid2233ResidualRegistered 锁定；修订措辞时
    # 必须同批改该锁，否则会出现「登记还在、锁变红」的假失败。

    def __post_init__(self) -> None:
        # 校验 ip/port 组合的合法性；非法形态一律抛 ValueError（调用方 main.py 会吞成一行打印，
        # 见 _is_ip_literal_without_port 的说明）
        if self.ip and not self.port and _is_ip_literal_without_port(self.ip):
            # 裸/括号 IPv6 字面量允许无端口（判定依据见该函数）。
            #   [历史注] 旧注释称此处「交给下方裸 IPv6 分支放行」不成立：那个分支位于
            #   `if self.ip and self.port:` 门内，上一条 raise 先命中，无端口的 "::1" 从来没通过。
            return
        if (self.ip and not self.port) or (not self.ip and self.port):
            raise ValueError("IP or port cannot be empty")

        if self.ip and self.port:
            if not self.port.isdigit() or not (1 <= int(self.port) <= 65535):
                raise ValueError("Port must be a digit between 1 and 65535")

            # localhost 是本地代理的常见主机名，单独放行
            if self.ip.lower() == "localhost":
                return

            # IPv6 带端口形态：Windows 注册表 ProxyServer 常存 "[::1]:8080"，必须单独识别，
            # 否则被 IPv4/域名正则双重拒
            if self.ip.startswith("[") and self.ip.endswith("]"):
                return
            # 不带方括号的裸 IPv6（"::1" / "2001:db8::1"，registry 实际格式少见，作兜底）；
            # 走到此处必然已带端口——无端口形态已在 __post_init__ 开头放行
            if ":" in self.ip:
                return

            ip_pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
            if not re.match(ip_pattern, self.ip):
                domain_pattern = r"^([a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]\.)+[a-zA-Z]{2,}$"
                if not re.match(domain_pattern, self.ip):
                    raise ValueError("Invalid IP address or domain format")


class ProxyDetector:
    # 系统代理检测器：Windows 读注册表 Internet Settings，其余平台读环境变量

    # 读取的环境变量集合（小写 + 大写两种形态都查）：curl / wget / requests 等主流工具都认两种
    # 大小写，all_proxy 是「所有协议」的兜底项。
    # **刻意不含 ftp_proxy**：本仓全部出站请求都是 http/https（含 HLS/FLV 拉流与所有平台解析），
    # 只配 ftp 代理的机器并不意味着「本程序有代理可用」。旧集合把它算进候选，于是 global_proxy=True
    # 成立而解析出的地址又被下游按 http 代理使用；最坏组合下 9 个海外平台走「有代理」分支、实际
    # 传给 async_req 的 proxy_address 为空 → 直连境外域名，全平台「网络异常」而日志显示「已检测到
    # 系统代理」，归因方向被彻底带偏。本程序不代理 FTP 流量，故不纳入。
    _LINUX_PROXY_ENV_NAMES = ("http_proxy", "https_proxy", "all_proxy")

    @staticmethod
    def _split_scheme(raw: str) -> tuple[str, str]:
        # 把 "socks5://host:port" 拆成 (scheme, "host:port")；无协议返回 ("", 原串)。
        # 协议不在白名单（"file://"、"proxy://" 等怪值）时**仍剥掉前缀**、只是不记 scheme：
        # 若改为报错或原样返回，"foo://bar" 会被 _split_host_port 切成 port="//bar" →
        # ProxyInfo 校验抛 ValueError → 整个系统代理检测被 main.py 外层 except 吞掉
        # （即「拿不到地址却显示有代理」）。为何要单独拆出 scheme 见 ProxyInfo.scheme。
        head, sep, tail = raw.strip().partition("://")
        if not sep:
            return "", raw.strip()
        scheme = head.strip().lower()
        return (scheme if scheme in _PROXY_SCHEMES else ""), tail

    @staticmethod
    def _split_host_port(hostport: str) -> tuple[str, str, str, str]:
        # 把 "user:pass@host:port" / "[::1]:8080" / "10.0.0.1:3128" 拆成 (ip, port, user, password)。
        # 原实现是 split(":", 1)：注册表存 "[::1]:8080" 时切出 ip="["、port=":1]:8080"，port 非
        # 数字 → __post_init__ 抛 ValueError，异常被 main.py 外层 except 吞成一行 print（global_proxy
        # 仍为 True 却拿不到地址），「专门为 [xxxx] 形态写的放行分支」永远收不到合法输入。故改
        # rsplit(":", 1) + 方括号特判；凭据原先被 split("@", 1)[1] 丢弃，现单独承载（见 ProxyInfo）。
        user = password = ""
        hostport = hostport.strip().rstrip("/")
        if not hostport:
            return "", "", "", ""
        if "@" in hostport:
            auth, _, hostport = hostport.rpartition("@")
            user, _, password = auth.partition(":")
        if hostport.startswith("["):
            end = hostport.find("]")
            if end >= 0:
                ip = hostport[: end + 1]
                rest = hostport[end + 1 :]
                return ip, (rest[1:] if rest.startswith(":") else ""), user, password
            return hostport, "", user, password
        if ":" in hostport:
            if hostport.count(":") >= 2:
                # 裸 IPv6（"::1" / "2001:db8::1"，注册表少见形态）：多冒号时不能用
                # 「最后一个冒号之后就是端口」来判定（IPv6 自身就有多个冒号），
                # 故整串作 ip、端口留空，交给 __post_init__ 开头的 IPv6 无端口放行分支
                # （MIN-2233③）。带端口的 IPv6 必须写成 [..]:port，上面已特判——这也是
                # RFC 3986 的形态。
                return hostport, "", user, password
            ip, _, port = hostport.rpartition(":")
            return ip, port, user, password
        return hostport, "", user, password

    @classmethod
    def _linux_proxy_values(cls) -> list[str]:
        # 按 http → https → all 的优先级收集非空代理环境变量取值（集合见 _LINUX_PROXY_ENV_NAMES：
        # ftp_proxy 刻意不在内）；同名小写优先（POSIX 惯例，curl/wget 亦以小写覆盖大写）。
        values: list[str] = []
        for name in cls._LINUX_PROXY_ENV_NAMES:
            raw = os.getenv(name) or os.getenv(name.upper())
            if raw:
                values.append(raw)
        return values

    def __init__(self) -> None:
        self.__internet_settings = None
        if sys.platform.startswith("win"):
            import winreg

            self.__path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            try:
                # 仅需 KEY_READ：用 KEY_ALL_ACCESS 会让非管理员用户直接开不了键
                key_user = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
                try:
                    self.__internet_settings = winreg.OpenKeyEx(key_user, self.__path, 0, winreg.KEY_READ)
                finally:
                    key_user.Close()
            except OSError as err:
                # 注册表打不开时 OSError 的 str() 可能为空，不带异常类型就只剩一条空白告警，
                # 无法区分权限不足与键不存在。
                logger.warning(i18n.tr("读取代理注册表项失败: {type_name}: {e}", type_name=type(err).__name__, e=err))

    def __del__(self) -> None:
        # 关闭注册表句柄，避免资源泄漏；解构期不得再抛错
        try:
            if self.__internet_settings is not None:
                self.__internet_settings.Close()
        except Exception:
            pass

    def get_proxy_info(self) -> ProxyInfo:
        if sys.platform.startswith("win"):
            return self._get_proxy_info_windows()
        return self._get_proxy_info_linux()

    def is_proxy_enabled(self) -> bool:
        if sys.platform.startswith("win"):
            return self._is_proxy_enabled_windows()
        return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> ProxyInfo:
        # Windows：读注册表 ProxyServer
        ip = port = user = password = scheme = ""
        if self._is_proxy_enabled_windows():
            if self.__internet_settings is None:
                return ProxyInfo()
            import winreg

            try:
                ip_port = cast(str, winreg.QueryValueEx(self.__internet_settings, "ProxyServer")[0])
                if ip_port:
                    # 兼容 "ip:port" 及多段代理配置（如 "http=ip:port;https=ip:port"）
                    first = ip_port.split(";")[0]
                    # 去掉多段代理的协议前缀（http=/https=/socks=），避免 "http=ip" 被误判为非法 IP
                    if "=" in first:
                        # 多段写法的 `http=` / `https=` 描述的是「哪类流量走这条代理」，**不是**代理
                        # 自身的协议，不能当 scheme 用（否则 socks=… 会被误标成 http）；只有段值
                        # 本身带 "://"（部分工具写 "socks5://ip:port"）时才识别协议。
                        first = first.split("=", 1)[1]
                    scheme, hostport = self._split_scheme(first)
                    ip, port, user, password = self._split_host_port(hostport)
            except FileNotFoundError as err:
                # OSError 家族的 str() 可能是空串（socket.timeout 即如此），只打 {e} 会得到一条
                # 空白尾巴、无从归因，故必须带异常类型。本处异常来自注册表读取，不含 URL/凭据。
                logger.warning(i18n.tr("未找到代理信息: {type_name}: {e}", type_name=type(err).__name__, e=err))
            except Exception as err:
                logger.error(i18n.tr("读取系统代理时发生错误: {type_name}: {e}", type_name=type(err).__name__, e=err))
        else:
            logger.debug(i18n.tr("系统未启用代理"))
        return ProxyInfo(ip, port, user, password, scheme)

    def _is_proxy_enabled_windows(self) -> bool:
        # Windows：读注册表 ProxyEnable
        if self.__internet_settings is None:
            return False
        import winreg

        try:
            if cast(int, winreg.QueryValueEx(self.__internet_settings, "ProxyEnable")[0]) == 1:
                return True
        except FileNotFoundError as err:
            # 同上：异常类型必带
            logger.warning(i18n.tr("未找到代理信息: {type_name}: {e}", type_name=type(err).__name__, e=err))
        except Exception as err:
            logger.error(i18n.tr("读取系统代理时发生错误: {type_name}: {e}", type_name=type(err).__name__, e=err))
        return False

    @classmethod
    def _get_proxy_info_linux(cls) -> ProxyInfo:
        # Linux / macOS：读环境变量。与 _is_proxy_enabled_linux 共用同一份候选集合——两个口径
        # 必须一致，否则「判定为有代理」与「取不到地址」会互相矛盾。
        for raw in cls._linux_proxy_values():
            # 按 (scheme, hostport) 拆开并随 ProxyInfo 承载（协议改写风险见 ProxyInfo.scheme）
            scheme, hostport = cls._split_scheme(raw)
            ip, port, user, password = cls._split_host_port(hostport)
            if ip and port:
                return ProxyInfo(ip, port, user, password, scheme)
        return ProxyInfo()

    def _is_proxy_enabled_linux(self) -> bool:
        # 与 _get_proxy_info_linux 同源判定（同一份候选集合），口径必须是「解析出 ip+port 才算有
        # 代理」：原先只判环境变量非空，无端口的代理写法会出现「面板显示有代理、实际直连」的矛盾。
        for raw in self._linux_proxy_values():
            _scheme, hostport = self._split_scheme(raw)
            ip, port, _user, _password = self._split_host_port(hostport)
            if ip and port:
                return True
        return False
