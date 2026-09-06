# SRT 字幕写入器。
#
# 按固定时长（segment_seconds）分片输出 SRT 文件，文件名与录像分片对齐：
#  {base}_{seg:03d}.srt  （对应录像 {base}_{seg:03d}.flv）
# 单文件模式（segment_seconds<=0 或 None）输出 {base}.srt。
#
# 时间轴基准：默认以 start() 锚定时刻（collector 启动 ≈ 录像起点）为 T0，
# 并立即创建 SRT 文件；未调 start() 时兜底以首条弹幕到达为 T0。每片内时间轴
# 重置为 0，保证与 ffmpeg segment + reset_timestamps 的视频 PTS 对齐（秒级）。

from __future__ import annotations

import threading
import time
from typing import Optional, TextIO


# 把相对秒数 seconds 格式化为 SRT 时间戳字符串 "HH:MM:SS,mmm"；负数按 0 处理，毫秒四舍五入并逐级进位。
def _format_ts(seconds: float) -> str:
    # 秒 -> HH:MM:SS,mmm。
    if seconds < 0:
        seconds = 0.0
    ms = int(round((seconds - int(seconds)) * 1000))
    s = int(seconds) % 60
    m = (int(seconds) // 60) % 60
    h = int(seconds) // 3600
    if ms == 1000:  # 四舍五入进位
        ms = 0
        s += 1
        if s == 60:
            s = 0
            m += 1
            if m == 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# SRT 字幕写入器：线程安全地按分片时长切换输出文件，并把弹幕按片内相对时间写成 SRT 条目。
class SrtWriter:
    # 初始化写入器：base_filename 为输出文件名前缀，segment_seconds 为分片时长（<=0/None 为单文件），
    # display_duration 为单条弹幕最小显示秒数；只做字段与锁初始化，不创建文件。
    def __init__(
        self,
        base_filename: str,
        segment_seconds: Optional[float] = 1800.0,
        display_duration: float = 1.5,
    ) -> None:
        # base_filename 为录像文件去掉扩展名后的前缀（如 .../主播名_2026-08-12_21-00-00）。
        #
        #        segment_seconds<=0 或 None 时为单文件模式。
        #        display_duration 为单条弹幕最小显示时长（秒），避免播放器瞬闪。
        self._base = base_filename
        self._seg_seconds = segment_seconds if segment_seconds and segment_seconds > 0 else None
        self._display_duration = display_duration

        self._lock = threading.Lock()
        self._t0: Optional[float] = None  # monotonic 基准（start() 锚定的录像起点）
        self._current_seg = -1
        self._index = 0  # 当前片内序号
        self._fp: Optional[TextIO] = None
        self._last_end: Optional[float] = None  # 上一条结束时间，用于密集弹幕错开

    # 锚定时间轴 T0 并立即创建第 0 片 SRT 文件；now 为 time.monotonic()（不传则内部取），幂等，无返回值。
    def start(self, now: Optional[float] = None) -> None:
        # 把时间轴锚定到录像起点并立即创建 SRT 文件（哪怕尚无弹幕）。
        #
        #        now 为 time.monotonic()，不传则内部取。幂等：已锚定则忽略。
        #        未调用时 write() 以首条弹幕为 T0 兜底（旧行为，兼容直接写调用的测试）。
        if now is None:
            now = time.monotonic()
        with self._lock:
            if self._t0 is not None:
                return
            self._t0 = now
            self._current_seg = 0
            self._index = 0
            self._open_segment(0)

    # 兜底初始化（需持锁调用）：未调用过 start() 时以 now 作为 T0 并打开第 0 片文件，无返回值。
    def _ensure_started(self, now: float) -> None:
        if self._t0 is None:
            self._t0 = now
            self._current_seg = 0
            self._index = 0
            self._open_segment(0)

    # 以追加模式打开第 seg 片 SRT 文件（UTF-8），并重置片内序号与上一条结束时间，无返回值。
    def _open_segment(self, seg: int) -> None:
        path = self._segment_path(seg)
        # 追加模式：若文件已存在（如重连后继续），保留已有内容续写
        self._fp = open(path, "a", encoding="utf-8")
        self._index = 0
        self._last_end = None

    # 根据分片序号 seg 返回 SRT 文件路径：单文件模式为 "{base}.srt"，否则为 "{base}_{seg:03d}.srt"
    # （与 ffmpeg 分段模板 _%03d 落盘的录像文件 _000/_001… 对齐）。
    def _segment_path(self, seg: int) -> str:
        if self._seg_seconds is None:
            return f"{self._base}.srt"
        return f"{self._base}_{seg:03d}.srt"

    # 写入一条弹幕 "user_name: message"：按 now（monotonic，缺省内部取）算出片号并按需切片，
    # 生成片内起止时间戳后立即 flush 落盘；全程持锁保证多线程安全，无返回值。
    def write(self, user_name: str, message: str, now: Optional[float] = None) -> None:
        # 写入一条弹幕。now 为 time.monotonic()，不传则内部取。
        if now is None:
            now = time.monotonic()
        with self._lock:
            self._ensure_started(now)
            assert self._t0 is not None  # _ensure_started 保证已初始化
            rel = now - self._t0  # 距 T0 总秒数
            if self._seg_seconds is not None:
                seg = int(rel // self._seg_seconds)
                if seg != self._current_seg:
                    self._close_locked()
                    self._current_seg = seg
                    self._open_segment(seg)
                start = rel - seg * self._seg_seconds  # 片内时间
            else:
                start = rel

            # 计算结束时间：至少 display_duration，且不与上一条重叠过紧
            end = start + self._display_duration
            if self._last_end is not None and end <= self._last_end:
                end = self._last_end + self._display_duration
            self._last_end = end

            self._index += 1
            line = f"{self._index}\n" f"{_format_ts(start)} --> {_format_ts(end)}\n" f"{user_name}: {message}\n\n"
            if self._fp is not None:
                self._fp.write(line)
                self._fp.flush()

    # 需持锁调用的内部关闭：flush 并关闭当前文件句柄后置空，异常忽略，无返回值。
    def _close_locked(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                pass
            self._fp = None

    # 对外关闭接口：加锁后落盘并关闭当前 SRT 文件，可重复调用，无返回值。
    def close(self) -> None:
        with self._lock:
            self._close_locked()
