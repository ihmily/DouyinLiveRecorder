import os
import sys
import gettext
import inspect
import builtins
from pathlib import Path


def init_gettext(locale_dir, locale_name):
    gettext.bindtextdomain('zh_CN', locale_dir)
    gettext.textdomain('zh_CN')
    os.environ['LANG'] = f'{locale_name}.utf8'
    return gettext.gettext


execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
_tr = init_gettext(Path(execute_dir) / 'i18n', 'zh_CN')
original_print = builtins.print
package_name = 'douyinliverecorder'


def translated_print(*args, **kwargs):
    for arg in args:
        if package_name in inspect.stack()[1].filename:
            translated_arg = _tr(str(arg))
        else:
            translated_arg = str(arg)
        original_print(translated_arg, **kwargs)



