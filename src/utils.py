#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 工具函数模块 - 提供通用工具函数，包括配置文件读写、文件操作、字符串处理等

import functools
import hashlib
import inspect
import json
import os
import random
import re
import shutil
import string
import traceback
import zipfile
from collections import OrderedDict
from collections.abc import Mapping
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar, cast
from urllib.parse import parse_qs, urlparse

# 优先使用 exejs（PyExecJS 的活跃维护继任者），未安装时回退到 PyExecJS
try:
    import exejs as execjs

    ProgramError = execjs.ExejsProgramError
except ImportError:
    import execjs  # type: ignore[no-redef]
    from execjs import ProgramError  # type: ignore[no-redef]

import configparser

from .logger import logger

OptionalStr = str | None
OptionalDict = dict[str, object] | None

# 表情符号匹配模式（模块级编译一次）：原实现在 remove_emojis 内每次调用都拼接 10 段字符串
# 构造约 400 字符的模式再 re.compile——既产生临时字符串分配，又要对长模式串做哈希查表。
# 该函数经 clean_name 被每个房间每轮多次调用（80+ 房间场景下每秒可达数百次），
# 提为模块级常量后省去拼接与编译查表开销，匹配语义完全不变。
_EMOJI_PATTERN = re.compile(
    "["
    + "\U0001f1e0-\U0001f1ff"  # flags (iOS)
    + "\U0001f300-\U0001f5ff"  # symbols & pictographs
    + "\U0001f600-\U0001f64f"  # emoticons
    + "\U0001f680-\U0001f6ff"  # transport & map symbols
    + "\U0001f700-\U0001f77f"  # alchemical symbols
    + "\U0001f780-\U0001f7ff"  # Geometric Shapes Extended
    + "\U0001f800-\U0001f8ff"  # Supplemental Arrows-C
    + "\U0001f900-\U0001f9ff"  # Supplemental Symbols and Pictographs
    + "\U0001fa00-\U0001fa6f"  # Chess Symbols
    + "\U0001fa70-\U0001faff"  # Symbols and Pictographs Extended-A
    + "\U00002702-\U000027b0"  # Dingbats
    + "]+",
    flags=re.UNICODE,
)


class Color:
    # 终端彩色输出常量类
    RED: str = "\033[31m"
    GREEN: str = "\033[32m"
    YELLOW: str = "\033[33m"
    BLUE: str = "\033[34m"
    MAGENTA: str = "\033[35m"
    CYAN: str = "\033[36m"
    WHITE: str = "\033[37m"
    RESET: str = "\033[0m"

    @staticmethod
    def print_colored(text: str, color: str) -> None:
        # 打印彩色文本
        print(f"{color}{text}{Color.RESET}")


P = ParamSpec("P")
R = TypeVar("R")


def _make_trace_error_guard(func: Callable[P, R], fallback: R) -> Callable[P, R]:
    # 错误追踪装饰器的共用实现（支持同步和异步函数）：吞掉异常并返回 fallback，
    # 日志同时标注函数名与兜底值类型，便于定位「错误被伪装成正常结果」的现场
    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            # 异步函数包装器：捕获并记录异常，返回 fallback
            try:
                return cast(R, await func(*args, **kwargs))
            except ProgramError:
                logger.warning("Failed to execute JS code. Please check if the Node.js environment")
                return fallback
            except Exception as e:
                tb = traceback.extract_tb(e.__traceback__) if e.__traceback__ else None
                error_line = tb[-1].lineno if tb else "unknown"
                error_info = (
                    f"message: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
                    f", fallback type: {type(fallback).__name__}"
                )
                logger.error(error_info)
                return fallback

        return cast(Callable[P, R], async_wrapper)

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # 同步函数包装器：捕获并记录异常，返回 fallback
        try:
            return func(*args, **kwargs)
        except ProgramError:
            logger.warning("Failed to execute JS code. Please check if the Node.js environment")
            return fallback
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__) if e.__traceback__ else None
            error_line = tb[-1].lineno if tb else "unknown"
            error_info = (
                f"message: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
                f", fallback type: {type(fallback).__name__}"
            )
            logger.error(error_info)
            return fallback

    return wrapper


def trace_error_decorator(func: Callable[P, R]) -> Callable[P, R]:
    # 错误追踪装饰器：吞掉异常并返回 {"is_live": False}。绝大多数被装饰函数（各平台
    # get_xxx_stream_data）返回含 is_live 键的 dict，调用方据其判定未开播。
    # 返回 str/tuple/None 的函数必须改用 trace_error_decorator_or_none，否则调用方会
    # 静默拿到一个 dict，把错误伪装成正常结果。
    return _make_trace_error_guard(func, cast(R, {"is_live": False}))


def trace_error_decorator_or_none(func: Callable[P, R]) -> Callable[P, R]:
    # trace_error_decorator 的类型匹配变体：出错返回 None，供返回 str/tuple 等类型的
    # 函数（login_*、get_*_info、get_*_tk）使用，调用方按 falsy 处理失败。
    return _make_trace_error_guard(func, cast(R, None))


def check_md5(file_path: str | Path) -> str:
    # 计算文件的 MD5 值
    with open(file_path, "rb") as fp:
        file_md5 = hashlib.md5(fp.read()).hexdigest()
    return file_md5


def unzip_file(zip_path: str | Path, extract_to: str | Path, delete: bool = True) -> None:
    # 解压 ZIP 文件到指定目录（含 Zip Slip 目录穿越校验）。
    # node_install / ffmpeg_install 共用同一份实现——原先两处逐字重复，
    # 任一处打安全补丁都会漏掉另一处
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)

    extract_root = os.path.realpath(extract_to)
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        # 防止 Zip Slip 目录穿越攻击：校验每个成员解压后的真实路径
        for member in zip_ref.namelist():
            member_path = os.path.realpath(os.path.join(extract_root, member))
            if not member_path.startswith(extract_root + os.sep) and member_path != extract_root:
                raise ValueError(f"Unsafe path in zip file: {member}")
        zip_ref.extractall(extract_to)

    if delete and os.path.exists(zip_path):
        os.remove(zip_path)


def dict_to_cookie_str(cookies_dict: Mapping[str, object]) -> str:
    # 将 cookie 字典转换为字符串格式
    cookie_str = "; ".join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


def read_config_value(file_path: str | Path, section: str, key: str) -> str | None:
    # 从配置文件读取指定配置项的值
    # 关闭插值：值中的裸 %（如 cookie、时间格式）不应触发 InterpolationSyntaxError
    config = configparser.ConfigParser(interpolation=None)

    try:
        _ = config.read(file_path, encoding="utf-8-sig")
    except Exception as e:
        print(f"Error occurred while reading the configuration file: {e}")
        return None

    if section in config:
        if key in config[section]:
            return config[section][key]
        else:
            print(f"Key [{key}] does not exist in section [{section}].")
    else:
        print(f"Section [{section}] does not exist in the file.")

    return None


def update_config(file_path: str | Path, section: str, key: str, new_value: str) -> None:
    # 更新配置文件中指定配置项的值
    # 关闭插值以避免 cookie 等含 % 的值被 BasicInterpolation 转义/反解析
    config = configparser.ConfigParser(interpolation=None)

    try:
        _ = config.read(file_path, encoding="utf-8-sig")
    except Exception as e:
        print(f"An error occurred while reading the configuration file: {e}")
        return

    if section not in config:
        print(f"Section [{section}] does not exist in the file.")
        return

    config[section][key] = new_value

    try:
        with open(file_path, "w", encoding="utf-8-sig") as configfile:
            config.write(configfile)
        print(f"The value of {key} under [{section}] in the configuration file has been updated.")
    except Exception as e:
        print(f"Error occurred while writing to the configuration file: {e}")


def get_file_paths(directory: str) -> list[str]:
    # 递归获取指定目录下所有文件的绝对路径
    file_paths: list[str] = []
    for root, _, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths


def remove_emojis(text: str, replace_text: str = "") -> str:
    # 从文本中移除表情符号（模式为模块级常量 _EMOJI_PATTERN，此处不再重复编译）
    return _EMOJI_PATTERN.sub(replace_text, text)


def remove_duplicate_lines(file_path: str | Path) -> None:
    # 移除文件中的重复行
    unique_lines: OrderedDict[str, None] = OrderedDict()
    text_encoding = "utf-8-sig"
    try:
        with open(file_path, "r", encoding=text_encoding) as input_file:
            for line in input_file:
                unique_lines[line.strip()] = None
    except UnicodeDecodeError:
        # 非 UTF-8 编码（如 GBK/UTF-16）时回退到系统默认编码读取
        with open(file_path, "r", encoding=None) as input_file:
            for line in input_file:
                unique_lines[line.strip()] = None
    with open(file_path, "w", encoding=text_encoding) as output_file:
        for line in unique_lines:
            _ = output_file.write(line + "\n")


def check_disk_capacity(file_path: str | Path, show: bool = False) -> float:
    # 检查指定文件所在磁盘的剩余空间（GB）
    absolute_path = os.path.abspath(file_path)
    directory = os.path.dirname(absolute_path)
    disk_usage = shutil.disk_usage(directory)
    disk_root = Path(directory).anchor
    free_space_gb = disk_usage.free / (1024**3)
    if show:
        print(
            f"{disk_root} Total: {disk_usage.total / (1024 ** 3):.2f} GB "
            + f"Used: {disk_usage.used / (1024 ** 3):.2f} GB "
            + f"Free: {free_space_gb:.2f} GB\n"
        )
    return free_space_gb


def handle_proxy_addr(proxy_addr: str | None) -> str | None:
    # 处理代理地址，自动添加 http 前缀
    # 已有协议前缀（http/https/socks 等）的地址不再二次添加
    if proxy_addr:
        if "://" not in proxy_addr:
            proxy_addr = "http://" + proxy_addr
    else:
        proxy_addr = None
    return proxy_addr


def generate_random_string(length: int) -> str:
    # 生成指定长度的随机字符串（大写字母 + 数字）
    characters = string.ascii_uppercase + string.digits
    random_string = "".join(random.choices(characters, k=length))
    return random_string


def jsonp_to_json(jsonp_str: str) -> OptionalDict:
    # 将 JSONP 格式字符串转换为 JSON 对象
    # re.DOTALL 支持跨行内容；回调名允许含点号（如 a.b(...)）
    pattern = r"([\w.]+)\((.*)\);?\s*$"
    match = re.search(pattern, jsonp_str, re.DOTALL)

    if match:
        _, json_str = match.groups()
        json_obj: dict[str, object] = cast(dict[str, object], json.loads(json_str))
        return json_obj
    else:
        raise Exception("No JSON data found in JSONP response.")


def replace_url(file_path: str | Path, old: str, new: str) -> None:
    # 替换文件中的 URL
    # 逐行匹配整行内容，避免子串替换误伤包含相同 URL 片段的其他行
    with open(file_path, "r", encoding="utf-8-sig") as f:
        lines = f.readlines()
    with open(file_path, "w", encoding="utf-8-sig") as f:
        for line in lines:
            if line.strip() == old:
                _ = f.write(new + "\n")
            elif old in line:
                _ = f.write(line.replace(old, new))
            else:
                _ = f.write(line)


def get_query_params(url: str, param_name: OptionalStr) -> dict[str, list[str]] | list[str]:
    # 从 URL 中获取查询参数
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)

    if param_name is None:
        return query_params
    else:
        values = query_params.get(param_name, [])
        return values
