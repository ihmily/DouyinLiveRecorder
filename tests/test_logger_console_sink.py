# 验证控制台 sink 的重建语义（Web 后台模式日志可见性的根因）：
# loguru 的 sink 在 add() 时即绑定具体对象，不会因 sys.stderr 被重新赋值而跟着变。
# web.py::_enter_background_mode 在 src.logger 导入之后才把 sys.stderr 重定向到
# logs/web_console.log 并 SW_HIDE 隐藏控制台窗口——若不重建 sink，DEBUG/WARNING
# 日志会全部写往被隐藏的控制台，web_console.log 里只剩 print 输出。

from __future__ import annotations

import io
import sys
from typing import Iterator

import pytest
from loguru import logger

import src.logger as logger_mod


@pytest.fixture()
def restore_sinks() -> Iterator[None]:
    # 用例内会 remove 并重建 sink，退出时还原一个指向真实 stderr 的 sink，
    # 避免把「无任何 sink」的状态泄漏给后续用例
    original = sys.stderr
    yield
    logger.remove()
    logger_mod._console_sink_id = None
    if original is not None:
        logger_mod._console_sink_id = logger.add(sink=original, level="DEBUG", enqueue=True)


def test_rebind_console_sink_follows_current_stderr(restore_sinks: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # 重定向后的 sys.stderr 必须成为新的日志落点，旧的（隐藏控制台）不再接收
    old_stderr = io.StringIO()
    new_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", old_stderr)
    logger.remove()
    logger_mod._console_sink_id = logger.add(sink=old_stderr, level="DEBUG", format="{message}", enqueue=True)

    # 模拟 web.py 的后台模式：替换 sys.stderr 后重建 sink
    monkeypatch.setattr(sys, "stderr", new_stderr)
    logger_mod.rebind_console_sink()

    logger.debug("probe-message")
    logger.complete()  # enqueue=True 为异步写入，需排空队列后再断言
    assert "probe-message" in new_stderr.getvalue()
    assert old_stderr.getvalue() == ""


def test_rebind_console_sink_removes_previous_sink(restore_sinks: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # 重建必须是「替换」而非「追加」：否则每次重建都会多一份 sink，
    # 同一条日志被重复写入，且旧 sink 仍指向失效对象
    first = io.StringIO()
    second = io.StringIO()
    monkeypatch.setattr(sys, "stderr", first)
    logger.remove()
    logger_mod._console_sink_id = logger.add(sink=first, level="DEBUG", format="{message}", enqueue=True)

    monkeypatch.setattr(sys, "stderr", second)
    logger_mod.rebind_console_sink()
    logger.debug("only-once")
    logger.complete()
    assert second.getvalue().count("only-once") == 1


def test_rebind_console_sink_noop_when_stderr_is_none(restore_sinks: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # 无控制台环境（pythonw / console=False 冻结 exe）下 sys.stderr 为 None：
    # 必须静默跳过而非抛 TypeError（loguru 拒绝 None 作为 sink）
    monkeypatch.setattr(sys, "stderr", None)
    logger.remove()
    logger_mod._console_sink_id = None
    logger_mod.rebind_console_sink()
    assert logger_mod._console_sink_id is None
