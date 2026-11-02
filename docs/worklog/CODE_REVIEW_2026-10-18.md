# 代码审查报告（CODE_REVIEW_2026-10-18）

## 1. 审查概述与背景

本报告为对 DouyinLiveRecorder 工作空间（`d:\DouyinLiveRecorder`）内全部自研源代码的一次全面代码审查。该项目为基于 Python 的多平台直播录制工具，主运行环境为 Windows，由以下部分组成：命令行/引擎入口（根目录 `main.py` 等）、Tkinter 旧版 GUI（`gui.py`）、PySide6 新版桌面 GUI（`src/gui_qt/`）、Web 管理面板（`src/web_api.py`、`web/` 前端）、多平台直播流解析（`src/platforms/`、`src/spider.py`）、录制与后处理（`ffmpeg_*`、`video_postprocess.py`）、以及 CI 门禁与构建脚本（`scripts/`、`build_exe.py`）。

**审查目标**：排查代码质量、潜在缺陷、安全漏洞与逻辑错误，逐文件记录问题并给出修复建议，为后续修复排期提供依据。

**审查方法**：对全部纳入范围的源文件逐文件通读（大文件分段覆盖全部行），按"网络与流处理、录制与调度、基础设施、Web 服务层、桌面 GUI、平台解析、前端、脚本、测试"九个模块组并行深度审查；对全部"严重"级及关键"中等"级发现进行二次人工核验（含字节级验证与逐行验证），剔除误报。审查为只读操作，未修改任何代码。

**重要核实结论（避免误报）**：本仓库 `pyproject.toml` 声明 `requires-python = ">=3.14"`，代码库中有意使用 PEP 758 无括号异常语法（`except TypeError, ValueError:` 不带 `as`），该写法在 Python 3.14+ 下合法（`src/spider.py:47`、`src/recorder_status.py:62` 有明确注释说明）。审查中出现的此类"疑似语法错误"均经核实后**不作为问题**报告。

## 2. 审查范围

### 2.1 纳入范围

| 模块 | 位置 | 文件数 | 约行数 |
|---|---|---:|---:|
| 根目录入口与构建 | `main.py`、`web.py`、`gui.py`、`i18n.py`、`msg_push.py`、`build_exe.py`、`StopRecording.vbs` | 7 | ~15,800 |
| 网络与流处理 | `src/async_http.py`、`sync_http.py`、`proxy.py`、`http_config.py`、`cookie_cache.py`、`ttwid.py`、`ab_sign.py`、`spider.py`、`stream.py`、`stream_select.py`、`ws_client.py` | 11 | ~15,000 |
| 录制与调度 | `src/ffmpeg_install.py`、`ffmpeg_linux_download.py`、`ffmpeg_master_download.py`、`ffmpeg_proc.py`、`video_postprocess.py`、`srt_writer.py`、`recorder_status.py`、`room.py`、`scheduler.py`、`collector.py`、`base.py`、`startup_cleanup.py` | 12 | ~10,000 |
| 基础设施 | `src/config_bool.py`、`config_io.py`、`config_read.py`、`utils.py`、`logger.py`、`log_archive.py`、`notify.py`、`node_install.py`、`danmaku_monitor.py` | 9 | ~6,000 |
| Web 服务层 | `src/web_api.py`、`web_config.py`、`web_models.py`、`web_tray.py` | 4 | ~5,000 |
| 桌面 GUI（Qt） | `src/gui_qt/` 全部（含 `pages/`） | 17 | ~6,500 |
| 平台解析与 JS 签名 | `src/platforms/`（8 个）+ `src/javascript/`（4 个自研 JS） | 12 | ~8,000 |
| Web 前端 | `web/app.js`、`motion.js`、`index.html`、`style.css` | 4 | ~2,200 |
| 脚本与工具 | `scripts/`（18 个）+ `.agents/skills/dlr-dev-playbook/scripts/`（4 个） | 22 | ~7,500 |
| 测试 | `tests/` 全部（含 `frontend/` 的 `.mjs`） | 159 | ~55,400 |
| **合计** | | **~257** | **~131,000** |

### 2.2 排除项及理由

- `node_modules`、`dist`、`build` 目录：按审查要求排除（当前工作区中未见 dist/build 产物目录）。
- `__pycache__`、`uv.lock`：构建缓存与锁文件。
- `.qoder/`、`.qoder-credits/`、`.workbuddy/`：IDE/代理工具的会话产物与历史备份副本（`.workbuddy/tmp/i18n_param_migration_backup/` 为 `src/` 的旧拷贝，非活动源码）。
- `typings/`（`.pyi`）：第三方库类型存根（execjs、pystray）。
- `src/proto/douyin_pb2.py`：protoc 自动生成文件（已核对其中 `Response.needAck`、`PushFrame.payloadType` 等字段与 `douyin.py` 的访问点一致，无问题）。
- `src/javascript/crypto-js.min.js`：第三方压缩库（vendored），不属于自研源码。

## 3. 问题统计与总体评价

| 严重程度 | 数量 | 分布 |
|---|---:|---|
| 严重 | 1 | 生产代码 1（Qt GUI 录制输出断路） |
| 中等 | 37 | 生产代码 24、测试代码 13 |
| 轻微 | 48 | 生产代码 35、测试代码 13 |
| **合计** | **86** | |

**总体评价**：代码库整体工程化水平较高——安全防线设计意识明显（SSRF 协议白名单、Zip Slip 防护、下载哈希校验、TOFU 基准、Web 鉴权中间件、敏感信息脱敏、CRLF 注入防护等普遍存在且有配套测试），测试覆盖面广。但存在一个使新版 Qt GUI 录制输出完全失效的严重断路缺陷，以及一批集中在"异常路径/边界路径"的中等问题：响应体无上限导致的内存放大、配置写回静默失败、GUI 跨线程与模态重入、前端竞态覆盖等。另有若干测试自身无效或脆弱，需要一并整治。

## 4. 严重问题（1 项）

### S-01 Qt GUI 录制子进程输出通路完全断路，录制状态机失真

- **位置**：`src/gui_qt/recorder.py:42`（信号定义）、`recorder.py:404-407`（`_push` 仅入队）、`recorder.py:92`（`drain()` 无生产调用方）、`src/gui_qt/main_window.py:627`（唯一消费点）
- **类型**：逻辑错误 / 核心功能失效（已人工逐行核验）
- **说明**：`_read_output` 读取线程将日志批次与"进程结束哨兵"全部通过 `_push()` 写入 `_read_queue`，但 `linesReceived` 信号在全仓库范围内**从未 emit**，`drain()`（唯一的队列消费口）在生产代码中**从未被调用**。`main_window.py:627` 连接的 `linesReceived → _on_lines_received` 因此成为永不触发的死连接；三个 QTimer（`_log_timer`/`_status_timer`/`_danmaku_timer`）均不消费该队列。
- **影响分析**：
  1. 录制日志页永远收不到 ffmpeg 子进程输出，画质监控 `parse_line` 永远无输入；
  2. 自然 EOF（主播下播）时的结束哨兵无人消费，`_running` 虽被读线程置 False，但 UI 侧 `_on_recorder_ended` 不触发——界面永久显示"运行中"，弹幕监控线程不退出；
  3. `_process` 不清理，再次点击"开始录制"将报 `already_running` 失败。
  即：新版 Qt GUI 的录制可启动但不可观测、自然结束不可感知、无法连续录制。
- **修复建议**：在读线程 flush 处直接 `linesReceived.emit(payload)`（Qt 信号跨线程投递是线程安全的），由主线程 `_on_lines_received` 消费并处理结束哨兵；或保留队列但由主线程定时器周期性调用 `drain()`。修复后应补充"信号可达性"回归测试（现有测试仅直接调用 `drain()`，掩盖了该断路）。

## 5. 中等问题（37 项）

### 5.1 生产代码（24 项）

#### 根目录模块

**M-01 Web 模式退出不排空后处理线程池，退出可能长时间挂起**
- 位置：`web.py:334` ｜ 类型：资源泄漏/并发
- 说明：Web 模式退出路径仅清理 ffmpeg 与 HTTP 连接池，未调用 `main._shutdown_postprocess_executor()`；后处理线程池 worker 为非 daemon 线程，解释器退出时会 join 在途转码任务（单任务上限 3600 秒）。
- 影响：面板退出可能长时间无响应，且转码子进程无人终止。
- 修复：退出 `finally` 中补一次线程池排空/终止。

**M-02 StopRecording.vbs 存在双重 BOM，兜底停录脚本必然解析失败**
- 位置：`StopRecording.vbs:1` ｜ 类型：跨平台/文件编码（已经字节级核验：文件头为 `FF FE FF FE`）
- 说明：文件以两个 UTF-16 LE BOM 开头，WSH 只剥离流首一个 BOM，第二个 U+FEFF 位于语句位置（其后才是注释符 `'`），触发 800A0408 "Invalid character"。
- 影响：文档化的紧急停录兜底脚本无法执行；GUI 卡死时用户失去该恢复手段，强行杀进程可能产生缺 moov 的损坏录制文件。
- 修复：删除多余的一个 U+FEFF 字节。

#### 网络与流处理（src/）

**M-03 sync_http 400 分支全量读取错误体，绕过模块自建内存上限**
- 位置：`src/sync_http.py:399` ｜ 类型：安全/资源
- 说明：HTTP 400 分支 `e.read()` 未复用 `_read_capped` 的双重上限（`_MAX_RESPONSE_BYTES`/`_MAX_DECOMPRESSED_BYTES`），恶意服务器可用超大 400 响应体造成 OOM。
- 影响：当前该模块暂无生产 importer，属潜在攻击面；一旦启用即成实际风险。
- 修复：对 `e.read()` 套用同样的读取上限。

**M-04 生产主请求路径（async_req）响应体读取无上限，可被压缩炸弹打爆内存**
- 位置：`src/async_http.py:437` ｜ 类型：安全/资源
- 说明：主请求路径非流式全量读取响应体，httpx 自动解压 gzip/brotli 且无上限；被劫持平台/中间人用小体积高压缩比响应即可消耗巨量内存。
- 影响：与 M-03 不同，此路径是所有平台解析的实际在用路径，风险真实存在。
- 修复：改为流式分块读取并设置响应体/解压产出上限。

**M-05 cookie_cache singleflight 失败日志未脱敏**
- 位置：`src/cookie_cache.py:350` ｜ 类型：安全/信息泄露
- 说明：记录失败日志时 `e=e` 未过 `mask_credentials`；同文件 `fetch_cookies` 同位置已按仓库口径（凭据不入日志）脱敏，而异常文本常内嵌带签名/凭据的完整 URL。
- 影响：签名参数、凭据可能随异常文本长期落盘于轮转日志。
- 修复：该处异常文本统一过 `utils.mask_credentials`。

#### 录制与调度（src/）

**M-06 master 源 TOFU 基准读取漏接 UnicodeDecodeError，异常穿透至启动流程**
- 位置：`src/ffmpeg_master_download.py:294` ｜ 类型：错误处理
- 说明：`_tofu_verify_or_record` 读基准只捕 `OSError`；基准文件含非 ASCII 字节时 `read_text(encoding="ascii")` 抛出的 `UnicodeDecodeError`（ValueError 子类）既不被此处也不被调用方 `except (IntegrityError, OSError)`（:418）捕获，会穿出 `download_ffmpeg_master → install_ffmpeg_windows → check_ffmpeg` 直达启动流程，违反"失败一律返回 False 不抛"契约。姊妹模块 `ffmpeg_linux_download.py:268` 已修同一形态。
- 影响：特定损坏的基准文件会让程序启动阶段直接抛栈。
- 修复：该 `except` 并捕 `UnicodeDecodeError`，按完整性错误拒装处理。

#### 基础设施（src/）

**M-07 config_io.update_file 未命中目标行仍重写全文件并返回新值，产生"假成功"**
- 位置：`src/config_io.py:92` ｜ 类型：逻辑错误
- 说明：`old_str` 未命中任何行时函数仍原子重写全文件并返回 `new_str`，"未命中"与"替换成功"不可区分。
- 影响：依赖"失败返回 old_str"负信号的上层仲裁（如 web_api）会拿到假成功，且无谓刷新 mtime/快照。
- 修复：无命中时不落盘并返回 `old_str`。

**M-08 update_config 使用 strict=True 的 ConfigParser，重复键场景下 cookie/token 回写永久静默失败**
- 位置：`src/utils.py:623`（`read_ini_value` :468 同病）｜ 类型：错误处理缺失
- 说明：默认 `strict=True` 的 ConfigParser 遇到 config.ini 中现实存在的重复键时抛 `DuplicateOptionError`，被 `except` 吞成 warning 后回写流程终止。
- 影响：凭据刷新（cookie/token）在特定配置形态下永远写不回，且用户仅能在日志里看到一条 warning。
- 修复：改用 `strict=False`（tolerant_config_parser）。

**M-09 日志归档窗口期关闭标准流，其他线程 print 可能崩溃**
- 位置：`src/log_archive.py:128` ｜ 类型：并发
- 说明：`_archive_web_console` 先 `close` sys.stdout/sys.stderr 再重建；窗口期内其它线程调用 `print()` 会抛 `ValueError: I/O operation on closed file`。Windows 慢盘/杀软扫描会放大该窗口。
- 影响：Web 模式下请求线程可能在归档瞬间崩溃。
- 修复：先建新句柄并接管标准流，再关闭旧流并改名。

**M-10 backup_file 吞异常且无返回值，备份失败后该内容版本永不再重试**
- 位置：`src/config_io.py:435` ｜ 类型：错误处理缺失
- 说明：内部吞掉全部异常，`backup_file_start` 仍无条件推进 MD5 基线。
- 影响：某次备份失败（磁盘满/文件占用）后，该版本配置将静默缺失备份，违背备份机制目的。
- 修复：`backup_file` 返回成败，失败时不更新 MD5 基线。

#### 桌面 GUI（src/gui_qt/）

**M-11 后台线程直接调用 QTimer.start()，被 Qt 拒绝导致日志批次滞留**
- 位置：`src/gui_qt/main_window.py:766` ｜ 类型：跨线程
- 说明：`_queue_log` 会被 DanmakuMonitor 的 tail 后台线程直接调用（`gui_qt/danmaku_monitor.py:160/174`），在非 GUI 线程调用 `self._log_timer.start()` 触发 Qt "Timers cannot be started from another thread"。
- 影响：该批弹幕/日志滞留到下一次主线程入队才刷出，界面更新不确定延迟。
- 修复：用信号或 `QMetaObject.invokeMethod` 把"有新日志"投回主线程再启定时器。

**M-12 URL 配置冲突检测在定时器链中弹模态框，弹窗嵌套堆积**
- 位置：`src/gui_qt/main_window.py:899-908` ｜ 类型：逻辑错误/模态重入
- 说明：`_watch_url_config` 在 `_status_tick` 定时器链里弹模态 `QMessageBox.question`；模态事件循环期间定时器继续触发且 mtime 未更新，每 3 秒再弹一个新的冲突框。
- 影响：弹窗无限堆积，用户被迫逐个关闭。
- 修复：弹窗前置位/更新 `_url_last_mtime`，询问期间挂起该检测。

**M-13 录制中切换语言后状态卡回退为"待机"**
- 位置：`src/gui_qt/pages/dashboard.py:49` ｜ 类型：状态显示错误
- 说明：`status_title/status_sub` 以静态文案登记重译，`retranslate_all()` 把它们打回"待机"，而重译后的 `refresh_status` 只刷新信息网格、不按运行态重写。
- 影响：录制中切语言后控制台页显示"待机"，与侧栏/托盘状态矛盾。
- 修复：切语言后按 `recorder.is_running()` 重调 `_set_running_ui`。

**M-14 侧栏导航、页标题、托盘状态等 i18n 登记遗漏，切语言不生效**
- 位置：`src/gui_qt/main_window.py:244`（导航按钮/页标题）、`main_window.py:201/215/338`（brand_sub、status_chip）、`src/gui_qt/tray.py:80-81`（status_action 不在 retranslate 内）、`src/gui_qt/pages/quality.py:46-48/75-78/83`、`src/gui_qt/pages/danmaku.py:60-62/87-90/112` ｜ 类型：i18n 遗漏
- 说明：上述控件用裸 `i18n.tr()` 构建而未走 `T()+set_text` 登记体系，语言切换后保持旧语言。
- 影响：多语言界面一致性破坏（与 M-13 同根：重译体系存在覆盖盲区）。
- 修复：全部改走 `T()+set_text` 登记，切换后补调 `_set_running_ui`/托盘状态刷新。

**M-15 设置对话框关闭后定时器存活，反复开关累积"幽灵定时器"**
- 位置：`src/gui_qt/settings_dialog.py:90`（配合 `main_window.py:994` 每次 new 新实例）｜ 类型：资源泄漏
- 说明：对话框 accept/reject 后 C++ 对象因父窗口存活而保留，`_watch_timer` 每 5 秒继续轮询 config.ini 并可能对不可见窗口触发 `_load_config`。
- 影响：开/关 N 轮累积 N 个轮询定时器，产生无谓 IO 与日志噪声。
- 修复：closeEvent/hideEvent 停表，或复用同一对话框实例。

**M-16 语法高亮器随调色板切换无限叠加**
- 位置：`src/gui_qt/widgets.py:349` ｜ 类型：资源泄漏/渲染
- 说明：`apply_highlighter` 在每次 `apply_palette`（主题/缩放/字体切换都会触发）时新建 QSyntaxHighlighter 挂到同一 QTextDocument，旧实例从不销毁。
- 影响：切换 N 次叠加 N 个高亮器，旧行被旧配色反复重着色（颜色错乱）且全文档重复高亮开销。
- 修复：只建一次，后续仅更新颜色表并 `rehighlight()`。

#### Web 前端（web/）

**M-17 配置容器的 data-i18n 残留，切语言会清空整个配置表单**
- 位置：`web/index.html:152`（配合 `web/app.js:594`）｜ 类型：逻辑错误
- 说明：`#config-container` 自带 `data-i18n="loading"`；`loadConfig` 用 `innerHTML` 重建子节点后该属性仍留在容器上，此后任意 `applyTranslations` 都会用"加载中..."覆写整个容器的 textContent。
- 影响：语言切换瞬间把配置表单连同未保存修改清成一行占位文本，属于破坏性数据丢失路径。
- 修复：删除该 `data-i18n` 属性，或让 `applyTranslations` 跳过动态容器。

**M-18 按需加载接口无请求代次防护，快速操作时旧响应覆盖新状态**
- 位置：`web/app.js:1787`（loadFiles）、`:1243`（loadRooms）、`:1488`（loadConfig）｜ 类型：竞态
- 说明：三条按需加载链没有请求序号/代次校验（三条轮询链已有 `makePollChain`，此处缺失）；快速连续点击"进入"或面包屑时先发目录的响应可能后到，把面包屑和列表整体覆盖回旧目录。
- 影响：文件浏览/配置页显示与实际状态不一致。
- 修复：每次加载持自增序号，落地时非最新即丢弃。

**M-19 弹幕房间筛选下拉在每次 2 秒轮询后无条件重建 options**
- 位置：`web/app.js:1201` ｜ 类型：功能缺陷
- 说明：轮询成功即 `sel.innerHTML = opts` 重建选项集合，浏览器会在 option 集合重建时关闭展开的下拉列表。
- 影响：用户展开下拉选择房间的过程被周期性打断，几乎无法完成选择。
- 修复：仅当房间名称列表与当前选中项实际变化时才重建。

#### 脚本与工具（scripts/）

**M-20 standalone 脚本优雅停止逻辑必然失效（bytes 写入 TextIOWrapper）**
- 位置：`scripts/douyin_live_recorder_standalone.py:1899`（配合 `:1991` 的 `text=True`）｜ 类型：功能缺陷（已人工核验）
- 说明：`terminate_all_ffmpeg` 向 stdin 写 `b"q"`，但 `run_ffmpeg` 的 Popen 带 `text=True`，stdin 是 TextIOWrapper，`write(b"q")` 必抛 TypeError 且被 `:1901` 的 `except Exception: pass` 吞掉。
- 影响："写 q 优雅收尾补 moov"的一级停止策略恒失效，Windows 下停止录制退化为 TerminateProcess 硬杀，可能产出缺 moov 的不可播放文件。
- 修复：改写 `"q"` 字符串或移除 `text=True`（与主线 `ffmpeg_proc.py` 的实现口径对齐）。

**M-21 i18n 补丁脚本无视子进程退出码，编译失败静默成功**
- 位置：`scripts/patch_i18n_2026_09_12.py:233` ｜ 类型：逻辑错误
- 说明：`main()` 无条件 `return 0`，无视 `compile_po` 子进程的 returncode，与 `:232` 注释"非零透传给上层（CI 可见）"直接矛盾。
- 影响：`.mo` 编译失败在 CI 中不可见，翻译产物可能缺失。
- 修复：`return res.returncode`。

**M-22 i18n 补丁脚本硬编码旧开发机路径，本仓必然抛栈**
- 位置：`scripts/patch_i18n_2026_09_12.py:23` ｜ 类型：功能缺陷
- 说明：`ROOT = Path("D:/DouyinLiveRecorder-dev")` 为硬编码旧路径，在本仓运行必因 PO_PATH 不存在而异常。
- 影响：该补丁脚本当前完全不可用，幂等重跑能力失效。
- 修复：改为 `Path(__file__).resolve().parent.parent`。

**M-23 注解基线防呆误拒主目录下的工作区子目录**
- 位置：`scripts/check_annotations.py:409` ｜ 类型：逻辑错误
- 说明：用 `home in resolved.parents` 拒绝用户主目录下的一切路径；仓库检出在主目录下（`C:\Users\...` 或 Linux 家目录，属常态）时，`--snapshot` 连工具自己提示的工作区子目录（如 `.workbuddy/ast-baseline`）也被拒。
- 影响：该功能在常见目录布局下不可用。
- 修复：仅拒绝 `resolved == home` 及其直接层级，放行 cwd 之下的工作区子目录。

### 5.2 测试代码（13 项）

**MT-01 无效测试：MD5 去重分支从未被执行**
- 位置：`tests/test_config_io_update_file.py:343` ｜ 类型：无效测试
- 说明：sleep 桩首轮即抛 `_StopBackupLoop`，循环只跑一轮即终止，"MD5 未变不重复备份"分支从未覆盖，删掉去重逻辑本用例仍绿。
- 修复：首轮放行、第二轮才停，并断言 `backed_up` 条数。

**MT-02 整个测试文件无任何 test_ 函数，断言永不自动执行**
- 位置：`tests/test_bilibili_danmaku.py:27` ｜ 类型：无效测试
- 说明：全文件无任何 `test_` 函数，pytest 收集 0 用例，真机断言（token/WS 连通）永不自动执行、可静默腐烂；与已修复的 `test_bili_e2e.py` 同一反模式。
- 修复：补离线收集型用例或按双模模板改造。

**MT-03 恒真断言使安全锁失效**
- 位置：`tests/test_agent_hook_guard.py:229` ｜ 类型：断言恒真
- 说明：断言 `b"--no-cache-dir" not in proc.stderr`，但被拦截命令本就不含该子串；"拒绝消息不得回显完整命令原文"这条锁恒真。
- 修复：改断言命令中真实存在的片段（如 `--force-reinstall`）不出现。

**MT-04 并发用例无超时，被测死锁会挂死整个测试会话**
- 位置：`tests/test_cookie_cache.py:248`（`barrier.wait()` 与 `:259` `t.join()` 均无超时）｜ 类型：并发挂死
- 修复：`barrier.wait(timeout=15)`、`join(timeout=15)` 并断言线程已退出。

**MT-05 模块级导入在收集期污染进程环境变量**
- 位置：`tests/test_gui_language_retranslate.py:16` ｜ 类型：状态泄漏/顺序依赖
- 说明：模块级 `import gui` 使 `gui.py:185` 在收集期把 `DLR_GUI_PARENT=1` 写入进程环境且永不还原，子集运行时会让后续导入 `src.logger` 的文件整会话进入 GUI 父进程模式，并随 env 泄入所有子进程（`test_gui_monitor.py:11` 已明文定性此污染源）。
- 修复：改为用例内导入并配 autouse fixture 清除该环境变量。

**MT-06 固定 sleep 的脆弱时序断言**
- 位置：`tests/test_gui_qt_units.py:250` ｜ 类型：脆弱测试
- 说明：断言前仅固定 `time.sleep(0.5)`，被测 tail 线程轮询周期 0.3s，CI 高负载下余量不足偶发假红。
- 修复：改成同文件上半段已有的 deadline 轮询（约 5s 上限）。

**MT-07 后台写线程下断言未先 flush，存在竞态假红**
- 位置：`tests/test_log_archive.py:206` ｜ 类型：并发竞态
- 说明：边车独立写线程下，`room_message` 后未 `flush()` 即断言 `hub._file` 与磁盘 size，首条事件可能未落盘。
- 修复：每步断言前先 `hub.flush()`（同 `test_regression_infra.py` 口径）。

**MT-08 心跳超时用例依赖真实挂钟**
- 位置：`tests/test_machine_validation_fixes.py:93` ｜ 类型：时间依赖
- 说明：超时 close 须落在约 1.1s 且早于 3.0s 的外部停止，CI 停顿 >1.9s 即假红。
- 修复：改用可控假时钟驱动 `wait_for` 超时或放大停止余量。

**MT-09 直接补丁 stdlib asyncio.sleep 本体**
- 位置：`tests/test_regression_spider.py:586` ｜ 类型：补丁路径
- 说明：`patch.object(sp.asyncio, "sleep", ...)` 补在 stdlib asyncio 模块本体，窗口内全进程协程 sleep 被替换，违反仓库既定口径。
- 修复：浅拷贝 shim 后 `monkeypatch.setattr(sp, "asyncio", shim)`。

**MT-10 直接补丁 stdlib smtplib 本体，注释与实现相反**
- 位置：`tests/test_regression_utils.py:289` ｜ 类型：补丁路径
- 说明：`_no_real_network`/`_send` 把 SMTP/SMTP_SSL 补在 `msg_push.smtplib`（即 stdlib 模块本体），`:296` 注释称"不碰 stdlib 模块对象本身"与实现相反。
- 修复：注入 `msg_push` 可替换的模块级引用。

**MT-11 直接改写 os.rename 本体**
- 位置：`tests/test_regression_infra.py:213` ｜ 类型：补丁路径
- 说明：`monkeypatch.setattr(os, "rename", ...)` 直接改写全进程唯一的 `os.rename`；仓库内同类问题（M-27 形态）已被定性为跨用例竞态源并修复过。
- 修复：改为替换 `log_archive` 命名空间内的 os 引用（shim）。

**MT-12 真窗用例缺少无显示环境 skip 守卫**
- 位置：`tests/test_ui_kit.py:220`（另见 251/280）｜ 类型：环境脆弱
- 说明：三条 `tk.Tk()` 真窗用例无 headless skip 守卫，与文件头"无显示环境 skip"的声明矛盾；无头 CI 上抛 TclError 变 ERROR 而非 skip。
- 修复：仿 `test_ui_theme.py` 的 `tk_root` fixture。

**MT-13 直接改写 stdlib ctypes 本体**
- 位置：`tests/test_web_tray.py:128` ｜ 类型：补丁路径
- 说明：`monkeypatch.setattr(ctypes, "WinDLL", boom)` 直接改写 stdlib ctypes 模块本体（因容器是裸 Name 逃过静态门禁）。
- 修复：浅拷贝 shim 后替换 `web_tray` 命名空间内的 ctypes 引用。

## 6. 轻微问题（48 项）

### 6.1 生产代码（35 项）

| 编号 | 位置 | 类型 | 说明与修复建议 |
|---|---|---|---|
| L-01 | `web.py:128` | 资源泄漏 | 后台模式 `web_console.log` 追加打开且无轮转，常驻运行无界增长；纳入 log_archive 轮转或加大小上限 |
| L-02 | `gui.py:4952` | 并发/逻辑 | 退出路径用先前捕获的 `child_pid` 无条件 `taskkill /F /T`，Windows PID 复用窗口内可能误杀无关进程树；杀前校验映像名 |
| L-03 | `i18n.py:197` | 逻辑 | `_should_translate` 用 `startswith(_project_root)` 判定且无路径分隔符边界，同名前缀目录会被误判；补 `os.sep` |
| L-04 | `gui.py:4900` | i18n | 托盘通知"程序已最小化到系统托盘…"为裸中文未过 `tr()`（另见 :3597）；包裹 `tr()` |
| L-05 | `main.py:4569` | i18n | "FLV is not supported for h265…"为裸英文日志，违反"logger 首参须为 tr 模板"口径；改用 tr 模板并登记 msgid |
| L-06 | `src/cookie_cache.py:387` | 逻辑 | `invalidate()/clear()` 只清缓存字典，从不清理 `_inflight` 登记表；孤儿 key 残留后调用方恒走"等待超时→空结果"；清缓存时同步清两张登记表 |
| L-07 | `src/cookie_cache.py:99` | 逻辑 | `get_cached` 固定按 30 分钟 TTL 判过期，与写入侧自定义 ttl 口径不一；entry 记录各自 ttl |
| L-08 | `src/spider.py:2297`（另 :2347） | 安全/日志 | buvid3（B 站设备凭据）明文写入 debug 日志，违反"凭据不入轮转日志"口径；脱敏后再记 |
| L-09 | `src/spider.py:1266` | 逻辑 | 快手备用接口 eid 用 `url.split("/u/")[1].strip()` 未剥查询串，带 `?from=` 的分享链接拼出坏 eid；先剥 query 再取末段 |
| L-10 | `src/proxy.py:64` | 安全/逻辑 | 代理 URL 拼接 user/password 未做 percent 编码，密码含保留字符时生成非法代理 URL；用 `urllib.parse.quote` 编码 |
| L-11 | `src/stream_select.py:595`（另 :519/:543/:868） | 资源 | 探针非流式全量读响应体且无大小上限，不遵守 Range 的节点可回任意大 body；改 `client.stream` 并限量 |
| L-12 | `src/ffmpeg_install.py:279` | 错误处理 | 基准读取漏接 `UnicodeDecodeError`（同 M-06 形态），fail-closed 分支与 zip 清理被跳过；并捕处理 |
| L-13 | `src/ffmpeg_install.py:416` | 资源泄漏 | 下载中断与解压异常两条出口均不删 `ffmpeg_official_temp.zip`，数百 MB 残留；出口统一 unlink |
| L-14 | `src/ffmpeg_install.py:560` | 逻辑 | yum 在位但抛非 FileNotFoundError 异常时 `is_RHS` 保持 True，apt 分支被跳过，违反"直下兜底须两条路径都试过"的自述顺序；该分支同样置 `is_RHS = False` |
| L-15 | `src/ffmpeg_install.py:708`（另 :408、`ffmpeg_master_download.py:452`） | 跨平台 | Windows 上 `subprocess.run(["ffmpeg",...])` 未带 STARTUPINFO/CREATE_NO_WINDOW，无控制台形态下每次探测闪现控制台；复用 `video_postprocess.get_startup_info` |
| L-16 | `src/logger.py:150` | 一致性 | 导入期控制台 sink 硬编码 `colorize=True`，stderr 重定向到文件时 ANSI 转义污染日志；与 `rebind_console_sink` 一样按 isatty 判定 |
| L-17 | `src/config_read.py:65` | 逻辑 | `find_duplicate_options` 把不含 `=`/`:` 的非空行当独立键统计，而 configparser 视其为续行，多行值触发虚假告警；无分隔符的行跳过 |
| L-18 | `src/danmaku_monitor.py:76` | 性能 | 边车轮转 `os.replace` 失败被静默吞掉且无记忆，此后每条事件都重走 close/reopen/replace 高频无效 IO；失败后置一次性标记跳过 |
| L-19 | `src/utils.py:251` | 挂起风险 | `run_node_script_async` 缺同文件 `run_js_async` 自述的 `asyncio.wait_for` 外层保险，node 孙进程握住管道写端时协程永久挂起；外层补 wait_for |
| L-20 | `src/web_api.py:612` | 鉴权白名单 | 免鉴权白名单仅匹配 `path.startswith("/web/")`，认证开启时 GET `/web`（无尾斜杠）直接 401；白名单补 `path == "/web"` |
| L-21 | `src/web_config.py:1110` | 信息泄露 | `is_sensitive_item` 节白名单为大小写敏感比较而键名匹配是 IGNORECASE，`[cookie]` 等变体节名会明文回显；节名比对统一 casefold |
| L-22 | `src/web_config.py:125` | 逻辑 | 写侧允许 URL 段含逗号而读侧 `re.split(r"[,，]")` 在首个逗号处截断 URL，房间实际生效地址与录入不一致；写侧对 URL 段拒绝逗号 |
| L-23 | `src/web_api.py:1285` | 缓存一致性 | 安全配置缓存显式失效清单漏掉 `web_allowed_hosts` 与 `web_trusted_proxy`，病态场景下安全变更可能延迟生效；两键并入失效条件 |
| L-24 | `src/javascript/liveme.js:391` | 安全 | 注释样例含真实形态的会话素材（tongdun_black_box 样本）随源码分发；替换为 `<REDACTED>` 占位符 |
| L-25 | `src/javascript/haixiu.js:5` | 安全/质量 | 构造器用 `eval("_hf_constants1")` 等 4 处 eval 求值静态常量，无必要 eval 面；改为直接引用变量 |
| L-26 | `src/platforms/bilibili.py:231` | 错误处理 | `_reject_auth` 用裸 `asyncio.ensure_future` 派发关闭协程，异常无人回收（违背同文件 :169-171 的托管约定）；改用 `spawn_danmaku_task` |
| L-27 | `web/style.css:405`（另 :411） | 死代码 | `.dm-time`/`.dm-empty` 选择器从未命中（前端不产出对应类名）；删除或补齐类名 |
| L-28 | `web/style.css:16` | 死代码 | `--sidebar` 变量在两套主题定义但全文件无 `var(--sidebar)` 引用；删除或落地使用 |
| L-29 | `scripts/check_runtime_pins.py:113` | 错误处理 | 直接取 `build_exe` 私有属性，属性缺失时以 rc=1 崩溃栈退出，与"结构缺陷=rc=2"契约冲突；getattr 探测缺失统一 `sys.exit(2)` |
| L-30 | `scripts/run_gates.py:296` | 跨平台 | venv 路径含空格时 `cmd.exe /c` 会剥掉恰好两层引号致门禁命令解析失败；整条命令再包一层引号或改参数列表执行 |
| L-31 | `scripts/smoke_test.py:289` | 错误处理 | `expect_contains` 不校验元素类型，元素非 str 时抛 TypeError 穿透 main 变 rc=1 崩溃栈；校验元素必须为 str |
| L-32 | `.agents/.../server.cjs:129` | 错误处理 | `getNewestScreen` 的 statSync/readFileSync 无异常处理且 http server 无 error 兜底，竞态删除文件即崩整个 Node 进程；包 try/catch 返回 4xx/5xx |
| L-33 | `.agents/.../server.cjs:167` | 安全 | WebSocket 升级不校验 Origin 也无鉴权，任意网页可跨源连 127.0.0.1 服务伪造事件；校验 Origin 或启动时生成 token |
| L-34 | `.agents/.../server.cjs:311` | 资源泄漏 | shutdown 用 `server.close(cb)`，存续 WS 裸 socket 使回调永不触发，打印 server-stopped 后进程挂住；先 destroy 全部 clients 再退出 |
| L-35 | `.agents/.../start-server.sh:112` | 逻辑 | 前台模式把脚本 shell 自身 `$$` 写进 server.pid，该 shell 随即退出，PID 复用后 stop-server.sh 会误杀无关进程；前台模式不写 pid 文件 |

### 6.2 测试代码（13 项）

| 编号 | 位置 | 类型 | 说明与修复建议 |
|---|---|---|---|
| LT-01 | `tests/test_async_http_lock.py:62` | 并发健壮性 | 8 线程 `join(timeout=15)` 返回值未校验，挂死时假绿；join 后断言线程已退出 |
| LT-02 | `tests/test_async_http.py:140` | 并发健壮性 | 同上，join 超时未校验；修复同 LT-01 |
| LT-03 | `tests/test_concurrency_rate_limit.py:74`（另 :108） | 并发健壮性 | join 未校验线程退出，限流逻辑死锁时假绿；修复同 LT-01 |
| LT-04 | `tests/test_concurrency.py:119`（另 :188） | 并发健壮性 | join 未校验，singleflight 临界区死锁时假绿；修复同 LT-01 |
| LT-05 | `tests/test_bili_e2e.py:88` | 状态泄漏 | `asyncio.set_event_loop(loop)` 后仅 close 未复位，已关闭循环跨用例残留；finally 中 `set_event_loop(None)` |
| LT-06 | `tests/test_async_http_lock.py:133` | 状态泄漏 | 用例结束未清 `_client_cache`，FakeAsyncClient 跨文件滞留整个会话；与 setup 对称清理 |
| LT-07 | `tests/test_notify_script_guard.py:40`、`tests/test_notify.py:22` | 状态泄漏 | 模块级 `sys.path.insert(0, ...)` 永不还原；移入 fixture 并退出时移除 |
| LT-08 | `tests/test_logger_gui_parent.py:31` | 状态泄漏 | `reload_logger` 卸载漏复位 `_streamget_sink_id`/`_playurl_sink_id`（同构 fixture 已复位三项）；补齐 |
| LT-09 | `tests/test_i18n.py:21` | 环境依赖 | 直接断言宿主环境 `LANG != "zh_CN.utf8"`，本机设置该 locale 的开发者必误报；改为对比导入前后取值 |
| LT-10 | `tests/test_regression_spider.py:409` | 冗余 | 对 `record_url` 的同一断言连续重复两行；删一行 |
| LT-11 | `tests/test_ffmpeg_install.py:92` | 死代码/注释失实 | 注释称 `MASTER_CALLS` "由 fixture 逐用例清空"但实现未清空且无断言读取；补 `clear()` 或删除死记录 |
| LT-12 | `tests/test_web_tray.py:347` | 补丁方式 | `monkeypatch.setattr(os, "_exit", ...)` 直改 stdlib os 本体，与仓库"不改 stdlib 本体"约定相悖；改 shim 方式 |
| LT-13 | `tests/test_start_record_command_golden.py:459` | 工具风险 | `GOLDEN_REGEN=1` 配合 `-k` 只跑部分用例时会用部分快照覆写黄金基准 JSON；落盘前断言用例集合完整 |

## 7. 改进建议与修复优先级

### P0（立即修复，1-2 个工作日内）

1. **S-01** Qt GUI 录制输出断路——新版 GUI 的核心功能缺陷，用户可感知且阻断日常使用；修复成本低（补一次 emit 或主线程 drain）。
2. **M-02** StopRecording.vbs 双 BOM——一行字节修复，恢复紧急停录兜底能力。
3. **M-20** standalone 脚本 `b"q"` 写入失效——一行类型修复，消除"停止录制产出损坏文件"的数据风险。

### P1（本迭代内修复）

4. **内存上限类**：M-03、M-04（生产请求路径响应体/解压上限）、L-11（探针读取上限）——统一"读取必设上限"的口径。
5. **数据完整性类**：M-07（update_file 假成功）、M-08（重复键静默失败）、M-10（备份失败不重试）、M-06/L-12（UnicodeDecodeError 漏接，两处同形态建议一并修）。
6. **GUI 稳定性类**：M-11（跨线程启定时器）、M-12（模态重入）、M-15/M-16（定时器与高亮器泄漏）、M-13/M-14（重译覆盖盲区，建议一次性梳理登记体系）。
7. **前端体验/正确性**：M-17（切语言清空表单——数据丢失路径，优先）、M-18（竞态代次）、M-19（下拉重建）。
8. **测试有效性**：MT-01/02/03（无效与恒真测试，使保护失效）、MT-05（环境变量污染）、MT-09/10/11/13（stdlib 本体补丁，建议在 `test_test_hygiene` 静态门禁中补规则覆盖 shim 形态）。
9. **脚本可用性**：M-21/M-22（补丁脚本不可用）、M-23（基线防呆误拒）。

### P2（后续迭代）

10. 其余轻微项按模块顺手修复；建议优先处理带安全属性的 L-05（凭据日志）、L-08（buvid3 明文）、L-21（敏感节大小写）、L-24（样本素材替换）、L-33（dev 工具 WS 鉴权），其余作为日常技术债清理。
11. **机制性建议**：
    - 建立"响应体读取上限"与"异常文本过 mask_credentials"两条全局静态检查（可纳入现有 `scripts/check_annotations.py` 或 pre-commit 门禁），防止新增代码再次引入同类问题。
    - 为 PEP 758 语法在 CI 中固化一条说明性检查（`except A, B as e` 非法的形态已有注释约定，可加 lint 规则防误改）。
    - 测试门禁中增加"收集数=0 即失败"（针对 MT-02 类空测试文件）与"join 后必须断言线程退出"的约定检查。

## 8. 总结性结论

本次审查覆盖工作空间内约 257 个自研源文件、约 13.1 万行代码（含测试），共确认问题 86 项：**严重 1 项、中等 37 项、轻微 48 项**，另剔除 3 项经核验的误报（PEP 758 语法被误判为 Python 2 残留）。

整体而言，该项目安全工程基础扎实：SSRF 协议白名单、Zip Slip/解压炸弹防护、下载哈希校验与 TOFU 基准、Web 鉴权与同源校验、敏感信息脱敏等机制普遍存在且大多有配套测试；错误处理与日志规范在主线代码中执行较好。主要风险集中在三类：**（1）新增 Qt GUI 的集成断路**（S-01，唯一严重项）；**（2）异常与边界路径的健壮性缺口**（响应体无上限、配置/备份静默失败、归档窗口竞态等）；**（3）测试自身的有效性**（恒真断言、空测试文件、stdlib 本体补丁——这些会削弱上述安全机制的保护力）。

建议按第 7 节优先级推进修复：P0 三项均为低成本高收益的一级修复；P1 建议按"内存上限→数据完整性→GUI 稳定性→测试有效性"四个专项集中治理；P2 项可随迭代消化。修复完成后建议针对本报告所列各项补充回归测试，并将第 7.11 节的机制性检查固化为长期门禁，防止同类问题回潮。

---
*审查方式：全量逐文件人工式审查 + 关键发现二次核验（字节级/逐行）；审查过程只读，未改动任何代码。*
