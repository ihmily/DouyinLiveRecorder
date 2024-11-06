# -*- coding: utf-8 -*-

import os
import shutil
from pathlib import Path
import functools
import hashlib
import re
import traceback
from typing import Any
from collections import OrderedDict
import execjs
from .logger import logger
import configparser


def trace_error_decorator(func: callable) -> callable:
    @functools.wraps(func)
    def wrapper(*args: list, **kwargs: dict) -> Any:
        try:
            return func(*args, **kwargs)
        except execjs.ProgramError:
            logger.warning('Failed to execute JS code. Please check if the Node.js environment')
        except Exception as e:
            error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
            error_info = f"错误信息: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
            logger.error(error_info)
            return []

    return wrapper


def check_md5(file_path: str | Path) -> str:
    with open(file_path, 'rb') as fp:
        file_md5 = hashlib.md5(fp.read()).hexdigest()
    return file_md5


def dict_to_cookie_str(cookies_dict: dict) -> str:
    cookie_str = '; '.join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


def read_config_value(file_path: str | Path, section: str, key: str) -> str | None:
    config = configparser.ConfigParser()

    try:
        config.read(file_path, encoding='utf-8-sig')
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return None

    if section in config:
        if key in config[section]:
            return config[section][key]
        else:
            print(f"键[{key}]不存在于部分[{section}]中。")
    else:
        print(f"部分[{section}]不存在于文件中。")

    return None


def update_config(file_path: str | Path, section: str, key: str, new_value: str) -> None:
    config = configparser.ConfigParser()

    try:
        config.read(file_path, encoding='utf-8-sig')
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return

    if section not in config:
        print(f"部分[{section}]不存在于文件中。")
        return

    # 转义%字符
    escaped_value = new_value.replace('%', '%%')
    config[section][key] = escaped_value

    try:
        with open(file_path, 'w', encoding='utf-8-sig') as configfile:
            config.write(configfile)
        print(f"配置文件中[{section}]下的{key}的值已更新")
    except Exception as e:
        print(f"写入配置文件时出错: {e}")


def get_file_paths(directory: str) -> list:
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths


def remove_emojis(text: str, replace_text: str = '') -> str:
    emoji_pattern = re.compile(
        "["
        "\U0001F1E0-\U0001F1FF"  # flags (iOS)
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F700-\U0001F77F"  # alchemical symbols
        "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
        "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
        "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
        "\U0001FA00-\U0001FA6F"  # Chess Symbols
        "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
        "\U00002702-\U000027B0"  # Dingbats
        "]+",
        flags=re.UNICODE
    )
    return emoji_pattern.sub(replace_text, text)


def remove_duplicate_lines(file_path: str | Path) -> None:
    unique_lines = OrderedDict()
    text_encoding = 'utf-8-sig'
    with open(file_path, 'r', encoding=text_encoding) as input_file:
        for line in input_file:
            unique_lines[line.strip()] = None
    with open(file_path, 'w', encoding=text_encoding) as output_file:
        for line in unique_lines:
            output_file.write(line + '\n')


def check_disk_capacity(file_path: str | Path, show: bool = False) -> float:
    absolute_path = os.path.abspath(file_path)
    directory = os.path.dirname(absolute_path)
    disk_usage = shutil.disk_usage(directory)
    disk_root = Path(directory).anchor
    free_space_gb = disk_usage.free / (1024 ** 3)
    if show:
        print(f"{disk_root} Total: {disk_usage.total / (1024 ** 3):.2f} GB "
              f"Used: {disk_usage.used / (1024 ** 3):.2f} GB "
              f"Free: {free_space_gb:.2f} GB")
    return free_space_gb
