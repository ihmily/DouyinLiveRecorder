# -*- coding: utf-8 -*-
# 国际化（i18n）模块 - 基于 gettext 的多语言支持系统

import os
import sys
import gettext
import builtins
from pathlib import Path


def init_gettext(locale_dir: str | Path, locale_name: str):
    # 初始化 gettext 翻译环境
    gettext.bindtextdomain(locale_name, locale_dir)
    gettext.textdomain(locale_name)
    os.environ['LANG'] = f'{locale_name}.utf8'
    return gettext.gettext


# 检测执行目录，支持打包后 (_internal) 和源码两种运行方式
execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
if os.path.exists(Path(execute_dir) / '_internal/i18n'):
    locale_path = Path(execute_dir) / '_internal/i18n'  # PyInstaller 打包版位置
else:
    locale_path = Path(execute_dir) / 'i18n'  # 源码运行位置
_tr = init_gettext(locale_path, 'zh_CN')  # 默认中文
original_print = builtins.print  # 保存原始 print 函数
package_name = 'src'  # 仅翻译 src 包下的代码输出


def translated_print(*args, **kwargs):
    # 包装后的 print 函数，自动翻译 src 目录下的输出
    try:
        caller_file = sys._getframe(1).f_code.co_filename  # 获取上一层调用者的文件
        should_translate = package_name in caller_file  # 检查是否来自 src 目录
    except (ValueError, AttributeError):
        should_translate = False

    sep = kwargs.get('sep', ' ')
    translated_args = []
    for arg in args:
        text = str(arg)
        if should_translate:
            text = _tr(text)  # 翻译文本
        translated_args.append(text)

    original_print(sep.join(translated_args), **kwargs)  # 调用原始 print
