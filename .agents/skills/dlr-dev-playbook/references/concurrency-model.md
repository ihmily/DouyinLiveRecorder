# 并发、事件循环与锁

> 涉及锁 / 事件循环 / 信号量的改动必须先读本节。
> 唯一事实源仍是 `AGENTS.md`；本文件展开架构细节与事故背景。

## 基础模型

- **每房间一个独立线程 + 各自独立的 `asyncio.run()` 事件循环**: `main()` 为每个 URL 启常驻 `threading.Thread`（`_room_thread_target` → `start_record`），线程内以 `asyncio.run(...)` 逐轮驱动异步请求。**不存在共享的全局事件循环。**

## 调度中枢 src/scheduler.py

- 取代旧「单个全局 `Semaphore(1)` + 单向压制的 `adjust_max_request`」模型（80 房间共抢 3 槽位、严重延迟）。
- `ConcurrencyScheduler` 为中枢：**并发模式由「最大同时录制数(0为不限制)」是否为 0 决定**——为 0 → 动态调速（默认 min=1/max=128，`max(下限, min(上限, ceil(活跃数/缩放因子)))`，错误率极高时温和降容但永不低于下限，杜绝死螺旋）；非 0 → 固定并发（忽略动态调速与背压，最小 1 槽）。`adjust_loop` 守护循环每 5s 重算容量（固定模式下重算为幂等 no-op）。`main()` 首轮初始化 `scheduler = ConcurrencyScheduler(configured_limit=max_request)`，把全局 `semaphore`/`recording_semaphore` 两 `ResizableSemaphore` 指向其属性。
- `ResizableSemaphore`: 支持运行时 `set_value` 调容（增大唤醒等待者；减小仅降上限、不强行回收已持槽位）；`__init__`/`set_value` **允许容量 0**（暂停态）。
- `PlatformBreaker`（按 host 熔断，`closed→open→half-open`）: open 经冷却后放唯一探针，成功→closed、失败→重新 open；按 host 隔离。探针带租约（`_PROBE_LEASE_SECONDS=60s`）——探针轮可能以 `continue` 结束且不触发 `record`（主播未开播等待/`disable_record`/线程退出），`_probing` 无租约兜底将永不复位→永久熔断；租约超时后 `allow()` 重新授予探针自愈。回归测试 `test_platform_breaker_probe_lease_regrants_after_timeout`。
- **接线点仅限固定几处**: `notify.record_error/record_success` 增 `key` 形参委托 `main.scheduler`；`start_record` 入口 `record_host = host_of(record_url)` 且**必须在 `while True` 外层 try 之前预置 `record_host = ""`**（否则 basedpyright 判 possibly unbound）；平台分派前 `scheduler.allow(record_host)` 预检、False 则退避后 `continue`；`check_subprocess` 录制循环受 `recording_semaphore` 管控。
- 相关配置项「最大同时录制数(0为不限制)」兼作网络并发模式开关；「同一时间访问网络的线程数」在动态模式下为容量下限之一、固定模式下即固定并发值（最小 1）。键名禁止含 `=`/`:`（见 known-pitfalls.md 配置键名条目）。
- **调度模块测试**: `tests/test_scheduler.py`（29 用例）。

## 录制结果反馈约定（main.py / src/stream_select.py）

- **`check_subprocess` 须按 ffmpeg 退出码上报调度样本**: `rc==0` → `record_success(host_of(record_url))`；`rc!=0` → `record_error(...)`。**禁止轮末无条件 `record_success`**——失败轮记成成功会稀释按 host 熔断统计。
- **快速失败须记入探针退避**: `time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS`(20.0) 判快速失败时，解析 `-i` 后实际拉流地址调 `stream_select.mark_ffmpeg_reject(url, platform)`。
- **录制成功须撤销该地址探针退避（`clear_ffmpeg_reject`，与 `mark` 对称）**。
- **解析成功轮即上报成功样本**: `port_info["anchor_name"]` 非空须 `record_success(record_host)`。
- **直下路径（`direct_download_stream`）补成功样本**。

## 锁的强制约定

- **禁止模块级 `asyncio.Lock()` 单例**: 惰性绑定首个 `await` 它的事件循环，后续新循环 `await` 即抛 `RuntimeError: … bound to a different event loop`。正确做法见 `src/async_http.py` 的 `_get_client_lock()`：**随当前事件循环缓存/重建**。仅单房间不报错，**必须并发多房间才能复现**。
- **跨 `await` 持有的跨线程锁一律用 `threading.RLock`，不得用 `threading.Lock`**: 凭据去重锁（`_ttwid_lock`/`_kuaishou_did_lock`/`_twitch_client_id_lock`）跨越 `await` 持有；普通 `Lock` 下同一循环第二个并发协程会自旋死锁。`RLock` 使同线程重入退化为幂等重复拉取，跨线程去重语义不变。
