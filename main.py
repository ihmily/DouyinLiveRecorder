#!/usr/bin/env python3
# -*- encoding: utf-8 -*-

# DouyinLiveRecorder 主程序入口 - 命令行版
#
# 这是直播录制工具的核心模块，负责：
# - 配置文件的读取和解析
# - 多平台直播流的获取和解析
# - FFmpeg 录制进程的管理
# - 多线程并发录制控制
# - 错误处理和自动重试
# - 直播状态通知推送
#
# 支持平台：60+ 国内外直播平台（详见下文）
#
# 架构流程：
#     URL配置 → 平台识别 → 获取直播数据 → 解析流地址 → FFmpeg录制 → 状态监控
#
# 对外主要函数：
# - main(non_interactive)：录制主循环入口（CLI 直跑与 web.py 守护线程共用）
# - start_record(url_data, count_variable)：单个直播间的录制线程主体
# - check_subprocess(...)：启动并守护一次 ffmpeg 录制子进程
# - get_status()：录制引擎运行状态快照，供 Web API 读取
#
# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-07-17 23:52:05
# Update: 2025-10-23 19:48:05
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.

# 强制标准流以 UTF-8 输出。
# 原因：冻结后的 exe 作为 GUI 子进程（stdout 是管道而非真实控制台）时，
# Python 会回退到 GBK 区域编码写输出；而 GUI 父进程按 UTF-8 读取该管道，
# 导致中文乱码（如「自动获取 Cookie ttwid 成功」变成「�Զ���ȡ����」）。
# 必须在导入任何会写日志/控制台的模块（如 src.logger）之前执行。
import os
import sys

# 当以 `python main.py` 直接运行时，本模块被加载为 `__main__` 而非 `main`；
# 若 src 子模块 `import main`，会再次执行整个 main.py（双重初始化、配置被重读）。
# 这里一次性把 `main` 指向当前 `__main__` 模块，避免重执行。
if sys.modules.get("main") is None:
    sys.modules["main"] = sys.modules["__main__"]


# 把 stdout/stderr 统一重配置为 UTF-8（Windows 额外把控制台代码页切到 65001）；无入参，无返回值
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
        # 把控制台代码页切到 UTF-8，否则即使 Python 输出 UTF-8 字节，
        # GBK 控制台也无法正确渲染。无控制台（窗口化/管道）时调用会失败，可忽略。
        try:
            import ctypes

            _k32 = ctypes.windll.kernel32
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
import shlex
import shutil
import signal
import subprocess
import threading
import time
import types
import uuid
from collections import deque
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, cast

import httpx
from loguru import logger

from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi
from src import get_danmaku_collector, spider, stream, utils
from src.config_io import (
    _safe_float,
    _safe_int,
    backup_file,
    backup_file_start,
    delete_line,
    read_config_value,
    update_anchor_name,
    update_file,
)
from src.ffmpeg_install import check_ffmpeg, ffmpeg_path

# ---- 重构：以下函数已抽离至 src 子模块，此处重新导出以保持 main.<name> 命名空间兼容 ----
from src.ffmpeg_proc import (
    _cleanup_single_ffmpeg_process,
    _get_error_line,
    _terminate_ffmpeg_process,
    cleanup_all_ffmpeg_processes,
    register_ffmpeg_process,
    unregister_ffmpeg_process,
)
from src.notify import (
    adjust_max_request,
    clear_record_info,
    push_message,
    record_error,
    record_success,
    run_script,
)
from src.proxy import ProxyDetector
from src.recorder_status import (
    display_info,
    get_status,
)
from src.scheduler import ConcurrencyScheduler, ResizableSemaphore, host_of
from src.stream_select import (
    _douyin_rate_limit,
    _validate_stream_url,
    clean_name,
    contains_url,
    get_quality_code,
    get_record_headers,
    get_record_user_agent,
    mark_ffmpeg_reject,
    select_source_url,
)
from src.video_postprocess import (
    _run_ffmpeg_checked,
    converts_m4a,
    converts_mp4,
    generate_subtitles,
    get_startup_info,
    segment_video,
)


# 获取当前程序版本号；无入参，返回形如 "v1.2.3" 的字符串（都取不到时回退 "v0.0.0"）
def _read_version_from_pyproject() -> str:
    # 从 pyproject.toml 读取版本号（单一事实源）。
    #
    # 优先使用 importlib.metadata（已安装时），
    # 回退到直接解析 pyproject.toml 文件。
    #
    try:
        from importlib.metadata import version as get_version

        return f"v{get_version('DouyinLiveRecorder')}"
    except Exception:
        pass
    # 回退：直接读取 pyproject.toml
    pyproject_path = Path(__file__).parent / "pyproject.toml"
    if pyproject_path.exists():
        text = pyproject_path.read_text(encoding="utf-8")
        m = re.search(r'^version\s*=\s*["\'](.+?)["\']', text, re.MULTILINE)
        if m:
            return f"v{m.group(1)}"
    return "v0.0.0"  # 最终回退


# 版本信息和支持的平台列表（从 pyproject.toml 读取）
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
recording_time_list: dict[str, list[datetime.datetime | str]] = {}  # 记录每个直播间的开始录制时间
exit_recording: bool = False  # 退出标志

# 错误控制和动态调优
error_count: int = 0  # 累计错误计数（自进程启动起单调递增，不做周期清零；窗口口径见 error_window）
pre_max_request: int = 10  # 之前的最大请求数
max_request: int = 3  # 同一时间访问网络的线程数（由 main() 读取配置后覆盖）
max_request_lock: threading.Lock = threading.Lock()  # 最大请求数的线程锁
error_window_size: int = 10  # 错误窗口大小
error_window: deque[int] = deque(maxlen=error_window_size)  # 错误窗口（deque maxlen 自动裁剪，避免无界增长）
error_threshold: float = 0.5  # 错误率阈值（0-1），错误率超过后降低并发

# URL 和配置管理
url_tuples_list: list[tuple[str, str, str]] = []  # 解析后的 URL 配置列表（格式：(画质, URL, 主播名)
url_comments: list[str] = []  # 被注释掉的 URL 列表
text_no_repeat_url: list[tuple[str, str, str]] = []  # 去重后的 URL 文本
need_update_line_list: list[str] = []  # 需要更新的配置行
not_record_list: list[str] = []  # 不录制的直播间列表
ini_URL_content: str = ""  # URL 配置文件初始内容（用于 update_file 异常恢复）

# 标志变量
first_start: bool = True  # 首次启动标志
first_run: bool = True  # 首次运行标志
global_proxy: bool = False  # 全局代理启用标志
use_proxy: bool = False  # 是否使用代理 IP（由 main() 读取配置后覆盖）
create_var: dict[str, threading.Thread] = {}  # 动态变量创建（用于字幕线程
start_display_time: "datetime.datetime" = datetime.datetime.now()  # 显示信息开始时间

# 录制配置（由 main() 读取 config.ini 后覆盖，此处给默认值供 display_info 等函数引用）
delay_default: int = 120  # 循环监测间隔时间（秒）
video_record_quality: str = "原画"  # 录制视频画质
video_save_type: str = "ts"  # 录制视频格式
split_video_by_time: bool = False  # 是否开启分段录制
split_time: str = "1800"  # 视频分段时间（秒）
create_time_file: bool = False  # 是否生成时间字幕文件
auto_update_anchor_name: bool = True  # 主播名变更时自动同步配置与录制文件（由 main() 读取配置后覆盖）
hls_collection_enabled: bool = True  # 是否优先使用 HLS(m3u8) 源采集；关闭时回退 FLV
# 弹幕录制设置（main() 热加载配置时经 global 写回，check_subprocess 读取）
enable_danmaku: bool = False  # 是否录制弹幕
enable_danmaku_monitor: bool = False  # 是否弹幕监控（与弹幕录制解耦：仅监控不落 SRT）
danmaku_split_time: float = 1800.0  # 弹幕分片时长(秒)
danmaku_platforms: list[str] = []  # 弹幕录制平台列表
record_danmaku_args: dict[str, Any] | None = None  # 当前录制房间的弹幕参数(平台相关)

# ==================== 路径和配置 ====================


# 计算应用根目录；无入参，返回 exe 同级目录（源码运行时为主脚本所在目录）的绝对路径字符串
def _app_root() -> str:
    # 应用程序根目录（exe 同级目录）。
    #
    #     源码运行返回主脚本目录；冻结运行（onedir + _internal）下 exe 与其同级的
    #     config/ ffmpeg/ node/ 等运行时资源位于 exe_dir，而 src/ 及依赖在
    #     exe_dir/_internal/，故此处返回 exe 同级目录，供定位 config/ffmpeg/node。
    #
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.split(os.path.realpath(sys.argv[0]))[0]


script_path: str = _app_root()  # 脚本所在目录（冻结后指向 _internal/）
config_file: str = f"{script_path}/config/config.ini"  # 主配置文件路径
url_config_file: str = f"{script_path}/config/URL_config.ini"  # URL 配置文件路径
backup_dir: str = f"{script_path}/backup_config"  # 配置备份目录
text_encoding: str = "utf-8-sig"  # 文本文件编码（支持 BOM
rstr: str = r"[\/\\\:\*\？?\"\<\>\|&#.。,， ~！· ]"  # 文件名字符过滤正则
default_path: str = f"{script_path}/downloads"  # 默认下载目录
os.makedirs(default_path, exist_ok=True)  # 确保下载目录存在
# RLock：主循环持锁读取配置期间可能再次进入 read_config_value 的写入路径，可重入避免同线程死锁
file_update_lock: threading.RLock = threading.RLock()  # 文件更新锁（防止多线程写入冲突

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
check_path: str = ""
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
host_id: re.Match[str] | None = None
input_url: str = ""
is_comment_line: bool = False
line: str = ""
line_list: list[str] = []
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
seen_urls: set[str] = set()
split_line: list[str] = []
start_with: str | None = None
t: threading.Thread | None = None
t2: threading.Thread | None = None
url: str = ""
url_host: str = ""
url_line_list: list[str] = []
url_tuple: tuple[str, ...] = ()

_recorder_thread = None  # 由 web.py 设置，用于 get_status() 检测存活


# 信号处理器：置退出标志、清理 ffmpeg 进程与 HTTP 连接池后退出进程；_signum/_frame 为信号回调形参（未使用），不返回
def safe_exit(_signum: int, _frame: types.FrameType | None) -> None:
    # 安全的退出处理函数
    global exit_recording
    exit_recording = True
    color_obj.print_colored("\n正在安全退出...", color_obj.YELLOW)
    cleanup_all_ffmpeg_processes()
    from src.async_http import close_all_clients_sync

    close_all_clients_sync()
    sys.exit(0)


# 注册信号处理器
_ = signal.signal(signal.SIGINT, safe_exit)
_ = signal.signal(signal.SIGTERM, safe_exit)
if hasattr(signal, "SIGBREAK"):
    _ = signal.signal(signal.SIGBREAK, safe_exit)

# 进程异常退出时兜底清理 ffmpeg 与 HTTP 连接池（覆盖硬杀 / 未捕获异常等非优雅退出路径）
_atexit_result_1 = atexit.register(cleanup_all_ffmpeg_processes)
from src.async_http import close_all_clients_sync

_atexit_result_2 = atexit.register(close_all_clients_sync)


os_type: str = os.name
color_obj: "utils.Color" = utils.Color()
# 将 ffmpeg 目录前置到当前 PATH：使用实时 os.environ（而非 import 时快照），
# 避免丢弃 import 之后对其余 PATH 条目的追加修改；并跳过重复插入。
_current_path = os.environ.get("PATH", "")
ffmpeg_path_norm = os.path.normpath(ffmpeg_path)
if ffmpeg_path_norm and ffmpeg_path_norm not in _current_path.split(os.pathsep):
    os.environ["PATH"] = ffmpeg_path_norm + os.pathsep + _current_path
else:
    os.environ["PATH"] = _current_path

PLATFORM_HOST = [
    "live.douyin.com",
    "v.douyin.com",
    "www.douyin.com",
    "live.kuaishou.com",
    "www.huya.com",
    "www.douyu.com",
    "www.yy.com",
    "live.bilibili.com",
    "www.redelight.cn",
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
    "live.shopee.",
    ".shp.ee",
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
    "live.shopee.",
    ".shp.ee",
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


# 用 httpx 流式把 source_url（FLV 直链）直接写入 save_path，不经 ffmpeg；
# record_name/live_url 用于中断判断与状态清理，platform 用于补对应平台请求头；返回是否下载完成
def direct_download_stream(
    source_url: str,
    save_path: str,
    record_name: str,
    live_url: str,
    platform: str,
    cookies: str | None = None,
) -> bool:
    # 直接下载直播流（不走 FFmpeg）；请求头/cookie/UA 与 ffmpeg 录制路径保持一致。
    try:
        with open(save_path, "wb") as f:
            headers: dict[str, str] = {}
            header_params = get_record_headers(platform, live_url, cookies=cookies)
            if header_params:
                headers.update(header_params)
            ua = get_record_user_agent(platform)
            if ua:
                headers["User-Agent"] = ua

            with httpx.Client(
                timeout=30, verify=_http_config.get_effective_ssl_verify(platform), headers=headers
            ) as client:
                with client.stream("GET", source_url, headers=headers, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(f"请求直播流失败: {source_url} - 状态码: {response.status_code}")
                        return False

                    downloaded = 0
                    chunk_size = 1024 * 16

                    for chunk in response.iter_bytes(chunk_size):
                        if live_url in url_comments or exit_recording:
                            color_obj.print_colored(
                                f"[{record_name}]录制时已被注释或请求停止,下载中断", color_obj.YELLOW
                            )
                            clear_record_info(record_name, live_url)
                            return False

                        if chunk:
                            _ = f.write(chunk)
                            downloaded += len(chunk)
                    print()
                    return True
    except Exception as e:
        logger.error(f"FLV下载错误: {source_url} - {type(e).__name__}: {e} 发生错误的行数: {_get_error_line(e)}")
        return False


# ffmpeg「快速失败」判定阈值（秒）：进程存活不超过该值即退出，视为输入打开被 CDN 拒绝
# 的签名（实测虎牙 HS 线路探针 200 后 ffmpeg 立即 403，约 1 秒退出）；拉流中断/重连耗尽
# （-reconnect_delay_max 60）通常远超该值，不属此类。模块级常量便于测试注入。
_FFMPEG_FAST_FAIL_SECONDS = 20.0


# 启动并全程守护一次 ffmpeg 录制：ffmpeg_command 为已拼好的完整命令（末位为输出路径），
# save_type 决定是否转 mp4/是否跳过弹幕与字幕，script_command 为录后自定义脚本，
# platform + danmaku_args 用于同步启停弹幕采集；
# 返回 True 表示因该地址被注释或收到退出标志而提前中断（调用方应结束线程），False 表示本次录制自然结束
def check_subprocess(
    record_name: str,
    record_url: str,
    ffmpeg_command: list[str],
    save_type: str,
    script_command: str | None = None,
    platform: str | None = None,
    danmaku_args: Any = None,
) -> bool:
    # 检查 FFmpeg 子进程状态并处理异常
    save_file_path = ffmpeg_command[-1]
    _proc_started_at = time.time()  # 进程启动时刻：失败时区分「快速失败(输入打开被拒)」与「拉流中断」
    process = subprocess.Popen(
        ffmpeg_command, stdin=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
    )

    # 注册 ffmpeg 进程
    register_ffmpeg_process(process)

    subs_file_path = save_file_path.rsplit(".", maxsplit=1)[0]

    # 分段录制时 save_file_path 是 ffmpeg 输出模板(含 %03d 占位符),实际落盘为 _000/_001…
    # SRT 前缀须与真实文件名对齐,去掉占位符,由 SrtWriter 自行追加 _000 分片号;
    # 占位符有 _%03d(视频分段)与 _%02d(音频分段)两种,统一剥离(replace 未命中为空操作)
    for _seg_placeholder in ("_%02d", "_%03d"):
        subs_file_path = subs_file_path.replace(_seg_placeholder, "")

    # 弹幕采集：与 ffmpeg 同起同停，SRT 前缀与录像同前缀同目录。
    # 录制弹幕与弹幕监控共用同一采集器/连接：任一开启即连接；
    # 仅监控（录制弹幕关）时不落 SRT（write_srt=False）；失败不影响录像。
    danmaku_collector = None
    _danmaku_active = enable_danmaku or enable_danmaku_monitor
    if _danmaku_active and platform is not None and platform in danmaku_platforms and "音频" not in save_type:
        if not danmaku_args:
            logger.debug(f"[{record_name}]弹幕跳过: 平台={platform} 未获取到弹幕参数(danmaku_args 为空),请查看上游日志")
        else:
            try:
                danmaku_collector = get_danmaku_collector(
                    platform=platform,
                    danmaku_args=danmaku_args,
                    base_filename=subs_file_path,
                    segment_seconds=danmaku_split_time if split_video_by_time else None,
                    room_name=record_name,
                    write_srt=enable_danmaku,
                )
                if danmaku_collector is not None:
                    danmaku_collector.start()
            except Exception as e:
                logger.warning(f"[{record_name}]弹幕采集启动失败,不影响录制: {e}")
                danmaku_collector = None

    subs_thread_name = f"subs_{Path(subs_file_path).name}"
    if create_time_file and not split_video_by_time and "音频" not in save_type:
        create_var[subs_thread_name] = threading.Thread(target=generate_subtitles, args=(record_name, subs_file_path))
        create_var[subs_thread_name].daemon = True
        create_var[subs_thread_name].start()

    # 内部包装：直接转调模块级 _terminate_ffmpeg_process 终止 proc，timeout 为总等待秒数，返回是否已退出
    def terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
        # 复用模块级公共终止逻辑（避免重复实现导致的逻辑漂移）
        return _terminate_ffmpeg_process(proc, timeout)

    # 录制并发软上限（资源治理）：限制同时进行的 ffmpeg 录制数，防 80+ 任务同时录制拖垮
    # CPU/磁盘/带宽。recording_limit=0 时 recording_semaphore 容量极高，acquire 不阻塞（等同不限制）。
    _rec_sem = recording_semaphore
    _rec_sem.acquire()
    try:
        while process.poll() is None:
            if record_url in url_comments or exit_recording:
                color_obj.print_colored(f"[{record_name}]录制时已被注释,本条线程将会退出", color_obj.YELLOW)
                clear_record_info(record_name, record_url)

                # 录制提前停止:在意SIGINT前 flush 弹幕,确保最后一批写入
                if danmaku_collector is not None:
                    danmaku_collector.stop()

                # 使用更可靠的进程终止机制
                success = terminate_ffmpeg_process(process)
                if not success:
                    logger.warning(f"[{record_name}] ffmpeg 进程可能没有完全终止，请检查系统进程")

                # 确保异常路径也注销 ffmpeg 进程
                unregister_ffmpeg_process(process)
                return True
            time.sleep(1)
    finally:
        # 无论正常结束还是提前中断/异常，均释放录制并发槽，避免槽位泄漏导致后续录制饿死
        _rec_sem.release()

    # ffmpeg 正常退出:弹幕尾收兜底停止(循环外,整个录制周期仅执行一次)
    if danmaku_collector is not None:
        danmaku_collector.stop()

    # 确保子进程资源被回收，避免僵尸进程/句柄滞留（尤其在 Web 常驻模式下）
    try:
        _ = process.wait(timeout=30)
    except Exception:
        pass
    return_code = process.returncode
    stop_time = time.strftime("%Y-%m-%d %H:%M:%S")
    if return_code == 0:
        if converts_to_mp4 and save_type == "TS":
            if split_video_by_time:
                file_paths = utils.get_file_paths(os.path.dirname(save_file_path))
                prefix = os.path.basename(save_file_path).rsplit("_", maxsplit=1)[0]
                for path in file_paths:
                    if prefix in path:
                        threading.Thread(target=converts_mp4, args=(path, delete_origin_file), daemon=True).start()
            else:
                threading.Thread(target=converts_mp4, args=(save_file_path, delete_origin_file), daemon=True).start()
        print(f"\n{record_name} {stop_time} 直播录制完成\n")

        if script_command:
            logger.debug("开始执行脚本命令!")
            if "python" in script_command:
                params = [
                    f'--record_name "{record_name}"',
                    f'--save_file_path "{save_file_path}"',
                    f"--save_type {save_type}",
                    f"--split_video_by_time {split_video_by_time}",
                    f"--converts_to_mp4 {converts_to_mp4}",
                ]
            else:
                params = [
                    f'"{record_name.split(" ", maxsplit=1)[-1]}"',
                    f'"{save_file_path}"',
                    save_type,
                    f"split_video_by_time:{split_video_by_time}",
                    f"converts_to_mp4:{converts_to_mp4}",
                ]
            script_command = script_command.strip() + " " + " ".join(params)
            run_script(script_command)
            logger.debug("脚本命令执行结束!")
        # 流正常结束（主播下线）＝平台健康：按房间 host 记一次成功样本（与下方失败分支配对）
        record_success(host_of(record_url))

    else:
        color_obj.print_colored(f"\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n", color_obj.RED)
        # —— 录制失败反馈调度器（2026-08-23 实测定稿）：
        # ① 按房间 host 记失败样本，驱动按平台熔断与全局背压——此前录制失败不上报，
        #   轮末还会无条件记成功样本，多房间同 host 时失败率被稀释、熔断永不触发
        #   （实测虎牙房间秒级 403 失败循环，www.huya.com 熔断器始终 closed）；
        # ② 快速失败（≤20s，输入打开被 CDN 拒绝的签名；拉流中断/重连耗尽通常 >60s）时，
        #   把 ffmpeg 实际拉流地址记入探针退避：下一轮 select_source_url 跳过该线路探针、
        #   直接尝试下一 CDN 候选。「探针 200 → ffmpeg 403」的假绿只在录制侧可观测，
        #   不标记则房间会无限循环撞同一条死线路（实测 hs.hls.huya.com）。——
        record_error(host_of(record_url))
        if time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS:
            try:
                _stream_url = ffmpeg_command[ffmpeg_command.index("-i") + 1]
                mark_ffmpeg_reject(_stream_url, platform)
            except ValueError:
                logger.debug(f"[{record_name}] ffmpeg 命令缺少 -i 输入参数，跳过探针退避标记")

    with record_state_lock:
        recording.discard(record_name)
        recording_time_list.pop(record_name, None)
    # 取消注册 ffmpeg 进程
    unregister_ffmpeg_process(process)
    return False


# 主播名变更后同步重命名保存目录及历史录制文件：把 {保存路径}/{platform}/{old_name} 目录
# 重命名为 {new_name}（目标已存在则逐项合并移入），并把目录树内以 "{old_name}_" 开头的录制
# 文件（含弹幕 SRT/时间字幕等同前缀产物）与以 "_{old_name}" 结尾的标题子目录批量改名，
# 保证文件系统命名与配置文件中的主播名一致；返回目录级操作是否成功（目录不存在视为成功，
# 从未录制过），失败返回 False 由调用方下轮轮询重试
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
        logger.warning(f"重命名主播目录失败（下轮重试）: {old_name} -> {new_name}: {e}")
        return False


# 把 old_dir 内全部条目移入 new_dir（同名冲突保留双方并告警）；全部移入且无残留时删除旧目录，
# 残留（冲突文件）只告警不抛异常——不阻塞主播名同步主流程，留给用户手动整理
def _merge_anchor_directory(old_dir: str, new_dir: str) -> None:
    for entry in list(os.scandir(old_dir)):
        dst = os.path.join(new_dir, entry.name)
        if os.path.exists(dst):
            logger.warning(f"合并主播目录时发现同名文件（双方保留，请手动整理）: {dst}")
            continue
        try:
            os.rename(entry.path, dst)
        except OSError as e:
            # 单条目移动失败（文件被转码/播放器占用）：告警后继续其余条目，下轮整体重试
            logger.warning(f"合并主播目录条目失败（下轮重试）: {entry.path} -> {dst}: {e}")
    try:
        if not os.listdir(old_dir):
            os.rmdir(old_dir)
    except OSError as e:
        logger.warning(f"删除旧主播目录失败（已忽略）: {old_dir}: {e}")


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
            logger.warning(f"主播名变更重命名失败（已跳过，不影响其余文件）: {entry.path}: {e}")


# 平台分派解析：把直播间地址按域名路由到对应平台的爬虫与流地址解析模块，得到本轮 port_info。
# 自 start_record 原样搬移（原内联 if/elif 链约 700 行，超出 basedpyright 单函数条件路径
# 复杂度上限），分支体语义未变；cookie/代理等配置项仍按模块级全局变量即时读取。
# 返回 (platform, port_info, record_danmaku_args, new_record_url)：
# - record_danmaku_args 为弹幕参数(平台相关)，进房失败为 None，由调用方传入 check_subprocess 启停弹幕；
# - new_record_url 为 Shopee 平台专用（带 uid 的完整 URL，用于更新配置）；
# - 无法识别的直播地址返回 None，由调用方 break 进入延迟后重试而非直接结束线程。
def _resolve_platform_stream(
    record_url: str, proxy_address: str | None, record_quality: str
) -> tuple[str, dict[str, Any], dict[str, Any] | None, str] | None:
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None  # 本轮弹幕参数;平台分支填充;进房失败为None时跳过弹幕
    new_record_url = ""  # Shopee 平台专用：记录带 uid 的完整 URL 用于更新配置
    if record_url.find("douyin.com/") > -1:
        platform = "抖音直播"
        with semaphore:
            _douyin_rate_limit()  # 速率限制：防止并发请求触发抖音风控
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

    elif record_url.find("https://www.tiktok.com/") > -1:
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

    elif record_url.find("https://live.kuaishou.com/") > -1:
        platform = "快手直播"
        with semaphore:
            json_data = asyncio.run(
                spider.get_kuaishou_stream_data(url=record_url, proxy_addr=proxy_address, cookies=ks_cookie)
            )
            port_info = asyncio.run(stream.get_kuaishou_stream_url(json_data, record_quality))

    elif record_url.find("https://www.huya.com/") > -1:
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
                    logger.warning(f"[虎牙直播]弹幕参数提取失败: {e}")
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
                            f"[虎牙直播]OD/BD/UHD app路径弹幕参数缺失，跳过弹幕: "
                            f"yyid={_ayyuid}, lChannelId={_topSid}, lSubChannelId={_subSid}"
                        )
                except Exception as e:
                    logger.warning(f"[虎牙直播]OD/BD/UHD app路径弹幕参数提取失败: {e}")

    elif record_url.find("https://www.douyu.com/") > -1:
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

    elif record_url.find("https://www.yy.com/") > -1:
        platform = "YY直播"
        with semaphore:
            json_data = asyncio.run(
                spider.get_yy_stream_data(url=record_url, proxy_addr=proxy_address, cookies=yy_cookie)
            )
            port_info = asyncio.run(stream.get_yy_stream_url(json_data))

    elif record_url.find("https://live.bilibili.com/") > -1:
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
                    logger.warning(f"[B站直播]弹幕信息获取失败: {e}")
                    record_danmaku_args = None
    elif record_url.find("http://xhslink.com/") > -1 or record_url.find("https://www.xiaohongshu.com/") > -1:
        platform = "小红书直播"
        with semaphore:
            port_info = asyncio.run(spider.get_xhs_stream_url(record_url, proxy_addr=proxy_address, cookies=xhs_cookie))

    elif record_url.find("www.bigo.tv/") > -1 or record_url.find("slink.bigovideo.tv/") > -1:
        platform = "bigo"
        with semaphore:
            port_info = asyncio.run(
                spider.get_bigo_stream_url(record_url, proxy_addr=proxy_address, cookies=bigo_cookie)
            )

    elif record_url.find("https://app.blued.cn/") > -1:
        platform = "blued"
        with semaphore:
            port_info = asyncio.run(
                spider.get_blued_stream_url(record_url, proxy_addr=proxy_address, cookies=blued_cookie)
            )

    elif record_url.find("sooplive.co.kr/") > -1 or record_url.find("sooplive.com/") > -1:
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
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                        utils.update_config(
                            config_file,
                            "Cookie",
                            "sooplive_cookie",
                            cast(str, json_data["new_cookies"]),
                        )
                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问SOOP(原AfreecaTV)平台")

    elif record_url.find("cc.163.com/") > -1:
        platform = "网易CC直播"
        with semaphore:
            json_data = asyncio.run(spider.get_netease_stream_data(url=record_url, cookies=netease_cookie))
            port_info = asyncio.run(stream.get_netease_stream_url(json_data, record_quality))

    elif record_url.find("qiandurebo.com/") > -1:
        platform = "千度热播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_qiandurebo_stream_data(url=record_url, proxy_addr=proxy_address, cookies=qiandurebo_cookie)
            )

    elif record_url.find("www.pandalive.co.kr/") > -1 or record_url.find("www.plive.kr/") > -1:
        platform = "PandaTV"
        with semaphore:
            if global_proxy or proxy_address:
                json_data = asyncio.run(
                    spider.get_pandatv_stream_data(url=record_url, proxy_addr=proxy_address, cookies=pandatv_cookie)
                )
                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")

    elif record_url.find("fm.missevan.com/") > -1:
        platform = "猫耳FM直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_maoerfm_stream_url(url=record_url, proxy_addr=proxy_address, cookies=maoerfm_cookie)
            )

    elif record_url.find("www.winktv.co.kr/") > -1:
        platform = "WinkTV"
        with semaphore:
            if global_proxy or proxy_address:
                json_data = asyncio.run(
                    spider.get_winktv_stream_data(url=record_url, proxy_addr=proxy_address, cookies=winktv_cookie)
                )
                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问WinkTV直播平台")

    elif record_url.find("www.flextv.co.kr/") > -1 or record_url.find("www.ttinglive.com/") > -1:
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
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                        utils.update_config(config_file, "Cookie", "flextv_cookie", cast(str, json_data["new_cookies"]))
                if "play_url_list" in json_data:
                    port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                else:
                    port_info = json_data
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TTingLive(原Flextv)直播平台")

    elif record_url.find("look.163.com/") > -1:
        platform = "Look直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_looklive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=look_cookie)
            )

    elif record_url.find("www.popkontv.com/") > -1:
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
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                        utils.update_config(
                            file_path=config_file,
                            section="Authorization",
                            key="popkontv_token",
                            new_value=cast(str, port_info["new_token"]),
                        )

            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PopkonTV直播平台")

    elif record_url.find("twitcasting.tv/") > -1:
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

            if port_info and port_info.get("new_cookies"):
                with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                    utils.update_config(
                        file_path=config_file,
                        section="Cookie",
                        key="twitcasting_cookie",
                        new_value=cast(str, port_info["new_cookies"]),
                    )

    elif record_url.find("live.baidu.com/") > -1:
        platform = "百度直播"
        with semaphore:
            json_data = asyncio.run(
                spider.get_baidu_stream_data(url=record_url, proxy_addr=proxy_address, cookies=baidu_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality))

    elif record_url.find("weibo.com/") > -1:
        platform = "微博直播"
        with semaphore:
            json_data = asyncio.run(
                spider.get_weibo_stream_data(url=record_url, proxy_addr=proxy_address, cookies=weibo_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, hls_extra_key="m3u8_url"))

    elif record_url.find("kugou.com/") > -1:
        platform = "酷狗直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_kugou_stream_url(url=record_url, proxy_addr=proxy_address, cookies=kugou_cookie)
            )

    elif record_url.find("www.twitch.tv/") > -1:
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
                    logger.warning(f"[TwitchTV]弹幕 channel 提取失败: {e}")
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TwitchTV直播平台")

    elif record_url.find("www.liveme.com/") > -1:
        if global_proxy or proxy_address:
            platform = "LiveMe"
            with semaphore:
                port_info = asyncio.run(
                    spider.get_liveme_stream_url(url=record_url, proxy_addr=proxy_address, cookies=liveme_cookie)
                )
        else:
            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问LiveMe直播平台")

    elif record_url.find("www.huajiao.com/") > -1:
        platform = "花椒直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_huajiao_stream_url(url=record_url, proxy_addr=proxy_address, cookies=huajiao_cookie)
            )

    elif record_url.find("7u66.com/") > -1:
        platform = "流星直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_liuxing_stream_url(url=record_url, proxy_addr=proxy_address, cookies=liuxing_cookie)
            )

    elif record_url.find("showroom-live.com/") > -1:
        platform = "ShowRoom"
        with semaphore:
            json_data = asyncio.run(
                spider.get_showroom_stream_data(url=record_url, proxy_addr=proxy_address, cookies=showroom_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

    elif record_url.find("live.acfun.cn/") > -1 or record_url.find("m.acfun.cn/") > -1:
        platform = "Acfun"
        with semaphore:
            json_data = asyncio.run(
                spider.get_acfun_stream_data(url=record_url, proxy_addr=proxy_address, cookies=acfun_cookie)
            )
            port_info = asyncio.run(
                stream.get_stream_url(json_data, record_quality, url_type="flv", flv_extra_key="url")
            )

    elif record_url.find("live.tlclw.com/") > -1:
        platform = "畅聊直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_changliao_stream_url(url=record_url, proxy_addr=proxy_address, cookies=changliao_cookie)
            )

    elif record_url.find("ybw1666.com/") > -1:
        platform = "音播直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_yinbo_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yinbo_cookie)
            )

    elif record_url.find("www.inke.cn/") > -1:
        platform = "映客直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_yingke_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yingke_cookie)
            )

    elif record_url.find("www.zhihu.com/") > -1:
        platform = "知乎直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_zhihu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=zhihu_cookie)
            )

    elif record_url.find("chzzk.naver.com/") > -1:
        platform = "CHZZK"
        with semaphore:
            json_data = asyncio.run(
                spider.get_chzzk_stream_data(url=record_url, proxy_addr=proxy_address, cookies=chzzk_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

    elif record_url.find("www.haixiutv.com/") > -1:
        platform = "嗨秀直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_haixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=haixiu_cookie)
            )

    elif record_url.find("vvxqiu.com/") > -1:
        platform = "VV星球"
        with semaphore:
            port_info = asyncio.run(
                spider.get_vvxqiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=vvxqiu_cookie)
            )

    elif record_url.find("17.live/") > -1:
        platform = "17Live"
        with semaphore:
            port_info = asyncio.run(
                spider.get_17live_stream_url(url=record_url, proxy_addr=proxy_address, cookies=yiqilive_cookie)
            )

    elif record_url.find("www.lang.live/") > -1:
        platform = "浪Live"
        with semaphore:
            port_info = asyncio.run(
                spider.get_langlive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=langlive_cookie)
            )

    elif record_url.find("m.pp.weimipopo.com/") > -1:
        platform = "飘飘直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_pplive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=pplive_cookie)
            )

    elif record_url.find(".6.cn/") > -1:
        platform = "六间房直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_6room_stream_url(url=record_url, proxy_addr=proxy_address, cookies=six_room_cookie)
            )

    elif record_url.find("lehaitv.com/") > -1:
        platform = "乐嗨直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_haixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=lehaitv_cookie)
            )

    elif record_url.find("h.catshow168.com/") > -1:
        platform = "花猫直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_pplive_stream_url(url=record_url, proxy_addr=proxy_address, cookies=huamao_cookie)
            )

    elif record_url.find("live.shopee") > -1 or record_url.find("shp.ee/") > -1:
        platform = "shopee"
        with semaphore:
            port_info = asyncio.run(
                spider.get_shopee_stream_url(url=record_url, proxy_addr=proxy_address, cookies=shopee_cookie)
            )
            if port_info.get("uid"):
                new_record_url = record_url.split("?")[0] + "?" + str(port_info["uid"])

    elif record_url.find("www.youtube.com/") > -1 or record_url.find("youtu.be/") > -1:
        platform = "YouTube"
        with semaphore:
            json_data = asyncio.run(
                spider.get_youtube_stream_url(url=record_url, proxy_addr=proxy_address, cookies=youtube_cookie)
            )
            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

    elif record_url.find("tb.cn") > -1 or record_url.find("tbzb.taobao.com") > -1:
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

    elif record_url.find("3.cn") > -1 or record_url.find("m.jd.com") > -1:
        platform = "京东直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_jd_stream_url(url=record_url, proxy_addr=proxy_address, cookies=jd_cookie)
            )

    elif record_url.find("faceit.com/") > -1:
        platform = "faceit"
        with semaphore:
            if global_proxy or proxy_address:
                json_data = asyncio.run(
                    spider.get_faceit_stream_data(url=record_url, proxy_addr=proxy_address, cookies=faceit_cookie)
                )
                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
            else:
                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问faceit直播平台")

    elif record_url.find("www.miguvideo.com") > -1 or record_url.find("m.miguvideo.com") > -1:
        platform = "咪咕直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_migu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=migu_cookie)
            )

    elif record_url.find("show.lailianjie.com") > -1:
        platform = "连接直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_lianjie_stream_url(url=record_url, proxy_addr=proxy_address, cookies=lianjie_cookie)
            )

    elif record_url.find("www.imkktv.com") > -1:
        platform = "来秀直播"
        with semaphore:
            port_info = asyncio.run(
                spider.get_laixiu_stream_url(url=record_url, proxy_addr=proxy_address, cookies=laixiu_cookie)
            )

    elif record_url.find("www.picarto.tv") > -1:
        platform = "Picarto"
        with semaphore:
            port_info = asyncio.run(
                spider.get_picarto_stream_url(url=record_url, proxy_addr=proxy_address, cookies=picarto_cookie)
            )

    elif record_url.find(".m3u8") > -1 or record_url.find(".flv") > -1:
        platform = "自定义录制直播"
        port_info = {
            "anchor_name": platform + "_" + str(uuid.uuid4())[:8],
            "is_live": True,
            "record_url": record_url,
        }
        if ".flv" in record_url:
            port_info["flv_url"] = record_url
        else:
            port_info["m3u8_url"] = record_url

    else:
        # 不可达分支（main() 已按平台白名单过滤）；返回 None 由调用方 break 进入延迟后重试
        logger.error(f"无法识别的直播地址，本轮跳过: {record_url}")
        return None
    return platform, port_info, record_danmaku_args, new_record_url


# 单个直播间的录制线程主体：url_data 为 (中文画质, 直播间地址, 主播名) 三元组，
# count_variable 为该房间的显示序号；内部死循环「按域名分派到对应平台爬虫 → 解析流地址 →
# 拼 ffmpeg 命令录制 → 间隔轮询」，仅在地址被注释/收到退出标志时 return，正常情况下不返回
def start_record(url_data: tuple[str, str, str], count_variable: int = -1) -> None:
    # 录制主循环：检测→获取流→启动 FFmpeg
    while True:
        # 本轮录制显示名；线程退出清理监控房间时复用（首轮可能为空）。置于 try 之前，
        # 保证 finally 中引用必然已绑定（try 首语句前抛异常时不以 NameError 掩盖原始异常）
        record_name = ""
        # 熔断 key（host）：与 record_name 一同置于 try 之前，保证最外层 except（2386）引用必然已绑定；
        # 默认空串在异常早退分支被 record_error 视为 falsy，仅计入全局错误预算、不触发按 key 熔断。
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
            # 熔断 key：本直播间 host，用于按平台隔离并发与错误预算（降级/避免连锁报错）
            record_host = host_of(record_url)
            # 真实下发的画质代码（由 stream 模块回采，可能为 None）
            from src.stream import code_to_zh
            from src.stream import is_downgrade as _is_downgrade

            proxy_address = proxy_addr
            platform = "未知平台"

            if proxy_addr:
                proxy_address = None
                if enable_proxy_platform_list:
                    # 循环变量不用 platform：避免遮蔽外层 platform="未知平台"，
                    # 导致循环结束后 platform 残留为列表最后一个元素（日志误报平台名）
                    for _proxy_platform in enable_proxy_platform_list:
                        if _proxy_platform and _proxy_platform.strip() in record_url:
                            proxy_address = proxy_addr
                            break

            if not proxy_address:
                if extra_enable_proxy_platform_list:
                    for pt in extra_enable_proxy_platform_list:
                        if pt and pt.strip() in record_url:
                            proxy_address = proxy_addr_bak or None

            # print(f'\r代理地址:{proxy_address}')
            # print(f'\r全局代理:{global_proxy}')
            while True:
                # 弹幕参数每个监测轮先归零再分派（AGENTS.md 约定）：绝不沿用上一轮录制遗留的旧参数，
                # 防御未来把解析短路/复用旧值的改动重新引入陈旧 danmaku_args 到 check_subprocess
                record_danmaku_args = None
                if exit_recording:
                    logger.debug(f"检测到退出标志，录制线程退出: {record_url}")
                    return
                # 配置实时性：URL 被注释/移除后立即退出，不等本轮解析结果——
                # 原检查点位于解析成功之后，解析持续失败（平台接口异常）时永远走不到，
                # 线程滞留并占用监控位，URL_config.ini 的变更迟迟不生效
                if record_url in url_comments:
                    print(f"[{record_url}]已被注释,本条线程将会退出")
                    clear_record_info(record_name, record_url)
                    return
                # —— 并发熔断预检：该平台(host)连续失败达阈值时跳过本轮网络探测并退避，
                # 释放全局并发槽给其他平台，避免单平台抖动拖垮整体（降级应对连锁报错）——
                if scheduler is not None and not scheduler.allow(record_host):
                    _backoff = scheduler.backoff_seconds(record_host)
                    _backoff = min(_backoff, max(30.0, float(delay_default)))
                    logger.debug(f"[{record_host}] 并发熔断中，跳过本轮探测，退避 {_backoff:.0f}s")
                    time.sleep(_backoff)
                    continue
                try:
                    # 平台分派解析（复杂度控制已抽取为 _resolve_platform_stream）：
                    # 返回 (platform, port_info, 弹幕参数, Shopee新URL)；无法识别的地址返回 None
                    _resolved = _resolve_platform_stream(record_url, proxy_address, record_quality)
                    if _resolved is None:
                        # 不可达分支（main() 已按平台白名单过滤），break 进入延迟后重试而非直接结束线程
                        break
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
                        print(f"序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_data}")
                        record_error(record_host)
                    else:
                        # —— 解析成功即上报成功样本：half-open 探针依赖本轮结果闭环——
                        # 此前成功样本仅在 ffmpeg 退出(rc==0)时上报，探针房间进入长时间
                        # 录制期间，同 host 其余房间持续熔断饿死；主播未开播等正常轮次
                        # 则完全无样本，探针 _probing 永不复位（靠调度器租约超时兜底自愈）。
                        # 与上方解析失败分支的 record_error 对称，仅解析真正成功才上报。
                        record_success(record_host)
                        anchor_name = clean_name(anchor_name)

                        # —— 主播名自动同步：平台最新名与当前使用名不一致时，先重命名历史
                        # 录制目录/文件，成功后再更新 URL_config.ini 与本轮使用名 ——
                        # 时机安全性：本线程此刻必然不在录制中（录制期间阻塞在
                        # check_subprocess 内，检测点位于每轮解析之后、录制启动之前），
                        # 重命名不会触碰 ffmpeg 正在写入的文件；后台转码/字幕线程占用的
                        # 个别文件改名失败仅告警，目录级失败则本轮放弃、下轮轮询重试。
                        # 自定义流地址的 anchor_name 含随机 UUID（每轮都不同），跳过以防
                        # 反复触发改名。
                        latest_anchor_name = clean_name(cast(str, port_info.get("anchor_name", "")))
                        if (
                            auto_update_anchor_name
                            and platform != "自定义录制直播"
                            and anchor_name
                            and latest_anchor_name
                            and latest_anchor_name != "空白昵称"
                            and anchor_name != latest_anchor_name
                        ):
                            # 文件系统与配置全部同步成功才切换本轮使用名；任一失败则保持
                            # 旧名，下一轮轮询重试整个同步（rename 对已改名的目录幂等）
                            if rename_anchor_directory(
                                anchor_name, latest_anchor_name, platform
                            ) and update_anchor_name(record_url, latest_anchor_name):
                                logger.info(
                                    f"主播名已变更，配置与录制文件同步更新: {anchor_name} -> {latest_anchor_name}"
                                )
                                # 清理旧名残留的录制状态（正常路径录制结束即清理，此处兜底
                                # 异常残留，防止状态列表长期挂旧名条目）
                                _stale_record_name = f"序号{count_variable} {anchor_name}"
                                anchor_name = latest_anchor_name
                                with record_state_lock:
                                    recording.discard(_stale_record_name)
                                    recording_time_list.pop(_stale_record_name, None)
                        record_name = f"序号{count_variable} {anchor_name}"

                        if record_url in url_comments:
                            print(f"[{anchor_name}]已被注释,本条线程将会退出")
                            clear_record_info(record_name, record_url)
                            return

                        if not url_data[-1] and not run_once:
                            if new_record_url:
                                need_update_line_list.append(
                                    f"{record_url}|{new_record_url},主播: {anchor_name.strip()}"
                                )
                                not_record_list.append(new_record_url)
                            else:
                                need_update_line_list.append(f"{record_url}|{record_url},主播: {anchor_name.strip()}")
                            run_once = True

                        push_at = datetime.datetime.today().strftime("%Y-%m-%d %H:%M:%S")
                        if not port_info.get("is_live", False):
                            if len(recording) == 0:
                                print(f"\r{record_name} 等待直播... ")

                            if start_pushed:
                                if over_show_push:
                                    push_content = "直播间状态更新：[直播间名称] 直播已结束！时间：[时间]"
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
                            content = f"\r{record_name} 正在直播中..."
                            print(content)

                            if live_status_push and not start_pushed:
                                if begin_show_push:
                                    push_content = "直播间状态更新：[直播间名称] 正在直播中，时间：[时间]"
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
                                time.sleep(push_check_seconds)
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
                            }.get(platform, "")

                            real_url = select_source_url(port_info, proxy_address, platform, cookies=platform_cookie)
                            if not real_url:
                                # 三级候选（HLS/FLV/record_url）本轮均校验失败且无末位放行：本轮放弃录制。
                                # 录制链（ffmpeg_command/title_in_name 等）假定 real_url 非空，强制进入会触发
                                # 未绑定变量异常（title_in_name）或复用上一轮残留的 ffmpeg 命令；
                                # 按常规监测间隔等待，下一轮重新解析校验。
                                logger.warning(f"{anchor_name} 本轮未获取到可用流地址，跳过录制")
                                time.sleep(max(random.randint(-5, 5) + delay_default, 0))
                                continue
                            full_path = f"{default_path}/{platform}"
                            # real_url 非空已由上方「if not real_url: continue」保证：时间戳/标题
                            # 前缀在此无条件构造。原「if real_url:」包装为恒真条件，且使录制链
                            # 依赖条件块内赋值的局部变量（basedpyright 判定 possibly unbound，
                            # 亦属「录制链不得嵌套于条件内」反模式），故移除。
                            now = datetime.datetime.today().strftime("%y%m%d_%H%M%S")
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
                                    full_path = f"{full_path}/{now[:10]}"
                                if folder_by_title and port_info.get("title"):
                                    if folder_by_time:
                                        full_path = f"{full_path}/{live_title}_{anchor_name}"
                                    else:
                                        full_path = f"{full_path}/{now[:10]}_{live_title}"
                                os.makedirs(full_path, exist_ok=True)
                            except Exception as e:
                                logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")

                            if platform not in ("自定义录制直播", "虎牙直播"):
                                if enable_https_recording and real_url.startswith("http://"):
                                    # HTTPS 录制模式：升级为 https 拉流（证书验证已在全局禁用）
                                    real_url = real_url.replace("http://", "https://")
                                elif not enable_https_recording and real_url.startswith("https://"):
                                    # HTTP 录制模式：降级为 http 拉流（无 TLS，不涉及证书验证）。
                                    # 海外平台（TikTok/YouTube 等）CDN 多为 https-only，强转 http
                                    # 必然拉流失败，检测到海外 host 时保持原样放行。
                                    if not any(pt_host in record_url for pt_host in OVERSEAS_PLATFORM_HOST):
                                        real_url = real_url.replace("https://", "http://")

                                http_record_list = ["shopee", "migu"]
                                if platform in http_record_list:
                                    real_url = real_url.replace("https://", "http://")

                            # 默认移动端 UA；虎牙/B站 等国内 CDN 拒绝移动端 UA，改用桌面 Chrome，
                            # 且与校验探针共用同一 UA（get_record_user_agent）避免校验“假绿”。
                            # 必须与 stream_select.MOBILE_UA 保持一字不差（校验与录制两端一致）。
                            user_agent = get_record_user_agent(platform) or (
                                "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 ("
                                "KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36"
                            )

                            rw_timeout = "15000000"
                            analyzeduration = "20000000"
                            probesize = "10000000"
                            bufsize = "8000k"
                            max_muxing_queue_size = "1024"
                            for pt_host in OVERSEAS_PLATFORM_HOST:
                                if pt_host in record_url:
                                    rw_timeout = "50000000"
                                    analyzeduration = "40000000"
                                    probesize = "20000000"
                                    bufsize = "15000k"
                                    max_muxing_queue_size = "2048"
                                    break

                            # FFmpeg 9.0 兼容说明：
                            # - 9.0 移除的 CLI 参数（-vsync/-top/-qphist/-filter_complex_script/
                            #   -adrift_threshold）本命令均未使用；所列参数在 9.0 全部保留。
                            # - 9.0 起 TLS 证书验证默认开启：是否插入 -tls_verify 0 由下方
                            #   get_effective_ssl_verify(platform) 统一裁决（禁用列表平台/
                            #   https 录制模式跳过校验，其余保持默认严格校验）。
                            # - 原命令中冗余的「-v verbose」已移除：其后的 -loglevel error
                            #   会覆盖之，属死参数。
                            ffmpeg_command = [
                                "ffmpeg",
                                "-y",
                                "-rw_timeout",
                                rw_timeout,
                                "-loglevel",
                                "error",
                                "-hide_banner",
                                "-user_agent",
                                user_agent,
                                "-protocol_whitelist",
                                "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
                                "-thread_queue_size",
                                "1024",
                                "-analyzeduration",
                                analyzeduration,
                                "-probesize",
                                probesize,
                                "-fflags",
                                "+discardcorrupt",
                                "-re",
                                "-i",
                                real_url,
                                "-bufsize",
                                bufsize,
                                "-sn",
                                "-dn",
                                "-reconnect_delay_max",
                                "60",
                                "-reconnect_streamed",
                                "-reconnect_at_eof",
                                "-max_muxing_queue_size",
                                max_muxing_queue_size,
                                "-correct_ts_overflow",
                                "1",
                                "-avoid_negative_ts",
                                "1",
                            ]

                            headers = get_record_headers(platform, record_url, cookies=platform_cookie)
                            if headers:
                                # ffmpeg 的 -headers 支持多行（\r\n 分隔）多个头；
                                # 合并 referer/origin 与 cookie，与校验探针保持一致。
                                header_blob = "\r\n".join(f"{k}:{v}" for k, v in headers.items())
                                ffmpeg_command.insert(11, "-headers")
                                ffmpeg_command.insert(12, header_blob)

                            # 证书校验：ffmpeg 默认即校验（安全优先）。整合后「是否启用https录制」
                            # 统一控制：开启=https 拉流且全局禁用证书验证（此处插入 -tls_verify 0，
                            # 绕过虎牙 TX CDN 等证书主机名不匹配问题）；关闭=http 拉流不涉及证书
                            # 验证（https-only 海外平台放行时按默认严格校验）。
                            # 与校验器 / 直下路径经同一接口读取，保证一致。
                            # 注意：-tls_verify 是 tls 协议私有选项，仅 https 流有 tls 组件消费它；
                            # 对 http 流插入会报 "Option tls_verify not found" 直接录制失败
                            # （虎牙 http FLV 实测），故仅 https 地址才插入。
                            if not _http_config.get_effective_ssl_verify(platform) and (real_url or "").startswith(
                                "https://"
                            ):
                                ffmpeg_command.insert(1, "-tls_verify")
                                ffmpeg_command.insert(2, "0")

                            if proxy_address:
                                ffmpeg_command.insert(1, "-http_proxy")
                                ffmpeg_command.insert(2, proxy_address)

                            with record_state_lock:
                                recording.add(record_name)
                                start_record_time = datetime.datetime.now()
                                actual_quality_value = port_info.get("actual_quality")
                                actual_quality_code: str | None = (
                                    actual_quality_value if isinstance(actual_quality_value, str) else None
                                )
                                actual_quality_zh = code_to_zh(actual_quality_code) if actual_quality_code else ""
                                # 降级告警：实际画质低于设置时记录日志
                                if actual_quality_code and _is_downgrade(record_quality, actual_quality_code):
                                    logger.warning(
                                        f"{record_name} 画质降级：设置 {record_quality_zh}({record_quality}) "
                                        + f"实际 {actual_quality_zh}({actual_quality_code})"
                                    )
                                recording_time_list[record_name] = [
                                    start_record_time,
                                    record_quality_zh,
                                    actual_quality_zh,
                                ]
                            rec_info = f"\r{anchor_name} 准备开始录制视频: {full_path}"
                            if show_url:
                                re_plat = ("WinkTV", "PandaTV", "ShowRoom", "CHZZK", "YouTube")
                                if platform in re_plat:
                                    logger.info(f"{platform} | {anchor_name} | 直播源地址: {port_info.get('m3u8_url')}")
                                else:
                                    logger.info(f"{platform} | {anchor_name} | 直播源地址: {real_url}")

                            only_flv_record = False
                            only_flv_platform_list = ["shopee", "花椒直播"]
                            if platform in only_flv_platform_list:
                                logger.debug(f"提示: {platform} 将强制使用FLV格式录制")
                                only_flv_record = True

                            only_audio_record = False
                            only_audio_platform_list = ["猫耳FM直播", "Look直播"]
                            if platform in only_audio_platform_list:
                                only_audio_record = True

                            record_save_type = video_save_type

                            if real_url == port_info.get("flv_url") and port_info.get("flv_url"):
                                codec = utils.get_query_params(cast(str, port_info["flv_url"]), "codec")
                                if isinstance(codec, list) and codec and codec[0] == "h265":
                                    logger.warning("FLV is not supported for h265 codec, use TS format instead")
                                    record_save_type = "TS"

                            if only_audio_record or any(i in record_save_type for i in ["MP3", "M4A"]):
                                try:
                                    now = time.strftime("%y%m%d_%H%M%S", time.localtime())
                                    extension = "mp3" if "m4a" not in record_save_type.lower() else "m4a"
                                    name_format = "_%02d" if split_video_by_time else "_00"
                                    save_file_path = (
                                        f"{full_path}/{anchor_name}_{title_in_name}{now}" f"{name_format}.{extension}"
                                    )

                                    if split_video_by_time:
                                        print(f"\r{anchor_name} 准备开始录制音频: {save_file_path}")

                                        if "MP3" in record_save_type:
                                            command = [
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
                                                "-reset_timestamps",
                                                "1",
                                                save_file_path,
                                            ]
                                        else:
                                            command = [
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
                                                "mpegts",
                                                "-reset_timestamps",
                                                "1",
                                                save_file_path,
                                            ]

                                    else:
                                        if "MP3" in record_save_type:
                                            command = [
                                                "-map",
                                                "0:a",
                                                "-c:a",
                                                "libmp3lame",
                                                "-ab",
                                                "320k",
                                                save_file_path,
                                            ]

                                        else:
                                            command = [
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

                                    ffmpeg_command.extend(command)
                                    comment_end = check_subprocess(
                                        record_name,
                                        record_url,
                                        ffmpeg_command,
                                        record_save_type,
                                        custom_script,
                                        platform=platform,
                                        danmaku_args=record_danmaku_args,
                                    )
                                    if comment_end:
                                        return

                                except subprocess.CalledProcessError as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                    record_error(record_host)

                            elif only_flv_record:
                                logger.info(f"Use Direct Downloader to Download FLV Stream: {record_url}")
                                filename = anchor_name + f"_{title_in_name}" + now + "_00" + ".flv"
                                save_file_path = f"{full_path}/{filename}"
                                print(f"{rec_info}/{filename}")

                                subs_file_path = save_file_path.rsplit(".", maxsplit=1)[0]
                                subs_thread_name = f"subs_{Path(subs_file_path).name}"
                                if create_time_file:
                                    create_var[subs_thread_name] = threading.Thread(
                                        target=generate_subtitles, args=(record_name, subs_file_path)
                                    )
                                    create_var[subs_thread_name].daemon = True
                                    create_var[subs_thread_name].start()

                                try:
                                    flv_url = port_info.get("flv_url")
                                    if isinstance(flv_url, str) and flv_url:
                                        # 先持锁写入录制状态，再调用阻塞式下载（避免持锁期间长时间阻塞迭代共享状态的其他线程）
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
                                                    f"{record_name} 画质降级：设置 {record_quality_zh}({record_quality}) "
                                                    + f"实际 {actual_quality_zh}({actual_quality_code})"
                                                )
                                            recording_time_list[record_name] = [
                                                start_record_time,
                                                record_quality_zh,
                                                actual_quality_zh,
                                            ]

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
                                                f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制完成\n"
                                            )
                                            # 直下路径无 check_subprocess 退出码反馈：成功按 host 补样本，
                                            # 与 ffmpeg 路径语义对齐
                                            record_success(record_host)
                                        elif record_url not in url_comments and not exit_recording:
                                            # 真-失败（CDN 拒绝非 200 / 网络异常在函数内部已消化成 False，
                                            # 走不到外层 except 的 record_error）必须在此上报，否则坏线路
                                            # 绕开按 host 熔断统计被无限重撞；被注释/退出标志的中断不计样本
                                            record_error(record_host)

                                        with record_state_lock:
                                            recording.discard(record_name)
                                            recording_time_list.pop(record_name, None)
                                    else:
                                        logger.debug("未找到FLV直播流，跳过录制")
                                except Exception as e:
                                    clear_record_info(record_name, record_url)
                                    color_obj.print_colored(
                                        f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n",
                                        color_obj.RED,
                                    )
                                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                    record_error(record_host)

                            elif record_save_type == "FLV":
                                filename = anchor_name + f"_{title_in_name}" + now + "_00" + ".flv"
                                print(f"{rec_info}/{filename}")
                                save_file_path = full_path + "/" + filename

                                try:
                                    if split_video_by_time:
                                        now = time.strftime("%y%m%d_%H%M%S", time.localtime())
                                        save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.flv"
                                        command = [
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
                                            "flv",
                                            "-reset_timestamps",
                                            "1",
                                            save_file_path,
                                        ]

                                    else:
                                        command = [
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
                                            "{path}".format(path=save_file_path),
                                        ]
                                    ffmpeg_command.extend(command)

                                    comment_end = check_subprocess(
                                        record_name,
                                        record_url,
                                        ffmpeg_command,
                                        record_save_type,
                                        custom_script,
                                        platform=platform,
                                        danmaku_args=record_danmaku_args,
                                    )
                                    if comment_end:
                                        return

                                except subprocess.CalledProcessError as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                    record_error(record_host)

                                try:
                                    if converts_to_mp4 and split_video_by_time:
                                        # FLV 分段产物是 <前缀>_%03d.flv 模式串对应的多个文件，
                                        # 逐段转码为同名 .mp4（原 segment_video 对模式串 os.path.exists
                                        # 恒为 False，整条转换路径是死代码）
                                        # flv 源文件 glob 模式：与 mp4 输出同前缀，匹配所有编号分段
                                        seg_pattern = f"{anchor_name}_{title_in_name}{now}_*.flv"
                                        seg_files = sorted(Path(full_path).glob(seg_pattern))
                                        if not seg_files:
                                            logger.warning(f"未找到分段 FLV 文件，跳过转换: {seg_pattern}")
                                        for seg_file in seg_files:
                                            converts_mp4(str(seg_file), delete_origin_file)
                                    elif converts_to_mp4:
                                        threading.Thread(
                                            target=converts_mp4, args=(save_file_path, delete_origin_file)
                                        ).start()
                                except Exception as e:
                                    logger.error(f"转码失败: {e} ")

                            elif record_save_type == "MKV":
                                filename = anchor_name + f"_{title_in_name}" + now + ".mkv"
                                print(f"{rec_info}/{filename}")
                                save_file_path = full_path + "/" + filename

                                try:
                                    if split_video_by_time:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mkv"
                                        command = [
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
                                            "matroska",
                                            "-reset_timestamps",
                                            "1",
                                            save_file_path,
                                        ]

                                    else:
                                        command = [
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
                                            "{path}".format(path=save_file_path),
                                        ]
                                    ffmpeg_command.extend(command)

                                    comment_end = check_subprocess(
                                        record_name,
                                        record_url,
                                        ffmpeg_command,
                                        record_save_type,
                                        custom_script,
                                        platform=platform,
                                        danmaku_args=record_danmaku_args,
                                    )
                                    if comment_end:
                                        return

                                except subprocess.CalledProcessError as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                    record_error(record_host)

                            elif record_save_type == "MP4":
                                filename = anchor_name + f"_{title_in_name}" + now + ".mp4"
                                print(f"{rec_info}/{filename}")
                                save_file_path = full_path + "/" + filename

                                try:
                                    if split_video_by_time:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mp4"
                                        command = [
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
                                            "mp4",
                                            "-reset_timestamps",
                                            "1",
                                            "-movflags",
                                            "+frag_keyframe+empty_moov",
                                            save_file_path,
                                        ]

                                    else:
                                        command = [
                                            "-map",
                                            "0",
                                            "-c:v",
                                            "copy",
                                            "-c:a",
                                            "copy",
                                            "-f",
                                            "mp4",
                                            save_file_path,
                                        ]

                                    ffmpeg_command.extend(command)
                                    comment_end = check_subprocess(
                                        record_name,
                                        record_url,
                                        ffmpeg_command,
                                        record_save_type,
                                        custom_script,
                                        platform=platform,
                                        danmaku_args=record_danmaku_args,
                                    )
                                    if comment_end:
                                        return

                                except subprocess.CalledProcessError as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                    record_error(record_host)

                            else:
                                if split_video_by_time:
                                    now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                    filename = anchor_name + f"_{title_in_name}" + now + ".ts"
                                    print(f"{rec_info}/{filename}")

                                    try:
                                        save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.ts"
                                        command = [
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
                                            # 音频分段用 ipod 容器（即 .m4a），而非 mpegts：
                                            # 原实现强制 mpegts 但输出扩展名为 .m4a，容器与扩展名不符
                                            "-segment_format",
                                            "ipod",
                                            "-reset_timestamps",
                                            "1",
                                            save_file_path,
                                        ]

                                        ffmpeg_command.extend(command)
                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script,
                                            platform=platform,
                                            danmaku_args=record_danmaku_args,
                                        )
                                        if comment_end:
                                            if converts_to_mp4:
                                                file_paths = utils.get_file_paths(os.path.dirname(save_file_path))
                                                prefix = os.path.basename(save_file_path).rsplit("_", maxsplit=1)[0]
                                                for path in file_paths:
                                                    if prefix in path:
                                                        try:
                                                            threading.Thread(
                                                                target=converts_mp4, args=(path, delete_origin_file)
                                                            ).start()
                                                        except subprocess.CalledProcessError as e:
                                                            logger.error(f"转码失败: {e} ")
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error(record_host)

                                else:
                                    filename = anchor_name + f"_{title_in_name}" + now + ".ts"
                                    print(f"{rec_info}/{filename}")
                                    save_file_path = full_path + "/" + filename

                                    try:
                                        command = [
                                            "-c:v",
                                            "copy",
                                            "-c:a",
                                            "copy",
                                            "-map",
                                            "0",
                                            "-f",
                                            "mpegts",
                                            save_file_path,
                                        ]

                                        ffmpeg_command.extend(command)
                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script,
                                            platform=platform,
                                            danmaku_args=record_danmaku_args,
                                        )
                                        if comment_end:
                                            threading.Thread(
                                                target=converts_mp4, args=(save_file_path, delete_origin_file)
                                            ).start()
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error(record_host)

                            count_time = time.time()
                            # 样本改由各录制路径按实际结果上报（check_subprocess 按退出码记成功/失败，
                            # 直下路径按下载结果记）：旧的「轮末无条件记成功」会把 ffmpeg 失败轮
                            # （如 CDN 403 秒退）也记成成功样本，稀释按 host 熔断统计——多房间
                            # 同 host 时失败率永远到不了熔断阈值，坏线路被无限重撞。

                except Exception as e:
                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                    record_error(record_host)

                num = random.randint(-5, 5) + delay_default
                if num < 0:
                    num = 0
                x = num

                if sum(error_window) >= 5:
                    x = x + 60
                    color_obj.print_colored("\r瞬时错误太多,延迟加60秒", color_obj.YELLOW)

                # 这里是.如果录制结束后,循环时间会暂时变成30s后检测一遍. 这样一定程度上防止主播卡顿造成少录
                # 当30秒过后检测一遍后. 会回归正常设置的循环秒数
                if record_finished:
                    count_time_end = time.time() - count_time
                    if count_time_end < 60:
                        x = 30
                    record_finished = False

                else:
                    x = num

                # 这里是正常循环
                while x:
                    x = x - 1
                    if loop_time:
                        print(f"\r{anchor_name}循环等待{x}秒 ", end="")
                    time.sleep(1)
                if loop_time:
                    print("\r检测直播间中...", end="")
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
            record_error(record_host)
            time.sleep(2)
        finally:
            # 房间线程退出（URL 被注释/移除/收到退出标志触发 return）：从弹幕监控枢纽
            # 移除该房间，监控页不再残留已失效直播间与旧弹幕数据；同房间重新录制时
            # 由 collector.start() 的 room_started 重新注册。监控为旁路功能，清理失败静默。
            if record_name:
                try:
                    from src.danmaku_monitor import get_hub

                    get_hub().room_stopped(record_name, "房间已停止录制")
                except Exception:
                    pass


# 打印本机 ffmpeg 版本信息并检测其可用性（缺失时由 check_ffmpeg 触发下载安装）；无入参，返回 ffmpeg 是否可用
def check_ffmpeg_existence() -> bool:
    # 检查 FFmpeg 是否可用，不可用则触发安装
    ffmpeg_exists = False
    try:
        result = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        # check=True 已保证 returncode==0，直接打印版本信息
        lines = result.stdout.splitlines()
        version_line = lines[0] if lines else "unknown"
        built_line = lines[1] if len(lines) > 1 else ""
        print(version_line)
        if built_line:
            print(built_line)
    except subprocess.CalledProcessError as e:
        logger.error(e)
    except FileNotFoundError:
        pass
    if check_ffmpeg():
        ffmpeg_exists = True
    return ffmpeg_exists


# --------------------------初始化程序-------------------------------------
print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(f"版本号: {version}")
print("GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(f"支持平台: {platforms}")
print(".....................................................")
# 不再在模块级执行 check_ffmpeg_existence()：import main（web.py/gui.py/测试/工具）不应触发
# 111MB 的 FFmpeg 下载副作用。安装检查统一由各真实入口的 main() 完成（CLI/Web 录制线程）。
os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()
# URL_config.ini 去重已移入 main() 入口执行：import main 不应改写用户配置文件


options: dict[str, bool] = {"是": True, "否": False}
config: configparser.RawConfigParser = configparser.RawConfigParser()


_config_read_result = config.read(config_file, encoding=text_encoding)


# 读取语言配置键 language：值留空则「跟随系统语言」，由 i18n.resolve_language 兜底
# 返回原始配置值；不可识别或语言目录文件缺失的兜底由 i18n 统一处理。
def _read_language_config(config_parser: configparser.RawConfigParser) -> str:
    return read_config_value(config_parser, "录制设置", "language", "")


language = _read_language_config(config)
# i18n 多语言初始化：resolve_language 统一解析——空 → 系统语言；键值不可识别或
# 语言目录文件缺失 → en_US 回退；随后加载对应翻译目录（gettext .mo / JSON / YAML，
# 见 i18n.py），后续输出即时按该语言翻译
from i18n import resolve_language as _i18n_resolve
from i18n import set_language as _i18n_set_language

language = _i18n_resolve(language)
_i18n_set_language(language)
skip_proxy_check = options.get(read_config_value(config, "录制设置", "是否跳过代理检测(是/否)", "否"), False)


def _read_https_recording_config(config_parser: configparser.RawConfigParser) -> bool:
    # 读取「是否启用https录制」（已整合原「是否强制启用https录制」与
    # 「是否禁用SSL证书验证(是/否)」两项功能）：
    # 1) 新键存在 → 直接取值；
    # 2) 新键缺失、旧键「是否强制启用https录制」存在 → 继承旧键值，并把该值
    #    迁移写回新键（保证 Web 配置页可见可编辑）；旧键本身只读、绝不重建；
    # 3) 两者皆无 → read_config_value 补写新键默认值「否」（保持配置自愈）。
    if config_parser.has_option("录制设置", "是否启用https录制"):
        return options.get(config_parser.get("录制设置", "是否启用https录制").strip(), False)
    if config_parser.has_option("录制设置", "是否强制启用https录制"):
        legacy = options.get(config_parser.get("录制设置", "是否强制启用https录制").strip(), False)
        return options.get(
            read_config_value(config_parser, "录制设置", "是否启用https录制", "是" if legacy else "否"), False
        )
    return options.get(read_config_value(config_parser, "录制设置", "是否启用https录制", "否"), False)


# SSL/HTTPS 整合开关：「是否启用https录制」合并原「是否强制启用https录制」（协议强转）
# 与「是否禁用SSL证书验证(是/否)」（证书校验）两个配置项，统一为单一二元语义：
# 开启 = 流地址升级 https 拉流，并禁用 SSL 证书验证（保证 https 录制不被 CDN 证书
#        主机名不匹配等问题阻断，即原「是否禁用SSL证书验证=是」的功能）；
# 关闭 = 流地址降级 http 拉流（无 TLS 不涉及证书验证），API 等请求恢复默认严格校验。
# 该开关由 main() 主循环每轮读取配置后同步（热更新）。
from src import http_config as _http_config

enable_https_recording = _read_https_recording_config(config)
_http_config.set_https_recording(enable_https_recording)
_http_config.set_ssl_verify(not enable_https_recording)
# 旧全局开关仅作迁移提示（只读，不写回）：检测到旧键=是 时告知功能已并入新开关
if config.has_option("录制设置", "是否禁用SSL证书验证(是/否)"):
    if options.get(config.get("录制设置", "是否禁用SSL证书验证(是/否)").strip(), False):
        print("提示: 「是否禁用SSL证书验证(是/否)」已整合进「是否启用https录制」，旧配置项不再生效")
# 平台级 SSL 覆盖：「禁用SSL证书验证的平台(逗号分隔)」列表。
# FFmpeg 9.0 起 TLS 证书验证默认开启（8.0 预告、9.0 落地），http 录制模式下
# https-only 流地址也会被默认校验证书——该列表经 http_config.get_effective_ssl_verify
# 仅在全局需要证书校验（ssl_verify=True）时生效，让证书异常平台跳过校验仍可拉流。
# 需禁用 SSL 验证的平台（分析全部可监控录制平台的流/接口证书得出）：
# - 虎牙直播：hw/TX CDN 流地址证书与拉流域名主机名不匹配（原独立配置键
#   「虎牙是否禁用SSL证书验证(是/否)」的存在原因），严格校验直接拉流失败；
# - B站直播：部分 CDN 节点证书链异常。
# 启动时自动把缺失项追加至配置键值（只追加、绝不移除用户手填的平台）。
SSL_DISABLE_REQUIRED_PLATFORMS: tuple[str, ...] = ("虎牙直播", "B站直播")


# 分析可监控的录制平台网址、识别需禁用 SSL 验证的平台并自动追加至该键值；
# 入参为已读取的配置解析器，返回合并后的平台集合（含用户原有手填项）
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
            logger.warning(f"自动追加需禁用SSL验证的平台 {appended} 写回配置失败（已忽略，内存态仍生效）")
        # 同步内存解析器，避免本轮后续读取拿到旧值
        config_parser.set("录制设置", "禁用SSL证书验证的平台(逗号分隔)", new_value)
        print(f"提示: 已自动追加需禁用SSL证书验证的平台: {','.join(appended)}")
    return set(kept + appended)


_ssl_disable_platforms = _sync_ssl_disable_platforms(config)
# 兼容旧版单列配置：虎牙是否禁用SSL证书验证(是/否)=是 → 等价于把「虎牙直播」加入列表。
# 注意：仅当旧键实际存在时才读取，绝不写回——旧键只应被读、不应被自动重建，
# 否则迁移后的配置旧键缺失反而触发「缺键→写回→不可写→崩溃」的坏兼容。
if config.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
    if options.get(config.get("录制设置", "虎牙是否禁用SSL证书验证(是/否)").strip(), False):
        _ssl_disable_platforms.add("虎牙直播")
for _p in _ssl_disable_platforms:
    _http_config.set_platform_ssl_verify(_p, False)
# 翻译包装不再按语言门控：任何语言下都安装 translated_print——
# zh_CN/zh_TW 把英文常量串译为中文；en_US/en_GB 把中文串译为英文；
# 未知串恒等返回，无额外代价。语言经 i18n.set_language 热切换（Web/GUI 即时生效）。
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


# 程序主入口（CLI 直跑与 web.py 守护线程共用）：先校验 ffmpeg，随后死循环「热加载 config.ini →
# 检查磁盘余量 → 解析并清理 URL_config.ini → 为每个新增直播间拉起 start_record 线程」；
# non_interactive=True 时 URL 配置为空不阻塞等待 input（供 Web 模式使用）；无返回值
def main(non_interactive: bool = False) -> None:
    # 录制主循环：读取配置 → 调度录制线程 → 热加载配置。
    #
    #     被 main.py 直接运行时调用，也被 web.py 在守护线程中调用。
    #     global 声明由重构脚本依据原模块级赋值自动生成，保持语义不变。
    #     若 non_interactive=True（如 web.py 守护线程），URL_config 为空时跳过 input() 阻塞。
    #
    global a, acfun_cookie, args, auto_update_anchor_name, baidu_cookie, bark_msg_api, bark_msg_level, bark_msg_ring, begin_push_message_text, begin_show_push, bigo_cookie, bili_cookie, blued_cookie
    global changliao_cookie, check_path, chzzk_cookie, clean_emoji, converts_to_h264, converts_to_mp4, create_time_file, custom_script, delay_default, delete_origin_file, dingtalk_api_url, danmaku_platforms, danmaku_split_time, enable_danmaku, enable_danmaku_monitor
    global dingtalk_is_atall, dingtalk_phone_num, disable_record, disk_space_limit, douyu_cookie, dy_cookie, email_host, email_password, enable_https_recording, enable_proxy_platform, enable_proxy_platform_list, exit_recording
    global extra_enable_proxy, extra_enable_proxy_platform_list, faceit_cookie, filename_by_title, first_run, first_start, flextv_cookie, flextv_password, flextv_username, folder_by_author, folder_by_time, folder_by_title
    global haixiu_cookie, hls_collection_enabled, host_id, huajiao_cookie, huamao_cookie, hy_cookie, ini_URL_content, input_url, is_comment_line, is_run_script, jd_cookie, ks_cookie, kugou_cookie
    global laixiu_cookie, langlive_cookie, language, lehaitv_cookie, lianjie_cookie, line, line_list, line_spilt, liuxing_cookie, live_status_push, liveme_cookie, local_delay_default, login_email
    global look_cookie, loop_time, maoerfm_cookie, max_request, middle, migu_cookie, monitoring, name, netease_cookie, new_line, new_url, new_word
    global ntfy_api, ntfy_email, ntfy_tags, open_smtp_ssl, origin_line, over_push_message_text, over_show_push, pandatv_cookie, picarto_cookie, popkontv_access_token, popkontv_partner_code, popkontv_password
    global popkontv_username, pplive_cookie, proxy_addr, proxy_addr_bak, push_check_seconds, push_message_title, pushplus_token, qiandurebo_cookie, quality, replace_words, running_snapshot, running_url
    global seen_urls, semaphore, sender_email, sender_name, shopee_cookie, show_url, showroom_cookie, six_room_cookie, smtp_port, sooplive_cookie, sooplive_password, sooplive_username
    global scheduler, recording_semaphore
    global split_line, split_time, split_video_by_time, start_with, t, t2, taobao_cookie, text_no_repeat_url, tg_chat_id, tg_token, tiktok_cookie, to_email
    global twitcasting_account_type, twitcasting_cookie, twitcasting_password, twitcasting_username, twitch_cookie, url, url_comments, url_host, url_line_list, url_tuple, url_tuples_list, use_proxy
    global video_record_quality, video_save_path, video_save_type, video_save_type_list, vvxqiu_cookie, weibo_cookie, winktv_cookie, xhs_cookie, xizhi_api_url, yinbo_cookie, yingke_cookie, yiqilive_cookie
    global youtube_cookie, yy_cookie, zhihu_cookie

    # FFmpeg 网关：原模块级 sys.exit(1) 会在 import main 时杀死 uvicorn（I7），
    # 故移到 main() 入口；缺失时打印警告并 return，守护线程干净退出，Web 面板继续服务。
    # 直接运行 `python main.py` 时同样从这里退出而非 sys.exit，避免硬退出。
    if not check_ffmpeg_existence():
        logger.error("缺少ffmpeg无法进行录制，程序退出")
        return

    # 启动时清理 URL_config.ini 重复行（原为模块级副作用，移入入口处执行）
    if os.path.isfile(url_config_file):
        utils.remove_duplicate_lines(url_config_file)

    # 初始化并发调度器（自适应全局容量 + 按平台熔断降级 + 可选录制并发软上限）。
    # 在 while 循环前创建，确保 start_record 线程启动前 scheduler/semaphore 已就绪。
    if scheduler is None:
        scheduler = ConcurrencyScheduler(configured_limit=max_request)
        semaphore = scheduler.network_semaphore
        recording_semaphore = scheduler.recording_semaphore

    while True:

        try:
            if not os.path.isfile(config_file):
                with open(config_file, "w", encoding=text_encoding) as file:
                    pass

            # 每轮重新读取配置文件，支持运行期间热更新；
            # 持锁读取避免与录制线程的 update_config 并发读到半写文件
            with file_update_lock:
                _ = config.read(config_file, encoding=text_encoding)

            ini_URL_content = ""
            if os.path.isfile(url_config_file):
                with open(url_config_file, "r", encoding=text_encoding) as file:
                    ini_URL_content = file.read().strip()

            if not ini_URL_content.strip():
                if non_interactive:
                    # 非交互模式（如 web.py 守护线程）：跳过阻塞，等待 Web API 写入 URL
                    time.sleep(5)
                    continue
                input_url = input("请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n")
                with open(url_config_file, "w", encoding=text_encoding) as file:
                    _ = file.write(input_url)
        except (OSError, configparser.Error) as err:
            logger.error(f"发生 I/O 或配置解析错误: {err}")
            time.sleep(3)

        video_save_path = read_config_value(config, "录制设置", "直播保存路径(不填则默认)", "")
        folder_by_author = options.get(read_config_value(config, "录制设置", "保存文件夹是否以作者区分", "是"), False)
        folder_by_time = options.get(read_config_value(config, "录制设置", "保存文件夹是否以时间区分", "否"), False)
        folder_by_title = options.get(read_config_value(config, "录制设置", "保存文件夹是否以标题区分", "否"), False)
        filename_by_title = options.get(read_config_value(config, "录制设置", "保存文件名是否包含标题", "否"), False)
        clean_emoji = options.get(read_config_value(config, "录制设置", "是否去除名称中的表情符号", "是"), True)
        auto_update_anchor_name = options.get(
            read_config_value(config, "录制设置", "是否自动更新主播名(是/否)", "是"), True
        )
        video_save_type = read_config_value(config, "录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
        video_record_quality = read_config_value(config, "录制设置", "原画|超清|高清|标清|流畅", "原画")
        hls_collection_enabled = options.get(
            read_config_value(config, "录制设置", "是否启用HLS采集(是/否)", "是"), True
        )
        use_proxy = options.get(read_config_value(config, "录制设置", "是否使用代理ip(是/否)", "是"), False)
        proxy_addr_bak = read_config_value(config, "录制设置", "代理地址", "")
        proxy_addr = None if not use_proxy else proxy_addr_bak
        # 仅在配置值变化时更新并发调度器：该值在动态模式下作为容量下限之一（容量随活跃任务数
        # 缩放、带安全下限），固定模式下即并发限制本身（见下方并发模式解析）；
        # 不再每轮重建信号量（旧逻辑会因实例替换导致并发计数失效、上限形同虚设）
        new_max_request = _safe_int(read_config_value(config, "录制设置", "同一时间访问网络的线程数", 3), 3)
        if new_max_request != max_request:
            max_request = new_max_request
            if scheduler is not None:
                scheduler.set_configured_limit(new_max_request)
            logger.debug(f"并发线程数配置更新为 {max_request}")
        # 录制并发软上限（资源治理）：0=不限制；>0 时限制同时 ffmpeg 录制数，防资源耗尽。
        # 键名不得含 = / : 等 configparser 分隔符：读取会在首个分隔符处截断（永远查不到键），
        # 写回会抛 InvalidWriteError（Python 3.13+ 禁止键名含分隔符）——曾致启动即崩溃
        new_recording_limit = _safe_int(read_config_value(config, "录制设置", "最大同时录制数(0为不限制)", 0), 0)
        if scheduler is not None and new_recording_limit != scheduler.recording_limit:
            scheduler.set_recording_limit(new_recording_limit)
        # 并发模式解析：该配置项兼作模式开关——为 0 时启用动态调速器（网络容量随活跃任务数自适应，
        # 带安全上下限）；非 0 时忽略动态调速器，固定使用「同一时间访问网络的线程数」作为并发限制
        # （最小 1 个槽位）。set_dynamic_mode 内部幂等（模式未变不重复播报），可每轮安全调用；
        # 同时录制上限语义不变（仍由上方 set_recording_limit 管控 ffmpeg 数量）
        if scheduler is not None:
            scheduler.set_dynamic_mode(new_recording_limit == 0)
        delay_default = _safe_int(read_config_value(config, "录制设置", "循环时间(秒)", 120), 120)
        local_delay_default = _safe_int(read_config_value(config, "录制设置", "排队读取网址时间(秒)", 0), 0)
        loop_time = options.get(read_config_value(config, "录制设置", "是否显示循环秒数", "否"), False)
        show_url = options.get(read_config_value(config, "录制设置", "是否显示直播源地址", "否"), False)
        # 语言热切换：配置变化时即时重载翻译目录（Web 面板/GUI 改语言后下轮循环生效），
        # 无需重启进程；录制中的 ffmpeg 子进程不受影响，仅影响新产生的控制台输出。
        # 空/未识别/语言目录缺失经 resolve_language 统一兜底（与启动初始化同语义）
        _new_language = _i18n_resolve(read_config_value(config, "录制设置", "language", ""))
        if _new_language != language:
            language = _new_language
            _i18n_set_language(_new_language)
            print(f"语言已切换: {_new_language}")
        split_video_by_time = options.get(read_config_value(config, "录制设置", "分段录制是否开启", "否"), False)
        enable_https_recording = _read_https_recording_config(config)
        # 整合联动（与模块级初始化同语义）：开启 = https 拉流 + 禁用 SSL 证书验证；
        # 关闭 = http 拉流 + 恢复默认证书校验。每轮同步以支持运行期间热更新
        # （Web 面板改配置后下轮循环即生效）。
        _http_config.set_https_recording(enable_https_recording)
        _http_config.set_ssl_verify(not enable_https_recording)
        disk_space_limit = _safe_float(read_config_value(config, "录制设置", "录制空间剩余阈值(gb)", 1.0), 1.0)
        split_time = str(read_config_value(config, "录制设置", "视频分段时间(秒)", 1800))
        converts_to_mp4 = options.get(read_config_value(config, "录制设置", "录制完成后自动转为mp4格式", "否"), False)
        converts_to_h264 = options.get(read_config_value(config, "录制设置", "mp4格式重新编码为h264", "否"), False)
        delete_origin_file = options.get(read_config_value(config, "录制设置", "追加格式后删除原文件", "否"), False)
        create_time_file = options.get(read_config_value(config, "录制设置", "生成时间字幕文件", "否"), False)
        is_run_script = options.get(read_config_value(config, "录制设置", "是否录制完成后执行自定义脚本", "否"), False)
        custom_script = read_config_value(config, "录制设置", "自定义脚本执行命令", "") if is_run_script else None
        enable_proxy_platform = read_config_value(
            config,
            "录制设置",
            "使用代理录制的平台(逗号分隔)",
            "tiktok, soop, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit",
        )
        enable_danmaku = options.get(read_config_value(config, "录制设置", "是否录制弹幕(是/否)", "否"), False)
        enable_danmaku_monitor = options.get(read_config_value(config, "录制设置", "是否弹幕监控(是/否)", "否"), False)
        danmaku_split_time = _safe_float(read_config_value(config, "录制设置", "弹幕分片时长(秒)", 1800), 1800.0)
        danmaku_platforms_str = read_config_value(
            config, "录制设置", "弹幕录制平台(逗号分隔)", "斗鱼直播,B站直播,虎牙直播,抖音直播,TwitchTV"
        )
        danmaku_platforms = danmaku_platforms_str.replace("，", ",").split(",") if danmaku_platforms_str else []
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
        dingtalk_is_atall = options.get(read_config_value(config, "推送配置", "钉钉通知@全体(是/否)", "否"), False)
        tg_token = read_config_value(config, "推送配置", "tgapi令牌", "")
        tg_chat_id = read_config_value(config, "推送配置", "tg聊天id(个人或者群组id)", "")
        email_host = read_config_value(config, "推送配置", "SMTP邮件服务器", "")
        open_smtp_ssl = options.get(read_config_value(config, "推送配置", "是否使用SMTP服务SSL加密(是/否)", "是"), True)
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
        disable_record = options.get(read_config_value(config, "推送配置", "只推送通知不录制(是/否)", "否"), False)
        push_check_seconds = _safe_int(read_config_value(config, "推送配置", "直播推送检测频率(秒)", 1800), 1800)
        begin_show_push = options.get(read_config_value(config, "推送配置", "开播推送开启(是/否)", "是"), True)
        over_show_push = options.get(read_config_value(config, "推送配置", "关播推送开启(是/否)", "否"), False)
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
        try:
            # 自定义保存路径可能尚不存在，shutil.disk_usage 会抛 FileNotFoundError
            os.makedirs(check_path, exist_ok=True)
            disk_free_gb = utils.check_disk_capacity(check_path, show=first_run)
        except Exception as e:
            logger.warning(f"磁盘空间检测失败（跳过限制检查）: {type(e).__name__}: {e}")
            disk_free_gb = float("inf")
        if disk_free_gb < disk_space_limit:
            exit_recording = True
            if not recording:
                logger.warning(
                    f"Disk space remaining is below {disk_space_limit} GB. "
                    + "Exiting program due to the disk space limit being reached."
                )
                sys.exit(-1)

        try:
            url_comments = []
            line_list = []
            url_line_list = []
            seen_urls = set()
            with open(url_config_file, "r", encoding=text_encoding, errors="ignore") as file:
                for origin_line in file:
                    if origin_line in line_list:
                        delete_line(url_config_file, origin_line)
                    line_list.append(origin_line)
                    line = origin_line.strip()
                    if len(line) < 18:
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

                    if len(split_line) == 1:
                        url = split_line[0]
                        quality, name = [video_record_quality, ""]
                    elif len(split_line) == 2:
                        if contains_url(split_line[0]):
                            quality = video_record_quality
                            url, name = split_line
                        else:
                            quality, url = split_line
                            name = ""
                    else:
                        quality, url, name = split_line

                    if quality not in ("原画", "蓝光", "超清", "高清", "标清", "流畅"):
                        quality = "原画"

                    if url not in url_line_list:
                        url_line_list.append(url)
                    else:
                        delete_line(url_config_file, origin_line)

                    url = "https://" + url if "://" not in url else url
                    url_host = url.split("/")[2]

                    if "live.shopee." in url_host or ".shp.ee" in url_host:
                        url_host = "live.shopee." if "live.shopee." in url_host else ".shp.ee"

                    if url_host in PLATFORM_HOST or any(ext in url for ext in (".flv", ".m3u8")):
                        if url_host in CLEAN_URL_HOST_LIST:
                            url = update_file(url_config_file, old_str=url, new_str=url.split("?")[0]) or url

                        if "xiaohongshu" in url:
                            host_id = re.search("&host_id=(.*?)(?=&|$)", url)
                            if host_id:
                                new_url = url.split("?")[0] + f"?host_id={host_id.group(1)}"
                                url = update_file(url_config_file, old_str=url, new_str=new_url) or url
                        seen_urls.add(url)
                        url_comments = [i for i in url_comments if url not in i]
                        if is_comment_line:
                            url_comments.append(url)
                        else:
                            new_line = (quality, url, name)
                            url_tuples_list.append(new_line)
                    else:
                        if not origin_line.startswith("#"):
                            color_obj.print_colored(
                                f"\r{origin_line.strip()} 本行包含未知链接.此条跳过", color_obj.YELLOW
                            )
                            _ = update_file(url_config_file, old_str=origin_line, new_str=origin_line, start_str="#")

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
            running_snapshot = list(running_list)
            for running_url in running_snapshot:
                if running_url not in seen_urls and running_url not in url_comments:
                    url_comments.append(running_url)

            text_no_repeat_url = list(set(url_tuples_list))

            if len(text_no_repeat_url) > 0:
                for url_tuple in text_no_repeat_url:
                    with record_state_lock:
                        monitoring = len(running_list)

                    if url_tuple[1] in not_record_list:
                        continue

                    if url_tuple[1] not in running_list and not exit_recording:
                        print(f"\r{'新增' if not first_start else '传入'}地址: {url_tuple[1]}")
                        with record_state_lock:
                            monitoring += 1
                            running_list.append(url_tuple[1])
                            args = (url_tuple, monitoring)
                        thread_key = f"thread_{monitoring}"

                        # 线程结束后从 create_var 清理，防止长期运行字典无界增长
                        # 房间录制线程入口：_key 为该线程在 create_var 中的注册键，
                        # _args 为传给 start_record 的参数元组（tuple[tuple[str,str,str], int]）。
                        # 通过 Thread(args=...) 在创建线程时绑定当前循环值，规避闭包晚期绑定陷阱；无返回值。
                        def _room_thread_target(_key: str, _args: tuple[tuple[str, str, str], int]) -> None:
                            try:
                                start_record(*_args)
                            finally:
                                with record_state_lock:
                                    create_var.pop(_key, None)

                        create_var[thread_key] = threading.Thread(
                            target=_room_thread_target,
                            name=thread_key,
                            args=(thread_key, args),
                        )
                        create_var[thread_key].daemon = True
                        create_var[thread_key].start()
                        time.sleep(local_delay_default)
            # 上报当前活跃监控数，供调度器自适应全局并发容量（解除多任务排队瓶颈）
            if scheduler is not None:
                scheduler.set_active_count(monitoring)
            url_tuples_list = []
            first_start = False

        except Exception as err:
            logger.error(f"错误信息: {err} 发生错误的行数: {_get_error_line(err)}")

        if first_run:
            t = threading.Thread(target=display_info, args=(), daemon=True)
            t.start()
            t2 = threading.Thread(target=adjust_max_request, args=(), daemon=True)
            t2.start()
            first_run = False

        time.sleep(3)


if __name__ == "__main__":
    main()
