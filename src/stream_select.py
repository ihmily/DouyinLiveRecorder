# -*- coding: utf-8 -*-
# 流地址选择 / 校验 / 文本工具（独立模块）
#
# 负责：
# - 判断字符串是否含 URL（contains_url）
# - 文件名清洗（clean_name）
# - 画质中文名 ↔ 代码映射（get_quality_code）
# - 按平台返回录制请求头（get_record_headers）
# - 流地址可达性校验（_validate_stream_url）
# - 从解析结果中挑选本轮实际录制地址（select_source_url）
# - 抖音接口限流（_douyin_rate_limit）
#
# 部分函数需要读取 main 的少量配置全局变量（rstr / clean_emoji / hls_collection_enabled /
# douyin_* 限流变量），通过 `import main` 在运行时惰性读取，避免循环导入与 __main__ 二次执行。

import random
import re
import threading
import time
from collections.abc import Mapping
from typing import cast
from urllib.parse import urlsplit

import httpx
from loguru import logger

import main
from src import http_config as _http_config
from src import utils


# 判断 string 中是否包含类 URL 片段（用于区分配置行里的画质字段与网址）；返回布尔值
def contains_url(string: str) -> bool:
    # 检查字符串是否包含 URL
    pattern = r"(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(/.*)?"
    return re.search(pattern, string) is not None


# 清洗 input_text 为合法文件名（过滤非法字符、可选去表情、& 换下划线）；返回清洗结果，全空时返回"空白昵称"
def clean_name(input_text: str) -> str:
    # 清理文件名中的非法字符
    cleaned_name = re.sub(main.rstr, "_", input_text.strip()).strip("_")
    cleaned_name = cleaned_name.replace("（", "(").replace("）", ")")
    if main.clean_emoji:
        cleaned_name = utils.remove_emojis(cleaned_name, "_").strip("_")
    # Windows 特殊字符清理：& 在 cmd 中会触发命令分隔，统一替换为下划线
    cleaned_name = cleaned_name.replace("&", "_")
    return cleaned_name or "空白昵称"


# 把中文画质名 qn（原画/蓝光/超清/高清/标清/流畅）映射为内部画质代码（OD/BD/UHD/HD/SD/LD），未知值回退 "OD"
def get_quality_code(qn: str) -> str:
    # 将画质描述转为代码（原画/超清/高清等）
    quality_zh_to_en = {"原画": "OD", "蓝光": "BD", "超清": "UHD", "高清": "HD", "标清": "SD", "流畅": "LD"}
    # 未知画质回退到 OD，避免返回 None 导致后续比较逻辑出错
    return quality_zh_to_en.get(qn, "OD")


# 桌面 Chrome UA：虎牙/B站 等国内 CDN 会拒绝移动端 UA（返回 403），录制拉流必须用
# 桌面 UA；校验探针与 ffmpeg 录制共用同一 UA（见 get_record_user_agent），否则校验“假绿”。
# 版本对齐全库基准 Chrome/141（见 room.DESKTOP_UA），避免 UA 指纹过旧被风控标记。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 移动端 UA：与 main.py ffmpeg 录制命令的默认 UA 保持一字不差。校验探针若不带此 UA
# （发 httpx 默认 UA），部分 CDN（斗鱼 hwa 实测）会对 GET 偶发 403 而 ffmpeg 移动 UA
# 拉流正常——校验与录制两端 UA 必须完全一致。2026-08 统一升级为 Android 14 + Chrome 141
# （原 SamsungBrowser/14.2 + Chrome/87 已过时 5 年+，旧 UA 指纹更易被风控识别）。
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 ("
    "KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
)

# 各平台录制所需的 base 请求头（不含 cookie），形如 {"referer": "...", "origin": "..."}；
# 该平台无需额外头时留空。shopee 的 origin 取 live_url 域名，故用 "origin" 占位由函数解析。
_RECORD_HEADER_RULES: dict[str, str] = {
    "PandaTV": "origin:https://www.pandalive.co.kr",
    "WinkTV": "origin:https://www.winktv.co.kr",
    "PopkonTV": "origin:https://www.popkontv.com",
    "TTingLive(原Flextv)": "origin:https://www.flextv.co.kr",
    "千度热播": "referer:https://qiandurebo.com",
    "17Live": "referer:https://17.live/en/live/6302408",
    "浪Live": "referer:https://www.lang.live",
    "shopee": "origin",  # 由 live_url 域名解析
    "blued": "referer:https://app.blued.cn",
    # 虎牙 HLS/FLV 防盗链：实测虎牙 CDN 现已【反向】校验——携带 Referer
    # (https://www.huya.com/) 的请求一律返回 403，不携带 Referer 时 HS 线路 GET 200
    # 正常拉流（AL/TX 仍可能按房间未承载推流而 403，由 select_source_url 多 CDN 候选
    # 校验自动跳过）。故此处【不下发】Referer；校验探针与 ffmpeg 录制共用本函数、两端
    # 一致地不携带 Referer 才能稳定拿到流。
    # （旧逻辑曾依赖 Referer 才能 200，该行为已被废弃；旧规则 "虎牙直播": "referer:..." 会直接 403。）
    # "虎牙直播": "referer:https://www.huya.com/",  # 已废弃：携带此 Referer 反而 403
    # B站直播 CDN（bilivideo.com）对无 Referer 的请求返回 403（content-type 空），
    # 与虎牙同源。校验器与 ffmpeg 录制共用此条目，保证两端一致地拿到流。
    "B站直播": "referer:https://live.bilibili.com/",
}


# 按 platform 返回录制拉流所需的请求头字典（合并 base 头与可选 cookie），无头时返回 None。
# - base 头按平台提供 referer/origin（B站 缺 Referer 会被 CDN 拒 403）；虎牙现已反向校验，
#   携带 Referer 反而 403，故不在此下发 Referer（见下方 _RECORD_HEADER_RULES 注释）。
# - cookies 为登录态 Cookie 字符串（如配置的 *cookie），转发给 CDN 以满足会话校验
#   （B站需 buvid3）。空字符串/None 时不注入 cookie。
# 校验探针与 ffmpeg 录制共用本函数，保证两端请求头完全一致。
def get_record_headers(platform: str, live_url: str, cookies: str | None = None) -> dict[str, str] | None:
    # 获取录制请求的 HTTP 头
    header_dict: dict[str, str] = {}
    rule = _RECORD_HEADER_RULES.get(platform)
    if rule == "origin" and live_url:
        live_domain = "/".join(live_url.split("/")[0:3])
        header_dict["origin"] = live_domain
    elif rule:
        key, value = rule.split(":", 1)
        header_dict[key] = value
    if cookies:
        header_dict["cookie"] = cookies
    return header_dict or None


# 需要桌面 UA 的平台（国内 CDN 拒绝移动端 UA，返回 403）。其它平台返回 None，
# 表示调用方沿用其默认移动 UA，避免对非相关平台引入行为变化。
_DESKTOP_UA_PLATFORMS = ("虎牙直播", "B站直播")


def get_record_user_agent(platform: str) -> str | None:
    # 校验探针与 ffmpeg 录制共用：虎牙/B站 用桌面 Chrome UA，其余返回 None（沿用现有移动 UA）。
    if platform in _DESKTOP_UA_PLATFORMS:
        return DESKTOP_UA
    return None


# GET 复核的两次探测间隔基准（秒）：斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针（HEAD→GET）
# 会偶发 403（ffmpeg 单次 GET 正常），隔开重试可区分「偶发限流」与「稳定拒绝」。
# 实际间隔在基准之上叠加随机抖动（见 _recheck_delay）：固定节奏的探针（间隔恒定）
# 是机器人指纹特征之一，抖动能显著降低被 CDN 风控按节奏识别的概率。
_GET_RECHECK_INTERVAL = 0.8
# 重试间隔抖动上限（秒）：实际间隔 = _GET_RECHECK_INTERVAL + uniform(0, 抖动上限)。
_GET_RECHECK_JITTER = 0.7

# 同一 CDN host 相邻两次探针的最小间隔（秒）+ 抖动上限：多房间并发监控时（各自独立的
# 房间线程），对同一 CDN 的探针可能毫秒级连击——正是风控误触发的根因。探针节流保证
# 同 host 探针至少间隔 _PROBE_MIN_HOST_INTERVAL + uniform(0, _PROBE_THROTTLE_JITTER)，
# 不同 host 互不影响、首次探针不等待。测试可将 _PROBE_MIN_HOST_INTERVAL 置 0 关闭节流。
_PROBE_MIN_HOST_INTERVAL = 0.35
_PROBE_THROTTLE_JITTER = 0.4
_probe_last_seen: dict[str, float] = {}
_probe_throttle_lock = threading.Lock()


# 计算一次带随机抖动的重试间隔：固定 0.8s 间隔的探针序列具有可识别节奏，
# 叠加 0~0.7s 抖动后节奏被打散，降低按节奏特征触发风控的概率；无入参，返回间隔秒数。
def _recheck_delay() -> float:
    return _GET_RECHECK_INTERVAL + random.uniform(0, _GET_RECHECK_JITTER)


# 同 host 探针节流：距上次同 host 探针不足最小间隔时补足等待（锁内计算、锁外睡眠，
# 不阻塞其它 host 的探针）；无返回值。这是探针层的全局限速，与退避（_probe_backoff，
# 被拒后的止损）互补：节流降低风控触发概率，退避在被拒后止血。
def _throttle_probe(url: str) -> None:
    host = urlsplit(url).netloc
    if not host:
        return
    wait = 0.0
    with _probe_throttle_lock:
        now = time.time()
        min_gap = _PROBE_MIN_HOST_INTERVAL + random.uniform(0, _PROBE_THROTTLE_JITTER)
        last = _probe_last_seen.get(host, 0.0)
        if now - last < min_gap:
            wait = min_gap - (now - last)
        _probe_last_seen[host] = now + wait  # 登记预计发出时刻，排队中的后续探针据此排队
    if wait > 0:
        time.sleep(wait)


# 探针退避（负缓存）：虎牙 aldirect CDN 对同一路径短时间内的连续连接做限流，每轮
# 「HLS 3 连探针 + FLV 2~3 连探针 + ffmpeg 拉流」会烧光连接预算——表现为校验通过(200)
# 后 ffmpeg 立即 403（Error opening input: 403 Forbidden），或拉流数百 KB 后被掐断
# （Stream ends prematurely），录制陷入秒级失败循环、弹幕采集器随之反复起停收不到消息。
# 对开启退避的平台：探针观测到 401/403（含重试后恢复的偶发拒绝，同样是限流证据）即把
# 「scheme://host/路径」记入退避窗口；窗口内跳过全部探针——非末位候选按校验失败回退
# 下一候选，末位候选直接放行给 ffmpeg，让 ffmpeg 拿到零探针占用的干净连接预算。
# 仅对虎牙开启：斗鱼 hw CDN 的偶发 403 由既有「重试一次再定罪」语义救回（重试即 206），
# 若对斗鱼启用退避跳过探针，会导致斗鱼 HLS-first 回退 FLV（游客态约 70 秒被掐）回归，
# 绝不可扩大名单。
_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)
_PROBE_BACKOFF_SECONDS = 60.0
_probe_backoff: dict[str, float] = {}
_probe_backoff_lock = threading.Lock()


# 提取 url 的退避键（scheme://host/路径，去掉 query）：虎牙每轮解析返回新 token（query 变化）
# 但路径稳定，按 host+路径聚合才能跨轮命中；不同房间路径不同，互不误伤。
def _probe_backoff_key(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


# 记录一次探针拒绝（401/403）：platform 在退避名单内才记录；顺带清理过期键防字典无界增长。
def _mark_probe_reject(url: str, platform: str | None) -> None:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return
    key = _probe_backoff_key(url)
    now = time.time()
    with _probe_backoff_lock:
        for stale in [k for k, ts in _probe_backoff.items() if now - ts > _PROBE_BACKOFF_SECONDS]:
            _probe_backoff.pop(stale, None)
        _probe_backoff[key] = now


# 查询 url 是否处于探针退避窗口内（仅对退避名单内平台生效）。
def _probe_in_backoff(url: str, platform: str | None) -> bool:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return False
    with _probe_backoff_lock:
        ts = _probe_backoff.get(_probe_backoff_key(url))
        return ts is not None and time.time() - ts <= _PROBE_BACKOFF_SECONDS


# ffmpeg 录制失败侧的反馈入口：录制「快速失败」（输入打开即被拒，如虎牙 HS 线路
# 探针 200/206 通过、ffmpeg 紧随其后 GET 却 403）时，把 ffmpeg 实际拉流的地址记入
# 探针退避窗口。下一轮 select_source_url 会跳过该地址的探针、直接尝试下一 CDN
# 候选——这类「探针假绿」在探针侧永远观测不到（httpx 与 ffmpeg 客户端指纹不同），
# 只有录制侧的失败能反馈该信息；不标记会形成「探针通过→录制被拒→下轮探针仍通过」
# 的死循环，房间永远录不上。platform 不在退避名单内时为无操作（与 _mark_probe_reject
# 同一白名单，当前仅虎牙）。
def mark_ffmpeg_reject(url: str, platform: str | None) -> None:
    _mark_probe_reject(url, platform)


# FLV/record_url 源 HEAD 通过后的 GET 复核（流式请求、不读 body）：
# 虎牙 al.flv.huya.com 等 CDN 出现过 HEAD=200 而 GET=403 —— 校验“假绿”后 ffmpeg 打开即 403、
# 录制反复失败。ffmpeg 拉流是「无 Range 的全量 GET」，复核必须与之完全一致：
# - 虎牙对无 Range GET 同样 403（拒绝的是 GET 本身），假绿仍能抓到；
# - 斗鱼 hwa CDN 曾对 Range-GET 偶发 403 而无 Range GET 正常（实测），带 Range 反而误杀可用源。
# 复核仅在拿到明确拒绝状态码（401/403）时推翻 HEAD 结论，且先原样重试一次再定罪：
# 斗鱼 hw/虎牙 al 实测对短时间内的连续探针会偶发 403，同 URL 片刻后重试即 200（探针误杀、
# ffmpeg 实际拉流成功）。其余异常（超时等）不推翻，避免把可用源误判为不可达。
# last_resort=True 表示该源已是最后一个候选（无备选可回退）：两次复核均拒绝时仅告警放行，
# 交由 ffmpeg 实际拉流定夺——探针（httpx）与 ffmpeg 的客户端指纹不同，存在探针稳定 403
# 而 ffmpeg 可正常拉流的实例。流式只读状态码不迭代 body，不会下载直播流。
def _confirm_get_ok(
    client: httpx.Client,
    url: str,
    head_status: int,
    last_resort: bool = False,
    platform: str | None = None,
) -> bool:
    reject_status: int | None = None
    for attempt in range(2):
        try:
            with client.stream("GET", url, follow_redirects=True) as probe:
                if probe.status_code not in (401, 403):
                    if attempt:
                        logger.debug(f"流地址校验: {url} - GET 复核重试通过({probe.status_code})，先前拒绝为偶发")
                    return True
                reject_status = probe.status_code
                # 偶发 403 即使重试恢复也是限流证据：记录退避，下一轮让 ffmpeg 直连
                _mark_probe_reject(url, platform)
        except Exception:
            return True  # GET 复核异常（超时等）不推翻 HEAD 结论
        if attempt == 0:
            time.sleep(_recheck_delay())
    if last_resort:
        logger.warning(
            f"流地址校验: {url} - HEAD={head_status} 通过但 GET 复核两次 {reject_status}；"
            "已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同，探针拒绝不代表 ffmpeg 不可拉流）"
        )
        return True
    logger.warning(
        f"流地址校验失败: {url} - HEAD={head_status} 通过但 GET 复核两次 {reject_status}（CDN 稳定拒绝 GET），判定不可达"
    )
    return False


# 探测流地址 url 是否可用于录制：proxy_addr 为可选代理、timeout 为超时秒数、
# verify 为 SSL 证书校验开关（None 时取全局配置）；返回可达且内容类型为流媒体则 True，否则 False（并打日志说明原因）
def _validate_stream_url(
    url: str,
    proxy_addr: str | None = None,
    timeout: int = 5,
    verify: bool | None = None,
    platform: str | None = None,
    cookies: str | None = None,
    last_resort: bool = False,
) -> bool:
    # 校验流地址可达性（与 async_http.get_response_status 语义保持一致）：
    # 1) 未显式指定时沿用全局 SSL 验证开关，避免与解析阶段的校验行为不一致
    #    （用户关闭证书验证后，同步校验仍验证证书会导致误判不可达）；
    # 2) m3u8 源 HEAD 非 2xx（含 403/404）时再做 Range GET 探测——抖音等 CDN 常
    #    对 HEAD 返回 4xx 而 GET 可正常拉流，仅覆盖 400/401/403/405 会漏掉 404；
    # 3) 失败必须记录原因（异常类型/状态码/content-type），禁止静默吞掉异常，
    #    否则回退 FLV 时无法定位真实原因（如超时、被拒、内容类型不符）；
    # 4) 按 platform 透传录制所需请求头（如虎牙 Referer），否则虎牙 CDN 无 Referer
    #    直接 403，校验会误判不可达而放弃录制——必须与 ffmpeg 录制路径保持一致。
    # 5) 未显式指定 verify 时取平台有效校验开关：由「是否启用https录制」统一联动——
    #    开启=https 拉流且全局禁用证书验证；关闭=http 拉流（恢复默认严格校验）。
    #    平台覆盖受 https_recording_enabled 门控，保证校验器与录制路径一致。
    if verify is None:
        verify = _http_config.get_effective_ssl_verify(platform)
    headers: dict[str, str] = {}
    if platform:
        # 校验探针必须与 ffmpeg 录制用相同请求头（referer/origin + cookie）与 UA，
        # 否则会出现“校验 200、ffmpeg 403”的假绿（如虎牙移动端 UA 被 CDN 拒）。
        base = get_record_headers(platform, url, cookies=cookies)
        if base:
            headers.update(base)
        # UA 与 ffmpeg 录制命令完全一致：桌面 UA 平台用桌面 UA，其余平台用移动 UA
        # （main.py ffmpeg 默认 UA）。发 httpx 默认 UA 会被部分 CDN（斗鱼 hwa 实测）
        # 在 GET 时偶发 403，造成校验与录制行为不一致。
        headers["User-Agent"] = get_record_user_agent(platform) or MOBILE_UA
    # 探针退避：该源所在 CDN 近端已被连续拒绝（限流中），本轮跳过全部探针。
    # 非末位候选按校验失败回退下一候选；末位候选直接放行给 ffmpeg——探针拒绝 ≠
    # ffmpeg 不可拉流（与 _confirm_get_ok 末位语义一致），且省下的连接预算正是
    # ffmpeg 拉流成败的关键（虎牙实测：探针烧光预算后 ffmpeg 立即 403）。
    if _probe_in_backoff(url, platform):
        if last_resort:
            logger.warning(f"流地址校验: {url} - CDN 探针退避中，跳过探针直接交由 ffmpeg 拉流")
            return True
        logger.warning(f"流地址校验: {url} - CDN 探针退避中，跳过本轮探针、回退下一候选")
        return False
    # 同 host 探针节流（退避未命中才走到这里）：补足与上次同 host 探针的最小间隔，
    # 消除多房间并发监控下的毫秒级连击探针——降低风控被误触发的概率。
    _throttle_probe(url)
    try:
        with httpx.Client(timeout=timeout, proxy=proxy_addr, verify=verify, headers=headers) as client:
            response = client.head(url, follow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()
            if response.status_code in (401, 403):
                _mark_probe_reject(url, platform)
            # m3u8 源：抖音等 CDN 对 HEAD 常回 4xx（如 405）+ text/html，但 GET 实际可拉流。
            # 优先做 Range GET 探测，绕过 HEAD 不可靠的 content-type/状态码（与 async_http.get_response_status 保持一致）。
            if ".m3u8" in url:
                if response.status_code == 200 or any(
                    k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")
                ):
                    return True
                # Range-GET 401/403 先隔 _GET_RECHECK_INTERVAL 原样重试一次再定罪（与 _confirm_get_ok
                # 同语义）：斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针（HEAD→GET）偶发 403，同 URL
                # 片刻后重试即 200（探针误杀、ffmpeg 单次 GET 正常）。HLS 优先于 FLV 录制——
                # 斗鱼游客态 FLV 长连接约 70 秒被 CDN 掐断，HLS 逐段拉取免疫，须尽力救回。
                probe: httpx.Response | None = (
                    None  # 失败路径（last_resort/告警）需 Range-GET 结果；先置 None 避免未绑定
                )
                for attempt in range(2):
                    probe = client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
                    if probe.status_code in (200, 206):
                        if attempt:
                            logger.debug(f"流地址校验: {url} - Range-GET 重试通过({probe.status_code})，先前拒绝为偶发")
                        return True
                    if probe.status_code not in (401, 403):
                        break  # 非探针误杀类拒绝（如 404），不重试
                    _mark_probe_reject(url, platform)
                    if attempt == 0:
                        time.sleep(_recheck_delay())
                # 循环已至少执行一次，probe 必非空；断言收窄类型供后续日志引用
                assert probe is not None
                if last_resort:
                    logger.warning(
                        f"流地址校验: {url} - HEAD={response.status_code}, Range-GET={probe.status_code}；"
                        "已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）"
                    )
                    return True
                logger.warning(
                    f"流地址校验失败: {url} - HEAD={response.status_code}, Range-GET={probe.status_code}, "
                    f"content-type={probe.headers.get('content-type', '')}"
                )
                return False
            # 非 m3u8 源（flv/record_url）沿用 content-type 启发式；HEAD 判定通过后再做
            # GET 复核（流式），杜绝 HEAD=200/GET=403 的“假绿”（ffmpeg 实际拉流是 GET）
            if any(k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")):
                return _confirm_get_ok(client, url, response.status_code, last_resort=last_resort, platform=platform)
            if "text/html" in content_type or "application/json" in content_type:
                if last_resort:
                    # 斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁用 HEAD 方法），ffmpeg 实际 GET 拉流正常。
                    # 末位候选（无备选可回退）稳定拒绝也仅告警放行、交由 ffmpeg 定夺，
                    # 避免 content-type 启发式误杀可用源导致整轮放弃录制。
                    logger.warning(
                        f"流地址校验: {url} - status_code={response.status_code}, content-type={content_type}；"
                        "已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）"
                    )
                    return True
                logger.warning(
                    f"流地址校验失败（返回非流媒体内容）: {url} - status_code={response.status_code}, content-type={content_type}"
                )
                return False
            if response.status_code == 200:
                return _confirm_get_ok(client, url, response.status_code, last_resort=last_resort, platform=platform)
            if last_resort:
                # 同上：末位候选的稳定拒绝（非 200 且无法识别 content-type）仅告警放行
                logger.warning(
                    f"流地址校验: {url} - status_code={response.status_code}, content-type={content_type}；"
                    "已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）"
                )
                return True
            logger.warning(f"流地址校验失败: {url} - status_code={response.status_code}, content-type={content_type}")
            return False
    except Exception as e:
        # Windows 下 socket.timeout 的 str() 为空，必须带上异常类型与 URL
        logger.warning(f"流地址校验异常（判定为不可达）: {url} - {type(e).__name__}: {e}")
        return False


# 从 stream_info（解析结果，含 m3u8_url/flv_url/record_url 等键）挑选本轮实际录制地址：
# 优先 HLS，其次 FLV，最后 record_url，proxy_addr 透传给可达性校验；全部不可用时返回 None
def select_source_url(
    stream_info: Mapping[str, object],
    proxy_addr: str | None = None,
    platform: str | None = None,
    cookies: str | None = None,
) -> str | None:
    # HLS(m3u8) 优先采集：当存在 HLS 源且配置启用 HLS 采集时优先使用；
    # 仅当无 HLS 源 或 配置关闭 HLS 采集时，才回退使用 FLV 源。
    # proxy_addr 必须透传给校验器：TikTok 等境外平台的流地址若不走与解析阶段
    # 相同的代理路径，直连校验会超时被误判为不可达，导致错误回退甚至放弃录制。
    # 候选合并：兼容「单 m3u8_url/flv_url」旧结构，同时支持平台（如虎牙）返回的候选列表
    # （m3u8_url_list/flv_url_list）。去重并按优先级排序：主源在前、候选列表在后。
    # 虎牙单房间多条 CDN 线路（HS/HW/TX/AL）共享同一套防盗链参数，但仅当前承载推流的
    # 线路返回 200、其余稳定 403；故必须逐候选校验、首条可达即选用，而非固定取某条线路
    # （此前固定取 index0=AL 或固定 TX 优先，频繁命中离线线路导致 HLS 整轮不可达）。
    def _as_str_list(value: object) -> list[str]:
        # 把单个 URL 或 URL 列表收敛为去空后的字符串列表（保持入参顺序）
        if isinstance(value, str) and value:
            return [value]
        if isinstance(value, list):
            return [u for u in value if isinstance(u, str) and u]
        return []

    hls_candidates = _as_str_list(stream_info.get("m3u8_url"))
    for u in _as_str_list(stream_info.get("m3u8_url_list")):
        if u not in hls_candidates:
            hls_candidates.append(u)
    flv_candidates = _as_str_list(stream_info.get("flv_url"))
    for u in _as_str_list(stream_info.get("flv_url_list")):
        if u not in flv_candidates:
            flv_candidates.append(u)
    record_url = stream_info.get("record_url")
    has_record_url = isinstance(record_url, str) and bool(record_url)
    hls_available = bool(hls_candidates)
    flv_available = bool(flv_candidates)
    has_fallback = flv_available or has_record_url

    if hls_available and main.hls_collection_enabled:
        # 逐 HLS 候选校验：中间候选失败继续尝试下一候选；仅当「最后一条 HLS 且无其它回退源」
        # 时才以 last_resort 放行（交给 ffmpeg 定夺），否则正常回退 FLV/record_url。
        for idx, cand in enumerate(hls_candidates):
            is_last = idx == len(hls_candidates) - 1
            if _validate_stream_url(
                cand,
                proxy_addr=proxy_addr,
                platform=platform,
                cookies=cookies,
                last_resort=is_last and not has_fallback,
            ):
                return cand
        logger.warning("HLS URL validation failed, falling back to FLV")

    if flv_available:
        for idx, cand in enumerate(flv_candidates):
            codec = utils.get_query_params(cand, "codec")
            if isinstance(codec, list) and codec and codec[0] == "h265":
                # h265 FLV 无法 copy 录制。存在 HLS 源且启用 HLS 采集时改走 HLS（逐候选校验，
                # 末位为 last_resort）；HLS 也不可用时不放弃整轮，继续尝试下一 FLV 候选
                # （可能非 h265），全部 h265 且 HLS 不可用才交由后续 record_url 兜底。
                if hls_available and main.hls_collection_enabled:
                    for h_idx, h_cand in enumerate(hls_candidates):
                        if _validate_stream_url(
                            h_cand,
                            proxy_addr=proxy_addr,
                            platform=platform,
                            cookies=cookies,
                            last_resort=h_idx == len(hls_candidates) - 1,
                        ):
                            logger.warning("FLV is not supported for h265 codec, use HLS source instead")
                            return h_cand
                    logger.warning("FLV 为 h265 且 HLS 源校验失败，尝试其它 FLV 候选")
                else:
                    logger.warning("FLV 为 h265 无法录制且 HLS 采集已关闭，尝试其它 FLV 候选")
                continue
            # 末位 FLV 且无 record_url 备选时恒为 last_resort（交给 ffmpeg 尝试，探针拒绝 ≠
            # ffmpeg 不可拉流），其余 FLV 候选失败继续回退下一候选/record_url。
            is_last = idx == len(flv_candidates) - 1
            if _validate_stream_url(
                cand,
                proxy_addr=proxy_addr,
                platform=platform,
                cookies=cookies,
                last_resort=is_last and not has_record_url,
            ):
                return cand
        logger.warning("FLV URL validation failed, trying record_url fallback")

    if isinstance(record_url, str) and record_url:
        codec = utils.get_query_params(record_url, "codec")
        if isinstance(codec, list) and codec and codec[0] == "h265":
            logger.warning("record_url has h265 codec, but no HLS or FLV fallback available")
        # record_url 是最后一档候选，恒为 last_resort：稳定拒绝也放行给 ffmpeg 定夺
        if _validate_stream_url(
            record_url, proxy_addr=proxy_addr, platform=platform, cookies=cookies, last_resort=True
        ):
            return record_url
    # 三类地址全为空：此前静默返回 None，房间会永远打印“正在直播中...”却不录制且无任何
    # 诊断线索（斗鱼 rtmp_live 为空即此形态）。必须留一条日志暴露根因。
    if not (hls_available or has_fallback):
        logger.warning(
            f"解析结果无任何流地址（m3u8/flv/record_url 均为空），本轮放弃: {stream_info.get('anchor_name') or ''}"
        )
    elif hls_available and not main.hls_collection_enabled and not has_fallback:
        # m3u8 存在但 HLS 采集关闭、且无 FLV/record_url 可回退：同为静默路径，
        # 用户可通过开启 HLS 采集恢复录制，必须提示而非无声跳过
        logger.warning(
            f"存在 HLS 源但 HLS 采集未启用，且无 FLV/record_url 可回退，本轮放弃"
            f"（可开启 HLS 采集恢复录制）: {stream_info.get('anchor_name') or ''}"
        )
    return None


# 抖音接口调用限流：必要时 sleep，保证两次抖音请求间隔不小于 douyin_min_interval 秒；无入参无返回值
def _douyin_rate_limit() -> None:
    # 抖音请求速率限制：保证两次抖音 API 请求之间有最小间隔，
    # 避免多线程并发监控多个直播间时触发抖音风控（返回空响应）。
    # 在 semaphore 内部调用，确保串行化 + 间隔双重保护。
    with main.douyin_rate_lock:
        now = time.time()
        elapsed = now - main.douyin_last_request_time
        if elapsed < main.douyin_min_interval:
            time.sleep(main.douyin_min_interval - elapsed)
        main.douyin_last_request_time = time.time()
