# -*- coding: utf-8 -*-
import time
from collections import OrderedDict, deque
from threading import Condition, Lock, Thread, current_thread

import i18n

from .logger import logger

# 高并发录制调度与资源管理
#
# 提供三件套：
#   - ResizableSemaphore：支持运行时调容的上下文信号量（消除重建竞态）
#   - PlatformBreaker：按 key（直播间 host）的熔断器 closed→open→half-open
#   - ConcurrencyScheduler：自适应全局并发容量（随活跃任务数缩放、带安全下限；亦支持固定
#     并发模式），按 key 聚合错误预算驱动熔断，提供可选的录制并发软上限，并由 adjust_loop
#     守护循环周期性重算容量。
#
# 设计目标：80+ 任务跨多平台时不因固定 3 槽而排队；单平台抖动被隔离降级、不拖垮全局；
# 单任务异常被捕获，避免连锁报错导致系统不可用。
#
# 同源副本：scripts/douyin_live_recorder_standalone.py 刻意不 import src/（单文件可独立运行），
# 因而自带一份 ResizableSemaphore 与 PlatformBreaker 的独立副本。改动本文件的并发语义
# （容量/已持有分离、调容唤醒规则、熔断阈值与探针租约等）时必须逐方法 diff 后同步副本，
# 不得假定两者已同步：两份 PlatformBreaker 并不等价（副本缺 _grant_probe / _end_probe /
# error_rate / backoff_seconds，样本入队函数名也不同）。副本被 check_annotations.py 排除，
# 但在 mypy 的 [tool.mypy].files 内，改动照样要过类型门禁；细则见 AGENTS.md 的 standalone 条目。


# 探针租约时长：half-open 探针被授予后超过该时长仍未上报样本（未开播等待轮、
# 禁录、房间线程退出等不上报样本的路径）时，allow() 重新授予探针——否则
# _probing 标志永不复位，该 key 将永久熔断直到进程重启。
_PROBE_LEASE_SECONDS = 60.0


# 熔断表容量上限：key 是 host_of(record_url) 的结果，属**外部可控**输入（用户自填的自定义流地址
# 可带任意端口/主机、短链落地页会改写 host），不回收则每个历史 host 都留一支 PlatformBreaker
# （含 40 长度样本窗口），24×7 长跑 + 房间持续增删下内存无界增长。达到上限时从「最久未被任何
# 房间使用」的一端逐出，判据见 _evict_breakers_locked。
_MAX_BREAKERS = 1024


class ResizableSemaphore:
    # 可运行时调容的信号量，实现上下文管理器协议。
    # 内部严格分离两个量：_capacity = 并发上限（只由 set_value 改）、_used = 当前已持有许可数
    # （只由 acquire/release 改）。set_value 增大时唤醒相应数量等待者；减小仅降低上限、
    # 不强行回收已持有槽位；容量允许为 0（暂停态）。
    # 两者必须分离：若用单个字段同时表示「剩余可用许可」，recompute() 拿剩余量与目标容量比较
    # 后赋值，会把可用数每轮补满到目标值，旧持有者仍在持有 → 实际并发净增、网络上限失控
    # （表现为「多房间连击同一 CDN → 偶发 403」，易被误判成平台风控）。
    # 同源副本：scripts/douyin_live_recorder_standalone.py::ResizableSemaphore（改并发语义须同步）。
    def __init__(self, value: int) -> None:
        # 容量允许为 0（表示暂停/全部阻塞），仅作下限保护避免负值。
        self._cond = Condition()
        self._capacity = max(0, int(value))
        self._used = 0

    def __enter__(self) -> "ResizableSemaphore":
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.release()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        # 获取一个许可；blocking=False 时非阻塞；timeout>=0 时带超时（秒）。
        # 判据是「已持有 + 1 是否超过上限」而非「剩余许可是否 > 0」：与 release 对称，
        # 且不受「release 凭空造容量」影响。
        with self._cond:
            if not blocking:
                if self._used + 1 > self._capacity:
                    return False
                self._used += 1
                return True
            endtime: float | None = None
            if timeout >= 0:
                endtime = _now() + timeout
            while self._used + 1 > self._capacity:
                if endtime is not None:
                    remaining = endtime - _now()
                    if remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()
            self._used += 1
            return True

    def release(self) -> None:
        # 归还一个许可（只减 _used，绝不增 _capacity）并唤醒一个等待者。
        # _used 的下界钳制：release 与 acquire 不配对（异常路径重复释放）时不得凭空造出许可。
        with self._cond:
            if self._used > 0:
                self._used -= 1
            self._cond.notify()

    def set_value(self, new_value: int) -> None:
        # 调整容量：只改上限，_used 保持不变（故 decrease 天然不回收已持有槽位）；
        # 唤醒数量取「新可用数 = 新容量 - 已持有」，即 min(可用数, 等待者数)——notify(n)
        # 至多唤醒 n 个等待者，唤醒偏多也无害（acquire 的 while 会重新检查并继续等待）。
        new_value = max(0, int(new_value))
        with self._cond:
            self._capacity = new_value
            free = new_value - self._used
            if free > 0:
                self._cond.notify(free)

    @property
    def value(self) -> int:
        # 剩余可用许可数（= 上限 - 已持有）。判定「还能不能再塞进一个请求」用它；
        # 展示/比较并发上限一律用 capacity，二者在有持有者时必然不同。
        with self._cond:
            return max(0, self._capacity - self._used)

    @property
    def capacity(self) -> int:
        # 并发上限本身（与当前持有数无关）：调度器重算容量时与之比较。
        with self._cond:
            return self._capacity


class PlatformBreaker:
    # 按 key 的熔断器：closed（放行）→ open（熔断，跳过探测并退避）→ half-open（放一个探针）。
    # 连续失败样本比例超阈值即 open；open 经 cooldown 后转 half-open 放行一个探针，探针成功则
    # closed、失败则重新 open。用于把单平台抖动隔离，避免连锁拖垮全局。
    # 同源副本：scripts/douyin_live_recorder_standalone.py::PlatformBreaker 只是部分同步
    # （缺哪些方法见模块头），改本类语义时须逐方法 diff 后决定是否回灌。
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
        # min_samples 必须钳在 1..window：窗口是「能收集多少样本」的硬上界，阈值超过它熔断器永不开。
        # [历史注] 旧实现只有下界，坏 host 会拿满流量且永不自愈。
        self._min_samples = max(1, min(int(min_samples), self._window_size))
        self._lock = Lock()
        self._samples: deque[int] = deque(maxlen=self._window_size)
        # 窗口内失败样本的增量计数（与 _samples 严格同步）：每次 record 对整窗 sum() 是
        # O(window) 且在 _lock 内执行，80+ 任务并发上报会放大锁持有时间；改增量后为 O(1)，
        # 语义完全等价。
        self._fail_count = 0
        self._state = "closed"  # "closed" | "open" | "half-open"
        self._open_until = 0.0
        self._probing = False
        self._probe_granted_at = 0.0
        # 探针代数 + 当前探针持有线程：_probing 只是布尔，租约重授予后旧探针的回报仍会命中
        # half-open 分支、替新探针把状态机复位（closed + 清窗口）。每次授予递增 _probe_seq
        # 并登记持有线程；record() 只接受当前持有线程的回报去驱动 half-open→closed/open，
        # 其余样本照常入窗口但不改状态。用 Thread 对象而非 get_ident()：ident 会被已死线程
        # 复用，对象身份不会。
        self._probe_seq = 0
        self._probe_owner: Thread | None = None

    def _push_sample(self, failed: int) -> None:
        # 入队一个样本并同步维护 _fail_count（调用方须已持锁）。
        # deque 达 maxlen 时 append 会挤出最旧样本，需扣减其贡献以保持计数与窗口一致。
        if len(self._samples) == self._window_size:
            self._fail_count -= self._samples[0]
        self._samples.append(failed)
        self._fail_count += failed

    def _grant_probe(self, now: float) -> None:
        # 授予（或按租约重授予）探针：递增代数、登记持有线程与授予时刻（调用方须已持锁）。
        # 房间线程内 allow() 与随后的 record() 在同一线程执行（main.py 的熔断预检与结果上报
        # 都在房间线程的 while True 体内），故线程身份足以判定回报属于哪一代探针。
        self._probing = True
        self._probe_seq += 1
        self._probe_owner = current_thread()
        self._probe_granted_at = now

    def _end_probe(self) -> None:
        # 探针闭环：清除持有线程（_probe_seq 保留，代数只增不减、供后续比对）。
        self._probing = False
        self._probe_owner = None

    def record(self, success: bool) -> None:
        # 上报一次结果（True=成功 / False=失败），按状态机推进。
        with self._lock:
            self._push_sample(0 if success else 1)
            if self._state == "closed":
                # _fail_count > 0 是必要条件：fail_rate=0 时 0 >= 0 恒真，全成功窗口也会被判熔断、
                # 让健康 host 白白退避整个冷却期。
                # 计数一律读增量维护的 _fail_count，不得改回 sum(self._samples)
                # （AGENTS「熔断计数必须增量」：整窗求和在 _lock 内是 O(window)，80+ 任务并发上报放大锁持有时间）。
                # [历史注] 旧判据无此条，fail_rate 填 0 时健康窗口同样熔断。
                if (
                    self._fail_count > 0
                    and len(self._samples) >= self._min_samples
                    and self._fail_count / len(self._samples) >= self._fail_rate
                ):
                    self._state = "open"
                    self._open_until = _now() + self._cooldown
                    self._end_probe()
            elif self._state == "half-open":
                if not self._probing or self._probe_owner is not current_thread():
                    # 非探针回报：① 转入 half-open 前已放行、此刻仍在途的普通轮次；
                    # ② 已被租约重授予取代的陈旧探针。样本照常入窗口（closed 态阈值复用），
                    # 但不得驱动 half-open→closed/open——否则旧探针会替新探针清窗口、关熔断。
                    return
                self._end_probe()
                # 当前探针结果决定：成功则恢复，失败则重新熔断（延长冷却）
                if success:
                    self._state = "closed"
                    self._samples.clear()
                    self._fail_count = 0
                else:
                    self._state = "open"
                    self._open_until = _now() + self._cooldown
            # open 状态：等待 cooldown 结束，由 allow() 转入 half-open

    def allow(self) -> bool:
        # 是否允许本次探测。open 且冷却结束后放行唯一探针；half-open 仅放一个探针；closed 放行。
        # 探针带租约：授予后超过 _PROBE_LEASE_SECONDS 仍未上报样本（探针轮以 continue 结束且
        # 不触发 record 的路径，如主播未开播）时重新授予，防止 _probing 永不复位导致该 key
        # 永久熔断（进程重启才恢复）。
        with self._lock:
            if self._state == "closed":
                return True
            now = _now()
            if self._state == "open":
                if now >= self._open_until:
                    if not self._probing:
                        self._state = "half-open"
                        self._grant_probe(now)
                        return True
                    return False
                return False
            # half-open
            if not self._probing:
                self._grant_probe(now)
                return True
            if now - self._probe_granted_at >= _PROBE_LEASE_SECONDS:
                # 租约超时：原探针未回报样本，重新授予（自愈）。代数随重授予递增并改记持有线程，
                # 原探针稍后回报时不再匹配当前持有者，只能作普通样本入窗口；同一线程重入时
                # 线程对象不变，仍能正常闭环。
                self._grant_probe(now)
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
            return self._fail_count / len(self._samples)


class ConcurrencyScheduler:
    # 录制并发与资源调度中枢：
    #   - 并发模式（set_dynamic_mode）：0=动态（网络容量随活跃任务数自适应缩放，带安全上下限）；
    #     非 0=固定（忽略动态调速器，网络容量恒为「同一时间访问网络的线程数」，最小 1 槽）；
    #   - 全局网络并发信号量（network_semaphore）：容量随活跃任务数自适应，带安全下限/上限；
    #   - 按 key 熔断器（breakers）：隔离各平台/站点错误，与并发模式正交，两种模式下均生效；
    #   - 可选录制并发软上限（recording_semaphore）：默认不限制，开启后限制同时 ffmpeg 数；
    #   - adjust_loop：守护循环，周期性重算全局容量。
    def __init__(
        self,
        *,
        configured_limit: int = 3,
        min_capacity: int = 1,
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
        # False=固定并发（容量恒为 configured_limit）。必须在 _compute_capacity() 首次调用
        # （下方创建 network_semaphore 时）之前初始化。_mode_announced 用于幂等播报。
        self._dynamic_mode = True
        self._mode_announced = False

        # 全局错误窗口（仅用于温和的全局背压，带安全下限），与 per-key 熔断互补。
        # 必须在 _compute_capacity() 首次调用（下方创建 network_semaphore 时）之前初始化。
        self._global_errors: deque[int] = deque(maxlen=self._error_window_size)
        # 窗口内失败数增量计数（与 _global_errors 同步）：整窗 sum() 是 O(window) 且持
        # _lock 执行；改增量后为 O(1)，语义等价。
        self._global_error_count = 0

        self._network_semaphore = ResizableSemaphore(self._compute_capacity())
        # 录制并发信号量：默认高容量（视作不限制）；set_recording_limit(>0) 时下调为实际上限
        self._recording_semaphore = ResizableSemaphore(self._RECORDING_UNLIMITED)
        self._recording_limit = 0  # 0 = 不限制

        # OrderedDict 而非普通 dict：_breaker 命中即 move_to_end，容量到顶时按「最久未使用」逐出
        # （普通 dict 没有 move_to_end，只能按插入序，一个仍在每轮上报的老 host 会被反复逐掉）。
        self._breakers: OrderedDict[str, PlatformBreaker] = OrderedDict()
        self._breakers_lock = Lock()

    # —— 容量计算 ——
    def _compute_capacity(self) -> int:
        # 单次加锁快照全部可变输入（模式/配置/活跃数/错误窗口由 main 主线程与 adjust_loop
        # 并发读写），保证多字段读取一致；_min/_max/_scale_divisor/_error_rate_floor 构造后
        # 不变，锁外读取安全。
        with self._lock:
            dynamic = self._dynamic_mode
            configured = self._configured_limit
            active = self._active_count
            if self._global_errors:
                rate = self._global_error_count / len(self._global_errors)
            else:
                rate = 0.0
        # 固定模式：忽略动态调速器与错误背压，容量恒为 configured_limit（即「同一时间访问网络的
        # 线程数」，set_configured_limit 已保证最小 1 个槽位）。
        # 这一支刻意**不**按 _max_capacity 封顶：AGENTS 把固定并发钉成「用户显式填写的并发值即上限」，
        # 在此顺手夹取会让用户填 200 只拿到 128 且毫无提示，属静默失准。
        if not dynamic:
            return configured
        # 动态模式：目标容量 = min(上限, max(配置值, ceil(活跃数/缩放因子)))；错误率极高时温和降容但永不低于下限。
        # 封顶必须发生在 max **之后**：只括住 max 的一支时，配置值一旦被填成大于 _max_capacity
        # （错配 / 复制粘贴来的大数）就整体取配置值，声明的安全上限被整个绕过——80 房间瞬间
        # 放开数百并发请求，正是这套调度器要防的形态。
        # [历史注] 旧写法 min 只括住 scaled 一支，即上述形态。
        target = min(
            self._max_capacity,
            max(configured, (active + self._scale_divisor - 1) // self._scale_divisor),
        )
        if rate >= self._error_rate_floor:
            target = max(self._min_capacity, int(target * 0.6))
        return max(self._min_capacity, target)

    def recompute(self) -> None:
        # 重算全局网络并发容量，容量变化时才调容（避免每轮无谓唤醒）。
        # 必须与 capacity 而非 value 比较：value 是剩余许可，有持有者时恒小于目标容量，
        # 每轮都会判定「变了」并 set_value，那正是并发净增失控的放大机制。
        new_cap = self._compute_capacity()
        if new_cap != self._network_semaphore.capacity:
            self._network_semaphore.set_value(new_cap)
            with self._lock:
                dynamic = self._dynamic_mode
                active = self._active_count
            if dynamic:
                logger.debug(
                    i18n.tr(
                        "并发模式: 动态调速，网络容量调整为 {new_cap}（活跃任务 {active}）",
                        new_cap=new_cap,
                        active=active,
                    )
                )
            else:
                logger.debug(
                    i18n.tr(
                        "并发模式: 固定，网络容量调整为 {new_cap}（来源: 同一时间访问网络的线程数）", new_cap=new_cap
                    )
                )

    # —— 配置入口 ——
    def set_active_count(self, n: int) -> None:
        # 上报当前活跃监控任务数（main 主循环每轮调用）。
        with self._lock:
            self._active_count = max(0, int(n))
        self.recompute()

    def set_configured_limit(self, n: int) -> None:
        # 上报配置中的「同一时间访问网络的线程数」：动态模式下作为容量下限之一；
        # 固定模式下即网络并发容量本身（固定值，非法值兜底为最小 1）。
        # 锁内写、锁释放后再 recompute（Lock 不可重入，避免与 _compute_capacity 嵌套）。
        with self._lock:
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
        # 设置并发模式：True=动态调速（网络容量随活跃任务数自适应，带安全上下限）；
        # False=固定并发（网络容量恒为「同一时间访问网络的线程数」）。
        # 幂等：模式未变且已播报过时直接返回（main 主循环每轮调用，避免重复日志与无谓调容）；
        # 模式变化或首次调用时重算容量并播报当前模式与有效并发数值。
        enabled = bool(enabled)
        # 幂等检查与写入同锁完成（read-modify-write 原子）；锁释放后再 recompute
        # （Lock 不可重入，避免与 _compute_capacity 嵌套）。
        with self._lock:
            if enabled == self._dynamic_mode and self._mode_announced:
                return
            self._dynamic_mode = enabled
            self._mode_announced = True
        self.recompute()
        # 播报取 capacity（并发上限本身）而非 value（剩余许可）：有房间持槽时后者会随
        # 瞬时占用波动，播报出的「网络容量」就不是调度器实际设定的上限了。
        # 关键字实参名 value 是四语目录里的占位符名，不得随属性名一起改（见 AGENTS「形参日志必须走 i18n.tr」）。
        if enabled:
            logger.debug(
                i18n.tr(
                    "并发模式: 动态调速（网络容量随活跃任务数自适应，当前 {value}，下限 {min_capacity}，上限 {max_capacity}）",
                    value=self._network_semaphore.capacity,
                    min_capacity=self._min_capacity,
                    max_capacity=self._max_capacity,
                )
            )
        else:
            logger.debug(
                i18n.tr(
                    "并发模式: 固定（忽略动态调速器，网络容量固定为 {value}，来源: 配置「同一时间访问网络的线程数」）",
                    value=self._network_semaphore.capacity,
                )
            )

    # —— 熔断器 ——
    def _evict_breakers_locked(self) -> None:
        # 调用方必须已持 _breakers_lock（本方法只在 _breaker 的锁内被调用）。
        # 逐出判据刻意排除「非 closed」的键：open / half-open 正是**仍在使用**的形态（冷却未结束、
        # 探针在飞），摘掉它等于把一次进行中的熔断重置成放行——那会把坏 CDN 立刻放回全部房间流量，
        # 比多留一支对象严重得多。因此只在 closed 键里挑最久未用的。
        # 锁序：本方法在 _breakers_lock 内读 br.state（再取 PlatformBreaker._lock）；PlatformBreaker
        # 从不反向引用调度器，不存在锁序环。
        # 全部键都在熔断态时本轮不逐出（宁可暂时超出上限，也不清除仍在生效的防线）：该形态要出现
        # 需要同时有 >_MAX_BREAKERS 个 host 处于 open/half-open，本身就是需要人工介入的信号。
        while len(self._breakers) > _MAX_BREAKERS:
            victim = next((key for key, br in self._breakers.items() if br.state == "closed"), None)
            if victim is None:
                return
            self._breakers.pop(victim, None)

    def _breaker(self, key: str) -> PlatformBreaker:
        with self._breakers_lock:
            b = self._breakers.get(key)
            if b is None:
                b = PlatformBreaker(key)
                self._breakers[key] = b
                self._evict_breakers_locked()
                return b
            # 命中即 touch：把键移到表尾，使「被逐出」等价于「没有任何房间再用过它」。
            # 不 touch 的话，一个仍在每轮 record 的 host 会因为创建得早而被逐掉、丢掉累计样本。
            self._breakers.move_to_end(key)
            return b

    def allow(self, key: str) -> bool:
        # 该 key 是否允许本轮探测（熔断时返回 False）。
        return self._breaker(key).allow()

    def backoff_seconds(self, key: str) -> float:
        return self._breaker(key).backoff_seconds()

    # —— 错误/成功计数（驱动熔断与全局背压）——
    def record_success(self, key: str | None = None) -> None:
        if key:
            self._breaker(key).record(True)
        with self._lock:
            self._push_global_error(0)

    def record_failure(self, key: str | None = None) -> None:
        if key:
            self._breaker(key).record(False)
        with self._lock:
            self._push_global_error(1)

    def _push_global_error(self, failed: int) -> None:
        # 入队一个全局样本并同步维护计数（调用方须已持 _lock）。
        # 扣减判据同 _push_sample：deque 达 maxlen 时 append 挤出最旧样本，须同步减其贡献。
        if len(self._global_errors) == self._error_window_size:
            self._global_error_count -= self._global_errors[0]
        self._global_errors.append(failed)
        self._global_error_count += failed

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

    # —— 守护循环 ——
    def adjust_loop(self) -> None:
        # 每 5 秒重算一次全局容量；per-key 熔断由 record_* 即时驱动，无需轮询。
        while True:
            _sleep(5)
            try:
                self.recompute()
            except Exception as e:  # 守护循环自身不应因异常退出
                logger.debug(i18n.tr("并发调度重算异常（已忽略）: {type_name}: {e}", type_name=type(e).__name__, e=e))


def host_of(url: str) -> str:
    # 熔断 key：取 URL 主机名——「://」后截到首个 /、?、# 为止（无 scheme 时对整串同样处理），
    # 小写、保留端口。空串或解析异常统一归 "unknown"（粗粒度兜底可接受：为坏地址细分只会
    # 多出零散桶，统计意义更弱）。
    # 截断后必须再剥 user:pass@：自定义流地址可写成 https://u:p@host/x.m3u8，不剥会导致
    # ① 凭据随 record_host 进 PlayURL.log / streamget.log（轮转保留多份 = 凭据长期落盘）；
    # ② 同一真实 host 因凭据不同被拆成多个熔断桶，失败样本被稀释、阈值到不了。
    # 用 rsplit 而非 split：IPv6 形态 [::1]:8080 与 userinfo 含 @ 的地址都要取最后一个 @ 之后。
    # 可复核判据：tests/test_regression_main.py::test_host_of_strips_userinfo
    # 孪生副本：scripts/douyin_live_recorder_standalone.py 的 host_of 是同语义副本（该文件按设计
    # 不 import src/），实测尚未剥 userinfo，待其负责人同步；改此处须两处同改。
    try:
        tail = url.split("://", 1)[-1]
        host = tail.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        host = host.rsplit("@", 1)[-1]
        host = host.lower()
        if not host:
            return "unknown"
        return host
    except Exception:
        return "unknown"


def _now() -> float:
    # 顶层已 import time；allow() 每个房间每轮都会走到这里，函数内 import 会多一次
    # sys.modules 查表，属纯浪费（此处仅保留可 patch 的间接层）。
    return time.monotonic()


def _sleep(seconds: float) -> None:
    time.sleep(seconds)


__all__ = [
    "ResizableSemaphore",
    "PlatformBreaker",
    "ConcurrencyScheduler",
    "host_of",
]
