#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 运行日志归档模块：停止录制流程（手动停止 / 异常或中断退出）统一调用的收尾步骤，
# 将四个运行时日志按「原文件名_YYYYMMDD_HHMMSS.扩展名」改名归档（目标已存在时追加 _N 序号）：
# - logs/streamget.log          loguru DEBUG 文件 sink（录制进程）
# - logs/PlayURL.log            loguru INFO 文件 sink（录制进程）
# - logs/danmaku_monitor.jsonl  弹幕监控枢纽自管的边车文件
# - logs/web_console.log        web.py 后台模式重定向的 sys.stdout/sys.stderr
#
# Windows 下句柄未关闭的文件 rename 会抛 PermissionError（WinError 32），故改名前先
# flush 并关闭对应句柄：loguru 文件 sink 经 logger.remove()（先 flush enqueue 队列再关文件）、
# 边车文件经 DanmakuMonitorHub.close_file()、web_console 经流对象自身 flush+close()。
# 归档全程不抛异常：单文件失败（如句柄被第三方进程占用）仅告警跳过，绝不中断停止录制流程；
# 归档后日志链路立即恢复（loguru 重新 add 即创建全新同名文件），不影响现有日志写入逻辑。

import os
import sys
import threading
from datetime import datetime
from typing import TextIO

from src.danmaku_monitor import close_monitor_file
from src.logger import (
    GUI_PARENT_ENV,
    add_file_sinks,
    logger,
    rebind_console_sink,
    remove_file_sinks,
    script_path,
)

# 参与归档的运行日志文件名（logs 目录下固定 ASCII 名，不含空格与非法字符）
ARCHIVE_LOG_NAMES: tuple[str, str, str, str] = (
    "streamget.log",
    "PlayURL.log",
    "danmaku_monitor.jsonl",
    "web_console.log",
)

# 归档禁用开关：测试进程（tests/conftest.py 设置）会导入 main 并注册归档 atexit，
# 但 pytest 退出并非「停止录制」事件，不得改名开发者工作副本里的真实日志。
_DISABLE_ENV = "DOUYIN_DISABLE_LOG_ARCHIVE"

# 归档串行锁：Web 面板停止与进程退出（atexit）可能并发触发，避免同一文件被重复处理
_archive_lock = threading.Lock()


# 生成归档目标路径：原名_YYYYMMDD_HHMMSS.扩展名；目标已存在时依次追加 _1/_2 序号避免覆盖。
def _archive_target(src_path: str, ts: str) -> str:
    dir_name, file_name = os.path.split(src_path)
    stem, ext = os.path.splitext(file_name)
    candidate = os.path.join(dir_name, f"{stem}_{ts}{ext}")
    seq = 1
    while os.path.exists(candidate):
        candidate = os.path.join(dir_name, f"{stem}_{ts}_{seq}{ext}")
        seq += 1
    return candidate


# 收集 sys.stdout/sys.stderr 中指向指定文件的活动句柄（web.py 后台模式两者为同一对象，去重）。
def _streams_bound_to(path: str) -> list[TextIO]:
    bound: list[TextIO] = []
    for stream in (sys.stdout, sys.stderr):
        if stream is None or any(stream is existing for existing in bound):
            continue
        name = getattr(stream, "name", None)
        if isinstance(name, str) and os.path.abspath(name) == os.path.abspath(path):
            bound.append(stream)
    return bound


# 重建 web_console.log 句柄并重新接管 sys.stdout/sys.stderr 与 loguru 控制台 sink
# （与 web.py::_enter_background_mode 同参数：追加写 + 行缓冲，保证后台日志实时落盘）。
def _rebind_web_console(path: str) -> None:
    try:
        stream = open(path, "a", encoding="utf-8", buffering=1)
    except OSError as e:
        logger.warning(f"重建 web_console.log 句柄失败: {type(e).__name__}: {e}")
        return
    sys.stdout = stream
    sys.stderr = stream
    rebind_console_sink()


# 归档 web_console.log：先关句柄再改名。该文件仅在 Web 后台模式下被重定向为
# sys.stdout/sys.stderr（同一对象）；改名后立即重建句柄，后续输出写往全新的同名文件，
# 避免任何线程向已关闭句柄写入。文件存在但未绑定标准流（历史遗留）时仅改名、不动标准流。
def _archive_web_console(logs_dir: str, ts: str, archived: list[str]) -> None:
    path = os.path.join(logs_dir, "web_console.log")
    if not os.path.isfile(path):
        return
    bound = _streams_bound_to(path)
    for stream in bound:
        try:
            stream.flush()
            stream.close()
        except Exception as e:
            logger.debug(f"关闭 web_console 句柄异常(忽略): {type(e).__name__}: {e}")
    try:
        target = _archive_target(path, ts)
        os.rename(path, target)
        archived.append(target)
    except OSError as e:
        # 改名失败（句柄被第三方进程占用等）：跳过归档，并重建原路径句柄保证输出链路不断
        logger.warning(f"日志归档失败(跳过): web_console.log - {type(e).__name__}: {e}")
        if bound:
            _rebind_web_console(path)
        return
    if bound:
        _rebind_web_console(path)


# 单文件归档：文件不存在则跳过；改名失败仅告警（Windows 下句柄被第三方进程占用时会发生），
# 绝不向调用方抛异常——归档是停止录制流程的旁路收尾步骤。
def _rename_one(path: str, ts: str, archived: list[str]) -> None:
    name = os.path.basename(path)
    try:
        if not os.path.isfile(path):
            return
        target = _archive_target(path, ts)
        os.rename(path, target)
        archived.append(target)
        logger.debug(f"日志已归档: {name} -> {os.path.basename(target)}")
    except OSError as e:
        logger.warning(f"日志归档失败(跳过): {name} - {type(e).__name__}: {e}")


# 停止录制流程的日志归档入口：flush/关闭四个运行日志的句柄后，按停止操作发生时刻的
# 本机时间戳逐个改名。reopen_streams=True（Web 面板停止等进程继续运行场景）时在改名后
# 重建 loguru 文件 sink，日志写入立即恢复到全新同名文件；False（atexit 等进程退出场景，
# 由调用方显式传参）仅关闭+改名，下次启动时经导入期注册自然重建。
# 返回成功归档的新路径列表（仅供日志/测试观察，流程不依赖返回值）；本函数绝不抛异常。
def archive_runtime_logs(*, reopen_streams: bool = True) -> list[str]:
    try:
        with _archive_lock:
            # 测试进程禁用（见 _DISABLE_ENV 注释）；GUI 父进程不持有录制日志句柄，
            # 也绝不能改名录制子进程正在写的日志文件
            if os.environ.get(_DISABLE_ENV, "").strip().lower() in ("1", "true", "yes"):
                return []
            if os.environ.get(GUI_PARENT_ENV) == "1":
                return []
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            logs_dir = os.path.join(script_path, "logs")
            archived: list[str] = []

            # web_console.log 最先处理：其句柄是 sys.stdout/sys.stderr，改名后须立即重建，
            # 使归档过程自身后续的日志输出有正常去处
            _archive_web_console(logs_dir, ts, archived)

            # loguru 文件 sink：remove() 先 flush enqueue 队列并关闭句柄（幂等），再改名
            remove_file_sinks()
            _rename_one(os.path.join(logs_dir, "streamget.log"), ts, archived)
            _rename_one(os.path.join(logs_dir, "PlayURL.log"), ts, archived)

            # 弹幕监控边车文件：hub 自管句柄 flush+close，下一条事件写入时自动重开
            close_monitor_file()
            _rename_one(os.path.join(logs_dir, "danmaku_monitor.jsonl"), ts, archived)

            if reopen_streams:
                # 进程继续运行：重新注册文件 sink，loguru add() 即创建全新同名文件
                add_file_sinks()

            if archived:
                logger.info(f"运行日志已归档: {'、'.join(os.path.basename(p) for p in archived)}")
            return archived
    except Exception as e:
        # 归档失败绝不允许影响停止录制本身：任何意外仅告警并返回空列表
        try:
            logger.warning(f"运行日志归档失败(忽略): {type(e).__name__}: {e}")
        except Exception:
            pass
        return []
