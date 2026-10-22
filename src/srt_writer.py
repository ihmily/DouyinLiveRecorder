# SRT 字幕写入器。
#
# 按固定时长（segment_seconds）分片输出 SRT 文件，文件名与录像分片对齐：
#  {base}_{seg:03d}.srt（对应录像 {base}_{seg:03d}.flv）；单文件模式（segment_seconds<=0
#  或 None）输出 {base}.srt。
#
# 时间轴基准：默认以 start() 锚定时刻（collector 启动 ≈ 录像起点）为 T0 并立即建文件；
# 未调 start() 时兜底以首条弹幕到达为 T0。每片内时间轴重置为 0，保证与 ffmpeg segment +
# reset_timestamps 的视频 PTS 对齐（秒级）。

from __future__ import annotations

import re
import threading
import time
from typing import Optional, TextIO

import i18n
from src.logger import logger

# SRT 句柄打开失败后的重试间隔（秒）：目录被删/磁盘满等瞬时故障恢复后需自愈，
# 否则本片（默认 30 分钟）内的弹幕会被静默丢弃。
_OPEN_RETRY_INTERVAL = 10.0
# close() 等待写锁的超时（秒），原因见 close()。
_CLOSE_LOCK_TIMEOUT = 5.0
# close() 成功后写入器进入终态 self._closed，此后到达的弹幕一律丢弃、不再重开句柄；
# 终态判定放在唯一开句柄入口 _open_segment()，原因见该处注释。


# 把相对秒数 seconds 格式化为 SRT 时间戳字符串 "HH:MM:SS,mmm"；负数按 0 处理，毫秒四舍五入并逐级进位。
def _format_ts(seconds: float) -> str:
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


# 按 Unicode 行界切分的解析器会把 U+2028/U+2029、U+0085 视为换行，\x0b/\x0c/NUL 同样破坏
# SRT 块结构——这些字符统一替换为空格（清洗集对齐 clean_name 的控制字符口径）；
# \r\n 与 "-->" 由 _sanitize_srt_text 单独处理。
_SRT_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u0085\u2028\u2029]")


# 清洗弹幕文本，避免污染 SRT 结构：user_name/message 均为外部可控输入，换行会截断字幕块、
# "-->" 会被当成新的时间轴行（可伪造任意字幕）；替换为可见字符而非删除，保留可读性。
def _sanitize_srt_text(text: str) -> str:
    return _SRT_CONTROL_CHARS_RE.sub(" ", text).replace("\r", " ").replace("\n", " ").replace("-->", "->")


# SRT 字幕写入器：线程安全地按分片时长切换输出文件，并把弹幕按片内相对时间写成 SRT 条目。
class SrtWriter:
    # 初始化写入器：base_filename 为录像文件去扩展名前缀（如 .../主播名_2026-08-12_21-00-00），
    # segment_seconds 为分片时长（<=0/None 为单文件模式），display_duration 为单条弹幕最小
    # 显示秒数（避免播放器瞬闪）；只做字段与锁初始化，不创建文件。
    def __init__(
        self,
        base_filename: str,
        segment_seconds: Optional[float] = 1800.0,
        display_duration: float = 1.5,
    ) -> None:
        self._base = base_filename
        self._seg_seconds = segment_seconds if segment_seconds and segment_seconds > 0 else None
        self._display_duration = display_duration

        self._lock = threading.Lock()
        self._t0: Optional[float] = None  # monotonic 基准（start() 锚定的录像起点）
        self._current_seg = -1
        self._index = 0  # 当前片内序号
        self._fp: Optional[TextIO] = None
        self._last_end: Optional[float] = None  # 上一条结束时间，用于密集弹幕错开
        self._last_open_attempt = 0.0  # WD-03：句柄打开失败的退避基准（monotonic）
        self._last_open_error = ""  # L-18：最近一次句柄打开失败的异常类型名（供重试失败告警）
        # MIN-2236③：close() 之后不再接受任何写入（终态位），_discarded_after_count
        # 只在首条丢弃时留一条 debug，避免高频房间刷屏
        self._closed = False
        self._discarded_after_count = 0

    # 锚定时间轴 T0（录像起点）并立即创建第 0 片 SRT 文件（哪怕尚无弹幕）；
    # now 为 time.monotonic()，不传则内部取。幂等：已锚定则忽略。
    # 未调用时 write() 以首条弹幕为 T0 兜底（旧行为，兼容直接写调用的测试）。
    def start(self, now: Optional[float] = None) -> None:
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

    # 以追加模式打开第 seg 片 SRT 文件（UTF-8），并重置片内序号与上一条结束时间。
    # 失败时不向上抛（见 write 中的节流重试），捕获 OSError 并保持 _fp 为 None。
    def _open_segment(self, seg: int) -> None:
        # 终态位判定放在这个唯一的开句柄入口，而不是只放在 write() 里——start()、分片切换、
        # 节流重试三条路径全部在此收口。close() 之后重开同一文件会导致块号回卷：本方法把
        # self._index 归 0，而文件以追加模式打开、旧内容还在，同一个 .srt 里会出现
        # 1,2,…,N,1,2,…，违反 SRT 块号单调递增的规范（播放器会错乱/截断）。
        if self._closed:
            self._fp = None
            return
        path = self._segment_path(seg)
        # 追加模式：若文件已存在（如重连后继续），保留已有内容续写
        try:
            self._fp = open(path, "a", encoding="utf-8")
            self._last_open_error = ""
        except OSError as e:
            # 目录被删/权限不足/磁盘满：保持 _fp 为 None，由 write() 按间隔重试。若让异常冒泡，
            # 本方法只在分片切换时被调用，本片剩余时间（默认 1800s）内不会再重试，write 里的
            # `if self._fp is not None` 会把整片弹幕静默跳过，且只在首次失败时有一条 warning。
            # 记录失败原因，供 write() 的重试失败告警留痕。
            self._last_open_error = type(e).__name__
            self._fp = None
        self._index = 0
        self._last_end = None

    # 根据分片序号 seg 返回 SRT 文件路径：单文件模式为 "{base}.srt"，否则为 "{base}_{seg:03d}.srt"
    # （与 ffmpeg 分段模板 _%03d 落盘的录像文件 _000/_001… 对齐）。
    def _segment_path(self, seg: int) -> str:
        if self._seg_seconds is None:
            return f"{self._base}.srt"
        return f"{self._base}_{seg:03d}.srt"

    # 写入一条弹幕 "user_name: message"：按 now（monotonic，缺省内部取）算出片号并按需切片，
    # 生成片内起止时间戳后立即 flush 落盘；全程持锁保证多线程安全。
    def write(self, user_name: str, message: str, now: Optional[float] = None) -> None:
        if now is None:
            now = time.monotonic()
        with self._lock:
            if self._closed:
                # close() 之后再写一律丢弃（终态判定与块号回卷后果见 _open_segment）。
                # 只 debug 不外抛：调用方是采集线程的 on_message 回调，抛出会污染录制主流程。
                self._discarded_after_count += 1
                if self._discarded_after_count == 1:
                    logger.debug(i18n.tr("[弹幕采集]SRT 文件已关闭，后续到达的弹幕一律丢弃"))
                return
            self._ensure_started(now)
            # M-58②（2026-10-21）：生产路径不得用 assert 守判据。原形态 `assert self._t0 is not None`
            # 在 `python -O`（以及任何 -OO / PYTHONOPTIMIZE 启动方式）下整条被剥掉，判据直接消失，
            # 紧随其后的 `rel = now - self._t0` 对 None 做减法抛 TypeError——而调用方是采集线程
            # 的 SRT 写循环，抛出会把该线程带崩（句柄与待写队列双泄漏），把一个「本条字幕没写成」
            # 升级成「弹幕链路断」。现改为显式判空 + 留痕 + 丢弃本条并正常返回。
            # 文案刻意复用四目录既有条目（本轮约束：不新增 i18n msgid）；{e} 收的是内部状态原因、
            # 不含外部可控文本，故不过 mask_credentials。
            if self._t0 is None:
                logger.warning(
                    i18n.tr(
                        "[弹幕采集]SRT 写入失败(继续采集): {type_name}: {e}",
                        type_name="RuntimeError",
                        e="时间轴基准 T0 未锚定（_ensure_started 未生效）",
                    )
                )
                return
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

            # 句柄缺失时的「节流重试开片」必须发生在生成条目之前：_open_segment() 会清零片内状态
            # （_index=0 / _last_end=None），旧顺序先自增 _index 并拼好 line、再重试开片，会让同一个
            # .srt 内出现重复块号与非单调时间轴。前置后：重试成功则本片首条从 1 开始；重试仍失败
            # 则本条按原逻辑丢弃（_fp 为 None 时不写），序号也不会被凭空跳大。
            if self._fp is None:
                # 句柄缺失（首次 open 失败 / 写入中被关闭）时按间隔重试打开，否则本片剩余弹幕会被
                # 静默丢弃且无任何提示。
                _now = time.monotonic()
                if _now - self._last_open_attempt >= _OPEN_RETRY_INTERVAL:
                    self._last_open_attempt = _now
                    self._open_segment(self._current_seg)
                    if self._fp is None:
                        # 重试仍失败补 warning：告警与重试同频（每 _OPEN_RETRY_INTERVAL 至多一条），
                        # 不刷屏。
                        logger.warning(
                            i18n.tr(
                                "SRT 字幕文件打开失败（弹幕暂时无法落盘，将按间隔重试）: {path} - {type_name}",
                                path=self._segment_path(self._current_seg),
                                type_name=self._last_open_error or "OSError",
                            )
                        )

            # 计算结束时间：至少 display_duration，且不与上一条重叠过紧
            end = start + self._display_duration
            if self._last_end is not None and end <= self._last_end:
                end = self._last_end + self._display_duration
            # 片内上界：末条弹幕的 end 不得越过本片时长，否则会与片边界及下一片首条
            # 时间轴重叠（下一片 _open_segment 会把片内时间轴归 0 重算）。
            # max(start, ...) 兜底保证 start <= end，不产生非法区间。
            if self._seg_seconds is not None:
                end = max(start, min(end, float(self._seg_seconds)))
            self._last_end = end

            # 弹幕原文与用户名均为外部可控：换行会破坏 SRT 块结构、"-->" 会被解析成
            # 伪时间轴行，必须先清洗再拼行。
            # M-58①（2026-10-21）：块号自增必须落在「这一条真的写出去了」的分支里。旧形态在拼行
            # 之前无条件 self._index += 1，句柄缺失被丢弃的条目照样吃掉一个块号，与本函数上方
            # 「重试仍失败则本条按原逻辑丢弃……序号也不会被凭空跳大」的承诺相反（审查 L-10 同条：
            # 注释声明强于实现）。今天多数场景被 _open_segment() 归零 _index 掩盖，但「丢弃」与
            # 「重新开片」之间不经过开片时（节流窗口内的连续丢弃后再成功写入）块号就会跳号。
            if self._fp is not None:
                self._index += 1
                line = (
                    f"{self._index}\n"
                    f"{_format_ts(start)} --> {_format_ts(end)}\n"
                    f"{_sanitize_srt_text(user_name)}: {_sanitize_srt_text(message)}\n\n"
                )
                self._fp.write(line)
                self._fp.flush()

    # 需持锁调用的内部关闭：flush 并关闭当前文件句柄后置空，异常忽略，无返回值。
    def _close_locked(self) -> None:
        if self._fp is not None:
            try:
                self._fp.flush()
                self._fp.close()
            except Exception:
                # 吞没即正确：调用点是「切片」与「close()」两条收尾路径，句柄已不可用
                # （磁盘满/文件被外部删除）时再抛错只会让录制线程收到弹幕写失败的异常，
                # 而 _fp 随后一律置空、内容已由 flush 尽力落盘，无进一步可恢复动作。
                pass
            self._fp = None

    # 对外关闭接口：加锁后落盘并关闭当前 SRT 文件，可重复调用。
    # 加锁带超时：调用方是录制线程（collector.stop）；若写线程正持锁卡在阻塞式 flush()
    # （网络盘/USB 掉线等），无超时 acquire 会把录制线程无限期挂住，比丢几条弹幕严重得多。
    # 超时即放弃本轮关闭（句柄由进程结束回收）并留一条告警。
    def close(self) -> None:
        if not self._lock.acquire(timeout=_CLOSE_LOCK_TIMEOUT):
            logger.warning(
                i18n.tr(
                    "[弹幕采集]SRT 关闭等待锁超时（{seconds}s），跳过本次关闭以免阻塞录制线程",
                    seconds=_CLOSE_LOCK_TIMEOUT,
                )
            )
            return
        try:
            self._close_locked()
            # 只有真正拿到锁、完成关闭的那一轮才置终态位；超时分支刻意不置位——那次关闭作废
            # （句柄仍被写线程持有），调用方仍可再次 close()，「可重复调用」的契约不变。
            self._closed = True
        finally:
            self._lock.release()
