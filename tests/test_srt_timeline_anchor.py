# -*- coding: utf-8 -*-
# SRT 时间轴锚定回归测试(离线,不依赖网络)。
#
# 覆盖:start() 立即创建 SRT 文件；弹幕时间戳相对录像起点计算；
# start() 幂等；分段模式每片时间轴重置；未调 start() 时以首条为 T0(旧行为兜底)。

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.base import DanmakuBase
from src.collector import DanmakuCollector
from src.srt_writer import SrtWriter

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_e2e")
os.makedirs(OUT, exist_ok=True)


def test_immediate_file_and_anchored_timeline() -> None:
    base = os.path.join(OUT, "anchor_单文件")
    for f in os.listdir(OUT):
        if f.startswith("anchor_"):
            os.remove(os.path.join(OUT, f))
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
    with open(base + ".srt", encoding="utf-8") as f:
        content = f.read()
    assert "00:00:10,500 --> 00:00:12,000" in content, f"时间戳应锚定录像起点(非0):\n{content}"
    assert content.startswith("1\n00:00:10,500"), f"首条不应是 00:00:00,000:\n{content}"
    print("[PASS] 单文件:start() 立即建 SRT + 时间戳锚定录像起点")


def test_segment_reset() -> None:
    base = os.path.join(OUT, "anchor_分段")
    for f in os.listdir(OUT):
        if f.startswith("anchor_"):
            os.remove(os.path.join(OUT, f))
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
    with open(seg0, encoding="utf-8") as f:
        c0 = f.read()
    with open(seg1, encoding="utf-8") as f:
        c1 = f.read()
    assert "00:00:00,500" in c0, f"片0应为片内时间:\n{c0}"
    assert "00:00:00,500" in c1, f"片1时间应重置回0:\n{c1}"
    print("[PASS] 分段:每片时间轴重置为 0,且 _000 立即生成")


def test_no_start_fallback() -> None:
    # 未调 start() 时以首条弹幕为 T0(兼容直接写调用的测试)。
    base = os.path.join(OUT, "anchor_兜底")
    w = SrtWriter(base_filename=base, segment_seconds=None)
    w.write("A", "首条", now=1.05)
    w.close()
    with open(base + ".srt", encoding="utf-8") as f:
        content = f.read()
    assert content.startswith("1\n00:00:00,000"), f"兜底应为首条=0:\n{content}"
    print("[PASS] 兜底:未 start() 时首条弹幕为 00:00:00,000")


class _SilentDanmaku(DanmakuBase):
    # 真实 collector 集成:连接后静默挂起,不发弹幕。

    heartbeat_interval = 0.0

    async def start(self, args):
        await asyncio.sleep(60)

    async def stop(self):
        pass

    async def heartbeat(self):
        pass

    def decode_message(self, data):
        pass


def test_collector_creates_srt_at_start() -> None:
    # 经真实 DanmakuCollector 启动,即使一条弹幕都没有,SRT 也应立即存在。
    base = os.path.join(OUT, "anchor_collector")
    for f in os.listdir(OUT):
        if f.startswith("anchor_"):
            os.remove(os.path.join(OUT, f))
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


if __name__ == "__main__":
    test_immediate_file_and_anchored_timeline()
    test_segment_reset()
    test_no_start_fallback()
    test_collector_creates_srt_at_start()
    print("=== SRT 时间轴锚定回归全部通过 ===")
