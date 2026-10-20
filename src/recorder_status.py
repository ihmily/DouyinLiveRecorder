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

# 录制状态快照与控制台信息展示（独立模块）
#
# 负责：
# - 汇总录制引擎运行状态快照，供 Web API 读取（get_status）
# - 后台守护线程定时刷新控制台状态显示（display_info）
#
# 需要读取 main 的大量运行时全局变量（监控数、录制集合、错误窗口、磁盘路径、引擎线程句柄等），
# 通过 `import main` 在运行时惰性读取，避免循环导入与 __main__ 二次执行问题。


# 汇总录制引擎运行状态快照（版本号、监控数、正在录制列表及时长/画质、累计与窗口错误数、
# 磁盘剩余空间、运行时长、引擎线程是否存活）；无入参，返回可直接 JSON 序列化的字典
def get_status() -> dict[str, object]:
    # MI-10：原「5 次重试 + 失败兜底」依据「部分路径未持 record_state_lock 改 recording /
    # recording_time_list」；核查全部写入点（main.py 录制增删、src/notify.py 计数更新）均在
    # with main.record_state_lock 内 → 死逻辑，改为单次持锁快照；except 保留作无锁写入留痕。
    now = datetime.datetime.now()
    recording_snapshot: list[str] = []
    recording_times: dict[str, dict[str, str]] = {}
    monitoring_val: int = main.monitoring
    running_val: list[str] = []
    error_val: int = main.error_count
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
    # 注：需要绑定异常对象时不能省括号（`except A, B as e:` 非法），此处保留括号写法
    except (RuntimeError, IndexError) as e:
        # 理论上不可达（写入点均已持锁）；一旦出现说明有新增路径漏锁，必须留痕
        logger.warning(
            i18n.tr("获取录制状态失败（疑似新增无锁写入路径），返回空快照: {type_name}", type_name=type(e).__name__)
        )
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
    # MI-09：用 process_start_time（进程启动即固定）而非 start_display_time——
    # 后者被 display_info 每 5 秒重置为当前时刻，会让 uptime 恒定在 0~5 秒之间。
    # L-31（2026-10-02）：模块级已声明属性直接访问（同文件对 main.scheduler 已是正确形态）；
    # 三参 getattr 返回 Any，warn_return_any 下泄漏类型且属性链检查全部失效。
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


# 当前网络并发容量的实时值：调度器就绪时取自适应容量（随活跃任务数缩放、错误率温和降容），
# 未就绪（main() 尚未初始化调度器，如极早期启动/测试环境）时回退配置值。
# 2026-08-23 定稿：实际并发槽由 ConcurrencyScheduler 动态决定，配置值「同一时间访问网络的
# 线程数」只是容量下限之一——控制台直接显示配置值会严重误导（实测容量 12/20 而显示 3，
# 高并发优化形同「未生效」）。
def _live_network_capacity() -> int:
    # 直接属性访问而非三参 getattr：mypy 不对三参 getattr 做字面量名解析（返回 Any），
    # 既触发 no-any-return 又丢失属性类型检查；main.scheduler 有模块级声明
    # （ConcurrencyScheduler | None，main.py），属性必然存在，无需 getattr 兜底。
    scheduler = main.scheduler
    if scheduler is not None:
        # 读 capacity（并发上限）而不是 value（剩余可用许可）：SEV-01 修复后二者分离，
        # 有房间持槽时 value 会随瞬时占用下跌，显示出来就成了「空闲槽数」，同样误导——
        # 用户要看到的是调度器设定的并发上限本身。
        return scheduler.network_semaphore.capacity
    return main.max_request


# display_info 的刷新节拍与异常退避（MID-31）：正常每 _DISPLAY_INTERVAL_SECONDS 秒刷一次，
# 连续失败按 2^n 指数退避、封顶 _DISPLAY_BACKOFF_MAX_SECONDS（原实现唯一 sleep 在 try 体内、
# except 无退避 → 异常路径零间隔重入，单核跑满 + 秒级灌满日志）。
_DISPLAY_INTERVAL_SECONDS = 5.0
_DISPLAY_BACKOFF_MAX_SECONDS = 300.0


def _sleep(seconds: float) -> None:
    # time.sleep 的模块内间接层（与 src/scheduler._sleep 同型）：供用例注入计数/停循环。
    # 不得改为 monkeypatch recorder_status.time——那是 stdlib 模块本体，会波及同进程所有线程。
    time.sleep(seconds)


def _display_delay(consecutive_failures: int) -> float:
    # 连续失败次数 → 下次休眠秒数：0 次为常规节拍，其后 5s×2^n（首次失败即 ≥2 倍常规节拍）
    # 并封顶 _DISPLAY_BACKOFF_MAX_SECONDS。
    # 指数上界钳到 16：本线程可能连续失败数天，没必要为此算 2^几千。
    # 底数刻意写成 2.0：typeshed 里 int ** int 的返回类型是 Any（会经 warn_return_any 报
    # no-any-return），float ** int 才是确定的 float。
    if consecutive_failures <= 0:
        return _DISPLAY_INTERVAL_SECONDS
    return min(_DISPLAY_INTERVAL_SECONDS * (2.0 ** min(consecutive_failures, 16)), _DISPLAY_BACKOFF_MAX_SECONDS)


# 守护线程主体：每 5 秒清屏并打印监控数/并发数/画质/格式/累计错误数及各房间已录时长；无入参，死循环不返回
def display_info() -> None:
    _sleep(_DISPLAY_INTERVAL_SECONDS)
    consecutive_failures = 0
    while True:
        # 无控制台环境下 sys.stdout 就是 None（pythonw.exe / 冻结 console=False exe，见 AGENTS
        # 「无控制台环境」条目），而 main.py 无条件启动本线程。必须在进入 try 之前判空：
        # 否则每轮 AttributeError → logger.error → 紧循环，既占满一个核又把 streamget.log 灌满。
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
            print(i18n.tr("累计错误数为: {error_count}", error_count=main.error_count), end=" | ")
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
        # 节拍控制放 try 之外（finally 亦可，根因见 MID-31）：flush 自身抛错（Web 后台模式下
        # logs/web_console.log 被归档改名、句柄已关时抛 ValueError: I/O operation on closed
        # file）或更早语句抛错都会跳过 try 内的 sleep → 零间隔重入，故按连续失败次数退避。
        _sleep(_display_delay(consecutive_failures))
