# -*- coding: utf-8 -*-
# 录制状态快照与控制台信息展示（独立模块）
#
# 负责：
# - 汇总录制引擎运行状态快照，供 Web API 读取（get_status）
# - 后台守护线程定时刷新控制台状态显示（display_info）
#
# 需要读取 main 的大量运行时全局变量（监控数、录制集合、错误窗口、磁盘路径、引擎线程句柄等），
# 通过 `import main` 在运行时惰性读取，避免循环导入与 __main__ 二次执行问题。

import datetime
import sys
import time
from typing import cast

from loguru import logger

import main
from src import utils
from src.ffmpeg_proc import _get_error_line


# 汇总录制引擎运行状态快照（版本号、监控数、正在录制列表及时长/画质、累计与窗口错误数、
# 磁盘剩余空间、运行时长、引擎线程是否存活）；无入参，返回可直接 JSON 序列化的字典
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
    monitoring_val: int = main.monitoring
    running_val: list[str] = []
    error_val: int = main.error_count
    snapshot_ok = False
    for _attempt in range(5):
        try:
            with main.record_state_lock:
                recording_snapshot = list(main.recording)
                recording_times = {}
                for _name, _info in main.recording_time_list.items():
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
                monitoring_val = main.monitoring
                running_val = list(main.running_list)
                error_val = main.error_count
                snapshot_ok = True
                break
        except (RuntimeError, IndexError):
            continue
    if not snapshot_ok:
        logger.warning("获取录制状态失败（并发竞争），返回空快照")
    # 窗口口径错误数：error_window 由 max_request_lock 保护，持锁采样避免迭代期并发修改
    with main.max_request_lock:
        recent_errors_val = sum(main.error_window)
    try:
        disk_free_gb = utils.check_disk_capacity(main.default_path)
    except Exception:
        disk_free_gb = -1.0
    # engine_alive: 录制引擎守护线程是否存活。None 表示未运行于 Web 模式（CLI 直跑，视作存活）。
    if main._recorder_thread is None:
        engine_alive = True
    else:
        engine_alive = main._recorder_thread.is_alive()
    uptime = str(now - main.start_display_time).split(".")[0] if main.start_display_time else "0:00:00"
    return {
        "version": main.version,
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
        "error_count": error_val,  # 累计错误数（进程启动起单调递增）
        "recent_errors": recent_errors_val,  # 近 error_window_size 次检测周期内的错误数（瞬时口径）
        "disk_free_gb": round(disk_free_gb, 2),
        "uptime": uptime,
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "engine_alive": engine_alive,
    }


# 当前网络并发容量的实时值：调度器就绪时取自适应容量（随活跃任务数缩放、错误率温和降容），
# 未就绪（main() 尚未初始化调度器，如极早期启动/测试环境）时回退配置值。
# 2026-08-23 定稿：实际并发槽由 ConcurrencyScheduler 动态决定，配置值「同一时间访问网络的
# 线程数」只是容量下限之一——控制台直接显示配置值会严重误导（实测容量 12/20 而显示 3，
# 高并发优化形同「未生效」）。
def _live_network_capacity() -> int:
    scheduler = getattr(main, "scheduler", None)
    if scheduler is not None:
        return scheduler.network_semaphore.value
    return main.max_request


# 守护线程主体：每 5 秒清屏并打印监控数/并发数/画质/格式/累计错误数及各房间已录时长；无入参，死循环不返回
def display_info() -> None:
    # 后台线程：刷新控制台状态显示
    time.sleep(5)
    while True:
        try:
            _ = sys.stdout.flush()
            time.sleep(5)
            if sys.stdout.isatty():
                _ = sys.stdout.write("\033[2J\033[H")
                _ = sys.stdout.flush()
            print(f"\r共监测{main.monitoring}个直播中", end=" | ")
            print(f"同一时间访问网络的线程数: {_live_network_capacity()}", end=" | ")
            print(f"是否开启代理录制: {'是' if main.use_proxy else '否'}", end=" | ")
            if main.split_video_by_time:
                print(f"录制分段开启: {main.split_time}秒", end=" | ")
            else:
                print("录制分段开启: 否", end=" | ")
            if main.create_time_file:
                print("是否生成时间文件: 是", end=" | ")
            print(f"录制视频质量为: {main.video_record_quality}", end=" | ")
            print(f"录制视频格式为: {main.video_save_type}", end=" | ")
            print(f"累计错误数为: {main.error_count}", end=" | ")
            now = time.strftime("%H:%M:%S", time.localtime())
            print(f"当前时间: {now}")

            if len(main.recording) == 0:
                time.sleep(5)
                if main.monitoring == 0:
                    print("\r没有正在监测和录制的直播")
                else:
                    print(f"\r没有正在录制的直播 循环监测间隔时间：{main.delay_default}秒")
            else:
                now_time = datetime.datetime.now()
                print("x" * 60)
                with main.record_state_lock:
                    no_repeat_recording = list(set(main.recording))
                print(f"正在录制{len(no_repeat_recording)}个直播: ")
                for recording_live in no_repeat_recording:
                    with main.record_state_lock:
                        _rt_info = main.recording_time_list.get(recording_live, [now_time, ""])
                    rt = cast(datetime.datetime, _rt_info[0]) if _rt_info else now_time
                    qa = str(_rt_info[1]) if len(_rt_info) > 1 else ""
                    have_record_time = now_time - rt
                    print(f"{recording_live}[{qa}] 正在录制中 {str(have_record_time).split('.')[0]}")

                # print('\n本软件已运行：'+str(now_time - start_display_time).split('.')[0])
                print("x" * 60)
                main.start_display_time = now_time
        except Exception as e:
            logger.error(f"错误信息: {e} 发生错误的行数: {_get_error_line(e)}")
