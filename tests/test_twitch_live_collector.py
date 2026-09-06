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

# Twitch 弹幕走 IRC 网关(经 WebSocket 桥接),必须连真实在线频道;拼错或离线会导致
# 服务端直接断开,因此 channel 规范化得空串时立即 exit 1,不进入后续连接流程。
RAW = sys.argv[1] if len(sys.argv) > 1 else "forsen"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20
PROXY = sys.argv[3] if len(sys.argv) > 3 else None

# 从参数规范化频道名：去掉查询串/尾斜杠、取路径末段、转小写、剥离开头 #（兼容
# 直接传 "forsen"、完整 URL 或 "#channel" 三种输入形态）。
channel = RAW.split("?")[0].rstrip("/").split("/")[-1].lower().lstrip("#")
if not channel:
    print("[FAIL] 无法从参数提取频道名")
    sys.exit(1)

# 代理策略:默认 None 即跟随系统代理(getproxies 全局生效),仅显式传第三参才注入;
# Twitch 国内常需代理,代理失效表现为连接超时而非「弹幕为空」。
danmaku_args = {"channel": channel}
if PROXY:
    danmaku_args["proxy"] = PROXY
print(f"[OK] danmaku_args: {danmaku_args}")

base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
os.makedirs(base_dir, exist_ok=True)
for f in os.listdir(base_dir):
    os.remove(os.path.join(base_dir, f))

# 文件名含频道名,便于并行多次运行时区分不同频道的 SRT 产物。
base = os.path.join(base_dir, f"Twitch弹幕验证_{channel}")
collector = DanmakuCollector(
    danmaku_cls=TwitchDanmaku,
    danmaku_args=danmaku_args,
    base_filename=base,
    segment_seconds=None,
)
collector.start()
print(f"[OK] collector 已启动,监听 {SECONDS}s (房间 #{channel})...")
# SECONDS=20 覆盖 Twitch IRC 进房(JOIN #channel)+ 订阅能力协商(cap reqs/NAMES)往返;
# 握手轻量但小于此可能收不到首批消息。stop() 在计数后调用以触发 SRT 落盘。
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
    # SRT 已生成而 count==0 仅表示静默频道(或刚 JOIN 尚无消息),连接正常;
    # SRT 未生成才是真正的连接/握手失败,二者必须区分。
    if count > 0:
        print("[PASS] 端到端:Twitch 真实弹幕已写入 SRT")
    else:
        print("[WARN] 当前房间该时段无弹幕(连接可能正常)")
else:
    print(f"[FAIL] SRT 未生成: {srt_file}")
    sys.exit(1)
