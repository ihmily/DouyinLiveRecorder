# -*- coding: utf-8 -*-
# src/ui_fonts.py — GUI 字体自选：偏好持久化、可用字体枚举与私有字体装载。
#
# 与 ui_theme / ui_scale 同一套约定：偏好落在 config.ini [GUI] 段、读写经
# src/web_config.update_or_append_config_line（行级替换 + 缺节补建 + 原子写），
# **刻意不用** configparser 覆写整文件（会把用户手写注释连带冲掉）。
#
# [为什么禁 woff2] Tk 在 Windows 上经 GDI 取字体，只认 SFNT 容器（.ttf/.otf/.ttc），
# woff2 是为其设计的传输格式、需解压后才能交给 GDI。引入解压依赖只为收尾一个 GUI
# 下拉框不划算，故导入环节直接把 woff2 挡在门外并给出明确原因——比「选了没反应」
# 好。用户在浏览器/系统里装好的字体（含 woff2 转 ttf 后的成品）只要在系统字体表里
# 出现，就能从这里选中。
#
# [为什么写「family 名」而不是文件路径到 Tk] Tk 的字号单位是点、字体标识
# 是 family 名（-font 字符串的三元组首项）。把文件注册成进程私有字体后，GDI 会把它
# 并入系统字体枚举，Tk 就能按 family 名取到它；此后 Fonts 侧的切换只有一次
# configure(family=...)，不涉及任何路径解析。
#
# [回退策略] Tk 的 family 名不被识别时**静默回退**到默认字体族（不报错、不弹窗、
# 也不存在 font-display 那样的异步加载期——GDI 注册是同步的）。这条既是优点
# （不会出现 FOIT/FOUT 闪烁）也是坑（选错了看不出来），故本模块要求调用方在
# 「注册后查 family 是否真的进入 Tk 的 families()」才允许选中——这是唯一的鉴别手段。

import os
import shutil
import struct
import sys
from pathlib import Path
from tkinter import font as tkfont
from typing import Any, Final

import i18n
from src.config_read import tolerant_config_parser
from src.logger import logger
from src.web_config import update_or_append_config_line

# 持久化落点：config.ini [GUI] gui_font（family 名或空 = 随系统默认）、
# gui_font_file（自定义字体文件路径，空 = 只用系统字体）。
GUI_SECTION: Final[str] = "GUI"
FONT_KEY: Final[str] = "gui_font"
FONT_FILE_KEY: Final[str] = "gui_font_file"

# 自定义字体的本地存放目录（相对 app_root）。
# [为什么必须复制一份而不是直接用原路径] 用户导完之后删掉临时字体是常态，
# 直接引用会造成「下次启动整窗回落到默认字体」这种看起来像 bug 的现象。
FONT_STORE_DIRNAME: Final[str] = "fonts"
FONT_STORE_RELPATH: Final[str] = os.path.join("config", FONT_STORE_DIRNAME)

# 接受导入的字体容器扩展名（SFNT：TrueType / OpenType / 字体集合）。
SUPPORTED_FONT_SUFFIXES: Final[tuple[str, ...]] = (".ttf", ".otf", ".ttc")
# 明确拒绝的格式：给用户一句能听懂的解释，而不是「不支持该文件」。
REJECTED_FONT_SUFFIXES: Final[tuple[str, ...]] = (".woff", ".woff2", ".eot")

# 预设字体候选（按优先级）：Tk 认不出或缺字家庭的会被 available_families() 过滤掉，
# 因此这里可以放心写上「目标机器大概率没有」的名字（macOS / Linux 的 CJK 字体）。
# 每项语义：同类中的首选在前，命中第一个即可停止——避免用户面对 8 个差不多名字。
PRESET_FAMILY_GROUPS: Final[tuple[tuple[str, ...], ...]] = (
    # Windows 现代 UI 黑体（默认就是这个）
    ("Microsoft YaHei UI", "Microsoft YaHei", "微软雅黑"),
    # 开源思源/Noto 系列（Linux 与安装了该字体的 Windows）
    ("Noto Sans CJK SC", "Source Han Sans SC", "思源黑体"),
    # macOS 中文 UI 字体
    ("PingFang SC", "苹方-简"),
    # Windows 传统衬线/黑体（宋体匹配公文观感）
    ("SimSun", "宋体"),
    ("SimHei", "黑体"),
    ("KaiTi", "楷体"),
    # 无衬线西文字体（纯拉丁界面时会落在它上面）
    ("Segoe UI", "Helvetica", "Arial"),
)

# 探测用的人造族名：用于观察「Tk 遇到不认识的族名时到底回退到哪一款」，
# 从而与真实请求的族名做对照（见 family_resolves）。刻意用不会有人注册的字符形态。
_MISSING_FAMILY_PROBE: Final[str] = "__dlr_missing_family_probe__"


# 读取字体偏好（family 名）。空串 = 未显式选择（沿用系统默认族）。
# 容错口径同 ui_theme.load_theme_preference：配置损坏绝不能让 GUI 起不来。
def load_font_preference(config_file: str | Path) -> str:
    try:
        cfg = tolerant_config_parser()
        cfg.read(config_file, encoding="utf-8-sig")
        if cfg.has_option(GUI_SECTION, FONT_KEY):
            return cfg.get(GUI_SECTION, FONT_KEY, fallback="").strip()
    except Exception:
        return ""
    return ""


# 读取自定义字体文件路径（空串 = 只用系统字体）。
def load_font_file_preference(config_file: str | Path) -> str:
    try:
        cfg = tolerant_config_parser()
        cfg.read(config_file, encoding="utf-8-sig")
        if cfg.has_option(GUI_SECTION, FONT_FILE_KEY):
            return cfg.get(GUI_SECTION, FONT_FILE_KEY, fallback="").strip()
    except Exception:
        return ""
    return ""


# 持久化字体偏好。family 为空即清「显式选择」键（保留 gui_font_file 行）。
# 返回是否写成功——写失败时 GUI 仍按新字体渲染并向用户告警（与主题/缩放同一口径）。
def save_font_preference(config_file: str | Path, family: str, font_file: str = "") -> bool:
    normalized = family.strip()
    written_family = update_or_append_config_line(config_file, GUI_SECTION, FONT_KEY, normalized)
    written_file = update_or_append_config_line(config_file, GUI_SECTION, FONT_FILE_KEY, font_file.strip())
    return bool(written_family and written_file)


# 当前进程可用的字体族名（小写集合 comparisons 用）。
def _installed_families(root: Any = None) -> frozenset[str]:
    try:
        return frozenset(tkfont.families(root))
    except Exception:
        return frozenset()


# 预设列表里在本机真实命中的那些（按组取第一个可用项，组内其余名字不再重复出现）。
def available_preset_families(root: Any = None) -> list[str]:
    installed = _installed_families(root)
    if not installed:
        return []
    picked: list[str] = []
    for group in PRESET_FAMILY_GROUPS:
        for name in group:
            if name in installed:
                picked.append(name)
                break
    return picked


# 某字体族在本机是否可用（区分大小写经 frozenset 精确匹配后，再退一层宽容匹配：
# Tk 在 Windows 上偶有把「Microsoft YaHei UI」枚举成别名的情况）。
# 判据只覆盖**注册表里已安装**的字体——私有注册进来的人并不会出现在这里（见下）。
def is_family_available(family: str, root: Any = None) -> bool:
    if not family:
        return False
    installed = _installed_families(root)
    if family in installed:
        return True
    lowered = family.casefold()
    return any(name.casefold() == lowered for name in installed)


# Tk 能否真的用这个族名取到一款**独立**字体。
#
# [为什么必须有这第二个判据] 实测（2026-10-17）：AddFontResourceExW(FR_PRIVATE)
# 返回成功、Tk 也确实能按该名字把字形排出来——但 tkfont.families() **永远列不到它**
# （Tk 只枚举注册表里已安装的字体）。于是「族名在 families() 里」既不是必要条件
# （私有字体不在），也不是充分的「能用」证明（缺字体时 Tk 静默回退到兜底字体，
# 同样不在列表里却不报错）。唯一能区分「真加载了」与「静默回退」的办法是拿 Tk 自己
# 解析一次，把它和一个必然不存在的族名所得的**兜底族名**比对：两者不同 = 这个名字
# 确实指向了某个特定字体（无论是私有注册还是系统安装）。
def family_resolves(family: str, root: Any = None) -> bool:
    if not family:
        return False
    try:
        resolved = str(tkfont.Font(root=root, family=family).actual()["family"])
        baseline = str(tkfont.Font(root=root, family=_MISSING_FAMILY_PROBE).actual()["family"])
    except Exception:
        return False
    if not resolved:
        return False
    return resolved.casefold() != baseline.casefold()


# ─── SFNT 解析：从字体文件里读出 family 名 ─────────────────────────────────
#
# 不引入 fontTools 这类依赖：我们只需要 name 表里的一条记录，而手上已经有字节流。
# 布局：sfnt 版本(4B) + numTables(2B) + ...，随后每张表 16B 目录项（tag/checksum/offset/length）。
# 'ttc' 容器是 ttcf 头 + 各字体表目录偏移数组，这里取第一个字体（谁也没选多路标）。


def _iter_table_dirs(data: bytes) -> tuple[int, int] | None:
    # 返回 (表目录偏移, 表数)；无法识别返回 None。
    if len(data) < 12:
        return None
    tag = data[:4]
    if tag == b"ttcf":
        if len(data) < 12:
            return None
        count = struct.unpack_from(">I", data, 8)[0]
        if count < 1:
            return None
        offset = struct.unpack_from(">I", data, 12)[0]
        return (offset, struct.unpack_from(">H", data, offset + 4)[0])
    if tag in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"typ1"):
        return (0, struct.unpack_from(">H", data, 4)[0])
    return None


def _find_table(data: bytes, dir_offset: int, wanted: bytes) -> tuple[int, int] | None:
    count = struct.unpack_from(">H", data, dir_offset + 4)[0]
    base = dir_offset + 12
    if count > 512:  # 上限不是协议要求，是防止损坏文件喂出畸变循环
        return None
    for i in range(count):
        pos = base + i * 16
        if pos + 16 > len(data):
            return None
        tag = data[pos : pos + 4]
        if tag == wanted:
            offset, length = struct.unpack_from(">II", data, pos + 8)
            return (offset, length)
    return None


# 读 family 名（name 表 nameID=1）。失败返回 None（坏文件由调用方提示）。
def sfnt_family_name(path: str | Path) -> str | None:
    try:
        data = Path(path).read_bytes()
    except Exception:
        return None
    located = _iter_table_dirs(data)
    if located is None:
        return None
    dir_offset, _count = located
    entry = _find_table(data, dir_offset, b"name")
    if entry is None:
        return None
    table_offset, table_len = entry
    # 表目录项的 offset 相对「表目录起点」（ttc 里它是容器内的偏移，不是文件偏移），
    # 故必须加上目录偏移——不加的话 ttc 分支读到的是目录自身而非 name 表内容。
    table_offset += dir_offset
    if table_offset + 6 > len(data) or table_len < 6:
        return None
    _fmt, name_count, string_offset = struct.unpack_from(">HHH", data, table_offset)
    best: str | None = None
    if name_count > 512:
        return None
    for i in range(name_count):
        rec = table_offset + 6 + i * 12
        if rec + 12 > len(data):
            break
        platform_id, _enc, _lang, name_id, length, offset = struct.unpack_from(">HHHHHH", data, rec)
        if name_id != 1 or length == 0:
            continue
        start = table_offset + string_offset + offset
        if start + length > len(data):
            continue
        raw = data[start : start + length]
        try:
            # platform 3 = Windows（UTF-16BE），platform 1 = Mac（Roman），0 = Unicode
            value = raw.decode("utf-16-be") if platform_id in (0, 3) else raw.decode("latin-1")
        except UnicodeDecodeError:
            continue
        candidate = value.strip("\x00").strip()
        if not candidate:
            continue
        # Windows 平台记录优先（Tk/GDI 在 Windows 上报的就是它），其余作为兜底
        if platform_id == 3:
            return candidate
        best = best or candidate
    return best


# ─── 私有字体装载（Windows） ───────────────────────────────────────────────


# _FR_PRIVATE：进程私有注册，注册表不被写入、也不影响其它进程（用户机器上出现一个
# 只在录制器里生效的字体不会污染系统字体菜单）。
_FR_PRIVATE: Final[int] = 0x10

_GDI32: Any | None = None


# 加载并声明 gdi32。返回 None 表示拿不到（非 Windows / 被策略限制）——调用方必须
# 显式判空。平台专属符号（WinDLL 只存在于 Windows typeshed）必须先按 sys.platform
# 字面量早返回，否则 mypy --platform linux 报 attr-defined（AGENTS 门控条）。
def _get_gdi32() -> Any | None:
    global _GDI32
    if _GDI32 is not None:
        return _GDI32
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        dll = ctypes.WinDLL("gdi32", use_last_error=True)
        dll.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        dll.AddFontResourceExW.restype = ctypes.c_int
        dll.RemoveFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        dll.RemoveFontResourceExW.restype = ctypes.c_int
        _GDI32 = dll
        return dll
    except Exception:
        return None


# 自定义字体在本地的存放目录（按需创建）。
def ensure_font_store(app_root: str | Path) -> Path:
    store = Path(app_root) / FONT_STORE_RELPATH
    try:
        store.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass  # 建目录失败也要往下走：调用方会看到复制失败并提示
    return store


# 把用户选的字体文件复制进本地字体目录，返回落盘路径（失败返回 None）。
# [为什么清洗文件名] 路径取自用户选择的任意位置，文件名可能含 Unicode 分隔符或
# Windows 保留设备名，直接拼接会在 cp936 控制台/冻结 exe 下静默失败。
def install_font_file(source: str | Path, app_root: str | Path) -> Path | None:
    src = Path(source)
    suffix = src.suffix.lower()
    if suffix not in SUPPORTED_FONT_SUFFIXES:
        return None
    store = ensure_font_store(app_root)
    safe_name = _safe_filename(src.name)
    target = store / safe_name
    try:
        shutil.copy2(src, target)
    except Exception as e:
        # [为什么必须留这一行日志] 调用方拿到 None 只会打「导入字体失败」的泛化提示
        # （main_window 的对话框文案是分类级的，不含 OSError 细节），异常若在此静默收敛，
        # 现场就只剩「用户复述点了一次没反应」——文件被占用 / 目标目录只读 / 磁盘满 /
        # 源文件在复制瞬间被移走（2026-10-17 真机实测到的是这条 FileNotFoundError
        # [WinError 2]）这几种成因在 UI 上完全同形，只有日志能把它们分开。
        logger.warning(
            i18n.tr(
                "复制字体文件失败: {name} -> {target} - {type_name}: {err}",
                name=src.name,
                target=str(target),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return None
    return target


# Windows 保留设备名。清洗仍然要挡，但理由不是「本机写不进去」——
# 2026-10-17 在本机（Windows 10.0.26300）实测 `CON.ttf`/`AUX.ttf` 经 Python open() 与
# cmd 重定向**都能落成普通文件**（iterdir 可见、getsize 正常），说明新构建的 Win32 名称解析
# 已放宽。挡它的真正原因是**可移植性**：同一份 config/fonts/CON.ttf 在更早的 Windows 构建、
# 资源管理器改名/复制、以及未走 \\?\ 前缀的第三方 API 下会被当设备或直接拒名；而这个文件名
# 还会被写进 gui_font_file 持久化并在下次启动读回，等于把一台机器上「看着没事」的路径
# 分发到所有机器。COM10/LPT10 刻意不扩——按 MSDN 保留段只到 1..9，扩到两位数会误改合法文件名。
_WIN_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


def _safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip(" .")
    cleaned = cleaned.replace(" ", "_")
    if not cleaned:
        return "custom_font.ttf"
    # 比对首个点之前的基名、大小写不敏感；加下划线前缀既避开保留名又保持幂等
    # （再洗一次得到的是同一个名字，不会一路加前缀）。
    if cleaned.split(".", 1)[0].upper() in _WIN_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


# 把字体文件注册为本进程私有字体，返回它对 Tk 开放的 family 名（失败返回 None）。
# 成功判据不看 AddFontResourceEx 的返回值本身（>0 只说明 GDI 收下了资源），而是注册
# 后**让 Tk 真的去解析一次这个名字**（family_resolves）——私有字体不会出现在
# families() 里，缺字体时 Tk 又静默回退，只有这条对照判据能分辨两者。
def register_private_font(path: str | Path, root: Any = None) -> str | None:
    src = str(path)
    family = sfnt_family_name(src)
    if not family:
        return None
    if is_family_available(family, root):
        # 已装字体无需注册；重复 AddFontResourceEx 会让同一份资源被计数两次，
        # 进程退出后 GDI 的引用计数不平衡（观察者形容为「卸载一次卸不干净」）。
        return family
    dll = _get_gdi32()
    if dll is None:
        # 非 Windows：Tk 只能用到系统安装的字体，走到这里说明该字体确实不在系统里
        return None
    try:
        added = dll.AddFontResourceExW(src, _FR_PRIVATE, None)
    except Exception:
        return None
    if added <= 0:
        return None
    return family if family_resolves(family, root) else None
