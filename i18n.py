# -*- coding: utf-8 -*-
# 国际化（i18n）模块 - 基于 gettext 的多语言支持系统

import builtins
import gettext
import inspect
import os
import sys
from pathlib import Path
from typing import Callable, TextIO


def init_gettext(locale_dir: str | Path, locale_name: str) -> Callable[[str], str]:
    # 初始化 gettext 翻译环境。
    # 不再写死 LANG 环境变量：".utf8" 后缀在 macOS 上不是合法 locale（应为 .UTF-8），
    # 且该变量会经 gui.py 的 env=os.environ.copy() 传染整个录制子进程树，
    # 导致子进程 locale.setlocale(LC_ALL, '') 抛 locale.Error。
    _ = gettext.bindtextdomain(locale_name, locale_dir)
    _ = gettext.textdomain(locale_name)
    return gettext.gettext


# 检测执行目录，支持打包后 (_internal) 和源码两种运行方式
# 优先基于本模块文件所在目录定位，避免 sys.argv[0] 在打包/-m 运行时被误解析；
# 冻结运行时模块可能位于 PYZ 中，__file__ 指向 PYZ 目录，需回退到 sys._MEIPASS。
module_dir = Path(__file__).resolve().parent
_meipass = getattr(sys, "_MEIPASS", None)
if os.path.exists(module_dir / "_internal/i18n"):
    locale_path = module_dir / "_internal/i18n"  # PyInstaller 打包版位置
elif _meipass and os.path.exists(Path(_meipass) / "i18n"):
    locale_path = Path(_meipass) / "i18n"  # 冻结运行 data 目录
else:
    locale_path = module_dir / "i18n"  # 源码运行位置
_tr = init_gettext(locale_path, "zh_CN")  # 默认中文
original_print = builtins.print  # 保存原始 print 函数

# 需要翻译的源码目录：src/ 包以及项目根（main.py 等顶层脚本）
# 统一规范化路径分隔符，兼容 Windows 下 sys._getframe 返回 / 而 os.path.realpath 返回 \ 的情况
_project_root = os.path.normpath(str(module_dir))


def _should_translate(caller_file: str) -> bool:
    # 判断调用者文件是否来自需要翻译的源码目录
    caller_norm = os.path.normpath(caller_file)
    # 在项目根目录下即为项目源码（含 src/ 及 main.py/web.py/gui.py 等）
    return caller_norm.startswith(_project_root)


def translated_print(
    *args: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    # 包装后的 print 函数，自动翻译 src/ 和项目根目录下的输出
    try:
        frame = inspect.currentframe()
        caller_file = frame.f_back.f_code.co_filename if frame and frame.f_back else ""
        should_translate = _should_translate(caller_file)
    except (ValueError, AttributeError):
        should_translate = False

    translated_args: list[str] = []
    for arg in args:
        text = str(arg)
        if should_translate:
            text = _tr(text)  # 翻译文本
        translated_args.append(text)

    original_print(sep.join(translated_args), sep=sep, end=end, file=file, flush=flush)  # 调用原始 print
