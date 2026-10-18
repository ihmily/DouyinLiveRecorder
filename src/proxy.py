#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
# 代理检测模块 - 检测系统代理配置，支持 Windows 和 Linux 系统

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

# MI-20：本模块日志统一走 i18n（原先 5 处为裸英文 + 字符串拼接，
# 在中文/繁体/英式目录下无法翻译，与仓库其它模块的日志口径不一致）
import i18n

# MIN-2233②：代理自身的协议。注册表/环境变量里出现的 scheme 只有这几种是有意义的
# （curl / wget / requests / httpx 所认集合的并集）；其余形态（"proxy-protocol://" 之类）
# 一律按「没有 scheme」处理——把垃圾串拼进 proxy_url 只会变成下游更难归因的 InvalidURL。
_PROXY_SCHEMES = frozenset(("http", "https", "socks5", "socks5h", "socks4", "socks4a"))


def _is_ip_literal_without_port(value: str) -> bool:
    # MIN-2233③：判定「IPv6 字面量」（裸写 "::1"/"2001:db8::1"，或带方括号 "[::1]"）。
    # 之所以单独放行「无端口」：IPv6 主机在 URL 里**必须**写 [..]，注册表却常存裸写无端口的
    # "::1"（用户填了一半）。判定用 ipaddress 而非正则：缩写形态（::、2001:db8::1、
    # fe80::1%eth0）正则容易漏，而 ipaddress 正是本仓其它内网判定的同款口径。
    # 若不放行，它会落入下面「IP or port cannot be empty」的 raise：该异常被 main.py 外层
    # except 吞成一行 print → global_proxy 仍为 True 但拿不到地址（MIN-20① 记录过的死锁式假象）。
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
    # MIN-20③：认证代理的凭据原先在解析处被 split("@", 1)[1] 直接丢弃，ProxyInfo 只剩
    # ip/port → 上层无法还原可用的代理地址。现单独承载，且 repr=False：该 dataclass 会被
    # print / 记进日志，凭据不得跟着进轮转日志文件。
    user: str = field(default="", repr=False)
    password: str = field(default="", repr=False)
    # MIN-2233②：代理**自身**的协议（来自 all_proxy=socks5://… 这类环境变量的 scheme，
    # 或注册表里显式写出的 "socks5://ip:port"）；空串表示来源未给协议。
    # 旧实现在解析处就把 scheme 丢掉、proxy_url 又恒补 http://，于是
    # `all_proxy=socks5://127.0.0.1:1080` 被静默改写成 HTTP 代理语义——socks 端口不认 HTTP
    # CONNECT，表现为「配了代理却全平台网络异常」，而日志看不出协议被换过。
    scheme: str = field(default="", repr=True)

    @property
    def proxy_url(self) -> str:
        # 还原可直接交给 requests/httpx 的代理地址（含凭据、保留原协议）；无 ip 时返回空串。
        # 与 utils.handle_proxy_addr 的语义一致：来源未给协议时补 http://。
        # 本函数**只负责拼 URL**，不做地址归一——归一点仍唯一留在 utils.handle_proxy_addr
        # （构造客户端之前那一处），不得在这里再补一遍前缀或改大小写。
        if not self.ip:
            return ""
        # L-10：user/password 必须 percent 编码再拼进 userinfo。原先直拼，密码含保留字符时
        # 生成的是**结构错位**的代理 URL：实测 http://u:p#ss@10.0.0.1:8080 被 urlsplit 判成
        # host='ss' + fragment、pa/ss 被切成 path、pa?ss 被切成 query，下游 httpx 直接抛
        # InvalidURL（"Invalid port: 'pa'"）——表现为「配了认证代理却全平台连不上」，
        # 而 ProxyInfo 的 repr 不带凭据，日志里看不出是编码问题。
        # safe="" 的取值判据是「分隔结构一律不能被动过」：userinfo 段里 @ : / ? # 与 % 全部
        # 转义。本模块的契约是 user/password 存**字面原文**（_split_host_port 从不 unquote），
        # 实测 8 种取值（p@ss / p%40ss / pa/ss / pa#ss / pa?ss / 50%off / p:ss / p%）经
        # safe="" 编码后，httpx 解出来的 password 与原文逐字相等（无损）；而 safe="%" 会让
        # 形如 %40 的字面口令被当成转义序列解掉（httpx 交出 'p@ss'，原文是 'p%40ss'）。
        auth = f"{quote(self.user, safe='')}:{quote(self.password, safe='')}@" if self.user else ""
        # IPv6 必须包方括号，否则 "http://::1:8080" 是非法 authority（下游按 InvalidURL 失败）
        host = self.ip if self.ip.startswith("[") or ":" not in self.ip else f"[{self.ip}]"
        prefix = f"{self.scheme}://" if self.scheme else "http://"
        return f"{prefix}{auth}{host}:{self.port}" if self.port else f"{prefix}{auth}{host}"

    # ── MIN-20③ 的**残留登记**（不得当成已修，交主会话/维护者决策）────────────────
    # 上面这些字段（user / password / scheme / proxy_url）在本仓**没有任何生产消费点**：
    #   ① main.py 的代理检测块只读 ip/port 两字段用于打印 System Proxy；
    #   ② 真正下发给 spider/stream 的 proxy_addr 取自 config.ini「录制设置/代理地址」
    #      （main.py 的 proxy_addr_bak），与系统代理检测是两条互不相通的链路；
    #   ③ src/ 下其余模块不 import 本模块。
    # 故「认证代理无法还原完整地址」这条只在**解析层**已修，**生效层**仍未闭合：
    # 系统代理带凭据/带 socks 协议时，录制链路依然收不到它。接上它需要改 main.py
    # （不在本次改动所有权内），因此只在此显式登记，不留「已修好」的错误陈述。

    def __post_init__(self) -> None:
        # 校验 ip/port 组合的合法性；非法形态一律抛 ValueError（调用方 main.py 会吞成一行打印，
        # 见 _is_ip_literal_without_port 的说明）
        if self.ip and not self.port and _is_ip_literal_without_port(self.ip):
            # MIN-2233③：裸/括号 IPv6 字面量允许无端口（判定依据见该函数）。
            #   [历史注] 本处旧注释曾称「交给下方裸 IPv6 分支放行」，实测不成立——那个分支位于
            #   `if self.ip and self.port:` 门内，上一条 raise 先命中，无端口的 "::1" 从来
            #   就没通过；现已就地改为本处早返回。
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

    # MIN-20②：读取的环境变量集合（小写 + 大写两种形态都查）。curl / wget / requests 等主流
    # 工具都同时认这两种大小写，all_proxy 还是「所有协议」的兜底项。
    # MIN-2233①：**刻意不含 ftp_proxy**——本仓全部出站请求都是 http/https（含 HLS/FLV 拉流
    # 与所有平台解析），一个只配了 ftp 代理的机器并不意味着「本程序有代理可用」。旧集合把
    # ftp_proxy 算进 _is_proxy_enabled_linux 的候选，于是 global_proxy=True 成立、解析出的地址
    # 又被下游按 http 代理使用；最坏组合是 ftp_proxy 指向纯 FTP 端口 → 9 个海外平台走
    # 「有代理」分支、实际传给 async_req 的 proxy_address 为空 → 直连境外域名，全平台
    # 「网络异常」而日志却显示「已检测到系统代理」，归因方向被彻底带偏。
    # 需要 FTP 代理的用户属另一场景：本程序不代理 FTP 流量，故不纳入。
    _LINUX_PROXY_ENV_NAMES = ("http_proxy", "https_proxy", "all_proxy")

    @staticmethod
    def _split_scheme(raw: str) -> tuple[str, str]:
        # 把 "socks5://host:port" 拆成 (scheme, "host:port")；无协议返回 ("", 原串)。
        # （为何要拆出 scheme 而非整段丢弃：见 ProxyInfo.scheme / MIN-2233②）
        # 协议不在白名单（"file://"、"proxy://" 等怪值）时**仍剥掉前缀**、只是不记 scheme，
        # 以保留旧实现的宽容度：若改为报错/原样返回，"foo://bar" 会被 _split_host_port 切成
        # port="//bar" → ProxyInfo 校验抛 ValueError → 整个系统代理检测被 main.py 的外层
        # except 吞掉（正是 MIN-20① 记录的「拿不到地址却显示有代理」形态）。
        head, sep, tail = raw.strip().partition("://")
        if not sep:
            return "", raw.strip()
        scheme = head.strip().lower()
        return (scheme if scheme in _PROXY_SCHEMES else ""), tail

    @staticmethod
    def _split_host_port(hostport: str) -> tuple[str, str, str, str]:
        # 把 "user:pass@host:port" / "[::1]:8080" / "10.0.0.1:3128" 拆成
        # (ip, port, user, password)。
        # MIN-20①：Windows 侧原实现是 first.split(":", 1)——注册表 ProxyServer 存
        # "[::1]:8080" 时切出 ip="["、port=":1]:8080"，port 非数字 → __post_init__ 抛
        # ValueError("Port must be a digit…")，于是「专门为 [xxxx] 形态写的放行分支」
        # 永远收不到合法输入（整块校验是死的），异常又被 main.py 外层 except 吞成一行 print
        # （global_proxy 仍为 True 但拿不到地址）。故改 rsplit(":", 1) + 方括号特判。
        # MIN-20③：凭据原先被 split("@", 1)[1] 整段丢弃，认证代理无法还原完整地址（残留
        # 范围见 ProxyInfo 的登记块）。
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
        # 按 http → https → all 的优先级收集非空代理环境变量取值（集合见 _LINUX_PROXY_ENV_NAMES
        # 的 MIN-2233① 说明：ftp_proxy 刻意不在内）；同名的小写优先（POSIX 惯例，
        # curl/wget 亦以小写覆盖大写）。
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
                # MIN-2222 同型第 5 处：注册表打不开时 OSError 的 str() 可能为空，
                # 不带异常类型就只剩一条空白告警，无法区分权限不足与键不存在。
                logger.warning(i18n.tr("读取代理注册表项失败: {type_name}: {e}", type_name=type(err).__name__, e=err))

    def __del__(self) -> None:
        # 关闭注册表句柄，避免资源泄漏；解构期不得再抛错
        try:
            if self.__internet_settings is not None:
                self.__internet_settings.Close()
        except Exception:
            pass

    def get_proxy_info(self) -> ProxyInfo:
        # 获取代理信息（按平台分派）
        if sys.platform.startswith("win"):
            return self._get_proxy_info_windows()
        return self._get_proxy_info_linux()

    def is_proxy_enabled(self) -> bool:
        # 检查代理是否启用（按平台分派）
        if sys.platform.startswith("win"):
            return self._is_proxy_enabled_windows()
        return self._is_proxy_enabled_linux()

    def _get_proxy_info_windows(self) -> ProxyInfo:
        # Windows：读注册表 ProxyServer（内部方法）
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
                        # MIN-2233②：多段写法的 `http=` / `https=` 描述的是「哪类流量走这条代理」，
                        # **不是**代理自身的协议，故不能当 scheme 用（否则 socks=… 那条会被误标成
                        # http，正是本条目要修的语义）。只有段值本身带 "://" 时
                        # （部分工具会写 "socks5://ip:port"）才识别协议。
                        first = first.split("=", 1)[1]
                    scheme, hostport = self._split_scheme(first)
                    ip, port, user, password = self._split_host_port(hostport)
            except FileNotFoundError as err:
                # MIN-2222：Windows 下 OSError 家族的 str() 可能是空串（socket.timeout 即如此），
                # 只打 {e} 会得到一条空白尾巴、完全无从归因，必须带异常类型。
                # 本处异常来自注册表读取，不含 URL/凭据，无需 mask_credentials。
                logger.warning(i18n.tr("未找到代理信息: {type_name}: {e}", type_name=type(err).__name__, e=err))
            except Exception as err:
                logger.error(i18n.tr("读取系统代理时发生错误: {type_name}: {e}", type_name=type(err).__name__, e=err))
        else:
            logger.debug(i18n.tr("系统未启用代理"))
        return ProxyInfo(ip, port, user, password, scheme)

    def _is_proxy_enabled_windows(self) -> bool:
        # Windows：读注册表 ProxyEnable（内部方法）
        if self.__internet_settings is None:
            return False
        import winreg

        try:
            if cast(int, winreg.QueryValueEx(self.__internet_settings, "ProxyEnable")[0]) == 1:
                return True
        except FileNotFoundError as err:
            # MIN-2222：同上，异常类型必带
            logger.warning(i18n.tr("未找到代理信息: {type_name}: {e}", type_name=type(err).__name__, e=err))
        except Exception as err:
            logger.error(i18n.tr("读取系统代理时发生错误: {type_name}: {e}", type_name=type(err).__name__, e=err))
        return False

    @classmethod
    def _get_proxy_info_linux(cls) -> ProxyInfo:
        # Linux / macOS：读环境变量（内部方法）。原先是 @staticmethod 且只读三个小写变量、
        # 只用 split(":", 1)，现与 _is_proxy_enabled_linux 共用同一份候选集合——两个口径必须
        # 一致，否则「判定为有代理」与「取不到地址」会互相矛盾。
        for raw in cls._linux_proxy_values():
            # 按 (scheme, hostport) 拆开并随 ProxyInfo 承载（协议改写风险见 ProxyInfo.scheme / MIN-2233②）
            scheme, hostport = cls._split_scheme(raw)
            ip, port, user, password = cls._split_host_port(hostport)
            if ip and port:
                return ProxyInfo(ip, port, user, password, scheme)
        return ProxyInfo()

    def _is_proxy_enabled_linux(self) -> bool:
        # Linux：与 _get_proxy_info_linux 同源判定（同一份候选集合，见其 MIN-2233① 说明）。
        # L-17（2026-10-02）：判定口径对齐 _get_proxy_info_linux 的「解析出 ip+port 才算有代理」
        # ——原先只判环境变量非空，无端口的代理写法（如 http://127.0.0.1:80，端口缺失形态）
        # 会出现「面板显示有代理、实际直连」的矛盾（MIN-20① 同型归因带偏）。
        for raw in self._linux_proxy_values():
            _scheme, hostport = self._split_scheme(raw)
            ip, port, _user, _password = self._split_host_port(hostport)
            if ip and port:
                return True
        return False
