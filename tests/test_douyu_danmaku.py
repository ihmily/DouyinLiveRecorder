# 斗鱼弹幕独立测试。
#
# 用法：
#    cd /Users/x/Desktop/fix-recorder/DouyinLiveRecorder
#    python tests/test_douyu_danmaku.py [room_id]
#
# 不传 room_id 默认 3125893。连真实斗鱼直播间 60 秒，看到弹幕输出即通过。
# 验证：WebSocket 握手、STT 编解码、loginreq/joingroup 登录、45s 心跳、chatmsg 解析。

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Any

from src.base import DanmakuMessageType
from src.platforms.douyu import DouyuDanmaku

count = 0
start_ts = time.monotonic()


def on_message(msg: Any) -> None:
    global count
    count += 1
    if msg.type == DanmakuMessageType.CHAT:
        rel = time.monotonic() - start_ts
        print(f"[{rel:6.2f}s] #{count:4d} <{msg.user_name}> {msg.message}")


def on_close(msg: Any) -> None:
    print(f"[close] {msg}")


async def main() -> None:
    room_id = sys.argv[1] if len(sys.argv) > 1 else "3125893"
    duration = 60
    print(f"连接斗鱼直播间 {room_id}，持续 {duration} 秒...")
    d = DouyuDanmaku(on_message=on_message, on_close=on_close, on_ready=lambda: print("[ready] 已连接，开始登录进房"))
    try:
        await asyncio.wait_for(d.start({"room_id": room_id}), timeout=20)
    except asyncio.TimeoutError:
        print("[error] 连接超时")
        return
    await asyncio.sleep(duration)
    await d.stop()
    print(f"\n测试结束，共收到 {count} 条弹幕。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已中断")
