# -*- coding: utf-8 -*-
# 斗鱼真实房间端到端验证:get_douyu_info_data(免 get_token_js)取 room_id → DouyuDanmaku → SRT 产出。
#
# 用法:python tests/test_douyu_live_collector.py [房间URL] [秒数]
# 与 main.py 一致:record_danmaku_args = {'room_id': json_data['room_id']}。

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.douyu import DouyuDanmaku

# 斗鱼弹幕走自有 WebSocket 协议;本脚本用 get_douyu_info_data(免 JS 令牌的简化路径)取
# room_id,适合自动化,但同样需主播真实在播才能验证。
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.douyu.com/88080"
# 双模式参数守卫（R7③）：pytest 传进来的 sys.argv[2] 可能是 `-q` 之类的选项，也可能是下一个
# 测试文件的路径——只判非选项会让 int(路径) 抛 ValueError 使本模块收集 ERROR，故补 isdigit 回落；
# 真机用法不变。
_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else 20


def main() -> None:
    # 调用 spider 取房间元数据;proxy=None 直连,该接口免 JS 令牌,但主播未开播时
    # is_live 为 False,需下方单独判定(不能仅凭 room_id 非空就认为可验证弹幕)。
    info = asyncio.run(spider.get_douyu_info_data(url=URL, proxy_addr=None))
    if not isinstance(info, dict) or not info.get("room_id"):
        print(f"[FAIL] 房间信息获取失败: {info!r}")
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "douyu", "script": "test_douyu_live_collector.py", "url": URL, "status": "FAIL", "messages": 0})}'
        )
        sys.exit(1)
    print(f"[OK] anchor={info.get('anchor_name')} is_live={info.get('is_live')} room_id={info.get('room_id')}")
    if not info.get("is_live"):
        print("[FAIL/WARN] 房间未开播,无法验证弹幕")
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "douyu", "script": "test_douyu_live_collector.py", "url": URL, "status": "SKIP", "reason": "room_offline", "messages": 0})}'
        )
        sys.exit(1)

    # 斗鱼弹幕仅需 room_id(rid):走 websocket 弹幕协议,无需额外签名/令牌;
    # str 化与 main.py record_danmaku_args 约定一致(避免 int 类型告警)。
    danmaku_args = {"room_id": str(info["room_id"])}
    print(f"[OK] danmaku_args: {danmaku_args}")

    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        # 仅删 Douyu 前缀文件而非整目录,避免清掉并行验证的其他平台产物。
        if f.startswith("Douyu弹幕验证"):
            stale = os.path.join(base_dir, f)
            # 先判 isfile：listdir 混进子目录时 os.remove 会抛 IsADirectoryError/PermissionError，
            # 真机验证会卡在清理阶段（R7④）。
            if os.path.isfile(stale):
                os.remove(stale)

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
    # 周期性心跳保活,时长不足会被服务端静默断开。stop() 在计数后触发落盘。
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
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "douyu", "script": "test_douyu_live_collector.py", "url": URL, "status": "FAIL", "messages": 0})}'
        )
        sys.exit(1)
    _srt_sz = os.path.getsize(srt_file)
    print(
        f'VERIFICATION_RESULT: {json.dumps({"platform": "douyu", "script": "test_douyu_live_collector.py", "url": URL, "status": "PASS" if count > 0 else "WARN", "messages": count, "srt_bytes": _srt_sz})}'
    )


if __name__ == "__main__":
    main()
