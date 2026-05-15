# 日志实时刷新修复 Spec

## Why
录制直播间时，子进程 main.py 输出的日志通过 `_read_output` → `flush_batch()` 写入队列后，按需调度器 (`_schedule_log_flush`) 在处理完一批数据后因队列为空而停止调度。后续子进程继续输出日志时，`flush_batch()` 只设置了 `_log_queue_has_data = True`，但没有重新激活调度器，导致日志永久滞留在队列中，UI 不再刷新。

## What Changes
- 修复 `_read_output()` 中的 `flush_batch()` 函数：在将数据放入队列后，检查调度器是否已停止，若停止则重新激活
- 确保两条日志写入路径（UI 线程的 `_log()` 和子进程读取线程的 `flush_batch()`）行为一致

## Impact
- Affected specs: `perf-startup-shutdown`（日志刷新按需调度是上次优化引入的）
- Affected code: `gui.pyw` 的 `_read_output()` 方法（L556-561 的 `flush_batch` 内部函数）

## MODIFIED Requirements

### Requirement: 按需调度日志刷新必须覆盖子进程输出路径
系统 SHALL 确保从子进程 stdout 读取的日志（通过 `_read_output` → `flush_batch()`）能够正确激活日志刷新调度器，行为与 UI 事件触发的 `_log()` 一致。

#### Scenario: 录制期间子进程持续输出日志
- **GIVEN** 录制子进程正在运行并持续向 stdout 输出日志
- **WHEN** `_read_output` 线程读取到日志行并通过 `flush_batch()` 放入队列
- **AND** 此时日志刷新调度器 (`_log_flush_job_id`) 已停止（为 None）
- **THEN** 调度器 SHALL 被重新激活，日志 SHALL 在 200ms 内刷新到 UI

#### Scenario: 录制期间子进程输出稀疏日志
- **GIVEN** 录制子进程正在运行但输出日志间隔 > 200ms
- **WHEN** 调度器处理完上一批日志后因队列为空而停止
- **AND** 随后子进程输出新日志行
- **THEN** 调度器 SHALL 被重新激活，新日志 SHALL 在 200ms 内刷新到 UI

#### Scenario: 空闲期间不空转（保持按需调度特性）
- **GIVEN** 子进程未运行，无任何日志输出
- **WHEN** 调度器处理完队列后停止
- **THEN** 调度器 SHALL 保持停止状态，不消耗 CPU 资源
- **AND** 当 `_log()` 或 `flush_batch()` 产生新日志时 SHALL 立即重新激活