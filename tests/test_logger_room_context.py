# 房间日志关联字段（extra["room"]）的行为回归测试。
#
# 背景：多房间并发录制时所有房间线程共用同一条文件 sink，enqueue 队列按到达顺序交织
# 落盘，此前只有 main.py 里手写的 [record_name] 前缀可辨房间，src/* 内部日志与解析
# 失败/退出等早期日志完全无法归属。修复方式是线程级 ContextVar + 全局 patcher 写入
# extra（见 src/logger.py::ROOM_FIELD），并把该字段加进两个录制文件 sink 的 format。
#
# 本文件锁定四件事：
#   ① 两房间并发交织时，同一房间的行可按该字段可靠切出（不要求行连续）；
#   ② 未绑定房间的日志仍能正常落盘且该列为空——缺 extra 默认值时 loguru 会为每条
#      日志向 stderr 吐 "Logging error in Loguru Handler" 并丢弃该行，属静默丢日志；
#   ③ 调用点显式 bind(room=...) 优先于线程级兜底（patcher 不得覆盖已存在的非空值）；
#   ④ 加了字段之后 INFO / DEBUG 的分档落盘位置与改动前一致（filter 分档未被格式改动牵连）。

from __future__ import annotations

import importlib
import sys
import threading
from pathlib import Path
from typing import Iterator

import pytest
from loguru import logger

import src.logger as logger_mod

# 每房间写入的行数：大于 1 才能证明「交织后仍能切出」，而不是碰巧只有一行
_PROBE_COUNT = 20
_ROOM_A = "序号1 主播甲"
_ROOM_B = "序号2 主播乙"


@pytest.fixture()
def recorder_logger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    # 与 tests/test_logger_gui_parent.py 同口径：把 _app_root() 的落点指向 tmp_path 以隔离
    # logs/ 与 config/，sys.stderr 置 None 跳过控制台 sink（本组用例只看文件 sink 落盘内容）。
    # 重载 src.logger 让「录制进程」分支重新注册两个文件 sink，同时重新装上房间 patcher。
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "main.py")])
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.delenv(logger_mod.GUI_PARENT_ENV, raising=False)
    config_dir = tmp_path / "config"
    config_dir.mkdir(exist_ok=True)
    (config_dir / "config.ini").write_text("[录制设置]\n是否启用日志文件(是/否) = 是\n", encoding="utf-8")
    importlib.reload(logger_mod)
    yield tmp_path
    # 复位全局 loguru 状态，避免 tmp 目录下的 sink 与房间字段泄漏给后续用例
    logger.complete()
    logger.remove()
    logger_mod._console_sink_id = None
    logger_mod._streamget_sink_id = None
    logger_mod._playurl_sink_id = None


def _streamget_col(room: str, level: str = "WARNING") -> str:
    # streamget.log 行结构：时间 | 级别(左对齐 8) | 房间 | 模块:函数:行号 - 消息
    # 断言统一匹配「级别 + 房间」整段列片段而非按 " | " 切分：级别右侧的补位空格会让
    # split 结果错位（如 WARNING 补 1 个空格后紧接空房间列，会多切出一个空列）
    return f"| {level:<8} | {room} | "


def _playurl_col(room: str) -> str:
    # PlayURL.log 行结构：时间 | 房间 | 消息
    return f"| {room} | "


def _read_lines(tmp_root: Path, name: str, marker: str) -> list[str]:
    # enqueue=True 为异步写入，读文件前必须排空队列，否则偶发读到空内容（假红）
    logger.complete()
    text = (tmp_root / "logs" / name).read_text(encoding="utf-8")
    return [line for line in text.splitlines() if marker in line]


def test_two_rooms_can_be_split_by_room_field(recorder_logger: Path) -> None:
    # ① 两个房间线程各写 _PROBE_COUNT 行，barrier 强制交织；按房间列切分后每房间必须
    # 恰好取回自己的全部行——这正是「单房间链路可从交织日志中切出」的验收条件
    barrier = threading.Barrier(2)
    seen: list[tuple[str, str]] = []

    def _room_worker(room: str) -> None:
        logger_mod.set_room_context(room)
        # setter 与 getter 同线程自洽：另一房间线程不得读到自己的值（线程隔离的直证）
        seen.append((room, logger_mod.get_room_context()))
        for _ in range(_PROBE_COUNT):
            barrier.wait()
            logger.warning("room-probe")

    threads = [threading.Thread(target=_room_worker, args=(room,)) for room in (_ROOM_A, _ROOM_B)]
    for t in threads:
        t.start()
    for t in threads:
        # 审查 7.11（2026-10-18）：裸 join() 会在一房线程卡在 barrier 时永久挂住整轮 pytest；
        # 带上限后 join 会返回，随后这条 is_alive 判据才是「两线程确实跑完各自的 _PROBE_COUNT 行」
        # 的真凭据——缺它时下面的行数断言可能拿半截日志误判（假绿）。
        t.join(timeout=10)
    alive = [t.name for t in threads if t.is_alive()]
    assert not alive, f"房间线程未在 10s 内退出（疑似 barrier 卡死）：{alive}"

    # 两线程的 append 顺序取决于调度，故排序后比较（每条记录的 (设入值, 读出值) 必须自洽）
    assert sorted(seen) == [(_ROOM_A, _ROOM_A), (_ROOM_B, _ROOM_B)], "房间字段未做到线程隔离"

    lines = _read_lines(recorder_logger, "streamget.log", "room-probe")
    assert len(lines) == _PROBE_COUNT * 2
    # 每行都必须带上且只带一个房间标记：既不能串味，也不能漏标
    tag_a = [_streamget_col(_ROOM_A) in line for line in lines]
    tag_b = [_streamget_col(_ROOM_B) in line for line in lines]
    assert sum(tag_a) == _PROBE_COUNT, f"{_ROOM_A} 的行数不符，房间字段串味或缺失"
    assert sum(tag_b) == _PROBE_COUNT, f"{_ROOM_B} 的行数不符，房间字段串味或缺失"
    assert not any(a and b for a, b in zip(tag_a, tag_b)), "同一行同时命中两个房间，字段被覆盖"
    # 交织确实发生：存在相邻两行属于不同房间。若不锁住这一前提，「每个房间各自单独成段
    # 写入」的退化实现同样能通过上面两条计数断言（假绿）
    rooms = ["A" if a else "B" for a in tag_a]
    assert any(x != y for x, y in zip(rooms, rooms[1:])), "两房间日志未交织，本用例未真正验证切分能力"


def test_unbound_room_logs_still_land_with_empty_column(recorder_logger: Path) -> None:
    # ② 未绑定房间（主循环 / GUI / 弹幕与转码线程池的日志即此类）：字段列必须为空且
    # 该行仍要落盘——缺 configure(extra=...) 默认值时 KeyError 会让 loguru 丢弃整行
    logger_mod.set_room_context("")
    logger.warning("orphan-probe")
    assert logger_mod.get_room_context() == "", "传空串应解绑"

    lines = _read_lines(recorder_logger, "streamget.log", "orphan-probe")
    assert len(lines) == 1
    assert _streamget_col("") in lines[0], "未绑定房间时房间列应为空，且不得影响该行格式化"


def test_explicit_bind_wins_over_thread_context(recorder_logger: Path) -> None:
    # ③ 线程级兜底不得覆盖调用点显式绑定，否则未来任何按调用点标注房间的写法都会失效
    logger_mod.set_room_context(_ROOM_A)
    logger.bind(room=_ROOM_B).warning("bind-probe")
    logger.warning("thread-probe")

    bound = _read_lines(recorder_logger, "streamget.log", "bind-probe")
    threaded = _read_lines(recorder_logger, "streamget.log", "thread-probe")
    assert len(bound) == 1 and _streamget_col(_ROOM_B) in bound[0]
    assert len(threaded) == 1 and _streamget_col(_ROOM_A) in threaded[0]


def test_level_routing_unchanged_after_adding_room_field(recorder_logger: Path) -> None:
    # ④ INFO 仍只进 PlayURL.log、DEBUG 仍只进 streamget.log（两条 sink 的 filter 分档
    # 未因新增字段而改变），且两个文件里的房间列都带上绑定值
    logger_mod.set_room_context(_ROOM_A)
    logger.info("info-probe")
    logger.debug("debug-probe")

    playurl = _read_lines(recorder_logger, "PlayURL.log", "probe")
    streamget = _read_lines(recorder_logger, "streamget.log", "probe")
    assert len(playurl) == 1 and "info-probe" in playurl[0], "INFO/DEBUG 分档被格式改动牵连"
    assert len(streamget) == 1 and "debug-probe" in streamget[0], "INFO/DEBUG 分档被格式改动牵连"
    assert _playurl_col(_ROOM_A) in playurl[0]
    assert _streamget_col(_ROOM_A, level="DEBUG") in streamget[0]
