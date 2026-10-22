# SrtWriter 重试开片与片内状态回归（CODE_REVIEW_2026-09-20 的 MIN-24①）。
#
# 全部离线：只在 tmp_path 下读写 .srt 文件，不涉及网络与采集线程。
#
# 锁定的不变量：
#   ① MIN-24①：句柄缺失后的「节流重试开片」必须在生成字幕条目**之前**完成——
#      _open_segment() 会重置 _index/_last_end，旧顺序（先拼行后重试）会让同一个 .srt
#      里出现重复/非单调块号，而 SRT 规范要求块序号递增；
#   ② 注入清洗（换行 / "-->"）与片内时间轴钳制两项既有保证不得被上述改动破坏；
#   ③ M-58①：被丢弃（句柄缺失）的条目不得占用块号——本文件既有的注释承诺
#      「序号也不会被凭空跳大」，实现必须与之相符（审查 L-10：注释声明强于实现）；
#   ④ M-58②：时间轴基准缺失的守卫必须是显式判空 + warning + 丢弃，不能是 assert
#      （`python -O` 下 assert 整条被剥掉，生产路径等于没有守卫）。

import time
from pathlib import Path

import pytest
from loguru import logger

from src.srt_writer import SrtWriter


def _block_numbers(content: str) -> list[int]:
    # 从 SRT 文本里取出各块的序号行（块结构：序号 / 时间轴 / 文本 / 空行）
    numbers: list[int] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            numbers.append(int(stripped))
    return numbers


def _warn_capture() -> tuple[list[str], int]:
    # 返回 (消息列表, handler id)；调用方负责在 finally 里 logger.remove(handler_id)
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level="WARNING", format="{message}")
    return captured, handler_id


def _ensure_started_noop(_now: float) -> None:
    # M-58② 用例的故障注入：把「兜底锚定 T0」换成 no-op，好让 _t0 为空这一内部状态故障形态
    # 真的走到守卫那一步。签名与 SrtWriter._ensure_started(self, now) 的绑定形态一致（只需收 now）。
    return None


def test_retry_open_happens_before_line_generation(tmp_path: Path) -> None:
    # 目录不存在 → 前若干条写入全部因句柄缺失被丢弃；目录恢复后按节流重试重新开片。
    # 期望：重新开片后首块序号为 1，且全文件序号严格递增、无重复。
    missing_dir = tmp_path / "not-yet"
    base = str(missing_dir / "live")
    writer = SrtWriter(base_filename=base, segment_seconds=None)
    writer.start(now=0.0)
    assert writer._fp is None

    for i in range(3):
        writer.write(f"用户{i}", f"弹幕{i}", now=float(i))

    missing_dir.mkdir(parents=True)
    # 绕过 10s 节流窗口（等价于「距上次尝试已超过 _OPEN_RETRY_INTERVAL」）
    writer._last_open_attempt = 0.0
    writer.write("用户3", "弹幕3", now=3.0)
    writer.write("用户4", "弹幕4", now=4.0)
    writer.close()

    content = (tmp_path / "not-yet" / "live.srt").read_text(encoding="utf-8")
    numbers = _block_numbers(content)
    assert numbers == [1, 2], f"块序号非从 1 严格递增（重试开片状态串了）: {numbers}"
    assert content.count("-->") == 2


def test_retry_open_keeps_timestamp_state_consistent(tmp_path: Path) -> None:
    # _open_segment 同时重置 _last_end；若顺序颠倒，重试后写入的那一行仍带着
    # 重置前算出的 end，时间轴会与片内基准不一致（下一条又会从 0 附近重来）。
    missing_dir = tmp_path / "gone"
    base = str(missing_dir / "seg")
    writer = SrtWriter(base_filename=base, segment_seconds=1800.0, display_duration=1.5)
    writer.start(now=0.0)
    writer._last_end = 999.0  # 模拟重试前已被抬高的上一条结束时间
    missing_dir.mkdir()
    writer._last_open_attempt = 0.0

    writer.write("u", "m1", now=10.0)
    writer.write("u", "m2", now=11.0)
    writer.close()

    content = (missing_dir / "seg_000.srt").read_text(encoding="utf-8")
    numbers = _block_numbers(content)
    assert numbers == [1, 2]
    # 片内时间轴从 start() 锚点算起（10s/11s）；重试前残留的 _last_end=999 必须已被
    # 开片重置——旧顺序（先算 end 再重试开片）会把 00:16:40,500 这种越界 end 写进文件。
    assert "00:00:10,000 --> 00:00:11,500" in content
    assert "00:00:11,000 --> 00:00:12,500" in content
    assert "00:16:40,500" not in content


def test_segment_switch_still_restarts_numbering(tmp_path: Path) -> None:
    # 切片时序号与时间轴按片重置（既有语义，不得被重试顺序调整破坏）
    base = str(tmp_path / "seg")
    writer = SrtWriter(base_filename=base, segment_seconds=1.0)
    writer.start(now=0.0)
    writer.write("u", "第一片", now=0.2)
    writer.write("u", "第二片", now=1.2)
    writer.write("u", "第二片b", now=1.4)
    writer.close()

    first = _block_numbers((tmp_path / "seg_000.srt").read_text(encoding="utf-8"))
    second = _block_numbers((tmp_path / "seg_001.srt").read_text(encoding="utf-8"))
    assert first == [1]
    assert second == [1, 2]


def test_injection_sanitizing_and_in_segment_clamp_unchanged(tmp_path: Path) -> None:
    # 两条既有硬保证：注入文本被清洗为可见字符（块结构不被破坏）、
    # 末条 end 不越过片边界。
    base = str(tmp_path / "safe")
    writer = SrtWriter(base_filename=base, segment_seconds=2.0, display_duration=5.0)
    writer.start(now=0.0)
    writer.write("攻击者\n2\n00:00:99,000 --> 00:00:99,999\nFAKE", "正常文本 --> 伪造轴", now=0.5)
    writer.close()

    content = (tmp_path / "safe_000.srt").read_text(encoding="utf-8")
    assert content.count("-->") == 1, "注入的伪时间轴行未被清洗"
    assert _block_numbers(content) == [1]
    # end 钳制到片边界（start=0.5，display_duration=5 → 仍不超过 2.0）
    assert "00:00:00,500 --> 00:00:02,000" in content


def test_dropped_entry_does_not_burn_a_block_number(tmp_path: Path) -> None:
    # M-58① 回归锁：旧形态在拼行之前无条件 self._index += 1，句柄缺失被丢弃的条目照样占用块号，
    # 与本文件既有注释「重试仍失败则本条按原逻辑丢弃……序号也不会被凭空跳大」的承诺相反。
    # 后果是「注释声明强于实现」（审查 L-10 同条），且丢弃与重新开片之间不经过 _open_segment
    # （节流窗口内的连续丢弃）时，恢复后的首块号会从跳大后的值继续、片内块号出现空洞。
    # 判据同时取两处：① 内部计数器 _index 在丢弃后不得增长；② 恢复写入后文件里块号从 1 连续。
    gone = tmp_path / "gone"
    writer = SrtWriter(base_filename=str(gone / "live"), segment_seconds=None)
    writer.start(now=0.0)
    assert writer._fp is None

    # 第一次写入会真去重试开片（失败），后续两条落在节流窗口内、只丢弃
    writer.write("用户", "弹幕1", now=1.0)
    writer._last_open_attempt = time.monotonic()
    writer.write("用户", "弹幕2", now=2.0)
    writer.write("用户", "弹幕3", now=3.0)
    assert writer._index == 0, "被丢弃的条目占用了块号（M-58① 回归）"

    gone.mkdir()
    writer._last_open_attempt = 0.0
    writer.write("用户", "弹幕4", now=4.0)
    writer.write("用户", "弹幕5", now=5.0)
    writer.close()

    numbers = _block_numbers((gone / "live.srt").read_text(encoding="utf-8"))
    assert numbers == [1, 2], f"恢复后块号不从 1 连续: {numbers}"


def test_missing_timeline_anchor_warns_and_returns_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # M-58② 回归锁：生产路径不得用 assert 守判据。`assert self._t0 is not None` 在
    # python -O / PYTHONOPTIMIZE 下整条被剥掉，紧随其后的 now - self._t0 对 None 做减法抛
    # TypeError，而调用方是采集线程的 SRT 写循环 —— 抛出会把写线程带崩（句柄与待写队列双泄漏）。
    # 现在要求：显式判空 + 一条 warning + 正常返回（不外抛、不写盘、不占用块号）。
    # 旧形态下本用例以 AssertionError 失败（pytest 不带 -O 跑，断言仍在）；改回 assert 即转红。
    writer = SrtWriter(base_filename=str(tmp_path / "live"), segment_seconds=None)
    writer.start(now=0.0)
    assert writer._fp is not None
    # 造出「_ensure_started 之后 _t0 仍为空」的内部状态故障形态：只把**这个实例**的兜底初始化
    # 换成 no-op（实例属性遮蔽绑定方法），不 patch 类，避免波及同会话其它写入器。
    monkeypatch.setattr(writer, "_ensure_started", _ensure_started_noop)
    writer._t0 = None

    captured, handler_id = _warn_capture()
    try:
        writer.write("用户", "弹幕", now=1.0)
    finally:
        logger.remove(handler_id)
    assert writer._index == 0, "T0 缺失时仍走完了写路径"
    assert len(captured) == 1, f"应恰好留一条 warning: {captured}"
    assert "SRT" in captured[0], captured[0]
