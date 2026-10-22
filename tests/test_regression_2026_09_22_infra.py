# 组「基础设施/旁路链路」（2026-09-22）回归锁：弹幕边车归档窗口、stats 线程自注销、
# web_console 重开失败回退、SRT 终态位、ffmpeg 清理事实同源。
#
# 与既有同名单元文件的分工：test_danmaku_monitor.py / test_log_archive.py / test_srt_writer.py /
# test_ffmpeg_proc.py 覆盖各模块**既有契约**；本文件只放本轮整改对应的**失效形态**锁
# （修复前必红、修复后必绿），不重复既有断言。
#   MID-2243  边车 close_file() 之后的惰性重开顶穿日志归档的改名窗口
#   MIN-2236④ stats 线程退出不自注销 + 唯一调用点在 room_started → 统计永久冻结
#   MID-2258  web_console 重开失败即 return，把已关闭对象留在 sys.stdout 上
#   MIN-2236③ SrtWriter.close() 无终态位 → 节流重开以追加模式把块号归 0（块号回卷）
#   MIN-2236② ffmpeg 清理的注册表复核与「未确认」告警用两套互斥事实 + 预算配不平
#   L-18（2026-10-18）边车轮转 os.replace 失败被静默吞掉且无记忆 → 此后每条事件重走 close/replace/open
#   MT-11（同批）test_window_is_closed_even_when_rename_fails 的 rename 替身改落 la 命名空间（M-27 同形态）
#
# 全部离线：不启动真实 ffmpeg、不联网，文件 IO 只落在 tmp_path。

import os
import sys
import threading
import time
import types
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
from loguru import logger

import src.danmaku_monitor as dm
import src.ffmpeg_proc as fp
import src.log_archive as la
import src.srt_writer as sw
from src.danmaku_monitor import DanmakuMonitorHub
from src.srt_writer import SrtWriter


def _capture_logs(level: str = "DEBUG") -> tuple[list[str], int]:
    # loguru 是进程级单例，临时加一个 handler 即可抓到本用例期间的全部日志
    captured: list[str] = []
    handler_id = logger.add(lambda msg: captured.append(str(msg)), level=level)
    return captured, handler_id


def _wait_until(predicate: Callable[[], bool], timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _sidecar_events(path: Path, ev: str) -> list[str]:
    # 读边车文件里某一类事件行。先等队列排空——MID-25 之后写盘在独立线程，
    # 不 flush 就读文件会读到半截，断言就成了随机结果。
    dm._get_sidecar().drain()
    if not path.is_file():
        return []
    needle = f'"{ev}"'
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if needle in ln]


def _silence_hub(hub: DanmakuMonitorHub) -> None:
    # 收尾：停掉周期 stats 线程并释放边车句柄（句柄留在进程级写线程里会拖到会话结束，
    #  tmp_path 被清理后只会留下一串写失败 debug，但句柄本身要到 GC 才关）
    hub._stats_stop.set()
    hub.resume_writes()
    hub.close_file()


# ─── MID-2243：归档窗口抑制（边车不被惰性重开顶穿） ─────────────


class TestSidecarArchiveWindow:
    def test_suspend_window_drops_events_and_resume_reopens(self, tmp_path: Path) -> None:
        # 抑制期内到达的事件一律丢弃、且不重新持有句柄；解除抑制后自动重开。修复前 close_file()
        # 只关一次，之后任何延迟事件都会重开文件，而归档改名与 close 之间没有同步点 → Windows 下
        # 改名必抛 PermissionError。
        path = tmp_path / "danmaku_monitor.jsonl"
        hub = DanmakuMonitorHub(log_path=str(path))
        try:
            hub.room_message("房间A", "chat", "用户", "窗口外第一条")
            assert hub.flush()
            assert hub._file is not None
            size_before = path.stat().st_size

            hub.suspend_writes()
            assert hub.writes_suspended() is True
            assert hub._file is None

            hub.room_message("房间A", "chat", "用户", "抑制期内的聊天")
            hub.room_message("房间A", "gift", "老板", "抑制期内的礼物")
            assert hub.flush()
            assert hub._file is None, "抑制期内仍有事件把边车文件重新打开"
            assert path.stat().st_size == size_before, "抑制期内文件被追加过"

            hub.resume_writes()
            assert hub.writes_suspended() is False
            hub.room_message("房间A", "chat", "用户", "解除抑制之后")
            assert hub.flush()
            assert hub._file is not None, "解除抑制后未能自动重开"
            assert path.stat().st_size > size_before
        finally:
            _silence_hub(hub)

    def test_events_queued_before_suspend_do_not_reopen_handle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 「置位之前就已入队」的指令也必须丢弃——这是 MID-2243 的关键一半：只挡新入队的话，
        # 慢盘期间排进队列的事件仍会在 drain 返回那刻重开文件，是否重开就又交回了调度时序。
        # 做法：让首条写盘真正卡住，期间排进 5 条，再置位、放行。
        path = tmp_path / "danmaku_monitor.jsonl"
        started = threading.Event()
        release = threading.Event()
        first = threading.Event()
        real_append = dm._append_sidecar_line

        def _slow_append(files: dict[str, Any], target: str, line: str) -> None:
            if not first.is_set():
                first.set()
                started.set()
                assert release.wait(timeout=10), "测试未在 10s 内放行慢写入"
            real_append(files, target, line)

        monkeypatch.setattr(dm, "_append_sidecar_line", _slow_append)
        hub = DanmakuMonitorHub(log_path=str(path))
        try:
            hub.room_message("房间A", "chat", "用户", "第一条")
            assert started.wait(3), "写线程未执行到落盘函数"
            for i in range(5):
                hub.room_message("房间A", "chat", "用户", f"排队{i}")

            # suspend_writes() = 「置位 + close_file()」，这里拆成两步：close_file() 会等
            # 队列排空，而首条此刻仍被本用例故意卡住，必须先放行才能排空。
            dm._get_sidecar().suspend(str(path))
            release.set()
            hub.close_file()

            assert len(_sidecar_events(path, "msg")) == 1, "抑制标记置位前排队的指令仍落了盘"
            assert hub._file is None
        finally:
            _silence_hub(hub)

    def test_archive_runtime_logs_suppresses_only_inside_the_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 接线锁：归档链路必须真的「进窗口 → 改名 → 出窗口」。改名时刻在窗口内投递一条
        # 事件，断言它既没打开句柄也没落盘；归档结束后解除抑制、监控恢复正常
        # （否则 GUI 面板永久停更，比原缺陷更难被发现）。
        logs = tmp_path / "logs"
        logs.mkdir()
        monkeypatch.delenv(la._DISABLE_ENV, raising=False)
        monkeypatch.delenv(la.GUI_PARENT_ENV, raising=False)
        monkeypatch.setattr(la, "script_path", str(tmp_path))
        monkeypatch.setattr(la, "remove_file_sinks", lambda: None)
        monkeypatch.setattr(la, "add_file_sinks", lambda: None)
        hub = DanmakuMonitorHub(log_path=str(logs / "danmaku_monitor.jsonl"))
        monkeypatch.setattr(dm, "_hub", hub)
        sidecar_path = logs / "danmaku_monitor.jsonl"
        try:
            hub.room_message("房间A", "chat", "用户", "窗口外")
            assert hub.flush()
            assert sidecar_path.is_file()

            observed: dict[str, bool] = {}
            real_rename_one = la._rename_one

            def _spy_rename_one(p: str, ts: str, archived: list[str]) -> None:
                if os.path.basename(p) == "danmaku_monitor.jsonl":
                    observed["suspended"] = hub.writes_suspended()
                    hub.room_message("房间A", "chat", "用户", "改名窗口内到达")
                    observed["handle"] = hub._file is not None
                real_rename_one(p, ts, archived)

            monkeypatch.setattr(la, "_rename_one", _spy_rename_one)
            archived = la.archive_runtime_logs(reopen_streams=False)

            assert observed == {"suspended": True, "handle": False}, observed
            archived_sidecar = [p for p in archived if os.path.basename(p).startswith("danmaku_monitor_")]
            assert archived_sidecar, archived
            assert hub.writes_suspended() is False, "归档结束后未解除抑制"
            # 改名窗口内投递的那条事件不得出现在被归档的那份文件里
            with open(archived_sidecar[0], encoding="utf-8") as fh:
                assert "改名窗口内到达" not in fh.read()

            hub.room_message("房间A", "chat", "用户", "窗口之后")
            assert hub.flush()
            assert sidecar_path.is_file()
            assert "窗口之后" in sidecar_path.read_text(encoding="utf-8")
        finally:
            _silence_hub(hub)

    def test_window_is_closed_even_when_rename_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 改名失败（句柄被第三方进程占用等）也必须退出窗口——抑制只是一次改名的手段，
        # 把它变成终态会让弹幕监控永久停更。
        logs = tmp_path / "logs"
        logs.mkdir()
        monkeypatch.delenv(la._DISABLE_ENV, raising=False)
        monkeypatch.delenv(la.GUI_PARENT_ENV, raising=False)
        monkeypatch.setattr(la, "script_path", str(tmp_path))
        monkeypatch.setattr(la, "remove_file_sinks", lambda: None)
        monkeypatch.setattr(la, "add_file_sinks", lambda: None)
        hub = DanmakuMonitorHub(log_path=str(logs / "danmaku_monitor.jsonl"))
        monkeypatch.setattr(dm, "_hub", hub)
        sidecar_path = logs / "danmaku_monitor.jsonl"
        hub.room_message("房间A", "chat", "用户", "窗口外")
        assert hub.flush()

        real_rename = os.rename

        def _deny_sidecar_rename(src: str, dst: str) -> None:
            if os.path.basename(src) == "danmaku_monitor.jsonl":
                raise PermissionError(32, "模拟改名失败")
            real_rename(src, dst)

        # MT-11（2026-10-18）：原写法 `monkeypatch.setattr(os, "rename", ...)` 改的是**全进程唯一**
        # 的 os 模块本体（M-27 同形态，仓库已定性为跨用例竞态源）——替身窗口内 loguru 的文件轮转、
        # 弹幕边车、GUI/录制后台线程的 rename 一并命中「遇 danmaku_monitor.jsonl 就抛 PermissionError」。
        # 现按仓库口径：浅拷贝 + 只覆盖所需属性 + 落进被测模块命名空间。
        monkeypatch.setattr(la, "os", types.SimpleNamespace(**{**vars(os), "rename": _deny_sidecar_rename}))
        # 反向见证：替身只落进 src.log_archive 的命名空间，进程全局 os.rename 必须仍是真实现
        assert os.rename is real_rename
        try:
            assert la.archive_runtime_logs(reopen_streams=False) == []
            assert hub.writes_suspended() is False, "改名失败后抑制标记未复位"
            hub.room_message("房间A", "chat", "用户", "失败之后仍要能写")
            assert hub.flush()
            assert "失败之后仍要能写" in sidecar_path.read_text(encoding="utf-8")
        finally:
            _silence_hub(hub)

    def test_suppressed_events_are_observable(self, tmp_path: Path) -> None:
        # 抑制期丢弃不得静默：至少留一条 debug 计数。边车是 GUI 面板的唯一数据源，
        # 「面板为什么少了若干条」必须能从日志里回答。
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
        try:
            hub.suspend_writes()
            captured, handler_id = _capture_logs()
            try:
                hub.room_message("房间A", "chat", "用户", "抑制期内")
            finally:
                logger.remove(handler_id)
            assert any("归档窗口内丢弃" in m for m in captured), captured
        finally:
            _silence_hub(hub)


# ─── L-18：边车轮转失败的按路径退避（不再每条事件重试） ───────────


class TestSidecarRotateBackoff:
    # 三条锁都直接驱动 _append_sidecar_line（MID-25 起它既是生产实现也是给测试留的注入口），不经
    # hub/写线程：轮转只在句柄 tell() 越阈值时发生，用真线程反而要把队列排空时机也钉进断言。
    # os.replace 替身按 M-27/MT-11 口径只落进 src.danmaku_monitor 的命名空间。
    @staticmethod
    def _close_all(files: dict[str, Any]) -> None:
        for fh in files.values():
            if not fh.closed:
                fh.close()

    def test_rotate_failure_backs_off_warns_and_still_appends(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # L-18：`.1` 被占用 / 跨卷时 os.replace 必失败，旧实现在 except OSError 里 pass 且不留任何
        # 记忆，而失败后重开的句柄 tell() 依旧 >= _ROTATE_BYTES，于是此后**每一条**事件都会重走
        # close → replace → open（80 房间 × 10 条/秒下即每秒数百次注定失败的磁盘操作）。
        # 现按路径记一个退避窗口：期内跳过轮转、**照常追加**，并留一条 warning。
        path = str(tmp_path / "dm.jsonl")
        monkeypatch.setattr(dm, "_ROTATE_BYTES", 8)
        attempts: list[str] = []
        real_replace = os.replace

        def _boom(src: str, dst: str) -> None:
            # 只对**本用例自己那只文件**制造失败：`dm.os` 是进程唯一的模块命名空间，其它用例的边车
            # 写线程会在本窗口内走进同一支替身（2026-10-18 全量 pytest 实测：别家 tmp_path 的 dm.jsonl
            # 混进 attempts，断言由 1 变 5；反向还会把别人的轮转打坏）。其余调用透传真实实现。
            if src != path:
                real_replace(src, dst)
                return
            attempts.append(src)
            raise PermissionError(32, "模拟 .1 备份被占用")

        monkeypatch.setattr(dm, "os", types.SimpleNamespace(**{**vars(os), "replace": _boom}))
        files: dict[str, Any] = {}
        captured, handler_id = _capture_logs(level="WARNING")
        try:
            for i in range(6):
                dm._append_sidecar_line(files, path, f"line-{i}")
            assert len(attempts) == 1, f"轮转失败后仍在每条事件上重试: {len(attempts)} 次"
            warns = [m for m in captured if "rotate" in m and "处理失败" in m]
            assert len(warns) == 1, f"轮转失败缺少可归因的告警（或重复刷屏）: {warns}"
            # 「跳过轮转」不等于「丢掉数据」：六行必须一条不少地还在原文件里
            assert Path(path).read_text(encoding="utf-8").splitlines() == [f"line-{i}" for i in range(6)]
        finally:
            logger.remove(handler_id)
            self._close_all(files)

    def test_rotate_backoff_expires_and_retries(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 反向锁：退避**不是**把轮转永久关掉。周期压成负数 = 「下一条即过期」，
        # 于是每条超阈值事件都会再试一次；若实现被改成一次性永久标记，本用例的 attempts 会停在 1。
        path = str(tmp_path / "dm.jsonl")
        monkeypatch.setattr(dm, "_ROTATE_BYTES", 8)
        monkeypatch.setattr(dm, "_ROTATE_RETRY_BACKOFF_SECONDS", -1.0)
        attempts: list[str] = []
        real_replace = os.replace

        def _boom(src: str, dst: str) -> None:
            # 同上一条：只 sabotage 本用例自己的路径，别家线程的轮转透传真实实现（跨用例竞态防线）。
            if src != path:
                real_replace(src, dst)
                return
            attempts.append(src)
            raise PermissionError(32, "模拟 .1 备份被占用")

        monkeypatch.setattr(dm, "os", types.SimpleNamespace(**{**vars(os), "replace": _boom}))
        files: dict[str, Any] = {}
        captured, handler_id = _capture_logs(level="WARNING")
        try:
            for i in range(4):
                dm._append_sidecar_line(files, path, f"line-{i}")
            # 断言用「>=2」而非精确次数：越过阈值的具体那一轮取决于 TextIOWrapper.tell() 的 cookie
            # 形态，写死会把用例变成字节算术锁；这里只钉「过期后确实会再试」。
            assert len(attempts) >= 2, f"退避到期后未重试轮转: {attempts}"
            warns = [m for m in captured if "rotate" in m and "处理失败" in m]
            assert len(warns) == len(attempts), "每次重试失败都应留下一条 warning"
        finally:
            logger.remove(handler_id)
            self._close_all(files)

    def test_rotation_recovers_and_clears_backoff_after_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 占用恢复后必须回到正常节奏：失败→置标记→标记过期→重试成功→历史进 .1，
        # 且过期条目由 _rotate_in_backoff 就地弹出（字典不留僵尸键，成功一侧无需再写清除分支）。
        path = str(tmp_path / "dm.jsonl")
        monkeypatch.setattr(dm, "_ROTATE_BYTES", 8)
        monkeypatch.setattr(dm, "_ROTATE_RETRY_BACKOFF_SECONDS", 0.05)
        attempts: list[str] = []
        state = {"boom": True}
        real_replace = os.replace

        def _maybe_boom(src: str, dst: str) -> None:
            # 同族跨用例竞态防线：别家路径不记账、不破坏，直接透传（否则 attempts 会被别的
            # 边车写线程喂脏，本用例的「失败 1 次 → 过期 → 重试成功」计数不再成立）。
            if src != path:
                real_replace(src, dst)
                return
            attempts.append(src)
            if state["boom"]:
                raise PermissionError(32, "模拟 .1 备份被占用")
            real_replace(src, dst)

        monkeypatch.setattr(dm, "os", types.SimpleNamespace(**{**vars(os), "replace": _maybe_boom}))
        files: dict[str, Any] = {}
        try:
            for i in range(3):
                dm._append_sidecar_line(files, path, f"line-{i}")
            assert len(attempts) == 1
            assert path in dm._rotate_backoff_until, "轮转失败后未置退避标记"
            state["boom"] = False
            time.sleep(0.08)
            dm._append_sidecar_line(files, path, "line-3")
            assert len(attempts) == 2, "退避到期后未重试"
            assert path not in dm._rotate_backoff_until, "轮转成功后未清除退避标记"
            assert (tmp_path / "dm.jsonl.1").is_file(), "重试成功却没有产生 .1 备份"
        finally:
            self._close_all(files)


# ─── MIN-2236④：stats 线程自注销 + room_message 侧兜底拉起 ────────


class _BoomStopEvent(threading.Event):
    # 注入「stats 线程在 while 条件处异常退出」这一形态。继承 threading.Event 而非拿裸对象顶替，
    # 是为了让 hub._stats_stop 的声明类型仍成立（本仓 mypy 连 tests/ 一起查）。
    def wait(self, timeout: float | None = None) -> bool:
        raise RuntimeError("模拟 stats 线程异常退出")


class TestStatsThreadLifecycle:
    def test_room_message_also_starts_stats_thread(self, tmp_path: Path) -> None:
        # 未经 room_started 隐式注册的房间（room_message 里 get→setdefault 那条分支）也得把周期
        # 统计线程拉起来：修复前唯一调用点在 room_started，这类房间的 msg_rate/online 永不刷新。
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
        try:
            assert hub._stats_thread is None
            hub.room_message("房间A", "chat", "用户", "只有弹幕到达这一条路径")
            thread = hub._stats_thread
            assert thread is not None, "room_message 未兜底拉起 stats 线程"
            assert thread.is_alive()
        finally:
            _silence_hub(hub)

    def test_crashed_thread_deregisters_and_next_message_recovers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 崩溃 → 自注销 → 下一条消息拉起新线程 → 统计事件重新落盘，整条恢复链路一次跑完。
        # 修复前：线程死了 self._stats_thread 仍指向那支死线程，而判活只看 is_alive()，
        # 房间表非空时既不会再有 room_started、老引用也清不掉 → 统计永久冻结。
        monkeypatch.setattr(dm, "_STATS_INTERVAL", 0.05)
        path = tmp_path / "dm.jsonl"
        hub = DanmakuMonitorHub(log_path=str(path))
        real_stop = hub._stats_stop
        try:
            hub.room_started("房间A", "抖音直播")
            first_thread = hub._stats_thread
            assert first_thread is not None and first_thread.is_alive()
            assert _wait_until(lambda: len(_sidecar_events(path, "stats")) > 0), "stats 线程未产出统计事件"

            captured, handler_id = _capture_logs(level="WARNING")
            try:
                monkeypatch.setattr(hub, "_stats_stop", _BoomStopEvent())
                assert _wait_until(lambda: hub._stats_thread is None), "stats 线程退出后未自注销引用"
                assert any("线程异常退出" in m for m in captured), f"缺少异常退出告警: {captured}"
            finally:
                logger.remove(handler_id)

            before = len(_sidecar_events(path, "stats"))
            monkeypatch.setattr(hub, "_stats_stop", real_stop)
            hub.room_message("房间A", "chat", "用户", "崩溃后的第一条")
            second_thread = hub._stats_thread
            assert second_thread is not None and second_thread is not first_thread, "未能重新拉起 stats 线程"
            assert _wait_until(lambda: len(_sidecar_events(path, "stats")) > before), "新线程未恢复统计落盘"
        finally:
            _silence_hub(hub)

    def test_empty_room_exit_also_deregisters(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # 「无房间自然退出」这条路径同样要自注销（每轮停止监控都会发生）：
        # 不清引用就等 room_started 才重启，隐式注册的房间永远等不到。
        monkeypatch.setattr(dm, "_STATS_INTERVAL", 0.05)
        hub = DanmakuMonitorHub(log_path=str(tmp_path / "dm.jsonl"))
        try:
            hub.room_started("房间A", "抖音直播")
            dead = hub._stats_thread
            assert dead is not None
            hub.room_stopped("房间A")
            dead.join(timeout=10)
            assert hub._rooms == {}
            assert _wait_until(lambda: hub._stats_thread is None), "正常退出未自注销 stats 线程引用"
        finally:
            _silence_hub(hub)


# ─── MID-2258：web_console 重开失败必须回退到 devnull ────────────


class TestWebConsoleRebindFallback:
    def test_rebind_failure_falls_back_to_devnull_and_recovers_next_round(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        logs = tmp_path / "logs"
        logs.mkdir()
        monkeypatch.delenv(la._DISABLE_ENV, raising=False)
        monkeypatch.delenv(la.GUI_PARENT_ENV, raising=False)
        monkeypatch.setattr(la, "script_path", str(tmp_path))
        monkeypatch.setattr(la, "remove_file_sinks", lambda: None)
        monkeypatch.setattr(la, "add_file_sinks", lambda: None)
        monkeypatch.setattr(la, "close_monitor_file", lambda: None)
        monkeypatch.setattr(la, "_web_console_rebind_pending", False)
        rebind_calls: list[str] = []
        monkeypatch.setattr(la, "rebind_console_sink", lambda: rebind_calls.append("rebind"))

        path = logs / "web_console.log"
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        created: list[Any] = []
        handle = open(path, "a", encoding="utf-8", buffering=1)
        handle.write("before-stop\n")
        handle.flush()
        monkeypatch.setattr(sys, "stdout", handle)
        monkeypatch.setattr(sys, "stderr", handle)

        def _deny_rebind(file: Any, *args: Any, **kwargs: Any) -> Any:
            # 只让「重开 web_console.log」这一步失败；其余 IO（含 os.devnull）走真实 open
            if str(file) == str(path):
                raise OSError(13, "模拟重开失败")
            return open(file, *args, **kwargs)

        try:
            monkeypatch.setattr(la, "open", _deny_rebind, raising=False)
            archived = la.archive_runtime_logs(reopen_streams=False)
            assert any(os.path.basename(p).startswith("web_console_") for p in archived), archived
            assert handle.closed, "改名前未关闭原句柄"

            stream = sys.stdout
            assert stream is not handle, "重开失败后 sys.stdout 仍指向已关闭对象"
            assert not stream.closed
            assert os.path.abspath(stream.name) == os.path.abspath(os.devnull)
            assert sys.stderr is stream
            assert rebind_calls, "回退路径漏掉 rebind_console_sink()"
            assert la._web_console_rebind_pending is True
            created.append(stream)
            # 本用例的核心断言：print 不再抛 ValueError: I/O operation on closed file
            print("重开失败后的第一条输出，不得抛异常")

            # 下一轮归档：open 恢复可用，pending 分支必须把链路从 devnull 接回真实文件
            monkeypatch.setattr(la, "open", open)
            assert la.archive_runtime_logs(reopen_streams=False) == []
            assert la._web_console_rebind_pending is False
            recovered = sys.stdout
            created.append(recovered)
            assert recovered is not stream
            assert os.path.abspath(recovered.name) == os.path.abspath(str(path))
            assert not recovered.closed
            print("链路已接回真实文件")
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            if not handle.closed:
                handle.close()
            for stream in created:
                if not stream.closed:
                    stream.close()


# ─── MIN-2236③：SrtWriter 终态位 ─────────────────────────────


def _srt_block_numbers(content: str) -> list[int]:
    return [int(ln.strip()) for ln in content.splitlines() if ln.strip().isdigit()]


class TestSrtTerminalState:
    def test_write_after_close_never_reopens_or_rewinds_block_numbers(self, tmp_path: Path) -> None:
        # close() 之后再喂一条「已远超重试间隔」的消息：修复前会走 WD-03 的节流重开分支（write →
        # _open_segment），以追加模式重开同一个 .srt 并把 _index 归 0，块号于是变成 1,2,1——
        # 直接违反 MIN-24① 确立的「块号单调不回卷」。
        base = str(tmp_path / "live")
        writer = SrtWriter(base_filename=base, segment_seconds=None)
        writer.start(now=0.0)
        writer.write("用户1", "弹幕1", now=1.0)
        writer.write("用户2", "弹幕2", now=2.0)
        writer.close()

        path = tmp_path / "live.srt"
        content_before = path.read_text(encoding="utf-8")
        assert _srt_block_numbers(content_before) == [1, 2]

        # 把节流基准推到 100s 之前，等价于「此刻必然触发重试开片」
        writer._last_open_attempt = time.monotonic() - 100.0
        writer.write("用户3", "弹幕3", now=300.0)

        assert writer._fp is None, "close() 之后句柄被重新打开"
        assert writer._index == 2, "close() 之后片内块号被推进/回卷"
        assert path.read_text(encoding="utf-8") == content_before, "close() 之后文件被追加过"

    def test_segment_switch_after_close_does_not_create_new_segment_file(self, tmp_path: Path) -> None:
        # 终态位放在唯一的开句柄入口 _open_segment()：分片切换同样不得重开——录制已收尾后才迟到
        # 的弹幕若把 seg 片新建出来，就会在已封盘的分片序列尾部多出一个「视频不存在、块号从 1
        # 开始」的孤儿 .srt。修复前该形态必然出现：write 里 seg 变化 → _close_locked() +
        # _open_segment(seg)。
        base = str(tmp_path / "late")
        writer = SrtWriter(base_filename=base, segment_seconds=1.0)
        writer.start(now=0.0)
        writer.write("u", "第一条", now=0.2)
        writer.close()
        assert writer._closed is True

        writer.write("u", "迟到跨片", now=5.0)
        assert writer._fp is None, "close() 之后分片切换重新打开了句柄"
        assert not (tmp_path / "late_005.srt").exists(), "close() 之后新建了迟到的分片文件"
        assert _srt_block_numbers((tmp_path / "late_000.srt").read_text(encoding="utf-8")) == [1]

    def test_close_before_start_does_not_create_file(self, tmp_path: Path) -> None:
        # 专测 _open_segment() 那一层守卫（write() 的早返回挡不到它）：采集器「stop 先于 start
        # 落地」的极端时序下，start() 会直接走 _open_segment(0)。修复前它会以追加模式创建
        # {base}.srt —— 录制已经收尾却凭空多出一个空字幕文件。
        base = str(tmp_path / "never")
        writer = SrtWriter(base_filename=base, segment_seconds=None)
        writer.close()
        assert writer._closed is True
        writer.start(now=0.0)
        assert writer._fp is None
        assert not (tmp_path / "never.srt").exists(), "close() 之后 start() 仍创建了 SRT 文件"

    def test_close_lock_timeout_does_not_set_terminal_state(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 反向锁：拿不到写锁时那一轮关闭作废，**不得**置终态位——否则 WD-03 确立的
        # 「close 可重复调用」会被悄悄改成「一次超时即永久丢弃弹幕」。
        monkeypatch.setattr(sw, "_CLOSE_LOCK_TIMEOUT", 0.05)
        writer = SrtWriter(base_filename=str(tmp_path / "busy"), segment_seconds=None)
        writer.start(now=0.0)
        assert writer._lock.acquire()
        try:
            writer.close()  # 超时分支：本次不置位
        finally:
            writer._lock.release()
        assert writer._closed is False
        writer.close()
        assert writer._closed is True


# ─── MIN-2236②：ffmpeg 清理事实同源 + 预算配平 ─────────────────


class _FakeStdin:
    def write(self, data: Any) -> int:
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeProcOnly:
    # 只实现清理链路用到的最小 Popen 接口（不启动真实进程）
    def __init__(self, pid: int = 9911) -> None:
        self.pid = pid
        self.stdin: Any = _FakeStdin()
        self.stdout: Any = None
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode


class _SelfExitingProc(_FakeProcOnly):
    # 模拟「清理线程还在跑三级终止、进程却已经自己退出」的交错：
    # poll() 会在约 0.4s 后转为非 None，而调用方（清理逻辑）尚未确认任何东西。
    def __init__(self, pid: int = 9913) -> None:
        super().__init__(pid=pid)
        self._exited_at = time.monotonic() + 0.4

    def poll(self) -> int | None:
        if self.returncode is None and time.monotonic() >= self._exited_at:
            self.returncode = 0
        return self.returncode


@pytest.fixture(autouse=True)
def _isolate_ffmpeg_registry() -> Any:
    # 注册表是模块级全局：逐用例前后清空，避免残留把别的用例带下水
    with fp._processes_lock:
        fp._ffmpeg_processes.clear()
    yield
    with fp._processes_lock:
        fp._ffmpeg_processes.clear()


def test_cleanup_wait_budget_scales_with_group_serial_depth(monkeypatch: pytest.MonkeyPatch) -> None:
    # 清理线程「组内串行、组间并行」⇒ 预算必须覆盖最忙那一组的串行长度 × 单进程超时。
    # 旧实现写死 45s：进程数 >8（串行深度 2 → 需要 60s）时慢终止必然被误判成未确认。
    assert fp._cleanup_wait_budget(1, 1) > fp._TERMINATE_TIMEOUT_SECONDS
    assert fp._cleanup_wait_budget(16, 8) > 45.0, "两组串行就已超出旧的固定 45s 预算"
    assert fp._cleanup_wait_budget(41, 8) == pytest.approx(6 * fp._TERMINATE_TIMEOUT_SECONDS + 5.0)
    # 显式收窄（排障 / 紧急退出）仍是**上限**语义，不得被公式覆盖
    monkeypatch.setattr(fp, "_CLEANUP_WAIT_SECONDS", 0.3)
    assert fp._cleanup_wait_budget(41, 8) == pytest.approx(0.3)


def test_slow_terminate_is_not_reported_as_unable_to_kill(monkeypatch: pytest.MonkeyPatch) -> None:
    # 「慢终止」样本：三级终止确实在跑（10s 后成功）。第一轮总预算收窄到 1s，此时注册表复核
    # 若另用 poll() 作判据，就会把「正在终止」谎报成「未能终止」；而 worker 稍后真把进程终止了
    # 也没人注销 → 死对象永久留在注册表。
    slow = _FakeProcOnly()

    def _slow_terminate(proc: Any, timeout: int = 30) -> bool:
        _ = timeout
        time.sleep(10.0)
        proc.returncode = 0
        return True

    monkeypatch.setattr(fp, "_terminate_ffmpeg_process", _slow_terminate)
    monkeypatch.setattr(fp, "_CLEANUP_WAIT_SECONDS", 1.0)
    with fp._processes_lock:
        fp._ffmpeg_processes.append(cast(Any, slow))

    captured, handler_id = _capture_logs(level="WARNING")
    try:
        started = time.monotonic()
        fp.cleanup_all_ffmpeg_processes()
        assert time.monotonic() - started < 5.0, "总预算未生效"
        kept = [m for m in captured if "已保留在注册表中" in m]
        # 唯一可接受的措辞：全部计入「未确认」，一个都不许说成「确认未能终止」
        assert any("确认未能终止 0 个" in m and "未确认 1 个" in m for m in kept), kept
        assert slow.poll() is None
        with fp._processes_lock:
            assert list(fp._ffmpeg_processes) == [cast(Any, slow)], "未确认的进程应保留（诚实）"

        # worker 完成后的第二轮：同一处事实下必须把已终止的进程清出注册表
        assert _wait_until(lambda: slow.poll() is not None, timeout=25.0)
        captured.clear()
        fp.cleanup_all_ffmpeg_processes()
        with fp._processes_lock:
            assert fp._ffmpeg_processes == [], "死对象永久留在注册表中"
        assert not any("已保留在注册表中" in m for m in captured), captured
    finally:
        logger.remove(handler_id)


def test_unconfirmed_entry_is_never_dropped_by_the_second_fact(monkeypatch: pytest.MonkeyPatch) -> None:
    # 注册表复核与「未确认」告警必须读同一处事实的反证：worker 还卡在三级终止里（事件未置位），
    # 而进程此刻自己退出了（poll() 已非 None）。旧写法会在这里把条目静默移出注册表，同时却又
    # 宣告「未在总预算内确认、已放弃等待」——同一轮留下两条互相矛盾的事实。
    self_exited = _SelfExitingProc()

    def _wedged(proc: Any, timeout: int = 30) -> bool:
        time.sleep(3.0)
        return True

    monkeypatch.setattr(fp, "_terminate_ffmpeg_process", _wedged)
    monkeypatch.setattr(fp, "_CLEANUP_WAIT_SECONDS", 1.0)
    with fp._processes_lock:
        fp._ffmpeg_processes.append(cast(Any, self_exited))

    captured, handler_id = _capture_logs(level="WARNING")
    try:
        fp.cleanup_all_ffmpeg_processes()
        assert self_exited.poll() is not None, "样本未按预期自行退出"
        assert any("未在" in m and "总预算内全部确认" in m for m in captured), captured
        with fp._processes_lock:
            assert list(fp._ffmpeg_processes) == [
                cast(Any, self_exited)
            ], "未确认的条目被第二套判据（poll()）移出了注册表"
    finally:
        logger.remove(handler_id)


def test_confirmed_surviving_process_is_reported_as_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    # 对偶用例：三级终止跑完仍在（真孤儿）时必须归入「确认未能终止」而不是「未确认」，
    # 否则两类完全不同的故障被压成同一句话，运维无从判断该等还是该手动杀。
    stuck = _FakeProcOnly(pid=9912)

    def _never(proc: Any, timeout: int = 30) -> bool:
        return False

    monkeypatch.setattr(fp, "_terminate_ffmpeg_process", _never)
    with fp._processes_lock:
        fp._ffmpeg_processes.append(cast(Any, stuck))
    captured, handler_id = _capture_logs(level="WARNING")
    try:
        fp.cleanup_all_ffmpeg_processes()
        kept = [m for m in captured if "已保留在注册表中" in m]
        assert any("确认未能终止 1 个" in m and "未确认 0 个" in m for m in kept), kept
        assert any("未能完全终止" in m for m in captured), "缺少单进程级的手动检查告警"
        with fp._processes_lock:
            assert list(fp._ffmpeg_processes) == [cast(Any, stuck)]
    finally:
        logger.remove(handler_id)


def test_registry_recheck_reads_the_same_fact_as_the_warning() -> None:
    # 结构锁：注册表复核处不得再出现 poll() 这第二套事实（「未确认」告警读 event、复核读 poll()
    # 正是 MIN-2236② 的根因形态）。只看有效代码行：本轮修复的注释里必然要提到旧写法。
    source = (Path(__file__).resolve().parents[1] / "src" / "ffmpeg_proc.py").read_text(encoding="utf-8")
    tail = source[source.rindex("with _processes_lock:") :]
    code = "\n".join(ln.split("#", 1)[0] for ln in tail.splitlines())
    assert "confirmed_terminated" in code, code
    assert "poll()" not in code, "注册表复核又用回了 poll()"
