# src/ui_theme.py
# GUI 主题偏好层：主题 id 白名单、系统明暗探测与 config.ini 持久化。
#
# 颜色 token 与 QSS 生成的唯一事实源是 src/gui_qt/theme.py；本模块只保留**与工具包无关**
# 的偏好读写，供窗口层启动时解析 [GUI] gui_theme。窗口层自持 THEME_IDS 的同名副本
# （src/gui_qt/theme.py），两边取值必须一致——用户切换窗口实现时已持久化的选择不能失效。
#
# 本模块不 import 任何 GUI 工具包：无头容器 / 冻结 CLI 产物 / Web 入口均可安全 import。
# 持久化走 src/web_config.update_or_append_config_line（缺节/缺键补建 + 行级注释保留 +
# 原子写），刻意不用 config_io.read_config_value：它写回时持 main.file_update_lock，
# 与录制进程耦合。
from __future__ import annotations

import configparser
import subprocess
import sys
from pathlib import Path

from src.config_read import tolerant_config_parser
from src.web_config import update_or_append_config_line

# 主题 id 全集（持久化值即 id 原文，故必须是安全的配置值：无空格无分隔符）。
# 与 src/gui_qt/theme.py 的 THEME_IDS 保持一致：config.ini 里已持久化的取值两套实现
# 都必须识别，否则用户在旧版选过的主题换了窗口层就失效。
THEME_IDS: tuple[str, ...] = ("light", "dark", "high_contrast")

# 持久化落点：config.ini [GUI] gui_theme。
GUI_SECTION = "GUI"
THEME_KEY = "gui_theme"


def detect_system_appearance() -> str:
    # 探测操作系统明暗偏好，返回主题 id（"light" 或 "dark"）。
    # Windows 读注册表 AppsUseLightTheme（0=深色）；macOS 走 `defaults read -g AppleInterfaceStyle`
    # （键缺失/命令失败 = 浅色）；其余平台无统一口径按浅色兜底。任何探测失败一律回 "light"——
    # 探测只是「跟随系统」的默认值来源，绝不能让 GUI 起不来（仅 GUI 运行期调用）。
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return "light" if int(value) != 0 else "dark"
        except OSError:
            # 键不存在 / 权限不足：按浅色兜底（企业策略锁定的机器上注册表读取可能被拒）
            return "light"
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                timeout=2,
            )
            return "dark" if result.returncode == 0 else "light"
        except OSError, subprocess.TimeoutExpired:
            return "light"
    return "light"


def load_theme_preference(config_file: str | Path) -> str:
    # 读取 [GUI] gui_theme。返回 "" 表示「未设置」（节/键缺失、值为空、值不在 THEME_IDS），
    # 调用方应回退到 detect_system_appearance()——用户没选过主题时保持跟随系统行为，
    # 只有显式选择过的偏好才覆盖它。
    parser = tolerant_config_parser()
    try:
        parser.read(config_file, encoding="utf-8-sig")
    except OSError, configparser.Error:
        # 损坏/不可读的配置按「未设置」处理：主题选择永远不能阻断 GUI 启动
        return ""
    if not parser.has_section(GUI_SECTION):
        return ""
    raw = parser.get(GUI_SECTION, THEME_KEY, fallback="").strip().lower()
    return raw if raw in THEME_IDS else ""


def save_theme_preference(config_file: str | Path, theme_id: str) -> bool:
    # 持久化主题偏好。经 update_or_append_config_line：行级替换优先、缺键/缺节补建，
    # 注释与节顺序保留、原子写。False = 文件不存在等不可写情形，调用方告警但不阻断内存态切换。
    # "" 是「清空显式偏好 = 跟随系统」的哨兵：与 load_theme_preference 返回 ""（未设置）同一口径，
    # 也与 save_scale_preference 接受 ""（=自动）一致。窗口层选「跟随系统」时落空值而非删键，
    # 既保留注释与节顺序，又让下次启动 load 回退到外观跟随。其余未知 id 仍按编程错误拦截。
    if theme_id not in ("", *THEME_IDS):
        raise ValueError(f"未知主题 id: {theme_id!r}（合法值: {THEME_IDS}）")
    return update_or_append_config_line(config_file, GUI_SECTION, THEME_KEY, theme_id)
