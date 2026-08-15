#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 日志配置模块 - 基于 Loguru，控制台彩色输出 + 日志文件轮转存储

import configparser
import os
import sys

from loguru import logger

__all__ = ["logger"]


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

# 日志异步入队开关：enqueue=True 依赖 multiprocessing.SimpleQueue（Windows 命名管道），
# 受限环境（测试/CI 沙箱）中可能阻塞或失败；允许通过环境变量禁用（仅影响性能，不影响行为）。
_log_enqueue = os.environ.get("DOUYIN_LOG_NO_ENQUEUE", "").strip().lower() not in ("1", "true", "yes")

# 控制台日志格式（彩色）
custom_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> - <level>{message}</level>"

# 添加控制台输出（无论是否启用日志文件，控制台输出始终保留）
_ = logger.add(sink=sys.stderr, format=custom_format, level="DEBUG", colorize=True, enqueue=_log_enqueue)

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
except (configparser.NoSectionError, configparser.NoOptionError):
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
        enqueue=_log_enqueue,
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
        enqueue=_log_enqueue,
        retention=3,
        rotation="300 KB",
        encoding="utf-8",
    )
