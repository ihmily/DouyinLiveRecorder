# CR-04 跨层默认值回归锁：only_fans 的「None = 不覆盖」契约。
#
# 三层链条（任一层改回硬默认值都会让上一层的修复静默失效）：
#   ① src/__init__.py::get_danmaku_collector(only_fans=None)
#   ② src/collector.py::DanmakuCollector.__init__(only_fans=None)，且 _run 内只在
#      `self._only_fans is not None` 时才覆盖实例属性；
#   ③ src/platforms/douyu.py::DouyuDanmaku.__init__(only_fans=False)——刻意关掉「只保留粉丝弹幕」
#      的默认过滤（审查 C-3：dart 上游根本没有粉丝过滤）。
# 历史事故：①② 原默认为 True，于是 ③ 的 False 在真实调用链上被反向覆盖，斗鱼只剩极少数粉丝弹幕、
# 普通弹幕被静默丢弃且无任何日志。本文件用**真实**工厂 + **真实**采集器 + **真实**平台类跑一遍，
# 只把网络层 danmaku.start 打桩（AGENTS：允许打桩网络层/时间常量，不得自实现被测逻辑）。

import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any

import pytest

from src import get_danmaku_collector
from src.collector import DanmakuCollector
from src.platforms.douyu import DouyuDanmaku
from src.platforms.huya import HuyaDanmaku

_ARGS: dict[str, Any] = {"room_id": "36252"}


def _drive_and_observe(
    collector: DanmakuCollector,
    danmaku_cls: type,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    # 启动真实采集线程，让真实 _run 去实例化平台类并落 only_fans；返回实例上的实际值。
    seen = threading.Event()
    captured: list[Any] = []

    async def _fake_start(self: Any, args: Any) -> None:
        # 网络层替身：只记录「采集器覆盖之后」实例上的 _only_fans。之后必须**无限阻塞**——
        # 真实契约是「start() 阻塞直到连接关闭或 stop() 被调用」。替身若立即返回，_run 会抢先关掉
        # 事件循环，与随后 collector.stop() 投递的 _shutdown 协程竞态（表现为 RuntimeWarning
        # 「coroutine _shutdown was never awaited」+ pending task 刷屏）。由生产侧 _shutdown 的
        # task.cancel() 收尾，本用例同时覆盖 MIN-23 的取消链。
        captured.append(getattr(self, "_only_fans", "<absent>"))
        seen.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(danmaku_cls, "start", _fake_start)
    collector.start()
    try:
        assert seen.wait(timeout=10), "采集线程未在 10s 内跑到 danmaku.start()，_run 主链路可能被改动"
    finally:
        # stop() 幂等且有界 join；放在 finally 里避免用例失败时留下活的采集线程
        collector.stop(timeout=10)
    assert captured, "未捕获到弹幕实例"
    return captured[0]


def _douyu_collector(tmp_path: Path, **kwargs: Any) -> DanmakuCollector:
    # base_filename 一律落在 tmp_path：write_srt=False 本就不该产出文件，落 tmp 更保险
    return DanmakuCollector(
        danmaku_cls=DouyuDanmaku,
        danmaku_args=_ARGS,
        base_filename=str(tmp_path / "v"),
        write_srt=False,
        **kwargs,
    )


def test_three_layer_defaults_are_none_none_false() -> None:
    # 签名层：①② 必须是 None（不指定＝不覆盖），③ 必须是 False（平台自己的默认）
    assert inspect.signature(get_danmaku_collector).parameters["only_fans"].default is None
    assert inspect.signature(DanmakuCollector.__init__).parameters["only_fans"].default is None
    assert inspect.signature(DouyuDanmaku.__init__).parameters["only_fans"].default is False


def test_default_collector_keeps_douyu_platform_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 关键回归：整条链都用默认值时，斗鱼实例必须是 False（不过滤）。
    # ①②任一层改回 True，这里就会拿到 True ——正是当年静默丢弹幕的形态。
    assert _drive_and_observe(_douyu_collector(tmp_path), DouyuDanmaku, monkeypatch) is False

    factory_collector = get_danmaku_collector("斗鱼直播", _ARGS, str(tmp_path / "f"))
    # 工厂返回 None 说明平台名/参数契约变了——必须显式失败，不能退回手工构造的采集器
    assert factory_collector is not None, "get_danmaku_collector 对斗鱼返回 None，工厂契约已变"
    assert _drive_and_observe(factory_collector, DouyuDanmaku, monkeypatch) is False


def test_explicit_only_fans_still_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 「None = 不覆盖」不等于「永远不覆盖」：显式传 True/False 必须仍然生效，
    # 否则 main 侧将来接一个配置开关会静默失灵。
    assert _drive_and_observe(_douyu_collector(tmp_path, only_fans=True), DouyuDanmaku, monkeypatch) is True
    assert _drive_and_observe(_douyu_collector(tmp_path, only_fans=False), DouyuDanmaku, monkeypatch) is False


def test_platform_without_only_fans_attr_is_not_touched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # ③ 层不支持该开关（HuyaDanmaku 没有 _only_fans）时，采集器既不能抛错也不能凭空造属性：
    # hasattr 守卫一旦被删，`danmaku._only_fans = True` 会给无过滤能力的平台挂上哑字段，
    # 表现为「用户开了粉丝过滤但一条都不过滤」——静默失效，比抛错更糟。
    collector = DanmakuCollector(
        danmaku_cls=HuyaDanmaku,
        danmaku_args={"ayyuid": "1", "topSid": "2"},
        base_filename=str(tmp_path / "v"),
        only_fans=True,
        write_srt=False,
    )
    assert _drive_and_observe(collector, HuyaDanmaku, monkeypatch) == "<absent>"


def test_factory_forwards_only_fans_to_collector() -> None:
    # ① 层必须把参数**原样**透传给 ②，不得在工厂里补默认值（补了就等于回到旧缺陷）。
    with_true = get_danmaku_collector("斗鱼直播", _ARGS, "v", only_fans=True)
    assert with_true is not None and with_true._only_fans is True
    with_none = get_danmaku_collector("斗鱼直播", _ARGS, "v")
    assert with_none is not None and with_none._only_fans is None
    # 平台不支持 / 参数为空 → 返回 None（既有契约，防止有人把工厂改成抛错）
    assert get_danmaku_collector("不存在的平台", _ARGS, "v") is None
    assert get_danmaku_collector("斗鱼直播", {}, "v") is None
