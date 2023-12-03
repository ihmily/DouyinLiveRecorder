# -*- coding: utf-8 -*-

import functools
import hashlib
import logging
import os
import traceback

# --------------------------log日志-------------------------------------
# 创建一个logger
logger = logging.getLogger('record_logger')
logger.setLevel(logging.INFO)
# 创建一个handler，用于写入日志文件
if not os.path.exists("./log"):
    os.makedirs("./log")
fh = logging.FileHandler("./log/错误日志文件.log", encoding="utf-8-sig", mode="a")
fh.setLevel(logging.WARNING)
# 定义handler的输出格式
formatter = logging.Formatter('%(asctime)s - %(message)s')
fh.setFormatter(formatter)
# 给logger添加handler
logger.addHandler(fh)


def trace_error_decorator(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_line = traceback.extract_tb(e.__traceback__)[-1].lineno
            error_info = f"错误信息: type: {type(e).__name__}, {str(e)} in function {func.__name__} at line: {error_line}"
            print(error_info)
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
