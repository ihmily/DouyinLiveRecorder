# -*- coding: utf-8 -*-
# 国际化（i18n）模块 - 多语言、多格式（gettext/.mo、JSON、YAML）翻译支持系统
#
# 语言目录（locale_path）布局与加载优先级（对每个语言依次探测，首个命中即用）：
#   1. <locale_path>/<lang>/LC_MESSAGES/<lang>.mo   # gettext 编译产物（zh_CN 现行方案）
#   2. <locale_path>/<lang>.json                    # JSON 目录：{"原文": "译文", ...}
#   3. <locale_path>/<lang>.yaml                    # YAML 目录：与 JSON 同构的键值映射
# 三种格式均为「原文 → 译文」的扁平字符串映射，加载后统一为 dict，行为一致。
#
# 运行时切换：set_language(lang) 热替换翻译函数（_tr），后续 print/logger 输出
# 即时使用新语言，无需重启进程（Web 面板/GUI 的即时切换语言功能依赖此入口）。
#
# 语言解析：resolve_language(value) 为配置键 language 的统一解析入口——
# 空 → 系统语言（detect_system_language）；不可识别或语言目录文件缺失 → en_US 回退。

import builtins
import gettext
import inspect
import json
import locale
import os
import sys
from pathlib import Path
from typing import Any, Callable, TextIO

# YAML 为可选依赖：缺失时仅损失 .yaml 目录支持，JSON/gettext 不受影响。
# mypy 默认配置要求显式 stubs（types-PyYAML），但项目把 PyYAML 视为可选，
# 故在此忽略"未安装/无类型存根"提示；运行时经下方 try/except 优雅降级。
try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - 环境相关分支
    yaml = None  # type: ignore[assignment]

# 支持的语言（有序；键为规范语言码，值为界面显示名，供 GUI/Web 语言选择器使用）
SUPPORTED_LANGUAGES: dict[str, str] = {
    "zh_CN": "简体中文 (Simplified Chinese)",
    "en_US": "English (US)",
    "en_GB": "English (UK)",
    "zh_TW": "繁體中文 (Traditional Chinese)",
}

# 默认语言（源码输出以中文为主、部分英文常量串，缺失翻译时回退恒等映射）
DEFAULT_LANGUAGE = "zh_CN"

# 回退语言：配置键值不可识别、或对应语言的目录文件缺失时，统一回退显示该语言
FALLBACK_LANGUAGE = "en_US"

# 语言别名归一化表：配置文件/浏览器/历史键值里的各种写法 → 规范语言码。
# 键统一为「小写 + 连字符」形态（normalize_language 会把下划线归一为连字符后查表）
_LANGUAGE_ALIASES: dict[str, str] = {
    "zh-cn": "zh_CN",
    "zh": "zh_CN",
    "zh-hans": "zh_CN",
    "zh-sg": "zh_CN",
    "en": "en_US",
    "en-us": "en_US",
    "en-gb": "en_GB",
    "zh-tw": "zh_TW",
    "zh-hant": "zh_TW",
    "zh-hk": "zh_TW",
    "zh-mo": "zh_TW",
}


# 判断语言标识是否可识别（受支持码/已知别名/带编码后缀变体）；不回退默认值
def is_recognized_language(value: str | None) -> bool:
    # 可识别 = 精确匹配规范码、别名表命中、或带编码后缀的前缀命中
    if not value:
        return False
    v = value.strip()
    if v in SUPPORTED_LANGUAGES:
        return True
    low = v.lower().replace("_", "-")
    if low in _LANGUAGE_ALIASES:
        return True
    prefix = low.split(".")[0].split("@")[0]
    if prefix in _LANGUAGE_ALIASES:
        return True
    return prefix.replace("-", "_") in SUPPORTED_LANGUAGES


# 把任意语言标识归一化为受支持的规范语言码；无法识别时回退默认语言
def normalize_language(value: str | None) -> str:
    # 归一化规则：精确匹配 → 别名表（小写/连字符）→ 前缀匹配（如 zh_CN.UTF-8）→ 默认
    if not value:
        return DEFAULT_LANGUAGE
    v = value.strip()
    if v in SUPPORTED_LANGUAGES:
        return v
    low = v.lower().replace("_", "-")
    if low in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[low]
    # 前缀匹配：zh_CN.UTF-8 / en_US.UTF-8 等带编码后缀的写法
    prefix = low.split(".")[0].split("@")[0]
    if prefix in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[prefix]
    if prefix.replace("-", "_") in SUPPORTED_LANGUAGES:
        return prefix.replace("-", "_")
    return DEFAULT_LANGUAGE


# 检测系统语言，失败返回 None（不抛异常）：
#   1) 环境变量 LANGUAGE / LC_ALL / LC_MESSAGES / LANG（LANGUAGE 为冒号分隔列表，
#      取首项；C / POSIX 视为未设置）
#   2) Windows：用户默认 UI 语言（LANGID 经 locale.windows_locale 映射为 zh_CN 等代码）
#   3) POSIX：locale.getlocale()（进程已 setlocale 时有效；C / POSIX 结果同样视为未设置，
#      实测 Linux CI 的 LANG=C 进程里 getlocale() 返回 ('C', None)，不拦会原样泄漏 "C"）
def detect_system_language() -> str | None:
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "").strip()
        if value and value.upper() not in ("C", "POSIX"):
            return value.split(":")[0].strip() or None
    if sys.platform == "win32":
        win_lang = _windows_ui_language()
        if win_lang:
            return win_lang
    try:
        current = locale.getlocale()[0]
    except ValueError:
        current = None
    if current and current.upper() not in ("C", "POSIX"):
        return current
    return None


# Windows 用户默认 UI 语言代码（如 zh_CN / en_US）；非 Windows 或调用失败返回 None
def _windows_ui_language() -> str | None:
    # 平台门控放函数体首行：WinDLL 仅存在于 Windows typeshed，裸引用会让 mypy 在
    # 非 win32 平台（CI 的 linux runner）报 attr-defined（对齐 src/web_tray.py 的门控惯例）
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        # WinDLL 而非 windll：与 web.py 的 Windows API 调用惯例一致（显式声明返回类型）
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetUserDefaultUILanguage.restype = ctypes.c_uint16
        lang_id = int(kernel32.GetUserDefaultUILanguage())
    except Exception:
        return None
    return locale.windows_locale.get(lang_id)


# 判断某语言是否存在可加载的翻译目录文件（.mo / .json / .yaml 任一存在即可）
def has_catalog(lang: str) -> bool:
    base = Path(locale_path)
    return (
        (base / lang / "LC_MESSAGES" / f"{lang}.mo").is_file()
        or (base / f"{lang}.json").is_file()
        or (base / f"{lang}.yaml").is_file()
    )


# 把配置语言键值解析为最终显示语言（main.py 启动初始化/热切换与 GUI 初始解析的统一入口）：
#   空 / 缺失         → 系统语言（检测结果不可用或无对应目录时回退 FALLBACK_LANGUAGE）
#   可识别且有目录    → 该语言（别名归一化，如 zh-cn → zh_CN）
#   不可识别 / 无目录 → FALLBACK_LANGUAGE（en_US）
def resolve_language(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        system_lang = detect_system_language()
        if system_lang and is_recognized_language(system_lang):
            normalized = normalize_language(system_lang)
            if has_catalog(normalized):
                return normalized
        return FALLBACK_LANGUAGE
    if not is_recognized_language(raw):
        return FALLBACK_LANGUAGE
    normalized = normalize_language(raw)
    return normalized if has_catalog(normalized) else FALLBACK_LANGUAGE


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

# 需要翻译的源码目录：src/ 包以及项目根（main.py 等顶层脚本）
# 统一规范化路径分隔符，兼容 Windows 下 sys._getframe 返回 / 而 os.path.realpath 返回 \ 的情况
_project_root = os.path.normpath(str(module_dir))


# 判断调用者文件是否位于需要翻译的项目源码目录下。
def _should_translate(caller_file: str) -> bool:
    # 判断调用者文件是否来自需要翻译的源码目录
    caller_norm = os.path.normpath(caller_file)
    # 在项目根目录下即为项目源码（含 src/ 及 main.py/web.py/gui.py 等）
    return caller_norm.startswith(_project_root)


# 从 JSON 文件加载「原文 → 译文」映射；文件不存在或解析失败时返回 None
def _load_json_catalog(path: Path) -> dict[str, str] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None
    if not isinstance(data, dict):
        return None
    # 仅保留 str→str 条目，其余类型跳过（容忍手工编辑出的杂项值）
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


# 从 YAML 文件加载「原文 → 译文」映射；未安装 pyyaml / 文件不存在 / 解析失败时返回 None
def _load_yaml_catalog(path: Path) -> dict[str, str] | None:
    if yaml is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # yaml.YAMLError（ParserError/ScannerError 等）不是 OSError/ValueError 子类，
    # 不捕获则损坏的 yaml 会让 set_language 抛异常（Web 语言切换接口直接 500）
    except OSError, ValueError, yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}


# 从 gettext .mo 编译产物加载「原文 → 译文」映射；文件不存在时返回 None
def _load_mo_catalog(locale_dir: str | Path, lang: str) -> dict[str, str] | None:
    mo_path = Path(locale_dir) / lang / "LC_MESSAGES" / f"{lang}.mo"
    if not mo_path.is_file():
        return None
    try:
        # fallback=False：文件存在但损坏时抛异常，由调用方降级到下一格式
        translation = gettext.translation(lang, str(locale_dir), languages=[lang], fallback=False)
    except Exception:
        return None
    # 直读 .mo 条目表：GNUTranslations._catalog 即 {msgid: msgstr}（含空串头，剔除）
    catalog = dict(getattr(translation, "_catalog", {}))
    catalog.pop("", None)
    return {k: v for k, v in catalog.items() if isinstance(k, str)}


# 按优先级加载某语言的翻译目录：gettext .mo → JSON → YAML；全缺失时返回 None
def _load_translations(locale_dir: str | Path, lang: str) -> dict[str, str] | None:
    base = Path(locale_dir)
    mo = _load_mo_catalog(base, lang)
    if mo is not None:
        return mo
    json_catalog = _load_json_catalog(base / f"{lang}.json")
    if json_catalog is not None:
        return json_catalog
    return _load_yaml_catalog(base / f"{lang}.yaml")


# 初始化 gettext 翻译环境，返回绑定域与目录的 gettext 函数。
def init_gettext(locale_dir: str | Path, locale_name: str) -> Callable[[str], str]:
    # 初始化 gettext 翻译环境。
    # 不再写死 LANG 环境变量：".utf8" 后缀在 macOS 上不是合法 locale（应为 .UTF-8），
    # 且该变量会经 gui.py 的 env=os.environ.copy() 传染整个录制子进程树，
    # 导致子进程 locale.setlocale(LC_ALL, '') 抛 locale.Error。
    #
    # 同时不再依赖 gettext.gettext 的全局查找：那会按 LANGUAGE/LC_ALL/LANG 环境变量
    # 推断语言目录，而 Windows 客户端普遍不设置这些变量（本仓库又未随包分发 .mo 的
    # 回退查找路径），结果 zh_CN.mo 永远查不到、翻译静默失效。
    # 这里显式指定 languages=[locale_name] 直接加载 locale_dir 下对应 .mo，
    # 缺文件时回退恒等映射，行为与之前一致。
    _ = gettext.bindtextdomain(locale_name, locale_dir)
    _ = gettext.textdomain(locale_name)
    translation = gettext.translation(locale_name, locale_dir, languages=[locale_name], fallback=True)
    return translation.gettext


# 构建某语言的翻译函数：加载翻译目录，命中返回译文、未命中回退原文
def _build_translator(locale_dir: str | Path, lang: str) -> Callable[[str], str]:
    catalog = _load_translations(locale_dir, lang)
    if not catalog:
        return lambda text: text
    return lambda text: catalog.get(text, text)


# 当前语言（模块级状态；set_language 热切换）
_current_language: str = DEFAULT_LANGUAGE

# 当前翻译函数：所有输出翻译统一经此引用（translated_print 与外部按需取用）
_tr: Callable[[str], str] = _build_translator(locale_path, DEFAULT_LANGUAGE)
original_print = builtins.print  # 保存原始 print 函数


# 切换当前语言：归一化 → 加载翻译目录 → 热替换 _tr；语言不可用或目录缺失时回退恒等映射。
# 返回切换是否成功（归一化后语言即视为成功；目录缺失只影响译文，不视为失败）
def set_language(lang: str | None) -> bool:
    global _current_language, _tr
    normalized = normalize_language(lang)
    _current_language = normalized
    _tr = _build_translator(locale_path, normalized)
    return True


# 返回当前语言规范码
def get_language() -> str:
    return _current_language


# 返回受支持的语言映射（键为语言码、值为显示名），供选择器渲染
def available_languages() -> dict[str, str]:
    return dict(SUPPORTED_LANGUAGES)


# 包装 print：对来自源码目录的输出自动翻译后再打印。
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
    except ValueError, AttributeError:
        should_translate = False

    translated_args: list[str] = []
    for arg in args:
        text = str(arg)
        if should_translate:
            text = _tr(text)  # 翻译文本
        translated_args.append(text)

    original_print(sep.join(translated_args), sep=sep, end=end, file=file, flush=flush)  # 调用原始 print
