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
import shutil
import signal
import subprocess
import threading
import time
import types
import uuid
from collections import deque
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import urlsplit

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
    read_config_bool,
    read_config_value,
    update_anchor_name,
    update_file,
)
from src.ffmpeg_install import check_ffmpeg, ffmpeg_path, should_prepend_bundled_ffmpeg_dir

# ---- 重构：以下函数已抽离至 src 子模块，此处重新导出以保持 main.<name> 命名空间兼容 ----
from src.ffmpeg_proc import (
    _cleanup_single_ffmpeg_process,
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
from src.recorder_status import (
    display_info,
    get_status,
)
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

# 本 import 列表刻意不含 converts_m4a / segment_video / shlex / collections.abc.Mapping：
# 生产代码零调用，留着会让静态检查报警、并让后来者误以为「音频直出 m4a / 分段转码」链路已接通
# （函数本身仍在 src/video_postprocess.py，有单测、是完整工具 API，将来接该配置项可直接启用）。
# 唯一例外是 _run_ffmpeg_checked：本文件确实无调用点，但它是 tests/test_main_fixes.py 的
# patch / 直调目标（该用例经 `main_mod._run_ffmpeg_checked(...)` 断言超时终止与退出码处理），
# 删掉会让该用例 AttributeError，故保留导入。
# 判据：只有「生产代码零引用**且**无测试依赖」才算可摘的死引用。
#   [历史注] 2026-09-12 F-15 摘 converts_m4a / segment_video；2026-09-22 MIN-2224 摘 shlex / Mapping。
from src.video_postprocess import (
    _run_ffmpeg_checked,
    converts_mp4,
    generate_subtitles,
    get_startup_info,
)


# 获取当前程序版本号；无入参，返回形如 "v1.2.3" 的字符串（都取不到时回退 "v0.0.0"）
def _read_version_from_pyproject() -> str:
    # 两条路径的分工：已安装为发行包时 importlib.metadata 直接命中；源码直跑（未 pip install）
    # 时它取不到包名，只能自己解析 pyproject.toml（版本号的唯一事实源）。
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
# 磁盘空间不足导致的「录制暂停」标志（SEV-2206，2026-09-22）。
# 与 exit_recording 的区别：exit_recording 是**进程级**退出意图（信号 / 未捕获异常 / 磁盘满
# 最终退出都不复位，仅下面 else 分支的空间恢复路径会清它一次）；disk_limited 表达的是**可逆的
# 资源约束**——磁盘腾出空间后必须复位，否则主循环与房间线程会永远停在「暂停」态。
# 二者在「空间不足」期间同步置位（房间线程因此停止拉流），恢复时同步复位。
# 可复核判据：tests/test_regression_2026_09_22_main.py::test_disk_limited_is_recoverable
disk_limited: bool = False
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
error_threshold: float = 0.5  # 错误率阈值（0-1），错误率超过后降低并发

# URL 和配置管理
url_tuples_list: list[tuple[str, str, str]] = []  # 解析后的 URL 配置列表（格式：(画质, URL, 主播名)
# 被注释掉的 URL 集合：主循环与 check_subprocess/start_record 均只做成员检测，
# 用 set 保证 O(1)（见下方主循环注释）。
url_comments: set[str] = set()
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
# MI-09：进程启动时刻，专供 uptime 计算。start_display_time 会被 display_info 每 5 秒
# 改写为「当前时刻」（注释掉的「本软件已运行」打印留下的历史行为），
# 而 recorder_status.get_status 仍按 now - start_display_time 算 uptime，
# 结果只要有过一次录制，面板上的运行时长就恒在 0~5 秒之间跳变，
# 运维据「是否需要重启」判断的依据失效。两者语义必须分离。
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
rstr: str = r"[\/\\\:\*\？?\"\<\>\|&#.。,， ~！·% ]"  # 文件名字符过滤正则
# ↑ 2026-09-22 补 `%`（SEV-2202，本机 ffmpeg/ffmpeg.exe 实测）：输出路径整串会作为 ffmpeg 的
# 文件名模板解释，主播名/标题里的裸 `%` 会与分段模板末位的 `_%03d` 一起构成非法占位符，
# ffmpeg 以 -22(EINVAL) 秒退；退出码又被 _describe_return_code 解释成「容器/编码不匹配」，
# 再落进「CDN 快速失败」判定，把健康线路记进探针退避并按 host 推熔断。
# 实测对照：含 `%` 的分段模板与含孤立 `%d` 的模板一律 rc=-22；干净模板与非分段形态含 `%` 均成功。
# 回归锁：tests/test_regression_2026_09_22_main.py::test_segment_template_has_single_percent_placeholder
default_path: str = f"{script_path}/downloads"  # 默认下载目录
os.makedirs(default_path, exist_ok=True)
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
# MID-07：单次录制时长上限（秒），由 main() 每轮从「录制设置」读取；0/负值表示不限制，
# 分段开/关均参与判定（见 check_subprocess 的 _record_limit_seconds）。
# 此处的字面默认值与下方看门狗小节的 _MAX_RECORD_SECONDS 保持同值——模块级语句顺序执行，
# 该常量在本行之后才定义，不能在此直接引用（main() 读取配置时以该常量为兜底默认）。
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
host_id: re.Match[str] | None = None
input_url: str = ""
is_comment_line: bool = False
line: str = ""
line_list: set[str] = set()  # 主循环内用于检测重复配置行，只做成员检测，用 set 保证 O(1)
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
url_line_list: set[str] = set()  # 主循环内已解析的 URL，只做成员检测，用 set 保证 O(1)
url_tuple: tuple[str, ...] = ()

_recorder_thread = None  # 由 web.py 设置，用于 get_status() 检测存活


# 可中断等待（MIN-2226，2026-09-22）：把散落各处的一次性 time.sleep(n) 收敛成逐秒 tick。
# 约定理由：本文件里所有「退出/停止录制/URL 被注释」的判定都只能在**循环顶**发生，
# 一次性 sleep 会让房间线程或主循环在最坏情况下滞留整个等待周期才响应——Web 面板点了
# 「停止录制」却仍有线程在拉流，或退出信号来了却要等满 N 秒。改为每秒醒来一次重新求值
# 模块全局（晚绑定，天然看到别的线程/Web 面板改动后的最新值）即可立即跳出。
# record_url 非空时追加第三个条件「该 URL 已被注释」（与房间线程循环顶的三条件同构）。
def _interruptible_sleep(seconds: float, record_url: str | None = None) -> None:
    _remaining = int(seconds) if seconds > 0 else 0
    while _remaining > 0:
        if exit_recording or not recording_enabled:
            break
        if record_url is not None and record_url in url_comments:
            break
        time.sleep(1)
        _remaining -= 1


# 后处理线程池的显式收尾（SEV-2207，2026-09-22，main.py 侧）。
# 不能把收尾留给解释器退出时的线程汇合：3.14 的 concurrent.futures.thread 是经
# threading._register_atexit(_python_exit) 登记的，而 threading._shutdown() 在 atexit 回调
# **之前**执行（Py_FinalizeEx 先 wait_for_thread_shutdown 再 call_py_exitfuncs）。于是
# 「池内 worker 的 join」恒早于本文件注册的 archive_runtime_logs /
# cleanup_all_ffmpeg_processes / close_all_clients_sync 三个钩子——转封装任务最长要占
# _MAX_CONVERT_TIMEOUT（src/video_postprocess.py:31，3600s），这期间 ffmpeg 子进程无人终止、
# 运行日志无人归档，表现为「点了退出却卡住，且事后查不到日志」。
# 本侧的修法是在**我们自己的退出路径**（safe_exit / 磁盘满退出）先显式 drain，
# 让退出顺序回到主进程手里；池已 drain 后 _python_exit 再跑就是空转，顺序问题自然消解。
# shutdown_postprocess_executor(wait, cancel_futures) 由 K 组在 src/video_postprocess.py 暴露；
# 该函数尚未落地时用 getattr 安全跳过——不得因这一个钩子阻塞或打断退出流程。
def _shutdown_postprocess_executor() -> None:
    try:
        from src import video_postprocess as _vp
    except Exception:
        return
    _shutdown = getattr(_vp, "shutdown_postprocess_executor", None)
    if _shutdown is None:
        return
    try:
        _shutdown(wait=True, cancel_futures=False)
    except Exception as e:
        logger.warning(i18n.tr("后处理线程池收尾失败: {type_name}: {e}", type_name=type(e).__name__, e=e))


# 信号处理器：置退出标志、清理 ffmpeg 进程与 HTTP 连接池后退出进程；_signum/_frame 为信号回调形参（未使用），不返回
def safe_exit(_signum: int, _frame: types.FrameType | None) -> None:
    global exit_recording
    exit_recording = True
    color_obj.print_colored("\n正在安全退出...", color_obj.YELLOW)
    # SEV-2207：先排空后处理线程池，再做 ffmpeg / HTTP 连接池清理（理由见函数上方注释）
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

# 进程异常退出时兜底清理 ffmpeg 与 HTTP 连接池（覆盖硬杀 / 未捕获异常等非优雅退出路径）
# 注意注册顺序：atexit 为 LIFO，归档必须先于两个 cleanup 注册——
# 进程退出（信号 safe_exit / 磁盘满 / 未捕获异常 / web 面板退出）时把 ffmpeg 清理等
# 收尾日志一并收进归档文件，四个运行日志统一按「原名_YYYYMMDD_HHMMSS.扩展名」改名
_atexit_result_0 = atexit.register(archive_runtime_logs, reopen_streams=False)
_atexit_result_1 = atexit.register(cleanup_all_ffmpeg_processes)
# async_req 供 _resolve_hy_fan_room_segment 解析虎牙移动端短链（redirect_url=True 契约）；
# 与 close_all_clients_sync 同源：src.async_http 本就是 main 的直接依赖，无新增导入环。
from src.async_http import async_req, close_all_clients_sync

_atexit_result_2 = atexit.register(close_all_clients_sync)


os_type: str = os.name
color_obj: "utils.Color" = utils.Color()
# 将 ffmpeg 目录前置到当前 PATH：使用实时 os.environ（而非 import 时快照），
# 避免丢弃 import 之后对其余 PATH 条目的追加修改；并跳过重复插入。
# 前置还要过一道「Apple Silicon 让位」判据（W6，2026-09-22）：包内 macOS ffmpeg 是 evermeet 的
# x86_64 静态构建（上游不发布 arm64 构建），无条件前置会遮蔽用户已装的原生 arm64 ffmpeg
# 并强制走 Rosetta 转译。判据本身**不在这里写**——收敛到
# src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir（唯一事实源，可在 Windows 上单测
# 「非 darwin 恒前置」分支），本文件只保留原有的「重复插入跳过」守卫。
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
    # 虎牙移动端分享短链 host（https://hy.fan/JbmwoV）：路径段为纯数字时即房间号，
    # 否则是短码、需跟随 301 跳转解析出真实房间段；两种形态都由 _resolve_hy_fan 归一成
    # www.huya.com 房间链接后复用桌面解析链路。与 m.douyu.com 同理：准入按
    # `url_host in PLATFORM_HOST` 精确匹配，缺此项时短链在读取 URL 配置阶段就被判
    # 「本行包含未知链接.此条跳过」并注释掉，根本走不到解析。
    "hy.fan",
    "www.douyu.com",
    # 斗鱼移动端页面 host（https://m.douyu.com/8751648）：房间信息与取流接口只认数字 rid、
    # 与来源域名无关，故与 www 共用 _resolve_douyu_com（详见 spider.get_douyu_info_data 注释）。
    # 准入侧按 `url_host in PLATFORM_HOST` 精确匹配，缺此项时移动端链接在读取 URL 配置阶段
    # 就被判「本行包含未知链接.此条跳过」并注释掉，根本走不到解析。
    "m.douyu.com",
    "www.yy.com",
    "live.bilibili.com",
    # B站移动端分享短链 host（https://b23.tv/ZyQrgYf）：路径段为纯数字时即房间号，
    # 否则是短码、需跟随 302 跳转解析出真实房间号；两种形态都由 _resolve_b23_tv 归一成
    # live.bilibili.com 房间链接后复用桌面解析链路。与 hy.fan / m.douyu.com 同理：准入按
    # `url_host in PLATFORM_HOST` 精确匹配，缺此项时短链在读取 URL 配置阶段就被判
    # 「本行包含未知链接.此条跳过」并注释掉，根本走不到解析。
    "b23.tv",
    # MID-04 修复（2026-09-20）：摘除 www.redelight.cn —— 该 host 无任何解析入口
    # （spider/stream/JS 签名脚本全仓零引用，平台清单亦无对应平台名），留着只会让用户配一个
    # 「每轮一条 error、永不录制、也不记 record_error」的地址：房间线程走 _resolve_unrecognized
    # → sleep → 无限空转，白占监控位；摘除后主循环按「包含未知链接」把它注释掉，与其它未知地址一致。
    # 同类审计回归锁见 tests/test_platform_dispatch.py
    # （「PLATFORM_HOST 每项必被某个 resolver 匹配片段命中」）。
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


# 用 httpx 流式把 source_url（FLV 直链）直接写入 save_path，不经 ffmpeg；请求头/cookie/UA
# 与 ffmpeg 录制路径保持一致；record_name/live_url 用于中断判断与状态清理，platform 用于补
# 对应平台请求头；返回是否下载完成。
# 失败时只清理**零字节**残留（F-03，2026-09-12）：open(save_path, "wb") 一进入就创建了文件，
# HTTP 非 200 时原实现直接 return False，把 0 字节的 .flv 留在保存目录——它会被归档/转码链路
# 当成有效产物处理，用户看到「录到了文件但打不开」却查不到原因。
# 已下载到内容时（主播下播、CDN 掐断、主动停止）一律保留，与 ffmpeg 录制路径语义一致
# （不替用户丢弃可能有价值的部分内容）。
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
            # MID-2209 修复（2026-09-22）：取不到平台专属 UA 时一律回落到同一个 MOBILE_UA
            # （与 ffmpeg 路径同一常量）。原写法 `if ua:` 恒不成立——get_record_user_agent 只对
            # 虎牙/B站返回非空（src/stream_select.py 的 _DESKTOP_UA_PLATFORMS），而强制直下的
            # 平台是 shopee / 花椒直播，于是 headers 里根本没有 User-Agent，httpx 以其默认
            # `python-httpx/<版本>` 发请求；CDN 侧普遍按 UA 分流/风控，校验探针用移动端 UA
            # 探活通过、真正下载却被风控拒（403/非 200），而失败只按 host 记错误样本，
            # 日志上看不出是 UA 问题——「与 ffmpeg 录制路径保持一致」当时是假的。
            # 回归锁（行为用例，真调 direct_download_stream 捕获 httpx 请求头）：
            # tests/test_regression_2026_09_22_main.py::test_direct_download_always_sends_ua
            headers["User-Agent"] = get_record_user_agent(platform) or MOBILE_UA

            with httpx.Client(
                timeout=30, verify=_http_config.get_effective_ssl_verify(platform), headers=headers
            ) as client:
                with client.stream("GET", source_url, headers=headers, follow_redirects=True) as response:
                    if response.status_code != 200:
                        logger.error(
                            i18n.tr(
                                "请求直播流失败: {source_url} - 状态码: {status_code}",
                                # MID-28 修复（2026-09-20）：拉流地址带签名参数（wsSecret/txSecret/
                                # signature 等），必须先过 mask_credentials 再入日志。占位符名沿用
                                # 目录既有 msgid（改名等于新增四语条目，须由 i18n 侧统一收口）。
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
                    # MID-06 修复（2026-09-20）：HTTP 200 + 空/极小响应体不是成功。
                    # 原实现在此无条件 return True：调用方（start_record 直下分支）据此打印
                    # 「直播录制完成」并记 record_success(record_host)，而 finally 已把 0 字节
                    # 文件删掉——这正是 CR-06 在 ffmpeg 路径专门修掉的形态，在直下路径
                    # （shopee/花椒）仍存，且坏线路不记任何失败样本、绕开按 host 熔断统计。
                    # 口径与 check_subprocess 的 `0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES` 统一。
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
                # MID-28 修复（2026-09-20）：同上方非 200 分支，入日志前先脱敏。
                source_url=utils.mask_credentials(source_url),
                type_name=type(e).__name__,
                e=e,
                get_error_line=_get_error_line(e),
            )
        )
        return False
    finally:
        # 仅在「open 已创建文件但一个字节都没写」时删除（判据与理由见函数头 F-03 注释）
        if _downloaded == 0:
            try:
                os.remove(save_path)
                logger.debug(i18n.tr("已清理零字节的直下残留文件: {save_path}", save_path=save_path))
            except OSError:
                pass


# 分段录制的「输出扩展名 → segment 内层容器」映射：容器必须与输出文件的扩展名严格一致，
# 否则会产出「容器与扩展名不符」的文件——轻则播放器拒绝，重则直接封装失败。
# 历史回归（2026-09-04）：TS 分支误用 ipod、M4A 分支误用 mpegts（两个值被互换），
# 导致 HEVC 原画 copy 进 ipod 时 AVERROR(EINVAL) 退出（Windows 上退出码显示为 4294967274），
# 而 H.264 虽不报错却把 MP4 内容写进 .ts 文件名（静默损坏，比报错更难排查）。
# 收敛为单一映射表后，新增分支只能查表取值，配合 tests/test_record_container.py 的断言，
# 杜绝「容器 ↔ 扩展名」再次错位。
SEGMENT_FORMAT_BY_SUFFIX: dict[str, str] = {
    ".ts": "mpegts",
    ".flv": "flv",
    ".mkv": "matroska",
    ".mp4": "mp4",
    ".m4a": "ipod",
    # .mp3 → mp3 容器：此前表内无 .mp3，查表落空后被兜底成 ipod，会让 MP3 音频装进
    # MP4 容器（与历史「TS 装进 ipod」同类错配）。补齐后两路音频均可显式查表取值。
    ".mp3": "mp3",
}


# ffmpeg「快速失败」判定阈值（秒）：进程存活不超过该值即退出，视为输入打开被 CDN 拒绝
# 的签名（实测虎牙 HS 线路探针 200 后 ffmpeg 立即 403，约 1 秒退出）；拉流中断/重连耗尽
# （-reconnect_delay_max 60）通常远超该值，不属此类。模块级常量便于测试注入。
_FFMPEG_FAST_FAIL_SECONDS = 20.0

# 等待录制槽位时的轮询间隔（秒）：见 check_subprocess 中 acquire(timeout=...) 的说明。
# 取 1 秒——既保证「停止录制」在 1 秒内被排队房间感知，又不至于让 80+ 房间的
# 等待线程每秒集体唤醒造成明显调度开销。
_SEM_WAIT_TICK = 1.0

# CR-05 修复：录制看门狗的两个阈值。守护循环若只有「进程自己退出 / 用户停止或注释」两个出口，
# 而 FLV 输入侧刻意保留了 -reconnect* 系列（HLS 已移除），CDN 掐断长连接时 ffmpeg 会按
# 1/3/7/…/60s 指数退避无限重连、永不退出；挂起的 ffmpeg 一直持有录制槽位（acquire 在 Popen
# 之前），槽位被逐条耗尽后所有房间录制饿死，且无法自愈。
# ① 单次录制时长上限 _MAX_RECORD_SECONDS：可配置，默认 6 小时、0 为不限制（SEV-08 / MID-07，
#    2026-09-20）——24 小时轮播/官方电台房间（B站/斗鱼/抖音的 CCTV 型直播间）超过 6 小时是
#    常态而非挂起。分段开/关均生效（MID-N04，2026-09-21 修正 MID-07 的「只认分段」半修）；
#    命中上限按「正常录完」收尾，不再记失败样本。
# ② 停滞窗口 _RECORD_STALL_SECONDS：输出文件连续 10 分钟毫无增长即判定停滞。基准是「最后一次
#    观测到增长的时刻」（见 check_subprocess::_stall_since），不是进程起跑时刻——旧写法配 30s
#    采样间隔，实际容忍窗口只有 30s（满 10 分钟后的任意一次无增长采样即杀进程）。
_MAX_RECORD_SECONDS = 6 * 60 * 60  # 「单次录制时长上限(秒)」的配置默认值
_RECORD_STALL_SECONDS = 10 * 60
# 停滞检测的文件大小采样间隔（秒）：每次采样都要 stat 一次，无需每轮都做。
_RECORD_STALL_PROBE_INTERVAL = 30.0
# 看门狗「单轮可信推进量」的上界（MID-2208，2026-09-23）：守护循环每轮 time.sleep(1)，
# 正常情况下两次取时之间的增量就是 1s 量级。取 300s 是为 80+ 房间并发下的 GIL 竞争、
# 满载磁盘 IO、以及单次 stat 慢盘留足余量；超过该上界的增量（或任何倒退）只可能是
# 挂钟被 NTP 校时/手动改表/挂起恢复拨动，一律按名义 1s 计，见 check_subprocess::_watch_seconds。
_WATCH_TICK_MAX_SECONDS = 300.0
_WATCH_TICK_NOMINAL_SECONDS = 1.0

# CR-06 修复：判定「录制产物有效」的最小字节数。HLS 播放列表返回 200 但分片全 404 时，
# ffmpeg 在 -loglevel error 下零输出、零字节产出、退出码仍为 0；旧实现只看退出码，
# 于是把空文件当成成功，还会撤销上一轮刚写入的线路退避，形成无法自愈的零字节闭环。
_MIN_VALID_RECORD_BYTES = 1024

# WD-12 修复：录后转码的专用线程池。
# 录制侧有 recording_semaphore 做并发治理，但录后处理原来完全没有——每产生一个分段就
# threading.Thread(...).start() 一次，线程数随「房间数 × 分段数」线性增长；开启
# converts_to_h264 时每个线程跑一路 libx264 重编码（单个 ffmpeg 最长存活 600s）。
# 80+ 房间 + 短分段场景下会瞬时堆出数十条 CPU 密集进程，与正在录制的 ffmpeg 争抢
# CPU/磁盘 IO，直接诱发录制丢帧与 -max_muxing_queue_size 溢出。
# 改为固定容量线程池：队列无上限但并发受控，产物只会延后转码，不会与录制抢资源。
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


# ffmpeg 退出码的 errno 语义提示：Windows 上 subprocess 拿到的是无符号 32 位值
# （如 -22 呈现为 4294967274），直接打印原值无法定位问题方向。仅收录本仓实测出现过
# 或语义明确可指路的取值，未知值返回空串，避免给日志堆噪音。
# 2026-09-11 补充：-22 除容器/编码错配外，还有「输入选项解析失败」一类（-reconnect*
# 缺值导致 reconnect_streamed 把下一个选项名当作值），EINVAL 提示需同时覆盖两类成因，
# 否则会把排查方向误导到容器问题上。
_FFMPEG_ERRNO_HINTS: dict[int, str] = {
    -22: " (EINVAL：无效参数，常见于容器/编码不匹配（如 HEVC 写进 ipod 容器）或输入选项解析失败)",
    -11: " (EAGAIN：输出写入被阻塞，多为磁盘 IO 或管道背压)",
    -2: " (ENOENT：输入地址或输出路径不存在)",
    -109: " (EBADF：连接被对端重置，多为 CDN 断流)",
    1: " (ffmpeg 常规错误，详见上方 ffmpeg 输出)",
    2: " (命令行参数错误)",
    255: " (ffmpeg 初始化失败/被中断)",
}


# 把 ffmpeg 退出码归一化为有符号 errno 并附语义提示：4294967274 → -22 (EINVAL…)。
# 仅当值超出 32 位有符号正区间时才做补码换算，正常小退出码原样返回。
def _describe_return_code(return_code: int) -> str:
    signed_rc = return_code - (1 << 32) if return_code > 0x7FFFFFFF else return_code
    return f"{signed_rc}{_FFMPEG_ERRNO_HINTS.get(signed_rc, '')}"


# 「输出侧本地失败」的豁免判据只有一条：输出父目录当前不存在（判定点见 check_subprocess
# 失败分支的同编号注释，MID-02）。曾设想过第二条判据（MID-N01）——读 ffmpeg 已缓冲输出、
# 按写侧特征归因（_FFMPEG_OUTPUT_FAILURE_MARKERS / _ffmpeg_reported_output_failure），
# 但 Popen 从未设 stdout=PIPE（stdin=PIPE + stderr=STDOUT，ffmpeg 输出直接进父控制台），
# proc.stdout 恒为 None → 恒返回 False；补 PIPE 又需在守护循环内持续消费，否则管道写满会
# 卡死 ffmpeg、比现状更糟——为一个二级豁免判据引入守护级复杂度不划算，故已整体删除。
#   [历史注] 2026-09-21 提出、2026-09-22 才落地：上一轮只删定义、留下调用点，mypy /
#   basedpyright / pytest 三面同时转红；该调用点在 `and` 右侧，只在「父目录不存在」这条分支上
#   真抛 NameError（Linux CI 的 /tmp 存在、短路不炸，Windows 本机必炸），是延迟爆炸的运行期
#   缺陷而非纯静态噪音。删除模块级符号前必须 grep 全部调用点，现已由 scripts/check_annotations.py
#   的符号可达性检查固化成门禁动作。


# 分段产物的「序号后缀」形状：`_<数字>.<扩展名>`，出现在字符串末尾。
# 刻意不用定长 `???` glob —— ffmpeg 的 `%03d` 在段号超过 999 时会输出 4 位，
# 定长模式会静默漏计这部分文件（_convert_after_record 同一口径）。
_SEG_INDEX_RE = re.compile(r"_\d+\.[A-Za-z0-9]+$")

# 分段输出**模板**的形状：`..._%03d.ts` / `..._%02d.m4a`（含 ffmpeg 的 %d 占位符）。
# MID-08 修复：check_subprocess 判定「是否分段」一律由已冻结的命令输出模板推导，
# 不再读模块全局 split_video_by_time——主循环每 3s 热加载配置，录制中途在面板切换
# 「分段录制是否开启」会让收尾校验按另一种形状 glob（恒返回 -1，零字节保护静默失效），
# 或对含 %03d 的字面路径提交注定失败的转码，并破坏 _000.srt ↔ _000.ts 的对应不变量。
# 只匹配「扩展名之前的序号占位符」，避免把标题里恰好含 %d 的文件名误判成分段模板。
_SEGMENT_TEMPLATE_RE = re.compile(r"_%0?\dd\.[A-Za-z0-9]+$")


# 输出路径是否为 ffmpeg 分段模板（决定产物求和方式、弹幕分片与录后转码的匹配形状）
def _is_segmented_output(save_file_path: str) -> bool:
    return _SEGMENT_TEMPLATE_RE.search(save_file_path) is not None


# 分段模板 → 实际落盘的分段文件（纯字符串前缀/后缀 + 序号正则，**绝不走 glob/fnmatch**）。
# 2026-09-22 实测（MID-2207 + MIN-2227）：rstr 里的 `[` `]` 只是字符类定界符、从不被清洗，
# 是合法文件名字符；而 Path.glob 经 fnmatch.translate 会把 `主播[A组]_..._*.ts` 译成字符类
# → 恒返回空 → 分段求和恒 -1（健康分段录制满 10 分钟即被看门狗判停滞杀掉）、
# 转码永远「未找到分段文件」。故三处枚举统一收敛到本函数：os.scandir + startswith + endswith。
# 三态返回（MID-2207 后半，2026-09-23），两种结果**不得**再压成同一种：
#   - None = 目录不可读（不存在 / 权限 / 网络盘抖动 / 目录被转码进程临时替换）→ 观测失败，对产物一无所知；
#   - []   = 目录可读但无任何匹配分段 → 「确实还没有产物」，是真实的零增长观测。
# 二者曾同返 []，于是一次偶发的 scandir 失败就能让**健康的分段录制满 10 分钟被终止**，并向
# 调度器投一条假的 record_error（污染按 host 的熔断统计、把好线路拉进探针退避）。调用方在观测
# 失败时不得刷新停滞基准、不得判停滞（见 _watchdog_hit 与
# tests/test_regression_2026_09_22_main.py::test_segment_observation_failure_is_not_stall）。
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


# CR-06 修复：统计本次录制实际落盘字节数。分段录制时 save_file_path 是含 %03d 的输出模板，
# 直接 stat 恒失败，须按 ffmpeg 实际的 _000/_001… 序号文件求和；单文件录制则直接取大小。
# 三态返回（MID-2207 后半，2026-09-23）：>=0 实际字节数；-1 路径/分段确实不存在（尚无产物）；
# None 观测失败（目录不可读）。调用方必须把 None 与 -1 分开处理——前者不得据此判停滞。
#
# MID-05 修复（2026-09-20）：分段的扩展名必须由模板推导、枚举走 _segment_files，不能写死 `.ts`。
# 早期的两种 glob 写法（`{base_stem}_???.ts` 与 `{base_stem}_*.ts`）都写死了 `.ts`，
# 对分段 FLV/MKV/MP4/音频恒不命中 → 恒返回 -1 →
# check_subprocess 的 `0 <= _produced_bytes < _MIN_VALID_RECORD_BYTES` 永不成立，
# 于是 CR-06 修掉的「零字节记成功、撤销线路退避」闭环在所有非 TS 分段形态上原样复发
# ——而分段 FLV 恰是虎牙/斗鱼的常见形态；且 glob 把 `[...]` 当字符类，
# 主播名含方括号时连 TS 形态都恒不命中、健康录制被误杀（MIN-2227）。
def _record_output_bytes(save_file_path: str, split_video_by_time: bool) -> int | None:
    if not split_video_by_time:
        try:
            return os.path.getsize(save_file_path)
        except OSError:
            # 非分段形态没有「目录可读但无产物」的中间态：文件不存在即「本轮还没写出产物」，
            # 正是 MID-N04 要判停滞的那类真实零产物信号，故保持 -1 而不是 None。
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
    # 录制并发软上限（资源治理）：限制同时进行的 ffmpeg 录制数，防 80+ 任务同时录制拖垮
    # CPU/磁盘/带宽。recording_limit=0 时 recording_semaphore 容量极高，acquire 不阻塞（等同不限制）。
    # 必须在 Popen 之前占槽：若先起进程再 acquire，并发上限根本约束不到 ffmpeg 进程数——
    # N 个房间仍会同时拉起 N 个 ffmpeg 拉流写盘（正是要防的资源耗尽），被阻塞的只是房间线程，
    # 且阻塞期间不检查注释/停止标志，无法及时退出。
    #
    # acquire 带超时轮询（2026-09-12）：原为无限阻塞，排队期间完全不看退出标志——Web 点
    # 「停止录制」或 URL 被注释后，排在队里的房间线程仍会干等到拿到槽位才继续（最坏等满一个
    # 完整录制周期），之后才在收包循环里发现该退出——表现为「点了停止，几十秒后仍有房间在起 ffmpeg」。
    # 每 _SEM_WAIT_TICK 秒检查一次退出条件，命中即放弃本轮录制（返回 True，与下方
    # 「被注释/已停止」语义一致：调用方据此 return 退出本房间线程）。
    _rec_sem = recording_semaphore
    while not _rec_sem.acquire(timeout=_SEM_WAIT_TICK):
        if record_url in url_comments or exit_recording or not recording_enabled:
            logger.debug(
                i18n.tr(
                    "[{record_name}]等待录制槽位期间检测到停止信号，放弃本轮录制",
                    record_name=record_name,
                )
            )
            # MID-01 修复：放弃本轮录制前必须回收录制状态。登记（recording / recording_time_list）
            # 早在 start_record 的录制链里完成，此处原样 return True 会留下幽灵「录制中」条目：
            #   ① 面板/CLI 永久显示该房间在录制；
            #   ② 磁盘满退出判定 `if not recording:` 恒假 → 已置 exit_recording 却永不退出、主循环空转；
            #   ③ 调用方把 True 一律解读为「录制中断」，TS 分支因此对从未创建的输出路径提交一次转码。
            # 与同函数下方「被注释/停止」分支的清理保持同构。
            clear_record_info(record_name, record_url)
            return True
    # MID-12 修复：process 提前置 None，令 finally 的统一回收能区分「Popen 之前就抛错」与
    # 「进程已起、但守护段（弹幕启动/字幕线程 start）抛错」——后者会留下无人守护的孤儿 ffmpeg
    process: subprocess.Popen[bytes] | None = None
    # SEV-N01（2026-09-21）+ SEV-2208（2026-09-22）：弹幕采集器的声明提到 try 之前，使 finally
    # 能安全引用它（原声明在 try 内，try 内任一处抛错即无从停止），并在 finally 内**无条件**
    # stop()——此前的 stop 真身一直在 try/finally 之后，异常穿出 try 时采集器不被停止。
    # finally 里的 unregister / clear_record_info 也与 terminate 解耦，不再共用
    # `process.poll() is None`（进程自然退出时原写法的三个收尾动作全部跳过）。可复核判据：
    # tests/test_regression_2026_09_22_main.py
    #   ::test_danmaku_collector_stopped_when_guard_section_raises
    #   ::test_finally_clears_state_when_process_already_exited
    danmaku_collector: Any = None
    _converged = False
    try:
        save_file_path = ffmpeg_command[-1]
        # MID-08：本函数后续所有「产物形状」判定一律取自已冻结的命令输出模板，不再读模块全局
        _split_output = _is_segmented_output(save_file_path)
        # MID-2208（2026-09-22）：「快速失败」是**时长**判定，必须走单调钟。
        # 系统时钟被 NTP 校时/手动改表/虚拟机挂起恢复拨动时，time.time() 的差值可以是任意值：
        # 向前跳 7 小时会让一次 0.5 秒的秒退看起来跑了 7 小时 → 逃过快速失败判定 → 坏线路
        # 不被记入探针退避（房间无限重撞同一条死线路）；向后跳则相反，把正常的长录制判成秒退。
        # 展示用时间戳（stop_time）仍走挂钟，只有判据换单调钟。
        # 看门狗的两处时长判据（停滞窗口 / 单次上限）同属此族，见下方 _watch_seconds 的
        # 「挂钟增量累加」实现与理由（不能直接套 monotonic 的原因写在那段注释里）。
        # 回归锁：tests/test_regression_2026_09_22_main.py
        #   ::test_fast_fail_judgement_ignores_wall_clock_jump
        _proc_started_mono = time.monotonic()
        process = subprocess.Popen(
            ffmpeg_command, stdin=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
        )

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
        # SEV-N01：本变量的声明已提到 try 之前（见函数体开头），每轮进函数即重置的语义不变。
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
                    # MIN-2242 修复（2026-09-22）：DanmakuCollector.start() 非原子
                    # （_started=True → SrtWriter 已开句柄 → 起 srt_writer 线程 → hub.room_started()
                    #  → 起采集线程），中途任一步抛错都会留下「半启动」对象。原实现直接把唯一
                    # 引用置 None，那些线程与句柄再无人可停止（只能等进程退出）。先幂等 stop 再丢引用。
                    # MIN-2223：异常类型一并入日志——asyncio.TimeoutError 的 str() 是 "()"、
                    # socket.timeout 是空串，只写 {e} 的日志无法定位。
                    if danmaku_collector is not None:
                        danmaku_collector.stop()
                    danmaku_collector = None

        subs_thread_name = f"subs_{Path(subs_file_path).name}"
        if create_time_file and not _split_output and "音频" not in save_type:
            # 2026-09-12 审查 6.1：原写法启动后 create_var 条目永不清理。generate_subtitles 是
            # 死循环（直到 recording 移除 record_name 才 return），线程与录制同生命周期、
            # daemon=True 在进程退出时自动回收，故不泄漏线程本身，但 dict 条目（key + Thread
            # 对象引用）在长生命周期场景下持续累积。故在 finally 里 pop，与 _room_thread_target
            # 的 finally pop 模式一致；graceful 退不出的极端情况（daemon 被信号杀）由进程退出兜底。
            def _subtitle_thread_target() -> None:
                try:
                    generate_subtitles(record_name, subs_file_path)
                finally:
                    with record_state_lock:
                        # MIN-01 同族防护：键由输出文件名推导，跨房间/跨轮可能重名，
                        # 只有登记的仍是本线程时才回收，否则会把别人的条目 pop 掉
                        if create_var.get(subs_thread_name) is threading.current_thread():
                            create_var.pop(subs_thread_name, None)

            create_var[subs_thread_name] = threading.Thread(
                target=_subtitle_thread_target, name=subs_thread_name, daemon=True
            )
            # L-02（2026-10-02）：start() 抛 RuntimeError（can't start new thread）时 target 未运行、
            # finally 清理不执行，create_var 条目缓慢累积；失败即移除登记。
            try:
                create_var[subs_thread_name].start()
            except RuntimeError:
                create_var.pop(subs_thread_name, None)
                raise

        # 内部包装：转调模块级 _terminate_ffmpeg_process（复用公共终止逻辑，避免在此重复实现
        # 导致逻辑漂移），timeout 为总等待秒数，返回是否已退出
        def terminate_ffmpeg_process(proc: subprocess.Popen[bytes], timeout: int = 30) -> bool:
            return _terminate_ffmpeg_process(proc, timeout)

        # CR-05 修复：看门狗状态。_stall_last_size = -1 表示「目录可读但确实还没有任何产物」
        # （MID-2207 后半：目录不可读时 _record_output_bytes 返 None，不落在 -1 上）。
        #
        # SEV-08 修复（2026-09-20）：停滞判据的基准必须是「最后一次观测到增长的时刻」
        # _stall_since（以进程起跑时刻起步 = 「尚未观测到任何增长」的初始态），而不是起跑时刻
        # 本身。旧判据 `now - 起跑时刻 > _RECORD_STALL_SECONDS` 配上 30s 的采样间隔，实际含义是
        # 「满 10 分钟后，任意一次相邻采样之间字节数不变就立刻杀进程」——与日志宣称的
        # 「连续 10 分钟无增长」不符。
        # 合法无增长窗口在本仓真实存在：FLV 输入刻意保留 -reconnect_delay_max 60
        # （1/3/7/15/31s 指数退避，期间一个字节都不写）、主播暂停推流、CDN 短抖同理。
        # 误杀的代价链：走 record_error(host) 把健康线路计入按 host 的熔断失败样本，
        # 且不走 rc==0 分支 → converts_to_mp4 与 clear_ffmpeg_reject 双双跳过。
        #
        # MID-2208（2026-09-23）：停滞窗口与单次时长上限都是**时长**判定，原实现直接吃挂钟，
        # 于是 NTP 校时 / 手动改表 / 虚拟机挂起恢复会把健康的分段录制立刻判成停滞并终止
        # （顺带向调度器投一条假 record_error、把好线路拉进探针退避），反向跳变则让时长上限
        # 永不命中、房间长期占着录制槽位。
        # 为什么不照抄上方快速失败的 time.monotonic()：那会让本仓的受控时钟失去抓手——
        # tests/test_record_watchdog.py::_Clock 只替换 time/sleep（monotonic 仍是真实实现），
        # 而它的「11 分钟停滞」「达到时长上限」两条用例把 ffmpeg 寿命设为 alive_at=inf、
        # 唯一出口就是看门狗；换成裸 monotonic 后这两条用例变成忙等挂死（2026-09-23 实测：
        # 改动后 `pytest tests/test_record_watchdog.py` 45s 不退出，改前 0.48s 全绿）。
        # 该文件不在本轮 main.py 所有权内，故这里改用**挂钟增量累加**（见 _watch_seconds）
        # 拿到同样的跳变免疫：每轮只把「合理范围内」的增量计入累计秒数，越界/倒退按名义
        # sleep 时长计。误差方向安全：漏算只会**推迟**停滞与上限判定（宁慢勿误杀）。
        # 回归锁：tests/test_regression_2026_09_22_main.py
        #   ::test_watchdog_elapsed_ignores_wall_clock_jump
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

        # 单次录制时长上限：取「录制设置」的「单次录制时长上限(秒,0为不限制)」热加载值，
        # 0 或负值表示不限制，分段开/关均生效。命中上限走 _watchdog_hit 的 "limit" 出口
        # = 与 rc==0 同一条正常收尾链路（成功样本 + 转码 + 撤销探针退避），不伪造 CDN 失败。
        # 24 小时轮播/官方电台房间（B站/斗鱼/抖音的 CCTV 型直播间）超过 6 小时是常态，
        # 故上限由配置侧适配：调大或设 0 即不限制。
        #   [历史注] MID-07（2026-09-20）曾把上限限死为「只在分段模式下生效」，MID-N04
        #   （2026-09-21，CODE_REVIEW_2026-09-21）改为两种形态均参与——否则非分段恒 0，
        #   「产物文件从未出现」形态（见下方 _watchdog_hit 的 MID-N04 注释）承诺的
        #   「交给时长上限兜底」在落地上不存在，房间会永久持有录制槽位。
        _record_limit_seconds = max_record_seconds

        def _watchdog_hit() -> str:
            # 返回 "" 表示一切正常；"stall"＝输出停滞（按失败终止）；
            # "limit"＝达到单次录制时长上限（正常收尾，与 rc==0 共用成功路径）
            nonlocal _stall_last_probe, _stall_last_size, _stall_since
            # 本函数所有时刻量统一取「可信已跑秒数」（MID-2208，理由见上方 _watch_seconds 段）
            now = _watch_seconds()
            if _record_limit_seconds > 0 and now - _proc_started_watch > _record_limit_seconds:
                # MIN-2225 修复（2026-09-22）：原文案恒说「分段续录」，而分段关闭时下一轮产出的是
                # 另一个**独立文件**（用户显式选择单文件长录）。按 _split_output 二选一措辞，
                # 两条 msgid 已登记进 _i18n_pending.json。
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
            # MID-N04 修复（2026-09-21，CODE_REVIEW_2026-09-21）：采样改用 _record_output_bytes，
            # 不再裸 stat 模板路径。旧实现把「分段模板 stat 恒失败」与「产物文件从未出现」混为
            # 同一个 OSError 直接放行，且判定又要求 _stall_last_size >= 0——于是
            # 「ffmpeg 打开输入后迟迟不创建输出（或输出被外部删除）」形态永不判停滞，
            # 房间无限持有录制槽位；注释承诺的「交给时长上限兜底」在旧的非分段形态恒为 0。
            # 现在：size < 0（尚无任何产物文件/分段可观测）时，自最后一次观测到增长的时刻
            # （初始即起跑时刻，SEV-08 基准不回退）越过停滞窗口即判停滞；
            # 分段形态自此也获得真实的「无增长」观测能力（求和 _000/_001… 实际序号文件）。
            size = _record_output_bytes(save_file_path, _split_output)
            if size is None:
                # MID-2207 后半修复（2026-09-23）：None = 目录不可读（scandir 抛 OSError），
                # 属**观测失败**而非「产物不存在」。此时对有没有增长一无所知：
                # 既不能刷新停滞基准（会把窗口推到错误时刻、变相延长停滞判定），更不能判停滞
                # ——一次偶发的 scandir 失败（网络盘抖动 / 目录被转码进程临时替换）就会
                # 杀掉健康的分段录制并投一条假 record_error。本直接放行本轮采样，
                # 交给下一次观测或单次时长上限兜底。
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

        # 「达到时长上限」标志：True 时本轮不按挂起/失败处理，而按「正常录完」收尾。
        # 旧实现每 6 小时就往熔断窗口里塞一条失败样本，多房间同 host 时足以把
        # PlatformBreaker 推向 open（收尾链路见上方 _record_limit_seconds 注释）。
        _reached_record_limit = False

        while process.poll() is None:
            # CR-05：守护循环每 1s 轮询一次，看门狗与「注释/停止」检查同轮进行
            _watchdog = _watchdog_hit()
            if _watchdog == "stall":
                # 本分支自带终止与注销，标记已收敛以免 finally 再回收一次（MID-12）
                _converged = True
                if danmaku_collector is not None:
                    danmaku_collector.stop()
                _ = terminate_ffmpeg_process(process)
                unregister_ffmpeg_process(process)
                clear_record_info(record_name, record_url)
                # 按失败处理：让调度器计入失败样本并维持该线路的退避，
                # 而不是像正常结束那样撤销退避（否则坏线路会被反复选中）
                record_error(host_of(record_url))
                return False
            if _watchdog == "limit":
                # 结束守护循环但**不**返回：终止 ffmpeg 后落到下方与 rc==0 相同的收尾链路。
                # 弹幕采集器交给循环外那一次 stop()（整个录制周期仅一次，避免重复停止）
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
                return True
            time.sleep(1)
    finally:
        # 无论正常结束还是提前中断/异常，均释放录制并发槽，避免槽位泄漏导致后续录制饿死。
        # 覆盖范围含 Popen 之前的注册/弹幕启动段：该段一旦抛错，槽位同样必须归还，
        # 否则泄漏累积到上限后所有后续录制永久饿死。
        _rec_sem.release()
        # 无条件停止弹幕采集器（SEV-2208，背景见函数体开头同名注释）：DanmakuCollector.stop()
        # 自带 _stop_called 幂等，与守护循环内各早退分支的调用重复安全。
        if danmaku_collector is not None:
            danmaku_collector.stop()
        # MID-12（2026-09-20）+ SEV-2208（2026-09-22）：Popen 成功之后仍有未被包装的抛错点
        # （最现实的是弹幕采集线程/字幕线程 Thread.start() —— 80+ 房间各自持线程时
        # RuntimeError: can't start new thread 可达）。异常路径必须与「被注释/停滞」等早退路径
        # 同样收敛：终止 + 注销 + 清录制状态；否则孤儿 ffmpeg 继续拉流写盘、不进守护循环
        # （用户点停止/注释都杀不到它）、进程注册表只增不清、recording 残留幽灵条目
        # （面板恒显「录制中」、磁盘满退出判定 `if not recording:` 恒假），
        # 而房间线程睡一轮后又在同一目录起第二路。
        # 存活判定只留给 _terminate_ffmpeg_process；unregister / clear_record_info 在
        # `not _converged` 时无条件执行（原写法把三个动作全挂在 `process.poll() is None` 上，
        # 「ffmpeg 已自然退出 + 守护段抛错」时三者都不执行）。_converged 保证已自行收尾的
        # 分支不被二次处理（否则会多一次 terminate 调用）。
        if process is not None and not _converged:
            if process.poll() is None:
                _ = _terminate_ffmpeg_process(process)
            unregister_ffmpeg_process(process)
            clear_record_info(record_name, record_url)

    # MID-12 把 process 的声明改成 Popen[bytes] | None（用于区分「Popen 之前就抛错」），但
    # Popen 抛错时异常已穿过 finally 向上传播、不可能落到本行之后 —— 这里做一次显式收窄，
    # 让静态检查可判定（AGENTS 口径：确需收窄时用 cast，不新增运行期分支）。
    # 类型必须写成字符串：测试会把 main.subprocess 换成 SimpleNamespace 替身（本仓约定），
    # 裸写下标会在运行期去订阅替身的 Popen 而抛 TypeError。
    proc = cast("subprocess.Popen[bytes]", process)

    # 弹幕采集器的停止已由上面的 finally 单点保证（SEV-2208），此处不再重复调用。

    # 确保子进程资源被回收，避免僵尸进程/句柄滞留（尤其在 Web 常驻模式下）
    try:
        _ = proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        # 超时说明 ffmpeg 未被回收：显式补杀并告警。原实现用 except Exception: pass
        # 静默吞掉，随后直接用可能为 None 的 returncode 判成败（并据此写探针退避），
        # 会把「回收失败」当成「录制失败」。
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
        # 兜底：kill 后仍拿不到退出码时用 -1 作「未知失败」哨兵，
        # 避免下游 _describe_return_code(None) 抛 TypeError。
        logger.warning(i18n.tr("[{record_name}] 无法获取 ffmpeg 退出码，按失败处理", record_name=record_name))
        return_code = -1
    stop_time = time.strftime("%Y-%m-%d %H:%M:%S")
    if return_code == 0 or _reached_record_limit:
        # CR-06：退出码为 0 不等于录到了东西（形态与后果见 _MIN_VALID_RECORD_BYTES 上方注释）。
        # 产物过小即按失败处理：记失败样本、保留退避（不撤销 clear_ffmpeg_reject）。
        # 达到单次录制时长上限的一轮也走这里——那是长直播的正常收尾，旧实现把它当挂起、
        # 单独 return，转码/成功样本/撤销退避三条收尾全跳过。
        _produced_bytes = _record_output_bytes(save_file_path, _split_output)
        if _produced_bytes is None:
            # MID-2207 后半（2026-09-23）：None = 分段目录不可读（观测失败），与「找不到分段」
            # 一样按 -1 处理——零字节校验的目的是把「rc==0 但一个字节没写」判失败，
            # 而观测失败提供不了这个证据，按失败处理会凭空投一条假 record_error 样本。
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
            # SEV-2208（2026-09-22）：本分支原样 return False，早于函数末尾的
            # recording.discard + unregister_ffmpeg_process → _ffmpeg_processes 只增不清、
            # recording 留下幽灵条目（面板恒显「录制中」、磁盘满判定 `if not recording:` 恒假）。
            # 改为「先收尾后 return」；函数末尾的同样动作对已清空的集合是幂等的。
            with record_state_lock:
                recording.discard(record_name)
                recording_time_list.pop(record_name, None)
            unregister_ffmpeg_process(proc)
            return False
        if converts_to_mp4 and save_type == "TS":
            if _split_output:
                # 2026-09-12 审查 6.1：原 utils.get_file_paths(目录) 递归扫描 + 子串匹配会把同目录下
                # 历史残留 .srt / 已转好的 .mp4 / 早期段产物误送给 ffmpeg，再叠加 converts_mp4 缺 -n，
                # 每条误匹配文件都触发 600s 超时挂死。现按「前缀 + _<数字序号>.<ext>」精确匹配
                # （与 ffmpeg 分段输出 _000/_001… 对齐），序号用 _SEG_INDEX_RE 而非定长 ???
                # （%03d 超过 999 段会输出 4 位），枚举统一走 _segment_files（MIN-2227：
                # glob 把方括号当字符类，主播名含 `[` 时恒返回空、用户开了「自动转 mp4」
                # 却永远拿不到 MP4，日志只说「未找到分段文件」，排查方向被彻底带偏）。
                # MID-2207 后半：None（目录不可读）在此按「本轮无可转文件」处理——转码本身也读不到
                # 该目录，静默跳过比抛 TypeError 丢掉整条成功收尾链路更克制。
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
        # 流正常结束（主播下线）＝平台健康：按房间 host 记一次成功样本（与下方失败分支配对）
        record_success(host_of(record_url))
        # 与下方失败分支的 mark_ffmpeg_reject 配对：本地址实际拉流成功，撤销先前记入的
        # 探针退避，避免窗口内明明已恢复的线路继续被跳过、白白回退到次优线路。
        try:
            clear_ffmpeg_reject(ffmpeg_command[ffmpeg_command.index("-i") + 1], platform)
        except ValueError:
            logger.debug(
                i18n.tr("[{record_name}] ffmpeg 命令缺少 -i 输入参数，跳过探针退避清除", record_name=record_name)
            )

    else:
        # 退出码经 _describe_return_code 换算回有符号并附 errno 语义（Windows 上 ffmpeg 以无符号
        # 32 位呈现，EINVAL 显示为 4294967274 而非 -22；详见 _FFMPEG_ERRNO_HINTS 上方注释），
        # 一眼可判断是「容器/参数不匹配」还是「网络/路径」问题。
        # MIN-2233 修复（2026-09-22）：f-string 直接传给 print_colored 时提取器扫不到本串
        # （既非 print 首参也非 logger/tr 首参）。改为常量模板 + tr 预格式化后整体传入。
        color_obj.print_colored(
            i18n.tr(
                "\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n",
                record_name=record_name,
                stop_time=stop_time,
                return_code=_describe_return_code(return_code),
            ),
            color_obj.RED,
        )
        # —— 录制失败反馈调度器（2026-08-23 实测定稿）：
        # ① 按房间 host 记失败样本，驱动按平台熔断与全局背压——此前录制失败不上报，
        #   轮末还会无条件记成功样本，多房间同 host 时失败率被稀释、熔断永不触发
        #   （实测虎牙房间秒级 403 失败循环，www.huya.com 熔断器始终 closed）；
        # ② 快速失败（≤20s，输入打开被 CDN 拒绝的签名；拉流中断/重连耗尽通常 >60s）时，
        #   把 ffmpeg 实际拉流地址记入探针退避：下一轮 select_source_url 跳过该线路探针、
        #   直接尝试下一 CDN 候选。「探针 200 → ffmpeg 403」的假绿只在录制侧可观测，
        #   不标记则房间会无限循环撞同一条死线路（实测 hs.hls.huya.com）。——
        record_error(host_of(record_url))
        # MID-02 修复（2026-09-20）：输出侧本地 IO 失败不得归因成「CDN 快速失败」。
        # 输出目录不可用（权限/只读挂载/路径过长/录制途中被外部删除）时 ffmpeg 打不开输出即秒退
        # （rc != 0），若按快速失败处理，会把一条**健康**流地址记进探针退避、并计入按 host 的
        # 熔断失败样本，每轮重复污染统计，用户只看到「网络异常」类日志。
        # 判据（2026-09-22 定稿）只看「输出父目录当前不存在」这一条，目录存在即判定到此结束、
        # 不读管道（上层 start_record 已对建目录失败打 error 并跳过本轮）。父目录不存在时 ffmpeg
        # 根本写不出任何产物，与「拉流被 CDN 拒」互斥，故这一条足以定性为本地 IO 失败；
        # 曾设想的第二条判据（读 ffmpeg 自报的写侧特征）不可得，见模块级 MID-N01 注释。
        _output_side_failure = not os.path.isdir(os.path.dirname(save_file_path) or ".")
        if time.monotonic() - _proc_started_mono <= _FFMPEG_FAST_FAIL_SECONDS and not _output_side_failure:
            try:
                _stream_url = ffmpeg_command[ffmpeg_command.index("-i") + 1]
                mark_ffmpeg_reject(_stream_url, platform)
            except ValueError:
                logger.debug(
                    i18n.tr("[{record_name}] ffmpeg 命令缺少 -i 输入参数，跳过探针退避标记", record_name=record_name)
                )

    with record_state_lock:
        recording.discard(record_name)
        recording_time_list.pop(record_name, None)
    unregister_ffmpeg_process(proc)
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


# 平台分派解析：把直播间地址按域名路由到对应平台的爬虫与流地址解析模块，得到本轮 port_info。
# 自 start_record 原样搬移（原内联 if/elif 链约 700 行，超出 basedpyright 单函数条件路径
# 复杂度上限），分支体语义未变；cookie/代理等配置项仍按模块级全局变量即时读取。
# 返回 (platform, port_info, record_danmaku_args, new_record_url)：
# - record_danmaku_args 为弹幕参数(平台相关)，进房失败为 None，由调用方传入 check_subprocess 启停弹幕；
# - new_record_url 为「解析后需要回写配置的规范地址」：Shopee 用它落带 uid 的完整 URL，
#   小红书用它把短链/动态路径解析出的最终直播地址写回 URL_config.ini（2026-10-04）；
# - 无法识别的直播地址返回 None，由调用方 break 进入延迟后重试而非直接结束线程。
# 平台解析上下文（F-01c）：承载迁移前 _resolve_platform_stream 的函数局部变量。
# 60+ 平台 elif 链改成分发表后，各平台处理函数需要显式载体读写这四个结果字段。
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


# 平台匹配器工厂：语义与迁移前的 `record_url.find(片段) > -1` 完全一致，多片段为 or。
def _match_host(*fragments: str) -> Callable[[str], bool]:
    # M-03（2026-10-02）：匹配对象从「整串子串」收窄为「scheme://host/ 归一串」。旧写法
    # url.find(frag) 是整串子串匹配，https://attacker.com/xhslink.com/x 会在**路径**里命中
    # xhslink.com/ 而被路由进小红书解析（并在解析函数入口白名单校验之前，就以带凭据的
    # headers 请求攻击者 host）。按 urlsplit 解析出的 hostname 归一后，fragment 只能与真实
    # host 匹配，路径/query 里出现的域名词不再参与平台路由。fragment 形态（host 或其子域
    # 后缀 + 可选尾部斜杠）在归一串上的命中语义与旧实现对全部合法输入一致：
    #   https://live.douyin.com/1  -> https://live.douyin.com/  命中 douyin.com/
    #   http://www.xiaohongshu.com/1 -> http://www.xiaohongshu.com/ 命中 www.xiaohongshu.com/
    # 无 scheme 输入（准入侧未补齐的极端形态）scheme 段为空串，host 命中语义不变。
    def _m(url: str) -> bool:
        try:
            parts = urlsplit(url)
        except ValueError:
            return False
        host = (parts.hostname or "").lower()
        if not host:
            return False
        normalized = f"{(parts.scheme or '').lower()}://{host}/"
        return any(frag.lower() in normalized for frag in fragments)

    return _m


# 取 URL **路径部分**的小写扩展名（含点），无扩展名/畸形地址返回空串。
# SEV-03 后续（2026-09-20）：自定义流判定必须只看 path，不能看整串子串——
# 旧写法 `".flv" in url.lower()` 让任意地址只要在 query 里塞 `?a=.flv` 就能命中自定义流分支，
# 于是面板写入的 http://127.0.0.1:8000/x?a=.flv 会被原样送进 ffmpeg 的 -i（SSRF 投递通道）。
# 只看 path 同时保留全部合法形态：path 以 .m3u8/.flv 结尾、后面可带任意 query/fragment
# （如 https://cdn/x/playlist.m3u8?wsSecret=... 与 http://cdn/x/live.FLV 均照常命中）。
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


# -------------------------- 平台处理函数（F-01c 分发表条目）--------------------------
# 每个函数对应原 elif 链的一个分支体：读 ctx 入参、写 ctx 结果字段，不再共享隐式局部变量。
# 函数体与迁移前逐字等价（仅缩进与末尾四行回写不同），新增平台在此追加即可。


def _resolve_douyin_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "抖音直播"
    # WD-11 修复：限速等待必须在占用网络并发槽**之前**完成。
    # 原写法把 _douyin_rate_limit()（内部 time.sleep 最长 douyin_min_interval=3s）放在
    # `with semaphore:` 内部，于是 N 个抖音房间排队时，每个等待线程都占着一个网络并发槽
    # 原地睡眠：单轮解析总耗时 ≥ 3×N 秒（80 个抖音房间即 ≥240s，远超 delay_default=120s），
    # 表现为「开播后要等好几分钟才被检测到」，同时抵消了调度器自适应扩容的收益。
    # 移出后仍由 douyin_rate_lock 保证「两次请求起点间隔 ≥ 3s」，风控保护不受影响
    # （semaphore 带来的额外排队只会拉大间隔，不会缩小）。
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
    platform = "未知平台"
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
    platform = "未知平台"
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
    platform = "未知平台"
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
                # MIN-2223（2026-09-22）：补 type_name —— asyncio.TimeoutError 的 str() 是 "()"、
                # socket.timeout 是空串，只写 {e} 的日志退化成没有原因的一行。
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
                # MIN-2223（2026-09-22）：同上，补 type_name
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
# hy.fan 是虎牙移动端分享域：路径段为纯数字时即房间号，否则是短码（如 JbmwoV），
# 需跟随 301 跳转解析出真实房间段。两种形态都归一成 https://www.huya.com/<房间段>
# 后委托 _resolve_huya_com —— 拉流/画质/弹幕/录制与桌面链接走同一条链路，不新增分支。
# 刻意不在准入层改写配置行：跳转解析依赖网络，放主循环准入会把一次网络抖动放大成
# 「配置行被注释/改写」；放解析函数内每轮重试天然兜住瞬态故障，成功结果由下方缓存摊薄。
# 布局注记：本节函数置于 _resolve_huya_com 之后、分发表之前，与「新增平台在此追加」的
# F-01c 约定一致；表项登记见 _PLATFORM_RESOLVERS（虎牙条目之后）。

# 短码 → 房间段解析结果缓存：短链与房间的映射是稳定事实，进程内缓存避免每个监测轮都
# 多发一次 301 跟随请求。dict 单键读写受 GIL 保护且同键写入值幂等，最坏并发后果只是
# 重复解析一次，无需加锁；条目上界是配置里的 hy.fan 行数（含历史变体），无淘汰必要。
_HY_FAN_ROOM_CACHE: dict[str, str] = {}


def _hy_fan_path_segment(record_url: str) -> str:
    # 取 hy.fan 链接的唯一路径段（房间号或短码）；形态不合法抛 ValueError，
    # 消息即用户日志里的失败原因——错误提示必须点名「缺什么 / 为什么不合法」。
    try:
        path = urlsplit(record_url).path
    except ValueError:
        # 含控制字符 / 非法端口等畸形入参：urlsplit 抛 ValueError，按「无法解析」定因
        raise ValueError("URL 无法解析")
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        raise ValueError("路径为空，缺少房间号")
    if len(segments) > 1:
        raise ValueError("路径含多级目录，不是标准房间链接")
    segment = segments[0]
    # isascii 收紧 isalnum 的 Unicode 宽字符误判：全角数字（３０７…）不是合法房间号，
    # 不能流向虎牙接口。与 spider.get_huya_app_stream_url 的 room_id.isdigit() 判定同口径，
    # 这里在入口先挡一层，短码侧同理（base62 短码本身就是 ASCII）。
    if not (segment.isascii() and segment.isalnum()):
        raise ValueError("房间号含非法字符")
    return segment


def _huya_room_segment_from_landing(final_url: str) -> str:
    # 从短链跳转落地页提取虎牙房间段；非虎牙域 / 形态不符一律返回空串（本函数只做
    # 「能不能提取」的判定，失败原因由调用方统一表述）。接受字母段：主播自定义号
    # www.huya.com/<字母号> 本就是合法房间形态，下游 app 路径已有 ProfileRoom 反查
    # 数字房间号的既有链路（spider.get_huya_app_stream_url），不在此重复实现。
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
    # 短码 → 真实房间段：走 async_req(redirect_url=True)，与 xhslink.com 短链解析同一契约——
    # 成功回最终落地 URL（httpx 已跟随重定向，逐跳 SSRF 复检由 async_http 的响应钩子承担，
    # 本函数只解析、不请求落地页）；失败回空串（网络异常 / 内网跳转拒绝已在 async_req
    # 内部记日志），这里统一转成带原因的 ValueError 交调用方写用户日志。
    # UA 取与 spider.get_huya_stream_data 同值的桌面 Firefox UA；不动 MOBILE_UA 那组
    # 四处同步约定（那是虎牙流地址侧的另一条 UA）。
    final_url = await async_req(
        url=record_url,
        proxy_addr=proxy_addr,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        },
        redirect_url=True,
    )
    # async_req 声明返回是覆盖 redirect_url/cookies 组合的联合类型，redirect_url=True 的运行时
    # 契约是「成功回最终 URL、失败回空串」（MID-2225）：按既有调用点口径 isinstance+非空收窄，
    # 空串与非 str 一律归为「未获取到跳转地址」。
    if not isinstance(final_url, str) or not final_url:
        raise ValueError("未获取到跳转地址")
    segment = _huya_room_segment_from_landing(final_url)
    if not segment:
        raise ValueError("跳转地址不是虎牙直播间")
    return segment


def _resolve_hy_fan(ctx: _PlatformResolveContext) -> None:
    # hy.fan 入口：归一为桌面链接后委托 _resolve_huya_com 回写 ctx 四字段（platform /
    # port_info / 弹幕参数 / new_record_url），本函数不重复赋值。表项置于虎牙之后：
    # test_resolver_table_priority_head 钉死前五项为迁移前 elif 链顺序，且 hy.fan 与
    # www.huya.com 的匹配片段互不重叠，先后不产生遮蔽。房间线程侧 record_host 仍是
    # hy.fan——按 host 隔离的熔断桶把「短链解析失败」与桌面链接的取流失败分开计数，
    # 语义反而更准，不需要回填成 www.huya.com。
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
                # reason 统一带异常类型：与 MIN-2223 口径一致（str() 为空的异常类型也要可见）
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
                # MIN-2223（2026-09-22）：同上，补 type_name
                logger.warning(i18n.tr("[B站直播]弹幕信息获取失败: {type_name}: {e}", type_name=type(e).__name__, e=e))
                record_danmaku_args = None
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


# ---------------------- B站移动端分享短链（b23.tv）----------------------
# b23.tv 是B站移动端分享域：路径段为纯数字时即房间号（标准 / 尾斜杠 / 带 query / http 四种
# 形态），否则是短码（如 ZyQrgYf），需跟随 302 跳转解析出真实房间号。两种形态都归一成
# https://live.bilibili.com/<房间号> 后委托 _resolve_live_bilibili_com —— 拉流/画质/弹幕/录制
# 与桌面链接走同一条链路，不新增分支。与 hy.fan 同款布局：刻意不在准入层改写配置行
# （跳转解析依赖网络，放主循环准入会把一次网络抖动放大成「配置行被注释/改写」），放解析
# 函数内每轮重试天然兜住瞬态故障，成功结果由下方缓存摊薄。
# 布局注记：本节函数置于 _resolve_live_bilibili_com 之后、分发表之前，与「新增平台在此追加」
# 的 F-01c 约定一致；表项登记见 _PLATFORM_RESOLVERS（B站条目之后）。

# 短码 → 房间号解析结果缓存：短链与房间的映射是稳定事实，进程内缓存避免每个监测轮都
# 多发一次 302 跟随请求。dict 单键读写受 GIL 保护且同键写入值幂等，最坏并发后果只是
# 重复解析一次，无需加锁；条目上界是配置里的 b23.tv 行数（含历史变体），无淘汰必要。
_B23_TV_ROOM_CACHE: dict[str, str] = {}


def _b23_tv_path_segment(record_url: str) -> str:
    # 取 b23.tv 链接的唯一路径段（房间号或短码）；形态不合法抛 ValueError，
    # 消息即用户日志里的失败原因——错误提示必须点名「缺什么 / 为什么不合法」。
    try:
        path = urlsplit(record_url).path
    except ValueError:
        # 含控制字符 / 非法端口等畸形入参：urlsplit 抛 ValueError，按「无法解析」定因
        raise ValueError("URL 无法解析")
    segments = [seg for seg in path.split("/") if seg]
    if not segments:
        raise ValueError("路径为空，缺少房间号")
    if len(segments) > 1:
        raise ValueError("路径含多级目录，不是标准房间链接")
    segment = segments[0]
    # isascii 收紧 isalnum 的 Unicode 宽字符误判：全角数字（２２７…）不是合法房间号/短码，
    # 不能流向B站接口。与 _hy_fan_path_segment 同口径，这里在入口先挡一层
    if not (segment.isascii() and segment.isalnum()):
        raise ValueError("房间号含非法字符")
    return segment


def _bilibili_room_id_from_landing(final_url: str) -> str:
    # 从 b23.tv 短链跳转落地页提取B站房间号；非B站直播域 / 形态不符一律返回空串（本函数只做
    # 「能不能提取」的判定，失败原因由调用方统一表述）。与虎牙不同，live.bilibili.com 的房间号
    # 只有纯数字形态（短号也是数字），故这里必须 isdigit；移动端落地页还存在 /h5/<房间号>
    # 形态，一并接受。落地 query（share_session_id 等分享参数）不参与判定。
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
    # 短码 → 真实房间号：走 async_req(redirect_url=True)，与 hy.fan / xhslink.com 短链解析
    # 同一契约——成功回最终落地 URL（httpx 已跟随重定向，逐跳 SSRF 复检由 async_http 的
    # 响应钩子承担，本函数只解析、不请求落地页）；失败回空串（网络异常 / 内网跳转拒绝已在
    # async_req 内部记日志），这里统一转成带原因的 ValueError 交调用方写用户日志。
    # UA 取与 spider.get_bilibili_room_info 同值的桌面 Firefox UA；b23.tv 是纯 302 跳转服务，
    # 不校验 UA。
    final_url = await async_req(
        url=record_url,
        proxy_addr=proxy_addr,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:148.0) Gecko/20100101 Firefox/148.0",
        },
        redirect_url=True,
    )
    # async_req 声明返回是覆盖 redirect_url/cookies 组合的联合类型，redirect_url=True 的运行时
    # 契约是「成功回最终 URL、失败回空串」（MID-2225）：按既有调用点口径 isinstance+非空收窄，
    # 空串与非 str 一律归为「未获取到跳转地址」。
    if not isinstance(final_url, str) or not final_url:
        raise ValueError("未获取到跳转地址")
    room_id = _bilibili_room_id_from_landing(final_url)
    if not room_id:
        raise ValueError("跳转地址不是B站直播间")
    return room_id


def _resolve_b23_tv(ctx: _PlatformResolveContext) -> None:
    # b23.tv 入口：归一为桌面链接后委托 _resolve_live_bilibili_com 回写 ctx 四字段（platform /
    # port_info / 弹幕参数 / new_record_url），本函数不重复赋值。表项置于B站之后：两者匹配
    # 片段互不重叠，先后不产生遮蔽。房间线程侧 record_host 仍是 b23.tv——按 host 隔离的
    # 熔断桶把「短链解析失败」与桌面链接的取流失败分开计数，语义反而更准，不需要回填成
    # live.bilibili.com（与 _resolve_hy_fan 同判据）。
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
        # 纯数字段就是房间号：零网络直接归一，覆盖标准 / 尾斜杠 / 带 query / http 四种形态
        room_id = segment
    else:
        room_id = _B23_TV_ROOM_CACHE.get(segment, "")
        if not room_id:
            try:
                room_id = asyncio.run(_resolve_b23_tv_room_segment(ctx.record_url, ctx.proxy_address))
            except Exception as err:
                # reason 统一带异常类型：与 MIN-2223 口径一致（str() 为空的异常类型也要可见）
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
    record_quality = ctx.record_quality
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "小红书直播"
    with semaphore:
        port_info = asyncio.run(spider.get_xhs_stream_url(record_url, proxy_addr=proxy_address, cookies=xhs_cookie))
    # 2026-10-04 小红书链接归一化批次：解析器给出结构化错误类别（链接不是直播/非官方域/短链
    # 重定向失败等），这些都不是「主播没开播」，必须在分派侧按未识别处理并留一条可检索告警——
    # 否则 start_record 会把它们当正常离线轮空转，只看到「等待直播」，永远指不到链接本身有问题。
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
    # 规范地址回写：短链/动态路径解析出的最终直播地址经 new_record_url 落回 URL_config.ini
    # （沿用 Shopee 的既有回写通道），后续轮次直接用长链，省掉每轮一次短链跳转请求。
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
                    # MIN-2229（2026-09-22）：同上，回写失败只告警（统一口径见 _resolve_platform_stream）
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
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "网易CC直播"
    with semaphore:
        # MIN-2228 修复（2026-09-22）：补透传 proxy_address —— 本解析器是全表唯一不传代理的
        # （spider.get_netease_stream_data 的签名接受 proxy_addr，隔壁所有平台都传），
        # 用户配了代理时网易 CC 仍走本机直连，取不到网址内容。
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    platform = "未知平台"
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
                # MIN-2229 补漏（2026-09-23）：popkontv / sooplive / twitcasting 四条同源回写里，
                # 本条此前没包异常（统一口径见 _resolve_platform_stream 的 MIN-2229 注释）——
                # 写盘失败会冒到那里的通用 except，把已拿到的流地址整轮丢弃并计入按 host 的
                # 熔断失败样本。回归锁：tests/test_regression_2026_09_22_main.py
                #   ::test_flextv_cookie_writeback_failure_keeps_stream_url
                try:
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
                # MIN-2229（2026-09-22）：回写是缓存优化，失败不得连累本轮已拿到的流地址
                try:
                    with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
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
    platform = "未知平台"
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

        # MID-2213 修复（2026-09-22）：回写源由 port_info 改为 json_data。
        # stream.get_stream_url 在真正取到流时**新建** dict（只有 anchor_name/is_live/record_url
        # 等键），`new_cookies` 只存在于 spider 返回的 json_data 上；读 port_info 意味着
        # 「恰好在播时永不落盘」→ 每 30-120s 重跑一次 login_twitcasting 明文账密 POST。
        # 同函数群的 SOOP / Flextv 读的就是 json_data，此处对齐同构。
        # 回归锁：tests/test_regression_2026_09_22_main.py::test_twitcasting_persists_cookie_when_live
        if json_data and json_data.get("new_cookies"):
            try:
                with file_update_lock:  # 与主循环 config.read/其他写入方互斥，防止半写
                    utils.update_config(
                        file_path=config_file,
                        section="Cookie",
                        key="twitcasting_cookie",
                        new_value=cast(str, json_data["new_cookies"]),
                    )
            except (configparser.Error, OSError) as e:
                # MIN-2229（2026-09-22）：回写失败不得丢弃本轮已拿到的流地址
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
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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


# Shopee「带 uid 的完整 URL」构造（MID-2226）：base 取原地址 `?` 之前的部分，
# uid 段取自接口响应（session_uid 是响应值），属半可信输入 —— 产物会经 need_update_line_list
# 落进 URL_config.ini，而主循环用 `|` 分行、用 `,` / `，` 分字段、用换行分行：含 `|` 会截断
# 本行、含换行/CR 会**往配置文件追加任意新行**（把接口返回值升级成配置注入面）。
# 故做两道断言：① uid 段字符集白名单；② 拼好的 URL 与 base 同源（host 不变）。
# 任一不过 → 返回空串，调用方据此不回填 uid 段（本轮按原 record_url 处理，与「未拿到 uid」一致）。
# 回归锁：tests/test_regression_2026_09_22_main.py::test_shopee_new_record_url_is_sanitized
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
    record_quality = ctx.record_quality
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "shopee"
    with semaphore:
        port_info = asyncio.run(
            spider.get_shopee_stream_url(url=record_url, proxy_addr=proxy_address, cookies=shopee_cookie)
        )
        if port_info.get("uid"):
            # MID-2226 修复（2026-09-22）：拼前做同源 + 字符集断言，不合格就丢弃 uid 段
            # （返回空串 → 本轮不回填配置）。判据与理由见 _build_shopee_record_url 上方注释。
            new_record_url = _build_shopee_record_url(record_url, str(port_info["uid"]))
    ctx.platform = platform
    ctx.port_info = port_info
    ctx.record_danmaku_args = record_danmaku_args
    ctx.new_record_url = new_record_url


def _resolve_youtube_com(ctx: _PlatformResolveContext) -> None:
    record_url = ctx.record_url
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    record_quality = ctx.record_quality
    platform = "未知平台"
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
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    platform = "自定义录制直播"
    port_info = {
        "anchor_name": platform + "_" + str(uuid.uuid4())[:8],
        "is_live": True,
        "record_url": record_url,
    }
    # SEV-03 后续：流地址键的归属与匹配器同一判据（路径扩展名），不再用整串子串——
    # 否则 https://cdn/x.m3u8?f=.flv 会被写进 flv_url，把 HLS 清单当 FLV 直下。
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
    proxy_address = ctx.proxy_address
    record_quality = ctx.record_quality
    platform = "未知平台"
    port_info: dict[str, Any] = {}
    record_danmaku_args: dict[str, Any] | None = None
    new_record_url = ""
    logger.error(
        i18n.tr(
            "无法识别的直播地址，本轮跳过: {record_url}",
            # MIN-2231 修复（2026-09-22）：这里入日志的是**原始 URL**，而自定义流地址可以写成
            # `https://u:p@host/x.m3u8`（userinfo 段），凭据会明文进 PlayURL.log /
            # streamget.log（300KB 轮转、保留多份）。入日志前一律脱敏。
            record_url=utils.mask_credentials(record_url),
        )
    )
    ctx.unrecognized = True


# 平台分发表（F-01c）：（匹配器, 处理函数）按优先级排列，替代原 60+ 层 elif 链。
# 迁移收益：①新平台接入 = 追加一个处理函数 + 一条表项，不再往 600 行链里插分支；
# ②处理函数可单独 import 与单测；③匹配顺序显式、可断言（见 tests）。
# 注意：表项顺序即优先级，与迁移前 elif 链完全一致，调整顺序等于调整平台判定优先级。
_PLATFORM_RESOLVERS: tuple[tuple[Callable[[str], bool], Callable[[_PlatformResolveContext], None]], ...] = (
    (_match_host("douyin.com/"), _resolve_douyin_com),
    # ↓ SEV-2203 修复（2026-09-22）：以下 7 条原本钉死 `https://` 前缀（如 "https://www.douyu.com/"），
    # 而准入侧只在 URL **完全没有** `://` 时才补 scheme（`"https://" + url if "://" not in url else url`），
    # 匹配器又是纯子串 `any(url.find(frag) > -1 ...)`。于是用户写 `http://www.douyu.com/9422371` 时
    # host 命中 PLATFORM_HOST → 起线程 → 7 条钉死 https 的表项全不命中 → 落到 _resolve_unrecognized
    # → sleep + continue 无限空转（永不录制、不记 record_error、白占监控位）。
    # 同表 `douyin.com/` / `kugou.com/` 等表项本就不带 scheme，证明「scheme 无关匹配」才是本意。
    # 回归锁：tests/test_regression_2026_09_22_main.py::test_every_platform_host_matches_without_scheme
    (_match_host("www.tiktok.com/"), _resolve_tiktok_com),
    (_match_host("live.kuaishou.com/"), _resolve_live_kuaishou_com),
    (_match_host("www.huya.com/"), _resolve_huya_com),
    # 虎牙移动端分享短链：路径段是房间号或短码，短码先经 301 跳转解析出真实房间段，
    # 再归一成 www.huya.com 链接委托 _resolve_huya_com（与斗鱼 m.douyu.com「同 resolver」
    # 思路同源，只是多了短码解析一步，见 _resolve_hy_fan）。PLATFORM_HOST 已同批登记
    # hy.fan（MID-04 契约：白名单每项必被某个 resolver 片段命中）。
    (_match_host("hy.fan/"), _resolve_hy_fan),
    # 斗鱼移动端域名与 www 同表项：二者只影响 URL 形态，解析与取流链路完全一致
    # （同一个 _resolve_douyu_com），不新增分支。
    (_match_host("www.douyu.com/", "m.douyu.com/"), _resolve_douyu_com),
    (_match_host("www.yy.com/"), _resolve_yy_com),
    (_match_host("live.bilibili.com/"), _resolve_live_bilibili_com),
    # B站移动端分享短链：与桌面链路同源，只是多了短码解析一步，见 _resolve_b23_tv。
    # PLATFORM_HOST 已同批登记 b23.tv（MID-04 契约：白名单每项必被某个 resolver 片段命中）。
    (_match_host("b23.tv/"), _resolve_b23_tv),
    # MID-04（2026-09-20）+ SEV-2203 残留（2026-09-23）：两个片段一律 scheme 无关。
    # 白名单里的 xhslink.com 不限协议、get_xhs_note_info 侧判据也是 "xhslink.com" in url，
    # 而本表项曾写死 http://、第二个片段曾留着 https:// —— 于是 https://xhslink.com/... 与
    # http://www.xiaohongshu.com/1 都能被准入却落不到解析器上、无限空转。
    # 准入只按 host，分派不得按协议（两种协议由回归锁各自覆盖）。
    (_match_host("xhslink.com/", "www.xiaohongshu.com/"), _resolve_xhslink_com),
    (_match_host("www.bigo.tv/", "slink.bigovideo.tv/"), _resolve_bigo_tv),
    (_match_host("app.blued.cn/"), _resolve_app_blued_cn),
    (_match_host("sooplive.co.kr/", "sooplive.com/"), _resolve_sooplive_co_kr),
    (_match_host("cc.163.com/"), _resolve_cc_163_com),
    (_match_host("qiandurebo.com/"), _resolve_qiandurebo_com),
    (_match_host("www.pandalive.co.kr/", "www.plive.kr/"), _resolve_pandalive_co_kr),
    (_match_host("fm.missevan.com/"), _resolve_fm_missevan_com),
    (_match_host("www.winktv.co.kr/"), _resolve_winktv_co_kr),
    (_match_host("www.flextv.co.kr/", "www.ttinglive.com/"), _resolve_flextv_co_kr),
    (_match_host("look.163.com/"), _resolve_look_163_com),
    (_match_host("www.popkontv.com/"), _resolve_popkontv_com),
    (_match_host("twitcasting.tv/"), _resolve_twitcasting_tv),
    (_match_host("live.baidu.com/"), _resolve_live_baidu_com),
    (_match_host("weibo.com/"), _resolve_weibo_com),
    (_match_host("kugou.com/"), _resolve_kugou_com),
    (_match_host("www.twitch.tv/"), _resolve_twitch_tv),
    (_match_host("www.liveme.com/"), _resolve_liveme_com),
    (_match_host("www.huajiao.com/"), _resolve_huajiao_com),
    (_match_host("7u66.com/"), _resolve_n7u66_com),
    (_match_host("showroom-live.com/"), _resolve_showroom_live_com),
    (_match_host("live.acfun.cn/", "m.acfun.cn/"), _resolve_live_acfun_cn),
    # MID-04 修复（2026-09-20）：白名单同时列了 live.tlclw.com 与 wap.tlclw.com，
    # 而表项只写 live 子域 → wap 形态永久空转。解析侧 get_changliao_stream_url 只取
    # URL 末段的房间号、API 域名固定为 wap.tlclw.com，两个子域都是合法入参
    # （与 7u66.com / ybw1666.com 两条表项的宽松写法同口径）。
    (_match_host("tlclw.com/"), _resolve_live_tlclw_com),
    (_match_host("ybw1666.com/"), _resolve_ybw1666_com),
    (_match_host("www.inke.cn/"), _resolve_inke_cn),
    (_match_host("www.zhihu.com/"), _resolve_zhihu_com),
    (_match_host("chzzk.naver.com/"), _resolve_chzzk_naver_com),
    (_match_host("www.haixiutv.com/"), _resolve_haixiutv_com),
    (_match_host("vvxqiu.com/"), _resolve_vvxqiu_com),
    (_match_host("17.live/"), _resolve_n17_live),
    (_match_host("www.lang.live/"), _resolve_lang_live),
    (_match_host("m.pp.weimipopo.com/"), _resolve_m_pp_weimipopo_com),
    (_match_host(".6.cn/"), _resolve_n6_cn),
    (_match_host("lehaitv.com/"), _resolve_lehaitv_com),
    (_match_host("h.catshow168.com/"), _resolve_h_catshow168_com),
    (_match_host("live.shopee", "shp.ee/"), _resolve_live_shopee),
    (_match_host("www.youtube.com/", "youtu.be/"), _resolve_youtube_com),
    # MID-04 修复（2026-09-20）：补 huodong.m.taobao.com —— 它是 PLATFORM_HOST 白名单里的
    # 淘宝直播分享页 host（get_taobao_stream_url 的 Referer 即该域名，README 亦列淘宝为支持平台），
    # 但表项只写了 tb.cn / tbzb.taobao.com，于是用户按白名单配置的这类地址永远落不到解析器上。
    (_match_host("tb.cn", "tbzb.taobao.com", "huodong.m.taobao.com"), _resolve_tb_cn),
    (_match_host("3.cn", "m.jd.com"), _resolve_n3_cn),
    (_match_host("faceit.com/"), _resolve_faceit_com),
    (_match_host("www.miguvideo.com", "m.miguvideo.com"), _resolve_miguvideo_com),
    (_match_host("show.lailianjie.com"), _resolve_show_lailianjie_com),
    (_match_host("www.imkktv.com"), _resolve_imkktv_com),
    (_match_host("www.picarto.tv"), _resolve_picarto_tv),
    (_match_stream_suffix(".m3u8", ".flv"), _resolve_custom_stream),
)


# 按直播间地址分派到对应平台解析：返回 (平台名, 流信息, 弹幕参数, Shopee 更新用 URL)；
# 地址无法识别时返回 None（调用方延迟重试）
def _resolve_platform_stream(
    record_url: str, proxy_address: str | None, record_quality: str
) -> tuple[str, dict[str, Any], dict[str, Any] | None, str] | None:
    ctx = _PlatformResolveContext(record_url, proxy_address, record_quality)
    for matcher, handler in _PLATFORM_RESOLVERS:
        if matcher(record_url):
            # MIN-2229 修复（2026-09-22）：handler 不再「裸调」。平台解析函数内部会做
            # cookie / token 回写（sooplive / twitcasting / popkontv 等），回写走 utils.update_config
            # → config.write(buf) 未包异常；Python 3.13+ 含分隔符的键名会抛 InvalidWriteError。
            # 一次本地写盘失败就把**已经拿到的流地址**整轮丢弃，并在调用方记 record_error(record_host)
            # ——把磁盘/权限问题计入按 host 的网络熔断样本。回写只是缓存优化，失败只告警。
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
        # 本分支的真实语义是「准入 host 命中 PLATFORM_HOST，但无任何匹配解析器」——并非不可达：
        # 准入按 `url_host in PLATFORM_HOST` 精确 host，分派按子串，两者口径不同，任何
        # 「host 在白名单、但所有表项片段都不命中」的地址都会落到这里（历史实例：表项钉死
        # https:// 时遇 http:// 形态；xhslink.com / wap.tlclw.com / huodong.m.taobao.com 亦然）。
        # SEV-2203（2026-09-22）同步静态锁见
        # tests/test_regression_2026_09_22_main.py::test_every_platform_host_matches_without_scheme。
        # 返回 None 由调用方延迟后重试
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
    # 统一 5 条原本散落各分支的 ffmpeg「输出侧」参数构造逻辑（音频 MP3/M4A + 视频 TS/FLV/MKV/MP4）。
    # 输入级选项（-reconnect*/-headers/-tls_verify/-http_proxy）与 save_file_path / 时间戳 now
    # 的构造仍留在 start_record 内，本函数纯做「输出参数」拼装，可独立测试且行为可逆。
    # 容器映射统一查 SEGMENT_FORMAT_BY_SUFFIX，杜绝历史上「.mp3 装进 MP4 / .ts 装进 ipod」
    # 的静默错封装（CODE_REVIEW P0 事故根因：5 份复制粘贴，改一处漏四处）。
    if is_audio:
        # 纯音频：record_save_type 含 MP3 → libmp3lame + mp3；其余（M4A / 纯音频平台默认）
        # → aac + aac_adtstoasc + ipod。扩展名由调用方按同条件推导，三方一致。
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

    # 视频容器：默认 TS（含 record_save_type 为 TS / 其他未知值）
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


# 输出文件名各维度差异的单一定义点（F-01）。
# 历史教训：文件名 / 时间戳格式 / 分段序号曾在 5 条保存类型分支里各写一份，
# 任何一处调整都要人工比对 5 份复制粘贴（CODE_REVIEW 的 `-segment_format`
# 两处互换 P0 事故即源于此）。此处把差异收敛成三张查表，分支只负责查表。
_EXTENSION_BY_SAVE_TYPE: dict[str, str] = {"FLV": "flv", "MKV": "mkv", "MP4": "mp4"}
# 分段文件名的时间戳格式：FLV 沿用历史 %y%m%d_%H%M%S，其余用 %Y-%m-%d_%H-%M-%S。
# 二者仅影响文件名观感（非分段沿用外层 now，格式恒为 %y%m%d_%H%M%S）。
_SEGMENT_NOW_FORMAT_BY_SAVE_TYPE: dict[str, str] = {
    "FLV": "%y%m%d_%H%M%S",
    "MKV": "%Y-%m-%d_%H-%M-%S",
    "MP4": "%Y-%m-%d_%H-%M-%S",
    "TS": "%Y-%m-%d_%H-%M-%S",
}
_DEFAULT_SEGMENT_NOW_FORMAT = "%Y-%m-%d_%H-%M-%S"


# 输出文件名模板的 `%` 兜底清洗（SEV-2202，2026-09-22）：ffmpeg 的 segment muxer 会把
# 输出路径当成 printf 风格模板解析——除末尾的序号占位符（`_%03d` / `_%02d`）之外还残留裸 `%`
# 时，ffmpeg 直接以「Invalid argument」退出（本机 ffmpeg/ffmpeg.exe 实测 rc=-22），分段录制
# 100% 失败；且失败码会被 _describe_return_code 误判为「容器/编码器不匹配」，进而落入
# _FFMPEG_FAST_FAIL_SECONDS 的「CDN 快速失败」，把一条健康的线路拉黑并触发 host 级熔断。
# rstr 已把 `%` 纳入过滤（见其上方注释），但昵称/标题还可能来自旧配置、手工改名或平台原样
# 返回值，故在拼进模板前再剥一层，并留一条可检索的告警。
# 回归锁：tests/test_regression_2026_09_22_main.py::test_segment_template_has_single_percent_placeholder
def _sanitize_output_name_base(base: str) -> str:
    if "%" not in base:
        return base
    cleaned = base.replace("%", "")
    logger.warning(i18n.tr("输出文件名模板含非法 %% 占位符，已剔除后继续录制: {name}", name=base))
    return cleaned


# 输出文件路径构造（F-01）：把 5 条分支各自的 filename/save_file_path 拼装收敛为单一实现。
# is_audio 时扩展名与序号占位符走音频口径（.mp3/.m4a、_%02d/_00）；
# 视频按保存类型查表，未知类型回落 ts（与 _build_ffmpeg_output_args 的容器裁决一致）。
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
        # 扩展名必须与 _build_ffmpeg_output_args 实际选用的编码器 / 容器一致，
        # 否则出现「.mp3 文件里装 AAC/MP4」这类三方错配（播放器按扩展名解复用必失败）
        extension = "mp3" if "MP3" in record_save_type else "m4a"
        name_format = "_%02d" if split_video_by_time else "_00"
        # SEV-2202（2026-09-22）：模板里只允许保留 `name_format` 这一个占位符。
        base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{now}")
        return f"{full_path}/{base_name}{name_format}.{extension}"

    extension = _EXTENSION_BY_SAVE_TYPE.get(record_save_type, "ts")
    if split_video_by_time:
        seg_now = time.strftime(
            _SEGMENT_NOW_FORMAT_BY_SAVE_TYPE.get(record_save_type, _DEFAULT_SEGMENT_NOW_FORMAT), time.localtime()
        )
        # SEV-2202（2026-09-22）：分段模板里只允许保留下面这一个 `_%03d`，其余 `%` 一律剥掉。
        base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{seg_now}")
        return f"{full_path}/{base_name}_%03d.{extension}"
    # 非分段：FLV 保留历史 _00 序号后缀（与直下 FLV 命名对齐），其余保存类型无该后缀
    plain_suffix = "_00" if record_save_type == "FLV" else ""
    # 非分段落盘不经过 segment muxer，但仍走同一清洗：文件名里带 `%` 会让后续
    # 转封装 / 合并步骤（同样按模板语义解析）在别的环节再炸一次（SEV-2202）。
    base_name = _sanitize_output_name_base(f"{anchor_name}_{title_in_name}{now}")
    return f"{full_path}/{base_name}{plain_suffix}.{extension}"


# ffmpeg 网络 / 缓冲参数取值（F-01）：海外平台 CDN 往返延迟高、GOP 探测更慢，
# 统一放大超时与探测窗口，避免 ffmpeg 在握手阶段就判超时退出。
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


# ffmpeg「输入侧」参数构造（F-01 第二阶段）：与 _build_ffmpeg_output_args 配套，
# 把散落在 start_record 内联的 -reconnect* / -headers / -tls_verify / -http_proxy
# 拼装收敛为纯函数，可独立测试且行为可逆。
# 参数顺序敏感：选项增删会移动后续下标，故全部按锚点（`-i` 下标 / 列表头插入）定位，
# 不用裸数字下标（F-02 已修过一处由此静默插错位置的问题）。
def _build_ffmpeg_input_args(
    real_url: str,
    user_agent: str,
    tuning: dict[str, str],
    headers: dict[str, str] | None = None,
    tls_verify: bool = True,
    proxy_address: str | None = None,
) -> list[str]:
    # FFmpeg 9.0 兼容说明：
    # - 9.0 移除的 CLI 参数（-vsync/-top/-qphist/-filter_complex_script/
    #   -adrift_threshold）本命令均未使用；所列参数在 9.0 全部保留。
    # - 9.0 起 TLS 证书验证默认开启：是否插入 -tls_verify 0 由调用方按
    #   get_effective_ssl_verify(platform) 裁决后经 tls_verify 传入。
    # - 原命令中冗余的「-v verbose」已移除：其后的 -loglevel error 会覆盖之，属死参数。
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
        # 2026-09-12 审查（低危）：移除 file 协议。
        # 本项目输入恒为 http(s)/rtmp 直播流，file 从不使用；
        # 放行它意味着「URL 可控」时 ffmpeg 可读写本地文件
        # （自定义流地址来自用户配置/平台返回，属不可信输入面）。
        # 按最小权限收敛；crypto 需保留（HLS 分片解密）。
        "-protocol_whitelist",
        "rtmp,crypto,http,https,tcp,tls,udp,rtp,httpproxy",
        "-analyzeduration",
        tuning["analyzeduration"],
        "-probesize",
        tuning["probesize"],
        "-fflags",
        "+discardcorrupt",
        # -reconnect* 属 input 级(HTTP 协议)选项，必须位于 -i 之前。
        # 曾置于 -i 之后：ffmpeg 会把它当作输出选项静默接受——实测无任何
        # 警告、退出码仍为 0，输入侧从未应用，重连完全失效且无可见症状；
        # 而失败判定（「慢速失败=重连耗尽」）全建立在其生效之上。
        "-reconnect_delay_max",
        "60",
        # 2026-09-11 事故：上一次把这三个选项移到 -i 之前时，丢失了
        # -reconnect_streamed / -reconnect_at_eof 的布尔值 "1"，ffmpeg
        # 把下一个选项名当作值 → 「Unable to parse ... as boolean」 →
        # Invalid argument，输入未打开即退出（-22）。每个 -reconnect*
        # 必须紧跟其取值，tests/test_ffmpeg_reconnect_args.py 有 AST
        # 断言同时锁定「带值」与「位于 -i 之前」两个不变量。
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
        # -thread_queue_size 只能放在 -i 之后（2026-09-23 事故，抖音 HLS 录制返回码 -22）：
        # 它原本挂在输入侧。上游 ffmpeg 已把该选项收窄为**输出专属**（doc/ffmpeg.texi：
        # 6.1/7.1/8.0/9.0.2 标 (input/output)，master 标 (output)；本机 master 构建
        # N-126755-g52f05ac780-20260922 的 -h full 把它列在
        # "Advanced per-file options (output-only)" 段）。放在 -i 之前不再是「静默不生效」
        # 而是拒绝打开输入，实测逐字报错：
        #   Option thread_queue_size (… per stream on the muxer) cannot be applied to
        #   input url … Error opening input files: Invalid argument
        # 输出侧位置对 6.1 起的 release 与 master 全部合法，是本仓支持面内唯一可用位置；
        # 代价：≤9.0.2 上「强制独立输入读取线程」的效果随之失去（master 已无此机制）。
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

    # HLS(m3u8) 输入禁用 -reconnect_at_eof（2026-09-11 事故沉淀）：
    # hls demuxer 依赖播放列表读到 EOF 才完成解析、开始拉取媒体段；开启该选项后 http 层在
    # 播放列表 EOF 处无限重连（-report 实测特征：连续「Will reconnect at <size> in N second(s),
    # error=End of file」，1/3/7/15/31/60s 指数退避、永不放弃）——媒体段一个都拉不到、视频数据
    # 零字节产出、进程永不退出（-loglevel error 下零输出零报错，check_subprocess 守护循环只见
    # 进程存活）。对照实验：同命令带 -t 10 限时，60 秒仍不退出且无产物；仅去掉该选项后 10 秒
    # 录制 9MB 正常退出。FLV 输入保留该选项：CDN 掐断长连接时在 EOF 处重连续写同一文件
    # （斗鱼游客态 FLV ~70s 被掐的既有缓解手段）。删除经 del 而非置 "0"，保证命令行干净。
    # 判据一律「小写 + 只看 path」（2026-09-12 补小写、MIN-2230 补 path，2026-09-22），
    # 两种误判方向都会复现事故：
    #   ① 整串子串匹配时，FLV 的 query 里带 .m3u8（如 `...flv?x=.m3u8`）→ 误删该选项，
    #      CDN 掐断长连接时丢 EOF 重连（斗鱼游客态 FLV ~70s 被掐的缓解手段失效）；
    #   ② 大小写敏感时 .M3U8 / .M3u8 落空 → 保留该选项，复现「播放列表 EOF 无限重连、
    #      零字节产出、进程永不退出」。
    # 孪生副本 scripts/douyin_live_recorder_standalone.py 同处仍是 `".m3u8" in url.lower()`
    # （该文件不 import src/、没有 _stream_path_suffix），两侧在「query 带 .m3u8 的 FLV」这一格
    # 上已漂移，改判据时须一并核对。
    if _stream_path_suffix(real_url) == ".m3u8":
        _eof_idx = command.index("-reconnect_at_eof")
        del command[_eof_idx : _eof_idx + 2]

    if headers:
        # ffmpeg 的 -headers 支持多行（\r\n 分隔）多个头；
        # 合并 referer/origin 与 cookie，与校验探针保持一致。
        header_blob = "\r\n".join(f"{k}:{v}" for k, v in headers.items())
        # 2026-09-12 修复（CODE_REVIEW_FIX_1 F-02）：按 `-i` 锚点定位，
        # 不再用裸下标 11/12。`-headers` 是**输入选项**，必须位于
        # `-i` 之前；而命令前段会随选项增删而变长变短——上方
        # `-reconnect_at_eof` 的 del 就删掉了两个元素，调整
        # `-reconnect*` 顺序同样会移动位置。写死下标会在这些改动后
        # 把 -headers 插到输入之后（ffmpeg 报 "Option headers not
        # found" 或更糟：静默插到输出选项区，头不生效）。
        _i_idx = command.index("-i")
        command[_i_idx:_i_idx] = ["-headers", header_blob]

    # 证书校验：ffmpeg 默认即校验（安全优先）。tls_verify=False 时插入
    # -tls_verify 0，绕过虎牙 TX CDN 等证书主机名不匹配问题。
    # 注意：-tls_verify 是 tls 协议私有选项，仅 https 流有 tls 组件消费它；
    # 对 http 流插入会报 "Option tls_verify not found" 直接录制失败
    # （虎牙 http FLV 实测），故仅 https 地址才插入。
    if not tls_verify and (real_url or "").startswith("https://"):
        # 下标 1 = 紧跟可执行档之后：全局选项必须位于 `-i` 之前，
        # 插在最前最稳（多次插入时后插者在前，同为全局选项不影响语义）
        command.insert(1, "-tls_verify")
        command.insert(2, "0")

    if proxy_address:
        command.insert(1, "-http_proxy")
        command.insert(2, proxy_address)

    return command


# 五条保存类型分支共用的「起一次 ffmpeg 录制」执行骨架（F-01 第三阶段）。
# 原实现在音频 / FLV / MKV / MP4 / TS 五处各写一份 try/except OSError +
# check_subprocess + record_finished 置位，任何一侧的修复（如启动失败时
# 清幽灵 recording 条目）都要人工同步五份。
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
        # ffmpeg 启动失败抛 FileNotFoundError / PermissionError 等 OSError 子类；
        # subprocess.CalledProcessError 仅在 subprocess.run(check=True) 时触发，
        # ffmpeg Popen 流程下永不会抛——原写法（2026-09-12 审查 6.1）是死代码。
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


# 录后转 MP4 统一出口（F-01）：原 TS 分段 / TS 非分段 / FLV 三条路径各写一份
# 遍历与起线程逻辑，其中 TS 非分段漏了 converts_to_mp4 判断（用户关闭转码
# 仍会转），FLV 用 `_*.flv` 宽匹配（会误伤同目录同名前缀的历史文件）。
# 统一为：关闭转码直接返回；分段按「前缀 + _<数字序号>.<ext>」正则精确匹配；
# 非分段直接转单个文件。
def _convert_after_record(save_file_path: str, split_video_by_time: bool) -> None:
    if not converts_to_mp4:
        return
    try:
        if not split_video_by_time:
            # 本函数作用域内没有 record_name（仅有输出路径），交由 _submit_postprocess 用文件名兜底标注
            _submit_postprocess(converts_mp4, save_file_path, delete_origin_file)
            return
        extension = os.path.basename(save_file_path).rsplit(".", maxsplit=1)[-1]
        # 枚举走 _segment_files（不再 glob，理由见其函数头）。MID-2207 后半（2026-09-23）：
        # None（目录不可读）必须与 []（确实没有分段）分开报，否则日志只说「未找到分段文件」，
        # 把权限/网络盘这类本地故障误导成「ffmpeg 没产出」。
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
            # MIN-2234 修复（2026-09-22）：原文案写死「FLV」，而本出口被 TS/MKV/MP4 音频等
            # 所有分段形态复用（seg_pattern 里明明是 `_*.ts`），排查被引向错误方向。
            # 改为带扩展名的中性措辞；新 msgid 已登记进 _i18n_pending.json。
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


# 单个直播间的录制线程主体：循环「解析平台 → 选源 → 起 ffmpeg / 直下」直到该 URL 被注释、
# 收到退出标志或录制停止开关关闭后返回（由主循环按配置重新拉起）。
# room_state：调用方（_room_thread_target）传入的可变字典，用于把「本轮录制名」带回线程出口，
# 使弹幕监控房间清理只在线程退出时执行一次（MID-30）；直接调用本函数时可不传。
def start_record(
    url_data: tuple[str, str, str], count_variable: int = -1, room_state: dict[str, str] | None = None
) -> None:
    # 房间日志关联字段在线程入口即绑定：首轮解析成功前 record_name 仍为空，而退出标志 /
    # 注释退出 / 解析失败 / 熔断退避这些日志已经产生，先用「序号N」占位保证本线程每一行
    # 日志都能归属到房间（解析出主播名后再升级为完整 record_name）。为何用 ContextVar
    # 而非逐处 logger.bind()：见 src/logger.py::ROOM_FIELD 与 AGENTS.md「已知坑」。
    set_room_context(f"序号{count_variable}")
    while True:
        # record_name / record_host 都置于外层 try 之前：最外层 except 与 finally 都要引用它们，
        # 放在 try 内会在「首语句前抛异常」时未绑定（并以 NameError 掩盖原始异常）。
        # record_host 是熔断 key（本直播间 host，用于按平台隔离并发与错误预算）；默认空串在
        # 异常早退分支被 record_error 视为 falsy，仅计入全局错误预算、不触发按 key 熔断。
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
                    # MIN-2231（2026-09-23）：房间地址可以是「自定义流地址」，用户写成
                    # `https://u:p@host/x.m3u8` 时凭据会原样进 PlayURL.log / streamget.log
                    # （300KB 轮转、保留多份）→ 入日志前一律脱敏，msgid 保持不变。
                    # 静态锁：tests/test_regression_2026_09_22_main.py
                    #   ::test_room_and_breaker_logs_mask_credentials（按调用点判定实参是否过码）
                    logger.debug(
                        i18n.tr(
                            "检测到退出标志，录制线程退出: {record_url}",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    return
                # 停止录制（Web 面板开关关闭）：本房间线程退出，运行列表清理由
                # _room_thread_target 的 finally 兜底（保证重新开始后能再次拉起）
                if not recording_enabled:
                    logger.debug(
                        i18n.tr(
                            "录制已停止，房间线程退出: {record_url}",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    return
                # 配置实时性：URL 被注释/移除后立即退出，不等本轮解析结果——
                # 原检查点位于解析成功之后，解析持续失败（平台接口异常）时永远走不到，
                # 线程滞留并占用监控位，URL_config.ini 的变更迟迟不生效
                if record_url in url_comments:
                    print(
                        i18n.tr(
                            "[{record_url}]已被注释,本条线程将会退出",
                            record_url=utils.mask_credentials(record_url),
                        )
                    )
                    clear_record_info(record_name, record_url)
                    return
                # —— 并发熔断预检：该平台(host)连续失败达阈值时跳过本轮网络探测并退避，
                # 释放全局并发槽给其他平台，避免单平台抖动拖垮整体（降级应对连锁报错）——
                if scheduler is not None and not scheduler.allow(record_host):
                    _backoff = scheduler.backoff_seconds(record_host)
                    _backoff = min(_backoff, max(30.0, float(delay_default)))
                    logger.debug(
                        i18n.tr(
                            "[{record_host}] 并发熔断中，跳过本轮探测，退避 {_backoff}s",
                            # MIN-2231（2026-09-23）：record_host 取自 host_of(record_url)。
                            # scheduler.host_of 现已剥去 `user:pass@`（凭据不再进熔断 key 与日志），
                            # 这里再过一次 mask_credentials 兜住任何非 host_of 来源的凭据形态。
                            record_host=utils.mask_credentials(record_host),
                            _backoff=f"{_backoff:.0f}",
                        )
                    )
                    _interruptible_sleep(_backoff, record_url)
                    continue
                try:
                    # 平台分派解析（复杂度控制已抽取为 _resolve_platform_stream）：
                    # 返回 (platform, port_info, 弹幕参数, Shopee新URL)；无法识别的地址返回 None
                    _resolved = _resolve_platform_stream(record_url, proxy_address, record_quality)
                    if _resolved is None:
                        # 无法识别的地址：延迟一轮后重试而非直接结束线程。原 `break` 跳出
                        # 内层循环会绕过位于循环体末尾的轮末延迟，导致无间隔刷请求刷日志
                        # （~100ms/轮）；sleep+continue 同时保留每轮预检（退出/注释/熔断）
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
                                # M-02（2026-10-02）：自定义流地址可能带 user:pass@ 凭据，print 进
                                # 控制台与 web_console.log（后者不轮转），实参必须过码。
                                # 过码对象取 str(tuple) 而非元组本身：mask_credentials 只接受 str
                                # （内部全是 re.sub），直接把 (画质, url, 主播名) 元组递进去会抛
                                # TypeError，把这条「获取失败重试」print 变成穿透到外层 except 的异常。
                                # 目录里该 msgid 的占位符就是 {url_data}，故只换实参、不动模板。
                                url_data=utils.mask_credentials(str(url_data)),
                            )
                        )
                        record_error(record_host)
                        # MID-2204 修复（2026-09-22）：本轮没拿到 anchor_name 就是「无状态轮」，
                        # 必须显式结束本轮。原写法不 continue，而是继续往下走进共享的轮末等待，
                        # 语义上把失败轮当成了正常收尾轮；而开播/下播推送的状态机（start_pushed
                        # 的置位与复位）整体位于下面的 else 成功分支内，失败轮本不该有机会推进它。
                        # 显式 continue 后，「状态机只在拿到真实直播状态时前进」成为结构性保证，
                        # 不会再出现「本轮压根没解析成功，下一轮却按已翻转的状态重复推送开播通知」。
                        # 等待沿用可中断口径（MIN-2226），与 `_resolved is None` 分支同构。
                        _interruptible_sleep(max(30.0, float(delay_default)), record_url)
                        continue
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
                                    i18n.tr(
                                        "主播名已变更，配置与录制文件同步更新: {anchor_name} -> {latest_anchor_name}",
                                        anchor_name=anchor_name,
                                        latest_anchor_name=latest_anchor_name,
                                    )
                                )
                                # 清理旧名残留的录制状态（正常路径录制结束即清理，此处兜底
                                # 异常残留，防止状态列表长期挂旧名条目）
                                _stale_record_name = f"序号{count_variable} {anchor_name}"
                                anchor_name = latest_anchor_name
                                with record_state_lock:
                                    recording.discard(_stale_record_name)
                                    recording_time_list.pop(_stale_record_name, None)
                                # MID-2205 修复（2026-09-22）：改名成功后还要把**旧名**从弹幕监控
                                # 枢纽里摘掉。枢纽按房间名（= record_name，见 src/collector.py 的
                                # hub.room_started(self._room_name)）登记，旧名条目只有在「房间线程
                                # 退出」时经 _room_thread_target 的 room_stopped 才会消失；而改名发生
                                # 在房间线程**内部**、线程还能继续跑几百轮，于是旧名永久挂在监控页
                                # 与 JSONL 边车里（主播改几次名就多几条永不结束的假房间）。
                                # 此处用改名**之前**算好的 _stale_record_name（上面 anchor_name
                                # 已被覆写为新名）。监控为旁路功能，失败静默——不得因此打断录制。
                                try:
                                    from src.danmaku_monitor import get_hub

                                    get_hub().room_stopped(_stale_record_name, "主播改名")
                                except Exception:
                                    pass
                        record_name = f"序号{count_variable} {anchor_name}"
                        # 关联字段升级为可读房间名：record_name 每轮重算，主播改名后同步刷新
                        # （与文件 sink 的 {extra[room]} 列共用同一值，见 src/logger.py）
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
                                    # MIN-2232 修复（2026-09-22）：原裸字面量既不过 tr() 也不是
                                    # print/logger 首参，extract_i18n_strings.py 三条提取规则全部
                                    # 扫不到 → 非 zh_CN 语言下推送正文仍是简体中文。包 tr() 后
                                    # 该 msgid 进入提取集合（复核：grep -n '直播间状态更新' main.py）。
                                    # 占位符是方括号字面量而非 {name}，故不传 kw、仍走下方 .replace 链。
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
                            # MIN-2233 修复（2026-09-22）：原先把 f-string 提到 content 变量再 print，
                            # 提取器的 print 规则只认「首参为常量/f-string」，变量引用扫不到 → 四语
                            # 目录中「正在直播中」零命中。改为在打印点直接 tr 插值。
                            print(i18n.tr("\r{record_name} 正在直播中...", record_name=record_name))

                            if live_status_push and not start_pushed:
                                if begin_show_push:
                                    # MIN-2232 修复（2026-09-22）：同上条，裸字面量补 tr() 包裹
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
                                # 2026-09-12 审查 6.1：原 time.sleep(push_check_seconds) 一次性阻塞整段
                                # 时间，Web「停止录制」后此线程最坏滞留 push_check_seconds 秒才退出。
                                # 改为逐秒 sleep + 每秒重查三个条件，中断时立即回到外层 while 顶；
                                # 直接引用模块全局即晚绑定（每轮重新求值，天然看到其它线程 / Web
                                # 面板改动后的最新值）。2026-09-14 修掉的形态是 `main.recording_enabled`
                                # ——本文件模块级 `main` 是入口函数 `main()` 而非模块对象，那样写
                                # 在「只监测不录制 + 推送检测间隔>0」时必抛 AttributeError
                                # （mypy 亦报 attr-defined）。
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
                                # L-04（2026-10-02）：补齐两个「强制直下」平台（only_flv_platform_list =
                                # shopee / 花椒直播）。二者的 [Cookie] 配置项在本文件已有读取点并透传给
                                # 解析函数（get_shopee_stream_url / get_huajiao_stream_url），却不进本表，
                                # 于是同一份用户 Cookie 在「解析」与「探针 / ffmpeg 录制头 / 直下」两条路上
                                # 口径不一——直下路径拿不到登录态，CDN 按游客态钳制或 403。
                                # 其余 25 个已声明却未入表的 *_cookie 不在本批补：逐平台是否需要登录态
                                # 取流未经现网抓包确认，盲加等于改变 25 个平台的出站请求头。
                                "shopee": shopee_cookie,
                                "花椒直播": huajiao_cookie,
                            }.get(platform, "")

                            real_url = select_source_url(port_info, proxy_address, platform, cookies=platform_cookie)
                            if not real_url:
                                # 三级候选（HLS/FLV/record_url）本轮均校验失败且无末位放行：本轮放弃录制。
                                # 录制链（ffmpeg_command/title_in_name 等）假定 real_url 非空，强制进入会触发
                                # 未绑定变量异常（title_in_name）或复用上一轮残留的 ffmpeg 命令；
                                # 按常规监测间隔等待，下一轮重新解析校验。
                                logger.warning(
                                    i18n.tr("{anchor_name} 本轮未获取到可用流地址，跳过录制", anchor_name=anchor_name)
                                )
                                _interruptible_sleep(max(random.randint(-5, 5) + delay_default, 0), record_url)
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
                                logger.error(
                                    i18n.tr(
                                        "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                                        type_name=type(e).__name__,
                                        e=e,
                                        get_error_line=_get_error_line(e),
                                    )
                                )
                                # MID-02 修复（2026-09-20）：输出目录建不出来时**不得**继续起 ffmpeg。
                                # 原写法只记一条 error 就往下走完整录制链，ffmpeg 打不开输出即秒退
                                # （rc != 0），随后被 check_subprocess 判成「CDN 快速失败」→
                                # 给一条健康流地址记探针退避 + record_error，每轮重复污染熔断统计，
                                # 用户只看到「网络异常」类日志。此处按常规监测间隔等一轮再试
                                # （与上方「本轮未获取到可用流地址」的降级口径同构）。
                                _interruptible_sleep(max(random.randint(-5, 5) + delay_default, 0), record_url)
                                continue

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

                                # MID-03 修复（2026-09-20）：列表元素必须是 resolver 回写的**平台名**，
                                # 不是 host 片段。原第二项写成 "migu"，而 _resolve_miguvideo_com 回写的是
                                # "咪咕直播" → 该项恒不命中，咪咕「强制走 http 拉流」的既有语义静默失效
                                # （同列表首项 "shopee" 恰好等于 _resolve_live_shopee 回写的平台名，
                                # 才让这条错配一直没人发现）。回归锁见 tests/test_platform_dispatch.py。
                                http_record_list = ["shopee", "咪咕直播"]
                                if platform in http_record_list:
                                    real_url = real_url.replace("https://", "http://")

                            # 默认移动端 UA；虎牙/B站 等国内 CDN 拒绝移动端 UA，改用桌面 Chrome，
                            # 且与校验探针共用同一 UA（get_record_user_agent）避免校验“假绿”。
                            # 必须与 stream_select.MOBILE_UA 保持一字不差（校验与录制两端一致）。
                            # MID-2209 修复（2026-09-22）：默认 UA 直接引用 stream_select.MOBILE_UA，
                            # 不再在本地复制字面量。原写法把整串 UA 抄在本文件里，与唯一事实源
                            # 分处两地——校验探针与 ffmpeg 录制两端只要有一端改了，另一端就会静默
                            # 漂移到不同 UA（CDN 侧表现为「校验通过但录制 403」）。
                            # 静态锁：tests/test_platform_dispatch.py::test_record_ua_uses_single_source
                            user_agent = get_record_user_agent(platform) or MOBILE_UA

                            # F-01：网络/缓冲参数与「输入侧」命令行构造全部下沉到纯函数，
                            # 此处只做「取参数 → 组装」两步，分支内不再出现裸选项列表。
                            is_overseas = any(pt_host in record_url for pt_host in OVERSEAS_PLATFORM_HOST)
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

                            # SEV-09 修复（2026-09-20）：强制直下（only_flv）平台的录制状态登记
                            # 下移到「确认拿到 flv_url」之后（见同文件该分支），此处只为 ffmpeg 路径登记。
                            # 原写法在分支判定之前无条件 recording.add，而 only_flv 的「未找到 FLV」
                            # 分支既不调 clear_record_info 也不 discard：
                            #   ① recording / recording_time_list 留下永久幽灵条目（磁盘满退出判定
                            #      `if not recording:` 恒假、面板状态失真、TS 分支提交注定失败的转码）；
                            #   ② 时间字幕线程 generate_subtitles 是 while True 每秒追加一条 SRT，
                            #      唯一退出条件就是 `record_name not in main.recording` ——
                            #      幽灵条目让它永不退出，且房间线程每轮（默认 120s）再起一条，
                            #      线程数与 .srt 体积无界增长。
                            # 平台判定因此提到登记之前（只读 platform，与分支顺序无耦合）。
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
                            # MIN-2233 修复（2026-09-22）：原先把含自然语言的 f-string 提到 rec_info
                            # 变量再在多处 print(f"{rec_info}/...")，提取器的 print 规则只认首参为
                            # 常量/f-string 的形态，变量引用扫不到「准备开始录制视频」→ 四语目录零命中。
                            # 此处只保留可插值的原始字段，实际打印点各自 tr 插值（见本分支三处 print）。
                            rec_info_anchor_name = anchor_name
                            rec_info_full_path = full_path
                            if show_url:
                                re_plat = ("WinkTV", "PandaTV", "ShowRoom", "CHZZK", "YouTube")
                                # MID-28 修复（2026-09-20）：直播源地址带签名参数
                                # （wsSecret / txSecret / signature / ttwid 等），此前在本文件内
                                # **零**处过 mask_credentials，明文写进 300KB 轮转、保留多份的
                                # PlayURL.log / streamget.log 等于凭据长期落盘。
                                # 占位符名沿用目录里既有的 {m3u8_url}/{real_url}（改占位符名等于
                                # 新增四语 msgid，须由 i18n 侧统一收口），值一律先脱敏再传入。
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
                                # h265 地址已在保存格式为 TS/MKV/MP4 时放行进常规序列
                                # （stream_select._h265_copy_format_supported），此处仅在当前容器
                                # 装不下 HEVC 直拷（FLV/纯音频）时才接管转 TS——否则 TS 用户选中
                                # h265 原画后会每轮收到一条误导性的「use TS format instead」告警
                                if (
                                    isinstance(codec, list)
                                    and bool(codec)
                                    and codec[0] == "h265"
                                    and record_save_type.upper() not in ("TS", "MKV", "MP4")
                                ):
                                    logger.warning("FLV is not supported for h265 codec, use TS format instead")
                                    record_save_type = "TS"

                            if only_audio_record or any(i in record_save_type for i in ["MP3", "M4A"]):
                                # 扩展名 / 路径 / 执行骨架三项全部走统一实现（F-01）：
                                # 原分支内按 "MP3" in record_save_type 二次分叉出 4 处
                                # 完全相同的 _build_ffmpeg_output_args 调用（复制粘贴残留），
                                # 编码器与容器的实际裁决本就在该函数内部按同一条件完成。
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
                                    # ffmpeg 子进程自然结束（rc==0 / 被注释退出）：与直下 FLV 路径
                                    # 的 record_finished = True 对齐（2026-09-12 审查 6.1），
                                    # 触发「录后 30s 快检」语义——主播下播速重开时不会等一整轮周期
                                    record_finished = True
                                if comment_end:
                                    return

                            elif only_flv_record:
                                logger.info(
                                    i18n.tr(
                                        "Use Direct Downloader to Download FLV Stream: {record_url}",
                                        # MIN-2231（2026-09-23）：直下分支的地址可来自「自定义流地址」
                                        # （含 `https://u:p@host/x.flv` 形态），INFO 级会进 PlayURL.log
                                        record_url=utils.mask_credentials(record_url),
                                    )
                                )
                                # MI-05：title_in_name 为空（未勾选标题入文件名）时原写法产生双下划线；
                                # 与视频分支 _build_record_output_path 同构拼接。
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
                                        # MID-2202 修复（2026-09-22）：录制状态登记必须在字幕线程**之前**。
                                        # 原顺序是「先起字幕线程 → 再持锁登记」，与 ffmpeg 路径
                                        # （先 Popen/先登记，再起字幕）相反，也与本分支自己上方那条
                                        # SEV-09 注释的时序约定自相矛盾：generate_subtitles 是 while True，
                                        # 唯一退出条件是 `record_name not in main.recording`，登记晚于线程
                                        # 启动就存在「线程已跑、recording 里还没有」的窗口——此时若下载
                                        # 侧抛错走 except 的 clear_record_info，该房间会被判为已停止，
                                        # 字幕线程却已在运行；反过来，若登记前就返回，字幕线程会一直空转等
                                        # 一个永不出现的条目。登记是纯内存操作、无失败路径，理应先做。
                                        # 先持锁写入录制状态，再启动字幕线程与阻塞式下载（避免持锁期间长时间阻塞迭代共享状态的其他线程）
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
                                                    # 与 ffmpeg 分支同一条 msgid（MID-68）：两条录制路径
                                                    # （ffmpeg 拉流 / 强制直下）都要在画质被服务端钳制时告警，
                                                    # 复用同一模板可避免为同一语义再登记一份待翻译串
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

                                        # SEV-09 修复（2026-09-20）：字幕线程只在 flv_url 校验通过之后
                                        # 启动（与 ffmpeg 路径「先起 ffmpeg 再起字幕」对齐）——原写法在
                                        # 校验之前启动，配合下面未命中的 else 分支不清理，正好踩中上方
                                        # MID-2202 说的「永不退出」窗口。
                                        # MI-03：线程结束时从 create_var 清理自身条目（与 check_subprocess
                                        # 内的写法对齐）；旧写法只加不删，GUI/Web 常驻模式下花椒/shopee
                                        # 这类强制直下平台每轮录制都会泄漏一条 dict 条目 + Thread 对象引用。
                                        if create_time_file:

                                            def _subtitle_thread_target_direct() -> None:
                                                try:
                                                    generate_subtitles(record_name, subs_file_path)
                                                finally:
                                                    with record_state_lock:
                                                        # MIN-01 同族防护：只在登记的仍是本线程时回收
                                                        if (
                                                            create_var.get(subs_thread_name)
                                                            is threading.current_thread()
                                                        ):
                                                            create_var.pop(subs_thread_name, None)

                                            create_var[subs_thread_name] = threading.Thread(
                                                target=_subtitle_thread_target_direct,
                                                name=subs_thread_name,
                                                daemon=True,
                                            )
                                            create_var[subs_thread_name].start()

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
                                            # 直下路径无 check_subprocess 退出码反馈：成功按 host 补样本，
                                            # 与 ffmpeg 路径语义对齐
                                            record_success(record_host)
                                        elif (
                                            record_url not in url_comments and not exit_recording and recording_enabled
                                        ):
                                            # 真-失败（CDN 拒绝非 200 / 网络异常在函数内部已消化成 False，
                                            # 走不到外层 except 的 record_error）必须在此上报，否则坏线路
                                            # 绕开按 host 熔断统计被无限重撞；被注释/退出标志/停止录制
                                            # 的中断不计样本（非网络故障，不应污染错误窗口）
                                            record_error(record_host)

                                        # MIN-07 修复（2026-09-20）：统一走 clear_record_info 收尾。
                                        # 原写法是裸 recording.discard + recording_time_list.pop，
                                        # 绕过了 clear_record_info 里「URL 已被注释 → 同步移出
                                        # running_list 并递减 monitoring」这一步，监控计数在
                                        # 异常收尾路径上永不回落。clear_record_info 自带
                                        # record_state_lock（非重入），故此处不得再包一层 with。
                                        clear_record_info(record_name, record_url)
                                    else:
                                        # SEV-09 修复（2026-09-20）：未拿到 flv_url 也必须回收状态。
                                        # 原分支只打一条 debug 就什么也不做，registration 留下的
                                        # 幽灵条目会让时间字幕线程永不退出（见上方同条目注释）。
                                        # shopee/花椒只回了 m3u8、或接口未下发 flv_url（游客态、
                                        # 下播瞬间、接口结构变更）都会命中这里。
                                        logger.debug(i18n.tr("未找到FLV直播流，跳过录制"))
                                        clear_record_info(record_name, record_url)
                                except Exception as e:
                                    clear_record_info(record_name, record_url)
                                    color_obj.print_colored(
                                        # MIN-2233 修复（2026-09-22）：同上，f-string 直传 print_colored
                                        # 提取器扫不到「直播录制出错」，改为 tr 预格式化后整体传入。
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
                                # F-01：FLV / MKV / MP4 三条分支的「路径构造 + 命令构造 +
                                # 执行骨架」完全一致，差异只在 _build_record_output_path 与
                                # _build_ffmpeg_output_args 内部按保存类型查表，故合并为一条。
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
                                    # ffmpeg 自然结束触发「录后 30s 快检」（详见同位置注释）
                                    record_finished = True
                                # MIN-2235 修复（2026-09-22）：转码必须在 comment_end 早退**之前**发起。
                                # 原顺序是「if comment_end: return」在前、FLV 转码在后（且只在 FLV 分支），
                                # 于是「地址被注释 / 收到停止录制」导致的提前结束会直接 return，已录到的
                                # .flv 永不转 mp4——用户开了「自动转 mp4」也拿不到 MP4，且无任何告警
                                # （静默丢失）。分段枚举由 _segment_files 精确匹配，早退前调用不会误伤。
                                # MKV / MP4 已是成品容器，历史行为即不转码，保持原样，故此处仅 FLV 真调用。
                                # 复核判据：tests/test_regression_2026_09_22_main.py 断言本分支
                                # FLV + comment_end 时 _convert_after_record 被调用而 MKV/MP4 不被调用。
                                _convert_if_flv = record_save_type == "FLV"
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
                                    # ffmpeg 自然结束触发「录后 30s 快检」（详见同位置注释）
                                    record_finished = True
                                if comment_end:
                                    # 被注释 / 停止录制导致的提前结束：check_subprocess 在
                                    # return True 之前走不到 rc==0 的转码分支，故在此补转
                                    # 已录到的部分。
                                    # 2026-09-14 统一修正：原 TS 非分段路径在此**无条件**
                                    # 起线程转码，无视用户「是否录制完成后转为MP4格式」设置，
                                    # 与 TS 分段路径、check_subprocess 自然结束路径的口径
                                    # 均不一致（F-01 五份复制粘贴造成的典型行为漂移）。
                                    _convert_after_record(save_file_path, split_video_by_time)
                                    return

                            count_time = time.time()
                            # 样本改由各录制路径按实际结果上报（check_subprocess 按退出码记成功/失败，
                            # 直下路径按下载结果记）：旧的「轮末无条件记成功」会把 ffmpeg 失败轮
                            # （如 CDN 403 秒退）也记成成功样本，稀释按 host 熔断统计——多房间
                            # 同 host 时失败率永远到不了熔断阈值，坏线路被无限重撞。

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

                # 这里是.如果录制结束后,循环时间会暂时变成30s后检测一遍. 这样一定程度上防止主播卡顿造成少录
                # 当30秒过后检测一遍后. 会回归正常设置的循环秒数
                if record_finished:
                    count_time_end = time.time() - count_time
                    if count_time_end < 60:
                        x = 30
                    record_finished = False
                # 「else: x = num」分支已删除（2026-09-12 审查 6.1）：它无条件把 x 重置回 num，
                # 让上面的 +60s 退避永远不生效；删掉后 record_finished 未触发时 x 自然保留退避值。

                # 正常循环等待：逐秒递减，且停止录制时立即打断剩余等待、回到循环顶检测退出标志
                # （否则空闲房间线程会残留最长一个完整循环周期才退出）
                # L-01（2026-10-02）：等待条件补齐三信号（与上方主循环顶部 1061 行及
                # disable_record 等待同口径）——原只查 recording_enabled，URL 被注释/移除
                # 或进程退出标志已置时，线程仍要把剩余等待耗完才回到循环顶。
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
            # MID-30 修复（2026-09-20）：这里原本直接调 get_hub().room_stopped(...)，
            # 但本 finally 与 while True 同层、**每轮**都执行一次，于是每轮监测都会把
            # 正在监控的房间从枢纽里弹出、向 JSONL 边车写一条假「房间已停止监控」事件、
            # 并把统计清零（监控页只在录制那段时间显示房间，下轮开播才由 room_started
            # 重新注册）。真正的清理时机是房间线程退出——故此处只把本轮录制名回传给
            # 调用方持有的 room_state，由 _room_thread_target 的 finally 在线程出口调用
            # room_stopped 一次。「URL 被移除/注释后仍要清理」的行为保持不变
            # （那三条 return 同样经线程出口）。监控为旁路功能，故未取到录制名时什么都不做。
            if room_state is not None and record_name:
                room_state["name"] = record_name


# 打印本机 ffmpeg 版本信息并检测其可用性（缺失时由 check_ffmpeg 触发下载安装）；无入参，返回 ffmpeg 是否可用
def check_ffmpeg_existence() -> bool:
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
        # L-03（2026-10-02）：裸 logger.error(e) 在 CalledProcessError 的 str 为空（部分场景
        # 只含 returncode）或异常 str() 语义不明时无法归因，改为 i18n 模板带 type_name
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
# import i18n 必须早于下方 banner 的 i18n.tr（模块级顺序执行，晚于此处的 import
# 对已执行的 print 无效）；此处 i18n._tr 仍为默认 zh_CN 目录，banner 保持中文原文，
# 与迁移前「banner 先于语言解析打印」的行为一致。
import i18n

print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(i18n.tr("版本号: {version}", version=version))
print("GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(i18n.tr("支持平台: {platforms}", platforms=platforms))
print(".....................................................")
# 不再在模块级执行 check_ffmpeg_existence()：import main（web.py/gui.py/测试/工具）不应触发
# 111MB 的 FFmpeg 下载副作用。安装检查统一由各真实入口的 main() 完成（CLI/Web 录制线程）。
os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()
# URL_config.ini 去重已移入 main() 入口执行：import main 不应改写用户配置文件


# 布尔配置项统一经 src.config_io.read_config_bool 解析，识别 是/否、true/false、1/0、
# yes/no、on/off（大小写不敏感）。2026-09-17 移除了原
# `options: dict[str, bool] = {"是": True, "否": False}` 字典查表实现：该实现只在值恰为
# 「是/否」时命中字典，其余写法（含 Web 面板/外部编辑器写入的 true/false）会**静默**回落到
# options.get 的兜底实参，无告警无日志——实测致 8 项配置生效值漂移，其中
# 「是否跳过代理检测 = true」被判为 False 后 global_proxy=False，9 个海外平台的解析分支
# 直接走 else，100% 无法录制。
config: configparser.RawConfigParser = configparser.RawConfigParser()


_config_read_result = config.read(config_file, encoding=text_encoding)


# 把 config.ini 重新解析进一个**全新**的 RawConfigParser 并整体替换模块全局（MID-09）。
# 返回是否发生了替换。两处保守条件缺一不可：
#   ① 解析失败 / 文件打不开时保持既有内存态——configparser.read() 对打不开的文件是静默
#      跳过的，若先 clear 再 read，一次瞬时失败会让所有键以「缺键」被默认值写回，
#      等于把用户配置抹平成出厂默认值；
#   ② 解析结果为空（空文件）时同样不替换，避免把内存态清成零键后触发自愈补写。
# 与录制线程的写入统一在 file_update_lock 下互斥（该锁是 RLock，读侧持锁期间
# read_config_value 的补写路径可重入安全）。
def _hot_reload_config() -> bool:
    global config
    fresh = configparser.RawConfigParser()
    try:
        with file_update_lock:
            with open(config_file, "r", encoding=text_encoding) as fp:
                fresh.read_file(fp)
            if not fresh.sections():
                return False
            config = fresh
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        # 只记一行、保留旧配置：热加载失败绝不能中断录制主循环，也不得清空内存态
        # （沿用目录既有 msgid，异常类型作为实参预先求值传入，避免为本行日志新增四语条目）
        logger.warning(i18n.tr("发生 I/O 或配置解析错误: {err}", err=f"{type(e).__name__}: {e}"))
        return False
    return True


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
skip_proxy_check = read_config_bool(config, "录制设置", "是否跳过代理检测(是/否)", False)


def _read_https_recording_config(config_parser: configparser.RawConfigParser) -> bool:
    # 读取「是否启用https录制」（整合语义见下方 enable_https_recording 的注释）三级继承：
    # 1) 新键存在 → 直接取值；
    # 2) 新键缺失、旧键「是否强制启用https录制」存在 → 继承旧键值，并把该值
    #    迁移写回新键（保证 Web 配置页可见可编辑）；旧键本身只读、绝不重建；
    # 3) 两者皆无 → read_config_value 补写新键默认值「否」（保持配置自愈）。
    # 三处统一走 read_config_bool（见 config 定义上方的布尔解析总注）：旧实现用 options 字典
    # 查表，「是否启用https录制 = true」曾被静默判为「否」→ 拉流被降级为 http。
    if config_parser.has_option("录制设置", "是否启用https录制"):
        return read_config_bool(config_parser, "录制设置", "是否启用https录制", False)
    if config_parser.has_option("录制设置", "是否强制启用https录制"):
        legacy = read_config_bool(config_parser, "录制设置", "是否强制启用https录制", False)
        return read_config_bool(config_parser, "录制设置", "是否启用https录制", legacy)
    return read_config_bool(config_parser, "录制设置", "是否启用https录制", False)


# SSL/HTTPS 整合开关：「是否启用https录制」合并原「是否强制启用https录制」（协议强转）
# 与「是否禁用SSL证书验证(是/否)」（证书校验）两个配置项，统一为单一二元语义：
# 开启 = 流地址升级 https 拉流，并禁用**拉流侧** SSL 证书验证（保证 https 录制不被
#        CDN 证书主机名不匹配等问题阻断，即原「是否禁用SSL证书验证=是」的功能）；
# 关闭 = 流地址降级 http 拉流（无 TLS 不涉及证书验证），拉流侧恢复默认严格校验。
# 证书豁免仅作用于拉流侧（http_config.stream_ssl_verify）：控制面（登录 / 取 Cookie /
# 推送 token / 平台 API，http_config.ssl_verify）恒为严格校验，不再被本开关关闭——
# 旧实现会让一个拉流选项顺带关掉全站 TLS 校验，属安全缺陷。
# 该开关由 main() 主循环每轮读取配置后同步（热更新）。
from src import http_config as _http_config

enable_https_recording = _read_https_recording_config(config)
# 仅联动拉流侧（set_https_recording 内部置 stream_ssl_verify）；控制面不参与
_http_config.set_https_recording(enable_https_recording)
# 旧全局开关仅作迁移提示（只读，不写回）：检测到旧键=是 时告知功能已并入新开关
if config.has_option("录制设置", "是否禁用SSL证书验证(是/否)"):
    if read_config_bool(config, "录制设置", "是否禁用SSL证书验证(是/否)", False):
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
            logger.warning(
                i18n.tr(
                    "自动追加需禁用SSL验证的平台 {appended} 写回配置失败（已忽略，内存态仍生效）", appended=appended
                )
            )
        # 同步内存解析器，避免本轮后续读取拿到旧值
        config_parser.set("录制设置", "禁用SSL证书验证的平台(逗号分隔)", new_value)
        print(i18n.tr("提示: 已自动追加需禁用SSL证书验证的平台: {appended}", appended=",".join(appended)))
    return set(kept + appended)


# 把「需禁用 SSL 证书验证的平台」解析出来并落到 http_config（幂等、只追加不移除）。
# 抽出为函数是为了两个调用点共用同一份语义：① 模块 import 时（进程首启）；
# ② main() 主循环在配置值变化时重跑（MID-10 热更新）。
# 返回本次生效的平台集合，便于调用方/测试观察。
def _apply_ssl_platform_exempt(config_parser: configparser.RawConfigParser) -> set[str]:
    platforms = _sync_ssl_disable_platforms(config_parser)
    # 兼容旧版单列配置：虎牙是否禁用SSL证书验证(是/否)=是 → 等价于把「虎牙直播」加入列表。
    # 注意：仅当旧键实际存在时才读取，绝不写回——旧键只应被读、不应被自动重建，
    # 否则迁移后的配置旧键缺失反而触发「缺键→写回→不可写→崩溃」的坏兼容。
    if config_parser.has_option("录制设置", "虎牙是否禁用SSL证书验证(是/否)"):
        if read_config_bool(config_parser, "录制设置", "虎牙是否禁用SSL证书验证(是/否)", False):
            platforms.add("虎牙直播")
    for _p in platforms:
        _http_config.set_platform_ssl_verify(_p, False)
    return platforms


_ssl_disable_platforms = _apply_ssl_platform_exempt(config)
# MID-10：热加载时用于判定「禁用SSL证书验证的平台」是否变化，初值取 import 时的内存态
_last_ssl_disable_platforms_raw = ",".join(sorted(_ssl_disable_platforms))
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
    global a, acfun_cookie, args, auto_update_anchor_name, baidu_cookie, bark_msg_api, bark_msg_level, bark_msg_ring, begin_push_message_text, begin_show_push, bigo_cookie, bili_cookie, blued_cookie
    global changliao_cookie, check_path, chzzk_cookie, clean_emoji, converts_to_h264, converts_to_mp4, create_time_file, custom_script, delay_default, delete_origin_file, dingtalk_api_url, danmaku_platforms, danmaku_split_time, enable_danmaku, enable_danmaku_monitor
    global dingtalk_is_atall, dingtalk_phone_num, disable_record, disk_limited, disk_space_limit, douyu_cookie, dy_cookie, email_host, email_password, enable_https_recording, enable_proxy_platform, enable_proxy_platform_list, exit_recording
    global extra_enable_proxy, extra_enable_proxy_platform_list, faceit_cookie, filename_by_title, first_run, first_start, flextv_cookie, flextv_password, flextv_username, folder_by_author, folder_by_time, folder_by_title
    global haixiu_cookie, hls_collection_enabled, hls_collection_exclude_platforms, host_id, huajiao_cookie, huamao_cookie, hy_cookie, ini_URL_content, input_url, is_comment_line, is_run_script, jd_cookie, ks_cookie, kugou_cookie
    global laixiu_cookie, langlive_cookie, language, lehaitv_cookie, lianjie_cookie, line, line_list, line_spilt, liuxing_cookie, live_status_push, liveme_cookie, local_delay_default, login_email
    global look_cookie, loop_time, maoerfm_cookie, max_request, middle, migu_cookie, monitoring, name, netease_cookie, new_line, new_url, new_word
    global ntfy_api, ntfy_email, ntfy_tags, open_smtp_ssl, origin_line, over_push_message_text, over_show_push, pandatv_cookie, picarto_cookie, popkontv_access_token, popkontv_partner_code, popkontv_password
    global popkontv_username, pplive_cookie, proxy_addr, proxy_addr_bak, push_check_seconds, push_message_title, pushplus_token, qiandurebo_cookie, quality, replace_words, running_snapshot, running_url
    global semaphore, sender_email, sender_name, shopee_cookie, show_url, showroom_cookie, six_room_cookie, smtp_port, sooplive_cookie, sooplive_password, sooplive_username
    global scheduler, recording_semaphore
    # MID-07 / MID-10：主循环热加载写回的两个模块全局（单次录制时长上限、SSL 豁免平台的
    # 上一次原始配置值，用于「值变化时才重跑」的幂等判定）
    global max_record_seconds, _last_ssl_disable_platforms_raw
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

    # 启动期陈旧字节码缓存清理（判定基线与被删范围见 src/startup_cleanup.py）。放在此处而非模块顶部：
    # 此刻 src.* 已 import 完毕，本轮启动不受影响，只有源码/版本真的变化时下一次启动才付重编译成本。
    purge_stale_bytecode_caches(
        script_path, version, read_config_bool(config, "录制设置", "是否启动时清理陈旧字节码缓存(是/否)", True)
    )

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

            # 每轮重新读取配置文件，支持运行期间热更新；持锁读取避免与录制线程的
            # update_config 并发读到半写文件。
            # MID-09 修复（2026-09-20）：必须换成「读入全新解析器后整体替换」——
            # RawConfigParser.read() 是**合并**语义（不清空既有 section/option），用户手删的键
            # 在内存里会永久保留旧值，且 read_config_value 的「缺键补写」自愈永不触发
            # （has_option 恒真），热加载实际只是增量合并。保守条件见 _hot_reload_config。
            _ = _hot_reload_config()

            ini_URL_content = ""
            if os.path.isfile(url_config_file):
                with open(url_config_file, "r", encoding=text_encoding) as file:
                    ini_URL_content = file.read().strip()

            if not ini_URL_content.strip():
                if non_interactive:
                    # 非交互模式（如 web.py 守护线程）：跳过阻塞，等待 Web API 写入 URL
                    _interruptible_sleep(5)
                    continue
                input_url = input("请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n")
                with open(url_config_file, "w", encoding=text_encoding) as file:
                    _ = file.write(input_url)
        except EOFError:
            # CR-01 修复：无可用标准输入时 input() 抛 EOFError（窗口化启动、stdin 被重定向
            # 到 nul 等）。旧实现只捕获 OSError/configparser.Error，该异常会穿透出去，
            # 进程带栈退出——GUI 侧表现为「一点开始录制就没了」且无任何提示。
            # 与 non_interactive 同策略：退化为轮询等待外部写入 URL，而不是崩掉。
            logger.error(i18n.tr("无法从控制台读取直播间网址（无可用标准输入），等待配置文件写入"))
            _interruptible_sleep(5)
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
        # 仅在配置值变化时更新并发调度器：该值在动态模式下作为容量下限之一（容量随活跃任务数
        # 缩放、带安全下限），固定模式下即并发限制本身（见下方并发模式解析）；
        # 不再每轮重建信号量（旧逻辑会因实例替换导致并发计数失效、上限形同虚设）
        new_max_request = _safe_int(read_config_value(config, "录制设置", "同一时间访问网络的线程数", 3), 3)
        if new_max_request != max_request:
            max_request = new_max_request
            if scheduler is not None:
                scheduler.set_configured_limit(new_max_request)
            logger.debug(i18n.tr("并发线程数配置更新为 {max_request}", max_request=max_request))
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
        # MID-2206 修复（2026-09-22）：轮询类时间配置必须有下界。
        # 与 split_time / max_record_seconds 同口径——那两处早已做了 `<=0 回落默认值`，
        # 唯独循环时间没有：填 0 / 负数 / 极小值会原样生效，主循环与房间线程随即退化成
        # 无间隔轮询（每轮一次平台解析 + 一次 ffmpeg 拉取判定），表现为本机 CPU 打满、
        # 平台侧被全速撞接口（触发限流甚至封 IP），而日志上只是一堆重复的「获取失败」。
        # 30s 与同文件其它退避口径（`max(30.0, float(delay_default))`）保持一致。
        delay_default = max(30, _safe_int(read_config_value(config, "录制设置", "循环时间(秒)", 120), 120))
        # 排队读取网址的间隔语义上是 0 = 不等待，故只夹下界到 0，不允许负值
        local_delay_default = max(0, _safe_int(read_config_value(config, "录制设置", "排队读取网址时间(秒)", 0), 0))
        loop_time = read_config_bool(config, "录制设置", "是否显示循环秒数", False)
        show_url = read_config_bool(config, "录制设置", "是否显示直播源地址", False)
        # 语言热切换：配置变化时即时重载翻译目录（Web 面板/GUI 改语言后下轮循环生效），
        # 无需重启进程；录制中的 ffmpeg 子进程不受影响，仅影响新产生的控制台输出。
        # 空/未识别/语言目录缺失经 resolve_language 统一兜底（与启动初始化同语义）
        _new_language = _i18n_resolve(read_config_value(config, "录制设置", "language", ""))
        if _new_language != language:
            language = _new_language
            _i18n_set_language(_new_language)
            print(i18n.tr("语言已切换: {_new_language}", _new_language=_new_language))
        split_video_by_time = read_config_bool(config, "录制设置", "分段录制是否开启", False)
        enable_https_recording = _read_https_recording_config(config)
        # 与模块级初始化同语义（二元联动口径见 enable_https_recording 上方注释）；
        # 每轮同步以支持运行期间热更新（Web 面板改配置后下轮循环即生效）。
        _http_config.set_https_recording(enable_https_recording)
        # MID-10 修复（2026-09-20）：「禁用SSL证书验证的平台」原本只在模块 import 时同步一次
        # （_sync_ssl_disable_platforms + set_platform_ssl_verify 都写在模块级），运行期增删豁免
        # 平台必须重启进程——而相邻的 HLS 开关、https 开关都是每轮热生效，用户无从区分；
        # 录制启动后新出现证书异常的平台也不会被自动追加（而「启动时自动追加」正是本仓既定行为）。
        # 现按「配置值变化时」重跑：_sync_ssl_disable_platforms 幂等且只追加、绝不移除用户手填项，
        # set_platform_ssl_verify 重复设置同一 (平台, False) 亦为幂等。
        _ssl_disable_raw = read_config_value(config, "录制设置", "禁用SSL证书验证的平台(逗号分隔)", "")
        if _ssl_disable_raw != _last_ssl_disable_platforms_raw:
            _last_ssl_disable_platforms_raw = _ssl_disable_raw
            _apply_ssl_platform_exempt(config)
        disk_space_limit = _safe_float(read_config_value(config, "录制设置", "录制空间剩余阈值(gb)", 1.0), 1.0)
        # MID-11 修复（2026-09-20）：与相邻的时间类配置同口径做数值归一（原来只 str()）。
        # 空值（面板清空输入框即可产出）或非数字会直接进到命令行 → `-segment_time ""` /
        # `-segment_time abc` → ffmpeg 以 -22 在启动阶段秒退，又被判成「CDN 快速失败」，
        # 给一条健康流地址记探针退避（与 MID-02 同类归因错误）。<=0 同样按默认值处理。
        _split_time_raw = _safe_int(read_config_value(config, "录制设置", "视频分段时间(秒)", 1800), 1800)
        split_time = str(_split_time_raw if _split_time_raw > 0 else 1800)
        # MID-07 修复（2026-09-20）：单次录制时长上限改为可配置（0 = 不限制）。
        # 24 小时轮播/官方电台房间超过 6 小时是常态，旧的硬上限每 6 小时制造一条
        # record_error 失败样本（把按 host 熔断推向 open）并跳过转码/清退避。
        # 生效范围（分段开/关均判定）见 _MAX_RECORD_SECONDS 上方的小节注释。
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
        # M-12 修复（2026-09-29 审查）：分割后逐项 strip 并丢弃空项，口径与上方「HLS采集排除平台」
        # （hls_collection_exclude_platforms）完全一致。原写法 replace 全角逗号后直接 split(",")，
        # 用户在面板/GUI 里最常见的 `"斗鱼直播, B站直播"` 会得到 `" B站直播"`，而匹配点
        # `platform in danmaku_platforms`（见本文件 _danmaku_active 分支）按平台名精确比较 → 恒不命中，
        # 该平台弹幕被**静默**关闭（无一条日志），表现为「配置勾了却没弹幕」。
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
        # MID-2206 修复（2026-09-22）：同 delay_default，推送检测频率也必须夹下界。
        # 填 0 时上面「只推送不录制」分支的逐秒等待退化为 while 0 > 0 立即穿透，
        # 房间线程变成每轮一次全速解析 + 一次推送，接口被全速重撞。
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
        try:
            # 自定义保存路径可能尚不存在，shutil.disk_usage 会抛 FileNotFoundError
            os.makedirs(check_path, exist_ok=True)
            disk_free_gb = utils.check_disk_capacity(check_path, show=first_run)
        except Exception as e:
            logger.warning(
                i18n.tr("磁盘空间检测失败（跳过限制检查）: {type_name}: {e}", type_name=type(e).__name__, e=e)
            )
            disk_free_gb = float("inf")
        # SEV-2206（2026-09-22）：磁盘满只应是**可逆暂停**。exit_recording 除下面 else 分支外
        # 全文件无处复位，拿它表达资源约束的结果是「磁盘满过一次」之后哪怕用户清出空间，主循环的
        # 拉起条件 `not exit_recording` 也恒假：引擎活着、房间线程活着、一条录制都不起，
        # 且不再有任何提示。故引入 disk_limited：进入限制时同步置位两者（房间线程据此停流），
        # 空间恢复后同步复位并显式告知（下面 else 分支）。
        # 只在**状态跃迁**时打日志：主循环每 3s 跑到这里，无条件打会刷屏。
        # 检测失败路径上面已把 disk_free_gb 置 inf，故这里无需再判 None。
        #   [历史注] 2026-09-23 回归修正：上一轮引入 disk_limited 时误把进入条件
        #   `disk_free_gb < disk_space_limit` 整条删掉、只剩 `if not disk_limited`，于是首轮
        #   必进该分支并置 exit_recording=True，启动瞬间 recording 为空即 sys.exit(-1)/return
        #   ——任何磁盘空间下程序都在主循环第一轮自行退出。
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
                    # 2026-09-12 审查（低危）：Web 模式下 main() 跑在 uvicorn 起的守护线程里
                    # （web.py: `Thread(target=main.main, kwargs={"non_interactive": True})`）。
                    # sys.exit(-1) 只向**该线程**抛 SystemExit——线程死了，但 uvicorn 与
                    # 面板仍在运行，用户看到「面板一切正常、录制永不恢复」且无任何提示，
                    # 只能靠翻 web 日志才发现磁盘满。按运行模式分流：
                    #   - Web（non_interactive=True）→ 置标志并 return，让线程干净退出，
                    #     面板继续服务；用户可在面板看到状态并自行处理磁盘。
                    #   - CLI / GUI → 保留 sys.exit(-1)（进程就该退出）。
                    # SEV-2207（2026-09-22）：退出前先排空后处理线程池，避免转封装 worker 的
                    # join 抢在 ffmpeg 清理与日志归档之前（详见 _shutdown_postprocess_executor 注释）
                    _shutdown_postprocess_executor()
                    if non_interactive:
                        logger.warning("Web 模式：录制引擎已因磁盘空间不足停止，Web 面板继续服务")
                        return
                    sys.exit(-1)
        elif disk_limited:
            # 空间已回到阈值之上：两个标志一起复位。只清 disk_limited 不够——房间线程与主循环
            # 真正读的是 exit_recording，不清就等于「暂停」永远不解除（引擎活着但零录制、零提示）。
            disk_limited = False
            exit_recording = False
            logger.warning(
                i18n.tr(
                    "磁盘空间已恢复（剩余 {disk_free_gb} GB），解除录制暂停并继续按配置拉起房间",
                    disk_free_gb=disk_free_gb,
                )
            )

        try:
            # 三者均只用于成员检测：原为 list，导致本循环内每行的 `in` 都是 O(N) 线性扫描，
            # 80+ 房间时退化成 O(N²)；改 set 后为 O(1)，且消除下方 url_comments 的整表重建。
            # MID-2203 修复（2026-09-22）：解析过程先写**局部**集合，整轮解析成功后
            # （本 try 末尾）再整体替换全局。原写法在解析开始前就把 url_comments /
            # line_list / url_line_list / seen_urls 逐个重绑成空 set，而房间线程与主循环
            # 全程都在读这几个全局集合：
            #   ① 解析窗口内 url_comments 恒空 → 用户刚注释掉的房间被判定为「未注释」，
            #      本轮又被拉起，出现「注释了却还在录」；
            #   ② 解析中途抛错（文件被占用 / 正则回溯 / 写回失败）走外层 except，全局集合
            #      停在被清空的那一版 → 整轮状态丢失，直到下一轮重读文件才恢复。
            # 局部变量名统一加下划线前缀，避免与全局名混淆。
            _url_comments: set[str] = set()
            _line_list: set[str] = set()
            _url_line_list: set[str] = set()
            _seen_urls: set[str] = set()
            # L-06（2026-10-02）：清空移到每轮解析开始处——原在 try 尾部（拉起循环之后）才清，
            # 解析中途抛错走外层 except 时旧条目残留，下一轮解析结果叠加其上（幽灵拉起）。
            # 拉起循环消费的 text_no_repeat_url 已先取了快照，此处提前清空不影响本轮。
            url_tuples_list = []
            # 2026-09-12 审查 6.1：原代码在此迭代同一文件，循环体内调 delete_line / update_file
            # （两者均 truncate 重写整个 URL_config.ini）。文件较大（>8KB）时迭代器底层
            # 文件指针已被 truncate，for origin_line in file: 漏读后半段；此外重复 I/O
            # 把 N 个重复行变成 N 次全文件读写。改为先 readlines 一次性物化为 list，
            # 再迭代去重与更新——file handle 全程关闭，update_file/delete_line 写入
            # 的临时文件不会被本 for 句柄持有，可正常 replace 落盘
            with open(url_config_file, "r", encoding=text_encoding, errors="ignore") as file:
                _url_lines = file.readlines()
            for origin_line in _url_lines:
                try:
                    if origin_line in _line_list:
                        # SEV-05 调用侧修复（2026-09-20）：delete_line 现返回 bool
                        # （True 仅当真的删掉了一行；两侧先 rstrip 行尾再比较，CRLF 文件不再
                        # 静默 no-op）。原调用点丢弃返回值，删除失败时整轮去重退化为永久 no-op
                        # 且完全不可观测——重复 URL 每轮重复起线程。此处按 False 告警。
                        # `is False` 而非 `not ...`：兼容「尚未返回 bool」的旧实现（返回 None
                        # 时不得误报失败）。
                        if delete_line(url_config_file, origin_line) is False:
                            logger.warning(
                                i18n.tr(
                                    "删除重复配置行失败: {origin_line}",
                                    origin_line=utils.mask_credentials(origin_line.strip()),
                                )
                            )
                    _line_list.add(origin_line)
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

                    # CR-02 修复：旧写法在元素个数 >3 时执行 `quality, url, name = split_line`
                    # 抛 ValueError（"too many values to unpack"），且该异常不在行内捕获，会
                    # 冒泡终止整个 for 循环——坏行之后的所有直播间此后每一轮都处理不到。
                    # 改为「前两段为画质+URL、其余全部合并为主播名」，结构上不可能抛异常。
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
                    elif contains_url(split_line[0]):
                        # 3 段以上且首段是 URL：未写画质，第二段起全是主播名
                        # （旧写法会把 URL 当成 quality、把主播名当成 url，拼出非法地址后被自动注释掉）
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
                        # SEV-05 调用侧修复：同上，按返回值告警（URL 归一后重复，但文件里删不掉）
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
                    url_host = url.split("/")[2]

                    if "live.shopee." in url_host or ".shp.ee" in url_host:
                        url_host = "live.shopee." if "live.shopee." in url_host else ".shp.ee"

                    # SEV-03 后续（2026-09-20）：准入白名单与分派表必须同一判据——一律走
                    # _stream_path_suffix（按 path 取**小写**扩展名，2026-09-12 补的小写判定
                    # 也在该函数内）。这里原先是整串子串包含，于是 ?a=.flv 形态的内网地址能
                    # 通过准入、却因 _match_stream_suffix 改判 path 而落到「无法识别」分支空转；
                    # 而大小写敏感时大写 .M3U8 / .FLV 会被判成「未知链接」直接注释掉。现两端无隙。
                    if url_host in PLATFORM_HOST or _stream_path_suffix(url) in (".flv", ".m3u8"):
                        if url_host in CLEAN_URL_HOST_LIST:
                            url = update_file(url_config_file, old_str=url, new_str=url.split("?")[0]) or url

                        if url_host == "www.xiaohongshu.com":
                            # 2026-10-04：改走统一解析器 spider.parse_xhs_live_url。旧写法
                            # `re.search("&host_id=(.*?)(?=&|$)")` 有三个洞：① `&` 前缀使
                            # `?host_id=...`（首个参数）整条落空，等于没归一化；② 只留 host_id，
                            # 把页面鉴权用的 xsec_token/xsec_source 一并剥掉；③ 判据与解析器
                            # 各写一份，路径形态一变就漂移。归一化失败（非直播/非主页路径）时
                            # 保留原始地址，交由解析侧给出明确错误，不在这里把行注释掉。
                            # 短链不在此归一化：解跳转要发网络请求，准入阶段做会因一次抖动
                            # 就改写用户配置；短链的规范地址由 _resolve_xhslink_com 经
                            # new_record_url 通道在首轮解析成功后回写。
                            try:
                                normalized = spider.parse_xhs_live_url(url)["normalized_url"]
                            except spider.XhsUrlError:
                                normalized = url
                            if normalized != url:
                                url = update_file(url_config_file, old_str=url, new_str=normalized) or url
                        _seen_urls.add(url)
                        # 原实现为 `[i for i in url_comments if url not in i]`：每解析一行都重建
                        # 整个列表（O(N²) 次比较与内存分配），且子串匹配会误删「以该 URL 为前缀」
                        # 的其它 URL（如 .../1 与 .../12）。集合元素均为规范化后的完整 URL，
                        # 精确 discard 语义更准确，且为 O(1)。
                        _url_comments.discard(url)
                        if is_comment_line:
                            _url_comments.add(url)
                        else:
                            new_line = (quality, url, name)
                            url_tuples_list.append(new_line)
                    else:
                        if not origin_line.startswith("#"):
                            # MIN-2233 修复（2026-09-22）：原 f-string 直接传给 print_colored，既非
                            # print 首参也非 logger/tr 首参 → 提取器扫不到「本行包含未知链接」。
                            # 改为常量模板 tr 预格式化后整体传入（print_colored 第二参是颜色，不可传 kw）。
                            color_obj.print_colored(
                                i18n.tr(
                                    "\r{line} 本行包含未知链接.此条跳过",
                                    line=utils.mask_credentials(origin_line.strip()),
                                ),
                                color_obj.YELLOW,
                            )
                            _ = update_file(url_config_file, old_str=origin_line, new_str=origin_line, start_str="#")

                except Exception as err:
                    # CR-02 修复：单行脏数据不得中断整轮解析（旧形态的后果见上方 unpack 处注释）；
                    # 且报错文案须带上该行内容与真实原因，否则无法自查。
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
            running_snapshot = list(running_list)
            for running_url in running_snapshot:
                if running_url not in _seen_urls and running_url not in _url_comments:
                    _url_comments.add(running_url)

            # MID-2203（2026-09-22）：整轮解析（含上面 running_snapshot 归并）走完且未抛错，
            # 此刻才把三个集合整体换位。解析中途抛错时全局集合保持上一轮的值，
            # 房间线程看到的始终是「一份完整、自洽的注释/去重状态」，而不是空集。
            # L-05（2026-10-02）：换位项由四项减为三项——模块级 seen_urls 全局是「只写不读」的死
            # 变量（去重实际消费的是局部 _seen_urls），删全局声明后本行只会绑定一个无人读取的
            # 函数局部名，一并删除。
            url_comments = _url_comments
            line_list = _line_list
            url_line_list = _url_line_list

            # 原为 list(set(...))：去重的同时把配置顺序打乱，导致每轮启动/新增房间的顺序随机
            # （日志与「序号N」提示随之抖动）。dict.fromkeys 保序去重，且同为 O(N)。
            text_no_repeat_url = list(dict.fromkeys(url_tuples_list))

            if len(text_no_repeat_url) > 0:
                for url_tuple in text_no_repeat_url:
                    with record_state_lock:
                        monitoring = len(running_list)

                    if url_tuple[1] in not_record_list:
                        continue

                    # 录制开关关闭（Web 面板「停止录制」）时不拉起新房间线程；
                    # 已退出的房间线程由 remove_room_from_running 清理运行列表，
                    # 重新开启后本循环会按配置再次拉起
                    # SEV-2206（2026-09-22）：disk_limited 与 exit_recording 同步置位/复位，
                    # 这里显式再判一次——空间不足期间即便 exit_recording 被别处清零也不该拉起新房间。
                    if (
                        url_tuple[1] not in running_list
                        and not exit_recording
                        and not disk_limited
                        and recording_enabled
                    ):
                        print(
                            i18n.tr(
                                "\r{first_start}地址: {url_tuple}",
                                first_start="新增" if not first_start else "传入",
                                url_tuple=utils.mask_credentials(url_tuple[1]),
                            )
                        )
                        with record_state_lock:
                            monitoring += 1
                            running_list.append(url_tuple[1])
                            args = (url_tuple, monitoring)
                        # MIN-01：thread_key 不再由 monitoring（= len(running_list)+1）推导，
                        # 见下方赋值处的说明；此处只保留「序号」语义的 monitoring 计数

                        # 房间录制线程入口：_key 为该线程在 create_var 中的注册键，
                        # _args 为传给 start_record 的参数元组（tuple[tuple[str,str,str], int]）。
                        # 通过 Thread(args=...) 在创建线程时绑定当前循环值，规避闭包晚期绑定陷阱；无返回值。
                        # _room_state：跨「线程退出」边界把本轮录制名带回本函数，
                        # 供 finally 做弹幕监控房间清理（MID-30，见该条注释）。
                        def _room_thread_target(
                            _key: str, _args: tuple[tuple[str, str, str], int], _room_state: dict[str, str]
                        ) -> None:
                            try:
                                start_record(*_args, room_state=_room_state)
                            finally:
                                # 房间线程退出兜底：从运行列表移除该房间 URL（幂等，注释退出
                                # 路径已由 clear_record_info 清理）。覆盖「停止录制」退出路径——
                                # 不清理则主循环误判「仍在运行」，重新开始后该房间永不重启
                                remove_room_from_running(_args[0][1])
                                # H-5 修复：Shopee 平台 URL 更新（带 uid 的 new_record_url 注入
                                # not_record_list 跳过本轮）后无清除路径，旧线程持有的旧 URL 已
                                # 不在配置中而注释退出——该直播间从监控中永久消失（直到重启进程）。
                                # 即使 uid 未变同样触发。线程退出（任何原因）时按 base URL + "?"
                                # 起始精确匹配本线程登记的条目并移除，避免前缀相似 URL 误伤
                                # （Shopee 注入格式：new_record_url = record_url.split("?")[0]
                                #  + "?<uid>"，故按 base + "?" 前缀可唯一定位本线程条目）。
                                # 不带锁是因为 not_record_list 是 list 而非 set，长度极短，
                                # 与主循环本端写入竞争窗口极窄——此处接受偶发漏清（下轮 Shopee
                                # 重新解析时会再次 append，相当于自然重置）
                                if _args[0][1]:
                                    _not_record_prefix = _args[0][1].split("?", 1)[0] + "?"
                                    # 长度守恒：清不到不抛错
                                    not_record_list[:] = [
                                        u for u in not_record_list if not u.startswith(_not_record_prefix)
                                    ]
                                # MID-30 修复（2026-09-20）：弹幕监控房间清理的时机是「线程退出」，
                                # 故由 start_record 每轮回填 room_state、在这里调一次（为什么不能
                                # 留在 start_record 的 finally：见那里的 MID-30 注释）。
                                # 清理也不能简单删除：删掉会回归「已失效房间永久残留」（AGENTS 约定）；
                                # 同房间重新录制时由 collector.start() 的 room_started 重新注册。
                                # 监控为旁路功能，清理失败静默（吞没即正确：不得因旁路中断录制收尾）。
                                if _room_state.get("name"):
                                    try:
                                        from src.danmaku_monitor import get_hub

                                        get_hub().room_stopped(_room_state["name"], "房间已停止录制")
                                    except Exception:
                                        pass
                                with record_state_lock:
                                    # MIN-01 修复（2026-09-20）：只在登记的确实是本线程时才 pop。
                                    # 键原为 f"thread_{len(running_list)}"，随房间退出而回落，
                                    # 新房间会复用仍存活线程的键 → 覆盖注册，旧线程退出时
                                    # 把别人的条目 pop 掉（任何「按 create_var 枚举房间线程」
                                    # 的后续改动都会立刻踩坑）。键已改为生命周期无关的唯一值，
                                    # 这里的归属校验是第二道防线（字幕线程同键族也走同一模式）。
                                    if create_var.get(_key) is threading.current_thread():
                                        create_var.pop(_key, None)

                        # MIN-01 修复：键与房间数量/序号解耦——uuid4 片段全局唯一，
                        # 不会与新拉起或仍在收尾的其它房间线程重名
                        thread_key = f"thread-{uuid.uuid4().hex[:12]}"
                        room_state: dict[str, str] = {"name": ""}
                        create_var[thread_key] = threading.Thread(
                            target=_room_thread_target,
                            name=thread_key,
                            args=(thread_key, args, room_state),
                        )
                        create_var[thread_key].daemon = True
                        # MID-2201（2026-09-22）：running_list.append / monitoring += 1 发生在
                        # start() **之前**，而 start() 是会抛异常的（线程数打满时 RuntimeError:
                        # can't start new thread）。原写法一旦抛错：该 URL 永久留在 running_list
                        # 里，主循环的「未在 running_list 中」判定恒假 → 这个房间从此再也不会被
                        # 拉起（重启进程才好），且没有任何告警。此处就地回滚登记并跳过本轮。
                        try:
                            create_var[thread_key].start()
                        except RuntimeError as e:
                            create_var.pop(thread_key, None)
                            remove_room_from_running(url_tuple[1])
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
            # 上报当前活跃监控数，供调度器自适应全局并发容量（解除多任务排队瓶颈）
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
