# src/web_config.py
# Web 管理面板：配置读取与 URL_config.ini 解析/格式化的纯函数模块。
# 不依赖 FastAPI / 网络，便于单测。
from __future__ import annotations

import base64
import configparser
import functools
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import socket
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Iterable, cast

from src.config_bool import parse_config_bool
from src.utils import atomic_write_text

# 与 main.py 保持一致的文本编码
TEXT_ENCODING = "utf-8-sig"


def _tolerant_config_parser() -> configparser.ConfigParser:
    # 读取侧统一走容错解析器（strict=False，重复键后写覆盖前写）。strict=True 下任一节出现
    # 重复键即抛 DuplicateOptionError，而本模块的三个读取点全部处在「每个请求都要过」的路径上
    # （auth_middleware → read_web_config），一次配置损坏就会让面板连 /health 都打不开。
    # 延迟导入：src/config_read.py 在模块级 `from src.web_config import TEXT_ENCODING`，
    # 顶层互导会形成部分初始化导入失败。
    from src.config_read import tolerant_config_parser

    return tolerant_config_parser()


# 内置画质档位全集（对齐 main.py 画质白名单与 src/stream_select.get_quality_code）。
# 元组顺序即 WEB 下拉与 GUI 切换菜单的展示顺序（自高画质到低画质）。
BUILTIN_QUALITIES: tuple[str, ...] = (
    "原画",
    "蓝光",
    "蓝光30M",
    "蓝光20M",
    "蓝光8M",
    "蓝光4M",
    "超清",
    "高清",
    "标清",
    "流畅",
)

# 画质关键词（历史别名，成员判定用；与 BUILTIN_QUALITIES 同一集合）
QUALITY_KEYWORDS = BUILTIN_QUALITIES

# 画质选项在 config.ini 中的落盘位置：[录制设置] 自定义画质选项(逗号分隔)
QUALITY_OPTIONS_SECTION = "录制设置"
QUALITY_OPTIONS_KEY = "自定义画质选项(逗号分隔)"

# 与 main.py CLEAN_URL_HOST_LIST 一致：这些 host 的 URL 去除 query string
CLEAN_URL_HOST_LIST = (
    "live.douyin.com",
    "live.bilibili.com",
    "www.huajiao.com",
    "www.zhihu.com",
    "www.huya.com",
    "chzzk.naver.com",
    "www.liveme.com",
    "www.haixiutv.com",
    "v.6.cn",
    "m.6.cn",
    "www.lehaitv.com",
)

# 默认画质（对齐 main.py）
DEFAULT_QUALITY = "原画"

WEB_DEFAULTS: dict[str, str | int | bool] = {
    "web_host": "127.0.0.1",
    "web_port": 8000,
    "web_auth_enable": False,
    "web_password": "",
    "web_token_expiry": 86400,
    "web_show_console": True,
    "web_minimize_to_tray": True,
    # 可信代理列表（逗号分隔）：仅当直连对端在列表中才信任 X-Forwarded-For
    "web_trusted_proxy": "",
    # 除回环/监听地址外，还允许哪些 Host/Origin 访问面板（逗号分隔）。未列出的
    # **多级域名** Host 会被拒绝，以阻断 DNS 重绑定（attacker.tld → 127.0.0.1）。
    # 绑定 0.0.0.0/:: 的远程部署必须把访问用 IP/域名登记进本键（手工编辑 config.ini——面板
    # 自己对这种请求也回 403，无法经面板完成），否则会「读得到、写不了」。
    "web_allowed_hosts": "",
}


def normalize_url(url: str) -> str:
    # 规范化 URL：补 https://，并对 CLEAN_URL_HOST_LIST 的 host 去除 query。
    url = url.strip()
    if "://" not in url:
        url = "https://" + url
    try:
        host = url.split("/", 3)[2]
    except IndexError:
        return url
    if host in CLEAN_URL_HOST_LIST:
        url = url.split("?")[0]
    return url


def parse_url_config(file_path: str | Path) -> list[dict[str, str | bool]]:
    # 解析 URL_config.ini，返回直播间列表。
    # 每项: {url, quality, name, enabled, raw_line}
    # 行格式: [画质,]URL[,主播: 名称]，# 前缀表示注释（禁用）。
    rooms: list[dict[str, str | bool]] = []
    path = Path(file_path)
    if not path.exists():
        return rooms

    with path.open("r", encoding=TEXT_ENCODING, errors="ignore") as f:
        for raw_line in f:
            line = raw_line.rstrip("\n").rstrip("\r")
            stripped = line.strip()
            if not stripped:
                continue

            enabled = True
            content = stripped
            if content.startswith("#"):
                enabled = False
                content = content.lstrip("#").strip()

            parts = re.split(r"[,，]", content)

            quality = DEFAULT_QUALITY
            url = ""
            name = ""

            if len(parts) == 1:
                url = parts[0].strip()
            elif len(parts) == 2:
                if _is_url(parts[0]):
                    url = parts[0].strip()
                    name = parts[1].strip()
                else:
                    quality = _normalize_quality(parts[0].strip())
                    url = parts[1].strip()
            elif _is_url(parts[0]):
                # 3 段以上且首段就是网址 → **未写画质**，第二段起全是主播名。与 main.py 主循环行解析逐字同规则。
                # [历史注] 旧实现无条件按「画质,URL,名称」定序：含逗号的主播名被拆成假房间 URL，
                # 面板渲染出不存在的房间、真行既改不了也删不掉。
                url = parts[0].strip()
                name = "，".join(p.strip() for p in parts[1:])
            else:
                quality = _normalize_quality(parts[0].strip())
                url = parts[1].strip()
                name = "，".join(p.strip() for p in parts[2:])

            if name.startswith("主播:"):
                name = name[len("主播:") :].strip()
            elif name.startswith("主播："):
                name = name[len("主播：") :].strip()

            if not url:
                continue

            url = normalize_url(url)
            rooms.append(
                {
                    "url": url,
                    "quality": quality,
                    "name": name,
                    "enabled": enabled,
                    "raw_line": raw_line,
                }
            )
    return rooms


def _is_url(s: str) -> bool:
    return "://" in s or "." in s


def _normalize_quality(q: str) -> str:
    q = q.strip()
    return q if q in QUALITY_KEYWORDS else DEFAULT_QUALITY


def _reject_newline(kind: str, value: str) -> None:
    # 换行注入防护：URL_config.ini 行级格式，任何字段含换行即可伪造额外配置行
    if value and ("\n" in value or "\r" in value):
        raise ValueError(f"{kind} 含换行符，禁止写入配置文件")


def _reject_list_separator(kind: str, value: str) -> None:
    # 写侧配套：主播名与 URL 段都不得含 `,` / `，`。行格式以逗号（含全角）为**字段分隔符**，
    # 两端读取侧都是先 `re.split("[,，]", line)` 切段再判形：名字带逗号会被拆段后以「，」重连
    # （与写入原文不同）；地址带逗号只取到首个逗号前（面板显示与实际拉流地址不一致，且按
    # 规范化 URL 精确匹配行，用户既看不出也改不动）。与其让两端各猜一次，不如在唯一写入口
    # 直接拒绝，把「同一行在两处解析成不同房间」这条缝隙从源头堵掉。
    # 画质段是 BUILTIN_QUALITIES 白名单值、本就无逗号；读取侧对**历史已存在**的含逗号行维持
    # 原解析行为不改（老配置只会按旧的截断语义继续跑，不会因写侧收紧而读不出或崩）。
    if value and ("," in value or "，" in value):
        raise ValueError(f"{kind} 含逗号（半角或全角），逗号是配置行的字段分隔符，请改用其他写法")


def format_url_line(url: str, quality: str | None = None, name: str | None = None) -> str:
    # 格式化一行 URL_config.ini 内容（不含换行）。
    # - 仅 URL：返回 url
    # - 画质+URL：返回 "画质,url"
    # - 全部：返回 "画质,url,主播: 名称"
    # quality 为空或默认"原画"时省略画质段（与 main.py 风格一致）。
    #
    # 校验**下沉**到本函数（URL_config.ini 的唯一写入口）。旧结构是「各端点各自先调
    # validate_room_target 再调本函数」，漏调一次即留一条无校验的写入口。接口层再显式调用只是冗余的第二道。
    validate_room_target(url, quality, name)
    _reject_newline("URL", url)
    _reject_newline("画质", quality or "")
    _reject_newline("主播名", name or "")
    # 与 validate_room_target 同一判据的第二道（本函数是唯一写入口，与上方下沉同一理由：任何调用方漏调一次都不该写出坏行）
    _reject_list_separator("主播名", name or "")
    # URL 段的第二道，同上——「先 validate 再自行拼行」的调用方同样不该写出被读取侧截断的行
    _reject_list_separator("URL", url)
    url = normalize_url(url)
    parts: list[str] = []
    q = (quality or "").strip()
    if q and q != DEFAULT_QUALITY:
        parts.append(q)
    parts.append(url)
    n = (name or "").strip()
    if n:
        parts.append(f"主播: {n}")
    return ",".join(parts)


def validate_config_target(section: str, key: str, value: str) -> None:
    # 校验 /api/config 写入目标：值含换行即拒绝（同换行注入防护，避免伪造配置行）
    _reject_newline(f"配置项 [{section}] {key} 的值", value)
    # MID-N45：再叠一层「出站目标」收口（仅对下表白名单内的 URL 类键生效）。落点选在这里而不是
    # 各端点：它是 config.ini 写侧唯一的校验入口，房间侧的教训（漏调一次即留一条无校验写入口）
    # 在这里同样成立，故把裁决绑进入口而非调用方。
    _validate_outbound_target_value(key, value)


# 直播间地址的 scheme / 目标校验。这道防线的由来：main.py 分发表的末项 `_match_stream_suffix(".m3u8", ".flv")`
# 用**子串包含**判定，形如 http://127.0.0.1:8080/manager/x?a=.flv 会被判成「自定义录制直播」，原始 URL
# 原样进入 ffmpeg 的 -i —— 即服务端可被驱动去请求攻击者指定的内网地址（盲 SSRF），
# 成败还能通过回读 streamget.log 区分（可回显侧信道）。
# [历史注] 此前的字符串前缀黑名单实测可被十进制/八进制缩写、带端口 IPv6、CGNAT、云元数据 IP 穿透，
# 现改为 ipaddress 语义 + DNS 解析双道判定。
_ALLOWED_ROOM_SCHEMES = frozenset(("http", "https"))

# Python 3.14 的 ipaddress 按 IANA 特别用途注册表判定 is_private，**100.64.0.0/10
# （CGNAT，RFC 6598）不再算私网**（实测 ip_address("100.64.0.1").is_private 为 False），
# 故共享地址空间等「不是私网但同样不该被录制链路访问」的网段必须显式列出。
_EXTRA_BLOCKED_V4_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT/共享地址空间（阿里云元数据 100.100.100.200 落于其中）
    ipaddress.ip_network("0.0.0.0/8"),  # 「本机」语义，含 0.x 缩写形态
    ipaddress.ip_network("198.18.0.0/15"),  # 基准测试段
    ipaddress.ip_network("192.0.0.0/24"),  # IETF 协议分配段
)

# IPv6 过渡技术前缀：is_private 为真但**不得**据此拦截（理由见 _internal_ip_reason）
_V6_TRANSITION_NETWORKS = (
    ipaddress.ip_network("2001::/32"),  # Teredo
    ipaddress.ip_network("2002::/16"),  # 6to4
)

# 云厂商元数据端点：即使所在网段已被上面的判定覆盖，也单列一份以给出准确告警文案。
_CLOUD_METADATA_IPS = frozenset(
    (
        "169.254.169.254",  # AWS / OpenStack / GCP 通用
        "169.254.170.2",  # AWS ECS 容器凭据
        "100.100.100.200",  # 阿里云（落在 100.64.0.0/10 内，但 3.14 起该段不算私网）
        "169.254.0.4",  # 腾讯云（元数据 IP 形态）
    )
)

# 内部/保留用途域名后缀（无需 DNS 即可定罪，保证离线环境与 DNS 被污染时同样拦截）
_INTERNAL_NAME_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",  # RFC 6762 私有解析 + AWS 的 *.ec2.internal，覆盖 metadata.google.internal
    ".home.arpa",  # RFC 8375 家庭网络域
    ".localdomain",
    ".invalid",
    ".test",
    ".onion",
    ".i2p",
)
_INTERNAL_NAME_EXACT = frozenset(
    (
        "localhost",
        "metadata",
        "metadata.tencentyun.com",  # 腾讯云元数据的域名形态（公网侧解析亦指向链路本地）
        "ip6-localhost",
        "ip6-loopback",
    )
)

# MID-N45：allow_local_targets=True 时豁免的「本机」名字（代理/SMTP 写成 localhost:7890 合法，
# 见 _host_internal_reason 同名参数注释）。刻意**不含** metadata 族与 *.local / *.internal。
_LOCAL_NAME_EXACT = frozenset(("localhost", "ip6-localhost", "ip6-loopback"))
_LOCAL_NAME_SUFFIX = ".localhost"


def _strip_host_port(value: str) -> str:
    # 去掉 IPv6 方括号与 :端口，返回纯主机名（小写）。用 rsplit 而非 urlparse，
    # 因为调用方给的可能只是 Host 头（含端口、无 scheme）而非完整 URL。
    h = value.strip().lower()
    if h.startswith("["):
        end = h.find("]")
        if end > 0:
            return h[1:end]
    if h.count(":") == 1:
        h = h.rsplit(":", 1)[0]
    return h.strip().rstrip(".")


def _parse_aton_part(part: str) -> int | None:
    # inet_aton 的段解析：0x 前缀为十六进制、0 前缀为八进制、其余十进制；空段/非数字返回 None
    if not part:
        return None
    low = part.lower()
    if low.startswith("0x"):
        digits, base, allow = part[2:], 16, "0123456789abcdef"
    elif part[0] == "0" and len(part) > 1:
        digits, base, allow = part[1:], 8, "01234567"
    else:
        digits, base, allow = part, 10, "0123456789"
    if not digits or any(ch not in allow for ch in digits.lower()):
        return None
    try:
        return int(digits, base)
    except ValueError:
        return None


def _ipv4_from_aton(host: str) -> ipaddress.IPv4Address | None:
    # 把 inet_aton 允许但 ipaddress 拒绝的缩写形态（2130706433 / 0177.0.0.1 / 127.1 / 0x7f.0.0.1）
    # 还原成规范 IPv4：这些形态最终都会被 glibc/Windows 的解析器还原为 127.0.0.1，必须在**本层**同款归一；
    # 若当作主机名交给 DNS，等于「看起来不像 IP 就先放行」。
    parts = host.split(".")
    n = len(parts)
    if not 1 <= n <= 4:
        return None
    last_index = n - 1
    total = 0
    for i, part in enumerate(parts):
        value = _parse_aton_part(part)
        if value is None:
            return None
        if i < last_index:
            # 非末段各占一个字节（大端序），末段可独占剩余 1~4 个字节
            if value > 255:
                return None
            total |= value << (8 * (3 - i))
        elif value >= 1 << (8 * (5 - n)):
            return None
        else:
            total |= value
    try:
        return ipaddress.IPv4Address(total)
    except ValueError:
        return None


def _parse_ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    # 主机名为 IP 字面量时返回可判定的地址对象，否则返回 None（交给 DNS）
    name = _strip_host_port(host)
    if not name:
        return None
    # 去掉 IPv6 的 %zone（fe80::1%eth0 与 fe80::1 是同一目标）
    name = name.split("%", 1)[0]
    try:
        return ipaddress.ip_address(name)
    except ValueError:
        return _ipv4_from_aton(name)


def _in_always_blocked_v4_network(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # 「即使允许本机/内网目标也仍然拒绝」的 v4 段（0.0.0.0/8 的本机语义、基准测试段、
    # IETF 协议分配段）。CGNAT 100.64.0.0/10 在 3.14 已不算私网，走函数末尾的同一条分支，
    # 因此不需要在这里重复列出，但它同样属于「恒拒绝」。
    return isinstance(addr, ipaddress.IPv4Address) and any(addr in net for net in _EXTRA_BLOCKED_V4_NETWORKS)


def _internal_ip_reason(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_local_targets: bool = False
) -> str | None:
    # 返回 None 表示该地址可放行；否则给出拒绝理由（写进 422 文案，只含地址不含本地信息）
    #
    # allow_local_targets：代理地址 / SMTP 服务器两类配置项的「本机与私网」目标是主流合法形态
    # （用户普遍把代理写成 127.0.0.1:7890），按房间地址那套内网收口判会全部误杀。置 True 时只放行
    # **回环 + RFC1918 私网**，链路本地 / 云元数据 / 未指定 / 组播 / 保留 / CGNAT 仍一律拒绝——
    # 那些不是任何人的代理，且正是 SSRF 的 payoff 目标。回环族的**域名**形态（localhost /
    # *.localhost）同步放行，见 _host_internal_reason 的同名参数。
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        # :ffff:127.0.0.1 这类 IPv4 映射地址必须按其承载的 v4 判定，否则 v6 侧一律「公网」
        return _internal_ip_reason(mapped, allow_local_targets=allow_local_targets)
    text = str(addr)
    if text in _CLOUD_METADATA_IPS:
        return f"云厂商元数据端点: {text}"
    if addr.is_loopback:
        if allow_local_targets:
            return None
        return f"回环地址: {text}"
    if addr.is_unspecified:
        return f"未指定地址(0.0.0.0/::): {text}"
    if addr.is_link_local:
        return f"链路本地地址(含 169.254.0.0/16): {text}"
    if addr.version == 6 and any(addr in net for net in _V6_TRANSITION_NETWORKS):
        # IPv6 过渡技术前缀（Teredo 2001::/32、6to4 2002::/16）在 IANA 注册表里「不是全局可聚合」，
        # Python 3.14 因此把其 is_private 判成 True——但真实公共服务确实会把 AAAA 发在这段
        # （本机实测 www.youtube.com → 2001::1）。当内网拦会砍掉可用的海外房间，而攻击者也无法
        # 借这两段指向目标机的回环（需要 Teredo/6to4 中继，且 Teredo 内嵌的是客户端自己的公网 IPv4）。
        return None
    if addr.is_private:
        # allow_local_targets 只放行「用户自己网络」那部分私网（RFC1918 / ULA），0.0.0.0/8「本机」
        # 语义段与基准测试段等仍拒绝——它们既不是任何人的代理，又是缩写/绕路写法常见的落点
        # （判定与函数末尾的 _EXTRA_BLOCKED_V4_NETWORKS 同源）。
        if allow_local_targets and not _in_always_blocked_v4_network(addr):
            return None
        return f"私网地址: {text}"
    if addr.is_multicast:
        return f"组播地址: {text}"
    if addr.is_reserved:
        return f"保留地址: {text}"
    if isinstance(addr, ipaddress.IPv4Address) and any(addr in net for net in _EXTRA_BLOCKED_V4_NETWORKS):
        return f"共享/保留网段(CGNAT 等): {text}"
    return None


def _resolve_host_ips(host: str) -> list[str]:
    # DNS 解析 seam：单列成函数便于用例打桩（测试不依赖真实网络，见 tests/test_web_config.py）。
    # 同时查 A/AAAA（family=AF_UNSPEC），任一结果指向内部即整体拒绝。
    infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    return [_strip_host_port(cast(str, info[4][0])) for info in infos]


def offline_internal_reason(host: str) -> str | None:
    # 只做「离线即可定罪」的内网判定：IP 字面量 + 内部用途域名后缀，**不解析 DNS**。
    # 供无法使用本机解析结论的调用方复用：「经代理出站」时不能按本机 DNS 结果拒绝（境外域名本机
    # 查不到是常态、代理却可解析），但「metadata、*.internal、*.local」从来不是合法流地址，
    # 与解析结果无关，必须照样拦。
    # 返回 None 只表示「本层无法定罪」，不代表可放行——调用方自行决定后续口径。
    # 名字表与 _host_internal_reason 共用同一组常量，不另建第二份清单。
    literal = _parse_ip_literal(host)
    if literal is not None:
        return _internal_ip_reason(literal)
    name = _strip_host_port(host)
    if not name:
        return "缺少主机名"
    if name in _INTERNAL_NAME_EXACT or any(name.endswith(suffix) for suffix in _INTERNAL_NAME_SUFFIXES):
        return f"本机/内部用途域名: {name}"
    return None


# 「主机名无法解析」理由前缀：单列常量供探针侧（src/async_http.py::get_response_status）区分
# 「DNS 解析失败（含瞬时故障）」与「内网/保留目标」两类拒绝——本函数的返回值就是字符串，前缀
# 对齐是现有接口下最窄的判别面；改动下方 OSError 分支的理由文案必须同步本常量。
DNS_UNRESOLVABLE_REASON_PREFIX = "主机名无法解析"


def _host_internal_reason(host: str, *, allow_local_targets: bool = False) -> str | None:
    # 判定主机名是否指向本机/内网/保留目标，返回拒绝理由或 None（可放行）。
    # 顺序：IP 字面量（含缩写形态）→ 内部用途域名后缀（离线即可定罪）→ DNS 解析结果。
    # **DNS 重绑定无法由本层挡住**：这里解析的是「写入配置那一刻」的 A/AAAA 记录，而真正发起连接的是
    # 稍后独立解析的 ffmpeg——需在出站网络层按目标地址收口，或拉流前二次校验。同理，sslip.io / nip.io
    # 这类「把 IP 编码进域名」的服务只能靠解析结果识别。
    # allow_local_targets：代理 / SMTP 类配置项放行回环与 RFC1918（含 localhost 的域名形态），
    # 但 metadata / *.internal / *.local 这类「内部用途名字」**不**跟着放行——它们从来不是代理
    # 或邮件服务器的合法写法，而 *.local / *.internal 正是集群内元数据服务的常用名字。
    literal = _parse_ip_literal(host)
    if literal is not None:
        return _internal_ip_reason(literal, allow_local_targets=allow_local_targets)
    name = _strip_host_port(host)
    if not name:
        return "直播间地址缺少主机名"
    if allow_local_targets and (name in _LOCAL_NAME_EXACT or name.endswith(_LOCAL_NAME_SUFFIX)):
        return None
    if name in _INTERNAL_NAME_EXACT or any(name.endswith(suffix) for suffix in _INTERNAL_NAME_SUFFIXES):
        return f"本机/内部用途域名: {name}"
    try:
        addresses = _resolve_host_ips(name)
    except OSError:
        # 解析失败（NXDOMAIN / 无 DNS）：一律拒绝。放行等于让录制链路去撞一个不可达目标，
        # 且会把「拼错的地址」伪装成「已通过的校验」，比拒绝更难排查
        return f"{DNS_UNRESOLVABLE_REASON_PREFIX}: {name}"
    if not addresses:
        return f"主机名无解析结果: {name}"
    for ip_text in addresses:
        parsed = _parse_ip_literal(ip_text)
        if parsed is None:
            continue
        reason = _internal_ip_reason(parsed, allow_local_targets=allow_local_targets)
        if reason is not None:
            return f"主机名 {name} 解析到{reason}"
    return None


def _check_url_target(
    raw_url: str,
    *,
    kind: str,
    allowed_schemes: frozenset[str],
    default_scheme: str | None,
    allow_local_targets: bool,
    hint: str = "",
) -> None:
    # 共用内核：房间地址与推送/SMTP/代理类配置键曾各写一份「scheme + 目标网段」判定，正是两条
    # 写入口分叉的成因（房间侧修过同一形态）。现在两处共用本函数，差异只以参数表达，
    # 任何一侧收紧都会同时作用于另一侧：
    #   kind                文案前缀（"直播间地址" / f"配置项「{key}」"）
    #   allowed_schemes     允许的协议集合
    #   default_scheme      省略协议时按哪个协议判定；None = 必须显式写出协议（房间地址补 https、
    #                       代理允许裸 ip:port 补 http；推送地址会被原样交给 urllib 的 Request，
    #                       缺协议时它本来就抛 ValueError，故不替用户猜）
    #   allow_local_targets 是否放行回环/私网目标（见 _host_internal_reason 同名参数）
    #   hint                追加到拒绝文案尾部的「怎么办」
    from urllib.parse import urlparse

    u = raw_url.strip()
    if not u:
        return
    if "://" in u:
        probe = u
    elif default_scheme:
        probe = f"{default_scheme}://{u}"
    else:
        probe = u
    parsed = urlparse(probe)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allowed_schemes:
        raise ValueError(f"{kind}协议不允许: {scheme or '(空)'}（仅支持 {'/'.join(sorted(allowed_schemes))}）")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(f"{kind}缺少主机名")
    # 拒绝内网/本机/链路本地/云元数据地址（含 userinfo、端口、缩写 IPv4 与 IPv6 形态）
    reason = _host_internal_reason(host, allow_local_targets=allow_local_targets)
    if reason is not None:
        raise ValueError(f"{kind}{reason}，禁止写入{hint}")


def _validate_room_url_target(raw_url: str) -> None:
    # 房间地址侧的薄封装：参数即「本仓对直播间地址的既有口径」，勿在此另立规则。
    _check_url_target(
        raw_url,
        kind="直播间地址",
        allowed_schemes=_ALLOWED_ROOM_SCHEMES,
        default_scheme="https",  # 允许省略协议（normalize_url 会补 https），按 host 段校验
        allow_local_targets=False,
    )


def validate_room_target(url: str, quality: str | None = None, name: str | None = None) -> None:
    # 校验房间写入目标（URL/画质/主播名均不得含换行）
    _reject_newline("URL", url)
    _reject_newline("画质", quality or "")
    _reject_newline("主播名", name or "")
    # 写侧第二道。判据必须落在**公共入口**上才成立：只写在 format_url_line 里时，「先 validate
    # 再自行拼行」的调用方仍能写出含逗号的主播名；这里补上后两处调用点各自都挡得住（幂等，不重复报错）。
    _reject_list_separator("主播名", name or "")
    # URL 段并入同一判据：读取侧都以逗号切段，含逗号地址一律在首个逗号处截断后才进 ffmpeg，
    # 写侧不挡等于「录入一条、生效另一条」；判据同样落在公共入口而非各端点。
    _reject_list_separator("URL", url)
    # 追加 scheme 与目标网段校验（见 _validate_room_url_target 说明）
    _validate_room_url_target(url)
    # 画质白名单落在公共校验入口：录制引擎对白名单外的档位名会**静默回退成原画**，写进去就是
    # 一个永不生效的档位；三个写入口（新增/改写/切画质）必须共用同一份裁决，否则又会出现「某个接口漏校验」。
    q = (quality or "").strip()
    if q and q not in BUILTIN_QUALITIES:
        raise ValueError(f"未知画质档位: {q}")


# ─── 推送 / SMTP / 代理地址类配置键的出站目标收口 ───────────────────
# 这些键的值不走录制链路，而是被**本进程自己**发出去：推送接口地址 → msg_push.py 逐段
# opener.open(Request(url))（dingtalk/xizhi/bark/ntfy 还会先按逗号拆成多目标）；smtp邮件服务器
# → smtplib 连接；代理地址 → 全部出站请求的落地主机。它们是「房间地址」这条信任边界上的第二条出口，
# 房间侧的内网收口对这里完全无效。且这些全局量在 main.py 的热重载循环里每轮重读，改一次即持续生效、
# 无需重启——写入口的严重性由此放大。

# 推送类：值必须是公网可达的 http(s) 接口地址（多目标逗号分隔，逐段判定）
_PUSH_URL_KEYS = frozenset({"钉钉推送接口链接", "微信推送接口链接", "bark推送接口链接", "ntfy推送地址"})
# 代理 / SMTP：值可以落在用户自己的网络里（见下方 _allow_internal_outbound_target 的说明）
_PROXY_ADDR_KEYS = frozenset({"代理地址"})
_SMTP_HOST_KEYS = frozenset({"smtp邮件服务器"})
# 代理协议集合：requests/httpx 支持的形态；裸 ip:port 由 http 兜底补前缀，
# 与 utils.handle_proxy_addr / sync_http 的归一同源（不得收紧成只允许 http/https，
# 那会把 socks5:// 这种本仓支持的写法判成非法）。
_PROXY_SCHEMES = frozenset(("http", "https", "socks4", "socks4a", "socks5", "socks5h"))

_INTERNAL_TARGET_HINT = (
    "；确需指向本机/内网自建服务（如与录制器同机部署的 ntfy），"
    "请设置环境变量 DOUYIN_WEB_ALLOW_INTERNAL_TARGET=1 后重启本进程"
)


def _allow_internal_outbound_target() -> bool:
    # 破例通道。刻意**不复用** DOUYIN_WEB_ALLOW_INSECURE：后者语义是「明知风险仍要把无认证面板
    # 暴露到局域网」，web.py 启动检查与鉴权中间件都在读它；挂同一枚开关上，所有「只是想看局域网
    # 面板」的用户会连带失去「推送地址不得指向内网」这条防线——那是静默放宽。
    # 单列一枚需显式设置、且每次判定时现读（不缓存、不在导入期固化）的开关，把两件事解耦。
    return os.environ.get("DOUYIN_WEB_ALLOW_INTERNAL_TARGET", "").strip().lower() in ("1", "true", "yes")


def _key_matches(key: str, table: frozenset[str]) -> bool:
    # 键名判定必须大小写不敏感：configparser 的 option 本就 casefold，而写入侧的行匹配带
    # re.IGNORECASE，只按规范写法精确比较等于给 BARK推送接口链接 / SMTP邮件服务器 留绕过路径。
    folded = key.strip().casefold()
    return any(folded == candidate.casefold() for candidate in table)


def _validate_outbound_target_value(key: str, value: str) -> None:
    # config.ini 写侧的「值会被本进程发出去」类键校验；不在表内的键直接返回。
    # 抛 ValueError 由 web_api 统一转成 422 + 中文文案（与房间地址同一口径），
    # 故这里的每条消息都是面板可见的、必须回答「为什么 + 怎么办」。
    stripped = value.strip()
    if not stripped:
        # 空值 = 未启用（不配代理 / 不推送），与房间地址「占位行」同口径放行；
        # 敏感键的空值另有 web_api 守卫在前面拦成 400。
        return
    kind = f"配置项「{key.strip()}」"
    if _key_matches(key, _PUSH_URL_KEYS):
        # 逗号分隔多目标必须**逐段**校验：msg_push 对每一段都发一次请求，
        # 只要有一段指向内网，整串就仍是一条可用的 SSRF 出口（只判首段等于没判）。
        # 拆分复用 _split_multi_value（含全角逗号归一），与推送侧的拆分口径逐字一致，
        # 避免出现「校验按 A 口径拆、发送按 B 口径拆」的缝隙。
        for segment in _split_multi_value(stripped):
            _check_url_target(
                segment,
                kind=kind,
                allowed_schemes=_ALLOWED_ROOM_SCHEMES,
                default_scheme=None,  # 推送地址缺协议时 urllib 本就报错，要求显式 http(s)://
                allow_local_targets=_allow_internal_outbound_target(),
                hint=_INTERNAL_TARGET_HINT,
            )
        return
    if _key_matches(key, _PROXY_ADDR_KEYS):
        # 代理地址按 allow_local_targets=True 判定：本仓文档与 src/sync_http.py 的归一注释都记着
        # 「用户普遍写 127.0.0.1:7890」，按房间口径会把合法写法整体误杀。
        # 本层能收口的是协议（拒绝 file/gopher/dict 之类）与目标类别（链路本地 / 云元数据 /
        # 0/8 / 组播 / 保留 / CGNAT 一律拒绝）；「回环代理指向 Redis」这类同机端口探测
        # 无法在本层区分合法代理与内网服务，须在出站网络层收口，不在此假装闭合。
        _check_url_target(
            stripped,
            kind=kind,
            allowed_schemes=_PROXY_SCHEMES,
            default_scheme="http",  # 裸 ip:port 写法（handle_proxy_addr 同款归一）
            allow_local_targets=True,
        )
        return
    if _key_matches(key, _SMTP_HOST_KEYS):
        # SMTP 值是裸主机名（可带端口）：smtplib.SMTP(host, port) 直接吃它。
        # 必须先把入参形态钉住再判主机——否则 "http://127.0.0.1:6379/" 会被 _strip_host_port
        # 打成一根认不出也不是 IP 的怪串（冒号不止一个 → 端口不剥），从而蒙过全部网段判定。
        if "://" in stripped or any(ch.isspace() for ch in stripped):
            raise ValueError(f"{kind}应填主机名或 IP（可带 :端口），不得含协议前缀或空白")
        host = _strip_host_port(stripped)
        reason = _host_internal_reason(host, allow_local_targets=True) if host else "缺少主机名"
        if reason is not None:
            raise ValueError(f"{kind}{reason}，禁止写入")


# ─── 画质选项（WEB 下拉 / GUI 切换菜单共用，落地 config.ini） ────────────────


# 拆分逗号分隔的多值配置（支持全角逗号），逐项 strip 并丢弃空项
def _split_multi_value(raw: str) -> list[str]:
    return [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]


# 规范化画质选项：仅保留内置档位并去重（保持传入顺序），结果为空时回退内置全集。
# 为什么不放开任意名称：main.py 对行首画质段做白名单校验，白名单外的名称会被静默
# 回退成「原画」，让用户勾选一个永远不生效的档位比不给他选更糟。
def normalize_quality_options(options: Iterable[str]) -> list[str]:
    result: list[str] = []
    for item in options:
        name = (item or "").strip()
        if name in BUILTIN_QUALITIES and name not in result:
            result.append(name)
    return result or list(BUILTIN_QUALITIES)


# 读取用户勾选的画质选项；键缺失/为空/全部非法时回退内置全集（首次使用行为不变）
def read_quality_options(config_file: str | Path) -> list[str]:
    parser = _tolerant_config_parser()
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    raw = ""
    if parser.has_section(QUALITY_OPTIONS_SECTION):
        raw = parser.get(QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, fallback="")
    return normalize_quality_options(_split_multi_value(raw))


# 写回画质选项（行级更新，保留注释与节顺序）；返回实际落盘的规范化列表，写失败返回 None
def write_quality_options(config_file: str | Path, options: Iterable[str]) -> list[str] | None:
    # 换行注入防护必须在 normalize 之前做：normalize 会把含换行的项静默丢掉，
    # 那时再校验就感知不到了（与 format_url_line 同款）。
    raw_list = list(options)
    for item in raw_list:
        _reject_newline("画质选项", str(item))
    normalized = normalize_quality_options(raw_list)
    value = ",".join(normalized)
    _reject_newline("画质选项", value)
    # 键缺失（历史 config.ini 无此项）时补建到目标节内，不改其余内容；
    # 替换/补建两步经 update_or_append_config_line 持锁原子化，防并发补建重复行。
    # 写失败必须回报：返回值是「规范化列表 或 None（写失败）」——旧实现丢弃
    # update_or_append_config_line 的布尔值，config.ini 缺失/原子写失败时仍返回 ok 而磁盘未变。
    ok = update_or_append_config_line(config_file, QUALITY_OPTIONS_SECTION, QUALITY_OPTIONS_KEY, value)
    return normalized if ok else None


# ─── URL_config.ini 房间画质保序改写 ──────────────────────────────────────


# 段是否像网址（仅需区分画质槽位与 URL 段，故只判 scheme，不用完整 URL 正则）
def _looks_like_url(segment: str) -> bool:
    return "://" in segment


# 段级 URL 匹配：配置行里的 URL 段可能缺 scheme 或带 query，统一规范化后比较，
# 避免 "live.douyin.com/1" 与 "https://live.douyin.com/1" 判为两行。
# 主播名字段直接排除——即便它含点号也不会被 normalize_url 误判成网址。
def _segment_matches_url(segment: str, url: str) -> bool:
    seg = segment.strip()
    if not seg or seg.startswith(("主播:", "主播：")):
        return False
    return seg == url or normalize_url(seg) == url


# 重写单行配置的画质段；行不匹配 URL 或已是目标画质时返回 None（无需变更）。
# 行格式: [画质,]URL[,主播: 名称]——画质槽位是 URL 段之前的那一段（与 main.py 的行
# 解析约定一致），注释前缀、行尾换行、主播名字段与 URL 原文全部保留。
def _rewrite_quality_field(raw_line: str, url: str, quality: str) -> str | None:
    stripped = raw_line.rstrip("\r\n")
    eol = raw_line[len(stripped) :]
    comment_prefix = ""
    body = stripped
    # 行首可有缩进 + `#` + 可选空白；完整前缀（含 `#` 与其后的空格）一并保留，
    # 避免 `# 注释` 被改写成 `#注释` 这种风格损坏
    m = re.match(r"^(\s*#\s*)", body)
    if m:
        comment_prefix = m.group(1)
        body = body[m.end() :]
    if not body.strip():
        return None

    segments = [seg.strip() for seg in re.split(r"[,，]", body)]
    url_idx = -1
    for i, seg in enumerate(segments):
        if _segment_matches_url(seg, url):
            url_idx = i
            break
    if url_idx < 0:
        return None

    # 目标画质：空或默认「原画」时移除画质段，让该房间回落到全局默认画质
    target_q = quality if quality and quality != DEFAULT_QUALITY else ""
    # 画质槽位：URL 段之前的首段。该段本身像网址时（异常行 "URL1,URL2"）不动它，
    # 避免把数据当成画质静默吞掉
    slot_idx = url_idx - 1 if url_idx > 0 and not _looks_like_url(segments[0]) else -1
    if (segments[slot_idx] if slot_idx >= 0 else "") == target_q:
        return None  # 已是目标画质，幂等跳过

    keep = [seg for i, seg in enumerate(segments) if i not in (url_idx, slot_idx) and seg]
    rebuilt_parts: list[str] = []
    if target_q:
        rebuilt_parts.append(target_q)
    rebuilt_parts.append(segments[url_idx])
    rebuilt_parts.extend(keep)
    return f"{comment_prefix}{','.join(rebuilt_parts)}{eol}"


# 将 URL_config.ini 中指定 URL 所在行的画质段更新为 quality；返回是否发生变更。
# quality 为空或等于 DEFAULT_QUALITY 时移除画质段（写为 "URL[,主播: 名称]"）；
# 否则按「画质,URL[,主播: 名称]」写入（如 "超清,https://live.douyin.com/745964462470"）。
# 未命中 URL / 已是目标画质 / 文件不存在均返回 False。
# 原子写（临时文件 + os.replace）：与录制子进程无跨进程锁，避免读到半写内容。
def update_room_quality(url_config_file: str | Path, url: str, quality: str | None) -> bool:
    if not url:
        return False
    target = normalize_url(url)
    new_quality = (quality or "").strip()
    _reject_newline("画质", new_quality)

    path = Path(url_config_file)
    if not path.exists():
        return False
    # newline=""：读/写均不做换行符翻译，保留文件原有的 \n / \r\n 行尾风格。
    # 读必须与写同在 _config_write_lock 内——读取在锁外时两个线程的 read-modify-write
    # 仍可交错（后写者基于旧快照覆盖前写者）。本锁是**进程内**锁：GUI 与 Web 分属两个进程时
    # 仍靠 config_io 侧的 main.file_update_lock 兜底。
    with _config_write_lock:
        with path.open("r", encoding=TEXT_ENCODING, newline="") as f:
            lines = f.readlines()

        changed = False
        out_lines: list[str] = []
        for raw_line in lines:
            rewritten = _rewrite_quality_field(raw_line, target, new_quality)
            if rewritten is not None:
                changed = True
                out_lines.append(rewritten)
            else:
                out_lines.append(raw_line)
        if not changed:
            return False

        joined = "".join(out_lines)
        # 不得丢弃返回值：_atomic_write_text 在临时文件创建 / os.replace 失败时明确返回 False，
        # 丢弃它等于把「磁盘里什么都没变」报成「已改成新画质」——与 update_room / toggle_room 的
        # 「负信号 + 重新解析」口径相反。
        return _atomic_write_text(path, joined)


# 委托 src.utils.atomic_write_text（唯一实现）；返回值为 bool，上层只关心是否落盘。
# 依赖方向实测无环：src.utils → src.logger → src.config_bool 不反向依赖 web_config。
# [历史注] 本函数曾是第二份独立实现（自造 tmp + open("w") + os.replace），缺 utils 版的四项加固：
# 保留原文件 mode（0o600 收紧被静默还原成 0644、含口令/cookie 的配置同机任意用户可读）、fsync、
# 含唯一后缀的临时名（同进程两线程互截断）、写失败清理 .tmp——故统一委托，不得恢复本地实现。
# 回归锁：tests/test_regression_utils.py::TestWebConfigDelegatesToUtilsAtomicWrite
# :test_web_config_write_is_the_same_implementation（AST 判据：本模块可执行调用点不得再出现
# mkstemp / os.replace，文档性注释里的同名字样不算）。
def _atomic_write_text(path: Path, text: str) -> bool:
    return atomic_write_text(str(path), text, encoding=TEXT_ENCODING)


# 按主播名反查直播间地址（GUI 画质监控行以主播名为键，写回配置需要 URL）。
# 精确命中优先；未命中返回空串，由调用方决定降级行为（如禁用该行切换菜单）。
def find_room_url_by_anchor_name(url_config_file: str | Path, anchor_name: str) -> str:
    target = (anchor_name or "").strip()
    if not target:
        return ""
    rooms = parse_url_config(url_config_file)
    for room in rooms:
        if str(room["name"]).strip() == target:
            return str(room["url"])
    # 兜底：主播名含全角/半角差异或多个主播名段时，退化为行内子串匹配
    for room in rooms:
        if target in str(room["name"]):
            return str(room["url"])
    return ""


def read_web_config(config_file: str | Path) -> dict[str, str | int | bool]:
    # 读取 [Web] 节配置，缺失项用默认值填充。
    parser = _tolerant_config_parser()
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    result: dict[str, str | int | bool] = {}
    for key, default in WEB_DEFAULTS.items():
        if not parser.has_section("Web"):
            result[key] = default
            continue
        raw = parser.get("Web", key, fallback=str(default))
        if isinstance(default, bool):
            # 与 main.py / logger.py 共用同一解析口径（是/否、true/false、1/0、yes/no、on/off）；
            # 原实现只认 "true"/"1"/"yes"/"是"，与「是否启用https录制」等录制侧键的写法判断不一致
            result[key] = parse_config_bool(raw, default)
        elif isinstance(default, int):
            try:
                result[key] = int(raw)
            except ValueError, TypeError:
                result[key] = default
        else:
            result[key] = raw
    return result


SENSITIVE_SECTIONS = {"Cookie", "账号密码", "Authorization", "推送配置"}
# 2026-10-21：增列 推送配置 节：该节内除键名正则已覆盖的 tgapi令牌/发件人密码/推送token 外，还有键名不含
# 凭据关键词的独立凭据（邮箱登录账号、钉钉@手机号、tg 聊天 id、ntfy 邮箱），仅靠键名正则整节漏网、
# 明文回显面板并进备份副本。**节白名单 + 键名正则的双重口径不变**，此条只是给「整节皆凭据」的节
# 补第一道；代价是该节非敏感开关值同样按 '***' 回显，属已接受的取舍。
# 节名的 casefold 视图：configparser 的 **section 大小写敏感**（原样保留），而键名判定走的
# _SENSITIVE_KEY_PATTERN 带 re.IGNORECASE，两套强度不一致：写成 [cookie] / [COOKIE] 即整节跳出
# 白名单，节内键名不一定含凭据关键词、值形态兜底又只对 URL 形态生效，凭据便会明文回显并进备份副本
# （build_exe / config_io 复用同一入口，一并覆盖）。白名单集合本身不得改动（新增节名改
# SENSITIVE_SECTIONS，本视图由它派生），比对统一走 casefold。
_SENSITIVE_SECTIONS_FOLDED = frozenset(name.casefold() for name in SENSITIVE_SECTIONS)
SENSITIVE_MASK = "***"

# ─── Host / Origin 允许名单（防 DNS 重绑定穿透 SOP + CSRF） ───────────
# [历史注] 旧实现把 Origin 与**请求自带的** Host 头比较：攻击者把自身域名的 A 记录 TTL=0 指到
# 127.0.0.1，用户浏览器访问 http://attacker.tld:8000/ 时二者相同 → 同源校验与 CSRF 校验同时失效。
# 现改为与**服务端配置**推导出的允许名单比较，Host 头本身不再参与「是否可信」的判定。
_WILDCARD_BIND_HOSTS = frozenset(("0.0.0.0", "::", "*", ""))


def is_loopback_bind_host(host: str) -> bool:
    # 判断监听/访问地址是否仅本机可达（回环）。用于「非回环 + 无认证」不变量：
    # 0.0.0.0 / :: / 局域网 IP 一律算非回环。127.0.0.53 这类整段 127/8 也是回环，
    # 故按 ipaddress 语义判定而非字符串比较。
    name = _strip_host_port(host)
    if not name:
        return False
    if name in ("localhost", "ip6-localhost", "ip6-loopback"):
        return True
    addr = _parse_ip_literal(name)
    return bool(addr is not None and addr.is_loopback)


def get_allowed_hosts(cfg: Mapping[str, str | int | bool]) -> set[str]:
    # 服务端推导的允许 Host 名单：配置的监听地址 + 显式登记的额外域名。
    # 绑到 0.0.0.0/:: 时监听地址本身不是可用的 Host 值，故不入名单（改由 IP 字面量规则兜底）。
    allowed = {"localhost"}
    for raw in (str(cfg.get("web_host", "") or ""), str(cfg.get("web_allowed_hosts", "") or "")):
        for item in raw.replace("，", ",").split(","):
            name = _strip_host_port(item)
            if name and name not in _WILDCARD_BIND_HOSTS:
                allowed.add(name)
    return allowed


def is_host_allowed(value: str, cfg: Mapping[str, str | int | bool]) -> bool:
    # 判定 Host（或 Origin 的 netloc）是否可接受。三条放行路径：
    # ① 命中 get_allowed_hosts；② 是 IP 字面量（含端口者已被剥掉）——攻击者无法用
    #    DNS 把「一个 IP」重绑定到别处，故以 IP 访问面板（0.0.0.0 部署下的局域网 IP）不受影响；
    # ③ **无点号的单标签名**——DNS 重绑定需要一个注册域名，而注册域名必然至少两级；
    #    单标签名只能由本机 hosts/内网解析得到，测试桩的 "testserver" 亦属此类。
    # 多级域名一律要求显式登记，未登记即拒绝（400），并在 web.py 侧同源生效。
    name = _strip_host_port(value)
    if not name:
        return False
    if name in get_allowed_hosts(cfg):
        return True
    if _parse_ip_literal(name) is not None:
        return True
    if "." not in name:
        return True
    # 允许名单里的「*.example.com」式通配登记（以 . 或 *. 开头表示后缀匹配）
    for allowed in get_allowed_hosts(cfg):
        if allowed.startswith("*.") and (name == allowed[2:] or name.endswith(allowed[1:])):
            return True
    return False


# ─── Origin 同源判定：与 Host 头**刻意不同**的一套口径 ──────────────
# is_host_allowed 为 Host 头设计的三条宽松规则（放行任何 IP 字面量、放行任何无点单标签名、
# 且 _strip_host_port 把端口丢掉）在 Host 语境下都成立。但 Origin 表达的是「发起这次写请求的
# 那个页面」：拿去复用就会让局域网里任意设备的网页（http://192.168.1.47/）、本机任意 dev server
# （http://localhost:3000/）都因「是 IP / 是无点名」且端口被丢掉而判为同源。认证关闭（出厂默认）
# 时这条判定是写接口唯一的防线，故 Origin **host 与端口都必须命中服务端推导的期望集合**，不复用
# 上面两条宽松规则；Host 那条保持原状（硬合并会让 Host 侧的重绑定防线退化）。
_ORIGIN_TEST_SENTINEL_HOSTS = frozenset(("testserver",))
_ORIGIN_SCHEME_PORTS: dict[str, int] = {"http": 80, "https": 443}


def _running_under_pytest() -> bool:
    # testserver 豁免的环境门。哨兵豁免本是 Starlette TestClient 的 base_url 桩，直接编进生产判定
    # 时生产进程若收到 Origin: http://testserver（本机 hosts 可把它指到任意处）即免端口放行，
    # 等于测试后门进生产。「pytest 在 sys.modules」由 tests/conftest.py 必然 import pytest 触发，
    # 是测试进程的低成本指纹，非测试环境恒 False
    return "pytest" in sys.modules


def _as_port(value: object) -> int:
    # 端口取值：web_port 经 read_web_config 已是 int，但调用方也可能塞进未解析的原始串
    # （用例里手写的 cfg dict）。解析不出来按 0（= 未知）返回，交由调用侧拒绝而不是猜一个。
    try:
        return int(str(value).strip())
    except ValueError:
        return 0


def _origin_authority(origin: str) -> tuple[str, int, bool] | None:
    # 把 Origin 拆成 (主机名, 生效端口, 端口是否显式给出)；任何不合法形态返回 None（判否）。
    # 刻意不用 urlparse：它对 "http://u@h"、"http://a:1:2" 这类畸形值会给出「看起来能用」的
    # hostname，而浏览器发出的 Origin 恒为 scheme://host[:port]（无 path、无 userinfo）。
    # 按「不认识的形态一律拒绝」处理，不给解析差异留可利用的空间。
    scheme, sep, rest = origin.strip().partition("://")
    if not sep:
        return None
    default_port = _ORIGIN_SCHEME_PORTS.get(scheme.lower())
    if default_port is None:
        return None
    # Origin 的序列化恒为 scheme://host[:port]，**从不含 path/query**（斜杠之后什么都没有）。
    # [历史注] 旧写法 `rest.split("/", 1)[0]` 会把 "http://127.0.0.1:8000/任意尾巴" 也当成合法
    # 主机而接受——按不认识的形态一律拒绝处理。
    authority, slash, tail = rest.partition("/")
    if slash or tail or not authority:
        return None
    if authority.startswith("["):
        # IPv6 形态：[::1]:8000 / [::1]（zone id 无意义，剥掉）
        end = authority.find("]")
        if end <= 0:
            return None
        host = authority[1:end].split("%", 1)[0]
        tail = authority[end + 1 :]
        if tail and not tail.startswith(":"):
            return None
        port_text = tail[1:] if tail else ""
    else:
        if authority.count(":") > 1:
            return None  # 裸 IPv6（未加方括号）不是浏览器会发出的 Origin 形态
        host, _, port_text = authority.partition(":")
    if not host or any(ch in authority for ch in "@?#\\"):
        # userinfo / query / fragment / 反斜杠（WHATWG 下等价于 /）都不是 Origin 的组成部分；
        # 显式列出而不是依赖下游解析的宽容度，避免「两种解析器各看到一个不同主机」的缝隙。
        return None
    host = host.strip().lower().rstrip(".")
    if not host:
        return None
    if not port_text:
        return host, default_port, False
    if not port_text.isdigit():
        return None
    port = int(port_text)
    if not 1 <= port <= 65535:
        return None
    return host, port, True


def get_origin_allowed_hosts(cfg: Mapping[str, str | int | bool]) -> dict[str, int | None]:
    # web_allowed_hosts 的 Origin 侧解释：host → 登记的端口（None = 未写端口，按实际绑定端口判）。
    # 与 get_allowed_hosts 的两点差别正是本条防线的要点：
    # ① **保留端口**（Host 那条把它丢掉，Origin 这条恰恰要靠它区分「本站页面」与
    #    「本机/局域网里另一台服务器上的页面」）；
    # ② 不做 *. 后缀通配（同源是按「那一台主机」成立的，把 *.example.com 判成同源
    #    等于接受任意/被签发的子域，与拒绝重绑定的初衷相反）。
    result: dict[str, int | None] = {}
    for item in _split_multi_value(str(cfg.get("web_allowed_hosts", "") or "")):
        parsed = _origin_authority(item if "://" in item else f"http://{item}")
        if parsed is None:
            continue
        host, port, explicit = parsed
        result[host] = port if explicit else None
    return result


def is_origin_allowed(
    origin: str,
    cfg: Mapping[str, str | int | bool],
    *,
    bind_host: str = "",
    bind_port: int = 0,
) -> bool:
    # Origin 是否可作为「同源」放行。bind_host / bind_port 是**进程实际绑定**的地址与端口
    # （由 web.py 接线，见 src/web_api.create_app）；未接线时调用侧回落到配置值，
    # 回落口径与理由见 web_api._guard_bind_host 的注释。
    parsed = _origin_authority(origin)
    if parsed is None:
        return False
    host, port, explicit_port = parsed
    # 测试桩豁免，边界写在这里：Starlette TestClient 的默认 base_url 是 http://testserver
    # （无端口），那是 httpx 写死的一个哨兵字符串，不是任何浏览器能交付的本站地址形态。
    # 豁免严格限定为「名字恰好等于该哨兵 **且** Origin 里没有显式端口」：不放开任意无点单标签
    # 名、不放开任意 IP，且 Origin 一旦带端口（含 testserver:8000）立即回到 host+端口双判。
    # 另经 _running_under_pytest() 环境门把关——豁免若在纯函数判定内无条件生效，属「测试后门进生产」
    if not explicit_port and host in _ORIGIN_TEST_SENTINEL_HOSTS and _running_under_pytest():
        return True
    expected_port = bind_port or _as_port(cfg.get("web_port"))
    registered = get_origin_allowed_hosts(cfg)
    if host in registered:
        want = registered[host]
        if want is not None:
            # 登记项自带端口：按登记端口判（反代 https://panel.example/ 这类入口端口
            # 与应用绑定端口不同的合法部署，登记即放行，不必把 web_host 改成公网名）
            return want == port
        return expected_port > 0 and port == expected_port
    if expected_port <= 0 or port != expected_port:
        return False
    if bind_host:
        bound = _strip_host_port(bind_host)
        if bound and bound not in _WILDCARD_BIND_HOSTS and bound == host:
            return True
    # 回环族恒可（端口已在上面校过）：面板的出厂访问路径就是 http://localhost:8000 /
    # http://127.0.0.1:8000，且回环端口只能被本机进程占用，能给出该 Origin 的页面必出自本机。
    # 注意这条**不放端口**——http://localhost:3000/（本机 dev server）正是本条要拦的形态。
    return is_loopback_bind_host(host)


# 敏感判定是「节白名单 SENSITIVE_SECTIONS + 键名正则」两道并联（见 is_sensitive_item），缺一不可：
# 仅靠节名白名单会漏掉「推送配置」节的 tgapi令牌 / 发件人密码(授权码) / pushplus推送token，以及各
# 平台节内的 popkontv_token 等独立凭据——它们会被 read_config_safe 原样明文返回给面板
# （前端再按节名用 text 输入框渲染）。
# 另补端点型键名：此前只匹配「键名含凭据关键词」，而「凭据嵌在值里」的键（钉钉/微信/bark
# 推送接口链接、ntfy 推送地址、代理地址）完全绕过脱敏，会被明文返回并以普通 text 输入框渲染。
_SENSITIVE_KEY_PATTERN = re.compile(
    r"令牌|密码|授权码|token|secret|passwd|password|api[_-]?key|推送接口链接|推送地址|代理地址",
    re.IGNORECASE,
)

# 值形态检测——键名不含凭据关键词、但值本身就是凭据的情形。
# 典型：企业微信/钉钉 webhook（?key= / access_token=）、bark 设备 key、
# 带账密的代理地址（http://user:pass@host:port）。
# 黑名单式键名匹配天然滞后于平台命名，值形态检测是第三道兜底。
# [历史注] 原配套的 _URL_VALUE_RE（scheme 门）已因摘除 scheme 限制而删除，
# 全仓 grep 实测零 importer（tests/ 亦不引用），判据见 _looks_like_secret_value 内注释
_SECRET_VALUE_QUERY_RE = re.compile(r"(access[_-]?token|token|key|secret|pwd|passwd|password|auth)=", re.IGNORECASE)


def _looks_like_secret_value(value: str) -> bool:
    # 判断配置「值」本身是否携带凭据（与键名无关），供 read_config_safe 兜底脱敏。
    # 判定收敛为两条不依赖 scheme 的形态：authority 段含 @（userinfo）、或值里带凭据型查询参数；
    # 纯文本值两样都不命中，不会把「普通配置」扩成误伤面
    # [历史注] 旧「必须以 scheme 开头」门会让代理地址的裸写形态 user:pass@host:port 整条逃逸
    # 值形态兜底（键名恰又不含凭据关键词时明文回显），故摘除该门
    v = value.strip()
    if not v:
        return False
    authority = v.split("://", 1)[-1].split("/", 1)[0]
    if "@" in authority:
        return True  # userinfo（http://user:pass@host 或裸 user:pass@host）
    return bool(_SECRET_VALUE_QUERY_RE.search(v))


# 反向例外表：含 expiry/timeout/过期/有效期 的键是数值型运维参数（如 web_token_expiry 的秒数），
# 脱敏会挡住面板编辑且无保密意义，故显式排除。判敏感 = 键名正则命中 **且** 不落在本表内。
_KEY_NOT_SECRET_PATTERN = re.compile(r"expiry|timeout|有效期|过期", re.IGNORECASE)


def is_sensitive_key(key: str) -> bool:
    # 判断配置键名是否属敏感字段（不依赖所属节，供脱敏与前端渲染类型复用）。
    # 反向例外表先判：命中 _KEY_NOT_SECRET_PATTERN（expiry/timeout/过期/有效期）即放行。
    if _KEY_NOT_SECRET_PATTERN.search(key):
        return False
    return bool(_SENSITIVE_KEY_PATTERN.search(key))


def is_sensitive_item(section: str, key: str) -> bool:
    # 敏感判定的唯一入口：节白名单命中 **或** 键名模式命中（后者覆盖「推送配置」等非白名单节内的
    # 独立凭据）。读写两侧都必须走它——web_api 的写侧守卫即直接复用本函数与 _looks_like_secret_value。
    # 2026-10-18：节名比对统一 casefold，与键名侧的 re.IGNORECASE 收到同一强度（失效形态与判据见
    # _SENSITIVE_SECTIONS_FOLDED 上方注释）。白名单集合本身未动，只收紧比对口径；
    # 中文节名（账号密码）casefold 幂等，实际差异只在 ASCII 族（Cookie/Authorization）。
    return section.casefold() in _SENSITIVE_SECTIONS_FOLDED or is_sensitive_key(key)


def read_config_safe(config_file: str | Path) -> dict[str, dict[str, str]]:
    # 读取 config.ini 全部节键值，敏感节非空值脱敏为 '***'，用于 API 返回前端展示。
    # Web 节单独对 web_password 脱敏（其他 Web 键需可编辑，故不整节脱敏）。
    #
    # 写入口是谁（判「写入口」一律 grep 调用点，别信注释）：PUT /api/config 走的是**本模块**的
    # update_config_line（行级替换，保留注释/节序/行内注释）+ _atomic_write_text；
    # utils.update_config 只在录制引擎侧的热加载写回里出现。
    # [历史注] 旧陈述「写入仍用 utils.update_config」已证伪，曾据此漏看本模块自己的写入面。
    parser = _tolerant_config_parser()
    _ = parser.read(config_file, encoding=TEXT_ENCODING)
    result: dict[str, dict[str, str]] = {}
    for section in parser.sections():
        items: dict[str, str] = {}
        for key, value in parser.items(section):
            # 键名命中或值本身形如凭据，统一脱敏
            if value.strip() and (is_sensitive_item(section, key) or _looks_like_secret_value(value)):
                items[key] = SENSITIVE_MASK
            else:
                items[key] = value
        result[section] = items
    return result


# 按 key 缓存编译后的行匹配模式：模式串依赖 key，无法整体预编译，但同 key 反复更新时应复用。
# maxsize 取 128，远超配置文件键数量，命中率接近 100%。
@functools.lru_cache(maxsize=128)
def _key_line_pattern(key: str) -> re.Pattern[str]:
    # 匹配 key 行：允许 = 或 ：或 : 分隔，key 前后空白（大小写不敏感）
    return re.compile(r"^(\s*" + re.escape(key) + r"\s*[=:：]\s*)(.*)$", re.IGNORECASE)


# config.ini 写入串行锁：Web 侧「改配置/改语言/密码升级写」、
# GUI 的 language 写回与引擎的 SSL 平台列表写回均为无锁 read-modify-write，并发交错
# 会互相覆盖丢写；RLock 可重入保证组合操作（update_or_append_config_line）持锁调用单步函数不自锁。
_config_write_lock = threading.RLock()


def update_config_line(config_file: str | Path, section: str, key: str, value: str) -> bool:
    # 注释保留的行级配置更新。逐行扫描：进入目标 section 后，匹配 `^\\s*key\\s*[=：:]\\s*` 的行
    # 并替换其值；未找到 section 或 key 时返回 False（不写入）。注释、空行、节顺序与原分隔符
    # 风格全部保留。key 匹配大小写不敏感：configparser 读取侧经 optionxform 统一小写，代码内
    # 常量（如「禁用SSL证书验证的平台」）与配置文件实际行（小写 ssl）不致时应仍可定位。
    path = Path(config_file)
    if not path.exists():
        return False
    with _config_write_lock:
        # newline=""：读侧不做换行翻译，\r\n 原样保留，配合原子写字节级 round-trip
        with path.open("r", encoding=TEXT_ENCODING, newline="") as f:
            lines = f.readlines()
        cur_section: str | None = None
        in_target = False
        replaced = False
        key_pattern = _key_line_pattern(key)
        # 手工编辑产生重复键时拒绝写入——旧实现只替换目标节内**首个**匹配行，写侧返回 True
        # 而 configparser 生效值来自另一行（「面板提示已保存、行为未变」）。
        # 判据复用既有失败出口（return False，由 web_api 转 404、write_quality_options 报写失败），
        # 不新增第三种返回形态；重复行留给读侧容错层（src/config_read）点名，写侧不再静默覆盖一半
        _match_count = 0
        _scan_section: str | None = None
        for line in lines:
            _scan_stripped = line.strip()
            if _scan_stripped.startswith("[") and _scan_stripped.endswith("]"):
                _scan_section = _scan_stripped[1:-1].strip()
                continue
            if _scan_section == section and key_pattern.match(line.rstrip("\n").rstrip("\r")):
                _match_count += 1
        if _match_count > 1:
            return False
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                cur_section = stripped[1:-1].strip()
                in_target = cur_section == section
                new_lines.append(line)
                continue
            if in_target and not replaced:
                m = key_pattern.match(line.rstrip("\n").rstrip("\r"))
                if m:
                    prefix = m.group(1)  # "key = " 部分
                    old_tail = m.group(2)  # 原值（可能含行内注释）
                    # 行内注释只认「引号定界」一种可信形态：引号包裹的值其注释必在**闭合引号之后**。
                    # [历史注] 旧实现一律按首个 " #" / " ;" 切分，值本身含该串时写回后变成
                    # 「新值 + 半个原值」（颜色值、含井号的密码/token、URL 锚点都中招）。
                    # 无引号值的 " #" / " ;" 启发式回落分支已整体移除：读侧 configparser 从未开启
                    # inline_comment_prefixes，旧值里的 " #" 本就是**值的一部分**，把它拼回新值等于
                    # 二次写入静默污染（读回值 ≠ 新值，含井号 token 莫名失效且无从排查）。
                    inline_comment = ""
                    _stripped_tail = old_tail.lstrip()
                    if _stripped_tail[:1] in ('"', "'"):
                        _quote = _stripped_tail[0]
                        _q_start = old_tail.find(_quote) + 1
                        _q_end = old_tail.find(_quote, _q_start)
                        if _q_end > 0:
                            inline_comment = old_tail[_q_end + 1 :]
                    # 保留原行尾换行符：先判 \r\n 再判 \n（CRLF 行同样以 \n 结尾，
                    # 顺序反了会把 CRLF 行降级成 LF，往 CRLF 文件里混入异风格行尾）
                    eol = "\r\n" if line.endswith("\r\n") else ("\n" if line.endswith("\n") else "")
                    new_lines.append(f"{prefix}{value}{inline_comment}{eol}")
                    replaced = True
                    continue
            new_lines.append(line)
        if not replaced:
            return False
        # 原子写：write_text 是 truncate+write 非原子，与引擎热加载的持锁读竞态时可读到
        # 空/半写文件；改同目录临时文件 + os.replace（读方只见旧/新完整内容）。
        # 必须**返回**原子写的结果：它在 mkstemp/os.replace 抛 OSError 时明确返回 False，丢弃它则
        # 磁盘满时 PUT /api/config 仍回 ok、set_language 的回滚也不触发——受影响面含 web_auth_enable /
        # web_password 这类安全键，假成功的代价是用户以为密码已改。
        return _atomic_write_text(path, "".join(new_lines))


def append_config_line(config_file: str | Path, section: str, key: str, value: str) -> bool:
    # 缺键补建的行级追加：update_config_line 只做替换、键或节缺失时返回 False
    # （如历史 config.ini 没有 `language` 键，Web 先于引擎首轮读配置时切换语言），
    # 本函数把 `key = value` 插入目标 section 内；节不存在时于文件尾新建。
    # 与 update_config_line 相同的行级文本风格：注释、空行、节顺序与其余内容全部保留。
    path = Path(config_file)
    if not path.exists():
        return False
    with _config_write_lock:
        # newline="" 保留 \r\n 原样，配合原子写字节级 round-trip（同 update_config_line）
        with path.open("r", encoding=TEXT_ENCODING, newline="") as f:
            lines = f.readlines()
        insert_at: int | None = None  # 目标节内的插入点（下一节头之前）；None＝文件尾
        in_section = False
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not (stripped.startswith("[") and stripped.endswith("]")):
                continue
            name = stripped[1:-1].strip()
            if in_section:
                insert_at = idx  # 走到下一节头部即目标节结束
                break
            if name == section:
                in_section = True
        # 末行无尾换行时先补一个：无论插入文件中间还是尾部，都不得与原内容粘连成一行
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        entry = f"{key} = {value}\n"
        if in_section:
            lines.insert(insert_at if insert_at is not None else len(lines), entry)
        else:
            lines.append(f"[{section}]\n{entry}")
        # 原子写（同 update_config_line）：truncate+write 窗口内读方会看到半写文件。
        # 必须回报原子写的布尔结果——补建分支（config.ini 缺 language 键、画质选项首次落盘）
        # 旧实现无条件 return True，磁盘写失败仍报成功，set_language 的回滚与
        # update_or_append_config_line 的失败判定全部失明
        return _atomic_write_text(path, "".join(lines))


# 行级「替换优先、缺键补建」的组合写入：两步全程持同一把
# 可重入锁，杜绝「替换失败→追加」间隙被并发写交错（如 language 键被 Web 与 GUI
# 同时补建导致重复行）。返回是否发生任一写入。
def _config_has_key(config_file: str | Path, section: str, key: str) -> bool:
    # 只判「目标节内是否存在该键行」，不做任何写入；供 update_or_append_config_line 区分
    # update_config_line 的 False 到底是「键不存在」还是「拒绝/失败」（M-26）。
    path = Path(config_file)
    if not path.exists():
        return False
    key_pattern = _key_line_pattern(key)
    cur_section: str | None = None
    with path.open("r", encoding=TEXT_ENCODING, newline="") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                cur_section = stripped[1:-1].strip()
                continue
            if cur_section == section and key_pattern.match(line.rstrip("\n").rstrip("\r")):
                return True
    return False


def update_or_append_config_line(config_file: str | Path, section: str, key: str, value: str) -> bool:
    with _config_write_lock:
        if update_config_line(config_file, section, key, value):
            return True
        # update_config_line 的 False 同时表示「键不存在」「重复键拒绝」「原子写失败」三种情况
        # （CODE_REVIEW_2026-10-29 M-26）：只有「键确实不存在」才允许追加，否则对已含重复键的
        # 文件再落一行、或对写入失败的文件补一条重复行，会把损坏态放大并回报成功。
        if _config_has_key(config_file, section, key):
            return False
        return append_config_line(config_file, section, key, value)


# === Web 登录密码哈希（PBKDF2-HMAC-SHA256）===
# 存储格式：pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>
# 落地配置只保存哈希，不保存明文；历史明文配置在首次登录时自动升级。
_PBKDF2_ALGO = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 200_000
# 迭代次数取自存储串（用户可直接编辑的 config.ini），若按其原值喂给 pbkdf2_hmac，把 200k 改成
# 2e7 就能让**每次登录**烧掉十几秒 CPU，而登录端点在事件循环线程里跑 → 面板级 CPU DoS。
# 故此处给出硬上下界：上界 1e6（约 0.7s）容纳未来一次有意的强度升级，下界取本模块默认值，
# 低于默认值的历史哈希一律判失败（宁可让人重设密码，也不给降级攻击留门）。
_PBKDF2_MAX_ITERATIONS = 1_000_000


def clamp_pbkdf2_iterations(raw: object) -> int:
    # 把存储串里的迭代次数收敛到 [_PBKDF2_ITERATIONS, _PBKDF2_MAX_ITERATIONS]。
    # 无法解析（非数字/为空）→ 返回默认值，由调用方的 compare_digest 自然判失败，不抛异常。
    try:
        value = int(cast("str", raw))
    except TypeError, ValueError:
        # 注：需要绑定异常对象时不能省括号（`except A, B as e:` 非法）
        return _PBKDF2_ITERATIONS
    return max(_PBKDF2_ITERATIONS, min(value, _PBKDF2_MAX_ITERATIONS))


def hash_web_password(plaintext: str) -> str:
    # 将明文密码派生为带随机盐的哈希串，用于安全存储（避免明文落盘）。
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"{_PBKDF2_ALGO}${_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def is_hashed_web_password(value: str) -> bool:
    # 判断存储值是否已是哈希格式（而非历史明文）。
    return bool(value) and value.startswith(f"{_PBKDF2_ALGO}$")


def verify_web_password(plaintext: str, stored: str) -> bool:
    # 校验密码：stored 为哈希串时按 PBKDF2 校验；历史明文也允许直接比较以兼容升级前配置。
    if not stored:
        return False
    if is_hashed_web_password(stored):
        try:
            _, iters_s, salt_b64, hash_b64 = stored.split("$")
            salt = base64.b64decode(salt_b64)
            expected = base64.b64decode(hash_b64)
            dk = hashlib.pbkdf2_hmac("sha256", plaintext.encode("utf-8"), salt, clamp_pbkdf2_iterations(iters_s))
        except ValueError:
            # 哈希串损坏/迭代数非法（base64.b64decode 的 binascii.Error 亦为 ValueError 子类）：
            # 视为校验失败而非崩溃
            return False
        return hmac.compare_digest(dk, expected)
    # 兼容历史明文存储。必须先编码再比较：compare_digest 对含非 ASCII 字符的 str
    # 直接抛 TypeError（历史明文密码含中文时 /api/login 会 500），bytes 比较无此限制
    return hmac.compare_digest(plaintext.encode("utf-8"), stored.encode("utf-8"))
