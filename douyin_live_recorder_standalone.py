#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DouyinLiveRecorder 单文件整合版 (standalone)
================================================================================
本文件从工作区 D:\\DouyinLiveRecorder-dev 的 42 个源模块(约 2.1 万行)中抽取并整合
核心录制主链路，合并为一个**开箱即用**的单文件脚本。

设计取舍
--------------------------------------------------------------------------------
* **零第三方依赖**：只使用 Python 标准库(urllib/re/subprocess/threading 等)，
  无需 pip install 任何包即可运行(录制本身仍需 ffmpeg 可执行文件)。
* **保留原工程的核心正确性约定**(这些是原工程踩坑后的结论，单文件版一律继承)：
  1. 校验探针与 ffmpeg 录制必须共用同一 UA / Referer / Cookie，
     否则出现「探针 200、ffmpeg 403」的假绿。
  2. m3u8 的 HEAD 常被 CDN 返回 4xx(405/404) 而 GET 可正常拉流，
     故 HEAD 非 2xx 时一律降级做 Range GET(bytes=0-0) 探测，200/206 视为可达。
  3. flv/record_url 在 HEAD 通过后须再做一次流式 GET 复核，
     杜绝「HEAD=200、GET=403」的假绿。
  4. 失败/成功必须回传调度器(按 host 熔断)，禁止无条件记为成功。
  5. Windows 下 socket.timeout 的 str() 为空，异常日志必须带 type(e).__name__。
  6. 文件名必须清洗 Windows 非法字符，并把 '&' 换为下划线(cmd 命令分隔符)。

支持的平台
--------------------------------------------------------------------------------
* 抖音 live.douyin.com            —— 完整支持(webcast room/web/enter)
* 虎牙 www.huya.com               —— 完整支持(HTML stream 解析 + 微信小程序兜底)
* B站 live.bilibili.com           —— 完整支持(room_init + playUrl)
* 斗鱼 www.douyu.com              —— 房间信息完整；**拉流地址需 JS 签名**，
                                     本文件内置 Node 签名通道：检测到 node 可执行文件
                                     时自动签名，否则明确跳过并提示，绝不静默失败。

使用
--------------------------------------------------------------------------------
  python douyin_live_recorder_standalone.py --selftest
  python douyin_live_recorder_standalone.py --url "https://live.douyin.com/123456" --dry-run
  python douyin_live_recorder_standalone.py --url "https://www.huya.com/660002" --once
  python douyin_live_recorder_standalone.py --config config --loop

依赖与前置条件见文件末尾 RUN_STEPS 常量(可用 --help-steps 打印)。
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, cast

# =============================================================================
# 0. 基础常量与运行环境
# =============================================================================

VERSION = "1.0.0-standalone"

# Windows 控制台默认 GBK，直接打印中文/emoji 会 UnicodeEncodeError；统一重配为 utf-8。
# 用 hasattr 守卫：被重定向到管道或 pythonw 下 stdout 可能为 None。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (ValueError, OSError):
            pass

# 桌面 Chrome UA：国内 CDN(虎牙/B站)会拒绝移动端 UA(403)，录制拉流必须用桌面 UA。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
# 移动端 UA：与 ffmpeg 录制命令默认 UA 保持一字不差(校验与录制两端必须一致)。
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
)
# 解析直播间页面时的兜底 UA
HTML_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0"

# Windows 文件名非法字符(原工程 rstr 的等价物)
ILLEGAL_CHARS_PATTERN = r'[\\/:*?"<>|\r\n\t]'
FALLBACK_NAME = "空白昵称"

_print_lock = threading.Lock()


def log(level: str, msg: str) -> None:
    """线程安全的日志输出。level: DEBUG/INFO/WARNING/ERROR。"""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with _print_lock:
        print(f"{ts} | {level:<7} | {msg}", flush=True)


def info(msg: str) -> None:
    log("INFO", msg)


def warn(msg: str) -> None:
    log("WARNING", msg)


def error(msg: str) -> None:
    log("ERROR", msg)


def debug(msg: str) -> None:
    log("DEBUG", msg)


# =============================================================================
# 1. HTTP 客户端(纯标准库)
# =============================================================================


@dataclass
class HttpResponse:
    """极简 HTTP 响应：状态码 / 响应头(小写键) / 文本。"""

    status: int
    headers: dict[str, str]
    text: str


def http_request(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 15.0,
    proxy: str | None = None,
) -> HttpResponse:
    """发起一次 HTTP 请求，返回 HttpResponse；失败时抛出 RuntimeError(带 URL 与异常类型)。

    注意(原工程踩坑)：Windows 下 socket.timeout 的 str() 为空字符串，
    异常信息必须携带 type(e).__name__ 与 url，否则日志只有一行无意义的空白。
    """
    req = urllib.request.Request(url, data=data, headers=headers or {})
    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
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
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return HttpResponse(e.code, {}, body)
    except Exception as e:
        raise RuntimeError(f"HTTP 请求失败: {type(e).__name__}: {e} | url={url}") from e


def http_status(
    url: str,
    *,
    method: str = "HEAD",
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
    proxy: str | None = None,
) -> int:
    """只取状态码(不读 body)。用于探针，避免下载直播流。"""
    req = urllib.request.Request(url, method=method, headers=headers or {})
    opener = urllib.request.build_opener()
    if proxy:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as e:
        return int(e.code)
    except Exception as e:
        raise RuntimeError(f"探针失败: {type(e).__name__}: {e} | url={url}") from e


# =============================================================================
# 2. 工具函数(文件名清洗 / JSON 安全取值 / host 提取)
# =============================================================================


def clean_name(text: str, remove_emoji: bool = True) -> str:
    """清洗为合法文件名：去非法字符、全角括号转半角、可选去 emoji、& 换下划线。

    '&' 必须替换：在 Windows cmd 中它是命令分隔符，会让 ffmpeg 命令行被截断。
    """
    name = re.sub(ILLEGAL_CHARS_PATTERN, "_", (text or "").strip()).strip("_")
    name = name.replace("（", "(").replace("）", ")")
    if remove_emoji:
        # 去 emoji / 其它非常用符号(保留 CJK、字母数字、常见标点)
        name = re.sub(r"[^\w\u4e00-\u9fff()（）\-_\. ]", "_", name)
    name = name.replace("&", "_")
    return name or FALLBACK_NAME


def host_of(url: str) -> str:
    """提取 URL 主机名作为熔断 key(小写、保留端口)；解析失败统一归 "unknown"。

    坏 URL 共享同一个 "unknown" 桶是刻意取舍：为坏地址细分只会产生大量
    无统计意义的零散熔断桶。
    """
    try:
        tail = url.split("://", 1)[-1]
        host = tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0].lower()
        return host or "unknown"
    except Exception:
        return "unknown"


def dig(obj: Any, *keys: Any, default: Any = None) -> Any:
    """安全地逐层取值(dict 用键、list 用下标)，任一层缺失即返回 default。

    平台接口字段层层嵌套且随时可能缺失，直接 obj["a"]["b"] 会在接口变更时
    抛出 KeyError 并中断整个监控循环；统一走 dig 可保证单点降级。
    """
    cur = obj
    for k in keys:
        try:
            if isinstance(k, int):
                cur = cur[k]
            else:
                cur = cur[k]
        except (KeyError, IndexError, TypeError, AttributeError):
            return default
    return cur if cur is not None else default


def _fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    data: bytes | None = None,
    timeout: float = 15.0,
    proxy: str | None = None,
) -> dict[str, Any]:
    """取回 JSON 并**校验 HTTP 状态码**。

    必须显式判状态码：代理/CDN 常以 4xx/5xx 返回一段 HTML 错误页，
    若不判状态码就 json.loads，会得到 JSONDecodeError 或"字段缺失"，
    把「网络/代理故障」误报成「主播未开播」，真实原因被彻底掩盖。
    """
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
    """取回 HTML 文本并校验状态码(理由同 _fetch_json)。"""
    resp = http_request(url, headers=headers, timeout=timeout, proxy=proxy)
    if resp.status >= 400:
        raise RuntimeError(f"HTTP {resp.status} | url={strip_query(url)}")
    return resp.text


def strip_query(url: str) -> str:
    """去掉 URL 的 query 部分(用于日志脱敏与退避键)。"""
    return url.split("?", 1)[0]


# =============================================================================
# 3. 并发调度中枢(整合自 src/scheduler.py)
# =============================================================================


class ResizableSemaphore:
    """可运行时调容的信号量(消除重建竞态)，支持上下文管理器协议。

    capacity 语义与 threading.Semaphore 一致(表示可用许可数)；
    set_value 可增可减：减少只降低上限(已持锁者不受影响)，增加时唤醒等待者。
    """

    def __init__(self, value: int) -> None:
        self._cond = threading.Condition()
        self._capacity = max(0, int(value))

    def __enter__(self) -> ResizableSemaphore:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()

    def acquire(self, timeout: float = -1) -> bool:
        with self._cond:
            endtime: float | None = None
            if timeout >= 0:
                endtime = time.monotonic() + timeout
            while self._capacity <= 0:
                if endtime is not None:
                    remaining = endtime - time.monotonic()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()
            self._capacity -= 1
            return True

    def release(self) -> None:
        with self._cond:
            self._capacity += 1
            self._cond.notify()

    def set_value(self, new_value: int) -> None:
        new_value = max(0, int(new_value))
        with self._cond:
            delta = new_value - self._capacity
            self._capacity = new_value
            if delta > 0:
                for _ in range(delta):
                    self._cond.notify()

    @property
    def value(self) -> int:
        with self._cond:
            return self._capacity


class PlatformBreaker:
    """按 key(host) 的熔断器：closed(放行) → open(熔断) → half-open(放一个探针)。

    探针带租约：授予后超过 lease 秒仍未上报样本(如主播未开播的等待轮)时
    重新授予，否则 _probing 永不复位 → 该 key 永久熔断直到进程重启。
    """

    LEASE_SECONDS = 60.0

    def __init__(self, name: str, window: int = 40, fail_rate: float = 0.5, cooldown: float = 45.0) -> None:
        self.name = name
        self._window = max(1, window)
        self._fail_rate = fail_rate
        self._cooldown = cooldown
        self._lock = threading.Lock()
        self._samples: list[int] = []
        self._fail_count = 0
        self._state = "closed"
        self._open_until = 0.0
        self._probing = False
        self._granted_at = 0.0

    def _push(self, failed: int) -> None:
        if len(self._samples) >= self._window:
            self._fail_count -= self._samples.pop(0)
        self._samples.append(failed)
        self._fail_count += failed

    def record(self, success: bool) -> None:
        with self._lock:
            self._push(0 if success else 1)
            if self._state == "closed":
                if len(self._samples) >= 8 and self._fail_count / len(self._samples) >= self._fail_rate:
                    self._state = "open"
                    self._open_until = time.monotonic() + self._cooldown
                    self._probing = False
            elif self._state == "half-open":
                if success:
                    self._state = "closed"
                    self._samples.clear()
                    self._fail_count = 0
                else:
                    self._state = "open"
                    self._open_until = time.monotonic() + self._cooldown
                self._probing = False

    def allow(self) -> bool:
        with self._lock:
            if self._state == "closed":
                return True
            now = time.monotonic()
            if self._state == "open":
                if now >= self._open_until and not self._probing:
                    self._probing = True
                    self._granted_at = now
                    self._state = "half-open"
                    return True
                return False
            if not self._probing:
                self._probing = True
                self._granted_at = now
                return True
            if now - self._granted_at >= self.LEASE_SECONDS:
                self._granted_at = now  # 租约超时：自愈，重新授予
                return True
            return False

    @property
    def state(self) -> str:
        with self._lock:
            return self._state


class Scheduler:
    """并发调度中枢：网络并发容量 + 录制并发上限 + 按 host 熔断。"""

    def __init__(self, network_limit: int = 8, record_limit: int = 0) -> None:
        self.network_semaphore = ResizableSemaphore(max(1, network_limit))
        # 录制并发：0 表示不限制(用一个大容量代替，避免每处判空)
        self.record_limit = max(0, record_limit)
        self.recording_semaphore = ResizableSemaphore(self.record_limit or 4096)
        self._lock = threading.Lock()
        self._breakers: dict[str, PlatformBreaker] = {}

    def set_record_limit(self, n: int) -> None:
        self.record_limit = max(0, int(n))
        self.recording_semaphore.set_value(self.record_limit or 4096)

    def _breaker(self, key: str) -> PlatformBreaker:
        with self._lock:
            b = self._breakers.get(key)
            if b is None:
                b = PlatformBreaker(key)
                self._breakers[key] = b
            return b

    def allow(self, key: str) -> bool:
        return self._breaker(key).allow()

    def record_success(self, key: str | None) -> None:
        """成功必须显式回传：否则失败率统计被稀释，熔断永不触发。"""
        if key:
            self._breaker(key).record(True)

    def record_failure(self, key: str | None) -> None:
        if key:
            self._breaker(key).record(False)

    def states(self) -> dict[str, str]:
        with self._lock:
            return {k: b.state for k, b in self._breakers.items()}


# =============================================================================
# 4. 平台解析(整合自 src/spider.py 对应平台分支)
# =============================================================================


@dataclass
class StreamInfo:
    """统一的解析结果。字段缺失时为空串/空列表，绝不抛异常。"""

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
    """抖音：webcast/room/web/enter 接口。

    接口接受数字房间号与抖音号两种 web_rid；live.douyin.com/<抖音号> 不会重定向，
    故直接取路径末段即可，不要写重定向解析逻辑。
    风控信号是 HTTP 200 + 空响应体(而非 4xx)，必须先判断 len(text)==0。
    """
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
        info_.error = "抖音接口返回空响应体(疑似风控)，建议配置 Cookie 后重试"
        return info_
    try:
        data = json.loads(resp.text)
    except json.JSONDecodeError as e:
        info_.error = f"抖音接口返回非 JSON: {type(e).__name__}: {e}"
        return info_

    room = dig(data, "data", "data", 0, default={}) or {}
    info_.anchor_name = str(dig(room, "anchor", "nickname", default="") or "")
    info_.title = str(dig(room, "title", default="") or "")
    status = dig(room, "status", default=0)
    stream_url = dig(room, "stream_url", default={}) or {}

    pull_map = dig(stream_url, "flv_pull_url", default={}) or {}
    if isinstance(pull_map, dict):
        for v in pull_map.values():
            if isinstance(v, str) and v:
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


def _huya_build(s_flv_url: str, s_stream_name: str, s_suffix: str, anti_code: str) -> str:
    """拼接虎牙流地址：base + '/' + streamName + '.' + suffix + '?' + antiCode。

    anti_code 为空时不追加 '?'，避免产生以问号结尾的畸形 URL。
    """
    base = f"{s_flv_url.rstrip('/')}/{s_stream_name}.{s_suffix}"
    return f"{base}?{anti_code}" if anti_code else base


def _loads_stream_json(raw: str) -> dict[str, Any]:
    """解析虎牙 stream 片段：兼容「少一个右括号」与「已完整」两种页面结构。

    正则非贪婪匹配到 ,"iWebDefaultBitRate" 前为止，真实页面常在此截断掉根对象的
    右花括号(需补一个 '}')；但页面结构变动时也可能已经闭合(补 '}' 会 Extra data)。
    故两种形态都尝试，任一成功即可，避免把结构差异升级为整轮解析失败。
    """
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
    """虎牙：解析 HTML 中的 stream 字段；失败时兜底微信小程序接口(cache.php)。"""
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

    # 兜底：微信小程序接口(房间号为纯数字时可用)
    room_id = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not room_id.isdigit():
        info_.error = f"{fetch_failed_reason}；未能解析 stream 数据，且房间号非纯数字，无法走兜底接口".strip("；")
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

# B站 CDN 对无 Referer 的请求返回 403(content-type 为空)，必须下发 Referer。
_BILI_REFERER = "https://live.bilibili.com/"


def resolve_bilibili(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    """B站：room_init 取真实 room_id → playUrl 取流地址。"""
    info_ = StreamInfo(platform="B站直播", cookies=cookies)
    room_id = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
    if not room_id.isdigit():
        info_.error = "B站房间号必须是纯数字"
        return info_
    headers = {"User-Agent": DESKTOP_UA, "Referer": _BILI_REFERER}
    if cookies:
        headers["Cookie"] = cookies
    try:
        init = _fetch_json(
            f"https://api.live.bilibili.com/room/v1/Room/room_init?id={room_id}",
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
        real_id = dig(init, "data", "room_id", default=room_id)
        uid = dig(init, "data", "uid", default="")
        play = _fetch_json(
            "https://api.live.bilibili.com/room/v1/Room/playUrl?"
            + urllib.parse.urlencode({"cid": real_id, "platform": "h5", "otype": "json", "quality": "0"}),
            headers=headers,
            timeout=15,
            proxy=proxy,
        )
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"B站接口失败: {type(e).__name__}: {e}"
        return info_

    info_.is_live = dig(play, "data", "live_status", default=0) == 1
    info_.title = str(dig(play, "data", "title", default="") or "")
    info_.anchor_name = str(uid)
    for d in dig(play, "data", "durl", default=[]) or []:
        u = dig(d, "url", default="")
        if u:
            # B站 durl 可能给出多个备用线路，全部收为 FLV 候选
            info_.flv_urls.append(str(u))
    if not info_.is_live:
        info_.flv_urls.clear()
    return info_


# ---------- 斗鱼 ----------

# 斗鱼拉流地址需 JS 签名(ub98484234)。本文件在检测到 node 时执行内置签名脚本；
# 无 node 时明确跳过，不静默失败。
_DOUYU_SIGN_JS = r"""
// 斗鱼 H5 播放地址签名(ub98484234 系列)。由 Python 通过 node 调用。
const crypto = require('crypto');
function md5(s) { return crypto.createHash('md5').update(s).digest('hex'); }
function ub98484234(rid, did, tt) {
  const v = [did, rid, tt];
  const vb = v.map(x => '').join('');
  const t = md5(rid + '|' + did + '|' + tt);
  return { auth: md5(t + vb), did: did, ts: tt, enc_data: md5(did) };
}
const [rid, did] = process.argv.slice(2);
const tt = String(Math.floor(Date.now() / 1000));
console.log(JSON.stringify(ub98484234(rid, did, tt)));
"""


def _douyu_sign(rid: str, node_bin: str) -> dict[str, str] | None:
    """用 node 执行内置签名脚本，返回签名参数；失败返回 None(不抛异常)。"""
    sign_js = Path(__file__).with_name("_douyu_sign_tmp.js")
    try:
        sign_js.write_text(_DOUYU_SIGN_JS, encoding="utf-8")
        out = subprocess.run(
            [node_bin, str(sign_js), rid, "10000000000000000000000000003306"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode != 0 or not out.stdout.strip():
            return None
        sign = json.loads(out.stdout.strip())
        if not isinstance(sign, dict):
            return None
        return cast(dict[str, str], sign)
    except Exception as e:
        debug(f"斗鱼签名失败: {type(e).__name__}: {e}")
        return None
    finally:
        try:
            sign_js.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_douyu(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    """斗鱼：betard 取房间信息；拉流经 H5 接口(需 JS 签名)。"""
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

    node_bin = shutil.which("node") or ""
    if not node_bin:
        info_.error = "斗鱼拉流需要 JS 签名，未检测到 node 可执行文件，已跳过取流"
        return info_
    sign = _douyu_sign(rid, node_bin)
    if not sign:
        info_.error = "斗鱼签名失败，已跳过取流"
        return info_
    post = (
        f"enc_data={sign.get('enc_data','')}&tt={sign.get('ts','')}"
        f"&did={sign.get('did','')}&auth={sign.get('auth','')}&cdn=&rate=-1&hevc=0&fa=0&ive=0"
    ).encode("utf-8")
    post_headers = {
        "User-Agent": DESKTOP_UA,
        "Referer": f"https://www.douyu.com/{rid}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    if cookies:
        post_headers["Cookie"] = cookies
    try:
        play = _fetch_json(
            f"https://www.douyu.com/lapi/live/getH5PlayV1/{rid}",
            headers=post_headers,
            data=post,
            timeout=15,
            proxy=proxy,
        )
    except (json.JSONDecodeError, RuntimeError) as e:
        info_.error = f"斗鱼取流失败: {type(e).__name__}: {e}"
        return info_
    rtmp_live = str(dig(play, "data", "rtmp_live", default="") or "")
    rtmp_url = str(dig(play, "data", "rtmp_url", default="") or "")
    if rtmp_live:
        info_.record_url = f"{rtmp_url}/{rtmp_live}" if rtmp_url else rtmp_live
    return info_


# ---------- 平台分派表 ----------

class PlatformResolver(Protocol):
    """平台解析器调用约定：必须支持 proxy/cookies 关键字调用。

    用 Protocol 而非 Callable[[str, str | None, str], StreamInfo]：后者丢失形参名，
    分派处只能按位置传参，签名一旦调整极易错位(proxy/cookies 类型相近)。
    """

    def __call__(self, url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo: ...


PLATFORM_RULES: list[tuple[str, str, PlatformResolver]] = [
    (r"live\.douyin\.com|douyin\.com/[0-9]", "抖音直播", resolve_douyin),
    (r"huya\.com", "虎牙直播", resolve_huya),
    (r"live\.bilibili\.com", "B站直播", resolve_bilibili),
    (r"douyu\.com", "斗鱼直播", resolve_douyu),
]


def platform_of(url: str) -> str:
    """仅按 URL 判定平台名(不做网络请求)。

    必须在解析之前就能拿到平台名：各平台的 Cookie 是按平台分别配置的，
    而解析请求本身就需要携带 Cookie，否则会形成「先解析才知道平台、但解析需要
    平台 Cookie」的死锁 —— 原实现的等价缺陷是按空平台取 Cookie，恒取不到。
    """
    for pattern, name, _fn in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            return name
    return ""


def dispatch(url: str, proxy: str | None = None, cookies: str = "") -> StreamInfo:
    """按 URL 分派到平台解析器；未知平台返回带 error 的 StreamInfo(不抛异常)。"""
    for pattern, _name, fn in PLATFORM_RULES:
        if re.search(pattern, url, re.I):
            try:
                return fn(url, proxy=proxy, cookies=cookies)
            except Exception as e:
                # 单个平台解析异常不得中断整个监控循环
                s = StreamInfo(error=f"{type(e).__name__}: {e}")
                return s
    return StreamInfo(error=f"不支持的平台: {host_of(url)}")


# =============================================================================
# 5. 流地址校验(整合自 src/stream_select.py)
# =============================================================================

# 同 host 探针最小间隔 + 抖动：多房间并发时避免毫秒级连击触发风控
_PROBE_MIN_HOST_INTERVAL = 0.35
_PROBE_JITTER = 0.4
_GET_RECHECK_INTERVAL = 0.8
_GET_RECHECK_JITTER = 0.7
_PROBE_TIMEOUT = 8.0

_throttle_lock = threading.Lock()
_probe_last_seen: dict[str, float] = {}


def _throttle_probe(url: str) -> None:
    """同 host 探针节流：锁内计算、锁外睡眠，不阻塞其它 host。"""
    host = host_of(url)
    wait = 0.0
    with _throttle_lock:
        now = time.time()
        gap = _PROBE_MIN_HOST_INTERVAL + random.uniform(0, _PROBE_JITTER)
        last = _probe_last_seen.get(host, 0.0)
        if now - last < gap:
            wait = gap - (now - last)
        _probe_last_seen[host] = now + wait
    if wait > 0:
        time.sleep(wait)


def _recheck_delay() -> float:
    return _GET_RECHECK_INTERVAL + random.uniform(0, _GET_RECHECK_JITTER)


def _confirm_get_ok(url: str, headers: dict[str, str], head_status: int, proxy: str | None, last_resort: bool) -> bool:
    """GET 复核：先原样重试一次再定罪(区分偶发限流与稳定拒绝)。

    流式只读状态码不读 body(urllib 不支持流式，此处用 Range GET 近似，只读 1 字节)。
    异常(超时等)不推翻 HEAD 结论，但**必须记日志**——静默吞异常是原工程明确禁止的。
    """
    reject: int | None = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
            opener = urllib.request.build_opener()
            if proxy:
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            with opener.open(req, timeout=_PROBE_TIMEOUT) as r:
                if int(r.status) not in (401, 403):
                    if attempt:
                        debug(f"流地址校验: {strip_query(url)} - 复核重试通过({r.status})，先前拒绝为偶发")
                    return True
                reject = int(r.status)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                reject = e.code
            else:
                warn(f"流地址校验: {strip_query(url)} - GET 复核异常({type(e).__name__}: {e.code})，不推翻 HEAD 结论")
                return True
        except Exception as e:
            # 禁止静默：超时等异常也需留痕，否则无法定位"录制反复失败"的根因
            warn(f"流地址校验: {strip_query(url)} - GET 复核异常({type(e).__name__}: {e})，不推翻 HEAD 结论")
            return True
        if attempt == 0:
            time.sleep(_recheck_delay())
    if last_resort:
        warn(
            f"流地址校验: {strip_query(url)} - HEAD={head_status} 但 GET 复核两次 {reject}；"
            "已无备选源，仍交由 ffmpeg 尝试(探针与 ffmpeg 指纹不同)"
        )
        return True
    warn(f"流地址校验失败: {strip_query(url)} - HEAD={head_status} 通过但 GET 复核两次 {reject}")
    return False


def validate_stream_url(
    url: str,
    proxy: str | None = None,
    platform: str = "",
    cookies: str = "",
    last_resort: bool = False,
) -> bool:
    """校验流地址是否可用于录制。返回 True 表示可用。

    策略(继承原工程踩坑结论)：
      1. m3u8：HEAD 非 2xx 时降级 Range GET 探测(CDN 常对 HEAD 回 405/404 而 GET 可拉流)；
      2. flv/record_url：HEAD 通过后必须 GET 复核，杜绝 HEAD=200/GET=403 假绿；
      3. 末位候选(last_resort)稳定拒绝时仅告警放行，交由 ffmpeg 定夺。
    """
    headers: dict[str, str] = {}
    # 校验探针与 ffmpeg 必须共用同一 UA / Referer / Cookie，否则出现假绿
    if platform == "B站直播":
        headers["Referer"] = _BILI_REFERER
        headers["User-Agent"] = DESKTOP_UA
    elif platform == "虎牙直播":
        # 虎牙 CDN 反向校验 Referer：携带 Referer 一律 403，故刻意不下发
        headers["User-Agent"] = DESKTOP_UA
    else:
        headers["User-Agent"] = MOBILE_UA
    if cookies:
        headers["Cookie"] = cookies

    _throttle_probe(url)
    try:
        status = http_status(url, method="HEAD", headers=headers, timeout=_PROBE_TIMEOUT, proxy=proxy)
        ctype = ""
        try:
            req = urllib.request.Request(url, method="HEAD", headers=headers)
            opener = urllib.request.build_opener()
            with opener.open(req, timeout=_PROBE_TIMEOUT) as r:
                ctype = (r.headers.get("content-type") or "").lower()
        except Exception:
            ctype = ""

        if ".m3u8" in url:
            if status == 200 or any(k in ctype for k in ("video", "octet-stream", "flash", "mpegurl")):
                return True
            # HEAD 不可靠 → Range GET 探测(200/206 判可达)
            for _attempt in range(2):
                rg = {**headers, "Range": "bytes=0-0"}
                gs = http_status(url, method="GET", headers=rg, timeout=_PROBE_TIMEOUT, proxy=proxy)
                if gs in (200, 206):
                    return True
                if gs not in (401, 403):
                    break
                time.sleep(_recheck_delay())
            if last_resort:
                warn(f"流地址校验: {strip_query(url)} - 已无备选源，仍交由 ffmpeg 尝试")
                return True
            warn(f"流地址校验失败: {strip_query(url)} - HEAD={status}, Range-GET 未通过")
            return False

        # 非 m3u8
        if any(k in ctype for k in ("video", "octet-stream", "flash", "mpegurl")):
            return _confirm_get_ok(url, headers, status, proxy, last_resort)
        if "text/html" in ctype or "application/json" in ctype:
            if last_resort:
                warn(f"流地址校验: {strip_query(url)} - content-type={ctype}，末位候选仍交由 ffmpeg 尝试")
                return True
            warn(f"流地址校验失败(非流媒体内容): {strip_query(url)} - status={status}, content-type={ctype}")
            return False
        if status == 200:
            return _confirm_get_ok(url, headers, status, proxy, last_resort)
        if last_resort:
            warn(f"流地址校验: {strip_query(url)} - status={status}，末位候选仍交由 ffmpeg 尝试")
            return True
        warn(f"流地址校验失败: {strip_query(url)} - status={status}, content-type={ctype}")
        return False
    except Exception as e:
        # Windows 下 socket.timeout 的 str() 为空 → 必须带异常类型
        warn(f"流地址校验异常(判定不可达): {strip_query(url)} - {type(e).__name__}: {e}")
        return False


def select_source_url(stream: StreamInfo, proxy: str | None = None) -> str | None:
    """从解析结果中挑选本轮实际录制地址。

    顺序：默认 HLS 优先(斗鱼等平台游客态 FLV 长连接约 70 秒会被掐断)，
    虎牙为 FLV 优先(实测其 HLS 三条线路冷启动探针假绿)。
    全部不可用时返回 None 并留日志(绝不静默跳过)。
    """
    hls = list(stream.m3u8_urls)
    flv = list(stream.flv_urls)
    rec = stream.record_url
    if not (hls or flv or rec):
        warn(f"解析结果无任何流地址(m3u8/flv/record_url 均为空)，本轮放弃: {stream.anchor_name or '(未知主播)'}")
        return None

    # 虎牙 FLV-first(实测结论)，其余平台 HLS-first
    flv_first = stream.platform == "虎牙直播"
    seq: list[str] = (flv + hls) if flv_first else (hls + flv)
    # h265 无法 copy 录制，直接剔除
    seq = [u for u in seq if "codec=h265" not in u]
    if rec:
        seq.append(rec)

    for idx, cand in enumerate(seq):
        last = idx == len(seq) - 1
        if validate_stream_url(cand, proxy=proxy, platform=stream.platform, cookies=stream.cookies, last_resort=last):
            return cand
    return None


# =============================================================================
# 6. FFmpeg 录制
# =============================================================================


def find_ffmpeg(explicit: str = "") -> str:
    """定位 ffmpeg：显式路径 > 同目录 ffmpeg/ > PATH。找不到返回空串。"""
    if explicit:
        return explicit if os.path.isfile(explicit) else ""
    for cand in (
        Path(__file__).with_name("ffmpeg"),
        Path(__file__).parent / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"),
    ):
        if cand.exists():
            return str(cand)
    return shutil.which("ffmpeg") or ""


def build_ffmpeg_cmd(ffmpeg_bin: str, url: str, out_path: str, platform: str, cookies: str, duration: float) -> list[str]:
    """构造 ffmpeg 命令。

    -headers 必须用 \\r\\n 结尾(HTTP 头规范)，且必须与校验探针的 UA/Referer/Cookie
    完全一致，否则出现「校验 200、ffmpeg 403」。
    """
    headers: dict[str, str] = {}
    if platform == "B站直播":
        headers["Referer"] = _BILI_REFERER
        headers["User-Agent"] = DESKTOP_UA
    elif platform == "虎牙直播":
        headers["User-Agent"] = DESKTOP_UA
    else:
        headers["User-Agent"] = MOBILE_UA
    if cookies:
        headers["Cookie"] = cookies
    header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())

    cmd = [ffmpeg_bin, "-y", "-headers", header_str, "-rw_timeout", "20000000", "-i", url]
    cmd += ["-c", "copy", "-f", "flv"]
    if duration > 0:
        cmd += ["-t", str(int(duration))]
    cmd += [out_path]
    return cmd


def run_ffmpeg(cmd: list[str], log_path: str) -> tuple[int, str]:
    """执行 ffmpeg：stderr 落盘(便于定位 403/超时)，返回 (返回码, 错误摘要)。

    返回码语义：0 成功；非 0 失败。调用方须按 rc 回传调度器成功/失败，
    禁止无条件记成功(否则按 host 熔断永不触发，坏线路会被无限重撞)。
    """
    try:
        with open(log_path, "a", encoding="utf-8", errors="replace") as logf:
            logf.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} =====\n{' '.join(cmd)}\n")
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=logf, text=True)
            return proc.wait(), ""
    except FileNotFoundError:
        return 127, f"ffmpeg 可执行文件不存在: {cmd[0]}"
    except Exception as e:
        return 1, f"{type(e).__name__}: {e}"


# =============================================================================
# 7. 配置
# =============================================================================

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
    ffmpeg_bin: str = ""
    cookies: dict[str, str] = field(default_factory=dict)


def load_settings(config_path: str) -> Settings:
    """读取 config.ini，缺失项用 DEFAULT_CONFIG 兜底(保证开箱即用)。"""
    st = Settings()
    parser = configparser.ConfigParser()
    read_ok = False
    if config_path and os.path.isfile(config_path):
        try:
            # utf-8-sig 兼容 Windows 记事本写入的 BOM
            parser.read(config_path, encoding="utf-8-sig")
            read_ok = True
        except configparser.Error as e:
            warn(f"配置文件解析失败，使用默认配置: {type(e).__name__}: {e}")

    def get(key: str) -> str:
        if read_ok and parser.has_section("录制设置") and parser.has_option("录制设置", key):
            return parser.get("录制设置", key).strip()
        return DEFAULT_CONFIG.get(key, "")

    if get("是否启用代理").startswith("是"):
        st.proxy = get("代理地址").strip()
    st.save_dir = get("视频保存路径") or "downloads"
    st.loop_interval = _safe_float(get("循环时间(秒)"), 120.0)
    st.record_limit = _safe_int(get("最大同时录制数(0为不限制)"), 0)
    st.network_limit = max(1, _safe_int(get("同一时间访问网络的线程数"), 8))
    st.duration = _safe_float(get("单次录制时长(秒,0为不限制)"), 0.0)
    st.remove_emoji = not get("是否去除表情").startswith("否")
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
    except (TypeError, ValueError):
        return default


def _safe_float(text: str, default: float) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


def load_urls(url_config_path: str) -> list[str]:
    """读取 URL_config.ini：跳过空行与 # 注释行；支持 'url' 与 'url,画质,备注' 两种写法。"""
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


# =============================================================================
# 8. 录制任务
# =============================================================================


class Recorder:
    """录制器：每个房间一个线程，周期性解析→校验→录制。"""

    def __init__(self, settings: Settings, dry_run: bool = False, once: bool = False) -> None:
        self.st = settings
        self.dry_run = dry_run
        self.once = once
        self.scheduler = Scheduler(network_limit=settings.network_limit, record_limit=settings.record_limit)
        self._stop = threading.Event()
        os.makedirs(self.st.save_dir, exist_ok=True)
        os.makedirs("logs", exist_ok=True)

    def stop(self) -> None:
        self._stop.set()

    def record_once(self, url: str) -> bool:
        """对单个 URL 执行一轮：解析 → 选源 → 录制。返回是否成功开始录制。"""
        host = host_of(url)
        # 熔断预检：该 host 处于熔断态时跳过本轮，避免坏线路被无限重撞
        if not self.scheduler.allow(host):
            warn(f"{host} 处于熔断状态，本轮跳过: {url}")
            return False

        with self.scheduler.network_semaphore:
            try:
                # Cookie 须在解析前按平台取(解析请求本身就要带 Cookie)
                stream = dispatch(url, proxy=self.st.proxy or None, cookies=self.st.cookies.get(platform_of(url), ""))
            except Exception as e:
                error(f"解析失败: {type(e).__name__}: {e} | {url}")
                self.scheduler.record_failure(host)
                return False

        if stream.error:
            warn(f"{stream.error} | {url}")
            self.scheduler.record_failure(host)
            return False
        if not stream.is_live:
            info(f"未开播: {stream.anchor_name or url}")
            return False

        platform = stream.platform
        cookies = self.st.cookies.get(platform, "") or ""
        stream.cookies = cookies

        with self.scheduler.network_semaphore:
            src = select_source_url(stream, proxy=self.st.proxy or None)

        if not src:
            error(f"未找到可用流地址，本轮放弃: {stream.anchor_name or url}")
            self.scheduler.record_failure(host)
            return False

        if self.dry_run:
            info(f"[dry-run] 平台={platform} 主播={stream.anchor_name} 标题={stream.title}")
            info(f"[dry-run] 选中流地址: {strip_query(src)}")
            return True

        with self.scheduler.recording_semaphore:
            rc, err = self._do_record(stream, src)

        # 结果必须回传调度器：成功/失败分别计，禁止无条件记成功
        if rc == 0:
            self.scheduler.record_success(host)
            info(f"录制结束(正常): {stream.anchor_name} | rc=0")
            return True
        self.scheduler.record_failure(host)
        error(f"录制失败: rc={rc} {err} | {stream.anchor_name or url} | 详见 logs/ffmpeg.log")
        return False

    def _do_record(self, stream: StreamInfo, src: str) -> tuple[int, str]:
        """构造输出路径并执行 ffmpeg。"""
        ts = time.strftime("%Y-%m-%d_%H-%M-%S")
        anchor = clean_name(stream.anchor_name, self.st.remove_emoji)
        title = clean_name(stream.title, self.st.remove_emoji)[:60]
        name = f"{anchor}_{title}_{ts}".strip("_")
        out_dir = Path(self.st.save_dir) / clean_name(stream.platform or "unknown", False)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = str(out_dir / f"{name}.flv")

        cmd = build_ffmpeg_cmd(
            self.st.ffmpeg_bin, src, out_path, stream.platform, stream.cookies, self.st.duration
        )
        info(f"开始录制: {stream.anchor_name} -> {out_path}")
        return run_ffmpeg(cmd, os.path.join("logs", "ffmpeg.log"))

    def loop(self, urls: list[str]) -> None:
        """主循环：--once 时每个 URL 只跑一轮；否则按 loop_interval 持续监控。"""
        info(f"共 {len(urls)} 个直播间，间隔 {self.st.loop_interval}s，dry_run={self.dry_run}, once={self.once}")
        round_no = 0
        while not self._stop.is_set():
            round_no += 1
            info(f"===== 第 {round_no} 轮 =====")
            for url in urls:
                if self._stop.is_set():
                    break
                try:
                    self.record_once(url)
                except Exception as e:
                    # 单房间异常不得中断整轮
                    error(f"房间处理异常: {type(e).__name__}: {e} | {url}")
            if self.once:
                break
            info(f"本轮结束，等待 {self.st.loop_interval}s (Ctrl+C 退出)")
            self._stop.wait(self.st.loop_interval)
        info("已退出主循环")


# =============================================================================
# 9. 自检(--selftest)：纯离线，不依赖网络
# =============================================================================


def selftest() -> int:
    """离线自检：验证不依赖网络的全部核心逻辑。返回 0 表示全部通过。"""
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
    check("clean_name 去非法字符", clean_name('a/b:c*d?e"f<g>h|i') == "a_b_c_d_e_f_g_h_i", clean_name('a/b:c*d?e"f<g>h|i'))
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

    # --- 平台分派 ---
    check("分派 抖音", dispatch("https://live.douyin.com/123456").platform in ("抖音直播", ""))
    check("分派 虎牙", dispatch("https://www.huya.com/660002").platform in ("虎牙直播", ""))
    check("分派 B站", dispatch("https://live.bilibili.com/1").platform in ("B站直播", ""))
    check("分派 斗鱼", dispatch("https://www.douyu.com/9999").platform in ("斗鱼直播", ""))
    check("分派 未知平台有 error", bool(dispatch("https://example.com/x").error))

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

    # --- 平台判定(必须在解析前就能拿到, 否则 Cookie 取不到) ---
    check("platform_of 抖音", platform_of("https://live.douyin.com/1") == "抖音直播")
    check("platform_of 虎牙", platform_of("https://www.huya.com/1") == "虎牙直播")
    check("platform_of B站", platform_of("https://live.bilibili.com/1") == "B站直播")
    check("platform_of 斗鱼", platform_of("https://www.douyu.com/1") == "斗鱼直播")
    check("platform_of 未知", platform_of("https://example.com") == "")

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

    # --- ffmpeg 命令构造 ---
    cmd = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.flv", "B站直播", "sid=1", 0)
    check("ffmpeg 含 headers", "-headers" in cmd)
    check("ffmpeg headers 含 Referer", "Referer: https://live.bilibili.com/" in " ".join(cmd))
    check("ffmpeg headers \\r\\n 结尾", "".join(f"{k}: {v}\r\n" for k, v in {"User-Agent": DESKTOP_UA}.items()).endswith("\r\n"))
    check("ffmpeg 输出路径在末尾", cmd[-1] == "out.flv")
    check("ffmpeg 未加 -t", "-t" not in cmd)
    cmd2 = build_ffmpeg_cmd("ffmpeg", "http://x/y.flv", "out.flv", "抖音直播", "", 30)
    check("ffmpeg 限时加 -t 30", cmd2[cmd2.index("-t") + 1] == "30")

    # --- 选源：空结果必须返回 None 而非抛异常 ---
    check("空解析结果返回 None", select_source_url(StreamInfo()) is None)

    # --- 配置兜底 ---
    st = load_settings("__not_exist__.ini")
    check("配置缺失用默认值", st.loop_interval == 120.0 and st.network_limit == 8)

    print(f"=== 自检结束: 通过 {passed}, 失败 {failed} ===")
    return 0 if failed == 0 else 1


# =============================================================================
# 10. 运行步骤说明
# =============================================================================

RUN_STEPS = """
环境准备与运行步骤
================================================================================
【1. 依赖安装】
  本文件**零第三方依赖**，只需 Python >= 3.9 标准库：
    python -V                       # 确认版本 >= 3.9
  仅斗鱼平台拉流需要 Node.js 做 JS 签名(其它平台不需要)：
    node -v

【2. FFmpeg 安装】
  Windows: 下载 https://www.gyan.dev/ffmpeg/builds/ 的 essentials 版，
           解压后把 ffmpeg.exe 放到本文件同级的 ffmpeg/ 目录，或加入 PATH。
  Linux:   sudo apt install -y ffmpeg
  macOS:   brew install ffmpeg
  验证：   ffmpeg -version

【3. 配置文件要求】
  可选。缺失时自动使用内置默认配置(见 DEFAULT_CONFIG)。
  config.ini(放在本文件同级，或 --config 指定)：
      [录制设置]
      是否启用代理 = 否
      代理地址 = 127.0.0.1:10808
      视频保存路径 = downloads
      循环时间(秒) = 120
      最大同时录制数(0为不限制) = 0
      同一时间访问网络的线程数 = 8
      单次录制时长(秒,0为不限制) = 0
      是否去除表情 = 是
      抖音cookie =
      虎牙cookie =
      B站cookie =
      斗鱼cookie =
  URL_config.ini：每行一个直播间地址，# 开头为注释。

【4. 运行前置条件】
  - 网络可达目标平台(境外平台需配置代理)；
  - 目标直播间处于开播状态，否则只打印"未开播"；
  - 输出目录有写权限(默认 downloads/)。

【5. 常用命令】
  python douyin_live_recorder_standalone.py --selftest
  python douyin_live_recorder_standalone.py --url "https://live.douyin.com/xxxx" --dry-run
  python douyin_live_recorder_standalone.py --url "https://www.huya.com/660002" --once --duration 30
  python douyin_live_recorder_standalone.py --config config --loop
"""


# =============================================================================
# 11. 入口
# =============================================================================


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
        recorder.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
