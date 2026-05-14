# 启动与退出代码性能分析 Spec

## Why
`gui.pyw` 和 `main.py` 的启动流程和退出流程中存在多处同步阻塞调用，导致程序启动缓慢（最长 15 秒代理检测）和退出时 UI 线程冻结（最长 25 秒进程清理），影响用户体验。

## What Changes
- 分析并消除 `main.py` 启动流程中的阻塞瓶颈（代理检测超时、重复配置读取、冗余 sleep）
- 分析并消除 `main.py` 退出流程中 `cleanup_all_ffmpeg_processes()` 的串行累积超时
- 分析并消除 `gui.pyw` 退出流程中 `stop_recording()` 阻塞 UI 线程的问题
- 分析并消除 `gui.pyw` 退出流程中 `_cleanup_zombie_ffmpeg()` 阻塞问题

## Impact
- Affected specs: 无（首次性能分析）
- Affected code: `main.py` (启动初始化区 L1987-2130、安全退出 L93-164)、`gui.pyw` (stop_recording L493-550、quit_application L732-758、_cleanup_zombie_ffmpeg L760-796)

## ADDED Requirements

### Requirement: main.py 启动时不阻塞超 5 秒
系统 SHALL 在 5 秒内完成启动初始化，包括 FFmpeg 检测和代理检测，不应因单次网络超时而大幅延长启动时间。

#### Scenario: 代理检测超时不应阻塞启动
- **GIVEN** 系统未配置代理或 Google 不可达
- **WHEN** `main.py` 启动执行代理检测
- **THEN** 代理检测 SHALL 在 5 秒内超时返回，而非等待 15 秒

#### Scenario: 配置文件不应被重复读取
- **GIVEN** `read_config_value()` 被多次调用
- **WHEN** 每次调用都触发 `config_parser.read()` 全量读取
- **THEN** 配置文件 SHALL 仅读取一次，后续调用使用内存缓存

### Requirement: main.py 退出时不应串行阻塞超 5 秒
系统 SHALL 在 5 秒内完成所有 FFmpeg 进程清理，多个进程应并行终止而非串行等待。

#### Scenario: 多个 FFmpeg 进程并行退出
- **GIVEN** 当前有 N 个 FFmpeg 子进程正在运行
- **WHEN** 用户发送 SIGINT/SIGTERM 信号触发 `safe_exit`
- **THEN** 所有 FFmpeg 进程 SHALL 并行终止，总等待时间不超过 5 秒

### Requirement: gui.pyw 退出时不应冻结 UI 线程
系统 SHALL 在退出流程中将进程终止操作移至后台线程执行，保持 UI 响应，总退出时间不超过 3 秒。

#### Scenario: stop_recording 在后台执行
- **GIVEN** 用户点击"彻底退出"按钮
- **WHEN** 有录制子进程正在运行
- **THEN** 进程终止操作 SHALL 在后台线程执行，UI SHALL 在 1 秒内关闭窗口

#### Scenario: ffmpeg 僵尸进程清理不阻塞退出
- **GIVEN** 用户触发退出流程
- **WHEN** `_cleanup_zombie_ffmpeg()` 被调用
- **THEN** 清理操作 SHALL 在 3 秒内完成（含超时保护）

## MODIFIED Requirements
无（首次分析，不涉及修改现有需求）

## REMOVED Requirements
无