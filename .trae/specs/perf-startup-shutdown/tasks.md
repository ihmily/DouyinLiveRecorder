# Tasks

- [x] Task 1: 分析 main.py 启动流程性能瓶颈
  - [x] 定位 `check_ffmpeg_existence()` 中 `time.sleep(1)` 的冗余延迟
  - [x] 定位代理检测 `urllib.request.urlopen("https://www.google.com/", timeout=15)` 的 15 秒超时阻塞
  - [x] 定位 `read_config_value()` 中每次调用都执行 `config_parser.read()` 的重复磁盘 I/O
  - [x] 量化每个瓶颈的实际耗时，输出分析报告

- [x] Task 2: 分析 main.py 退出流程性能瓶颈
  - [x] 定位 `cleanup_all_ffmpeg_processes()` 中每个 FFmpeg 进程串行等待 10+5+5 秒的累积超时
  - [x] 定位 `safe_exit()` 中 `sys.exit(0)` 前无超时保护的问题
  - [x] 量化最坏情况下的退出总耗时（N 个 FFmpeg 进程时），输出分析报告

- [x] Task 3: 分析 gui.pyw 退出流程性能瓶颈
  - [x] 定位 `stop_recording()` 中 `proc.wait(timeout=10)` + `proc.wait(timeout=5)` 阻塞 UI 线程共 15 秒
  - [x] 定位 `quit_application()` 中 `_cleanup_zombie_ffmpeg()` 的 `subprocess.run(timeout=10)` 阻塞 UI 线程 10 秒
  - [x] 定位 `quit_application()` 中 `self.root.quit()` 调用前总计阻塞 25 秒的问题
  - [x] 量化退出时 UI 冻结的总时长，输出分析报告

- [x] Task 4: 汇总分析结果，生成性能瓶颈报告
  - [x] 汇总 main.py 和 gui.pyw 的所有性能瓶颈及其影响
  - [x] 按严重程度排序（UI 冻结 > 启动阻塞 > 退出等待）
  - [x] 生成 Markdown 格式的最终分析报告，包含每个瓶颈的代码位置、原因、影响和修复建议

# Task Dependencies
- Task 4 依赖 Task 1、Task 2、Task 3 全部完成
- Task 1、Task 2、Task 3 可并行执行