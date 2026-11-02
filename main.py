#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

# DouyinLiveRecorder 主程序入口（CLI 录制 + Web 录制引擎）
#
# 职责：读取配置 → 平台分派 → 取流选源 → ffmpeg 录制或直下 → 守护收尾；
# 并管理并发调度、错误重试、状态推送与运行日志归档。
#
# 主链路：
#     URL_config.ini → 平台识别 → 取流选源 → ffmpeg/直下 → 状态监控 → 转码/推送
#
# 对外入口与可观测面：
# - main(non_interactive)：录制主循环；CLI 直跑与 web.py 守护线程共用
# - start_record(url_data, count_variable, room_state)：单个直播间的录制线程主体
# - check_subprocess(...)：启动并守护一次 ffmpeg 录制子进程
# - get_status()：录制引擎状态快照，供 Web API 读取
#
# Author: Hmily
# GitHub: https://github.com/ihmily
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.

# stdout/stderr 必须最先统一为 UTF-8：冻结后的 exe 作为 GUI/Web 子进程时 stdout 是管道，
# Python 会回退到 GBK 区域编码，而父进程按 UTF-8 读取 → 中文乱码。
# 必须先于任何日志/控制台模块导入（如 src.logger）：loguru 的 sink 一旦按旧编码绑定，
# 后续 reconfigure 不会重绑，整轮运行的日志编码就此定型。
import os
import sys

# `python main.py` 时本模块叫 `__main__`；src 子模块若 `import main` 会再次执行整个文件
# （双重初始化、配置重读）。先把 `main` 指向当前模块，避免重执行。
if sys.modules.get("main") is None:
    sys.modules["main"] = sys.modules["__main__"]


# 把 stdout/stderr 重配置为 UTF-8；Windows 另外切控制台代码页，否则 UTF-8 字节在 GBK 控制台仍乱码
def _fix_encoding() -> None:
    import io
    from typing import cast

    _streams: list[io.TextIOWrapper | None] = [
        cast(io.TextIOWrapper | None, getattr(sys, "stdout", None)),
        cast(io.TextIOWrapper | None, getattr(sys, "stderr", None)),
    ]
    if sys.platform == "win32":
        for _s in _streams:
            if _s is not None and hasattr(_s, "reconfigure"):
                try:
                    _s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass
        # 无控制台（窗口化/管道）时 SetConsole* 会失败，忽略即可
        try:
            import ctypes

            # WinDLL 而非 windll：对齐全仓惯例（AGENTS「Python 版本」条）。
            _k32 = ctypes.WinDLL("kernel32")
            _k32.SetConsoleOutputCP(65001)
            _k32.SetConsoleCP(65001)
        except Exception:
            pass
    else:
        for _s in _streams:
            if _s is not None and hasattr(_s, "reconfigure"):
                try:
                    _s.reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass


_fix_encoding()

import asyncio
import atexit
import builtins
import configparser
import datetime
import random
import re
import signal
import subprocess
import tempfile
import threading
import time
import types
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx
from loguru import logger

from src import get_danmaku_collector, spider, stream, utils
from src.config_io import (
    _safe_float,
    _safe_int,
    backup_file_start,
    delete_line,
    read_config_bool,
    read_config_value,
    update_anchor_name,
    update_file,
)
from src.config_read import tolerant_config_parser, warn_duplicate_options
from src.ffmpeg_install import check_ffmpeg, ffmpeg_path, should_prepend_bundled_ffmpeg_dir

# ---- 重构：以下函数已抽离至 src 子模块，此处重新导出以保持 main.<name> 命名空间兼容 ----
from src.ffmpeg_proc import (
    _get_error_line,
    _terminate_ffmpeg_process,
    cleanup_all_ffmpeg_processes,
    register_ffmpeg_process,
    unregister_ffmpeg_process,
)
from src.log_archive import archive_runtime_logs
from src.logger import set_room_context
from src.notify import (
    adjust_max_request,
    clear_record_info,
    push_message,
    record_error,
    record_success,
    remove_room_from_running,
    run_script,
)
from src.proxy import ProxyDetector
from src.recorder_status import display_info, get_status
from src.scheduler import ConcurrencyScheduler, ResizableSemaphore, host_of
from src.startup_cleanup import purge_stale_bytecode_caches
from src.stream_select import (
    MOBILE_UA,
    _douyin_rate_limit,
    _validate_stream_url,
    clean_name,
    clear_ffmpeg_reject,
    contains_url,
    get_quality_code,
    get_record_headers,
    get_record_user_agent,
    mark_ffmpeg_reject,
    select_source_url,
)

# 死引用的唯一判据：生产代码零引用**且**测试零依赖。本列表刻意不含 converts_m4a / segment_video /
# shlex / Mapping（生产零引用，留着会让人误以为「音频直出 / 分段转码」链路已接通）；
# _run_ffmpeg_checked 与 _validate_stream_url 虽在本文件无调用点，但分别是 tests/test_main_fixes.py
# 的 patch 目标与 9 处直调锁（末位放行 / 分片假绿），删除会让用例 AttributeError，故保留。
from src.video_postprocess import _run_ffmpeg_checked, converts_mp4, generate_subtitles, get_startup_info


# 版本号唯一事实源是 pyproject.toml；解析失败时回退 v0.0.0
# 已安装发行包时走 importlib.metadata；源码直跑取不到包名，只能自行解析 pyproject.toml
def _read_version_from_pyproject() -> str:
    try:
        from importlib.metadata import version as get_version

        return f"v{get_version('DouyinLiveRecorder')}"
    except Exception:
        pass
    pyproject_path = Path(__file__).parent / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
        if m:
            return f"v{m.group(1)}"
    return "v0.0.0"  # 最终回退


# 版本号取自 pyproject.toml；平台清单仅用于 banner 展示，准入判据以 PLATFORM_HOST 为准
version: str = _read_version_from_pyproject()
platforms: str = (
    "\n国内站点：抖音|快手|虎牙|斗鱼|YY|B站|小红书|bigo|blued|网易CC|千度热播|猫耳FM|Look直播|TwitCasting|百度|微博|"
    "酷狗|花椒|流星|Acfun|畅聊|映客|音播|知乎|嗨秀|VV星球|17Live|浪Live|飘飘|六间房|乐嗨|花猫|淘宝|京东|咪咕|连接|来秀"
    "\n海外站点：TikTok|SOOP(原AfreecaTV)|PandaTV|WinkTV|TTingLive(原Flextv)|PopkonTV|TwitchTV|LiveMe|ShowRoom|CHZZK|Shopee|"
    "YouTube|Faceit|Picarto"
)

# ==================== 全局状态变量 ====================

# 录制状态管理
recording: set[str] = set()  # 正在录制的直播间集合
monitoring: int = 0  # 正在监控的直播间数量
running_list: list[str] = []  # 正在运行的 URL 列表
recording_time_list: dict[str, list[datetime.datetime | str]] = {}  # [开始时间, 设置画质, 实际画质]
exit_recording: bool = False  # 退出标志
# 磁盘空间不足导致的「录制暂停」标志：与 exit_recording（进程级退出意图，不复位）不同，
# disk_limited 表达可逆的资源约束——空间腾出后必须复位，否则主循环与房间线程永远停在暂停态。
# 空间不足期间两者同步置位，恢复时同步复位；判据见
# tests/test_regression_main.py::test_disk_limited_is_recoverable
disk_limited: bool = False
# 上一次**成功**测得的磁盘剩余空间（GB）。检测失败的那一轮沿用此值而不是置 inf——把「测不到」
# 当成「空间无限」会让磁盘暂停在盘离线时被误解除。
disk_free_gb: float = float("inf")
# Web 模式录制开关：False 时主循环不拉起新房间线程，既有房间线程终止 ffmpeg/下载后退出。
# CLI/GUI 直跑保持 True（行为不变）；web.py 启动录制引擎前置 False，由 Web 面板
# 「开始/停止录制」按钮经 POST /api/recording/toggle 手动切换（见 src/web_api.py）。
recording_enabled: bool = True

# 错误控制和动态调优
error_count: int = 0  # 累计错误计数（自进程启动起单调递增，不做周期清零；窗口口径见 error_window）
max_request: int = 3  # 同一时间访问网络的线程数（由 main() 读取配置后覆盖）
max_request_lock: threading.Lock = threading.Lock()  # 最大请求数的线程锁
error_window_size: int = 10  # 错误窗口大小
error_window: deque[int] = deque(maxlen=error_window_size)  # 错误窗口（deque maxlen 自动裁剪，避免无界增长）
# [历史注] 此处原有的 error_threshold（错误率阈值）全仓零引用：并发压制已由 src/scheduler.ConcurrencyScheduler 接管。

# URL 和配置管理
url_tuples_list: list[tuple[str, str, str]] = []  # 解析后的 URL 配置项（画质, URL, 主播名）
# 被注释掉的 URL 集合：主循环与 check_subprocess/start_record 只做成员检测，用 set 保证 O(1)
url_comments: set[str] = set()
text_no_repeat_url: list[tuple[str, str, str]] = []  # 保序去重后的 URL 配置项
need_update_line_list: list[str] = []  # 需要更新的配置行
not_record_list: list[str] = []  # 本轮需跳过的规范 URL（Shopee uid 回写后）
ini_URL_content: str = ""  # URL 配置文件初始内容（用于 update_file 异常恢复）

# 标志变量
first_start: bool = True  # 首次启动标志
first_run: bool = True  # 首次运行标志
global_proxy: bool = False  # 全局代理启用标志
use_proxy: bool = False  # 是否使用代理 IP（由 main() 读取配置后覆盖）
create_var: dict[str, threading.Thread] = {}  # 动态创建的线程登记表（字幕线程 / 房间线程）
start_display_time: "datetime.datetime" = datetime.datetime.now()  # 显示信息开始时间
# 进程启动时刻，专供 uptime 计算。上报展示用的 start_display_time 会被 display_info 周期改写，
# 若 uptime 也用它，面板运行时长会恒在 0~5 秒之间跳变，运维据此判断「是否需重启」的依据失效。
process_start_time: "datetime.datetime" = datetime.datetime.now()

# 录制配置（由 main() 读取 config.ini 后覆盖，此处给默认值供 display_info 等函数引用）
delay_default: int = 120  # 循环监测间隔时间（秒）
video_record_quality: str = "原画"  # 录制视频画质
video_save_type: str = "ts"  # 录制视频格式
split_video_by_time: bool = False  # 是否开启分段录制
split_time: str = "1800"  # 视频分段时间（秒）
create_time_file: bool = False  # 是否生成时间字幕文件
auto_update_anchor_name: bool = True  # 主播名变更时自动同步配置与录制文件（由 main() 读取配置后覆盖）
hls_collection_enabled: bool = True  # 是否优先使用 HLS(m3u8) 源采集；关闭时回退 FLV
# HLS 采集排除平台列表（「HLS采集排除平台(逗号分隔)」，由 main() 读取配置后覆盖）：
# 命中平台无视「是否启用HLS采集」配置、恒按 FLV 采集（等效于仅对该平台关闭 HLS 采集）
hls_collection_exclude_platforms: list[str] = []
# 弹幕录制设置（main() 热加载配置时经 global 写回，check_subprocess 读取）
enable_danmaku: bool = False  # 是否录制弹幕
enable_danmaku_monitor: bool = False  # 是否弹幕监控（与弹幕录制解耦：仅监控不落 SRT）
danmaku_split_time: float = 1800.0  # 弹幕分片时长(秒)
danmaku_platforms: list[str] = []  # 弹幕录制平台列表

# ==================== 路径和配置 ====================


# 应用根目录：源码运行时是主脚本目录；冻结运行（onedir + _internal）时是 exe 同级目录——
# config/ ffmpeg/ node/ 等运行时资源在 exe 同级，而 src/ 及依赖在 exe_dir/_internal/。
def _app_root() -> str:
    # 供定位 config/ffmpeg/node，不能用 _internal/ 内的模块路径
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.split(os.path.realpath(sys.argv[0]))[0]


script_path: str = _app_root()  # 脚本所在目录（冻结后为 exe 同级目录）
config_file: str = f"{script_path}/config/config.ini"  # 主配置文件路径
url_config_file: str = f"{script_path}/config/URL_config.ini"  # URL 配置文件路径
backup_dir: str = f"{script_path}/backup_config"  # 配置备份目录
text_encoding: str = "utf-8-sig"  # 文本文件编码（兼容 BOM）
rstr: str = r"[\/\\\:\*\？?\"\<\>\|&#.。,， ~！·% ]"  # 文件名字符过滤正则
# `%` 必须在名单内：输出路径会被 ffmpeg 当作 printf 文件名模板解析，
# 主播名/标题里的裸 `%` 会与分段占位符 `_%03d` 冲突，ffmpeg 以 -22 秒退，
# 随后被误判成「CDN 快速失败」而拉黑健康线路。
# 回归锁：tests/test_regression_main.py::test_segment_template_has_single_percent_placeholder
default_path: str = f"{script_path}/downloads"  # 默认下载目录
# 模块导入不建目录：任何 `import main`（GUI / Web / 测试）都不应在宿主机产生磁盘副作用。
# 下载目录由 main() 入口与录制路径按需创建。
# RLock：主循环持锁读配置期间可能再次进入 read_config_value 的写入路径，可重入避免同线程死锁
file_update_lock: threading.RLock = threading.RLock()  # 配置文件读写锁（防多线程写入冲突）

# 录制状态全局锁（保护 recording/running_list/monitoring/recording_time_list）
record_state_lock: threading.Lock = threading.Lock()

# ==================== 配置变量（由 main() 读取 config.ini 后覆盖） ====================
# 以下声明供 main() 之外的函数（push_message, start_record 等）引用，
# 避免类型检查器在未追踪 global 声明时报告 "Could not find name"。

# 代理与网络
proxy_addr: str | None = None
proxy_addr_bak: str = ""
enable_proxy_platform: str = ""
enable_proxy_platform_list: list[str] | None = None
extra_enable_proxy: str = ""
extra_enable_proxy_platform_list: list[str] | None = None

# 海外/代理平台判定只看 urlsplit 得到的 hostname，但条目本身仍按**子串**比对：配置默认值里的
# tiktok / twitch / shopee / chzzk / youtu / shp 都不含点号，`youtu` 更是 `youtube` 的前缀而非独立
# 标签——若要求「含点号且按标签边界匹配」，默认配置过半条目会静默失效、代理对它们全部不再生效。
# [历史注] 旧实现拿条目在整条 URL 上做子串匹配，query 里出现平台名即误判为海外/走代理。
_PROXY_PLATFORM_MIN_SUFFIX_LEN = 3


def _host_in_platform_list(record_url: str, entries: list[str] | None) -> bool:
    if not entries:
        return False
    try:
        host = (urlsplit(record_url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    for entry in entries:
        token = entry.strip().strip("/").strip(".").lower()
        # 过短的条目（单字符/空）不参与判定：否则 `a` 会命中任何含 a 的主机。
        if len(token) < _PROXY_PLATFORM_MIN_SUFFIX_LEN:
            continue
        if token in host:
            return True
    return False


# 并发调度器：自适应全局网络并发 + 按平台(host)熔断降级 + 可选录制并发软上限。
# 由 main() 启动时实例化；semaphore/recording_semaphore 指向其内部信号量，供 `with` 直接使用。
scheduler: ConcurrencyScheduler | None = None
semaphore: ResizableSemaphore = ResizableSemaphore(1)
recording_semaphore: ResizableSemaphore = ResizableSemaphore(1024)
local_delay_default: int = 0
loop_time: bool = False
show_url: bool = False
enable_https_recording: bool = False
disk_space_limit: float = 1.0

# 抖音请求速率限制器：防止多线程并发请求触发抖音风控
# 保证同一时刻只有一个抖音 API 请求在执行，且两次请求之间至少间隔 N 秒
douyin_rate_lock: threading.Lock = threading.Lock()
douyin_last_request_time: float = 0.0
douyin_min_interval: float = 3.0  # 两次抖音请求的最小间隔（秒）

# 录制与文件
video_save_path: str = ""
# 单次录制时长上限（秒），由 main() 每轮热加载；0/负值表示不限制，分段开/关均参与判定
# （见 check_subprocess 的 _record_limit_seconds）。
# 字面默认值与 _MAX_RECORD_SECONDS 同值：后者定义在本行之后，模块级语句不能前向引用。
max_record_seconds: int = 6 * 60 * 60
clean_emoji: bool = True
filename_by_title: bool = False
folder_by_author: bool = False
folder_by_time: bool = False
folder_by_title: bool = False
converts_to_h264: bool = False
converts_to_mp4: bool = False
delete_origin_file: bool = False
is_run_script: bool = False
custom_script: str | None = None
video_save_type_list: tuple[str, ...] = ("FLV", "MKV", "TS", "MP4", "MP3音频", "M4A音频", "MP3", "M4A")

# 推送配置
live_status_push: str = ""
push_message_title: str = ""
begin_show_push: bool = True
begin_push_message_text: str = ""
over_show_push: bool = False
over_push_message_text: str = ""
disable_record: bool = False
push_check_seconds: int = 1800

# 钉钉 / 微信 / Bark
dingtalk_api_url: str = ""
dingtalk_phone_num: str = ""
dingtalk_is_atall: bool = False
xizhi_api_url: str = ""
bark_msg_api: str = ""
bark_msg_level: str = "active"
bark_msg_ring: str = "bell"

# 邮件
email_host: str = ""
email_password: str = ""
login_email: str = ""
sender_email: str = ""
sender_name: str = ""
to_email: str = ""
smtp_port: str = ""
open_smtp_ssl: bool = True

# Telegram / NTFY / PushPlus
tg_chat_id: str = ""
tg_token: str = ""
ntfy_api: str = ""
ntfy_tags: str = "tada"
ntfy_email: str = ""
pushplus_token: str = ""

# 账号密码
sooplive_username: str = ""
sooplive_password: str = ""
flextv_username: str = ""
flextv_password: str = ""
popkontv_username: str = ""
popkontv_partner_code: str = "P-00001"
popkontv_password: str = ""
popkontv_access_token: str = ""
twitcasting_account_type: str = "normal"
twitcasting_username: str = ""
twitcasting_password: str = ""

# Cookie 变量
dy_cookie: str = ""
ks_cookie: str = ""
tiktok_cookie: str = ""
hy_cookie: str = ""
douyu_cookie: str = ""
yy_cookie: str = ""
bili_cookie: str = ""
xhs_cookie: str = ""
bigo_cookie: str = ""
blued_cookie: str = ""
sooplive_cookie: str = ""
netease_cookie: str = ""
qiandurebo_cookie: str = ""
pandatv_cookie: str = ""
maoerfm_cookie: str = ""
winktv_cookie: str = ""
flextv_cookie: str = ""
look_cookie: str = ""
liveme_cookie: str = ""
huajiao_cookie: str = ""
liuxing_cookie: str = ""
showroom_cookie: str = ""
acfun_cookie: str = ""
changliao_cookie: str = ""
yinbo_cookie: str = ""
yingke_cookie: str = ""
zhihu_cookie: str = ""
chzzk_cookie: str = ""
haixiu_cookie: str = ""
vvxqiu_cookie: str = ""
yiqilive_cookie: str = ""
langlive_cookie: str = ""
pplive_cookie: str = ""
six_room_cookie: str = ""
lehaitv_cookie: str = ""
huamao_cookie: str = ""
shopee_cookie: str = ""
youtube_cookie: str = ""
taobao_cookie: str = ""
jd_cookie: str = ""
faceit_cookie: str = ""
migu_cookie: str = ""
lianjie_cookie: str = ""
laixiu_cookie: str = ""
picarto_cookie: str = ""
baidu_cookie: str = ""
weibo_cookie: str = ""
kugou_cookie: str = ""
twitch_cookie: str = ""
twitcasting_cookie: str = ""

# main() 循环临时变量（global 声明引用，避免类型检查报错）
a: str | None = None
args: tuple[object, ...] | None = None
input_url: str = ""
is_comment_line: bool = False
line: str = ""
line_spilt: list[str] = []
middle: str = ""
name: str = ""
new_line: tuple[str, ...] = ()
new_url: str = ""
new_word: str = ""
origin_line: str = ""
quality: str = "原画"
replace_words: list[str] = []
running_snapshot: list[str] = []
running_url: str = ""
split_line: list[str] = []
start_with: str | None = None
t: threading.Thread | None = None
t2: threading.Thread | None = None
url: str = ""
url_host: str = ""
url_tuple: tuple[str, ...] = ()

_recorder_thread = None  # 由 web.py 设置，用于 get_status() 检测存活


# 可中断等待：一次性 time.sleep(n) 收敛为逐秒 tick，使「退出 / 停止录制 / URL 被注释」在 1 秒内得到
# 响应（这些判定只发生在循环顶）；每秒重新求值模块全局即晚绑定，能看到其他线程与 Web 面板的最新改动。
#
# 返回值 = 是否被提前中断。中断时本函数零耗时返回，而两处 continue 分支恰好跳过主循环末尾的
# time.sleep(3)：Web 模式启动即置 recording_enabled=False，「面板刚起、用户还没填 URL」的默认状态
# 会让循环零间隔空转（打满一核、反复解析配置与 URL 文件），故调用方必须补一个固定退避。
def _interruptible_sleep(seconds: float, record_url: str | None = None) -> bool:
    _remaining = int(seconds) if seconds > 0 else 0
    while _remaining > 0:
        if exit_recording or not recording_enabled:
            return True
        if record_url is not None and record_url in url_comments:
            return True
        time.sleep(1)
        _remaining -= 1
    return False


# 后处理线程池必须在**我们自己的退出路径**上显式排空（safe_exit / 磁盘满退出）：解释器退出时
# threading._shutdown() 先于 atexit 回调执行，池内 worker 的 join 会早于 archive_runtime_logs /
# cleanup_all_ffmpeg_processes / close_all_clients_sync；转封装最长可占 3600s，期间 ffmpeg 无人
# 终止、日志无人归档，表现为「退出卡住、事后查不到日志」。先 drain 让顺序回到主进程手里，
# 之后 _python_exit 再跑即为空转。模块侧若无 shutdown_postprocess_executor 则退回收本文件自己的池；
# 池未创建过时零动作。排空参数固定 wait=True、cancel_futures=False：改成 wait=False 会把在途转码的
# 产物留在半截。
def _shutdown_postprocess_executor() -> None:
    try:
        from src import video_postprocess as _vp
    except Exception:
        _shutdown_own_postprocess_pool()
        return
    _shutdown = getattr(_vp, "shutdown_postprocess_executor", None)
    if _shutdown is None:
        _shutdown_own_postprocess_pool()
        return
    if not _run_bounded_drain(lambda: _shutdown(wait=True, cancel_futures=False)):
        # 超预算：再补一次「取消未开始的任务」。ThreadPoolExecutor.shutdown 可重入，
        # 第二次 wait=False 立即返回，把排队中的转封装任务撤掉。
        try:
            _shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            logger.warning(i18n.tr("后处理线程池收尾失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 排空预算：单次转封装最长可占 3600s，信号处理器里无预算 drain 会让 Ctrl+C 卡住整小时，
# ffmpeg 清理、连接关闭、日志归档与 sys.exit 全部排在后面。
# 预算只约束等待时长，不改变排空顺序；超预算由调用方取消未开始的任务。
# 取 15s 是「正常收尾够用、异常收尾不像挂死」的经验值，不走配置项（退出兜底不应再引入外部开关）。
_POSTPROCESS_DRAIN_BUDGET_SECONDS = 15.0


def _run_bounded_drain(drain: Callable[[], None], budget: float = _POSTPROCESS_DRAIN_BUDGET_SECONDS) -> bool:
    # drain 在守护线程里执行，主线程只等 budget 秒：shutdown(wait=True) 遇到卡死的转封装
    # 任务无法中断，只能「不等了」。超时后不 join（它仍阻塞在 wait=True），故必须 daemon=True。
    # 返回 True = 预算内已排空；False = 超预算，由调用方决定是否取消剩余任务。
    done = threading.Event()

    def _target() -> None:
        try:
            drain()
        except Exception as e:
            logger.warning(i18n.tr("后处理线程池收尾失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        finally:
            done.set()

    worker = threading.Thread(target=_target, name="postprocess-drain", daemon=True)
    worker.start()
    if done.wait(budget):
        return True
    logger.warning(
        i18n.tr(
            "后处理线程池排空超过 {budget} 秒，已放弃等待并继续退出（在途转封装可能留下半截产物）",
            budget=int(budget),
        )
    )
    return False


# 自持回退：关闭本文件的 `_postprocess_executor`。独立成函数便于测试单独驱动该分支。
def _shutdown_own_postprocess_pool() -> None:
    with _postprocess_executor_lock:
        pool = _postprocess_executor
    if pool is None:
        return
    if _run_bounded_drain(lambda: pool.shutdown(wait=True, cancel_futures=False)):
        return
    # 超预算后再补一次「取消未开始的任务」：第一次 shutdown 已在守护线程里阻塞在 wait=True，
    # 这里 wait=False + cancel_futures=True 立即返回，把排队的转封装任务取消掉，
    # 避免它们在本进程余下的退出步骤里继续抢占 ffmpeg 与磁盘。
    try:
        pool.shutdown(wait=False, cancel_futures=True)
    except Exception as e:
        logger.warning(i18n.tr("后处理线程池收尾失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 信号处理器：置退出标志 → 排空后处理池 → 清理 ffmpeg 与 HTTP 连接池 → 退出进程
def safe_exit(_signum: int, _frame: types.FrameType | None) -> None:
    global exit_recording
    exit_recording = True
    color_obj.print_colored("\n正在安全退出...", color_obj.YELLOW)
    # 先排空后处理线程池，再做 ffmpeg / HTTP 连接池清理（理由见 _shutdown_postprocess_executor 上方注释）
    _shutdown_postprocess_executor()
    cleanup_all_ffmpeg_processes()
    from src.async_http import close_all_clients_sync

    close_all_clients_sync()
    sys.exit(0)


# 注册信号处理器
_ = signal.signal(signal.SIGINT, safe_exit)
_ = signal.signal(signal.SIGTERM, safe_exit)
if hasattr(signal, "SIGBREAK"):
    _ = signal.signal(signal.SIGBREAK, safe_exit)

# 进程退出兜底（硬杀 / 未捕获异常 / Web 面板退出等非优雅路径）。
# atexit 为 LIFO：archive_runtime_logs 必须先注册，才会最后执行——四份运行日志按
# 「原名_YYYYMMDD_HHMMSS.扩展名」归档时，才能把前面 ffmpeg / 连接池清理产生的收尾日志一并收进去。
_atexit_result_0 = atexit.register(archive_runtime_logs, reopen_streams=False)
_atexit_result_1 = atexit.register(cleanup_all_ffmpeg_processes)
# async_req 供 _resolve_hy_fan_room_segment 解析虎牙移动端短链（redirect_url=True 契约）；
# 与 close_all_clients_sync 同源，不新增导入环。
from src.async_http import async_req, close_all_clients_sync

_atexit_result_2 = atexit.register(close_all_clients_sync)


os_type: str = os.name
color_obj: "utils.Color" = utils.Color()
# 把 ffmpeg 目录前置到 PATH：读实时 os.environ（不是 import 时快照），并跳过重复插入。
# 「是否前置」由 src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir 统一裁决——Apple Silicon
# 上包内 x86_64 静态 ffmpeg 会遮蔽用户已装的原生 arm64 构建并强制走 Rosetta，判据不在此复制。
_current_path = os.environ.get("PATH", "")
ffmpeg_path_norm = os.path.normpath(ffmpeg_path)
if (
    ffmpeg_path_norm
    and ffmpeg_path_norm not in _current_path.split(os.pathsep)
    and should_prepend_bundled_ffmpeg_dir(ffmpeg_path_norm, _current_path)
):
    os.environ["PATH"] = ffmpeg_path_norm + os.pathsep + _current_path
else:
    os.environ["PATH"] = _current_path

PLATFORM_HOST = [
    "live.douyin.com",
    "v.douyin.com",
    "www.douyin.com",
    "live.kuaishou.com",
    "www.huya.com",
    # 虎牙移动端分享短链：数字段即房间号，其余为短码，由 _resolve_hy_fan 归一成
    # www.huya.com 后复用桌面链路。准入按 url_host 精确匹配，缺此项会在读取配置阶段
    # 被判「未知链接」并注释掉，走不到解析。
    "hy.fan",
    "www.douyu.com",
    # 斗鱼移动端页面：接口只认数字 rid，与来源域名无关，与 www 共用 _resolve_douyu_com。
    # 准入按 url_host 精确匹配，缺此项会在配置读取阶段被判「未知链接」。
    "m.douyu.com",
    "www.yy.com",
    "live.bilibili.com",
    # B站移动端分享短链：数字段即房间号，其余为短码，由 _resolve_b23_tv 归一成
    # live.bilibili.com 后复用桌面链路。准入按 url_host 精确匹配，缺此项走不到解析。
    "b23.tv",
    # www.redelight.cn 已摘除：全仓无解析入口，留着只会让用户配出一个每轮报错、永不录制、
    # 也不计失败样本的空转房间。不变式见 tests/test_platform_dispatch.py：
    # PLATFORM_HOST 每项必须被某个 resolver 片段命中。
    "www.xiaohongshu.com",
    "xhslink.com",
    "www.bigo.tv",
    "slink.bigovideo.tv",
    "app.blued.cn",
    "cc.163.com",
    "qiandurebo.com",
    "fm.missevan.com",
    "look.163.com",
    "twitcasting.tv",
    "live.baidu.com",
    "weibo.com",
    "fanxing.kugou.com",
    "fanxing2.kugou.com",
    "mfanxing.kugou.com",
    "www.huajiao.com",
    "www.7u66.com",
    "wap.7u66.com",
    "live.acfun.cn",
    "m.acfun.cn",
    "live.tlclw.com",
    "wap.tlclw.com",
    "live.ybw1666.com",
    "wap.ybw1666.com",
    "www.inke.cn",
    "www.zhihu.com",
    "www.haixiutv.com",
    "h5webcdnp.vvxqiu.com",
    "17.live",
    "www.lang.live",
    "m.pp.weimipopo.com",
    "v.6.cn",
    "m.6.cn",
    "www.lehaitv.com",
    "h.catshow168.com",
    "e.tb.cn",
    "m.tb.cn",
    "tbzb.taobao.com",
    "huodong.m.taobao.com",
    "3.cn",
    "eco.m.jd.com",
    "www.miguvideo.com",
    "m.miguvideo.com",
    "show.lailianjie.com",
    "www.imkktv.com",
    "www.picarto.tv",
    "www.tiktok.com",
    "play.sooplive.co.kr",
    "m.sooplive.co.kr",
    "www.sooplive.com",
    "m.sooplive.com",
    "www.pandalive.co.kr",
    "www.winktv.co.kr",
    "www.flextv.co.kr",
    "www.ttinglive.com",
    "www.popkontv.com",
    "www.twitch.tv",
    "www.liveme.com",
    "www.showroom-live.com",
    "chzzk.naver.com",
    "m.chzzk.naver.com",
    "live.shopee.co",
    "shp.ee",
    "www.youtube.com",
    "youtu.be",
    "www.faceit.com",
]

OVERSEAS_PLATFORM_HOST = [
    "www.tiktok.com",
    "play.sooplive.co.kr",
    "m.sooplive.co.kr",
    "www.sooplive.com",
    "m.sooplive.com",
    "www.pandalive.co.kr",
    "www.winktv.co.kr",
    "www.flextv.co.kr",
    "www.ttinglive.com",
    "www.popkontv.com",
    "www.twitch.tv",
    "www.liveme.com",
    "www.showroom-live.com",
    "chzzk.naver.com",
    "m.chzzk.naver.com",
    "live.shopee.co",
    "shp.ee",
    "www.youtube.com",
    "youtu.be",
    "www.faceit.com",
]

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


# httpx 流式直下 FLV（不经 ffmpeg）：请求头/cookie/UA 与 ffmpeg 路径同源；
# record_name/live_url 用于中断判断与状态清理，platform 用于补平台请求头；返回是否下载完成。
# 失败只清理**零字节**残留：open(..., "wb") 一进入就建文件，非 200 直 return 会留下 0 字节 .flv，
# 被归档/转码链路当成有效产物。已下载到内容时（下播、CDN 掐断、主动停止）一律保留。
def direct_download_stream(
    source_url: str,
    save_path: str,
    record_name: str,
    live_url: str,
    platform: str,
    cookies: str | None = None,
) -> bool:
    _downloaded = 0
    try:
        with open(save_path, "wb") as f:
            headers: dict[str, str] = {}
            header_params = get_record_headers(platform, live_url, cookies=cookies)
            if header_params:
                headers.update(header_params)
            # UA 取平台专属值，取不到则回落 MOBILE_UA（与 ffmpeg 路径同一常量）。
            # 直下平台（shopee / 花椒）没有专属 UA，缺省会让 httpx 发 python-httpx 默认 UA，
            # CDN 按 UA 风控时会「探针通过、下载 403」。回归锁：
            # tests/test_regression_main.py::test_direct_download_always_sends_ua
            headers["User-Agent"] = get_record_user_agent(platform) or MOBILE_UA

            # headers 只逐请求传，不挂 client 级：client 头会跟随经该 client 的每一个请求
            # （含重定向），一旦复用就会带出录制的 Referer/Cookie（与 src/stream_select.py 探针同口径）。
            with httpx.Client(timeout=30, verify=_http_config.get_effective_ssl_verify(platform)) as client:
                with client.stream("GET", source_url, headers=headers, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(
                            i18n.tr(
                                "请求直播流失败: {source_url} - 状态码: {status_code}",
                                # 拉流地址带签名参数，必须先脱敏再入日志（占位符名沿用既有 msgid）
                                source_url=utils.mask_credentials(source_url),
                                status_code=response.status_code,
                            )
                        )
                        return False

                    downloaded = 0
                    chunk_size = 1024 * 16

                    for chunk in response.iter_bytes(chunk_size):
                        if live_url in url_comments or exit_recording or not recording_enabled:
                            # f-string 直传 print_colored 提取器扫不到（盲区①），先查表后插值才能被目录命中
                            color_obj.print_colored(
                                i18n.tr("[{record_name}]录制时已被注释或停止录制,下载中断", record_name=record_name),
                                color_obj.YELLOW,
                            )
                            clear_record_info(record_name, live_url)
                            _downloaded = downloaded
                            return False

                        if chunk:
                            _ = f.write(chunk)
                            downloaded += len(chunk)
                            _downloaded = downloaded
                    print()
                    # HTTP 200 + 空/极小响应体不算成功：否则调用方会打印「录制完成」并记成功样本，
                    # 而文件已被 finally 删掉，坏线路也绕开按 host 熔断统计。
                    # 口径与 check_subprocess 的 `0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES` 一致。
                    if _downloaded < _MIN_VALID_RECORD_BYTES:
                        logger.error(
                            i18n.tr(
                                "直下直播流响应体过小（{size} 字节），按失败处理: {masked_url}",
                                size=_downloaded,
                                masked_url=utils.mask_credentials(source_url),
                            )
                        )
                        return False
                    return True
    except Exception as e:
        logger.error(
            i18n.tr(
                "FLV下载错误: {source_url} - {type_name}: {e} 发生错误的行数: {get_error_line}",
                # 同上：入日志前先脱敏
                source_url=utils.mask_credentials(source_url),
                type_name=type(e).__name__,
                e=e,
                get_error_line=_get_error_line(e),
            )
        )
        return False
    finally:
        # 仅在「open 已创建文件但一个字节都没写」时删除（判据与理由见函数头注释）
        if _downloaded == 0:
            try:
                os.remove(save_path)
                logger.debug(i18n.tr("已清理零字节的直下残留文件: {save_path}", save_path=save_path))
            except OSError:
                pass


# 输出扩展名 → segment 内层容器：必须严格一致，否则轻则播放器拒绝，重则封装失败。
# [历史注] 曾把 TS 与 M4A 两值互换（HEVC 拷进 ipod 直接 -22 退出、H.264 把 MP4 内容写进 .ts 静默损坏），回归锁 tests/test_record_container.py。
SEGMENT_FORMAT_BY_SUFFIX: dict[str, str] = {
    ".ts": "mpegts",
    ".flv": "flv",
    ".mkv": "matroska",
    ".mp4": "mp4",
    ".m4a": "ipod",
    # .mp3 → mp3 容器：此前缺表项会被兜底成 ipod（MP3 装进 MP4 容器），与历史「TS 装进 ipod」同类错配。
    ".mp3": "mp3",
}


# 「快速失败」阈值（秒）：进程存活不超过该值即退出，视为输入打开被 CDN 拒绝的签名
# （实测虎牙 HS 线路探针 200、ffmpeg 约 1 秒 403）；重连耗尽通常远超此值。模块级常量便于测试注入。
_FFMPEG_FAST_FAIL_SECONDS = 20.0

# 等待录制槽位的轮询间隔：1 秒内可感知「停止录制」，又不至于让 80+ 房间每秒集体唤醒。
_SEM_WAIT_TICK = 1.0

# ffmpeg 的 stderr 改写到临时文件而不是继承父 stdout：一次录制可达 6 小时，继承时报错只落在控制台
# （Web/GUI 模式下等于消失），失败归因只能靠退出码；stdin 从 PIPE 改 DEVNULL 则修「管道从未写入也
# 从未关闭、整个录制周期滞留句柄」。必须在**守护循环结束后**（进程已退出）读尾部：边跑边读会让
# 临时文件无界增长。
_FFMPEG_STDERR_KEEP_BYTES = 4096
_FFMPEG_STDERR_KEEP_LINES = 20

# 录制看门狗的两个阈值。FLV 输入保留 -reconnect*，CDN 掐断长连接时 ffmpeg 会按 1/3/…/60s
# 指数退避无限重连、永不退出；而它一直持有录制槽位（acquire 在 Popen 之前），槽位耗尽后
# 所有房间饿死且无法自愈。
# ① 单次录制时长上限：可配置，默认 6 小时、0 为不限制——24 小时轮播/官方电台房间超过 6 小时
#    是常态。分段开/关均生效；命中上限按「正常录完」收尾（成功样本 + 转码 + 撤销退避）。
# ② 停滞窗口：输出文件连续 10 分钟无增长即判停滞。基准是「最后一次观测到增长的时刻」
#    （见 check_subprocess::_stall_since），不是起跑时刻。
_MAX_RECORD_SECONDS = 6 * 60 * 60  # 「单次录制时长上限(秒)」的配置默认值
_RECORD_STALL_SECONDS = 10 * 60
# 停滞检测的文件大小采样间隔（秒）：每次采样都要 stat 一次，无需每轮都做。
_RECORD_STALL_PROBE_INTERVAL = 30.0
# 看门狗「单轮可信推进量」上界：守护循环每轮 sleep(1)，正常增量是 1s 量级；
# 300s 为 GIL 竞争、满载 IO 与慢盘 stat 留余量。超过上界或倒退只可能是 NTP 校时/改表/挂起恢复，
# 一律按名义 1s 计（见 check_subprocess::_watch_seconds）。
_WATCH_TICK_MAX_SECONDS = 300.0
_WATCH_TICK_NOMINAL_SECONDS = 1.0

# 录制产物有效的最小字节数：播放列表 200 但分片全 404 时，ffmpeg 零输出、零字节、rc=0；
# 只看退出码会把空文件当成功并撤销线路退避，形成无法自愈的零字节闭环。
_MIN_VALID_RECORD_BYTES = 1024

# 录后转码专用线程池：原实现每个分段起一条线程，开启转 H.264 时每条跑一路 libx264，
# 80+ 房间 + 短分段会堆出数十条 CPU 密集进程，与录制争抢 CPU/磁盘并诱发丢帧。
# 改为固定容量池：队列无上限、并发受控，产物只会延后转码。
_POSTPROCESS_WORKERS = max(2, min(4, (os.cpu_count() or 4) // 2))
_postprocess_executor: ThreadPoolExecutor | None = None
_postprocess_executor_lock = threading.Lock()


def _get_postprocess_executor() -> ThreadPoolExecutor:
    # 惰性创建（模块导入期不建线程），线程名前缀便于在日志/进程列表里区分
    global _postprocess_executor
    with _postprocess_executor_lock:
        if _postprocess_executor is None:
            _postprocess_executor = ThreadPoolExecutor(
                max_workers=_POSTPROCESS_WORKERS, thread_name_prefix="postprocess"
            )
        return _postprocess_executor


# 提交一个录后转码任务（含删除源文件开关）；线程池满时任务排队而非无限新建线程
def _submit_postprocess(func: Callable[..., Any], path: str, delete_origin: bool, record_name: str = "") -> None:
    try:
        _ = _get_postprocess_executor().submit(func, path, delete_origin)
    except RuntimeError as e:
        # 解释器关闭中（池已 shutdown）等场景：退化为同步执行会阻塞录制线程，只记日志
        logger.warning(
            i18n.tr(
                "[{record_name}] 转码任务提交失败（{type_name}）: {e}",
                record_name=record_name or os.path.basename(path),
                type_name=type(e).__name__,
                e=e,
            )
        )


# ffmpeg 退出码的 errno 语义提示：Windows 上拿到的是无符号 32 位值（-22 → 4294967274），
# 直接打印无法定位方向。只收录实测出现过或语义明确的取值，未知值返回空串。
# -22 同时覆盖「容器/编码错配」与「输入选项解析失败」两类成因（如 -reconnect* 缺值）。
_FFMPEG_ERRNO_HINTS: dict[int, str] = {
    -22: " (EINVAL：无效参数，常见于容器/编码不匹配（如 HEVC 写进 ipod 容器）或输入选项解析失败)",
    -11: " (EAGAIN：输出写入被阻塞，多为磁盘 IO 或管道背压)",
    -2: " (ENOENT：输入地址或输出路径不存在)",
    -109: " (EBADF：连接被对端重置，多为 CDN 断流)",
    1: " (ffmpeg 常规错误，详见上方 ffmpeg 输出)",
    2: " (命令行参数错误)",
    255: " (ffmpeg 初始化失败/被中断)",
}


# 退出码归一化为有符号 errno：仅超出 32 位有符号正区间时做补码换算，正常小退出码原样返回。
def _describe_return_code(return_code: int) -> str:
    signed_rc = return_code - (1 << 32) if return_code > 0x7FFFFFFF else return_code
    return f"{signed_rc}{_FFMPEG_ERRNO_HINTS.get(signed_rc, '')}"


# 输出侧本地失败只有一条判据：输出父目录当前不存在（判定点见 check_subprocess 失败分支）。
# 读 ffmpeg 输出按写侧特征归因不可行：Popen 只设 stdin=PIPE + stderr=STDOUT，
# proc.stdout 恒为 None；补 PIPE 又需在守护循环持续消费，否则管道写满会卡死 ffmpeg。


# 分段序号后缀形状 `_<数字>.<扩展名>`（位于字符串末尾）。不用定长 `???` glob：
# ffmpeg 的 %03d 在段号超过 999 时输出 4 位，定长模式会静默漏计。
_SEG_INDEX_RE = re.compile(r"_\d+\.[A-Za-z0-9]+$")

# 分段输出模板形状 `..._%03d.ts` / `..._%02d.m4a`。「是否分段」一律由已冻结的命令输出模板
# 推导，不读模块全局 split_video_by_time——主循环每 3s 热加载，录制中途切换开关会让收尾校验
# 按错误形状枚举（零字节保护静默失效）或提交注定失败的转码，并破坏 _000.srt ↔ _000.ts 的对应。
# 只匹配扩展名前的序号占位符，避免把标题里恰好含 %d 的文件名误判。
_SEGMENT_TEMPLATE_RE = re.compile(r"_%0?\dd\.[A-Za-z0-9]+$")


# 输出路径是否为 ffmpeg 分段模板（决定产物求和方式、弹幕分片与录后转码的匹配形状）
def _is_segmented_output(save_file_path: str) -> bool:
    return _SEGMENT_TEMPLATE_RE.search(save_file_path) is not None


# 分段模板 → 实际落盘的分段文件：纯字符串前缀/后缀 + 序号正则，**绝不用 glob/fnmatch**。
# 主播名里的 `[` `]` 是合法文件名字符，但 Path.glob 会把 `主播[A组]_*` 译成字符类而恒返回空，
# 导致分段求和恒 -1（健康录制满 10 分钟被判停滞）与「未找到分段文件」。三处枚举统一走本函数。
# 三态返回，None 与 [] 不得合并：
#   None = 目录不可读（不存在 / 权限 / 网络盘抖动 / 被转码临时替换）→ 观测失败，对产物一无所知；
#   []   = 目录可读但无匹配分段 → 真实的零增长观测。
# 观测失败时不得刷新停滞基准、不得判停滞（见 _watchdog_hit 与
# tests/test_regression_main.py::test_segment_observation_failure_is_not_stall）。
def _segment_files(save_file_path: str) -> list[str] | None:
    directory = os.path.dirname(save_file_path)
    template = os.path.basename(save_file_path)
    base_stem = template.rsplit("_", maxsplit=1)[0]
    prefix = base_stem + "_"
    suffix = "." + template.rsplit(".", maxsplit=1)[-1]
    matched: list[str] = []
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                name = entry.name
                # 序号正则同时排除 `_000_extra.ts` 这类非序号后缀（与 ffmpeg 的 _000/_001… 对齐）
                if name.startswith(prefix) and name.endswith(suffix) and _SEG_INDEX_RE.search(name):
                    matched.append(entry.path)
    except OSError:
        return None
    return matched


# 统计本次录制实际落盘字节数：分段模板含 %03d，直接 stat 恒失败，须按 _000/_001… 求和；
# 单文件录制直接取大小。
# 三态：>=0 实际字节数；-1 路径/分段确实不存在；None 观测失败（目录不可读）。
# 调用方必须分开处理 None 与 -1——前者不得据此判停滞。
# 扩展名由模板推导、枚举走 _segment_files，不写死 .ts：否则分段 FLV/MKV/MP4/音频恒返回 -1，
# 「零字节记成功、撤销退避」的闭环会在非 TS 形态复发（分段 FLV 是虎牙/斗鱼常见形态）。
def _record_output_bytes(save_file_path: str, split_video_by_time: bool) -> int | None:
    if not split_video_by_time:
        try:
            return os.path.getsize(save_file_path)
        except OSError:
            # 非分段形态没有「目录可读但无产物」的中间态：文件不存在即「本轮还没写出产物」，
            # 这正是要判停滞的真实零产物信号，故保持 -1 而不是 None。
            return -1
    seg_paths = _segment_files(save_file_path)
    if seg_paths is None:
        return None
    total = 0
    found = False
    for seg_path in seg_paths:
        found = True
        try:
            total += os.path.getsize(seg_path)
        except OSError:
            continue
    return total if found else -1


# 读 ffmpeg 错误输出的尾部若干行（进程退出后调用），并删除临时文件。
# 只读文件末尾 _FFMPEG_STDERR_KEEP_BYTES 字节再按行截取：6 小时录制可能写出几十 MB stderr，
# 整份读进来既慢又占内存。任何失败一律返回空串——归因信息不值得让收尾链路抛错。
def _read_ffmpeg_stderr_tail(path: str) -> str:
    try:
        with open(path, "rb") as handle:
            _ = handle.seek(0, os.SEEK_END)
            size = handle.tell()
            _ = handle.seek(max(0, size - _FFMPEG_STDERR_KEEP_BYTES))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        tail = ""
    try:
        os.remove(path)
    except OSError:
        pass
    lines = [line for line in tail.splitlines() if line.strip()]
    return "\n".join(lines[-_FFMPEG_STDERR_KEEP_LINES:])


# 成功轮、看门狗早退、被注释/停止早退三条路径也要删 stderr 临时文件：正常删除只挂在「rc != 0」
# 分支上，而 ffmpeg 把进度写 stderr，一轮 6h 可留数 MB，长跑下 tempfile.gettempdir() 里的
# dlr_ffmpeg_*.log 会逐轮累积。这些路径只删不读，与 rc != 0 分支读完再删不冲突（重复删由 OSError 吞掉）。
def _discard_ffmpeg_stderr(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


# 启动并守护一次 ffmpeg 录制：ffmpeg_command 末位为输出路径；save_type 决定转码与弹幕/字幕；
# platform + danmaku_args 用于同步启停弹幕采集。
# 返回 True = 因地址被注释 / 收到退出标志 / 停止录制而提前中断（调用方应结束线程）；
# False = 本次录制自然结束。
def check_subprocess(
    record_name: str,
    record_url: str,
    ffmpeg_command: list[str],
    save_type: str,
    script_command: str | None = None,
    platform: str | None = None,
    danmaku_args: Any = None,
) -> bool:
    # 录制并发软上限：limit=0 时信号量容量极高，acquire 不阻塞（等同不限制）。
    # 必须在 Popen 之前占槽——先起进程再 acquire 约束不到 ffmpeg 进程数，被阻塞的只是房间线程。
    # acquire 带超时轮询：排队期间每 _SEM_WAIT_TICK 秒检查退出条件，命中即放弃本轮并返回 True，
    # 避免「点了停止，几十秒后仍有房间在起 ffmpeg」。
    _rec_sem = recording_semaphore
    while not _rec_sem.acquire(timeout=_SEM_WAIT_TICK):
        if record_url in url_comments or exit_recording or not recording_enabled:
            logger.debug(
                i18n.tr(
                    "[{record_name}]等待录制槽位期间检测到停止信号，放弃本轮录制",
                    record_name=record_name,
                )
            )
            # 放弃本轮前必须回收录制状态：登记早已在 start_record 完成，直接 return 会留下幽灵条目
            # （面板恒显录制中、磁盘满判定恒假、调用方对从未创建的输出路径提交转码）。
            # 与下方「被注释/停止」分支同构。
            clear_record_info(record_name, record_url)
            return True
    # process 提前置 None：finally 才能区分「Popen 前就抛错」与「进程已起、守护段抛错」，
    # 后者会留下无人守护的孤儿 ffmpeg。
    process: subprocess.Popen[bytes] | None = None
    # 弹幕采集器声明在 try 之前，finally 才能安全引用；finally 内无条件 stop()（stop 自带幂等）。
    # unregister / clear_record_info 与 terminate 解耦，进程自然退出时同样执行。
    # 判据：tests/test_regression_main.py
    #   :test_danmaku_collector_stopped_when_guard_section_raises
    #   :test_finally_clears_state_when_process_already_exited
    danmaku_collector: Any = None
    _converged = False
    # ffmpeg 的错误输出落临时文件（理由见 _FFMPEG_STDERR_KEEP_BYTES 上方注释）。
    # 声明在 try 之前，收尾段才能读到；文件名带 uuid 避免同目录多房间并发时互相覆盖。
    _ffmpeg_stderr_path = os.path.join(tempfile.gettempdir(), f"dlr_ffmpeg_{uuid.uuid4().hex[:12]}.log")
    _ffmpeg_stderr_file: Any = None
    try:
        save_file_path = ffmpeg_command[-1]
        # 产物形状判定一律取自已冻结的命令输出模板，不读模块全局
        _split_output = _is_segmented_output(save_file_path)
        # 「快速失败」是时长判定，必须走单调钟：NTP 校时 / 改表 / 挂起恢复会让 time.time() 差值
        # 任意跳动——向前跳会逃过快速失败（坏线路不入探针退避），向后跳会把长录制判成秒退。
        # 展示用 stop_time 仍走挂钟。看门狗的时长判据见 _watch_seconds（同类问题、不同解法）。
        # 回归锁：tests/test_regression_main.py::test_fast_fail_judgement_ignores_wall_clock_jump
        _proc_started_mono = time.monotonic()
        # stderr 重定向失败（临时目录不可写）不得阻断录制：回退到原来的「继承父 stdout」形态，
        # 只是失去事后归因能力。
        try:
            _ffmpeg_stderr_file = open(_ffmpeg_stderr_path, "wb")
        except OSError:
            _ffmpeg_stderr_file = None
        # stdin=PIPE：Windows 停止录制时 ffmpeg_proc 靠「写 q」走优雅退出（不写 q 只能硬杀，
        # 正在写的 mp4/mkv/m4a 分段会缺 moov/索引、产物不可播）；接 DEVNULL 则 Popen.stdin
        # 为 None，优雅分支整条不可达。句柄由 unregister_ffmpeg_process 在收尾时 close，
        # 不留整个录制周期。stderr 写临时文件（否则继承父 stdout，Web/GUI 模式下 ffmpeg 的报错直接消失）。
        try:
            process = subprocess.Popen(
                ffmpeg_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=_ffmpeg_stderr_file if _ffmpeg_stderr_file is not None else subprocess.STDOUT,
                startupinfo=get_startup_info(os_type),
            )
        except BaseException:
            # Popen 抛错（ffmpeg 二进制缺失等）时，stderr 临时文件已建但成功路径
            # 的 close 与后续 finally 的 discard 均不会执行——%TEMP% 每次失败残留一个 0 字节
            # dlr_ffmpeg_*.log，句柄靠引用计数兜底、磁盘文件不清理。就地收尾后原样再抛。
            if _ffmpeg_stderr_file is not None:
                _ffmpeg_stderr_file.close()
                _ffmpeg_stderr_file = None
                _discard_ffmpeg_stderr(_ffmpeg_stderr_path)
            raise
        # 子进程已继承写句柄，父进程这只立即关掉：否则录制期间多占一个句柄，且 Windows 上
        # 未关闭的句柄不影响读取但会让清理 tmp 时出现占用。
        if _ffmpeg_stderr_file is not None:
            _ffmpeg_stderr_file.close()
            _ffmpeg_stderr_file = None

        register_ffmpeg_process(process)

        subs_file_path = save_file_path.rsplit(".", maxsplit=1)[0]

        # SRT 前缀须与真实文件名对齐：剥离 _%03d / _%02d 占位符（未命中即空操作），
        # 分片号由 SrtWriter 自行追加 _000。
        for _seg_placeholder in ("_%02d", "_%03d"):
            subs_file_path = subs_file_path.replace(_seg_placeholder, "")

        # 弹幕与 ffmpeg 同起同停，SRT 前缀与录像一致。录制弹幕/弹幕监控共用同一采集器：
        # 任一开启即连接，仅监控时不落 SRT；启动失败不影响录像。
        _danmaku_active = enable_danmaku or enable_danmaku_monitor
        if _danmaku_active and platform is not None and platform in danmaku_platforms and "音频" not in save_type:
            if not danmaku_args:
                logger.debug(
                    i18n.tr(
                        "[{record_name}]弹幕跳过: 平台={platform} 未获取到弹幕参数(danmaku_args 为空),请查看上游日志",
                        record_name=record_name,
                        platform=platform,
                    )
                )
            else:
                try:
                    danmaku_collector = get_danmaku_collector(
                        platform=platform,
                        danmaku_args=danmaku_args,
                        base_filename=subs_file_path,
                        segment_seconds=danmaku_split_time if _split_output else None,
                        room_name=record_name,
                        write_srt=enable_danmaku,
                    )
                    if danmaku_collector is not None:
                        danmaku_collector.start()
                except Exception as e:
                    logger.warning(
                        i18n.tr(
                            "[{record_name}]弹幕采集启动失败,不影响录制: {type_name}: {e}",
                            record_name=record_name,
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
                    # start() 非原子（句柄/线程/hub 注册分步进行），中途抛错会留下半启动对象；
                    # 先幂等 stop 再丢引用，否则线程与句柄无人可停。
                    # 日志带 type_name：asyncio.TimeoutError 的 str() 为 "()"、socket.timeout 为空串。
                    if danmaku_collector is not None:
                        danmaku_collector.stop()
                    danmaku_collector = None

        subs_thread_name = f"subs_{Path(subs_file_path).name}"
        if create_time_file and not _split_output and "音频" not in save_type:
            # 字幕线程与录制同生命周期（generate_subtitles 直到 record_name 移出 recording 才返回），
            # 线程本身由 daemon 兜底；但 create_var 的条目会长期累积，故在 finally 里 pop。
            def _subtitle_thread_target() -> None:
                try:
                    generate_subtitles(record_name, subs_file_path)
                finally:
                    with record_state_lock:
                        # 键由输出文件名推导，跨房间/跨轮可能重名：只有登记的仍是本线程时才回收
                        if create_var.get(subs_thread_name) is threading.current_thread():
                            create_var.pop(subs_thread_name, None)

            # 登记与 start() 一并收进 lock：回收侧本来就在锁内，写入侧在锁外会让「写 → start」
            # 与别的线程的 finally pop 交错，启动一个已不归属自己的线程且条目永久残留。
            # start() 只做线程创建、不等待 target，持锁时间是常数级。
            with record_state_lock:
                create_var[subs_thread_name] = threading.Thread(
                    target=_subtitle_thread_target, name=subs_thread_name, daemon=True
                )
                # start() 抛 RuntimeError 时 target 不运行、finally 清理不执行，失败即回滚登记。
                try:
                    create_var[subs_thread_name].start()
                except RuntimeError:
                    create_var.pop(subs_thread_name, None)
                    raise

        # 转调模块级 _terminate_ffmpeg_process，避免终止逻辑在此重复实现而漂移
        def terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
            return _terminate_ffmpeg_process(proc, timeout)

        # 看门狗状态：_stall_last_size = -1 表示「目录可读但确实还没有任何产物」（目录不可读返回
        # None，不会落到 -1）。停滞基准 _stall_since 取「最后一次观测到增长的时刻」、初始为起跑时刻：
        # 按起跑时刻直接判 `now - start > 窗口` 会变成「满 10 分钟后任意一次无增长采样就杀」，而 FLV
        # 的 -reconnect_delay_max 60（退避期间零写入）、主播暂停推流、CDN 短抖都是合法无增长窗口。
        # 误杀代价：record_error(host) 把健康线路计入熔断样本，且不走 rc==0 分支 → 转码与
        # clear_ffmpeg_reject 双双跳过。
        # 时长判定不吃挂钟，也不换裸 time.monotonic()：tests/test_record_watchdog.py::_Clock 只替换
        # time/sleep，换单调钟会让其受控时钟用例忙等挂死。故按挂钟增量累加（见 _watch_seconds），
        # 只累计合理范围内的增量，越界/倒退按名义 sleep 计，漏算只会推迟判定（宁慢勿误杀）。
        # 回归锁：tests/test_regression_main.py::test_watchdog_elapsed_ignores_wall_clock_jump
        _watch_prev_wall = time.time()
        _watch_elapsed = 0.0

        def _watch_seconds() -> float:
            # 看门狗专用的「可信已跑秒数」：从 0 起算，只随真实推进的挂钟增量增长
            nonlocal _watch_prev_wall, _watch_elapsed
            raw = time.time()
            delta = raw - _watch_prev_wall
            _watch_prev_wall = raw
            if 0.0 <= delta <= _WATCH_TICK_MAX_SECONDS:
                _watch_elapsed += delta
            else:
                # 倒退（改小系统时间）或荒谬跳变：按本轮名义 sleep 时长计，跳变量绝不进判定
                _watch_elapsed += _WATCH_TICK_NOMINAL_SECONDS
            return _watch_elapsed

        _proc_started_watch = _watch_seconds()
        _stall_last_probe = _proc_started_watch
        _stall_last_size = -1
        _stall_since = _proc_started_watch

        # 单次录制时长上限取热加载值：0/负值不限制，分段开/关均生效。命中上限走 _watchdog_hit
        # 的 "limit" 出口，与 rc==0 共用正常收尾链路（成功样本 + 转码 + 撤销探针退避）。
        # 非分段形态也必须参与：否则「产物从未出现」的房间会永久持有录制槽位。
        _record_limit_seconds = max_record_seconds

        def _watchdog_hit() -> str:
            # 返回 "" 表示一切正常；"stall"＝输出停滞（按失败终止）；
            # "limit"＝达到单次录制时长上限（正常收尾，与 rc==0 共用成功路径）
            nonlocal _stall_last_probe, _stall_last_size, _stall_since
            # 时刻量统一取「可信已跑秒数」（理由见上方 _watch_seconds 段）
            now = _watch_seconds()
            if _record_limit_seconds > 0 and now - _proc_started_watch > _record_limit_seconds:
                # 分段关时下一轮产出的是另一个独立文件，措辞按 _split_output 二选一
                if _split_output:
                    logger.warning(
                        i18n.tr(
                            "[{record_name}] 达到单次录制时长上限（{limit}），结束本轮并分段续录",
                            record_name=record_name,
                            limit=f"{_record_limit_seconds}s",
                        )
                    )
                else:
                    logger.warning(
                        i18n.tr(
                            "[{record_name}] 达到单次录制时长上限（{limit}），结束本轮并在下轮新开一个文件",
                            record_name=record_name,
                            limit=f"{_record_limit_seconds}s",
                        )
                    )
                return "limit"
            if now - _stall_last_probe < _RECORD_STALL_PROBE_INTERVAL:
                return ""
            _stall_last_probe = now
            # 采样走 _record_output_bytes，不裸 stat 模板：后者对分段恒失败，会把「从未创建输出」
            # 与「分段模板」混为同一个 OSError 而永不判停滞，房间无限持有槽位。
            # size < 0（尚无任何产物）时，自最后一次增长（初始为起跑时刻）越过窗口即判停滞。
            size = _record_output_bytes(save_file_path, _split_output)
            if size is None:
                # None = 目录不可读，属观测失败而非「产物不存在」：既不能刷新停滞基准，
                # 也不能判停滞——一次偶发 scandir 失败就会杀掉健康录制并投假失败样本。
                return ""
            if size < 0:
                if now - _stall_since > _RECORD_STALL_SECONDS:
                    logger.warning(
                        i18n.tr(
                            "[{record_name}] 输出文件连续 {minutes} 分钟无增长，判定为停滞并终止",
                            record_name=record_name,
                            minutes=int(_RECORD_STALL_SECONDS // 60),
                        )
                    )
                    return "stall"
                return ""
            if size > _stall_last_size:
                _stall_last_size = size
                _stall_since = now
                return ""
            if _stall_last_size >= 0 and now - _stall_since > _RECORD_STALL_SECONDS:
                logger.warning(
                    i18n.tr(
                        "[{record_name}] 输出文件连续 {minutes} 分钟无增长，判定为停滞并终止",
                        record_name=record_name,
                        minutes=int(_RECORD_STALL_SECONDS // 60),
                    )
                )
                return "stall"
            return ""

        # 「达到时长上限」标志：True 时按「正常录完」收尾，不往熔断窗口塞失败样本
        _reached_record_limit = False

        while process.poll() is None:
            # 守护循环每 1s 轮询一次，看门狗与「注释/停止」检查同轮进行
            _watchdog = _watchdog_hit()
            if _watchdog == "stall":
                # 本分支自带终止与注销，标记已收敛以免 finally 二次处理
                _converged = True
                if danmaku_collector is not None:
                    danmaku_collector.stop()
                _ = terminate_ffmpeg_process(process)
                unregister_ffmpeg_process(process)
                clear_record_info(record_name, record_url)
                # 按失败处理：让调度器计入失败样本并维持该线路的退避，
                # 而不是像正常结束那样撤销退避（否则坏线路会被反复选中）
                record_error(host_of(record_url))
                _discard_ffmpeg_stderr(_ffmpeg_stderr_path)
                return False
            if _watchdog == "limit":
                # 结束守护循环但不返回：终止 ffmpeg 后落到与 rc==0 相同的收尾链路。
                # 弹幕采集器交给循环外那一次 stop()，整个周期只停一次。
                _converged = True
                _ = terminate_ffmpeg_process(process)
                unregister_ffmpeg_process(process)
                _reached_record_limit = True
                break
            if record_url in url_comments or exit_recording or not recording_enabled:
                # 同上：f-string 直传 print_colored 是提取盲区，改 tr 预格式化
                color_obj.print_colored(
                    i18n.tr("[{record_name}]录制时已被注释或停止录制,本条线程将会退出", record_name=record_name),
                    color_obj.YELLOW,
                )
                # 本分支自行 clear_record_info + terminate + unregister，标记已收敛以免 finally 二次处理
                _converged = True
                clear_record_info(record_name, record_url)

                # 提前停止：先停弹幕采集器，确保最后一批写入被 flush（再终止 ffmpeg）
                if danmaku_collector is not None:
                    danmaku_collector.stop()

                success = terminate_ffmpeg_process(process)
                if not success:
                    logger.warning(
                        i18n.tr("[{record_name}] ffmpeg 进程可能没有完全终止，请检查系统进程", record_name=record_name)
                    )

                unregister_ffmpeg_process(process)
                _discard_ffmpeg_stderr(_ffmpeg_stderr_path)
                return True
            time.sleep(1)
    finally:
        # 无论正常结束、提前中断还是异常，都必须归还录制槽位；泄漏累积到上限会让所有后续录制饿死。
        _rec_sem.release()
        # 无条件停采集器；stop() 自带 _stop_called 幂等，与各早退分支重复调用安全。
        if danmaku_collector is not None:
            danmaku_collector.stop()
        # Popen 之后仍有未包装的抛错点（弹幕/字幕线程 start() 的 RuntimeError 在 80+ 房间时可达）。
        # 异常路径必须与早退路径同样收敛：终止 + 注销 + 清录制状态；否则孤儿 ffmpeg 不进守护循环，
        # 用户点停止/注释都杀不到它，注册表只增不清、recording 留下幽灵条目。
        # 存活判定只留给 _terminate_ffmpeg_process；unregister / clear_record_info 在
        # `not _converged` 时无条件执行，_converged 防止已自行收尾的分支被二次 terminate。
        if process is not None and not _converged:
            if process.poll() is None:
                _ = _terminate_ffmpeg_process(process)
            unregister_ffmpeg_process(process)
            clear_record_info(record_name, record_url)

    # 显式收窄供静态检查（Popen 抛错时异常已向上传播，不会落到本行之后）。
    # 类型必须写成字符串：测试把 main.subprocess 换成 SimpleNamespace 替身，裸下标会抛 TypeError。
    proc = cast("subprocess.Popen[bytes]", process)

    # 采集器已由上面的 finally 单点停止，此处不再重复调用。

    # 回收子进程资源，避免僵尸进程/句柄滞留（Web 常驻模式下尤其重要）
    try:
        _ = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        # 超时说明 ffmpeg 未被回收：补杀并告警。静默吞掉会让后续 None 的 returncode 判成败，
        # 把「回收失败」当成「录制失败」并据此写探针退避。
        logger.warning(i18n.tr("[{record_name}] ffmpeg 进程 30 秒内未退出，强制终止", record_name=record_name))
        try:
            proc.kill()
            _ = proc.wait(timeout=10)
        except Exception as e:
            logger.warning(
                i18n.tr(
                    "[{record_name}] 强制终止 ffmpeg 失败: {type_name}: {e}",
                    record_name=record_name,
                    type_name=type(e).__name__,
                    e=e,
                )
            )
    return_code = proc.returncode
    if return_code is None:
        # kill 后仍无退出码时用 -1 作「未知失败」哨兵，避免 _describe_return_code(None) 抛 TypeError
        logger.warning(i18n.tr("[{record_name}] 无法获取 ffmpeg 退出码，按失败处理", record_name=record_name))
        return_code = -1
    stop_time = time.strftime("%Y-%m-%d %H:%M:%S")
    if return_code == 0 or _reached_record_limit:
        # rc==0 不等于录到了东西（见 _MIN_VALID_RECORD_BYTES）：产物过小按失败处理，保留退避。
        # 达到时长上限的一轮也走这里，按正常收尾（转码 + 成功样本 + 撤销退避）。
        _produced_bytes = _record_output_bytes(save_file_path, _split_output)
        if _produced_bytes is None:
            # None = 分段目录不可读：与「找不到分段」一样按 -1 处理，避免凭空投假失败样本。
            _produced_bytes = -1
        if 0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES:
            logger.warning(
                i18n.tr(
                    "[{record_name}] ffmpeg 退出码为 0 但产物为空（{size} 字节），按失败处理",
                    record_name=record_name,
                    size=_produced_bytes,
                )
            )
            record_error(host_of(record_url))
            # 先收尾后 return：否则进程注册表只增不清、recording 留下幽灵条目。
            # 函数末尾的同样动作对已清空的集合是幂等的。
            with record_state_lock:
                recording.discard(record_name)
                recording_time_list.pop(record_name, None)
            unregister_ffmpeg_process(proc)
            _discard_ffmpeg_stderr(_ffmpeg_stderr_path)
            return False
        if converts_to_mp4 and save_type == "TS":
            if _split_output:
                # 按「前缀 + _<数字序号>.<ext>」精确匹配，不递归扫描目录：否则历史 .srt / 已转好的
                # .mp4 会被误送 ffmpeg，每条都触发超时挂死。序号用 _SEG_INDEX_RE、枚举走 _segment_files
                # （glob 会把方括号当字符类，主播名含 `[` 时恒返回空）。
                # None（目录不可读）按「本轮无可转文件」处理，静默跳过而非丢掉整条成功收尾链路。
                _ts_segments = _segment_files(save_file_path)
                if _ts_segments is None:
                    logger.warning(
                        i18n.tr(
                            "分段目录不可读，跳过转换: {directory}",
                            directory=utils.mask_credentials(os.path.dirname(save_file_path)),
                        )
                    )
                for ts_path in _ts_segments or ():
                    _submit_postprocess(converts_mp4, str(ts_path), delete_origin_file, record_name)
            else:
                _submit_postprocess(converts_mp4, save_file_path, delete_origin_file, record_name)
        print(i18n.tr("\n{record_name} {stop_time} 直播录制完成\n", record_name=record_name, stop_time=stop_time))

        if script_command:
            logger.debug("开始执行脚本命令!")
            if "python" in script_command:
                params = [
                    f'--record_name "{record_name}"',
                    f'--save_file_path "{save_file_path}"',
                    f"--save_type {save_type}",
                    f"--split_video_by_time {_split_output}",
                    f"--converts_to_mp4 {converts_to_mp4}",
                ]
            else:
                params = [
                    f'"{record_name.split(" ", maxsplit=1)[-1]}"',
                    f'"{save_file_path}"',
                    save_type,
                    f"split_video_by_time:{_split_output}",
                    f"converts_to_mp4:{converts_to_mp4}",
                ]
            script_command = script_command.strip() + " " + " ".join(params)
            run_script(script_command)
            logger.debug("脚本命令执行结束!")
        # 流正常结束 = 平台健康：按 host 记成功样本，并撤销该源地址的探针退避（与失败分支配对）
        record_success(host_of(record_url))
        try:
            clear_ffmpeg_reject(ffmpeg_command[ffmpeg_command.index("-i") + 1], platform)
        except ValueError:
            logger.debug(
                i18n.tr("[{record_name}] ffmpeg 命令缺少 -i 输入参数，跳过探针退避清除", record_name=record_name)
            )

    else:
        # 退出码先归一化并附 errno 语义，便于区分容器/参数错配与网络/路径问题。
        # 用 tr 预格式化后整体传给 print_colored：f-string 直传时 i18n 提取器扫不到。
        color_obj.print_colored(
            i18n.tr(
                "\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n",
                record_name=record_name,
                stop_time=stop_time,
                return_code=_describe_return_code(return_code),
            ),
            color_obj.RED,
        )
        # 录制失败反馈调度器：
        # ① 按 host 记失败样本，驱动平台熔断与全局背压；不上报会让多房间同 host 的失败率被稀释，
        #    熔断永不触发（实测虎牙秒级 403 循环时 www.huya.com 熔断器始终 closed）。
        # ② 快速失败（≤20s，输入打开被 CDN 拒绝）时把实际拉流地址记入探针退避，下一轮
        #    select_source_url 跳过该线路。「探针 200 → ffmpeg 403」的假绿只在录制侧可见，
        #    不标记则房间会无限重撞同一条死线路（实测 hs.hls.huya.com）。
        record_error(host_of(record_url))
        # 输出侧本地 IO 失败不得归因成「CDN 快速失败」：输出目录不可用（权限/只读/路径过长/
        # 途中被删）时 ffmpeg 打不开输出即秒退，按快速失败处理会把一条健康流地址记进探针退避，
        # 每轮重复污染按 host 的统计。判据只看「输出父目录当前不存在」——此时 ffmpeg 写不出
        # 任何产物，与拉流被拒互斥；上层已对建目录失败打 error 并跳过本轮。
        _output_side_failure = not os.path.isdir(os.path.dirname(save_file_path) or ".")
        if time.monotonic() - _proc_started_mono <= _FFMPEG_FAST_FAIL_SECONDS and not _output_side_failure:
            try:
                _stream_url = ffmpeg_command[ffmpeg_command.index("-i") + 1]
                mark_ffmpeg_reject(_stream_url, platform)
            except ValueError:
                logger.debug(
                    i18n.tr("[{record_name}] ffmpeg 命令缺少 -i 输入参数，跳过探针退避标记", record_name=record_name)
                )
        # 失败归因补一条 ffmpeg 自己的报错尾部：错误输出落在临时文件里（见 _FFMPEG_STDERR_KEEP_BYTES
        # 上方注释），失败日志才不止有退出码。进程已退出，读尾部不会无界增长。
        _ffmpeg_stderr_tail = _read_ffmpeg_stderr_tail(_ffmpeg_stderr_path)
        if _ffmpeg_stderr_tail:
            logger.warning(
                i18n.tr(
                    "[{record_name}] ffmpeg 错误输出尾部: {tail}",
                    # ffmpeg 报错里会出现拉流地址，必须先脱敏再入轮转日志
                    record_name=record_name,
                    tail=utils.mask_credentials(_ffmpeg_stderr_tail),
                )
            )

    # rc==0 / 达到时长上限的两条出口在此汇合（前者中途的「产物过小」分支已单独清理）；
    # rc!=0 分支里的 _read_ffmpeg_stderr_tail 读后已自删，重复调用只是又一次 OSError，无害。
    _discard_ffmpeg_stderr(_ffmpeg_stderr_path)
    with record_state_lock:
        recording.discard(record_name)
        recording_time_list.pop(record_name, None)
    unregister_ffmpeg_process(proc)
    return False


# 主播名变更后同步文件系统：把 {保存路径}/{platform}/{old_name} 改名为 new_name（目标已存在
# 则逐项合并），并批量改名以 "{old_name}_" 开头的录制文件与以 "_{old_name}" 结尾的标题子目录。
# 返回目录级操作是否成功（目录不存在视为成功）；失败由调用方下轮重试。
def rename_anchor_directory(old_name: str, new_name: str, platform: str) -> bool:
    if not old_name or not new_name or old_name == new_name:
        return True
    try:
        save_root = video_save_path or default_path
        platform_dir = os.path.join(save_root, platform)
        if not os.path.isdir(platform_dir):
            return True
        old_dir = os.path.join(platform_dir, old_name)
        new_dir = os.path.join(platform_dir, new_name)
        if os.path.isdir(old_dir):
            if os.path.isdir(new_dir):
                # 目标目录已存在（主播改回曾用名/用户手动整理）：逐项合并而非整体替换
                _merge_anchor_directory(old_dir, new_dir)
            else:
                os.rename(old_dir, new_dir)
        # 前缀同步覆盖所有子目录结构（作者/日期/标题文件夹组合）：旧目录不存在
        # （从未录制或已被手动整理）时也对平台目录整体扫描，兼容中途开关"以作者区分"的存量文件
        _rename_prefixed_entries(platform_dir, old_name, new_name)
        return True
    except OSError as e:
        logger.warning(
            i18n.tr(
                "重命名主播目录失败（下轮重试）: {old_name} -> {new_name}: {e}",
                old_name=old_name,
                new_name=new_name,
                e=e,
            )
        )
        return False


# 把 old_dir 内全部条目移入 new_dir（同名冲突保留双方并告警）；全部移入且无残留时删除旧目录，
# 残留（冲突文件）只告警不抛异常——不阻塞主播名同步主流程，留给用户手动整理
def _merge_anchor_directory(old_dir: str, new_dir: str) -> None:
    for entry in list(os.scandir(old_dir)):
        dst = os.path.join(new_dir, entry.name)
        if os.path.exists(dst):
            logger.warning(i18n.tr("合并主播目录时发现同名文件（双方保留，请手动整理）: {dst}", dst=dst))
            continue
        try:
            os.rename(entry.path, dst)
        except OSError as e:
            # 单条目移动失败（文件被转码/播放器占用）：告警后继续其余条目，下轮整体重试
            logger.warning(
                i18n.tr(
                    "合并主播目录条目失败（下轮重试）: {path} -> {dst}: {type_name}: {e}",
                    path=entry.path,
                    dst=dst,
                    type_name=type(e).__name__,
                    e=e,
                )
            )
    try:
        if not os.listdir(old_dir):
            os.rmdir(old_dir)
    except OSError as e:
        logger.warning(
            i18n.tr(
                "删除旧主播目录失败（已忽略）: {old_dir}: {type_name}: {e}",
                old_dir=old_dir,
                type_name=type(e).__name__,
                e=e,
            )
        )


# 递归把 base_dir 下以 "{old_name}_" 开头的文件改名为 "{new_name}_" 前缀，
# 并把以 "_{old_name}" 结尾的子目录（时间+标题组合下的 "{标题}_{主播}" 目录）改名；
# 单个条目失败（被后台转码/字幕/播放器占用）仅告警跳过，不影响其余条目与整体结果
def _rename_prefixed_entries(base_dir: str, old_name: str, new_name: str) -> None:
    try:
        entries = list(os.scandir(base_dir))
    except OSError:
        return
    for entry in entries:
        try:
            if entry.is_dir(follow_symlinks=False):
                # 先深入子目录处理其内容，再按需重命名目录自身
                _rename_prefixed_entries(entry.path, old_name, new_name)
                dir_name = entry.name
                if dir_name != new_name and dir_name.endswith(f"_{old_name}"):
                    os.rename(entry.path, os.path.join(base_dir, dir_name[: -len(old_name)] + new_name))
            elif entry.name.startswith(f"{old_name}_"):
                os.rename(entry.path, os.path.join(base_dir, f"{new_name}_{entry.name[len(old_name) + 1 :]}"))
        except OSError as e:
            logger.warning(
                i18n.tr(
                    "主播名变更重命名失败（已跳过，不影响其余文件）: {path}: {type_name}: {e}",
                    path=entry.path,
                    type_name=type(e).__name__,
                    e=e,
                )
            )


# 平台分派：按域名把直播间地址路由到对应平台的爬虫与取流模块。cookie/代理等仍按模块级全局即时读取。
# 返回 (platform, port_info, record_danmaku_args, new_record_url)：
# - record_danmaku_args：平台相关弹幕参数，进房失败为 None，交给 check_subprocess 启停采集；
# - new_record_url：需回写配置的规范地址（Shopee 带 uid 的 URL、小红书短链解出的长链）；
# - 无法识别返回 None，由调用方延迟重试而非结束线程。
# 平台解析上下文替代迁移前 _resolve_platform_stream 的函数局部变量：各平台处理函数需要显式载体读写
# 这四个结果字段。
class _PlatformResolveContext:
    def __init__(self, record_url: str, proxy_address: str | None, record_quality: str) -> None:
        self.record_url = record_url
        self.proxy_address = proxy_address
        self.record_quality = record_quality
        # 默认「未知平台」：与迁移前 if 链未命中任何分支时的初值一致
        self.platform = "未知平台"
        self.port_info: dict[str, Any] = {}
        # 本轮弹幕参数;平台分支填充;进房失败为 None 时跳过弹幕
        self.record_danmaku_args: dict[str, Any] | None = None
        # 解析后需回写配置的规范地址（Shopee 带 uid 的 URL、小红书短链解出的直播长链）
        self.new_record_url = ""
        # 兜底分支命中（无法识别的地址）：调用方据此返回 None 并延迟重试
        self.unrecognized = False


# 平台匹配器工厂：多片段为 or。
def _match_host(*fragments: str) -> Callable[[str], bool]:
    # 只匹配 urlsplit 解析出的 host，不匹配整串子串：否则 https://attacker.com/xhslink.com/x 会在路径里
    # 命中而路由进小红书解析，以带凭据的 headers 请求攻击者 host（SSRF）。
    # 判据是**标签边界**：host 等于片段，或等于「标签 + . + 片段」。前缀/子串判据会让
    # https://evilweibo.com/（含 "weibo.com/"）、https://evil3.cn/（含 "3.cn"）命中，而准入侧
    # `_stream_path_suffix(url) in (".flv", ".m3u8")` 又对任意 host 无条件放行 → 攻击者可控域名被
    # 分派进平台解析器，以带 Cookie 的平台请求头向它发请求。
    # 片段首尾的 "." / "/" 与可能带的 scheme（历史表项与测试用 `https://probe.example/` 形态）一律剥掉：
    # 旧实现在 `scheme://host/` 上做子串比较时这类写法天然成立，不剥会静默失效（扩展点契约被破坏）。
    def _normalize_fragment(frag: str) -> str:
        text = frag.strip().lower()
        if "://" in text:
            text = text.split("://", 1)[1]
        return text.strip("/").strip(".")

    _labels = tuple(_normalize_fragment(frag) for frag in fragments)
    _labels = tuple(label for label in _labels if label)

    def _m(url: str) -> bool:
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        host = (parts.hostname or "").lower()
        if not host:
            return False
        return any(host == label or host.endswith("." + label) for label in _labels)

    return _m


# 取 URL 路径部分的小写扩展名（含点）；无扩展名或畸形地址返回空串。
# 必须只看 path：整串子串匹配会让 ?a=.flv 形态的内网地址命中自定义流分支，
# 被原样送进 ffmpeg 的 -i（SSRF 投递通道）。只看 path 仍兼容带 query/fragment 的合法地址。
def _stream_path_suffix(url: str) -> str:
    try:
        path = urlsplit(url).path
    except ValueError:
        # 含控制字符 / 非法端口等畸形入参：urlsplit 抛 ValueError，按「无扩展名」处理
        return ""
    return os.path.splitext(path)[1].lower()


# 自定义流地址匹配器：按小写**路径扩展名**精确比对（平台/用户手填地址可能是 .M3U8 / .FLV 大写形态）
def _match_stream_suffix(*suffixes: str) -> Callable[[str], bool]:
    lowered = tuple(s.lower() for s in suffixes)

    def _m(url: str) -> bool:
        return _stream_path_suffix(url) in lowered

    return _m


# 从一整行配置里取出 URL，供「本轮被跳过的行」在归并时整行豁免。URL 未必在第一段：行格式是
# 「画质,URL,主播名」或「URL,主播名」，按 [,，] 切段后取第一个含 :// 的段（无协议头时取第一段——
# 准入侧正是这样补 https://）。取不到（空行/纯标点）返回空串。
def _line_contains_url(line: str) -> str:
    parts = re.split("[,，]", line) if line else []
    for part in parts:
        candidate = part.strip()
        if "://" in candidate:
            return candidate
    first = parts[0].strip() if parts else ""
    # 与准入侧 contains_url 同判据：只有带 :// 才算地址，否则任何文字都会被当成 URL
    return first if "://" in first else ""


# -------------------------- 平台处理函数（分发表条目）--------------------------
# 每个函数对应原 elif 链的一个分支：读 ctx 入参、写 ctx 结果字段，不共享隐式局部变量。
# 新增平台在此追加，并在 _PLATFORM_RESOLVERS 登记。


def _resolve_douyin_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "抖音直播"
    # 限速等待必须在占用网络并发槽之前：放在 `with semaphore` 内会让 N 个抖音房间各占一个槽
    # 原地睡眠（单轮 ≥3×N 秒），抵消调度器扩容收益。移出后仍由 douyin_rate_lock 保证
    # 「两次请求起点间隔 ≥ 3s」，并发槽的额外排队只会拉大间隔。
    _douyin_rate_limit()
    with semaphore:
        if "v.douyin.com" not in record_url and "/user/" not in record_url:
            json_data = asyncio.run(
                spider.get_douyin_web_stream_data(url=record_url, proxy_addr=proxy_address, cookies=dy_cookie)
            )
        else:
            json_data = asyncio.run(
                spider.get_douyin_app_stream_data(url=record_url, proxy_addr=proxy_address, cookies=dy_cookie)
            )
        # 抖音弹幕:room_id 取 19 位 id_str(web/app 两种返回均含);user_id 随机12位;cookie 复用录制 cookie
        _douyin_room_id = ""
        if isinstance(json_data, dict):
            _douyin_room_id = str(json_data.get("id_str") or json_data.get("id") or "")
        if _douyin_room_id:
            record_danmaku_args = {
                "room_id": _douyin_room_id,
                "user_id": str(random.randint(10**11, 10**12 - 1)),
                "cookie": dy_cookie or "",
            }
        port_info = asyncio.run(stream.get_douyin_stream_url(json_data, record_quality, proxy_address))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_tiktok_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "TikTok直播"
    with semaphore:
        if global_proxy or proxy_address:
            tiktok_data = asyncio.run(
                spider.get_tiktok_stream_data(url=record_url, proxy_addr=proxy_address, cookies=tiktok_cookie)
            )
            # dict 值类型参数是不变的：回退字面量 {"is_live": False} 会被推断为
            # dict[str, bool]，与形参 dict[str, object] 不兼容，故 cast 收敛
            json_data = tiktok_data if tiktok_data is not None else cast(dict[str, object], {"is_live": False})
            port_info = asyncio.run(stream.get_tiktok_stream_url(json_data, record_quality, proxy_address))
        else:
            logger.error("错误信息: 网络异常，请检查网络是否能正常访问TikTok平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_live_kuaishou_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "快手直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_kuaishou_stream_data(url=record_url, proxy_addr=proxy_address, cookies=ks_cookie)
        )
        port_info = asyncio.run(stream.get_kuaishou_stream_url(json_data, record_quality))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_huya_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "虎牙直播"
    with semaphore:
        if record_quality not in ["OD", "BD", "UHD"]:
            json_data = asyncio.run(
                spider.get_huya_stream_data(url=record_url, proxy_addr=proxy_address, cookies=hy_cookie)
            )
            port_info = asyncio.run(stream.get_huya_stream_url(json_data, record_quality))
            # 虎牙弹幕(web路径):ayyuid=gameLiveInfo.yyid, topSid/subSid=gameStreamInfoList[0].lChannelId/lSubChannelId
            try:
                _huya_data0 = cast(
                    dict[str, object],
                    (cast(list[object], (json_data or {}).get("data") or [{}]))[0],
                )
                _gstream = cast(
                    dict[str, object],
                    (cast(list[object], _huya_data0.get("gameStreamInfoList") or [{}]))[0],
                )
                _glive = cast(dict[str, object], _huya_data0.get("gameLiveInfo") or {})
                _ayyuid = cast(Any, _glive.get("yyid"))
                _topSid = cast(Any, _gstream.get("lChannelId"))
                _subSid = cast(Any, _gstream.get("lSubChannelId"))
                if _ayyuid is not None and _topSid is not None and _subSid is not None:
                    record_danmaku_args = {
                        "ayyuid": int(_ayyuid),
                        "topSid": int(_topSid),
                        "subSid": int(_subSid),
                    }
            except Exception as e:
                # 带 type_name：部分异常 str() 为空串，只写 {e} 无法定位
                logger.warning(i18n.tr("[虎牙直播]弹幕参数提取失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
        else:
            # OD/BD/UHD 走 app 路径(profileRoom):yyid/lChannelId/lSubChannelId 由 spider 返回
            port_info = asyncio.run(
                spider.get_huya_app_stream_url(url=record_url, proxy_addr=proxy_address, cookies=hy_cookie)
            )
            try:
                _ayyuid = cast(Any, (port_info or {}).get("yyid"))
                _topSid = cast(Any, (port_info or {}).get("lChannelId"))
                _subSid = cast(Any, (port_info or {}).get("lSubChannelId"))
                if _ayyuid is not None and _topSid is not None and _subSid is not None:
                    record_danmaku_args = {
                        "ayyuid": int(_ayyuid),
                        "topSid": int(_topSid),
                        "subSid": int(_subSid),
                    }
                else:
                    # 消除静默跳过: 记录缺失字段便于定位 spider 返回结构变化
                    logger.debug(
                        i18n.tr(
                            "[虎牙直播]OD/BD/UHD app路径弹幕参数缺失，跳过弹幕: yyid={_ayyuid}, lChannelId={_topSid}, lSubChannelId={_subSid}",
                            _ayyuid=_ayyuid,
                            _topSid=_topSid,
                            _subSid=_subSid,
                        )
                    )
            except Exception as e:
                # 带 type_name：部分异常 str() 为空串
                logger.warning(
                    i18n.tr(
                        "[虎牙直播]OD/BD/UHD app路径弹幕参数提取失败: {type_name}: {e}",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


# ---------------------- 虎牙移动端分享短链（hy.fan）----------------------
# 数字段即房间号，其余为短码，需跟随 301 解析；两种形态都归一成 www.huya.com/<段> 后
# 委托 _resolve_huya_com，复用桌面链路。不在准入层改写配置行：跳转依赖网络，一次抖动
# 会变成「配置行被注释」，放在解析函数内每轮重试更稳，结果由下方缓存摊薄。

# 短码 → 房间段缓存：映射稳定，进程内缓存避免每轮多发一次 301。
# dict 单键读写受 GIL 保护且同键写入幂等，最坏只是重复解析一次，无需加锁。
_HY_FAN_ROOM_CACHE: dict[str, str] = {}


def _hy_fan_path_segment(record_url: str) -> str:
    # 取 hy.fan 的唯一路径段（房间号或短码）；不合法抛 ValueError，消息直接作为用户可见原因。
    try:
        path = urlsplit(record_url).path
    except ValueError:
        # 含控制字符 / 非法端口等畸形入参：urlsplit 抛 ValueError，按「无法解析」定因
        raise ValueError(i18n.tr("URL 无法解析"))
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        raise ValueError(i18n.tr("路径为空，缺少房间号"))
    if len(segments) > 1:
        raise ValueError(i18n.tr("路径含多级目录，不是标准房间链接"))
    segment = segments[0]
    # isascii 收紧 isalnum：全角数字不是合法房间号，与下游 room_id.isdigit() 同口径，
    # 在入口先挡一层（base62 短码本身即 ASCII）。
    if not (segment.isascii() and segment.isalnum()):
        raise ValueError(i18n.tr("房间号含非法字符"))
    return segment


def _huya_room_segment_from_landing(final_url: str) -> str:
    # 从落地页提取房间段；非虎牙域 / 形态不符返回空串（只判「能否提取」，原因由调用方表述）。
    # 接受字母段：自定义号 www.huya.com/<字母号> 是合法形态，数字房间号由下游 ProfileRoom 反查。
    try:
        parts = urlsplit(final_url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if host != "huya.com" and not host.endswith(".huya.com"):
        return ""
    segments = [seg for seg in parts.path.split("/") if seg]
    if len(segments) != 1:
        return ""
    segment = segments[0]
    if not (segment.isascii() and segment.isalnum()):
        return ""
    return segment


async def _resolve_hy_fan_room_segment(record_url: str, proxy_addr: str | None) -> str:
    # 短码 → 房间段：走 async_req(redirect_url=True)，与 xhslink.com 同一契约——成功回最终 URL
    # （逐跳 SSRF 复检由 async_http 响应钩子承担，本函数只解析、不请求落地页），失败回空串。
    # UA 取与 spider.get_huya_stream_data 同值的桌面 Firefox UA，不动 MOBILE_UA 那组约定。
    final_url = await async_req(
        url=record_url,
        proxy_addr=proxy_addr,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        },
        redirect_url=True,
    )
    # 联合返回类型需按运行时契约收窄：redirect_url=True 时成功回最终 URL、失败回空串。
    if not isinstance(final_url, str) or not final_url:
        raise ValueError(i18n.tr("未获取到跳转地址"))
    segment = _huya_room_segment_from_landing(final_url)
    if not segment:
        raise ValueError(i18n.tr("跳转地址不是虎牙直播间"))
    return segment


def _resolve_hy_fan(ctx: _PlatformResolveContext) -> None:
    # 归一为桌面链接后委托 _resolve_huya_com 回写 ctx 四字段，本函数不重复赋值。
    # 表项在虎牙之后：test_resolver_table_priority_head 钉死前五项顺序，且两片段不重叠。
    # record_host 仍是 hy.fan：按 host 隔离的熔断桶把「短链解析失败」与「取流失败」分开计数。
    try:
        segment = _hy_fan_path_segment(ctx.record_url)
    except ValueError as err:
        logger.error(
            i18n.tr(
                "虎牙移动端链接缺少有效房间号，本轮跳过: {record_url} - {reason}",
                record_url=utils.mask_credentials(ctx.record_url),
                reason=str(err),
            )
        )
        ctx.unrecognized = True
        return
    if segment.isascii() and segment.isdigit():
        # 纯数字段就是房间号：零网络直接归一，覆盖标准 / 尾斜杠 / 带 query / http 四种形态
        room_segment = segment
    else:
        room_segment = _HY_FAN_ROOM_CACHE.get(segment, "")
        if not room_segment:
            try:
                room_segment = asyncio.run(_resolve_hy_fan_room_segment(ctx.record_url, ctx.proxy_address))
            except Exception as err:
                # reason 统一带异常类型：str() 为空的异常类型也要可见
                logger.error(
                    i18n.tr(
                        "虎牙移动端短链解析失败，本轮跳过: {record_url} - {reason}",
                        record_url=utils.mask_credentials(ctx.record_url),
                        reason=f"{type(err).__name__}: {err}",
                    )
                )
                ctx.unrecognized = True
                return
            _HY_FAN_ROOM_CACHE[segment] = room_segment
    ctx.record_url = f"https://www.huya.com/{room_segment}"
    _resolve_huya_com(ctx)


def _resolve_douyu_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "斗鱼直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_douyu_info_data(url=record_url, proxy_addr=proxy_address, cookies=douyu_cookie)
        )
        # 斗鱼弹幕:room_id 必须在 get_douyu_stream_url 内部 pop 之前从 json_data 抓取
        _douyu_rid = str(json_data.get("room_id") or "") if isinstance(json_data, dict) else ""
        if _douyu_rid:
            record_danmaku_args = {"room_id": _douyu_rid}
        port_info = asyncio.run(
            stream.get_douyu_stream_url(
                json_data,
                video_quality=record_quality,
                cookies=douyu_cookie,
                proxy_addr=proxy_address,
            )
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_yy_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "YY直播"
    with semaphore:
        json_data = asyncio.run(spider.get_yy_stream_data(url=record_url, proxy_addr=proxy_address, cookies=yy_cookie))
        port_info = asyncio.run(stream.get_yy_stream_url(json_data))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_live_bilibili_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "B站直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_bilibili_room_info(url=record_url, proxy_addr=proxy_address, cookies=bili_cookie)
        )
        port_info = asyncio.run(
            stream.get_bilibili_stream_url(
                json_data,
                video_quality=record_quality,
                cookies=bili_cookie,
                proxy_addr=proxy_address,
            )
        )
        # B站弹幕:额外调 getDanmuInfo 拿 token/server_host/buvid/uid。
        # 仅开播时获取(本周期即将启动录制);未开播周期不发弹幕请求,
        # 避免等待直播期间每轮 spi/nav/getDanmuInfo 高频探测反复触发 B站风控(200+空 body)。
        if port_info.get("is_live", False):
            try:
                record_danmaku_args = asyncio.run(
                    spider.get_bilibili_danmaku_info(url=record_url, proxy_addr=proxy_address, cookies=bili_cookie)
                )
            except Exception as e:
                logger.warning(i18n.tr("[B站直播]弹幕信息获取失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
                record_danmaku_args = None
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


# ---------------------- B站移动端分享短链（b23.tv）----------------------
# 数字段即房间号，其余为短码，需跟随 302 解析；两种形态都归一成 live.bilibili.com/<房间号>
# 后委托 _resolve_live_bilibili_com，复用桌面链路。不在准入层改写配置行（同 hy.fan）。

# 短码 → 房间号缓存：映射稳定，进程内缓存避免每轮多发一次 302（锁判据同 _HY_FAN_ROOM_CACHE）。
_B23_TV_ROOM_CACHE: dict[str, str] = {}


def _b23_tv_path_segment(record_url: str) -> str:
    # 取 b23.tv 的唯一路径段（房间号或短码）；不合法抛 ValueError，消息直接作为用户可见原因。
    try:
        path = urlsplit(record_url).path
    except ValueError:
        raise ValueError(i18n.tr("URL 无法解析"))
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        raise ValueError(i18n.tr("路径为空，缺少房间号"))
    if len(segments) > 1:
        raise ValueError(i18n.tr("路径含多级目录，不是标准房间链接"))
    segment = segments[0]
    # isascii 收紧 isalnum：全角数字不是合法房间号/短码，与 _hy_fan_path_segment 同口径。
    if not (segment.isascii() and segment.isalnum()):
        raise ValueError(i18n.tr("房间号含非法字符"))
    return segment


def _bilibili_room_id_from_landing(final_url: str) -> str:
    # 从落地页提取房间号；非B站直播域 / 形态不符返回空串（只判「能否提取」）。
    # live.bilibili.com 的房间号只有纯数字形态（短号也是数字），另接受移动端 /h5/<房间号>；
    # 落地 query（share_session_id 等）不参与判定。
    try:
        parts = urlsplit(final_url)
    except ValueError:
        return ""
    host = (parts.hostname or "").lower()
    if host != "live.bilibili.com" and not host.endswith(".live.bilibili.com"):
        return ""
    segments = [seg for seg in parts.path.split("/") if seg]
    if len(segments) == 1:
        room_id = segments[0]
    elif len(segments) == 2 and segments[0] == "h5":
        room_id = segments[1]
    else:
        return ""
    if not (room_id.isascii() and room_id.isdigit()):
        return ""
    return room_id


async def _resolve_b23_tv_room_segment(record_url: str, proxy_addr: str | None) -> str:
    # 短码 → 房间号：走 async_req(redirect_url=True)，与 hy.fan 同一契约（只解析、不请求落地页）。
    # UA 取与 spider.get_bilibili_room_info 同值的桌面 Firefox UA；b23.tv 是纯 302 服务、不校验 UA。
    final_url = await async_req(
        url=record_url,
        proxy_addr=proxy_addr,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        },
        redirect_url=True,
    )
    # 联合返回类型需按运行时契约收窄：redirect_url=True 时成功回最终 URL、失败回空串。
    if not isinstance(final_url, str) or not final_url:
        raise ValueError(i18n.tr("未获取到跳转地址"))
    room_id = _bilibili_room_id_from_landing(final_url)
    if not room_id:
        raise ValueError(i18n.tr("跳转地址不是B站直播间"))
    return room_id


def _resolve_b23_tv(ctx: _PlatformResolveContext) -> None:
    # 归一为桌面链接后委托 _resolve_live_bilibili_com 回写 ctx 四字段，本函数不重复赋值。
    # 表项在B站之后：两片段不重叠，先后不产生遮蔽。record_host 仍是 b23.tv——按 host 隔离的
    # 熔断桶把「短链解析失败」与「取流失败」分开计数。
    try:
        segment = _b23_tv_path_segment(ctx.record_url)
    except ValueError as err:
        logger.error(
            i18n.tr(
                "B站移动端链接缺少有效房间号，本轮跳过: {record_url} - {reason}",
                record_url=utils.mask_credentials(ctx.record_url),
                reason=str(err),
            )
        )
        ctx.unrecognized = True
        return
    if segment.isascii() and segment.isdigit():
        # 纯数字段就是房间号：零网络直接归一（判据同 _resolve_hy_fan）
        room_id = segment
    else:
        room_id = _B23_TV_ROOM_CACHE.get(segment, "")
        if not room_id:
            try:
                room_id = asyncio.run(_resolve_b23_tv_room_segment(ctx.record_url, ctx.proxy_address))
            except Exception as err:
                logger.error(
                    i18n.tr(
                        "B站移动端短链解析失败，本轮跳过: {record_url} - {reason}",
                        record_url=utils.mask_credentials(ctx.record_url),
                        reason=f"{type(err).__name__}: {err}",
                    )
                )
                ctx.unrecognized = True
                return
            _B23_TV_ROOM_CACHE[segment] = room_id
    ctx.record_url = f"https://live.bilibili.com/{room_id}"
    _resolve_live_bilibili_com(ctx)


def _resolve_xhslink_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "小红书直播"
    with semaphore:
        port_info = asyncio.run(spider.get_xhs_stream_url(record_url, proxy_addr=proxy_address, cookies=xhs_cookie))
    # 解析器返回结构化错误（非直播/非官方域/短链重定向失败）时按未识别处理并告警：
    # 否则会被当成正常离线轮空转，只看到「等待直播」，指不到链接本身的问题。
    _error = str(port_info.get("error") or "")
    if _error:
        logger.warning(
            i18n.tr(
                "小红书链接解析失败，本轮按未识别处理: {record_url} - {code}",
                record_url=utils.mask_credentials(record_url),
                code=_error,
            )
        )
        ctx.unrecognized = True
    # 规范地址经 new_record_url 落回 URL_config.ini，后续轮次直接用长链，省掉每轮一次跳转。
    _normalized = str(port_info.get("normalized_url") or "")
    if _normalized and _normalized != record_url:
        new_record_url = _normalized
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_bigo_tv(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "bigo"
    with semaphore:
        port_info = asyncio.run(spider.get_bigo_stream_url(record_url, proxy_addr=proxy_address, cookies=bigo_cookie))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_app_blued_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "blued"
    with semaphore:
        port_info = asyncio.run(spider.get_blued_stream_url(record_url, proxy_addr=proxy_address, cookies=blued_cookie))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_sooplive_co_kr(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "SOOP(原AfreecaTV)"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_sooplive_stream_data(
                    url=record_url,
                    proxy_addr=proxy_address,
                    cookies=sooplive_cookie,
                    username=sooplive_username,
                    password=sooplive_password,
                )
            )
            if json_data and json_data.get("new_cookies"):
                try:
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                        utils.update_config(
                            config_file,
                            "Cookie",
                            "sooplive_cookie",
                            cast(str, json_data["new_cookies"]),
                        )
                except (configparser.Error, OSError) as e:
                    # 回写失败只告警（统一口径见 _resolve_platform_stream）
                    logger.warning(
                        i18n.tr(
                            "凭据回写失败（不影响本轮录制）: {type_name}: {e}",
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问SOOP(原AfreecaTV)平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_cc_163_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "网易CC直播"
    with semaphore:
        # 必须透传 proxy_address：否则用户配了代理时网易 CC 仍走本机直连，取不到内容。
        json_data = asyncio.run(
            spider.get_netease_stream_data(url=record_url, proxy_addr=proxy_address, cookies=netease_cookie)
        )
        port_info = asyncio.run(stream.get_netease_stream_url(json_data, record_quality))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_qiandurebo_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "千度热播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_qiandurebo_stream_data(url=record_url, proxy_addr=proxy_address, cookies=qiandurebo_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_pandalive_co_kr(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "PandaTV"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_pandatv_stream_data(url=record_url, proxy_addr=proxy_address, cookies=pandatv_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_fm_missevan_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "猫耳FM直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_maoerfm_stream_url(url=record_url, proxy_addr=proxy_address, cookies=maoerfm_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_winktv_co_kr(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "WinkTV"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_winktv_stream_data(url=record_url, proxy_addr=proxy_address, cookies=winktv_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问WinkTV直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_flextv_co_kr(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "TTingLive(原Flextv)"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_flextv_stream_data(
                    url=record_url,
                    proxy_addr=proxy_address,
                    cookies=flextv_cookie,
                    username=flextv_username,
                    password=flextv_password,
                )
            )
            if json_data and json_data.get("new_cookies"):
                # 回写失败只告警：冒到外层会把已拿到的流地址整轮丢弃，并计入按 host 的熔断样本。
                # 回归锁：tests/test_regression_main.py
                #   :test_flextv_cookie_writeback_failure_keeps_stream_url
                try:
                    with file_update_lock:
                        utils.update_config(config_file, "Cookie", "flextv_cookie", cast(str, json_data["new_cookies"]))
                except (configparser.Error, OSError) as e:
                    logger.warning(
                        i18n.tr(
                            "凭据回写失败（不影响本轮录制）: {type_name}: {e}",
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )
            if "play_url_list" in json_data:
                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            else:
                port_info = json_data
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TTingLive(原Flextv)直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_look_163_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "Look直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_looklive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=look_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_popkontv_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "PopkonTV"
    with semaphore:
        if global_proxy or proxy_address:
            port_info = asyncio.run(
                spider.get_popkontv_stream_url(
                    url=record_url,
                    proxy_addr=proxy_address,
                    access_token=popkontv_access_token,
                    username=popkontv_username,
                    password=popkontv_password,
                    partner_code=popkontv_partner_code,
                )
            )
            if port_info and port_info.get("new_token"):
                # 回写是缓存优化，失败不得连累本轮已拿到的流地址
                try:
                    with file_update_lock:
                        utils.update_config(
                            file_path=config_file,
                            section="Authorization",
                            key="popkontv_token",
                            new_value=cast(str, port_info["new_token"]),
                        )
                except (configparser.Error, OSError) as e:
                    logger.warning(
                        i18n.tr(
                            "凭据回写失败（不影响本轮录制）: {type_name}: {e}",
                            type_name=type(e).__name__,
                            e=e,
                        )
                    )

        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PopkonTV直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_twitcasting_tv(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "TwitCasting"
    with semaphore:
        json_data = asyncio.run(
            spider.get_twitcasting_stream_url(
                url=record_url,
                proxy_addr=proxy_address,
                cookies=twitcasting_cookie,
                account_type=twitcasting_account_type,
                username=twitcasting_username,
                password=twitcasting_password,
            )
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=False))

        # 回写源必须是 json_data：stream.get_stream_url 取到流时会新建 dict，new_cookies 只存在
        # 于 spider 返回值上；读 port_info 会导致「恰好在播时永不落盘」，反复重跑账密登录。
        # 回归锁：tests/test_regression_main.py::test_twitcasting_persists_cookie_when_live
        if json_data and json_data.get("new_cookies"):
            try:
                with file_update_lock:
                    utils.update_config(
                        file_path=config_file,
                        section="Cookie",
                        key="twitcasting_cookie",
                        new_value=cast(str, json_data["new_cookies"]),
                    )
            except (configparser.Error, OSError) as e:
                # 回写失败不得丢弃本轮已拿到的流地址
                logger.warning(
                    i18n.tr(
                        "凭据回写失败（不影响本轮录制）: {type_name}: {e}",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_live_baidu_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "百度直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_baidu_stream_data(url=record_url, proxy_addr=proxy_address, cookies=baidu_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_weibo_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "微博直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_weibo_stream_data(url=record_url, proxy_addr=proxy_address, cookies=weibo_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, hls_extra_key="m3u8_url"))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_kugou_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "酷狗直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_kugou_stream_url(url=record_url, proxy_addr=proxy_address, cookies=kugou_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_twitch_tv(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "TwitchTV"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_twitchtv_stream_data(url=record_url, proxy_addr=proxy_address, cookies=twitch_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            # Twitch 弹幕:channel 名从 URL 末段提取(去 query/锚点),小写
            try:
                _twitch_channel = record_url.split("?")[0].rstrip("/").split("/")[-1].lower()
                if _twitch_channel:
                    _danmaku_extra = {}
                    if proxy_address:
                        # Twitch 需海外网络,弹幕走与录制一致的代理
                        _danmaku_extra["proxy"] = proxy_address
                    record_danmaku_args = {"channel": _twitch_channel, **_danmaku_extra}
            except Exception as e:
                logger.warning(
                    i18n.tr(
                        "[TwitchTV]弹幕 channel 提取失败: {type_name}: {e}",
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TwitchTV直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_liveme_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    # 「未知平台」初值不是死赋值：下方「LiveMe」覆盖在 `if global_proxy or proxy_address:` 之内，
    # 无代理路径（else 分支）会原样读到本值并回写 ctx.platform（死赋值清理已排除本函数）。
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    if global_proxy or proxy_address:
        platform = "LiveMe"
        with semaphore:
            port_info = asyncio.run(
                spider.get_liveme_stream_url(url=record_url, proxy_addr=proxy_address, cookies=liveme_cookie)
            )
    else:
        logger.error("错误信息: 网络异常，请检查本网络是否能正常访问LiveMe直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_huajiao_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "花椒直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_huajiao_stream_url(url=record_url, proxy_addr=proxy_address, cookies=huajiao_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_n7u66_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "流星直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_liuxing_stream_url(url=record_url, proxy_addr=proxy_address, cookies=liuxing_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_showroom_live_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "ShowRoom"
    with semaphore:
        json_data = asyncio.run(
            spider.get_showroom_stream_data(url=record_url, proxy_addr=proxy_address, cookies=showroom_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_live_acfun_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "Acfun"
    with semaphore:
        json_data = asyncio.run(
            spider.get_acfun_stream_data(url=record_url, proxy_addr=proxy_address, cookies=acfun_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, url_type="flv", flv_extra_key="url"))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_live_tlclw_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "畅聊直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_changliao_stream_url(url=record_url, proxy_addr=proxy_address, cookies=changliao_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_ybw1666_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "音播直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_yinbo_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yinbo_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_inke_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "映客直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_yingke_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yingke_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_zhihu_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "知乎直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_zhihu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=zhihu_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_chzzk_naver_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "CHZZK"
    with semaphore:
        json_data = asyncio.run(
            spider.get_chzzk_stream_data(url=record_url, proxy_addr=proxy_address, cookies=chzzk_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_haixiutv_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "嗨秀直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_haixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=haixiu_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_vvxqiu_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "VV星球"
    with semaphore:
        port_info = asyncio.run(
            spider.get_vvxqiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=vvxqiu_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_n17_live(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "17Live"
    with semaphore:
        port_info = asyncio.run(
            spider.get_17live_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yiqilive_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_lang_live(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "浪Live"
    with semaphore:
        port_info = asyncio.run(
            spider.get_langlive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=langlive_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_m_pp_weimipopo_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "飘飘直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_pplive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=pplive_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_n6_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "六间房直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_6room_stream_url(url=record_url, proxy_addr=proxy_address, cookies=six_room_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_lehaitv_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "乐嗨直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_haixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=lehaitv_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_h_catshow168_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "花猫直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_pplive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=huamao_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


# Shopee 带 uid 的 URL 构造：uid 来自接口响应（半可信），且会经 need_update_line_list 落进
# URL_config.ini（`|` 分行、`,`/`，` 分字段、换行分行）。含 `|` 会截断本行、含换行会追加
# 任意新行，等于把接口返回值升级成配置注入面。故做两道断言：① uid 字符集白名单；
# ② 拼好的 URL 与 base 同源（host 不变）。任一不过返回空串，本轮按原 record_url 处理。
# 回归锁：tests/test_regression_main.py::test_shopee_new_record_url_is_sanitized
_SHOPEE_UID_SAFE_RE = re.compile(r"^[A-Za-z0-9_\-&=%./:]+$")


def _build_shopee_record_url(record_url: str, uid: str) -> str:
    base = record_url.split("?")[0]
    if not uid or not _SHOPEE_UID_SAFE_RE.match(uid) or "\n" in uid or "\r" in uid:
        logger.warning(
            i18n.tr(
                "Shopee 返回的 uid 含不合法字符，已跳过配置回写: {record_url}",
                record_url=utils.mask_credentials(record_url),
            )
        )
        return ""
    candidate = base + "?" + uid
    try:
        if (urlsplit(candidate).hostname or "") != (urlsplit(base).hostname or ""):
            logger.warning(
                i18n.tr(
                    "Shopee 返回的 uid 会改变目标主机，已跳过配置回写: {record_url}",
                    record_url=utils.mask_credentials(record_url),
                )
            )
            return ""
    except ValueError:
        return ""
    return candidate


def _resolve_live_shopee(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "shopee"
    with semaphore:
        port_info = asyncio.run(
            spider.get_shopee_stream_url(url=record_url, proxy_addr=proxy_address, cookies=shopee_cookie)
        )
        if port_info.get("uid"):
            # 拼前做同源 + 字符集断言，不合格就丢弃 uid 段（返回空串 → 本轮不回填配置）
            new_record_url = _build_shopee_record_url(record_url, str(port_info["uid"]))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_youtube_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "YouTube"
    with semaphore:
        json_data = asyncio.run(
            spider.get_youtube_stream_url(url=record_url, proxy_addr=proxy_address, cookies=youtube_cookie)
        )
        port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_tb_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "淘宝直播"
    with semaphore:
        json_data = asyncio.run(
            spider.get_taobao_stream_url(url=record_url, proxy_addr=proxy_address, cookies=taobao_cookie)
        )
        port_info = asyncio.run(
            stream.get_stream_url(
                json_data,
                record_quality,
                url_type="all",
                hls_extra_key="hlsUrl",
                flv_extra_key="flvUrl",
            )
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_n3_cn(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "京东直播"
    with semaphore:
        port_info = asyncio.run(spider.get_jd_stream_url(url=record_url, proxy_addr=proxy_address, cookies=jd_cookie))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_faceit_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "faceit"
    with semaphore:
        if global_proxy or proxy_address:
            json_data = asyncio.run(
                spider.get_faceit_stream_data(url=record_url, proxy_addr=proxy_address, cookies=faceit_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问faceit直播平台")
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_miguvideo_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "咪咕直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_migu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=migu_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_show_lailianjie_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "连接直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_lianjie_stream_url(url=record_url, proxy_addr=proxy_address, cookies=lianjie_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_imkktv_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "来秀直播"
    with semaphore:
        port_info = asyncio.run(
            spider.get_laixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=laixiu_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_picarto_tv(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "Picarto"
    with semaphore:
        port_info = asyncio.run(
            spider.get_picarto_stream_url(url=record_url, proxy_addr=proxy_address, cookies=picarto_cookie)
        )
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_custom_stream(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "自定义录制直播"
    port_info = {
        "anchor_name": platform + "_" + str(uuid.uuid4())[:8],
        "is_live": True,
        "record_url": record_url,
    }
    # 流地址键的归属与匹配器同一判据（路径扩展名）：否则 ?f=.flv 会让 HLS 清单被写进 flv_url。
    if _stream_path_suffix(record_url) == ".flv":
        port_info["flv_url"] = record_url
    else:
        port_info["m3u8_url"] = record_url
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_unrecognized(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    logger.error(
        i18n.tr(
            "无法识别的直播地址，本轮跳过: {record_url}",
            # 自定义流地址可带 user:pass@，入 PlayURL.log / streamget.log 前必须脱敏（轮转文件长期保留）。
            record_url=utils.mask_credentials(record_url),
        )
    )
    ctx.unrecognized = True


# 平台分发表：（匹配器, 处理函数）按优先级排列，替代原 60+ 层 elif 链。
# 新增平台 = 追加处理函数 + 一条表项；表项顺序即优先级，调整顺序等于调整平台判定优先级。
_PLATFORM_RESOLVERS: tuple[tuple[Callable[[str], bool], Callable[[_PlatformResolveContext], None]], ...] = (
    # 片段一律写裸 host 或 host 后缀（无尾斜杠、无前导点）：_match_host 按 DNS 标签边界比较，
    # 尾斜杠与前导点都不再是判据。
    (_match_host("douyin.com"), _resolve_douyin_com),
    # 片段一律 scheme 无关：准入侧只在 URL 完全没有 `://` 时补 scheme，写死 https:// 会让
    # http:// 形态命中白名单却落不到解析器，无限空转（不录制、不计失败样本）。
    # 回归锁：tests/test_regression_main.py::test_every_platform_host_matches_without_scheme
    (_match_host("www.tiktok.com"), _resolve_tiktok_com),
    (_match_host("live.kuaishou.com"), _resolve_live_kuaishou_com),
    (_match_host("www.huya.com"), _resolve_huya_com),
    # 虎牙移动端短链：先解析短码再归一为桌面链接，见 _resolve_hy_fan。白名单已登记 hy.fan。
    (_match_host("hy.fan"), _resolve_hy_fan),
    # 斗鱼移动端与 www 共用 _resolve_douyu_com，只影响 URL 形态。
    (_match_host("www.douyu.com", "m.douyu.com"), _resolve_douyu_com),
    (_match_host("www.yy.com"), _resolve_yy_com),
    (_match_host("live.bilibili.com"), _resolve_live_bilibili_com),
    # B站移动端短链：与桌面链路同源，见 _resolve_b23_tv。白名单已登记 b23.tv。
    (_match_host("b23.tv"), _resolve_b23_tv),
    # 两个片段均 scheme 无关：准入只按 host，分派不得按协议（两种协议均有回归覆盖）。
    (_match_host("xhslink.com", "www.xiaohongshu.com"), _resolve_xhslink_com),
    (_match_host("www.bigo.tv", "slink.bigovideo.tv"), _resolve_bigo_tv),
    (_match_host("app.blued.cn"), _resolve_app_blued_cn),
    (_match_host("sooplive.co.kr", "sooplive.com"), _resolve_sooplive_co_kr),
    (_match_host("cc.163.com"), _resolve_cc_163_com),
    (_match_host("qiandurebo.com"), _resolve_qiandurebo_com),
    (_match_host("www.pandalive.co.kr", "www.plive.kr"), _resolve_pandalive_co_kr),
    (_match_host("fm.missevan.com"), _resolve_fm_missevan_com),
    (_match_host("www.winktv.co.kr"), _resolve_winktv_co_kr),
    (_match_host("www.flextv.co.kr", "www.ttinglive.com"), _resolve_flextv_co_kr),
    (_match_host("look.163.com"), _resolve_look_163_com),
    (_match_host("www.popkontv.com"), _resolve_popkontv_com),
    (_match_host("twitcasting.tv"), _resolve_twitcasting_tv),
    (_match_host("live.baidu.com"), _resolve_live_baidu_com),
    (_match_host("weibo.com"), _resolve_weibo_com),
    (_match_host("kugou.com"), _resolve_kugou_com),
    (_match_host("www.twitch.tv"), _resolve_twitch_tv),
    (_match_host("www.liveme.com"), _resolve_liveme_com),
    (_match_host("www.huajiao.com"), _resolve_huajiao_com),
    (_match_host("7u66.com"), _resolve_n7u66_com),
    (_match_host("showroom-live.com"), _resolve_showroom_live_com),
    (_match_host("live.acfun.cn", "m.acfun.cn"), _resolve_live_acfun_cn),
    # 白名单含 live/wap 两个子域，解析侧只取末段房间号，故片段放宽到 tlclw.com。
    (_match_host("tlclw.com"), _resolve_live_tlclw_com),
    (_match_host("ybw1666.com"), _resolve_ybw1666_com),
    (_match_host("www.inke.cn"), _resolve_inke_cn),
    (_match_host("www.zhihu.com"), _resolve_zhihu_com),
    (_match_host("chzzk.naver.com"), _resolve_chzzk_naver_com),
    (_match_host("www.haixiutv.com"), _resolve_haixiutv_com),
    (_match_host("vvxqiu.com"), _resolve_vvxqiu_com),
    (_match_host("17.live"), _resolve_n17_live),
    (_match_host("www.lang.live"), _resolve_lang_live),
    (_match_host("m.pp.weimipopo.com"), _resolve_m_pp_weimipopo_com),
    (_match_host("6.cn"), _resolve_n6_cn),
    (_match_host("lehaitv.com"), _resolve_lehaitv_com),
    (_match_host("h.catshow168.com"), _resolve_h_catshow168_com),
    # Shopee 各地区站是 live.shopee.<TLD> 形态，片段取两段；单段 "live.shopee" 会因尾部残点
    # 在标签边界判据下永假（白名单的 "live.shopee." 由准入侧单独归一，见 main() 主循环）。
    (_match_host("live.shopee.co", "shp.ee"), _resolve_live_shopee),
    (_match_host("www.youtube.com", "youtu.be"), _resolve_youtube_com),
    # 补 huodong.m.taobao.com：它是白名单里的淘宝分享页 host，也是取流 Referer。
    (_match_host("tb.cn", "tbzb.taobao.com", "huodong.m.taobao.com"), _resolve_tb_cn),
    (_match_host("3.cn", "m.jd.com"), _resolve_n3_cn),
    (_match_host("faceit.com"), _resolve_faceit_com),
    (_match_host("www.miguvideo.com", "m.miguvideo.com"), _resolve_miguvideo_com),
    (_match_host("show.lailianjie.com"), _resolve_show_lailianjie_com),
    (_match_host("www.imkktv.com"), _resolve_imkktv_com),
    (_match_host("www.picarto.tv"), _resolve_picarto_tv),
    (_match_stream_suffix(".m3u8", ".flv"), _resolve_custom_stream),
)


# 按地址分派到平台解析；无法识别返回 None（调用方延迟重试）
def _resolve_platform_stream(
    record_url: str, proxy_address: str | None, record_quality: str
) -> tuple[str, dict[str, Any], dict[str, Any] | None, str] | None:
    ctx = _PlatformResolveContext(record_url, proxy_address, record_quality)
    for matcher, handler in _PLATFORM_RESOLVERS:
        if matcher(record_url):
            # handler 必须包异常：内部 cookie/token 回写会走 utils.update_config（未包异常）。
            # 一次写盘失败就会把已拿到的流地址整轮丢弃，并把磁盘/权限问题计入按 host 的熔断样本。
            # 回写只是缓存优化，失败只告警。
            try:
                handler(ctx)
            except Exception as e:
                logger.warning(
                    i18n.tr(
                        "平台解析或凭据回写失败（本轮按未识别处理）: {record_url} - {type_name}: {e}",
                        record_url=utils.mask_credentials(record_url),
                        type_name=type(e).__name__,
                        e=e,
                    )
                )
                ctx.unrecognized = True
            break
    else:
        # 准入按精确 host、分派按片段，口径不同：白名单命中但无解析器的地址会落到这里
        # （历史上有 http:// 遇 https:// 钉死、xhslink.com、wap.tlclw.com 等）。
        # 静态锁：tests/test_regression_main.py::test_every_platform_host_matches_without_scheme
        _resolve_unrecognized(ctx)
    if ctx.unrecognized:
        return None
    return ctx.platform, ctx.port_info, ctx.record_danmaku_args, ctx.new_record_url


def _build_ffmpeg_output_args(
    save_file_path: str,
    record_save_type: str,
    split_video_by_time: bool,
    split_time: str,
    is_audio: bool = False,
) -> list[str]:
    # 输出侧参数统一在此拼装（音频 MP3/M4A + 视频 TS/FLV/MKV/MP4）；输入级选项与文件名/时间戳
    # 仍由 start_record 负责。容器一律查 SEGMENT_FORMAT_BY_SUFFIX，杜绝「.mp3 装进 MP4 /
    # .ts 装进 ipod」这类静默错封装（历史上 5 份复制粘贴，改一处漏四处）。
    if is_audio:
        # 纯音频：含 MP3 → libmp3lame + mp3；其余（M4A / 纯音频平台）→ aac + aac_adtstoasc + ipod
        if "MP3" in record_save_type:
            if split_video_by_time:
                return [
                    "-map",
                    "0:a",
                    "-c:a",
                    "libmp3lame",
                    "-ab",
                    "320k",
                    "-f",
                    "segment",
                    "-segment_time",
                    split_time,
                    "-segment_format",
                    SEGMENT_FORMAT_BY_SUFFIX[".mp3"],
                    "-reset_timestamps",
                    "1",
                    save_file_path,
                ]
            return ["-map", "0:a", "-c:a", "libmp3lame", "-ab", "320k", save_file_path]
        # M4A / 纯音频平台（猫耳FM / Look）：aac + aac_adtstoasc + ipod 容器
        if split_video_by_time:
            return [
                "-map",
                "0:a",
                "-c:a",
                "aac",
                "-bsf:a",
                "aac_adtstoasc",
                "-ab",
                "320k",
                "-f",
                "segment",
                "-segment_time",
                split_time,
                "-segment_format",
                SEGMENT_FORMAT_BY_SUFFIX[".m4a"],
                "-reset_timestamps",
                "1",
                save_file_path,
            ]
        return [
            "-map",
            "0:a",
            "-c:a",
            "aac",
            "-bsf:a",
            "aac_adtstoasc",
            "-ab",
            "320k",
            "-movflags",
            "+faststart",
            save_file_path,
        ]

    # 视频容器：FLV / MKV / MP4 显式分支，其余（TS 或未知值）走默认 TS
    if record_save_type == "FLV":
        if split_video_by_time:
            return [
                "-map",
                "0",
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-bsf:a",
                "aac_adtstoasc",
                "-f",
                "segment",
                "-segment_time",
                split_time,
                "-segment_format",
                SEGMENT_FORMAT_BY_SUFFIX[".flv"],
                "-reset_timestamps",
                "1",
                save_file_path,
            ]
        return [
            "-map",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-bsf:a",
            "aac_adtstoasc",
            "-f",
            "flv",
            save_file_path,
        ]
    if record_save_type == "MKV":
        if split_video_by_time:
            return [
                "-flags",
                "global_header",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0",
                "-f",
                "segment",
                "-segment_time",
                split_time,
                "-segment_format",
                SEGMENT_FORMAT_BY_SUFFIX[".mkv"],
                "-reset_timestamps",
                "1",
                save_file_path,
            ]
        return [
            "-flags",
            "global_header",
            "-map",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-f",
            "matroska",
            save_file_path,
        ]
    if record_save_type == "MP4":
        if split_video_by_time:
            return [
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-map",
                "0",
                "-f",
                "segment",
                "-segment_time",
                split_time,
                "-segment_format",
                SEGMENT_FORMAT_BY_SUFFIX[".mp4"],
                "-reset_timestamps",
                "1",
                "-movflags",
                "+frag_keyframe+empty_moov",
                save_file_path,
            ]
        return ["-map", "0", "-c:v", "copy", "-c:a", "copy", "-f", "mp4", save_file_path]

    # 默认 TS（record_save_type == "TS" 或未知值）：分段必须显式 mpegts，
    # 非分段直接 -f mpegts（HEVC 经 ipod 会 AVERROR(EINVAL)，见 CODE_REVIEW P0）。
    if split_video_by_time:
        return [
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-map",
            "0",
            "-f",
            "segment",
            "-segment_time",
            split_time,
            "-segment_format",
            SEGMENT_FORMAT_BY_SUFFIX[".ts"],
            "-reset_timestamps",
            "1",
            save_file_path,
        ]
    return ["-c:v", "copy", "-c:a", "copy", "-map", "0", "-f", "mpegts", save_file_path]


# 输出文件名差异的单一定义点：扩展名与分段时戳格式各一张查表，分支只负责查表。
# [历史注] 这两项曾在 5 条保存类型分支里各写一份，`-segment_format` 两处互换的 P0 事故即源于此。
_EXTENSION_BY_SAVE_TYPE: dict[str, str] = {"FLV": "flv", "MKV": "mkv", "MP4": "mp4"}
# 分段文件名时戳格式：FLV 沿用历史 %y%m%d_%H%M%S，其余 %Y-%m-%d_%H-%M-%S；
# 非分段沿用外层 now，格式恒为 %y%m%d_%H%M%S。
_SEGMENT_NOW_FORMAT_BY_SAVE_TYPE: dict[str, str] = {
    "FLV": "%y%m%d_%H%M%S",
    "MKV": "%Y-%m-%d_%H-%M-%S",
    "MP4": "%Y-%m-%d_%H-%M-%S",
    "TS": "%Y-%m-%d_%H-%M-%S",
}
_DEFAULT_SEGMENT_NOW_FORMAT = "%Y-%m-%d_%H-%M-%S"


# 输出文件名模板的 `%` 兜底清洗：segment muxer 把输出路径当 printf 模板，除末尾 `_%03d`/
# `_%02d` 外残留裸 `%` 会直接 rc=-22，且被误判成容器不匹配 → CDN 快速失败 → 健康线路被拉黑。
# rstr 已过滤 `%`，但昵称/标题还可能来自旧配置、手工改名或平台原样返回，故拼模板前再剥一层。
def _sanitize_output_name_base(base: str) -> str:
    if "%" not in base:
        return base
    cleaned = base.replace("%", "")
    logger.warning(i18n.tr("输出文件名模板含非法 %% 占位符，已剔除后继续录制: {name}", name=base))
    return cleaned


# 输出文件路径构造：音频走 .mp3/.m4a 与 _%02d/_00，视频按保存类型查表、未知值回落 ts
# （与 _build_ffmpeg_output_args 的容器裁决一致）。
def _build_record_output_path(
    full_path: str,
    anchor_name: str,
    title_in_name: str,
    now: str,
    record_save_type: str,
    split_video_by_time: bool,
    is_audio: bool = False,
) -> str:
    if is_audio:
        # 扩展名必须与 _build_ffmpeg_output_args 选用的编码器/容器一致，否则出现「.mp3 里装 AAC/MP4」
        extension = "mp3" if "MP3" in record_save_type else "m4a"
        name_format = "_%02d" if split_video_by_time else "_00"
        # 模板里只允许保留 name_format 这一个占位符
        base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{now}")
        return f"{full_path}/{base_name}{name_format}.{extension}"

    extension = _EXTENSION_BY_SAVE_TYPE.get(record_save_type, "ts")
    if split_video_by_time:
        seg_now = time.strftime(
            _SEGMENT_NOW_FORMAT_BY_SAVE_TYPE.get(record_save_type, _DEFAULT_SEGMENT_NOW_FORMAT), time.localtime()
        )
        # 分段模板只允许保留 _%03d，其余 % 一律剥掉
        base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{seg_now}")
        return f"{full_path}/{base_name}_%03d.{extension}"
    # 非分段：FLV 保留历史 _00 序号后缀（与直下 FLV 命名对齐），其余保存类型无该后缀
    plain_suffix = "_00" if record_save_type == "FLV" else ""
    # 非分段不经过 segment muxer，但仍走同一清洗：带 % 会让后续转封装/合并在别的环节再炸一次
    base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{now}")
    return f"{full_path}/{base_name}{plain_suffix}.{extension}"


# 海外平台 CDN 往返延迟高、GOP 探测更慢，统一放大超时与探测窗口，避免握手阶段超时退出。
def _ffmpeg_network_tuning(is_overseas: bool) -> dict[str, str]:
    if is_overseas:
        return {
            "rw_timeout": "50000000",
            "analyzeduration": "40000000",
            "probesize": "20000000",
            "bufsize": "15000k",
            "max_muxing_queue_size": "2048",
        }
    return {
        "rw_timeout": "15000000",
        "analyzeduration": "20000000",
        "probesize": "10000000",
        "bufsize": "8000k",
        "max_muxing_queue_size": "1024",
    }


# ffmpeg 输入侧参数构造：把 -reconnect* / -headers / -tls_verify / -http_proxy 收敛为纯函数。
# 参数顺序敏感，一律按锚点（`-i` 下标 / 列表头插入）定位，不用裸数字下标。
def _build_ffmpeg_input_args(
    real_url: str,
    user_agent: str,
    tuning: dict[str, str],
    headers: dict[str, str] | None = None,
    tls_verify: bool = True,
    proxy_address: str | None = None,
) -> list[str]:
    # FFmpeg 9.0 兼容：未使用 9.0 移除的 CLI 参数；TLS 校验默认开启，是否插 -tls_verify 0
    # 由调用方按 get_effective_ssl_verify(platform) 裁决。
    command = [
        "ffmpeg",
        "-y",
        "-rw_timeout",
        tuning["rw_timeout"],
        "-loglevel",
        "error",
        "-hide_banner",
        "-user_agent",
        user_agent,
        # 协议白名单按最小权限收敛：输入恒为 http(s)/rtmp 直播流，放行 file 会让可控 URL
        # 读写本地文件；crypto 必须保留（HLS 分片解密）。
        "-protocol_whitelist",
        "rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy",
        "-analyzeduration",
        tuning["analyzeduration"],
        "-probesize",
        tuning["probesize"],
        "-fflags",
        "+discardcorrupt",
        # -reconnect* 是 input 级（HTTP 协议）选项，必须位于 -i 之前：放到 -i 之后会被
        # 当作输出选项静默接受（无警告、rc=0、重连完全失效），而失败判定全建立在其生效之上。
        "-reconnect_delay_max",
        "60",
        # 每个 -reconnect* 必须紧跟其取值：缺值会让 ffmpeg 把下一个选项名当值，
        # 报「Unable to parse ... as boolean」并以 -22 退出。
        # tests/test_ffmpeg_reconnect_args.py 用 AST 同时锁定「带值」与「位于 -i 之前」。
        "-reconnect_streamed",
        "1",
        "-reconnect_at_eof",
        "1",
        "-re",
        "-i",
        real_url,
        "-bufsize",
        tuning["bufsize"],
        "-sn",
        "-dn",
        # -thread_queue_size 只能放在 -i 之后：上游已将其收窄为输出专属（6.1 起 release 标
        # input/output、master 仅 output）。放在 -i 前不是「静默不生效」而是拒绝打开输入：
        #   Option thread_queue_size ... cannot be applied to input url ... Invalid argument
        # 代价：≤9.0.2 上失去「强制独立输入读取线程」效果（master 已无此机制）。
        # 回归锁：tests/test_ffmpeg_reconnect_args.py::TestOutputOnlyOptionsFollowInputFlag
        "-thread_queue_size",
        "1024",
        "-max_muxing_queue_size",
        tuning["max_muxing_queue_size"],
        "-correct_ts_overflow",
        "1",
        "-avoid_negative_ts",
        "1",
    ]

    # HLS 输入禁用 -reconnect_at_eof：hls demuxer 需读到播放列表 EOF 才拉媒体段，
    # 开启后 http 层会在 EOF 处无限重连（1/3/7/…/60s 退避），媒体段一个拉不到、零字节、
    # 进程永不退出。FLV 必须保留：CDN 掐断长连接时在 EOF 处重连续写同一文件（斗鱼游客态缓解）。
    # 判据必须「小写 + 只看 path」：整串匹配会把 query 带 .m3u8 的 FLV 误删；大小写敏感
    # 会让 .M3U8 漏配。删除用 del 而非置 "0"，保证命令行干净。
    # 孪生副本 scripts/douyin_live_recorder_standalone.py 仍是 `".m3u8" in url.lower()`，
    # 改判据时须一并核对。
    if _stream_path_suffix(real_url) == ".m3u8":
        _eof_idx = command.index("-reconnect_at_eof")
        del command[_eof_idx : _eof_idx + 2]

    if headers:
        # ffmpeg 的 -headers 支持多行（\r\n 分隔）多个头；
        # 合并 referer/origin 与 cookie，与校验探针保持一致。
        header_blob = "\r\n".join(f"{k}:{v}" for k, v in headers.items())
        # -headers 是输入选项，必须按 `-i` 锚点插入：上方 del 与选项增删都会移动下标，
        # 写死下标会把头插到输入之后（报 "Option headers not found" 或静默落到输出区）。
        _i_idx = command.index("-i")
        command[_i_idx:_i_idx] = ["-headers", header_blob]

    # 默认校验证书；tls_verify=False 时插 -tls_verify 0（绕过虎牙 TX CDN 等主机名不匹配）。
    # -tls_verify 是 tls 私有选项，对 http 流插入会报 "Option tls_verify not found"，故仅 https。
    if not tls_verify and (real_url or "").startswith("https://"):
        # 下标 1 = 紧跟可执行档之后：全局选项必须在 -i 之前，插最前最稳（多次插入时后插者在前）
        command.insert(1, "-tls_verify")
        command.insert(2, "0")

    if proxy_address:
        command.insert(1, "-http_proxy")
        command.insert(2, proxy_address)

    return command


# 五条保存类型分支共用的「起一次 ffmpeg 录制」执行骨架（原为五份复制粘贴）。
# 返回 (started, comment_end)：
#   started=False —— ffmpeg 未启动（OSError），调用方不应置 record_finished；
#   comment_end=True —— 地址被注释 / 收到退出标志，调用方应结束本房间线程。
def _run_ffmpeg_record(
    record_name: str,
    record_url: str,
    record_host: str,
    ffmpeg_command: list[str],
    record_save_type: str,
    custom_script: str | None,
    platform: str,
    record_danmaku_args: dict[str, Any] | None,
) -> tuple[bool, bool]:
    try:
        comment_end = check_subprocess(
            record_name,
            record_url,
            ffmpeg_command,
            record_save_type,
            custom_script,
            platform=platform,
            danmaku_args=record_danmaku_args,
        )
    except OSError as e:
        # ffmpeg 启动失败只抛 OSError 子类；CalledProcessError 仅在 run(check=True) 时出现，
        # Popen 流程下不会抛。
        logger.error(
            i18n.tr(
                "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                type_name=type(e).__name__,
                e=e,
                get_error_line=_get_error_line(e),
            )
        )
        # 启动失败时 recording 集合中本房间条目已先于 Popen 加入（见 start_record
        # 内的 with record_state_lock 块），此处必须同步 discard，否则「正在录制」
        # 快照长期幽灵存在，磁盘满时的 sys.exit 判定、通知推送、UI 状态都会基于
        # 幽灵条目做出错误决策
        with record_state_lock:
            recording.discard(record_name)
            recording_time_list.pop(record_name, None)
        record_error(record_host)
        return False, False
    return True, comment_end


# 录后转 MP4 统一出口：关闭转码直接返回；分段按「前缀 + _<数字序号>.<ext>」精确匹配；
# 非分段直接转单个文件（不使用 `_*.flv` 宽匹配，避免误伤同名前缀的历史文件）。
def _convert_after_record(save_file_path: str, split_video_by_time: bool) -> None:
    if not converts_to_mp4:
        return
    try:
        if not split_video_by_time:
            # 本函数作用域内没有 record_name（仅有输出路径），交由 _submit_postprocess 用文件名兜底标注
            _submit_postprocess(converts_mp4, save_file_path, delete_origin_file)
            return
        extension = os.path.basename(save_file_path).rsplit(".", maxsplit=1)[-1]
        # 枚举走 _segment_files（理由见其函数头）。None（目录不可读）必须与 [] 分开报，
        # 否则会把权限/网络盘故障误导成「ffmpeg 没产出」。
        _seg_paths = _segment_files(save_file_path)
        if _seg_paths is None:
            logger.warning(
                i18n.tr(
                    "分段目录不可读，跳过转换: {directory}",
                    directory=utils.mask_credentials(os.path.dirname(save_file_path)),
                )
            )
            return
        seg_files = sorted(_seg_paths)
        if not seg_files:
            # 文案带扩展名：本出口被 TS/MKV/MP4/音频等所有分段形态复用，写死「FLV」会把排查引向错误方向。
            logger.warning(
                i18n.tr(
                    "未找到分段文件（{extension}），跳过转换: {seg_pattern}",
                    extension=extension,
                    seg_pattern=f"{os.path.basename(save_file_path).rsplit('_', maxsplit=1)[0]}_*.{extension}",
                )
            )
        for seg_file in seg_files:
            _submit_postprocess(converts_mp4, str(seg_file), delete_origin_file)
    except Exception as e:
        logger.error(i18n.tr("转码失败: {type_name}: {e} ", type_name=type(e).__name__, e=e))


# 单个直播间的录制线程主体：循环「解析平台 → 选源 → ffmpeg/直下」，直到 URL 被注释、
# 收到退出标志或停止录制开关关闭。room_state 用于把本轮录制名带回线程出口，
# 使弹幕监控清理只在线程退出时执行一次；直接调用时可不传。
def start_record(
    url_data: tuple[str, str, str], count_variable: int = -1, room_state: dict[str, str] | None = None
) -> None:
    # 日志关联字段在线程入口即绑定：首轮解析前 record_name 为空，但退出/注释/解析失败等日志
    # 已经产生，先用「序号N」占位，解析出主播名后再升级（原因见 src/logger.py::ROOM_FIELD）。
    set_room_context(f"序号{count_variable}")
    while True:
        # 两者都置于外层 try 之前：最外层 except/finally 都要引用，放 try 内会在首语句抛错时
        # 未绑定。record_host 是熔断 key；空串在 record_error 中视为 falsy，只计全局预算。
        record_name = ""
        record_host = ""
        try:
            record_finished = False
            run_once = False
            start_pushed = False
            new_record_url = ""  # Shopee 平台专用：记录带 uid 的完整 URL 用于更新配置
            record_danmaku_args: dict[str, Any] | None = None  # 弹幕参数(平台相关)，传入 check_subprocess 启停弹幕
            count_time = time.time()
            record_quality_zh, record_url, anchor_name = url_data
            record_quality = get_quality_code(record_quality_zh)
            record_host = host_of(record_url)
            # 画质回采值与降级判定用的两个 helper（见下方录制状态登记处的 actual_quality*）
            from src.stream import code_to_zh
            from src.stream import is_downgrade as _is_downgrade

            proxy_address = proxy_addr
            platform = "未知平台"

            if proxy_addr:
                proxy_address = None
                if enable_proxy_platform_list:
                    # 循环变量不用 platform：避免遮蔽外层 platform="未知平台"，
                    # 导致循环结束后 platform 残留为列表最后一个元素（日志误报平台名）
                    # 只比 urlsplit 得到的 host，不拿整条 URL 做子串匹配（query 里出现平台名即误判）
                    if _host_in_platform_list(record_url, enable_proxy_platform_list):
                        proxy_address = proxy_addr

            if not proxy_address:
                if extra_enable_proxy_platform_list:
                    # 与上方 enable_proxy_platform_list 同判据（只比 host）
                    if _host_in_platform_list(record_url, extra_enable_proxy_platform_list):
                        proxy_address = proxy_addr_bak or None

            while True:
                # 每轮先归零再分派：绝不沿用上一轮遗留的弹幕参数，防止解析短路时把旧值带进录制
                record_danmaku_args = None
                if exit_recording:
                    # 自定义流地址可写成 `https://u:p@host/x.m3u8`，入日志前必须脱敏
                    # （PlayURL.log / streamget.log 轮转保留多份）。静态锁：
                    # tests/test_regression_main.py::test_room_and_breaker_logs_mask_credentials
                    logger.debug(
                        i18n.tr(
                            "检测到退出标志，录制线程退出: {record_url}",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    return
                # 停止录制：线程退出，运行列表由 _room_thread_target 的 finally 兜底
                if not recording_enabled:
                    logger.debug(
                        i18n.tr(
                            "录制已停止，房间线程退出: {record_url}",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    return
                # URL 被注释/移除立即退出，不等解析结果：解析持续失败时后者永远走不到，
                # 线程会一直占着监控位，配置变更迟迟不生效。
                if record_url in url_comments:
                    print(
                        i18n.tr(
                            "[{record_url}]已被注释,本条线程将会退出",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    clear_record_info(record_name, record_url)
                    return
                # 熔断预检：该 host 连续失败达阈值时跳过本轮探测并退避，把并发槽让给其他平台。
                if scheduler is not None and not scheduler.allow(record_host):
                    _backoff = scheduler.backoff_seconds(record_host)
                    _backoff = min(_backoff, max(30.0, float(delay_default)))
                    logger.debug(
                        i18n.tr(
                            "[{record_host}] 并发熔断中，跳过本轮探测，退避 {_backoff}s",
                            # host_of 已剥去 `user:pass@`；再过一次 mask 兜住非 host_of 来源的凭据形态
                            record_host=utils.mask_credentials(record_host),
                            _backoff=f"{_backoff:.0f}",
                        )
                    )
                    _interruptible_sleep(_backoff, record_url)
                    continue
                try:
                    # 平台分派；无法识别返回 None，走延迟重试
                    _resolved = _resolve_platform_stream(record_url, proxy_address, record_quality)
                    if _resolved is None:
                        # 无法识别：延迟一轮重试而非结束线程。直接 break 会绕过轮末延迟，
                        # 变成 ~100ms/轮的空转刷请求；sleep+continue 同时保留每轮预检。
                        _interruptible_sleep(max(30.0, float(delay_default)), record_url)
                        continue
                    platform, port_info, record_danmaku_args, new_record_url = _resolved

                    if anchor_name:
                        if "主播:" in anchor_name:
                            anchor_split: list[str] = anchor_name.split("主播:")
                            if len(anchor_split) > 1 and anchor_split[1].strip():
                                anchor_name = anchor_split[1].strip()
                            else:
                                anchor_name = cast(str, port_info.get("anchor_name", ""))
                    else:
                        anchor_name = cast(str, port_info.get("anchor_name", ""))

                    if not port_info.get("anchor_name", ""):
                        print(
                            i18n.tr(
                                "序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_data}",
                                count_variable=count_variable,
                                # 自定义流地址可能带 user:pass@，实参必须过码（控制台与不轮转的
                                # web_console.log）。mask_credentials 只接受 str，故传 str(tuple)；
                                # 占位符沿用目录里既有的 {url_data}。
                                url_data=utils.mask_credentials(str(url_data)),
                            )
                        )
                        record_error(record_host)
                        # 拿不到 anchor_name 就是「无状态轮」，必须显式 continue：下面的开播/下播
                        # 状态机只在解析成功分支内推进，失败轮不应有机会翻转推送状态。
                        # 等待与 `_resolved is None` 分支同构，保持可中断。
                        _interruptible_sleep(max(30.0, float(delay_default)), record_url)
                        continue
                    else:
                        # 解析成功即上报成功样本：half-open 探针依赖本轮结果闭环。只在 ffmpeg
                        # 退出时上报会让长时间录制期间同 host 其余房间持续熔断饿死，未开播轮又
                        # 完全无样本。与上方失败分支的 record_error 对称。
                        record_success(record_host)
                        anchor_name = clean_name(anchor_name)

                        # 主播名自动同步：最新名与当前使用名不一致时，先改历史录制目录/文件，
                        # 成功后再更新 URL_config.ini 与本轮使用名。此刻必然不在录制中（录制期间
                        # 阻塞在 check_subprocess），不会触碰 ffmpeg 正在写入的文件；个别文件被
                        # 转码/字幕占用时只告警。自定义流地址的 anchor_name 含随机 UUID，跳过。
                        latest_anchor_name = clean_name(cast(str, port_info.get("anchor_name", "")))
                        if (
                            auto_update_anchor_name
                            and platform != "自定义录制直播"
                            and anchor_name
                            and latest_anchor_name
                            and latest_anchor_name != "空白昵称"
                            and anchor_name != latest_anchor_name
                        ):
                            # 文件系统与配置都成功才切换本轮使用名，否则保持旧名、下轮重试
                            # （rename 对已改名的目录幂等）
                            if rename_anchor_directory(
                                anchor_name, latest_anchor_name, platform
                            ) and update_anchor_name(record_url, latest_anchor_name):
                                logger.info(
                                    i18n.tr(
                                        "主播名已变更，配置与录制文件同步更新: {anchor_name} -> {latest_anchor_name}",
                                        anchor_name=anchor_name,
                                        latest_anchor_name=latest_anchor_name,
                                    )
                                )
                                # 清理旧名残留的录制状态（兜底异常残留，防状态列表长期挂旧名）
                                _stale_record_name = f"序号{count_variable} {anchor_name}"
                                anchor_name = latest_anchor_name
                                with record_state_lock:
                                    recording.discard(_stale_record_name)
                                    recording_time_list.pop(_stale_record_name, None)
                                # 改名后要把旧名从弹幕监控枢纽摘掉：枢纽按房间名登记，旧名只在
                                # 线程退出时才会经 room_stopped 清除；改名发生在线程内部，线程还能
                                # 跑几百轮，旧名会永久挂在监控页与 JSONL 边车里。用改名前的
                                # _stale_record_name；监控为旁路，失败静默、不得打断录制。
                                try:
                                    from src.danmaku_monitor import get_hub

                                    get_hub().room_stopped(_stale_record_name, "主播改名")
                                except Exception:
                                    pass
                        record_name = f"序号{count_variable} {anchor_name}"
                        # 关联字段升级为可读房间名：每轮重算，主播改名后同步刷新（与文件 sink 的 {extra[room]} 同值）
                        set_room_context(record_name)

                        if record_url in url_comments:
                            print(i18n.tr("[{anchor_name}]已被注释,本条线程将会退出", anchor_name=anchor_name))
                            clear_record_info(record_name, record_url)
                            return

                        if not url_data[-1] and not run_once:
                            if new_record_url:
                                need_update_line_list.append(
                                    f"{record_url}|{new_record_url},主播: {anchor_name.strip()}"
                                )
                                with record_state_lock:
                                    not_record_list.append(new_record_url)
                            else:
                                need_update_line_list.append(f"{record_url}|{record_url},主播: {anchor_name.strip()}")
                            run_once = True

                        push_at = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
                        if not port_info.get("is_live", False):
                            if len(recording) == 0:
                                print(i18n.tr("\r{record_name} 等待直播... ", record_name=record_name))

                            if start_pushed:
                                if over_show_push:
                                    # 裸字面量必须包 tr() 才会进入 i18n 提取集合，否则非简中下
                                    # 推送正文仍是中文；占位符是方括号，故仍走下面的 .replace 链。
                                    push_content = i18n.tr("直播间状态更新：[直播间名称] 直播已结束！时间：[时间]")
                                    if over_push_message_text:
                                        push_content = over_push_message_text

                                    push_content = push_content.replace("[直播间名称]", record_name).replace(
                                        "[时间]", push_at
                                    )
                                    threading.Thread(
                                        target=push_message,
                                        args=(record_name, record_url, push_content.replace(r"\n", "\n")),
                                        daemon=True,
                                    ).start()
                                start_pushed = False

                        else:
                            # 在打印点直接 tr 插值：提取器只认「首参为常量/f-string」，变量引用扫不到
                            print(i18n.tr("\r{record_name} 正在直播中...", record_name=record_name))

                            if live_status_push and not start_pushed:
                                if begin_show_push:
                                    # 同上：裸字面量补 tr() 包裹
                                    push_content = i18n.tr("直播间状态更新：[直播间名称] 正在直播中，时间：[时间]")
                                    if begin_push_message_text:
                                        push_content = begin_push_message_text

                                    push_content = push_content.replace("[直播间名称]", record_name).replace(
                                        "[时间]", push_at
                                    )
                                    threading.Thread(
                                        target=push_message,
                                        args=(record_name, record_url, push_content.replace(r"\n", "\n")),
                                        daemon=True,
                                    ).start()
                                start_pushed = True

                            if disable_record:
                                # 逐秒 sleep + 每秒重查三条件：一次性 sleep(push_check_seconds)
                                # 会让线程在「停止录制」后滞留整段间隔。直接引用模块全局即晚绑定；
                                # 注意 `main` 在本文件是入口函数而非模块对象，不能写 main.recording_enabled。
                                _sleep_remaining = push_check_seconds
                                while _sleep_remaining > 0:
                                    if not recording_enabled or exit_recording or record_url in url_comments:
                                        break
                                    time.sleep(1)
                                    _sleep_remaining -= 1
                                continue

                            # 按 platform 转发对应登录态 Cookie 给校验探针与 ffmpeg 录制命令（解决 CDN 403）
                            platform_cookie = {
                                "抖音直播": dy_cookie,
                                "TikTok直播": tiktok_cookie,
                                "快手直播": ks_cookie,
                                "虎牙直播": hy_cookie,
                                "斗鱼直播": douyu_cookie,
                                "YY直播": yy_cookie,
                                "B站直播": bili_cookie,
                                "小红书直播": xhs_cookie,
                                "bigo": bigo_cookie,
                                "blued": blued_cookie,
                                "SOOP(原AfreecaTV)": sooplive_cookie,
                                "网易CC直播": netease_cookie,
                                "千度热播": qiandurebo_cookie,
                                "PandaTV": pandatv_cookie,
                                "猫耳FM直播": maoerfm_cookie,
                                "WinkTV": winktv_cookie,
                                "TTingLive(原Flextv)": flextv_cookie,
                                "Look直播": look_cookie,
                                "TwitCasting": twitcasting_cookie,
                                "百度直播": baidu_cookie,
                                "微博直播": weibo_cookie,
                                "酷狗直播": kugou_cookie,
                                "LiveMe": liveme_cookie,
                                # 强制直下平台（shopee / 花椒）必须入表：解析函数已用同一份 Cookie，
                                # 不入表会让直下路径拿不到登录态，CDN 按游客态钳制或 403。
                                # 其余已声明未入表的 *_cookie 不盲加：是否需登录态未经现网确认。
                                "shopee": shopee_cookie,
                                "花椒直播": huajiao_cookie,
                            }.get(platform, "")

                            real_url = select_source_url(port_info, proxy_address, platform, cookies=platform_cookie)
                            if not real_url:
                                # 三级候选全部校验失败：本轮放弃。录制链假定 real_url 非空，强进会
                                # 抛未绑定变量或复用上一轮残留命令；等一轮后重新解析。
                                logger.warning(
                                    i18n.tr("{anchor_name} 本轮未获取到可用流地址，跳过录制", anchor_name=anchor_name)
                                )
                                _interruptible_sleep(max(random.randint(-5, 5) + delay_default, 0), record_url)
                                continue
                            full_path = f"{default_path}/{platform}"
                            # real_url 非空已由上方 continue 保证，时间戳/标题前缀无条件构造
                            # （不要把录制链再嵌进条件块，否则局部变量可能未绑定）。
                            now = datetime.datetime.today().strftime("%y%m%d_%H%M%S")
                            # 日期目录单独取，不能切 now：`%y%m%d_%H%M%S` 的 now[:10] 会粘上
                            # 小时与分钟位，导致每约 10 分钟换一个目录。
                            date_dir = datetime.datetime.today().strftime("%y%m%d")
                            live_title = cast(str, port_info.get("title", ""))
                            title_in_name = ""
                            if live_title:
                                live_title = clean_name(live_title)
                                title_in_name = live_title + "_" if filename_by_title else ""

                            try:
                                if len(video_save_path) > 0:
                                    if not video_save_path.endswith(("/", "\\")):
                                        full_path = f"{video_save_path}/{platform}"
                                    else:
                                        full_path = f"{video_save_path}{platform}"

                                full_path = full_path.replace("\\", "/")
                                if folder_by_author:
                                    full_path = f"{full_path}/{anchor_name}"
                                if folder_by_time:
                                    full_path = f"{full_path}/{date_dir}"
                                if folder_by_title and port_info.get("title"):
                                    if folder_by_time:
                                        full_path = f"{full_path}/{live_title}_{anchor_name}"
                                    else:
                                        full_path = f"{full_path}/{date_dir}_{live_title}"
                                os.makedirs(full_path, exist_ok=True)
                            except Exception as e:
                                logger.error(
                                    i18n.tr(
                                        "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                                        type_name=type(e).__name__,
                                        e=e,
                                        get_error_line=_get_error_line(e),
                                    )
                                )
                                # 目录建不出来不得继续起 ffmpeg：ffmpeg 打不开输出即秒退，会被
                                # 判成「CDN 快速失败」，给健康流地址记探针退避并污染熔断统计。
                                # 等一轮再试（与上方「无可用流地址」同口径）。
                                _interruptible_sleep(max(random.randint(-5, 5) + delay_default, 0), record_url)
                                continue

                            if platform not in ("自定义录制直播", "虎牙直播"):
                                if enable_https_recording and real_url.startswith("http://"):
                                    # HTTPS 录制模式：升级为 https 拉流（拉流侧证书校验按开关收紧/豁免）
                                    real_url = real_url.replace("http://", "https://")
                                elif not enable_https_recording and real_url.startswith("https://"):
                                    # HTTP 录制模式：降级为 http 拉流。海外 CDN 多为 https-only，
                                    # 强转必然失败，海外 host 保持原样。
                                    if not _host_in_platform_list(record_url, OVERSEAS_PLATFORM_HOST):
                                        real_url = real_url.replace("https://", "http://")

                                # 列表元素是 resolver 回写的平台名，不是 host 片段。回归锁见 tests/test_platform_dispatch.py。
                                http_record_list = ["shopee", "咪咕直播"]
                                if platform in http_record_list:
                                    real_url = real_url.replace("https://", "http://")

                            # 默认移动端 UA；虎牙/B站等国内 CDN 拒绝移动端，改用桌面 UA。
                            # 必须引用 stream_select.MOBILE_UA 唯一事实源：与校验探针共用，
                            # 抄字面量会让两端静默漂移（表现为「校验通过但录制 403」）。
                            # 静态锁：tests/test_regression_main.py
                            # :TestDirectDownloadUserAgent::test_fallback_ua_is_the_same_constant_as_ffmpeg_path
                            user_agent = get_record_user_agent(platform) or MOBILE_UA

                            # 网络/缓冲参数与输入侧命令行全部下沉到纯函数，此处只做「取参数 → 组装」
                            is_overseas = _host_in_platform_list(record_url, OVERSEAS_PLATFORM_HOST)
                            tuning = _ffmpeg_network_tuning(is_overseas)
                            headers = get_record_headers(platform, record_url, cookies=platform_cookie)
                            ffmpeg_command = _build_ffmpeg_input_args(
                                real_url,
                                user_agent,
                                tuning,
                                headers=headers,
                                # 证书校验由「是否启用https录制」统一裁决（语义见 _http_config
                                # / 模块级 enable_https_recording 注释）；本函数内只在 https
                                # 地址上插 -tls_verify 0，理由见 _build_ffmpeg_input_args 内注释。
                                # 校验探针与直下路径经同一 get_effective_ssl_verify 读取，保证一致。
                                tls_verify=_http_config.get_effective_ssl_verify(platform),
                                proxy_address=proxy_address,
                            )

                            # 录制状态登记只给 ffmpeg 路径（强制直下在确认拿到 flv_url 后再登记）：
                            # 无条件 add 会让「未找到 FLV」分支留下幽灵条目（磁盘满判定恒假、
                            # 字幕线程永不退出且每轮再起一条）。
                            only_flv_record = False
                            only_flv_platform_list = ["shopee", "花椒直播"]
                            if platform in only_flv_platform_list:
                                logger.debug(i18n.tr("提示: {platform} 将强制使用FLV格式录制", platform=platform))
                                only_flv_record = True

                            if not only_flv_record:
                                with record_state_lock:
                                    recording.add(record_name)
                                    start_record_time = datetime.datetime.now()
                                    actual_quality_value = port_info.get("actual_quality")
                                    actual_quality_code: str | None = (
                                        actual_quality_value if isinstance(actual_quality_value, str) else None
                                    )
                                    actual_quality_zh = code_to_zh(actual_quality_code) if actual_quality_code else ""
                                    if actual_quality_code and _is_downgrade(record_quality, actual_quality_code):
                                        logger.warning(
                                            i18n.tr(
                                                "{record_name} 画质降级：设置 {record_quality_zh}({record_quality})"
                                                " 实际 {actual_quality_zh}({actual_quality_code})",
                                                record_name=record_name,
                                                record_quality_zh=record_quality_zh,
                                                record_quality=record_quality,
                                                actual_quality_zh=actual_quality_zh,
                                                actual_quality_code=actual_quality_code,
                                            )
                                        )
                                    recording_time_list[record_name] = [
                                        start_record_time,
                                        record_quality_zh,
                                        actual_quality_zh,
                                    ]
                            # 只保留可插值的原始字段，打印点各自 tr 插值：含自然语言的 f-string
                            # 若先提到变量再 print，i18n 提取器扫不到。
                            rec_info_anchor_name = anchor_name
                            rec_info_full_path = full_path
                            if show_url:
                                re_plat = ("WinkTV", "PandaTV", "ShowRoom", "CHZZK", "YouTube")
                                # 直播源地址带签名参数（wsSecret/txSecret/ttwid 等），入 PlayURL.log /
                                # streamget.log 前必须脱敏（轮转文件会长期保留）。占位符名沿用目录既有。
                                if platform in re_plat:
                                    logger.info(
                                        i18n.tr(
                                            "{platform} | {anchor_name} | 直播源地址: {m3u8_url}",
                                            platform=platform,
                                            anchor_name=anchor_name,
                                            m3u8_url=utils.mask_credentials(str(port_info.get("m3u8_url") or "")),
                                        )
                                    )
                                else:
                                    logger.info(
                                        i18n.tr(
                                            "{platform} | {anchor_name} | 直播源地址: {real_url}",
                                            platform=platform,
                                            anchor_name=anchor_name,
                                            real_url=utils.mask_credentials(real_url),
                                        )
                                    )

                            only_audio_record = False
                            only_audio_platform_list = ["猫耳FM直播", "Look直播"]
                            if platform in only_audio_platform_list:
                                only_audio_record = True

                            record_save_type = video_save_type

                            if real_url == port_info.get("flv_url") and port_info.get("flv_url"):
                                codec = utils.get_query_params(cast(str, port_info["flv_url"]), "codec")
                                # TS/MKV/MP4 已放行 h265 直拷（stream_select._h265_copy_format_supported），
                                # 只在当前容器装不下 HEVC 时才转 TS，避免 TS 用户每轮收到误导性告警。
                                if (
                                    isinstance(codec, list)
                                    and bool(codec)
                                    and codec[0] == "h265"
                                    and record_save_type.upper() not in ("TS", "MKV", "MP4")
                                ):
                                    # loguru sink 不经过 builtins.print 包装，裸英文串必须包 tr()，
                                    # 否则非简中下原样输出（四语译文早已存在，只是没查表）。
                                    logger.warning(
                                        i18n.tr("FLV is not supported for h265 codec, use TS format instead")
                                    )
                                    record_save_type = "TS"

                            if only_audio_record or any(i in record_save_type for i in ["MP3", "M4A"]):
                                # 扩展名/路径/执行骨架统一走既有实现：编码器与容器的裁决在
                                # _build_ffmpeg_output_args 内部按同一条件完成，无需二次分叉。
                                save_file_path = _build_record_output_path(
                                    full_path,
                                    anchor_name,
                                    title_in_name,
                                    now,
                                    record_save_type,
                                    split_video_by_time,
                                    is_audio=True,
                                )
                                if split_video_by_time:
                                    print(
                                        i18n.tr(
                                            "\r{anchor_name} 准备开始录制音频: {save_file_path}",
                                            anchor_name=anchor_name,
                                            save_file_path=save_file_path,
                                        )
                                    )
                                ffmpeg_command.extend(
                                    _build_ffmpeg_output_args(
                                        save_file_path, record_save_type, split_video_by_time, split_time, is_audio=True
                                    )
                                )
                                started, comment_end = _run_ffmpeg_record(
                                    record_name,
                                    record_url,
                                    record_host,
                                    ffmpeg_command,
                                    record_save_type,
                                    custom_script,
                                    platform,
                                    record_danmaku_args,
                                )
                                if started:
                                    # 触发「录后 30s 快检」，与直下路径对齐：下播速重开不必等一整轮
                                    record_finished = True
                                if comment_end:
                                    return

                            elif only_flv_record:
                                logger.info(
                                    i18n.tr(
                                        "Use Direct Downloader to Download FLV Stream: {record_url}",
                                        # 地址可能是带 user:pass@ 的自定义流，INFO 级会进 PlayURL.log
                                        record_url=utils.mask_credentials(record_url),
                                    )
                                )
                                # 与视频分支同构拼接：title_in_name 为空时不会产生双下划线
                                filename = f"{anchor_name}_{title_in_name}{now}_00.flv"
                                save_file_path = f"{full_path}/{filename}"
                                print(
                                    i18n.tr(
                                        "\r{anchor_name} 准备开始录制视频: {full_path}/{filename}",
                                        anchor_name=rec_info_anchor_name,
                                        full_path=rec_info_full_path,
                                        filename=filename,
                                    )
                                )

                                subs_file_path = save_file_path.rsplit(".", maxsplit=1)[0]
                                subs_thread_name = f"subs_{Path(subs_file_path).name}"

                                try:
                                    flv_url = port_info.get("flv_url")
                                    if isinstance(flv_url, str) and flv_url:
                                        # 录制状态登记必须在字幕线程之前：generate_subtitles 的唯一退出
                                        # 条件是 record_name 移出 recording，登记晚于线程启动会出现
                                        # 「线程已跑、recording 里还没有」的窗口（下载抛错后字幕空转）。
                                        # 登记是纯内存操作、无失败路径，先持锁写状态再起线程与下载。
                                        with record_state_lock:
                                            recording.add(record_name)
                                            start_record_time = datetime.datetime.now()
                                            actual_quality_value = port_info.get("actual_quality")
                                            actual_quality_code = (
                                                actual_quality_value if isinstance(actual_quality_value, str) else None
                                            )
                                            actual_quality_zh = (
                                                code_to_zh(actual_quality_code) if actual_quality_code else ""
                                            )
                                            if actual_quality_code and _is_downgrade(
                                                record_quality, actual_quality_code
                                            ):
                                                logger.warning(
                                                    # 与 ffmpeg 分支复用同一 msgid：两条路径都要在画质被
                                                    # 服务端钳制时告警，避免重复登记翻译串
                                                    i18n.tr(
                                                        "{record_name} 画质降级：设置 {record_quality_zh}({record_quality})"
                                                        " 实际 {actual_quality_zh}({actual_quality_code})",
                                                        record_name=record_name,
                                                        record_quality_zh=record_quality_zh,
                                                        record_quality=record_quality,
                                                        actual_quality_zh=actual_quality_zh,
                                                        actual_quality_code=actual_quality_code,
                                                    )
                                                )
                                            recording_time_list[record_name] = [
                                                start_record_time,
                                                record_quality_zh,
                                                actual_quality_zh,
                                            ]

                                        # 字幕线程只在 flv_url 校验通过后启动（与 ffmpeg 路径「先起录制
                                        # 再起字幕」对齐）；线程结束从 create_var 清理自身条目，否则
                                        # 常驻模式下每轮都泄漏一条。
                                        if create_time_file:

                                            def _subtitle_thread_target_direct() -> None:
                                                try:
                                                    generate_subtitles(record_name, subs_file_path)
                                                finally:
                                                    with record_state_lock:
                                                        # 只在登记的仍是本线程时回收
                                                        if (
                                                            create_var.get(subs_thread_name)
                                                            is threading.current_thread()
                                                        ):
                                                            create_var.pop(subs_thread_name, None)

                                            # 写入与 start() 一并收进锁，防止与别的线程的 finally pop
                                            # 交错；start() 抛错时 target 不运行，失败即回滚登记。
                                            with record_state_lock:
                                                create_var[subs_thread_name] = threading.Thread(
                                                    target=_subtitle_thread_target_direct,
                                                    name=subs_thread_name,
                                                    daemon=True,
                                                )
                                                try:
                                                    create_var[subs_thread_name].start()
                                                except RuntimeError:
                                                    create_var.pop(subs_thread_name, None)

                                        download_success = direct_download_stream(
                                            flv_url,
                                            save_file_path,
                                            record_name,
                                            record_url,
                                            platform,
                                            cookies=platform_cookie,
                                        )

                                        if download_success:
                                            record_finished = True
                                            print(
                                                i18n.tr(
                                                    "\n{anchor_name} {strftime} 直播录制完成\n",
                                                    anchor_name=anchor_name,
                                                    strftime=time.strftime("%Y-%m-%d %H:%M:%S"),
                                                )
                                            )
                                            # 直下路径无退出码反馈：成功按 host 补样本，与 ffmpeg 路径对齐
                                            record_success(record_host)
                                        elif (
                                            record_url not in url_comments and not exit_recording and recording_enabled
                                        ):
                                            # 真失败（非 200 / 网络异常已在函数内消化成 False）必须在此
                                            # 上报，否则坏线路绕开熔断统计；被注释/退出/停止不算样本。
                                            record_error(record_host)

                                        # 统一走 clear_record_info：它还会在 URL 被注释时移出 running_list、
                                        # 递减 monitoring。该函数自带非重入锁，此处不得再包一层 with。
                                        clear_record_info(record_name, record_url)
                                    else:
                                        # 未拿到 flv_url 也必须回收状态：否则幽灵条目会让字幕线程
                                        # 永不退出（shopee/花椒只回 m3u8、游客态、下播瞬间都会命中）。
                                        logger.debug(i18n.tr("未找到FLV直播流，跳过录制"))
                                        clear_record_info(record_name, record_url)
                                except Exception as e:
                                    clear_record_info(record_name, record_url)
                                    color_obj.print_colored(
                                        # 用 tr 预格式化后整体传入：f-string 直传 print_colored 时提取器扫不到
                                        i18n.tr(
                                            "\n{anchor_name} {strftime} 直播录制出错,请检查网络\n",
                                            anchor_name=anchor_name,
                                            strftime=time.strftime("%Y-%m-%d %H:%M:%S"),
                                        ),
                                        color_obj.RED,
                                    )
                                    logger.error(
                                        i18n.tr(
                                            "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                                            type_name=type(e).__name__,
                                            e=e,
                                            get_error_line=_get_error_line(e),
                                        )
                                    )
                                    record_error(record_host)

                            elif record_save_type in ("FLV", "MKV", "MP4"):
                                # FLV/MKV/MP4 三条分支的路径、命令与执行骨架完全一致，差异在
                                # 两个 _build_* 函数内部按保存类型查表，故合并为一条。
                                save_file_path = _build_record_output_path(
                                    full_path, anchor_name, title_in_name, now, record_save_type, split_video_by_time
                                )
                                print(
                                    i18n.tr(
                                        "\r{anchor_name} 准备开始录制视频: {full_path}/{filename}",
                                        anchor_name=rec_info_anchor_name,
                                        full_path=rec_info_full_path,
                                        filename=os.path.basename(save_file_path),
                                    )
                                )
                                ffmpeg_command.extend(
                                    _build_ffmpeg_output_args(
                                        save_file_path, record_save_type, split_video_by_time, split_time
                                    )
                                )
                                started, comment_end = _run_ffmpeg_record(
                                    record_name,
                                    record_url,
                                    record_host,
                                    ffmpeg_command,
                                    record_save_type,
                                    custom_script,
                                    platform,
                                    record_danmaku_args,
                                )
                                if started:
                                    # 触发「录后 30s 快检」：下播速重开不必等一整轮
                                    record_finished = True
                                # 转码必须在 comment_end 早退之前发起：否则「被注释/停止录制」
                                # 提前结束会直接 return，已录到的 .flv 静默丢失。
                                # 仅 FLV 需要转码（MKV/MP4 已是成品容器），且必须 started——
                                # ffmpeg 根本没起来时提交转码只会用转码错误盖住真实原因。
                                # 复核：FLV + comment_end 调 _convert_after_record，MKV/MP4 不调。
                                _convert_if_flv = started and record_save_type == "FLV"
                                if comment_end:
                                    if _convert_if_flv:
                                        _convert_after_record(save_file_path, split_video_by_time)
                                    return
                                if _convert_if_flv:
                                    _convert_after_record(save_file_path, split_video_by_time)

                            else:
                                # 默认 TS（record_save_type == "TS" 或未知值）
                                save_file_path = _build_record_output_path(
                                    full_path, anchor_name, title_in_name, now, record_save_type, split_video_by_time
                                )
                                print(
                                    i18n.tr(
                                        "\r{anchor_name} 准备开始录制视频: {full_path}/{filename}",
                                        anchor_name=rec_info_anchor_name,
                                        full_path=rec_info_full_path,
                                        filename=os.path.basename(save_file_path),
                                    )
                                )
                                ffmpeg_command.extend(
                                    _build_ffmpeg_output_args(
                                        save_file_path, record_save_type, split_video_by_time, split_time
                                    )
                                )
                                started, comment_end = _run_ffmpeg_record(
                                    record_name,
                                    record_url,
                                    record_host,
                                    ffmpeg_command,
                                    record_save_type,
                                    custom_script,
                                    platform,
                                    record_danmaku_args,
                                )
                                if started:
                                    record_finished = True
                                if comment_end:
                                    # 提前结束走不到 rc==0 的转码分支，在此补转已录到的部分；
                                    # _convert_after_record 内部会先检查用户是否开启转码。
                                    _convert_after_record(save_file_path, split_video_by_time)
                                    return

                            count_time = time.time()
                            # 样本由各录制路径按实际结果上报；轮末无条件记成功会稀释按 host 的
                            # 熔断统计（失败轮也变成功），坏线路永远撞不到阈值。

                except Exception as e:
                    logger.error(
                        i18n.tr(
                            "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                            type_name=type(e).__name__,
                            e=e,
                            get_error_line=_get_error_line(e),
                        )
                    )
                    record_error(record_host)

                num = random.randint(-5, 5) + delay_default
                if num < 0:
                    num = 0
                x = num

                if sum(error_window) >= 5:
                    x = x + 60
                    color_obj.print_colored("\r瞬时错误太多,延迟加60秒", color_obj.YELLOW)

                # 录制结束后 30 秒内快速复检一次，减少卡顿/短暂重开造成的漏录，之后回归配置间隔
                if record_finished:
                    count_time_end = time.time() - count_time
                    if count_time_end < 60:
                        x = 30
                    record_finished = False
                # 不要在此把 x 重置回 num：那会让上面的 +60s 退避永远不生效

                # 逐秒递减等待，三信号（URL 被注释 / 退出标志 / 停止录制）任一命中即打断，
                # 立即回到循环顶；只查 recording_enabled 会让线程耗完整个周期才响应。
                while x:
                    if record_url in url_comments or exit_recording or not recording_enabled:
                        break
                    x = x - 1
                    if loop_time:
                        print(i18n.tr("\r{anchor_name}循环等待{x}秒 ", anchor_name=anchor_name, x=x), end="")
                    time.sleep(1)
                if loop_time:
                    print("\r检测直播间中...", end="")
        except Exception as e:
            logger.error(
                i18n.tr(
                    "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                    type_name=type(e).__name__,
                    e=e,
                    get_error_line=_get_error_line(e),
                )
            )
            record_error(record_host)
            time.sleep(2)
        finally:
            # 本 finally 与 while True 同层，每轮都会执行：不能在此调 room_stopped，
            # 否则每轮都会把房间弹出枢纽、写一条假的「停止监控」事件。真正的清理时机是
            # 线程退出，故只回传本轮录制名，由 _room_thread_target 的 finally 调一次。
            if room_state is not None and record_name:
                room_state["name"] = record_name


# 打印 ffmpeg 版本并检测可用性（缺失时触发下载安装）；返回是否可用
def check_ffmpeg_existence() -> bool:
    ffmpeg_exists = False
    try:
        # text=True 按 locale 解码（中文 Windows 是 cp936），版本行出现非 GBK 字节会抛
        # UnicodeDecodeError（不属 OSError，会穿透成启动期崩溃）；errors="replace" 保证解码不失败。
        # timeout=15：-version 是秒级命令，ffmpeg 挂起（杀软锁文件/坏包装的假二进制）时
        # 无上限会阻塞整个启动入口。TimeoutExpired 与 CalledProcessError 同组处理。
        result = subprocess.run(
            ["ffmpeg", "-version"],
            check=True,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
        )
        # check=True 已保证 returncode==0，直接打印版本信息
        lines = result.stdout.splitlines()
        version_line = lines[0] if lines else "unknown"
        built_line = lines[1] if len(lines) > 1 else ""
        print(version_line)
        if built_line:
            print(built_line)
    # 需 as 绑定，按 AGENTS except 约定回退加括号形态。
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        # 带 type_name：CalledProcessError 的 str 可能为空或语义不明。TimeoutExpired 并入同组
        # （本函数新增 timeout 后它不再是被 check=True 排除的形态）。
        logger.error(
            i18n.tr(
                "ffmpeg 版本检查命令执行失败: {type_name}: {e}",
                type_name=type(e).__name__,
                e=e,
            )
        )
    except FileNotFoundError:
        pass
    if check_ffmpeg():
        ffmpeg_exists = True
    return ffmpeg_exists


# --------------------------初始化程序-------------------------------------
# i18n 必须先于 banner 的 tr 导入（模块级顺序执行）；此时仍是默认 zh_CN 目录，
# banner 保持中文原文，与「banner 先于语言解析打印」的既有行为一致。
import i18n

print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(i18n.tr("版本号: {version}", version=version))
print("GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(i18n.tr("支持平台: {platforms}", platforms=platforms))
print(".....................................................")
# 模块级不执行 check_ffmpeg_existence()：import main（web.py/gui.py/测试）不应触发
# FFmpeg 下载副作用；安装检查统一由各真实入口的 main() 完成。
os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()
# URL_config.ini 去重已移入 main() 入口执行：import main 不应改写用户配置文件


# 布尔配置统一经 src.config_io.read_config_bool：识别 是/否、true/false、1/0、yes/no、on/off
# （大小写不敏感）。不要退回「是/否」字典查表：其余写法会静默落到兜底实参，
# 实测曾致 8 项配置漂移（含「跳过代理检测 = true」被判 False，9 个海外平台无法录制）。
config: configparser.RawConfigParser = tolerant_config_parser()


config.read(config_file, encoding=text_encoding)

# 重复键点名：容错解析器会把重复项折叠成最后一次取值（strict 解析器则会抛
# DuplicateOptionError，曾有「import 即崩」事故），必须把折叠位置说出来，否则无从归因。
warn_duplicate_options(config_file, text_encoding)


# 把 config.ini 解析进全新的 RawConfigParser 并整体替换模块全局；返回是否替换。
# 两处保守条件缺一不可：① 解析失败/打不开时保留内存态（否则瞬时失败会把所有键按缺键
# 写回默认值，等于抹平用户配置）；② 结果为空时不替换，避免清成零键触发自愈补写。
# 与录制线程的写入统一由 file_update_lock（RLock）互斥。
def _hot_reload_config() -> bool:
    global config
    # 用容错解析器：否则遇到重复键会走 except 保留旧配置，用户改的键永远读不到
    fresh = tolerant_config_parser()
    try:
        with file_update_lock:
            with open(config_file, "r", encoding=text_encoding) as fp:
                fresh.read_file(fp)
            if not fresh.sections():
                return False
            config = fresh
        warn_duplicate_options(config_file, text_encoding)
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        # 只记一行、保留旧配置：热加载失败不得中断录制主循环，也不得清空内存态
        logger.warning(i18n.tr("发生 I/O 或配置解析错误: {err}", err=f"{type(e).__name__}: {e}"))
        return False
    return True


# 读取 language 原始值；空 → 跟随系统语言，不可识别/目录缺失由 i18n.resolve_language 兜底。
def _read_language_config(config_parser: configparser.RawConfigParser) -> str:
    return read_config_value(config_parser, "录制设置", "language", "")


language = _read_language_config(config)

# i18n 初始化：空 → 系统语言；不可识别/目录缺失 → en_US；随后加载翻译目录并即时生效。
from i18n import resolve_language as _i18n_resolve
from i18n import set_language as _i18n_set_language

language = _i18n_resolve(language)
_i18n_set_language(language)
skip_proxy_check = read_config_bool(config, "录制设置", "是否跳过代理检测(是/否)", False)


def _read_https_recording_config(config_parser: configparser.RawConfigParser) -> bool:
    # 三级继承：新键存在直接取值；否则旧键「是否强制启用https录制」存在则继承并写回新键
    # （旧键只读、不重建）；两者皆无则由 read_config_value 补写默认「否」。
    # 统一走 read_config_bool，避免 true 被静默判成「否」。
    if config_parser.has_option("录制设置", "是否启用https录制"):
        return read_config_bool(config_parser, "录制设置", "是否启用https录制", False)
    if config_parser.has_option("录制设置", "是否强制启用https录制"):
        legacy = read_config_bool(config_parser, "录制设置", "是否强制启用https录制", False)
        return read_config_bool(config_parser, "录制设置", "是否启用https录制", legacy)
    return read_config_bool(config_parser, "录制设置", "是否启用https录制", False)


# SSL/HTTPS 整合开关（合并原「强制启用 https」与「禁用 SSL 证书验证」两项）：
# 开启 = 流地址 http→https 升级（语义只落在 start_record 的协议改写一处）；关闭 = 降级 http。
# 本开关**不再**联动拉流侧证书校验：SSL_DISABLE_REQUIRED_PLATFORMS / 用户名单是拉流侧免检的
# 唯一入口（名单内平台按 get_effective_ssl_verify(platform) 返回 False，名单外一律严格校验）；
# 控制面（登录/取 Cookie/推送/平台 API，http_config.ssl_verify）恒严格校验，拉流开关不得顺带关掉全站 TLS。
# main() 每轮读取后同步，支持热更新。相关判据的用例在 tests/test_http_config.py
# （拉流侧豁免范围 + 控制面不受联动）；
# main 侧「热更新轮次不得按开关联动 set_https_recording」这条尚无独立回归锁。
from src import http_config as _http_config

enable_https_recording = _read_https_recording_config(config)
# 显式落严格校验基线：豁免名单随后经 _apply_ssl_platform_exempt 逐平台生效。
# [历史注] 原实现开开关时在此调 _http_config.set_https_recording(True) 把 stream_ssl_verify
# 全局置 False——为绕虎牙 CDN 证书问题会让抖音/B站/YouTube 的**全部**拉流都不校验证书
# （可被中间人劫持），而真正带证书问题的只有豁免名单里的平台。
_http_config.set_https_recording(False)
# 旧全局开关仅作迁移提示（只读，不写回）：检测到旧键=是 时告知功能已并入新开关
if config.has_option("录制设置", "是否禁用SSL证书验证(是/否)"):
    if read_config_bool(config, "录制设置", "是否禁用SSL证书验证(是/否)", False):
        print("提示: 「是否禁用SSL证书验证(是/否)」已整合进「是否启用https录制」，旧配置项不再生效")
# 平台级 SSL 豁免列表：FFmpeg 9.0 起默认校验证书，http 模式下 https-only 源也会被校验；
# 该列表经 http_config.get_effective_ssl_verify 生效（仅在控制面仍需校验时）。
# 虎牙：hw/TX CDN 证书与拉流域名不匹配，严格校验直接失败；B站：部分节点证书链异常。
# 启动时自动追加缺失项，只追加、不移除用户手填的平台。
SSL_DISABLE_REQUIRED_PLATFORMS: tuple[str, ...] = ("虎牙直播", "B站直播")


# 解析「禁用SSL证书验证的平台」并自动追加必需项；返回合并后的集合
def _sync_ssl_disable_platforms(config_parser: configparser.RawConfigParser) -> set[str]:
    # 读取现值（键缺失时 read_config_value 会补写空默认值，保证键存在）
    raw = read_config_value(config_parser, "录制设置", "禁用SSL证书验证的平台(逗号分隔)", "")
    kept = [p.strip() for p in raw.replace("，", ",").split(",") if p.strip()]
    appended = [p for p in SSL_DISABLE_REQUIRED_PLATFORMS if p not in kept]
    if appended:
        merged = kept + appended
        new_value = ",".join(merged)
        # 行级写回（保留注释与其他键；大小写不敏感匹配文件行）
        from src.web_config import update_config_line

        if not update_config_line(config_file, "录制设置", "禁用SSL证书验证的平台(逗号分隔)", new_value):
            logger.warning(
                i18n.tr(
                    "自动追加需禁用SSL验证的平台 {appended} 写回配置失败（已忽略，内存态仍生效）", appended=appended
                )
            )
        # 同步内存解析器，避免本轮后续读取拿到旧值
        config_parser.set("录制设置", "禁用SSL证书验证的平台(逗号分隔)", new_value)
        print(i18n.tr("提示: 已自动追加需禁用SSL证书验证的平台: {appended}", appended=",".join(appended)))
    return set(kept + appended)


# 解析平台豁免并落到 http_config（幂等、只追加不移除）；两个调用点共用：
# 模块 import 首启，以及 main() 在配置值变化时重跑。返回本次生效的平台集合。
def _apply_ssl_platform_exempt(config_parser: configparser.RawConfigParser) -> set[str]:
    platforms = _sync_ssl_disable_platforms(config_parser)
    # 旧单列配置兼容：仅当旧键存在时读取，绝不写回（自动重建旧键会触发「缺键→写回→崩溃」）。
    if config_parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
        if read_config_bool(config_parser, "录制设置", "虎牙是否禁用SSL证书验证(是/否)", False):
            platforms.add("虎牙直播")
    # 名单内平台显式置 False；名单**外**的平台显式复位 True。不补后一步时，热加载把某平台
    # 从名单里删掉后，http_config 里那条 False 覆盖会永远留着——名单就不再是唯一入口了。
    for _p in sorted(platforms):
        _http_config.set_platform_ssl_verify(_p, False)
    for _p in sorted(set(_http_config.ssl_verify_platform_overrides) - platforms):
        _http_config.set_platform_ssl_verify(_p, True)
    return platforms


_ssl_disable_platforms = _apply_ssl_platform_exempt(config)
# 热加载时判定「禁用SSL证书验证的平台」是否变化，初值取 import 时的内存态
_last_ssl_disable_platforms_raw = ",".join(sorted(_ssl_disable_platforms))
# 主循环是否已按名单落地过一次平台覆盖（名单是拉流侧免检的唯一入口，首轮必须跑）
_ssl_exempt_applied = False
# translated_print 在所有语言下安装：中英互译，未知串恒等返回；语言经 set_language 热切换。
from i18n import translated_print

builtins.print = translated_print  # type: ignore[assignment]

try:
    if skip_proxy_check:
        global_proxy = True
    else:
        # 通过本地系统代理配置检测（读取注册表/环境变量），避免联网探测导致的卡顿
        pd = ProxyDetector()
        global_proxy = pd.is_proxy_enabled()
        if global_proxy:
            proxy_info = pd.get_proxy_info()
            print("System Proxy: http://{}:{}".format(proxy_info.ip, proxy_info.port))
except Exception as err:
    print("An unexpected error occurred:", err)


# 程序主入口（CLI 直跑与 web.py 守护线程共用）：校验 ffmpeg 后死循环「热加载 config.ini →
# 检查磁盘余量 → 解析清理 URL_config.ini → 为新增房间拉起 start_record 线程」。
# non_interactive=True 时 URL 配置为空不阻塞 input（Web 模式）。
def main(non_interactive: bool = False) -> None:
    global a, acfun_cookie, args, auto_update_anchor_name, baidu_cookie, bark_msg_api, bark_msg_level, bark_msg_ring, begin_push_message_text, begin_show_push, bigo_cookie, bili_cookie, blued_cookie
    global changliao_cookie, chzzk_cookie, clean_emoji, converts_to_h264, converts_to_mp4, create_time_file, custom_script, delay_default, delete_origin_file, dingtalk_api_url, danmaku_platforms, danmaku_split_time, enable_danmaku, enable_danmaku_monitor
    global dingtalk_is_atall, dingtalk_phone_num, disable_record, disk_free_gb, disk_limited, disk_space_limit, douyu_cookie, dy_cookie, email_host, email_password, enable_https_recording, enable_proxy_platform, enable_proxy_platform_list, exit_recording
    global extra_enable_proxy, extra_enable_proxy_platform_list, faceit_cookie, filename_by_title, first_run, first_start, flextv_cookie, flextv_password, flextv_username, folder_by_author, folder_by_time, folder_by_title
    global haixiu_cookie, hls_collection_enabled, hls_collection_exclude_platforms, huajiao_cookie, huamao_cookie, hy_cookie, ini_URL_content, input_url, is_comment_line, is_run_script, jd_cookie, ks_cookie, kugou_cookie
    global laixiu_cookie, langlive_cookie, language, lehaitv_cookie, lianjie_cookie, line, line_spilt, liuxing_cookie, live_status_push, liveme_cookie, local_delay_default, login_email
    global look_cookie, loop_time, maoerfm_cookie, max_request, middle, migu_cookie, monitoring, name, netease_cookie, new_line, new_url, new_word
    global ntfy_api, ntfy_email, ntfy_tags, open_smtp_ssl, origin_line, over_push_message_text, over_show_push, pandatv_cookie, picarto_cookie, popkontv_access_token, popkontv_partner_code, popkontv_password
    global popkontv_username, pplive_cookie, proxy_addr, proxy_addr_bak, push_check_seconds, push_message_title, pushplus_token, qiandurebo_cookie, quality, replace_words, running_snapshot, running_url
    global semaphore, sender_email, sender_name, shopee_cookie, show_url, showroom_cookie, six_room_cookie, smtp_port, sooplive_cookie, sooplive_password, sooplive_username
    global scheduler, recording_semaphore
    # 热加载写回的两个全局：单次录制时长上限、SSL 豁免平台的上一次原始值（用于变更判定）
    global max_record_seconds, _last_ssl_disable_platforms_raw
    global _ssl_exempt_applied
    global split_line, split_time, split_video_by_time, start_with, t, t2, taobao_cookie, text_no_repeat_url, tg_chat_id, tg_token, tiktok_cookie, to_email
    global twitcasting_account_type, twitcasting_cookie, twitcasting_password, twitcasting_username, twitch_cookie, url, url_comments, url_host, url_tuple, url_tuples_list, use_proxy
    global video_record_quality, video_save_path, video_save_type, video_save_type_list, vvxqiu_cookie, weibo_cookie, winktv_cookie, xhs_cookie, xizhi_api_url, yinbo_cookie, yingke_cookie, yiqilive_cookie
    global youtube_cookie, yy_cookie, zhihu_cookie

    # FFmpeg 网关放在 main() 入口：模块级 sys.exit(1) 会在 import main 时杀死 uvicorn。
    # 缺失时告警并 return，录制引擎线程干净退出而 Web 面板继续服务；CLI 也从这里退出，避免硬退。
    if not check_ffmpeg_existence():
        logger.error("缺少ffmpeg无法进行录制，程序退出")
        return

    # 启动时清理 URL_config.ini 重复行（原为模块级副作用，移入入口处执行）
    if os.path.isfile(url_config_file):
        utils.remove_duplicate_lines(url_config_file)

    # 默认下载目录在入口创建（模块 import 不再产生磁盘写入）；录制路径仍能看到目录已存在。
    try:
        os.makedirs(default_path, exist_ok=True)
    except OSError as e:
        # 建不出来不致命：录制侧会按 check_path 再建并报出真实原因，
        # 此处提前崩会把「无权限/磁盘满」变成启动失败。
        logger.debug(i18n.tr("创建默认下载目录失败: {type_name}: {e}", type_name=type(e).__name__, e=e))

    # 陈旧字节码缓存清理放在此而非模块顶部：src.* 已 import 完毕，本轮启动不受影响；
    # 只有源码/版本真的变化时下一次启动才付重编译成本。
    purge_stale_bytecode_caches(
        script_path, version, read_config_bool(config, "录制设置", "是否启动时清理陈旧字节码缓存(是/否)", True)
    )

    # 并发调度器在 while 前创建，确保 start_record 线程启动前 scheduler/semaphore 已就绪
    if scheduler is None:
        scheduler = ConcurrencyScheduler(configured_limit=max_request)
        semaphore = scheduler.network_semaphore
        recording_semaphore = scheduler.recording_semaphore

    # 序号源必须跨轮次存活：在 while 之外初始化后序号单调递增，_room_seq_in_use 记录「序号 → 使用者
    # 线程」，分配时跳过仍在存活的序号；线程退出时自行 pop（见 _room_thread_target 的 finally
    # 与 start 失败回滚分支）。
    # [历史注] 两个容器曾在每轮 try 内重新初始化，首轮拉起的房间下一轮会被新的「序号1」覆盖撞键。
    _count_source = 0
    _room_seq_in_use: dict[int, threading.Thread] = {}

    while True:

        try:
            if not os.path.isfile(config_file):
                # 新建配置文件也必须走 atomic_write_text：open(..., "w") 直接建文件会按 umask 落 0644，
                # 而 config.ini 含 Cookie/代理口令；原子写新建文件是 0600（utils.atomic_write_text 的
                # orig_mode 缺省）。两条创建路径权限不一致会让「收紧配置权限」只在部分场景成立。
                _ = utils.atomic_write_text(config_file, "", encoding=text_encoding)

            # 每轮热加载配置；持锁读取避免与录制线程的 update_config 读到半写文件。
            # 必须「读入全新解析器后整体替换」：RawConfigParser.read() 是合并语义，用户手删的键
            # 会永久保留旧值，缺键补写自愈也永不触发。保守条件见 _hot_reload_config。
            _ = _hot_reload_config()

            ini_URL_content = ""
            if os.path.isfile(url_config_file):
                # errors="ignore"：外部编辑器存成非 text_encoding 时 read() 会抛
                # UnicodeDecodeError（ValueError 子类），而本 try 只捕 EOFError/OSError/配置错误，
                # 异常会穿透主循环。与下方 readlines 处保持一致，避免把替换字符塞进 URL。
                with open(url_config_file, "r", encoding=text_encoding, errors="ignore") as file:
                    ini_URL_content = file.read().strip()

            if not ini_URL_content.strip():
                if non_interactive:
                    # 非交互模式：跳过阻塞等待 Web API 写入 URL；被中断时补固定退避，
                    # 否则 continue 会跳过循环末尾的 sleep(3)，退化成零延迟忙循环。
                    if _interruptible_sleep(5):
                        time.sleep(3)
                    continue
                input_url = input("请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n")
                # 新建 URL_config.ini 与 config.ini 同口径走 atomic_write_text：
                # 裸 open("w") 按 umask 落 0644，而该文件可含 user:pass@ 自定义流地址，
                # Linux/Docker 下新建即全局可读。
                _ = utils.atomic_write_text(url_config_file, input_url, encoding=text_encoding)
        except EOFError:
            # 无可用 stdin 时 input() 抛 EOFError（窗口化 / stdin 被重定向）：不能让它穿透，
            # 否则进程带栈退出（GUI 表现为「一点开始录制就没了」）。退化为轮询等待配置写入。
            logger.error(i18n.tr("无法从控制台读取直播间网址（无可用标准输入），等待配置文件写入"))
            # 同上：被中断时补退避
            if _interruptible_sleep(5):
                time.sleep(3)
            continue
        except (OSError, configparser.Error) as err:
            logger.error(i18n.tr("发生 I/O 或配置解析错误: {err}", err=err))
            _interruptible_sleep(3)

        video_save_path = read_config_value(config, "录制设置", "直播保存路径(不填则默认)", "")
        folder_by_author = read_config_bool(config, "录制设置", "保存文件夹是否以作者区分", True)
        folder_by_time = read_config_bool(config, "录制设置", "保存文件夹是否以时间区分", False)
        folder_by_title = read_config_bool(config, "录制设置", "保存文件夹是否以标题区分", False)
        filename_by_title = read_config_bool(config, "录制设置", "保存文件名是否包含标题", False)
        clean_emoji = read_config_bool(config, "录制设置", "是否去除名称中的表情符号", True)
        auto_update_anchor_name = read_config_bool(config, "录制设置", "是否自动更新主播名(是/否)", True)
        video_save_type = read_config_value(config, "录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
        video_record_quality = read_config_value(config, "录制设置", "原画|超清|高清|标清|流畅", "原画")
        hls_collection_enabled = read_config_bool(config, "录制设置", "是否启用HLS采集(是/否)", True)
        # HLS 采集排除平台：命中平台无视「是否启用HLS采集」配置、恒按 FLV 采集（select_source_url
        # 按平台名精确匹配）；支持中英文逗号分隔，热更新与 HLS 开关一致（每轮主循环重读）
        hls_exclude_platforms_str = read_config_value(config, "录制设置", "HLS采集排除平台(逗号分隔)", "")
        hls_collection_exclude_platforms = (
            [p.strip() for p in hls_exclude_platforms_str.replace("，", ",").split(",") if p.strip()]
            if hls_exclude_platforms_str
            else []
        )
        use_proxy = read_config_bool(config, "录制设置", "是否使用代理ip(是/否)", True)
        proxy_addr_bak = read_config_value(config, "录制设置", "代理地址", "")
        proxy_addr = None if not use_proxy else proxy_addr_bak
        # 仅在配置值变化时更新调度器：动态模式下它是容量下限之一，固定模式下即并发限制本身；
        # 不要每轮重建信号量（实例替换会让并发计数失效、上限形同虚设）
        new_max_request = _safe_int(read_config_value(config, "录制设置", "同一时间访问网络的线程数", 3), 3)
        if new_max_request != max_request:
            max_request = new_max_request
            if scheduler is not None:
                scheduler.set_configured_limit(new_max_request)
            logger.debug(i18n.tr("并发线程数配置更新为 {max_request}", max_request=max_request))
        # 录制并发软上限：0=不限制。键名不得含 = / : 等 configparser 分隔符——读取会在首个
        # 分隔符处截断、写回会抛 InvalidWriteError（曾有启动即崩事故）。
        new_recording_limit = _safe_int(read_config_value(config, "录制设置", "最大同时录制数(0为不限制)", 0), 0)
        if scheduler is not None and new_recording_limit != scheduler.recording_limit:
            scheduler.set_recording_limit(new_recording_limit)
        # 非 0 时忽略动态调速器，固定使用「同一时间访问网络的线程数」；0 时启用动态调速
        # （容量随活跃任务数缩放）。set_dynamic_mode 幂等，可每轮调用。
        if scheduler is not None:
            scheduler.set_dynamic_mode(new_recording_limit == 0)
        # 轮询类时间配置必须有下界：填 0/负数会让主循环与房间线程退化成无间隔轮询
        # （CPU 打满、平台接口被全速撞），日志上只是重复的「获取失败」。
        delay_default = max(30, _safe_int(read_config_value(config, "录制设置", "循环时间(秒)", 120), 120))
        # 排队读取网址的间隔语义上是 0 = 不等待，故只夹下界到 0，不允许负值
        local_delay_default = max(0, _safe_int(read_config_value(config, "录制设置", "排队读取网址时间(秒)", 0), 0))
        loop_time = read_config_bool(config, "录制设置", "是否显示循环秒数", False)
        show_url = read_config_bool(config, "录制设置", "是否显示直播源地址", False)
        # 语言热切换：配置变化时即时重载翻译目录（下轮生效，无需重启）；录制中的 ffmpeg 不受影响。
        _new_language = _i18n_resolve(read_config_value(config, "录制设置", "language", ""))
        if _new_language != language:
            language = _new_language
            _i18n_set_language(_new_language)
            print(i18n.tr("语言已切换: {_new_language}", _new_language=_new_language))
        split_video_by_time = read_config_bool(config, "录制设置", "分段录制是否开启", False)
        enable_https_recording = _read_https_recording_config(config)
        # 2026-10-21：**不得**在这里按开关联动 set_https_recording：那会关掉抖音/B站/YouTube 的全部拉流证书校验
        # （可被中间人劫持，理由见模块级 enable_https_recording 注释）。本开关在本轮只用于 start_record
        # 的 http→https 协议改写。SSL 豁免平台按「配置值变化时」重跑（与相邻 HLS/https 开关一样热生效）：
        # _sync_ssl_disable_platforms 幂等且只追加不删；重复设置同一 (平台, False) 亦幂等。
        # 名单是拉流侧免检的唯一入口，故首次进入循环也要跑一次（不能只在「变化时」跑：用户配置为空串时
        # 初值与本轮读值相等，名单外的平台将永远拿不到显式 True 复位）。
        _ssl_disable_raw = read_config_value(config, "录制设置", "禁用SSL证书验证的平台(逗号分隔)", "")
        if _ssl_disable_raw != _last_ssl_disable_platforms_raw or not _ssl_exempt_applied:
            _last_ssl_disable_platforms_raw = _ssl_disable_raw
            _ssl_exempt_applied = True
            _apply_ssl_platform_exempt(config)
        disk_space_limit = _safe_float(read_config_value(config, "录制设置", "录制空间剩余阈值(gb)", 1.0), 1.0)
        # 分段时间做数值归一：空值/非数字会进命令行（`-segment_time ""`）让 ffmpeg 秒退，
        # 又被误判成 CDN 快速失败；<=0 同样回落默认值。
        _split_time_raw = _safe_int(read_config_value(config, "录制设置", "视频分段时间(秒)", 1800), 1800)
        split_time = str(_split_time_raw if _split_time_raw > 0 else 1800)
        # 单次录制时长上限可配置（0 = 不限制）：24 小时轮播是常态，硬上限会每 6 小时
        # 制造一条失败样本并跳过转码/清退避。生效范围见 _MAX_RECORD_SECONDS 上方注释。
        _max_record_raw = _safe_int(
            read_config_value(config, "录制设置", "单次录制时长上限(秒,0为不限制)", _MAX_RECORD_SECONDS),
            _MAX_RECORD_SECONDS,
        )
        max_record_seconds = _max_record_raw if _max_record_raw > 0 else 0
        converts_to_mp4 = read_config_bool(config, "录制设置", "录制完成后自动转为mp4格式", False)
        converts_to_h264 = read_config_bool(config, "录制设置", "mp4格式重新编码为h264", False)
        delete_origin_file = read_config_bool(config, "录制设置", "追加格式后删除原文件", False)
        create_time_file = read_config_bool(config, "录制设置", "生成时间字幕文件", False)
        is_run_script = read_config_bool(config, "录制设置", "是否录制完成后执行自定义脚本", False)
        custom_script = read_config_value(config, "录制设置", "自定义脚本执行命令", "") if is_run_script else None
        enable_proxy_platform = read_config_value(
            config,
            "录制设置",
            "使用代理录制的平台(逗号分隔)",
            "tiktok, soop, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit",
        )
        enable_danmaku = read_config_bool(config, "录制设置", "是否录制弹幕(是/否)", False)
        enable_danmaku_monitor = read_config_bool(config, "录制设置", "是否弹幕监控(是/否)", False)
        danmaku_split_time = _safe_float(read_config_value(config, "录制设置", "弹幕分片时长(秒)", 1800), 1800.0)
        danmaku_platforms_str = read_config_value(
            config, "录制设置", "弹幕录制平台(逗号分隔)", "斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV"
        )
        # 分割后逐项 strip 并丢弃空项（与 HLS 排除平台同口径）：否则 "斗鱼直播, B站直播"
        # 会得到 " B站直播"，而匹配点按平台名精确比较 → 弹幕被静默关闭。
        danmaku_platforms = (
            [p.strip() for p in danmaku_platforms_str.replace("，", ",").split(",") if p.strip()]
            if danmaku_platforms_str
            else []
        )
        enable_proxy_platform_list = (
            enable_proxy_platform.replace("，", ",").split(",") if enable_proxy_platform else None
        )
        extra_enable_proxy = read_config_value(config, "录制设置", "额外使用代理录制的平台(逗号分隔)", "")
        extra_enable_proxy_platform_list = (
            extra_enable_proxy.replace("，", ",").split(",") if extra_enable_proxy else None
        )
        live_status_push = read_config_value(config, "推送配置", "直播状态推送渠道", "")
        dingtalk_api_url = read_config_value(config, "推送配置", "钉钉推送接口链接", "")
        xizhi_api_url = read_config_value(config, "推送配置", "微信推送接口链接", "")
        bark_msg_api = read_config_value(config, "推送配置", "bark推送接口链接", "")
        bark_msg_level = read_config_value(config, "推送配置", "bark推送中断级别", "active")
        bark_msg_ring = read_config_value(config, "推送配置", "bark推送铃声", "bell")
        dingtalk_phone_num = read_config_value(config, "推送配置", "钉钉通知@对象(填手机号)", "")
        dingtalk_is_atall = read_config_bool(config, "推送配置", "钉钉通知@全体(是/否)", False)
        tg_token = read_config_value(config, "推送配置", "tgapi令牌", "")
        tg_chat_id = read_config_value(config, "推送配置", "tg聊天id(个人或者群组id)", "")
        email_host = read_config_value(config, "推送配置", "SMTP邮件服务器", "")
        open_smtp_ssl = read_config_bool(config, "推送配置", "是否使用SMTP服务SSL加密(是/否)", True)
        smtp_port = read_config_value(config, "推送配置", "SMTP邮件服务器端口", "")
        login_email = read_config_value(config, "推送配置", "邮箱登录账号", "")
        email_password = read_config_value(config, "推送配置", "发件人密码(授权码)", "")
        sender_email = read_config_value(config, "推送配置", "发件人邮箱", "")
        sender_name = read_config_value(config, "推送配置", "发件人显示昵称", "")
        to_email = read_config_value(config, "推送配置", "收件人邮箱", "")
        ntfy_api = read_config_value(config, "推送配置", "ntfy推送地址", "")
        ntfy_tags = read_config_value(config, "推送配置", "ntfy推送标签", "tada")
        ntfy_email = read_config_value(config, "推送配置", "ntfy推送邮箱", "")
        pushplus_token = read_config_value(config, "推送配置", "pushplus推送token", "")
        push_message_title = read_config_value(config, "推送配置", "自定义推送标题", "直播间状态更新通知")
        begin_push_message_text = read_config_value(config, "推送配置", "自定义开播推送内容", "")
        over_push_message_text = read_config_value(config, "推送配置", "自定义关播推送内容", "")
        disable_record = read_config_bool(config, "推送配置", "只推送通知不录制(是/否)", False)
        # 推送检测频率同样夹下界：填 0 会让「只推送不录制」的逐秒等待立即穿透，
        # 房间线程变成全速解析 + 全速推送。
        push_check_seconds = max(
            30, _safe_int(read_config_value(config, "推送配置", "直播推送检测频率(秒)", 1800), 1800)
        )
        begin_show_push = read_config_bool(config, "推送配置", "开播推送开启(是/否)", True)
        over_show_push = read_config_bool(config, "推送配置", "关播推送开启(是/否)", False)
        sooplive_username = read_config_value(config, "账号密码", "sooplive账号", "")
        sooplive_password = read_config_value(config, "账号密码", "sooplive密码", "")
        flextv_username = read_config_value(config, "账号密码", "flextv账号", "")
        flextv_password = read_config_value(config, "账号密码", "flextv密码", "")
        popkontv_username = read_config_value(config, "账号密码", "popkontv账号", "")
        popkontv_partner_code = read_config_value(config, "账号密码", "partner_code", "P-00001")
        popkontv_password = read_config_value(config, "账号密码", "popkontv密码", "")
        twitcasting_account_type = read_config_value(config, "账号密码", "twitcasting账号类型", "normal")
        twitcasting_username = read_config_value(config, "账号密码", "twitcasting账号", "")
        twitcasting_password = read_config_value(config, "账号密码", "twitcasting密码", "")
        popkontv_access_token = read_config_value(config, "Authorization", "popkontv_token", "")
        dy_cookie = read_config_value(config, "Cookie", "抖音cookie", "")
        ks_cookie = read_config_value(config, "Cookie", "快手cookie", "")
        tiktok_cookie = read_config_value(config, "Cookie", "tiktok_cookie", "")
        hy_cookie = read_config_value(config, "Cookie", "虎牙cookie", "")
        douyu_cookie = read_config_value(config, "Cookie", "斗鱼cookie", "")
        yy_cookie = read_config_value(config, "Cookie", "yy_cookie", "")
        bili_cookie = read_config_value(config, "Cookie", "B站cookie", "")
        xhs_cookie = read_config_value(config, "Cookie", "小红书cookie", "")
        bigo_cookie = read_config_value(config, "Cookie", "bigo_cookie", "")
        blued_cookie = read_config_value(config, "Cookie", "blued_cookie", "")
        sooplive_cookie = read_config_value(config, "Cookie", "sooplive_cookie", "")
        netease_cookie = read_config_value(config, "Cookie", "netease_cookie", "")
        qiandurebo_cookie = read_config_value(config, "Cookie", "千度热播_cookie", "")
        pandatv_cookie = read_config_value(config, "Cookie", "pandatv_cookie", "")
        maoerfm_cookie = read_config_value(config, "Cookie", "猫耳fm_cookie", "")
        winktv_cookie = read_config_value(config, "Cookie", "winktv_cookie", "")
        flextv_cookie = read_config_value(config, "Cookie", "flextv_cookie", "")
        look_cookie = read_config_value(config, "Cookie", "look_cookie", "")
        twitcasting_cookie = read_config_value(config, "Cookie", "twitcasting_cookie", "")
        baidu_cookie = read_config_value(config, "Cookie", "baidu_cookie", "")
        weibo_cookie = read_config_value(config, "Cookie", "weibo_cookie", "")
        kugou_cookie = read_config_value(config, "Cookie", "kugou_cookie", "")
        twitch_cookie = read_config_value(config, "Cookie", "twitch_cookie", "")
        liveme_cookie = read_config_value(config, "Cookie", "liveme_cookie", "")
        huajiao_cookie = read_config_value(config, "Cookie", "huajiao_cookie", "")
        liuxing_cookie = read_config_value(config, "Cookie", "liuxing_cookie", "")
        showroom_cookie = read_config_value(config, "Cookie", "showroom_cookie", "")
        acfun_cookie = read_config_value(config, "Cookie", "acfun_cookie", "")
        changliao_cookie = read_config_value(config, "Cookie", "changliao_cookie", "")
        yinbo_cookie = read_config_value(config, "Cookie", "yinbo_cookie", "")
        yingke_cookie = read_config_value(config, "Cookie", "yingke_cookie", "")
        zhihu_cookie = read_config_value(config, "Cookie", "zhihu_cookie", "")
        chzzk_cookie = read_config_value(config, "Cookie", "chzzk_cookie", "")
        haixiu_cookie = read_config_value(config, "Cookie", "haixiu_cookie", "")
        vvxqiu_cookie = read_config_value(config, "Cookie", "vvxqiu_cookie", "")
        yiqilive_cookie = read_config_value(config, "Cookie", "17live_cookie", "")
        langlive_cookie = read_config_value(config, "Cookie", "langlive_cookie", "")
        pplive_cookie = read_config_value(config, "Cookie", "pplive_cookie", "")
        six_room_cookie = read_config_value(config, "Cookie", "6room_cookie", "")
        lehaitv_cookie = read_config_value(config, "Cookie", "lehaitv_cookie", "")
        huamao_cookie = read_config_value(config, "Cookie", "huamao_cookie", "")
        shopee_cookie = read_config_value(config, "Cookie", "shopee_cookie", "")
        youtube_cookie = read_config_value(config, "Cookie", "youtube_cookie", "")
        taobao_cookie = read_config_value(config, "Cookie", "taobao_cookie", "")
        jd_cookie = read_config_value(config, "Cookie", "jd_cookie", "")
        faceit_cookie = read_config_value(config, "Cookie", "faceit_cookie", "")
        migu_cookie = read_config_value(config, "Cookie", "migu_cookie", "")
        lianjie_cookie = read_config_value(config, "Cookie", "lianjie_cookie", "")
        laixiu_cookie = read_config_value(config, "Cookie", "laixiu_cookie", "")
        picarto_cookie = read_config_value(config, "Cookie", "picarto_cookie", "")

        video_save_type_list = ("FLV", "MKV", "TS", "MP4", "MP3音频", "M4A音频", "MP3", "M4A")
        if video_save_type and video_save_type.upper() in video_save_type_list:
            video_save_type = video_save_type.upper()
        else:
            video_save_type = "TS"

        check_path = video_save_path or default_path
        # 2026-10-21：检测失败时不得置 inf：inf 会让下方 `elif disk_limited` 命中并**解除暂停**——网络盘离线 /
        # 盘符拔出恰恰是「磁盘实际不可用」的时刻，此时恢复拉起 ffmpeg 只会让所有写入失败，并把失败
        # 样本喂给探针退避与平台熔断。故沿用上一轮的余量并置「本轮未取得测量」标记：无法测量不等于
        # 空间充足，暂停态保持原样、不放行新的拉起。
        _disk_measure_failed = False
        try:
            # 自定义保存路径可能尚不存在，shutil.disk_usage 会抛 FileNotFoundError
            os.makedirs(check_path, exist_ok=True)
            disk_free_gb = utils.check_disk_capacity(check_path, show=first_run)
        except Exception as e:
            _disk_measure_failed = True
            logger.warning(
                i18n.tr(
                    "磁盘空间检测失败（本轮沿用上次读数 {disk_free_gb} GB，不解除已有暂停）: {type_name}: {e}",
                    disk_free_gb=f"{disk_free_gb:.1f}",
                    type_name=type(e).__name__,
                    e=e,
                )
            )
        # 磁盘满只应是可逆暂停：exit_recording 全文件只在空间恢复分支复位，拿它表达
        # 资源约束会让「满过一次」之后永久不再拉起。故引入 disk_limited：进入限制时同步
        # 置位两者（房间线程据此停流），恢复时同步复位。
        # 只在状态跃迁时打日志（主循环每 3s 跑到这里）。
        # [历史注] 恢复判定另由 `not _disk_measure_failed` 兜住：检测失败不再置 inf，只看余量会误判。
        if disk_free_gb < disk_space_limit:
            if not disk_limited:
                disk_limited = True
                logger.warning(
                    i18n.tr(
                        "磁盘剩余空间低于 {disk_space_limit} GB，暂停拉起新录制并等待现有录制结束",
                        disk_space_limit=disk_space_limit,
                    )
                )
                exit_recording = True
                if not recording:
                    logger.warning(
                        i18n.tr(
                            "Disk space remaining is below {disk_space_limit} GB."
                            " Exiting program due to the disk space limit being reached.",
                            disk_space_limit=disk_space_limit,
                        )
                    )
                    # Web 模式下 main() 跑在 uvicorn 的守护线程里（web.py: recorder-engine）：
                    # sys.exit(-1) 只杀该线程，面板继续运行且用户看不到任何提示。
                    # 故 Web（non_interactive=True）置标志并 return；CLI/GUI 保留 sys.exit(-1)。
                    # 退出前先排空后处理池（理由见 _shutdown_postprocess_executor）。
                    _shutdown_postprocess_executor()
                    if non_interactive:
                        logger.warning("Web 模式：录制引擎已因磁盘空间不足停止，Web 面板继续服务")
                        return
                    sys.exit(-1)
        elif disk_limited and not _disk_measure_failed:
            # 空间恢复：两个标志一起复位。房间线程与主循环真正读的是 exit_recording，
            # 只清 disk_limited 等于暂停永不解除。本轮没测到余量时一律不解锁：沿用上一轮读数只是
            # 为了让「进入限制」一侧行为不变，恢复必须由一次**成功**的测量给出结论。
            disk_limited = False
            exit_recording = False
            logger.warning(
                i18n.tr(
                    "磁盘空间已恢复（剩余 {disk_free_gb} GB），解除录制暂停并继续按配置拉起房间",
                    disk_free_gb=disk_free_gb,
                )
            )

        try:
            # 集合只用于成员检测（set 保证 O(1)，避免 80+ 房间时 O(N²)）。
            # 解析过程先写局部集合，整轮成功后（本 try 末尾）再整体替换全局 url_comments：
            # 边解析边清空会让房间线程在窗口内把「刚注释掉的房间」判成未注释，
            # 中途抛错时全局集合还会停在半空状态。局部变量统一加下划线前缀。
            _url_comments: set[str] = set()
            _line_list: set[str] = set()
            _url_line_list: set[str] = set()
            _seen_urls: set[str] = set()
            # 本轮**被跳过**的行与其中已识别出的 URL。下方归并判据是「running 但不在 _seen_urls 且不在
            # _url_comments → 当作已注释」，而 _seen_urls 只在准入成功那一支填充：过短行 / 解析异常行里的
            # URL 从不在其中，归并就会把**正在进行的录制**判成已注释并强制停掉（表现为「录了一半自己停了，
            # 配置行一个字没变」）。被跳过的行既不证明被注释、也不证明被移除，必须豁免归并。
            _unparsed_lines: set[str] = set()
            _skipped_urls: set[str] = set()
            # monitoring 只由「拉起 +1 / 线程退出 -1」增量维护，没有「每轮重算」可依仗，启动前先与运行
            # 列表对齐（正常初值同为 0；Web 面板重启引擎时 running_list 可能非空）；漂移值会直接喂给
            # scheduler.set_active_count，自适应并发容量被错误压低。
            # 2026-10-21：序号必须来自单调源、且与房间绑定：取 len(running_list) 会让「线程退出后计数复用到同名主播」
            # 算出同一个「序号N 主播名」键，recording / recording_time_list 互相覆盖，clear_record_info
            # 与字幕线程会误清另一个房间的状态。用确定性哈希而非全局计数器，是为了让序号跨轮次稳定
            # （计数器在 running_list 清空后会从 1 重来，同样会撞上仍在收尾的线程留下的旧键）；序号源与
            # 「序号 → 使用者线程」表在 while 之外初始化（见 main() 循环头），此处不再每轮重置。
            with record_state_lock:
                monitoring = len(running_list)
            # 清空放在解析开始处：放在 try 尾部（拉起循环之后）时，中途抛错会留下旧条目，
            # 下一轮结果叠加其上形成幽灵拉起。拉起循环已先取快照，提前清空不影响本轮。
            url_tuples_list = []
            # 先 readlines 物化为 list 再迭代：循环体内会 truncate 重写整个 URL_config.ini，
            # 边读边写会漏读被截断的后半段；一次性物化也能把 N 次全文件读写降为一次。
            with open(url_config_file, "r", encoding=text_encoding, errors="ignore") as file:
                _url_lines = file.readlines()
            for origin_line in _url_lines:
                try:
                    if origin_line in _line_list:
                        # delete_line 返回 bool，失败时告警：丢弃返回值会让去重退化为永久
                        # no-op 且不可观测。`is False` 兼容返回 None 的旧实现（不误报）。
                        if delete_line(url_config_file, origin_line) is False:
                            logger.warning(
                                i18n.tr(
                                    "删除重复配置行失败: {origin_line}",
                                    origin_line=utils.mask_credentials(origin_line.strip()),
                                )
                            )
                    _line_list.add(origin_line)
                    line = origin_line.strip()
                    # 长度阈值只用于挡掉空行/纯标点行。阈值 18 会把合法短链（https://3.cn/xxx）
                    # 一并静默挡掉，而它与「解析失败」共用同一条无痕 continue，事后无从区分。
                    if len(line) < 18:
                        _unparsed_lines.add(origin_line)
                        continue

                    line_spilt = line.split("主播: ")
                    if len(line_spilt) > 2:
                        # 多段 "主播:" 时保留首尾，中间用空格连接，避免静默丢弃数据
                        middle = " ".join(line_spilt[1:-1])
                        line = (
                            update_file(url_config_file, line, f"{line_spilt[0]}主播: {middle} {line_spilt[-1]}")
                            or line
                        )

                    is_comment_line = line.startswith("#")
                    if is_comment_line:
                        line = line.lstrip("#")

                    if re.search("[,，]", line):
                        split_line = re.split("[,，]", line)
                    else:
                        split_line = [line, ""]

                    # 前两段为画质+URL、其余全部合并为主播名：直接解包在 >3 段时会抛 ValueError，
                    # 且异常不在行内捕获，会终止整个 for，坏行之后的房间永远处理不到。
                    if len(split_line) == 2:
                        if contains_url(split_line[0]):
                            quality = video_record_quality
                            url, name = split_line
                        else:
                            quality, url = split_line
                            name = ""
                    elif contains_url(split_line[0]):
                        # 3 段以上且首段是 URL：未写画质，第二段起全是主播名
                        quality = video_record_quality
                        url = split_line[0]
                        name = "，".join(split_line[1:])
                    else:
                        quality, url = split_line[0], split_line[1]
                        name = "，".join(split_line[2:])

                    if quality not in (
                        "原画",
                        "蓝光",
                        "蓝光4M",
                        "蓝光8M",
                        "蓝光20M",
                        "蓝光30M",
                        "超清",
                        "高清",
                        "标清",
                        "流畅",
                    ):
                        quality = "原画"

                    if url in _url_line_list:
                        # 同上：按返回值告警（URL 归一后重复，但文件里删不掉）
                        if delete_line(url_config_file, origin_line) is False:
                            logger.warning(
                                i18n.tr(
                                    "删除重复配置行失败: {origin_line}",
                                    origin_line=utils.mask_credentials(origin_line.strip()),
                                )
                            )
                    else:
                        _url_line_list.add(url)

                    url = "https://" + url if "://" not in url else url
                    # 2026-10-21：必须取 urlsplit().hostname 与分派侧（_match_host）
                    # 同口径。原用 url.split("/")[2]，带凭据地址（https://u:p@www.huya.com/123）得到的是
                    # "u:p@www.huya.com"，白名单恒不命中 → 被判「未知链接」并自动注释掉该行，而录制链
                    # 本身支持带凭据地址（只有 .flv/.m3u8 形态因下方扩展名放行能存活）。
                    url_host = urlsplit(url).hostname or ""

                    # _match_host 改按 DNS 标签边界比较后，shopee 各地区站
                    # （live.shopee.sg / s.shp.ee 等）不再命中两段片段，故准入侧把它们收敛到白名单的
                    # 两段条目再比对；分派侧片段是 live.shopee.co / shp.ee，两侧边界同一口径。
                    if "live.shopee." in url_host:
                        url_host = "live.shopee.co"
                    elif url_host == "shp.ee" or url_host.endswith(".shp.ee"):
                        url_host = "shp.ee"

                    # 准入与分派必须同一判据（_stream_path_suffix：按 path 取小写扩展名）：
                    # 整串包含会让 ?a=.flv 通过准入却落不到解析器，大小写敏感会误判 .M3U8。
                    if url_host in PLATFORM_HOST or _stream_path_suffix(url) in (".flv", ".m3u8"):
                        if url_host in CLEAN_URL_HOST_LIST:
                            url = update_file(url_config_file, old_str=url, new_str=url.split("?")[0]) or url

                        if url_host == "www.xiaohongshu.com":
                            # 统一走 spider.parse_xhs_live_url：它保留鉴权参数（xsec_token 等），
                            # 失败时保留原始地址交由解析侧报错，不在此注释整行。
                            # 短链不在此解跳转（准入阶段发网络请求会因抖动改写用户配置），
                            # 由 _resolve_xhslink_com 经 new_record_url 在首轮成功后回写。
                            try:
                                normalized = spider.parse_xhs_live_url(url)["normalized_url"]
                            except spider.XhsUrlError:
                                normalized = url
                            if normalized != url:
                                url = update_file(url_config_file, old_str=url, new_str=normalized) or url
                        _seen_urls.add(url)
                        # 精确 discard（O(1)）：子串匹配会误删以该 URL 为前缀的其它房间（.../1 与 .../12）
                        _url_comments.discard(url)
                        if is_comment_line:
                            _url_comments.add(url)
                        else:
                            new_line = (quality, url, name)
                            url_tuples_list.append(new_line)
                    else:
                        if not origin_line.startswith("#"):
                            # 常量模板 + tr 预格式化后整体传入：f-string 直传 print_colored 时
                            # i18n 提取器扫不到；第二参是颜色，不可传 kw。
                            color_obj.print_colored(
                                i18n.tr(
                                    "\r{line} 本行包含未知链接.此条跳过",
                                    line=utils.mask_credentials(origin_line.strip()),
                                ),
                                color_obj.YELLOW,
                            )
                            _ = update_file(url_config_file, old_str=origin_line, new_str=origin_line, start_str="#")

                except Exception as err:
                    # 单行脏数据不得中断整轮解析；报错须带该行内容与真实原因。
                    # 本行与行进 try 前登记（该行、以及原行里能认出的 URL）一并记进「被跳过」快照，
                    # 供下方归并整行豁免——解析异常不等于用户把这一行注释掉了。
                    _unparsed_lines.add(origin_line)
                    _skipped_url = _line_contains_url(origin_line.strip().lstrip("#").strip())
                    if _skipped_url:
                        _skipped_urls.add(_skipped_url)
                    logger.error(
                        i18n.tr(
                            "直播间配置行解析失败（已跳过该行）: {line} - {err}",
                            line=utils.mask_credentials(origin_line.strip()),
                            err=err,
                        )
                    )
                    continue
            while len(need_update_line_list):
                a = need_update_line_list.pop()
                replace_words = a.split("|")
                if replace_words[0] != replace_words[1]:
                    if replace_words[1].startswith("#"):
                        start_with = "#"
                        new_word = replace_words[1][1:]
                    else:
                        start_with = None
                        new_word = replace_words[1]
                    _ = update_file(url_config_file, old_str=replace_words[0], new_str=new_word, start_str=start_with)
            # 第二轮「被跳过行里的 URL」：进 try 后的早退分支（如无协议头补 https:// 后取不出 host）
            # 与异常分支分属不同位置，这里统一把原行里能认出的 URL 补进快照。放在归并之前即判据所在。
            for _unparsed_line in _unparsed_lines:
                _skipped_url = _line_contains_url(_unparsed_line.strip().lstrip("#").strip())
                if _skipped_url:
                    _skipped_urls.add(_skipped_url)
            running_snapshot = list(running_list)
            for running_url in running_snapshot:
                if running_url in _skipped_urls:
                    # 本行本轮解析失败/被跳过，既不能证明还在、也不能证明被注释——保留上一轮
                    # 注释状态，绝不在此把它当「已注释」写进 _url_comments（那会强制停掉正在进行的录制）。
                    continue
                if running_url not in _seen_urls and running_url not in _url_comments:
                    _url_comments.add(running_url)

            # 整轮解析（含 running_snapshot 归并）成功后才整体换位 url_comments：
            # 中途抛错时全局集合保持上一轮值，房间线程始终看到完整自洽的注释状态。
            url_comments = _url_comments

            # dict.fromkeys 保序去重（list(set(...)) 会打乱房间顺序），同为 O(N)。
            text_no_repeat_url = list(dict.fromkeys(url_tuples_list))

            if len(text_no_repeat_url) > 0:
                for url_tuple in text_no_repeat_url:
                    # 写侧（start_record 的 append）已入锁，读取侧同样持锁，否则
                    # 「录制线程 append + 主循环切片整体替换」在锁外交错会丢条目。
                    with record_state_lock:
                        if url_tuple[1] in not_record_list:
                            continue

                    # 停止录制时不拉起新线程；disk_limited 需单独再判一次——空间不足期间
                    # 即使 exit_recording 被别处清零也不应拉起。
                    if (
                        url_tuple[1] not in running_list
                        and not exit_recording
                        and not disk_limited
                        and recording_enabled
                    ):
                        # 序号取「与该 URL 绑定且单调」的源（理由见本 try 头部 _count_source 注释）
                        _count_source += 1
                        _room_seq = _count_source
                        with record_state_lock:
                            # 跳过分属仍在收尾线程的序号：它们留下的旧录制名尚未清完
                            while _count_source in _room_seq_in_use and _room_seq_in_use[_count_source].is_alive():
                                _count_source += 1
                                _room_seq = _count_source
                            _room_seq_in_use[_room_seq] = threading.current_thread()
                        print(
                            i18n.tr(
                                "\r{first_start}地址: {url_tuple}",
                                first_start="新增" if not first_start else "传入",
                                url_tuple=utils.mask_credentials(url_tuple[1]),
                            )
                        )
                        # 一次临界区内完成「计数 +1 → 登记 → 快照序号」，增量维护 monitoring。
                        # not_record_list 的写入统一挪到 record_state_lock 内（消费侧也持锁读）；
                        # 锁外交错会丢条目 → 该房间再也不会被拉起。
                        with record_state_lock:
                            monitoring += 1
                            running_list.append(url_tuple[1])
                            args = (url_tuple, _room_seq)
                        # monitoring 只保留「活跃监控数」语义；thread_key 用 uuid、录制名序号用
                        # _room_seq，见下方

                        # 线程入口：_key 是 create_var 注册键，_args 是 start_record 参数元组，
                        # _room_state 把本轮录制名带回线程出口供弹幕监控清理。
                        # 参数经 Thread(args=...) 绑定当前循环值，规避闭包晚期绑定。
                        def _room_thread_target(
                            _key: str, _args: tuple[tuple[str, str, str], int], _room_state: dict[str, str]
                        ) -> None:
                            try:
                                start_record(*_args, room_state=_room_state)
                            finally:
                                # 线程退出兜底：从运行列表移除该 URL（幂等）。不清理会让主循环
                                # 误判「仍在运行」，重新开始后该房间永不重启。
                                remove_room_from_running(_args[0][1])
                                # Shopee 的 new_record_url 会进 not_record_list 跳过本轮，
                                # 线程退出时须按 base + "?" 前缀移除本线程条目，否则该房间永久消失。
                                # 增删一律在 record_state_lock 内做，并按值定点移除（锁外交错会丢条目）。
                                if _args[0][1]:
                                    _not_record_prefix = _args[0][1].split("?", 1)[0] + "?"
                                    with record_state_lock:
                                        # 长度守恒：清不到不抛错
                                        not_record_list[:] = [
                                            u for u in not_record_list if not u.startswith(_not_record_prefix)
                                        ]
                                # 弹幕监控清理的时机是线程退出：start_record 回填 room_state，
                                # 这里调一次 room_stopped。清理失败静默（旁路功能不得中断收尾）。
                                if _room_state.get("name"):
                                    try:
                                        from src.danmaku_monitor import get_hub

                                        get_hub().room_stopped(_room_state["name"], "房间已停止录制")
                                    except Exception:
                                        pass
                                with record_state_lock:
                                    # 只在登记的确实是本线程时才 pop：键若按房间数量推导会被
                                    # 新房间复用，旧线程退出时会误删别人的条目。归属校验是第二道防线。
                                    if create_var.get(_key) is threading.current_thread():
                                        create_var.pop(_key, None)
                                    # 序号随线程退出一并作废，避免与仍在收尾/后续房间的序号重叠。
                                    # 放在锁内与上面的 pop 同一临界区，读侧（start_record 首行）永远
                                    # 看到「线程已登记 ⇔ 序号已占用」的自洽状态。
                                    _room_seq_in_use.pop(_args[1], None)

                        # 键与房间数量/序号解耦：uuid4 片段全局唯一，不会与仍在收尾的线程重名
                        thread_key = f"thread-{uuid.uuid4().hex[:12]}"
                        room_state: dict[str, str] = {"name": ""}
                        create_var[thread_key] = threading.Thread(
                            target=_room_thread_target,
                            name=thread_key,
                            args=(thread_key, args, room_state),
                        )
                        create_var[thread_key].daemon = True
                        # start() 会抛 RuntimeError（线程数打满）：登记发生在前，抛错必须
                        # 就地回滚，否则该 URL 永远留在 running_list、房间再也不会被拉起。
                        try:
                            create_var[thread_key].start()
                        except RuntimeError as e:
                            create_var.pop(thread_key, None)
                            remove_room_from_running(url_tuple[1])
                            # 2026-10-30（M-01）：登记发生在 start() 之前，启动失败必须一并回滚序号。
                            # 登记值是本调度线程（恒 alive），线程退出口的 pop（_room_thread_target 的
                            # finally）永远等不到——漏 pop 即永久烧掉一个录制名序号，并在
                            # _room_seq_in_use 里留一条恒活条目，7×24 常驻进程下无界累积。
                            with record_state_lock:
                                _room_seq_in_use.pop(_room_seq, None)
                            logger.warning(
                                i18n.tr(
                                    "录制线程启动失败，本轮跳过该房间（下轮会重试）: {url} {type_name}: {e}",
                                    url=utils.mask_credentials(url_tuple[1]),
                                    type_name=type(e).__name__,
                                    e=e,
                                )
                            )
                            continue
                        _interruptible_sleep(local_delay_default)
            # 上报活跃监控数，供调度器自适应并发容量
            if scheduler is not None:
                scheduler.set_active_count(monitoring)
            first_start = False

        except Exception as err:
            logger.error(
                i18n.tr(
                    "错误信息: {err} 发生错误的行数: {get_error_line}", err=err, get_error_line=_get_error_line(err)
                )
            )

        if first_run:
            t = threading.Thread(target=display_info, args=(), daemon=True)
            t.start()
            t2 = threading.Thread(target=adjust_max_request, args=(), daemon=True)
            t2.start()
            first_run = False

        time.sleep(3)


if __name__ == "__main__":
    main()
