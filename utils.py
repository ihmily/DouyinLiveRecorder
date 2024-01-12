# -*- coding: utf-8 -*-

import functools
import hashlib
import traceback
from logger import logger


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
