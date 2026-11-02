# -*- coding: utf-8 -*-
# src.scheduler 单元测试：覆盖 ResizableSemaphore / PlatformBreaker / ConcurrencyScheduler。
# 聚焦高并发录制调度的关键不变量：信号量可安全调容、熔断器状态机正确、
# 全局并发容量随活跃任务数自适应缩放且带安全下限、按 key 错误预算隔离、录制并发软上限。
# 补 SEV-01（有持有者时重算不得放大可用许可）与 MIN-22（探针代数标记）回归锁：原有 16 用例全部在
# 无持有者场景断言 .value（此时 value == capacity），结构上抓不到该缺陷。追加三组不变量（改回旧形态即应转红）：
#   M-35  动态模式的目标容量必须在 max 之后才封顶，错配的 configured_limit 不得绕过 _max_capacity；
#         固定模式那一支**不**封顶（AGENTS 把固定并发钉成配置值本身），不对称本身也要有锁；
#   M-42  min_samples 必须钳到 1..window，且 open 判据要求真的失败过（fail_rate=0 时
#         全成功窗口不得因 0 >= 0 熔断）；
#   M-36a 熔断表按 host 无界增长（key 属外部可控输入）→ 必须有 LRU 上限，且逐出只碰 closed 键、
#         命中即 touch（仍在每轮上报的 host 不得被逐掉、丢累计样本与探针状态）。

import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

import src.scheduler as scheduler_module
from src.scheduler import (
    _PROBE_LEASE_SECONDS,
    ConcurrencyScheduler,
    PlatformBreaker,
    ResizableSemaphore,
)


def test_resizable_semaphore_value_is_available_not_capacity() -> None:
    # SEV-01 语义单测：capacity = 并发上限、value = 剩余可用许可，二者在有持有者时必然分离。
    # 原实现只有一个字段，release() 递增它 → 「可用数」被当作「容量」，调容逻辑因此失去约束。
    sem = ResizableSemaphore(2)
    assert sem.capacity == 2
    assert sem.value == 2
    assert sem.acquire(blocking=False) is True
    assert sem.capacity == 2  # 上限不因占用而变
    assert sem.value == 1  # 只剩一个空闲槽
    sem.release()
    assert (sem.capacity, sem.value) == (2, 2)


def test_resizable_semaphore_unbalanced_release_cannot_create_permits() -> None:
    # 多余/不配对的 release 不得凭空造出许可：这是 SEV-01 「每轮补满」的同类放大机制。
    sem = ResizableSemaphore(1)
    assert sem.acquire(blocking=False) is True
    sem.release()
    sem.release()  # 无配对的释放
    assert sem.capacity == 1
    assert sem.value == 1  # 仍为 1，未涨到 2


def test_resizable_semaphore_set_value_notifies_waiters_while_holders_exist() -> None:
    # 有持有者时扩容仍须唤醒等待者：唤醒数量按「新容量 - 已持有」计，而不是「新容量」本身。
    sem = ResizableSemaphore(1)
    assert sem.acquire(blocking=False) is True  # 占满，value=0
    acquired: list[bool] = []

    def worker() -> None:
        acquired.append(sem.acquire(timeout=2.0))

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)
    assert acquired == []  # 容量已被持有者占满，应阻塞
    sem.set_value(2)  # 扩到 2，空闲 = 2 - 1 = 1 → 唤醒一个
    t.join(timeout=2)
    # 与本文件 test_scheduler_real_concurrency_bounded_while_recompute_runs 收尾的 alive 判据同口径：
    # join 超时是静默返回的，等待者仍挂在 sem.acquire() 里时 acquired 是空列表、下一条断言只是
    # 「没唤醒」的间接信号；显式判线程退出才能区分「唤醒链坏了」与「唤醒后线程自己没跑完」。
    assert not t.is_alive(), "等待者线程未在 2s 内退出：扩容后唤醒链或 acquire 收尾挂死，不得判绿"
    assert acquired == [True]
    assert sem.capacity == 2
    assert sem.value == 0  # 两个持有者、零空闲


def test_resizable_semaphore_shrink_keeps_held_slots() -> None:
    # 缩容/置 0（暂停态）只降低上限，绝不回收已持有槽位；归还后不得再放行。
    sem = ResizableSemaphore(3)
    for _ in range(3):
        assert sem.acquire(blocking=False) is True
    sem.set_value(0)
    assert sem.capacity == 0
    assert sem.value == 0
    assert sem.acquire(blocking=False) is False  # 暂停态：无人可进
    sem.release()  # 已持有者正常归还
    assert sem.value == 0
    assert sem.acquire(blocking=False) is False


def test_resizable_semaphore_set_zero_blocks_and_resume_wakes() -> None:
    # 容量 0 是合法「暂停态」（AGENTS 明示 __init__/set_value 允许 0）：置 0 后新请求阻塞，
    # 恢复容量时等待者必须被唤醒。
    sem = ResizableSemaphore(0)
    assert sem.acquire(blocking=False) is False
    assert sem.value == 0
    acquired: list[bool] = []

    def worker() -> None:
        acquired.append(sem.acquire(timeout=2.0))

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)
    assert acquired == []
    sem.set_value(1)
    t.join(timeout=2)
    # 同上一条口径：暂停态恢复容量这条链一旦失去唤醒，等待者线程永不退出；join 超时静默返回时
    # acquired 为空、失败原因会被读成「没唤醒」而不是「线程挂死」，线程挂死与非守护线程残留本身就是要防的形态。
    assert not t.is_alive(), "等待者线程未在 2s 内退出：恢复容量后唤醒链挂死，不得判绿"
    assert acquired == [True]
    assert sem.value == 0


def test_resizable_semaphore_context_and_value() -> None:
    sem = ResizableSemaphore(1)
    assert sem.value == 1
    with sem:
        assert sem.value == 0
    assert sem.value == 1


def test_resizable_semaphore_set_value_wakes_waiters() -> None:
    sem = ResizableSemaphore(0)
    acquired: list[bool] = []

    def worker() -> None:
        sem.acquire()
        acquired.append(True)

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.05)
    assert acquired == []  # 容量为 0，应阻塞
    sem.set_value(1)
    t.join(timeout=1)
    # 同上一条口径：本用例的 worker 走的是**无超时** acquire()，唤醒失败时线程会永久阻塞；不判
    # is_alive 就只能靠 acquired==[True] 间接反映，而线程残留（非守护）会拖住解释器退出，表现为整轮 pytest 挂死而非本条判红。
    assert not t.is_alive(), "等待者线程未在 1s 内退出：acquire() 没被唤醒，不得判绿"
    assert acquired == [True]
    assert sem.value == 0


def test_platform_breaker_closed_by_default() -> None:
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    assert b.state == "closed"
    assert b.allow() is True


def test_platform_breaker_opens_on_failure_rate() -> None:
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    for _ in range(4):
        b.record(False)
    assert b.state == "open"
    assert b.allow() is False
    assert b.backoff_seconds() > 0


def test_platform_breaker_half_open_then_close() -> None:
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    for _ in range(4):
        b.record(False)
    assert b.state == "open"
    time.sleep(0.1)  # 冷却结束
    assert b.allow() is True  # 放行唯一探针
    assert b.allow() is False  # 探针在飞，拒绝第二个
    b.record(True)  # 探针成功
    assert b.state == "closed"
    assert b.allow() is True


def test_platform_breaker_reopen_on_probe_failure() -> None:
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    for _ in range(4):
        b.record(False)
    assert b.state == "open"
    time.sleep(0.1)
    assert b.allow() is True  # 探针
    b.record(False)  # 探针失败，重新熔断
    assert b.state == "open"
    assert b.allow() is False


def test_platform_breaker_probe_lease_regrants_after_timeout() -> None:
    # 探针租约自愈：探针轮可能以 continue 结束且不触发 record（主播未开播等待轮、
    # 禁录、房间线程退出等路径），_probing 若无租约兜底将永不复位 → 该 key 永久熔断
    # 直到进程重启。租约超时后 allow() 应重新授予探针，实现自愈。
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    for _ in range(4):
        b.record(False)
    assert b.state == "open"
    time.sleep(0.1)  # 冷却结束
    assert b.allow() is True  # 授予唯一探针
    assert b.allow() is False  # 探针在飞（租约内），拒绝
    b._probe_granted_at -= _PROBE_LEASE_SECONDS + 1.0  # 模拟租约超时（探针未回报样本）
    assert b.allow() is True  # 租约到期 → 重新授予探针（自愈）
    b.record(True)  # 新探针成功上报
    assert b.state == "closed"
    assert b.allow() is True


def test_scheduler_capacity_floor_and_scaling() -> None:
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_active_count(0)
    assert s.network_semaphore.value >= 3  # 动态下限=1 收敛至配置值 3（不再被旧下限 8 抬升）
    s.set_active_count(8)
    assert s.network_semaphore.value == 3  # ceil(8/4)=2 < 配置3 -> 配置值兜底
    s.set_active_count(80)
    assert s.network_semaphore.value >= 20  # ceil(80/4)=20，解除排队


def test_scheduler_configured_limit_respected_as_floor() -> None:
    s = ConcurrencyScheduler(configured_limit=50, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_active_count(8)
    assert s.network_semaphore.value == 50  # 高配置值作为下限生效


def test_scheduler_keyed_breaker_isolation() -> None:
    s = ConcurrencyScheduler()
    key = "live.douyin.com"
    for _ in range(10):
        s.record_failure(key)
    assert s.allow(key) is False  # 该平台熔断
    assert s.allow("other.example.com") is True  # 其他平台不受影响


def test_scheduler_recording_limit() -> None:
    s = ConcurrencyScheduler()
    s.set_recording_limit(5)
    assert s.recording_semaphore.value == 5
    s.set_recording_limit(0)
    assert s.recording_semaphore.value >= 4096  # 不限制时高容量


def test_scheduler_recompute_idempotent() -> None:
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, scale_divisor=4)
    s.set_active_count(40)
    cap = s.network_semaphore.value
    s.recompute()
    assert s.network_semaphore.value == cap


def test_scheduler_fixed_mode_pins_capacity_to_configured_limit() -> None:
    # 固定模式（「最大同时录制数(0为不限制)」非 0）：忽略动态调速器，容量恒为
    # 「同一时间访问网络的线程数」，不随活跃任务数变化，且允许低于动态模式的安全下限
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, max_capacity=128, scale_divisor=4)
    assert s.dynamic_mode is True  # 默认动态调速
    s.set_dynamic_mode(False)
    assert s.dynamic_mode is False
    assert s.network_semaphore.value == 3
    s.set_active_count(200)
    assert s.network_semaphore.value == 3  # 任务数暴涨也不调整
    s.set_dynamic_mode(False)  # 幂等：重复设置不改变容量
    assert s.network_semaphore.value == 3
    s.set_dynamic_mode(True)  # 切回动态：恢复自适应（含安全下限）
    assert s.network_semaphore.value >= 1


def test_scheduler_fixed_mode_ignores_error_backpressure() -> None:
    # 固定模式忽略动态调速器：全局错误背压不压缩固定容量（动态模式下错误率过高会温和降容）
    s = ConcurrencyScheduler(configured_limit=4, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    for _ in range(20):
        s.record_failure()
    s.recompute()
    assert s.network_semaphore.value == 4


def test_scheduler_fixed_mode_guarantees_min_one_slot() -> None:
    # 固定模式下「同一时间访问网络的线程数」热更新即时生效；配置非法（0/负值）时兜底为最小 1 个槽位
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, scale_divisor=4)
    s.set_dynamic_mode(False)
    assert s.network_semaphore.value == 3
    s.set_configured_limit(5)
    assert s.network_semaphore.value == 5
    s.set_configured_limit(0)
    assert s.network_semaphore.value == 1


def test_scheduler_record_success_resets_breaker() -> None:
    # 验证：熔断（open）后，经冷却并成功完成一次探针，熔断解除、恢复放行。
    s = ConcurrencyScheduler()
    key = "huya.com"
    for _ in range(10):
        s.record_failure(key)
    assert s.allow(key) is False  # open（冷却中）

    # 模拟冷却结束：将 breaker 的开放截止时间置 0，使其进入可探测状态
    b = s._breaker(key)
    b._open_until = 0.0
    assert s.allow(key) is True  # 放行唯一探针（half-open）
    s.record_success(key)  # 探针成功 → closed
    assert s.allow(key) is True  # 已恢复放行


# —— SEV-01 回归锁：有持有者时容量重算不得放大可用许可 ——


def test_scheduler_dynamic_recompute_does_not_inflate_with_holders() -> None:
    # 动态调速模式：主循环每轮 set_active_count()（内部 recompute）+ adjust_loop 每 5s 一次
    # recompute。原实现把「剩余许可」当「容量」比较后无条件 set_value → 每轮把可用数补满到
    # 目标值，旧持有者仍在持有，实际并发每轮净增。
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_active_count(80)  # ceil(80/4)=20 → 目标容量 20
    cap = s.network_semaphore.capacity
    assert cap >= 20
    for _ in range(cap):
        assert s.network_semaphore.acquire(blocking=False) is True
    assert s.network_semaphore.value == 0  # 全部槽位被持有
    for _ in range(5):
        s.set_active_count(80)  # 触发 recompute（模拟主循环每轮）
        s.recompute()  # 触发 recompute（模拟 adjust_loop）
    assert s.network_semaphore.capacity == cap  # 上限恒定
    assert s.network_semaphore.value == 0  # 关键：可用数不得被补满
    assert s.network_semaphore.acquire(blocking=False) is False  # 实际并发仍 <= cap
    s.network_semaphore.release()
    assert s.network_semaphore.value == 1
    assert s.network_semaphore.acquire(blocking=False) is True


def test_scheduler_fixed_mode_concurrency_stays_bounded_with_holders() -> None:
    # 固定并发模式（「最大同时录制数(0为不限制)」非 0）：容量恒为「同一时间访问网络的线程数」。
    # 原实现下只要有人持槽，每轮重算都会把可用数抬回 3 → 「同一时间访问网络的线程数」形同不存在。
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    assert s.network_semaphore.capacity == 3
    for _ in range(3):
        assert s.network_semaphore.acquire(blocking=False) is True
    assert s.network_semaphore.value == 0
    for _ in range(5):
        s.set_active_count(200)  # 活跃任务暴涨也不得放大并发
        s.recompute()
    assert s.network_semaphore.capacity == 3
    assert s.network_semaphore.value == 0
    assert s.network_semaphore.acquire(blocking=False) is False
    # 热更新（配置改小）后：新上限立即生效，已持有者不受影响
    s.set_configured_limit(1)
    assert s.network_semaphore.capacity == 1
    assert s.network_semaphore.value == 0
    for _ in range(3):
        s.network_semaphore.release()
    assert s.network_semaphore.value == 1  # 只留 1 个空闲槽，不是 3


def test_scheduler_recompute_skips_set_value_when_capacity_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # recompute 必须与 capacity 比较：与 value（剩余许可）比较时，只要有持有者就永远「看起来变了」，
    # 于是每 5s 一次无条件 set_value —— 除无谓唤醒等待者外，还会反复播报「网络容量调整为 X」的
    # 误导性调试日志（容量其实一点没变）。
    s = ConcurrencyScheduler(configured_limit=2, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    sem = s.network_semaphore
    assert sem.acquire(blocking=False) is True
    assert sem.acquire(blocking=False) is True
    assert (sem.capacity, sem.value) == (2, 0)

    calls: list[int] = []
    real_set_value = sem.set_value

    def spy(new_value: int) -> None:
        calls.append(new_value)
        real_set_value(new_value)

    monkeypatch.setattr(sem, "set_value", spy)
    for _ in range(3):
        s.recompute()
    assert calls == []  # 容量未变 → 完全不调容
    s.set_configured_limit(5)  # 热更新才调一次
    assert calls == [5]
    assert (sem.capacity, sem.value) == (5, 3)


def test_scheduler_real_concurrency_bounded_while_recompute_runs() -> None:
    # 端到端不变量：8 个房间线程争抢容量 2 的槽位，主线程按 adjust_loop 节奏持续 recompute，
    # 实测峰值并发必须 <= 2。本断言与调度时序无关（峰值只在真正持槽期间采样），修复后恒成立；
    # 原实现在此场景下每轮补满许可 → 峰值一路涨到房间数。
    limit = 2
    rooms = 8
    s = ConcurrencyScheduler(configured_limit=limit, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    lock = threading.Lock()
    stop = threading.Event()
    state = {"active": 0, "peak": 0}

    def room() -> None:
        while not stop.is_set():
            # 带超时获取：避免收尾时等待者拿不到 notify 而永久阻塞（与断言无关，纯测试卫生）
            if not s.network_semaphore.acquire(timeout=0.05):
                continue
            try:
                with lock:
                    state["active"] += 1
                    state["peak"] = max(state["peak"], state["active"])
                time.sleep(0.01)  # 持槽期：模拟一次网络请求
                with lock:
                    state["active"] -= 1
            finally:
                s.network_semaphore.release()

    threads = [threading.Thread(target=room) for _ in range(rooms)]
    for t in threads:
        t.start()
    try:
        deadline = time.monotonic() + 0.6
        while time.monotonic() < deadline:
            s.set_active_count(rooms)
            s.recompute()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=5)
    assert not any(t.is_alive() for t in threads)
    assert s.network_semaphore.capacity == limit
    assert state["peak"] <= limit


def test_recording_semaphore_limit_respects_holders() -> None:
    # 录制并发软上限同样按「上限/已持有」两态计：已持有的 ffmpeg 数不得被 set_recording_limit
    # 的热更新放大或凭空回收（main.py::check_subprocess 在 Popen 之前 acquire）。
    s = ConcurrencyScheduler()
    s.set_recording_limit(2)
    sem = s.recording_semaphore
    assert sem.capacity == 2
    for _ in range(2):
        assert sem.acquire(blocking=False) is True
    s.set_recording_limit(2)  # 幂等重设（主循环每轮都会调用）
    assert sem.capacity == 2
    assert sem.value == 0
    assert sem.acquire(blocking=False) is False
    s.set_recording_limit(0)  # 不限制 → 恢复高容量，等待者立即可进
    assert sem.capacity == 4096
    assert sem.acquire(blocking=False) is True


# —— MIN-22 回归锁：探针代数标记 ——


def _run_in_thread(fn: Callable[[], Any]) -> None:
    # 在独立线程里执行一次（熔断器的探针归属按线程身份判定，需要真实的第二线程）。
    done: list[bool] = []

    def target() -> None:
        fn()
        done.append(True)

    t = threading.Thread(target=target)
    t.start()
    t.join(timeout=5)
    # 同本文件三条 ResizableSemaphore 用例的口径：helper 被多条熔断器归属用例复用，join 超时返回时
    # done 可能已写入而线程仍卡在锁里，调用方拿到的「第二线程已回报」其实是半截状态；helper 里收口一次，所有调用点同时受益。
    assert not t.is_alive(), "第二线程未在 5s 内退出：被测的 allow()/record() 挂死，不得判绿"
    assert done == [True]


def _open_breaker() -> PlatformBreaker:
    b = PlatformBreaker("t", window=10, fail_rate=0.5, cooldown=0.05, min_samples=4)
    for _ in range(4):
        b.record(False)
    assert b.state == "open"
    return b


def test_platform_breaker_stale_probe_report_does_not_reset_state() -> None:
    # 交错：线程 A 取得探针#1（解析慢，70s 后才回报）；租约 60s 到期后主线程取得探针#2；
    # 此时 A 的回报不得替探针#2 复位状态机（关熔断 + 清窗口）。
    b = _open_breaker()
    b._open_until = 0.0  # 冷却结束
    _run_in_thread(lambda: b.allow() is True)  # 探针#1 授予线程 A
    seq_after_first = b._probe_seq
    assert b.allow() is False  # A 的探针在飞（租约内）→ 拒绝主线程
    b._probe_granted_at -= _PROBE_LEASE_SECONDS + 1.0  # 租约超时
    assert b.allow() is True  # 重授予主线程（探针#2）
    assert b._probe_seq == seq_after_first + 1  # 代数递增
    assert b.state == "half-open"
    _run_in_thread(lambda: b.record(True))  # A 的陈旧探针回报「成功」
    assert b.state == "half-open"  # 关键：不得被陈旧回报关闭
    assert b._probing is True
    assert b.error_rate == 0.8  # 4 失败 + 1 成功 → 样本仍入窗口，只是不改状态
    b.record(True)  # 当前探针（主线程）回报
    assert b.state == "closed"
    assert b.error_rate == 0.0  # 由当前探针负责清窗口


def test_platform_breaker_non_probe_sample_does_not_change_state() -> None:
    # 转态前已放行、此刻仍在途的普通轮次（从未被授予探针）回报时：样本入窗口、不改状态，
    # 否则「一个在途成功轮即可清窗口 + 关闭熔断」，冷却语义失效。
    b = _open_breaker()
    b._open_until = 0.0
    assert b.allow() is True  # 探针授予主线程
    _run_in_thread(lambda: b.record(True))  # 其它线程的在途普通轮次
    assert b.state == "half-open"
    _run_in_thread(lambda: b.record(False))  # 同理，失败回报也不得重新 open
    assert b.state == "half-open"
    assert b.error_rate > 0.0  # 两条样本都计入了窗口
    b.record(False)  # 当前探针失败 → 重新熔断
    assert b.state == "open"


def test_platform_breaker_same_thread_regrant_still_closes() -> None:
    # 同一房间线程在租约到期后自己重新取探针（下一轮轮询的正常形态）：线程对象不变，
    # 重授予后它的回报仍须能正常闭环，否则退化为永久熔断（租约回归锁承诺的语义）。
    b = _open_breaker()
    b._open_until = 0.0
    assert b.allow() is True  # 探针#1（主线程）
    b._probe_granted_at -= _PROBE_LEASE_SECONDS + 1.0
    assert b.allow() is True  # 同线程重授予探针#2
    assert b._probe_seq == 2
    b.record(True)
    assert b.state == "closed"
    assert b.allow() is True


# —— M-35 回归锁：动态模式的目标容量必须先取大再封顶 ——


def test_scheduler_dynamic_capacity_clamps_configured_to_max_capacity() -> None:
    # configured_limit 被填成大于 max_capacity 的值（错配 / 抄来的大数）时，旧写法
    # max(configured, min(上限, scaled)) 整体取 configured —— 声明的安全上限被一个配置值绕过，
    # 80 房间瞬间放开数百并发请求，正是这套调度器要防的形态。
    s = ConcurrencyScheduler(configured_limit=500, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_active_count(8)
    assert s.network_semaphore.capacity == 128
    # 活跃数继续涨也不得越过上限（降容路径同样不得被 configured 顶回去）
    s.set_active_count(2000)
    assert s.network_semaphore.capacity == 128


def test_scheduler_dynamic_capacity_keeps_configured_below_max() -> None:
    # 反向保证：封顶改动**不得**把正常的「配置值作下限」压掉（configured < max 时取两者较大）。
    s = ConcurrencyScheduler(configured_limit=50, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_active_count(8)
    assert s.network_semaphore.capacity == 50


def test_scheduler_fixed_mode_is_deliberately_not_clamped() -> None:
    # 不对称本身也是契约：固定并发模式下容量恒为用户填写的「同一时间访问网络的线程数」，
    # 不受 max_capacity 约束（AGENTS 钉死的语义）。顺手把这一支也夹取 = 用户填 200 只拿到 128
    # 且零提示，属新的静默失准，故这里明确断言它**不被**封顶。
    s = ConcurrencyScheduler(configured_limit=500, min_capacity=1, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    assert s.network_semaphore.capacity == 500


# —— M-42 回归锁：min_samples 钳到窗口内 + open 必须真的失败过 ——


def test_platform_breaker_min_samples_clamped_to_window() -> None:
    # min_samples(8) > window(3) 时旧写法让 len(_samples) 永远达不到阈值 → 熔断器整生不开，
    # 坏 host 拿满全部房间流量且永不自愈。
    b = PlatformBreaker("t", window=3, fail_rate=0.5, cooldown=60.0, min_samples=8)
    assert b._min_samples == 3
    for _ in range(3):
        b.record(False)
    assert b.state == "open", b.state
    assert b.allow() is False  # 冷却未结束，拒绝探测（旧写法下这里永远是 True：熔断从未打开）


def test_platform_breaker_zero_fail_rate_does_not_open_on_all_success() -> None:
    # fail_rate=0 时旧判据 0 >= 0 恒真：一个**全成功**的窗口也会被判熔断，健康 host 白白退避。
    b = PlatformBreaker("t", window=10, fail_rate=0.0, cooldown=0.0, min_samples=4)
    for _ in range(10):
        b.record(True)
    assert b.state == "closed", b.state
    assert b.allow() is True
    # fail_rate=0 的合法语义是「有任何失败即熔断」：一次真失败就该开
    b.record(False)
    assert b.state == "open", b.state


def test_platform_breaker_fail_count_stays_incremental() -> None:
    # _fail_count 必须与窗口严格同步（增量维护）：deque 满员挤出最旧样本时要扣掉它的贡献。
    # 本用例同时是「不得改回 sum(self._samples)」的行为见证——计数与窗口一旦脱钩这里就红。
    b = PlatformBreaker("t", window=4, fail_rate=1.0, cooldown=0.0, min_samples=4)
    b.record(False)
    b.record(False)
    assert b._fail_count == 2
    assert b.error_rate == 1.0  # 窗口此刻只有这两条样本
    b.record(True)
    b.record(True)
    assert b._fail_count == 2  # 满窗前只入样，不挤出
    b.record(True)
    b.record(True)  # 这两条把两条失败样本挤出 deque(maxlen=4)
    assert b._fail_count == 0, b._fail_count
    assert b.state == "closed"


# —— M-36a 回归锁：熔断表有上限、逐出只碰 closed、命中即 touch ——


def test_scheduler_breaker_table_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(scheduler_module, "_MAX_BREAKERS", 4)
    s = ConcurrencyScheduler()
    for i in range(30):
        s.record_failure(f"host{i}.example")  # 每个 key 一条失败样本：仍处 closed，可被逐出
    assert len(s._breakers) == 4, len(s._breakers)
    # 保留的必须是最近使用的四个键（而不是最早创建的四个）
    assert list(s._breakers) == [f"host{i}.example" for i in range(26, 30)], list(s._breakers)


def test_scheduler_breaker_eviction_keeps_non_closed_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # 「仍在使用」= open / half-open（冷却未结束、探针在飞）。摘掉它等于把一次进行中的熔断重置成
    # 放行 —— 坏 CDN 会立刻回到全部房间流量，比多留一支对象严重得多。
    monkeypatch.setattr(scheduler_module, "_MAX_BREAKERS", 2)
    s = ConcurrencyScheduler()
    for _ in range(10):
        s.record_failure("bad.example")  # 连打失败样本 → 该键进入 open
    assert s._breaker("bad.example").state == "open"
    s.record_failure("a.example")
    s.record_failure("b.example")
    s.record_failure("c.example")
    assert "bad.example" in s._breakers, "熔断中的键被逐出：探针/冷却状态被重置"
    # 表内其余 closed 键照常被逐出，总量仍在量级内（open 键 + 至多 cap 个 closed 键）
    assert len([k for k in s._breakers if k != "bad.example"]) <= 2


def test_scheduler_breaker_touch_protects_active_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # 命中即 touch：最早创建但仍在每轮上报的 host 不得因为「创建得早」被逐掉。
    monkeypatch.setattr(scheduler_module, "_MAX_BREAKERS", 2)
    s = ConcurrencyScheduler()
    s.record_success("busy.example")  # 先创建，处于表首
    s.record_success("x.example")
    s.record_success("busy.example")  # touch → busy 移到表尾
    s.record_success("y.example")  # 触发逐出，被逐的应是 x（最久未使用）
    assert "busy.example" in s._breakers, list(s._breakers)
    assert "x.example" not in s._breakers, list(s._breakers)
