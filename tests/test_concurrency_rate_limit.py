# -*- encoding: utf-8 -*-
# 并发模式验证测试：threading.Lock 线程安全 + 速率限制。
#
# 验证 concurrency-rate-limit Skill 中描述的两种核心模式：
# 1. 统一凭证管理（threading.Lock 保护共享缓存，仅获取一次）
# 2. 全局速率限制（最小请求间隔控制）
#
import threading
import time

# ---------------------------------------------------------------------------
# 1. threading.Lock 线程安全：模拟统一凭证管理
# ---------------------------------------------------------------------------


class TestThreadSafeCredentialCache:
    # 验证 threading.Lock 保护共享缓存的线程安全性。

    def test_concurrent_access_only_fetches_once(self):
        # 多线程并发访问时，底层 fetch 只被调用一次。
        lock = threading.Lock()
        cached_value: str = ""
        fetch_count = 0

        def fake_fetch() -> str:
            nonlocal fetch_count
            fetch_count += 1
            time.sleep(0.05)  # 模拟网络延迟
            return "credential_value"

        def get_credential() -> str:
            nonlocal cached_value
            if cached_value:
                return cached_value
            with lock:
                # 双重检查：拿到锁后再看一次
                if not cached_value:
                    cached_value = fake_fetch()
                return cached_value

        results: list[str] = []
        threads: list[threading.Thread] = []
        for _ in range(10):
            t = threading.Thread(target=lambda: results.append(get_credential()))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 10
        assert all(r == "credential_value" for r in results)
        assert fetch_count == 1, f"期望 fetch 仅调用 1 次，实际调用 {fetch_count} 次"

    def test_lock_prevents_race_condition(self):
        # 无锁计数器会出现竞态，有锁计数器结果正确。
        counter_no_lock = 0
        counter_with_lock = 0
        lock = threading.Lock()
        iterations = 1000

        def increment_no_lock():
            nonlocal counter_no_lock
            for _ in range(iterations):
                counter_no_lock += 1

        def increment_with_lock():
            nonlocal counter_with_lock
            for _ in range(iterations):
                with lock:
                    counter_with_lock += 1

        threads: list[threading.Thread] = []
        for _ in range(10):
            threads.append(threading.Thread(target=increment_no_lock))
            threads.append(threading.Thread(target=increment_with_lock))

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert counter_with_lock == 10 * iterations
        # 无锁计数器在高竞争下 *通常* 会小于期望值，但不保证一定不等，故仅断言有锁正确

    def test_lock_acquire_nonblocking(self):
        # 非阻塞 acquire：未抢到锁的线程应等待而非重复获取。
        lock = threading.Lock()
        acquired_order: list[int] = []

        def worker(worker_id: int) -> None:
            if lock.acquire(blocking=False):
                acquired_order.append(worker_id)
                time.sleep(0.1)
                lock.release()
            else:
                # 等待 owner 完成
                with lock:
                    pass

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 只有一个线程成功非阻塞获取
        assert len(acquired_order) == 1


# ---------------------------------------------------------------------------
# 2. 速率限制：全局锁 + 最小请求间隔
# ---------------------------------------------------------------------------


class TestRateLimiter:
    # 验证速率限制器的最小间隔控制。

    def _make_rate_limiter(self, min_interval: float):
        # 创建一个速率限制器闭包。
        rate_lock = threading.Lock()
        last_request_time: float = 0.0

        def rate_limit() -> float:
            # 执行速率限制，返回实际等待秒数。
            nonlocal last_request_time
            start = time.monotonic()
            with rate_lock:
                now = time.monotonic()
                wait = min_interval - (now - last_request_time)
                if wait > 0:
                    time.sleep(wait)
                last_request_time = time.monotonic()
            return time.monotonic() - start

        return rate_limit

    def test_rate_limit_enforces_minimum_interval(self):
        # 连续调用间隔不小于 min_interval。
        min_interval = 0.1
        rate_limit = self._make_rate_limiter(min_interval)

        timestamps: list[float] = []
        for _ in range(5):
            rate_limit()
            timestamps.append(time.monotonic())

        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            assert gap >= min_interval * 0.9, f"第 {i} 次间隔 {gap:.4f}s < 期望 {min_interval}s"

    def test_rate_limit_thread_safety(self):
        # 多线程并发调用速率限制器，所有调用均被串行化。
        min_interval = 0.05
        rate_limit = self._make_rate_limiter(min_interval)

        timestamps: list[float] = []
        ts_lock = threading.Lock()

        def worker():
            rate_limit()
            with ts_lock:
                timestamps.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(timestamps) == 6
        timestamps.sort()
        # 检查排序后的相邻时间戳间隔
        for i in range(1, len(timestamps)):
            gap = timestamps[i] - timestamps[i - 1]
            assert gap >= min_interval * 0.8, f"并发场景第 {i} 次间隔 {gap:.4f}s < 期望 {min_interval}s"

    def test_rate_limit_no_wait_when_enough_time_passed(self):
        # 间隔足够长时不应额外等待。
        min_interval = 0.05
        rate_limit = self._make_rate_limiter(min_interval)

        rate_limit()
        time.sleep(0.2)  # 等待远超 min_interval
        wait_time = rate_limit()

        assert wait_time < min_interval, f"间隔足够长时不应等待，实际等待 {wait_time:.4f}s"
