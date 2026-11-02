# 斗鱼弹幕手动验证脚本（无 test_ 函数，不被 pytest 收集）。
#
# 用法：在项目根目录执行 python tests/test_douyu_danmaku.py [room_id]（默认 3125893）。
# 连真实在播直播间 60 秒，看到弹幕输出即通过：覆盖 WebSocket 握手、STT 编解码、
# loginreq/joingroup 登录、45s 心跳、chatmsg 解析；与 main.py 链路一致，只传 room_id（无签名/令牌环节）。
# start() 的 wait_for 只兜连接阶段，其后 60 秒是纯观察窗口。
# 与 tests/test_douyu_live_collector.py 分工：本脚本验协议本身，那个脚本验 SRT 产出与清理。

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
    # stop() 主动关闭 WS；此后 on_message 不再触发，count 即整个观察窗口的累计值
    await d.stop()
    print(f"\n测试结束，共收到 {count} 条弹幕。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已中断")
