# -*- coding: utf-8 -*-
# 斗鱼真实房间端到端验证:get_douyu_info_data(不依赖 get_token_js)取 room_id → collector(DouyuDanmaku) → SRT 产出。
#
# 用法:python tests/test_douyu_live_collector.py [房间URL] [秒数]
# 与 main.py 一致:record_danmaku_args = {'room_id': json_data['room_id']}。

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.douyu import DouyuDanmaku

# 斗鱼弹幕走自有 WebSocket 协议;本脚本用 get_douyu_info_data(免 get_token_js 的
# 简化路径)取 room_id,不依赖 JS 令牌,适合自动化,但同样需主播真实在播才能验证。
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyu.com/88080"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else 20


def main() -> None:
    # 调用 spider 取房间元数据;proxy=None 直连,该接口免 JS 令牌,但主播未开播时
    # is_live 为 False,需下方单独判定(不能仅凭 room_id 非空就认为可验证弹幕)。
    info = asyncio.run(spider.get_douyu_info_data(url=URL, proxy_addr=None))
    if not isinstance(info, dict) or not info.get("room_id"):
        print(f"[FAIL] 房间信息获取失败: {info!r}")
        sys.exit(1)
    print(f"[OK] anchor={info.get('anchor_name')} is_live={info.get('is_live')} room_id={info.get('room_id')}")
    if not info.get("is_live"):
        print("[FAIL/WARN] 房间未开播,无法验证弹幕")
        sys.exit(1)

    # 斗鱼弹幕仅需 room_id（rid）：走 websocket 弹幕协议，无需额外签名/令牌，
    # 与 main.py record_danmaku_args 约定一致（str 化避免 int 类型告警）。
    danmaku_args = {"room_id": str(info["room_id"])}
    print(f"[OK] danmaku_args: {danmaku_args}")

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        # 仅删 Douyu 前缀文件而非整目录,与抖音一致,避免清掉并行其他平台验证产物。
        if f.startswith("Douyu弹幕验证"):
            os.remove(os.path.join(base_dir, f))

    # 文件名含固定房间号后缀,配合清理时的 "Douyu弹幕验证" 前缀过滤,保证只清本平台产物。
    base = os.path.join(base_dir, "Douyu弹幕验证_88080")
    collector = DanmakuCollector(
        danmaku_cls=DouyuDanmaku,
        danmaku_args=danmaku_args,
        base_filename=base,
        segment_seconds=None,
    )
    collector.start()
    print(f"[OK] collector 已启动,监听 {SECONDS}s...")
    # SECONDS=20 覆盖斗鱼 WS 握手 + 进房(login req) + 心跳(gtk)往返;斗鱼要求
    # 周期性心跳保活,时长不足会导致连接被服务端静默断开。stop() 在计数后触发落盘。
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
        # count==0 仅表示当前无弹幕(连接正常);SRT 未生成(连接/握手失败)才 exit 1。
        if count > 0:
            print("[PASS] 端到端:斗鱼真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接可能正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
