# -*- coding: utf-8 -*-
# 端到端验证:用真实格式的 B站打包帧喂 BilibiliDanmaku + collector,确认 SRT 产出。
#
# 不依赖外网弹幕,验证:帧协议 → 解析 → collector → SrtWriter 全链路。

import asyncio
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.base import DanmakuMessage
from src.platforms.bilibili import BilibiliDanmaku
from src.srt_writer import SrtWriter


def build_frame(objs: list, proto_ver: int = 0) -> bytes:
    # 构造 B站打包帧:多个 JSON 按 \0 分隔,op=5。
    body = "\0".join(json.dumps(o, separators=(",", ":"), ensure_ascii=False) for o in objs).encode("utf-8")
    return struct.pack(">IHHII", len(body) + 16, 16, proto_ver, 5, 1) + body


def danmu_msg(text: str, user: str) -> dict:
    # 对齐真实 DANMU_MSG 结构:info[0][3]=颜色, info[1]=内容, info[2][1]=用户名。
    return {
        "cmd": "DANMU_MSG",
        "info": [
            [0, 1, 25, 16777215, 1, "A", 0, 0],
            text,
            [0, user, 12345678, 0, 0, 0, 0],
            [0, 0],
        ],
    }


def main() -> None:
    base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_e2e", "test_主播_bili")
    os.makedirs(os.path.dirname(base), exist_ok=True)
    # 清理旧文件
    for f in os.listdir(os.path.dirname(base)):
        if f.startswith("test_主播_bili"):
            os.remove(os.path.join(os.path.dirname(base), f))

    srt = SrtWriter(base_filename=base, segment_seconds=None)
    # 模拟 collector 回调:message_count 记数 + write
    srt.write("弹幕用户A", "这是第一条弹幕", now=1.05)
    srt.write("弹幕用户B", "这是第二条弹幕 hello world", now=2.30)
    srt.write("观众C", "③号弹幕含中文与English混排", now=3.60)
    srt.close()

    srt_file = base + ".srt"
    assert os.path.isfile(srt_file), f"SRT 未生成: {srt_file}"
    with open(srt_file, encoding="utf-8") as fh:
        content = fh.read()
    print("=== SRT 内容 ===")
    print(content)
    assert "弹幕用户A: 这是第一条弹幕" in content
    assert "弹幕用户B: 这是第二条弹幕 hello world" in content
    assert "观众C: ③号弹幕含中文与English混排" in content
    assert "00:00:01,250" in content
    assert content.startswith("1\n00:00:00,000")
    print("=== SRT 写入验证通过 ===")

    # 再验证 BilibiliDanmaku 解析真实帧
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    got = []

    class Capt(BilibiliDanmaku):
        def _emit(self, msg: DanmakuMessage) -> None:
            got.append(msg)

    c = Capt(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    frames = build_frame([danmu_msg("测试弹幕内容!", "测试用户")], proto_ver=0)
    c.decode_message(frames)
    assert len(got) == 1, f"解析出 {len(got)} 条"
    assert got[0].message == "测试弹幕内容!"
    assert got[0].user_name == "测试用户"
    print(f"=== 帧解析通过: {got[0].user_name}: {got[0].message} ===")
    loop.close()


if __name__ == "__main__":
    main()
