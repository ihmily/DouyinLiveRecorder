# 代码审查报告（CODE_REVIEW_2026-10-19）

## 1. 审查概述与背景

本报告为对 DouyinLiveRecorder 工作空间（`D:\DouyinLiveRecorder`）内全部自研源代码的一次全面代码审查。该项目为基于 Python 3.14 的多平台（60+）直播录制工具，提供四个入口：命令行/录制引擎（根目录 `main.py`）、旧版 Tkinter GUI（`gui.py`）、新版 PySide6 GUI（`src/gui_qt/`）、Web 管理面板（`src/web_api.py` + `web/` 前端）。

**审查目标**：排查代码质量、潜在缺陷、安全漏洞与逻辑错误，逐文件记录问题并给出修复建议，为后续修复排期提供依据。

**审查方法**：

1. **分组并行深度通读**：按"根目录入口、平台解析、网络层、选源与录制流、工具与调度、录制与后处理基础设施、Web 服务层、桌面 GUI、前端与 JS、脚本与构建、测试有效性"划分为 11 个审查分组，逐文件分段通读（大文件如 `spider.py` 7384 行、`main.py` 5948 行、`gui.py` 5366 行均按段覆盖至末行），共覆盖约 263 个自研源文件、约 13.1 万行代码。
2. **关键结论二次实测裁定**：对全部"严重"级结论及若干争议结论，使用项目 venv 的 Python 3.14.8 进行实测核验（AST 解析、内存峰值测量、脱敏函数复现、命令守卫变形语料测试等），剔除误报 2 项、降级 1 项。**未经实测支撑的结论一律标注"（待核）"**。
3. **与前次报告的差分复核**：对 2026-10-18 报告（`CODE_REVIEW_2026-10-18.md`，86 项）中可机检的条目逐条复核现状，结果见第 7 节。

**审查性质**：全程只读，未修改任何生产代码、测试或配置。

### 1.1 已剔除的误报（重要）

| 被判定的"问题" | 裁定 | 实测依据 |
|---|---|---|
| 7 个 UI/GUI 文件（含 `src/gui_qt/shared.py:58,73,81`、`src/ui_theme.py:196,244`、`src/ui_scale.py:176`、`src/ui_motion.py:99,123`、`src/ui_kit.py:670`）使用"Python 2 语法" `except A, B:`，导致 GUI 无法导入 | **证伪，不予采纳** | 用项目 venv Python **3.14.8** 对 `shared.py`/`danmaku_monitor.py`/`pages/danmaku.py`/`ui_theme.py`/`ui_scale.py`/`ui_motion.py`/`ui_kit.py`/`logger.py`/`utils.py`/`spider.py` 执行 `ast.parse`，**SyntaxError 计数 = 0**。该写法是 PEP 758 无括号多异常语法，在 3.14 下合法且为本仓有意采用（`AGENTS.md`「代码风格」明确登记）。用 3.13 及以下的解释器做 `compileall`/`py_compile` 会产生此假阳性。 |
| `src/ws_client.py:88` 的 `obj.flush()` 不带长度参数，使解压上限被完全绕过，单帧可膨胀至 GB 级 | **部分证伪，降级为轻微（L-16）** | 实测：gzip 压缩 200MB 全零数据（压缩后 203,860 字节）送入 `decompress_limited(comp, 8MiB)`，正确抛 `ValueError`，`tracemalloc` 测得**峰值 16.2 MB**（60MB 载荷下同为 16.1 MB）。即 `flush()` 的实际产出受内部缓冲约束，峰值约为标称上限的 2 倍，**不随载荷线性放大**，不存在所述 GB 级放大。 |

---

## 2. 审查范围

### 2.1 纳入范围

| 模块组 | 主要位置 | 文件数 | 约行数 |
|---|---|---:|---:|
| 根目录入口 | `main.py`、`gui.py`、`web.py`、`i18n.py`、`msg_push.py`、`build_exe.py` | 6 | ~15,000 |
| 平台解析 | `src/spider.py`、`src/platforms/`（7）、`src/proto/` | 9 | ~8,900 |
| 网络层 | `src/async_http.py`、`sync_http.py`、`http_config.py`、`proxy.py`、`ws_client.py`、`cookie_cache.py`、`ttwid.py`、`ab_sign.py`、`node_install.py` | 9 | ~3,830 |
| 选源与录制流 | `src/stream_select.py`、`src/stream.py` | 2 | ~2,520 |
| 工具与调度 | `src/utils.py`、`collector.py`、`scheduler.py`、`room.py`、`base.py`、`recorder_status.py`、`danmaku_monitor.py` | 7 | ~3,760 |
| 录制/后处理/基础设施 | `src/ffmpeg_install.py`、`ffmpeg_proc.py`、`ffmpeg_linux_download.py`、`ffmpeg_master_download.py`、`video_postprocess.py`、`srt_writer.py`、`log_archive.py`、`logger.py`、`config_io.py`、`config_read.py`、`config_bool.py`、`notify.py`、`startup_cleanup.py`、`src/__init__.py` | 14 | ~5,200 |
| Web 服务层 | `src/web_api.py`、`web_config.py`、`web_models.py`、`web_tray.py` | 4 | ~3,420 |
| 桌面 GUI | `src/gui_qt/`（含 `pages/`）、`src/ui_kit.py`、`ui_theme.py`、`ui_scale.py`、`ui_motion.py`、`ui_fonts.py`、`ui_i18n.py` | 22 | ~7,450 |
| 前端与自研 JS | `web/app.js`、`motion.js`、`index.html`、`style.css`、`src/javascript/`（4 个自研签名脚本） | 8 | ~4,950 |
| 脚本与构建 | `scripts/`（15 个 `.py` + 2 个 `.sh`）、`StopRecording.vbs` | 18 | ~8,000 |
| 测试 | `tests/`（含 `frontend/` 的 `.mjs`） | 164 | ~68,000 |
| **合计** | | **~263** | **~131,000** |

### 2.2 排除项及理由

- `node_modules`、`dist`、`build`：按审查要求排除（当前工作区无 `dist`/`build` 产物目录）。
- `__pycache__`、`uv.lock`、`DouyinLiveRecorder.egg-info`：构建缓存与自动生成元数据。
- `.venv/`、`.workbuddy/`、`.agents/skills/*/scripts/`（Node 侧可视化伴侣）、`.qoder*`：运行环境与工具链产物。
- `typings/`（`.pyi`）：第三方库类型存根（execjs、pystray）。
- `src/proto/douyin_pb2.py`：protoc 自动生成文件。
- `src/javascript/crypto-js.min.js`：vendored 第三方压缩库。
- `docs/`、`i18n/*.json|yaml|po|mo`、`README*.md`：文档与语言资源（非源码逻辑）。

---

## 3. 问题统计与总体评价

| 严重程度 | 数量 | 分布 |
|---|---:|---|
| 严重 | 5 | 生产代码 4（安全 2、逻辑/资源 2）+ 工具脚本 1（安全） |
| 中等 | 48 | 生产代码 37、工具脚本 4、测试代码 7 |
| 轻微 | 55 | 生产代码 36、工具脚本 7、测试代码 12 |
| **合计** | **108** | |

**总体评价**：与上一轮审查相比，本轮的最大变化是**安全防线的"完成度"显著提高而"一致性"成为新的短板**。上一轮指出的绝大多数条目已被真实修复（详见第 7 节，可机检的 26 项中 24 项已修）；SSRF 逐跳复检、响应体上限、凭据脱敏、Zip Slip/解压炸弹防护、运行时二进制哈希钉定、Web 鉴权与同源校验等机制普遍存在且大多带回归锁。

但本轮暴露出三个系统性问题：

1. **"兜底即绕过"的 fail-open 形态在多条安全链上并存**——备份脱敏在解析失败时返回明文（S-02）、派生地址安全闸在末位放行时被翻回"可达"（S-04）、node 官方校验文档不可达时零校验放行（M-19）。共同模式是：异常被当作"保守放行"处理，而最可能被攻击者触发的恰恰是这条异常路径。
2. **安全判据的实现强度弱于注释声明**——命令守卫按文本形态匹配因而可被引号/尾随空格绕过（S-01）、响应体上限在重定向中间跳与单块解码输出上留有缺口（M-16/M-17）、打包冒烟的"进程存活"判据名不副实（M-41）。这类落差比完全没有防线更危险，因为后来者会照文件头声明去信任结论。
3. **新增 Qt GUI 的生命周期路径未做端到端验证**——退出后事件循环永不返回（S-03）、停止路径异常后 UI 永久卡死（M-33）。上一轮的 S-01（输出断路）修复方式正确，说明该模块正在快速成熟，但"退出"这条路径仍未跑通。

---

## 4. 严重问题（5 项）

### S-01 删除守卫可被引号、尾随空格与参数分写形态整体绕过

- **位置**：`scripts/agent_hook_guard.py:239-252`（关键行 244-246）；相关薄弱点 `:73-76`（动词表）、`:112`
- **类型**：安全 / 拦截绕过
- **说明**：`_protected_hit` 判定受保护目录时，要求目录名**紧随其后的那一字节**必须是 `/`、`\` 或字符串结尾：

  ```python
  tail = statement[match.end() : match.end() + 1]
  if tail and tail not in "/\\":
      continue          # 目录名后还有任何字符即跳过本次命中
  ```

  于是给目标加引号、或末尾多一个空格，命中即被整条跳过。
- **实测裁定**（venv 3.14.8，直接调 `check_bash_command`）：

  | 命令 | 结果 |
  |---|---|
  | `rm -rf logs` | BLOCKED |
  | `rm -rf logs `（尾随空格） | **ALLOWED** |
  | `rm -rf "logs"` / `rm -rf 'logs'` | **ALLOWED** |
  | `find logs -type f -delete` | **ALLOWED** |
  | `rm -r -f .`（参数分写） | **ALLOWED** |
  | `rm -rf ./logs/`、`rm -rf logs/` | BLOCKED |

- **影响分析**：该 Hook 是 PreToolUse 侧唯一能确定性阻断（`exit 2`）的检查点，其存在理由正是"不可逆"（模块头 5-8 行）。上述形态全部绕过 → `downloads/`、`logs/`、`recordings/`、`backup_config/`、`scripts/` 可被递归强制删除且无拦截。引号与尾随空格属最自然的命令书写形态，不是刻意构造的变形；`rm -r -f` 分写与 `-Recurse`+`-Force` 也是常见写法。`_DELETE_VERB_RE` 另漏 `ri`（PowerShell `Remove-Item` 别名）、`os.removedirs`、`Clear-*`。
- **修复建议**：① 判定前先剥离 token 外层引号再取 `tail`；② `tail` 判据改为"目录名后为路径分隔符、引号、空白或行尾"之一；③ `_RECURSIVE_FORCE_RE` 增补 `-r`/`-f` 分写与 `--recursive`/`--force` 长选项形态；④ 删除动词补 `ri`、`os.removedirs`、`Clear-Content`；⑤ 每条新增形态进 `run_self_test()` 的 `block_cases`（现有 3 条全是"干净形态"，等于只证明了理想输入能拦住）。

### S-02 备份脱敏在配置重复键下 fail-open，明文凭据落入 backup_config

- **位置**：`src/config_io.py:367-376`（`_redact_ini_secrets`）、`:412-423`（`backup_file` 调用与回退）
- **类型**：安全 / 凭据泄露
- **说明**：`_redact_ini_secrets` 用 `configparser.ConfigParser(interpolation=None)` 解析，该构造**默认 `strict=True`**。`config.ini` 一旦出现"同一节内两行同名键"，`parser.read_string(text)` 抛 `DuplicateOptionError`（`configparser.Error` 子类），被 `:375-376` 的 `except configparser.Error: return text` 接住后**返回未脱敏原文**，随后 `backup_file` 将含明文 `[Cookie]` / `[Authorization]` / 账号密码的整份配置写入 `backup_config/`。
- **实测裁定**（venv 3.14.8，`import main` 后调用 `_redact_ini_secrets`）：

  ```
  === 含重复键 ===
  [Cookie]
  cookie = SECRET_TOKEN_VALUE_123      ← 明文，未脱敏
  [录制设置]
  保存文件夹是否以时间区分 = 是
  保存文件夹是否以时间区分 = 否

  === 无重复键 ===
  [Cookie]
  cookie = ***                          ← 正常脱敏
  ```

- **影响分析**：这不是假想形态——`src/config_read.py:32-36` 的注释明确记载"2026-10-17 在本仓 `config/config.ini` 的 `[录制设置]` 实测到过"重复键。即**恰恰是真实发生过的那一种配置损坏形态，会让脱敏整条链路静默失效**。产物（明文备份）按设计保留 6 份副本，且落在模块注释自己认定的"用户最容易整体打包/云同步/发给他人求助"的目录。用户以为默认（`DLR_BACKUP_KEEP_SECRETS` 未设）是脱敏备份，实际拿到明文。
- **修复建议**：改用本仓已有的容错解析器 `src.config_read.tolerant_config_parser`（`strict=False` + `interpolation=None`），或复用 `src/utils._tolerant_ini_parser()`；解析仍失败时才回退原文，但必须 `logger.warning` 明确告知"本次备份未脱敏、含明文凭据"，并考虑直接跳过备份（fail-closed）。**注**：现注释（`:360-361`、`:422`）把"宁留明文不丢备份"写为有意取舍，与本仓 `AGENTS.md`「凭据与敏感配置红线」冲突，修复时需同步更新该注释口径。

### S-03 Qt GUI 退出后事件循环永不返回，进程残留为僵尸

- **位置**：`src/gui_qt/app.py:44`（`app.setQuitOnLastWindowClosed(False)`）、`:67`（`app.exec` 调用）；`src/gui_qt/main_window.py` 的 `_finalize_quit()`
- **类型**：逻辑错误 / 资源泄漏
- **实测裁定**：在 `src/gui_qt/` 全目录 grep `\.quit\(\)`、`QApplication\.quit`、`app\.exit`、`quitOnLastWindowClosed`、`sys\.exit` → **0 命中**（`app.py:44` 的 `setQuitOnLastWindowClosed` 已单独确认存在）。
- **说明**：`app.py:44` 关闭了"最后一个窗口关闭即退出"语义（理由见 `:42-43` 注释，合理），但全仓不存在任何触发退出的调用。`_finalize_quit()` 只做了停定时器 + `tray.hide()` + `self.close()`，此后事件循环永不返回。
- **影响分析**：点"彻底退出"或托盘退出后——窗口消失、托盘图标隐藏、录制已停，但**进程仍在运行且无任何可召回的 UI**，只能从任务管理器杀掉。这是每个用户每次退出都会遇到的"退出无效"，且会连带留下未收割的 ffmpeg 子进程与未归档的日志。
- **修复建议**：`_finalize_quit()` 末尾（或在 `shutdownFinished` 槽中）调用 `QApplication.instance().quit()`；或改为在 `_finalize_quit` 内 `self.close()` 之前先 `app.setQuitOnLastWindowClosed(True)`。建议补一条离屏回归用例，断言"走完退出流程后事件循环返回"。

### S-04 派生地址安全闸在末位放行与同址复用分支被翻回"可达"

- **位置**：`src/stream_select.py:601`、`:631`（安全闸返回 `False`）；`:907-918`、`:940-949`（`last_resort` 翻回 `True`）；`:1404-1421`（record_url 同址复用分支）
- **类型**：安全 / SSRF 防线被击穿
- **说明**：`_probe_hls_segment` 因安全闸拒绝（`_is_derived_hop_allowed` 命中内网/形态不合规）时返回 `False`，但该返回值与"分片 404 不可达"**无法区分**，于是两处末位放行分支把它翻回 `True`：

  ```python
  if _probe_hls_segment(probe_client, url, headers, platform=platform):
      return True
  if last_resort:
      logger.warning(... "HLS 媒体分片不可达；已无备选源，仍交由 ffmpeg 尝试")
      return True          # ← 安全拒绝在此被翻回放行
  ```

  `select_source_url` 的 record_url 通道另有一处同型漏洞：`:1407-1421` 只要该地址本轮已探过，就**不论结论如何**照常 `_accept_source(...)` 交付（`:1412-1419` 的注释明确写了"沿用探针拒绝 ≠ ffmpeg 不可拉流的既有语义"）；抖音/TikTok/网易CC 的 `record_url = m3u8_url or flv_url` 恒成立，故该分支极易命中。
- **影响分析**：被劫持/MITM 的播放列表（虎牙/斗鱼在本仓被刻意降级为 http，MITM 现实可行）正文写 `http://127.0.0.1:6379/x.ts` 或 `169.254.169.254` 元数据地址时，该列表仍会被选中并交给 ffmpeg `-i`，ffmpeg 按正文连内网并复用平台 Cookie。同时日志已打出"流地址形态不合规，已丢弃（不交给 ffmpeg -i）"，**与实际行为相反**，排障归因反向。
- **修复建议**：安全拒绝改为抛专用内部控制流异常（照 `RedirectHopRejected` 先例，如 `_DerivedHopRejected`），在 `_validate_stream_url` 中排在 `except Exception` 之前且**不受 `last_resort` 影响**；`select_source_url` 增设 `security_rejected: set[str]`，在 `:1407` 复用分支前判定不交付。回归锁两条：① 正文含内网分片 + `last_resort=True` → `_validate_stream_url(...) is False`；② `m3u8_url == record_url` 且正文含内网分片 → `select_source_url(...) is None`。

### S-05 Web 模式空 URL 时主循环退化为零延迟忙循环

- **位置**：`main.py:5279-5283`（配合 `:5287-5294` 的 `EOFError` 分支）、`main.py:501-509`（`_interruptible_sleep`）、`web.py:337`（`main.recording_enabled = False`）
- **类型**：逻辑错误 / 资源
- **实测裁定**：`web.py:337` 确在启动时置 `main.recording_enabled = False`；`_interruptible_sleep` 的实现为

  ```python
  while _remaining > 0:
      if exit_recording or not recording_enabled:
          break        # ← 立即 break，一秒不睡
      ...
      time.sleep(1)
  ```

  空 URL 分支执行 `_interruptible_sleep(5)` 后 `continue`，**跳过循环体末尾的 `time.sleep(3)`**。
- **说明**：Web 模式下 `recording_enabled=False` 且 `URL_config.ini` 为空（面板刚启动、用户尚未填写 URL 的**默认状态**）时，`_interruptible_sleep` 立即返回，`continue` 又跳过收尾 sleep，主循环以零间隔空转。
- **影响分析**：面板启动即打满一个 CPU 核；每轮还重复执行 `_hot_reload_config()`（含 config.ini 解析与文件写回自愈）与全量读取 `URL_config.ini`，磁盘持续被读写；日志无任何异常提示，排查困难。`EOFError` 分支（`:5292-5294`）同构同样中招。
- **修复建议**：令 `_interruptible_sleep` 返回"是否被中断"（bool），被中断时调用方改用固定 `time.sleep(3)`；或把两处改为"先 `time.sleep(1)` 再判断退出"的先睡后查结构。

---

## 5. 中等问题（48 项）

### 5.1 根目录入口与推送（7 项）

**M-01 `main.py:4409`、`:4427`、`:4432`｜逻辑错误（时间戳格式与切片错配）**
「按时间分目录」用 `now[:10]` 取日期，但 `now` 现为 `strftime("%y%m%d_%H%M%S")`（13 字符，如 `251019_123456`），`now[:10]` 得到 `251019_123`——日期后面粘了小时 2 位与分钟十位。该切片明显是为旧的 `%Y-%m-%d_...` 格式写的，格式改短后未同步。影响：开启"保存文件夹是否以时间区分"时目录名形如 `251019_123`，同一天每约 10 分钟换一个目录，一天的录制被打散到上百个文件夹。修复：改为 `now[:6]` 或单独取 `strftime("%Y-%m-%d")`，并补目录名断言用例。

**M-02 `main.py:4486-4498` → `:3929-3941` → `:1147`｜安全（凭据进入进程命令行）**
`get_record_headers(platform, record_url, cookies=platform_cookie)` 把 `dy_cookie`/`hy_cookie` 等放进 `header_blob`，再作为 argv 元素传给 `subprocess.Popen`；`-http_proxy`（`:3954-3956`）同理可能携带 `user:pass@`。命令行对本机任意用户可见（`ps`/任务管理器/WMI），且不受 `utils.mask_credentials` 保护（它只覆盖日志面）。影响：登录态 Cookie 与代理口令泄露给本机其它用户/进程。修复：改用不经命令行的注入方式（本地转发代理或受限权限临时文件）；无法避免时应确保 ffmpeg 命令串永不进入日志与状态快照。

**M-03 `main.py:565-575`（`_shutdown_postprocess_executor` `:535-561`）｜错误处理 / 退出挂起**
信号处理器内做阻塞式线程池 drain：`pool.shutdown(wait=True, cancel_futures=False)`，单个转封装任务最长占 `_MAX_CONVERT_TIMEOUT`（3600s）。信号处理期间主线程被完全阻塞，`sys.exit(0)` 与其后的 ffmpeg 清理/日志归档全部推迟。影响：Ctrl+C 后程序可能"卡死"十几分钟且不响应第二次中断。修复：给 drain 加总预算，超时后转 `cancel_futures=True`；或在信号处理器里只置标志，把 drain 交给主循环/atexit。

**M-04 `gui.py:543-568` + `:636-654`｜逻辑错误（缩放口径不一致）**
等宽字体创建时用 `Fonts._cache[...] = tkfont.Font(..., size=cls._profile.mono_pt())`（含 `MONO_SCALE_FACTOR=0.9` 收敛），但换档时 `rescale_all → _resolve_size("mono_normal")` 走通用分支 `cls._profile.pt("mono")`，丢掉 0.9 系数。影响：启动时等宽区是 10pt，任意换一次缩放档（含换回原档）后变 11pt 且不回来，违背 `src/ui_scale.py:59-62` 的设计口径（等宽字宽，放大后一行可容列数骤减）。修复：`_resolve_size` 对 `parts[0] == "mono"` 直接返回 `mono_pt()`。

**M-05 `gui.py:4941-4951`（经 `:4922` 周期调用）｜逻辑错误（模态框叠加）**
`_watch_url_config` 在 `after` 链里调用 `messagebox.askyesno`；Tk 消息框是嵌套事件循环，`after` 定时器照常触发。影响：录制子进程每轮回写 `URL_config.ini` 使 mtime 持续变化，用户不点则每 3 秒再弹一个确认框层层堆叠。修复：改为非模态提示条 + "立即重载"按钮，或加"等待应答期间不再问"的去重标志。

**M-06 `gui.py:4910-4911`（另 `:4532-4533`、`:4830-4831`）｜错误处理（内层宽 except 架空留痕）**
文件已为三条周期链建立"异常留痕 + 30s 限频"口径，但 `_update_status_bar` 自身 `except Exception: pass` 吞掉全部异常。影响：控件销毁、属性缺失等持续性故障表现为"状态栏永久停在旧值"而日志零线索，使 `_warn_chain` 永不触发。修复：把这几处的 `pass` 换成 `self._warn_chain(chain_name, e)`，或收窄 `try` 范围。

**M-07 `msg_push.py:25-26`（调用点 `:93`/`:136`/`:366`/`:444`/`:503`）｜安全（SSRF / 本地文件读取）**
`opener = urllib.request.build_opener(no_proxy_handler)` 是默认 handler 集，含 `FileHandler`。五个推送渠道（钉钉/息知/Bark/ntfy/PushPlus）直接把配置里的地址交给 `opener.open()`，**无 scheme、无主机校验**，与 `scripts/douyin_live_recorder_standalone.py:228-253` 的 `_build_opener()` 只注册 http/https 的白名单做法相反。影响：推送地址来自 `config.ini`，而 Web 面板可写全部配置——可写入 `file:///…` 读取本地文件，或 `http://169.254.169.254/…` 打云元数据；ntfy 分支（`:456-458`）在响应含 `error` 键时把该值原样写进日志，文件内容可进 `logs/`。修复：仿 `_build_opener` 只注册 http/https，入口处显式校验 scheme，并对非公网 IP 字面量与内部主机复用 `_untrusted_stream_target_reason` 同族判据。

### 5.2 平台解析 `src/spider.py`（7 项）

**M-08 `src/spider.py:636-651`（同型 `:859-874`、`:1002-1021`）｜逻辑错误（坏候选注入）**
三条抖音 ORIGIN 注入路径都以 `if origin_url_list:` 作为"能注入"的依据，但非空并不代表其 `hls`/`flv` 键是非空字符串——实际形态常是 `{"sdk_params": "..."}` 或只下发单路。此时仍拼出 `"&codec="` 并以 `{**origin_m3u8, **hls_pull_url_map}` 注入清晰度映射。文件 `:852-855` 的注释明确把这类坏条目列为要消灭的形态，现有判据并未挡住。影响：ORIGIN 是原画首位候选，注入空地址后每轮先烧一次必败探针；上层若只取首选则以空地址起 ffmpeg，表现为"在播却漏录/反复重试"。修复：逐路判空后再注入，三处抽成 `_inject_origin_urls()` 复用。

**M-09 `src/spider.py:1156-1172`｜错误处理（漏接异常致归因分支死亡）**
`try` 块内主动抛出的是 `ValueError`（`:1161`、`:1165`），而 `except (AttributeError, IndexError, json.JSONDecodeError)` 不含 `ValueError`；且捕获元组里的三项实际都不可触发（`_loads_dict` 已吞 `JSONDecodeError`，下标前已有非空判据）。结果：注释承诺的"结构解析失败 → 记 `Failed to parse JSON data` 并按未开播返回"这条分支是死的。影响：页面改版/被风控时异常直穿装饰器，与"主播真未开播"在日志上完全同形。修复：改为 `except ValueError, AttributeError, IndexError`（PEP 758 无括号写法）。

**M-10 `src/spider.py:319-330`｜并发/竞态（锁外写三元组）**
`_ensure_kuaishou_did` 在 singleflight 未拿到新值的分支里，于锁外直接改写 `_cached_kuaishou_did`/`_ts`/`_proxy` 三个全局；而 `:311-318` 的注释明确要求"三元组必须整组在锁内写"，`_ensure_twitch_client_id` 的对称分支（`:374-377`）也确实持锁。影响：两个不同代理的房间并发走到该清空路径时产生"值与出口记录错配"，表现为间歇性 `200 + 空 body` 风控。修复：把 `:322-330` 整体移入 `with _kuaishou_did_lock:`。

**M-11 `src/spider.py:5864-5867`、`:6326-6329`｜逻辑错误（条件写反）**
映客与浪 Live 在"已判定开播"后仍用 `if not m3u8_url or not flv_url:` 判无源，即要求 HLS 与 FLV **同时**存在；与本文件 MID-2212 在 Look（`:4116`）、微博（`:4841`）、LiveMe（`:5177`）定下的"两路皆空才判无源"口径正好相反。影响：只下发单路的房间被判 `is_live=False`，而"未开播"轮次刻意静默 → 在播却漏录且无日志。修复：改为 `if not m3u8_url and not flv_url:`。

**M-12 `src/spider.py:3516-3528`｜逻辑错误（空地址却 is_live=True）**
千度热播用 `if len(play_url) > 0` 判定，校验的是正则匹配结果的**列表长度**而非地址串非空；页面渲染出 `"play_url": ""` 时 `len(...)>0` 成立，于是 `record_url` 为空串且 `is_live=True`。同型问题在 ShowRoom（`:5572-5579`，MIN-2215）已修，此处是漏网点。影响：返回"在播但地址为空"的壳结果，上层每轮白烧探针，且熔断统计把这轮计入解析成功样本。修复：判据改为 `play_url and play_url[0].strip()`，取不到走 `_warn_api_abnormal` + `is_live=False`。

**M-13 `src/spider.py:2857-2866`、`:2896-2899`｜逻辑错误（URL 解析边界）**
Bigo 非 `bigo.tv` 落地页分支 `room_id = web_url.split("&amp;h=")[-1]` 未校验分隔符存在——og:url 不含该串时 `room_id` 变成整条 URL 并被当作 `siteId` 提交；`url.split("/")[3]` 在 `https://host`（三段）形态抛 `IndexError`，在 `https://host/` 形态取到空串拼出 `//<room_id>`。影响：分享/第三方落地页形态的 Bigo 房间解析失败且日志无指向性线索。修复：改 `urllib.parse` 取 query 里的 `h`，补名请求改用 `_safe_extract_id` 或 path 段解析。

**M-14 `src/spider.py:2039-2078`｜错误处理（缺 MID-48 加固）**
B站 v2 取流路径在 `_loads_dict` 之后回到裸下标与裸 `itemgetter`：`stream_list[0].get(...)`、`sorted(..., key=itemgetter("current_qn"))`、`stream_data["base_url"]`（`:2070`）在字段缺失时抛 `KeyError`/`TypeError`。整条函数其余部分（`:1964-2038`）已按 MID-48 用 `_dig` 收口，这一段是缺口。影响：B站改版或降级响应触发 KeyError，被装饰器吞成"未开播"，与真未开播不可区分。修复：列表用 `_dig_list` 收口，排序键改 `lambda x: _dig(x, "current_qn") or 0`，`base_url` 用 `_dig_str`。

**M-15 `src/spider.py:6829-6850`｜错误处理（捕获过窄 + 静默）**
淘宝会话票据回写配置的 `try` 只接 `(ImportError, OSError)`；`utils.update_config`/`read_ini_value` 抛出其它类型（configparser 相关异常等）时异常穿透两轮重试循环，把已拿到 `SUCCESS` 的取流结果一起作废；失败路径只落 `logger.debug`。影响：票据无法持久化时每轮重走登录式刷新，且失败原因在常规日志级别下不可见。修复：改 `except Exception as e`（保留 `type_name`），级别提到 warning（值仍不落日志）。

### 5.3 网络层（6 项）

**M-16 `src/async_http.py:583-587`｜安全（重定向中间跳响应体完全无上限）**
`_bounded_response_read` 对 `response.has_redirect_location` 的中间跳直接 `return` 不读体；而 httpx 在钩子之后、跟随重定向前会执行无上限且自动解压的 `aread()`，并把带完整正文的 Response 存进 `history`。实测（审查组复现）：302 + gzip 正文（压缩后 203KB、解压 200MB）→ `async_req` 峰值内存 **405 MB**，最终正常返回，上限完全未生效。影响：被劫持/恶意 CDN 返回"3xx + Location + 超大 gzip 正文"即可让房间线程申请数 GB 内存 → 单进程承载 80+ 房间时进程 OOM。修复：对 3xx 跳同样按上限读取（读满即判失败），或在钩子内对该跳 `await response.aclose()` 拒绝物化正文。

**M-17 `src/async_http.py:598-603`｜安全（单块解码输出不受控）**
`response.aiter_bytes()` 未传 `chunk_size`，httpx `ByteChunker` 走 `chunk_size is None` 分支原样返回"一个原始块的全部解码输出"；实测 64KB 原始块 → 单块解码输出 64.3MB，200MB 炸弹打到最终跳时峰值 146.9MB（名义上限 32MB，约 4.6×），超限检查发生在整块物化**之后**。修复：改走 `aiter_raw(chunk_size=64KB)` + 自持 decoder 增量喂入，对每次 `decoder.decode()` 的产出也判累计上限。

**M-18 `src/sync_http.py:338`（及 `:330-331`）｜安全（代理路径无上限）**
代理分支的 `response.text` 由 requests/urllib3 自行解码 gzip/deflate/br，两道上限对它完全不生效；`redirect_url=True` 时 `Session.send` 的 `if not stream: r.content` 仍把正文全量读入内存。影响：本模块当前无生产 importer，但 `session()`（`:187`）是公开出口、面向"登录/令牌刷新类端点"，一旦接线即成压缩炸弹面。修复：代理分支改 `stream=True` + 手工分块计数；`redirect_url` 分支改用 `response.headers`/`history[-1].url`，避免物化正文。

**M-19 `src/node_install.py:157-184`（`:164-169`、`:183`）｜安全（下载完整性 fail-open）**
① 官方 `SHASUMS256.txt` 取不到即降级 TOFU；若本地 `.sha256` 基准不存在（首次安装），直接把本次实算值写成基准并 `return True`——**零校验**；② 读基准抛 `OSError` 也 `return True` 放行。影响：攻击者（或网络策略）只需丢弃该 15 秒探测请求，无需 MITM，即可让首次安装无校验地落地并执行数百 MB 的 node 二进制（随后 `:269` 把该目录前置进 `PATH`）。修复：官方不可达且无既有基准时 fail-closed（拒绝安装并提示手动安装），只保留"已有基准的重下载比对"这条降级路径；基准读取失败应拒绝而非放行。

**M-20 `src/node_install.py:277-283`（配合 `:269`）｜安全（已装目录无完整性校验）**
"目标 `node` 目录已存在"分支只跑 `subprocess.run(["node","-v"])`，returncode==0 即返回 True，不做任何哈希校验；而安装成功后 `:269` 把该目录前置进 `os.environ["PATH"]`，全进程及所有子进程后续 `node` 调用都命中它。影响：任何能在该目录写入可执行档的本地主体都能让本进程执行其代码，且无任何告警。修复：对 node 目录内可执行文件建立哈希钉定/启动复核（与 `ffmpeg_install` 同口径）。

**M-21 `src/async_http.py:543-544`｜安全（有代理时域名维度 SSRF 判定整体失效）**
`if proxy_addr and web_config._parse_ip_literal(host) is None: return None` —— 经代理出站时对**域名一律不做 DNS 判定**，只判 IP 字面量。于是 `http://metadata.google.internal/…`、`http://redis.internal/…` 在开代理时全部放行（代码已在 `:522-530` 登记为"避免误杀境外域名"的取舍）。影响：被攻陷平台在响应里写内网域名，探针会经代理访问它并把 `status_code` + `content-type` 回显进 debug 日志，构成稳定的内网端口/服务观测口。修复：补一条不依赖 DNS 的域名后缀黑名单（`.internal`、`.local`、`metadata*` 等），或做成可配置策略而非全量豁免。

### 5.4 工具、调度与基础设施（7 项）

**M-22 `src/utils.py:201-223`（阻塞段 `:218-221`）｜并发 / 挂死风险**
`run_js_async` 把整个 `execjs.call()` 阻塞段丢进 `asyncio.to_thread` 的**默认线程池**。该池线程非 daemon，且工作线程不可取消——当内层超时语义失效时（文件注释 `:205-213` 已列出两种可达形态：回退的 PyExecJS 1.5.1 根本不收 `timeout`；execjs 内部在 kill 后又调一次不带超时的 `communicate()`），工作线程永久阻塞：`asyncio.wait_for` 只让 await 侧脱身，线程不归还；`asyncio.run()` 收尾时 `shutdown_default_executor` 有 300 秒 join 超时，超时后该非 daemon 线程被弃而未被 join，解释器退出时 `_python_exit` 仍要 join 它 → **进程可能退不掉**。影响：单个 node 挂死即可让房间线程停摆 5 分钟并让整个进程退不掉。修复：改自有 `ThreadPoolExecutor` + `loop.run_in_executor(自定义池, ...)`；更彻底的是与 `run_node_script_async`（`:325-358`）同构，自管 Popen + `communicate(timeout)` + 进程树 kill。

**M-23 `src/utils.py:442-444`、`:465-467`｜错误处理（失败降级为假成功）**
`_make_trace_error_guard` 的 `ProgramError` 分支把"Node.js 环境缺失 / 签名脚本执行失败"静默降级为 `{"is_live": False}`（即"主播未开播"），且日志是一句**未过 i18n 的英文硬编码**、不含函数名、不含异常类型与内容——与紧邻的 generic 分支（`type(e).__name__` + `mask_credentials(str(e))` + `func.__name__` + 行号）口径完全不一致。影响：环境级故障被伪装成"未开播"，用户看不到 Node/签名链已坏，非中文语言下混入英文且日志无归因线索。修复：补 `type(e).__name__`/`func.__name__`/脱敏后的 `str(e)`，文案走 `i18n.tr`。

**M-24 `src/utils.py:487`｜并发 / 共享可变状态**
`trace_error_decorator` 的兜底值 `{"is_live": False}` 在装饰时**只构造一次**，被 76 处平台解析函数共用：每次异常返回的是**同一个 dict 实例**。任一调用方对返回值做写入（补 `anchor_name`、缓存派生键、`pop` 等）都会污染全局兜底，污染持续到进程结束并跨房间、跨轮次串数据。影响：潜在跨房间数据串台，属极难归因的"偶发脏数据"（当前未发现写方，属潜伏缺陷）。修复：改为每次调用新建（fallback 工厂或返回前 `dict(...)`）。

**M-25 `src/danmaku_monitor.py:455-458`（配合 `:415-442`）｜竞态 / 状态机**
`room_message` 在房间未登记时会**隐式注册**（`self._rooms[room] = self._default_state("未知")`），而 `room_stopped` 才是清理出口。`main.py:1429-1430` 先 `danmaku_collector.stop()`、再由 finally 调 `room_stopped`；`stop()` 的 `join(timeout=8)` 超时即返回，此时采集线程仍存活，随后到达的弹幕会在 `room_stopped` 弹掉条目之后**把房间重新注册回来**（下次 `room_stopped` 已不会再执行）。影响：监控页残留一个 platform="未知"、永不清理的幽灵房间（SEV-2208 所修形态的复发）。修复：`room_stopped` 落"已停止"墓碑集合，`room_message` 的隐式注册分支跳过墓碑房间；或 `stop()` 在 join 超时时不视为收尾完成。

**M-26 `src/ffmpeg_install.py:311-317`、`:370-371`（对照 `src/ffmpeg_linux_download.py:237-247`）｜安全（校验口径分叉）**
Windows 官方源在"取不到官方 `.sha256` 文档"时**无条件退回 TOFU 首信任记账并放行安装**；同一降级形态下，Linux 姊妹模块 `_verify_archive` 在 `not master_allowed` 时**明确拒装**并要求显式设 `FFMPEG_MASTER_ALLOWED=1`。影响：攻击者只需让 `<zip>.sha256` 这一个 15 秒超时的小请求失败（DNS 污染、连接重置、前置代理拦截），即可把默认唯一的 Windows 自动安装路径降级成"等同未校验安装"——首次安装正是供应链投毒最有价值的窗口，与本模块头"P-1 权威校验优先"的自述相反。修复：Windows 侧对齐 Linux 口径，两侧共用同一条 `master_allowed` 判据。

**M-27 `src/notify.py:83-88`｜安全（凭据泄露口径分叉）**
推送失败分支把**未脱敏的异常对象直接插值**进 `i18n.tr("直播消息推送到{platform}失败: {e}", ..., e=e)`，再落控制台与日志；而同一文件 `run_script` 的三处异常日志（`:233`、`:255/264`、`:274`）全部走 `utils.mask_credentials(str(e))`。影响：推送渠道的 API URL 本身即凭据载体（息知 `https://xizhi.qq.com/<key>`、Bark `https://api.day.app/<key>/...`、TG `.../bot<token>/sendMessage`），urllib/requests 异常的 `str()` 常规把完整 URL 带 path 拼进消息 → 密钥明文写进 `logs/` 并按 rotation 保留多份。修复：`e=utils.mask_credentials(str(e))`。

**M-28 `src/startup_cleanup.py:96-99`（配合 `:220`）｜错误处理 / 契约违反**
模块头 `:15-16` 把"全程不抛：任何异常都不得让录制主流程起不来"写成硬约束，但 `_read_stamp()` 只捕 `OSError`，而 `Path.read_text(encoding="utf-8")` 在基线文件被写坏/被同步工具转成非 UTF-8 时抛的是 `UnicodeDecodeError`（`ValueError` 子类）；外层 `:220` 同样只捕 `OSError`。影响：一份损坏的 `logs/.pyc_stamp` 会让"启动期外围清理"把异常抛进 `main()` 的启动路径——正是该模块明示要避免的形态（本轮 `UnicodeDecodeError` 漏接的第 3 例）。修复：改为 `except (OSError, UnicodeDecodeError)`。

### 5.5 Web 服务层（4 项）

**M-29 `src/web_config.py:1240`（调用点 `src/web_api.py:1283`、`:1346`）｜错误处理（假成功）**
`update_config_line` 执行 `_atomic_write_text(...)` 后**丢弃其布尔返回值**并 `return True`；而 `atomic_write_text` 在 `mkstemp`/`os.replace` 抛 `OSError` 时明确 `return False`（`src/utils.py:700`、`:717`）。影响：磁盘满/临时文件创建失败时 `PUT /api/config` 走成功分支返回 `{"ok": true}`；`set_language` 的回滚（`:1348-1351`）因此不触发，出现"进程已切语言、config.ini 仍是旧码"。受影响含 `web_auth_enable`/`web_password` 等安全键。修复：`return replaced and _atomic_write_text(...)`。

**M-30 `src/web_config.py:820`、`:717`（调用点 `src/web_api.py:1083`、`:1059`）｜错误处理（假成功，同型）**
`update_room_quality` 丢弃 `:820` 的整文件重写结果并返回 `True`；`write_quality_options` 既丢弃 `:717` 的 `update_or_append_config_line` 返回值，其内部亦丢弃原子写结果。影响：`PUT /api/rooms/qualities` 在 config.ini 缺失/节缺失时恒返回 `{"ok": true, "options": [...]}`；`PUT /api/rooms/quality` 返回 `changed: true` 而磁盘未变——与 `update_room`/`toggle_room` 已采用的 MIN-2243"负信号 + 重新解析裁决"口径不一致。修复：三处统一返回写结果，`web_api.py:1083` 复用 `update_room` 的同款写后校验。

**M-31 `src/web_api.py:1287-1289`｜安全（会话吊销覆盖不全）**
`_tokens.clear()` **仅在写 `web_password` 时**执行；`web_auth_enable` 目标态变化（`:1177` 分支）不清理已签发令牌。影响："关认证 → 再开认证"无法切断此前签发的 bearer（最长 7 天），而重新打开认证本应是"切断所有既有访问"的动作；泄漏令牌的有效期窗口被拉长。修复：在 `:1301` 的键清单里对 `web_auth_enable` 任一变更同样清令牌。

**M-32 `src/web_api.py:856-868`｜错误处理（伪状态）**
`list_rooms` 取 `main.running_list` 用 `except Exception: running = []`，随后把**每个房间**标为 `recording = False`。影响：任何瞬时异常（导入失败、锁竞争、属性缺失）都被降级为"全部房间未在录制"，与 `/api/status` 已采用的 `error`/`stale` 真实信号口径相反，用户据假阴性停止/重启录制。修复：捕获后返回带 `error` 字段的响应，或每房间置 `recording: None` 并记录内部异常。

### 5.6 桌面 GUI（4 项）

**M-33 `src/gui_qt/recorder.py:344-346`｜状态机 / 错误处理（停止路径单向出口）**
`_stop_worker_body` 的异常分支只做 `self._stopping = False` + 记一条 error 日志，**既不 `self._clear_process()`，也不 `self.ended.emit(session)`**；而 `_stopping` 复位后又解开 `start()` 的闸门假象——但 `_process` 仍非 None，`start()` 返回 `already_running`。影响：停止子进程过程中一旦出现异常（句柄失效等），界面**永久卡死**：两个按钮都保持禁用（`main_window.py:1075-1076` 只由 `_on_recorder_ended` 恢复），再点"开始录制"恒报 `already_running`，只能重启 GUI——叠加 S-03 后重启成本更高。修复：`except` 分支补 `_clear_process()` 与 `ended.emit(session)`，并给"停止中"加超时兜底（如 >40s 强制复位 UI 并告警）。

**M-34 `src/gui_qt/main_window.py:1068-1076`｜状态机（无自愈通道）**
`stop_recording()` 禁用 start/stop 双按钮后，唯一的恢复通道是 `_on_recorder_ended`。与 M-33 叠加构成死锁；即便 M-33 修好，也应加超时自愈，避免任何一条链断掉即永久禁用。

**M-35 `src/gui_qt/main_window.py:1095-1103`｜资源泄漏**
`open_advanced_settings()` 在"旧实例不可见"时直接 `new` 一个新 dialog 覆盖 `self._advanced_dialog`，旧实例既无 `WA_DeleteOnClose` 也无 `deleteLater()`，且 parent 是主窗口 → C++ 对象一直存活。影响：开/关 N 轮累积 N 个 QDialog + QPlainTextEdit（含整份 config 文本），内存持续增长。修复：复用单实例（关闭后再次打开走 `_load_config()` 重载），或设 `WA_DeleteOnClose` 并在 `destroyed` 里清空引用。

**M-36 `src/ui_fonts.py:29`、`src/ui_theme.py:29-31`｜依赖 / 架构**
两个模块在**模块级**导入 tkinter（`from tkinter import font as tkfont`、`import tkinter as tk`）；而 `main_window.py:40,59` 从它们导入 `load_theme_preference`、`install_font_file` 等 → **PySide6 GUI 的导入链强依赖 Tk**。影响：与"GUI 迁 PySide6 后剪除 tkinter"的打包方向直接冲突，一旦 PyInstaller 侧剪掉 tkinter，冻结版 GUI 启动即 ImportError。修复：把纯数据/持久化函数拆出不依赖 Tk，Tk 相关改为函数内延迟导入。

### 5.7 前端与自研 JS（4 项）

**M-37 `web/app.js:717`（配合 `:1305-1314`）｜竞态（第四条按需链无代次防护）**
`showView('rooms')` 执行 `loadQualityOptions().finally(loadRooms)`，而 `loadQualityOptions()` 是唯一没有 `chain.halt()/isCurrent()` 的按需拉取（另三条已按上一轮 M-18 修复）。影响：快速切走再切回产生两支并发请求，先发后到者覆盖 `qualityOptions`/`qualityBuiltin`，画质 chips、候选下拉取自过期集合，界面与 config.ini 不一致且无提示。修复：新增 `qualityChain` 或复用 `roomsChain` 的代次。

**M-38 `web/app.js:1886-1915`｜资源 / 性能**
`downloadFile` 用 `res.blob()`（`:1902`）把整个录制文件（动辄数百 MB～数 GB）读进浏览器内存，无进度反馈、fetch 未传 `signal`（`:1890`，大文件卡住时界面无反馈）；`URL.revokeObjectURL(url)` 在 `a.click()` 后同步执行（`:1912`），部分浏览器下载尚未接管 blob 时 URL 已失效。修复：改为后端支持 Range/`Content-Disposition` 的直接链接下载，或至少延后 revoke 并加超时/错误提示。

**M-39 `src/javascript/liveme.js:348`（另 `:374`、`:384`、`:388`、`:419`、`:421`）｜安全（敏感信息回显）**
`console.log` 打印的 `sKey` 由 `signParams.lm_s_id + lm_s_ts + lm_s_key` 拼成（`:345-347`），其中 `lm_s_key` 是 base64 混淆的静态签名密钥。该脚本经 execjs 在 node 子进程执行（调用点 `src/utils.py:201`），stdout 被宿主捕获，一旦调用方在失败路径打印子进程输出，密钥与整组签名入参即进日志。同时 `:421` 的 ANSI 转义与 6 处 `console.log` 使脚本可用性**依赖宿主对 stdout 的解析协议**。修复：删除全部调试 `console.log`。

**M-40 `web/index.html:3-9` + `web/app.js:752`、`:219-221`｜安全（纵深防御）**
后端为 Starlette + uvicorn 明文 HTTP（docker-compose 明确讨论 0.0.0.0 暴露场景），登录口令（`:752`）与后续每个请求的 Bearer token（`:219-221`）均明文过网；页面未声明 CSP meta。影响：一旦将来某处渲染漏掉 `esc()`，注入脚本可直接读 `sessionStorage` 里的 token 并调全部 API（CSRF 本身不适用——认证走 Authorization 头而非 Cookie）。修复：补 `Content-Security-Policy` meta（本页无内联脚本、无 eval，可上较严策略），文档强调仅限回环或启用反向代理 TLS。

### 5.8 脚本与构建（4 项）

**M-41 `build_exe.py:1996`｜逻辑错误（门禁假绿）**
`if expect_alive and not still_running and proc.returncode not in (0, None):` —— `expect_alive=True` 只在"进程非 0 退出"时才报错；进程**提前以 rc=0 退出**时同样判通过并打印"通过 ✅"。而 `smoke_cli()`（`:2002-2009`）的语义是"跑满 25s 进入监控循环"，若 CLI 因配置为空、URL 全注释而秒退 0，冒烟仍报绿。影响：三入口冒烟对"应用根本没起来"这一最严重形态完全失明，参数名与实际判据不符。修复：把"仍存活"本身作为判据，rc=0 早退单独归类为"未进入主循环"。

**M-42 `build_exe.py:1380-1405`、`:1604-1658`｜资源泄漏 / 分发污染**
下载与解包都在 `RELEASE_DIR` 内进行，清理只写在**成功路径**：`_download_nodejs` 的 `archive.unlink()`（`:1399`）与 `shutil.rmtree(extract_tmp)`（`:1400`）位于 `return True` 之前；`_download_ffmpeg` 的 `archive.unlink(missing_ok=True)`（`:1653`）同样只在成功分支。影响：失败后 `node-vX.Y.Z-*.zip`（约 30MB）、`_node_extract/` 整棵解包树、`_ffmpeg_temp.zip` 残留在 `RELEASE_DIR`；此后 `--dual` 的 `make_zip(..., "-full")`（`:2174`）会 `RELEASE_DIR.rglob("*")` 全量打包 → 本地/未开严格模式的构建会把半成品打进对外分发的 full zip。修复：清理移进 `finally`；`make_zip` 前增加"不得存在 `_*_temp.*`/`_node_extract`/`node-*.zip|tar.gz`"的实物断言。

**M-43 `scripts/smoke_test.py:211-218`（关键 `:212`）｜逻辑错误（退出码语义 + 声明落差）**
文件头 `:14-21` 声明"覆盖面扩到任意形态畸形…全部前置拒绝并退 2"，但 `_validate_check_item` 只校验 `headers`/`expect_json`/`expect_contains`（`:128-154`）；`url`/`path`/`method` 的形态完全不校验：`cast(str, check.get("url") or ...)` 后 `raw.startswith(...)` 在非 str 时抛 `AttributeError`，`main()` 只接 `(OSError, ValueError)`（`:469`）→ 崩溃栈 + rc=1，被 CI 读成"面板接口挂了"再重试一轮。修复：在 `_SHAPE_REQUIREMENTS` 增补 `url`/`path` → `str`、`method` → `str`，与既有三条同点同码退 2。

**M-44 `scripts/douyin_live_recorder_standalone.py:1896-1915`｜逻辑错误（优雅停止一级恒失效）**
上一轮 M-20 的 `b"q"` 类型问题已修（Popen 已去掉 `text=True`，见 `:1986-1999` 注释），但写 `q`（`:1899`）、`close()`（`:1908`）与 `proc.terminate()`（`:1913`）之间**没有任何等待**。影响：Windows 下 `terminate()` 即硬杀，ffmpeg 来不及处理 stdin 里的 `q`，moov 仍不落盘——正是 `:1884-1888` 注释点名要消灭的"输出文件截断成不可播放"形态，该一级在 Windows 上等于空转。修复：`close()` 后先 `proc.wait(timeout=_TERMINATE_GRACE_SECONDS)`，超时再走 `terminate() → kill()`。

### 5.9 测试有效性（4 项）

**M-45 `tests/test_main_fixes.py:377,420,428,439,454`；`test_stream_select.py:843,909,1246,1258,1271,1481`；`test_spider.py:190,209`；`test_spider_platform.py:160,170,181`；`test_spider_platforms.py:417,429`；`test_sync_http.py:340,353`（共 20 处 / 6 文件）｜状态泄漏（R1 未覆盖形态）**
`patch("<被测模块>.<stdlib>.<属性>")` 这类**深路径**替身，`mock` 的 `_get_target` 会解析出中间那个 stdlib 模块对象并把属性写在其**本体**上。已抽查确认 `test_stream_select.py:843` 为 `patch("src.stream_select.httpx.Client", cls), patch("src.stream_select.time.sleep")`。影响：替身生效窗口内全进程所有 `time.sleep`/`asyncio.sleep`/`urllib.request.urlopen` 调用方都被换成 Mock——loguru enqueue 线程、conftest 守护线程、其它并发用例的协程都会吃到假实现（`time.sleep` 变成立刻返回的 Mock 可引发忙等）。R1 的文件头注释自己承认这是缺口（"已知未覆盖面…不覆盖 ≠ 合规"），数量已从 11 涨到 20。修复：按既定范式改浅拷贝 shim（`test_cookie_cache.py:66` 的 `fake_clock` 是现成样本），并给 R1 补"中间段命中 stdlib"的判据。

**M-46 6 个测试文件全文｜空测试文件（收集 0 条，断言永不执行）**
`tests/test_bili_live_collector.py`、`test_douyin_live_collector.py`、`test_douyu_live_collector.py`、`test_huya_live_collector.py`、`test_douyu_danmaku.py`、`test_douyu_stream_url.py` 无任何 `test_` 函数。影响：R9 用 `_R9_ZERO_COLLECTION_SANCTIONED` 白名单登记了它们，门禁是绿的——但这只是把缺陷写进白名单：R9 自己在条目里写明"改造为离线收集型用例…不得长期赖在本表"。文件里的真机断言（token/WS 握手/STT 编解码/SRT 落盘）永不自动执行，可无限腐烂。修复：按 `tests/test_bilibili_danmaku.py` 的形态改造（保留 `_xxx()` 断言主体 + `main()` 手动通道，再补离线收集型 `test_xxx(tmp_path)` 入口），每改好一个从白名单删一行。

**M-47 `tests/test_node_install.py:312`、`:334`｜状态泄漏（改写 stdlib `platform` 本体）**
`monkeypatch.setattr(node_install.platform, "machine", lambda: "ARM64")` —— `node_install.platform` 就是 stdlib `platform` 模块对象，不在 R1 的 `_MUTABLE_MODULE_NAMES` 里故门禁不拦（与已按 MT-13 修成 shim 的 `test_web_tray.py:150` 同形，这两处漏改）。修复：改为替换 `node_install` 命名空间内的 `platform` 引用（shim）。

**M-48 `tests/test_regression_gates.py:479`｜安全锁条件跳过**
`test_config_sanitizer_removes_every_sensitive_value`（SEV-2213 主锁：真实凭据不得被整目录复制）在 `config/config.ini` 不存在时 `pytest.skip`。已核实该文件当前被 git 跟踪（不会触发），但一旦有人误删，这条主锁会**静默跳过而非判红**。修复：把 skip 换成 `pytest.fail`，或在文件缺失时回落到合成样本走完同一判据。

---

## 6. 轻微问题（55 项）

### 6.1 生产代码（36 项）

| 编号 | 位置 | 类型 | 说明与修复建议 |
|---|---|---|---|
| L-01 | `main.py:4858-4864` | 逻辑 | FLV 分支在 `started=False`（Popen 抛 OSError、无产物）时仍提交转码；改 `if started and _convert_if_flv:` |
| L-02 | `main.py:99`、`:153`、`:126` | 死代码 | `_validate_stream_url`、`_cleanup_single_ffmpeg_process`、`as_completed` 三处导入零引用；按 `:164-171` 的判据可摘 |
| L-03 | `main.py:234`、`:344` | 死代码 | `error_threshold` 全仓零引用；`check_path` 仅局部使用却声明为模块全局（含 `:5218` 的 `global`） |
| L-04 | `main.py:5665-5667` | 死代码 | `len(split_line) == 1` 分支不可达（上方命中逗号才 split，否则固定 2 元素） |
| L-05 | `main.py:5261-5297` | 错误处理 | 读 `URL_config.ini` 未覆盖 `UnicodeDecodeError`（`_hot_reload_config` 已覆盖）；补入元组或统一 `errors="ignore"` |
| L-06 | `main.py:4986`（待核） | 错误处理 | `subprocess.run(..., text=True)` 的解码异常未捕获；改 `errors="replace"` 并补 `except UnicodeDecodeError` |
| L-07 | `main.py:307` | 质量 | 模块级 `os.makedirs(default_path)` 与本文件"import 不应触发副作用"的自述（`:5025-5030`）相悖；移入 `main()` |
| L-08 | `main.py:1223-1232`、`:4743` | 并发 | 字幕线程登记写入 `create_var` 未持 `record_state_lock`（回收处均在锁内）；同名房间并发时条目可能永久残留 |
| L-09 | `main.py:4946` | 质量 | 注释中的行号引用（"1061 行"）已失效；改按函数名/锚点引用 |
| L-10 | `main.py:789-792` | 质量 | headers 同时传给 `httpx.Client` 与 `client.stream`；保留一处 |
| L-11 | `gui.py:2558` | 笔误 | `getattr(self, "close_dialog", None)` 实际属性名是 `_close_dialog`，该分支恒空转 |
| L-12 | `gui.py:4368-4372` | 资源 | 日志刷新链双臂排期（`_schedule_log_flush()` 后又排一条并覆盖 id）；删掉二次排期或改走 `_after_retry` |
| L-13 | `gui.py:4868-4871`（待核） | 错误处理 | 普通弹幕把空字符串当 tag 名传给 `insert`；改为有 tag 时才传（本机无 tkinter 未实测） |
| L-14 | `gui.py:5116-5131` | 安全 | 退出兜底用映像名比对收窄 PID 复用，但同名进程仍会被 `taskkill /F /T` 误杀；补启动时间戳比对 |
| L-15 | `gui.py:3685-3687` | 资源泄漏 | `open_downloads_folder` 的 Popen 不 wait（无收割）；补受保护的 `wait(timeout=2)` |
| L-16 | `src/ws_client.py:88` | 安全 | `obj.flush()` 未限长：实测峰值约 16.2 MB（标称 8 MiB 上限的约 2 倍），非无限放大但强于注释声明；改为 `obj.flush(limit - len(out) + 1)`，并更正 `:96-101` 注释中"zlib 在 C 层硬截断"的表述（该描述仅对 brotli 侧的诚实登记适用） |
| L-17 | `src/ws_client.py:465-474`、`:483-492` | 资源 | `close()`/`fail()` 不取消 `_pending` 中的发送任务也不置空 `_ws`；补 cancel + `gather(..., return_exceptions=True)` |
| L-18 | `src/ttwid.py:76`、`:91-122`、`:202-203` | 并发 | `_ttwid_lock` 自 H-2 起不再 acquire，三组模块级状态的读-改-写序列无互斥；把读写收回锁内（临界区内无 await） |
| L-19 | `src/cookie_cache.py:242-244`、`:409-415` | 质量 | 命中缓存直接返回对象引用（无 copy），调用方就地修改会污染全进程；返回 `dict(entry[0])` 或写明只读契约 |
| L-20 | `src/node_install.py:240-251` | 资源 | `requests.get(..., timeout=30)` 是单次读写超时而非总时长，`iter_content` 无墙钟/总字节上限；改 `timeout=(10, 30)` 并加总量上限 |
| L-21 | `src/node_install.py:255-263` | 安全 | 校验与解压之间 TOCTOU（重新打开同一路径）；校验通过后移到进程私有临时路径再解压，失败时一并删 `.sha256` |
| L-22 | `src/proxy.py:119-120`、`:183-189` | 边界 | 裸 IPv6 带端口（`::1:8080`）丢端口，拼出无端口的 `http://[::1:8080]`；放行前先区分末段是否为端口段 |
| L-23 | `src/http_config.py:56-63` | 可观测性 | 开启"https 录制"会静默关掉探针 TLS 校验（`stream_ssl_verify=False`）；该分支补一条 warning/debug |
| L-24 | `src/ab_sign.py:305` | 安全 | 签名随机前缀用非密码学 PRNG（`random.random()`），观测约 200 余条可恢复状态；改 `secrets.randbits()` |
| L-25 | `src/async_http.py:345-351` | 质量 | `content_encoding`/`abroad` 形参被静默忽略，与 `sync_req` 同签名语义不同；落到 `response.encoding` 或从签名移除 |
| L-26 | `src/sync_http.py:385-390` | 兼容 | 只识别 `Content-Encoding: gzip`，deflate/br/zstd 与多值不解压 → 解码异常；按 `,` 拆分或显式发 `Accept-Encoding: identity` |
| L-27 | `src/sync_http.py:416-427` | 质量 | `URLError` 分支先 warning 再 raise，外层又记一条 error；同一故障固定两条日志 |
| L-28 | `src/spider.py:1092-1096` | 性能 | TikTok 的 `await asyncio.sleep(1)` 在成功路径也白等；退避移到"确认失败"之后且最后一次跳过 |
| L-29 | `src/spider.py:2406-2409` | 安全 | 兜底 UUID 分支把完整 `buvid` 写 debug 日志，与 `:2204-2211` 声明的"唯一形态是自留前缀+长度"矛盾；统一走 `_buvid_log_form` |
| L-30 | `src/spider.py:3445` | 边界 | `url[-1]` 在空串时抛 `IndexError`；改 `url.rstrip("/") + "/"` 或先判空 |
| L-31 | `src/spider.py:4702-4707`、`:6755`、`:6976+` | 质量 | 百度/淘宝/京东手工拼 JSON 未转义；改 `json.dumps` |
| L-32 | `src/spider.py:5533` | 逻辑 | `url.split("room_id=")[-1]` 未校验分隔符也未截断 query；改用 `get_params(url, "room_id")` 并判空 |
| L-33 | `src/spider.py:540-575`、`:3202-3228`、`:3301-3320` | 质量 | 三份 m3u8 清单解析并存且行为细节不同；统一到 `get_play_url_list` |
| L-34 | `src/spider.py:5742-5816`、`:5873-5939`、`:5471-5513` | 质量 | 畅聊/音播/流星三平台同一实现逐字复制（含 `get_live_domain`）；抽公共函数 |
| L-35 | `src/spider.py:3753`、`:3603`、`:3769` | 质量 | 异常消息塞完整响应体；双参构造 `RuntimeError` 使 `str(e)` 成元组字面量 |
| L-36 | `src/stream_select.py:453-465` | 安全 | `_PRIVATE_HOST_PATTERN` 漏数字型/十六进制 IPv4 与 IPv4-mapped IPv6（`http://2130706433/`、`http://0x7f000001/`、`[::ffff:127.0.0.1]`）；补形态或复用 `web_config._host_internal_reason` |
| L-37 | `src/stream_select.py:901` | 逻辑 | `if ".m3u8" in url.lower()` 对整串做子串匹配，`https://cdn/a.flv?tag=b.m3u8` 会被误判为 HLS；改判 `urlsplit(url).path` 扩展名 |
| L-38 | `src/stream_select.py:1198-1201` | 逻辑 | `has_fallback` 在 h265 过滤与 record_url 形态闸之前计算，全部 FLV 为 h265 时 `has_fallback=True` 但实际无回退；按过滤后的 `usable` 重算 |
| L-39 | `src/stream_select.py:1263-1275`、`:1451-1459` | 错误处理 | `probe_client` 只有注解未赋初值，`_probe_client` 内的 import 若抛 `ImportError` 会在 `finally` 触发 `UnboundLocalError` 掩盖原始异常；补初值并把 `except` 扩展为 `Exception` |
| L-40 | `src/stream_select.py:835`、`:1311` | 错误处理 | `internal_stream_target_reason` 两处调用点无异常保护，畸形 host 的 `ValueError` 会穿透整轮；与 `_is_recordable_url:343-349` 同口径收口 |
| L-41 | `src/stream_select.py:143-154`、`:852` | 逻辑 | 探针侧 `get_record_headers` 传候选流地址、ffmpeg 侧传房间 URL，两端 `origin` 取值不同，违反"两端请求头完全一致"的注释；增传房间 URL |
| L-42 | `src/stream_select.py:326`/`:350` 与 `:893`（待核） | 逻辑 | 白名单允许 `rtmp`/`rtmps` 但 httpx 不支持，rtmp 候选只能靠末位放行；改显式"免探针放行 + 告警"分支 |
| L-43 | `src/stream.py:389-399` | 逻辑 | `bitrate_to_quality` 扫描序列漏 `BD30/BD20/BD8/BD4`，>4000 kbps 一律回采 OD（最高档），与注释"避免把低码率源误标成高画质"相反，且降级告警永不触发；改为按 `QUALITY_MAPPING_BIT` 升序完整档位 |
| L-44 | `src/stream.py:434-452` | 边界 | `get_quality_index` 数字分支取 `int(quality_str[0])`（"10"→1），越界回落 `keys[0]`=OD 最高档；改全量解析并钳到最低档 |
| L-45 | `src/stream.py:774-798` | 边界 | 快手分支假定 `flv_list[0]` 为 dict，裸 URL 串时走 else 分支后 `.get` 抛 `AttributeError`；加 `isinstance` 判型 |
| L-46 | `src/stream.py:606-639` | 错误处理 | TikTok `except` 漏 `AttributeError`（`json.loads` 返回非 dict 时），一条脏条目使整房判未开播；补 `AttributeError` |
| L-47 | `src/utils.py:669-725` | 资源 | `atomic_write_text` 只捕 `OSError`，`UnicodeEncodeError` 会抛出且 `*.tmp` 残留；补捕获或在 `finally` 清理 |
| L-48 | `src/utils.py:522`、`:633-634` | 死代码 | `is_valid_zip` 内重复 import `zipfile`；`read_config_value` 兼容别名零调用点（且是 F-16 要消除的混淆源） |
| L-49 | `src/room.py:16-19`、`:65-75` | 死代码 | `try: import exejs` 与 `get_xbogus` 均无生产调用点（后者仅测试断言其存在）；确认后删除或补注释说明保留理由 |
| L-50 | `src/room.py:196-198`（待核） | 逻辑 | `headers["Cookie"] = ttwid_cookie` 是覆盖而非追加，会丢调用方登录态 Cookie（当前唯一调用点不传 headers） |
| L-51 | `src/danmaku_monitor.py:457`、`:813` | i18n / 文案 | 隐式注册用硬编码"未知"未过 i18n；`resume_writes` 的异常日志复用"关闭边车文件异常"文案，语义不符 |
| L-52 | `src/recorder_status.py:182,184,197,206`、`:236-243` | i18n / 安全 | 四处 `print` 未走 `i18n.tr`；`:236-243` 异常日志的 `{e}` 未过 `mask_credentials` |
| L-53 | `src/collector.py:161` | 安全 | SRT 初始化失败日志的 `{e}` 未过码，异常文本常含完整文件路径 |
| L-54 | `src/config_io.py:428-431` | 错误处理 | 轮转段 `getmtime` 抛 `FileNotFoundError` 会让"本次副本已落盘"被判为备份失败（假失败）；轮转按尽力而为处理 |
| L-55 | `src/config_io.py:354`；`src/log_archive.py:297`；`src/__init__.py:37` | 一致性 | 三处各自手写布尔集合 `("1","true","yes")`，与唯一入口 `parse_config_bool`（`{是/true/t/yes/y/on/1}`）不一致，`on`/`t` 不被识别；改调 `parse_config_bool` |
| L-56 | `src/ffmpeg_master_download.py:410-415` | 错误处理 | 候选源探测循环不在任何 try 内，非 `RequestException` 会穿出，违反函数头"失败一律返回 False"的契约 |
| L-57 | `src/ffmpeg_install.py:484` | 逻辑 | PATH 注入用模块级常量 `ffmpeg_path` 而非 `dest_dir/ffmpeg`；当前等价但签名暴露 `dest_dir` 形参 |
| L-58 | `src/ffmpeg_proc.py:167-173`（待核） | 资源 | 三级终止只关 `proc.stdout` 未关 `proc.stderr` |
| L-59 | `src/video_postprocess.py:171`、`:268`、`:386` | 逻辑 | `segment_video` 与 `converts_m4a` 未传 `timeout`，恒用固定 600s，未同步 MIN-04 的按体积放大口径 |
| L-60 | `src/logger.py:269-274` | 死代码 | 外层 `except OSError` 不可达（内部已逐个捕获），而可能穿出的 `ValueError` 未覆盖 |
| L-61 | `src/config_read.py:74-76`（待核） | 逻辑 | 上一轮 L-17 修正不彻底：多行值里含 `:` 的续行仍被切分当独立键，触发虚假重复告警 |
| L-62 | `src/gui_qt/recorder.py:355`、`:322-326`、`:94-96` | 死代码 | `_cleanup_target_pid` 只写不读；`_shutdown_callback` 未在 `__init__` 初始化；`has_queue_data()` 无生产调用方 |
| L-63 | `src/gui_qt/main_window.py:1184-1185`、`:406`/`:562`、`:1038-1039` | 质量 | `else: _ = cancel_btn` 占位；页标题靠 `btn.text().split("  ")[-1]` 反解（译文空格数变化即错位）；`has_room_config` 的 `except OSError: return True` 是反向容错且无注释 |
| L-64 | `src/gui_qt/settings_dialog.py:120`、`:40-45`、`:50,56,75,76` | 死代码 / i18n / 类型 | 函数内重复 import os；窗口标题/按钮/提示未走 `T()+set_text` 登记；`parent: "object"` 抹掉了真实类型 |
| L-65 | `src/gui_qt/tray.py:30`、`:25-29`/`:76`；`widgets.py:130` | 资源 / 质量 | `QMenu()` 无父对象；托盘配色一次性快照不随主题更新；`StatusDot.__init__` 里 `repaint()` 无效 |
| L-66 | `src/gui_qt/main_window.py:1135-1149` | 退出路径 | `_quitting=True` 后状态链/弹幕链仍在跑，退出过程中 `_watch_url_config` 仍可能弹模态框钉住退出序列 |
| L-67 | `src/gui_qt/pages/danmaku.py:190` | 错误处理 | `total_msgs += int(...)` 无兜底，一处脏值使整轮统计静默不更新；改走 `shared.as_int` |
| L-68 | `src/ui_motion.py:213-225` | 注释与实现相反 | 类注释称"句柄登记在册，`cancel_all()` 统一撤销"，实现只 `pop`/`clear`，从不真正取消定时器；持 root 引用后改为真实取消 |
| L-69 | `web/app.js:946` vs `:912-926` | 口径不一致 | "取证失败"在表体用 `error != null \|\| stale`，顶部横幅只认 `error === 'status_unavailable'` |
| L-70 | `web/app.js:1603-1613`、`:718-719`、`:1715`、`:289`、`:2123-2124`、`:5-7` | 状态 / i18n | 保存失败明细不随切视图清除；每次点配置页无条件重拉丢弃未保存修改；值恰为 `***` 的普通项永远提交不上；`fmtTime` 硬编码 `zh-CN`；"随登录页隐去"注释无实现；头注释称导出给内联 onclick 但已改事件委托 |
| L-71 | `web/index.html:203`、`:98`；`web/motion.js:144`、`:167`；`src/javascript/x-bogus.js:9`、`:1` | i18n / 死代码 / 质量 | 复验口令按钮复用 `config.save` 键；"全部房间" option 的 `data-i18n` 首次重建后丢失；`[data-reveal]` 选择器零命中；入场动效无兜底（面板高度超过约 6.1 倍视口时 IO 阈值永不可达，内容停在 `opacity:0`）；`jsvmp` 隐式全局、`var window = null` 遮蔽全局 |
| L-72 | `src/javascript/liveme.js:317,332,376,413,422`、`:284-312`；`migu.js:143-146,235,244` | 质量 / 可观测性 | 5 处隐式全局（加 `'use strict'` 即 ReferenceError）；`hC`/`t` 死代码、"假签名"结果被覆盖；因子接口静默回退且三处 fetch 无 `signal` |
| L-73 | `src/web_api.py:256-259` vs `:699-712`、`:1193-1197`、`:1256-1257`、`:621`、`:910-912`、`:1371-1416` | 注释 / 死代码 / 资源 | 注释称全局预算"不会因单键聚合误伤"，但 per-IP 5 次锁仍生效（反代下所有人共用一个 host）；"禁止清空密码"分支不可达；`current_cfg is None` 兜底永假；`/favicon.ico` 白名单条目恒 404 且头部清单未列 `/web`；URL_config 末字节探测失败静默继续；`/api/files` 无分页与条目上限 |
| L-74 | `src/web_config.py:876` + `config_bool.py:47` | 安全（fail-open） | `web_auth_enable` 解析失败回落 `False`（无认证），且无告警；安全开关解析失败应按"保持认证开启"兜底并记 warning |

### 6.2 工具脚本（7 项）

| 编号 | 位置 | 类型 | 说明与修复建议 |
|---|---|---|---|
| L-75 | `build_exe.py:1260` | 死代码 | `shown = pinned if pinned else UNVERIFIED_PIN`——上方 `:1248` 已 `if not pinned: continue`，分支不可达 |
| L-76 | `build_exe.py:408-413`、`:424` | 安全 / 断言 | `config/` 下非白名单文件原样复制进分发 zip；`assert RELEASE_DIR.is_dir()` 在 `python -O` 下被剥离；两处改显式 `raise SystemExit(1)` |
| L-77 | `scripts/agent_hook_guard.py:73-76`、`:112` | 覆盖面 | 动词表漏 `ri`/`os.removedirs`/`Clear-*`；`_BARE_WIDE_TOKENS` 里 `"."`/`"*"` 重复 |
| L-78 | `scripts/check_annotations.py:418-431`、`:497` | 注释与实现相反 / 漏判 | 注释称"cwd 本身是家目录时不放行"但无对应分支（实际放行）；`check_equivalence` 只遍历基线，新增文件不参与判定 |
| L-79 | `scripts/check_skill_agents_consistency.py:256` | 死代码 | `total_issues` 计算后从未使用 |
| L-80 | `scripts/smoke_test.py:326`、`:396` | 输出注入 | HTML 报告把服务端响应值原样拼接；拼装前 `html.escape` |
| L-81 | `i18n.py:208`、`:241`；`scripts/run_gates.py:145,164`；`check_coverage.py:37,200`；`check_version.py:48` | 一致性 / 质量 | 目录加载用 `utf-8` 而同仓其它脚本一律 `utf-8-sig`，带 BOM 时静默降级为"无目录"；`agants_path` 拼写错误；`datetime` 重复导入；版本检测只认一种字面形态 |

### 6.3 测试代码（12 项）

| 编号 | 位置 | 类型 | 说明与修复建议 |
|---|---|---|---|
| LT-01 | 9 处：`test_huya_danmaku.py:17`、`test_huya_tars_simple_list.py:20`、`test_srt_timeline_anchor.py:23`、`test_notify.py:32`、`test_notify_script_guard.py:45`、`test_bili_e2e.py:25`、`test_bilibili_danmaku.py:31`、`test_douyu_danmaku.py:15`、`test_douyu_stream_url.py:14` | 状态泄漏 | 模块级 `sys.path.insert` 未还原，累积 9 条重复项且造成模块名遮蔽风险；删除或移入 conftest/pythonpath |
| LT-02 | `test_gui_qt_settings_dialog.py:26`、`test_gui_qt_units.py:53`、`test_gui_qt_window.py:30`、`test_regression_gui_output_chain.py:34` | 状态泄漏 | 模块级 `os.environ.setdefault("QT_QPA_PLATFORM","offscreen")` 不可还原且使判据随宿主漂移；移进 `pytest_configure` 或改 `monkeypatch.setenv` |
| LT-03 | `test_regression_wp_b_netguard.py:246` | 状态泄漏 | 改写 stdlib `urllib.request.FileHandler` 类本体；改桩 `src.sync_http` 命名空间内的 opener |
| LT-04 | `test_spider_platform.py:1325`、`:849`；`test_huya_danmaku.py:82`；`test_start_record_command_golden.py:516` | 弱断言 | 只断 `isinstance(result, dict)` / `len>0` / `reason is not None`，桩已备好却未验证实质；补内容断言 |
| LT-05 | `test_scheduler.py:57`、`:98`、`:128` | 脆弱时序 | 负向 sleep 断言可被"线程还没跑起来"满足；改为"Event 确认已进入阻塞 → 再断言未获得"的两段式 |
| LT-06 | 15 个文件（`test_regression_infra.py:669,709`、`test_gui_wrap_hints.py:82,90`、`test_frontend_quality_ui.py:210,288`、`test_danmaku_offloop.py:147,154`、`test_scheduler.py:160,173,188`、`test_log_archive.py:219`、`test_gui_qt_units.py:254,267,315,349`、`test_gui_tail_robustness.py:305,345`、`test_gui_stop_exit_singleflight.py:170,188,223,229`、`test_collector.py:271`、`test_danmaku_monitor.py:313,580,595`、`test_srt_timeline_anchor.py:118`） | 脆弱时序 | 固定 `time.sleep` 后直接断言；统一改 `_wait_until(pred, timeout=…)` 轮询（`:686` 已有该函数） |
| LT-07 | 70 处（如 `test_agent_hook_guard.py:92`、`test_async_http.py:367`、`test_stream_select.py:2111`、`test_quality_tiers.py:207`） | 冗余 | `assert X is not None` 后紧接着使用；多为类型收窄，建议改注释说明以免被误读为判据 |
| LT-08 | `test_ab_sign.py:246,276`、`test_gui_qt_units.py:190`、`test_spider.py:372`、`test_xhs_live_links.py:322` | 断言形态提示 | 自比形态 5 处，核查后均为确定性/幂等用例（合法），但其中 3 处缺少"不同输入产生不同输出"的配对用例 |
| LT-09 | `test_spider_hardening.py:198` | 覆盖面 | 基类按 `silent_body is None` 跳过会悄悄缩小平台覆盖面；统计实际跳过数量并在报告显式化 |
| LT-10 | 43 处 skip（26 命令式 + 17 `skipif`），`xfail` 0 | 登记 | 全部带环境理由、无长期挂起；仅作登记，不需处理 |
| LT-11 | `test_regression_spider.py:586`、`test_regression_utils.py:289`、`test_regression_infra.py:213` | 补丁路径 | 三处直改 stdlib 本体（`asyncio.sleep`、`msg_push.smtplib`、`os.rename`）；改 shim 浅拷贝 |
| LT-12 | `test_cookie_cache.py:248/259`、`test_async_http_lock.py:62/133`、`test_async_http.py:140`、`test_concurrency*.py` 等 | 登记 | join 未校验已根治（44 处 join 全配 `assert not t.is_alive()`，R10 门禁 + 文件内注释双保险）；仅登记确认 |

---

## 7. 与前次报告（2026-10-18）的差分复核

对上一轮报告中可机检的条目逐条复核现状（行号为当前 HEAD 位置，与旧报告可能不同）：

| 原编号 | 原问题摘要 | 现状 |
|---|---|---|
| **S-01** | Qt GUI `linesReceived` 从未 emit，录制输出断路 | **已修复**：改为 `outputReady = Signal()`，`_push()` 入队后 emit（`recorder.py:430`），`main_window._pump_recorder_queue`（`:678-694`）为生产消费方；修复方式为重构而非打补丁 |
| M-02 | `StopRecording.vbs` 双 BOM | **已修复**：实测文件头为 `fffe27002a00`（单个 UTF-16LE BOM） |
| M-03 | `sync_http` 400 分支未走上限 | **已修复**：`sync_http.py:411` 走 `_read_capped` |
| M-04 | `async_req` 响应体无上限 | **已收口**（残余见 M-16/M-17）：`_bounded_response_read` 挂在唯一客户端构造点 `_build_client:88` |
| M-05 | cookie_cache 失败日志未脱敏 | **已修复**：`cookie_cache.py:468-475` |
| M-06 / L-12 | TOFU 基准漏接 `UnicodeDecodeError` | **已修复**：`ffmpeg_master_download.py:327`、`ffmpeg_install.py:334` 均为 `except (OSError, UnicodeDecodeError)` |
| M-07 | `update_file` 未命中仍返新值 | **已修复**：新增 `matched` 标志，未命中即 `return old_str` 不落盘 |
| M-10 | `backup_file` 吞异常无返回值 | **已修复**：签名改 `-> bool`（`config_io.py:403`），`backup_file_start` 仅在 True 时推进基线 |
| M-09 | 归档窗口期关闭标准流 | **已修复**：新增 `_ConsoleBridge`（`log_archive.py:108-155`）先接管后改名 |
| M-11 | 后台线程调 `QTimer.start()` | **已修复**：改经 `logQueued` 信号，主线程槽才启表 |
| M-12 | 定时器链中弹模态框堆积 | **已修复**：守卫 + mtime 前置 + `finally` 复位 |
| M-13 / M-14 | 切语言状态回退 / i18n 登记遗漏 | **已修复**：`_repopulate_static_texts` 末段重驱 `_set_running_ui`；导航/页标题/托盘均改 `T()+set_text` |
| M-15 / M-16 | 设置对话框幽灵定时器 / 高亮器叠加 | **已修复**：`hideEvent`/`showEvent` 按可见性启停；`TerminalText._highlighter` 单实例复用 |
| M-17 / M-18 / M-19 | 前端 `data-i18n` 残留 / 按需链无代次 / 下拉无条件重建 | **已修复**（代次链第四条 `loadQualityOptions` 遗漏，见 M-37） |
| M-20 | standalone 向 TextIOWrapper 写 `b"q"` | **已修复**（不完整，见 M-44）：Popen 已去掉 `text=True` |
| M-21 / M-22 | `patch_i18n_2026_09_12.py` 无视退出码 / 硬编码旧路径 | **已消除**：该脚本已从 `scripts/` 移除 |
| L-20 / L-21 / L-22 / L-23 | web_api 白名单 `/web`、敏感节大小写、缓存失效清单、URL 逗号 | **全部已修复** |
| L-24 / L-25 | liveme 样本素材 / haixiu eval | **已修复**：实值已换 `<REDACTED>`；eval 改为直接引用常量 |
| L-26 | bilibili `_reject_auth` 裸 `ensure_future` | **已修复**：改 `spawn_danmaku_task` |
| L-29 / L-30 / L-31 | `check_runtime_pins` 崩溃栈 / `run_gates` 空格路径 / `smoke_test` 类型 | **全部已修复** |
| L-11 / L-13 / L-14 / L-15 / L-16 / L-17 | 探针上限 / 临时 zip / yum `is_RHS` / 无控制台闪窗 / logger colorize / 重复键告警 | **全部已修复**（L-17 修正不彻底，见 L-61） |
| M-01 | web.py 退出未排空后处理线程池 | **已修复**：`web.py:412` 调用 `main._shutdown_postprocess_executor()` |
| M-08 | `update_config` 用 `strict=True` | 未纳入本轮机检范围，建议单列复核 |

**差分小结**：上一轮 86 项中，可机检的 26 项里 24 项已修复，2 项部分修复（M-04 残余、M-20 不完整）。上一轮唯一严重项（S-01）已以重构方式正确修复。**本轮新增/仍存在的问题集中在"防线的一致性"而非"防线的有无"**。

---

## 8. 改进建议与修复优先级

### P0（立即修复，1-2 个工作日内）

1. **S-01** 命令守卫绕过——实测 8 条变形语料中 5 条放行；建议一次性补齐"去引号 + tail 白名单 + 动词表 + 参数分写形态"，并把变形语料固化进 `run_self_test()`。
2. **S-02** 备份脱敏 fail-open——实测复现；改容错解析器 + 失败告警（fail-closed 或显式告警），同步更新"宁留明文不丢备份"的注释口径。
3. **S-03** Qt GUI 退出后进程残留——补 `QApplication.instance().quit()`；这是每个用户每次退出都会遇到的缺陷。
4. **S-05** Web 空 URL 忙循环——`_interruptible_sleep` 返回中断标志，调用方改固定 sleep。
5. **S-04** 派生地址安全闸被末位放行翻回——引入 `_DerivedHopRejected` 内部控制流异常，并在 `select_source_url` 增设 `security_rejected` 集合。

### P1（本迭代内集中治理）

6. **内存放大面**：M-16（重定向中间跳）、M-17（单块解码输出）、L-16（`flush()` 未限长）——统一"任何一条读取路径都必须设上限"的口径，并补"上限强度"的实测判据（建议以峰值内存实测数入回归锁，而非仅断言抛错）。
7. **供应链校验**：M-19（node 首次安装零校验）、M-20（已装目录无校验却前置 PATH）、M-26（Windows TOFU 降级与 Linux 口径分叉）——三者统一到与 `ffmpeg_install` 同强度的 fail-closed 判据。
8. **写路径假成功**：M-29、M-30（config/画质写入丢弃原子写结果）——把 `_atomic_write_text` 的返回值贯通到全部返回点，与 MIN-2243 口径对齐。
9. **凭据泄露口径**：M-02（Cookie 进命令行）、M-27（推送异常未脱敏）、M-39（liveme 密钥打 stdout）、L-52/L-53（异常文本未过码）——建议新增一条全局检查：所有日志与 print 的异常插值必须过 `mask_credentials`。
10. **GUI 生命周期**：M-33、M-34、L-66——补"停止异常注入"与"退出流程后事件循环返回"两组离屏回归用例。
11. **前端一致性与资源**：M-37（第四条按需链代次）、M-38（大文件 blob）、M-40（CSP/TLS）、L-71（动效无兜底）。
12. **门禁可信度**：M-41（冒烟假绿）、M-42（残留进分发 zip）、M-43（smoke_test 形态校验）。
13. **测试有效性**：M-45（20 处深路径 stdlib 改写，数量在扩散）、M-46（6 个 0 收集文件）、M-48（安全锁条件 skip）。

### P2（后续迭代按需消化）

14. 平台解析同族缺陷：M-08/M-11/M-12/M-13/M-14/M-15——这是"修了 Look/微博/LiveMe 却漏了同型平台"的残留，建议按"判无源口径""空地址判据""`_dig` 收口"三条各做一次全平台普查。
15. 其余轻微项按模块顺手清理；优先处理带安全属性的 L-36（内网字面量缺口）、L-43（画质回采失真）、L-55（布尔口径游离）、L-74（安全开关 fail-open）。

### 机制性建议

- **把"防线声明"与"防线实现"绑定**：本轮 S-01、M-16、M-41 三处的共同点是"文件头声明的覆盖面 > 实现覆盖面"。建议对每条守卫（命令守卫、响应体上限、冒烟判据）在注释里写明"已知未覆盖形态"清单，并由一条用例反向验证该清单（即：清单里的形态必须真的被拦住/被拒绝）。
- **新增"变形语料"门禁**：`scripts/agent_hook_guard.py` 的 `run_self_test()` 应含不少于 10 条变形语料（引号、尾随空格、参数分写、别名、PowerShell 形态），否则守卫强度无法随维护迭代保持。
- **上限类修复必须附实测读数**：建议在回归锁中记录 `tracemalloc` 峰值（如"200MB 炸弹 → 峰值 ≤ 2×上限"），避免"设了上限但强度不足"被当成已修复。
- **测试卫生门禁补两条**：R1 增加"深路径中间段命中 stdlib"判据（对应 M-45）；新增"收集数为 0 的测试文件必须有已登记排期"（对应 M-46，当前白名单只能防赖着不走，不能推动改造）。

---

## 9. 总结性结论

本次审查覆盖工作空间内约 263 个自研源文件、约 13.1 万行代码（含测试），共确认问题 **108 项：严重 5 项、中等 48 项、轻微 55 项**；另剔除误报 2 项（其中 1 项降级为轻微）。

核心结论有三条：

**（1）工程基线扎实，上一轮问题已大面积收敛。** 上一轮 86 项中可机检的 26 项有 24 项已修复，唯一严重项（Qt GUI 输出断路）以重构方式正确修复。SSRF 逐跳复检、响应体上限、凭据脱敏、Zip Slip/解压炸弹防护、运行时二进制哈希钉定、Web 鉴权与同源校验等机制普遍存在且大多带回归锁，注释中愿意登记残余风险而非假装闭合——这本身是可维护性的正面信号。

**（2）当前主要风险已从"有没有防线"转为"防线在异常路径上是否还成立"。** 五条严重项中有三条（S-02、S-04、S-01）是"兜底/降级路径把安全结论翻回放行"：配置重复键让脱敏返回明文、末位放行让内网地址重新可达、命令守卫因文本形态匹配被自然书写方式绕过。共同根因是把"异常"当作"保守放行"处理，而最可能被攻击者触发的恰恰是异常路径。

**（3）声明与实现的落差是最高杠杆的治理点。** S-01、M-16、M-41、M-43 四处都是"文件头写了覆盖面、代码只覆盖一部分"，且都在最需要报警的时刻失效。建议把"已知未覆盖形态"显式写进守卫注释并用反向用例钉住，这比逐条修补更能防止同类问题回潮。

建议按第 8 节优先级推进：P0 五项均为"低成本、高确定性收益"的修复（其中 S-01/S-03/S-05 各为单点改动，S-02/S-04 需各配两条回归锁）；P1 建议按"内存上限 → 供应链校验 → 写路径返回值 → 凭据泄露口径 → GUI 生命周期 → 测试有效性"六个专项集中治理；P2 随迭代消化。修复完成后建议针对本报告所列各项补充回归测试，并将第 8 节的机制性建议固化为长期门禁。

---

*审查方式：11 个分组并行全量通读 + 关键结论二次实测裁定（venv Python 3.14.8）；审查过程只读，未改动任何代码。*
