#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import configparser
import os
import sys

from loguru import logger

__all__ = ["logger", "rebind_console_sink"]


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
    # DEBUG 级别日志文件（排除 INFO）
    _ = logger.add(
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

    # INFO 级别日志文件（直播流 URL 等）
    _ = logger.add(
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
