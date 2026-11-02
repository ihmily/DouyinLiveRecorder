# -*- coding: utf-8 -*-
# src/ui_icons.py — 托盘 / 应用图标（ICO）：偏好持久化、格式与分辨率校验、导入落盘、默认图标探测。
#
# 与 src/ui_fonts.py 同一套约定：偏好落在 config.ini（[GUI] gui_tray_icon、[Web] web_tray_icon），
# 读写经 src/web_config.update_or_append_config_line（行级替换 + 缺节补建 + 原子写），刻意不用
# configparser 覆写整文件（会把用户手写注释连带冲掉）。
#
# [为什么只认 .ico] Windows 托盘与 exe 资源都消费 ICO 容器——单文件即可携带多分辨率，系统按
# 场景自取；PNG/SVG 在这两处要么被按单一尺寸取样（高分屏发虚）、要么根本不被识别。故导入环节
# 只放行 .ico，不给「选了也出不来效果」的中间态。运行期**读取**侧不做格式限制（Qt 的 QIcon 自己
# 解码），本模块只管校验与落盘。
#
# [为什么要校验 16×16] 托盘区实际按 16px 取样：缺这一档时系统要从 256 缩到 16，圆环与圆点糊成一
# 团（无异常、只有肉眼可辨），用户会说「图标是花的」。故 16 是硬性准入，256 只作建议（缺了按放大
# 处理，图标偏软但功能完好）——「拒绝」与「提示」分档的用意在此。
#
# [为什么要落盘副本] 同 ui_fonts 的字体：用户导入后删掉原文件是常态，直接引用原路径会变成「下次
# 启动静默回落到默认图标」，看起来像 bug。副本统一落在 config/icons/。
#
# [静默降级] 本模块所有读取 / 解析失败的出口都是 None 或空串，由调用方回落到自绘 / 内置图标。
# 图标是装饰性资源，**绝不允许它挡住启动**：一个坏 ICO 的代价只应是「图标没换」，不是「程序起不来」。

import os
import struct
import sys
from pathlib import Path
from typing import Final, NamedTuple

import i18n
from src.config_read import tolerant_config_parser
from src.logger import logger
from src.web_config import update_or_append_config_line

# 持久化落点：config.ini [GUI] gui_tray_icon（桌面托盘 + 窗口图标）、[Web] web_tray_icon（Web 托盘 +
# 面板标签图标）。空 = 用内置默认图标（assets/app.ico），仍缺失则回落到自绘。
GUI_SECTION: Final[str] = "GUI"
GUI_ICON_KEY: Final[str] = "gui_tray_icon"
WEB_SECTION: Final[str] = "Web"
WEB_ICON_KEY: Final[str] = "web_tray_icon"

# 导入图标的本地存放目录（相对 app_root）。与字体同构（config/fonts/）。
ICON_STORE_DIRNAME: Final[str] = "icons"
ICON_STORE_RELPATH: Final[str] = os.path.join("config", ICON_STORE_DIRNAME)

# 接受导入的图标容器扩展名（见文件头「为什么只认 .ico」）。
SUPPORTED_ICON_SUFFIXES: Final[tuple[str, ...]] = (".ico",)

# 内置默认图标（仓库 assets/app.ico，含 16/24/32/48/64/128/256 七档）。
DEFAULT_ICON_FILENAME: Final[str] = "app.ico"
DEFAULT_ICON_RELPATH: Final[str] = os.path.join("assets", DEFAULT_ICON_FILENAME)

# ICO 头（ICONDIR）：reserved(2)=0 + type(2)=1，随后 count(2) 与 count 个 16 字节目录项；
# 目录项首两字节是宽高，**0 表示 256**（协议规定），读成 0 会让 256 档被判成非法尺寸。
_ICO_MAGIC: Final[bytes] = b"\x00\x00\x01\x00"
_ICONDIR_HEADER_SIZE: Final[int] = 6
_ICONDIR_ENTRY_SIZE: Final[int] = 16
# 帧数上限不是协议要求，是防损坏文件喂出畸变循环（同 ui_fonts._find_table 的 512 上限）
_MAX_ICON_FRAMES: Final[int] = 32
# 单文件体积上限：图标不是视频，512KB 已远超七档 ICO（内置那份 37KB——小档 BMP、大档 PNG）。
MAX_ICON_BYTES: Final[int] = 512 * 1024

# 托盘取样尺寸（硬性准入）与「应用图标 / 资源管理器大图标」档位（建议档，缺则放大）
TRAY_ICON_SIZE: Final[int] = 16
APP_ICON_SIZE: Final[int] = 256


class IconCheck(NamedTuple):
    # 校验结论：ok=False = 拒绝导入；ok=True 且 code 非空 = 通过但带提示（缺 256 档）。
    # 只回码不回文案：文案归调用方 tr()，本模块不新增 msgid（少一处四目录漂移面）。
    ok: bool
    code: str
    sizes: tuple[tuple[int, int], ...]


def load_icon_preference(config_file: str | Path, section: str, key: str) -> str:
    # 读取图标路径偏好；空串 = 未导入（用内置默认）。容错口径同 ui_fonts.load_font_preference：
    # 配置损坏绝不能让 GUI / Web 起不来。
    try:
        cfg = tolerant_config_parser()
        cfg.read(config_file, encoding="utf-8-sig")
        if cfg.has_option(section, key):
            return cfg.get(section, key, fallback="").strip()
    except Exception:
        return ""
    return ""


def save_icon_preference(config_file: str | Path, section: str, key: str, value: str) -> bool:
    # 持久化图标路径。写入失败返回 False，调用方按「已生效但没记住」提示（不回滚界面上已换的图标）。
    return bool(update_or_append_config_line(config_file, section, key, value.strip()))


def ensure_icon_store(app_root: str | Path) -> Path:
    # 导入图标的本地存放目录（按需创建）。建目录失败也要往下走：调用方会看到落盘失败并提示。
    store = Path(app_root) / ICON_STORE_RELPATH
    try:
        store.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return store


def probe_ico_sizes(data: bytes) -> tuple[tuple[int, int], ...] | None:
    # 解析 ICONDIR 目录项取出各帧尺寸；不是合法 ICO / 头部越界一律返回 None。
    # 不用 Pillow：本仓已摘除 PIL 依赖（见 requirements.txt 的 [历史注]），而只需要目录项这两个字节。
    try:
        if len(data) < _ICONDIR_HEADER_SIZE or data[:4] != _ICO_MAGIC:
            return None
        count = struct.unpack_from("<H", data, 4)[0]
        if count == 0 or count > _MAX_ICON_FRAMES:
            return None
        if len(data) < _ICONDIR_HEADER_SIZE + count * _ICONDIR_ENTRY_SIZE:
            # 目录项被截断：后面解析不出尺寸，按「坏文件」处理而不是读半个目录
            return None
        sizes: list[tuple[int, int]] = []
        for i in range(count):
            width, height = struct.unpack_from("<BB", data, _ICONDIR_HEADER_SIZE + i * _ICONDIR_ENTRY_SIZE)
            sizes.append((width or 256, height or 256))
        return tuple(sizes)
    except Exception:
        # struct.error 与一切解析期异常收敛成 None：调用链上没有一处准备处理「图标解析炸」的形态
        return None


def validate_icon_bytes(data: bytes, max_bytes: int = MAX_ICON_BYTES) -> IconCheck:
    # 三段校验：体积 → 结构（是否 ICO）→ 分辨率（16 必含、256 建议）。顺序不可换：先挡体积，
    # 才不会把 100MB 的文件读进结构解析里。
    if not data:
        return IconCheck(False, "empty", ())
    if len(data) > max_bytes:
        return IconCheck(False, "too_large", ())
    sizes = probe_ico_sizes(data)
    if sizes is None:
        return IconCheck(False, "not_ico", ())
    if not any(w == TRAY_ICON_SIZE and h == TRAY_ICON_SIZE for w, h in sizes):
        # 托盘硬性准入：缺 16 档时系统从大图硬缩，16px 下圆环与圆点糊成一片
        return IconCheck(False, "no_tray_size", sizes)
    if not any(w >= APP_ICON_SIZE and h >= APP_ICON_SIZE for w, h in sizes):
        # 仅提示：资源管理器大图标 / Alt+Tab 会取最大档，缺 256 只是放大发虚，不影响可用性
        return IconCheck(True, "no_app_size", sizes)
    return IconCheck(True, "", sizes)


def install_icon_bytes(data: bytes, app_root: str | Path, filename: str = DEFAULT_ICON_FILENAME) -> Path | None:
    # 校验通过后落盘到 config/icons/，返回落盘路径（校验失败 / 写失败返回 None）。
    # 文件名走 ui_fonts.safe_filename（与字体同一套清洗口径：Unicode 分隔符、Windows 保留设备名）。
    # 延迟导入保留：本模块被 Web 托盘与 favicon 路由在**读取路径**上直接 import（那时根本不需要
    # 落盘），把 ui_fonts 的导入面收紧到落盘分支，图标是装饰、不能因任何导入期问题挡住启动。
    from src.ui_fonts import safe_filename

    check = validate_icon_bytes(data)
    if not check.ok:
        return None
    store = ensure_icon_store(app_root)
    target = store / safe_filename(filename or DEFAULT_ICON_FILENAME)
    try:
        target.write_bytes(data)
    except Exception as e:
        # 与 ui_fonts.install_font_file 同一条理由：调用方拿到的 None 只有分类级提示，
        # 「目录只读 / 磁盘满 / 文件被占用」在 UI 上完全同形，只有日志能把它们分开。
        logger.warning(
            i18n.tr(
                "写入图标文件失败: {name} -> {target} - {type_name}: {err}",
                name=target.name,
                target=str(target),
                type_name=type(e).__name__,
                err=e,
            )
        )
        return None
    return target


def install_icon_file(source: str | Path, app_root: str | Path) -> Path | None:
    # 导入本地图标文件（GUI 侧「导入图标…」）：按扩展名初筛 → 读字节 → 与上传路径共用同一校验。
    # 先读字节再校验（而不是先复制再校验）的理由：坏文件不该在 config/icons/ 里留下一份垃圾。
    src = Path(source)
    if src.suffix.lower() not in SUPPORTED_ICON_SUFFIXES:
        return None
    try:
        data = src.read_bytes()
    except Exception as e:
        logger.warning(
            i18n.tr(
                "读取图标文件失败: {name} - {type_name}: {err}",
                name=src.name,
                type_name=type(e).__name__,
                err=e,
            )
        )
        return None
    return install_icon_bytes(data, app_root, src.name)


def resolve_icon_path(app_root: str | Path, configured: str) -> Path | None:
    # 按配置值定位图标文件：绝对路径直接用；相对路径按 app_root 解析（config/icons/xx.ico 这类）。
    # 文件不存在 / 不是文件一律返回 None —— 调用方据此回落到内置默认，绝不因一条陈旧配置报错。
    raw = (configured or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = Path(app_root) / raw
    try:
        if not candidate.is_file():
            return None
    except Exception:
        # is_file() 在畸形路径（含 NUL / 超长）上会抛，而不是返回 False
        return None
    return candidate


def default_icon_path(app_root: str | Path) -> Path | None:
    # 内置默认图标的探测点，顺序即优先级：
    #   ① app_root/assets/app.ico —— 源码运行（仓库根）与冻结态（复制到 exe 同级）都命中；
    #   ② 冻结态 _internal/assets/app.ico —— build_exe 经 datas 收集的那份（onedir 下 _MEIPASS
    #      就是 _internal，与 ① 常常是同一份，两条根是有意冗余：只写一条会让「换了打包布局」即失效）；
    #   ③ 本文件上级目录的 assets/app.ico —— 源码运行的兜底（ui_icons.py → src → 仓库根）。
    roots: list[Path] = [Path(app_root)]
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if isinstance(meipass, str) and meipass:
            roots.append(Path(meipass))
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        candidate = root / DEFAULT_ICON_RELPATH
        try:
            if candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def current_icon_path(app_root: str | Path, configured: str) -> Path | None:
    # 生效图标的唯一出口：用户导入优先，其次内置默认，都没有则 None（调用方回落到自绘 / 无图标）。
    # 三个入口（GUI 托盘 / Web 托盘 / favicon 路由）必须都走这里，否则会出现「托盘换了、标签没换」。
    from_config = resolve_icon_path(app_root, configured)
    if from_config is not None:
        return from_config
    return default_icon_path(app_root)
