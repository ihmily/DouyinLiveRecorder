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
# hls_collection_exclude_platforms / douyin_* 限流变量），通过 `import main` 在运行时惰性读取，
# 避免循环导入与 __main__ 二次执行。

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


# WD-14：文件名长度上限（字符数）。main.py 把平台 API 下发、长度不可控的标题拼进
# 「保存目录/平台/主播/日期_标题/文件名」，叠加较深的保存目录极易突破 Windows MAX_PATH(260)，
# 届时 os.makedirs / ffmpeg 输出路径都会失败，而错误只表现为一句笼统的「录制出错」。
# scripts/douyin_live_recorder_standalone.py 早有 [:60] 截断，主程序此前缺失该防线。
_MAX_NAME_CHARS = 60

# WD-14：Windows 保留设备名。同名文件/目录在 Windows 上无法创建（即使带扩展名），
# 用保留名做主播名时行为是「目录创建失败 → 录制静默失败」。
_WINDOWS_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
)


# 清洗 input_text 为合法文件名（过滤非法字符、控制字符、保留设备名、超长截断、可选去表情、
# & 换下划线）；返回清洗结果，全空时返回"空白昵称"
def clean_name(input_text: str) -> str:
    cleaned_name = re.sub(main.rstr, "_", input_text.strip()).strip("_")
    # WD-14：控制字符（0x00-0x1F）不在 rstr 的字符集内，但同样会让写盘失败
    cleaned_name = re.sub(r"[\x00-\x1f\x7f]", "_", cleaned_name).strip("_")
    cleaned_name = cleaned_name.replace("（", "(").replace("）", ")")
    if main.clean_emoji:
        cleaned_name = utils.remove_emojis(cleaned_name, "_").strip("_")
    # Windows 特殊字符清理：& 在 cmd 中会触发命令分隔，统一替换为下划线
    cleaned_name = cleaned_name.replace("&", "_")
    # WD-14：保留设备名加后缀（CON → CON_），否则 Windows 上无法创建同名目录
    if cleaned_name and cleaned_name.split(".")[0].upper() in _WINDOWS_RESERVED_NAMES:
        cleaned_name = cleaned_name + "_"
    # WD-14：超长截断。按字符数（非字节）截断，中文名不会被腰斩成半个字符；
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


# 桌面 Chrome UA：虎牙/B站 等国内 CDN 会拒绝移动端 UA（返回 403），录制拉流必须用桌面 UA；
# 校验探针与 ffmpeg 录制共用同一 UA（见 get_record_user_agent），否则校验“假绿”。
# 版本对齐全库基准 Chrome/141（见 room.DESKTOP_UA），避免 UA 指纹过旧被风控标记。
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)

# 移动端 UA：与 main.py ffmpeg 录制命令的默认 UA 保持一字不差——探针若改发 httpx 默认 UA，
# 部分 CDN（斗鱼 hwa 实测）会对 GET 偶发 403 而 ffmpeg 带移动 UA 拉流正常，
# 故校验与录制两端 UA 必须完全一致。
#   [历史注] 2026-08 由 SamsungBrowser/14.2 + Chrome/87 升级为 Android 14 (Pixel 8) + Chrome 141。
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
    #   [历史注] 旧规则 "虎牙直播": "referer:https://www.huya.com/" 曾必需 Referer 才 200，该行为已废弃。
    # B站直播 CDN（bilivideo.com）对无 Referer 的请求返回 403（content-type 空），
    # 与虎牙同源。校验器与 ffmpeg 录制共用此条目，保证两端一致地拿到流。
    "B站直播": "referer:https://live.bilibili.com/",
}


# 按 platform 返回录制拉流所需的请求头字典（合并 base 头与可选 cookie），无头时返回 None。
# - base 头按平台给 referer/origin（B站缺 Referer 被 CDN 拒 403；虎牙反向校验，
#   携带 Referer 反而 403，故不在 _RECORD_HEADER_RULES 中登记）；
# - cookies 为登录态 Cookie 字符串（如配置的 *cookie），转发给 CDN 以满足会话校验
#   （B站需 buvid3）。空字符串/None 时不注入 cookie。
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
# （HEAD→GET）会偶发 403（ffmpeg 单次 GET 正常），隔开重试才能区分「偶发限流」与「稳定
# 拒绝」。实际间隔 = 基准 + uniform(0, 抖动上限)——恒定间隔本身就是可识别的机器人节奏
# 指纹，叠加抖动能显著降低被 CDN 按节奏特征风控的概率。
_GET_RECHECK_INTERVAL = 0.8
_GET_RECHECK_JITTER = 0.7

# 同一 CDN host 相邻两次探针的最小间隔（秒）+ 抖动上限：多房间并发监控时（各自独立的房间线程），
# 对同一 CDN 的探针可能毫秒级连击——即上方「偶发 403」的根因。探针节流保证同 host 探针至少间隔
# _PROBE_MIN_HOST_INTERVAL + uniform(0, _PROBE_THROTTLE_JITTER)，不同 host 互不影响、首次探针不等待。
# 测试可将 _PROBE_MIN_HOST_INTERVAL 置 0 关闭节流。
_PROBE_MIN_HOST_INTERVAL = 0.35
_PROBE_THROTTLE_JITTER = 0.4
_probe_last_seen: dict[str, float] = {}
_probe_throttle_lock = threading.Lock()


# 计算一次带随机抖动的重试间隔（节奏指纹依据见 _GET_RECHECK_INTERVAL 注释）；返回间隔秒数。
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
# 后 ffmpeg 立即 403（Error opening input: 403 Forbidden），或拉流数百 KB 后被掐断
# （Stream ends prematurely），录制陷入秒级失败循环、弹幕采集器随之反复起停收不到消息。
# 对开启退避的平台：探针观测到 401/403（含重试后恢复的偶发拒绝，同样是限流证据）即把
# 「scheme://host/路径」记入退避窗口；窗口内跳过全部探针——非末位候选按校验失败回退
# 下一候选，末位候选直接放行给 ffmpeg，让 ffmpeg 拿到零探针占用的干净连接预算。
# 仅对虎牙开启、绝不可扩大名单：斗鱼 hw 的偶发 403 由既有「重试一次再定罪」救回（重试即
# 206），若对它跳过探针会让 HLS-first 退回游客态约 70 秒被掐的 FLV，属回归。
#   [历史注] 2026-09-20 审查 MID-17 建议「重试成功即撤销退避」，已核实但不构成问题：偶发拒绝
#   本就是限流证据（test_huya_transient_flv_403_marks_backoff 锁死），且斗鱼不在名单内、零条目。
_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)
# FLV-first 平台：select_source_url 的候选尝试顺序反转为 FLV → HLS → record_url。
# 依据（2026-08-28/29 三轮真机，虎牙 880214 与 chuhe 两房间复现）：HLS 三条 CDN 线路
# （hs/tx/al.hls.huya.com）冷启动探针假绿——探针 200/206 而 ffmpeg 打开即 403（返回码
# 3436169992），TX/AL 在次轮探针也稳定 403；FLV 每轮稳定可用（最长连录 6 分钟）。
# 恒定 FLV 优先把「冷启动假绿损失」从约 2 分钟（一个完整退避周期）降为零，FLV 不可用时
# 仍按序回退 HLS。斗鱼绝不加入：游客态 FLV 长连接约 70 秒被 CDN 掐断，必须 HLS 优先。
_FLV_FIRST_PLATFORMS = ("虎牙直播",)
# 退避窗口下限（秒）。实际窗口由 _probe_backoff_window() 计算，必须 ≥ 一个主循环周期。
_PROBE_BACKOFF_SECONDS = 60.0
# 覆盖主循环间隔的余量（秒）：main.py 的单轮等待 = delay_default + 抖动(±5s)，且错误窗口
# 满 5 次时再 +60s，故取 70s 覆盖「一个完整周期 + 抖动 + 最坏错误加成」。退避偏长代价很小
# （末位候选本就放行给 ffmpeg，录制成功还会立即清除），偏短代价是假绿死循环——宁长勿短。
_PROBE_BACKOFF_INTERVAL_MARGIN = 70.0
_probe_backoff: dict[str, float] = {}
_probe_backoff_lock = threading.Lock()


# 退避窗口必须至少跨过一个主循环周期，否则闭环恒不成立：原实现固定 60s，而 main.py 的
# delay_default 默认为 **120s**——ffmpeg 快速失败记入退避后下一轮在 T+124s 才到，早已出窗，
# 于是又去撞同一条死线路。实测虎牙 880214 即此形态（间隔 ~124s、重试 7 轮仅 2 轮侥幸录上，
# 两轮日志中「CDN 探针退避中」告警一次都没出现）。
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


# ffmpeg 录制侧的反馈入口：与探针侧 _mark_probe_reject / _clear_probe_reject 共用同一份
# 实现（同一白名单、同一退避键），不再各写一层纯转发包装，语义见上面两处内部函数注释。
# 录制「快速失败」（输入打开即被拒，如虎牙 HS 线路探针 200/206 通过、ffmpeg 紧随其后
# GET 却 403）时把实际拉流地址记入退避，下一轮 select_source_url 即跳过该地址、改试下一
# CDN 候选——「探针假绿」在探针侧永远观测不到（httpx 与 ffmpeg 客户端指纹不同），不标记
# 就成了「探针通过→录制被拒→下轮探针仍通过」的死循环；录制成功则立即撤销退避。
mark_ffmpeg_reject = _mark_probe_reject
clear_ffmpeg_reject = _clear_probe_reject


# 判定流地址是否为 h265 编码：候选过滤、record_url 兜底与 stream.py 的 h264 备选收集
# 三处共用的判定逻辑，抽为单一实现避免口径漂移。
# [历史注 2026-10-01] 原注释「h265 无法 copy 录制」已证伪收窄——直拷可行性取决于输出容器
# 而非编码本身，容器判定收进 _h265_copy_format_supported。
def _is_h265(url: str) -> bool:
    codec = utils.get_query_params(url, "codec")
    return isinstance(codec, list) and bool(codec) and codec[0] == "h265"


# 判定当前「视频保存格式」的容器能否直拷（-c copy）HEVC 流：TS(mpegts)/MKV(matroska)/MP4
# 三个 muxer 均支持写 HEVC（main.py 选中 h265 地址时强制 record_save_type=TS 即同一事实）；
# FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展，仓库口径不支持——main.py 对 h265 地址同样强制转 TS）、
# MP3/M4A 纯音频格式（容器装不下视频轨）不支持。取值经 main 的热更新全局 video_save_type
# 惰性读取（与 _hls_selection_config 同一模式）：main() 启动后已把它 .upper() 收敛进
# video_save_type_list 域（非法值回 "TS"），此处仍做 strip+upper 以覆盖配置加载前的小写
# 模块默认值；缺失/非字符串一律按「不支持」处理，保住 h265 过滤的保守语义。
def _h265_copy_format_supported() -> bool:
    raw = getattr(main, "video_save_type", "")
    fmt = raw.strip().upper() if isinstance(raw, str) else ""
    return fmt in ("TS", "MKV", "MP4")


# 可交给 ffmpeg `-i` 的流地址协议白名单（MID-19）。rtmp/rtmps 是合法用例
# （斗鱼 rtmp 拼接、部分海外平台仍下发 rtmp），故不能简单要求 http(s)。
_ALLOWED_STREAM_SCHEMES = frozenset({"http", "https", "rtmp", "rtmps"})


# 判定 url 是否具备「可以进 ffmpeg -i」的最小形态：协议在白名单内 + 主机名非空 + 不以 '-' 开头。
def _is_recordable_url(url: str) -> bool:
    # 末位候选（last_resort）的放行语义只针对「网络 / CDN 拒绝」，但它原先对**任何**异常都
    # 成立，包括 httpx 的 UnsupportedProtocol（非 http/https）、InvalidURL（含空格/控制字符）、
    # MissingSchema（平台 JSON 给出 /path/x.m3u8 这类相对路径）。于是远端可控（接口被劫持 /
    # MITM）的 `file:///…`、`concat:…` 或以 '-' 开头的串会被当成「探针异常但末位可用」直接
    # 塞进 -i：前者把本地文件读进录制产物（信息泄露），后者是 ffmpeg 选项注入（argv 以列表
    # 传入无 shell 注入，但 ffmpeg 自身选项仍有写文件/改协议能力）。一律告警丢弃，不享受末位放行。
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


# 探针同步客户端的唯一构造点（WP-J，2026-09-30，方案 1-A）：本模块原有两处各自裸写
# httpx.Client(...)（_validate_stream_url 的 owns_client 自建分支、select_source_url 的整轮共用客户端），
# 两处都 follow_redirects=True 却都没挂逐跳复检——被劫持/被 MITM 的平台接口只要回传一个「公网 URL →
# 302 → http://127.0.0.1:6379/ 或 http://169.254.169.254/」，同步探针就会照着跟进去连内网，并把该跳的
# status_code / content-type 回显进轮转日志（= 稳定的内网端口观测口，MIN-2219 的跳转形态）。
# 现两处一律经本工厂，异步钩子随之挂上；「新增第三处裸构造就静默漏掉防线」由
# tests/test_sync_probe_internal_guard.py 的 AST 结构锁挡住（构造点唯一 + 工厂调用点计数 +
# event_hooks 实参必须来自 build_sync_hop_guard）。
# proxy_addr 必须由**调用方**在传入之前经 utils.handle_proxy_addr 归一：SEV-N05 的「归一只放在构造客户
# 端之前这一处」原意即「各探针调用点不各自归一」，本工厂既不做二次归一、也绝不允许把归一挪到构造之后
# （两处调用点各自的位置保持原样，见其上方注释）。
# 复用形态一律未动：作用域仍是单次选源、finally 关闭、keepalive 保持默认、不按 (proxy, verify) 做模块级
# 全局缓存（AGENTS「HTTP 客户端复用与连接管理」——虎牙 CDN 按连接预算限流，常驻 keepalive 会与 ffmpeg
# 拉流争抢）。本函数只加 event_hooks。
def _probe_client(timeout: int, proxy_addr: str | None, verify: bool) -> httpx.Client:
    # 钩子工厂与判定都来自 src.async_http，本模块不另写一份（口径分叉本身就是缺口）。
    # 这里**函数内 import** 而非模块级：沿 async_http.py:518-521 记录的同一手法——本模块有模块级
    # `import main`、main.py 又 `from src.stream_select import ...`，这条环已让 async_http 把
    # web_config 的 import 放进函数内；给本模块加一条模块级出边会改变各模块的初始化顺序（同一手法、
    # 同一理由）。本函数每轮选源只走 1~2 次，多一次已缓存的 sys.modules 查找没有成本。
    from src.async_http import build_sync_hop_guard

    return httpx.Client(
        timeout=timeout,
        proxy=proxy_addr,
        verify=verify,
        event_hooks={"response": [build_sync_hop_guard(proxy_addr)]},
    )


# ── L-11（2026-10-19，CODE_REVIEW_2026-10-18）：探针读取响应体必须有上限，且是唯一入口 ──
# 本模块四处探针（_probe_hls_segment 的播放列表 GET / 变体列表 GET / 媒体分片 Range-GET，
# _validate_stream_url 的 m3u8 Range-GET）此前一律走 client.get()：httpx 会把响应体**一次性读满**
# 才返回，而四处里只有前两处真的要看正文（解析分片行），后两处只看状态码——正文一个字节都不需要。
# 风险面不是「列表有点大」而是 Range 只是请求：不遵守 Range 的边缘节点（2026-09-13 斗鱼 hw 事故
# 注记里同一批 f19c*.livehwc4 节点形态）会把 .ts 当整段流媒体一直发，于是每个房间线程每轮选源
# 都能吃进任意大的 body，80+ 房间并发时是无界内存，且日志上一条都看不出来。
# 真实播放列表正文远小于 64 KB（斗鱼/虎牙实测单行分片列表约 2~8 KB），取满即截断也够解析末行分片。
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
    # 流式打开、最多读 body_limit 字节即断开。判定所需的 status_code / headers 与 client.get()
    # 完全一致，**不改任何判定分支**（HEAD→Range-GET 的 200/206 基线、401/403 原样重试一次再定罪、
    # 末位候选仅告警放行、退避与节流一律留在调用点）。三条必须成立的接线形态：
    # ① 逐跳内网复检：response 钩子在**响应头到达时**触发（httpx 的 _send_handling_redirects 里
    #    钩子早于任何正文读取），所以 RedirectHopRejected 仍从本函数原样抛到调用点既有的
    #    except RedirectHopRejected 分支——本函数**刻意不接任何异常**，接了一次就等于把内部控制流
    #    异常喂给「维持可达」的兜底（WP-J 登记的原始事故形态）。
    # ② 客户端仍是调用方手里那一支：不新建第三处客户端、不按 (proxy, verify) 升级为模块级缓存、
    #    复用作用域仍是单次选源（AGENTS「HTTP 客户端复用与连接管理」）。
    # ③ 提前断开的那条连接由 httpcore 直接丢弃，keepalive 配置一字未动；「只读状态码不读正文」
    #    这一形态在本模块已由 _confirm_get_ok 的流式复核跑在生产链路上，不是新引入的赌注。
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


# ── 正文派生的第二跳请求（变体列表 / 媒体分片）的边界（MID-2231，2026-09-22）──
# urljoin 对**绝对** URL 会整体丢弃 base，于是播放列表正文里的一行就能把下一跳指到任意 host；
# 而 headers 里带着 get_record_headers(platform, url, cookies=…) 注入的用户 Cookie。httpx 只在
# **重定向**跨源时自动剥 Cookie，对这种「新起的第二跳请求」不做任何处理——一个被劫持的 m3u8
# 即可让本机带着登录态向任意 host 发 GET（凭据外泄 + 内网 SSRF）。故派生地址先过形态白名单与
# 「非内网目标」，再按「是否与列表同域」决定是否带 Cookie。

# 内网 / 本机 / 链路本地目标（IPv4 私网段 + IPv6 环回与本地地址）的字面量前缀。只按字面量判定、
# 不做 DNS 解析：探针每轮对多候选执行，解析既多一个可被远端操纵的攻击面，也多一段不可控延迟。
_PRIVATE_HOST_PATTERN = re.compile(
    r"^(?:localhost|127\.|0\.|10\.|169\.254\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.|::1|fe80|f[cd][0-9a-f]{2}:)",
    re.IGNORECASE,
)
_IPV4_HOST_PATTERN = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")


# 派生地址是否允许发出：形态合规（_is_recordable_url）且不是内网/本机目标。
def _is_derived_hop_allowed(url: str) -> bool:
    if not _is_recordable_url(url):
        return False
    host = urlsplit(url).hostname or ""
    return not _PRIVATE_HOST_PATTERN.match(host)


# 播放列表正文派生的地址命中安全闸时抛出的**内部控制流异常**（S-04，2026-10-19）。
#
# 为什么必须是异常而不是 `return False`：`_probe_hls_segment` 的 bool 返回值同时承载
# 「分片 404 不可达」与「安全闸拒绝」两种语义，而调用方对前者的既有处理是「末位候选
# (last_resort) 仍交由 ffmpeg 尝试」——把安全拒绝编码成 False，就等于让它继承末位放行的
# 语义，内网地址最终仍被交给 ffmpeg -i。异常与控制流分开后，安全结论不再参与
# 「可达/不可达」的推断，也就不会被任何兜底分支翻回 True。
# 与 async_http.RedirectHopRejected 同族（那是**重定向链**上的逐跳复检），本类只覆盖
# **正文派生**的第二跳请求；两者都不穿透给最终调用方，只用于在本模块内定级。
class _DerivedHopRejected(Exception):
    def __init__(self, hop_url: str, reason: str) -> None:
        super().__init__(f"{reason}: {hop_url}")
        self.hop_url = hop_url
        self.reason = reason


# 取主机名的近似注册域（末两段：a.b.example.com → example.com）。
# 单段/双段主机名与 IPv4 字面量返回 ""：双段时「同域与否」已由 host 全等比较覆盖，
# 此时返回有效值只会让 example.com 与 evil.com 这类不同域被误判为同域。
def _registrable_domain(host: str) -> str:
    if _IPV4_HOST_PATTERN.fullmatch(host):
        return ""
    labels = host.split(".")
    if len(labels) < 3:
        return ""
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


# 派生地址这一跳实际使用的请求头：同域沿用原头，跨域只剥 Cookie、继续探测（凭据外泄面已
# 消除）。「保守返回 True（跳过探测）」仅保留给形态不合规与内网目标这两种不该发请求的情形
# ——分片 host 常与列表 host 跨注册域（斗鱼 hw3a…douyucdn2.cn → f19c…livehwc4.com，见
# _probe_hls_segment 的 2026-09-13 事故注释），跨域即跳过会把
# test_hls_segment_404_rejects_playlist 锁住的「列表 200、分片 404 判假绿」能力整体废掉。
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


# 从 master playlist 正文里挑出「应当探测」的变体 URL：按 BANDWIDTH 取最高码率档（MIN-03）。
# 原实现跟随**首个**变体，而 # 注释行在分片解析时被整体丢弃、连 BANDWIDTH 一起看不见，只能按
# 位置取 lines[0]。HLS 规范不要求变体按带宽降序（不少生成器升序列出、最低档在前），于是
# 「探到的是最低档分片、ffmpeg 实际按自身码率策略拉最高档」——正是 2026-09-13 斗鱼 hw
# 「列表 200、分片 404」假绿要防的那类偏差，只是从列表层挪到了变体层；反向情形（首变体不可用
# 而高档可用）则会误杀可用源。返回 None 表示取不到任何变体 URL（调用方按「解析不出」保守放行）。
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


# HLS 播放列表可达 ≠ 可录制：媒体分片必须单独探测（2026-09-13 斗鱼 hw CDN 实测事故）。
# 事故形态：hw3a.douyucdn2.cn 的 m3u8 播放列表恒 200（CDN 动态合成，列表层无风控），但边缘节点
# （f19c*.livehwc4.com）上所有 .ts 分片 404 —— ffmpeg 拉列表成功后逐分片 404，hls demuxer 无限
# 「Segment failed too many times, skipping」循环：零字节产出、进程常驻、-loglevel error 下零输出
# （404 属 demuxer warning 级，不上 stderr）。生产表现即「录制只出弹幕 SRT、无视频文件」；同房间
# 同 token 的 FLV 完全可用（10s 录制 10.6MB）。根因在探针假绿：旧校验「列表 200 即可达」从未看过
# 分片。本函数补上分片层：GET 播放列表 → 若为 master playlist（含 #EXT-X-STREAM-INF）跟随**带宽
# 最高**的变体到媒体列表（见 _pick_master_variant，MIN-03）→ 取末行分片（最新，避开已滚出窗口的
# 旧分片误杀）→ Range bytes=0-0 GET 探测。
# 判定原则（保守优先，不误杀可用源）：分片 200/206 → 真可达；分片明确 4xx/5xx → 列表假绿，判不可达
# （调用方回退下一候选，如 FLV）；任何解析不出分片（空列表 / 非 .ts|.mp4 行 / 子列表取不到 / 探测
# 异常）→ 维持旧结论「列表可达」，交由 ffmpeg 定夺——只有「探到了分片且被明确拒绝」才推翻列表结论。
# 401/403 按既有「隔 _GET_RECHECK_INTERVAL 重试一次再定罪」的偶发限流语义处理（连击偶发 403 成因见
# _confirm_get_ok）；404 是「分片不存在」的确定性信号，不重试。
# 本函数日志一律把 URL 过 utils.mask_credentials（MID-N32，2026-09-21）：列表与分片地址都挂有斗鱼
# wsAuth / 抖音 signature 等查询侧凭据，直传会明文落进轮转日志。
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
        # L-11：正文经 _bounded_probe_get 的有界读取（真实列表远小于上限），解析不出分片时仍走
        # 下方既有的「保守维持列表可达」分支，判定结论与改前逐字一致
        # master playlist：跟随带宽最高的变体（见 _pick_master_variant），最多两层，
        # 覆盖「变体→子列表」的嵌套形态如斗鱼 hw
        for _ in range(2):
            if "#EXT-X-STREAM-INF" not in text:
                break
            variant_url = _pick_master_variant(text, media_url)
            if not variant_url:
                return True  # 只有标签行、取不到变体 URL——解析不出分片，保守维持列表可达
            # MID-2231：正文派生的地址先过「形态合规 + 非内网目标」，再按同域与否裁决 Cookie
            if not _is_derived_hop_allowed(variant_url):
                logger.warning(
                    i18n.tr(
                        "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                        url=utils.mask_credentials(variant_url),
                    )
                )
                # SR-01：安全闸拒绝是确定性失败，不是「解析不出分片」的保守兜底——维持可达等于把
                # 内网地址经播放列表正文交给 ffmpeg -i（与下方 RedirectHopRejected 分支同一判据），
                # 候选判失败、回退下一候选。
                # S-04（2026-10-19）：改为抛内部控制流异常。原 `return False` 会被调用方的
                # last_resort 分支翻回「仍交由 ffmpeg 尝试」，安全结论因此形同虚设。
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
        # MID-2231：分片地址同样由正文派生，先过形态/内网闸，再按同域与否裁决 Cookie
        # （对照基准是本轮校验的播放列表 url，而不是可能已经跨域的 media_url）
        if not _is_derived_hop_allowed(seg_url):
            logger.warning(
                i18n.tr(
                    "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                    url=utils.mask_credentials(seg_url),
                )
            )
            # SR-01：与变体派生跳同判据——安全闸拒绝判候选失败，不得维持可达
            # S-04（2026-10-19）：同上方，改抛内部控制流异常以脱离 last_resort 的放行语义
            raise _DerivedHopRejected(seg_url, "媒体分片地址形态不合规/指向内网")
        seg_headers = _headers_for_derived_hop(playlist_url, seg_url, headers)
    except _DerivedHopRejected:
        # S-04：安全拒绝必须先于通用兜底上抛——下面的 `except Exception` 会把它当「探测异常」
        # 并按「列表可达」处理（return True），正是本条要消灭的形态。
        raise
    except RedirectHopRejected:
        # WP-J：本函数每一条「保守维持列表可达」的兜底都不得吞掉内部控制流异常——在内网落地目标面前，
        # 维持可达就等于把内网地址交给 ffmpeg（调用方末位候选还会 return True 放行）。原样上抛，
        # 由 _validate_stream_url 的 RedirectHopRejected 分支统一收敛成「本候选校验失败」。
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
        # 同 host 探针节流（分片 host 常与列表 host 不同，如 hw3a…→f19c…livehwc4）：
        # 多房间并发下对同一边缘 host 的分片探测同样存在毫秒级连击风控面
        _throttle_probe(seg_url)
        try:
            seg_resp = _bounded_probe_get(client, seg_url, {**seg_headers, "Range": "bytes=0-0"}, read_body=False)
        except RedirectHopRejected:
            # WP-J：同上——分片探测的「按列表可达处理」兜底也不得吞掉内部控制流异常
            # （函数级说明见本文件上方 _probe_hls_segment 第一条 except RedirectHopRejected）。
            # 这里绝不能改成 pass：seg_url 分支被跳过后下一句就引用未赋值的 seg_resp，
            # UnboundLocalError 会被外层 except Exception 当成「探测异常」吞掉，
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
            # MIN-02：退避键必须是**播放列表 URL**——查询侧（_validate_stream_url 的
            # _probe_in_backoff）用的是候选本身（播放列表），而分片取自列表末行、每轮滑动，
            # 记成分片 URL 会得到一条永不被读到、只被自身过期回收的死条目，
            # 「分片被拒 → 下轮跳过该线路探针」在分片层完全没落地。
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


# FLV/record_url 源 HEAD 通过后的 GET 复核（流式请求、不读 body）：虎牙 al.flv.huya.com 等 CDN
# 出现过 HEAD=200 而 GET=403 —— 校验“假绿”后 ffmpeg 打开即 403、录制反复失败。ffmpeg 拉流是
# 「无 Range 的全量 GET」，复核必须与之完全一致：虎牙对无 Range GET 同样 403（拒绝的是 GET 本身），
# 假绿仍能抓到；斗鱼 hwa CDN 曾对 Range-GET 偶发 403 而无 Range GET 正常（实测），带 Range 反而误杀。
# 复核仅在拿到明确拒绝状态码（401/403）时推翻 HEAD 结论，且先原样重试一次再定罪：斗鱼 hw/虎牙 al
# 实测对短时间内的连续探针会偶发 403，同 URL 片刻后重试即 200（探针误杀、ffmpeg 实际拉流成功）。
# 其余异常（超时等）不推翻，避免把可用源误判为不可达。last_resort=True 表示该源已是最后一个候选：
# 两次复核均拒绝时仅告警放行、交由 ffmpeg 实际拉流定夺（探针 httpx 与 ffmpeg 客户端指纹不同，存在
# 探针稳定 403 而 ffmpeg 可正常拉流的实例）。流式只读状态码不迭代 body，不会下载直播流。
def _confirm_get_ok(
    client: httpx.Client,
    url: str,
    head_status: int,
    headers: Mapping[str, str],
    last_resort: bool = False,
    platform: str | None = None,
) -> bool:
    reject_status: int | None = None
    # 函数内 import 的理由见 _probe_client
    from src.async_http import RedirectHopRejected

    for attempt in range(2):
        try:
            # headers 由调用方逐请求显式传入：探针客户端在多个候选间复用，不能再把
            # UA/Referer/Cookie 挂在 client 上（否则各候选互相污染）
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
            # WP-J：本函数的 except 分支语义是「异常（超时等）**不推翻** HEAD 结论」，末位候选还直接
            # return True——内部控制流异常一旦走进那条分支，就等于「公网 HEAD 通过 → 302 落在内网 →
            # 探针判可用」，正是 MIN-2219 的跳转形态。原样上抛，交 _validate_stream_url 收敛为校验失败。
            raise
        except Exception as e:
            # 异常（超时等）不推翻 HEAD 结论，但必须留痕（禁止静默吞异常）；
            # attempt 0 的异常可能是偶发超时，按「重试一次再定罪」语义隔开后重试，
            # 两次均异常才放弃复核（HEAD 结论维持通过）
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


# 探测流地址 url 是否可用于录制：proxy_addr 为可选代理、timeout 为单次探针超时秒数、verify 为 SSL
# 证书校验开关（None 时取全局配置）、client 为可选复用的 httpx 客户端、last_resort 表示该候选已是
# 末位（无备选可回退）；返回可达且内容类型为流媒体则 True，否则 False 并打日志说明原因。语义必须与
# async_http.get_response_status 保持一致：
# 1) verify 未显式指定时取 _http_config.get_effective_ssl_verify(platform)，由「是否启用https
#    录制」统一联动（开启=https 拉流且全局禁用证书验证；关闭=http 拉流、恢复严格校验），平台覆盖受
#    https_recording_enabled 门控。少了这一步，用户关闭证书验证后同步校验仍严格验证书，会误判不可达；
# 2) m3u8 源 HEAD 非 2xx（含 403/404）时再做 Range-GET 探测——抖音等 CDN 常对 HEAD 回 4xx 而 GET
#    可正常拉流，只覆盖 400/401/403/405 会漏掉 404；
# 3) 失败必须记录原因（异常类型/状态码/content-type），禁止静默吞异常，否则回退 FLV 时无法定位真实
#    原因（超时、被拒、内容类型不符）；
# 4) 按 platform 透传录制所需请求头与 UA：否则出现「校验 200、ffmpeg 403」的假绿——虎牙无 Referer
#    直接 403、发 httpx 默认 UA 被斗鱼 hwa 在 GET 时偶发 403；
# 5) client 由 select_source_url 传入时整轮候选共用（keepalive 生效，verify/timeout/proxy 以该 client
#    为准、本函数不再覆盖），不传时自建自管、与旧行为一致。
# 6) WP-J（2026-09-30，方案 1-A）：本函数是「即将对某个候选地址发探针」的唯一入口，故两道内网防线都落
#    在这里——① 发第一个请求之前对**初始 URL** 调一次内网/保留目标判定（口径 6 之前该侧连这一层都没有，
#    只有 _is_recordable_url 的协议形态白名单，它挡 file:///concat:，不挡 http://127.0.0.1:6379）；
#    ② 自建/复用两支客户端一律带逐跳重定向复检钩子（见 _probe_client）。判定复用 src/async_http 的同一份
#    实现，本模块不另写 urlparse/内网名单。命中一律回 False（本候选校验失败）且**不享受末位放行**：
#    last_resort 的语义边界是「网络 / CDN 拒绝」（MID-19），内网目标不是「CDN 拒绝」，放行等于把 ffmpeg
#    指向内网。返回契约仍是 bool，异常绝不穿透给调用方。
# 7) S-04（2026-10-19）：正文派生跳（变体列表 / 媒体分片）命中安全闸时，_probe_hls_segment 抛
#    _DerivedHopRejected 而非返回 False；本函数把它收敛成与口径 6 相同的 False，并（可选地）
#    把该 URL 记进调用方的 security_rejected 集合——select_source_url 的「本轮已探过就复用结论」
#    分支据此拒绝交付，否则安全拒绝会在那里被当成普通探针失败再次放行。
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

    # WP-J：初始 URL 的内网/保留目标判定。位置三条都不能挪——
    #   ① 必须早于 _probe_in_backoff：那条分支在「退避中 + 末位候选」时无条件 return True 放行给 ffmpeg，
    #      内网地址一旦走到那儿就被请进 -i；
    #   ② 必须早于客户端构造与任何探针：命中即一个字节都不发（本判定是**安全判定**，不是可达性判定）；
    #   ③ 与 _is_recordable_url 的形态白名单互不替代（协议形态与内网目标管的是两回事，两道都要在）。
    # 用 internal_stream_target_reason 而**不是** redirect_hop_rejection_reason：后者带 scheme 白名单
    # （utils.is_safe_http_url 只认 http/https），而本模块的候选允许 rtmp/rtmps（MID-19 /
    # _ALLOWED_STREAM_SCHEMES，斗鱼 rtmp 拼接与部分海外平台仍在下发），协议维度已由 _is_recordable_url
    # 把关，这里只补内网维度；逐跳钩子仍用 redirect_hop_rejection_reason（与异步侧完全同口径）。
    # proxy_addr 此处仍是调用方传入的原文（自建分支要到下方才归一，见 SEV-N05 的「归一只放在构造客户端
    # 之前这一处」）：_internal_stream_target_reason 只用它判断「本次是否经代理出站」，而归一前后的
    # 真值性完全一致（有代理→非空串；无代理→"" 或 None→假），故不构成口径分叉。
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
    # 探针退避：该源所在 CDN 近端已被连续拒绝（限流中），本轮跳过全部探针。非末位候选按校验失败
    # 回退下一候选；末位候选直接放行给 ffmpeg（口径同 _confirm_get_ok 的末位语义），省下的连接预算
    # 正是 ffmpeg 拉流成败的关键（虎牙实测：探针烧光预算后 ffmpeg 立即 403）。
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
    # 探针客户端：传入时在整轮候选间复用（收益实测见 select_source_url）；未传入时自建自管。
    # 客户端在多候选间共享，故 UA / Referer / Cookie 不能再挂到 client 上、必须逐请求传入
    # （与原先挂 client 时等价：httpx 的 _merge_headers 本就是「client 头为底、请求头覆盖」）。
    owns_client = client is None
    probe_client: httpx.Client | None = client
    try:
        if probe_client is None:
            # SEV-N05 修复（2026-09-21）：proxy_addr 是配置项「代理地址」原文，允许裸 ip:port
            # 写法（由 utils.handle_proxy_addr 补 scheme，见 src/utils.py 同函数注释与
            # _PROXY_CREDENTIAL_RE 说明），而 httpx 0.28 的 Client(proxy=...) 只认带 scheme 的
            # 地址——裸串与空串一律抛 ValueError: Unknown scheme for proxy URL（实测），仅 None
            # 正常。归一只放在「构造客户端之前」这一处：head / Range-GET / _confirm_get_ok 各
            # 探针调用点不各自归一，与 select_source_url 的整轮共用客户端走同一函数，故两侧对
            # 同一配置值得到同一代理结论（AGENTS「同步/异步校验器 proxy/verify/UA 三者一致」）。
            # 构造失败无需另加保护：本函数已有的 except Exception 会收敛为「本候选校验异常」，
            # 末位候选仍按既有口径放行给 ffmpeg，owns_client 语义不变。
            # WP-J：构造改走 _probe_client 单点工厂（逐跳复检钩子随客户端挂上）；归一位置未动、
            # owns_client 与「自建自管 + finally 关闭」语义未动。
            proxy_addr = utils.handle_proxy_addr(proxy_addr)
            probe_client = _probe_client(timeout, proxy_addr, verify)
        response = probe_client.head(url, headers=headers, follow_redirects=True)
        content_type = response.headers.get("content-type", "").lower()
        if response.status_code in (401, 403):
            _mark_probe_reject(url, platform)
        # m3u8 源：抖音等 CDN 对 HEAD 常回 4xx（如 405）+ text/html，但 GET 实际可拉流，故优先做
        # Range GET 探测，绕过 HEAD 不可靠的 content-type/状态码（与 async_http.get_response_status 一致）。
        # 2026-09-12 审查（低危）：扩展名按小写判定——大写 .M3U8 会漏掉 Range GET 探测、被 HEAD 的
        # 4xx 直接判成不可达（与 async_http 同型问题）
        if ".m3u8" in url.lower():
            if response.status_code == 200 or any(
                k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")
            ):
                # 2026-09-13 斗鱼 hw 事故：列表 200 ≠ 可录制——必须补分片层探测
                # （_probe_hls_segment 内部保守判定，解析不出分片时维持旧「可达」结论）。
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
            # Range-GET 401/403 先隔 _recheck_delay() 原样重试一次再定罪（与 _confirm_get_ok 同语义：
            # 连击偶发 403、片刻后重试即 200，属探针误杀）。HLS 须尽力救回——斗鱼游客态 FLV 长连接
            # 约 70 秒被 CDN 掐断，HLS 逐段拉取免疫。
            probe: _ProbeResponse | None = None  # 失败路径（last_resort/告警）需 Range-GET 结果；先置 None 避免未绑定
            for attempt in range(2):
                # 显式合并 headers 与 Range（与 async_http.py 同语义）：客户端在候选间复用，
                # Range 只能作为请求级头附加，不能覆盖录制所需的 UA/Referer/Cookie
                # L-11：本跳只是可达性判定，正文一个字节都不需要（read_body=False），
                # 不遵守 Range 的节点回多大的 body 都不会被读进内存；状态码/头的判定路径逐字未变
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
            # 循环已至少执行一次，probe 理论上必非空；显式判空收窄类型（assert 在 -O
            # 下会被整体剔除，且失败抛 AssertionError 而非可诊断的告警路径）
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
                # 斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁用 HEAD 方法），ffmpeg 实际 GET 拉流正常。
                # 末位候选（无备选可回退）稳定拒绝也仅告警放行、交由 ffmpeg 定夺，
                # 避免 content-type 启发式误杀可用源导致整轮放弃录制。
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
        # S-04（2026-10-19）：正文派生的变体/分片地址命中安全闸。与上方 WP-J 的两条内网防线同口径
        # ——warning 级、URL 脱敏、**不享受末位放行**。这里绝不能被 `except Exception` 接住：
        # 那条分支在 last_resort 时 return True，正好是「安全拒绝被翻回可达」的原形态。
        # 复用已登记的同一模板（「探针拒绝内网/保留目标…」），避免为同一语义新增第二种措辞。
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
        # WP-J：3xx 落地跳命中内网/保留目标（或非白名单协议）。与 async_http.get_response_status 的
        # 同名分支同一口径——MIN-2219 那三条定级理由逐字适用（安全判定必须 warning、不能被降级成
        # 「相邻画质不通」、URL 必须脱敏），故复用同一条已登记模板而不新增第二套措辞。
        # **必须排在 except Exception 之前**：落到那条分支去就意味着末位候选被 return True 放行，
        # 而末位放行的语义边界是「网络 / CDN 拒绝」（MID-19），内网目标从来不属于这一类。
        # 返回契约不变：仍是「本候选校验失败」的同一个 False，由 select_source_url 按既有口径
        # 回退下一候选；本函数绝不把内部控制流异常穿透给调用方。
        # 残余风险同 _build_hop_guard：跳转那一跳的连接已经发生；DNS 重绑定窗口本层不闭合。
        logger.warning(
            i18n.tr(
                "探针拒绝内网/保留目标（疑似被篡改的流地址）: {masked_url} - {reason}",
                masked_url=utils.mask_credentials(e.hop_url),
                reason=f"重定向逐跳复检命中: {e.reason}（初始地址 {utils.mask_credentials(url)}）",
            )
        )
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
        # 末位候选探针异常同样仅告警放行，与本函数其余分支（401/403 复核、content-type、
        # 非 200 拒绝）的「稳定拒绝在末位放行」口径一致：原实现此处无条件 return False，
        # 末位超时/连接异常会误杀可用源、整轮放弃录制，语义自相矛盾。
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
        # 仅关闭本函数自建的客户端；复用的客户端由 select_source_url 统一关闭。选源结束即释放连接：
        # 常驻 keepalive 会与随后的 ffmpeg 拉流争抢 CDN 侧连接预算（依据见 select_source_url 处）。
        if owns_client and probe_client is not None:
            try:
                probe_client.close()
            except Exception as e:
                logger.debug(i18n.tr("关闭探针客户端失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 读取 main 的 HLS 采集配置（是否启用 + 排除平台名），对「全局缺失 / 类型异常」做兜底：
# main 的这两个全局在启动早期（配置文件尚未加载完）或测试替身下可能缺省，直接属性访问会抛
# AttributeError，使整轮选源中断——表现为房间静默不录制且无任何选源日志，极难定位。
# 此处一律回退到安全默认（启用 HLS、无排除平台），并容忍「逗号分隔字符串」形态
# （与 main() 的配置解析同语义，亦兼容把配置全局直接写成字符串的场景）。
# 返回 (是否启用 HLS, 排除平台名元组)
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
# 替换成 m3u8（.flv→.m3u8）后再下发（见 src/stream.py 的 get_douyu_stream_url），二者共享
# 同一防盗链 token（wsAuth），仅容器/协议不同。2026-09-13 斗鱼 hw 事故即：m3u8 列表 200 但
# 边缘节点分片全 404，而同 token 的 FLV 可正常拉流——同源 FLV 是首选回退目标。此函数用于在
# 选择/日志里显式识别这层同源关系，避免把同源 FLV 当作无关候选而漏掉回退。
# 命中返回该 FLV 候选（原样），无同源返回 None
def _same_origin_flv(hls_url: str, flv_candidates: list[str]) -> str | None:
    stem = hls_url.lower().split("?", 1)[0]
    if not stem.endswith(".m3u8"):
        return None
    target = stem[: -len(".m3u8")] + ".flv"
    for candidate in flv_candidates:
        if candidate.lower().split("?", 1)[0] == target:
            return candidate
    return None


# 选源结论单行日志（观测增强）：记下「最终采用哪条源、属于哪一类候选」，便于在
# 「只出弹幕 SRT、无视频」类故障里一眼确认 ffmpeg 实际拉的是 HLS 还是 FLV，无需翻找
# 逐候选的告警。kind 为机器可读字面量（HLS/FLV/record_url），不翻译，便于日志检索。
def _log_source_choice(platform: str | None, kind: str, url: str) -> None:
    logger.debug(
        i18n.tr(
            "选源结论: platform={platform} 采用 {kind} 源: {url}",
            platform=platform or "",
            kind=kind,
            url=utils.mask_credentials(url),
        )
    )


# 从 stream_info（解析结果，含 m3u8_url/flv_url/record_url 等键）挑选本轮实际录制地址：
# 候选尝试顺序：默认优先 HLS，其次 FLV，最后 record_url；FLV-first 平台（见
# _FLV_FIRST_PLATFORMS，当前仅虎牙）反转为 FLV → HLS → record_url。proxy_addr 透传给
# 可达性校验；全部不可用时返回 None。
# HLS 采集排除列表（main.hls_collection_exclude_platforms）：命中平台无视「是否启用HLS采集」
# 配置、恒按 FLV 采集（等效于仅对该平台关闭 HLS 采集，HLS 候选整组剔除、不作回退）；
# 列表外平台不受影响，仍按全局配置 HLS 优先。
# MID-18（2026-09-20）：record_url 通道同受该「整组剔除」语义约束（抖音/TikTok/网易CC 的
# record_url 本身就是 m3u8）；并且与序列候选同址时复用本轮已探结论、不再重复发探针
# （同一地址二次探测正是虎牙/斗鱼 CDN 连接预算要省的地方）。
# MID-19：返回给上层的地址（含末位放行）一律先过 _is_recordable_url 形态白名单。
def select_source_url(
    stream_info: Mapping[str, object],
    proxy_addr: str | None = None,
    platform: str | None = None,
    cookies: str | None = None,
) -> str | None:
    # proxy_addr 必须透传给校验器：TikTok 等境外平台的流地址若不走与解析阶段相同的代理路径，
    # 直连校验会超时被误判为不可达，导致错误回退甚至放弃录制。
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

    # 配置兜底：经 _hls_selection_config 读取，缺失/类型异常时回退安全默认（启用 HLS、无排除
    # 平台），避免配置全局尚未就绪时 AttributeError 中断整轮选源。
    # MID-18：这一段必须早于 record_url 通道判定——record_url 是否可用同样取决于该开关。
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
    # MID-18：record_url 通道同受「HLS 整组剔除」语义约束。抖音（stream.py 的
    # `"record_url": m3u8_url or flv_url`）、TikTok、网易CC 的 record_url 本身就是 m3u8；
    # 命中「HLS采集排除平台」或全局关闭 HLS 采集时，HLS 组被整组剔除后落到 record_url，
    # 原实现仍会对 .m3u8 照发 HEAD/Range-GET/分片探测、且 last_resort=True 拒绝也放行，
    # 与该配置项 2026-09-05 定稿的「HLS 探针一次都不发」直接冲突
    # （原有 5 个排除列用例一律写 `"record_url": ""`，结构上发现不了这一点）。
    record_url_is_hls = ".m3u8" in record_url_str.lower()
    record_url_enabled = bool(record_url_str) and (hls_effective_enabled or not record_url_is_hls)
    hls_available = bool(hls_candidates)
    flv_available = bool(flv_candidates)
    # 回退可行性按「有效」口径判定：被 HLS 排除规则挡掉的 record_url 不构成回退，
    # 否则 m3u8-only 的排除平台会绕过快照告警、静默走到「本轮无可用源」。
    has_fallback = flv_available or record_url_enabled

    # 三类地址全为空：此前静默返回 None，房间会永远打印“正在直播中...”却不录制且无任何
    # 诊断线索（斗鱼 rtmp_live 为空即此形态）。必须留一条日志暴露根因。
    # （该分支不会产生任何探针，先于客户端构造处理，避免无谓的连接池开销）
    if not (hls_available or has_fallback):
        logger.warning(
            i18n.tr(
                "解析结果无任何流地址（m3u8/flv/record_url 均为空），本轮放弃: {anchor_name}",
                anchor_name=stream_info.get("anchor_name") or "",
            )
        )
        return None
    if hls_available and not hls_effective_enabled and not has_fallback:
        # m3u8 存在但 HLS 采集对本平台关闭（全局关闭 或 命中排除列表）、且无 FLV/record_url
        # 可回退：同为静默路径，必须提示而非无声跳过；两种成因给出各自的恢复指引
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

    # SEV-N05 修复（2026-09-21）：proxy_addr 由 main.py 原样透传配置项「代理地址」
    # （proxy_addr = None if not use_proxy else proxy_addr_bak），该项允许裸 ip:port 写法，且「代理
    # 开关打开但地址留空」也是合法取值（""）。而 httpx 0.28 的 Client(proxy=...) 只认带 scheme 的
    # 地址：裸串与空串一律抛 ValueError: Unknown scheme for proxy URL（实测），仅 None 正常。本模块
    # 曾是全仓唯一未经归一的出站面（async_http:255/365、room:92/176/268、spider:3495 均先过
    # handle_proxy_addr），于是「解析成功、选源每轮抛穿房间线程」：房间永不进入录制链，还持续向按
    # host 的熔断器投失败样本（极端情况会把用户配置里的房间地址自动注释掉）。归一必须在构造之前、
    # 且只这一处口径（_validate_stream_url 的自建分支同一函数）。
    #   [历史注] 原此处另把 sync_http:179 列为「已接线的出站面」，2026-09-22 实测不成立：
    #   src/sync_http.py 无生产导入方，录制/选源/解析三条链路都不经它
    #   （复核：grep -rn "sync_http" main.py web.py src/ build_exe.py）。
    proxy_addr = utils.handle_proxy_addr(proxy_addr)
    # 本轮全部候选探针共用一个 httpx.Client：keepalive 生效，且 SSLContext / 连接池只构造一次（原每
    # 候选各建一个——虎牙 4 条 CDN 线路即 4 次；实测构造约 6.7ms、复用后单次探针约 0.77ms，而新建
    # Client + 单次探针约 15.9ms）。作用域严格限制在本次选源内、finally 关闭：刻意不做全局
    # (proxy, verify) 缓存——常驻 keepalive 会长期占用 CDN 侧的连接预算，与紧随其后的 ffmpeg 拉流
    # 争抢（虎牙实测：预算耗尽后 ffmpeg 打开即 403），且全局缓存会引入跨线程共享与进程退出清理复杂度。
    # SEV-N05（同上）：构造原先落在下方 try 之外、只被 finally 覆盖不到，抛穿即打断录制。现把
    # 「构造失败」收敛为「本轮无可用探针客户端」（probe_client=None）而非判成「所有候选不可达」放弃
    # 本轮，三条理由都不构成校验假红：
    # ① client=None 正是 _validate_stream_url 既有的 owns_client 自建路径，未新增分支；
    # ② 自建同样抛错时由该函数既有的 except Exception 记 WARNING「流地址校验异常: {url} -
    #    {type_name}: {e}」，并按「探针拒绝 ≠ ffmpeg 不可拉流」让末位候选（序列末位无 record_url 时，
    #    或 record_url 档本身）放行——故本轮恒有地址返回给 ffmpeg 定夺；
    # ③ 构造失败意味着**一个探针都没发出去**，因此不写 _mark_probe_reject、不把可用线路误记进 CDN
    #    退避表（那才会把一次配置错误放大成后续若干轮的假红）。
    # 归一之后仍能走到这里的只剩「带 scheme 但 httpx 不接受的取值」（如 ftp://…）；handle_proxy_addr
    # 要求入参 str|None，类型异常属编码错误、由 mypy 与用例挡在前面。不额外记一条轮级日志：新增 tr
    # 模板须同步四语目录 + .mo，不属本文件的改动权限。
    probe_client: httpx.Client | None
    try:
        # WP-J：构造改走 _probe_client 单点工厂（逐跳复检钩子随客户端挂上，本轮全部候选与
        # _confirm_get_ok / _probe_hls_segment 那四处 follow_redirects=True 一并被覆盖）；
        # 归一仍在上方那一处、复用作用域仍是单次选源、finally 关闭，形态一律未动。
        probe_client = _probe_client(
            _PROBE_TIMEOUT_SECONDS, proxy_addr, _http_config.get_effective_ssl_verify(platform)
        )
    # M-06：httpx.InvalidURL 直继 Exception（httpx 0.28.1 实测 MRO：InvalidURL → Exception），
    # 不是 ValueError 子类——裸 IPv6 形态的代理（handle_proxy_addr 补全后构造期即抛）会逃出本分支
    # 每轮抛穿房间线程。归入「本轮无可用探针客户端」，走下方既有自建降级路径。
    except ValueError, TypeError, httpx.InvalidURL:
        probe_client = None
    try:
        # MID-19：record_url 通道先过形态白名单——不合规直接摘掉该档（连探针都不发），
        # 并且不再据此给序列末位候选发放 last_resort 资格（那等于把畸形值间接请进 ffmpeg）。
        if record_url_enabled and not _is_recordable_url(record_url_str):
            logger.warning(
                i18n.tr(
                    "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                    url=utils.mask_credentials(record_url_str),
                )
            )
            record_url_enabled = False

        def _accept_source(url: str, kind: str) -> str | None:
            # MID-19：末位放行的语义边界是「网络 / CDN 拒绝」，不是「任何异常」。
            # 平台接口被劫持时回传的 file:///… 、concat:… 、相对路径、以 '-' 开头的串
            # 一律告警丢弃，绝不作为可用源返回（形态说明见 _is_recordable_url）。
            if not _is_recordable_url(url):
                logger.warning(
                    i18n.tr(
                        "流地址形态不合规，已丢弃（不交给 ffmpeg -i）: {url}",
                        url=utils.mask_credentials(url),
                    )
                )
                return None
            # WP-J（2026-09-30）：交付 ffmpeg -i 前的最后一道内网闸门，与上面的形态闸门并列、互不替代
            # （形态白名单管协议与字符合法性，管不住 http://127.0.0.1:6379）。
            # 为什么探针层那道判定（_validate_stream_url 入口）不够：record_url 与本轮已探候选同址时走的是
            # 「复用结论并交由 ffmpeg 拉流」分支（本函数所在作用域下方 `record_url_str in probed`），那条
            # 分支**一个探针都不发**、也就一次都不经过探针入口的判定，于是「探针已判失败的内网地址」会被
            # 原样递给 -i。判定仍复用 async_http 那一份，本模块不另写规则。
            # 成本：只在选中地址时走一次（每轮至多多一次 getaddrinfo，与 MIN-2219 记入的探针成本同量级）；
            # 刻意不给判定结果加缓存——缓存会把一次解析供给所有跳与所有请求，等于主动拉长 DNS 重绑定窗口
            # （理由逐字见 async_http._build_hop_guard 的残余风险登记）。
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
        # 统一为一个有序序列逐候选校验。两处与旧分块逻辑的刻意差异：
        # ① h265 候选在构建序列时按保存格式判定，仅在不支持 HEVC 直拷时剔除（判据见
        #    _h265_copy_format_supported；[历史注 2026-10-01] 原口径「h265 无法 copy 录制、
        #    一律剔除」已按容器可行性收窄）；旧实现
        #    「FLV 为 h265 → 立即重试整组 HLS」在默认顺序（HLS 已在前面试过全败）下会把
        #    HLS 探针白烧一遍；剔除后末位放行（last_resort）基于过滤后的序列判定，
        #    h265 之前的候选自然获得末位资格，语义与旧「插入式回退」一致但不多烧探针。
        # ② last_resort 统一为「过滤后序列的末位 且 无 record_url」：原「HLS 末位还需无
        #    FLV」的条件在新结构下由「序列末位」天然覆盖（其后已无任何候选）。
        #    2026-09-20（MID-18/19）收窄为「无**可用**的 record_url 通道」：被 HLS 整组剔除
        #    规则挡掉的 m3u8 record_url、以及形态不合规的 record_url 都不再给前序候选发放
        #    末位资格——否则「末位放行」会绕开这两道闸门，把本不该进 ffmpeg 的地址请进去。
        flv_first = platform in _FLV_FIRST_PLATFORMS
        # 排除列表命中（hls_excluded）时 hls_effective_enabled 恒为 False，HLS 候选整组
        # 剔除、不进入序列（连同 h265-FLV → HLS 的切换一并失效），恒按 FLV 采集
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

        # 逐候选校验：中间候选失败继续尝试下一候选；仅末位且无可用 record_url 通道时以
        # last_resort 放行（交给 ffmpeg 定夺，探针拒绝 ≠ ffmpeg 不可拉流）。到达分组边界
        # 即意味前一类候选已全部校验失败（顺序遍历），打一条与旧实现同义的回退告警。
        # MID-18：probed 记下本轮已探地址及其结论，供 record_url 复用——虎牙的 record_url
        # 与主 FLV 候选逐字相同、斗鱼亦然，旧实现在选源结束前把同一地址完整再探一次，
        # 正面消耗该 CDN 的连接预算（正是探针退避机制要消除的行为）。
        probed: dict[str, bool] = {}
        # S-04（2026-10-19）：本轮因**安全闸**被拒的地址。与 probed 分开建模的理由：
        # probed 的 False 同时表示「CDN 拒绝」与「安全拒绝」，而 record_url 复用分支对前者的
        # 既有语义是「探针拒绝 ≠ ffmpeg 不可拉流，照常交付」——安全拒绝绝不能继承这条语义。
        security_rejected: set[str] = set()
        prev_kind: bool | None = None
        for idx, (cand, is_hls) in enumerate(usable):
            if prev_kind is not None and is_hls != prev_kind:
                if prev_kind:
                    # L-16（2026-10-02）：用户可见回退告警统一走 i18n（原为裸英文常量）
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
            # 同源候选（观测增强）：HLS 被拒（含「列表 200 但分片 404」假绿）时，若存在同
            # token 的 FLV 候选，显式点名该回退目标——它是斗鱼 hw 事故的首选可用源，
            # 单独记一条便于巡检确认「是否已按预期回退同源 FLV」。
            if is_hls and not probed[cand]:
                same_origin = _same_origin_flv(cand, flv_candidates)
                if same_origin:
                    # MID-N32 修复（2026-09-21，CODE_REVIEW_2026-09-21）：同源 FLV 回退地址同为签名直链
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
            # S-04（2026-10-19）：`not in security_rejected` 这个前置条件把安全拒绝挡在两条交付
            # 路径之外。原实现在复用分支只判 `record_url_str in probed`，于是「同址探过、结论
            # False」会被无条件交付；而抖音 / TikTok / 网易CC 的 record_url 恒等于 m3u8_url 或
            # flv_url，该分支极易命中——安全闸的拒绝实际上形同没有。
            # 不额外打日志：拒绝原因已由 _validate_stream_url 按同一模版发过一条 warning。
            if record_url_str in probed and record_url_str not in security_rejected:
                # MID-18：同一地址本轮已探过——复用结论、零新增探针。record_url 是末位档，
                # 沿用「探针拒绝 ≠ ffmpeg 不可拉流」的既有语义：即便上一轮探针判失败，
                # 也照常交由 ffmpeg 定夺（与旧实现「再探一次 + 末位放行」结果一致，
                # 只是不再多烧一整轮 HEAD/Range-GET/分片探针）。
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
        # 观测增强：整轮无可用源时补一条收束结论（逐候选告警已各自给出原因），
        # 让「房间一直不录制」在日志里有一句可检索的结论行
        if hls_available and not hls_effective_enabled:
            # HLS 组被配置整组剔除是唯一「零日志静默丢弃」的选源成因：有 FLV/record_url 兜底时
            # 上方 1134 的早退告警不触发、候选序列里也看不到 m3u8 的踪影，用户只能对着
            # 「在播但不录制且无告警」猜配置原因（2026-10-01 死锁房实测盲区），无源结论前必须
            # 点名并给恢复开关；选中源的轮次不打——观测只跟随失败轮，健康轮零噪音。
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
        # 选源结束即释放连接：连接预算要让给随后的 ffmpeg 拉流
        # SEV-N05 修复（同上）：整轮共用客户端构造失败时 probe_client 为 None（本轮无可用探针
        # 客户端，各候选已改走自建路径），此时无连接可释放，须跳过关闭
        if probe_client is not None:
            try:
                probe_client.close()
            except Exception as e:
                logger.debug(i18n.tr("关闭探针客户端失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


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
