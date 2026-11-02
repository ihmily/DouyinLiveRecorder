# -*- coding: utf-8 -*-
import datetime
import sys
import time
from typing import cast

from loguru import logger

import i18n
import main
from src import utils
from src.ffmpeg_proc import _get_error_line

# 录制状态快照与控制台显示（独立模块）
#
# - get_status()：汇总运行状态快照，供 Web API 读取
# - display_info()：后台守护线程定时刷新控制台状态
#
# 通过 `import main` 在运行时惰性读取 main 的全局变量（监控数、录制集合、错误窗口、磁盘路径、
# 引擎线程句柄等），避免循环导入与 __main__ 二次执行。


# 汇总运行状态快照（版本、监控数、正在录制列表及时长/画质、累计与窗口错误数、磁盘剩余、
# 运行时长、引擎线程存活），返回可直接 JSON 序列化的字典。
def get_status() -> dict[str, object]:
    # 录制集合的写入点均持 record_state_lock（main.py 录制增删、src/notify.py 计数更新），
    # 故单次持锁快照即可；except 保留：一旦触发说明新增了无锁写入路径，必须留痕。
    now = datetime.datetime.now()
    recording_snapshot: list[str] = []
    recording_times: dict[str, dict[str, str]] = {}
    monitoring_val: int = main.monitoring
    running_val: list[str] = []
    # 累计错误数必须在下面**同一次 max_request_lock 持锁**内与 error_window 一起快照：
    # 写侧 record_error 的 `error_count += 1` 是读-改-写三步，分开采样会拿到「加了一半」的旧值，
    # 面板随之出现「累计 0 / 窗口 3」这类互相矛盾的状态。此处只留初值占位。
    # [历史注] 旧实现在本行无锁读一次 error_count。
    error_val: int = 0
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
            # error_count/error_window 的写侧用 max_request_lock，record_state_lock 对它不构成
            # 互斥——「持了某把锁」不等于「持了对的锁」，累计值改到下面与窗口值同锁同批快照。
            # 本块只管录制集合。
    # 绑定异常对象时必须保留括号（`except A, B as e:` 非法）
    except (RuntimeError, IndexError) as e:
        # 理论上不可达（写入点均已持锁）；一旦出现说明有新增路径漏锁，必须留痕
        logger.warning(
            i18n.tr("获取录制状态失败（疑似新增无锁写入路径），返回空快照: {type_name}", type_name=type(e).__name__)
        )
    # 累计值与窗口值必须在**同一次持锁**内一起读：分两次采样时中间任何一次 record_error 都会
    # 让二者来自不同时刻，面板拿到一对不自洽的数。写侧只有这一把锁，故单点持锁读全。
    with main.max_request_lock:
        error_val = main.error_count
        recent_errors_val = sum(main.error_window)
    try:
        disk_free_gb = utils.check_disk_capacity(main.default_path)
    except Exception:
        disk_free_gb = -1.0
    # engine_alive：录制引擎守护线程是否存活；None 表示非 Web 模式（CLI 直跑，视作存活）
    if main._recorder_thread is None:
        engine_alive = True
    else:
        engine_alive = main._recorder_thread.is_alive()
    # uptime 取 process_start_time（进程启动即固定）；start_display_time 每 5 秒被
    # display_info 重置为当前时刻，用它算 uptime 会恒在 0~5 秒之间。
    # 直接属性访问而非三参 getattr：后者返回 Any，既丢类型检查又触发 warn_return_any；
    # main.process_start_time 有模块级声明，属性必然存在。
    _proc_start = main.process_start_time
    uptime = str(now - _proc_start).split(".")[0] if _proc_start else "0:00:00"
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
        # Web 录制开关（False=已停止）：面板「开始/停止录制」按钮状态的同步依据，
        # 页面刷新/重连后经本字段恢复按钮的真实态（与引擎线程存活正交）
        "recording_enabled": main.recording_enabled,
    }


# 当前网络并发容量：调度器就绪时取自适应容量（随活跃任务数缩放、错误率温和降容），
# 未就绪（main() 尚未初始化调度器，如极早期启动/测试环境）时回退配置值。
# 配置值「同一时间访问网络的线程数」只是容量下限，直接显示会让人误以为高并发优化未生效。
def _live_network_capacity() -> int:
    # 直接属性访问而非三参 getattr：后者返回 Any，既丢类型检查又触发 no-any-return；
    # main.scheduler 有模块级声明（ConcurrencyScheduler | None），属性必然存在。
    scheduler = main.scheduler
    if scheduler is not None:
        # 读 capacity（并发上限）而非 value（剩余许可）：有房间持槽时 value 会随瞬时占用
        # 下跌，显示出来是「空闲槽数」，同样误导。
        return scheduler.network_semaphore.capacity
    return main.max_request


# display_info 的刷新节拍与异常退避：正常 5s 一次；连续失败按 2^n 退避并封顶 300s，
# 避免异常路径零间隔重入跑满单核并灌满日志。
_DISPLAY_INTERVAL_SECONDS = 5.0
_DISPLAY_BACKOFF_MAX_SECONDS = 300.0


def _sleep(seconds: float) -> None:
    # time.sleep 的模块内间接层（与 src/scheduler._sleep 同型），供用例注入计数/停循环；
    # 不得改为 monkeypatch recorder_status.time——那是 stdlib 模块本体，会波及同进程所有线程。
    time.sleep(seconds)


def _display_delay(consecutive_failures: int) -> float:
    # 连续失败次数 → 下次休眠秒数：0 次为常规节拍，其后 5s×2^n（首次失败即 ≥2 倍）并封顶。
    # 指数上界钳到 16：线程可能连续失败数天，不必为此算 2^几千。
    # 底数写 2.0：typeshed 中 int ** int 返回 Any（触发 warn_return_any），float ** int 才是 float。
    if consecutive_failures <= 0:
        return _DISPLAY_INTERVAL_SECONDS
    return min(_DISPLAY_INTERVAL_SECONDS * (2.0 ** min(consecutive_failures, 16)), _DISPLAY_BACKOFF_MAX_SECONDS)


# 守护线程主体：每 5 秒清屏并打印监控数/并发数/画质/格式/累计错误数及各房间已录时长；死循环不返回。
def display_info() -> None:
    _sleep(_DISPLAY_INTERVAL_SECONDS)
    consecutive_failures = 0
    while True:
        # 无控制台环境（pythonw.exe / 冻结 console=False exe）下 sys.stdout 为 None，
        # 而 main.py 无条件启动本线程：必须在进 try 之前判空，否则每轮 AttributeError →
        # logger.error 紧循环，跑满一核并灌满 streamget.log。
        if sys.stdout is None:
            _sleep(_DISPLAY_INTERVAL_SECONDS)
            continue
        try:
            _ = sys.stdout.flush()
            if sys.stdout.isatty():
                _ = sys.stdout.write("\033[2J\033[H")
                _ = sys.stdout.flush()
            print(i18n.tr("\r共监测{monitoring}个直播中", monitoring=main.monitoring), end=" | ")
            print(
                i18n.tr(
                    "同一时间访问网络的线程数: {live_network_capacity}", live_network_capacity=_live_network_capacity()
                ),
                end=" | ",
            )
            print(i18n.tr("是否开启代理录制: {use_proxy}", use_proxy="是" if main.use_proxy else "否"), end=" | ")
            if main.split_video_by_time:
                print(i18n.tr("录制分段开启: {split_time}秒", split_time=main.split_time), end=" | ")
            else:
                print("录制分段开启: 否", end=" | ")
            if main.create_time_file:
                print("是否生成时间文件: 是", end=" | ")
            print(
                i18n.tr("录制视频质量为: {video_record_quality}", video_record_quality=main.video_record_quality),
                end=" | ",
            )
            print(i18n.tr("录制视频格式为: {video_save_type}", video_save_type=main.video_save_type), end=" | ")
            # 与 get_status 同锁取值：`+=` 是读-改-写三步，控制台「累计错误数」与面板读数必须
            # 可比。持锁只取值、不打印——锁窗口内不得有 IO（慢控制台会把 record_error 挂住）。
            with main.max_request_lock:
                _error_count_snapshot = main.error_count
            print(i18n.tr("累计错误数为: {error_count}", error_count=_error_count_snapshot), end=" | ")
            now = time.strftime("%H:%M:%S", time.localtime())
            print(i18n.tr("当前时间: {now}", now=now))

            if len(main.recording) == 0:
                _sleep(_DISPLAY_INTERVAL_SECONDS)
                if main.monitoring == 0:
                    print("\r没有正在监测和录制的直播")
                else:
                    print(
                        i18n.tr(
                            "\r没有正在录制的直播 循环监测间隔时间：{delay_default}秒", delay_default=main.delay_default
                        )
                    )
            else:
                now_time = datetime.datetime.now()
                print("x" * 60)
                with main.record_state_lock:
                    no_repeat_recording = list(set(main.recording))
                print(
                    i18n.tr(
                        "正在录制{no_repeat_recording_count}个直播: ",
                        no_repeat_recording_count=len(no_repeat_recording),
                    )
                )
                for recording_live in no_repeat_recording:
                    with main.record_state_lock:
                        _rt_info = main.recording_time_list.get(recording_live, [now_time, ""])
                    rt = cast(datetime.datetime, _rt_info[0]) if _rt_info else now_time
                    qa = str(_rt_info[1]) if len(_rt_info) > 1 else ""
                    have_record_time = now_time - rt
                    print(
                        i18n.tr(
                            "{recording_live}[{qa}] 正在录制中 {have_record_time}",
                            recording_live=recording_live,
                            qa=qa,
                            have_record_time=str(have_record_time).split(".")[0],
                        )
                    )

                print("x" * 60)
                # [2026-10-30 L-03] main.start_display_time 当前无任何生产读取点（仅本处每 5s 回写；
                # recorder_status 的 uptime 判据已改用 process_start_time，见本文件 get_status 注释）。
                # 保留写入是为维持 main 模块级状态契约（外部诊断/历史脚本可能读取），删除前须全仓 grep 复核。
                main.start_display_time = now_time
            consecutive_failures = 0
        except Exception as e:
            consecutive_failures += 1
            logger.error(
                i18n.tr(
                    "错误信息: {type_name}: {e} 发生错误的行数: {get_error_line}",
                    type_name=type(e).__name__,
                    e=e,
                    get_error_line=_get_error_line(e),
                )
            )
        # 节拍控制放 try 之外：flush 自身抛错（Web 后台模式下 logs/web_console.log 被归档、
        # 句柄已关时抛 ValueError: I/O operation on closed file）或更早语句抛错都会跳过
        # try 内的 sleep → 零间隔重入，故按连续失败次数退避。
        _sleep(_display_delay(consecutive_failures))
