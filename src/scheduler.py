# -*- coding: utf-8 -*-
# 高并发录制调度与资源管理
#
# 取代原先「单全局信号量 + 错误率单向压制」的模型，提供：
#   - ResizableSemaphore：支持运行时调容的上下文信号量（消除重建竞态）
#   - PlatformBreaker：按 key（直播间 host）的熔断器 closed→open→half-open
#   - ConcurrencyScheduler：自适应全局并发容量（随活跃任务数缩放、带安全下限；
#     亦支持固定并发模式——容量恒为配置的「同一时间访问网络的线程数」），
#     按 key 聚合错误预算驱动熔断，提供可选的录制并发软上限（资源治理），
#     并以 adjust_loop 守护循环取代旧 adjust_max_request。
#
# 设计目标：80+ 任务跨多平台时不因固定 3 槽而排队；单平台抖动被隔离降级，
# 不拖垮全局；单任务异常被捕获，避免连锁报错导致系统不可用。

from collections import deque
from threading import Condition, Lock
from typing import Any

from .logger import logger


class ResizableSemaphore:
    # 可运行时调容的信号量，实现上下文管理器协议。
    # capacity 语义与 threading.Semaphore 一致（表示可用许可数）；set_value 可增可减，
    # 减少时仅降低上限（已持锁者不受影响），增加时会唤醒等待者。
    def __init__(self, value: int) -> None:
        # 容量允许为 0（表示暂停/全部阻塞），仅作下限保护避免负值。
        self._cond = Condition()
        self._capacity = max(0, int(value))

    def __enter__(self) -> "ResizableSemaphore":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        # 获取一个许可；blocking=False 时非阻塞；timeout>=0 时带超时（秒）。
        with self._cond:
            if not blocking:
                if self._capacity <= 0:
                    return False
                self._capacity -= 1
                return True
            endtime: float | None = None
            if timeout >= 0:
                endtime = _now() + timeout
            while self._capacity <= 0:
                if endtime is not None:
                    remaining = endtime - _now()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()
            self._capacity -= 1
            return True

    def release(self) -> None:
        # 释放一个许可并唤醒一个等待者。
        with self._cond:
            self._capacity += 1
            self._cond.notify()

    def set_value(self, new_value: int) -> None:
        # 调整容量：增大则唤醒相应数量等待者；减小则仅降低上限，不强行回收已持锁。
        # 容量允许为 0（暂停）。
        new_value = max(0, int(new_value))
        with self._cond:
            delta = new_value - self._capacity
            self._capacity = new_value
            if delta > 0:
                for _ in range(delta):
                    self._cond.notify()

    @property
    def value(self) -> int:
        with self._cond:
            return self._capacity


class PlatformBreaker:
    # 按 key 的熔断器：closed（放行）→ open（熔断，跳过探测并退避）→ half-open（放一个探针）。
    # 连续失败样本比例超阈值即 open；open 经 cooldown 后转 half-open 放行一个探针，
    # 探针成功则 closed、失败则重新 open。用于把单平台抖动隔离，避免连锁拖垮全局。
    def __init__(
        self,
        name: str,
        *,
        window: int = 40,
        fail_rate: float = 0.5,
        cooldown: float = 45.0,
        min_samples: int = 8,
    ) -> None:
        self.name = name
        self._window_size = max(1, int(window))
        self._fail_rate = min(1.0, max(0.0, float(fail_rate)))
        self._cooldown = max(0.0, float(cooldown))
        self._min_samples = max(1, int(min_samples))
        self._lock = Lock()
        self._samples: deque[int] = deque(maxlen=self._window_size)
        self._state = "closed"  # "closed" | "open" | "half-open"
        self._open_until = 0.0
        self._probing = False

    def record(self, success: bool) -> None:
        # 上报一次结果（True=成功 / False=失败），按状态机推进。
        with self._lock:
            self._samples.append(0 if success else 1)
            if self._state == "closed":
                if len(self._samples) >= self._min_samples and (
                    sum(self._samples) / len(self._samples) >= self._fail_rate
                ):
                    self._state = "open"
                    self._open_until = _now() + self._cooldown
                    self._probing = False
            elif self._state == "half-open":
                # 探针结果决定：成功则恢复，失败则重新熔断（延长冷却）
                if success:
                    self._state = "closed"
                    self._samples.clear()
                else:
                    self._state = "open"
                    self._open_until = _now() + self._cooldown
                self._probing = False
            # open 状态：等待 cooldown 结束，由 allow() 转入 half-open

    def allow(self) -> bool:
        # 是否允许本次探测。open 且冷却结束后放行唯一探针；half-open 仅放一个探针；closed 放行。
        with self._lock:
            if self._state == "closed":
                return True
            now = _now()
            if self._state == "open":
                if now >= self._open_until:
                    if not self._probing:
                        self._probing = True
                        self._state = "half-open"
                        return True
                    return False
                return False
            # half-open
            if not self._probing:
                self._probing = True
                return True
            return False

    def backoff_seconds(self) -> float:
        # 熔断态下建议的退避秒数（冷却剩余 + 余量）。
        with self._lock:
            if self._state == "open":
                return max(0.0, self._open_until - _now()) + 5.0
            return 5.0

    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def error_rate(self) -> float:
        with self._lock:
            if not self._samples:
                return 0.0
            return sum(self._samples) / len(self._samples)


class ConcurrencyScheduler:
    # 录制并发与资源调度中枢：
    #   - 并发模式（set_dynamic_mode）：动态调速（默认）/ 固定并发，由「最大同时录制数(0为不限制)」
    #     是否为 0 决定——0=动态（网络容量随活跃任务数自适应缩放，带安全上下限）；
    #     非 0=固定（忽略动态调速器，网络容量恒为「同一时间访问网络的线程数」，最小 1 个槽位）；
    #   - 全局网络并发信号量（network_semaphore）：容量随活跃任务数自适应缩放，带安全下限/上限；
    #   - 按 key 熔断器（breakers）：隔离各平台/站点错误，触发降级退避（与并发模式正交，两种模式下均生效）；
    #   - 可选录制并发软上限（recording_semaphore）：默认不限制，开启后限制同时 ffmpeg 数；
    #   - adjust_loop：守护循环，周期性重算容量（取代旧 adjust_max_request 的单向压制）。
    def __init__(
        self,
        *,
        configured_limit: int = 3,
        min_capacity: int = 8,
        max_capacity: int = 128,
        scale_divisor: int = 4,
        error_rate_floor: float = 0.5,
        error_window: int = 60,
    ) -> None:
        self._configured_limit = max(1, int(configured_limit))
        self._min_capacity = max(1, int(min_capacity))
        self._max_capacity = max(self._min_capacity, int(max_capacity))
        self._scale_divisor = max(1, int(scale_divisor))
        self._error_rate_floor = min(1.0, max(0.0, float(error_rate_floor)))
        self._error_window_size = max(1, int(error_window))

        self._RECORDING_UNLIMITED = 4096  # 录制并发「不限制」时的高容量上限
        self._lock = Lock()
        self._active_count = 0

        # 并发模式：True=动态调速（默认，对应「最大同时录制数(0为不限制)」为 0）；
        # False=固定并发（容量恒为 configured_limit）。
        # 必须在 _compute_capacity() 首次调用（下方创建 network_semaphore 时）之前初始化；
        # _mode_announced 用于幂等播报：启动后至少播报一次当前模式，之后仅在模式变化时播报。
        self._dynamic_mode = True
        self._mode_announced = False

        # 全局错误窗口（仅用于温和的全局背压，带安全下限），与 per-key 熔断互补。
        # 必须在 _compute_capacity() 首次调用（下方创建 network_semaphore 时）之前初始化。
        self._global_errors: deque[int] = deque(maxlen=self._error_window_size)

        self._network_semaphore = ResizableSemaphore(self._compute_capacity())
        # 录制并发信号量：默认高容量（视作不限制）；set_recording_limit(>0) 时下调为实际上限
        self._recording_semaphore = ResizableSemaphore(self._RECORDING_UNLIMITED)
        self._recording_limit = 0  # 0 = 不限制

        self._breakers: dict[str, PlatformBreaker] = {}
        self._breakers_lock = Lock()

    # —— 容量计算 ——
    def _compute_capacity(self) -> int:
        # 固定模式：忽略动态调速器与错误背压，容量恒为 configured_limit
        # （即「同一时间访问网络的线程数」，set_configured_limit 已保证最小 1 个槽位）。
        if not self._dynamic_mode:
            return self._configured_limit
        # 动态模式：目标容量 = max(配置值, min(上限, ceil(活跃数/缩放因子)))；错误率极高时温和降容但永不低于下限。
        with self._lock:
            active = self._active_count
        target = max(
            self._configured_limit,
            min(self._max_capacity, (active + self._scale_divisor - 1) // self._scale_divisor),
        )
        with self._lock:
            if self._global_errors:
                rate = sum(self._global_errors) / len(self._global_errors)
            else:
                rate = 0.0
        if rate >= self._error_rate_floor:
            target = max(self._min_capacity, int(target * 0.6))
        return max(self._min_capacity, target)

    def recompute(self) -> None:
        # 重算全局网络并发容量，变化时才调容（避免每轮无谓唤醒）。
        new_cap = self._compute_capacity()
        if new_cap != self._network_semaphore.value:
            self._network_semaphore.set_value(new_cap)
            if self._dynamic_mode:
                logger.debug(f"并发模式: 动态调速，网络容量调整为 {new_cap}（活跃任务 {self._active_count}）")
            else:
                logger.debug(f"并发模式: 固定，网络容量调整为 {new_cap}（来源: 同一时间访问网络的线程数）")

    # —— 配置入口 ——
    def set_active_count(self, n: int) -> None:
        # 上报当前活跃监控任务数（main 主循环每轮调用）。
        with self._lock:
            self._active_count = max(0, int(n))
        self.recompute()

    def set_configured_limit(self, n: int) -> None:
        # 上报配置中的「同一时间访问网络的线程数」：动态模式下作为容量下限之一；
        # 固定模式下即网络并发容量本身（固定值，非法值兜底为最小 1）。
        self._configured_limit = max(1, int(n))
        self.recompute()

    def set_recording_limit(self, n: int) -> None:
        # 设置同时录制（ffmpeg）上限：>0 生效，0 表示不限制（恢复高容量，acquire 永不阻塞）。
        self._recording_limit = max(0, int(n))
        if self._recording_limit > 0:
            self._recording_semaphore.set_value(self._recording_limit)
        else:
            self._recording_semaphore.set_value(self._RECORDING_UNLIMITED)

    def set_dynamic_mode(self, enabled: bool) -> None:
        # 设置并发模式：True=动态调速（网络容量随活跃任务数自适应缩放，带安全上下限）；
        # False=固定并发（忽略动态调速器，网络容量恒为「同一时间访问网络的线程数」）。
        # 幂等：模式未变且已播报过时直接返回（main 主循环每轮调用，避免重复日志与无谓调容）；
        # 模式变化或首次调用时重算容量，并播报当前模式与有效并发数值。
        enabled = bool(enabled)
        if enabled == self._dynamic_mode and self._mode_announced:
            return
        self._dynamic_mode = enabled
        self._mode_announced = True
        self.recompute()
        if enabled:
            logger.debug(
                f"并发模式: 动态调速（网络容量随活跃任务数自适应，当前 {self._network_semaphore.value}，"
                f"下限 {self._min_capacity}，上限 {self._max_capacity}）"
            )
        else:
            logger.debug(
                f"并发模式: 固定（忽略动态调速器，网络容量固定为 {self._network_semaphore.value}，"
                f"来源: 配置「同一时间访问网络的线程数」）"
            )

    # —— 熔断器 ——
    def _breaker(self, key: str) -> PlatformBreaker:
        with self._breakers_lock:
            b = self._breakers.get(key)
            if b is None:
                b = PlatformBreaker(key)
                self._breakers[key] = b
            return b

    def allow(self, key: str) -> bool:
        # 该 key 是否允许本轮探测（熔断时返回 False）。
        return self._breaker(key).allow()

    def backoff_seconds(self, key: str) -> float:
        return self._breaker(key).backoff_seconds()

    def breaker_state(self, key: str) -> str:
        return self._breaker(key).state

    def breaker_states(self) -> dict[str, dict[str, Any]]:
        # 快照（监控/调试用）：各 key 的熔断状态与错误率。
        with self._breakers_lock:
            keys = list(self._breakers.keys())
        return {k: {"state": self._breaker(k).state, "error_rate": round(self._breaker(k).error_rate, 3)} for k in keys}

    # —— 错误/成功计数（驱动熔断与全局背压）——
    def record_success(self, key: str | None = None) -> None:
        if key:
            self._breaker(key).record(True)
        with self._lock:
            self._global_errors.append(0)

    def record_failure(self, key: str | None = None) -> None:
        if key:
            self._breaker(key).record(False)
        with self._lock:
            self._global_errors.append(1)

    # —— 暴露信号量（供 `with scheduler.network_semaphore:` 直接使用）——
    @property
    def network_semaphore(self) -> ResizableSemaphore:
        return self._network_semaphore

    @property
    def recording_semaphore(self) -> ResizableSemaphore:
        return self._recording_semaphore

    @property
    def recording_limit(self) -> int:
        return self._recording_limit

    @property
    def dynamic_mode(self) -> bool:
        # 当前是否处于动态调速模式（False 表示固定并发模式）。
        return self._dynamic_mode

    # —— 守护循环（取代旧 adjust_max_request）——
    def adjust_loop(self) -> None:
        # 每 5 秒重算一次全局容量；per-key 熔断由 record_* 即时驱动，无需轮询。
        while True:
            _sleep(5)
            try:
                self.recompute()
            except Exception as e:  # 守护循环自身不应因异常退出
                logger.debug(f"并发调度重算异常（已忽略）: {type(e).__name__}: {e}")


def host_of(url: str) -> str:
    # 熔断 key：取 URL 主机名（小写、去端口/路径/查询），自定义 flv/m3u8 直链退回路径本身。
    try:
        tail = url.split("://", 1)[-1]
        host = tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        host = host.lower()
        if not host:
            return "unknown"
        return host
    except Exception:
        return "unknown"


def _now() -> float:
    import time

    return time.monotonic()


def _sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


__all__ = [
    "ResizableSemaphore",
    "PlatformBreaker",
    "ConcurrencyScheduler",
    "host_of",
]
