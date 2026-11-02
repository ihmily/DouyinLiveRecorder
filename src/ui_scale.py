# src/ui_scale.py
# GUI 缩放档位层：可选档位、自动档计算与 config.ini 持久化。
#
# 为什么只保留这一层：颜色 token / QSS 在 src/gui_qt/theme.py，窗口几何与控件间距由 Qt
# 布局系统承担；本模块负责「用户选哪个缩放档 + 下次启动怎么读回来」，不持有任何控件
# 对象、不 import 窗口工具包，无头容器与 CLI 冻结产物均可安全 import。
#
# 持久化落 config.ini [GUI] gui_scale，通道与 ui_theme 的 gui_theme 一致
# （update_or_append_config_line：行级替换 + 缺节补建 + 原子写），刻意不用
# config_io.read_config_value——它写回时持 main.file_update_lock，GUI 进程不应
# 把 [GUI] 键的补写混进录制引擎的锁体系。
from __future__ import annotations

import configparser
from typing import Final

from src.config_read import tolerant_config_parser
from src.web_config import update_or_append_config_line

# 用户可选档位（百分比）。下限 85 是可读性地板：再小侧栏导航会撞行；上限 150 是布局
# 天花板：再大侧栏两列信息网格会挤成两行。
SCALE_PRESETS: Final[tuple[int, ...]] = (85, 100, 115, 130, 150)

# 「自动」哨兵 id（刻意不在 SCALE_PRESETS 内）：选中即清空显式偏好、按屏幕可用区
# 现算档位，下次启动继续跟随（与「跟随系统主题」同一套「写空值 = 跟随」的约定）。
AUTO_SCALE_ID: Final[str] = "_auto_scale_"

# 持久化落点：config.ini [GUI] gui_scale（键名无 configparser 分隔符 = :）。
GUI_SECTION: Final[str] = "GUI"
SCALE_KEY: Final[str] = "gui_scale"

# 小屏降档阈值（屏幕可用宽/高的逻辑像素）。低于此值说明屏幕装不下 100% 档的完整布局
# （如 1366x768 虽够，但任务栏/标题栏吃掉一部分后很紧），自动降一档。
SMALL_SCREEN_WIDTH: Final[int] = 1400
SMALL_SCREEN_HEIGHT: Final[int] = 800

# 自动档在「小屏」与「正常屏」之间取的那一档。取 85（可读性地板）而不是 100：
# 小屏上真正的问题是放不下，降一档比让用户自己发现「界面被裁掉了」更省事。
AUTO_SCALE_SMALL: Final[int] = 85
AUTO_SCALE_NORMAL: Final[int] = 100


def is_valid_scale(value: int) -> bool:
    # 菜单展示用：只认 SCALE_PRESETS 里的档位，避免用户面对一串没意义的百分比。
    return value in SCALE_PRESETS


def parse_scale(raw: str) -> str:
    # 归一化持久化/配置里的原始值。返回 SCALE_PRESETS 的百分比字符串、
    # AUTO_SCALE_ID、或 ""（未设置/非法 → 调用方按「自动」处理）。
    # 与 ui_theme.load_theme_preference 同一容错口径：配置损坏绝不能让 GUI 起不来。
    text = raw.strip()
    if not text:
        return ""
    if text == AUTO_SCALE_ID or text == "auto":
        return AUTO_SCALE_ID
    try:
        value = int(float(text))
    except ValueError:
        # "115%" 这类带百分号的写法在用户手改配置时很常见，静默按「自动」兜底
        return ""
    return str(value) if is_valid_scale(value) else ""


def auto_scale_for_screen(screen_width: int, screen_height: int) -> int:
    # 自动档的纯函数形态（供无头测试与窗口层复用）：按屏幕可用区给小屏降一档。
    # 两个维度取「更严格」的一方（or）：1366x900 与 1920x700 都属于任一维度装不下，
    # 只看宽会让竖屏小窗口用户拿到 100% 而横向溢出。
    if screen_width < SMALL_SCREEN_WIDTH or screen_height < SMALL_SCREEN_HEIGHT:
        return AUTO_SCALE_SMALL
    return AUTO_SCALE_NORMAL


def load_scale_preference(config_file: str) -> str:
    # 读取 [GUI] gui_scale。返回 "" 表示「未设置」（节/键缺失、值为空、值非法），
    # 调用方按「自动」处理——用户没选过时保持按屏幕现算，而不是钉死某个百分数
    # （换台分辨率不同的机器就再也不对了）。
    parser = tolerant_config_parser()
    try:
        parser.read(config_file, encoding="utf-8-sig")
    except OSError, configparser.Error:
        return ""
    if not parser.has_section(GUI_SECTION):
        return ""
    return parse_scale(parser.get(GUI_SECTION, SCALE_KEY, fallback=""))


def save_scale_preference(config_file: str, scale: str) -> bool:
    # 持久化缩放偏好。scale 取 parse_scale 的归一化形态（百分比串或 AUTO_SCALE_ID）或 ""
    # （清空显式偏好 = 回到自动）。False = 文件不存在等不可写情形，调用方告警但不阻断
    # 内存态切换（与 gui_theme 同一容错口径）。
    normalized = scale if scale == AUTO_SCALE_ID else parse_scale(scale)
    return update_or_append_config_line(config_file, GUI_SECTION, SCALE_KEY, normalized)
