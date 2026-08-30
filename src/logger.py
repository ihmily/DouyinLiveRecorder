#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import configparser
import os
import sys

from loguru import logger

__all__ = ["logger", "rebind_console_sink", "child_process_env", "remove_file_sinks", "add_file_sinks"]

# GUI 父进程环境标记：gui.py 必须在导入任何 src 模块**之前**设置。
# GUI 进程只做面板展示与配置管理、不执行录制，绝不能持有录制日志文件
# （logs/streamget.log / logs/PlayURL.log）的句柄——GUI 与录制子进程双开同一文件时，
# 任一方到达轮转阈值（rotation="300 KB"）写日志都要先 os.rename 改名，而对方句柄
# 未关即抛 PermissionError WinError 32：轮转永不成功、该进程的文件日志自此全量
# 静默丢失且每条日志向 stderr 吐 Logging error（2026-08-29 实测：streamget.log
# 卡在 300031 字节，录制子进程日志全丢）。GUI 进程改为独占写 logs/gui.log
# （单进程单句柄、轮转安全）。改名标记时必须同步 gui.py 的设置处与下方 child_process_env。
GUI_PARENT_ENV = "DLR_GUI_PARENT"

# 当前进程是否为 GUI 父进程（logger.py 在导入期求值，故 GUI 入口须先设标记再导入 src）
_gui_parent = os.environ.get(GUI_PARENT_ENV) == "1"


def _app_root() -> str:
    # 返回应用程序根目录（exe 同级目录）。
    #
    #     - 源码运行：主脚本（sys.argv[0]）所在目录（项目根）。
    #     - 冻结运行（PyInstaller onedir + contents_directory='_internal'）：
    #       exe 与其同级的 config/ ffmpeg/ node/ 等运行时资源位于 <exe_dir>；
    #       而 src/ 及全部依赖包统一落在 <exe_dir>/_internal/。
    #       故这里返回 exe 同级目录（_internal 的父目录），供定位 config/ffmpeg/node
    #       等运行时资源，使其在打包后保持与 exe 同级、可被直接读写。
    #
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.realpath(sys.executable))
    return os.path.split(os.path.realpath(sys.argv[0]))[0]


# 移除默认处理器
logger.remove()

# 控制台日志格式（彩色）
custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"

# 控制台 sink 的 handler id：供 rebind_console_sink() 在 stderr 被重定向后重建
_console_sink_id: int | None = None


# 按当前 sys.stderr 建立/重建控制台 sink。
# loguru 的 sink 在 add() 时即绑定具体对象，**不会**因之后 sys.stderr 被替换而跟着变。
# Web 后台模式（web.py::_enter_background_mode）在本模块导入之后才把 sys.stdout/sys.stderr
# 重定向到 logs/web_console.log 并 SW_HIDE 隐藏控制台窗口——若不重建 sink，全部 DEBUG/
# WARNING 日志仍写往已被隐藏的控制台，web_console.log 里只剩 print 输出，排障时会误判
# 「没有日志 = 没有发生」（实测据此把「探针假绿」错判成「校验未执行」）。
def rebind_console_sink() -> None:
    global _console_sink_id
    if _console_sink_id is not None:
        try:
            logger.remove(_console_sink_id)
        except ValueError:
            # handler 已不存在（如调用方执行过 logger.remove()）：id 失效，忽略即可
            pass
        _console_sink_id = None
    if sys.stderr is None:
        return
    # 重定向到文件后不再着色：ANSI 转义序列会污染日志文本
    is_tty = bool(getattr(sys.stderr, "isatty", lambda: False)())
    _console_sink_id = logger.add(sink=sys.stderr, format=custom_format, level="DEBUG", colorize=is_tty, enqueue=True)


# 构造录制子进程的启动环境：剔除 GUI 父进程标记（否则子进程同样被判为 GUI、
# 不写录制日志文件，录制日志将全量丢失），并固定子进程输出编码为 UTF-8。
# gui.py 拉起录制核心（main.py / 冻结 CLI exe）时必须经此函数，禁止直接透传
# os.environ。base 传 None 时以当前进程环境为底。
def child_process_env(base: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    env.pop(GUI_PARENT_ENV, None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# 添加控制台输出（无论是否启用日志文件，控制台输出始终保留）
# 注意：pythonw / 窗口化启动器（console=False 的冻结 exe）不会分配控制台，
# 此时 sys.stderr 为 None；loguru 拒绝把 None 作为 sink，会抛
# `TypeError: Cannot log to objects of type 'NoneType'`，导致模块导入期即崩溃、
# 窗口化运行静默失败。故此处先行判空：无控制台环境跳过控制台 sink，
# 日志持久化交由下方文件 sink 兜底。
if sys.stderr is not None:
    _console_sink_id = logger.add(sink=sys.stderr, format=custom_format, level="DEBUG", colorize=True, enqueue=True)

# 运行时资源根目录（exe 同级：config/ logs/ downloads/ 等），
# 与 _app_root() 保持一致；冻结后指向 exe 父目录而非 _internal。
script_path = _app_root()

# 录制日志文件 sink 的 handler id：供停止录制归档流程（src/log_archive.py）
# 经 remove_file_sinks() 关闭句柄、add_file_sinks() 重建，导入期注册与运行期重建共用同参。
_streamget_sink_id: int | None = None
_playurl_sink_id: int | None = None


# 注册 DEBUG 级文件 sink（排除 INFO），返回 handler id。
def _add_streamget_sink() -> int:
    return logger.add(
        f"{script_path}/logs/streamget.log",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
        filter=lambda i: i["level"].name != "INFO",
        serialize=False,
        enqueue=True,
        retention=3,
        rotation="300 KB",
        encoding="utf-8",
    )


# 注册 INFO 级文件 sink（直播流 URL 等），返回 handler id。
def _add_playurl_sink() -> int:
    return logger.add(
        f"{script_path}/logs/PlayURL.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {message}",
        filter=lambda i: i["level"].name == "INFO",
        serialize=False,
        enqueue=True,
        retention=3,
        rotation="300 KB",
        encoding="utf-8",
    )


# 移除并关闭录制日志文件 sink：loguru remove() 会先 flush enqueue 队列再关闭文件句柄，
# 保证归档改名前内容完整落盘。幂等：sink 未注册（GUI 父进程 / 配置关闭 / 已移除）时为 no-op。
def remove_file_sinks() -> None:
    global _streamget_sink_id, _playurl_sink_id
    if _streamget_sink_id is not None:
        try:
            logger.remove(_streamget_sink_id)
        except ValueError:
            # handler 已不存在（如调用方执行过 logger.remove()）：id 失效，忽略即可
            pass
        _streamget_sink_id = None
    if _playurl_sink_id is not None:
        try:
            logger.remove(_playurl_sink_id)
        except ValueError:
            pass
        _playurl_sink_id = None


# 重新注册录制日志文件 sink（归档改名后恢复日志写入，loguru add() 即创建全新同名文件）。
# 与导入期注册同参数；GUI 父进程或「是否启用日志文件」关闭时不注册。
def add_file_sinks() -> None:
    global _streamget_sink_id, _playurl_sink_id
    if _gui_parent or not _log_to_file:
        return
    if _streamget_sink_id is None:
        _streamget_sink_id = _add_streamget_sink()
    if _playurl_sink_id is None:
        _playurl_sink_id = _add_playurl_sink()


# 读取配置：是否将日志导出到 logs 文件夹
# 注意：logger.py 在 main.py 读取配置之前即被导入（通过 src.utils 传递引入），
# 因此这里直接用 configparser 读取 config.ini，避免依赖 main.py 的执行顺序
# 默认启用日志文件，以保持向后兼容行为
_log_to_file: bool = True
try:
    _cfg_parser = configparser.RawConfigParser()
    _files_read = _cfg_parser.read(f"{script_path}/config/config.ini", encoding="utf-8-sig")
    _log_to_file = _cfg_parser.get("录制设置", "是否启用日志文件(是/否)").strip() != "否"
except configparser.NoSectionError, configparser.NoOptionError:
    # 配置项缺失时保持默认启用（向后兼容）
    pass
except Exception:
    # 任何读取异常都不应影响日志模块初始化
    pass

if _log_to_file:
    if _gui_parent:
        # GUI 父进程：仅写本进程独占的 gui.log（同款轮转/保留策略），
        # 绝不创建录制日志文件 streamget.log / PlayURL.log（原因见 GUI_PARENT_ENV 注释）
        _ = logger.add(
            f"{script_path}/logs/gui.log",
            level="DEBUG",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            serialize=False,
            enqueue=True,
            retention=3,
            rotation="300 KB",
            encoding="utf-8",
        )
    else:
        # DEBUG 级别日志文件（排除 INFO）
        _streamget_sink_id = _add_streamget_sink()

        # INFO 级别日志文件（直播流 URL 等）
        _playurl_sink_id = _add_playurl_sink()
