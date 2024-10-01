# -*- coding: utf-8 -*-

import os
import functools
import hashlib
import traceback
from typing import Union, Any

from .logger import logger
import configparser


def trace_error_decorator(func: callable) -> callable:
    @functools.wraps(func)
    def wrapper(*args: list, **kwargs: dict) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
            error_info = f"错误信息: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
            logger.error(error_info)
            return []

    return wrapper


def check_md5(file_path: str) -> str:
    with open(file_path, 'rb') as fp:
        file_md5 = hashlib.md5(fp.read()).hexdigest()
    return file_md5


def dict_to_cookie_str(cookies_dict) -> str:
    cookie_str = '; '.join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


def read_config_value(file_path, section, key) -> Union[str, None]:
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


def update_config(file_path, section, key, new_value) -> None:

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


def get_file_paths(directory) -> list:
    file_paths = []
    for root, dirs, files in os.walk(directory):
        for file in files:
            file_paths.append(os.path.join(root, file))
    return file_paths
