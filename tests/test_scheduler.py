# -*- coding: utf-8 -*-
# src.scheduler 单元测试：覆盖 ResizableSemaphore / PlatformBreaker / ConcurrencyScheduler。
# 聚焦高并发录制调度的关键不变量：信号量可安全调容、熔断器状态机正确、
# 全局并发容量随活跃任务数自适应缩放且带安全下限、按 key 错误预算隔离、录制并发软上限。

import threading
import time

from src.scheduler import ConcurrencyScheduler, PlatformBreaker, ResizableSemaphore


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


def test_scheduler_capacity_floor_and_scaling() -> None:
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=8, max_capacity=128, scale_divisor=4)
    s.set_active_count(0)
    assert s.network_semaphore.value >= 8  # 安全下限
    s.set_active_count(8)
    assert s.network_semaphore.value == 8  # ceil(8/4)=2 < 配置3 < 下限8 -> 下限
    s.set_active_count(80)
    assert s.network_semaphore.value >= 20  # ceil(80/4)=20，解除排队


def test_scheduler_configured_limit_respected_as_floor() -> None:
    s = ConcurrencyScheduler(configured_limit=50, min_capacity=8, max_capacity=128, scale_divisor=4)
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
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=8, scale_divisor=4)
    s.set_active_count(40)
    cap = s.network_semaphore.value
    s.recompute()
    assert s.network_semaphore.value == cap


def test_scheduler_fixed_mode_pins_capacity_to_configured_limit() -> None:
    # 固定模式（「最大同时录制数(0为不限制)」非 0）：忽略动态调速器，容量恒为
    # 「同一时间访问网络的线程数」，不随活跃任务数变化，且允许低于动态模式的安全下限
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=8, max_capacity=128, scale_divisor=4)
    assert s.dynamic_mode is True  # 默认动态调速
    s.set_dynamic_mode(False)
    assert s.dynamic_mode is False
    assert s.network_semaphore.value == 3
    s.set_active_count(200)
    assert s.network_semaphore.value == 3  # 任务数暴涨也不调整
    s.set_dynamic_mode(False)  # 幂等：重复设置不改变容量
    assert s.network_semaphore.value == 3
    s.set_dynamic_mode(True)  # 切回动态：恢复自适应（含安全下限）
    assert s.network_semaphore.value >= 8


def test_scheduler_fixed_mode_ignores_error_backpressure() -> None:
    # 固定模式忽略动态调速器：全局错误背压不压缩固定容量（动态模式下错误率过高会温和降容）
    s = ConcurrencyScheduler(configured_limit=4, min_capacity=8, max_capacity=128, scale_divisor=4)
    s.set_dynamic_mode(False)
    for _ in range(20):
        s.record_failure()
    s.recompute()
    assert s.network_semaphore.value == 4


def test_scheduler_fixed_mode_guarantees_min_one_slot() -> None:
    # 固定模式下「同一时间访问网络的线程数」热更新即时生效；配置非法（0/负值）时兜底为最小 1 个槽位
    s = ConcurrencyScheduler(configured_limit=3, min_capacity=8, scale_divisor=4)
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
