# -*- coding: utf-8 -*-

import functools
import hashlib
import traceback
from logger import logger
import configparser


def trace_error_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
            error_info = f"错误信息: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
            logger.warning(error_info)
            return []

    return wrapper


def check_md5(file_path):
    """
    计算文件的md5值
    """
    with open(file_path, 'rb') as fp:
        file_md5 = hashlib.md5(fp.read()).hexdigest()
    return file_md5


def dict_to_cookie_str(cookies_dict):
    cookie_str = '; '.join([f"{key}={value}" for key, value in cookies_dict.items()])
    return cookie_str


def read_config_value(file_path, section, key):
    """
    从配置文件中读取指定键的值。

    参数:
    - file_path: 配置文件的路径。
    - section: 部分名称。
    - key: 键名称。

    返回:
    - 键的值，如果部分或键不存在则返回None。
    """
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


def update_config(file_path, section, key, new_value):
    """
    更新配置文件中的键值。

    参数:
    - file_path: 配置文件的路径。
    - section: 要更新的部分名称。
    - key: 要更新的键名称。
    - new_value: 新的键值。
    """
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
