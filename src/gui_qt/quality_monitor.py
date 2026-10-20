# -*- coding: utf-8 -*-
# 画质监控数据模型：解析录制子进程的状态行，维护「主播 → 画质/降级」表。
#
# 主线程约定：stdout 批次经 Signal 回到主线程后才解析，数据只由主线程触碰，因此本类
# **刻意不加锁**——加锁反而会暗示「可以跨线程用」，而 `_update_*` 里充满了非原子的多步读写。
from __future__ import annotations

import time
from typing import Callable

from .shared import quality_alert_expired, status_patterns

# 超过 30s 未见心跳的录制标记为已停（直播已停但未输出「没有正在录制」行）。
_STALE_RECORDING_SECONDS: float = 30.0


class QualityMonitor:
    def __init__(self) -> None:
        # {name: {set_quality, actual_quality, downgraded, alert_time, alert_at, alert_message,
        #         recording, last_seen}}
        self._data: dict[str, dict[str, str | bool | float]] = {}
        self._problems: tuple[str, ...] | None = None

    def reset(self) -> None:
        # 每次启动新会话清空，避免旧会话的降级告警残留到本次。
        self._data.clear()

    def has_data(self) -> bool:
        return any(bool(info.get("recording")) for info in self._data.values())

    # 解析一条已剥离 loguru 前缀的状态行（录制中 / 画质降级 / 空态）。
    def parse_line(self, line: str, log: Callable[[str, str], None], timestamp: str) -> None:
        msg = line.lstrip("\r")
        # 剥离 loguru 前缀（控制台格式 "{time} | {level} - {message}"、
        # 文件格式 "{time} | {level} | {module}:{func}:{line} - {message}"）：
        # 找到最后一个 " | " 后的 " - "，取其后内容作为 message。
        if " | " in msg:
            pipe_idx = msg.rfind(" | ")
            dash_idx = msg.find(" - ", pipe_idx)
            if dash_idx > 0:
                msg = msg[dash_idx + 3 :]

        patterns = status_patterns()
        # 译稿写坏导致某条模板拼不出可用正则时，按 problems 变化去重，避免每行日志刷一条（M-14）。
        if patterns.problems and self._problems != patterns.problems:
            self._problems = patterns.problems
            for problem in patterns.problems:
                log(f"画质监控状态行解析降级: {problem}", "warn")

        match = patterns.downgrade.search(msg) if patterns.downgrade is not None else None
        if match is not None:
            name = match.group("record_name").strip()
            set_zh = match.group("record_quality_zh")
            set_code = match.group("record_quality")
            actual_zh = match.group("actual_quality_zh")
            actual_code = match.group("actual_quality_code")
            info = self._data.setdefault(name, {})
            info.update(
                {
                    "set_quality": set_zh,
                    "actual_quality": actual_zh,
                    "downgraded": True,
                    "alert_time": timestamp,
                    # 数值时刻用于「告警是否已被后续轮次取代」的时间序比较；每轮录制启动只要
                    # 仍在降级就会重打本告警，故这里等价于续期，迟到的旧告警也清不掉新告警。
                    "alert_at": time.time(),
                    "alert_message": f"设置 {set_zh}({set_code}) 实际 {actual_zh}({actual_code})",
                    "recording": True,
                    "last_seen": time.time(),
                }
            )
            return

        match = patterns.recording.match(msg) if patterns.recording is not None else None
        if match is not None:
            name = match.group("recording_live").strip()
            quality = match.group("qa").strip()
            now = time.time()
            info = self._data.setdefault(name, {})
            info["recording"] = True
            info["set_quality"] = quality
            info["last_seen"] = now
            # 未检测到（或告警已过期）的降级时认为实际画质与设置一致：
            # 一次瞬时降级若不复位，会把房间永久钉成「降级」，
            # 而用户按提示切档后下一轮明明已正常录制。
            if quality_alert_expired(info, now):
                info["downgraded"] = False
                info["alert_time"] = ""
                info["alert_message"] = ""
                info["alert_at"] = 0.0
            if not info.get("downgraded"):
                info["actual_quality"] = quality
            return

        # 空态行 → 清除所有录制标记。子串表由 tr() 结果 + 原文两种形态组成
        # （理由见 shared.STATUS_TPL_EMPTY 注释）。
        for needle in patterns.idle_needles:
            if needle and needle in msg:
                for item in self._data.values():
                    item["recording"] = False
                break

    # 返回「仍在录制」的房间快照，顺带清理超时未更新心跳的录制标记。
    def snapshot(self) -> dict[str, dict[str, str | bool | float]]:
        now = time.time()
        for info in self._data.values():
            if info.get("recording") and now - float(str(info.get("last_seen", 0.0))) > _STALE_RECORDING_SECONDS:
                info["recording"] = False
        return {name: dict(info) for name, info in self._data.items() if info.get("recording")}
