import os
import sys
import gettext
import builtins
from pathlib import Path


def init_gettext(locale_dir: str | Path, locale_name: str):
    gettext.bindtextdomain(locale_name, locale_dir)
    gettext.textdomain(locale_name)
    os.environ['LANG'] = f'{locale_name}.utf8'
    return gettext.gettext


execute_dir = os.path.split(os.path.realpath(sys.argv[0]))[0]
if os.path.exists(Path(execute_dir) / '_internal/i18n'):
    locale_path = Path(execute_dir) / '_internal/i18n'
else:
    locale_path = Path(execute_dir) / 'i18n'
_tr = init_gettext(locale_path, 'zh_CN')
original_print = builtins.print
package_name = 'src'


def translated_print(*args, **kwargs):
    try:
        caller_file = sys._getframe(1).f_code.co_filename
        should_translate = package_name in caller_file
    except (ValueError, AttributeError):
        should_translate = False

    sep = kwargs.get('sep', ' ')
    translated_args = []
    for arg in args:
        text = str(arg)
        if should_translate:
            text = _tr(text)
        translated_args.append(text)

    original_print(sep.join(translated_args), **kwargs)
