# CR-03 畸形 Tars 帧边界回归锁（src/platforms/_tars.py，2026-09-21 补）。
#
# 被守的失败形态：解码器把协议里的长度字段当游标增量直接用，且只判「未越上界」不判负数。
# 负长度 → 切片得空串且游标**回退**到刚消费的头字节之前，而 _goto / finish_struct /
# _skip_to_struct_end 都是 `while True` 且隐含「每轮至少前进 1 字节」，于是同一字段被反复
# 读到、游标来回跳 → 弹幕线程 100% CPU 挂死（不是异常，任何 try/except 都拦不住）。
# _peek_field 又只判 `_pos >= len(data)`，负下标走 Python 负索引还能合法读到尾部字节，
# 所以既不抛 IndexError 也不自曝。
#
# 现契约（本文件逐条钉死）：
#   C1 任何长度消费点先过 `_need`，越界/负数即抛 ValueError("bad tars length")；
#   C2 容器 size 先与缓冲长度比对，超大即抛 ValueError（不得按伪造 size 空转）；
#   C3 畸形帧必须在**常数级时间**内失败——「不挂死、不无界分配」是硬性质；
#   C4 游标单调不减且始终落在 [0, len(data)]（负回退即 C1 失守的直接证据）；
#   C5 平台侧（HuyaDanmaku.decode_message）对任意畸形帧只丢包+debug 日志，绝不让异常
#      冲出弹幕线程。
#   C6 「每轮至少前进 1 字节」由 _assert_progress 兜底：无推进即抛 ValueError，
#      而不是在 while True 里挂死（新增用例 test_no_progress_guard_raises_instead_of_hanging）。
#
# 已知残留（诚实记录，非本文件引入）：_skip 的 STRING1 长度读取与 _take_head 的扩展 tag
# 未过 _need，截断帧上抛的是 IndexError；read_int 的 unpack_from 越界抛 struct.error。
# 三者都被 C5 的 except Exception 吸收，不构成挂死/崩溃，但「降级为可捕获的 ValueError」
# 尚未 100% 兑现 → 见 test_documented_residual_escape_types（已作为遗留点上报）。

import struct
import time
from typing import Any

import pytest

from src.platforms._tars import SIMPLE_LIST, TarsInputStream, TarsOutputStream
from src.platforms.huya import HuyaDanmaku


def _int_field(value: int) -> bytes:
    # Tars 的容器长度/元素长度是「自描述整数域」，必须用生产编码器造，不能手写裸 int32
    out = TarsOutputStream()
    out.write_int(value, 0)
    return out.to_bytes()


def _valid_frame() -> bytes:
    # 用生产编码器造一条「好帧」，再按前缀截断/改长度造畸形帧（不在测试里重写编解码器）
    out = TarsOutputStream()
    out.write_int(123, 0)
    out.write_string("hello", 1)
    out.write_bytes(b"\x01\x02\x03", 2)
    out.write_int(2**40, 3)
    return out.to_bytes()


def _string4_frame(length: int) -> bytes:
    # STRING4 的长度按协议就是裸 int32（解码用 unpack_from(">i")），故此处直接拼
    return bytes([(1 << 4) | 7]) + struct.pack(">i", length) + b"abc"


def _simple_list_frame(length_value: int) -> bytes:
    # SIMPLE_LIST: 字段头 + 元素类型头(BYTE tag0) + 自描述整数长度 + 内容
    return bytes([(2 << 4) | SIMPLE_LIST, 0]) + _int_field(length_value) + b"abc"


# C1：越界与负长度一律 ValueError("bad tars length")
_READERS: dict[str, Any] = {
    # 三个读取入口都走同一 _need 裁决，按帧的头类型挑对应函数
    "read_string": lambda s: s.read_string(1),
    "read_bytes": lambda s: s.read_bytes(2),
}


@pytest.mark.parametrize(
    ("frame", "reader_name"),
    [
        (b"\x16\x05hi", "read_string"),  # STRING1 声明 5 字节，实到 2 字节
        (_string4_frame(200), "read_string"),  # STRING4 声明 200 字节
        (_string4_frame(-1), "read_string"),  # 负长度（0xFFFFFFFF 按 >i 解出 -1）
        (_string4_frame(2**31 - 1), "read_string"),  # 超大长度：不得按它分配
        (_simple_list_frame(10**7), "read_bytes"),  # SIMPLE_LIST 超大
        (_simple_list_frame(-(10**6)), "read_bytes"),  # SIMPLE_LIST 负长度
    ],
    ids=[
        "string1-truncated",
        "string4-oversized",
        "string4-negative",
        "string4-intmax",
        "list-oversized",
        "list-negative",
    ],
)
def test_bad_length_fields_raise_value_error(frame: bytes, reader_name: str) -> None:
    stream = TarsInputStream(frame)
    started = time.monotonic()
    with pytest.raises(ValueError, match="bad tars length"):
        _READERS[reader_name](stream)
    # C3：失败必须是「立刻」失败——旧实现会在这里分配 GB 级缓冲或空转数十亿次
    assert time.monotonic() - started < 1.0, "畸形长度字段未在 1s 内失败，疑似无界分配/空转"
    # C4：抛错后游标仍须落在缓冲范围内
    assert 0 <= stream._pos <= len(frame)


# C2：容器 size 上限（LIST 每元素≥1 字节、MAP 每对≥2 字节）
@pytest.mark.parametrize(("type_id", "size"), [(9, 10**7), (8, 10**7), (9, 2**31 - 1), (8, 2**31 - 1)])
def test_huge_container_sizes_rejected(type_id: int, size: int) -> None:
    frame = bytes([type_id]) + _int_field(size) + b"\x00"
    stream = TarsInputStream(frame)
    started = time.monotonic()
    with pytest.raises(ValueError, match="bad tars (list|map) size"):
        stream._skip(type_id)
    assert time.monotonic() - started < 1.0, "容器按伪造 size 空转"


@pytest.mark.parametrize("type_id", [9, 8])
def test_negative_container_size_terminates_without_rewinding(type_id: int) -> None:
    # 现状：容器用的是 `if n > len(data)` 而**没有**下界判定，故负 size 不抛错，
    # 只是 range(负数) 零次迭代 = 当作空容器跳过。这不再制造死循环（CR-03 的主症状已消除），
    # 但把「损坏帧」当成「空容器」静默放过，与 C1 的负长度裁决口径不一致 → 已作为遗留点上报。
    # 本用例因此钉的是真正要紧的性质：立刻返回、且游标不回退（不会重新吃掉同一字段）。
    frame = bytes([type_id]) + _int_field(-1) + b"\x00"
    stream = TarsInputStream(frame)
    started = time.monotonic()
    stream._skip(type_id)
    assert time.monotonic() - started < 1.0, "负 size 未在 1s 内返回"
    assert 0 <= stream._pos <= len(frame)


# C4 + C3：对一条好帧的**每一个前缀**跑遍全部公开读接口
def test_every_truncated_prefix_fails_fast_and_never_rewinds() -> None:
    base = _valid_frame()
    readers = {
        "read_int0": lambda s: s.read_int(0),
        "read_int3": lambda s: s.read_int(3),
        "read_string1": lambda s: s.read_string(1),
        "read_bytes2": lambda s: s.read_bytes(2),
        "finish_struct": lambda s: s.finish_struct(),
        "goto0": lambda s: s._goto(0),
        "skip_struct": lambda s: s.read_struct(0, lambda inner: inner.finish_struct()),
    }
    started = time.monotonic()
    for cut in range(len(base) + 1):
        data = base[:cut]
        for name, fn in readers.items():
            stream = TarsInputStream(data)
            try:
                fn(stream)
            except ValueError, IndexError, struct.error:
                # 允许的错误形态都属「立刻失败」（异常类型的不对称由下面的专用用例记录）
                pass
            # C4：无论成功还是抛错，游标都不许回退到负数或越过缓冲末尾
            assert 0 <= stream._pos <= len(data), f"cut={cut} reader={name} 游标越界: {stream._pos}"
    # 31 字节 × 7 个入口的全部前缀组合必须很快跑完（挂死即此断言变红）
    assert time.monotonic() - started < 5.0, "截断帧扫描耗时异常，疑似解析卡死"


# 已知残留（不改生产，仅钉死现状：错误类型一旦扩散到这三类之外即变红）
def test_documented_residual_escape_types() -> None:
    # _skip 的 STRING1 长度读取（`n = self._data[self._pos]`）与 _take_head 的扩展 tag、
    # read_int 的 unpack_from 均未先过 _need → 截断帧抛出的是 IndexError / struct.error，
    # 而不是 CR-03 注释承诺的 ValueError。三者都被平台侧 except Exception 吸收（见 C5），
    # 不构成挂死或崩溃，但异常类型不统一会让「畸形帧」与「解码器 bug」在日志里难以区分。
    with pytest.raises(IndexError):
        TarsInputStream(b"\x16").finish_struct()  # STRING1 头之后没有长度字节

    with pytest.raises(struct.error):
        TarsInputStream(b"\x22\x00\x00").read_int(2)  # INT4 头之后不足 4 字节

    with pytest.raises(IndexError):
        TarsInputStream(b"\xf0").finish_struct()  # tag==15 的扩展 tag 字节缺失


# C6：_assert_progress —— 「本轮无推进即抛错」的最后防线。C1/C2 挡的是「长度字段本身」，
# 但 while True 循环的正确性还依赖「每轮至少前进 1 字节」这一**不变式**；一旦某个类型分支
# 忘记消费字节（新增 Tars 类型、或 _skip 被改坏），没有这道断言就是确定性 100% CPU 挂死，
# 而且不是异常，任何 try/except 都拦不住。
# 用例做法：把 _skip 换成「什么都不消费」的替身，令不变式被人为破坏，再断言
# finish_struct / _goto 立刻抛 "tars parse stuck"。_peek_field 同时带**调用次数上限**，
# 这样即使守卫被删，循环也会在有限轮后自行退出 → 用例变红而不是挂死整个会话。
@pytest.mark.parametrize("entry", ["finish_struct", "goto"])
def test_no_progress_guard_raises_instead_of_hanging(entry: str, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"peek": 0}

    def _peek(self: TarsInputStream) -> tuple[int, int] | None:
        calls["peek"] += 1
        if calls["peek"] > 8:  # 兜底：守卫被删时靠这里退出，绝不让用例挂死
            return None
        return 1, 0  # BYTE 类型、tag 0（_goto 用更大的目标 tag，才会走「跳过未知字段」分支）

    monkeypatch.setattr(TarsInputStream, "_peek_field", _peek)
    monkeypatch.setattr(TarsInputStream, "_take_head", lambda self: (1, 0))
    monkeypatch.setattr(TarsInputStream, "_skip", lambda self, typ: None)

    stream = TarsInputStream(b"\x00" * 8)
    started = time.monotonic()
    with pytest.raises(ValueError, match="tars parse stuck"):
        if entry == "finish_struct":
            stream.finish_struct()
        else:
            stream._goto(5)
    assert time.monotonic() - started < 1.0, "无推进守卫未在 1s 内发作"
    # 守卫必须在**第一轮**就发作：走到第 2 轮才抛说明它检查的是别的东西，挂死窗口仍在
    assert calls["peek"] == 1, f"守卫延迟到第 {calls['peek']} 轮才发作"


# C5：平台侧只丢包，异常绝不冲出弹幕线程
@pytest.mark.parametrize(
    "frame",
    [
        b"",
        b"\x00",
        b"\x16",
        b"\xff" * 40,
        _string4_frame(2**31 - 1),
        _string4_frame(-1),
        _simple_list_frame(10**7),
        bytes([9]) + _int_field(10**7),
        b"\x16\x05hi",
    ],
)
def test_huya_decoder_swallows_malformed_frames(frame: bytes, monkeypatch: pytest.MonkeyPatch) -> None:
    # 真实 HuyaDanmaku.decode_message：任何畸形帧都不得抛到调用方（WsClient 收包循环）
    emitted: list[object] = []
    monkeypatch.setattr(HuyaDanmaku, "_emit", lambda self, *a, **k: emitted.append(a))
    client = HuyaDanmaku(on_message=lambda m: None, on_close=lambda r: None, on_ready=lambda: None)
    started = time.monotonic()
    client.decode_message(frame)
    assert time.monotonic() - started < 2.0, "畸形帧解码未在 2s 内失败"
    assert emitted == []
