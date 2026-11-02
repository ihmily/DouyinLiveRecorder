#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
# DouyinLiveRecorder 单文件整合版 (standalone)
# =============================================================================
# 本文件从工作区的源模块(约 2.1 万行)中抽取核心录制主链路，合并为一个开箱即用的单文件脚本。
#
# 设计取舍
# * **零第三方依赖**：只使用 Python 标准库(urllib/math/subprocess/threading 等)，
#   无需 pip install 即可运行(录制本身仍需 ffmpeg 可执行文件)。
# * **本文件是被整合模块的独立副本，不是薄封装**：src/scheduler.py 的并发实现、src/spider.py
#   的部分平台解析、src/stream_select.py 的探针/退避、src/ffmpeg_install.py 的包内 ffmpeg 判据，
#   以及 ffmpeg 命令构造(本文件有**两处**定义点，main.py 只有一处)都在此各有一份拷贝。副本的
#   通病是「单边修改 → 语义漂移」，故改判据必须两处同改、两边注释互相点名；并发两份实现的
#   **等价性并不完整**，逐条差异见 PlatformBreaker 类注释。漂移的机检面：
#   tests/test_regression_standalone.py、tests/test_ffmpeg_reconnect_args.py、
#   tests/test_ffmpeg_path_preference.py。
#   http_request 响应体上限（_MAX_RESPONSE_BYTES=8MiB）与主线 sync_http/async_http 同值收敛
#   （M-14）；网络层异常文本内嵌的 url 统一 strip_query（M-13）。
# * **语法基线 Python >= 3.14**：本仓统一使用 PEP 758 无括号多异常写法(except A, B:)，
#   该语法 3.14 起才合法——请勿用 3.13 及以下版本运行本文件。
# * **保留原工程的核心正确性约定**(原工程踩坑后的结论，单文件版一律继承)：
#   1. 校验探针与 ffmpeg 录制必须共用同一 UA / Referer / Cookie(record_headers 单点构造)，
#      否则出现「探针 200、ffmpeg 403」的假绿。
#   2. m3u8 的 HEAD 常被 CDN 返回 4xx(405/404) 而 GET 可正常拉流，
#      故 HEAD 非 2xx 时一律降级做 Range GET(bytes=0-0) 探测，200/206 视为可达。
#   3. flv/record_url 在 HEAD 通过后须再做一次 GET 复核，杜绝「HEAD=200、GET=403」的假绿；
#      复核先原样重试一次再定罪(偶发限流 ≠ 稳定拒绝)。
#   4. 失败/成功必须回传调度器(按 host 熔断)：解析成功/失败、ffmpeg 退出码分别采样，
#      禁止轮末无条件记成功。
#   5. Windows 下 socket.timeout 的 str() 为空，异常日志必须带 type(e).__name__ 与 url。
#   6. 文件名必须清洗 Windows 非法字符，并把 '&' 换为下划线(cmd 命令分隔符)。
#   7. 虎牙 CDN 反向校验 Referer(携带反而 403)且按连接预算限流——虎牙候选走 FLV 优先、
#      401/403 记探针退避(白名单仅虎牙)、录制成功撤销退避。
#   8. 斗鱼游客态 FLV 长连接约 70 秒被 CDN 掐断——必须附带同 token 的 .flv→.m3u8 HLS 候选。
#
# 支持的平台
# -----------------------------------------------------------------------------
# * 抖音 live.douyin.com       —— webcast room/web/enter；web_rid 同时接受数字房间号与抖音号，
#                                不做重定向解析。
# * 虎牙 www.huya.com          —— HTML stream 解析 + 微信小程序接口兜底，房间别名经 ProfileRoom
#                                字段还原数字房间号。
# * B站 live.bilibili.com      —— room_init 判开播 → playUrl 取流 → Master/info 取主播名 →
#                                getH5InfoByRoom 取标题。
# * 斗鱼 www.douyu.com         —— betard 房间信息 + getEncryption 签名 + getH5PlayV1 取流；签名
#                                是纯 MD5 链式算法（RFC 1321 纯 Python 实现，**不需要 Node.js**）。
#
# 使用
# -----------------------------------------------------------------------------
# 本文件位于 scripts/ 下，以下命令均在仓库根目录执行：
#   python scripts/douyin_live_recorder_standalone.py --selftest
#   python scripts/douyin_live_recorder_standalone.py --url "https://live.douyin.com/123456" --dry-run
#   python scripts/douyin_live_recorder_standalone.py --url "https://www.huya.com/660002" --once
#   python scripts/douyin_live_recorder_standalone.py --config config/config.ini --url-config config/URL_config.ini
#
# 依赖与前置条件见文件末尾 RUN_STEPS 常量(可用 --help-steps 打印)。

from __future__ import annotations

import argparse
import configparser
import ipaddress
import json
import math
import os
import platform
import random
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

# ===== 0. 基础常量与运行环境 =====

VERSION = "1.1.0-standalone"

# Windows 控制台默认 GBK，直接打印中文/emoji 会 UnicodeEncodeError；统一重配为 utf-8。
# 用 hasattr 守卫：被重定向到管道或 pythonw 下 stdout 可能为 None。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except ValueError, OSError:
            pass

# 桌面 Chrome UA：国内 CDN(虎牙/B站)会拒绝移动端 UA(403)，录制拉流必须用桌面 UA。
# 与原工程 room.DESKTOP_UA / stream_select.DESKTOP_UA 一字不差。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
# 移动端 UA：与 ffmpeg 录制命令默认 UA 保持一字不差(校验与录制两端必须一致)。
MOBILE_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
# 解析直播间页面时的兜底 UA(与原工程 get_huya/get_douyu_info 使用的 Firefox 指纹一致)
HTML_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"

# Windows 文件名非法字符(原工程 rstr 的等价物)
ILLEGAL_CHARS_PATTERN = r'[\\/:*?"<>|\r\n\t]'
FALLBACK_NAME = "空白昵称"

# 密码学安全随机源：仅用于探针节流/重试的时间抖动(非安全用途)，
# 按安全审计建议统一使用 SystemRandom，避免 weaker-random 告警。
_SYS_RANDOM = random.SystemRandom()

_print_lock = threading.Lock()

# 可选文件日志路径：Recorder 初始化时按配置赋值；空串表示关闭
_LOG_FILE_PATH = ""

# 日志轮转阈值。standalone.log 与 ffmpeg.log 均为无上限 append
# （该只解决了凭据明文问题，磁盘占满这一半未闭合），长跑数周可写满磁盘。
_LOG_ROTATE_BYTES = 10 * 1024 * 1024


def _rotate_log_if_needed(path: str) -> None:
    # 单代轮转：超阈值时 rename 为 .1（旧 .1 直接覆盖）。只保两代（当前 + .1），
    # 与主程序 loguru rotation 的最小可用形态对齐；调用点持 _print_lock 或在
    # run_ffmpeg 单线程打开前执行，无并发窗口。Windows 下文件被占用时 os.replace
    # 抛 PermissionError——静默跳过本轮轮转，日志继续 append（不能影响录制主链路）。
    try:
        if os.path.isfile(path) and os.path.getsize(path) >= _LOG_ROTATE_BYTES:
            rotated = path + ".1"
            if os.path.exists(rotated):
                os.remove(rotated)
            os.replace(path, rotated)
    except OSError:
        pass


def log(level: str, msg: str) -> None:
    # 线程安全的日志输出：stdout 可用时打印，启用文件日志时同步落盘。
    # pythonw / 无控制台环境下 sys.stdout 为 None，必须判空(原工程 logger 同约定)。
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} | {level:<7} | {msg}"
    with _print_lock:
        if sys.stdout is not None:
            print(line, flush=True)
        if _LOG_FILE_PATH:
            _rotate_log_if_needed(_LOG_FILE_PATH)
            try:
                with open(_LOG_FILE_PATH, "a", encoding="utf-8", errors="replace") as f:
                    f.write(line + "\n")
            except OSError:
                # 日志落盘失败不得影响录制主链路，也无需刷屏(每次异常都会静默重试)
                pass


def info(msg: str) -> None:
    log("INFO", msg)


def warn(msg: str) -> None:
    log("WARNING", msg)


def error(msg: str) -> None:
    log("ERROR", msg)


def debug(msg: str) -> None:
    log("DEBUG", msg)


# ===== 1. HTTP 客户端(纯标准库) =====


@dataclass
class HttpResponse:
    # 极简 HTTP 响应：状态码 / 响应头(小写键) / 文本。
    status: int
    headers: dict[str, str]
    text: str


@dataclass
class ProbeResult:
    # 探针结果：状态码 + 响应头(小写键)。status 与 content-type 必须来自**同一次**请求，
    # 禁止为取 content-type 再发一次 HEAD——虎牙等 CDN 按连接预算限流，双倍探针会烧光预算。
    status: int
    headers: dict[str, str]

    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").lower()


# 显式协议白名单 handler 集：与主程序 src/sync_http.py 的定稿同构。
# build_opener 即使显式传入 ProxyHandler，默认 Handler 集合（含 FileHandler/FTPHandler/
# DataHandler）**仍然生效**——file:// 会被本地读出 200，与「平台 API 候选属不可信输入面」
# 叠加成「候选 → 探针 → ffmpeg 读本地文件」的完整利用链。现只显式注册 http/https 相关
# handler，白名单外协议经 UnknownHandler 统一抛 URLError('unknown url type: …')，响应体
# 一步都不读。UnknownHandler 必须保留：它是白名单外协议的统一拒绝口。
# 残余缺口（登记，与主线同边界）：DNS 重绑定窗口不在本层闭合。
# [历史注] SR-02 前本集用的是裸 HTTPRedirectHandler——探针自动跟随重定向且每跳
# 不复检，公网候选 302 到内网/云元数据时逐跳判定缺失；现改挂下方 _HopGuardRedirectHandler。
class _HopGuardRedirectHandler(urllib.request.HTTPRedirectHandler):
    # SR-02：重定向逐跳复检（主线防线回灌）。主线同层防线是探针客户端挂
    # src/async_http.build_sync_hop_guard（response 事件钩子，每跳含落地跳均判内网/协议，
    # 命中即断），本副本按设计不 import src，故在 urllib 的重定向单点复刻同判据：
    # HTTPRedirectHandler 的 301/302/303/307/308 全部经 redirect_request() 发起下一跳，
    # 在此复用 _untrusted_stream_target_reason(newurl)（定义在下方，与初始候选同一份判定，
    # 不另写 urlparse/内网名单）复检目标，不通过即抛 URLError 断链——请求不发出，fp 由
    # HTTPErrorProcessor/DefaultErrorHandler 既有链路关闭。
    # 与主线触发时机的差异（判据注释互点名）：主线钩子在「该跳响应头已收到后」触发，闭合的是
    # 「不再跟随 + 响应不外流」，不是「不建连」；本 handler 在发起下一跳**之前**拦截，跳转目标
    # 的连接根本不发生。两者同样不闭合 DNS 重绑定窗口（残余缺口与主线一致）。
    def redirect_request(self, req: urllib.request.Request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        reason = _untrusted_stream_target_reason(newurl)
        if reason is not None:
            raise urllib.error.URLError(f"重定向目标不可信({reason}): {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_HTTP_ONLY_HANDLERS: tuple[type[urllib.request.BaseHandler], ...] = (
    urllib.request.UnknownHandler,
    urllib.request.HTTPHandler,
    urllib.request.HTTPDefaultErrorHandler,
    _HopGuardRedirectHandler,
    urllib.request.HTTPErrorProcessor,
)


def _build_opener(proxy: str | None) -> urllib.request.OpenerDirector:
    # proxy 显式传入时代理该地址；**未传时用空 ProxyHandler 屏蔽系统/环境代理**——
    # urllib 的默认 opener 会读取 http_proxy/ALL_PROXY 等环境变量，导致「配置说直连、
    # 实际走了系统代理」的隐性行为。代理策略必须只由配置文件决定(与原工程 httpx
    # proxy=None 直连语义对齐)。
    # [历史注] 原经 build_opener 构造——默认 Handler 集合不受显式
    # ProxyHandler 影响，file/ftp/data 三类协议全部可读；改按上方白名单手工组装
    # （HTTPSHandler 仍为必挂实参，http/https 是本项目仅有的两类出站协议）。
    opener = urllib.request.OpenerDirector()
    if proxy:
        opener.add_handler(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener.add_handler(urllib.request.ProxyHandler({}))
    for klass in _HTTP_ONLY_HANDLERS:
        opener.add_handler(klass())
    opener.add_handler(urllib.request.HTTPSHandler())
    return opener


# M-14：响应体读取上限，与主线 src/sync_http.py / src/async_http.py 的
# _MAX_RESPONSE_BYTES 同值。消费面（_probe_hls_segment_lite 等）拉取的是 CDN 控制的播放列表
# 正文，属不可信输入面（见下方「不可信流地址候选」节）；无上限的 resp.read() 可被异常/被劫持
# 源把长跑进程内存打爆。单次 read(limit+1)：http.client 的 read(amt) 会阻塞读满 amt 或到 EOF，
# 长度超限即抛——调用侧既有「请求失败」分支按不可达处理，与主线「超限即拒绝该响应」同形。
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def http_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 15.0,
    proxy: str | None = None,
) -> HttpResponse:
    # 发起一次 HTTP 请求，返回 HttpResponse；网络层失败时抛出 RuntimeError(带 URL 与异常类型)。
    # 注意(原工程踩坑)：Windows 下 socket.timeout 的 str() 为空字符串，
    # 异常信息必须携带 type(e).__name__ 与 url，否则日志只有一行无意义的空白。
    # M-13：url 内嵌前经 strip_query——异常对象会被上层原样写进日志（流地址校验
    # 异常路径等），完整 URL 含 wsSecret/anti_code 等签名 token，明文落盘违反「写入日志前必须
    # 脱敏」红线；保留 host+path 已足够定位。
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with _build_opener(proxy).open(req, timeout=timeout) as resp:
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise RuntimeError(f"响应体超过 {_MAX_RESPONSE_BYTES} 字节上限 | url={strip_query(url)}")
            head = {k.lower(): v for k, v in resp.headers.items()}
            charset = "utf-8"
            ctype = head.get("content-type", "")
            m = re.search(r"charset=([\w-]+)", ctype, re.I)
            if m:
                charset = m.group(1)
            return HttpResponse(resp.status, head, raw.decode(charset, errors="replace"))
    except urllib.error.HTTPError as e:
        # HTTPError 也是响应(4xx/5xx)，读取 body 后按正常响应返回，便于上层判定
        try:
            err_raw = e.read(_MAX_RESPONSE_BYTES + 1)
            if len(err_raw) > _MAX_RESPONSE_BYTES:
                raise RuntimeError(f"错误响应体超过 {_MAX_RESPONSE_BYTES} 字节上限 | url={strip_query(url)}")
            body = err_raw.decode("utf-8", errors="replace")
        except Exception:
            # 错误体读不出/超限一律按空 body 降级：上层只做状态码与内容判定，不依赖错误体原文
            body = ""
        err_headers = {k.lower(): v for k, v in (e.headers or {}).items()}
        return HttpResponse(e.code, err_headers, body)
    except Exception as e:
        raise RuntimeError(f"HTTP 请求失败: {type(e).__name__}: {e} | url={strip_query(url)}") from e


def http_probe(
    url: str,
    *,
    method: str = "HEAD",
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
    proxy: str | None = None,
) -> ProbeResult:
    # 探针请求：只取状态码与响应头，不读 body(避免把直播流下载下来)。
    # 4xx/5xx 的 HTTPError 同样返回 ProbeResult(HTTPError 自带响应头)——斗鱼 hw CDN 对
    # HEAD 回 405+text/html，丢失响应头会让 content-type 启发式失效。
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with _build_opener(proxy).open(req, timeout=timeout) as resp:
            return ProbeResult(int(resp.status), {k.lower(): v for k, v in resp.headers.items()})
    except urllib.error.HTTPError as e:
        return ProbeResult(int(e.code), {k.lower(): v for k, v in (e.headers or {}).items()})
    except Exception as e:
        raise RuntimeError(f"探针失败: {type(e).__name__}: {e} | url={strip_query(url)}") from e


# ===== 2. 工具函数(文件名清洗 / JSON 安全取值 / host 提取 / 协议 MD5) =====


def clean_name(text: str, remove_emoji: bool = True) -> str:
    # 清洗为合法文件名：去非法字符、全角括号转半角、可选去 emoji、& 换下划线。
    # '&' 必须替换：在 Windows cmd 中它是命令分隔符，会让 ffmpeg 命令行被截断。
    name = re.sub(ILLEGAL_CHARS_PATTERN, "_", (text or "").strip()).strip("_")
    name = name.replace("（", "(").replace("）", ")")
    if remove_emoji:
        # 去 emoji / 其它非常用符号(保留 CJK、字母数字、常见标点)
        name = re.sub(r"[^\w\u4e00-\u9fff()（）\-_\. ]", "_", name)
    name = name.replace("&", "_")
    return name or FALLBACK_NAME


def host_of(url: str) -> str:
    # 提取 URL 主机名作为熔断 key(小写、保留端口)；解析失败统一归 "unknown"。
    # 坏 URL 共享同一个 "unknown" 桶是刻意取舍：为坏地址细分只会产生大量
    # 无统计意义的零散熔断桶。
    try:
        tail = url.split("://", 1)[-1]
        host = tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].lower()
        return host or "unknown"
    except Exception:
        return "unknown"


def dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    # 安全地逐层取值(dict 用键、list 用下标)，任一层缺失即返回 default。
    # 平台接口字段层层嵌套且随时可能缺失，直接 obj["a"]["b"] 会在接口变更时
    # 抛出 KeyError 并中断整个监控循环；统一走 dig 可保证单点降级。
    cur = obj
    for k in keys:
        try:
            cur = cur[k]
        except KeyError, IndexError, TypeError, AttributeError:
            return default
    return cur if cur is not None else default


def strip_query(url: str) -> str:
    # 去掉 URL 的 query 部分(用于日志脱敏与退避键)。
    return url.split("?", 1)[0]


# --- 不可信流地址候选的协议/目标判定 ---
#
# 平台 API 响应是不可信输入面(恶意/被劫持代理、接口投毒、MITM 都可能改写候选)，
# 候选在进探针与 ffmpeg 命令之前必须先过这道闸。与主程序 src/web_config.py 的
# _host_internal_reason / _internal_ip_reason 同判据的**离线子集**：不解析 DNS
# (与主线派生跳判定同一边界，DNS 重绑定窗口不在本层闭合)，只做「协议白名单 +
# IP 字面量(含 inet_aton 缩写形态) + 内部用途主机名」三类零 DNS 判定。

# 内部用途主机名(离线即可定罪)：云元数据端点与本机/内网集群常用名
_INTERNAL_HOST_EXACT = frozenset(
    {"localhost", "metadata", "metadata.google.internal", "metadata.goog", "metadata.tencentyun.com"}
)
_INTERNAL_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")
# CGNAT 100.64.0.0/10 在 3.14 的 ipaddress 里已不算私网(与主线同口径)，显式列出
_CGNAT_V4_NETWORK = ipaddress.ip_network("100.64.0.0/10")


def _parse_aton_part(part: str) -> int | None:
    # 单段解析：十进制 / 0x 十六进制 / 前导 0 八进制（与主线 web_config._parse_aton_part 同形；
    # int(part, 0) 会把 0177 这类前导零形态当非法抛 ValueError，不能用它）
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
    # 把 inet_aton 允许但 ipaddress 拒绝的缩写形态（2130706433 / 0177.0.0.1 / 127.1 /
    # 0x7f.0.0.1）还原成规范 IPv4。这些形态最终都会被 glibc/Windows 的解析器还原为
    # 127.0.0.1，必须在**本层**同款归一，不能指望「看起来不像 IP 就交给 DNS」——那会
    # 先被当作主机名放行。（与主线 web_config._ipv4_from_aton 同形）
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
    # 主机名为 IP 字面量时返回可判定的地址对象，否则返回 None(与主线 web_config._parse_ip_literal 同形)
    name = host.split("%", 1)[0]  # 去 IPv6 的 %zone(fe80::1%eth0 与 fe80::1 是同一目标)
    if not name:
        return None
    try:
        return ipaddress.ip_address(name)
    except ValueError:
        return _ipv4_from_aton(name)


def _internal_ip_reason(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    # 返回 None 表示可放行；否则给出拒绝理由(写进日志)。判据与主线 _internal_ip_reason 同族，
    # 独立发行版按「永不允许本机/内网目标」收口(无主线代理/SMTP 场景的 allow_local_targets 变体)。
    mapped = getattr(addr, "ipv4_mapped", None)
    if mapped is not None:
        # :ffff:127.0.0.1 这类 IPv4 映射地址必须按其承载的 v4 判定，否则 v6 侧一律「公网」
        return _internal_ip_reason(mapped)
    if addr.is_loopback:
        return f"回环地址({addr})"
    if addr.is_unspecified:
        return f"未指定地址({addr})"
    if addr.is_link_local:
        return f"链路本地地址({addr})"
    if addr.is_private:
        return f"私网地址({addr})"
    if addr.is_multicast:
        return f"组播地址({addr})"
    if addr.is_reserved:
        return f"保留地址({addr})"
    if addr.version == 4 and addr in _CGNAT_V4_NETWORK:
        return f"CGNAT 网段({addr})"
    return None


def _untrusted_stream_target_reason(url: str) -> str | None:
    # 返回 None 表示候选可放行；否则给出拒绝理由。三段判定顺序与主线一致：
    # 协议白名单最前 → IP 字面量(含缩写形态) → 内部用途主机名。
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return "URL 解析失败"
    if parts.scheme.lower() not in ("http", "https"):
        return f"协议不在白名单({parts.scheme or '空'})"
    host = parts.hostname or ""
    if not host:
        return "缺少主机名"
    literal = _parse_ip_literal(host)
    if literal is not None:
        return _internal_ip_reason(literal)
    lowered = host.lower()
    if lowered in _INTERNAL_HOST_EXACT or any(lowered.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES):
        return f"内部用途主机名({lowered})"
    return None


# --- 协议 MD5(RFC 1321 纯 Python 实现) ---
#
# 斗鱼 getEncryption 签名协议规定服务端按同一 MD5 链计算并校验，算法**不可更换**
# (换成其它摘要算法签名将永远不被服务端接受)。此处是第三方协议签名的忠实复刻，
# 非口令存储/完整性保护等安全用途。经逐行实现的 RFC 1321 算法完成，
# 正确性由 --selftest 的标准测试向量(空串/"abc"/fox 句)锁定。
_MD5_S = (7, 12, 17, 22) * 4 + (5, 9, 14, 20) * 4 + (4, 11, 16, 23) * 4 + (6, 10, 15, 21) * 4
# K[i] = floor(2^32 * |sin(i+1)|)，RFC 1321 标准推导(double 精度足以精确表示)
_MD5_K = tuple(int(abs(math.sin(i + 1)) * (1 << 32)) & 0xFFFFFFFF for i in range(64))


def _md5_hex(data: bytes | str) -> str:
    # RFC 1321 MD5，返回十六进制摘要。仅用于斗鱼签名(见上方说明)。
    msg = bytearray(data.encode("utf-8") if isinstance(data, str) else data)
    bit_len = (len(msg) * 8) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", bit_len)
    a0, b0, c0, d0 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    for off in range(0, len(msg), 64):
        m = [int.from_bytes(msg[off + i * 4 : off + i * 4 + 4], "little") for i in range(16)]
        a, b, c, d = a0, b0, c0, d0
        for i in range(64):
            if i < 16:
                f = (b & c) | (~b & d)
                g = i
            elif i < 32:
                f = (d & b) | (~d & c)
                g = (5 * i + 1) % 16
            elif i < 48:
                f = b ^ c ^ d
                g = (3 * i + 5) % 16
            else:
                f = c ^ (b | ~d)
                g = (7 * i) % 16
            f = (f + a + _MD5_K[i] + m[g]) & 0xFFFFFFFF
            a, d, c = d, c, b
            s = _MD5_S[i]
            b = (b + (((f << s) & 0xFFFFFFFF) | (f >> (32 - s)))) & 0xFFFFFFFF
        a0 = (a0 + a) & 0xFFFFFFFF
        b0 = (b0 + b) & 0xFFFFFFFF
        c0 = (c0 + c) & 0xFFFFFFFF
        d0 = (d0 + d) & 0xFFFFFFFF
    return struct.pack("<IIII", a0, b0, c0, d0).hex()


def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 15.0,
    proxy: str | None = None,
) -> dict[str, Any]:
    # 取回 JSON 并**校验 HTTP 状态码**。
    # 必须显式判状态码：代理/CDN 常以 4xx/5xx 返回一段 HTML 错误页，
    # 若不判状态码就 json.loads，会得到 JSONDecodeError 或"字段缺失"，
    # 把「网络/代理故障」误报成「主播未开播」，真实原因被彻底掩盖。
    resp = http_request(url, headers=headers, data=data, timeout=timeout, proxy=proxy)
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status} | url={strip_query(url)}")
    if not resp.text.strip():
        raise RuntimeError(f"响应体为空(疑似风控) | url={strip_query(url)}")
    return cast(dict[str, Any], json.loads(resp.text))


def _fetch_html(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    proxy: str | None = None,
) -> str:
    # 取回 HTML 文本并校验状态码(理由同 _fetch_json)。
    resp = http_request(url, headers=headers, timeout=timeout, proxy=proxy)
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status} | url={strip_query(url)}")
    return resp.text


# ===== 3. 录制请求头(校验探针与 ffmpeg 录制的唯一构造点) =====

# B站 CDN(bilivideo.com) 对无 Referer 的请求返回 403(content-type 为空)，必须下发。
_BILI_REFERER = "https://live.bilibili.com/"
_RECORD_REFERER_RULES: dict[str, str] = {"B站直播": _BILI_REFERER}

# 虎牙 CDN 反向校验 Referer：携带 Referer(https://www.huya.com/) 一律 403，
# 故虎牙**刻意不下发** Referer(原工程 _RECORD_HEADER_RULES 同结论，勿"补全"它)。

# 需要桌面 UA 的平台(国内 CDN 拒绝移动端 UA，返回 403)；其余平台沿用移动 UA
# (main.py ffmpeg 默认 UA)。桌面/移动 UA 与原工程一字不差。
_DESKTOP_UA_PLATFORMS = ("虎牙直播", "B站直播")


def record_headers(platform: str, cookies: str) -> dict[str, str]:
    # 按平台构造录制拉流请求头(UA/Referer/Cookie)。
    # 校验探针(validate_stream_url)与 ffmpeg 录制(build_ffmpeg_cmd)必须共用本函数，
    # 两端请求头一字不差——历史上任何一端单独改动 UA/Referer 都会造成
    # 「校验 200、ffmpeg 403」或反向的假绿/假红。
    headers: dict[str, str] = {}
    referer = _RECORD_REFERER_RULES.get(platform)
    if referer:
        headers["Referer"] = referer
    headers["User-Agent"] = DESKTOP_UA if platform in _DESKTOP_UA_PLATFORMS else MOBILE_UA
    if cookies:
        headers["Cookie"] = cookies
    return headers


# ===== 4. 并发调度中枢(整合自 src/scheduler.py) =====


class ResizableSemaphore:
    # 可运行时调容的信号量(消除重建竞态)，支持上下文管理器协议。本类是
    # src/scheduler.py::ResizableSemaphore 的**独立副本**(standalone 不 import src/)：
    # 改并发语义必须两处同改，改动此处时同步改 src/scheduler.py::ResizableSemaphore。
    # 内部严格分离两个量：_capacity = 并发上限(只由 set_value 改)、_used = 当前已持有
    # 许可数(只由 acquire/release 改)。**不得合并成单一字段**：一旦共用，该字段实际表示
    # 「剩余可用许可」而类注释与调用方都按「容量」理解它，于是任何「按目标容量绝对赋值」
    # 的重算(以及 release 与 acquire 不配对)都会把可用数补满 → 并发上限实质失控。
    # [历史注] 2026-09-20 修 src 侧该缺陷时副本未跟，2026-09-21 同步回灌。
    # 与 src 侧的行为等价性已实测一致：满员后第 4 次 acquire 失败；持有 3 个时
    # set_value(3→10) 只新增 7 个可用；超额 release 后 value 恒 <= capacity；set_value(0) 为暂停态。
    # 语义：set_value 增大唤醒相应数量等待者；减小仅降低上限、不强行回收已持有槽位；
    # 容量允许为 0(暂停态，acquire 永久阻塞直到调容)。
    def __init__(self, value: int) -> None:
        # 容量允许为 0(表示暂停/全部阻塞)，仅作下限保护避免负值。
        self._cond = threading.Condition()
        self._capacity = max(0, int(value))
        self._used = 0

    def __enter__(self) -> ResizableSemaphore:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        # 获取一个许可；blocking=False 时非阻塞；timeout>=0 时带超时(秒)。
        # 判据是「已持有 + 1 是否超过上限」而非「剩余许可是否 > 0」：与 release 对称，
        # 且不受「release 凭空造容量」影响。
        with self._cond:
            if not blocking:
                if self._used + 1 > self._capacity:
                    return False
                self._used += 1
                return True
            endtime: float | None = None
            if timeout >= 0:
                endtime = time.monotonic() + timeout
            while self._used + 1 > self._capacity:
                if endtime is not None:
                    remaining = endtime - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()
            self._used += 1
            return True

    def release(self) -> None:
        # 归还一个许可(只减 _used，绝不增 _capacity)并唤醒一个等待者。
        # _used 下界钳制：release 与 acquire 不配对(异常路径重复释放)时不得凭空造出许可。
        with self._cond:
            if self._used > 0:
                self._used -= 1
            self._cond.notify()

    def set_value(self, new_value: int) -> None:
        # 调整容量：**只改上限**，_used 保持不变(故 decrease 天然不回收已持有槽位)；
        # 唤醒数量取「新可用数 = 新容量 - 已持有」——Condition.notify(n) 至多唤醒 n 个，
        # 等待者更少时全部唤醒、唤醒偏多也无害(acquire 的 while 会重新检查并继续等待)。
        new_value = max(0, int(new_value))
        with self._cond:
            self._capacity = new_value
            free = new_value - self._used
            if free > 0:
                self._cond.notify(free)

    @property
    def value(self) -> int:
        # 剩余可用许可数(= 上限 - 已持有)。判定「还能不能再塞进一个请求」用它；
        # 展示/比较并发上限一律用 capacity，二者在有持有者时必然不同。
        with self._cond:
            return max(0, self._capacity - self._used)

    @property
    def capacity(self) -> int:
        # 并发上限本身(与当前持有数无关)：调度器重算容量时与之比较。
        with self._cond:
            return self._capacity


class PlatformBreaker:
    # 按 key(host) 的熔断器：closed(放行) → open(熔断) → half-open(放一个探针)。
    # 探针带租约：授予后超过 lease 秒仍未上报样本(如主播未开播的等待轮)时重新授予，否则 _probing
    # 永不复位 → 该 key 永久熔断直到进程重启。
    # half-open 的回报必须经 _probing/_probe_owner/_probe_seq 门控：只有「当前代探针的持有线程」
    # 的回报才允许驱动状态迁移，其余回报只入窗口。缺门控的后果不是「统计略偏」而是行为相反：
    # 熔断前已放行、此刻才收尾的普通轮次 record_success 会直接 clear() 样本窗口并置 closed →
    # 坏 CDN 立刻重新拿到全部房间流量；租约重授予后那条陈旧探针的回报同样能关掉新探针。
    # 同源副本：src/scheduler.py::PlatformBreaker(本类按设计不 import src/)。**两份实现并不等价**，
    # 且方法集合会随单边改动漂移，故不在此抄快照 —— 要下结论就现场跑 `grep -n "^    def "`
    # 逐方法 diff 后再显式决定同步方向。
    # 已知的刻意保留差异(逐条显式决定，不是漏同步)：① 时间源用 time.monotonic() 而非 src 的
    # _now() 间接层(那是给测试 patch 的 seam，副本无该测试面)；② 探针归属比对用
    # threading.current_thread() 对象身份而非 get_ident()(ident 会被已死线程复用)；③ min_samples
    # 取 src 默认值 8 但不做构造参数(本副本构造点只有一处)；④ 租约时长以类属性 LEASE_SECONDS
    # 表达(src 是模块级 _PROBE_LEASE_SECONDS)，数值同为 60.0，改一侧须同步另一侧；⑤ 仍缺 src 的
    # error_rate / backoff_seconds，样本入队函数名为 _push 而非 _push_sample —— 属**已登记**的
    # 行为无关差异，不是待回灌项。
    LEASE_SECONDS = 60.0
    MIN_SAMPLES = 8  # 与 src/scheduler.py::PlatformBreaker 的 min_samples 默认值同值

    def __init__(self, name: str, window: int = 40, fail_rate: float = 0.5, cooldown: float = 45.0) -> None:
        self.name = name
        self._window = max(1, window)
        # 该回灌(与 src/scheduler.py:PlatformBreaker 同批改)：fail_rate 钳到 [0,1]。
        # 副本此前原样保存配置值，0.0 会让「0 >= 0」恒真、1.5 会让熔断永不触发，两种错配在
        # 主线已被 clamp 消化，副本不 clamp 就是同一份配置的两种行为。
        self._fail_rate = min(1.0, max(0.0, float(fail_rate)))
        self._cooldown = max(0.0, float(cooldown))
        # 2026-10-21 该回灌：阈值必须同时受窗口上界约束——MIN_SAMPLES(8) > window 时
        # len(_samples) 永远达不到阈值、熔断器整生不开，坏 host 拿满全部流量且永不自愈。
        self._min_samples = max(1, min(self.MIN_SAMPLES, self._window))
        self._lock = threading.Lock()
        # deque(maxlen) + 增量计数：满员时 append 自行挤出最旧样本，扣掉它的贡献即 O(1)，
        # 与 src::_push_sample 逐行同实现。禁止退回 sum(samples) 全量重算，也禁止退回
        # 「list + 满员 pop(0)」——那是**持锁下**每条样本多一次 O(n) 元素搬移(窗口 40)。
        # [历史注] pop(0) 形态于 2026-09-23 该回灌时消除。
        self._samples: deque[int] = deque(maxlen=self._window)
        self._fail_count = 0
        self._state = "closed"
        self._open_until = 0.0
        self._probing = False
        self._granted_at = 0.0
        # 探针代数 + 当前探针持有线程(与 src 同结构)：_probing 只是布尔，租约重授予后
        # 旧探针的回报仍会命中 half-open 分支、替新探针把状态机复位，故须记归属。
        self._probe_seq = 0
        self._probe_owner: threading.Thread | None = None

    def _push(self, failed: int) -> None:
        # 入队一个样本并同步维护失败计数(挤出/入队各 O(1)，见上方 _samples 注释)；调用方须已持锁。
        if len(self._samples) == self._window:
            self._fail_count -= self._samples[0]
        self._samples.append(failed)
        self._fail_count += failed

    def _grant_probe(self, now: float) -> None:
        # 授予(或按租约重授予)探针：递增代数、登记持有线程与授予时刻。调用方须已持锁。
        # 本副本的 allow()/record() 均在同一录制线程内调用(run_loop 的房间线程)，
        # 故线程身份足以判定某条回报属于哪一代探针。
        self._probing = True
        self._probe_seq += 1
        self._probe_owner = threading.current_thread()
        self._granted_at = now

    def _end_probe(self) -> None:
        # 探针闭环：清除持有线程(_probe_seq 保留，代数只增不减、供后续比对)。
        self._probing = False
        self._probe_owner = None

    def record(self, success: bool) -> None:
        with self._lock:
            self._push(0 if success else 1)
            if self._state == "closed":
                # 该回灌：_fail_count > 0 是必要条件(fail_rate=0 时全成功窗口
                # 会因 0 >= 0 被直接熔断)，阈值改读按窗口钳制过的 _min_samples(见 __init__)。
                # 计数仍走增量 _fail_count，禁止退回 sum(self._samples)(AGENTS「熔断计数必须增量」)。
                if (
                    self._fail_count > 0
                    and len(self._samples) >= self._min_samples
                    and self._fail_count / len(self._samples) >= self._fail_rate
                ):
                    self._state = "open"
                    self._open_until = time.monotonic() + self._cooldown
                    self._end_probe()
            elif self._state == "half-open":
                if not self._probing or self._probe_owner is not threading.current_thread():
                    # 非探针回报：① 转入 half-open 前就已放行、此刻仍在途的普通轮次；
                    # ② 已被租约重授予取代的**陈旧探针**(其持有线程不是当前持有者)。
                    # 样本照常入窗口(供 closed 态复用阈值判定)，但不得驱动
                    # half-open→closed/open 迁移——否则旧探针会替新探针清窗口、关熔断。
                    return
                self._end_probe()
                # 当前探针结果决定：成功则恢复，失败则重新熔断(延长冷却)
                if success:
                    self._state = "closed"
                    self._samples.clear()
                    self._fail_count = 0
                else:
                    self._state = "open"
                    self._open_until = time.monotonic() + self._cooldown

    def allow(self) -> bool:
        with self._lock:
            if self._state == "closed":
                return True
            now = time.monotonic()
            if self._state == "open":
                if now >= self._open_until:
                    if not self._probing:
                        self._state = "half-open"
                        self._grant_probe(now)
                        return True
                    return False
                return False
            # half-open
            if not self._probing:
                self._grant_probe(now)
                return True
            if now - self._granted_at >= self.LEASE_SECONDS:
                self._grant_probe(now)  # 租约超时：自愈，重新授予(代数递增、归属改记)
                return True
            return False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state


class Scheduler:
    # 并发调度中枢：网络并发容量 + 录制并发上限 + 按 host 熔断。
    # 熔断表容量上限(该回灌，与 src/scheduler.py:_MAX_BREAKERS 同值同判据)——
    # key 来自 host_of(record_url)，属外部可控输入，旧写法只增不减，24×7 长跑下每个历史 host
    # 留一支 PlatformBreaker(含 window 长度样本窗口)。逐出只看「最久未使用 + closed」，
    # open/half-open 的键**不逐**（摘掉等于把一次进行中的熔断重置成放行，坏 CDN 会立刻回到全部房间）。
    MAX_BREAKERS = 1024

    def __init__(self, network_limit: int = 8, record_limit: int = 0) -> None:
        self.network_semaphore = ResizableSemaphore(max(1, network_limit))
        # 录制并发：0 表示不限制(用一个大容量代替，避免每处判空)
        self.record_limit = max(0, record_limit)
        self.recording_semaphore = ResizableSemaphore(self.record_limit or 4096)
        self._lock = threading.Lock()
        # OrderedDict：_breaker 命中即 move_to_end，容量到顶时按「最久未被任何房间使用」逐出
        self._breakers: OrderedDict[str, PlatformBreaker] = OrderedDict()

    def set_record_limit(self, n: int) -> None:
        self.record_limit = max(0, int(n))
        self.recording_semaphore.set_value(self.record_limit or 4096)

    def _evict_breakers_locked(self) -> None:
        # 调用方须已持 self._lock；锁序与主线一致：本方法在 _lock 内读 br.state(再取
        # PlatformBreaker._lock)，PlatformBreaker 从不反向引用调度器，不存在锁序环。
        # 全部键都在熔断态时本轮不逐出(宁可暂时超限，也不清除仍在生效的防线)。
        while len(self._breakers) > self.MAX_BREAKERS:
            victim = next((key for key, br in self._breakers.items() if br.state == "closed"), None)
            if victim is None:
                return
            self._breakers.pop(victim, None)

    def _breaker(self, key: str) -> PlatformBreaker:
        with self._lock:
            b = self._breakers.get(key)
            if b is None:
                b = PlatformBreaker(key)
                self._breakers[key] = b
                self._evict_breakers_locked()
                return b
            # 命中即 touch：仍在每轮上报的 host 因此不会因「创建得早」被逐掉、丢累计样本
            self._breakers.move_to_end(key)
            return b

    def allow(self, key: str) -> bool:
        return self._breaker(key).allow()

    def record_success(self, key: str | None) -> None:
        # 成功必须显式回传：否则失败率统计被稀释，熔断永不触发。
        if key:
            self._breaker(key).record(True)

    def record_failure(self, key: str | None) -> None:
        if key:
            self._breaker(key).record(False)

    def states(self) -> dict[str, str]:
        with self._lock:
            return {k: b.state for k, b in self._breakers.items()}


# ===== 5. 平台解析(整合自 src/spider.py 对应平台分支) =====


@dataclass
class StreamInfo:
    # 统一的解析结果。字段缺失时为空串/空列表，绝不抛异常。
    platform: str = ""
    anchor_name: str = ""
    title: str = ""
    is_live: bool = False
    m3u8_urls: list[str] = field(default_factory=list)
    flv_urls: list[str] = field(default_factory=list)
    record_url: str = ""
    cookies: str = ""
    error: str = ""

    @property
    def has_stream(self) -> bool:
        return bool(self.m3u8_urls or self.flv_urls or self.record_url)


# ---------- 抖音 ----------


def resolve_douyin(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    # 抖音：webcast/room/web/enter 接口。
    # 接口接受数字房间号与抖音号两种 web_rid；live.douyin.com/<抖音号> 不会重定向，
    # 故直接取路径末段即可，不要写重定向解析逻辑。
    # 风控信号是 HTTP 200 + 空响应体(而非 4xx)，必须先判断 len(text)==0。
    info_ = StreamInfo(platform="抖音直播", cookies=cookies)
    rid = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not rid:
        info_.error = "无法从 URL 解析抖音房间号"
        return info_
    params = {
        "aid": "6383",
        "app_name": "douyin_web",
        "live_id": "1",
        "device_platform": "web",
        "language": "zh-CN",
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "web_rid": rid,
    }
    api = f"https://live.douyin.com/webcast/room/web/enter/?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": DESKTOP_UA, "Referer": "https://live.douyin.com/", "Accept": "application/json"}
    if cookies:
        headers["Cookie"] = cookies
    resp = http_request(api, headers=headers, timeout=15, proxy=proxy)
    if resp.status >= 400:
        info_.error = f"抖音接口 HTTP {resp.status}"
        return info_
    if not resp.text.strip():
        # 风控特征：200 + 空 body
        info_.error = "抖音接口返回空响应体(疑似风控)，建议配置 抖音cookie 后重试"
        return info_
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError as e:
        info_.error = f"抖音接口返回非 JSON: {type(e).__name__}: {e}"
        return info_

    # 第二道检测：抖音风控的第二形态是「HTTP 200 + 合法 JSON，但业务层 status_code 非零」
    # （如 status_code=8 需登录、=4002 参数异常）。只看 HTTP 状态与空响应体会漏掉这一形态
    # → 风控被误报成"未开播"，用户得不到「去配 cookie」的有效提示，只会反复重试。
    # 与主工程 src/spider.py 同判据（该侧在 200+合法 JSON 后同样检 status_code 非零）。
    if isinstance(data, dict):
        try:
            api_status_code = int(cast(str, data.get("status_code"))) if data.get("status_code") is not None else 0
        except TypeError, ValueError:
            api_status_code = 0
        if api_status_code != 0:
            status_msg = data.get("status_msg", "unknown error")
            info_.error = (
                f"抖音接口业务层拒绝: status_code={api_status_code}, msg={status_msg}，建议配置 抖音cookie 后重试"
            )
            return info_

    room = dig(data, "data", "data", 0, default={}) or {}
    info_.anchor_name = str(dig(room, "anchor", "nickname", default="") or "")
    info_.title = str(dig(room, "title", default="") or "")
    status = dig(room, "status", default=0)
    stream_url = dig(room, "stream_url", default={}) or {}

    pull_map = dig(stream_url, "flv_pull_url", default={}) or {}
    if isinstance(pull_map, dict):
        for k, v in pull_map.items():
            # h265 流无法 -c copy 进 flv 容器，按键名直接剔除(FULL_H265/SD_H265 等)
            if isinstance(v, str) and v and "h265" not in str(k).lower():
                info_.flv_urls.append(v)
    hls_map = dig(stream_url, "hls_pull_url_map", default={}) or {}
    if isinstance(hls_map, dict):
        for v in hls_map.values():
            if isinstance(v, str) and v:
                info_.m3u8_urls.append(v)
    info_.record_url = str(dig(stream_url, "hls_pull_url", default="") or "")
    # status==2 表示正在直播；有流地址也视为在播(部分版本 status 字段不可靠)
    info_.is_live = (status == 2) or info_.has_stream
    return info_


# ---------- 虎牙 ----------

# 虎牙页面中的 stream 数据：非贪婪匹配到 "iWebDefaultBitRate" 结束(与原工程一致)
_HUYA_STREAM_RE = re.compile(r'stream: (\{"data".*?),"iWebDefaultBitRate"')
# 房间别名(含字母)时从 HTML 提取数字房间号(与原工程 get_huya_app_stream_url 一致)
# 孪生点：主实现 src/spider.py:get_huya_app_stream_url 的正则现已与本
# 副本**逐字同串**(键名起始引号作锚点)，且两侧都在取回后剥引号 + 判 isdigit。改此处须两处同改。
_HUYA_PROFILE_ROOM_RE = re.compile(r'"ProfileRoom":(.*?),"sPrivateHost')


def _huya_build(s_flv_url: str, s_stream_name: str, s_suffix: str, anti_code: str) -> str:
    # 拼接虎牙流地址：base + '/' + streamName + '.' + suffix + '?' + antiCode。
    # anti_code 为空时不追加 '?'，避免产生以问号结尾的畸形 URL。
    base = f"{s_flv_url.rstrip('/')}/{s_stream_name}.{s_suffix}"
    return f"{base}?{anti_code}" if anti_code else base


def _loads_stream_json(raw: str) -> dict[str, Any]:
    # 解析虎牙 stream 片段：兼容「少一个右括号」与「已完整」两种页面结构。
    # 正则非贪婪匹配到 ,"iWebDefaultBitRate" 前为止，真实页面常在此截断掉根对象的
    # 右花括号(需补一个 '}')；但页面结构变动时也可能已经闭合(补 '}' 会 Extra data)。
    # 故两种形态都尝试，任一成功即可，避免把结构差异升级为整轮解析失败。
    last_err: Exception | None = None
    for candidate in (raw + "}", raw):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as e:
            last_err = e
    raise json.JSONDecodeError(f"虎牙 stream 字段无法解析: {last_err}", raw, 0)


def resolve_huya(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    # 虎牙：解析 HTML 中的 stream 字段；失败时兜底微信小程序接口(cache.php)。
    info_ = StreamInfo(platform="虎牙直播", cookies=cookies)
    headers = {
        "User-Agent": HTML_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.8",
    }
    if cookies:
        headers["Cookie"] = cookies
    # 主路径失败原因必须与"主播未开播"严格区分：若页面因代理/网络/状态码取不到，
    # 兜底接口会把它静默掩盖成"未开播"，真实故障再也无法定位(实测 502 即此形态)。
    fetch_failed_reason = ""
    html = ""
    match: Any = None
    try:
        html = _fetch_html(url, headers=headers, timeout=15, proxy=proxy)
        match = _HUYA_STREAM_RE.search(html)
    except Exception as e:
        fetch_failed_reason = f"页面获取失败: {type(e).__name__}: {e}"
    if match:
        try:
            data = _loads_stream_json(match.group(1))
        except json.JSONDecodeError as e:
            info_.error = f"虎牙 stream 字段解析失败: {type(e).__name__}: {e}"
            return info_
        info_.anchor_name = str(dig(data, "data", 0, "gameLiveInfo", "nick", default="") or "")
        info_.title = str(dig(data, "data", 0, "gameLiveInfo", "roomName", default="") or "")
        stream_list = dig(data, "data", 0, "gameStreamInfoList", default=[]) or []
        for item in stream_list:
            flv = _huya_build(
                str(dig(item, "sFlvUrl", default="") or ""),
                str(dig(item, "sStreamName", default="") or ""),
                str(dig(item, "sFlvUrlSuffix", default="flv") or "flv"),
                str(dig(item, "sFlvAntiCode", default="") or ""),
            )
            if flv.startswith("http"):
                info_.flv_urls.append(flv)
            hls = _huya_build(
                str(dig(item, "sHlsUrl", default="") or ""),
                str(dig(item, "sStreamName", default="") or ""),
                str(dig(item, "sHlsUrlSuffix", default="m3u8") or "m3u8"),
                str(dig(item, "sHlsAntiCode", default="") or ""),
            )
            if hls.startswith("http"):
                info_.m3u8_urls.append(hls)
        info_.is_live = info_.has_stream
        return info_

    # 兜底：微信小程序接口。房间别名(含字母)时先从已取到的 HTML 还原数字房间号
    room_id = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not room_id.isdigit() and html:
        m = _HUYA_PROFILE_ROOM_RE.search(html)
        if m:
            # 页面的 "ProfileRoom" 有数字(:6030242)与字符串(:"6030242")两种内联形态，
            # 非贪婪捕获对后者会连引号一起收下 → 不剥引号则恒判非数字、白丢兜底接口
            # (与 src/spider.py 同步，见上方 _HUYA_PROFILE_ROOM_RE 的孪生点注释)。
            room_id = m.group(1).strip().strip('"')
    if not room_id.isdigit():
        info_.error = f"{fetch_failed_reason}；未能解析 stream 数据，且未取得数字房间号，无法走兜底接口".strip("；")
        return info_
    api = f"https://mp.huya.com/cache.php?{urllib.parse.urlencode({'m': 'Live', 'do': 'profileRoom', 'roomid': room_id, 'showSecret': '1'})}"
    wx_headers = {
        "User-Agent": "ios/7.830 (ios 17.0; ; iPhone 15 (A2846/A3089/A3090/A3092))",
        "xweb_xhr": "1",
        "referer": "https://servicewechat.com/wx74767bf0b684f7d3/301/page-frame.html",
    }
    try:
        body = _fetch_json(api, headers=wx_headers, timeout=15, proxy=proxy)
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"{fetch_failed_reason}；兜底接口亦失败: {type(e).__name__}: {e}".strip("；")
        return info_
    data_field = dig(body, "data", default={}) or {}
    info_.anchor_name = str(dig(data_field, "profileInfo", "nick", default="") or "")
    if dig(data_field, "realLiveStatus", default="") != "ON":
        info_.is_live = False
        # 仅在主路径确属"取页失败"时披露原因；页面正常但未开播则不制造噪音
        if fetch_failed_reason:
            info_.error = fetch_failed_reason
        return info_
    for item in dig(data_field, "stream", "baseSteamInfoList", default=[]) or []:
        flv = _huya_build(
            str(dig(item, "sFlvUrl", default="") or ""),
            str(dig(item, "sStreamName", default="") or ""),
            str(dig(item, "sFlvUrlSuffix", default="flv") or "flv"),
            str(dig(item, "sFlvAntiCode", default="") or ""),
        )
        if flv.startswith("http"):
            info_.flv_urls.append(flv)
    info_.is_live = info_.has_stream
    return info_


# ---------- B站 ----------


def resolve_bilibili(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    # B站：room_init 判开播/取真实房间号与 uid → playUrl 取流；
    # 开播后再补主播名(Master/info)与标题(getH5InfoByRoom)。
    # 注意：live_status 在 room_init 响应里，**不在 playUrl 响应里**——
    # 从 playUrl 读 live_status 恒为缺失，会导致 B站永远判定未开播(1.0.0 版实测缺陷)。
    info_ = StreamInfo(platform="B站直播", cookies=cookies)
    room_id = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not room_id.isdigit():
        info_.error = "B站房间号必须是纯数字"
        return info_
    headers = record_headers("B站直播", cookies)
    try:
        init = _fetch_json(
            f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}",
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"B站接口失败: {type(e).__name__}: {e}"
        return info_
    real_id = str(dig(init, "data", "room_id", default=room_id) or room_id)
    uid = dig(init, "data", "uid", default="")
    if dig(init, "data", "live_status", default=0) != 1:
        info_.is_live = False
        return info_
    info_.is_live = True

    # 主播名与标题获取失败不致整轮失败(取不到时降级为 uid / 空标题)
    try:
        master = _fetch_json(
            f"https://api.live.bilibili.com/live_user/v1/Master/info?uid={uid}",
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
        info_.anchor_name = str(dig(master, "data", "info", "uname", default="") or "")
    except (json.JSONDecodeError, RuntimeError) as e:
        debug(f"B站主播名获取失败，以 uid 兜底: {type(e).__name__}: {e}")
        info_.anchor_name = str(uid or "")
    try:
        h5 = _fetch_json(
            f"https://api.live.bilibili.com/xlive/web-room/v1/index/getH5InfoByRoom?room_id={room_id}",
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
        info_.title = str(dig(h5, "data", "room_info", "title", default="") or "")
    except (json.JSONDecodeError, RuntimeError) as e:
        debug(f"B站标题获取失败: {type(e).__name__}: {e}")

    try:
        play = _fetch_json(
            "https://api.live.bilibili.com/room/v1/Room/playUrl?"
            + urllib.parse.urlencode({"cid": real_id, "qn": "10000", "platform": "web"}),
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"B站取流失败: {type(e).__name__}: {e}"
        return info_
    durl = dig(play, "data", "durl", default=[]) or []
    urls = [u for u in (str(dig(d, "url", default="") or "") for d in durl) if u]
    if urls:
        # 优选 d1--cn-gotcha 线路(原工程同策略)，其余按序作备选候选
        preferred = [u for u in urls if "d1--cn-gotcha" in u]
        info_.flv_urls = preferred + [u for u in urls if "d1--cn-gotcha" not in u]
    return info_


# ---------- 斗鱼 ----------

# 斗鱼访客 did(与原工程 get_douyu_stream_data 一致的固定值)
_DOUYU_DID = "10000000000000000000000000003306"


def _douyu_compute_auth(rand_str: str, key: str, enc_time: int, sign_str: str) -> str:
    # 斗鱼签名核心：auth = rand_str 经 enc_time 次 md5(auth+key) 迭代后，再 md5(auth+key+sign_str)。
    # sign_str 在 is_special==1 时为空串，否则为 f"{rid}{ts}"(由调用方决定)。
    # 这是纯 MD5 链式算法——**不需要 Node/JS 引擎**，见 _md5_hex 的 RFC 1321 实现。
    auth = rand_str
    for _ in range(max(0, enc_time)):
        auth = _md5_hex(auth + key)
    return _md5_hex(auth + key + sign_str)


def _douyu_sign_params(rid: str, proxy: str | None) -> dict[str, str]:
    # 经 getEncryption 接口取签名要素并本地计算(与原工程 spider.get_token_js 对齐)：
    # 接口下发 rand_str/key/enc_time/enc_data/is_special，失败抛 RuntimeError。
    headers = {"User-Agent": DESKTOP_UA, "Referer": f"https://www.douyu.com/{rid}"}
    api = f"https://www.douyu.com/wgapi/livenc/liveweb/websec/getEncryption?did={_DOUYU_DID}"
    data = _fetch_json(api, headers=headers, timeout=15, proxy=proxy)
    err = dig(data, "error", default=-1)
    if err != 0:
        raise RuntimeError(f"getEncryption 返回 error={err}")
    enc = dig(data, "data", default={}) or {}
    ts = int(time.time())
    sign_str = "" if dig(enc, "is_special", default=0) == 1 else f"{rid}{ts}"
    auth = _douyu_compute_auth(
        str(dig(enc, "rand_str", default="") or ""),
        str(dig(enc, "key", default="") or ""),
        int(dig(enc, "enc_time", default=0) or 0),
        sign_str,
    )
    return {"enc_data": str(dig(enc, "enc_data", default="") or ""), "did": _DOUYU_DID, "ts": str(ts), "auth": auth}


def resolve_douyu(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    # 斗鱼：betard 取房间信息 → getEncryption 签名 → getH5PlayV1 取流。
    info_ = StreamInfo(platform="斗鱼直播", cookies=cookies)
    rid = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    m = re.search(r"rid=(\d+)", url)
    if m:
        rid = m.group(1)
    if not rid.isdigit():
        info_.error = "斗鱼房间号必须是纯数字"
        return info_
    headers = {"User-Agent": HTML_UA, "Referer": f"https://www.douyu.com/{rid}"}
    if cookies:
        headers["Cookie"] = cookies
    try:
        room = _fetch_json(f"https://www.douyu.com/betard/{rid}", headers=headers, timeout=15, proxy=proxy)
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"斗鱼房间信息获取失败: {type(e).__name__}: {e}"
        return info_
    info_.anchor_name = str(dig(room, "room", "nickname", default="") or "")
    live = dig(room, "room", "videoLoop", default=1) == 0 and dig(room, "room", "show_status", default=0) == 1
    if not live:
        info_.is_live = False
        return info_
    info_.is_live = True
    info_.title = str(dig(room, "room", "room_name", default="") or "").replace("&nbsp;", "")

    post_headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": f"https://www.douyu.com/{rid}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if cookies:
        post_headers["Cookie"] = cookies
    try:
        sign = _douyu_sign_params(rid, proxy)
        post = (
            f"enc_data={sign['enc_data']}&tt={sign['ts']}"
            f"&did={sign['did']}&auth={sign['auth']}&cdn=&rate=-1&hevc=0&fa=0&ive=0"
        ).encode("utf-8")
        play = _fetch_json(
            f"https://www.douyu.com/lapi/live/getH5PlayV1/{rid}",
            headers=post_headers,
            data=post,
            timeout=15,
            proxy=proxy,
        )
    except (json.JSONDecodeError, KeyError, RuntimeError) as e:
        info_.error = f"斗鱼取流失败: {type(e).__name__}: {e}"
        return info_
    err = dig(play, "error", default=-1)
    if err != 0:
        info_.error = f"斗鱼取流失败: error={err} msg={dig(play, 'msg', default='')}"
        return info_
    rtmp_live = str(dig(play, "data", "rtmp_live", default="") or "")
    rtmp_url = str(dig(play, "data", "rtmp_url", default="") or "")
    if rtmp_live and rtmp_url:
        flv = f"{rtmp_url}/{rtmp_live}"
        info_.record_url = flv
        # 同 token FLV→m3u8 HLS 候选(原工程硬约定)：游客态 FLV 长连接约 70 秒被 CDN
        # 掐断(反复分段 I/O error)，token 对 FLV/HLS 通用，改路径后缀即得 HLS 播放列表；
        # HLS 逐段拉取免疫单连接超时。候选可达性由 select_source_url 校验 gating。
        if ".flv" in rtmp_live:
            info_.m3u8_urls.append(flv.replace(".flv", ".m3u8", 1))
    return info_


# ---------- 平台分派表 ----------


class PlatformResolver(Protocol):
    # 平台解析器调用约定：必须支持 proxy/cookies 关键字调用。
    # 用 Protocol 而非 Callable[[str, str | None, str], StreamInfo]：后者丢失形参名，
    # 分派处只能按位置传参，签名一旦调整极易错位(proxy/cookies 类型相近)。
    def __call__(self, url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo: ...


PLATFORM_RULES: list[tuple[str, str, PlatformResolver]] = [
    (r"live\.douyin\.com|douyin\.com/[0-9]", "抖音直播", resolve_douyin),
    (r"huya\.com", "虎牙直播", resolve_huya),
    (r"live\.bilibili\.com", "B站直播", resolve_bilibili),
    (r"douyu\.com", "斗鱼直播", resolve_douyu),
]


def platform_of(url: str) -> str:
    # 仅按 URL 判定平台名(不做网络请求)。
    # 必须在解析之前就能拿到平台名：各平台的 Cookie 是按平台分别配置的，
    # 而解析请求本身就需要携带 Cookie，否则会形成「先解析才知道平台、但解析需要
    # 平台 Cookie」的死锁 —— 原实现的等价缺陷是按空平台取 Cookie，恒取不到。
    for pattern, name, _fn in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            return name
    return ""


def dispatch(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    # 按 URL 分派到平台解析器；未知平台返回带 error 的 StreamInfo(不抛异常)。
    for pattern, _name, fn in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            try:
                return fn(url, proxy=proxy, cookies=cookies)
            except Exception as e:
                # 单个平台解析异常不得中断整个监控循环
                return StreamInfo(error=f"{type(e).__name__}: {e}")
    return StreamInfo(error=f"不支持的平台: {host_of(url)}")


# ===== 6. 流地址校验(整合自 src/stream_select.py) =====

# 同 host 探针最小间隔 + 抖动：多房间并发时避免毫秒级连击触发风控
_PROBE_MIN_HOST_INTERVAL = 0.35
_PROBE_JITTER = 0.4
# GET 复核重试间隔 + 抖动(固定间隔会形成「按节奏识别」的机器人指纹)
_GET_RECHECK_INTERVAL = 0.8
_GET_RECHECK_JITTER = 0.7
_PROBE_TIMEOUT = 8.0
# 流媒体 content-type 判定关键字(m3u8/flv 共用)
_STREAM_MEDIA_TYPES = ("video", "octet-stream", "flash", "mpegurl")

_throttle_lock = threading.Lock()
_probe_last_seen: dict[str, float] = {}


def _throttle_probe(url: str) -> None:
    # 同 host 探针节流：锁内计算、锁外睡眠，不阻塞其它 host。
    # 计时一律 time.monotonic()：墙上时钟会被 NTP 校时/手动改表/虚拟机漂移而**向前跳变**，
    # 此时 gap-(now-last) 算出巨大的 wait，把探针线程冻结数十秒甚至更久(表现为「某房间
    # 突然长时间不检测」且无任何日志)；向后回拨则让节流静默失效。
    # [历史注] 2026-09-12 审查前用 time.time()。
    host = host_of(url)
    wait = 0.0
    with _throttle_lock:
        now = time.monotonic()
        gap = _PROBE_MIN_HOST_INTERVAL + _SYS_RANDOM.uniform(0, _PROBE_JITTER)
        last = _probe_last_seen.get(host, 0.0)
        if now - last < gap:
            wait = gap - (now - last)
        _probe_last_seen[host] = now + wait
    if wait > 0:
        time.sleep(wait)


def _recheck_delay() -> float:
    return _GET_RECHECK_INTERVAL + _SYS_RANDOM.uniform(0, _GET_RECHECK_JITTER)


# ---------- 探针退避(整合自 src/stream_select.py，白名单仅虎牙) ----------
#
# 虎牙 CDN 按连接预算限流：每轮「探针 + ffmpeg 拉流」烧光预算后，校验 GET 复核通过、
# ffmpeg 立即 403，录制陷入秒级失败循环。观测到 401/403 后把该线路记入退避窗口：
# 窗口内跳过全部探针——非末位候选回退下一候选，末位候选零探针直接放行 ffmpeg。
# **绝不可把斗鱼等平台加入名单**：斗鱼的偶发 403 由「重试一次再定罪」救回，
# 负缓存会导致斗鱼回退 FLV(游客态约 70 秒被掐)回归。
_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)
# 退避窗口动态下限：主循环周期由 Recorder 按配置写入。窗口必须 ≥ 一个主循环周期
# (+ 错误窗口余量)，否则「记退避 → 下一轮早已出窗 → 再撞同一条死线路」闭环恒不成立。
_MAIN_LOOP_INTERVAL: float = 120.0
_PROBE_BACKOFF_MARGIN = 70.0

_probe_backoff_lock = threading.Lock()
_probe_reject_until: dict[str, float] = {}


def _probe_backoff_window() -> float:
    return max(60.0, _MAIN_LOOP_INTERVAL + _PROBE_BACKOFF_MARGIN)


def _probe_key(url: str) -> str:
    # 退避键 = scheme://host/路径(去 query)：虎牙 antiCode 里的 wsTime 等参数每轮变化，
    # 按 query 区分会让退避永远命不中。
    return strip_query(url)


def _mark_probe_reject(url: str, platform: str) -> None:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return
    with _probe_backoff_lock:
        _probe_reject_until[_probe_key(url)] = time.monotonic() + _probe_backoff_window()


def _probe_in_backoff(url: str, platform: str) -> bool:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return False
    with _probe_backoff_lock:
        until = _probe_reject_until.get(_probe_key(url))
        if until is None:
            return False
        if time.monotonic() >= until:
            _probe_reject_until.pop(_probe_key(url), None)
            return False
        return True


def clear_probe_reject(url: str, platform: str) -> None:
    # 录制成功的线路立即撤销退避(与 _mark_probe_reject 共用白名单与键)：
    # 否则窗口内已恢复的线路会被继续跳过、白白回退到次优线路。
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return
    with _probe_backoff_lock:
        _probe_reject_until.pop(_probe_key(url), None)


def _registrable_domain_lite(host: str) -> str:
    # 近似注册域（末两段），仅用于派生跳的 Cookie 裁决（主线 src/stream_select.py
    # _registrable_domain 同判据）；IP 字面量与双段主机返回空串（不成域、只认精确相等）。
    if _parse_ip_literal(host) is not None or ":" in host:
        return ""
    labels = host.split(".")
    if len(labels) < 3:
        return ""
    return ".".join(labels[-2:])


def _is_same_probe_scope_lite(base_url: str, derived_url: str) -> bool:
    # 派生地址与播放列表是否同 host 或同（近似）注册域
    base_host = (urllib.parse.urlsplit(base_url).hostname or "").lower()
    derived_host = (urllib.parse.urlsplit(derived_url).hostname or "").lower()
    if not base_host or not derived_host:
        return False
    if base_host == derived_host:
        return True
    base_domain = _registrable_domain_lite(base_host)
    return bool(base_domain) and base_domain == _registrable_domain_lite(derived_host)


def _headers_for_derived_hop_lite(base_url: str, derived_url: str, headers: dict[str, str]) -> dict[str, str]:
    # 派生跳的 Cookie 裁决（主线 _headers_for_derived_hop 同判据）：与播放列表同 host/注册域
    # 才沿用原头；跨域只剥 Cookie、继续探测（凭据外泄面已消除，指纹头保留）。跨域即整体跳过
    # 会把「列表 200、分片 404 判假绿」能力废掉，故剥离而非跳过。
    if _is_same_probe_scope_lite(base_url, derived_url):
        return dict(headers)
    debug(f"流地址校验: {strip_query(derived_url)} - 派生地址与播放列表不同域，剥离 Cookie 后探测")
    return {name: value for name, value in headers.items() if name.lower() != "cookie"}


def _pick_master_variant_lite(text: str, base_url: str) -> str | None:
    # 从 master playlist 取带宽最高的变体 URL（主线 _pick_master_variant 同判据）：
    # 缺 BANDWIDTH 的变体记 -1（任何带带宽的变体都优先于它），全缺时按出现序取首个。
    variants: list[tuple[int, str]] = []
    pending_bw: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("#EXT-X-STREAM-INF"):
                m = re.search(r"BANDWIDTH=(\d+)", line)
                pending_bw = int(m.group(1)) if m else None
            continue
        variants.append((pending_bw if pending_bw is not None else -1, urllib.parse.urljoin(base_url, line)))
        pending_bw = None
    if not variants:
        return None
    best_bw = max(bw for bw, _ in variants)
    return next(u for bw, u in variants if bw == best_bw)


# 自检模式标记（2026-10-21）：selftest() 的承诺是「纯离线，绝不发真实请求」，而它的
# 保守放行分支（请求异常 → 维持「列表可达」）正好把这个承诺**吃进肚子里**——真发一次请求、
# 真失败、然后打印 PASS，自检于是对「有没有换绑假实现」完全失明。自检期间置 True，
# 让这类「保守兜底」在自检里变成显式 FAIL；生产路径恒为 False，保守语义逐字不变。
_SELFTEST_ACTIVE = False


def _probe_hls_segment_lite(url: str, headers: dict[str, str], proxy: str | None) -> bool:
    # （主线分片级探测回灌）：「播放列表 200」≠ 可录制——CDN 动态合成的
    # 列表恒 200 但分片可能 404（2026-09-13 斗鱼 hw 事故形态：ffmpeg 逐分片失败、零字节
    # 产出）。列表 200 后再探一层：master playlist 跟随带宽最高变体（最多两层，覆盖
    # 变体→子列表嵌套）→ 取末行分片（最新，避开滚出窗口的旧分片误杀）→ Range bytes=0-0
    # GET 探测。判定原则与主线 _probe_hls_segment 一致（保守优先，不误杀可用源）：
    #   分片明确 4xx/5xx → 列表假绿、判不可达（回退下一候选）；
    #   解析不出分片（空列表/非分片行/取不到变体/请求异常）→ 维持「列表可达」交 ffmpeg 定夺；
    #   派生地址（变体/分片）先过 _untrusted_stream_target_reason 闸，不通过判**不可达**——
    #   SR-01 同判据：内网/不合规目标面前维持可达就等于把它经播放列表正文交给 ffmpeg，
    #   本副本逐跳复检 handler 拦不住「正文内嵌地址」（那不是 HTTP 重定向）。
    try:
        resp = http_request(url, headers=dict(headers), timeout=_PROBE_TIMEOUT, proxy=proxy)
    except Exception:
        if _SELFTEST_ACTIVE:
            # 自检期间这里的异常**只有一种解释**——selftest 没有把 http_request
            # 换绑成假实现，于是这条用例真的对 cdn.example 发了网络请求（违反文件头的离线契约），
            # 旧写法把它当「列表 GET 失败、保守维持可达」返回 True，离线环境下自检照样打印 PASS，
            # 是典型的假绿。自检模式下显式判失败，让「没换绑」当场变红；生产路径不受影响。
            return False
        return True  # 列表 GET 失败（HEAD/Range-GET 已通过）——不据此推翻，交由 ffmpeg
    if resp.status != 200:
        return True
    text = resp.text or ""
    media_url = url
    seg_url = ""
    for _ in range(2):
        if "#EXT-X-STREAM-INF" not in text:
            break
        variant = _pick_master_variant_lite(text, media_url)
        if not variant:
            return True  # 只有标签行、取不到变体 URL——保守维持列表可达
        if _untrusted_stream_target_reason(variant) is not None:
            warn(f"流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {strip_query(variant)}")
            return False
        try:
            sub = http_request(variant, headers=_headers_for_derived_hop_lite(url, variant, headers), proxy=proxy)
        except Exception:
            return True  # 子列表取不到——保守，不下分片结论
        if sub.status != 200:
            return True
        media_url = variant
        text = sub.text or ""
    media_lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    if not media_lines:
        return True  # 空列表（直播刚结束/未推流）——无分片可探，维持列表可达
    seg_line = media_lines[-1]
    is_media = seg_line.endswith((".ts", ".mp4", ".m4s")) or any(
        ext + "?" in seg_line for ext in (".ts", ".mp4", ".m4s")
    )
    if not is_media:
        return True  # 非标准分片行（加密/自定义格式）——保守放行
    seg_url = urllib.parse.urljoin(media_url, seg_line)
    if _untrusted_stream_target_reason(seg_url) is not None:
        warn(f"流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {strip_query(seg_url)}")
        return False
    try:
        seg = http_probe(
            seg_url,
            method="GET",
            headers={**_headers_for_derived_hop_lite(url, seg_url, headers), "Range": "bytes=0-0"},
            timeout=_PROBE_TIMEOUT,
            proxy=proxy,
        )
    except Exception:
        return True  # 分片探测异常——保守维持列表可达
    if seg.status in (200, 206):
        return True
    if 400 <= seg.status < 600:
        # 分片「不存在/被拒」是确定性信号：列表可达但不可录制，判假绿回退下一候选
        debug(f"流地址校验: {strip_query(url)} - 播放列表 200 但分片探测得 {seg.status}，判列表假绿")
        return False
    return True  # 3xx 及其它非常规状态——保守，不据此推翻列表结论


def _confirm_get_ok(
    url: str, headers: dict[str, str], head_status: int, proxy: str | None, platform: str, last_resort: bool
) -> bool:
    # GET 复核：先原样重试一次再定罪(区分偶发限流与稳定拒绝)。
    # 流式只读状态码不读 body(urllib 用 Range GET 近似，只读 1 字节)。
    # 语义对齐原工程：非 401/403 的状态(含 404/405)不推翻 HEAD 结论；
    # 网络异常在 attempt 0 按「重试一次再定罪」隔开后重试，两次均异常才维持 HEAD 结论。
    # 但异常**必须记日志**——静默吞异常是原工程明确禁止的。
    reject: int | None = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
            with _build_opener(proxy).open(req, timeout=_PROBE_TIMEOUT) as r:
                st = int(r.status)
                if st not in (401, 403):
                    if attempt:
                        debug(f"流地址校验: {strip_query(url)} - 复核重试通过({st})，先前拒绝为偶发")
                    return True
                reject = st
                _mark_probe_reject(url, platform)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                reject = e.code
                _mark_probe_reject(url, platform)
            else:
                warn(f"流地址校验: {strip_query(url)} - GET 复核得 {e.code}(非拒绝类)，不推翻 HEAD 结论")
                return True
        except Exception as e:
            warn(f"流地址校验: {strip_query(url)} - GET 复核异常(attempt {attempt}, {type(e).__name__}: {e})")
            if attempt == 0:
                time.sleep(_recheck_delay())
                continue
            return True
        if attempt == 0:
            time.sleep(_recheck_delay())
    if last_resort:
        warn(
            f"流地址校验: {strip_query(url)} - HEAD={head_status} 但 GET 复核两次 {reject}；"
            "已无备选源，仍交由 ffmpeg 尝试(探针与 ffmpeg 指纹不同)"
        )
        return True
    warn(f"流地址校验失败: {strip_query(url)} - HEAD={head_status} 通过但 GET 复核两次 {reject}(CDN 稳定拒绝 GET)")
    return False


def validate_stream_url(
    url: str, proxy: str | None = None, platform: str = "", cookies: str = "", last_resort: bool = False
) -> bool:
    # 校验流地址是否可用于录制。返回 True 表示可用。
    # 策略(继承原工程踩坑结论)：
    #   1. m3u8：HEAD 非 2xx 时降级 Range GET 探测(CDN 常对 HEAD 回 405/404 而 GET 可拉流)；
    #      Range-GET 401/403 先隔 _GET_RECHECK_INTERVAL 原样重试一次再定罪(偶发限流救回)；
    #   2. flv/record_url：HEAD 通过后必须 GET 复核，杜绝 HEAD=200/GET=403 假绿；
    #   3. 末位候选(last_resort)稳定拒绝时仅告警放行，交由 ffmpeg 定夺；
    #   4. 虎牙(退避白名单)线路在退避窗口内跳过全部探针：非末位回退、末位零探针放行。
    # 协议/目标违规的候选不做探针、也不吃 last_resort 放行——「末位候选仅告警放行」
    # 的对象是 CDN 拒绝类误杀，不是本地文件/内网/云元数据目标。
    _target_reason = _untrusted_stream_target_reason(url)
    if _target_reason is not None:
        warn(f"流地址校验拒绝(不可信目标): {strip_query(url)} - {_target_reason}")
        return False
    headers = record_headers(platform, cookies)
    if _probe_in_backoff(url, platform):
        if last_resort:
            warn(f"流地址校验: {strip_query(url)} - CDN 探针退避中，跳过探针直接交由 ffmpeg 拉流")
            return True
        warn(f"流地址校验: {strip_query(url)} - CDN 探针退避中，跳过本轮探针、回退下一候选")
        return False
    _throttle_probe(url)
    # 容器判定一律先看小写形态：本文件三处 .m3u8 判定(此处 + build_ffmpeg_cmd / run_ffmpeg
    # 的两处命令构造)必须同口径。大写 .M3U8 若落进「非 m3u8」分支就会走 content-type 启发式
    # + _confirm_get_ok，而 m3u8 在多家 CDN 上 HEAD 恒回 4xx → 正好命中「探针误杀可用源」
    # (非末位候选被直接拒，整轮回退或放弃录制)，并连带漏掉 -reconnect_at_eof 的移除、
    # 复现 HLS 挂起事故。主程序侧 main.py::_validate_stream_url / src/stream_select.py /
    # src/async_http.py 同样 lower。
    url_lower = url.lower()
    try:
        # 状态码与 content-type 必须取自同一次 HEAD(单次探针，省连接预算)。
        # 旧版在此后另发一次无代理的 HEAD 取 content-type，既是双倍探针又与代理配置不一致。
        head = http_probe(url, method="HEAD", headers=headers, timeout=_PROBE_TIMEOUT, proxy=proxy)
        status = head.status
        ctype = head.content_type()
        if status in (401, 403):
            _mark_probe_reject(url, platform)

        if ".m3u8" in url_lower:
            if status == 200 or any(k in ctype for k in _STREAM_MEDIA_TYPES):
                # 列表 200 不再直接判可达——补分片级探测，拦「列表 200 但分片 404」
                # 的假绿候选（斗鱼 hw 事故整改回灌）
                return _probe_hls_segment_lite(url, headers, proxy)
            # HEAD 不可靠 → Range GET 探测(200/206 判可达)，401/403 重试一次再定罪
            last_gs = status
            for attempt in range(2):
                gs = http_probe(
                    url, method="GET", headers={**headers, "Range": "bytes=0-0"}, timeout=_PROBE_TIMEOUT, proxy=proxy
                )
                last_gs = gs.status
                if gs.status in (200, 206):
                    if attempt:
                        debug(f"流地址校验: {strip_query(url)} - Range-GET 重试通过({gs.status})，先前拒绝为偶发")
                    return _probe_hls_segment_lite(url, headers, proxy)
                if gs.status not in (401, 403):
                    break  # 非探针误杀类拒绝(如 404)，不重试
                _mark_probe_reject(url, platform)
                if attempt == 0:
                    time.sleep(_recheck_delay())
            if last_resort:
                warn(
                    f"流地址校验: {strip_query(url)} - HEAD={status}, Range-GET={last_gs}；已无备选源，仍交由 ffmpeg 尝试"
                )
                return True
            warn(f"流地址校验失败: {strip_query(url)} - HEAD={status}, Range-GET={last_gs}")
            return False

        # 非 m3u8：content-type 启发式 → GET 复核
        if any(k in ctype for k in _STREAM_MEDIA_TYPES):
            return _confirm_get_ok(url, headers, status, proxy, platform, last_resort)
        if "text/html" in ctype or "application/json" in ctype:
            if last_resort:
                # 斗鱼 hw CDN 对探针 HEAD 回 405+text/html(禁 HEAD 方法)，ffmpeg 实际 GET 拉流正常；
                # 末位候选稳定拒绝也仅告警放行，避免 content-type 启发式误杀可用源
                warn(
                    f"流地址校验: {strip_query(url)} - status={status}, content-type={ctype}，末位候选仍交由 ffmpeg 尝试"
                )
                return True
            warn(f"流地址校验失败(非流媒体内容): {strip_query(url)} - status={status}, content-type={ctype}")
            return False
        if status == 200:
            return _confirm_get_ok(url, headers, status, proxy, platform, last_resort)
        if last_resort:
            warn(f"流地址校验: {strip_query(url)} - status={status}，末位候选仍交由 ffmpeg 尝试")
            return True
        warn(f"流地址校验失败: {strip_query(url)} - status={status}, content-type={ctype}")
        return False
    except Exception as e:
        # Windows 下 socket.timeout 的 str() 为空 → 必须带异常类型
        warn(f"流地址校验异常(判定不可达): {strip_query(url)} - {type(e).__name__}: {e}")
        return False


def _h265_copy_format_supported_standalone(record_format: str) -> bool:
    # 判定「视频保存格式」的容器能否直拷(-c copy) HEVC（回灌主线
    # _h265_copy_format_supported 同判据）：TS(mpegts)/MKV(matroska)/MP4 三个 muxer 均支持
    # 写 HEVC；FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展，仓库口径不支持）与未识别取值不支持
    # （保守默认）。standalone 无 main 热更新全局，格式由调用方从 Settings 传入。
    return (record_format or "").strip().upper() in ("TS", "MKV", "MP4")


def select_source_url(stream: StreamInfo, proxy: str | None = None, record_format: str = "") -> str | None:
    # 从解析结果中挑选本轮实际录制地址。
    # 顺序：默认 HLS 优先(斗鱼等平台游客态 FLV 长连接约 70 秒会被掐断)，
    # 虎牙为 FLV 优先(实测其 HLS 三条线路冷启动探针假绿)。
    # 全部不可用时返回 None 并留日志(绝不静默跳过)。
    hls = list(stream.m3u8_urls)
    flv = list(stream.flv_urls)
    rec = stream.record_url
    if not (hls or flv or rec):
        warn(f"解析结果无任何流地址(m3u8/flv/record_url 均为空)，本轮放弃: {stream.anchor_name or '(未知主播)'}")
        return None

    # 虎牙 FLV-first(实测结论)，其余平台 HLS-first
    flv_first = stream.platform == "虎牙直播"
    seq: list[str] = (flv + hls) if flv_first else (hls + flv)
    # h265 候选按保存格式放行——TS/MKV/MP4 可直拷 HEVC，保留参与探针；
    # FLV/未识别取值仍无条件剔除(大小写不敏感)。原实现无条件剔除，mp4/ts 输出下
    # 白白丢弃 h265-only 房间的可用源。
    if _h265_copy_format_supported_standalone(record_format):
        if rec:
            seq.append(rec)
    else:
        seq = [u for u in seq if "h265" not in u.lower()]
        if rec and "h265" not in rec.lower():
            seq.append(rec)
    # 不可信候选(协议不在白名单/指向本机/内网/云元数据)先丢弃再探针——
    # 绝不交给探针与 ffmpeg。逐条留日志(带 strip_query 后的地址)保证「候选为何没录」可归因。
    trusted: list[str] = []
    for cand in seq:
        reason = _untrusted_stream_target_reason(cand)
        if reason is not None:
            warn(f"丢弃不可信流地址候选({reason}): {strip_query(cand)}")
            continue
        trusted.append(cand)
    seq = trusted

    for idx, cand in enumerate(seq):
        last = idx == len(seq) - 1
        if validate_stream_url(cand, proxy=proxy, platform=stream.platform, cookies=stream.cookies, last_resort=last):
            return cand
    return None


# ===== 7. FFmpeg 录制 =====


# 包内 ffmpeg 是否优先于系统 PATH 上那份 —— 与 `src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir()`
# 是**刻意维护的孪生副本**（本文件按设计不 import src/，可独立单文件分发；同 src/scheduler.py 的
# 副本先例：改判据必须两处同改，且两边注释互相点名）。
# 判据与主程序逐条一致，任一不成立即维持「包内优先」的既有顺序：
#   darwin ∧ arm64 ∧ 包内目录存在 ∧ 注入前 PATH 上另有 ffmpeg ∧ 那份 realpath 不在包内目录里。
# 为什么 Apple Silicon 要让位：full 包/仓库自带的 macOS ffmpeg 是 evermeet 的 **x86_64** 静态构建
#   （上游不发布 arm64 产物），无条件优先会让已装原生 ffmpeg 的用户白付 Rosetta 转译开销。
# 为什么不复用主程序那份日志/i18n：本文件不依赖 src/，且 find_ffmpeg 只在启动时调一次，
#   这里用一行 print 就够，不为一条日志引入 i18n 依赖。
def should_prepend_bundled_ffmpeg_dir(bundled_dir: str, current_path: str) -> bool:
    # 平台门控一律用 sys.platform 字面量（mypy 跨平台门禁要求）。非 darwin 恒 True = 行为逐字不变。
    if sys.platform != "darwin":
        return True
    # 解释器自身被 Rosetta 转译时 machine() 报 x86_64 → 判据不成立、维持包内优先：
    # 这是刻意选择的漏判方向（架构信息不可信时不改用系统那份）。
    if platform.machine().lower() != "arm64":
        return True
    if not os.path.isdir(bundled_dir):
        return True
    # 必须用调用方传进来的 PATH 快照做探测（与主程序同一约束）；自读环境变量在
    # 「用户已把包内目录写进 PATH」时会探到同一份，让位判断失去意义。
    system_ffmpeg = shutil.which("ffmpeg", path=current_path) if current_path else None
    if not system_ffmpeg:
        return True
    candidate_real = os.path.realpath(system_ffmpeg)
    bundle_real = os.path.realpath(bundled_dir)
    # 自我遮蔽（探到的其实就是包内那份）→ 不让位，否则日志会承诺「原生 arm64」而实际仍是 x86_64。
    if candidate_real == bundle_real or candidate_real.startswith(bundle_real + os.sep):
        return True
    return False


def find_ffmpeg(explicit: str = "") -> str:
    # 定位 ffmpeg：显式路径 > 脚本同级 ffmpeg/<exe> > 仓库根目录 ffmpeg/<exe> > PATH。
    # 找不到返回空串。注意必须校验**可执行文件**而非 ffmpeg/ 目录本身——目录存在
    # 但里面没有 ffmpeg.exe 时，把目录路径交给子进程只会得到难以理解的
    # FileNotFoundError。本文件位于 scripts/ 下，仓库自带的 ffmpeg/ 在其上一级；
    # 脚本被单独拷出使用时仍优先找其同目录 ffmpeg/。
    # 唯一例外：Apple Silicon 上系统已装原生 ffmpeg 时让位（见
    # should_prepend_bundled_ffmpeg_dir，与主程序 main.py 的 PATH 策略同源）。
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    if explicit:
        return explicit if os.path.isfile(explicit) else ""
    here = Path(__file__).resolve().parent
    for local in (here / "ffmpeg" / exe, here.parent / "ffmpeg" / exe):
        if local.is_file():
            if should_prepend_bundled_ffmpeg_dir(str(local.parent), os.environ.get("PATH", "")):
                return str(local)
            system = shutil.which("ffmpeg", path=os.environ.get("PATH", "")) or ""
            print(f"[ffmpeg] Apple Silicon：让位于系统原生构建 {system}（包内为 x86_64 转译构建）")
            return system or str(local)
    return shutil.which("ffmpeg") or ""


# 容器格式 → ffmpeg muxer 名；录制文件格式仅支持这三种。输出容器的取值**只能查这张表**，
# 不得在任何分支写 -f 的裸字面量：原工程 2026-09-04 的 P0 就是 TS 分支误写 ipod、
# M4A 分支误写 mpegts(两值互换)——H.264 灌进错封装器不报错、exit 0，只把 MP4 内容
# 写进 .ts 文件名(魔数 ftyp 而非 0x47)，属静默损坏，只有语义断言拦得住(本副本无分段
# 录制，故 -f 承担 main.py 里 -segment_format 的同一职责；键须与输出扩展名严格对应)。
_RECORD_FORMATS: dict[str, str] = {"flv": "flv", "mp4": "mp4", "ts": "mpegts"}
# 单次录制时长不限制时 -t 的等效上限(10 年)：使命令形状固定(便于与 Popen 内联
# 参数列表逐一配对)，直播流自然结束(主播下线)时 ffmpeg 照常正常退出，语义不变。
_RECORD_UNLIMITED_CAP = "315360000"


def build_ffmpeg_cmd(
    ffmpeg_bin: str, url: str, out_path: str, platform: str, cookies: str, duration: float, fmt: str = "flv"
) -> list[str]:
    # 构造 ffmpeg 命令(标志集与原工程 main.py 一致)，用于日志展示与自检断言。
    # -headers 必须用 \r\n 结尾(HTTP 头规范)，且必须与校验探针的 UA/Referer/Cookie
    # 完全一致(统一经 record_headers 构造)，否则出现「校验 200、ffmpeg 403」。
    # 本命令在本副本有**两个定义点**：此处的规范列表 + run_ffmpeg 内 Popen 前的内联列表
    # (写入门禁要求参数内联在调用点、不得传拼接变量)。两处必须逐字对齐，改任一处即同步
    # 另一处；下面的 m3u8 移除 -reconnect_at_eof 守卫同样两处都要有
    # (回归锁 tests/test_ffmpeg_reconnect_args.py 扫描本文件、按定义点逐一断言守卫存在)。
    headers = record_headers(platform, cookies)
    header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    duration_cap = str(int(duration)) if duration > 0 else _RECORD_UNLIMITED_CAP
    # 下面三个 -reconnect* 是**输入级(HTTP 协议)选项**：必须全部位于 -i 之前，且每个选项
    # 紧跟自己的字面量取值。两条各对应一次真实事故：
    #   · 写在 -i 之后会被划入输出组，而 ffmpeg 对已全局注册的选项名不报错——实测静默接受、
    #     退出码 0、输入侧从未应用，重连完全失效却没有任何可见症状(2026-09-10)；
    #   · 缺值时 ffmpeg 把下一个选项名当取值，报「Unable to parse "reconnect_streamed"
    #     option value "-reconnect_at_eof" as boolean」→ Invalid argument，输入未打开即
    #     退出 -22，真实录制 100% 复现(2026-09-11)。
    # 故新增输入级选项时同样按「-i 之前 + 成对字面量」写，不得用裸下标插入。
    # 回归锁 tests/test_ffmpeg_reconnect_args.py(两不变量 × main.py 与本文件双定义点)。
    cmd = [
        ffmpeg_bin,
        "-y",
        "-loglevel",
        "error",
        "-headers",
        header_str,
        "-rw_timeout",
        "15000000",
        # 输入协议白名单：与主程序 main.py:_build_ffmpeg_input_args 逐字同值。
        # 本项目输入恒为 http(s)/rtmp 直播流，file 从不使用；放行 file 意味着「URL 可控」时
        # ffmpeg 可读写本地文件(平台 API 候选属不可信输入面)。crypto 需保留(HLS 分片解密)。
        # 两处命令定义点(本列表 + run_ffmpeg 内联列表)必须同值同位(-i 之前)。
        "-protocol_whitelist",
        "rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy",
        "-reconnect_delay_max",
        "60",
        "-reconnect_streamed",
        "1",
        "-reconnect_at_eof",
        "1",
        "-i",
        url,
        "-c",
        "copy",
        "-f",
        _RECORD_FORMATS.get(fmt, "flv"),
        "-t",
        duration_cap,
        out_path,
    ]
    # HLS(m3u8) 输入禁用 -reconnect_at_eof（与原工程 main.py 同规则）：hls demuxer 依赖
    # 播放列表读到 EOF 才完成解析、开始拉取媒体段，开启该选项后 http 层在「列表下载完」处
    # 无限重连（-report 实测特征：连续「Will reconnect at <size> in N second(s),
    # error=End of file」，1/3/7/15/31/60s 指数退避、永不放弃；-reconnect_delay_max 60 只限
    # 单次延迟上限）——媒体段一个都拉不到、视频零字节产出、进程永不退出，且 -loglevel error
    # 下零输出零报错，形态即「只录到字幕没录到视频」。
    # FLV 输入保留该选项：CDN 掐断长连接时在 EOF 处重连续写同一文件(斗鱼游客态 FLV
    # ~70s 被掐的既有缓解手段)。del 只按字面量标志对删除，不引入动态拼接。
    # 判定必须走小写形态(大写 .M3U8 会漏判并复现上述挂起)。
    if ".m3u8" in url.lower():
        _eof_idx = cmd.index("-reconnect_at_eof")
        del cmd[_eof_idx : _eof_idx + 2]
    return cmd


def _mask_ffmpeg_cmd_for_log(cmd: list[str]) -> str:
    # 2026-09-30：写进 logs/ffmpeg.log 的命令原文必须脱敏。完整命令含 -headers 实参
    # (record_headers 会把用户配置的平台 Cookie 拼进去——抖音/B站登录态会话凭据)与 -i 的
    # 带 token 流地址(wsSecret/anti_code/auth 等)；该日志 append 无轮转，凭据明文落盘等于
    # 泄漏(与主程序「写入日志前必须脱敏」红线同源，主程序从不落盘完整命令)。只保留参数
    # 形状供排障：-headers 值换占位符，-i 值走 strip_query(保留路径、去 query)。
    masked: list[str] = []
    i = 0
    while i < len(cmd):
        token = cmd[i]
        if i + 1 < len(cmd) and token == "-headers":
            masked += [token, f"<headers:{len(cmd[i + 1])} chars>"]
            i += 2
            continue
        if i + 1 < len(cmd) and token == "-i":
            masked += [token, strip_query(cmd[i + 1])]
            i += 2
            continue
        masked.append(token)
        i += 1
    return " ".join(masked)


# 运行中的 ffmpeg 进程登记表：Ctrl+C / 停止时统一终止，避免孤儿 ffmpeg
# 继续拉流占用 CDN 连接预算与磁盘
_ACTIVE_FFMPEG: set[subprocess.Popen] = set()
_ACTIVE_FFMPEG_LOCK = threading.Lock()
# 单进程三级终止的总预算（秒）：「写 q 后等优雅退出 → terminate 后等 → kill 后等」三段按剩余时间分摊，
# 见 _stage_budget。取值 10s 而非主线的 30s：主线 _terminate_ffmpeg_process 由后台清理线程**一次一个**
# 地处理进程，本副本却在 Ctrl+C / 停止流程里**串行**处理全部在录进程，30s × N 会把退出挂死。
# [历史注] 旧形态只有一个 _TERMINATE_GRACE_SECONDS = 3.0，且只挂在 terminate() 之后、q 之后不留等待
# 窗口（Windows 下 terminate() 即 TerminateProcess 硬杀，那 3 秒对「读 q 并收尾」毫无作用，
# 优雅退出那一级因此从未生效，停止录制后的 mp4/mov 一律缺 moov）。
_TERMINATE_BUDGET_SECONDS = 10.0
# 单段等待的最小秒数：proc.wait(0) 会立即抛 TimeoutExpired，等于整段跳过优雅退出——正在写的
# mp4/mov 因此丢 moov。与 src/ffmpeg_proc.py::_MIN_STAGE_WAIT_SECONDS 同值（物理孪生，改一侧须同步）。
_MIN_STAGE_WAIT_SECONDS = 1.0


def _stage_budget(deadline: float, stages_left: int) -> float:
    # 按剩余预算给下一段等待分配秒数（与 src/ffmpeg_proc.py::_stage_budget 同形的**物理孪生**：
    # 本副本按设计不 import src/，故只能各存一份，判据改动必须两处同改）。
    remaining = deadline - time.monotonic()
    return max(_MIN_STAGE_WAIT_SECONDS, remaining / max(stages_left, 1))


def terminate_all_ffmpeg() -> int:
    # 原实现只 proc.terminate() 就返回——SIGTERM 后 ffmpeg 仍需
    # 时间 flush 缓冲并写 mp4 的 moov box，调用方（Ctrl+C / 停止流程）紧接着退出或
    # 删除句柄，会把输出文件截断成「不可播放」（moov 缺失，播放器报 invalid data）。
    # 改为 terminate → 宽限 wait(3s) → 仍存活才 kill 的两级终止。
    # （回灌主线三级终止链）：在最前增加「写 q 到 stdin + 关闭」一级——
    # Windows 下 terminate() 即 TerminateProcess 硬杀，上方 3 秒宽限对它毫无作用，
    # 只有 ffmpeg 自己读到 q/SIGINT 才会走收尾流程补写 moov。主线实现见
    # src/ffmpeg_proc.py::_terminate_ffmpeg_process（写 q / SIGINT → terminate → kill）。
    # run_ffmpeg 的 Popen 须配 stdin=PIPE 才有管道可写（同批修改）。
    with _ACTIVE_FFMPEG_LOCK:
        procs = list(_ACTIVE_FFMPEG)
    killed = 0
    for proc in procs:
        try:
            if proc.poll() is not None:
                continue  # 已自然退出，无需终止
            try:
                if proc.stdin:
                    try:
                        proc.stdin.write(b"q")
                        proc.stdin.flush()
                    except Exception:
                        # 吞没即正确（与主线同判据）：ffmpeg 已卡死且不读 stdin 时，管道缓冲
                        # 满会让 write/flush 永久阻塞，唯一出路是下面的 terminate → kill 兜底
                        pass
                    finally:
                        # 部分构建要读到 EOF 才处理 'q'，写完（无论成败）必须关闭
                        try:
                            proc.stdin.close()
                        except Exception:
                            pass
            except Exception:
                pass
            # 2026-10-21 ：写完 q 必须先给优雅退出留一段**有界等待**，再进入 terminate/kill。
            # 旧实现紧跟着无条件 terminate()：Windows 下那是 TerminateProcess 硬杀，ffmpeg 还没
            # 读到 q 就被带走，上面那一整级（含其注释承诺的「补写 moov」）实际从未生效，
            # 停止录制后的 mp4/mov 缺 moov、不可播放。三段预算与主线 _terminate_ffmpeg_process 同形。
            stage_deadline = time.monotonic() + _TERMINATE_BUDGET_SECONDS
            try:
                proc.wait(timeout=_stage_budget(stage_deadline, 3))
            except subprocess.TimeoutExpired:
                pass  # 该级没等到 = 进入下一级，不是错误（与主线同口径，重抛会放弃仍可杀的进程）
            except Exception as e:
                debug(f"ffmpeg 优雅退出等待异常(继续下一级): {type(e).__name__}: {e}")
            if proc.poll() is not None:
                killed += 1
                continue  # 优雅级已退出：moov 已由 ffmpeg 自己补写，无需硬杀
            try:
                proc.terminate()
                proc.wait(timeout=_stage_budget(stage_deadline, 2))
            except subprocess.TimeoutExpired:
                # 宽限期未退出（卡在写盘/网络读）：强制 kill 并再回收一次，避免僵尸
                proc.kill()
                try:
                    proc.wait(timeout=_stage_budget(stage_deadline, 1))
                except subprocess.TimeoutExpired:
                    debug(f"ffmpeg kill 后仍未退出: pid={proc.pid}")
            killed += 1
        except Exception as e:
            debug(f"ffmpeg 终止失败: {type(e).__name__}: {e}")
    return killed


def run_ffmpeg(
    ffmpeg_bin: str, url: str, out_path: str, platform: str, cookies: str, duration: float, fmt: str, log_path: str
) -> tuple[int, str]:
    # 执行 ffmpeg：stderr 落盘(便于定位 403/超时)，返回 (返回码, 错误摘要)。
    # 返回码语义：0 成功；非 0 失败。调用方须按 rc 回传调度器成功/失败，
    # 禁止无条件记成功(否则按 host 熔断永不触发，坏线路会被无限重撞)。
    # 安全说明：下方 Popen 用**调用点内联字面量列表**(写入门禁要求，不得传拼接变量)且显式
    # shell=False——不经 shell 解释，URL/文件名中的元字符(&、|、> 等)不可能被注入命令
    # (文件名已在 clean_name 清洗)。该列表即 build_ffmpeg_cmd 规范列表之外的第二处定义点，
    # 两处必须逐字对齐、改任一处即同步另一处，m3u8 移除 -reconnect_at_eof 的守卫同样两处都要。
    cmd_log = _mask_ffmpeg_cmd_for_log(build_ffmpeg_cmd(ffmpeg_bin, url, out_path, platform, cookies, duration, fmt))
    headers = record_headers(platform, cookies)
    header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    duration_cap = str(int(duration)) if duration > 0 else _RECORD_UNLIMITED_CAP
    try:
        _rotate_log_if_needed(log_path)
        logf = open(log_path, "a", encoding="utf-8", errors="replace")
    except OSError as e:
        return 1, f"ffmpeg 日志文件打开失败: {type(e).__name__}: {e} | path={log_path}"
    try:
        logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{cmd_log}\n")
        logf.flush()
        # 形状与 build_ffmpeg_cmd 逐一对应(约束见该函数与本函数的注释)：列表仍为纯字面量
        # 构造(无拼接变量)，下方的 del 只按字面量标志对删除，不引入注入面、门禁语义不变。
        proc_args: list[str] = [
            ffmpeg_bin,
            "-y",
            "-loglevel",
            "error",
            "-headers",
            header_str,
            "-rw_timeout",
            "15000000",
            # 输入协议白名单：与 build_ffmpeg_cmd 逐字同值，理由见该函数注释
            "-protocol_whitelist",
            "rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy",
            "-reconnect_delay_max",
            "60",
            "-reconnect_streamed",
            "1",
            "-reconnect_at_eof",
            "1",
            "-i",
            url,
            "-c",
            "copy",
            "-f",
            _RECORD_FORMATS.get(fmt, "flv"),
            "-t",
            duration_cap,
            out_path,
        ]
        # 第二处守卫：m3u8 输入同样必须删掉 -reconnect_at_eof 参数对并按小写判定
        # (规则与后果详述见 build_ffmpeg_cmd)——这里漏删即等于真实录制路径仍会挂起。
        if ".m3u8" in url.lower():
            _eof_idx = proc_args.index("-reconnect_at_eof")
            del proc_args[_eof_idx : _eof_idx + 2]
        proc = subprocess.Popen(
            proc_args,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=logf,
            # （2026-10-19 审查修复）：stdin 必须是二进制管道——本文件 terminate_all_ffmpeg
            # 按主线 src/ffmpeg_proc.py::_terminate_ffmpeg_process 口径写 b"q"，而 text=True 时
            # stdin 是 TextIOWrapper、写 bytes 必抛 TypeError 并被写 q 处的 except 吞没，
            # 「写 q 优雅收尾补 moov」一级恒失效，Windows 下退化为 TerminateProcess 硬杀。
            # 该 Popen 的 stdout=DEVNULL、stderr=文件句柄，副本内无 communicate()/读 stdout 的点，
            # 去掉 text 形态无其它消费方受影响。回归锁：tests/test_regression_standalone.py
            # :TestStandaloneGracefulQuitChain。
            shell=False,
        )
    except FileNotFoundError:
        return 127, f"ffmpeg 可执行文件不存在: {ffmpeg_bin}"
    except OSError as e:
        return 1, f"ffmpeg 启动失败: {type(e).__name__}: {e}"
    finally:
        logf.close()
    with _ACTIVE_FFMPEG_LOCK:
        _ACTIVE_FFMPEG.add(proc)
    try:
        return proc.wait(), ""
    finally:
        with _ACTIVE_FFMPEG_LOCK:
            _ACTIVE_FFMPEG.discard(proc)


# ===== 8. 配置 =====

# 布尔配置值解析（回灌主线 src/config_bool.py 统一口径）：旧前缀判断
# (`startswith("是")` / `not startswith("否")`) 在 true/false、1/0、yes/no、on/off 取值下
# 静默反向生效（主线 2026-09-17 P0 同款：8 项配置漂移、9 个海外平台 100% 无法录制）。
# token 集与主线逐字同源（比较前 strip + lower）；空值与未识别值返回 default，调用方传
# 该配置项的文档默认值（DEFAULT_CONFIG 同值）。孪生约定：改本表须与主线 config_bool.py
# 同批同步（AGENTS「主线修复必须核对 standalone 孪生副本」）。
_TRUE_TOKENS = frozenset({"是", "true", "t", "yes", "y", "on", "1"})
_FALSE_TOKENS = frozenset({"否", "false", "f", "no", "n", "off", "0"})


def parse_config_bool(raw: str | bool | int | None, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    token = str(raw).strip().lower()
    if token in _TRUE_TOKENS:
        return True
    if token in _FALSE_TOKENS:
        return False
    return default


DEFAULT_CONFIG: dict[str, str] = {
    "是否启用代理": "否",
    "代理地址": "",
    "视频保存路径": "downloads",
    "循环时间(秒)": "120",
    "最大同时录制数(0为不限制)": "0",
    "同一时间访问网络的线程数": "8",
    "是否启用日志文件": "是",
    "录制文件格式": "flv",
    "单次录制时长(秒,0为不限制)": "0",
    "是否去除表情": "是",
    "抖音cookie": "",
    "虎牙cookie": "",
    "B站cookie": "",
    "斗鱼cookie": "",
}


@dataclass
class Settings:
    proxy: str = ""
    save_dir: str = "downloads"
    loop_interval: float = 120.0
    record_limit: int = 0
    network_limit: int = 8
    duration: float = 0.0
    remove_emoji: bool = True
    record_format: str = "flv"
    log_file: bool = True
    ffmpeg_bin: str = ""
    cookies: dict[str, str] = field(default_factory=dict)


def load_settings(config_path: str) -> Settings:
    # 读取 config.ini，缺失项用 DEFAULT_CONFIG 兜底(保证开箱即用)。
    # interpolation=None 必须显式关闭：configparser 默认把 % 视为插值起始符，
    # 而 Cookie 值(URL 编码)几乎必然含 %，默认配置下读取直接抛 InterpolationSyntaxError。
    st = Settings()
    parser = configparser.ConfigParser(interpolation=None)
    read_ok = False
    if config_path and os.path.isfile(config_path):
        try:
            # utf-8-sig 兼容 Windows 记事本写入的 BOM
            parser.read(config_path, encoding="utf-8-sig")
            read_ok = True
        except (configparser.Error, UnicodeDecodeError) as e:
            # UnicodeDecodeError 也要兜住——ANSI/GBK 编码的 config.ini(旧版记事本默认)
            # 在 utf-8-sig 解码期直接抛，此前会启动即崩。降级为默认配置并告警，与 load_urls
            # 的 errors="replace" 容错口径对齐。
            warn(f"配置文件解析失败，使用默认配置: {type(e).__name__}: {e}")

    def get(key: str) -> str:
        if read_ok and parser.has_section("录制设置") and parser.has_option("录制设置", key):
            return parser.get("录制设置", key).strip()
        return DEFAULT_CONFIG.get(key, "")

    if parse_config_bool(get("是否启用代理"), default=False):
        st.proxy = get("代理地址").strip()
        # 启用代理但地址为空时，下游 `proxy or None` 会把空串判成 falsy → 静默直连：
        # 用户以为流量走了代理（往往正是为了隐藏出口 IP / 绕过地域限制），实际全部裸连，
        # 既不达预期又无任何提示。故显式告警要求补填，而不是悄悄降级为直连。
        if not st.proxy:
            warn("「是否启用代理 = 是」但「代理地址」为空，将按直连处理；请填写代理地址或关闭代理开关")
    st.save_dir = get("视频保存路径") or "downloads"
    st.loop_interval = _safe_float(get("循环时间(秒)"), 120.0)
    if st.loop_interval < 5.0:
        # 过小的轮询间隔退化为对平台接口的毫秒级连击(风控风险)，钳回默认值
        warn(f"循环时间(秒)={st.loop_interval:g} 过小，已钳制为 120")
        st.loop_interval = 120.0
    st.record_limit = _safe_int(get("最大同时录制数(0为不限制)"), 0)
    st.network_limit = max(1, _safe_int(get("同一时间访问网络的线程数"), 8))
    st.duration = _safe_float(get("单次录制时长(秒,0为不限制)"), 0.0)
    st.remove_emoji = parse_config_bool(get("是否去除表情"), default=True)
    fmt = get("录制文件格式").lower()
    if fmt not in _RECORD_FORMATS:
        if fmt:
            warn(f"录制文件格式={fmt!r} 不受支持(仅 flv/mp4/ts)，已回退 flv")
        fmt = "flv"
    st.record_format = fmt
    st.log_file = parse_config_bool(get("是否启用日志文件"), default=True)
    st.cookies = {
        "抖音直播": get("抖音cookie"),
        "虎牙直播": get("虎牙cookie"),
        "B站直播": get("B站cookie"),
        "斗鱼直播": get("斗鱼cookie"),
    }
    return st


def _safe_int(text: str, default: int) -> int:
    try:
        return int(float(str(text).strip()))
    except TypeError, ValueError:
        return default


def _safe_float(text: str, default: float) -> float:
    try:
        return float(str(text).strip())
    except TypeError, ValueError:
        return default


def load_urls(url_config_path: str) -> list[str]:
    # 读取 URL_config.ini：跳过空行与 # 注释行；支持 'url' 与 'url,画质,备注' 两种写法。
    urls: list[str] = []
    if not url_config_path or not os.path.isfile(url_config_path):
        return urls
    with open(url_config_path, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            urls.append(line.split(",")[0].strip())
    return urls


# ===== 9. 录制任务 =====


class Recorder:
    # 录制器：**每个房间一个独立线程**(对齐原工程线程模型)，各自周期性
    # 解析 → 选源 → 录制。录制(ffmpeg)期间只占用录制信号量，不占网络信号量，
    # 因此多房间可同时录制、网络探测按「同一时间访问网络的线程数」限流。
    def __init__(self, settings: Settings, dry_run: bool = False, once: bool = False) -> None:
        global _LOG_FILE_PATH, _MAIN_LOOP_INTERVAL
        self.st = settings
        self.dry_run = dry_run
        self.once = once
        self.scheduler = Scheduler(network_limit=settings.network_limit, record_limit=settings.record_limit)
        self._stop = threading.Event()
        # 探针退避窗口必须 ≥ 一个主循环周期(+余量)，否则退避闭环恒不成立(原工程硬约定)
        _MAIN_LOOP_INTERVAL = max(1.0, settings.loop_interval)
        # logs/ 目录无条件创建：ffmpeg.log 是诊断录制失败的核心出口，与可选的
        # 控制台镜像日志(是否启用日志文件)无关
        os.makedirs("logs", exist_ok=True)
        if settings.log_file:
            _LOG_FILE_PATH = os.path.join("logs", "standalone.log")
        os.makedirs(self.st.save_dir, exist_ok=True)

    def stop(self) -> None:
        self._stop.set()
        killed = terminate_all_ffmpeg()
        if killed:
            warn(f"已终止 {killed} 个运行中的 ffmpeg 进程")

    def record_once(self, url: str) -> bool:
        # 对单个 URL 执行一轮：解析 → 选源 → 录制。返回是否成功开始(或完成)录制。
        host = host_of(url)
        # 熔断预检：该 host 处于熔断态时跳过本轮，避免坏线路被无限重撞
        if not self.scheduler.allow(host):
            warn(f"{host} 处于熔断状态，本轮跳过: {url}")
            return False

        with self.scheduler.network_semaphore:
            # Cookie 须在解析前按平台取(解析请求本身就要带 Cookie)
            stream = dispatch(url, proxy=self.st.proxy or None, cookies=self.st.cookies.get(platform_of(url), ""))

        if stream.error:
            warn(f"{stream.error} | {url}")
            self.scheduler.record_failure(host)
            return False
        if not stream.is_live:
            info(f"未开播: {stream.anchor_name or url}")
            return False

        # 解析成功即上报成功样本(与解析失败分支对称，原工程约定)：
        # 否则探针房间进入长时间录制期间，half-open 的同 host 其余房间被饿死
        self.scheduler.record_success(host)

        platform = stream.platform
        cookies = self.st.cookies.get(platform, "") or ""
        stream.cookies = cookies

        with self.scheduler.network_semaphore:
            src = select_source_url(stream, proxy=self.st.proxy or None, record_format=self.st.record_format)

        if not src:
            # 解析已成功，线路校验失败不记熔断样本(CDN 线路健康度由 ffmpeg 退出码采样)；
            # 但必须告警留痕，绝不静默跳过
            error(f"未找到可用流地址，本轮放弃: {stream.anchor_name or url}")
            return False

        if self.dry_run:
            info(f"[dry-run] 平台={platform} 主播={stream.anchor_name} 标题={stream.title}")
            info(f"[dry-run] 选中流地址: {strip_query(src)}")
            return True

        record_started = time.monotonic()
        with self.scheduler.recording_semaphore:
            rc, err = self._do_record(stream, src)

        # 结果必须回传调度器：成功/失败分别计，禁止无条件记成功
        if rc == 0:
            self.scheduler.record_success(host)
            # 录制成功的线路立即撤销探针退避(HLS 的退避不受影响——
            # HLS 仍不可用时应继续走 FLV，这正是期望语义)
            clear_probe_reject(src, platform)
            info(f"录制结束(正常): {stream.anchor_name} | rc=0")
            return True
        self.scheduler.record_failure(host)
        # 快速失败(≤20s，主线 _FFMPEG_FAST_FAIL_SECONDS 同值)记探针退避——
        # 「探针通过 → ffmpeg 打开即被拒」的探针假绿在探针侧永远观测不到(httpx/urllib 与
        # ffmpeg 指纹不同)，不标记就是逐轮 parse+probe+ffmpeg 失败死循环；白名单(仅虎牙)
        # 由 _mark_probe_reject 自行判定。慢速失败只记失败样本不记退避。
        if time.monotonic() - record_started <= 20.0:
            _mark_probe_reject(src, platform)
        error(f"录制失败: rc={rc} {err} | {stream.anchor_name or url} | 详见 logs/ffmpeg.log")
        return False

    def _do_record(self, stream: StreamInfo, src: str) -> tuple[int, str]:
        # 构造输出路径并执行 ffmpeg。
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        anchor = clean_name(stream.anchor_name, self.st.remove_emoji)
        title = clean_name(stream.title, self.st.remove_emoji)[:60]
        name = f"{anchor}_{title}_{ts}".strip("_")
        out_dir = Path(self.st.save_dir) / clean_name(stream.platform or "unknown", False)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"{name}.{self.st.record_format}")

        info(f"开始录制: {stream.anchor_name} -> {out_path}")
        return run_ffmpeg(
            self.st.ffmpeg_bin,
            src,
            out_path,
            stream.platform,
            stream.cookies,
            self.st.duration,
            self.st.record_format,
            os.path.join("logs", "ffmpeg.log"),
        )

    def _room_loop(self, url: str) -> None:
        # 单房间监控线程：--once 时只跑一轮；否则按 loop_interval 持续监控。
        # 等待统一走 _stop.wait()：停止信号随时打断等待，线程秒级退出。
        round_no = 0
        host = host_of(url)
        while not self._stop.is_set():
            round_no += 1
            info(f"[{host}] ===== 第 {round_no} 轮 =====")
            try:
                self.record_once(url)
            except Exception as e:
                # 单房间单轮异常不得中断该房间的后续监控
                error(f"房间处理异常: {type(e).__name__}: {e} | {url}")
            if self.once:
                break
            if self._stop.wait(self.st.loop_interval):
                break
        debug(f"房间线程退出: {host}")

    def loop(self, urls: list[str]) -> None:
        # 主入口：为每个 URL 启动一个房间线程；--once 时等全部线程跑完一轮，
        # 常驻模式下主线程挂起等待停止信号(Ctrl+C)。
        info(
            f"共 {len(urls)} 个直播间，间隔 {self.st.loop_interval:g}s，"
            f"dry_run={self.dry_run}, once={self.once}, 格式={self.st.record_format}"
        )
        threads: list[threading.Thread] = []
        for idx, url in enumerate(urls):
            t = threading.Thread(target=self._room_loop, args=(url,), name=f"room-{idx}-{host_of(url)}", daemon=True)
            t.start()
            threads.append(t)
        if self.once:
            for t in threads:
                t.join()
        else:
            while not self._stop.is_set():
                if not any(t.is_alive() for t in threads):
                    break
                self._stop.wait(1.0)
        # 唤醒并收尾所有房间线程
        self._stop.set()
        info("已退出主循环")


# ===== 10. 自检(--selftest)：纯离线，不依赖网络 =====


def selftest() -> int:
    # 离线自检：验证不依赖网络的全部核心逻辑。返回 0 表示全部通过。
    # 注意：绝不能在本函数里调用 dispatch(具体平台 URL)/resolve_* 等真函数——
    # 那会发出真实网络请求(1.0.0 版缺陷：号称离线自检却对四个平台各发一次请求)。
    passed, failed = 0, 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print(f"  [PASS] {name}")
        else:
            failed += 1
            print(f"  [FAIL] {name} {detail}")

    print("=== 自检开始 ===")

    # --- 文件名清洗 ---
    check(
        "clean_name 去非法字符", clean_name('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i", clean_name('a/b:c*d?e"f<g>h|i')
    )
    check("clean_name 替换 &", "&" not in clean_name("A&B 直播"))
    check("clean_name 空值兜底", clean_name("") == FALLBACK_NAME)
    check("clean_name 去 emoji", clean_name("主播🎉开播") == "主播_开播", clean_name("主播🎉开播"))
    check("clean_name 全角括号", clean_name("（测试）") == "(测试)", clean_name("（测试）"))

    # --- host 提取 ---
    check("host_of 常规", host_of("https://live.douyin.com/123?a=1") == "live.douyin.com")
    check("host_of 带端口", host_of("http://1.2.3.4:8080/x.flv") == "1.2.3.4:8080")
    check("host_of 异常兜底", host_of("") == "unknown")

    # --- 安全取值 ---
    check("dig 命中", dig({"a": {"b": [{"c": 1}]}}, "a", "b", 0, "c") == 1)
    check("dig 缺失兜底", dig({"a": {}}, "a", "b", "c", default="NA") == "NA")
    check("dig 列表越界兜底", dig({"a": []}, "a", 5, default="NA") == "NA")

    # --- 协议 MD5(RFC 1321 实现按公开标准向量锁定) ---
    check("md5 空串", _md5_hex(b"") == "d41d8cd98f00b204e9800998ecf8427e")
    check("md5 abc", _md5_hex(b"abc") == "900150983cd24fb0d6963f7d28e17f72")
    check("md5 fox", _md5_hex(b"The quick brown fox jumps over the lazy dog") == "9e107d9d372bb6826bd81d3542a419d6")
    check("md5 长输入(跨块)", _md5_hex(b"a" * 128) == "e510683b3f5ffe4093d021808bc6ff70")

    # --- 平台判定(必须在解析前就能拿到, 否则 Cookie 取不到) ---
    check("platform_of 抖音", platform_of("https://live.douyin.com/1") == "抖音直播")
    check("platform_of 虎牙", platform_of("https://www.huya.com/1") == "虎牙直播")
    check("platform_of B站", platform_of("https://live.bilibili.com/1") == "B站直播")
    check("platform_of 斗鱼", platform_of("https://www.douyu.com/1") == "斗鱼直播")
    check("platform_of 未知", platform_of("https://example.com") == "")

    # --- 分派路由(注入假解析器验证，绝不发真实网络请求) ---
    saved_rules = PLATFORM_RULES[:]
    try:
        PLATFORM_RULES[:] = [
            (
                r"example\.com",
                "测试平台",
                lambda url, proxy=None, cookies="": StreamInfo(platform="测试平台", anchor_name="ok"),
            )
        ]
        routed = dispatch("https://example.com/x")
        check("分派路由命中注入解析器", routed.anchor_name == "ok" and routed.platform == "测试平台", routed.error)
    finally:
        PLATFORM_RULES[:] = saved_rules
    check("分派 未知平台有 error", bool(dispatch("https://example.org/x").error))

    # --- 录制请求头(校验与录制两端的唯一构造点) ---
    check("B站带 Referer", record_headers("B站直播", "").get("Referer") == _BILI_REFERER)
    check("虎牙无 Referer(反向校验)", "Referer" not in record_headers("虎牙直播", ""))
    check("虎牙桌面 UA", record_headers("虎牙直播", "").get("User-Agent") == DESKTOP_UA)
    check("抖音移动 UA", record_headers("抖音直播", "").get("User-Agent") == MOBILE_UA)
    check("cookie 注入", record_headers("抖音直播", "ttwid=1").get("Cookie") == "ttwid=1")

    # --- 虎牙地址拼接 ---
    u = _huya_build("http://a.com/live", "room", "flv", "wsSecret=1")
    check("虎牙 flv 拼接", u == "http://a.com/live/room.flv?wsSecret=1", u)
    check("虎牙空 anticode 不加问号", _huya_build("http://a.com/live", "r", "flv", "") == "http://a.com/live/r.flv")

    # --- 虎牙 HTML 正则(两种页面结构都要能解析) ---
    # 形态 A：真实页面 —— 非贪婪匹配在 ,"iWebDefaultBitRate" 前截断，根对象少一个 '}'
    html_a = (
        'stream: {"data":[{"gameStreamInfoList":[{"sFlvUrl":"http://x","sStreamName":"n",'
        '"sFlvUrlSuffix":"flv","sFlvAntiCode":"a=1"}]}],"vMultiStreamInfo":[],"iWebDefaultBitRate":0}'
    )
    # 形态 B：结构变动后已完整闭合
    html_b = (
        'stream: {"data":[{"gameStreamInfoList":[{"sFlvUrl":"http://x","sStreamName":"n",'
        '"sFlvUrlSuffix":"flv","sFlvAntiCode":"a=1"}]}]},"iWebDefaultBitRate":0}'
    )
    for label, html in (("A(缺右括号)", html_a), ("B(已闭合)", html_b)):
        m = _HUYA_STREAM_RE.search(html)
        check(f"虎牙 stream 正则命中 {label}", m is not None)
        if m:
            try:
                d = _loads_stream_json(m.group(1))
                check(
                    f"虎牙 stream JSON 可解析 {label}",
                    dig(d, "data", 0, "gameStreamInfoList", 0, "sFlvUrl") == "http://x",
                    str(d),
                )
            except json.JSONDecodeError as e:
                check(f"虎牙 stream JSON 可解析 {label}", False, str(e))

    # --- 斗鱼签名(纯 MD5 链，本地即可验证) ---
    check("斗鱼签名 enc_time=0", _douyu_compute_auth("", "k", 0, "rs") == _md5_hex("krs"))
    check("斗鱼签名 enc_time=1", _douyu_compute_auth("r", "k", 1, "") == _md5_hex(_md5_hex("rk") + "k"))
    check(
        "斗鱼签名 enc_time=2",
        _douyu_compute_auth("r", "k", 2, "") == _md5_hex(_md5_hex(_md5_hex("rk") + "k") + "k"),
    )

    # --- 探针退避(白名单仅虎牙；键去 query；成功清除) ---
    _probe_reject_until.clear()
    _mark_probe_reject("http://cdna.example/live/4001.flv?wsSecret=aaa", "虎牙直播")
    check("退避命中且跨 token", _probe_in_backoff("http://cdna.example/live/4001.flv?wsSecret=bbb", "虎牙直播") is True)
    check("退避不跨平台", _probe_in_backoff("http://cdna.example/live/4001.flv", "斗鱼直播") is False)
    clear_probe_reject("http://cdna.example/live/4001.flv?wsSecret=ccc", "虎牙直播")
    check("录制成功清除退避", _probe_in_backoff("http://cdna.example/live/4001.flv", "虎牙直播") is False)

    # --- 数字解析兜底 ---
    check("_safe_int 非法值", _safe_int("abc", 7) == 7)
    check("_safe_int 浮点串", _safe_int("3.9", 0) == 3)
    check("_safe_float 空值", _safe_float("", 5.0) == 5.0)

    # --- 信号量 ---
    sem = ResizableSemaphore(1)
    sem.acquire()
    check("信号量耗尽后非阻塞失败", sem.acquire(timeout=0.05) is False)
    sem.release()
    check("信号量释放后可获取", sem.acquire(timeout=0.05) is True)
    sem.release()
    sem.set_value(3)
    check("信号量调容", sem.value == 3)

    # --- 熔断器 ---
    br = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.2)
    for _ in range(10):
        br.record(False)
    check("连续失败后熔断", br.state == "open", br.state)
    check("熔断期间拒绝", br.allow() is False)
    time.sleep(0.25)
    check("冷却后放行探针", br.allow() is True)
    br.record(True)
    check("探针成功后恢复", br.state == "closed", br.state)

    # --- 熔断器 half-open 探针归属门控(该回灌项，失效后果见 PlatformBreaker 类注释) ---
    # 两条用例分别覆盖两种非探针回报：另一线程收尾的在途普通轮次、租约重授予后的陈旧探针。
    br_gate = PlatformBreaker("probe-gate", window=10, fail_rate=0.5, cooldown=0.0)
    for _ in range(8):
        br_gate.record(False)
    check("归属门控前置：已熔断", br_gate.state == "open", br_gate.state)
    check("归属门控前置：放行探针", br_gate.allow() is True)
    check("归属门控前置：half-open", br_gate.state == "half-open", br_gate.state)
    # 另一线程的普通轮次回报(在途请求收尾)：样本照常入窗口，但不得驱动状态迁移
    outsider = threading.Thread(target=lambda: br_gate.record(True))
    outsider.start()
    outsider.join()
    check("非探针线程回报不得关熔断", br_gate.state == "half-open", br_gate.state)
    br_gate.record(True)  # 探针持有线程(本线程)回报 → 才允许闭环
    check("探针持有线程回报后恢复 closed", br_gate.state == "closed", br_gate.state)

    # 租约重授予后的**陈旧探针**：持有线程已被换掉，其回报同样不得关熔断。
    # 直接把 _granted_at 往前推(不真等 60s)，避免自检用例挂在 sleeps 上。
    br_lease = PlatformBreaker("probe-lease", window=10, fail_rate=0.5, cooldown=0.0)
    for _ in range(8):
        br_lease.record(False)
    br_lease.allow()  # 本线程 = 第 1 代探针持有者
    br_lease._granted_at -= PlatformBreaker.LEASE_SECONDS + 1.0
    regrant: dict[str, object] = {}
    new_holder = threading.Thread(target=lambda: regrant.__setitem__("granted", br_lease.allow()))
    new_holder.start()
    new_holder.join()
    check("租约到期后重授予探针", regrant.get("granted") is True and br_lease.state == "half-open", str(regrant))
    stale_probe = threading.Thread(target=lambda: br_lease.record(True))  # 第 1 代的陈旧回报
    stale_probe.start()
    stale_probe.join()
    check("陈旧探针回报不得关熔断", br_lease.state == "half-open", br_lease.state)

    # --- 流地址校验的容器判定大小写(失效形态见 validate_stream_url 注释) ---
    # 此处注入假探针(绝不发真实请求)，两种大小写必须同结果：Range-GET=206 救回即证明走的是
    # HLS 分支。HEAD 用 405 —— 非 401/403，避免污染退避表(_mark_probe_reject 只认那两个码)。
    saved_probe = http_probe
    saved_throttle = _throttle_probe
    # HLS 分支最终调用的是 http_request（_probe_hls_segment_lite 取播放列表正文），
    # 只换绑 http_probe / _throttle_probe 时那一步会**真的**向 cdn.example 发一次请求——
    # 违反本函数的离线契约，且异常被 except 吞掉后仍打印 PASS（假绿）。现一并换绑，并把
    # 「假实现收到过调用」作为「确实走了 HLS 分支且没走真实网络」的凭据。
    saved_request = http_request
    hls_requests: list[str] = []
    try:
        _probe_reject_until.clear()
        globals()["_SELFTEST_ACTIVE"] = True

        def _fake_probe(
            url: str,
            *,
            method: str = "HEAD",
            headers: dict[str, str] | None = None,
            timeout: float = 8.0,
            proxy: str | None = None,
        ) -> ProbeResult:
            if method == "HEAD":
                return ProbeResult(405, {"content-type": "text/html"})
            return ProbeResult(206, {"content-type": "application/vnd.apple.mpegurl"})

        def _no_throttle(url: str) -> None:
            return None

        def _fake_request(
            url: str,
            *,
            headers: dict[str, str] | None = None,
            data: bytes | None = None,
            timeout: float = 15.0,
            proxy: str | None = None,
        ) -> HttpResponse:
            # 返回一份**带分片行**的媒体播放列表：让 _probe_hls_segment_lite 走到「末行分片
            # Range-GET」那一步（分片探测由 _fake_probe 应答 206），而不是在「空列表」处保守早退
            # ——后者即使 http_request 完全没被换绑也给出同样的 True，等于断言自我掩盖。
            hls_requests.append(url)
            return HttpResponse(200, {"content-type": "application/vnd.apple.mpegurl"}, "#EXTINF:-1\n0001.ts\n")

        # 经 globals() 换绑而非 global 声明：selftest() 前半段已按普通名读取过这两个名字，
        # 同作用域内「先用后声明 global」是语法错误。validate_stream_url 在调用点查全局名，
        # 故换绑即刻生效。
        globals()["http_probe"] = _fake_probe
        globals()["_throttle_probe"] = _no_throttle
        globals()["http_request"] = _fake_request
        check(
            "小写 .m3u8 走 HLS 分支(Range-GET 救回)",
            validate_stream_url("https://cdn.example/live/a/b.m3u8", platform="斗鱼直播") is True,
        )
        check(
            "大写 .M3U8 同走 HLS 分支(大小写不敏感)",
            validate_stream_url("https://cdn.example/live/a/b.M3U8", platform="斗鱼直播") is True,
        )
        # 离线契约的凭据：两次 HLS 校验都由假实现应答（URL 逐条对上），真实网络一次都没走到。
        check(
            "HLS 自检全程走假 http_request(离线契约)",
            hls_requests == ["https://cdn.example/live/a/b.m3u8", "https://cdn.example/live/a/b.M3U8"],
            str(hls_requests),
        )
    finally:
        globals()["http_probe"] = saved_probe
        globals()["_throttle_probe"] = saved_throttle
        globals()["http_request"] = saved_request
        globals()["_SELFTEST_ACTIVE"] = False
        _probe_reject_until.clear()

    # --- ffmpeg 命令构造：自检只驱动 build_ffmpeg_cmd 这一处规范列表 ---
    # run_ffmpeg 的内联列表不被自检执行(会真起进程)，两处的一致性由
    # tests/test_ffmpeg_reconnect_args.py 的 AST 扫描把守，改动时以该锁为准。
    cmd = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.flv", "B站直播", "sid=1", 0)
    blob = next(a for a in cmd if "\r\n" in a)
    check("ffmpeg headers 含 Referer", ("Referer: " + _BILI_REFERER) in blob)
    check("ffmpeg headers 含桌面 UA", DESKTOP_UA in blob)
    check("ffmpeg headers \\r\\n 结尾", blob.endswith("\r\n"))
    check("ffmpeg 含 -loglevel error", "-loglevel" in cmd and cmd[cmd.index("-loglevel") + 1] == "error")
    check("ffmpeg 含 reconnect 参数", "-reconnect_delay_max" in cmd)
    check("ffmpeg 输出路径在末尾", cmd[-1] == "out.flv")
    check("ffmpeg 不限时用上限 cap", "-t" in cmd and cmd[cmd.index("-t") + 1] == _RECORD_UNLIMITED_CAP)
    cmd2 = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.flv", "抖音直播", "", 30)
    check("ffmpeg 限时加 -t 30", cmd2[cmd2.index("-t") + 1] == "30")
    cmd3 = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.mp4", "抖音直播", "", 0, "mp4")
    check("mp4 格式参数", cmd3[cmd3.index("-f") + 1] == "mp4")
    cmd4 = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.ts", "抖音直播", "", 0, "ts")
    check("ts 格式参数", cmd4[cmd4.index("-f") + 1] == "mpegts")

    # --- 选源：空结果必须返回 None 而非抛异常 ---
    check("空解析结果返回 None", select_source_url(StreamInfo()) is None)

    # --- 配置兜底 ---
    st = load_settings("__not_exist__.ini")
    check("配置缺失用默认值", st.loop_interval == 120.0 and st.network_limit == 8 and st.record_format == "flv")
    check("配置缺失 cookie 键齐全", set(st.cookies) == {"抖音直播", "虎牙直播", "B站直播", "斗鱼直播"})

    print(f"=== 自检结束: 通过 {passed}, 失败 {failed} ===")
    return 0 if failed == 0 else 1


# ===== 11. 运行步骤说明 =====

RUN_STEPS = """
环境准备与运行步骤 (douyin_live_recorder_standalone.py v@@VERSION@@)
================================================================================
【1. 依赖安装】
  本文件**零第三方依赖**，只需 Python 标准库。但语法基线是 **Python >= 3.14**
  (使用了 PEP 758 无括号多异常等 3.14 语法)，3.13 及以下会直接 SyntaxError：
    python -V                       # 必须显示 3.14+
  不需要 Node.js(斗鱼签名是纯 MD5 链式算法，经 RFC 1321 纯 Python 实现直接完成)。

【2. FFmpeg 安装(录制必需，--dry-run 可免)】
  Windows: 下载 https://www.gyan.dev/ffmpeg/builds/ 的 essentials 版，
           解压后把 ffmpeg.exe 放到仓库根目录的 ffmpeg/ 目录(本文件位于 scripts/ 下，
           脚本会自动向上查找)，或加入 PATH。
  Linux:   sudo apt install -y ffmpeg
  macOS:   brew install ffmpeg
  验证：   ffmpeg -version

【3. 配置文件要求】
  可选。缺失时自动使用内置默认配置(见 DEFAULT_CONFIG)。
  config.ini(按运行时工作目录解析，或 --config 指定；本仓库自带 config/config.ini)：
      [录制设置]
      是否启用代理 = 否
      代理地址 = 127.0.0.1:10808
      视频保存路径 = downloads
      循环时间(秒) = 120
      最大同时录制数(0为不限制) = 0
      同一时间访问网络的线程数 = 8
      单次录制时长(秒,0为不限制) = 0
      是否去除表情 = 是
      是否启用日志文件 = 是
      录制文件格式 = flv
      抖音cookie =
      虎牙cookie =
      B站cookie =
      斗鱼cookie =
  URL_config.ini：每行一个直播间地址，# 开头为注释(支持 url,画质,备注 写法)。
  注意：代理只在「是否启用代理 = 是」时生效；本工具不会读取系统/环境变量代理。
  建议：抖音接口风控较严格，强烈建议配置抖音 cookie(浏览器登录后 F12 复制)。

【4. 运行前置条件】
  - 网络可达目标平台(境外平台需配置代理)；
  - 目标直播间处于开播状态，否则只打印"未开播"；
  - 输出目录有写权限(默认 downloads/)；
  - 支持平台：抖音 / 虎牙 / B站 / 斗鱼(其余平台请用原工程完整版)。

【5. 常用命令】(本文件位于 scripts/ 下，以下命令在仓库根目录执行)
  python scripts/douyin_live_recorder_standalone.py --selftest          # 离线自检
  python scripts/douyin_live_recorder_standalone.py --help-steps        # 打印本说明
  python scripts/douyin_live_recorder_standalone.py --url "https://live.douyin.com/xxxx" --dry-run
  python scripts/douyin_live_recorder_standalone.py --url "https://www.huya.com/660002" --once --duration 30
  python scripts/douyin_live_recorder_standalone.py --config config.ini --url-config URL_config.ini

【6. 结果验证方式】
  1) --selftest 全部 [PASS]，退出码 0；
  2) --dry-run 能打印 平台/主播/标题 与选中的流地址(只解析与校验，不录制)；
  3) --once --duration 30 后 downloads/<平台>/ 下出现 30 秒左右的录制文件，
     logs/ffmpeg.log 无 403/超时堆栈；
  4) 常驻模式下 Ctrl+C 退出，无残留 ffmpeg 进程(任务管理器/ps 验证)。
""".replace("@@VERSION@@", VERSION)


# ===== 12. 入口 =====


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DouyinLiveRecorder 单文件整合版(抖音/虎牙/B站/斗鱼)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--url", action="append", default=[], help="直播间地址，可重复传入")
    parser.add_argument("--config", default="", help="config.ini 路径")
    parser.add_argument("--url-config", default="", help="URL_config.ini 路径")
    parser.add_argument("--save-dir", default="", help="覆盖配置中的视频保存路径")
    parser.add_argument("--proxy", default="", help="覆盖配置中的代理地址")
    parser.add_argument("--ffmpeg", default="", help="ffmpeg 可执行文件路径")
    parser.add_argument("--duration", type=float, default=-1, help="单次录制时长(秒)，-1 表示跟随配置")
    parser.add_argument("--dry-run", action="store_true", help="只解析与校验，不实际录制")
    parser.add_argument("--once", action="store_true", help="只跑一轮即退出(适合验证)")
    parser.add_argument("--loop", action="store_true", help="持续监控(默认行为，显式声明用)")
    parser.add_argument("--selftest", action="store_true", help="离线自检，验证核心逻辑")
    parser.add_argument("--help-steps", action="store_true", help="打印环境准备与运行步骤")
    args = parser.parse_args(argv)

    if args.help_steps:
        print(RUN_STEPS)
        return 0
    if args.selftest:
        return selftest()

    settings = load_settings(args.config or "config.ini")
    if args.save_dir:
        settings.save_dir = args.save_dir
    if args.proxy:
        settings.proxy = args.proxy
    if args.duration >= 0:
        settings.duration = args.duration
    settings.ffmpeg_bin = find_ffmpeg(args.ffmpeg)

    urls = list(args.url)
    if not urls:
        urls = load_urls(args.url_config or "URL_config.ini")
    urls = [u for u in urls if u]
    if not urls:
        parser.error("未提供直播间地址：请用 --url 传入，或提供 URL_config.ini")

    if not settings.ffmpeg_bin and not args.dry_run:
        parser.error("未找到 ffmpeg：请安装后加入 PATH，或用 --ffmpeg 指定路径(也可加 --dry-run 只做解析验证)")

    recorder = Recorder(settings, dry_run=args.dry_run, once=args.once)
    try:
        recorder.loop(urls)
    except KeyboardInterrupt:
        info("收到 Ctrl+C，正在退出...")
    finally:
        # 停止所有房间线程并终止仍在运行的 ffmpeg(避免孤儿进程继续拉流)
        recorder.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
