# -*- encoding: utf-8 -*-

"""
Author: Hmily
GitHub: https://github.com/ihmily
Date: 2023-07-17 23:52:05
Update: 2025-10-23 19:48:05
Copyright (c) 2023-2025 by Hmily, All Rights Reserved.
Function: Record live stream video.
"""
import asyncio
import os
import sys
import builtins
import subprocess
import signal
import threading
import time
import datetime
import re
import shutil
import random
import uuid
from pathlib import Path
import urllib.request
from urllib.error import URLError, HTTPError
from typing import Any
import configparser
import httpx
from src import spider, stream, danmaku
from src.proxy import ProxyDetector
from src.utils import logger
from src import utils
from msg_push import (
    dingtalk, xizhi, tg_bot, send_email, bark, ntfy, pushplus
)
from ffmpeg_install import (
    check_ffmpeg, ffmpeg_path, current_env_path
)

version = "v4.0.7"
platforms = ("\n国内站点：抖音|快手|虎牙|斗鱼|YY|B站|小红书|bigo|blued|网易CC|千度热播|猫耳FM|Look|TwitCasting|百度|微博|"
             "酷狗|花椒|流星|Acfun|畅聊|映客|音播|知乎|嗨秀|VV星球|17Live|浪Live|漂漂|六间房|乐嗨|花猫|淘宝|京东|咪咕|连接|来秀"
             "\n海外站点：TikTok|SOOP|PandaTV|WinkTV|FlexTV|PopkonTV|TwitchTV|LiveMe|ShowRoom|CHZZK|Shopee|"
             "Youtube|Faceit|Picarto")

recording = set()
error_count = 0
pre_max_request = 10
max_request_lock = threading.Lock()
error_window = []
error_window_size = 10
error_threshold = 5
monitoring = 0
running_list = []
url_tuples_list = []
url_comments = []
text_no_repeat_url = []
create_var = locals()
first_start = True
exit_recording = False
need_update_line_list = []
first_run = True
not_record_list = []
start_display_time = datetime.datetime.now()
global_proxy = False
recording_time_list = {}
# 抖音直播间 web_rid -> 真实 room_id，弹幕 WebSocket 需要真实 room_id
danmaku_room_ids = {}
# 弹幕开关先给默认值：真正的配置在下面的主循环里才读取，
# 这里不初始化的话，循环尚未执行到配置段时 check_subprocess 会引用到未定义变量
danmaku_enabled = False
danmaku_formats = 'json,srt,ass'
danmaku_burn = False
danmaku_max_lines = 4
danmaku_duration = 5.0
danmaku_font_size = 40
script_path = os.path.split(os.path.realpath(sys.argv[0]))[0]
config_file = f'{script_path}/config/config.ini'
url_config_file = f'{script_path}/config/URL_config.ini'
backup_dir = f'{script_path}/backup_config'
text_encoding = 'utf-8-sig'
rstr = r"[\/\\\:\*\？?\"\<\>\|&#.。,， ~！· ]"
default_path = f'{script_path}/downloads'
os.makedirs(default_path, exist_ok=True)
file_update_lock = threading.Lock()
os_type = os.name
clear_command = "cls" if os_type == 'nt' else "clear"
color_obj = utils.Color()
os.environ['PATH'] = ffmpeg_path + os.pathsep + current_env_path

# 绿色版（打包成 exe）时，Node 运行时随包放在 exe 同目录的 runtime 子目录里。
# 弹幕签名要用 PyExecJS 执行 JS，而 execjs 只认 PATH 里的 node.exe，这里补进去；
# 源码方式运行时没有这个目录，此段无副作用。
_runtime_dir = os.path.join(script_path, 'runtime')
if os.path.isdir(_runtime_dir):
    os.environ['PATH'] = _runtime_dir + os.pathsep + os.environ.get('PATH', '')


def signal_handler(_signal, _frame):
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)


def display_info() -> None:
    global start_display_time
    time.sleep(5)
    while True:
        try:
            sys.stdout.flush()
            time.sleep(5)
            if Path(sys.executable).name != 'pythonw.exe':
                os.system(clear_command)
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
                no_repeat_recording = list(set(recording))
                print(f"正在录制{len(no_repeat_recording)}个直播: ")
                for recording_live in no_repeat_recording:
                    rt, qa = recording_time_list[recording_live]
                    have_record_time = now_time - rt
                    print(f"{recording_live}[{qa}] 正在录制中 {str(have_record_time).split('.')[0]}")

                # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                print("x" * 60)
                start_display_time = now_time
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")


def update_file(file_path: str, old_str: str, new_str: str, start_str: str = None) -> str | None:
    if old_str == new_str and start_str is None:
        return old_str
    with file_update_lock:
        file_data = []
        with open(file_path, "r", encoding=text_encoding) as f:
            try:
                for text_line in f:
                    if old_str in text_line:
                        text_line = text_line.replace(old_str, new_str)
                        if start_str:
                            text_line = f'{start_str}{text_line}'
                    if text_line not in file_data:
                        file_data.append(text_line)
            except RuntimeError as e:
                logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                if ini_URL_content:
                    with open(file_path, "w", encoding=text_encoding) as f2:
                        f2.write(ini_URL_content)
                    return old_str
        if file_data:
            with open(file_path, "w", encoding=text_encoding) as f:
                f.write(''.join(file_data))
        return new_str


def delete_line(file_path: str, del_line: str, delete_all: bool = False) -> None:
    with file_update_lock:
        with open(file_path, 'r+', encoding=text_encoding) as f:
            lines = f.readlines()
            f.seek(0)
            f.truncate()
            skip_line = False
            for txt_line in lines:
                if del_line in txt_line:
                    if delete_all or not skip_line:
                        skip_line = True
                        continue
                else:
                    skip_line = False
                f.write(txt_line)


def get_startup_info(system_type: str):
    if system_type == 'nt':
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    else:
        startup_info = None
    return startup_info


def segment_video(converts_file_path: str, segment_save_file_path: str, segment_format: str, segment_time: str,
                  is_original_delete: bool = True) -> None:
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            ffmpeg_command = [
                "ffmpeg",
                "-i", converts_file_path,
                "-c:v", "copy",
                "-c:a", "copy",
                "-map", "0",
                "-f", "segment",
                "-segment_time", segment_time,
                "-segment_format", segment_format,
                "-reset_timestamps", "1",
                "-movflags", "+frag_keyframe+empty_moov",
                segment_save_file_path,
            ]
            _output = subprocess.check_output(
                ffmpeg_command, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
            )
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f'Error occurred during conversion: {e}')
    except Exception as e:
        logger.error(f'An unknown error occurred: {e}')


def converts_mp4(converts_file_path: str, is_original_delete: bool = True) -> None:
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            if converts_to_h264:
                color_obj.print_colored("正在转码为MP4格式并重新编码为h264\n", color_obj.YELLOW)
                ffmpeg_command = [
                    "ffmpeg", "-i", converts_file_path,
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "23",
                    "-vf", "format=yuv420p",
                    "-c:a", "copy",
                    "-f", "mp4", converts_file_path.rsplit('.', maxsplit=1)[0] + ".mp4",
                ]
            else:
                color_obj.print_colored("正在转码为MP4格式\n", color_obj.YELLOW)
                ffmpeg_command = [
                    "ffmpeg", "-i", converts_file_path,
                    "-c:v", "copy",
                    "-c:a", "copy",
                    "-f", "mp4", converts_file_path.rsplit('.', maxsplit=1)[0] + ".mp4",
                ]
            _output = subprocess.check_output(
                ffmpeg_command, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
            )
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f'Error occurred during conversion: {e}')
    except Exception as e:
        logger.error(f'An unknown error occurred: {e}')


_ASS_TIME_RE = re.compile(r'^(\d+):(\d{1,2}):(\d{1,2})[.,](\d{1,3})$')


def _parse_ass_time(value: str) -> float:
    """ASS 时间戳 H:MM:SS.cc -> 秒。"""
    m = _ASS_TIME_RE.match(value.strip())
    if not m:
        return 0.0
    h, minute, second, frac = m.groups()
    return int(h) * 3600 + int(minute) * 60 + int(second) + float(f'0.{frac}')


def _format_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    h = int(seconds // 3600)
    m = int(seconds % 3600 // 60)
    s = int(seconds % 60)
    cs = int(round(seconds * 100) % 100)
    return f'{h:d}:{m:02d}:{s:02d}.{cs:02d}'


def probe_video_info(video_path: str) -> tuple:
    """探测视频起始时间戳与时长，失败返回 (0.0, 0.0)。

    分段录制的片段时间戳未必从 0 开始（取决于 muxer 有没有重置），
    烧录前要靠它决定要不要平移时间轴。
    """
    try:
        output = subprocess.check_output(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=start_time,duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
            stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
        )
        values = output.decode('utf-8', errors='ignore').split()
        if len(values) >= 2:
            return float(values[0]), float(values[1])
    except Exception:
        pass
    return 0.0, 0.0


def has_ass_events(ass_path: str) -> int:
    """统计 ASS 里的字幕条数，用于判断这次到底有没有抓到可烧的弹幕。"""
    try:
        with open(ass_path, encoding='utf-8') as f:
            return sum(1 for line in f if line.startswith('Dialogue:'))
    except OSError:
        return 0


def slice_ass_for_segment(ass_path: str, start_sec: float, duration_sec: float, out_path: str) -> int:
    """从整场 ASS 裁出「某一段」的字幕。

    分段录制时每个片段是独立文件，而弹幕 ASS 只有一份且按整场时间轴排列，
    所以要把时间轴整体前移该段的起始位置，并丢掉落在这一段之外的条目。
    返回保留下来的条数。
    """
    try:
        with open(ass_path, encoding='utf-8') as f:
            raw = f.read().splitlines()
    except OSError:
        return 0

    lines = []
    for line in raw:
        if line.startswith('Dialogue:'):
            # Text 是最后一个字段且允许内含逗号，所以只切前 9 个逗号
            parts = line.split(',', 9)
            if len(parts) < 10:
                continue
            start = _parse_ass_time(parts[1]) - start_sec
            end = _parse_ass_time(parts[2]) - start_sec
            if end <= 0 or start >= duration_sec or end <= start:
                continue
            parts[1] = _format_ass_time(max(0.0, start))
            parts[2] = _format_ass_time(min(end, duration_sec))
            lines.append(','.join(parts))
        else:
            lines.append(line)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return sum(1 for line in lines if line.startswith('Dialogue:'))


def probe_video_size(video_path: str) -> tuple[int, int] | None:
    """取视频画面的宽高。ASS 的 PlayRes 必须与之一致，否则字幕会被拉伸变形。"""
    try:
        output = subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height', '-of', 'csv=p=0', video_path,
        ], stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type))
        parts = output.decode('utf-8', errors='ignore').strip().split(',')
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return None


def ass_matching_video(ass_path: str, size: tuple[int, int] | None) -> tuple[str, str | None]:
    """按视频分辨率重新渲染一份 ASS，返回 (实际要用的 ass 路径, 需要调用方删除的临时文件)。

    弹幕 ASS 是在录制结束时生成的，那一刻还看不到成品视频的分辨率，只能先按 1080p 排；
    而抖音有不少竖屏直播（720x1280），直接套上去字幕会被压扁。这里拿 jsonl 里的原始
    记录按真实宽高重排一遍，row 轨道和时间戳都不变。
    """
    if not size:
        return ass_path, None
    jsonl_path = None
    if ass_path.endswith('.danmaku.ass'):
        jsonl_path = ass_path[: -len('.danmaku.ass')] + '.danmaku.jsonl'
    if not jsonl_path or not os.path.exists(jsonl_path):
        return ass_path, None
    playres = (int(size[0]), int(size[1]))
    temp_path = f'{ass_path}.{playres[0]}x{playres[1]}.ass'
    try:
        written, _dropped = danmaku.render_ass_from_jsonl(
            jsonl_path, temp_path, danmaku_max_lines, danmaku_duration, danmaku_mode, playres,
            types=danmaku_types, gift_min_diamond=danmaku_gift_min_diamond,
            font_size=danmaku_font_size,
        )
        if written:
            return temp_path, temp_path
    except Exception as e:
        logger.warning(f'按 {playres[0]}x{playres[1]} 重排弹幕失败，沿用原字幕: {e}')
    return ass_path, None


def burn_danmaku_into_video(video_path: str, ass_path: str, video_start: float = 0.0) -> None:
    """把弹幕 ASS 字幕烧进视频画面。

    输出到独立的「原名_弹幕.mp4」，**原文件保留**：烧录是整段重编码，
    耗时和体积都不小，失败或被中断时不该连原始素材一起损失。
    """
    if not (os.path.exists(video_path) and os.path.exists(ass_path)):
        return
    try:
        if os.path.getsize(video_path) == 0 or os.path.getsize(ass_path) == 0:
            return
    except OSError:
        return

    if has_ass_events(ass_path) == 0:
        logger.warning(f'本次没有抓到任何弹幕，跳过烧录: {ass_path}')
        return

    video_path = os.path.abspath(video_path)
    base, ext = video_path.rsplit('.', maxsplit=1)
    out_path = f'{base}_弹幕.{ext}'

    # 幂等：产物已存在（上次烧过）就不重烧。启动补烧扫描靠它避免重复劳动。
    try:
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            logger.info(f'弹幕烧录产物已存在，跳过: {os.path.basename(out_path)}')
            return
    except OSError:
        pass

    # ass 滤镜参数里的 Windows 盘符冒号极难转义（实测 `C\:` 会把参数撕碎报
    # "No option name"，引号包裹、双反斜杠也各有兼容性坑），而弹幕文件和视频
    # 本来就在同一目录——直接把工作目录切过去用纯文件名引用，彻底绕开这个坑。
    work_dir = os.path.dirname(ass_path)
    ass_name = os.path.basename(ass_path)

    try:
        color_obj.print_colored(f"正在把弹幕烧进画面 -> {os.path.basename(out_path)}\n", color_obj.YELLOW)
        ffmpeg_command = ["ffmpeg", "-y"]
        # 片段时间戳不是从 0 开始时，先把它们拉回原点，字幕时间轴才对得上
        if video_start > 0.5:
            ffmpeg_command += ["-itsoffset", f"-{video_start:.3f}"]
        ffmpeg_command += [
            "-i", video_path,
            "-vf", f"ass={ass_name}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-f", ext, out_path,
        ]
        subprocess.check_output(
            ffmpeg_command, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type), cwd=work_dir
        )
        color_obj.print_colored(f"弹幕已烧录: {out_path}\n", color_obj.GREEN)
    except subprocess.CalledProcessError as e:
        output = getattr(e, 'output', b'') or b''
        tail = output.decode('utf-8', errors='ignore')[-400:]
        logger.error(f'弹幕烧录失败: {e}\nffmpeg 输出尾部:\n{tail}')
    except Exception as e:
        logger.error(f'弹幕烧录出现未知错误: {e}')


def post_process_video(video_path: str, is_original_delete: bool, ass_path: str | None = None) -> None:
    """转码为 MP4，随后按需把弹幕烧进画面。两者必须串行——烧录的输入是转码产物。"""
    converts_mp4(video_path, is_original_delete)
    if not (danmaku_burn and ass_path):
        return
    final_path = video_path.rsplit('.', maxsplit=1)[0] + '.mp4'
    if os.path.exists(final_path):
        start_time, _duration = probe_video_info(final_path)
        used_ass, temp_ass = ass_matching_video(ass_path, probe_video_size(final_path))
        try:
            burn_danmaku_into_video(final_path, used_ass, video_start=start_time)
        finally:
            if temp_ass:
                try:
                    os.remove(temp_ass)
                except OSError:
                    pass


def post_process_segments(segment_template_path: str, is_original_delete: bool, ass_path: str,
                          need_convert: bool = True) -> None:
    """分段录制下的后半程：逐个片段处理 + 烧录各自区间的弹幕。

    need_convert 为真时先转码成 mp4 再烧（保存格式是 TS 的情况）；为假时片段
    本身就是成品（保存格式 mp4/flv/mkv），跳过转码直接烧。

    必须串行处理：每一段的字幕起点来自它前面所有段的**实际时长累加**
    （ffmpeg 按关键帧切段，边界不严格等于配置的分段秒数），并行就算不出这个偏移。
    """
    directory = os.path.dirname(segment_template_path)
    prefix = os.path.basename(segment_template_path).rsplit('_', maxsplit=1)[0]
    video_exts = ('.ts', '.flv', '.mkv', '.mp4')
    danmaku_exts = ('.danmaku.ass', '.danmaku.srt', '.danmaku.jsonl')

    candidates = []
    for path in utils.get_file_paths(directory):
        name = os.path.basename(path)
        if prefix not in name or '_弹幕' in name:
            continue
        if name.endswith(danmaku_exts):
            continue
        if os.path.splitext(name)[1].lower() not in video_exts:
            continue
        candidates.append(path)
    candidates.sort()

    if not candidates:
        logger.warning(f'没有找到待处理的分段视频: {directory}')
        return

    sized_ass = ass_path
    temp_ass = None
    try:
        offset = 0.0
        for index, path in enumerate(candidates, start=1):
            if need_convert:
                converts_mp4(path, is_original_delete)
                final_path = path.rsplit('.', maxsplit=1)[0] + '.mp4'
            else:
                final_path = path
            if not os.path.exists(final_path) or os.path.getsize(final_path) == 0:
                continue
            start_time, duration = probe_video_info(final_path)
            if duration <= 0:
                duration = 0.0
            # 已有烧录产物的段直接跳过（启动补烧场景），但时长偏移必须照常累加
            burned_path = f'{os.path.splitext(final_path)[0]}_弹幕.mp4'
            if os.path.exists(burned_path) and os.path.getsize(burned_path) > 0:
                logger.info(f'第 {index}/{len(candidates)} 段已有烧录产物，跳过')
                offset += duration
                continue
            if sized_ass == ass_path:
                # 各段分辨率一致，重排一次就够了
                sized_ass, temp_ass = ass_matching_video(ass_path, probe_video_size(final_path))
            seg_ass = f'{os.path.splitext(final_path)[0]}.seg{index:03d}.ass'
            kept = slice_ass_for_segment(sized_ass, offset, duration, seg_ass)
            logger.info(f'第 {index}/{len(candidates)} 段：命中 {kept} 条弹幕，准备烧录')
            try:
                burn_danmaku_into_video(final_path, seg_ass, video_start=start_time)
            finally:
                try:
                    os.remove(seg_ass)
                except OSError:
                    pass
            offset += duration
    finally:
        if temp_ass:
            try:
                os.remove(temp_ass)
            except OSError:
                pass


def scan_and_reburn_missed(download_root: str) -> None:
    """启动时扫描历史录制目录，把「字幕已生成但没有烧录产物」的场次补烧。

    录制结束后的烧录是重活（每段一次完整重编码），中途重启容器/断电/崩溃都会
    把它打断，留下的场次字幕齐全却没有 _弹幕.mp4。判断依据很稳：
    ASS 只在录制结束后才生成，它存在就代表该场已经结束，不会和正在录的场次撞车；
    再配合 burn_danmaku_into_video 的幂等跳过，重复执行也安全。
    """
    if not download_root or not os.path.isdir(download_root):
        return
    # 稍等再扫：给启动期的录制拉起留点余量，也避免和刚结束场次的正常烧录抢跑
    time.sleep(60)
    if exit_recording:
        return
    now = time.time()
    for dirpath, _dirnames, filenames in os.walk(download_root):
        for name in filenames:
            if not name.endswith('.danmaku.ass') or '.danmaku.ass.' in name:
                continue  # 跳过按分辨率重排的临时 ass（形如 xxx.danmaku.ass.1280x720.ass）
            ass_path = os.path.join(dirpath, name)
            try:
                if now - os.path.getmtime(ass_path) < 600:
                    continue  # 刚生成的，正常流程马上会自己烧
            except OSError:
                continue
            prefix_path = ass_path[:-len('.danmaku.ass')]
            if not os.path.exists(prefix_path + '.danmaku.jsonl'):
                continue
            base_name = os.path.basename(prefix_path)
            segments = sorted(
                p for p in utils.get_file_paths(dirpath)
                if os.path.basename(p).startswith(base_name + '_')
                and '_弹幕' not in os.path.basename(p)
                and '.seg' not in os.path.basename(p)
                and os.path.splitext(p)[1].lower() == '.mp4'
            )
            logger.info(f'发现未烧录的历史录制，开始补烧: {ass_path}')
            try:
                if segments:
                    # post_process_segments 从传入路径提取前缀，所以要带段号传第一个分段
                    post_process_segments(segments[0], False, ass_path, need_convert=False)
                else:
                    single = prefix_path + '.mp4'
                    if os.path.exists(single):
                        sized_ass, temp_ass = ass_matching_video(ass_path, probe_video_size(single))
                        try:
                            burn_danmaku_into_video(single, sized_ass)
                        finally:
                            if temp_ass:
                                try:
                                    os.remove(temp_ass)
                                except OSError:
                                    pass
            except Exception as e:
                logger.error(f'补烧 {ass_path} 失败: {e}')


def converts_m4a(converts_file_path: str, is_original_delete: bool = True) -> None:
    try:
        if os.path.exists(converts_file_path) and os.path.getsize(converts_file_path) > 0:
            _output = subprocess.check_output([
                "ffmpeg", "-i", converts_file_path,
                "-n", "-vn",
                "-c:a", "aac", "-bsf:a", "aac_adtstoasc", "-ab", "320k",
                converts_file_path.rsplit('.', maxsplit=1)[0] + ".m4a",
            ], stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type))
            if is_original_delete:
                time.sleep(1)
                if os.path.exists(converts_file_path):
                    os.remove(converts_file_path)
    except subprocess.CalledProcessError as e:
        logger.error(f'Error occurred during conversion: {e}')
    except Exception as e:
        logger.error(f'An unknown error occurred: {e}')


def generate_subtitles(record_name: str, ass_filename: str, sub_format: str = 'srt') -> None:
    index_time = 0
    today = datetime.datetime.now()
    re_datatime = today.strftime('%Y-%m-%d %H:%M:%S')

    def transform_int_to_time(seconds: int) -> str:
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    while True:
        index_time += 1
        txt = str(index_time) + "\n" + transform_int_to_time(index_time) + ',000 --> ' + transform_int_to_time(
            index_time + 1) + ',000' + "\n" + str(re_datatime) + "\n\n"

        with open(f"{ass_filename}.{sub_format.lower()}", 'a', encoding=text_encoding) as f:
            f.write(txt)

        if record_name not in recording:
            return
        time.sleep(1)
        today = datetime.datetime.now()
        re_datatime = today.strftime('%Y-%m-%d %H:%M:%S')


def adjust_max_request() -> None:
    global max_request, error_count, pre_max_request, error_window
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
                print(f"\r同一时间访问网络的线程数动态改为 {max_request}")

        error_window.append(error_count)
        if len(error_window) > error_window_size:
            error_window.pop(0)
        error_count = 0


def push_message(record_name: str, live_url: str, content: str) -> None:
    msg_title = push_message_title.strip() or "直播间状态更新通知"
    push_functions = {
        '微信': lambda: xizhi(xizhi_api_url, msg_title, content),
        '钉钉': lambda: dingtalk(dingtalk_api_url, content, dingtalk_phone_num, dingtalk_is_atall),
        '邮箱': lambda: send_email(
            email_host, login_email, email_password, sender_email, sender_name,
            to_email, msg_title, content, smtp_port, open_smtp_ssl
        ),
        'TG': lambda: tg_bot(tg_chat_id, tg_token, content),
        'BARK': lambda: bark(
            bark_msg_api, title=msg_title, content=content, level=bark_msg_level, sound=bark_msg_ring
        ),
        'NTFY': lambda: ntfy(
            ntfy_api, title=msg_title, content=content, tags=ntfy_tags, action_url=live_url, email=ntfy_email
        ),
        'PUSHPLUS': lambda: pushplus(pushplus_token, msg_title, content),
    }

    for platform, func in push_functions.items():
        if platform in live_status_push.upper():
            try:
                result = func()
                print(f'提示信息：已经将[{record_name}]直播状态消息推送至你的{platform},'
                      f' 成功{len(result["success"])}, 失败{len(result["error"])}')
            except Exception as e:
                color_obj.print_colored(f"直播消息推送到{platform}失败: {e}", color_obj.RED)


def run_script(command: str) -> None:
    try:
        process = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=get_startup_info(os_type)
        )
        stdout, stderr = process.communicate()
        stdout_decoded = stdout.decode('utf-8')
        stderr_decoded = stderr.decode('utf-8')
        if stdout_decoded.strip():
            print(stdout_decoded)
        if stderr_decoded.strip():
            print(stderr_decoded)
    except PermissionError as e:
        logger.error(e)
        logger.error('脚本无执行权限!, 若是Linux环境, 请先执行:chmod +x your_script.sh 授予脚本可执行权限')
    except OSError as e:
        logger.error(e)
        logger.error('Please add `#!/bin/bash` at the beginning of your bash script file.')


def clear_record_info(record_name: str, record_url: str) -> None:
    global monitoring
    recording.discard(record_name)
    if record_url in url_comments and record_url in running_list:
        running_list.remove(record_url)
        monitoring -= 1
        color_obj.print_colored(f"[{record_name}]已经从录制列表中移除\n", color_obj.YELLOW)


def direct_download_stream(source_url: str, save_path: str, record_name: str, live_url: str, platform: str) -> bool:
    try:
        with open(save_path, 'wb') as f:
            client = httpx.Client(timeout=None)

            headers = {}
            header_params = get_record_headers(platform, live_url)
            if header_params:
                key, value = header_params.split(":", 1)
                headers[key] = value

            with client.stream('GET', source_url, headers=headers, follow_redirects=True) as response:
                if response.status_code != 200:
                    logger.error(f"请求直播流失败，状态码: {response.status_code}")
                    return False

                downloaded = 0
                chunk_size = 1024 * 16

                for chunk in response.iter_bytes(chunk_size):
                    if live_url in url_comments or exit_recording:
                        color_obj.print_colored(f"[{record_name}]录制时已被注释或请求停止,下载中断", color_obj.YELLOW)
                        clear_record_info(record_name, live_url)
                        return False

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                print()
                return True
    except Exception as e:
        logger.error(f"FLV下载错误: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
        return False


def check_subprocess(record_name: str, record_url: str, ffmpeg_command: list, save_type: str,
                     script_command: str | None = None) -> bool:
    save_file_path = ffmpeg_command[-1]

    # 抖音弹幕抓取：与 ffmpeg 录制并行，录制结束时一起收尾
    danmaku_key = None
    if danmaku_enabled and 'douyin.com' in record_url:
        danmaku_room_id = danmaku_room_ids.get(record_url)
        if danmaku_room_id:
            danmaku_key = save_file_path
            threading.Thread(
                target=danmaku.start_danmaku,
                kwargs={
                    'room_id': danmaku_room_id,
                    'save_file_path': save_file_path,
                    'anchor_name': record_name.split(' ', maxsplit=1)[-1],
                    'cookie': dy_cookie,
                    'formats': danmaku_formats.split(','),
                    'sync_start': datetime.datetime.now(),
                    'subtitle_max_lines': danmaku_max_lines,
                    'subtitle_duration': danmaku_duration,
                    'subtitle_mode': danmaku_mode,
                    'subtitle_types': danmaku_types,
                    'gift_min_diamond': danmaku_gift_min_diamond,
                    'subtitle_font_size': danmaku_font_size,
                },
                name=f'danmaku_start_{record_name}',
                daemon=True,
            ).start()

    process = subprocess.Popen(
        ffmpeg_command, stdin=subprocess.PIPE, stderr=subprocess.STDOUT, startupinfo=get_startup_info(os_type)
    )

    subs_file_path = save_file_path.rsplit('.', maxsplit=1)[0]
    subs_thread_name = f'subs_{Path(subs_file_path).name}'
    if create_time_file and not split_video_by_time and '音频' not in save_type:
        create_var[subs_thread_name] = threading.Thread(
            target=generate_subtitles, args=(record_name, subs_file_path)
        )
        create_var[subs_thread_name].daemon = True
        create_var[subs_thread_name].start()

    while process.poll() is None:
        if record_url in url_comments or exit_recording:
            color_obj.print_colored(f"[{record_name}]录制时已被注释,本条线程将会退出", color_obj.YELLOW)
            clear_record_info(record_name, record_url)
            # process.terminate()
            if os.name == 'nt':
                if process.stdin:
                    process.stdin.write(b'q')
                    process.stdin.close()
            else:
                process.send_signal(signal.SIGINT)
            process.wait()
            if danmaku_key:
                danmaku.stop_danmaku(danmaku_key)
            return True
        time.sleep(1)

    return_code = process.returncode
    stop_time = time.strftime('%Y-%m-%d %H:%M:%S')

    # 弹幕必须先收尾：ASS 字幕是连接关闭时才落盘的，晚于它的话转码/烧录拿不到文件
    ass_path = None
    if danmaku_key:
        danmaku.stop_danmaku(danmaku_key)
        if 'ass' in [f.strip().lower() for f in danmaku_formats.split(',')]:
            ass_path = danmaku.clean_base_path(save_file_path) + '.danmaku.ass'

    want_burn = bool(danmaku_burn and ass_path and '音频' not in save_type)

    if return_code == 0:
        if converts_to_mp4 and save_type == 'TS':
            if split_video_by_time:
                if want_burn and ass_path and os.path.exists(ass_path):
                    # 分段也能烧：ASS 只有一份且按整场计时，这里为每段单独裁一份再烧，
                    # 因此必须串行处理（每段的偏移取决于前面各段的实际时长）
                    logger.info('开启分段录制，将逐段把弹幕烧进画面（每段一次重编码，耗时较长）')
                    threading.Thread(
                        target=post_process_segments,
                        args=(save_file_path, delete_origin_file, ass_path),
                    ).start()
                else:
                    if want_burn:
                        logger.warning(f'没有拿到弹幕 ASS（{ass_path}），本次只做转码，不烧录字幕')
                    file_paths = utils.get_file_paths(os.path.dirname(save_file_path))
                    prefix = os.path.basename(save_file_path).rsplit('_', maxsplit=1)[0]
                    for path in file_paths:
                        if prefix in path:
                            threading.Thread(target=converts_mp4, args=(path, delete_origin_file)).start()
            else:
                threading.Thread(
                    target=post_process_video,
                    args=(save_file_path, delete_origin_file, ass_path if want_burn else None),
                ).start()
        elif want_burn and split_video_by_time:
            # 直接存 mp4/flv/mkv 又开了分段：片段本身就是成品，不用转码，直接逐段烧
            logger.info('开启分段录制（无转码模式），将逐段把弹幕烧进画面（每段一次重编码，耗时较长）')
            threading.Thread(
                target=post_process_segments,
                args=(save_file_path, False, ass_path, False),
            ).start()
        elif want_burn and not split_video_by_time:
            # 未开启转码（直接存 mp4/flv 等）时，烧录直接作用于录制产物
            threading.Thread(target=burn_danmaku_into_video, args=(save_file_path, ass_path)).start()
        print(f"\n{record_name} {stop_time} 直播录制完成\n")

        if script_command:
            logger.debug("开始执行脚本命令!")
            if "python" in script_command:
                params = [
                    f'--record_name "{record_name}"',
                    f'--save_file_path "{save_file_path}"',
                    f'--save_type {save_type}',
                    f'--split_video_by_time {split_video_by_time}',
                    f'--converts_to_mp4 {converts_to_mp4}',
                ]
            else:
                params = [
                    f'"{record_name.split(" ", maxsplit=1)[-1]}"',
                    f'"{save_file_path}"',
                    save_type,
                    f'split_video_by_time:{split_video_by_time}',
                    f'converts_to_mp4:{converts_to_mp4}'
                ]
            script_command = script_command.strip() + ' ' + ' '.join(params)
            run_script(script_command)
            logger.debug("脚本命令执行结束!")

    else:
        color_obj.print_colored(f"\n{record_name} {stop_time} 直播录制出错,返回码: {return_code}\n", color_obj.RED)

    recording.discard(record_name)
    return False


def clean_name(input_text):
    cleaned_name = re.sub(rstr, "_", input_text.strip()).strip('_')
    cleaned_name = cleaned_name.replace("（", "(").replace("）", ")")
    if clean_emoji:
        cleaned_name = utils.remove_emojis(cleaned_name, '_').strip('_')
    return cleaned_name or '空白昵称'


def get_quality_code(qn):
    QUALITY_MAPPING = {
        "原画": "OD",
        "蓝光": "BD",
        "超清": "UHD",
        "高清": "HD",
        "标清": "SD",
        "流畅": "LD"
    }
    return QUALITY_MAPPING.get(qn)


def get_record_headers(platform, live_url):
    live_domain = '/'.join(live_url.split('/')[0:3])
    record_headers = {
        'PandaTV': 'origin:https://www.pandalive.co.kr',
        'WinkTV': 'origin:https://www.winktv.co.kr',
        'PopkonTV': 'origin:https://www.popkontv.com',
        'FlexTV': 'origin:https://www.flextv.co.kr',
        '千度热播': 'referer:https://qiandurebo.com',
        '17Live': 'referer:https://17.live/en/live/6302408',
        '浪Live': 'referer:https://www.lang.live',
        'shopee': f'origin:{live_domain}',
        'Blued直播': 'referer:https://app.blued.cn'
    }
    return record_headers.get(platform)


def is_flv_preferred_platform(link):
    return any(i in link for i in ["douyin", "tiktok"])


def select_source_url(link, stream_info):
    if is_flv_preferred_platform(link):
        codec = utils.get_query_params(stream_info.get('flv_url'), "codec")
        if codec and codec[0] == 'h265':
            logger.warning("FLV is not supported for h265 codec, use HLS source instead")
        else:
            return stream_info.get('flv_url')

    return stream_info.get('record_url')


def start_record(url_data: tuple, count_variable: int = -1) -> None:
    global error_count

    while True:
        try:
            record_finished = False
            run_once = False
            start_pushed = False
            new_record_url = ''
            count_time = time.time()
            retry = 0
            record_quality_zh, record_url, anchor_name = url_data
            record_quality = get_quality_code(record_quality_zh)
            proxy_address = proxy_addr
            platform = '未知平台'
            live_domain = '/'.join(record_url.split('/')[0:3])

            if proxy_addr:
                proxy_address = None
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
                    port_info = []
                    if record_url.find("douyin.com/") > -1:
                        platform = '抖音直播'
                        with semaphore:
                            if 'v.douyin.com' not in record_url and '/user/' not in record_url:
                                json_data = asyncio.run(spider.get_douyin_web_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=dy_cookie))
                            else:
                                json_data = asyncio.run(spider.get_douyin_app_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=dy_cookie))
                            if danmaku_enabled:
                                # 弹幕 WebSocket 需要真实 room_id，能拿到就抓，拿不到该场自动跳过弹幕
                                try:
                                    _rid = (json_data.get('id_str') or json_data.get('room_id')
                                            or json_data.get('web_rid') or '')
                                    if _rid:
                                        danmaku_room_ids[record_url] = str(_rid)
                                    else:
                                        logger.warning(
                                            f'没有取到直播间 room_id，本场不抓取弹幕: {record_url}')
                                except Exception:
                                    pass

                            port_info = asyncio.run(
                                stream.get_douyin_stream_url(json_data, record_quality, proxy_address))

                    elif record_url.find("https://www.tiktok.com/") > -1:
                        platform = 'TikTok直播'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_tiktok_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=tiktok_cookie))
                                port_info = asyncio.run(
                                    stream.get_tiktok_stream_url(json_data, record_quality, proxy_address))
                            else:
                                logger.error("错误信息: 网络异常，请检查网络是否能正常访问TikTok平台")

                    elif record_url.find("https://live.kuaishou.com/") > -1:
                        platform = '快手直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_kuaishou_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=ks_cookie))
                            port_info = asyncio.run(stream.get_kuaishou_stream_url(json_data, record_quality))

                    elif record_url.find("https://www.huya.com/") > -1:
                        platform = '虎牙直播'
                        with semaphore:
                            if record_quality not in ['OD', 'BD', 'UHD']:
                                json_data = asyncio.run(spider.get_huya_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=hy_cookie))
                                port_info = asyncio.run(stream.get_huya_stream_url(json_data, record_quality))
                            else:
                                port_info = asyncio.run(spider.get_huya_app_stream_url(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=hy_cookie
                                ))

                    elif record_url.find("https://www.douyu.com/") > -1:
                        platform = '斗鱼直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_douyu_info_data(
                                url=record_url, proxy_addr=proxy_address, cookies=douyu_cookie))
                            port_info = asyncio.run(stream.get_douyu_stream_url(
                                json_data, video_quality=record_quality, cookies=douyu_cookie, proxy_addr=proxy_address
                            ))

                    elif record_url.find("https://www.yy.com/") > -1:
                        platform = 'YY直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_yy_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=yy_cookie))
                            port_info = asyncio.run(stream.get_yy_stream_url(json_data))

                    elif record_url.find("https://live.bilibili.com/") > -1:
                        platform = 'B站直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_bilibili_room_info(
                                url=record_url, proxy_addr=proxy_address, cookies=bili_cookie))
                            port_info = asyncio.run(stream.get_bilibili_stream_url(
                                json_data, video_quality=record_quality, cookies=bili_cookie, proxy_addr=proxy_address))

                    elif record_url.find("http://xhslink.com/") > -1 or \
                            record_url.find("https://www.xiaohongshu.com/") > -1:
                        platform = '小红书直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_xhs_stream_url(
                                record_url, proxy_addr=proxy_address, cookies=xhs_cookie))
                            retry += 1

                    elif record_url.find("www.bigo.tv/") > -1 or record_url.find("slink.bigovideo.tv/") > -1:
                        platform = 'Bigo直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_bigo_stream_url(
                                record_url, proxy_addr=proxy_address, cookies=bigo_cookie))

                    elif record_url.find("https://app.blued.cn/") > -1:
                        platform = 'Blued直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_blued_stream_url(
                                record_url, proxy_addr=proxy_address, cookies=blued_cookie))

                    elif record_url.find("sooplive.co.kr/") > -1 or record_url.find("sooplive.com/") > -1:
                        platform = 'SOOP'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_sooplive_stream_data(
                                    url=record_url, proxy_addr=proxy_address,
                                    cookies=sooplive_cookie,
                                    username=sooplive_username,
                                    password=sooplive_password
                                ))
                                if json_data and json_data.get('new_cookies'):
                                    utils.update_config(
                                        config_file, 'Cookie', 'sooplive_cookie', json_data['new_cookies']
                                    )
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问SOOP平台")

                    elif record_url.find("cc.163.com/") > -1:
                        platform = '网易CC直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_netease_stream_data(
                                url=record_url, cookies=netease_cookie))
                            port_info = asyncio.run(stream.get_netease_stream_url(json_data, record_quality))

                    elif record_url.find("qiandurebo.com/") > -1:
                        platform = '千度热播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_qiandurebo_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=qiandurebo_cookie))

                    elif record_url.find("www.pandalive.co.kr/") > -1:
                        platform = 'PandaTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_pandatv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=pandatv_cookie
                                ))
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PandaTV直播平台")

                    elif record_url.find("fm.missevan.com/") > -1:
                        platform = '猫耳FM直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_maoerfm_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=maoerfm_cookie))

                    elif record_url.find("www.winktv.co.kr/") > -1:
                        platform = 'WinkTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_winktv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=winktv_cookie))
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问WinkTV直播平台")

                    elif record_url.find("www.flextv.co.kr/") > -1 or record_url.find("www.ttinglive.com/") > -1:
                        platform = 'FlexTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_flextv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=flextv_cookie,
                                    username=flextv_username,
                                    password=flextv_password
                                ))
                                if json_data and json_data.get('new_cookies'):
                                    utils.update_config(
                                        config_file, 'Cookie', 'flextv_cookie', json_data['new_cookies']
                                    )
                                if 'play_url_list' in json_data:
                                    port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                                else:
                                    port_info = json_data
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问FlexTV直播平台")

                    elif record_url.find("look.163.com/") > -1:
                        platform = 'Look直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_looklive_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=look_cookie
                            ))

                    elif record_url.find("www.popkontv.com/") > -1:
                        platform = 'PopkonTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                port_info = asyncio.run(spider.get_popkontv_stream_url(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    access_token=popkontv_access_token,
                                    username=popkontv_username,
                                    password=popkontv_password,
                                    partner_code=popkontv_partner_code
                                ))
                                if port_info and port_info.get('new_token'):
                                    utils.update_config(
                                        file_path=config_file, section='Authorization', key='popkontv_token',
                                        new_value=port_info['new_token']
                                    )

                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问PopkonTV直播平台")

                    elif record_url.find("twitcasting.tv/") > -1:
                        platform = 'TwitCasting'
                        with semaphore:
                            json_data = asyncio.run(spider.get_twitcasting_stream_url(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=twitcasting_cookie,
                                account_type=twitcasting_account_type,
                                username=twitcasting_username,
                                password=twitcasting_password
                            ))
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=False))

                            if port_info and port_info.get('new_cookies'):
                                utils.update_config(
                                    file_path=config_file, section='Cookie', key='twitcasting_cookie',
                                    new_value=port_info['new_cookies']
                                )

                    elif record_url.find("live.baidu.com/") > -1:
                        platform = '百度直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_baidu_stream_data(
                                url=record_url,
                                proxy_addr=proxy_address,
                                cookies=baidu_cookie))
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality))

                    elif record_url.find("weibo.com/") > -1:
                        platform = '微博直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_weibo_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=weibo_cookie))
                            port_info = asyncio.run(stream.get_stream_url(
                                json_data, record_quality, hls_extra_key='m3u8_url'))

                    elif record_url.find("kugou.com/") > -1:
                        platform = '酷狗直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_kugou_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=kugou_cookie))

                    elif record_url.find("www.twitch.tv/") > -1:
                        platform = 'TwitchTV'
                        with semaphore:
                            if global_proxy or proxy_address:
                                json_data = asyncio.run(spider.get_twitchtv_stream_data(
                                    url=record_url,
                                    proxy_addr=proxy_address,
                                    cookies=twitch_cookie
                                ))
                                port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问TwitchTV直播平台")

                    elif record_url.find("www.liveme.com/") > -1:
                        if global_proxy or proxy_address:
                            platform = 'LiveMe'
                            with semaphore:
                                port_info = asyncio.run(spider.get_liveme_stream_url(
                                    url=record_url, proxy_addr=proxy_address, cookies=liveme_cookie))
                        else:
                            logger.error("错误信息: 网络异常，请检查本网络是否能正常访问LiveMe直播平台")

                    elif record_url.find("www.huajiao.com/") > -1:
                        platform = '花椒直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_huajiao_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=huajiao_cookie))

                    elif record_url.find("7u66.com/") > -1:
                        platform = '流星直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_liuxing_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=liuxing_cookie))

                    elif record_url.find("showroom-live.com/") > -1:
                        platform = 'ShowRoom'
                        with semaphore:
                            json_data = asyncio.run(spider.get_showroom_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=showroom_cookie))
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("live.acfun.cn/") > -1 or record_url.find("m.acfun.cn/") > -1:
                        platform = 'Acfun'
                        with semaphore:
                            json_data = asyncio.run(spider.get_acfun_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=acfun_cookie))
                            port_info = asyncio.run(stream.get_stream_url(
                                json_data, record_quality, url_type='flv', flv_extra_key='url'))

                    elif record_url.find("live.tlclw.com/") > -1:
                        platform = '畅聊直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_changliao_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=changliao_cookie))

                    elif record_url.find("ybw1666.com/") > -1:
                        platform = '音播直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_yinbo_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=yinbo_cookie))

                    elif record_url.find("www.inke.cn/") > -1:
                        platform = '映客直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_yingke_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=yingke_cookie))

                    elif record_url.find("www.zhihu.com/") > -1:
                        platform = '知乎直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_zhihu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=zhihu_cookie))

                    elif record_url.find("chzzk.naver.com/") > -1:
                        platform = 'CHZZK'
                        with semaphore:
                            json_data = asyncio.run(spider.get_chzzk_stream_data(
                                url=record_url, proxy_addr=proxy_address, cookies=chzzk_cookie))
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("www.haixiutv.com/") > -1:
                        platform = '嗨秀直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_haixiu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=haixiu_cookie))

                    elif record_url.find("vvxqiu.com/") > -1:
                        platform = 'VV星球'
                        with semaphore:
                            port_info = asyncio.run(spider.get_vvxqiu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=vvxqiu_cookie))

                    elif record_url.find("17.live/") > -1:
                        platform = '17Live'
                        with semaphore:
                            port_info = asyncio.run(spider.get_17live_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=yiqilive_cookie))

                    elif record_url.find("www.lang.live/") > -1:
                        platform = '浪Live'
                        with semaphore:
                            port_info = asyncio.run(spider.get_langlive_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=langlive_cookie))

                    elif record_url.find("m.pp.weimipopo.com/") > -1:
                        platform = '漂漂直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_pplive_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=pplive_cookie))

                    elif record_url.find(".6.cn/") > -1:
                        platform = '六间房直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_6room_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=six_room_cookie))

                    elif record_url.find("lehaitv.com/") > -1:
                        platform = '乐嗨直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_haixiu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=lehaitv_cookie))

                    elif record_url.find("h.catshow168.com/") > -1:
                        platform = '花猫直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_pplive_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=huamao_cookie))

                    elif record_url.find("live.shopee") > -1 or record_url.find("shp.ee/") > -1:
                        platform = 'shopee'
                        with semaphore:
                            port_info = asyncio.run(spider.get_shopee_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=shopee_cookie))
                            if port_info.get('uid'):
                                new_record_url = record_url.split('?')[0] + '?' + str(port_info['uid'])

                    elif record_url.find("www.youtube.com/") > -1 or record_url.find("youtu.be/") > -1:
                        platform = 'Youtube'
                        with semaphore:
                            json_data = asyncio.run(spider.get_youtube_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=youtube_cookie))
                            port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))

                    elif record_url.find("tb.cn") > -1:
                        platform = '淘宝直播'
                        with semaphore:
                            json_data = asyncio.run(spider.get_taobao_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=taobao_cookie))
                            port_info = asyncio.run(stream.get_stream_url(
                                json_data, record_quality,
                                url_type='all', hls_extra_key='hlsUrl', flv_extra_key='flvUrl'
                            ))

                    elif record_url.find("3.cn") > -1 or record_url.find("m.jd.com") > -1:
                        platform = '京东直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_jd_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=jd_cookie))

                    elif record_url.find("faceit.com/") > -1:
                        platform = 'faceit'
                        with semaphore:
                            if global_proxy or proxy_address:
                                with semaphore:
                                    json_data = asyncio.run(spider.get_faceit_stream_data(
                                        url=record_url, proxy_addr=proxy_address, cookies=faceit_cookie))
                                    port_info = asyncio.run(stream.get_stream_url(json_data, record_quality, spec=True))
                            else:
                                logger.error("错误信息: 网络异常，请检查本网络是否能正常访问faceit直播平台")

                    elif record_url.find("www.miguvideo.com") > -1 or record_url.find("m.miguvideo.com") > -1:
                        platform = '咪咕直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_migu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=migu_cookie))

                    elif record_url.find("show.lailianjie.com") > -1:
                        platform = '连接直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_lianjie_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=lianjie_cookie))

                    elif record_url.find("www.imkktv.com") > -1:
                        platform = '来秀直播'
                        with semaphore:
                            port_info = asyncio.run(spider.get_laixiu_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=laixiu_cookie))

                    elif record_url.find("www.picarto.tv") > -1:
                        platform = 'Picarto'
                        with semaphore:
                            port_info = asyncio.run(spider.get_picarto_stream_url(
                                url=record_url, proxy_addr=proxy_address, cookies=picarto_cookie))

                    elif record_url.find(".m3u8") > -1 or record_url.find(".flv") > -1:
                        platform = '自定义录制直播'
                        port_info = {
                            "anchor_name": platform + '_' + str(uuid.uuid4())[:8],
                            "is_live": True,
                            "record_url": record_url,
                        }
                        if '.flv' in record_url:
                            port_info['flv_url'] = record_url
                        else:
                            port_info['m3u8_url'] = record_url

                    else:
                        logger.error(f'{record_url} {platform}直播地址')
                        return

                    if anchor_name:
                        if '主播:' in anchor_name:
                            anchor_split: list = anchor_name.split('主播:')
                            if len(anchor_split) > 1 and anchor_split[1].strip():
                                anchor_name = anchor_split[1].strip()
                            else:
                                anchor_name = port_info.get("anchor_name", '')
                    else:
                        anchor_name = port_info.get("anchor_name", '')

                    if not port_info.get("anchor_name", ''):
                        print(f'序号{count_variable} 网址内容获取失败,进行重试中...获取失败的地址是:{url_data}')
                        with max_request_lock:
                            error_count += 1
                            error_window.append(1)
                    else:
                        anchor_name = clean_name(anchor_name)
                        record_name = f'序号{count_variable} {anchor_name}'

                        if record_url in url_comments:
                            print(f"[{anchor_name}]已被注释,本条线程将会退出")
                            clear_record_info(record_name, record_url)
                            return

                        if not url_data[-1] and run_once is False:
                            if new_record_url:
                                need_update_line_list.append(
                                    f'{record_url}|{new_record_url},主播: {anchor_name.strip()}')
                                not_record_list.append(new_record_url)
                            else:
                                need_update_line_list.append(f'{record_url}|{record_url},主播: {anchor_name.strip()}')
                            run_once = True

                        push_at = datetime.datetime.today().strftime('%Y-%m-%d %H:%M:%S')
                        if port_info['is_live'] is False:
                            print(f"\r{record_name} 等待直播... ")

                            if start_pushed:
                                if over_show_push:
                                    push_content = "直播间状态更新：[直播间名称] 直播已结束！时间：[时间]"
                                    if over_push_message_text:
                                        push_content = over_push_message_text

                                    push_content = (push_content.replace('[直播间名称]', record_name).
                                                    replace('[时间]', push_at))
                                    threading.Thread(
                                        target=push_message,
                                        args=(record_name, record_url, push_content.replace(r'\n', '\n')),
                                        daemon=True
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

                                    push_content = (push_content.replace('[直播间名称]', record_name).
                                                    replace('[时间]', push_at))
                                    threading.Thread(
                                        target=push_message,
                                        args=(record_name, record_url, push_content.replace(r'\n', '\n')),
                                        daemon=True
                                    ).start()
                                start_pushed = True

                            if disable_record:
                                time.sleep(push_check_seconds)
                                continue

                            real_url = select_source_url(record_url, port_info)
                            full_path = f'{default_path}/{platform}'
                            if real_url:
                                now = datetime.datetime.today().strftime("%Y-%m-%d_%H-%M-%S")
                                live_title = port_info.get('title')
                                title_in_name = ''
                                if live_title:
                                    live_title = clean_name(live_title)
                                    title_in_name = live_title + '_' if filename_by_title else ''

                                try:
                                    if len(video_save_path) > 0:
                                        if not video_save_path.endswith(('/', '\\')):
                                            full_path = f'{video_save_path}/{platform}'
                                        else:
                                            full_path = f'{video_save_path}{platform}'

                                    full_path = full_path.replace("\\", '/')
                                    if folder_by_author:
                                        full_path = f'{full_path}/{anchor_name}'
                                    if folder_by_time:
                                        full_path = f'{full_path}/{now[:10]}'
                                    if folder_by_title and port_info.get('title'):
                                        if folder_by_time:
                                            full_path = f'{full_path}/{live_title}_{anchor_name}'
                                        else:
                                            full_path = f'{full_path}/{now[:10]}_{live_title}'
                                    if not os.path.exists(full_path):
                                        os.makedirs(full_path)
                                except Exception as e:
                                    logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")

                                if platform != '自定义录制直播':
                                    if enable_https_recording and real_url.startswith("http://"):
                                        real_url = real_url.replace("http://", "https://")

                                    http_record_list = ['shopee', "migu"]
                                    if platform in http_record_list:
                                        real_url = real_url.replace("https://", "http://")

                                user_agent = ("Mozilla/5.0 (Linux; Android 11; SAMSUNG SM-G973U) AppleWebKit/537.36 ("
                                              "KHTML, like Gecko) SamsungBrowser/14.2 Chrome/87.0.4280.141 Mobile "
                                              "Safari/537.36")

                                rw_timeout = "15000000"
                                analyzeduration = "20000000"
                                probesize = "10000000"
                                bufsize = "8000k"
                                max_muxing_queue_size = "1024"
                                for pt_host in overseas_platform_host:
                                    if pt_host in record_url:
                                        rw_timeout = "50000000"
                                        analyzeduration = "40000000"
                                        probesize = "20000000"
                                        bufsize = "15000k"
                                        max_muxing_queue_size = "2048"
                                        break

                                ffmpeg_command = [
                                    'ffmpeg', "-y",
                                    "-v", "verbose",
                                    "-rw_timeout", rw_timeout,
                                    "-loglevel", "error",
                                    "-hide_banner",
                                    "-user_agent", user_agent,
                                    "-protocol_whitelist", "rtmp,crypto,file,http,https,tcp,tls,udp,rtp,httpproxy",
                                    "-thread_queue_size", "1024",
                                    "-analyzeduration", analyzeduration,
                                    "-probesize", probesize,
                                    "-fflags", "+discardcorrupt",
                                    "-re", "-i", real_url,
                                    "-bufsize", bufsize,
                                    "-sn", "-dn",
                                    "-reconnect_delay_max", "60",
                                    "-reconnect_streamed", "-reconnect_at_eof",
                                    "-max_muxing_queue_size", max_muxing_queue_size,
                                    "-correct_ts_overflow", "1",
                                    "-avoid_negative_ts", "1"
                                ]

                                headers = get_record_headers(platform, record_url)
                                if headers:
                                    ffmpeg_command.insert(11, "-headers")
                                    ffmpeg_command.insert(12, headers)

                                if proxy_address:
                                    ffmpeg_command.insert(1, "-http_proxy")
                                    ffmpeg_command.insert(2, proxy_address)

                                recording.add(record_name)
                                start_record_time = datetime.datetime.now()
                                recording_time_list[record_name] = [start_record_time, record_quality_zh]
                                rec_info = f"\r{anchor_name} 准备开始录制视频: {full_path}"
                                if show_url:
                                    re_plat = ('WinkTV', 'PandaTV', 'ShowRoom', 'CHZZK', 'Youtube')
                                    if platform in re_plat:
                                        logger.info(
                                            f"{platform} | {anchor_name} | 直播源地址: {port_info.get('m3u8_url')}")
                                    else:
                                        logger.info(
                                            f"{platform} | {anchor_name} | 直播源地址: {real_url}")

                                only_flv_record = False
                                only_flv_platform_list = ['shopee', '花椒直播']
                                if platform in only_flv_platform_list:
                                    logger.debug(f"提示: {platform} 将强制使用FLV格式录制")
                                    only_flv_record = True

                                only_audio_record = False
                                only_audio_platform_list = ['猫耳FM直播', 'Look直播']
                                if platform in only_audio_platform_list:
                                    only_audio_record = True

                                record_save_type = video_save_type

                                if is_flv_preferred_platform(record_url) and port_info.get('flv_url'):
                                    codec = utils.get_query_params(port_info['flv_url'], "codec")
                                    if codec and codec[0] == 'h265':
                                        logger.warning("FLV is not supported for h265 codec, use TS format instead")
                                        record_save_type = "TS"

                                if only_audio_record or any(i in record_save_type for i in ['MP3', 'M4A']):
                                    try:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        extension = "mp3" if "m4a" not in record_save_type.lower() else "m4a"
                                        name_format = "_%03d" if split_video_by_time else ""
                                        save_file_path = (f"{full_path}/{anchor_name}_{title_in_name}{now}"
                                                          f"{name_format}.{extension}")

                                        if split_video_by_time:
                                            print(f'\r{anchor_name} 准备开始录制音频: {save_file_path}')

                                            if "MP3" in record_save_type:
                                                command = [
                                                    "-map", "0:a",
                                                    "-c:a", "libmp3lame",
                                                    "-ab", "320k",
                                                    "-f", "segment",
                                                    "-segment_time", split_time,
                                                    "-reset_timestamps", "1",
                                                    save_file_path,
                                                ]
                                            else:
                                                command = [
                                                    "-map", "0:a",
                                                    "-c:a", "aac",
                                                    "-bsf:a", "aac_adtstoasc",
                                                    "-ab", "320k",
                                                    "-f", "segment",
                                                    "-segment_time", split_time,
                                                    "-segment_format", 'mpegts',
                                                    "-reset_timestamps", "1",
                                                    save_file_path,
                                                ]

                                        else:
                                            if "MP3" in record_save_type:
                                                command = [
                                                    "-map", "0:a",
                                                    "-c:a", "libmp3lame",
                                                    "-ab", "320k",
                                                    save_file_path,
                                                ]

                                            else:
                                                command = [
                                                    "-map", "0:a",
                                                    "-c:a", "aac",
                                                    "-bsf:a", "aac_adtstoasc",
                                                    "-ab", "320k",
                                                    "-movflags", "+faststart",
                                                    save_file_path,
                                                ]

                                        ffmpeg_command.extend(command)
                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        with max_request_lock:
                                            error_count += 1
                                            error_window.append(1)

                                if only_flv_record:
                                    logger.info(f"Use Direct Downloader to Download FLV Stream: {record_url}")
                                    filename = anchor_name + f'_{title_in_name}' + now + '.flv'
                                    save_file_path = f'{full_path}/{filename}'
                                    print(f'{rec_info}/{filename}')

                                    subs_file_path = save_file_path.rsplit('.', maxsplit=1)[0]
                                    subs_thread_name = f'subs_{Path(subs_file_path).name}'
                                    if create_time_file:
                                        create_var[subs_thread_name] = threading.Thread(
                                            target=generate_subtitles, args=(record_name, subs_file_path)
                                        )
                                        create_var[subs_thread_name].daemon = True
                                        create_var[subs_thread_name].start()

                                    try:
                                        flv_url = port_info.get('flv_url')
                                        if flv_url:
                                            recording.add(record_name)
                                            start_record_time = datetime.datetime.now()
                                            recording_time_list[record_name] = [start_record_time, record_quality_zh]

                                            download_success = direct_download_stream(
                                                flv_url, save_file_path, record_name, record_url, platform
                                            )

                                            if download_success:
                                                record_finished = True
                                                print(
                                                    f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制完成\n")

                                            recording.discard(record_name)
                                        else:
                                            logger.debug("未找到FLV直播流，跳过录制")
                                    except Exception as e:
                                        clear_record_info(record_name, record_url)
                                        color_obj.print_colored(
                                            f"\n{anchor_name} {time.strftime('%Y-%m-%d %H:%M:%S')} 直播录制出错,请检查网络\n",
                                            color_obj.RED)
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        with max_request_lock:
                                            error_count += 1
                                            error_window.append(1)

                                elif record_save_type == "FLV":
                                    filename = anchor_name + f'_{title_in_name}' + now + ".flv"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.flv"
                                            command = [
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-bsf:a", "aac_adtstoasc",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "flv",
                                                "-reset_timestamps", "1",
                                                save_file_path
                                            ]

                                        else:
                                            command = [
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-bsf:a", "aac_adtstoasc",
                                                "-f", "flv",
                                                "{path}".format(path=save_file_path),
                                            ]
                                        ffmpeg_command.extend(command)

                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        with max_request_lock:
                                            error_count += 1
                                            error_window.append(1)

                                    try:
                                        if converts_to_mp4:
                                            seg_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mp4"
                                            if split_video_by_time:
                                                segment_video(
                                                    save_file_path, seg_file_path,
                                                    segment_format='mp4', segment_time=split_time,
                                                    is_original_delete=delete_origin_file
                                                )
                                            else:
                                                threading.Thread(
                                                    target=converts_mp4,
                                                    args=(save_file_path, delete_origin_file)
                                                ).start()

                                        else:
                                            seg_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.flv"
                                            if split_video_by_time:
                                                segment_video(
                                                    save_file_path, seg_file_path,
                                                    segment_format='flv', segment_time=split_time,
                                                    is_original_delete=delete_origin_file
                                                )
                                    except Exception as e:
                                        logger.error(f"转码失败: {e} ")

                                elif record_save_type == "MKV":
                                    filename = anchor_name + f'_{title_in_name}' + now + ".mkv"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mkv"
                                            command = [
                                                "-flags", "global_header",
                                                "-c:v", "copy",
                                                "-c:a", "aac",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "matroska",
                                                "-reset_timestamps", "1",
                                                save_file_path,
                                            ]

                                        else:
                                            command = [
                                                "-flags", "global_header",
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-f", "matroska",
                                                "{path}".format(path=save_file_path),
                                            ]
                                        ffmpeg_command.extend(command)

                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        with max_request_lock:
                                            error_count += 1
                                            error_window.append(1)

                                elif record_save_type == "MP4":
                                    filename = anchor_name + f'_{title_in_name}' + now + ".mp4"
                                    print(f'{rec_info}/{filename}')
                                    save_file_path = full_path + '/' + filename

                                    try:
                                        if split_video_by_time:
                                            now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                            save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.mp4"
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "aac",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", "mp4",
                                                "-reset_timestamps", "1",
                                                "-movflags", "+frag_keyframe+empty_moov",
                                                save_file_path,
                                            ]

                                        else:
                                            command = [
                                                "-map", "0",
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-f", "mp4",
                                                save_file_path,
                                            ]

                                        ffmpeg_command.extend(command)
                                        comment_end = check_subprocess(
                                            record_name,
                                            record_url,
                                            ffmpeg_command,
                                            record_save_type,
                                            custom_script
                                        )
                                        if comment_end:
                                            return

                                    except subprocess.CalledProcessError as e:
                                        logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                        with max_request_lock:
                                            error_count += 1
                                            error_window.append(1)

                                else:
                                    if split_video_by_time:
                                        now = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                                        filename = anchor_name + f'_{title_in_name}' + now + ".ts"
                                        print(f'{rec_info}/{filename}')

                                        try:
                                            save_file_path = f"{full_path}/{anchor_name}_{title_in_name}{now}_%03d.ts"
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-map", "0",
                                                "-f", "segment",
                                                "-segment_time", split_time,
                                                "-segment_format", 'mpegts',
                                                "-reset_timestamps", "1",
                                                save_file_path,
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                record_url,
                                                ffmpeg_command,
                                                record_save_type,
                                                custom_script
                                            )
                                            if comment_end:
                                                if converts_to_mp4:
                                                    file_paths = utils.get_file_paths(os.path.dirname(save_file_path))
                                                    prefix = os.path.basename(save_file_path).rsplit('_', maxsplit=1)[0]
                                                    for path in file_paths:
                                                        if prefix in path:
                                                            try:
                                                                threading.Thread(
                                                                    target=converts_mp4,
                                                                    args=(path, delete_origin_file)
                                                                ).start()
                                                            except subprocess.CalledProcessError as e:
                                                                logger.error(f"转码失败: {e} ")
                                                return

                                        except subprocess.CalledProcessError as e:
                                            logger.error(
                                                f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            with max_request_lock:
                                                error_count += 1
                                                error_window.append(1)

                                    else:
                                        filename = anchor_name + f'_{title_in_name}' + now + ".ts"
                                        print(f'{rec_info}/{filename}')
                                        save_file_path = full_path + '/' + filename

                                        try:
                                            command = [
                                                "-c:v", "copy",
                                                "-c:a", "copy",
                                                "-map", "0",
                                                "-f", "mpegts",
                                                save_file_path,
                                            ]

                                            ffmpeg_command.extend(command)
                                            comment_end = check_subprocess(
                                                record_name,
                                                record_url,
                                                ffmpeg_command,
                                                record_save_type,
                                                custom_script
                                            )
                                            if comment_end:
                                                threading.Thread(
                                                    target=converts_mp4, args=(save_file_path, delete_origin_file)
                                                ).start()
                                                return

                                        except subprocess.CalledProcessError as e:
                                            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                                            with max_request_lock:
                                                error_count += 1
                                                error_window.append(1)

                                count_time = time.time()

                except Exception as e:
                    logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
                    with max_request_lock:
                        error_count += 1
                        error_window.append(1)

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
                        print(f'\r{anchor_name}循环等待{x}秒 ', end="")
                    time.sleep(1)
                if loop_time:
                    print('\r检测直播间中...', end="")
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {e.__traceback__.tb_lineno}")
            with max_request_lock:
                error_count += 1
                error_window.append(1)
            time.sleep(2)


def backup_file(file_path: str, backup_dir_path: str, limit_counts: int = 6) -> None:
    try:
        if not os.path.exists(backup_dir_path):
            os.makedirs(backup_dir_path)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file_name = os.path.basename(file_path) + '_' + timestamp
        backup_file_path = os.path.join(backup_dir_path, backup_file_name).replace("\\", "/")
        shutil.copy2(file_path, backup_file_path)

        files = os.listdir(backup_dir_path)
        _files = [f for f in files if f.startswith(os.path.basename(file_path))]
        _files.sort(key=lambda x: os.path.getmtime(os.path.join(backup_dir_path, x)))

        while len(_files) > limit_counts:
            oldest_file = _files[0]
            os.remove(os.path.join(backup_dir_path, oldest_file))
            _files = _files[1:]

    except Exception as e:
        logger.error(f'\r备份配置文件 {file_path} 失败：{str(e)}')


def backup_file_start() -> None:
    config_md5 = ''
    url_config_md5 = ''

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
    try:
        result = subprocess.run(['ffmpeg', '-version'], check=True, capture_output=True, text=True)
        if result.returncode == 0:
            lines = result.stdout.splitlines()
            version_line = lines[0]
            built_line = lines[1]
            print(version_line)
            print(built_line)
    except subprocess.CalledProcessError as e:
        logger.error(e)
    except FileNotFoundError:
        pass
    finally:
        if check_ffmpeg():
            time.sleep(1)
            return True
    return False


# --------------------------初始化程序-------------------------------------
print("-----------------------------------------------------")
print("|                DouyinLiveRecorder                 |")
print("-----------------------------------------------------")

print(f"版本号: {version}")
print("GitHub: https://github.com/ihmily/DouyinLiveRecorder")
print(f'支持平台: {platforms}')
print('.....................................................')
if not check_ffmpeg_existence():
    logger.error("缺少ffmpeg无法进行录制，程序退出")
    sys.exit(1)
os.makedirs(os.path.dirname(config_file), exist_ok=True)
t3 = threading.Thread(target=backup_file_start, args=(), daemon=True)
t3.start()
utils.remove_duplicate_lines(url_config_file)


def read_config_value(config_parser: configparser.RawConfigParser, section: str, option: str, default_value: Any) \
        -> Any:
    try:

        # 用户可能用记事本把配置存成 GBK，这里按 utf-8-sig/utf-8/gbk 依次尝试
        config_parser.read_string(utils.read_text_auto(config_file))
        if '录制设置' not in config_parser.sections():
            config_parser.add_section('录制设置')
        if '推送配置' not in config_parser.sections():
            config_parser.add_section('推送配置')
        if 'Cookie' not in config_parser.sections():
            config_parser.add_section('Cookie')
        if 'Authorization' not in config_parser.sections():
            config_parser.add_section('Authorization')
        if '账号密码' not in config_parser.sections():
            config_parser.add_section('账号密码')
        return config_parser.get(section, option)
    except (configparser.NoSectionError, configparser.NoOptionError):
        config_parser.set(section, option, str(default_value))
        with open(config_file, 'w', encoding=text_encoding) as f:
            config_parser.write(f)
        return default_value


options = {"是": True, "否": False}
config = configparser.RawConfigParser()
language = read_config_value(config, '录制设置', 'language(zh_cn/en)', "zh_cn")
skip_proxy_check = options.get(read_config_value(config, '录制设置', '是否跳过代理检测(是/否)', "否"), False)
if language and 'en' not in language.lower():
    from i18n import translated_print

    builtins.print = translated_print

try:
    if skip_proxy_check:
        global_proxy = True
    else:
        print('系统代理检测中，请耐心等待...')
        response_g = urllib.request.urlopen("https://www.google.com/", timeout=15)
        global_proxy = True
        print('\r全局/规则网络代理已开启√')
        pd = ProxyDetector()
        if pd.is_proxy_enabled():
            proxy_info = pd.get_proxy_info()
            print("System Proxy: http://{}:{}".format(proxy_info.ip, proxy_info.port))
except HTTPError as err:
    print(f"HTTP error occurred: {err.code} - {err.reason}")
except URLError:
    color_obj.print_colored("INFO：未检测到全局/规则网络代理，请检查代理配置（若无需录制海外直播请忽略此条提示）",
                            color_obj.YELLOW)
except Exception as err:
    print("An unexpected error occurred:", err)

while True:

    try:
        if not os.path.isfile(config_file):
            with open(config_file, 'w', encoding=text_encoding) as file:
                pass

        ini_URL_content = ''
        if os.path.isfile(url_config_file):
            ini_URL_content = utils.read_text_auto(url_config_file).strip()

        if not ini_URL_content.strip():
            try:
                input_url = input('请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n')
            except EOFError:
                # Docker / systemd 这类没有可交互终端的环境：input() 会直接抛 EOFError。
                # 这里不让容器退出——说清楚地址该填到哪儿，稍后重新读取，
                # 用户在宿主机上补好后无需重启容器即可继续。
                logger.error(
                    '读取直播间地址失败：当前没有可交互的终端（容器环境？）。'
                    f'请把直播间地址写入 {url_config_file}（每行一个），30 秒后自动重试。'
                )
                time.sleep(30)
                continue
            with open(url_config_file, 'w', encoding=text_encoding) as file:
                file.write(input_url)
    except OSError as err:
        logger.error(f"发生 I/O 错误: {err}")

    video_save_path = read_config_value(config, '录制设置', '直播保存路径(不填则默认)', "")
    folder_by_author = options.get(read_config_value(config, '录制设置', '保存文件夹是否以作者区分', "是"), False)
    folder_by_time = options.get(read_config_value(config, '录制设置', '保存文件夹是否以时间区分', "否"), False)
    folder_by_title = options.get(read_config_value(config, '录制设置', '保存文件夹是否以标题区分', "否"), False)
    filename_by_title = options.get(read_config_value(config, '录制设置', '保存文件名是否包含标题', "否"), False)
    clean_emoji = options.get(read_config_value(config, '录制设置', '是否去除名称中的表情符号', "是"), True)
    video_save_type = read_config_value(config, '录制设置', '视频保存格式ts|mkv|flv|mp4|mp3音频|m4a音频', "ts")
    video_record_quality = read_config_value(config, '录制设置', '原画|超清|高清|标清|流畅', "原画")
    use_proxy = options.get(read_config_value(config, '录制设置', '是否使用代理ip(是/否)', "是"), False)
    proxy_addr_bak = read_config_value(config, '录制设置', '代理地址', "")
    proxy_addr = None if not use_proxy else proxy_addr_bak
    max_request = int(read_config_value(config, '录制设置', '同一时间访问网络的线程数', 3))
    semaphore = threading.Semaphore(max_request)
    delay_default = int(read_config_value(config, '录制设置', '循环时间(秒)', 120))
    local_delay_default = int(read_config_value(config, '录制设置', '排队读取网址时间(秒)', 0))
    loop_time = options.get(read_config_value(config, '录制设置', '是否显示循环秒数', "否"), False)
    show_url = options.get(read_config_value(config, '录制设置', '是否显示直播源地址', "否"), False)
    split_video_by_time = options.get(read_config_value(config, '录制设置', '分段录制是否开启', "否"), False)
    enable_https_recording = options.get(read_config_value(config, '录制设置', '是否强制启用https录制', "否"), False)
    disk_space_limit = float(read_config_value(config, '录制设置', '录制空间剩余阈值(gb)', 1.0))
    split_time = str(read_config_value(config, '录制设置', '视频分段时间(秒)', 1800))
    converts_to_mp4 = options.get(read_config_value(config, '录制设置', '录制完成后自动转为mp4格式', "否"), False)
    converts_to_h264 = options.get(read_config_value(config, '录制设置', 'mp4格式重新编码为h264', "否"), False)
    delete_origin_file = options.get(read_config_value(config, '录制设置', '追加格式后删除原文件', "否"), False)
    create_time_file = options.get(read_config_value(config, '录制设置', '生成时间字幕文件', "否"), False)
    danmaku_enabled = options.get(read_config_value(config, '录制设置', '是否录制弹幕(是/否)', "否"), False)
    danmaku_formats = read_config_value(config, '录制设置', '弹幕保存格式(逗号分隔)', "json,srt,ass")
    danmaku_burn = options.get(
        read_config_value(config, '录制设置', '录制完成后自动将弹幕烧录到视频(是/否)', "否"), False)
    try:
        danmaku_max_lines = max(1, int(read_config_value(config, '录制设置', '弹幕最多同时显示行数', "4")))
    except (TypeError, ValueError):
        danmaku_max_lines = 4
    try:
        danmaku_duration = max(1.0, float(read_config_value(config, '录制设置', '弹幕单条显示时长(秒)', "5")))
    except (TypeError, ValueError):
        danmaku_duration = 5.0
    danmaku_types = [t.strip().lower() for t in str(read_config_value(
        config, '录制设置', '弹幕字幕包含的消息类型(逗号分隔)', "chat,gift,emoji")).replace('，', ',').split(',') if t.strip()]
    try:
        danmaku_gift_min_diamond = max(0.0, float(read_config_value(config, '录制设置', '弹幕礼物最低钻石数', "0")))
    except (TypeError, ValueError):
        danmaku_gift_min_diamond = 0.0
    danmaku_mode = '固定' if '固定' in str(read_config_value(config, '录制设置', '弹幕显示方式(滚动/固定)', "滚动")) else '滚动'
    try:
        danmaku_font_size = max(12, int(read_config_value(config, '录制设置', '弹幕字号(像素)', "40")))
    except (TypeError, ValueError):
        danmaku_font_size = 40
    danmaku_reburn = options.get(read_config_value(
        config, '录制设置', '启动时自动补烧遗漏的弹幕(是/否)', "是"), True)
    if danmaku_enabled:
        logger.info("弹幕录制已开启，当前仅支持抖音直播，若缺少依赖请执行: pip install websocket-client protobuf")
    if danmaku_enabled and danmaku_burn and danmaku_reburn:
        # 补烧扫描放后台：中断过的场次（重启容器/断电）在下次启动时自动续上
        threading.Thread(
            target=scan_and_reburn_missed, args=(video_save_path or default_path,),
            name='danmaku_reburn_scan', daemon=True,
        ).start()
    is_run_script = options.get(read_config_value(config, '录制设置', '是否录制完成后执行自定义脚本', "否"), False)
    custom_script = read_config_value(config, '录制设置', '自定义脚本执行命令', "") if is_run_script else None
    enable_proxy_platform = read_config_value(
        config, '录制设置', '使用代理录制的平台(逗号分隔)',
        'tiktok, soop, pandalive, winktv, flextv, popkontv, twitch, liveme, showroom, chzzk, shopee, shp, youtu, faceit'
    )
    enable_proxy_platform_list = enable_proxy_platform.replace('，', ',').split(',') if enable_proxy_platform else None
    extra_enable_proxy = read_config_value(config, '录制设置', '额外使用代理录制的平台(逗号分隔)', '')
    extra_enable_proxy_platform_list = extra_enable_proxy.replace('，', ',').split(',') if extra_enable_proxy else None
    live_status_push = read_config_value(config, '推送配置', '直播状态推送渠道', "")
    dingtalk_api_url = read_config_value(config, '推送配置', '钉钉推送接口链接', "")
    xizhi_api_url = read_config_value(config, '推送配置', '微信推送接口链接', "")
    bark_msg_api = read_config_value(config, '推送配置', 'bark推送接口链接', "")
    bark_msg_level = read_config_value(config, '推送配置', 'bark推送中断级别', "active")
    bark_msg_ring = read_config_value(config, '推送配置', 'bark推送铃声', "bell")
    dingtalk_phone_num = read_config_value(config, '推送配置', '钉钉通知@对象(填手机号)', "")
    dingtalk_is_atall = options.get(read_config_value(config, '推送配置', '钉钉通知@全体(是/否)', "否"), False)
    tg_token = read_config_value(config, '推送配置', 'tgapi令牌', "")
    tg_chat_id = read_config_value(config, '推送配置', 'tg聊天id(个人或者群组id)', "")
    email_host = read_config_value(config, '推送配置', 'SMTP邮件服务器', "")
    open_smtp_ssl = options.get(read_config_value(config, '推送配置', '是否使用SMTP服务SSL加密(是/否)', "是"), True)
    smtp_port = read_config_value(config, '推送配置', 'SMTP邮件服务器端口', "")
    login_email = read_config_value(config, '推送配置', '邮箱登录账号', "")
    email_password = read_config_value(config, '推送配置', '发件人密码(授权码)', "")
    sender_email = read_config_value(config, '推送配置', '发件人邮箱', "")
    sender_name = read_config_value(config, '推送配置', '发件人显示昵称', "")
    to_email = read_config_value(config, '推送配置', '收件人邮箱', "")
    ntfy_api = read_config_value(config, '推送配置', 'ntfy推送地址', "")
    ntfy_tags = read_config_value(config, '推送配置', 'ntfy推送标签', "tada")
    ntfy_email = read_config_value(config, '推送配置', 'ntfy推送邮箱', "")
    pushplus_token = read_config_value(config, '推送配置', 'pushplus推送token', "")
    push_message_title = read_config_value(config, '推送配置', '自定义推送标题', "直播间状态更新通知")
    begin_push_message_text = read_config_value(config, '推送配置', '自定义开播推送内容', "")
    over_push_message_text = read_config_value(config, '推送配置', '自定义关播推送内容', "")
    disable_record = options.get(read_config_value(config, '推送配置', '只推送通知不录制(是/否)', "否"), False)
    push_check_seconds = int(read_config_value(config, '推送配置', '直播推送检测频率(秒)', 1800))
    begin_show_push = options.get(read_config_value(config, '推送配置', '开播推送开启(是/否)', "是"), True)
    over_show_push = options.get(read_config_value(config, '推送配置', '关播推送开启(是/否)', "否"), False)
    sooplive_username = read_config_value(config, '账号密码', 'sooplive账号', '')
    sooplive_password = read_config_value(config, '账号密码', 'sooplive密码', '')
    flextv_username = read_config_value(config, '账号密码', 'flextv账号', '')
    flextv_password = read_config_value(config, '账号密码', 'flextv密码', '')
    popkontv_username = read_config_value(config, '账号密码', 'popkontv账号', '')
    popkontv_partner_code = read_config_value(config, '账号密码', 'partner_code', 'P-00001')
    popkontv_password = read_config_value(config, '账号密码', 'popkontv密码', '')
    twitcasting_account_type = read_config_value(config, '账号密码', 'twitcasting账号类型', 'normal')
    twitcasting_username = read_config_value(config, '账号密码', 'twitcasting账号', '')
    twitcasting_password = read_config_value(config, '账号密码', 'twitcasting密码', '')
    popkontv_access_token = read_config_value(config, 'Authorization', 'popkontv_token', '')
    dy_cookie = read_config_value(config, 'Cookie', '抖音cookie', '')
    ks_cookie = read_config_value(config, 'Cookie', '快手cookie', '')
    tiktok_cookie = read_config_value(config, 'Cookie', 'tiktok_cookie', '')
    hy_cookie = read_config_value(config, 'Cookie', '虎牙cookie', '')
    douyu_cookie = read_config_value(config, 'Cookie', '斗鱼cookie', '')
    yy_cookie = read_config_value(config, 'Cookie', 'yy_cookie', '')
    bili_cookie = read_config_value(config, 'Cookie', 'B站cookie', '')
    xhs_cookie = read_config_value(config, 'Cookie', '小红书cookie', '')
    bigo_cookie = read_config_value(config, 'Cookie', 'bigo_cookie', '')
    blued_cookie = read_config_value(config, 'Cookie', 'blued_cookie', '')
    sooplive_cookie = read_config_value(config, 'Cookie', 'sooplive_cookie', '')
    netease_cookie = read_config_value(config, 'Cookie', 'netease_cookie', '')
    qiandurebo_cookie = read_config_value(config, 'Cookie', '千度热播_cookie', '')
    pandatv_cookie = read_config_value(config, 'Cookie', 'pandatv_cookie', '')
    maoerfm_cookie = read_config_value(config, 'Cookie', '猫耳fm_cookie', '')
    winktv_cookie = read_config_value(config, 'Cookie', 'winktv_cookie', '')
    flextv_cookie = read_config_value(config, 'Cookie', 'flextv_cookie', '')
    look_cookie = read_config_value(config, 'Cookie', 'look_cookie', '')
    twitcasting_cookie = read_config_value(config, 'Cookie', 'twitcasting_cookie', '')
    baidu_cookie = read_config_value(config, 'Cookie', 'baidu_cookie', '')
    weibo_cookie = read_config_value(config, 'Cookie', 'weibo_cookie', '')
    kugou_cookie = read_config_value(config, 'Cookie', 'kugou_cookie', '')
    twitch_cookie = read_config_value(config, 'Cookie', 'twitch_cookie', '')
    liveme_cookie = read_config_value(config, 'Cookie', 'liveme_cookie', '')
    huajiao_cookie = read_config_value(config, 'Cookie', 'huajiao_cookie', '')
    liuxing_cookie = read_config_value(config, 'Cookie', 'liuxing_cookie', '')
    showroom_cookie = read_config_value(config, 'Cookie', 'showroom_cookie', '')
    acfun_cookie = read_config_value(config, 'Cookie', 'acfun_cookie', '')
    changliao_cookie = read_config_value(config, 'Cookie', 'changliao_cookie', '')
    yinbo_cookie = read_config_value(config, 'Cookie', 'yinbo_cookie', '')
    yingke_cookie = read_config_value(config, 'Cookie', 'yingke_cookie', '')
    zhihu_cookie = read_config_value(config, 'Cookie', 'zhihu_cookie', '')
    chzzk_cookie = read_config_value(config, 'Cookie', 'chzzk_cookie', '')
    haixiu_cookie = read_config_value(config, 'Cookie', 'haixiu_cookie', '')
    vvxqiu_cookie = read_config_value(config, 'Cookie', 'vvxqiu_cookie', '')
    yiqilive_cookie = read_config_value(config, 'Cookie', '17live_cookie', '')
    langlive_cookie = read_config_value(config, 'Cookie', 'langlive_cookie', '')
    pplive_cookie = read_config_value(config, 'Cookie', 'pplive_cookie', '')
    six_room_cookie = read_config_value(config, 'Cookie', '6room_cookie', '')
    lehaitv_cookie = read_config_value(config, 'Cookie', 'lehaitv_cookie', '')
    huamao_cookie = read_config_value(config, 'Cookie', 'huamao_cookie', '')
    shopee_cookie = read_config_value(config, 'Cookie', 'shopee_cookie', '')
    youtube_cookie = read_config_value(config, 'Cookie', 'youtube_cookie', '')
    taobao_cookie = read_config_value(config, 'Cookie', 'taobao_cookie', '')
    jd_cookie = read_config_value(config, 'Cookie', 'jd_cookie', '')
    faceit_cookie = read_config_value(config, 'Cookie', 'faceit_cookie', '')
    migu_cookie = read_config_value(config, 'Cookie', 'migu_cookie', '')
    lianjie_cookie = read_config_value(config, 'Cookie', 'lianjie_cookie', '')
    laixiu_cookie = read_config_value(config, 'Cookie', 'laixiu_cookie', '')
    picarto_cookie = read_config_value(config, 'Cookie', 'picarto_cookie', '')

    video_save_type_list = ("FLV", "MKV", "TS", "MP4", "MP3音频", "M4A音频", "MP3", "M4A")
    if video_save_type and video_save_type.upper() in video_save_type_list:
        video_save_type = video_save_type.upper()
    else:
        video_save_type = "TS"

    check_path = video_save_path or default_path
    if utils.check_disk_capacity(check_path, show=first_run) < disk_space_limit:
        exit_recording = True
        if not recording:
            logger.warning(f"Disk space remaining is below {disk_space_limit} GB. "
                           f"Exiting program due to the disk space limit being reached.")
            sys.exit(-1)


    def contains_url(string: str) -> bool:
        pattern = r"(https?://)?(www\.)?[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+(:\d+)?(/.*)?"
        return re.search(pattern, string) is not None


    try:
        url_comments, line_list, url_line_list = [[] for _ in range(3)]
        with (open(url_config_file, "r", encoding=text_encoding, errors='ignore') as file):
            for origin_line in file:
                if origin_line in line_list:
                    delete_line(url_config_file, origin_line)
                line_list.append(origin_line)
                line = origin_line.strip()
                if len(line) < 18:
                    continue

                line_spilt = line.split('主播: ')
                if len(line_spilt) > 2:
                    line = update_file(url_config_file, line, f'{line_spilt[0]}主播: {line_spilt[-1]}')

                is_comment_line = line.startswith("#")
                if is_comment_line:
                    line = line.lstrip('#')

                if re.search('[,，]', line):
                    split_line = re.split('[,，]', line)
                else:
                    split_line = [line, '']

                if len(split_line) == 1:
                    url = split_line[0]
                    quality, name = [video_record_quality, '']
                elif len(split_line) == 2:
                    if contains_url(split_line[0]):
                        quality = video_record_quality
                        url, name = split_line
                    else:
                        quality, url = split_line
                        name = ''
                else:
                    quality, url, name = split_line

                if quality not in ("原画", "蓝光", "超清", "高清", "标清", "流畅"):
                    quality = '原画'

                if url not in url_line_list:
                    url_line_list.append(url)
                else:
                    delete_line(url_config_file, origin_line)

                url = 'https://' + url if '://' not in url else url
                url_host = url.split('/')[2]

                platform_host = [
                    'live.douyin.com',
                    'v.douyin.com',
                    'www.douyin.com',
                    'live.kuaishou.com',
                    'www.huya.com',
                    'www.douyu.com',
                    'www.yy.com',
                    'live.bilibili.com',
                    'www.redelight.cn',
                    'www.xiaohongshu.com',
                    'xhslink.com',
                    'www.bigo.tv',
                    'slink.bigovideo.tv',
                    'app.blued.cn',
                    'cc.163.com',
                    'qiandurebo.com',
                    'fm.missevan.com',
                    'look.163.com',
                    'twitcasting.tv',
                    'live.baidu.com',
                    'weibo.com',
                    'fanxing.kugou.com',
                    'fanxing2.kugou.com',
                    'mfanxing.kugou.com',
                    'www.huajiao.com',
                    'www.7u66.com',
                    'wap.7u66.com',
                    'live.acfun.cn',
                    'm.acfun.cn',
                    'live.tlclw.com',
                    'wap.tlclw.com',
                    'live.ybw1666.com',
                    'wap.ybw1666.com',
                    'www.inke.cn',
                    'www.zhihu.com',
                    'www.haixiutv.com',
                    "h5webcdnp.vvxqiu.com",
                    "17.live",
                    'www.lang.live',
                    "m.pp.weimipopo.com",
                    "v.6.cn",
                    "m.6.cn",
                    'www.lehaitv.com',
                    'h.catshow168.com',
                    'e.tb.cn',
                    'huodong.m.taobao.com',
                    '3.cn',
                    'eco.m.jd.com',
                    'www.miguvideo.com',
                    'm.miguvideo.com',
                    'show.lailianjie.com',
                    'www.imkktv.com',
                    'www.picarto.tv'
                ]
                overseas_platform_host = [
                    'www.tiktok.com',
                    'play.sooplive.co.kr',
                    'm.sooplive.co.kr',
                    'www.sooplive.com',
                    'm.sooplive.com',
                    'www.pandalive.co.kr',
                    'www.winktv.co.kr',
                    'www.flextv.co.kr',
                    'www.ttinglive.com',
                    'www.popkontv.com',
                    'www.twitch.tv',
                    'www.liveme.com',
                    'www.showroom-live.com',
                    'chzzk.naver.com',
                    'm.chzzk.naver.com',
                    'live.shopee.',
                    '.shp.ee',
                    'www.youtube.com',
                    'youtu.be',
                    'www.faceit.com'
                ]

                platform_host.extend(overseas_platform_host)
                clean_url_host_list = (
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
                    'www.lehaitv.com'
                )

                if 'live.shopee.' in url_host or '.shp.ee' in url_host:
                    url_host = 'live.shopee.' if 'live.shopee.' in url_host else '.shp.ee'

                if url_host in platform_host or any(ext in url for ext in (".flv", ".m3u8")):
                    if url_host in clean_url_host_list:
                        url = update_file(url_config_file, old_str=url, new_str=url.split('?')[0])

                    if 'xiaohongshu' in url:
                        host_id = re.search('&host_id=(.*?)(?=&|$)', url)
                        if host_id:
                            new_url = url.split('?')[0] + f'?host_id={host_id.group(1)}'
                            url = update_file(url_config_file, old_str=url, new_str=new_url)

                    url_comments = [i for i in url_comments if url not in i]
                    if is_comment_line:
                        url_comments.append(url)
                    else:
                        new_line = (quality, url, name)
                        url_tuples_list.append(new_line)
                else:
                    if not origin_line.startswith('#'):
                        color_obj.print_colored(f"\r{origin_line.strip()} 本行包含未知链接.此条跳过", color_obj.YELLOW)
                        update_file(url_config_file, old_str=origin_line, new_str=origin_line, start_str='#')

        while len(need_update_line_list):
            a = need_update_line_list.pop()
            replace_words = a.split('|')
            if replace_words[0] != replace_words[1]:
                if replace_words[1].startswith("#"):
                    start_with = '#'
                    new_word = replace_words[1][1:]
                else:
                    start_with = None
                    new_word = replace_words[1]
                update_file(url_config_file, old_str=replace_words[0], new_str=new_word, start_str=start_with)

        text_no_repeat_url = list(set(url_tuples_list))

        if len(text_no_repeat_url) > 0:
            for url_tuple in text_no_repeat_url:
                monitoring = len(running_list)

                if url_tuple[1] in not_record_list:
                    continue

                if url_tuple[1] not in running_list:
                    print(f"\r{'新增' if not first_start else '传入'}地址: {url_tuple[1]}")
                    monitoring += 1
                    args = [url_tuple, monitoring]
                    create_var[f'thread_{monitoring}'] = threading.Thread(target=start_record, args=args)
                    create_var[f'thread_{monitoring}'].daemon = True
                    create_var[f'thread_{monitoring}'].start()
                    running_list.append(url_tuple[1])
                    time.sleep(local_delay_default)
        url_tuples_list = []
        first_start = False

    except Exception as err:
        logger.error(f"错误信息: {err} 发生错误的行数: {err.__traceback__.tb_lineno}")

    if first_run:
        t = threading.Thread(target=display_info, args=(), daemon=True)
        t.start()
        t2 = threading.Thread(target=adjust_max_request, args=(), daemon=True)
        t2.start()
        first_run = False

    time.sleep(3)