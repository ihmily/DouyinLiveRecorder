# -*- coding: utf-8 -*-
# 流地址选择 / 校验 / 文本工具（独立模块）
#
# 负责：URL 片段判定（contains_url）、文件名清洗（clean_name）、画质中文名 ↔ 代码映射
# （get_quality_code）、按平台返回录制请求头（get_record_headers）、流地址可达性校验
# （_validate_stream_url）、从解析结果中挑选本轮实际录制地址（select_source_url）、
# 抖音接口限流（_douyin_rate_limit）。
#
# 部分函数需读取 main 的少量配置全局变量（rstr / clean_emoji / hls_collection_enabled /
# hls_collection_exclude_platforms / douyin_* 限流变量），通过 `import main` 在运行时惰性读取，
# 避免循环导入与 __main__ 二次执行。

import ipaddress
import random
import re
import threading
import time
from collections.abc import Mapping
from urllib.parse import urljoin, urlsplit

import httpx
from loguru import logger

import i18n
import main
from src import http_config as _http_config
from src import utils

# 类 URL 片段匹配模式（模块级编译一次）：主循环每解析一行 URL 配置就调用 contains_url，
# 80+ 房间时每轮上百次；预编译省掉每次走 re 模块模式串缓存查表的开销。
_URL_PATTERN = re.compile(r"(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(/.*)?")


# 判断 string 中是否包含类 URL 片段（用于区分配置行里的画质字段与网址）；返回布尔值
def contains_url(string: str) -> bool:
    return _URL_PATTERN.search(string) is not None


# 文件名长度上限（字符数）。main.py 把平台 API 下发、长度不可控的标题拼进保存路径，
# 叠加较深的保存目录极易突破 Windows MAX_PATH(260)，届时 makedirs / ffmpeg 输出都会失败，
# 错误却只表现为一句笼统的「录制出错」。
_MAX_NAME_CHARS = 60

# Windows 保留设备名：同名文件/目录在 Windows 上无法创建（即使带扩展名），
# 用保留名做主播名时行为是「目录创建失败 → 录制静默失败」。
_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
)


# 清洗 input_text 为合法文件名（过滤非法字符、控制字符、保留设备名、超长截断、可选去表情、
# & 换下划线）；返回清洗结果，全空时返回"空白昵称"
def clean_name(input_text: str) -> str:
    cleaned_name = re.sub(main.rstr, "_", input_text.strip()).strip("_")
    # 控制字符（0x00-0x1F）不在 rstr 的字符集内，但同样会让写盘失败
    cleaned_name = re.sub(r"[\x00-\x1f\x7f]", "_", cleaned_name).strip("_")
    cleaned_name = cleaned_name.replace("（", "(").replace("）", ")")
    if main.clean_emoji:
        cleaned_name = utils.remove_emojis(cleaned_name, "_").strip("_")
    # Windows 特殊字符清理：& 在 cmd 中会触发命令分隔，统一替换为下划线
    cleaned_name = cleaned_name.replace("&", "_")
    # 保留设备名改名（CON → CON_），否则 Windows 上无法创建同名目录。
    # Windows 拒绝的是「基础名 + 任意扩展名」的整个形态（CON.txt 同样建不出来），
    # 原实现只在整串末尾加下划线（CON.txt → CON.txt_），基础名仍是保留名、目录创建依旧失败。
    # 故按第一个点切分出基础名，改名后**接回原扩展名**（CON.txt → CON_.txt）。
    reserved_head, dot, reserved_tail = cleaned_name.partition(".")
    if reserved_head.upper() in _WINDOWS_RESERVED_NAMES:
        cleaned_name = reserved_head + "_" + dot + reserved_tail
    # 超长截断按字符数（非字节），中文名不会被腰斩成半个字符；
    # 截断后可能留下结尾下划线，再 strip 一次。
    if len(cleaned_name) > _MAX_NAME_CHARS:
        cleaned_name = cleaned_name[:_MAX_NAME_CHARS].strip("_")
    return cleaned_name or "空白昵称"


# 把中文画质名 qn 映射为内部画质代码，未知值回退 "OD"。
# 蓝光细粒度档位（蓝光4M/8M/20M/30M）：虎牙/斗鱼按各自专属档位表处理（见 src/stream.py），
# 其他平台经 get_quality_index 折叠到 BD 槽位。
def get_quality_code(qn: str) -> str:
    quality_zh_to_en = {
        "原画": "OD",
        "蓝光": "BD",
        "蓝光30M": "BD30",
        "蓝光20M": "BD20",
        "蓝光8M": "BD8",
        "蓝光4M": "BD4",
        "超清": "UHD",
        "高清": "HD",
        "标清": "SD",
        "流畅": "LD",
    }
    # 未知画质回退到 OD，避免返回 None 导致后续比较逻辑出错
    return quality_zh_to_en.get(qn, "OD")


# 桌面 Chrome UA：虎牙/B站 等国内 CDN 会拒绝移动端 UA（返回 403），录制拉流必须用桌面 UA。
# 校验探针与 ffmpeg 录制共用同一 UA（见 get_record_user_agent），否则校验「假绿」。
# 版本对齐全库基准 Chrome/141（见 room.DESKTOP_UA），避免 UA 指纹过旧被风控标记。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 移动端 UA：与 main.py ffmpeg 录制命令的默认 UA 保持一字不差——探针若改发 httpx 默认 UA，
# 部分 CDN（斗鱼 hwa 实测）会对 GET 偶发 403 而 ffmpeg 带移动 UA 拉流正常，
# 故校验与录制两端 UA 必须完全一致。
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
    # 虎牙 HLS/FLV 防盗链：实测虎牙 CDN 现已反向校验——携带 Referer 的请求一律 403，
    # 不携带时 HS 线路 GET 200 正常拉流（AL/TX 仍可能因房间未承载推流而 403，由
    # select_source_url 多 CDN 候选校验自动跳过）。故此处不下发 Referer；探针与 ffmpeg
    # 共用本函数、两端一致才能稳定拿到流。
    # B站直播 CDN（bilivideo.com）对无 Referer 的请求返回 403（content-type 空），
    # 校验器与 ffmpeg 录制共用此条目，保证两端一致地拿到流。
    "B站直播": "referer:https://live.bilibili.com/",
}


# 按 platform 返回录制拉流所需的请求头字典（合并 base 头与可选 cookie），无头时返回 None。
# base 头按平台给 referer/origin；cookies 为登录态 Cookie（B站需 buvid3），空值不注入。
# 校验探针与 ffmpeg 录制共用本函数，保证两端请求头完全一致。
def get_record_headers(platform: str, live_url: str, cookies: str | None = None) -> dict[str, str] | None:
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


# 校验探针与 ffmpeg 录制共用：虎牙/B站 用桌面 Chrome UA，其余返回 None（沿用现有移动 UA）。
def get_record_user_agent(platform: str) -> str | None:
    if platform in _DESKTOP_UA_PLATFORMS:
        return DESKTOP_UA
    return None


# GET 复核的两次探测间隔基准（秒）与抖动上限：斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针
# （HEAD→GET）会偶发 403，隔开重试才能区分「偶发限流」与「稳定拒绝」。实际间隔 =
# 基准 + uniform(0, 抖动上限)——恒定间隔是可识别的机器人节奏指纹，抖动降低被风控的概率。
_GET_RECHECK_INTERVAL = 0.8
_GET_RECHECK_JITTER = 0.7

# 同一 CDN host 相邻两次探针的最小间隔（秒）+ 抖动上限：多房间并发时各自线程可能对同一
# CDN 毫秒级连击——即上方「偶发 403」的根因。不同 host 互不影响、首次探针不等待；
# 测试可将 _PROBE_MIN_HOST_INTERVAL 置 0 关闭节流。
_PROBE_MIN_HOST_INTERVAL = 0.35
_PROBE_THROTTLE_JITTER = 0.4
_probe_last_seen: dict[str, float] = {}
_probe_throttle_lock = threading.Lock()


# 计算一次带随机抖动的重试间隔（节奏指纹依据见 _GET_RECHECK_INTERVAL 注释）；返回间隔秒数。
def _recheck_delay() -> float:
    return _GET_RECHECK_INTERVAL + random.uniform(0, _GET_RECHECK_JITTER)


# 同 host 探针节流：距上次同 host 探针不足最小间隔时补足等待（锁内计算、锁外睡眠，
# 不阻塞其它 host）。与退避互补：节流降低风控触发概率，退避在被拒后止血。
def _throttle_probe(url: str) -> None:
    host = urlsplit(url).netloc
    if not host:
        return
    wait = 0.0
    with _probe_throttle_lock:
        now = time.time()
        min_gap = _PROBE_MIN_HOST_INTERVAL + random.uniform(0, _PROBE_THROTTLE_JITTER)
        # 顺带剔除长期未探针的旧 host（对照 _probe_backoff 的过期清理）：只增不删会在
        # 60+ 平台长跑下无界增长；清掉的 host 下次按首次探针对待（不等待），语义不变
        retention = _PROBE_MIN_HOST_INTERVAL * 10
        for stale_host in [h for h, ts in _probe_last_seen.items() if now - ts > retention]:
            _probe_last_seen.pop(stale_host, None)
        last = _probe_last_seen.get(host, 0.0)
        if now - last < min_gap:
            wait = min_gap - (now - last)
        _probe_last_seen[host] = now + wait  # 登记预计发出时刻，排队中的后续探针据此排队
    if wait > 0:
        time.sleep(wait)


# 探针退避（负缓存）：虎牙 aldirect CDN 对同一路径短时间内的连续连接做限流，每轮
# 「HLS 3 连探针 + FLV 2~3 连探针 + ffmpeg 拉流」会烧光连接预算——表现为校验通过(200)
# 后 ffmpeg 立即 403，或拉流数百 KB 后被掐断，录制陷入秒级失败循环。
# 退避名单内的平台观测到 401/403（含重试后恢复的偶发拒绝，同样是限流证据）即把
# 「scheme://host/路径」记入窗口；窗口内跳过全部探针——非末位候选回退下一候选，末位候选
# 直接放行给 ffmpeg，让 ffmpeg 拿到零探针占用的干净连接预算。
# 仅对虎牙开启、绝不可扩大名单：斗鱼 hw 的偶发 403 由既有「重试一次再定罪」救回（重试即
# 206），跳过探针会让 HLS-first 退回游客态约 70 秒被掐的 FLV，属回归。
_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)
# FLV-first 平台：select_source_url 的候选尝试顺序反转为 FLV → HLS → record_url。
# 依据（虎牙真机复现）：HLS 三条 CDN 线路冷启动探针假绿——探针 200/206 而 ffmpeg 打开
# 即 403，TX/AL 在次轮探针也稳定 403；FLV 每轮稳定可用。FLV 优先把「冷启动假绿损失」
# 从约一个完整退避周期降为零，FLV 不可用时仍按序回退 HLS。
# 斗鱼绝不加入：游客态 FLV 长连接约 70 秒被 CDN 掐断，必须 HLS 优先。
_FLV_FIRST_PLATFORMS = ("虎牙直播",)
# 退避窗口下限（秒）。实际窗口由 _probe_backoff_window() 计算，必须 ≥ 一个主循环周期。
_PROBE_BACKOFF_SECONDS = 60.0
# 覆盖主循环间隔的余量（秒）：单轮等待 = delay_default + 抖动(±5s)，错误窗口满 5 次时再
# +60s，故取 70s 覆盖「完整周期 + 抖动 + 最坏错误加成」。偏长代价很小（末位候选本就放行
# 给 ffmpeg，录制成功还会立即清除），偏短代价是假绿死循环——宁长勿短。
_PROBE_BACKOFF_INTERVAL_MARGIN = 70.0
_probe_backoff: dict[str, float] = {}
_probe_backoff_lock = threading.Lock()


# 退避窗口必须至少跨过一个主循环周期，否则闭环恒不成立：固定 60s 而 delay_default 默认
# 120s 时，ffmpeg 快速失败记入退避后下一轮在 T+124s 才到，早已出窗，于是又去撞同一条死线路。
def _probe_backoff_window() -> float:
    interval = float(main.delay_default or 0)
    return max(_PROBE_BACKOFF_SECONDS, interval + _PROBE_BACKOFF_INTERVAL_MARGIN)


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
    window = _probe_backoff_window()
    with _probe_backoff_lock:
        for stale in [k for k, ts in _probe_backoff.items() if now - ts > window]:
            _probe_backoff.pop(stale, None)
        _probe_backoff[key] = now


# 撤销一次退避记录：该地址已被实际拉流验证可用（录制成功），先前的拒绝（探针假绿或
# 偶发限流）已解除。不清除会让明明恢复的线路在窗口内继续被跳过、白白回退到次优线路。
def _clear_probe_reject(url: str, platform: str | None) -> None:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return
    key = _probe_backoff_key(url)
    with _probe_backoff_lock:
        _probe_backoff.pop(key, None)


# 查询 url 是否处于探针退避窗口内（仅对退避名单内平台生效）。
def _probe_in_backoff(url: str, platform: str | None) -> bool:
    if platform not in _PROBE_BACKOFF_PLATFORMS:
        return False
    with _probe_backoff_lock:
        ts = _probe_backoff.get(_probe_backoff_key(url))
        return ts is not None and time.time() - ts <= _probe_backoff_window()


# ffmpeg 录制侧的反馈入口：与探针侧共用同一份实现（同一白名单、同一退避键）。
# 录制「快速失败」（输入打开即被拒，如探针 200/206 而 ffmpeg GET 403）时把实际拉流地址
# 记入退避，下轮选源即跳过——「探针假绿」在探针侧永远观测不到（客户端指纹不同），
# 不标记就成了「探针通过→录制被拒→下轮探针仍通过」的死循环；录制成功则立即撤销退避。
mark_ffmpeg_reject = _mark_probe_reject
clear_ffmpeg_reject = _clear_probe_reject


# 判定流地址是否为 h265 编码：候选过滤、record_url 兜底与 stream.py 的 h264 备选收集
# 三处共用的单一实现，避免口径漂移。是否可直拷取决于输出容器，见 _h265_copy_format_supported。
# 原实现只认 `codec[0] == "h265"`，而抖音侧（stream.py）用的是大小写不敏感的
# 「h265 / hevc 都算」——同一条流两处口径不同：平台下发 `HEVC` / `H265` 时本侧不剔除，保存 FLV/纯音频
# 仍把 HEVC 候选交付 ffmpeg 直拷，录制失败或产物异常。现收敛为同一判据：小写比较、同时识别 hevc。
def _is_h265(url: str) -> bool:
    codec = utils.get_query_params(url, "codec")
    return isinstance(codec, list) and bool(codec) and codec[0].strip().lower() in ("h265", "hevc")


# 判定当前「视频保存格式」的容器能否直拷（-c copy）HEVC 流：TS/MKV/MP4 三个 muxer 均
# 支持；FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展，仓库口径不支持）与 MP3/M4A 纯音频格式
# 不支持。取值经 main 的全局 video_save_type 惰性读取，仍做 strip+upper 以覆盖配置加载
# 前的小写默认值；缺失/非字符串一律按「不支持」处理，保住 h265 过滤的保守语义。
def _h265_copy_format_supported() -> bool:
    raw = getattr(main, "video_save_type", "")
    fmt = raw.strip().upper() if isinstance(raw, str) else ""
    return fmt in ("TS", "MKV", "MP4")


# 可交给 ffmpeg `-i` 的流地址协议白名单（MID-19）。rtmp/rtmps 是合法用例
# （斗鱼 rtmp 拼接、部分海外平台仍下发 rtmp），故不能简单要求 http(s)。
_ALLOWED_STREAM_SCHEMES = frozenset({"http", "https", "rtmp", "rtmps"})


# 判定 url 是否具备「可以进 ffmpeg -i」的最小形态：协议在白名单内 + 主机名非空 + 不以 '-' 开头。
def _is_recordable_url(url: str) -> bool:
    # 末位候选（last_resort）的放行语义只针对「网络 / CDN 拒绝」，但它原先对任何异常都
    # 成立。远端可控的 file:///…、concat:…、相对路径或以 '-' 开头的串会被当成「探针异常但
    # 末位可用」直接塞进 -i：前者把本地文件读进录制产物，后者是 ffmpeg 选项注入。
    # 一律告警丢弃，不享受末位放行。
    if not url or url.startswith("-"):
        return False
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        # 含裸空格/控制字符的串 httpx 会以 InvalidURL 抛错（末位放行就等于把它请进 ffmpeg）；
        # 合法流地址从不含裸空格（查询参数一律百分号编码），无需为此形态开绿灯
        return False
    try:
        parts = urlsplit(url)
        # 显式访问一次 .port：urlsplit 对端口是**惰性**校验的，非法端口只有取属性才抛错
        _ = parts.port
    except ValueError:
        # 非法端口 / 其他 InvalidURL 形态
        return False
    return parts.scheme.lower() in _ALLOWED_STREAM_SCHEMES and bool(parts.netloc)


# 单次探针的超时秒数（HEAD / Range-GET / GET 复核共用）
_PROBE_TIMEOUT_SECONDS = 5


# 探针同步客户端的唯一构造点：两处调用（_validate_stream_url 自建分支、select_source_url
# 整轮共用）都必须经此工厂，逐跳复检钩子才能统一挂上——否则「公网 URL → 302 → 内网」会被
# 照着跟进去，并把落地 status_code / content-type 回显进日志。新增第三处裸构造会被
# tests/test_sync_probe_internal_guard.py 的 AST 结构锁挡住。
# proxy_addr 必须由调用方在传入前经 utils.handle_proxy_addr 归一，本工厂不做二次归一。
# 作用域仍是单次选源 + finally 关闭，不按 (proxy, verify) 做模块级缓存：常驻 keepalive
# 会与 ffmpeg 拉流争抢虎牙 CDN 的连接预算。
def _probe_client(timeout: int, proxy_addr: str | None, verify: bool) -> httpx.Client:
    # 钩子工厂与判定都来自 src.async_http，本模块不另写一份。函数内 import 而非模块级：
    # 本模块有模块级 import main、main 又 import 本模块，新增模块级出边会改变初始化顺序；
    # 本函数每轮选源只走 1~2 次，多一次已缓存的 sys.modules 查找没有成本。
    from src.async_http import build_sync_hop_guard

    return httpx.Client(
        timeout=timeout,
        proxy=proxy_addr,
        verify=verify,
        event_hooks={"response": [build_sync_hop_guard(proxy_addr)]},
    )


# ── 探针读取响应体必须有上限，且是唯一入口 ────────────────────────────────
# 四处探针此前一律走 client.get()（httpx 会把响应体一次性读满），而后两处只看状态码、
# 正文一个字节都不需要。风险面在于 Range 只是请求：不遵守 Range 的边缘节点会把 .ts 当
# 整段流媒体一直发，80+ 房间并发时是无界内存，日志上一条都看不出来。
# 真实播放列表正文远小于 64 KB（实测约 2~8 KB），取满即截断也够解析末行分片。
_PROBE_BODY_LIMIT = 65_536


class _ProbeResponse:
    # 探针读取结果：只暴露判定与日志要用的三个字段。刻意不直接返回 httpx.Response——
    # 那会让调用方以为正文是全量（本函数的 text 可能是被上限截断过的）。
    def __init__(self, status_code: int, headers: Mapping[str, str], text: str) -> None:
        self.status_code = status_code
        self.headers = headers
        self.text = text


def _bounded_probe_get(
    client: httpx.Client,
    url: str,
    headers: Mapping[str, str],
    *,
    read_body: bool = True,
    body_limit: int = _PROBE_BODY_LIMIT,
) -> _ProbeResponse:
    # 流式打开、最多读 body_limit 字节即断开。判定所需的 status_code / headers 与
    # client.get() 一致，不改任何判定分支（200/206 基线、401/403 重试一次再定罪、末位放行、
    # 退避与节流一律留在调用点）。三条约束：
    # ① 逐跳内网复检：response 钩子在响应头到达时触发，RedirectHopRejected 仍原样抛到调用点
    #    的 except 分支——本函数刻意不接任何异常，接了就等于把安全拒绝喂给「维持可达」兜底。
    # ② 客户端仍是调用方手里那一支，不新建、不升级为模块级缓存。
    # ③ 提前断开由 httpcore 丢弃，keepalive 配置未动；「只读状态码不读正文」已由
    #    _confirm_get_ok 跑在生产链路上。
    with client.stream("GET", url, headers=dict(headers), follow_redirects=True) as resp:
        if not read_body:
            return _ProbeResponse(resp.status_code, resp.headers, "")
        chunks: list[bytes] = []
        total = 0
        for chunk in resp.iter_bytes():
            chunks.append(chunk)
            total += len(chunk)
            if total >= body_limit:
                break
        raw = b"".join(chunks)[:body_limit]
        if not raw:
            return _ProbeResponse(resp.status_code, resp.headers, "")
        # 解码口径与改前读的 httpx Response.text 一致：charset 头优先、否则 utf-8、errors=replace
        encoding = resp.encoding or "utf-8"
        return _ProbeResponse(resp.status_code, resp.headers, raw.decode(encoding, errors="replace"))


# ── 正文派生的第二跳请求（变体列表 / 媒体分片）的边界 ──────────────────────
# urljoin 对绝对 URL 会整体丢弃 base，播放列表正文里的一行就能把下一跳指到任意 host；
# 而 headers 里带着用户 Cookie。httpx 只在重定向跨源时自动剥 Cookie，对「新起的第二跳
# 请求」不做任何处理——一个被劫持的 m3u8 即可让本机带着登录态向任意 host 发 GET。
# 故派生地址先过形态白名单与非内网判定，再按「是否与列表同域」决定是否带 Cookie。

# 内网 / 本机 / 链路本地目标的判定。只判字面量、不做 DNS 解析：探针每轮对多候选执行，解析既多
# 一个可被远端操纵的攻击面，也多一段不可控延迟。
#
# 原实现是「字面量前缀」正则，实测四类写法全部漏网——`2130706433`（整数字面量）、
# `0177.0.0.1`（八进制）、`::ffff:127.0.0.1`（IPv4-mapped IPv6）、`100.64.0.1`（CGNAT）：它们最终都被
# 解析成 127.0.0.1 / CGNAT 目标，却没有一个以 `127.` 这类前缀开头。现按结构化判定，就地升级、不新建
# 模块（判据族仍只有一份事实源）。只保留「本机名」这条名字判定，且改为全等而非前缀——原正则的
# `localhost` 前缀（LOCALHOST 后接任意串命中）与 `0.` 前缀（0.evil.com 命中）都是假阳性。
_PRIVATE_HOST_EXACT = frozenset({"localhost"})
# CGNAT 100.64.0.0/10：3.14 的 is_private 不再覆盖它，但它是运营商级 NAT 地址、云上常见元数据代理落点，
# 同样不该由播放列表正文把探针引过去。
_CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")
_IPV4_HOST_PATTERN = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


def _aton_part(part: str) -> int | None:
    # inet_aton 的单段解析（十进制 / 0x 十六进制 / 0 前缀八进制）；空段、非法字符、越界一律 None。
    if not part:
        return None
    low = part.lower()
    if low.startswith("0x"):
        body, base = low[2:], 16
    elif part[0] == "0" and len(part) > 1:
        body, base = part[1:], 8
    else:
        body, base = part, 10
    try:
        return int(body, base)
    except ValueError:
        return None


def _ipv4_from_aton(host: str) -> ipaddress.IPv4Address | None:
    # `2130706433` / `0177.0.0.1` / `127.1` / `0x7f.0.0.1` 这些写法 glibc 与 Windows 都会还原成
    # 127.0.0.1，而 ipaddress 只认点分十进制——不在此归一，它们就只是「一个看起来不像 IP 的主机名」。
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    total = 0
    last = len(parts) - 1
    for i, part in enumerate(parts):
        value = _aton_part(part)
        if value is None:
            return None
        if i < last:
            # 非末段各占一个字节（大端），末段独占剩余 1~4 个字节
            if value > 0xFF:
                return None
            total |= value << (8 * (3 - i))
        elif value >= 1 << (8 * (5 - len(parts))):
            return None
        else:
            total |= value
    return ipaddress.IPv4Address(total)


def _literal_address(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    # 主机名是 IP 字面量（含缩写形态）时返回地址对象；urlsplit().hostname 已去掉 IPv6 方括号，
    # 此处只需再剥掉 %zone（fe80::1%eth0 与 fe80::1 是同一目标）。解析不出返回 None。
    name = host.split("%", 1)[0]
    try:
        return ipaddress.ip_address(name)
    except ValueError:
        return _ipv4_from_aton(name)


def _is_internal_host(host: str) -> bool:
    # 与 async_http 入口那道内网闸（web_config._host_internal_reason）的口径对齐：回环 / 私网 / 链路
    # 本地（含 169.254 云元数据）/ 未指定 / 组播 / 保留 / CGNAT 一律拒。IPv4-mapped IPv6 按其承载的 v4
    # 判定，否则 ::ffff:127.0.0.1 在 v6 侧会被当成公网。**未经结构化的主机名一律放行**：本层只做
    # 「离线即可定罪」的字面量判定（承上方「不做 DNS 解析」的既有取舍），泛域名由逐跳复检钩子兜。
    name = host.strip().rstrip(".").lower()
    if not name:
        return False
    if name in _PRIVATE_HOST_EXACT:
        return True
    addr = _literal_address(name)
    if addr is None:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr.is_loopback or addr.is_private or addr.is_link_local or addr.is_unspecified or addr.is_multicast:
        return True
    if addr.is_reserved:
        return True
    return isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT_NETWORK


# 派生地址是否允许发出：形态合规（_is_recordable_url）且不是内网/本机目标。
def _is_derived_hop_allowed(url: str) -> bool:
    if not _is_recordable_url(url):
        return False
    host = urlsplit(url).hostname or ""
    return not _is_internal_host(host)


# 播放列表正文派生的地址命中安全闸时抛出的内部控制流异常。
#
# 必须是异常而不是 return False：`_probe_hls_segment` 的 bool 同时承载「分片不可达」与
# 「安全闸拒绝」两种语义，而调用方对前者的处理是「末位候选仍交由 ffmpeg 尝试」——把安全
# 拒绝编码成 False 就让它继承末位放行语义，内网地址最终仍被交给 ffmpeg -i。异常与控制流
# 分开后，安全结论不参与可达性推断，也不会被任何兜底分支翻回 True。
# 与 async_http.RedirectHopRejected 同族（那是重定向链上的逐跳复检），本类只覆盖正文派生
# 的第二跳；两者都不穿透给最终调用方，只用于在本模块内定级。
class _DerivedHopRejected(Exception):
    def __init__(self, hop_url: str, reason: str) -> None:
        super().__init__(f"{reason}: {hop_url}")
        self.hop_url = hop_url
        self.reason = reason


# 公共后缀表：原实现把「末两段」当注册域，`.co.kr` / `.com.cn` / `.co.uk` /
# `.com.br` 这类**公共后缀本身含两段**的域上，`a.example.co.kr` 与 `evil.co.kr` 的「注册域」都是
# `co.kr`，于是被判同域、沿用原请求头→本机带平台 Cookie 向同公共后缀的任意主机发 GET。本仓覆盖的
# PandaTV / FlexTV 正是 `.co.kr` 域，该分支极易命中。
# 取向是**保守**：只内置「两段及以上的公共后缀」——漏登记一条的后果只是多剥一次 Cookie（少一次带凭据
# 探测），错登记的后果才是凭据外泄，故宁可多列。单段后缀（com/cn/kr/io…）「末两段」本身就是注册域，
# 不需要登记。
_TWO_LEVEL_PUBLIC_SUFFIXES = frozenset(
    "ac.cn com.cn edu.cn gov.cn net.cn org.cn "
    "co.kr ne.kr or.kr re.kr pe.kr go.kr "
    "co.uk org.uk ac.uk gov.uk me.uk ltd.uk plc.uk net.uk sch.uk "
    "com.br net.br org.br gov.br edu.br "
    "com.tw net.tw org.tw idv.tw "
    "com.hk net.hk org.hk edu.hk gov.hk "
    "co.jp ne.jp or.jp ac.jp go.jp "
    "com.sg net.sg org.sg edu.sg "
    "com.my net.my org.my "
    "co.th in.th or.th ac.th "
    "com.vn net.vn org.vn "
    "co.id or.id ac.id web.id "
    "com.ph net.ph org.ph "
    "com.au net.au org.au edu.au gov.au "
    "co.nz net.nz org.nz "
    "co.in net.in org.in firm.in "
    "com.tr net.tr org.tr "
    "com.ar com.mx com.co com.pe com.ve com.ec com.uy com.py com.bo "
    "co.za org.za web.za "
    "com.ua com.ru com.pl com.de "
    "com.es com.pt com.it com.fr "
    "com.sa com.ae com.eg "
    "co.il com.pk com.bd com.np com.lk "
    "com.ng co.ke co.tz "
    "com.kw com.qa com.om com.bh com.jo com.lb "
    "com.cy com.gr com.hr com.ro com.cz com.sk com.hu com.bg com.rs "
    "com.mt com.is com.lu com.be com.nl com.at com.ch "
    "com.se com.no com.dk com.fi com.ie".split()
)


# 取主机名的近似注册域（末两段，公共后缀含两段时再多取一段：a.b.example.co.kr → example.co.kr）。
# 单段/双段主机名与 IPv4 字面量返回 ""：双段时「同域与否」已由 host 全等比较覆盖，
# 此时返回有效值只会让 example.com 与 evil.com 这类不同域被误判为同域。
def _registrable_domain(host: str) -> str:
    if _IPV4_HOST_PATTERN.fullmatch(host):
        return ""
    labels = host.split(".")
    if len(labels) < 3:
        return ""
    if ".".join(labels[-2:]) in _TWO_LEVEL_PUBLIC_SUFFIXES:
        # 末两段是公共后缀：注册域要退到前三段。三段时（example.co.kr）退位后只剩两段，与「末两段
        # 比较」等价——此时同域判据不可能比 host 全等更紧，返回 "" 让调用方走剥 Cookie 的保守分支。
        if len(labels) < 4:
            return ""
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


# 派生地址与播放列表是否同 host 或同注册域
def _is_same_probe_scope(base_url: str, derived_url: str) -> bool:
    base_host = (urlsplit(base_url).hostname or "").lower()
    derived_host = (urlsplit(derived_url).hostname or "").lower()
    if not base_host or not derived_host:
        return False
    if base_host == derived_host:
        return True
    base_domain = _registrable_domain(base_host)
    return bool(base_domain) and base_domain == _registrable_domain(derived_host)


# 剥掉 cookie 头：是否携带的唯一判据是「与播放列表是否同域」，不由跳转形态决定。
def _headers_without_cookie(headers: Mapping[str, str]) -> dict[str, str]:
    return {name: value for name, value in headers.items() if name.lower() != "cookie"}


# 派生地址这一跳实际使用的请求头：同域沿用原头，跨域只剥 Cookie、继续探测（凭据外泄面
# 已消除）。不能「跨域即跳过」——分片 host 常与列表 host 跨注册域（斗鱼 hw3a…douyucdn2.cn
# → f19c…livehwc4.com），跳过会把「列表 200、分片 404 判假绿」的能力整体废掉。
def _headers_for_derived_hop(base_url: str, derived_url: str, headers: Mapping[str, str]) -> dict[str, str]:
    if _is_same_probe_scope(base_url, derived_url):
        return dict(headers)
    logger.debug(
        i18n.tr(
            "HLS 播放列表派生的地址与列表不同域，已剥离 Cookie 后继续探测: {url}",
            url=utils.mask_credentials(derived_url),
        )
    )
    return _headers_without_cookie(headers)


# master playlist 变体属性行里的带宽字段（MIN-03）。src/spider.py 另有一份同名模式用于
# HLS 带宽解析，两处用途不同（一处解析接口 JSON/文本、一处解析播放列表），刻意不共享，
# 避免 spider 的解析口径漂移影响到探针选路。
_BANDWIDTH_PATTERN = re.compile(r"BANDWIDTH=(\d+)")


# 从 master playlist 正文里挑出「应当探测」的变体 URL：按 BANDWIDTH 取最高码率档。
# HLS 规范不要求变体按带宽降序（不少生成器升序列出、最低档在前），跟随首个变体会出现
# 「探到最低档分片、ffmpeg 实际拉最高档」的假绿偏差；反向情形则会误杀可用源。
# 返回 None 表示取不到任何变体 URL（调用方按「解析不出」保守放行）。
def _pick_master_variant(text: str, base_url: str) -> str | None:
    variants: list[tuple[int, str]] = []
    pending_bw: int | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            # 只认 #EXT-X-STREAM-INF（#EXT-X-I-FRAME-STREAM-INF 不带后继 URL，不参与）
            if line.startswith("#EXT-X-STREAM-INF"):
                bw_match = _BANDWIDTH_PATTERN.search(line)
                pending_bw = int(bw_match.group(1)) if bw_match else None
            continue
        # 缺 BANDWIDTH 的变体记 -1：任何带带宽的变体都优先于它，全缺时按出现序取首个
        variants.append((pending_bw if pending_bw is not None else -1, urljoin(base_url, line)))
        pending_bw = None
    if not variants:
        return None
    best_bw = max(bw for bw, _ in variants)
    return next(u for bw, u in variants if bw == best_bw)


# HLS 播放列表可达 ≠ 可录制：媒体分片必须单独探测（斗鱼 hw CDN 实测事故）。
# 事故形态：播放列表恒 200（CDN 动态合成），但边缘节点上所有 .ts 分片 404——ffmpeg 拉列表
# 成功后逐分片 404，hls demuxer 无限「Segment failed too many times」循环：零字节产出、
# 进程常驻、-loglevel error 下零输出，生产表现即「只出弹幕 SRT、无视频文件」。
# 流程：GET 播放列表 → master playlist 跟随带宽最高的变体（见 _pick_master_variant）→ 取
# 末行分片（最新，避开已滚出窗口的旧分片误杀）→ Range bytes=0-0 GET 探测。
# 判定原则（保守优先，不误杀可用源）：分片 200/206 → 真可达；分片明确 4xx/5xx → 列表
# 假绿，判不可达；任何解析不出分片（空列表 / 非 .ts|.mp4 行 / 子列表取不到 / 探测异常）→
# 维持「列表可达」，交由 ffmpeg 定夺。401/403 按「重试一次再定罪」处理，404 不重试。
# 日志一律把 URL 过 utils.mask_credentials：列表与分片地址都挂有 wsAuth / signature 凭据。
def _probe_hls_segment(
    client: httpx.Client,
    playlist_url: str,
    headers: Mapping[str, str],
    platform: str | None = None,
) -> bool:
    media_url = playlist_url
    media_lines: list[str] = []
    # 函数内 import 的理由见 _probe_client
    from src.async_http import RedirectHopRejected

    try:
        resp = _bounded_probe_get(client, playlist_url, headers)
        if resp.status_code != 200:
            return True  # 列表 GET 失败（HEAD/Range-GET 已通过）——不据此推翻，交由 ffmpeg
        text = resp.text or ""
        # 正文经 _bounded_probe_get 有界读取；解析不出分片时仍走下方「维持列表可达」分支。
        # master playlist 跟随带宽最高的变体，最多两层（覆盖斗鱼 hw 的「变体→子列表」形态）。
        for _ in range(2):
            if "#EXT-X-STREAM-INF" not in text:
                break
            variant_url = _pick_master_variant(text, media_url)
            if not variant_url:
                return True  # 只有标签行、取不到变体 URL——解析不出分片，保守维持列表可达
            # 正文派生地址先过形态/内网闸，再按同域与否裁决 Cookie
            if not _is_derived_hop_allowed(variant_url):
                logger.warning(
                    i18n.tr(
                        "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                        url=utils.mask_credentials(variant_url),
                    )
                )
                # 安全闸拒绝是确定性失败，不是「解析不出分片」的保守兜底——维持可达等于把内网
                # 地址经播放列表正文交给 ffmpeg -i。抛内部异常而非 return False：后者会被调用方
                # 的 last_resort 分支翻回「仍交由 ffmpeg 尝试」，安全结论形同虚设。
                raise _DerivedHopRejected(variant_url, "变体列表地址形态不合规/指向内网")
            sub = _bounded_probe_get(
                client,
                variant_url,
                _headers_for_derived_hop(playlist_url, variant_url, headers),
            )
            if sub.status_code != 200:
                return True  # 子列表取不到——保守，不下分片结论
            media_url = variant_url
            text = sub.text or ""
        media_lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
        if not media_lines:
            return True  # 空列表（直播刚结束/未推流）——无分片可探，维持列表可达结论
        seg_line = media_lines[-1]
        is_media = seg_line.endswith((".ts", ".mp4", ".m4s")) or any(
            ext + "?" in seg_line for ext in (".ts", ".mp4", ".m4s")
        )
        if not is_media:
            return True  # 非标准分片行（加密/自定义格式）——解析不出，保守放行
        seg_url = urljoin(media_url, seg_line)
        # 分片地址同样由正文派生：先过形态/内网闸，再按同域与否裁决 Cookie
        # （对照基准是本轮校验的播放列表 url，而不是可能已跨域的 media_url）。
        if not _is_derived_hop_allowed(seg_url):
            logger.warning(
                i18n.tr(
                    "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                    url=utils.mask_credentials(seg_url),
                )
            )
            # 与变体派生跳同判据：安全闸拒绝判候选失败，抛内部异常以脱离 last_resort 放行。
            raise _DerivedHopRejected(seg_url, "媒体分片地址形态不合规/指向内网")
        seg_headers = _headers_for_derived_hop(playlist_url, seg_url, headers)
    except _DerivedHopRejected:
        # 安全拒绝必须先于通用兜底上抛：下面的 except Exception 会把它当「探测异常」并按
        # 「列表可达」处理（return True），正是本条要消灭的形态。
        raise
    except RedirectHopRejected:
        # 「保守维持列表可达」的兜底都不得吞掉内部控制流异常——维持可达等于把内网地址交给
        # ffmpeg；原样上抛，由 _validate_stream_url 统一收敛成「本候选校验失败」。
        raise
    except Exception as e:
        logger.debug(
            i18n.tr(
                "HLS 分片探测解析异常(按列表可达处理): {url} - {type_name}: {e}",
                url=utils.mask_credentials(playlist_url),
                type_name=type(e).__name__,
                e=e,
            )
        )
        return True
    probe_status: int | None = None
    for attempt in range(2):
        # 同 host 探针节流（分片 host 常与列表 host 不同）；并发探测同一边缘 host 存在
        # 毫秒级连击的风控面。
        _throttle_probe(seg_url)
        try:
            seg_resp = _bounded_probe_get(client, seg_url, {**seg_headers, "Range": "bytes=0-0"}, read_body=False)
        except RedirectHopRejected:
            # 同上，不得吞掉内部控制流异常。绝不能改成 pass：seg_url 分支被跳过后下一句
            # 引用未赋值的 seg_resp，UnboundLocalError 会被外层当成「探测异常」吞掉，
            # 末位候选于是 return True 把内网地址交给 ffmpeg。
            raise
        except Exception as e:
            logger.debug(
                i18n.tr(
                    "HLS 分片探测异常(按列表可达处理): {url} - {type_name}: {e}",
                    url=utils.mask_credentials(seg_url),
                    type_name=type(e).__name__,
                    e=e,
                )
            )
            return True
        if seg_resp.status_code in (200, 206):
            if attempt:
                logger.debug(
                    i18n.tr(
                        "HLS 分片探测重试通过({status_code})，先前拒绝为偶发: {url}",
                        url=utils.mask_credentials(seg_url),
                        status_code=seg_resp.status_code,
                    )
                )
            return True
        probe_status = seg_resp.status_code
        if seg_resp.status_code in (401, 403):
            # 退避键必须是播放列表 URL：_probe_in_backoff 查的就是候选本身，而分片地址每轮
            # 滑动，记成分片 URL 会得到一条永不被读到的死条目。
            _mark_probe_reject(playlist_url, platform)
            if attempt == 0:
                time.sleep(_recheck_delay())
                continue
        break  # 404 等确定性拒绝不重试
    logger.warning(
        i18n.tr(
            "HLS 播放列表可达但媒体分片不可达({status_code})，列表层为假绿: {url}",
            url=utils.mask_credentials(seg_url),
            status_code=probe_status,
        )
    )
    return False


# FLV/record_url 源 HEAD 通过后的 GET 复核（流式请求、不读 body）：虎牙等 CDN 出现过
# HEAD=200 而 GET=403——校验「假绿」后 ffmpeg 打开即 403。ffmpeg 拉流是无 Range 的全量 GET，
# 复核必须与之完全一致（斗鱼 hwa 曾对 Range-GET 偶发 403，带 Range 反而误杀）。
# 仅拿到明确拒绝状态码（401/403）时推翻 HEAD 结论，且先原样重试一次再定罪；其余异常
# （超时等）不推翻。last_resort=True 时两次均拒绝也只告警放行，交由 ffmpeg 定夺
# （httpx 与 ffmpeg 客户端指纹不同，存在探针 403 而 ffmpeg 可正常拉流的实例）。
def _confirm_get_ok(
    client: httpx.Client,
    url: str,
    head_status: int,
    headers: Mapping[str, str],
    last_resort: bool = False,
    platform: str | None = None,
) -> bool:
    reject_status: int | None = None
    from src.async_http import RedirectHopRejected

    for attempt in range(2):
        try:
            # headers 逐请求显式传入：客户端在多个候选间复用，挂在 client 上会互相污染
            with client.stream("GET", url, headers=headers, follow_redirects=True) as probe:
                if probe.status_code not in (401, 403):
                    if attempt:
                        logger.debug(
                            i18n.tr(
                                "流地址校验: {url} - GET 复核重试通过({status_code})，先前拒绝为偶发",
                                url=utils.mask_credentials(url),
                                status_code=probe.status_code,
                            )
                        )
                    return True
                reject_status = probe.status_code
                # 偶发 403 即使重试恢复也是限流证据：记录退避，下一轮让 ffmpeg 直连
                _mark_probe_reject(url, platform)
        except RedirectHopRejected:
            # 「异常不推翻 HEAD 结论」的分支不能接住内部控制流异常，否则「公网 HEAD 通过 →
            # 302 落在内网 → 探针判可用」；原样上抛，交 _validate_stream_url 收敛为校验失败。
            raise
        except Exception as e:
            # 异常（超时等）不推翻 HEAD 结论，但必须留痕；attempt 0 的异常可能是偶发超时，
            # 隔开后重试，两次均异常才放弃复核（HEAD 结论维持通过）。
            logger.debug(
                i18n.tr(
                    "流地址校验: {url} - GET 复核异常: {type_name}: {e}（attempt {attempt}）",
                    url=utils.mask_credentials(url),
                    type_name=type(e).__name__,
                    e=e,
                    attempt=attempt,
                )
            )
            if attempt == 0:
                time.sleep(_recheck_delay())
                continue
            return True
        if attempt == 0:
            time.sleep(_recheck_delay())
    if last_resort:
        logger.warning(
            i18n.tr(
                "流地址校验: {url} - HEAD={head_status} 通过但 GET 复核两次 {reject_status}；已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同，探针拒绝不代表 ffmpeg 不可拉流）",
                url=utils.mask_credentials(url),
                head_status=head_status,
                reject_status=reject_status,
            )
        )
        return True
    logger.warning(
        i18n.tr(
            "流地址校验失败: {url} - HEAD={head_status} 通过但 GET 复核两次 {reject_status}（CDN 稳定拒绝 GET），判定不可达",
            url=utils.mask_credentials(url),
            head_status=head_status,
            reject_status=reject_status,
        )
    )
    return False


# 探测流地址是否可用于录制：proxy_addr 为可选代理、timeout 为单次探针超时、verify 为 SSL
# 校验开关（None 取全局配置）、client 为可选复用客户端、last_resort 表示该候选已是末位。
# 语义必须与 async_http.get_response_status 保持一致：
# 1) verify 未指定时取 _http_config.get_effective_ssl_verify(platform)，由「是否启用https
#    录制」统一联动；少了这一步，用户关闭证书验证后同步校验仍严格验证书，会误判不可达。
# 2) m3u8 源 HEAD 非 2xx（含 403/404）时再做 Range-GET——抖音等 CDN 常对 HEAD 回 4xx
#    而 GET 可正常拉流，只覆盖 400/401/403/405 会漏掉 404。
# 3) 失败必须记录原因（异常类型/状态码/content-type），禁止静默吞异常。
# 4) 按 platform 透传录制请求头与 UA，否则出现「校验 200、ffmpeg 403」的假绿。
# 5) client 由 select_source_url 传入时整轮候选共用（verify/timeout/proxy 以该 client 为准）。
# 6) 本函数是「即将对候选发探针」的唯一入口，两道内网防线都落在这里：发请求前对初始 URL
#    做内网/保留目标判定，且自建/复用客户端一律带逐跳复检钩子（见 _probe_client）。命中回
#    False 且不享受末位放行——last_resort 的边界是「网络 / CDN 拒绝」，内网目标不属于这一类。
# 7) 正文派生跳命中安全闸时 _probe_hls_segment 抛 _DerivedHopRejected，本函数收敛成同样的
#    False，并把 URL 记进 security_rejected，供 select_source_url 的「复用结论」分支拒绝交付。
def _validate_stream_url(
    url: str,
    proxy_addr: str | None = None,
    timeout: int = _PROBE_TIMEOUT_SECONDS,
    verify: bool | None = None,
    platform: str | None = None,
    cookies: str | None = None,
    last_resort: bool = False,
    client: httpx.Client | None = None,
    security_rejected: set[str] | None = None,
) -> bool:
    # 函数内 import 的理由见 _probe_client（沿 async_http.py:518-521 的同一手法，模块级出边会改变
    # 本模块与 main 的初始化顺序）。RedirectHopRejected 必须是 except 可见的名字，故也在此取。
    from src.async_http import RedirectHopRejected, internal_stream_target_reason

    # 初始 URL 的内网/保留目标判定，位置三条都不能挪：
    # ① 早于 _probe_in_backoff——那条分支在「退避中 + 末位」时无条件 return True 放行给 ffmpeg；
    # ② 早于客户端构造与任何探针——命中即一个字节都不发（安全判定，不是可达性判定）；
    # ③ 与 _is_recordable_url 的形态白名单互不替代（协议形态与内网目标管的是两回事）。
    # 用 internal_stream_target_reason 而非 redirect_hop_rejection_reason：后者带 http(s) 白名单，
    # 而本模块允许 rtmp/rtmps；proxy_addr 归一前后的真值性一致，不影响「是否经代理」判断。
    internal_reason = internal_stream_target_reason(url, proxy_addr)
    if internal_reason is not None:
        logger.warning(
            i18n.tr(
                "探针拒绝内网/保留目标（疑似被篡改的流地址）: {masked_url} - {reason}",
                masked_url=utils.mask_credentials(url),
                reason=internal_reason,
            )
        )
        # S-04：把安全结论回传给调用方——「本轮已探过就复用结论」那条分支只看 probed 的真假，
        # 分不出「CDN 拒绝」与「安全拒绝」，必须靠这个集合另行把关。
        if security_rejected is not None:
            security_rejected.add(url)
        return False
    # verify 仍按原规则解析（供自建 client 时使用）；传入 client 时其值被忽略
    if verify is None:
        verify = _http_config.get_effective_ssl_verify(platform)

    headers: dict[str, str] = {}
    if platform:
        # 探针与 ffmpeg 录制共用这两个函数取头与 UA，两端一字不差（依据见上方口径 4）
        base = get_record_headers(platform, url, cookies=cookies)
        if base:
            headers.update(base)
        headers["User-Agent"] = get_record_user_agent(platform) or MOBILE_UA
    # 探针退避：该源所在 CDN 已被连续拒绝（限流中），本轮跳过全部探针。非末位候选回退下一
    # 候选；末位候选直接放行给 ffmpeg——省下的连接预算正是 ffmpeg 拉流成败的关键。
    if _probe_in_backoff(url, platform):
        if last_resort:
            logger.warning(
                i18n.tr(
                    "流地址校验: {url} - CDN 探针退避中，跳过探针直接交由 ffmpeg 拉流", url=utils.mask_credentials(url)
                )
            )
            return True
        logger.warning(
            i18n.tr("流地址校验: {url} - CDN 探针退避中，跳过本轮探针、回退下一候选", url=utils.mask_credentials(url))
        )
        return False
    # 同 host 探针节流（退避未命中才走到这里）：依据见 _PROBE_MIN_HOST_INTERVAL
    _throttle_probe(url)
    # 探针客户端：传入时在整轮候选间复用，未传入时自建自管。UA / Referer / Cookie 必须
    # 逐请求传入，不能挂到共享 client 上（httpx 的 _merge_headers 本来就是请求头覆盖 client 头）。
    owns_client = client is None
    probe_client: httpx.Client | None = client
    try:
        if probe_client is None:
            # proxy_addr 是配置项「代理地址」原文，允许裸 ip:port（由 handle_proxy_addr 补
            # scheme），而 httpx 0.28 的 Client(proxy=...) 只认带 scheme 的地址——裸串与空串
            # 一律抛 ValueError。归一只放在「构造客户端之前」这一处，各探针调用点不各自归一。
            # 构造失败由本函数已有的 except Exception 收敛为「本候选校验异常」，末位候选仍按
            # 既有口径放行给 ffmpeg；构造走 _probe_client 单点工厂以挂上逐跳复检钩子。
            proxy_addr = utils.handle_proxy_addr(proxy_addr)
            probe_client = _probe_client(timeout, proxy_addr, verify)
        response = probe_client.head(url, headers=headers, follow_redirects=True)
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code in (401, 403):
            _mark_probe_reject(url, platform)
        # m3u8 源：抖音等 CDN 对 HEAD 常回 4xx（如 405）+ text/html，但 GET 实际可拉流，故优先
        # 做 Range-GET 探测，绕过 HEAD 不可靠的 content-type/状态码。扩展名按小写判定——大写
        # .M3U8 会漏掉 Range-GET、被 HEAD 的 4xx 直接判成不可达。
        if ".m3u8" in url.lower():
            if response.status_code == 200 or any(
                k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")
            ):
                # 列表 200 ≠ 可录制：必须补分片层探测（_probe_hls_segment 内部保守判定，
                # 解析不出分片时维持「可达」结论）。
                if _probe_hls_segment(probe_client, url, headers, platform=platform):
                    return True
                # 分片明确不可达（假绿）：非末位候选回退下一候选（如 FLV）；
                # 末位候选保持「探针拒绝 ≠ ffmpeg 不可拉流」的既有放行语义。
                if last_resort:
                    logger.warning(
                        i18n.tr(
                            "流地址校验: {url} - HLS 媒体分片不可达；已无备选源，仍交由 ffmpeg 尝试",
                            url=utils.mask_credentials(url),
                        )
                    )
                    return True
                return False
            # Range-GET 401/403 先隔 _recheck_delay() 重试一次再定罪（连击偶发 403、片刻后重试
            # 即 200，属探针误杀）。HLS 须尽力救回——斗鱼游客态 FLV 长连接约 70 秒被掐断。
            probe: _ProbeResponse | None = None  # 失败路径（last_resort/告警）需 Range-GET 结果；先置 None 避免未绑定
            for attempt in range(2):
                # 显式合并 headers 与 Range：客户端在候选间复用，Range 只能作为请求级头附加，
                # 不能覆盖 UA/Referer/Cookie。本跳只看状态码（read_body=False），不读正文。
                probe = _bounded_probe_get(probe_client, url, {**headers, "Range": "bytes=0-0"}, read_body=False)
                if probe.status_code in (200, 206):
                    if attempt:
                        logger.debug(
                            i18n.tr(
                                "流地址校验: {url} - Range-GET 重试通过({status_code})，先前拒绝为偶发",
                                url=utils.mask_credentials(url),
                                status_code=probe.status_code,
                            )
                        )
                    # Range-GET 拿到的 200/206 同样只是列表层，假绿成因与上方 HEAD 路径一致
                    if _probe_hls_segment(probe_client, url, headers, platform=platform):
                        return True
                    if last_resort:
                        logger.warning(
                            i18n.tr(
                                "流地址校验: {url} - HLS 媒体分片不可达；已无备选源，仍交由 ffmpeg 尝试",
                                url=utils.mask_credentials(url),
                            )
                        )
                        return True
                    return False
                if probe.status_code not in (401, 403):
                    break  # 非探针误杀类拒绝（如 404），不重试
                _mark_probe_reject(url, platform)
                if attempt == 0:
                    time.sleep(_recheck_delay())
            # 循环已至少执行一次，probe 理论上必非空；显式判空收窄类型（assert 在 -O 下
            # 会被整体剔除，且失败抛 AssertionError 而非可诊断的告警路径）。
            if probe is None:
                logger.warning(
                    i18n.tr("流地址校验: {url} - Range-GET 未取得响应，按校验失败处理", url=utils.mask_credentials(url))
                )
                return False
            if last_resort:
                logger.warning(
                    i18n.tr(
                        "流地址校验: {url} - HEAD={status_code}, Range-GET={status_code_2}；已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）",
                        url=utils.mask_credentials(url),
                        status_code=response.status_code,
                        status_code_2=probe.status_code,
                    )
                )
                return True
            logger.warning(
                i18n.tr(
                    "流地址校验失败: {url} - HEAD={status_code}, Range-GET={status_code_2}, content-type={content_type}",
                    url=utils.mask_credentials(url),
                    status_code=response.status_code,
                    status_code_2=probe.status_code,
                    content_type=probe.headers.get("content-type", ""),
                )
            )
            return False
        # 非 m3u8 源（flv/record_url）沿用 content-type 启发式；HEAD 判定通过后再做
        # GET 复核（流式），杜绝 HEAD=200/GET=403 的“假绿”（ffmpeg 实际拉流是 GET）
        if any(k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")):
            return _confirm_get_ok(
                probe_client, url, response.status_code, headers, last_resort=last_resort, platform=platform
            )
        if "text/html" in content_type or "application/json" in content_type:
            if last_resort:
                # 斗鱼 hw 对探针 HEAD 回 405+text/html（禁用 HEAD），ffmpeg 实际 GET 正常。
                # 末位候选稳定拒绝也只告警放行，避免 content-type 启发式误杀可用源。
                logger.warning(
                    i18n.tr(
                        "流地址校验: {url} - status_code={status_code}, content-type={content_type}；已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）",
                        url=utils.mask_credentials(url),
                        status_code=response.status_code,
                        content_type=content_type,
                    )
                )
                return True
            logger.warning(
                i18n.tr(
                    "流地址校验失败（返回非流媒体内容）: {url} - status_code={status_code}, content-type={content_type}",
                    url=utils.mask_credentials(url),
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )
            return False
        if response.status_code == 200:
            return _confirm_get_ok(
                probe_client, url, response.status_code, headers, last_resort=last_resort, platform=platform
            )
        if last_resort:
            # 同上：末位候选的稳定拒绝（非 200 且无法识别 content-type）仅告警放行
            logger.warning(
                i18n.tr(
                    "流地址校验: {url} - status_code={status_code}, content-type={content_type}；已无备选源，仍交由 ffmpeg 尝试（探针与 ffmpeg 客户端指纹不同）",
                    url=utils.mask_credentials(url),
                    status_code=response.status_code,
                    content_type=content_type,
                )
            )
            return True
        logger.warning(
            i18n.tr(
                "流地址校验失败: {url} - status_code={status_code}, content-type={content_type}",
                url=utils.mask_credentials(url),
                status_code=response.status_code,
                content_type=content_type,
            )
        )
        return False
    except _DerivedHopRejected as e:
        # 正文派生的变体/分片地址命中安全闸：与两条内网防线同口径——warning 级、URL 脱敏、
        # 不享受末位放行。绝不能被 except Exception 接住：那条分支在 last_resort 时 return
        # True，正好是「安全拒绝被翻回可达」的原形态。复用已登记的同一模板，不新增措辞。
        logger.warning(
            i18n.tr(
                "探针拒绝内网/保留目标（疑似被篡改的流地址）: {masked_url} - {reason}",
                masked_url=utils.mask_credentials(e.hop_url),
                reason=f"播放列表正文派生跳命中: {e.reason}（初始地址 {utils.mask_credentials(url)}）",
            )
        )
        if security_rejected is not None:
            security_rejected.add(url)
        return False
    except RedirectHopRejected as e:
        # 3xx 落地跳命中内网/保留目标（或非白名单协议）：warning 级、URL 脱敏，复用已登记模板。
        # 必须排在 except Exception 之前——落到那条分支意味着末位候选被 return True 放行，
        # 而末位放行的边界是「网络 / CDN 拒绝」，内网目标不属于这一类。
        # 返回契约不变：仍是「本候选校验失败」的 False；异常绝不穿透给调用方。
        # 残余风险同 _build_hop_guard：跳转连接已经发生，DNS 重绑定窗口本层不闭合。
        logger.warning(
            i18n.tr(
                "探针拒绝内网/保留目标（疑似被篡改的流地址）: {masked_url} - {reason}",
                masked_url=utils.mask_credentials(e.hop_url),
                reason=f"重定向逐跳复检命中: {e.reason}（初始地址 {utils.mask_credentials(url)}）",
            )
        )
        # 与上面两条安全出口一样登记进 security_rejected。只 return False 而不登记
        # 时，本地址在 probed 里只是「结论 False」，select_source_url 的 record_url 同址复用分支会把
        # 「CDN 拒绝」的语义套上去、照常交付给 ffmpeg -i——而抖音/TikTok/网易CC 的 record_url 恒等于
        # m3u8_url 或 flv_url，该分支极易命中，等于内网地址带着平台 Cookie 直接连出去。
        if security_rejected is not None:
            security_rejected.add(url)
        return False
    except Exception as e:
        # Windows 下 socket.timeout 的 str() 为空，必须带上异常类型与 URL
        logger.warning(
            i18n.tr(
                "流地址校验异常: {url} - {type_name}: {e}",
                url=utils.mask_credentials(url),
                type_name=type(e).__name__,
                e=e,
            )
        )
        # 末位候选探针异常同样仅告警放行，与本函数其余分支的「稳定拒绝在末位放行」口径
        # 一致；否则末位超时/连接异常会误杀可用源、整轮放弃录制。
        if last_resort:
            logger.warning(
                i18n.tr(
                    "已无备选源，仍交由 ffmpeg 尝试: {url}",
                    url=utils.mask_credentials(url),
                )
            )
            return True
        logger.warning(
            i18n.tr(
                "流地址校验异常（判定为不可达）: {url}",
                url=utils.mask_credentials(url),
            )
        )
        return False
    finally:
        # 仅关闭本函数自建的客户端；复用的客户端由 select_source_url 统一关闭。常驻 keepalive
        # 会与随后的 ffmpeg 拉流争抢 CDN 侧连接预算。
        if owns_client and probe_client is not None:
            try:
                probe_client.close()
            except Exception as e:
                logger.debug(i18n.tr("关闭探针客户端失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 读取 main 的 HLS 采集配置（是否启用 + 排除平台名）：两个全局在启动早期或测试替身下
# 可能缺省，直接属性访问会抛 AttributeError、使整轮选源中断且无任何日志。此处回退安全
# 默认（启用 HLS、无排除平台），并容忍逗号分隔字符串形态。返回 (是否启用, 排除平台元组)。
def _hls_selection_config() -> tuple[bool, tuple[str, ...]]:
    enabled = bool(getattr(main, "hls_collection_enabled", True))
    raw: object = getattr(main, "hls_collection_exclude_platforms", ())
    if isinstance(raw, str):
        names = raw.replace("，", ",").split(",")
    elif isinstance(raw, (list, tuple, set, frozenset)):
        names = [str(p) for p in raw]
    else:
        names = []
    return enabled, tuple(name.strip() for name in names if name.strip())


# 从 FLV 候选里找出与给定 HLS 地址「同源」的那条：部分平台（如斗鱼）把 FLV 直链按扩展名
# 替换成 m3u8 后再下发（见 src/stream.py 的 get_douyu_stream_url），二者共享同一防盗链
# token，仅容器不同。m3u8 列表 200 而分片全 404 时，同 token 的 FLV 是首选回退目标。
# 命中返回该 FLV 候选（原样），无同源返回 None。
def _same_origin_flv(hls_url: str, flv_candidates: list[str]) -> str | None:
    stem = hls_url.lower().split("?", 1)[0]
    if not stem.endswith(".m3u8"):
        return None
    target = stem[: -len(".m3u8")] + ".flv"
    for candidate in flv_candidates:
        if candidate.lower().split("?", 1)[0] == target:
            return candidate
    return None


# 选源结论单行日志：记下「最终采用哪条源、属于哪一类候选」，便于在「只出弹幕 SRT、
# 无视频」类故障里确认 ffmpeg 实际拉的是 HLS 还是 FLV。kind 为机器可读字面量，不翻译。
def _log_source_choice(platform: str | None, kind: str, url: str) -> None:
    logger.debug(
        i18n.tr(
            "选源结论: platform={platform} 采用 {kind} 源: {url}",
            platform=platform or "",
            kind=kind,
            url=utils.mask_credentials(url),
        )
    )


# 从 stream_info 挑选本轮实际录制地址：默认 HLS → FLV → record_url；FLV-first 平台
# （_FLV_FIRST_PLATFORMS，当前仅虎牙）反转为 FLV → HLS → record_url。全部不可用时返回
# None。HLS 采集排除列表命中的平台无视全局开关、恒按 FLV 采集（HLS 候选整组剔除，不作
# 回退）。record_url 通道同受该「整组剔除」语义约束（抖音/TikTok/网易CC 的 record_url
# 本身就是 m3u8）；与序列候选同址时复用本轮已探结论、不重复发探针。
# 返回给上层的地址（含末位放行）一律先过 _is_recordable_url 形态白名单。
def select_source_url(
    stream_info: Mapping[str, object],
    proxy_addr: str | None = None,
    platform: str | None = None,
    cookies: str | None = None,
) -> str | None:
    # proxy_addr 必须透传给校验器：境外平台若不走与解析阶段相同的代理路径，直连校验会
    # 超时被误判为不可达。
    # 候选合并兼容「单 m3u8_url/flv_url」旧结构与平台返回的候选列表；去重后主源在前。
    # 虎牙多 CDN 线路共享同一套防盗链参数，但仅当前承载推流的线路返回 200、其余稳定 403，
    # 故必须逐候选校验、首条可达即选用，不能固定取某条线路。
    def _as_str_list(value: object) -> list[str]:
        # 把单个 URL 或 URL 列表收敛为去空后的字符串列表（保持入参顺序）
        if isinstance(value, str) and value:
            return [value]
        if isinstance(value, list):
            return [u for u in value if isinstance(u, str) and u]
        return []

    # 配置兜底经 _hls_selection_config 读取；必须早于 record_url 通道判定——record_url
    # 是否可用同样取决于该开关。
    _hls_enabled, _hls_exclude_platforms = _hls_selection_config()
    hls_excluded = platform is not None and platform in _hls_exclude_platforms
    hls_effective_enabled = _hls_enabled and not hls_excluded

    hls_candidates = _as_str_list(stream_info.get("m3u8_url"))
    for u in _as_str_list(stream_info.get("m3u8_url_list")):
        if u not in hls_candidates:
            hls_candidates.append(u)
    flv_candidates = _as_str_list(stream_info.get("flv_url"))
    for u in _as_str_list(stream_info.get("flv_url_list")):
        if u not in flv_candidates:
            flv_candidates.append(u)
    record_url_raw = stream_info.get("record_url")
    record_url_str = record_url_raw if isinstance(record_url_raw, str) else ""
    # record_url 通道同受「HLS 整组剔除」约束：抖音/TikTok/网易CC 的 record_url 本身就是
    # m3u8，HLS 组剔除后落到 record_url 时不得再对 .m3u8 发探针，也就不能在 last_resort 下
    # 放行——否则与「HLS 探针一次都不发」的配置语义冲突。
    record_url_is_hls = ".m3u8" in record_url_str.lower()
    record_url_enabled = bool(record_url_str) and (hls_effective_enabled or not record_url_is_hls)
    hls_available = bool(hls_candidates)
    flv_available = bool(flv_candidates)
    # 回退可行性按「有效」口径判定：被 HLS 排除规则挡掉的 record_url 不构成回退，
    # 否则 m3u8-only 的排除平台会绕过快照告警、静默走到「本轮无可用源」。
    has_fallback = flv_available or record_url_enabled

    # 三类地址全为空：必须留一条日志暴露根因，否则房间永远打印「正在直播中...」却不录制。
    # 该分支不产生任何探针，先于客户端构造处理，避免无谓的连接池开销。
    if not (hls_available or has_fallback):
        logger.warning(
            i18n.tr(
                "解析结果无任何流地址（m3u8/flv/record_url 均为空），本轮放弃: {anchor_name}",
                anchor_name=stream_info.get("anchor_name") or "",
            )
        )
        return None
    if hls_available and not hls_effective_enabled and not has_fallback:
        # m3u8 存在但 HLS 采集对本平台关闭、且无 FLV/record_url 可回退：同为静默路径，
        # 必须提示而非无声跳过，两种成因各给恢复指引。
        if hls_excluded:
            logger.warning(
                i18n.tr(
                    "平台 {platform} 在 HLS 采集排除列表中，且无 FLV/record_url 可回退，本轮放弃（可将该平台移出排除列表恢复 HLS 采集）: {anchor_name}",
                    platform=platform,
                    anchor_name=stream_info.get("anchor_name") or "",
                )
            )
        else:
            logger.warning(
                i18n.tr(
                    "存在 HLS 源但 HLS 采集未启用，且无 FLV/record_url 可回退，本轮放弃（可开启 HLS 采集恢复录制）: {anchor_name}",
                    anchor_name=stream_info.get("anchor_name") or "",
                )
            )
        return None

    # proxy_addr 由 main.py 原样透传配置项「代理地址」，允许裸 ip:port，且「开关打开但地址
    # 留空」也合法。httpx 0.28 的 Client(proxy=...) 只认带 scheme 的地址，裸串/空串一律抛
    # ValueError。归一只放在构造之前这一处（_validate_stream_url 的自建分支同一函数），
    # 否则选源每轮抛穿房间线程，还持续向按 host 的熔断器投失败样本。
    proxy_addr = utils.handle_proxy_addr(proxy_addr)
    # 本轮全部候选共用一个 httpx.Client：keepalive 生效，SSLContext / 连接池只构造一次。
    # 作用域严格限制在本次选源内、finally 关闭：刻意不做全局 (proxy, verify) 缓存——常驻
    # keepalive 会占用 CDN 连接预算，与随后的 ffmpeg 拉流争抢（预算耗尽后 ffmpeg 立即 403）。
    # 构造失败收敛为 probe_client=None（本轮无可用探针客户端），而不是判成「所有候选不可达」：
    # client=None 会走 _validate_stream_url 既有的自建路径，自建再失败时由该函数记 WARNING 并
    # 按末位语义放行，故本轮恒有地址返回给 ffmpeg；且一个探针都没发出，不写探针退避表。
    # 显式赋 None 而不是只留类型标注。原先构造抛出捕获面之外的异常（ssl.SSLError /
    # OSError 等，见下方 except 的注释）时，probe_client 从未绑定，finally 里的 `if probe_client is not
    # None` 先抛 UnboundLocalError，把原始异常整个吞掉并穿透房间线程——最需要诊断信息的路径反而最没信息。
    probe_client: httpx.Client | None = None
    try:
        # 构造走 _probe_client 单点工厂，逐跳复检钩子随客户端覆盖本轮全部候选；归一仍在
        # 上方那一处，复用作用域仍是单次选源、finally 关闭。
        probe_client = _probe_client(
            _PROBE_TIMEOUT_SECONDS, proxy_addr, _http_config.get_effective_ssl_verify(platform)
        )
    # httpx.InvalidURL 直继 Exception（不是 ValueError 子类）：裸 IPv6 形态的代理会在构造期
    # 抛它，不捕获会每轮抛穿房间线程。归入「本轮无可用探针客户端」，走下方自建降级路径。
    # 捕获面补 OSError——httpx.Client 构造期还会用 verify 建 SSL 上下文，
    # 证书库异常以 ssl.SSLError（OSError 子类）形态抛出；上方注释承诺「构造失败收敛为
    # probe_client=None」的本意是覆盖全部构造失败，只捕前三个会把 ssl/OSError 系仍漏回房间线程，
    # 与 1301-1303 的设计承诺互相矛盾。
    except ValueError, TypeError, httpx.InvalidURL, OSError:
        probe_client = None
    try:
        # record_url 通道先过形态白名单——不合规直接摘掉该档（连探针都不发），也不再据此
        # 给序列末位候选发放 last_resort 资格（那等于把畸形值间接请进 ffmpeg）。
        if record_url_enabled and not _is_recordable_url(record_url_str):
            logger.warning(
                i18n.tr(
                    "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                    url=utils.mask_credentials(record_url_str),
                )
            )
            record_url_enabled = False

        def _accept_source(url: str, kind: str) -> str | None:
            # 末位放行的语义边界是「网络 / CDN 拒绝」，不是「任何异常」。平台接口被劫持时
            # 回传的 file:///…、concat:…、相对路径、以 '-' 开头的串一律告警丢弃。
            if not _is_recordable_url(url):
                logger.warning(
                    i18n.tr(
                        "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                        url=utils.mask_credentials(url),
                    )
                )
                return None
            # 交付 ffmpeg -i 前的最后一道内网闸门，与形态闸门并列、互不替代（形态白名单管协议
            # 与字符合法性，管不住 http://127.0.0.1:6379）。探针层那道判定不够：record_url 与
            # 已探候选同址时走「复用结论」分支，一个探针都不发、也就不经过探针入口判定。
            # 成本只在选中地址时一次 getaddrinfo；刻意不缓存判定结果——缓存会把一次解析供给
            # 所有请求，等于主动拉长 DNS 重绑定窗口。
            from src.async_http import internal_stream_target_reason  # 函数内 import，理由见 _probe_client

            landing_reason = internal_stream_target_reason(url, proxy_addr)
            if landing_reason is not None:
                logger.warning(
                    i18n.tr(
                        "探针拒绝内网/保留目标（疑似被篡改的流地址）: {masked_url} - {reason}",
                        masked_url=utils.mask_credentials(url),
                        reason=f"交给 ffmpeg -i 前的落地复核命中（{kind} 通道）: {landing_reason}",
                    )
                )
                return None
            _log_source_choice(platform, kind, url)
            return url

        # ---- 候选序列：按平台偏好排序（默认 HLS 优先，FLV-first 平台反转）----
        # ① h265 候选按保存格式判定，仅在不支持 HEVC 直拷时剔除；剔除后末位放行基于过滤后的
        #    序列判定，语义与旧「插入式回退」一致但不多烧 HLS 探针。
        # ② last_resort 统一为「过滤后序列的末位 且 无可用 record_url 通道」：被 HLS 整组剔除
        #    规则挡掉的 m3u8 record_url、形态不合规的 record_url 都不给前序候选发放末位资格，
        #    否则「末位放行」会绕开这两道闸门。
        flv_first = platform in _FLV_FIRST_PLATFORMS
        # 排除列表命中时 hls_effective_enabled 恒为 False：HLS 候选整组剔除、不进入序列
        hls_seq: list[tuple[str, bool]] = (
            [(u, True) for u in hls_candidates] if (hls_available and hls_effective_enabled) else []
        )
        flv_seq: list[tuple[str, bool]] = [(u, False) for u in flv_candidates]
        seq = flv_seq + hls_seq if flv_first else hls_seq + flv_seq

        # h265 候选仅在当前保存格式装不下 HEVC 直拷时剔除：TS/MKV/MP4 放行进常规序列，
        # FLV/纯音频/取值异常仍剔除（stream.py 保留的 h264 原画备选继续承担不支持格式下的兜底）
        h265_copy_ok = _h265_copy_format_supported()
        usable: list[tuple[str, bool]] = []
        for url, is_hls in seq:
            if _is_h265(url) and not h265_copy_ok:
                logger.warning(i18n.tr("h265 编码候选无法 copy 录制，跳过: {url}", url=utils.mask_credentials(url)))
                continue
            usable.append((url, is_hls))

        # 逐候选校验：失败继续下一候选；仅末位且无可用 record_url 时以 last_resort 放行。
        # 到达分组边界即意味前一类候选已全部失败，打一条回退告警。probed 记下本轮已探地址
        # 及结论，供 record_url 复用（虎牙/斗鱼的 record_url 与主 FLV 候选逐字相同，不记会
        # 把同一地址完整再探一次、白耗 CDN 连接预算）。
        probed: dict[str, bool] = {}
        # 本轮因安全闸被拒的地址：probed 的 False 同时表示「CDN 拒绝」与「安全拒绝」，而
        # record_url 复用分支对前者的语义是「照常交付」——安全拒绝绝不能继承这条语义。
        security_rejected: set[str] = set()
        prev_kind: bool | None = None
        for idx, (cand, is_hls) in enumerate(usable):
            if prev_kind is not None and is_hls != prev_kind:
                if prev_kind:
                    # 用户可见回退告警统一走 i18n（原为裸英文常量）
                    logger.warning(i18n.tr("HLS 候选校验失败，回退 FLV"))
                else:
                    logger.warning(i18n.tr("FLV 候选校验失败，回退 HLS"))
            prev_kind = is_hls
            is_last = idx == len(usable) - 1
            reachable = _validate_stream_url(
                cand,
                proxy_addr=proxy_addr,
                platform=platform,
                cookies=cookies,
                last_resort=is_last and not record_url_enabled,
                client=probe_client,
                security_rejected=security_rejected,
            )
            probed[cand] = reachable
            if reachable:
                accepted = _accept_source(cand, "HLS" if is_hls else "FLV")
                if accepted:
                    return accepted
                # 形态不合规：视同校验失败继续下一候选，绝不享受末位放行
                probed[cand] = False
            # HLS 被拒（含「列表 200 但分片 404」假绿）时，若存在同 token 的 FLV 候选，
            # 显式点名该回退目标，便于巡检确认「是否已按预期回退同源 FLV」。
            if is_hls and not probed[cand]:
                same_origin = _same_origin_flv(cand, flv_candidates)
                if same_origin:
                    # 同源 FLV 回退地址同为签名直链，必须脱敏
                    logger.warning(
                        i18n.tr(
                            "HLS 源校验失败，将回退同 token 的 FLV 源: {url}",
                            url=utils.mask_credentials(same_origin),
                        )
                    )
        if usable and record_url_enabled:
            logger.warning(i18n.tr("HLS/FLV 全部候选校验失败，尝试 record_url 兜底"))

        if record_url_enabled:
            if _is_h265(record_url_str):
                logger.warning(i18n.tr("record_url 含 h265 编码，且无 HLS/FLV 兜底可用"))
            # `not in security_rejected` 把安全拒绝挡在两条交付路径之外：复用分支若只判
            # `record_url_str in probed`，「同址探过、结论 False」会被无条件交付，而抖音/
            # TikTok/网易CC 的 record_url 恒等于 m3u8_url 或 flv_url，该分支极易命中。
            # 不额外打日志：拒绝原因已由 _validate_stream_url 按同一模板发过 warning。
            if record_url_str in probed and record_url_str not in security_rejected:
                # 同一地址本轮已探过：复用结论、零新增探针。record_url 是末位档，沿用
                # 「探针拒绝 ≠ ffmpeg 不可拉流」的语义，探针判失败也照常交由 ffmpeg 定夺。
                if not probed[record_url_str]:
                    logger.warning(
                        i18n.tr(
                            "流地址校验: {url} - 与本轮已探候选同址，复用结论并交由 ffmpeg 拉流",
                            url=utils.mask_credentials(record_url_str),
                        )
                    )
                accepted = _accept_source(record_url_str, "record_url")
                if accepted:
                    return accepted
            # record_url 是最后一档候选，恒为 last_resort：稳定拒绝也放行给 ffmpeg 定夺
            elif record_url_str not in security_rejected and _validate_stream_url(
                record_url_str,
                proxy_addr=proxy_addr,
                platform=platform,
                cookies=cookies,
                last_resort=True,
                client=probe_client,
                security_rejected=security_rejected,
            ):
                accepted = _accept_source(record_url_str, "record_url")
                if accepted:
                    return accepted
        # 整轮无可用源时补一条收束结论（逐候选告警已各自给出原因），让「房间一直不录制」
        # 在日志里有一句可检索的结论行。
        if hls_available and not hls_effective_enabled:
            # HLS 组被配置整组剔除是唯一「零日志静默丢弃」的选源成因：有 FLV/record_url 兜底
            # 时上方早退告警不触发、候选序列里也看不到 m3u8，用户只能对着「在播但不录制且
            # 无告警」猜配置原因。无源结论前必须点名并给恢复开关；选中源的轮次不打。
            logger.warning(
                i18n.tr(
                    "存在 {count} 条 m3u8 候选但 HLS 采集对本平台关闭（全局关闭或命中排除列表），"
                    "已整组静默丢弃（可开启「是否启用HLS采集(是/否)」或将平台移出「HLS采集排除平台(逗号分隔)」恢复）: {anchor_name}",
                    count=len(hls_candidates),
                    anchor_name=stream_info.get("anchor_name") or "",
                )
            )
        logger.warning(i18n.tr("选源结论: platform={platform} 本轮无可用源", platform=platform or ""))
        return None
    finally:
        # 选源结束即释放连接，把预算让给随后的 ffmpeg 拉流；构造失败时 probe_client 为
        # None（各候选已走自建路径），无连接可释放，须跳过关闭。
        if probe_client is not None:
            try:
                probe_client.close()
            except Exception as e:
                logger.debug(i18n.tr("关闭探针客户端失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 抖音接口调用限流：必要时 sleep，保证两次抖音请求间隔不小于 douyin_min_interval 秒。
def _douyin_rate_limit() -> None:
    # 在 semaphore 内部调用：串行化 + 最小间隔双重保护，避免多线程并发监控触发风控。
    with main.douyin_rate_lock:
        now = time.time()
        elapsed = now - main.douyin_last_request_time
        if elapsed < main.douyin_min_interval:
            time.sleep(main.douyin_min_interval - elapsed)
        main.douyin_last_request_time = time.time()
