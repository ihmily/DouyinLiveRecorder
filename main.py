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
# Author: Hmily
# GitHub: https://github.com/ihmily
# Date: 2023-07-17 23:52:05
# Update: 2025-10-23 19:48:05
# Version: v4.0.8.2
# Copyright (c) 2023-2025 by Hmily, All Rights Reserved.

# 强制标准流以 UTF-8 输出。
# 原因：冻结后的 exe 作为 GUI 子进程（stdout 是管道而非真实控制台）时，
# Python 会回退到 GBK 区域编码写输出；而 GUI 父进程按 UTF-8 读取该管道，
# 导致中文乱码（如「自动获取 Cookie ttwid 成功」变成「�Զ���ȡ����」）。
# 必须在导入任何会写日志/控制台的模块（如 src.logger）之前执行。
import os
import sys


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
from typing import cast

import httpx
from loguru import logger

from msg_push import bark, dingtalk, ntfy, pushplus, send_email, tg_bot, xizhi
from src import spider, stream, utils
from src.ffmpeg_install import check_ffmpeg, ffmpeg_path
from src.proxy import ProxyDetector


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
error_count: int = 0  # 当前错误计数
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
hls_collection_enabled: bool = True  # 是否优先使用 HLS(m3u8) 源采集；关闭时回退 FLV

# ==================== 路径和配置 ====================


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
file_update_lock: threading.Lock = threading.Lock()  # 文件更新锁（防止多线程写入冲突

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
semaphore: threading.Semaphore = threading.Semaphore(1)
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

# ==================== FFmpeg 进程管理 ====================

# 全局跟踪所有 ffmpeg 进程（用于安全退出时清理
_ffmpeg_processes: list[subprocess.Popen[bytes]] = []
_processes_lock: threading.Lock = threading.Lock()


def register_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    # 注册新启动的 ffmpeg 进程
    with _processes_lock:
        _ffmpeg_processes.append(process)


def unregister_ffmpeg_process(process: subprocess.Popen[bytes]) -> None:
    # 取消注册已结束的 ffmpeg 进程
    with _processes_lock:
        if process in _ffmpeg_processes:
            _ffmpeg_processes.remove(process)


def _terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
    # 安全地终止 ffmpeg 进程，包含多层级 fallback 机制（被多处复用，避免逻辑漂移）
    # 返回 True 表示进程已退出
    if proc.poll() is not None:
        return True
    try:
        # 第一步：尝试正常退出（发送 q 命令或 SIGINT）
        if os.name == "nt":
            if proc.stdin:
                try:
                    _ = proc.stdin.write(b"q")
                    proc.stdin.flush()
                    proc.stdin.close()
                except Exception:
                    pass
        else:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass

        # 等待进程正常退出
        try:
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第二步：尝试终止进程
        try:
            proc.terminate()
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 第三步：强制杀死进程
        try:
            proc.kill()
            _ = proc.wait(timeout=timeout // 3)
            if proc.poll() is not None:
                return True
        except Exception:
            pass

        # 最后手段：尝试清理资源
        try:
            if proc.stdout:
                proc.stdout.close()
        except Exception:
            pass

        return proc.poll() is not None
    except Exception as e:
        logger.error(f"终止 ffmpeg 进程时出错: {e}")
        return False


def _cleanup_single_ffmpeg_process(proc: subprocess.Popen[bytes]) -> None:
    # 清理单个 ffmpeg 进程（在并行线程中调用），复用公共终止逻辑
    try:
        if proc.poll() is None:
            logger.info(f"尝试终止 ffmpeg 进程 (PID: {proc.pid})")
            _ = _terminate_ffmpeg_process(proc)
        logger.info(f"ffmpeg 进程 (PID: {proc.pid}) 已清理")
    except Exception as e:
        logger.error(f"清理 ffmpeg 进程时出错: {e}")


def cleanup_all_ffmpeg_processes() -> None:
    # 清理所有注册的 ffmpeg 进程（并行执行）
    logger.info("正在清理所有 ffmpeg 进程...")
    with _processes_lock:
        processes_to_clean = list(_ffmpeg_processes)

    if processes_to_clean:
        with ThreadPoolExecutor(max_workers=min(len(processes_to_clean), 8)) as executor:
            futures = [executor.submit(_cleanup_single_ffmpeg_process, proc) for proc in processes_to_clean]
            for f in as_completed(futures):
                try:
                    f.result(timeout=10)
                except Exception as e:
                    logger.debug(f"清理 ffmpeg 进程异常: {e}")

    with _processes_lock:
        _ffmpeg_processes.clear()
    logger.info("所有 ffmpeg 进程清理完成")


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


def _get_error_line(e: BaseException) -> str:
    # 从异常对象获取真正出错的行号（取 traceback 最内层帧，而非最外层）
    tb = e.__traceback__
    if not tb:
        return "unknown"
    # 遍历到 traceback 最内层，获取真正出错的行
    while tb.tb_next is not None:
        tb = tb.tb_next
    return str(tb.tb_lineno)


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


def contains_url(string: str) -> bool:
    # 检查字符串是否包含 URL
    pattern = r"(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(/.*)?"
    return re.search(pattern, string) is not None


def display_info() -> None:
    # 后台线程：刷新控制台状态显示
    global start_display_time
    time.sleep(5)
    while True:
        try:
            _ = sys.stdout.flush()
            time.sleep(5)
            if sys.stdout.isatty():
                _ = sys.stdout.write("\033[2J\033[H")
                _ = sys.stdout.flush()
            print(f"\r共监测{monitoring}个直播中", end=" | ")
            print(f"同一时间访问网络的线程数: {max_request}", end=" | ")
            print(f"是否开启代理录制: {'是' if use_proxy else '否'}", end=" | ")
            if split_video_by_time:
                print(f"录制分段开启: {split_time}秒", end=" | ")
            else:
                print("录制分段开启: 否", end=" | ")
            if create_time_file:
                print("是否生成时间文件: 是", end=" | ")
            print(f"录制视频质量为: {video_record_quality}", end=" | ")
            print(f"录制视频格式为: {video_save_type}", end=" | ")
            print(f"目前瞬时错误数为: {error_count}", end=" | ")
            now = time.strftime("%H:%M:%S", time.localtime())
            print(f"当前时间: {now}")

            if len(recording) == 0:
                time.sleep(5)
                if monitoring == 0:
                    print("\r没有正在监测和录制的直播")
                else:
                    print(f"\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒")
            else:
                now_time = datetime.datetime.now()
                print("x" * 60)
                with record_state_lock:
                    no_repeat_recording = list(set(recording))
                print(f"正在录制{len(no_repeat_recording)}个直播: ")
                for recording_live in no_repeat_recording:
                    with record_state_lock:
                        _rt_info = recording_time_list.get(recording_live, [now_time, ""])
                        rt = cast(datetime.datetime, _rt_info[0]) if _rt_info else now_time
                        qa = str(_rt_info[1]) if len(_rt_info) > 1 else ""
                    have_record_time = now_time - rt
                    print(f"{recording_live}[{qa}] 正在录制中 {str(have_record_time).split('.')[0]}")

                # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                print("x" * 60)
                start_display_time = now_time
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")


def update_file(file_path: str, old_str: str, new_str: str, start_str: str | None = None) -> str | None:
    # 安全更新文件内容（加锁防止并发写入）
    global ini_URL_content
    if old_str == new_str and start_str is None:
        return old_str
    with file_update_lock:
        file_data: list[str] = []
        try:
            with open(file_path, "r", encoding=text_encoding) as f:
                for text_line in f:
                    if old_str in text_line:
                        text_line = text_line.replace(old_str, new_str)
                        if start_str:
                            text_line = f"{start_str}{text_line}"
                    if text_line not in file_data:
                        file_data.append(text_line)
        except (RuntimeError, UnicodeDecodeError) as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
            # 读取失败时尝试用初始内容恢复，避免文件被清空
            if ini_URL_content:
                with open(file_path, "w", encoding=text_encoding) as f2:
                    _ = f2.write(ini_URL_content)
                return old_str
            return old_str
        if file_data:
            joined = "".join(file_data)
            with open(file_path, "w", encoding=text_encoding) as f:
                _ = f.write(joined)
            # 更新快照为当前已落盘内容，使后续异常恢复只回滚到最近一次成功修改，而非整个循环开始时的旧内容
            ini_URL_content = joined
        return new_str


def delete_line(file_path: str, del_line: str, delete_all: bool = False) -> None:
    # 从文件中删除指定行
    # delete_all=False 时仅删除第一个匹配行
    with file_update_lock:
        with open(file_path, "r+", encoding=text_encoding) as f:
            lines = f.readlines()
            _ = f.seek(0)
            _ = f.truncate()
            deleted_one = False
            for txt_line in lines:
                if del_line == txt_line and (delete_all or not deleted_one):
                    deleted_one = True
                    continue
                _ = f.write(txt_line)


# Windows 下 subprocess.STARTUPINFO 仅存在于 Windows typeshed，Linux/macOS 上 mypy 无法解析该名字。
# 返回值类型用 object 而非具体 STARTUPINFO：该符号在非 Windows typeshed 中不存在，无法作为跨平台类型引用；
# 调用方仅将其透传给 subprocess 的 startupinfo 参数（typeshed 中本就是宽松类型），object | None 不损失实际类型安全。
def get_startup_info(system_type: str) -> object | None:
    # 获取平台启动信息（Windows 隐藏控制台窗口）。
    # 运行时只在 Windows（os.name == "nt"）构造 STARTUPINFO，其他平台恒返回 None；
    # mypy 依据 sys.platform 字面量分支跳过非当前平台代码，从而通过跨平台类型检查。
    if system_type != "nt":
        return None
    if sys.platform == "win32":
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return startup_info
    return None


def segment_video(
    converts_file_path: str,
    segment_save_file_path: str,
    segment_format: str,
    segment_time: str,
    is_original_delete: bool = True,
) -> None:
    # 使用 FFmpeg 对视频进行分段录制
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            ffmpeg_command = [
                "ffmpeg",
                "-i",
                converts_file_path,
                "-c:v",
                "copy",
                "-c:a",
                "copy",
                "-map",
                "0",
                "-f",
                "segment",
                "-segment_time",
                segment_time,
                "-segment_format",
                segment_format,
                "-reset_timestamps",
                "1",
                "-movflags",
                "+frag_keyframe+empty_moov",
                segment_save_file_path,
            ]
            _ = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type))
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred during conversion: {e}")
    except Exception as e:
        logger.error(f"An unknown error occurred: {e}")


def converts_mp4(converts_file_path: str, is_original_delete: bool = True) -> None:
    # 将录制文件转换为 MP4 格式
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            if converts_to_h264:
                color_obj.print_colored("正在转码为MP4格式并重新编码为h264\n", color_obj.YELLOW)
                ffmpeg_command = [
                    "ffmpeg",
                    "-i",
                    converts_file_path,
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "23",
                    "-vf",
                    "format=yuv420p",
                    "-c:a",
                    "copy",
                    "-f",
                    "mp4",
                    converts_file_path.rsplit(".", maxsplit=1)[0] + ".mp4",
                ]
            else:
                color_obj.print_colored("正在转码为MP4格式\n", color_obj.YELLOW)
                ffmpeg_command = [
                    "ffmpeg",
                    "-i",
                    converts_file_path,
                    "-c:v",
                    "copy",
                    "-c:a",
                    "copy",
                    "-f",
                    "mp4",
                    converts_file_path.rsplit(".", maxsplit=1)[0] + ".mp4",
                ]
            _ = subprocess.check_output(ffmpeg_command, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type))
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred during conversion: {e}")
    except Exception as e:
        logger.error(f"An unknown error occurred: {e}")


def converts_m4a(converts_file_path: str, is_original_delete: bool = True) -> None:
    # 将录制文件转换为 M4A 音频格式
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            _ = subprocess.check_output(
                [
                    "ffmpeg",
                    "-i",
                    converts_file_path,
                    "-n",
                    "-vn",
                    "-c:a",
                    "aac",
                    "-bsf:a",
                    "aac_adtstoasc",
                    "-ab",
                    "320k",
                    converts_file_path.rsplit(".", maxsplit=1)[0] + ".m4a",
                ],
                stderr=subprocess.STDOUT,
                startupinfo=get_startup_info(os_type),
            )
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error occurred during conversion: {e}")
    except Exception as e:
        logger.error(f"An unknown error occurred: {e}")


def generate_subtitles(record_name: str, ass_filename: str, sub_format: str = "srt") -> None:
    # 生成字幕文件（SRT/ASS/VTT 格式）
    index_time = 0
    today = datetime.datetime.now()
    re_datetime = today.strftime("%Y-%m-%d %H:%M:%S")

    def transform_int_to_time(seconds: int) -> str:
        # 将整数秒数转为时间戳字符串
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    while True:
        index_time += 1
        txt = (
            str(index_time)
            + "\n"
            + transform_int_to_time(index_time)
            + ",000 --> "
            + transform_int_to_time(index_time + 1)
            + ",000"
            + "\n"
            + re_datetime
            + "\n\n"
        )

        with open(f"{ass_filename}.{sub_format.lower()}", "a", encoding=text_encoding) as f:
            _ = f.write(txt)

        with record_state_lock:
            still_recording = record_name in recording
        if not still_recording:
            return
        time.sleep(1)
        today = datetime.datetime.now()
        re_datetime = today.strftime("%Y-%m-%d %H:%M:%S")


def record_error() -> None:
    # 线程安全地记录一次错误：递增计数并追加到滑动窗口（deque maxlen 自动裁剪）
    global error_count
    with max_request_lock:
        error_count += 1
        error_window.append(1)


def adjust_max_request() -> None:
    # 根据错误率动态调整并发线程数
    global max_request, error_count, pre_max_request
    preset = max_request

    while True:
        time.sleep(5)
        with max_request_lock:
            if error_window:
                error_rate = sum(error_window) / len(error_window)
            else:
                error_rate = 0

            if error_rate > error_threshold:
                max_request = max(1, max_request - 1)
            elif error_rate < error_threshold / 2 and max_request < preset:
                max_request += 1
            else:
                pass

            if pre_max_request != max_request:
                pre_max_request = max_request
                logger.debug(f"同一时间访问网络的线程数动态改为 {max_request}")

            # 复位本周期错误数（窗口只记录错误事件，由 record_error 统一追加 1，避免口径混用）
            error_count = 0


def push_message(record_name: str, live_url: str, content: str) -> None:
    # 触发消息推送（多渠道分发）
    msg_title = push_message_title.strip() or "直播间状态更新通知"
    push_functions = {
        "微信": lambda: xizhi(xizhi_api_url, msg_title, content),
        "钉钉": lambda: dingtalk(dingtalk_api_url, content, dingtalk_phone_num, dingtalk_is_atall),
        "邮箱": lambda: send_email(
            email_host,
            login_email,
            email_password,
            sender_email,
            sender_name,
            to_email,
            msg_title,
            content,
            smtp_port,
            open_smtp_ssl,
        ),
        "TG": lambda: tg_bot(tg_chat_id, tg_token, content),
        "BARK": lambda: bark(bark_msg_api, title=msg_title, content=content, level=bark_msg_level, sound=bark_msg_ring),
        "NTFY": lambda: ntfy(
            ntfy_api, title=msg_title, content=content, tags=ntfy_tags, action_url=live_url, email=ntfy_email
        ),
        "PUSHPLUS": lambda: pushplus(pushplus_token, msg_title, content),
    }

    for platform, func in push_functions.items():
        if platform in live_status_push.upper():
            try:
                result = func()  # type: ignore[no-untyped-call]
                result_dict = cast(dict[str, list[str | int]], result)
                logger.info(
                    f'提示信息：已经将[{record_name}]直播状态消息推送至你的{platform}, 成功{len(result_dict["success"])}, 失败{len(result_dict["error"])}'
                )
            except Exception as e:
                color_obj.print_colored(f"直播消息推送到{platform}失败: {e}", color_obj.RED)


def run_script(command: str) -> None:
    # 执行自定义脚本命令
    # 使用 shlex.split 安全解析命令字符串，避免 shell=True 命令注入
    try:
        args = shlex.split(command)
        process = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=get_startup_info(os_type)
        )
        stdout, stderr = process.communicate()
        stdout_decoded = stdout.decode("utf-8")
        stderr_decoded = stderr.decode("utf-8")
        if stdout_decoded.strip():
            print(stdout_decoded)
        if stderr_decoded.strip():
            print(stderr_decoded)
    except PermissionError as e:
        logger.error(e)
        logger.error("脚本无执行权限!, 若是Linux环境, 请先执行:chmod +x your_script.sh 授予脚本可执行权限")
    except OSError as e:
        logger.error(e)
        logger.error("Please add `#!/bin/bash` at the beginning of your bash script file.")
    except ValueError as e:
        logger.error(f"脚本命令解析失败: {e}")


def clear_record_info(record_name: str, record_url: str) -> None:
    # 清理录制状态信息
    global monitoring
    with record_state_lock:
        recording.discard(record_name)
        if record_url in url_comments and record_url in running_list:
            running_list.remove(record_url)
            monitoring -= 1
            color_obj.print_colored(f"[{record_name}]已经从录制列表中移除\n", color_obj.YELLOW)


def direct_download_stream(source_url: str, save_path: str, record_name: str, live_url: str, platform: str) -> bool:
    # 直接下载直播流（不走 FFmpeg）
    try:
        with open(save_path, "wb") as f:
            headers: dict[str, str] = {}
            header_params = get_record_headers(platform, live_url)
            if header_params:
                key, value = header_params.split(":", 1)
                headers[key] = value

            with httpx.Client(timeout=30) as client:
                with client.stream("GET", source_url, headers=headers, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(f"请求直播流失败，状态码: {response.status_code}")
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
        logger.error(f"FLV下载错误: {e} 发生错误的行数: {_get_error_line(e)}")
        return False


def check_subprocess(
    record_name: str, record_url: str, ffmpeg_command: list[str], save_type: str, script_command: str | None = None
) -> bool:
    # 检查 FFmpeg 子进程状态并处理异常
    save_file_path = ffmpeg_command[-1]
    process = subprocess.Popen(
        ffmpeg_command, stdin=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
    )

    # 注册 ffmpeg 进程
    register_ffmpeg_process(process)

    subs_file_path = save_file_path.rsplit(".", maxsplit=1)[0]
    subs_thread_name = f"subs_{Path(subs_file_path).name}"
    if create_time_file and not split_video_by_time and "音频" not in save_type:
        create_var[subs_thread_name] = threading.Thread(target=generate_subtitles, args=(record_name, subs_file_path))
        create_var[subs_thread_name].daemon = True
        create_var[subs_thread_name].start()

    def terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
        # 复用模块级公共终止逻辑（避免重复实现导致的逻辑漂移）
        return _terminate_ffmpeg_process(proc, timeout)

    while process.poll() is None:
        if record_url in url_comments or exit_recording:
            color_obj.print_colored(f"[{record_name}]录制时已被注释,本条线程将会退出", color_obj.YELLOW)
            clear_record_info(record_name, record_url)

            # 使用更可靠的进程终止机制
            success = terminate_ffmpeg_process(process)
            if not success:
                logger.warning(f"[{record_name}] ffmpeg 进程可能没有完全终止，请检查系统进程")

            # 确保异常路径也注销 ffmpeg 进程
            unregister_ffmpeg_process(process)
            return True
        time.sleep(1)

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

    else:
        color_obj.print_colored(f"\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n", color_obj.RED)

    with record_state_lock:
        recording.discard(record_name)
    # 取消注册 ffmpeg 进程
    unregister_ffmpeg_process(process)
    return False


def clean_name(input_text: str) -> str:
    # 清理文件名中的非法字符
    cleaned_name = re.sub(rstr, "_", input_text.strip()).strip("_")
    cleaned_name = cleaned_name.replace("（", "(").replace("）", ")")
    if clean_emoji:
        cleaned_name = utils.remove_emojis(cleaned_name, "_").strip("_")
    # Windows 特殊字符清理：& 在 cmd 中会触发命令分隔，统一替换为下划线
    cleaned_name = cleaned_name.replace("&", "_")
    return cleaned_name or "空白昵称"


def get_quality_code(qn: str) -> str:
    # 将画质描述转为代码（原画/超清/高清等）
    quality_zh_to_en = {"原画": "OD", "蓝光": "BD", "超清": "UHD", "高清": "HD", "标清": "SD", "流畅": "LD"}
    # 未知画质回退到 OD，避免返回 None 导致后续比较逻辑出错
    return quality_zh_to_en.get(qn, "OD")


def get_record_headers(platform: str, live_url: str) -> str | None:
    # 获取录制请求的 HTTP 头
    live_domain = "/".join(live_url.split("/")[0:3])
    record_headers = {
        "PandaTV": "origin:https://www.pandalive.co.kr",
        "WinkTV": "origin:https://www.winktv.co.kr",
        "PopkonTV": "origin:https://www.popkontv.com",
        "TTingLive(原Flextv)": "origin:https://www.flextv.co.kr",
        "千度热播": "referer:https://qiandurebo.com",
        "17Live": "referer:https://17.live/en/live/6302408",
        "浪Live": "referer:https://www.lang.live",
        "shopee": f"origin:{live_domain}",
        "blued": "referer:https://app.blued.cn",
    }
    return record_headers.get(platform)


def _validate_stream_url(
    url: str,
    proxy_addr: str | None = None,
    timeout: int = 5,
    verify: bool | None = None,
) -> bool:
    # 校验流地址可达性（与 async_http.get_response_status 语义保持一致）：
    # 1) 未显式指定时沿用全局 SSL 验证开关，避免与解析阶段的校验行为不一致
    #    （用户关闭证书验证后，同步校验仍验证证书会导致误判不可达）；
    # 2) m3u8 源 HEAD 非 2xx（含 403/404）时再做 Range GET 探测——抖音等 CDN 常
    #    对 HEAD 返回 4xx 而 GET 可正常拉流，仅覆盖 400/401/403/405 会漏掉 404；
    # 3) 失败必须记录原因（异常类型/状态码/content-type），禁止静默吞掉异常，
    #    否则回退 FLV 时无法定位真实原因（如超时、被拒、内容类型不符）。
    if verify is None:
        verify = _http_config.ssl_verify
    try:
        with httpx.Client(timeout=timeout, proxy=proxy_addr, verify=verify) as client:
            response = client.head(url, follow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()
            if any(k in content_type for k in ("video", "octet-stream", "flash", "mpegurl")):
                return True
            if "text/html" in content_type or "application/json" in content_type:
                logger.warning(
                    f"流地址校验失败（返回非流媒体内容）: {url} - status_code={response.status_code}, content-type={content_type}"
                )
                return False
            if response.status_code == 200:
                return True
            if ".m3u8" in url:
                probe = client.get(url, headers={"Range": "bytes=0-0"}, follow_redirects=True)
                if probe.status_code in (200, 206):
                    return True
                logger.warning(
                    f"流地址校验失败: {url} - HEAD={response.status_code}, Range-GET={probe.status_code}, "
                    f"content-type={probe.headers.get('content-type', '')}"
                )
                return False
            logger.warning(f"流地址校验失败: {url} - status_code={response.status_code}, content-type={content_type}")
            return False
    except Exception as e:
        # Windows 下 socket.timeout 的 str() 为空，必须带上异常类型与 URL
        logger.warning(f"流地址校验异常（判定为不可达）: {url} - {type(e).__name__}: {e}")
        return False


def select_source_url(_link: str, stream_info: Mapping[str, object], proxy_addr: str | None = None) -> str | None:
    # HLS(m3u8) 优先采集：当存在 HLS 源且配置启用 HLS 采集时优先使用；
    # 仅当无 HLS 源 或 配置关闭 HLS 采集时，才回退使用 FLV 源。
    # proxy_addr 必须透传给校验器：TikTok 等境外平台的流地址若不走与解析阶段
    # 相同的代理路径，直连校验会超时被误判为不可达，导致错误回退甚至放弃录制。
    m3u8_url = stream_info.get("m3u8_url")
    flv_url = stream_info.get("flv_url")
    hls_available = isinstance(m3u8_url, str) and bool(m3u8_url)

    if hls_available and hls_collection_enabled:
        if _validate_stream_url(cast(str, m3u8_url), proxy_addr=proxy_addr):
            return cast(str | None, m3u8_url)
        logger.warning("HLS URL validation failed, falling back to FLV")

    if isinstance(flv_url, str) and flv_url:
        codec = utils.get_query_params(flv_url, "codec")
        if isinstance(codec, list) and codec and codec[0] == "h265":
            logger.warning("FLV is not supported for h265 codec, use HLS source instead")
            if hls_available:
                return cast(str | None, m3u8_url)
        if _validate_stream_url(flv_url, proxy_addr=proxy_addr):
            return flv_url
        logger.warning("FLV URL validation failed, trying record_url fallback")

    record_url = stream_info.get("record_url")
    if isinstance(record_url, str) and record_url:
        codec = utils.get_query_params(record_url, "codec")
        if isinstance(codec, list) and codec and codec[0] == "h265":
            logger.warning("record_url has h265 codec, but no HLS or FLV fallback available")
        if _validate_stream_url(record_url, proxy_addr=proxy_addr):
            return record_url
    return None


def _douyin_rate_limit() -> None:
    # 抖音请求速率限制：保证两次抖音 API 请求之间有最小间隔，
    # 避免多线程并发监控多个直播间时触发抖音风控（返回空响应）。
    # 在 semaphore 内部调用，确保串行化 + 间隔双重保护。
    global douyin_last_request_time
    with douyin_rate_lock:
        now = time.time()
        elapsed = now - douyin_last_request_time
        if elapsed < douyin_min_interval:
            time.sleep(douyin_min_interval - elapsed)
        douyin_last_request_time = time.time()


def start_record(url_data: tuple[str, str, str], count_variable: int = -1) -> None:
    # 录制主循环：检测→获取流→启动 FFmpeg
    while True:
        try:
            record_finished = False
            run_once = False
            start_pushed = False
            new_record_url = ""  # Shopee 平台专用：记录带 uid 的完整 URL 用于更新配置
            count_time = time.time()
            record_quality_zh, record_url, anchor_name = url_data
            record_quality = get_quality_code(record_quality_zh)
            # 真实下发的画质代码（由 stream 模块回采，可能为 None）
            from src.stream import code_to_zh
            from src.stream import is_downgrade as _is_downgrade

            proxy_address = proxy_addr
            platform = "未知平台"

            if proxy_addr:
                proxy_address = None
                if enable_proxy_platform_list:
                    for platform in enable_proxy_platform_list:
                        if platform and platform.strip() in record_url:
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
                try:
                    port_info = {}
                    if record_url.find("douyin.com/") > -1:
                        platform = "抖音直播"
                        with semaphore:
                            _douyin_rate_limit()  # 速率限制：防止并发请求触发抖音风控
                            if "v.douyin.com" not in record_url and "/user/" not in record_url:
                                json_data = asyncio.run(
                                    spider.get_douyin_web_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=dy_cookie
                                    )
                                )
                            else:
                                json_data = asyncio.run(
                                    spider.get_douyin_app_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=dy_cookie
                                    )
                                )
                            port_info = asyncio.run(
                                stream.get_douyin_stream_url(json_data, record_quality, proxy_address)
                            )

                    elif record_url.find("https://www.tiktok.com/") > -1:
                        platform = "TikTok直播"
                        with semaphore:
                            if global_proxy or proxy_address:
                                tiktok_data = asyncio.run(
                                    spider.get_tiktok_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=tiktok_cookie
                                    )
                                )
                                # dict 值类型参数是不变的：回退字面量 {"is_live": False} 会被推断为
                                # dict[str, bool]，与形参 dict[str, object] 不兼容，故 cast 收敛
                                json_data = (
                                    tiktok_data
                                    if tiktok_data is not None
                                    else cast(dict[str, object], {"is_live": False})
                                )
                                port_info = asyncio.run(
                                    stream.get_tiktok_stream_url(json_data, record_quality, proxy_address)
                                )
                            else:
                                logger.error("错误信息: 网络异常，请检查网络是否能正常访问TikTok平台")

                    elif record_url.find("https://live.kuaishou.com/") > -1:
                        platform = "快手直播"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_kuaishou_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=ks_cookie
                                )
                            )
                            port_info = asyncio.run(stream.get_kuaishou_stream_url(json_data, record_quality))

                    elif record_url.find("https://www.huya.com/") > -1:
                        platform = "虎牙直播"
                        with semaphore:
                            if record_quality not in ["OD", "BD", "UHD"]:
                                json_data = asyncio.run(
                                    spider.get_huya_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=hy_cookie
                                    )
                                )
                                port_info = asyncio.run(stream.get_huya_stream_url(json_data, record_quality))
                            else:
                                port_info = asyncio.run(
                                    spider.get_huya_app_stream_url(
                                        url=record_url, proxy_addr=proxy_address, cookies=hy_cookie
                                    )
                                )

                    elif record_url.find("https://www.douyu.com/") > -1:
                        platform = "斗鱼直播"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_douyu_info_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=douyu_cookie
                                )
                            )
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
                                spider.get_bilibili_room_info(
                                    url=record_url, proxy_addr=proxy_address, cookies=bili_cookie
                                )
                            )
                            port_info = asyncio.run(
                                stream.get_bilibili_stream_url(
                                    json_data,
                                    video_quality=record_quality,
                                    cookies=bili_cookie,
                                    proxy_addr=proxy_address,
                                )
                            )

                    elif (
                        record_url.find("http://xhslink.com/") > -1
                        or record_url.find("https://www.xiaohongshu.com/") > -1
                    ):
                        platform = "小红书直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_xhs_stream_url(record_url, proxy_addr=proxy_address, cookies=xhs_cookie)
                            )

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
                                    utils.update_config(
                                        config_file, "Cookie", "sooplive_cookie", cast(str, json_data["new_cookies"])
                                    )
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问SOOP(原AfreecaTV)平台")

                    elif record_url.find("cc.163.com/") > -1:
                        platform = "网易CC直播"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_netease_stream_data(url=record_url, cookies=netease_cookie)
                            )
                            port_info = asyncio.run(stream.get_netease_stream_url(json_data, record_quality))

                    elif record_url.find("qiandurebo.com/") > -1:
                        platform = "千度热播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_qiandurebo_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=qiandurebo_cookie
                                )
                            )

                    elif record_url.find("www.pandalive.co.kr/") > -1 or record_url.find("www.plive.kr/") > -1:
                        platform = "PandaTV"
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(
                                    spider.get_pandatv_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=pandatv_cookie
                                    )
                                )
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")

                    elif record_url.find("fm.missevan.com/") > -1:
                        platform = "猫耳FM直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_maoerfm_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=maoerfm_cookie
                                )
                            )

                    elif record_url.find("www.winktv.co.kr/") > -1:
                        platform = "WinkTV"
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(
                                    spider.get_winktv_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=winktv_cookie
                                    )
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
                                    utils.update_config(
                                        config_file, "Cookie", "flextv_cookie", cast(str, json_data["new_cookies"])
                                    )
                                if "play_url_list" in json_data:
                                    port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                                else:
                                    port_info = json_data
                            else:
                                logger.error(
                                    "错误信息: 网络异常，请检查本网络是否能正常访问TTingLive(原Flextv)直播平台"
                                )

                    elif record_url.find("look.163.com/") > -1:
                        platform = "Look直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_looklive_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=look_cookie
                                )
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
                                spider.get_baidu_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=baidu_cookie
                                )
                            )
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality))

                    elif record_url.find("weibo.com/") > -1:
                        platform = "微博直播"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_weibo_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=weibo_cookie
                                )
                            )
                            port_info = asyncio.run(
                                stream.get_stream_url(json_data, record_quality, hls_extra_key="m3u8_url")
                            )

                    elif record_url.find("kugou.com/") > -1:
                        platform = "酷狗直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_kugou_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=kugou_cookie
                                )
                            )

                    elif record_url.find("www.twitch.tv/") > -1:
                        platform = "TwitchTV"
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(
                                    spider.get_twitchtv_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=twitch_cookie
                                    )
                                )
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TwitchTV直播平台")

                    elif record_url.find("www.liveme.com/") > -1:
                        if global_proxy or proxy_address:
                            platform = "LiveMe"
                            with semaphore:
                                port_info = asyncio.run(
                                    spider.get_liveme_stream_url(
                                        url=record_url, proxy_addr=proxy_address, cookies=liveme_cookie
                                    )
                                )
                        else:
                            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问LiveMe直播平台")

                    elif record_url.find("www.huajiao.com/") > -1:
                        platform = "花椒直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_huajiao_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=huajiao_cookie
                                )
                            )

                    elif record_url.find("7u66.com/") > -1:
                        platform = "流星直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_liuxing_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=liuxing_cookie
                                )
                            )

                    elif record_url.find("showroom-live.com/") > -1:
                        platform = "ShowRoom"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_showroom_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=showroom_cookie
                                )
                            )
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("live.acfun.cn/") > -1 or record_url.find("m.acfun.cn/") > -1:
                        platform = "Acfun"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_acfun_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=acfun_cookie
                                )
                            )
                            port_info = asyncio.run(
                                stream.get_stream_url(json_data, record_quality, url_type="flv", flv_extra_key="url")
                            )

                    elif record_url.find("live.tlclw.com/") > -1:
                        platform = "畅聊直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_changliao_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=changliao_cookie
                                )
                            )

                    elif record_url.find("ybw1666.com/") > -1:
                        platform = "音播直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_yinbo_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=yinbo_cookie
                                )
                            )

                    elif record_url.find("www.inke.cn/") > -1:
                        platform = "映客直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_yingke_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=yingke_cookie
                                )
                            )

                    elif record_url.find("www.zhihu.com/") > -1:
                        platform = "知乎直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_zhihu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=zhihu_cookie
                                )
                            )

                    elif record_url.find("chzzk.naver.com/") > -1:
                        platform = "CHZZK"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_chzzk_stream_data(
                                    url=record_url, proxy_addr=proxy_address, cookies=chzzk_cookie
                                )
                            )
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("www.haixiutv.com/") > -1:
                        platform = "嗨秀直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_haixiu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=haixiu_cookie
                                )
                            )

                    elif record_url.find("vvxqiu.com/") > -1:
                        platform = "VV星球"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_vvxqiu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=vvxqiu_cookie
                                )
                            )

                    elif record_url.find("17.live/") > -1:
                        platform = "17Live"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_17live_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=yiqilive_cookie
                                )
                            )

                    elif record_url.find("www.lang.live/") > -1:
                        platform = "浪Live"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_langlive_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=langlive_cookie
                                )
                            )

                    elif record_url.find("m.pp.weimipopo.com/") > -1:
                        platform = "飘飘直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_pplive_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=pplive_cookie
                                )
                            )

                    elif record_url.find(".6.cn/") > -1:
                        platform = "六间房直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_6room_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=six_room_cookie
                                )
                            )

                    elif record_url.find("lehaitv.com/") > -1:
                        platform = "乐嗨直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_haixiu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=lehaitv_cookie
                                )
                            )

                    elif record_url.find("h.catshow168.com/") > -1:
                        platform = "花猫直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_pplive_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=huamao_cookie
                                )
                            )

                    elif record_url.find("live.shopee") > -1 or record_url.find("shp.ee/") > -1:
                        platform = "shopee"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_shopee_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=shopee_cookie
                                )
                            )
                            if port_info.get("uid"):
                                new_record_url = record_url.split("?")[0] + "?" + str(port_info["uid"])

                    elif record_url.find("www.youtube.com/") > -1 or record_url.find("youtu.be/") > -1:
                        platform = "YouTube"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_youtube_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=youtube_cookie
                                )
                            )
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("tb.cn") > -1 or record_url.find("tbzb.taobao.com") > -1:
                        platform = "淘宝直播"
                        with semaphore:
                            json_data = asyncio.run(
                                spider.get_taobao_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=taobao_cookie
                                )
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
                                    spider.get_faceit_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=faceit_cookie
                                    )
                                )
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问faceit直播平台")

                    elif record_url.find("www.miguvideo.com") > -1 or record_url.find("m.miguvideo.com") > -1:
                        platform = "咪咕直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_migu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=migu_cookie
                                )
                            )

                    elif record_url.find("show.lailianjie.com") > -1:
                        platform = "连接直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_lianjie_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=lianjie_cookie
                                )
                            )

                    elif record_url.find("www.imkktv.com") > -1:
                        platform = "来秀直播"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_laixiu_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=laixiu_cookie
                                )
                            )

                    elif record_url.find("www.picarto.tv") > -1:
                        platform = "Picarto"
                        with semaphore:
                            port_info = asyncio.run(
                                spider.get_picarto_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=picarto_cookie
                                )
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
                        logger.error(f"{record_url} {platform}直播地址")
                        return

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
                        record_error()
                    else:
                        anchor_name = clean_name(anchor_name)
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

                            real_url = select_source_url(record_url, port_info, proxy_address)
                            full_path = f"{default_path}/{platform}"
                            if real_url:
                                now = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
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

                                if platform != "自定义录制直播":
                                    if enable_https_recording and real_url.startswith("http://"):
                                        real_url = real_url.replace("http://", "https://")

                                    http_record_list = ["shopee", "migu"]
                                    if platform in http_record_list:
                                        real_url = real_url.replace("https://", "http://")

                                user_agent = (
                                    "Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 ("
                                    "KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile "
                                    "Safari/537.36"
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

                                ffmpeg_command = [
                                    "ffmpeg",
                                    "-y",
                                    "-v",
                                    "verbose",
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

                                headers = get_record_headers(platform, record_url)
                                if headers:
                                    ffmpeg_command.insert(11, "-headers")
                                    ffmpeg_command.insert(12, headers)

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
                                        logger.info(
                                            f"{platform} | {anchor_name} | 直播源地址: {port_info.get('m3u8_url')}"
                                        )
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
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        extension = "mp3" if "m4a" not in record_save_type.lower() else "m4a"
                                        name_format = "_%03d" if split_video_by_time else ""
                                        save_file_path = (
                                            f"{full_path}/{anchor_name}_{title_in_name}{now}"
                                            f"{name_format}.{extension}"
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
                                            record_name, record_url, ffmpeg_command, record_save_type, custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error()

                                elif only_flv_record:
                                    logger.info(f"Use Direct Downloader to Download FLV Stream: {record_url}")
                                    filename = anchor_name + f"_{title_in_name}" + now + ".flv"
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
                                                    actual_quality_value
                                                    if isinstance(actual_quality_value, str)
                                                    else None
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
                                                flv_url, save_file_path, record_name, record_url, platform
                                            )

                                            if download_success:
                                                record_finished = True
                                                print(
                                                    f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制完成\n"
                                                )

                                            with record_state_lock:
                                                recording.discard(record_name)
                                        else:
                                            logger.debug("未找到FLV直播流，跳过录制")
                                    except Exception as e:
                                        clear_record_info(record_name, record_url)
                                        color_obj.print_colored(
                                            f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n",
                                            color_obj.RED,
                                        )
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error()

                                elif record_save_type == "FLV":
                                    filename = anchor_name + f"_{title_in_name}" + now + ".flv"
                                    print(f"{rec_info}/{filename}")
                                    save_file_path = full_path + "/" + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
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
                                            record_name, record_url, ffmpeg_command, record_save_type, custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error()

                                    try:
                                        if converts_to_mp4:
                                            seg_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mp4"
                                            if split_video_by_time:
                                                segment_video(
                                                    save_file_path,
                                                    seg_file_path,
                                                    segment_format="mp4",
                                                    segment_time=split_time,
                                                    is_original_delete=delete_origin_file,
                                                )
                                            else:
                                                threading.Thread(
                                                    target=converts_mp4, args=(save_file_path, delete_origin_file)
                                                ).start()

                                        else:
                                            seg_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.flv"
                                            if split_video_by_time:
                                                segment_video(
                                                    save_file_path,
                                                    seg_file_path,
                                                    segment_format="flv",
                                                    segment_time=split_time,
                                                    is_original_delete=delete_origin_file,
                                                )
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
                                            record_name, record_url, ffmpeg_command, record_save_type, custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error()

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
                                            record_name, record_url, ffmpeg_command, record_save_type, custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                        record_error()

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
                                                "-segment_format",
                                                "mpegts",
                                                "-reset_timestamps",
                                                "1",
                                                save_file_path,
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name, record_url, ffmpeg_command, record_save_type, custom_script
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
                                            record_error()

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
                                                record_name, record_url, ffmpeg_command, record_save_type, custom_script
                                            )
                                            if comment_end:
                                                threading.Thread(
                                                    target=converts_mp4, args=(save_file_path, delete_origin_file)
                                                ).start()
                                                return

                                        except subprocess.CalledProcessError as e:
                                            logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                                            record_error()

                                count_time = time.time()

                except Exception as e:
                    logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
                    record_error()

                num = random.randint(-5, 5) + delay_default
                if num < 0:
                    num = 0
                x = num

                if error_count > 20:
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
            record_error()
            time.sleep(2)


def backup_file(file_path: str, backup_dir_path: str, limit_counts: int = 6) -> None:
    # 备份配置文件到 backup_config 目录
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_file_name = os.path.basename(file_path) + "_" + timestamp
        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        _ = shutil.copy2(file_path, backup_file_path)

        files = os.listdir(backup_dir_path)
        _files = [f for f in files if f.startswith(os.path.basename(file_path))]
        _files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))

        while len(_files) > limit_counts:
            oldest_file = _files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            _files = _files[1:]

    except Exception as e:
        logger.error(f"\r备份配置文件 {file_path} 失败：{e}")


def backup_file_start() -> None:
    # 启动时备份文件（首次运行触发）
    config_md5 = ""
    url_config_md5 = ""

    while True:
        try:
            if os.path.exists(config_file):
                new_config_md5 = utils.check_md5(config_file)
                if new_config_md5 != config_md5:
                    backup_file(config_file, backup_dir)
                    config_md5 = new_config_md5

            if os.path.exists(url_config_file):
                new_url_config_md5 = utils.check_md5(url_config_file)
                if new_url_config_md5 != url_config_md5:
                    backup_file(url_config_file, backup_dir)
                    url_config_md5 = new_url_config_md5
            time.sleep(600)
        except Exception as e:
            logger.error(f"备份配置文件失败, 错误信息: {e}")


def check_ffmpeg_existence() -> bool:
    # 检查 FFmpeg 是否可用，不可用则触发安装
    ffmpeg_exists = False
    try:
        result = subprocess.run(["ffmpeg", "-version"], check=True, capture_output=True, text=True)
        if result.returncode == 0:
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
if not check_ffmpeg_existence():
    logger.error("缺少ffmpeg，录制主循环将不会启动（Web 面板仍可运行）")
os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()
utils.remove_duplicate_lines(url_config_file)


def read_config_value(
    config_parser: configparser.RawConfigParser, section: str, option: str, default_value: str | int | float | bool = ""
) -> str:
    # 读取配置文件指定节键值
    try:
        if "录制设置" not in config_parser.sections():
            config_parser.add_section("录制设置")
        if "推送配置" not in config_parser.sections():
            config_parser.add_section("推送配置")
        if "Cookie" not in config_parser.sections():
            config_parser.add_section("Cookie")
        if "Authorization" not in config_parser.sections():
            config_parser.add_section("Authorization")
        if "账号密码" not in config_parser.sections():
            config_parser.add_section("账号密码")
        return config_parser.get(section, option)
    except (configparser.NoSectionError, configparser.NoOptionError):
        config_parser.set(section, option, str(default_value))
        with open(config_file, "w", encoding=text_encoding) as f:
            config_parser.write(f)
        return str(default_value)


options: dict[str, bool] = {"是": True, "否": False}
config: configparser.RawConfigParser = configparser.RawConfigParser()
_config_read_result = config.read(config_file, encoding=text_encoding)
language = read_config_value(config, "录制设置", "language(zh_cn/en)", "zh_cn")
skip_proxy_check = options.get(read_config_value(config, "录制设置", "是否跳过代理检测(是/否)", "否"), False)
# SSL 证书验证全局开关：默认开启验证（安全优先），统一控制所有 HTTP 客户端
disable_ssl_verify = options.get(read_config_value(config, "录制设置", "是否禁用SSL证书验证(是/否)", "否"), False)
from src import http_config as _http_config

_http_config.set_ssl_verify(not disable_ssl_verify)
if language and "en" not in language.lower():
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


def get_status() -> dict[str, object]:
    # 返回录制引擎状态快照（线程安全），供 Web API 调用。
    #
    #     注意：部分录制路径在未持有 record_state_lock 的情况下修改 recording /
    #     recording_time_list（既有行为），因此即便持锁迭代仍可能触发
    #     "Set changed size during iteration"。此处用有限次重试兜底。
    #
    now = datetime.datetime.now()
    # 既有代码存在未加锁的并发写，持锁迭代可能抛 RuntimeError，重试兜底
    recording_snapshot: list[str] = []
    recording_times: dict[str, dict[str, str]] = {}
    monitoring_val: int = monitoring
    running_val: list[str] = []
    error_val: int = error_count
    for _attempt in range(5):
        try:
            with record_state_lock:
                recording_snapshot = list(recording)
                recording_times = {}
                for _name, _info in recording_time_list.items():
                    if _info and len(_info) > 1:
                        # 兼容旧格式 [start, quality] 和新格式 [start, quality, actual_quality]
                        _start = cast(datetime.datetime, _info[0])
                        _quality = str(_info[1])
                        _actual_q = str(_info[2]) if len(_info) > 2 else ""
                        recording_times[_name] = {
                            "start_time": _start.strftime("%Y-%m-%d %H:%M:%S"),
                            "quality": _quality,
                            "actual_quality": _actual_q,
                            "duration": str(now - _start).split(".")[0],
                        }
                    else:
                        recording_times[_name] = {
                            "start_time": "",
                            "quality": "",
                            "actual_quality": "",
                            "duration": "0:00:00",
                        }
                monitoring_val = monitoring
                running_val = list(running_list)
                error_val = error_count
                break
        except (RuntimeError, IndexError):
            continue
    try:
        disk_free_gb = utils.check_disk_capacity(default_path)
    except Exception:
        disk_free_gb = -1.0
    # engine_alive: 录制引擎守护线程是否存活。None 表示未运行于 Web 模式（CLI 直跑，视作存活）。
    if _recorder_thread is None:
        engine_alive = True
    else:
        engine_alive = _recorder_thread.is_alive()
    uptime = str(now - start_display_time).split(".")[0] if start_display_time else "0:00:00"
    return {
        "version": version,
        "monitoring": monitoring_val,
        "recording_count": len(recording_snapshot),
        "recording": [
            {
                "name": _n,
                "start_time": recording_times.get(_n, {}).get("start_time", ""),
                "quality": recording_times.get(_n, {}).get("quality", ""),
                "actual_quality": recording_times.get(_n, {}).get("actual_quality", ""),
                "duration": recording_times.get(_n, {}).get("duration", "0:00:00"),
            }
            for _n in recording_snapshot
        ],
        "running_list": running_val,
        "error_count": error_val,
        "disk_free_gb": round(disk_free_gb, 2),
        "uptime": uptime,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_alive": engine_alive,
    }


def main(non_interactive: bool = False) -> None:
    # 录制主循环：读取配置 → 调度录制线程 → 热加载配置。
    #
    #     被 main.py 直接运行时调用，也被 web.py 在守护线程中调用。
    #     global 声明由重构脚本依据原模块级赋值自动生成，保持语义不变。
    #     若 non_interactive=True（如 web.py 守护线程），URL_config 为空时跳过 input() 阻塞。
    #
    global a, acfun_cookie, args, baidu_cookie, bark_msg_api, bark_msg_level, bark_msg_ring, begin_push_message_text, begin_show_push, bigo_cookie, bili_cookie, blued_cookie
    global changliao_cookie, check_path, chzzk_cookie, clean_emoji, converts_to_h264, converts_to_mp4, create_time_file, custom_script, delay_default, delete_origin_file, dingtalk_api_url
    global dingtalk_is_atall, dingtalk_phone_num, disable_record, disk_space_limit, douyu_cookie, dy_cookie, email_host, email_password, enable_https_recording, enable_proxy_platform, enable_proxy_platform_list, exit_recording
    global extra_enable_proxy, extra_enable_proxy_platform_list, faceit_cookie, filename_by_title, first_run, first_start, flextv_cookie, flextv_password, flextv_username, folder_by_author, folder_by_time, folder_by_title
    global haixiu_cookie, host_id, huajiao_cookie, huamao_cookie, hy_cookie, ini_URL_content, input_url, is_comment_line, is_run_script, jd_cookie, ks_cookie, kugou_cookie
    global laixiu_cookie, langlive_cookie, lehaitv_cookie, lianjie_cookie, line, line_list, line_spilt, liuxing_cookie, live_status_push, liveme_cookie, local_delay_default, login_email
    global look_cookie, loop_time, maoerfm_cookie, max_request, middle, migu_cookie, monitoring, name, netease_cookie, new_line, new_url, new_word
    global ntfy_api, ntfy_email, ntfy_tags, open_smtp_ssl, origin_line, over_push_message_text, over_show_push, pandatv_cookie, picarto_cookie, popkontv_access_token, popkontv_partner_code, popkontv_password
    global popkontv_username, pplive_cookie, proxy_addr, proxy_addr_bak, push_check_seconds, push_message_title, pushplus_token, qiandurebo_cookie, quality, replace_words, running_snapshot, running_url
    global seen_urls, semaphore, sender_email, sender_name, shopee_cookie, show_url, showroom_cookie, six_room_cookie, smtp_port, sooplive_cookie, sooplive_password, sooplive_username
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

    while True:

        try:
            if not os.path.isfile(config_file):
                with open(config_file, "w", encoding=text_encoding) as file:
                    pass

            # 每轮重新读取配置文件，支持运行期间热更新
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
        except OSError as err:
            logger.error(f"发生 I/O 错误: {err}")

        video_save_path = read_config_value(config, "录制设置", "直播保存路径(不填则默认)", "")
        folder_by_author = options.get(read_config_value(config, "录制设置", "保存文件夹是否以作者区分", "是"), False)
        folder_by_time = options.get(read_config_value(config, "录制设置", "保存文件夹是否以时间区分", "否"), False)
        folder_by_title = options.get(read_config_value(config, "录制设置", "保存文件夹是否以标题区分", "否"), False)
        filename_by_title = options.get(read_config_value(config, "录制设置", "保存文件名是否包含标题", "否"), False)
        clean_emoji = options.get(read_config_value(config, "录制设置", "是否去除名称中的表情符号", "是"), True)
        video_save_type = read_config_value(config, "录制设置", "视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频", "ts")
        video_record_quality = read_config_value(config, "录制设置", "原画|超清|高清|标清|流畅", "原画")
        use_proxy = options.get(read_config_value(config, "录制设置", "是否使用代理ip(是/否)", "是"), False)
        proxy_addr_bak = read_config_value(config, "录制设置", "代理地址", "")
        proxy_addr = None if not use_proxy else proxy_addr_bak
        max_request = int(read_config_value(config, "录制设置", "同一时间访问网络的线程数", 3))
        semaphore = threading.Semaphore(max_request)
        delay_default = int(read_config_value(config, "录制设置", "循环时间(秒)", 120))
        local_delay_default = int(read_config_value(config, "录制设置", "排队读取网址时间(秒)", 0))
        loop_time = options.get(read_config_value(config, "录制设置", "是否显示循环秒数", "否"), False)
        show_url = options.get(read_config_value(config, "录制设置", "是否显示直播源地址", "否"), False)
        split_video_by_time = options.get(read_config_value(config, "录制设置", "分段录制是否开启", "否"), False)
        enable_https_recording = options.get(
            read_config_value(config, "录制设置", "是否强制启用https录制", "否"), False
        )
        disk_space_limit = float(read_config_value(config, "录制设置", "录制空间剩余阈值(gb)", 1.0))
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
        push_check_seconds = int(read_config_value(config, "推送配置", "直播推送检测频率(秒)", 1800))
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
        if utils.check_disk_capacity(check_path, show=first_run) < disk_space_limit:
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

                    if url_tuple[1] not in running_list:
                        print(f"\r{'新增' if not first_start else '传入'}地址: {url_tuple[1]}")
                        with record_state_lock:
                            monitoring += 1
                            running_list.append(url_tuple[1])
                            args = (url_tuple, monitoring)
                        create_var[f"thread_{monitoring}"] = threading.Thread(target=start_record, args=args)
                        create_var[f"thread_{monitoring}"].daemon = True
                        create_var[f"thread_{monitoring}"].start()
                        time.sleep(local_delay_default)
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
