# -*- coding: utf-8 -*-
# Twitch 真实房间端到端验证:channel → collector(TwitchDanmaku) → SRT 产出。
#
# 用法:python tests/test_twitch_live_collector.py [频道名或URL] [秒数]
# 代理:默认跟随系统代理(getproxies),可选第三个参数显式指定,如 http://127.0.0.1:7890

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collector import DanmakuCollector
from src.platforms.twitch import TwitchDanmaku

RAW = sys.argv[1] if len(sys.argv) > 1 else "forsen"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20
PROXY = sys.argv[3] if len(sys.argv) > 3 else None

channel = RAW.split("?")[0].rstrip("/").split("/")[-1].lower().lstrip("#")
if not channel:
    print("[FAIL] 无法从参数提取频道名")
    sys.exit(1)

danmaku_args = {"channel": channel}
if PROXY:
    danmaku_args["proxy"] = PROXY
print(f"[OK] danmaku_args: {danmaku_args}")

base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
os.makedirs(base_dir, exist_ok=True)
for f in os.listdir(base_dir):
    os.remove(os.path.join(base_dir, f))

base = os.path.join(base_dir, f"Twitch弹幕验证_{channel}")
collector = DanmakuCollector(
    danmaku_cls=TwitchDanmaku,
    danmaku_args=danmaku_args,
    base_filename=base,
    segment_seconds=None,
)
collector.start()
print(f"[OK] collector 已启动,监听 {SECONDS}s (房间 #{channel})...")
time.sleep(SECONDS)
count = collector.message_count
collector.stop()
print(f"[OK] 收到弹幕消息数: {count}")

srt_file = base + ".srt"
if os.path.isfile(srt_file):
    with open(srt_file, encoding="utf-8") as fh:
        content = fh.read()
    print("=== SRT 内容(前 20 行) ===")
    print("\n".join(content.splitlines()[:20]))
    if count > 0:
        print("[PASS] 端到端:Twitch 真实弹幕已写入 SRT")
    else:
        print("[WARN] 当前房间该时段无弹幕(连接可能正常)")
else:
    print(f"[FAIL] SRT 未生成: {srt_file}")
    sys.exit(1)
