# -*- coding: utf-8 -*-
# src/ui_fonts.py — GUI 字体自选：偏好持久化、字体文件导入与文件名清洗。
#
# 与 ui_theme / ui_scale 同一套约定：偏好落在 config.ini [GUI] 段、读写经
# src/web_config.update_or_append_config_line（行级替换 + 缺节补建 + 原子写），
# 刻意不用 configparser 覆写整文件（会把用户手写注释连带冲掉）。
#
# 字体枚举与「某族名能否解析」由窗口层用 Qt 的 QFontDatabase 判定
# （src/gui_qt/main_window.py）；本模块不 import 任何 GUI 工具包，无头容器与
# 冻结 CLI 产物均可安全 import。
#
# [为什么导入时复制一份而不是直接用原路径] 用户导完之后删掉临时字体是常态，
# 直接引用会造成「下次启动整窗回落到默认字体」这种看起来像 bug 的现象。
import os
import shutil
from pathlib import Path
from typing import Final

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
FONT_STORE_DIRNAME: Final[str] = "fonts"
FONT_STORE_RELPATH: Final[str] = os.path.join("config", FONT_STORE_DIRNAME)

# 接受导入的字体容器扩展名（SFNT：TrueType / OpenType / 字体集合）。
# woff/woff2 是网页传输格式，Qt/GDI 取字体只认 SFNT，故在文件选择与校验处直接拒绝并
# 给出明确原因——比「选了没反应」好。
SUPPORTED_FONT_SUFFIXES: Final[tuple[str, ...]] = (".ttf", ".otf", ".ttc")


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
        # （main_window 的对话框文案是分类级的，不含 OSError 细节）。异常若在此静默收敛，
        # 现场就只剩「用户复述点了一次没反应」——文件被占用 / 目录只读 / 磁盘满 / 源文件
        # 在复制瞬间被移走（实测到的 FileNotFoundError [WinError 2]）在 UI 上完全同形，
        # 只有日志能把它们分开。
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


# Windows 保留设备名。挡它的理由不是「本机写不进去」——新构建的 Win32 名称解析已放宽，
# CON.ttf/AUX.ttf 经 open() 也能落成普通文件；真正原因是**可移植性**：同一份
# config/fonts/CON.ttf 在更早的 Windows 构建、资源管理器改名/复制、以及未走 \\?\ 前缀的
# 第三方 API 下会被当设备或直接拒名，而这个文件名还会被写进 gui_font_file 持久化并在下次
# 启动读回，等于把一台机器上「看着没事」的路径分发到所有机器。COM10/LPT10 刻意不扩——
# MSDN 保留段只到 1..9，扩到两位数会误改合法文件名。
_WIN_RESERVED_NAMES: Final[frozenset[str]] = frozenset(
    {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
)


# 公开名（原为 _safe_filename）：图标导入（src/ui_icons.py）与字体导入共用同一套清洗口径——
# 两处各写一份就会出现「字体挡得住的保留名、图标挡不住」，而这种失败只在特定文件名上发生、
# 排查成本极高。旧私有名保留为别名：既有调用点与 tests/test_ui_fonts.py 直接按它取用。
def safe_filename(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._- " else "_" for ch in name).strip(" .")
    cleaned = cleaned.replace(" ", "_")
    if not cleaned:
        return "custom_font.ttf"
    # 比对首个点之前的基名、大小写不敏感；加下划线前缀既避开保留名又保持幂等
    # （再洗一次得到的是同一个名字，不会一路加前缀）。
    if cleaned.split(".", 1)[0].upper() in _WIN_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


_safe_filename = safe_filename
