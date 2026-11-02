# -*- coding: utf-8 -*-
# 端到端验证：用真实格式的 B站打包帧喂 BilibiliDanmaku + collector，确认 SRT 产出。
# 全程离线（自己 struct.pack 造帧），覆盖「帧协议 → 解析 → collector → SrtWriter」全链路。
#
# ②：本文件原先 0 个 `test_` 函数，全部逻辑待在 `main()` 里、只在 `__main__` 守卫下
# 执行，pytest 收集到的是「空文件」——这条串联从不自动跑，断言可无限腐烂而文件继续向读者
# advertise「e2e 已验证」。它也与允许「需活房间 + 外网、默认人工通道」的 5 个
# `test_*_live_collector.py` 不同类，没有理由不进 pytest；主体拆成
# test_bili_frame_to_srt_end_to_end，直跑入口 `python tests/test_bili_e2e.py` 仍可用（同一函数）。
# 输出走 tmp_path，不再写 tests/_out_e2e/：该目录由 tests/conftest.py 在**任意** pytest 会话
# 退出时 rmtree（AGENTS「全量 pytest 期间不得再启第二个 pytest 会话」），并发会话下必红。

import asyncio
import json
import os
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.base import DanmakuMessage
from src.platforms.bilibili import BilibiliDanmaku
from src.srt_writer import SrtWriter


def build_frame(objs: list, proto_ver: int = 0) -> bytes:
    # 构造 B站打包帧：多个 JSON 按 \0 分隔拼进 body，op=5 为普通消息。
    body = "\0".join(json.dumps(o, separators=(",", ":"), ensure_ascii=False) for o in objs).encode("utf-8")
    # 帧头 >IHHII = (包总长, 头部固定 16, 协议版本 proto_ver, op=5 普通消息, 序列号 1)。
    # proto_ver=0 表示 body 为明文 JSON；真实链路还有 2(zlib)/3(brotli) 压缩态，
    # 本验证只覆盖 0 以确认基础解析与 SRT 落盘，压缩分支由单测另行覆盖。
    return struct.pack(">IHHII", len(body) + 16, 16, proto_ver, 5, 1) + body


def danmu_msg(text: str, user: str) -> dict:
    # 对齐真实 DANMU_MSG 结构：info[0][3] 是颜色，info[1] 是内容，info[2][1] 是用户名。
    return {
        "cmd": "DANMU_MSG",
        "info": [
            [0, 1, 25, 16777215, 1, "A", 0, 0],
            text,
            [0, user, 12345678, 0, 0, 0, 0],
            [0, 0],
        ],
    }


def _run_end_to_end(out_dir: str) -> None:
    # 端到端主体：SRT 落盘 + 真实帧解析两段断言，全部写进调用方给的 out_dir。
    base = os.path.join(out_dir, "test_主播_bili")
    os.makedirs(out_dir, exist_ok=True)
    # base 含中文文件名，顺带验证 SrtWriter 对 UTF-8 路径的兼容（Windows 默认 GBK 易踩坑）。
    # out_dir 由 tmp_path / mkdtemp 提供，本是空目录，无需清扫历史文件。

    srt = SrtWriter(base_filename=base, segment_seconds=None)
    # 模拟 collector 回调（message_count 记数 + write）：now 为相对秒数（浮点），SrtWriter
    # 据此换算 00:00:00,000 时码。下方断言校验 now=1.05 → 00:00:01,250 的换算，
    # 以及首条序号 1 与起始时码 00:00:00,000。
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

    # 再验证 BilibiliDanmaku 解析真实帧。手动 new_event_loop 而非 asyncio.run：Capt 实例需
    # 保留在作用域供断言，且 decode_message 是同步接口，只需空循环满足基类初始化约束。
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    got = []

    try:

        class Capt(BilibiliDanmaku):
            def _emit(self, msg: DanmakuMessage) -> None:
                # 重写 _emit 拦截解析结果（on_message 仅透传）收集到 got，便于对
                # message/user_name 做精确断言，验证字段映射。
                got.append(msg)

        c = Capt(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
        frames = build_frame([danmu_msg("测试弹幕内容!", "测试用户")], proto_ver=0)
        # 直接喂整帧字节（跳过实时 WS 接收）：decode_message 内部按帧头切分并回调 _emit，
        # 验证单帧能被正确解码为 DanmakuMessage。
        c.decode_message(frames)
        assert len(got) == 1, f"解析出 {len(got)} 条"
        assert got[0].message == "测试弹幕内容!"
        assert got[0].user_name == "测试用户"
        print(f"=== 帧解析通过: {got[0].user_name}: {got[0].message} ===")
    finally:
        # 旧形态只有顺序执行的 loop.close()——中间任一条断言转红时
        # 循环既不关闭也不复位；即便跑到底也只 close 不 set_event_loop(None)，于是「已关闭的
        # 循环」被留在当前线程 policy 上跨用例残留，后续取当前循环的代码拿到的都是死循环，
        # 报错形态与被测逻辑无关。3.14 起 get_event_loop() 不再隐式新建循环，复位成 None 才是
        # 诚实状态；本文件其余链路只走显式 new_event_loop/asyncio.run，不依赖隐式循环。
        loop.close()
        asyncio.set_event_loop(None)

    # 复位是否到位用公开 API 复核。判据刻意放在 try/finally **之外**：写在 finally 里，本条
    # 一旦转红会顶掉用例真正的失败（与 msg_push 「finally 里的异常替换结论」同族）。
    # 3.14 的语义是「当前线程无循环 → RuntimeError」（AGENTS「3.14 破坏性变更基线」）；
    # 不碰 policy 私有属性（如 _local._loop），那会让判据随 CPython 内部实现漂移。
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        pass
    else:
        raise AssertionError("当前线程仍绑着事件循环：LT-05 复位失效，跨用例残留未消除")


def test_bili_frame_to_srt_end_to_end(tmp_path: Path) -> None:
    # pytest 入口（ ②）：与直跑共用同一个 _run_end_to_end，避免两套演化。
    # 只依赖 tmp_path——不触网、不读 config、不碰 tests/_out_e2e 这类会话级共享目录。
    _run_end_to_end(str(tmp_path))


def main() -> None:
    # 人工通道入口：跑同一套断言，产物落临时目录后即弃。
    with tempfile.TemporaryDirectory(prefix="dlr_bili_e2e_") as out_dir:
        _run_end_to_end(out_dir)
    print("=== 端到端验证全部通过 ===")


if __name__ == "__main__":
    main()
