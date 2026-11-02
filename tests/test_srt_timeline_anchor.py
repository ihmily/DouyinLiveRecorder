# -*- coding: utf-8 -*-
# SRT 时间轴锚定回归测试(离线,不依赖网络)。
#
# 覆盖:start() 立即创建 SRT 文件；弹幕时间戳相对录像起点计算；
# start() 幂等；分段模式每片时间轴重置；未调 start() 时以首条为 T0(旧行为兜底)。
#
# 产物目录一律走 tmp_path / TemporaryDirectory，不用模块级 `tests/_out_e2e`：conftest.py
# 会在 pytest 会话退出时 rmtree 该共享目录，若 import 期就 os.makedirs 则全量跑偶发
# FileNotFoundError 假红（[历史注] 2026-09-24 迁移前即此坑）。每个 case 用独立空目录，
# 无需每段开头预清扫。

import asyncio
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.base import DanmakuBase
from src.collector import DanmakuCollector
from src.srt_writer import SrtWriter


# 守护正常路径：start() 须同步创建 SRT 文件（即使尚无弹幕）；弹幕时间戳相对录像起点
# T0 计算（非从 0 开始），且对同一 writer 重复 start() 保持幂等（不重置 T0）。
def _immediate_file_and_anchored_timeline(out_dir: str) -> None:
    base = os.path.join(out_dir, "anchor_单文件")
    w = SrtWriter(base_filename=base, segment_seconds=None)
    t0 = 1000.0
    w.start(now=t0)
    # start() 后立即有文件(即使尚无弹幕)
    assert os.path.isfile(base + ".srt"), "start() 后应立即创建 SRT 文件"
    # 幂等:再次 start 不重置 T0
    w.start(now=t0 + 100)
    w.write("A", "第10秒的弹幕", now=t0 + 10.5)
    w.write("B", "第12秒的弹幕", now=t0 + 12.0)
    w.close()
    with open(base + ".srt", encoding="utf-8") as fh:
        content = fh.read()
    assert "00:00:10,500 --> 00:00:12,000" in content, f"时间戳应锚定录像起点(非0):\n{content}"
    assert content.startswith("1\n00:00:10,500"), f"首条不应是 00:00:00,000:\n{content}"
    print("[PASS] 单文件:start() 立即建 SRT + 时间戳锚定录像起点")


# 守护分段模式：每片时间轴各自从片内 0 复位，且 start() 即生成 _000 片（无需等弹幕到达）。
def _segment_reset(out_dir: str) -> None:
    base = os.path.join(out_dir, "anchor_分段")
    w = SrtWriter(base_filename=base, segment_seconds=2.0)
    t0 = 1000.0
    w.start(now=t0)
    w.write("A", "第一片", now=t0 + 0.5)  # rel=0.5 -> 片0 00:00:00,500
    w.write("B", "第二片", now=t0 + 2.5)  # rel=2.5 -> 片1 00:00:00,500
    w.close()
    seg0 = base + "_000.srt"
    seg1 = base + "_001.srt"
    assert os.path.isfile(seg0), "分段模式应一开始就生成 _000"
    assert os.path.isfile(seg1), "应有 _001"
    with open(seg0, encoding="utf-8") as fh:
        c0 = fh.read()
    with open(seg1, encoding="utf-8") as fh:
        c1 = fh.read()
    assert "00:00:00,500" in c0, f"片0应为片内时间:\n{c0}"
    assert "00:00:00,500" in c1, f"片1时间应重置回0:\n{c1}"
    print("[PASS] 分段:每片时间轴重置为 0,且 _000 立即生成")


# 守护旧行为兜底：未显式 start() 时以首条弹幕为 T0（时间戳 00:00:00,000），
# 兼容直接写调用、无需预热起点。
def _no_start_fallback(out_dir: str) -> None:
    base = os.path.join(out_dir, "anchor_兜底")
    w = SrtWriter(base_filename=base, segment_seconds=None)
    w.write("A", "首条", now=1.05)
    w.close()
    with open(base + ".srt", encoding="utf-8") as fh:
        content = fh.read()
    assert content.startswith("1\n00:00:00,000"), f"兜底应为首条=0:\n{content}"
    print("[PASS] 兜底:未 start() 时首条弹幕为 00:00:00,000")


class _SilentDanmaku(DanmakuBase):
    # 真实 collector 集成:连接后静默挂起,不发弹幕。

    heartbeat_interval = 0.0

    async def start(self, args: Any) -> None:
        _ = args
        await asyncio.sleep(60)

    async def stop(self) -> None:
        pass

    async def heartbeat(self) -> None:
        pass

    def decode_message(self, data: bytes | str) -> None:
        pass


# 经真实 DanmakuCollector 启动的集成回归：即使一条弹幕都没有，SRT 也须在 start() 同步
# 存在——守护「文件在 start() 同步落盘、不依赖弹幕到达」的不变量（time.sleep 仅为等线程）。
def _collector_creates_srt_at_start(out_dir: str) -> None:
    base = os.path.join(out_dir, "anchor_collector")
    collector = DanmakuCollector(
        danmaku_cls=_SilentDanmaku,
        danmaku_args={},
        base_filename=base,
        segment_seconds=None,
    )
    collector.start()
    time.sleep(0.3)  # 给线程一点启动时间(文件应在 start() 同步创建,不依赖弹幕)
    assert os.path.isfile(base + ".srt"), "collector.start() 后 SRT 应立即存在"
    collector.stop()
    print("[PASS] collector 集成:start() 同步创建 SRT(无弹幕也有文件)")


def test_immediate_file_and_anchored_timeline(tmp_path: Path) -> None:
    # pytest 入口：断言与直跑共用同一个 _* 主体，产物只落 tmp_path，不碰会话级共享目录。
    _immediate_file_and_anchored_timeline(str(tmp_path))


def test_segment_reset(tmp_path: Path) -> None:
    _segment_reset(str(tmp_path))


def test_no_start_fallback(tmp_path: Path) -> None:
    _no_start_fallback(str(tmp_path))


def test_collector_creates_srt_at_start(tmp_path: Path) -> None:
    _collector_creates_srt_at_start(str(tmp_path))


def main() -> None:
    # 保留 `python tests/test_srt_timeline_anchor.py` 的人工通道：跑同一套断言，
    # 四个 case 的 base 文件名互不重叠，共用一个临时目录即可，产物用后即弃。
    with tempfile.TemporaryDirectory(prefix="dlr_srt_anchor_") as out_dir:
        _immediate_file_and_anchored_timeline(out_dir)
        _segment_reset(out_dir)
        _no_start_fallback(out_dir)
        _collector_creates_srt_at_start(out_dir)
    print("=== SRT 时间轴锚定回归全部通过 ===")


if __name__ == "__main__":
    main()
