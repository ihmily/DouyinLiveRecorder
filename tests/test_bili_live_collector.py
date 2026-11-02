# -*- coding: utf-8 -*-
# 真实房间端到端验证（双模：可独立直跑，也允许被 pytest 收集）：BilibiliDanmaku +
# collector 线程 → SRT 产出。
#
# 用法：python tests/test_bili_live_collector.py https://live.bilibili.com/545068 [秒数]

import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import spider
from src.collector import DanmakuCollector
from src.platforms.bilibili import BilibiliDanmaku

URL = sys.argv[1] if len(sys.argv) > 1 else "https://live.bilibili.com/545068"
# 参数守卫必须两步式（R7③）：先排除 `-q`/`-x` 这类 pytest 选项（否则 int('-q') 在收集期
# 抛 ValueError，报错位置与本行相距较远、排查成本高）；再判 isdigit——`pytest a.py b.py`
# 一次点多个文件时 sys.argv[2] 是下一个测试文件的路径，不带 `-` 前缀，只判非选项会放行，
# 随后 int(路径) 当场 ValueError，本模块收集直接 ERROR。真机调用语义不变（"60".isdigit() 为真）。
_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""
SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else 20


def main() -> None:
    info = asyncio.run(spider.get_bilibili_danmaku_info(url=URL, proxy_addr=None))
    assert isinstance(info, dict), f"弹幕信息获取失败: {info!r}"
    # 契约前置校验：防止后续下标访问因缺字段 KeyError。仅 token 额外要求非空，
    # room_id / server_host 只需存在。
    required_keys = ("room_id", "server_host", "token")
    missing = [k for k in required_keys if k not in info]
    assert not missing and info.get("token"), f"弹幕信息缺失或无效字段: {missing} | info={info!r}"
    # token 是字符串令牌：断言非空后按 str 收窄，避免 object 类型告警。
    token = info["token"]
    assert isinstance(token, str), f"token 类型异常: {type(token)!r}"
    print(f"[OK] danmaku_info: room={info['room_id']} host={info['server_host']} token_len={len(token)}")

    # 输出目录固定为 tests/_out_live：先按前缀清掉本脚本自己的产物，避免上一轮遗留的 SRT
    # 混入本轮结果（「文件存在」通过而内容来自旧数据）；无差别删每项会误伤并行运行的其它
    # 平台验证产物，目录里混进子目录时 os.remove 还会抛 IsADirectoryError/PermissionError（R7④）。
    base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out_live")
    os.makedirs(base_dir, exist_ok=True)
    for f in os.listdir(base_dir):
        if f.startswith("真实弹幕验证"):
            stale = os.path.join(base_dir, f)
            # 先判是文件再删：子目录一律跳过，交由 tests/conftest.py 的会话收尾统一 rmtree。
            if os.path.isfile(stale):
                os.remove(stale)

    base = os.path.join(base_dir, "真实弹幕验证_545068")
    collector = DanmakuCollector(
        danmaku_cls=BilibiliDanmaku,
        danmaku_args=info,
        base_filename=base,
        # segment_seconds=None 不按时间分片：短时验证只需单文件 SRT，分片会额外产生
        # _001/_002 等后缀文件，增加结果判定复杂度。
        segment_seconds=None,
    )
    collector.start()
    print(f"[OK] collector 已启动,监听 {SECONDS}s...")
    # 采集在独立线程中运行，主线程睡眠等待其积累消息；SECONDS 需覆盖 WebSocket 握手 +
    # 进房 + AUTH 的耗时。
    time.sleep(SECONDS)
    count = collector.message_count
    # stop() 必须在计数之后、判定之前调用：它负责收尾写入 SRT，提前停止会让下面的
    # isfile 判定因 SRT 尚未落盘而失败。
    collector.stop()
    print(f"[OK] 收到弹幕消息数: {count}")

    srt_file = base + ".srt"
    if os.path.isfile(srt_file):
        with open(srt_file, encoding="utf-8") as fh:
            content = fh.read()
        print("=== SRT 内容(前 20 行) ===")
        print("\n".join(content.splitlines()[:20]))
        # count 为 0 不算失败：SRT 已生成说明连接与 AUTH 链路正常，只是该时段无人发言
        # （冷门房间/深夜常见），须与连接失败区分。
        if count > 0:
            print("[PASS] 端到端:真实弹幕已写入 SRT")
        else:
            print("[WARN] 当前房间该时段无弹幕(连接正常)")
    else:
        print(f"[FAIL] SRT 未生成: {srt_file}")
        print(
            f'VERIFICATION_RESULT: {json.dumps({"platform": "bilibili", "script": "test_bili_live_collector.py", "url": URL, "status": "FAIL", "messages": 0})}'
        )
        sys.exit(1)
    _srt_sz = os.path.getsize(srt_file)
    print(
        f'VERIFICATION_RESULT: {json.dumps({"platform": "bilibili", "script": "test_bili_live_collector.py", "url": URL, "status": "PASS" if count > 0 else "WARN", "messages": count, "srt_bytes": _srt_sz})}'
    )


if __name__ == "__main__":
    main()
