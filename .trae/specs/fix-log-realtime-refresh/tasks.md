# Tasks

- [x] Task 1: 修复 `_read_output()` 中 `flush_batch()` 未重新激活调度器的问题
  - [x] 在 `flush_batch()` 内部函数中（L556-561），设置 `_log_queue_has_data = True` 后，添加调度器重新激活逻辑
  - [x] 实现与 `_log()` 方法（L675-676）一致的激活模式：检查 `self._log_flush_job_id is None`，若为 None 则调用 `self.root.after()` 重新激活
  - [x] 验证修改后语法正确

- [x] Task 2: 验证修复效果
  - [x] 检查 `_log()` 和 `flush_batch()` 两条路径的调度器激活逻辑一致
  - [x] 确认空闲时调度器仍会正确停止（不空转）
  - [x] 确认子进程日志路径和 UI 事件日志路径都能正常激活调度器

# Task Dependencies
- Task 2 依赖 Task 1 完成