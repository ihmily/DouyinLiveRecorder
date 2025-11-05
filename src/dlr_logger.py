# -*- encoding: utf-8 -*-
"""
[DLR] Unified Logging System for DouyinLiveRecorder
Author: Claude Code
Date: 2025-11-05
Function: Unified logging with standardized tags and modules
"""

import logging
import sys
from enum import Enum
from typing import Optional
from pathlib import Path


class Module(Enum):
    """[DLR] Module tags for logging"""
    M3U8 = "M3U8"           # M3U8 fetching and processing
    REC = "REC"             # Recording operations
    SCHED = "SCHED"         # Scheduler operations
    DEPS = "DEPS"           # Dependency management
    PREMIUM = "PREMIUM"     # Premium/Fans-only rooms
    QOS = "QOS"             # Quality of Service (bitrate/fps)
    COOKIE = "COOKIE"       # Cookie management
    TG = "TG"               # Telegram notifications
    I18N = "I18N"           # Internationalization
    CFG = "CFG"             # Configuration management
    PATH = "PATH"           # Path and file naming
    ERR = "ERR"             # Error handling


class Platform(Enum):
    """[DLR] Platform tags for logging"""
    PANDA = "PANDA"         # PandaLive
    SOOP = "SOOP"           # SOOP (AfreecaTV)
    DOUYIN = "DOUYIN"       # 抖音
    TIKTOK = "TIKTOK"       # TikTok
    GENERIC = "GENERIC"     # Generic/Multiple platforms


class DLRLogger:
    """
    # [DLR] Unified Logger with standardized tags

    Format: [DLR][{MODULE}][{PLATFORM}] {LEVEL}: {message}

    Example:
        logger.info_m3u8("Fetching master playlist", Platform.PANDA)
        # Output: [DLR][M3U8][PANDA] INFO: Fetching master playlist
    """

    def __init__(self, name: str = "DLR", log_dir: Optional[Path] = None):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)

        # Format: [DLR][MODULE][PLATFORM] LEVEL: message
        formatter = logging.Formatter(
            '%(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)

        if not self.logger.handlers:
            self.logger.addHandler(console_handler)

        # File handler (optional)
        if log_dir:
            log_dir = Path(log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                log_dir / "dlr_detailed.log",
                encoding='utf-8'
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def _format_msg(self, module: Module, platform: Optional[Platform],
                    level: str, message: str) -> str:
        """Format message with DLR tags"""
        platform_tag = f"[{platform.value}]" if platform else ""
        return f"[DLR][{module.value}]{platform_tag} {level}: {message}"

    # === M3U8 Operations ===
    def info_m3u8(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][M3U8] INFO level logging"""
        self.logger.info(self._format_msg(Module.M3U8, platform, "INFO", message))

    def debug_m3u8(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][M3U8] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.M3U8, platform, "DEBUG", message))

    def warn_m3u8(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][M3U8] WARN level logging"""
        self.logger.warning(self._format_msg(Module.M3U8, platform, "WARN", message))

    def error_m3u8(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][M3U8] ERROR level logging"""
        self.logger.error(self._format_msg(Module.M3U8, platform, "ERROR", message))

    # === Recording Operations ===
    def info_rec(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][REC] INFO level logging"""
        self.logger.info(self._format_msg(Module.REC, platform, "INFO", message))

    def debug_rec(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][REC] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.REC, platform, "DEBUG", message))

    def warn_rec(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][REC] WARN level logging"""
        self.logger.warning(self._format_msg(Module.REC, platform, "WARN", message))

    def error_rec(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][REC] ERROR level logging"""
        self.logger.error(self._format_msg(Module.REC, platform, "ERROR", message))

    # === Scheduler Operations ===
    def info_sched(self, message: str):
        """# [DLR][SCHED] INFO level logging"""
        self.logger.info(self._format_msg(Module.SCHED, None, "INFO", message))

    def debug_sched(self, message: str):
        """# [DLR][SCHED] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.SCHED, None, "DEBUG", message))

    # === Dependency Management ===
    def info_deps(self, message: str):
        """# [DLR][DEPS] INFO level logging"""
        self.logger.info(self._format_msg(Module.DEPS, None, "INFO", message))

    def warn_deps(self, message: str):
        """# [DLR][DEPS] WARN level logging"""
        self.logger.warning(self._format_msg(Module.DEPS, None, "WARN", message))

    def error_deps(self, message: str):
        """# [DLR][DEPS] ERROR level logging"""
        self.logger.error(self._format_msg(Module.DEPS, None, "ERROR", message))

    # === Premium/Fans Rooms ===
    def info_premium(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][PREMIUM] INFO level logging"""
        self.logger.info(self._format_msg(Module.PREMIUM, platform, "INFO", message))

    def warn_premium(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][PREMIUM] WARN level logging"""
        self.logger.warning(self._format_msg(Module.PREMIUM, platform, "WARN", message))

    def error_premium(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][PREMIUM] ERROR level logging"""
        self.logger.error(self._format_msg(Module.PREMIUM, platform, "ERROR", message))

    # === Quality of Service ===
    def info_qos(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][QOS] INFO level logging"""
        self.logger.info(self._format_msg(Module.QOS, platform, "INFO", message))

    def debug_qos(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][QOS] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.QOS, platform, "DEBUG", message))

    # === Cookie Management ===
    def info_cookie(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][COOKIE] INFO level logging"""
        self.logger.info(self._format_msg(Module.COOKIE, platform, "INFO", message))

    def debug_cookie(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][COOKIE] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.COOKIE, platform, "DEBUG", message))

    def warn_cookie(self, message: str, platform: Optional[Platform] = None):
        """# [DLR][COOKIE] WARN level logging"""
        self.logger.warning(self._format_msg(Module.COOKIE, platform, "WARN", message))

    # === Telegram Notifications ===
    def info_tg(self, message: str):
        """# [DLR][TG] INFO level logging"""
        self.logger.info(self._format_msg(Module.TG, None, "INFO", message))

    def debug_tg(self, message: str):
        """# [DLR][TG] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.TG, None, "DEBUG", message))

    def error_tg(self, message: str):
        """# [DLR][TG] ERROR level logging"""
        self.logger.error(self._format_msg(Module.TG, None, "ERROR", message))

    # === Configuration ===
    def info_cfg(self, message: str):
        """# [DLR][CFG] INFO level logging"""
        self.logger.info(self._format_msg(Module.CFG, None, "INFO", message))

    def error_cfg(self, message: str):
        """# [DLR][CFG] ERROR level logging"""
        self.logger.error(self._format_msg(Module.CFG, None, "ERROR", message))

    # === Path Management ===
    def info_path(self, message: str):
        """# [DLR][PATH] INFO level logging"""
        self.logger.info(self._format_msg(Module.PATH, None, "INFO", message))

    def debug_path(self, message: str):
        """# [DLR][PATH] DEBUG level logging"""
        self.logger.debug(self._format_msg(Module.PATH, None, "DEBUG", message))

    # === Error Handling ===
    def error_detailed(self, message: str, platform: Optional[Platform] = None,
                      line: Optional[int] = None, cause: Optional[str] = None):
        """
        # [DLR][ERR] Detailed error logging with line number and cause
        """
        detail = f"{message}"
        if line:
            detail += f" | Line: {line}"
        if cause:
            detail += f" | Cause: {cause}"
        self.logger.error(self._format_msg(Module.ERR, platform, "ERROR", detail))

    # === Generic logging methods ===
    def info(self, message: str):
        """Generic INFO logging"""
        self.logger.info(f"[DLR] INFO: {message}")

    def debug(self, message: str):
        """Generic DEBUG logging"""
        self.logger.debug(f"[DLR] DEBUG: {message}")

    def warning(self, message: str):
        """Generic WARNING logging"""
        self.logger.warning(f"[DLR] WARN: {message}")

    def error(self, message: str):
        """Generic ERROR logging"""
        self.logger.error(f"[DLR] ERROR: {message}")


# [DLR][CFG] Create global logger instance
dlr_logger = DLRLogger()


# [DLR][M3U8] M3U8 specific anchors
def log_m3u8_fetch_start(url: str, platform: Platform):
    """# [DLR][M3U8] FETCH_START"""
    dlr_logger.info_m3u8(f"FETCH_START: {url}", platform)


def log_m3u8_refresh(interval: int):
    """# [DLR][M3U8] REFRESH_EVERY_5M"""
    dlr_logger.info_sched(f"REFRESH_EVERY_5M: Refreshing m3u8 every {interval}s")


# [DLR][REC] Recording specific anchors
def log_rec_auto_start(anchor_name: str, platform: Platform):
    """# [DLR][REC] AUTO_START"""
    dlr_logger.info_rec(f"AUTO_START: {anchor_name}", platform)


def log_rec_signal_handler():
    """# [DLR][REC] SIGNAL_HANDLER"""
    dlr_logger.info_rec("SIGNAL_HANDLER: Graceful shutdown initiated")


def log_rec_stop_and_flush():
    """# [DLR][REC] STOP_AND_FLUSH"""
    dlr_logger.info_rec("STOP_AND_FLUSH: Flushing and saving recording")


# [DLR][PREMIUM] Premium/Fans room anchors
def log_premium_mode_switch(mode: str):
    """# [DLR][PREMIUM] MODE_SWITCH"""
    dlr_logger.info_premium(f"MODE_SWITCH: Switching to mode={mode}")


def log_premium_error_coin(url: str, platform: Platform):
    """# [DLR][PREMIUM] ERROR_NEED_COIN_PURCHASE"""
    dlr_logger.error_premium(f"ERROR_NEED_COIN_PURCHASE: {url}", platform)


def log_premium_fallback(url: str, platform: Platform):
    """# [DLR][PREMIUM] FALLBACK_TO_PREV_M3U8"""
    dlr_logger.warn_premium(f"FALLBACK_TO_PREV_M3U8: {url}", platform)


# [DLR][QOS] Quality selection anchors
def log_qos_select_highest():
    """# [DLR][QOS] SELECT_HIGHEST_BITRATE"""
    dlr_logger.info_qos("SELECT_HIGHEST_BITRATE: Selecting highest quality stream")


def log_qos_variant_switch(old_bitrate: int, new_bitrate: int):
    """# [DLR][QOS] SWITCH_VARIANT_IF_BETTER"""
    dlr_logger.info_qos(f"SWITCH_VARIANT_IF_BETTER: {old_bitrate}kbps -> {new_bitrate}kbps")


# [DLR][COOKIE] Cookie management anchors
def log_cookie_soop_sanitize():
    """# [DLR][COOKIE] SOOP_SANITIZE_APPLIED"""
    dlr_logger.info_cookie("SOOP_SANITIZE_APPLIED: Cleaning invalid characters", Platform.SOOP)


# [DLR][TG] Telegram notification anchors
def log_tg_template_applied():
    """# [DLR][TG] TEMPLATE_APPLIED"""
    dlr_logger.info_tg("TEMPLATE_APPLIED: Using full_v2 template")


def log_tg_status_color(status: str, color: str):
    """# [DLR][TG] STATUS_COLOR_MAP"""
    dlr_logger.debug_tg(f"STATUS_COLOR_MAP: {status} -> {color}")


# [DLR][SCHED] Scheduler anchors
def log_sched_cleanup_7d():
    """# [DLR][SCHED] CLEANUP_7D"""
    dlr_logger.info_sched("CLEANUP_7D: Starting 7-day log cleanup")


# [DLR][DEPS] Dependency check anchors
def log_deps_check_missing(dep: str):
    """# [DLR][DEPS] CHECK_MISSING"""
    dlr_logger.warn_deps(f"CHECK_MISSING: {dep} not found")


def log_deps_auto_install(dep: str):
    """# [DLR][DEPS] AUTO_INSTALL"""
    dlr_logger.info_deps(f"AUTO_INSTALL: Installing {dep}")


if __name__ == "__main__":
    # Test logging
    print("=== [DLR] Testing Unified Logging System ===\n")

    log_m3u8_fetch_start("https://www.pandalive.co.kr/live/play/test", Platform.PANDA)
    log_rec_auto_start("TestAnchor-123", Platform.SOOP)
    log_premium_mode_switch("fans")
    log_qos_select_highest()
    log_cookie_soop_sanitize()
    log_tg_template_applied()
    log_sched_cleanup_7d()

    print("\n=== [DLR] Detailed error example ===")
    dlr_logger.error_detailed(
        "유저 정보가 없습니다 (No user info)",
        Platform.PANDA,
        line=1281,
        cause="bjInfo not in response"
    )
