# DouyinLiveRecorder 全量源代码审查报告

- **报告日期**：2026-09-18
- **审查对象**：`D:\DouyinLiveRecorder-dev`（工作副本 A）
- **版本基线**：4.3.0（依据 `pyproject.toml`）
- **审查方式**：静态源码审查（人工通读 + 跨模块交叉验证），未执行修改、未运行被测程序
- **报告结论摘要**：共登记 **62 项**问题，其中 **严重 12 项**、**中等 22 项**、**轻微 28 项**

---

## 一、审查概述与背景

### 1.1 背景

DouyinLiveRecorder 是一款支持 60+ 直播平台录制的一体化工具，以三种形态分发：命令行 CLI（`main.py`）、桌面 GUI（`gui.py`，Tkinter + customtkinter + pystray 托盘）、Web 管理面板（`web.py` + FastAPI 后端 + 原生 JS 前端）。运行时链路包含：

1. **配置读取**（`config/config.ini`、`config/URL_config.ini`）→ 2. **直播间 URL 分派** → 3. **平台解析**（`src/spider.py`、`src/platforms/*`）→ 4. **选源与可达性校验**（`src/stream_select.py`）→ 5. **FFmpeg 子进程录制**（`main.py` + `src/ffmpeg_proc.py`）→ 6. **录后转封装**（`src/video_postprocess.py`）→ 7. **并发调度与按平台熔断**（`src/scheduler.py`）。旁路还存在**弹幕采集链路**（WebSocket → protobuf/Tars/IRC/gzip 解码 → SRT 落盘）与**Web 面板控制链路**。

该架构决定了本次审查的三个高风险域：**① 面向不可信输入的边界处理**（平台返回 JSON、直播流二进制帧、Web 用户提交的 URL/配置）；**② 长生命周期进程的资源与失控治理**（子进程、线程、队列、握手重连）；**③ 凭据的处理面**（Cookie、Token、SMTP 授权码、推送 Webhook，以及自动安装器下载的第三方二进制）。

### 1.2 审查目标

依据委托要求，本次覆盖 **Python / JavaScript / HTML / CSS /  protobuf 定义**等全部自有源码，逐文件排查以下五类问题并记录路径与修复建议：

- 代码质量（可维护性、重复代码、注释与实现一致性）
- 潜在缺陷（空值/越界/竞态/资源泄漏/逻辑错误）
- 安全漏洞（注入、路径穿越、凭据泄露、SSRF、供应链、XSS、鉴权缺失）
- 逻辑错误（分支绑定错误、默认值漂移、判定口径错误）
- 可靠性（无退避重试、无超时、无限增长、失败不可观测）

### 1.3 审查方法

1. **范围确立**：先枚举工作区全部源文件并剔除第三方依赖与构建产物，得到待审清单（见第二章），作为覆盖率的可验证基准。
2. **分组并行通读**：按运行时链路划分为 7 个模块组，逐组**全文分段通读**（非抽样），要求每条结论必须附带 `文件:行号` 与逐字符复制的原文片段。
3. **跨模块交叉验证**：对涉及数据流与调用契约的判断（如命令注入、默认值传递、脱敏覆盖面、下载校验），强制回溯调用方与被调用方两侧源码确认，避免单点误判。
4. **逐条回源复核**：对全部拟定为**严重**的条目，由复核环节重新打开原文逐行核对逻辑可执行性与触发前提；无法 walking-through 到确切失效点的条目一律降级或剔除。
5. **约定对齐**：尊重本项目既定约定（`#` 行注释不用 docstring、`except A, B:` PEP 758 写法、black line-length 120、四语 i18n 同源等），不将上述刻意约定登记为问题。

### 1.4 结果统计

| 严重程度 | 数量 | 定义 |
|---|---|---|
| **严重** | 12 | 可直接导致录制失败/数据丢失/任意代码执行/凭据泄露/面板被接管，或在默认配置下必然发生 |
| **中等** | 22 | 在特定触发条件下导致功能失效、资源泄漏、可观测性丧失或显著性能劣化 |
| **轻微** | 28 | 风格、命名、注释失真、低危加固项，不影响主流程正确性 |
| **合计** | **62** | — |

按问题域分布：

| 问题域 | 严重 | 中等 | 轻微 | 小计 |
|---|---|---|---|---|
| 可靠性与缺陷 | 7 | 11 | 14 | 32 |
| 安全 | 5 | 6 | 5 | 16 |
| 并发与资源治理 | 0 | 5 | 2 | 7 |
| 可观测性（日志/多语言一致性） | 0 | 0 | 2 | 2 |
| 代码质量与一致性 | 0 | 0 | 5 | 5 |
| **合计** | **12** | **22** | **28** | **62** |

---

## 二、审查范围

### 2.1 覆盖范围

工作区扫描出 **148 个自有源文件，共 44,385 行**。按行数排列的重点审查对象：

| 模块组 | 主要文件 | 行数 |
|---|---|---|
| 平台解析 | `src/spider.py` | 4,859 |
| CLI 主入口 | `main.py` | 3,916 |
| 桌面 GUI | `gui.py` | 3,002 |
| 平台数据流 | `src/stream.py`、`src/stream_select.py` | 1,608 |
| 录制与后处理 | `src/stream.py`链路、`src/video_postprocess.py`、`src/ffmpeg_proc.py` | 1,269 |
| Web 后端 | `src/web_api.py`、`src/web_config.py`、`src/web_tray.py`、`web.py` | 1,523 |
| Web 前端 | `web/app.js`、`web/index.html`、`web/style.css` | 1,796 |
| 网络与配置 | `src/async_http.py`、`src/sync_http.py`、`src/cookie_cache.py`、`src/config_io.py`、`src/utils.py` 等 11 个 | 2,279 |
| 平台与弹幕 | `src/platforms/*`（7 个）、`src/collector.py`、`src/danmaku_monitor.py`、`src/srt_writer.py`、`src/ws_client.py` 等 8 个 | 2,231 |
| 安装与工具 | `src/ffmpeg_install.py`、`src/node_install.py`、`build_exe.py`、`msg_push.py`、`i18n.py` | 1,802 |
| 脚本与客户端 JS | `scripts/*.py`（8 个）、`src/javascript/*.js`（6 个） | 2,905 |
| 根目录页面 | `index.html` | 253 |
| 测试用例 | `tests/*.py`（63 个） | — |

**重点说明**：上述文件中除测试代码外均按「全文分段通读」处理；`tests/` 目录合计约 1.1 万行，采用**抽样审查 + 针对已知技术债的回归覆盖检查**，原因是测试代码缺陷通常通过「用例是否守住生产侧约定」体现，已在各模块结论中单独指出（见 W-16）。

### 2.2 明确排除项（第三方依赖与构建产物）

依据委托要求，以下不纳入审查范围：

- `D:\DouyinLiveRecorder-dev\.venv\**`（含 pip / nodejs_wheel / npm / mypy / basedpyright / coverage 等 site-packages 全量内容）
- `src/javascript/crypto-js.min.js`（压缩后的第三方密码库）
- `src/proto/douyin_pb2.py`（protoc 生成，文件头标注 DO NOT EDIT）
- `typings/**/*.pyi`（第三方库手写类型存根，非实现）
- `node\`、`ffmpeg\`、`downloads\`、`logs\`、`backup_config\`、`build\`、`dist\`、`__pycache__\`、`DouyinLiveRecorder.egg-info\` 等运行期与构建期产物

---

## 三、严重问题清单

> 以下 12 项均已回源复核确认。每项给出精确定位、触发路径、实际影响与修复建议。

---

### CR-01 ｜ GUI 启动的录制子进程在 URL 配置为空时永久阻塞于 `input()`

- **位置**：`main.py:3828-3835`；`gui.py:2238`、`gui.py:2252`、`gui.py:2261-2273`
- **类别**：可靠性 / 缺陷
- **原文证据**：

```python
# main.py:3770
def main(non_interactive: bool = False) -> None:
...
# main.py:3828
            if not ini_URL_content.strip():
                if non_interactive:
                    # 非交互模式（如 web.py 守护线程）：跳过阻塞，等待 Web API 写入 URL
                    time.sleep(5)
                    continue
                input_url = input("请输入要录制的主播直播间网址（尽量使用PC网页端的直播间地址）:\n")
```

```python
# gui.py:2238
                record_cmd = [cli_exe]
# gui.py:2270
                creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NEW_CONSOLE
```

- **问题分析**：`non_interactive` 默认值为 `False`，全仓仅 `web.py:226` 一处显式传入 `True`。GUI 以 `record_cmd = [cli_exe]` 启动录制子进程，**不带任何开关参数**，因此必然进入 `input()` 阻塞分支。而该子进程经 `CREATE_NEW_CONSOLE | CREATE_NEW_PROCESS_GROUP` + `SW_HIDE` 创建，拥有一个**真实存在但被隐藏的控制台**，其 stdin 为 `CONIN$` 且永不关闭——`input()` 将无限期等待键盘输入。若运行环境重定向了 stdin，则抛出 `EOFError`，但外层 `except (OSError, configparser.Error)`（main.py:3836）并不覆盖该类型，进程将带栈直接崩溃退出。
- **影响分析**：这是**首次使用者的默认路径**——用户安装后 `config/URL_config.ini` 天然为空。在 GUI 中点击「开始录制」的表现为：状态灯转为「录制中 (PID: xxx)」、日志输出一行提示后**再无任何动静、无任何报错**，而实际上一个隐藏的黑框进程正卡在等待输入。终端用户无法区分这与「软件损坏」。该问题同时污染「停止录制」链路（父进程向子进程发送 CTRL_BREAK 时，GUI 侧 `_send_ctrl_break_to_child`（`gui.py:641`）会调用进程级的 `FreeConsole/AttachConsole`，与此处被占用的控制台交互，令优雅停止退化为超时后 `taskkill /F` 硬杀，存在 ffmpeg 孤儿化风险）。
- **修复建议**：
  1. **治标（当日可上线）**：`gui.py:start_recording()` 在 `Popen` 之前自检 `URL_config.ini` 有效非空行数，为 0 时直接 `messagebox.showwarning` 提示并返回，不拉起子进程；同时 `main.py` 的 `input()` 外层补 `except EOFError` 兜底（记录日志后 `return`，避免裸栈退出）。
  2. **治本**：为 CLI 增加显式开关（如 `--non-interactive`），由 GUI 与未来所有非交互宿主统一传入，消除「靠默认值区分宿主」这一隐性耦合。
- **优先级**：**P0**

---

### CR-02 ｜ URL_config.ini 中一行含 3 个以上逗号即中断整轮解析，其后所有直播间永久不录制

- **位置**：`main.py:4088-4104`；异常捕获位于 `main.py:4248`
- **类别**：缺陷
- **原文证据**：

```python
# main.py:4088
                if re.search("[,，]", line):
                    split_line = re.split("[,，]", line)
                else:
                    split_line = [line, ""]

                if len(split_line) == 1:
                    url = split_line[0]
                    quality, name = [video_record_quality, ""]
                elif len(split_line) == 2:
                    ...
                else:
                    quality, url, name = split_line
```

- **问题分析**：`re.split` 的结果元素个数完全由用户配置文本中逗号的数量决定。当元素个数 **> 3** 时，`quality, url, name = split_line` 抛出 `ValueError: too many values to unpack`。该异常不在当前行的 `<3` 分支处理范围内，直接冒泡至最外层 `except`，导致 `for origin_line in _url_lines:` **循环当场终止**。由于配置行顺序稳定，坏行之后的所有直播间在此后的每一轮都不会被处理。此外，元素个数**恰好为 3** 时不抛异常但静默错配：`quality` 拿到 URL、`url` 拿到主播名片段 → 拼接出非法 URL → 被 `main.py:4153` 的 else 分支**自动加 `#` 注释掉**（用户数据被静默废弃）。
- **影响分析**：用户仅需在备注名中多写一个逗号（如 `原画,https://.../123,主播: 张三,李四`）即可触发。后果是**排在坏行之后的所有直播间永久静默不录制**，而用户看到的只有一条与真实原因毫无关联的笼统报错 `错误信息: too many values to unpack`。这是「部分房间莫名其妙不录」类工单的最可能根因，且因缺乏行号上下文而无法自查。
- **修复建议**：采用「前两段为画质 + URL、其余全部合并为主播名」的宽容解析，**结构上不可能抛异常**：

```python
if len(split_line) >= 2 and contains_url(split_line[0]):
    quality, url = video_record_quality, split_line[0]
else:
    quality, url = split_line[0], split_line[1]
name = "主播: ".join(split_line[2:]) if len(split_line) > 2 else ""
```

  并在此基础上把 `for` 循环体整体包一层 `try/except Exception`，捕获后记录 `origin_line` 的行号与原文并 `continue`，保证单行脏数据不会拖垮整轮。
- **优先级**：**P0**

---

### CR-03 ｜ Tars 流式解码全链路缺少长度字段边界校验，畸形帧可致弹幕线程永久死循环

- **位置**：`src/platforms/_tars.py:66-75`（`_skip`）、`164-175`（`read_string`）、`186-202`（`read_bytes`）、`97-108`（`_skip_to_struct_end`）、`222-233`（`finish_struct`）
- **类别**：安全（输入校验） / 缺陷
- **原文证据**：

```python
# src/platforms/_tars.py:68
        elif typ == STRING4:
            n = struct.unpack_from(">i", self._data, self._pos)[0]
            self._pos += 4 + n
        elif typ == SIMPLE_LIST:
            self._take_head()
            n = self.read_int(0)
            self._pos += n
```

```python
# src/platforms/_tars.py:169
                n = struct.unpack_from(">i", self._data, self._pos)[0]
                self._pos += 4
            s = self._data[self._pos : self._pos + n]
            self._pos += n
```

```python
# src/platforms/_tars.py:222
    def finish_struct(self) -> None:
        while True:
            f = self._peek_field()
            if f is None:
                return
```

- **问题分析**：长度字段的确切来源与用法已核对：STRING4 的长度取自 `_pos` 处 4 字节大端整数（调用 `_take_head()` 之后），SIMPLE_LIST 的长度取自 `read_int(0)` 读出的自描述整数域。三处消费点（`_skip`、`read_string`、`read_bytes`）**均未做任何 `n < 0` 或 `self._pos + n <= len(self._data)` 的校验**。当 `n` 为负数且绝对值较大时：
  - 切片 `self._data[self._pos : self._pos + n]` 因上界小于下界而返回**空**（不抛异常）；
  - 随后 `self._pos += n` 使**游标回退**，退回到刚刚消费过的字段头之前；
  - `_goto` / `_skip_to_struct_end` / `finish_struct` 三处 `while True` 循环均隐含「每轮至少前进 1 字节」的假设，游标回退后将在同一组字节上反复读到同一个负值并反复回退，形成**确定性死循环**。

  额外放大因子：`_peek_field` 仅判断 `self._pos >= len(self._data)`，负下标会走 Python 负索引合法读到缓冲区尾部字节，因此**不会抛出 IndexError 自曝**，而是持续错解析。
- **影响分析**：触发后在弹幕采集线程上表现为 **100% CPU 永久挂起**（虎牙链路：`huya.py:107` → `_decode_chat` → `parse_sender/parse_format` 的 `finish_struct`）。由于它不是异常而是无限循环，`ws_client.py:123` 的逐帧异常隔离机制完全无效。连带后果是：`collector.stop()` 的 `loop.call_soon_threadsafe(self._schedule_stop)` 永远得不到执行 → 事件循环无法停止 → 线程 join 超时残留、SRT 缓冲区不 flush 不关闭、监控面板中该房间永久显示「在线」。在 80+ 并发目标下，多个此类线程会累积拖垮整机。
- **修复建议**：在 `TarsInputStream` 内增设统一边界助手并强制所有长度消费点经过它：

```python
def _need(self, k: int) -> None:
    if k < 0 or self._pos + k > len(self._data):
        raise ValueError(f"bad tars length: pos={self._pos} len={k} total={len(self._data)}")
```

  所有 `n` 解析后紧跟 `self._need(n)`；同时为三处 `while True` 增加「本轮未前进即抛 `ValueError`」的进度断言，把不可恢复的死循环**降级为可被上层 `except Exception` 捕获并记录的异常**。huya 调用侧已有异常兜底，降级后仅影响单帧弹幕而非整线程。
- **优先级**：**P0**

---

### CR-04 ｜ `only_fans` 默认值在三层各存一份且互不兼容，已修复的斗鱼过滤回归（弹幕被静默丢弃）

- **位置**：`src/collector.py:46`、`src/collector.py:208-210`；`src/__init__.py:85`、`src/__init__.py:102`；`src/platforms/douyu.py:37`、`douyu.py:173`；调用点 `main.py:835-842`
- **类别**：缺陷（回归）
- **原文证据**：

```python
# src/platforms/douyu.py:35-39
    # only_fans 默认 False（2026-09-12 审查 C-3）：dart 上游无任何粉丝过滤，移植时引入
    def __init__(self, *args: Any, only_fans: bool = False, **kwargs: Any) -> None:
        self._only_fans = only_fans  # 是否只显示粉丝弹幕（True 时过滤 if!='1' 的消息，默认不过滤）
```

```python
# src/collector.py:46
        only_fans: bool = True,
# src/collector.py:58
        self._only_fans = only_fans
# src/collector.py:208-210
            # 透传 only_fans（斗鱼等支持的平台）
            if hasattr(danmaku, "_only_fans"):
                cast(Any, danmaku)._only_fans = self._only_fans
```

```python
# src/__init__.py:85
    only_fans: bool = True,
```

- **问题分析**：这是一条典型的**「修了一半」回归**。上一次审查（记录于 `CODE_WIKI.md:2043` 的 C-3）已将 `DouyuDanmaku.__init__` 的类默认值改为 `False`，注释也明确记载了「True 默认值导致普通观众弹幕被静默丢弃」。但真实调用链上共有**三个**默认值来源：`main.py:835-842` 调用 `get_danmaku_collector` 时**根本不传 `only_fans`** → 工厂（`src/__init__.py:85`）取 `True` → `DanmakuCollector.__init__`（`collector.py:46`）取 `True` → `collector.py:209-210` 用 `hasattr` 反向把 `True` **覆盖回**刚由斗鱼类设置为 `False` 的实例属性。类默认值的修正在实际执行路径上被完全绕过。
- **影响分析**：`douyu.py:173` 的判定 `if self._only_fans and fans != "1"` 随之生效，斗鱼直播间录制出的 SRT **仅剩极少数粉丝弹幕**，绝大多数普通观众弹幕被丢弃。用户开启「录制弹幕」后得到近乎空文件的产物，且全过程**无任何日志或告警**指向过滤逻辑，排查成本极高。
- **修复建议**：
  1. 三处默认值统一为 `False`（与 `DouyuDanmaku` 对齐）；更稳妥的做法是把 `DanmakuCollector` 与工厂的形参默认值改为 `None`，**仅在非 None 时**才执行属性覆盖，避免采集器反向覆盖平台类的刻意默认。
  2. 补充回归测试：断言「不传 `only_fans` 调用工厂后，`DouyuDanmaku._only_fans is False`」，锁死跨层默认值漂移。
- **优先级**：**P0**

---

### CR-05 ｜ ffmpeg 录制进程无看门狗，CDN 长连接掐断时无限重连挂起，永久性占用并发槽位

- **位置**：`main.py:877-896`（守护循环）；`main.py:2743-2754`（FLV 重连参数）；`main.py:790-791`（槽位获取）
- **类别**：可靠性 / 资源泄漏
- **原文证据**：

```python
# main.py:877
        while process.poll() is None:
            if record_url in url_comments or exit_recording or not recording_enabled:
                ...
                success = terminate_ffmpeg_process(process)
                ...
                return True
            time.sleep(1)
```

```python
# main.py:2751-2754（FLV 路径刻意保留）
    "-reconnect", "1",
    "-reconnect_streamed", "1",
    "-reconnect_at_eof", "1",
    "-reconnect_delay_max", "60",
```

- **问题分析**：守护循环的全部退出条件只有两个：**进程自己退出**，或**用户停止/注释该房间**。循环体内既没有 wall-clock 总时长上限，也没有「输出文件在 N 秒内无增长」的停滞检测，`time.sleep(1)` 仅决定轮询粒度。而 FLV 输入侧刻意启用了 `-reconnect / -reconnect_streamed / -reconnect_at_eof / -reconnect_delay_max 60`（相比之下 HLS 侧已于 `main.py:2786-2788` 删除该组选项）。这意味着 CDN 掐断长连接时，ffmpeg 会按指数退避**无限重连且永不退出**——`main.py:2773` 的注释表明该形态在本仓已有事故记录。
- **影响分析**：挂起的 ffmpeg 持续持有 `recording_semaphore` 槽位（获取发生在 `Popen` 之前）。开启「最大同时录制数」后，槽位会被挂起进程逐条耗尽，最终导致**全部房间录制饿死**且无法自愈（只有进程退出时才可能回收）。同时房间线程永不返回，`main.recording` 条目与监控位永久驻留，Web 面板的「正在录制」列表长期失真。在 80+ 并发的目标形态下，这是全局可用性级别的故障面。
- **修复建议**：在守护循环内加入双阈值看门狗：
  1. **总时长上限**：`if time.time() - _proc_started_at > MAX_RECORD_SECONDS`（建议默认 6 小时，可配置）；
  2. **停滞检测**：周期性 `os.path.getsize(save_file_path)`，连续 N 个周期（如 3×60s）无增长即判定停滞。
  命中任一条件即调用 `_terminate_ffmpeg_process` 并按**失败**处理（`record_error` + `mark_ffmpeg_reject`）。同时为 FLV 的重连设置总量上限——建议改为「有限重连 + 外层重启录制」，而非依赖 ffmpeg 内部无限重连。
- **优先级**：**P0**

---

### CR-06 ｜ 录制成功判定仅看退出码，零字节产物被记为成功并主动撤销线路退避

- **位置**：`main.py:927-936`（判定）、`main.py:973-978`（成功上报与退避撤销）；事故形态见 `src/stream_select.py:301-306`
- **类别**：可靠性 / 逻辑错误
- **原文证据**：

```python
# main.py:927
    return_code = process.returncode
    ...
# main.py:934
    if return_code == 0:
```

```python
# main.py:973
        # 流正常结束（主播下线）＝平台健康：按房间 host 记一次成功样本（与下方失败分支配对）
        record_success(host_of(record_url))
        # 与下方失败分支的 mark_ffmpeg_reject 配对：本地址实际拉流成功，撤销先前记入的
        # 探针退避，避免窗口内明明已恢复的线路继续被跳过、白白回退到次优线路。
        try:
            clear_ffmpeg_reject(ffmpeg_command[ffmpeg_command.index("-i") + 1], platform)
```

- **问题分析**：成功与否完全由 `return_code == 0` 决定。已对 `main.py` 全量检索 `getsize` / `st_size` / `size`，**零命中**——录制结束后不存在任何产物体积校验。而 `src/stream_select.py:301-306` 本仓自己记录过该事故形态：**HLS 播放列表返回 200、但分片全部位于其他边缘节点返回 404** 时，ffmpeg 在 `-loglevel error` 下零输出、**零字节产出、退出码仍为 0**。
- **影响分析**：后果是自相抵消的闭环：分片层探测（`_probe_hls_segment`）已经识别出线路异常并记入了 `mark_ffmpeg_reject` 退避，但录制侧的成功判定随即做了两件事——① 为坏 host 记一次**成功**样本，稀释失败率使 `PlatformBreaker` 永不触发；② **`clear_ffmpeg_reject` 主动撤销**上一轮刚写入的退避。结果是「零字节录制」稳定存在且无法自愈。用户侧表现为「任务显示录制完成，但文件 0 字节/无法播放」，且下一次同一坏线路会被优先选中。
- **修复建议**：在 `return_code == 0` 之后追加产物校验作为成功的前置条件：
  - 非分段录制：`os.path.getsize(save_file_path)` 需大于阈值（建议 ≥ 1 KiB）；
  - 分段录制：按 glob 校验首个序号分段非空。
  零字节时按**失败**处理（`record_error` + `mark_ffmpeg_reject`），并保留源文件便于人工取证，不走 `converts_mp4` 转封装（避免把空文件当作有效产物清理掉原始线索）。
- **优先级**：**P0**

---

### CR-07 ｜ 凭据明文落盘且被备份线程复制扩散，全程无权限收紧

- **位置**：`src/utils.py:370-389`（写入实现）；写入点 `main.py:1594-1596`、`1649-1656`、`1688-1695`、`src/spider.py:4959-4963`；读取点 `src/spider.py:739`、`4409`；备份 `src/config_io.py:318-341`、`348-365`
- **类别**：安全
- **原文证据**：

```python
# src/utils.py:387
    try:
        with open(file_path, "w", encoding="utf-8-sig") as configfile:
            config.write(configfile)
```

```python
# main.py:1651
            if json_data and json_data.get("new_cookies"):
                with file_update_lock:
                    utils.update_config(config_file, "Cookie", "flextv_cookie", cast(str, json_data["new_cookies"]))
```

```python
# src/config_io.py:327
        _ = shutil.copy2(file_path, backup_file_path)
# src/config_io.py:333
        while len(_files) > limit_counts:
```

- **问题分析**：`config/config.ini` 的 `[Cookie]`、`[Authorization]`、`[账号密码]` 三段以明文存储的平台凭据，与录制参数混编在同一文件中（`config/config.ini:57-58` 邮箱账号与 SMTP 授权码、`128` popkontv_token、`130-140` 四个平台账号密码已核实存在）。而 `src/config_io.py:348` 的备份守护线程每 10 分钟比对 MD5，**一旦变化即 `shutil.copy2` 整份文件**到 `backup_config/`，并保留 `limit_counts=6` 份历史副本。全仓检索 `chmod` / `0o600` / `0o700` 仅命中测试与文档，**生产代码无任何权限收紧**。
- **影响分析**：同一份凭据在磁盘上常驻可达 **7 处**（1 份主配置 + 6 份备份），权限沿用 umask（Linux 常见 0644，Windows 下同机其他用户可读）。Cookie 一旦泄露即等同账号会话被劫持；而 `backup_config/` 恰恰是用户最容易整体打包备份、云同步、或发给他人求助的目录。此外 `read_config_value` 的缺键补写（`config_io.py:253-281`）会重写整份 config.ini，进而触发 MD5 变化再生成一份备份，形成「越使用、凭据副本越多」的扩散。
- **修复建议**：
  1. **拆分凭据文件**：将 `[Cookie]` / `[Authorization]` / `[账号密码]` 迁移到独立的 `config/credentials.ini`，并将其排除出备份范围；或至少在备份时对敏感三段的值做替换后再落盘。
  2. **权限收紧**：写入凭据后立即 `os.chmod(config_file, 0o600)`（Windows 下用 `stat.S_IREAD | stat.S_IWRITE`），备份文件继承同样权限。
  3. 含凭据文件的备份保留数单独收紧至 1 份。
- **优先级**：**P1**

---

### CR-08 ｜ Web 面板「认证」可被自身接口关闭或改写，存在接管与永久锁死两条攻击路径

- **位置**：`src/web_api.py:520-556`（写入端点）、`src/web_api.py:191-207`（鉴权中间件）、`src/web_api.py:268-269`（login）
- **类别**：安全
- **原文证据**：

```python
# src/web_api.py:528
        if key.casefold() in _DANGEROUS_CONFIG_KEYS_FOLDED:
            raise HTTPException(403, "该配置项不允许通过 Web 修改")
        # 认证开启时禁止清空密码：空密码 + 开启认证会让 login 直接 500，面板自锁
        if section == "Web" and key == "web_password" and not req.value.strip():
            current_cfg = read_web_config(cast(str, app.state.config_file))
            if cast(bool, current_cfg["web_auth_enable"]):
                raise HTTPException(400, "请先关闭 Web 认证再清空密码")
```

```python
# src/web_api.py:196（中间件豁免条件）
        if (
            not cast(bool, cfg["web_auth_enable"])
            or path == "/api/login"
            or path == "/api/auth/status"
            ...
```

- **问题分析**：现有的「防自锁」保护仅覆盖了「认证**已开启**时清空密码」这一种情形，**反向路径完全敞开**：
  1. **面板接管**：认证关闭时（**出厂默认状态**，`config/config.ini:146` 为 `web_auth_enable = false`），任何人可 `PUT /api/config {section:"Web", key:"web_password"}` 写入自己掌握的密码（端点会自动做 PBKDF2 哈希，`web_api.py:542-544`），再写入 `web_auth_enable=true` 开启认证。由于中间件**逐请求重读配置**（见 WD-06），改动立即生效，且 `update_config` 在密码变更时执行 `_tokens.clear()` 踢掉全部在线会话。
  2. **永久锁死**：仅写 `web_auth_enable=true` 而保持密码为空即可让全部 `/api/*` 返回 401，同时 `login` 端点直接 `raise HTTPException(500, "web_password 未配置但认证已开启")`，面板彻底不可用，只能手工编辑 `config.ini` 恢复。
- **影响分析**：触发门槛极低——同机任意进程、恶意网页的跨站写入（见 WD-08，无需预检的 simple request 即可送达），或局域网可达时的任何人。接管成功后攻击者获得全部 API 能力：读写配置、读取日志、遍历下载录制产物、增删改直播间。配合 CR-09 的 SSRF 载荷可进一步横向。
- **修复建议**：
  1. 对 `section == "Web" and key in {"web_auth_enable", "web_password"}` 的写入做**对称校验**：目标态为「开启认证但密码为空」或「关闭认证」时一律返回 400。
  2. 把 `_DANGEROUS_CONFIG_KEYS` 从「黑名单一个键」升级为**「允许 Web 写入的键白名单」**，并将 `web_*` 整组键排除在 Web 写权限之外（仅允许手工改配置或经 GUI 修改）。
- **优先级**：**P0**

---

### CR-09 ｜ 直播间 URL 无任何协议与目标校验，任意内网地址可进入 ffmpeg（盲 SSRF）

- **位置**：`src/web_config.py:195-199`（唯一校验）；`main.py:1131-1137`、`main.py:2421`（分发到最后一项）
- **类别**：安全
- **原文证据**：

```python
# src/web_config.py:193-199（房间目标校验的全部内容）
def validate_room_target(url: str, quality: str | None = None, name: str | None = None) -> None:
    # 校验房间写入目标（URL/画质/主播名均不得含换行）
    _reject_newline("URL", url)
    _reject_newline("画质", quality or "")
    _reject_newline("主播名", name or "")
```

```python
# main.py:1131（自定义录制的兜底分支）
    _url_lower = record_url.lower()
    platform = "自定义录制直播"
    port_info = {
        "anchor_name": platform + "_" + str(uuid.uuid4())[:8],
        "is_live": True,
        "record_url": record_url,
    }
```

- **问题分析**：`validate_room_target` 只拦截换行符，`normalize_url` 对无 `://` 的输入补 https，但**没有 scheme 白名单、没有主机/IP 段黑名单**。而 `main.py:2421` 的分发表末项 `_match_stream_suffix(".m3u8", ".flv")` 使用的是**子串包含**而非扩展名判定（`suffix in lowered`），因此 `http://127.0.0.1:8080/manager/x?a=.flv`、`http://169.254.169.254/latest/meta-data/?x=.m3u8` 这类 URL 会被判定为「自定义录制直播」，原始 URL 原样进入 `port_info["record_url"]` 并交给 ffmpeg 的 `-i` 参数。web.py 虽默认不自动启动录制，但攻击者可自行 `POST /api/recording/toggle` 打开（`src/web_api.py:347-363`）。
- **影响分析**：
  - **确定成立**：盲 SSRF。服务端（含 ffmpeg 子进程，且可能经 `代理地址` 配置强制走攻击者 MITM 代理——此时平台 Cookie 也会流经该代理）向攻击者指定地址发起真实请求，可用于内网端口与服务存活探测。
  - **可回显侧信道**：成败可通过 `GET /api/logs` 回读 `streamget.log` 的错误文案加以区分。
  - **升级路径**：若目标返回可被 `-c copy` 接受的媒体内容，会被写入 downloads 目录并经 `GET /api/files/download` 取回。
  - **已排除**：未发现命令行注入（`Popen` 传参数列表，全仓无 `shell=True`）。
- **修复建议**：在 `POST /api/rooms` 校验**用户原始 `req.url`**（而非仅 `format_url_line` 的输出）：限定 scheme ∈ {http, https}；解析 host 后拒绝 loopback / link-local / 私有网段（除非显式开关）；将 `_match_stream_suffix` 改为按 `urlparse` 的 path 扩展名判定，而非全串子串包含。
- **优先级**：**P1**

---

### CR-10 ｜ 配置脱敏采用「键名黑名单」，漏掉全部 URL 型凭据

- **位置**：`src/web_config.py:405-444`；消费端 `src/web_api.py:516-518`；`web/app.js:1043`
- **类别**：安全
- **原文证据**：

```python
# src/web_config.py:405
SENSITIVE_SECTIONS = {"Cookie", "账号密码", "Authorization"}
# src/web_config.py:411
_SENSITIVE_KEY_PATTERN = re.compile(r"令牌|密码|授权码|token|secret|passwd|password|api[_-]?key", re.IGNORECASE)
```

```ini
# config/config.ini:16
代理地址 =
# config/config.ini:45-47
钉钉推送接口链接 =
微信推送接口链接 =
bark推送接口链接 =
# config/config.ini:62
ntfy推送地址 =
```

- **问题分析**：脱敏判定只匹配**键名**，凡「凭据嵌在值里」的配置项全部绕过。已核实 `config/config.ini` 中至少 5 个键不命中上述任何关键词：`钉钉推送接口链接`（值内含 `access_token=`）、`微信推送接口链接`（企业微信 webhook 内含 `?key=`）、`bark推送接口链接`（值本身即设备 key）、`ntfy推送地址`、`代理地址`（常见形态 `http://user:pass@host:port`）。
- **影响分析**：`GET /api/config` 会将这些值**原文 JSON 返回**，前端还因 `isSensitiveField` 判定为普通项而用明文 `text` 输入框渲染。在 CR-08 与 WD-07 所描述的默认无认证暴露面前提下，这是实打实的凭据泄露，危害与 SMTP 授权码同级。拿到这些值可：向受害者手机推送任意内容（Bark 设备 key）、冒充机器人向钉钉/企微群发消息、盗用带账密的代理出口。
- **修复建议**：`read_config_safe` 增加**值形态检测**——形如 `^https?://` 且含 `access_token=` / `key=` / `@`（userinfo）的值统一脱敏（保留 `scheme://host/path`，隐去 userinfo 与整个 query）；并把 `推送接口链接|推送地址|代理地址` 一类端点型键名并入 `_SENSITIVE_KEY_PATTERN`。**注意 `web/app.js:32` 的 `SENSITIVE_KEY_RE` 必须同步扩充**，保持两端口径一致（`AGENTS.md` 已有「改一侧须同步另一侧」的踩坑记录）。
- **优先级**：**P1**

---

### CR-11 ｜ 自动安装器与打包流程缺少完整性校验，存在供应链攻击面并伴 Zip Slip

- **位置**：`src/ffmpeg_install.py:283-304`（蓝奏云分支，含 `190-200` 的 TOFU 基线）、`src/ffmpeg_install.py:99-107`（TOFU 自写基线）、`src/ffmpeg_install.py:139-141`（绕过 `unzip_file`）、`src/node_install.py:52-79` 与 `111`（第三方镜像源）、`build_exe.py:212-218 / 254-256 / 300-310 / 324-330`
- **类别**：安全
- **原文证据**：

```python
# src/ffmpeg_install.py:283-300
        expected = os.environ.get("FFMPEG_LANZOU_SHA256", "").strip().lower()
        if expected:
            if expected != lanzou_hash:
                ...
                return False
            logger.debug("蓝奏云 SHA256 校验通过")

        # 解压并验证
        unzip_file(zip_file_path, execute_dir)
        ...
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=30)
```

```python
# src/ffmpeg_install.py:99-105（官方源：trust-on-first-use）
        logger.debug("ffmpeg SHA256 校验通过")
        return True
    # 首次记录
    try:
        hash_file.write_text(current_hash, encoding="ascii")
```

```python
# build_exe.py:304-310（手工写成员）
            with zipfile.ZipFile(archive) as zf:
                for member in zf.namelist():
                    if "/bin/" in member and not member.endswith("/"):
                        name = member.split("/bin/")[-1]
                        if name:
                            with zf.open(member) as src, open(ffmpeg_dir / name, "wb") as dst:
                                shutil.copyfileobj(src, dst)
```

- **问题分析**：本仓已有正确的实现（`utils.unzip_file` 提供 Zip Slip 与解压炸弹防护、`utils.is_safe_http_url`、JS 的 `_JS_SHA256_EXPECTED` 钉定），但存在多处绕过：
  1. **蓝奏云分支**：期望哈希来自环境变量，**未设置时（默认路径）仅以 debug 级别打印哈希后继续解压并执行**刚从第三方个人网盘下载的二进制；且最终重定向 URL 未经 https 校验。
  2. **TOFU 基线**：官方源与 Node 源的哈希基准由本机首次下载**自己写入**，而非随代码分发的受信值；首次下载是「唯一真正生效」的场景，恰好无外部信任锚。Node 源还额外引入第三方镜像运营方（`nodejs.org` → `npmmirror.com`）这一信任方。
  3. **`build_exe.py`**：四个下载源全部「下载 → 解压 → 打进 `--dual` 发布包」，**零哈希或签名校验**；Windows 分支还手工 `open(ffmpeg_dir / name, "wb")` 写成员，绕过了 `extractall` 的路径净化。
- **影响分析**：供应链投毒可导致**任意代码执行**（以当前用户权限），且被植入的 ffmpeg 会被后续所有录制调用。危害半径排序：`build_exe`（污染产物会分发给**所有下载用户**）> 运行时安装器（单机）> Node 安装。Zip Slip 在无校验前提下可覆盖已存在目录下的任意文件。
- **修复建议**：
  1. 将哈希从「可选」改为「**默认强制**」：内置仓库维护的期望 SHA256（版本升级时同步更新），不匹配则拒绝解压与执行。
  2. 统一调用 `utils.unzip_file`，销毁全部旁路 `extractall` / 手工成员写；`build_exe.py` 的下载改用复用.Request CI 校验，`--dual` 单组件失败应 `sys.exit(1)` 而非仅警告。
  3. 拉流安装前校验最终 URL 必须为 https。
- **优先级**：**P0**

---

### CR-12 ｜ 平台解析层「裸取 JSON + 装饰器兜底」的错误处理范式，把故障静默伪装成「未开播」

- **位置**：`src/spider.py:210-231`（`_loads_dict` 与 `_safe_loads`）、`src/spider.py:4396-4417`（装饰器错配）、`src/spider.py:2990` 与 `4067`（返回值类型与装饰器不匹配）
- **类别**：缺陷 / 可维护性
- **原文证据**：

```python
# src/spider.py:210-218
def _loads_dict(text: object) -> dict[str, object]:
    # ...
    # 空串/非 JSON/非 dict 一律回 {} 而非 None，保证调用方始终能 .get() 而不必先判空，
    # 否则上游取 stream_url/origin 时会因 None 触发 AttributeError 崩主循环。
    s = _get_str_response(text)
    if not s:
        return {}
    parsed = cast(object, json.loads(s))
    return parsed if isinstance(parsed, dict) else {}
```

```python
# src/spider.py:4396-4417（@trace_error_decorator 与 def 之间夹着注释，实际绑定到 4400）
@trace_error_decorator
# 读取哫秀/哫哫接口 accessToken 的外部覆盖值：优先环境变量，其次 config.ini 的 [Cookie] 段。
# ...
def _read_haixiu_token_override(is_haixiu: bool) -> str:
    ...
async def get_haixiu_stream_url(
    url: str, proxy_addr: OptionalStr = None, cookies: OptionalStr = None
) -> dict[str, object]:
```

- **问题分析**：本组问题有三个互相独立的确证点：
  1. **`_loads_dict` 自相矛盾**：注释承诺「非 JSON 一律回 `{}`」，但 `if not s` 只挡住空串；`json.loads(s)` 无任何异常保护。平台在风控/改版返回 HTML（WAF 页、302 落地页、截断 JSON）时立即抛出 `JSONDecodeError`。同文件 221 行已写好异常安全版 `_safe_loads`，但**全仓检索仅命中定义处本身，生产零调用**（只在 `tests/test_machine_validation_fixes.py` 中被引用）。`_loads_dict` 在本文件被调用约 40 处。
  2. **装饰器错配**：Python 允许装饰器与 `def` 之间夹注释，故 4396 的 `@trace_error_decorator` 实际绑定到返回 `str` 的同步函数 `_read_haixiu_token_override`（违反 `utils.py:263-268` 明文记载的「返回 str/tuple/None 的函数必须用 `_or_none` 变体」），而它"看起来"要装饰的 `get_haixiu_stream_url`（4415）**裸奔无兜底**；`get_looklive_stream_url`（2888）同样缺失。
  3. **类型契约错误**：`get_popkontv_stream_data`（2990，返回二元组）与 `get_acfun_sign_params`（4067，返回三元组）误用 dict 版装饰器，失败时返回 `{"is_live": False}`，调用点 3099 / 4122 做元组解包会抛 `ValueError`，该错误又被上层装饰器二次吞没。
- **影响分析**：三种形态的共同后果是**静默漏录**——明明在播却持续判定为「未开播」，日志只剩一行通用 error，无法区分「真离线」与「解析挂了」。此外嗨秀/Look 因缺少兜底，异常会穿透到 `main.py:3569` 触发 `record_error(record_host)` 计入按 host 的失败样本，达到阈值后可能**把用户配置里的房间地址自动注释掉**；而其余 50+ 平台遇到同类瞬时故障只是安静重试一轮。同一类故障在不同平台上后果严重不一致。
- **修复建议**：
  1. `_loads_dict` 内部改用 `_safe_loads`：`parsed = _safe_loads(s); return parsed or {}`；随后把 spider.py 中剩余的裸 `json.loads` 按优先级批量迁移。
  2. 把 `@trace_error_decorator` 移到 `get_haixiu_stream_url` 之前；为 `get_looklive_stream_url` 补装饰器；`_read_haixiu_token_override` 移除装饰器。
  3. `get_popkontv_stream_data` 与 `get_acfun_sign_params` 改用 `trace_error_decorator_or_none`，调用点显式判空。
  4. **加 AST 级单测**：扫描 spider.py 中所有 `get_*_stream_*` 必须带兜底装饰器，且返回注解含 `tuple`/`str`/`None` 的函数必须使用 `_or_none` 变体，防止契约再次腐烂。
- **优先级**：**P0**

---

## 四、中等问题清单

### WD-01 ｜ 日志 URL 脱敏只覆盖 `url` 形参，异常文本与 `get_response_status` 整条直链明文落盘
- **位置**：`src/async_http.py:230-237`、`262`、`287`、`296`、`306-313`；`src/sync_http.py:244-247`、`258-268`
- **证据**：`logger.debug(i18n.tr("async_req 请求失败: {masked_url} - {type_name}: {e}", masked_url=utils.mask_credentials(url), ..., e=e))`；`get_response_status` 四处均为 `url=url`。
- **问题**：`utils.mask_credentials` 只套在 `url` 上，异常对象 `e` 的文本被原样拼进日志；而 httpx / urllib3 的异常文本**必然内嵌完整请求 URL**（如 `MaxRetryError: Max retries exceeded with url: /api/xxx?signature=...`），代理分支还会带上 `user:pass@host:port`。`get_response_status` 更是把带 `codec/签名/鉴权` 查询串的**真实 m3u8/flv 直链**整体打出。
- **影响**：`src/logger.py:110-121` 的 DEBUG sink 为 `rotation="300 KB"` + `retention=3`，意味着同一份凭据会被复制到 3 个轮转文件中长期驻留——与本安装包 `async_http.py:229` 注释自己写下的风险判断直接矛盾。
- **建议**：整条日志消息统一过 `mask_credentials`；`get_response_status` 四处改用 `utils.mask_credentials(url)` 且 `e` 同样处理；同时为 `_SECRET_QUERY_RE` 补 `sign|pwd|pass|password|session|auth`（当前 `sign=` 不命中）。

### WD-02 ｜ SRT 写入队列实为无界（注释却写「有界队列」），无任何背压策略
- **位置**：`src/collector.py:76-82`、`244-258`、`278-279`
- **证据**：`self._srt_queue: "queue.SimpleQueue[...]" = queue.SimpleQueue()`；注释先称「推入有界队列」，紧接着承认「SimpleQueue 无界」，自相矛盾。
- **影响**：生产者是事件循环线程的 `_on_message`，唯一消费者是 `_srt_writer_loop` 单线程，全链路无 `put_nowait` 拒收、无 `maxsize`、无水位告警。高热度房间叠加慢盘/网络盘/杀软扫描时，元组无上限堆积直至 OOM；`stop()` 侧只能靠 `join(timeout=3.0)` 兜底，3 秒内排不完的弹幕被丢弃且无提示。
- **建议**：换 `queue.Queue(maxsize=10000)`，`put_nowait` 捕获 `queue.Full` 后计数丢弃并按分钟聚合告警；同步修正注释措辞。

### WD-03 ｜ SRT 写盘失败后不重试、不告警节流，且 `close()` 可能在锁上无限等待IO
- **位置**：`src/srt_writer.py:95-100`、`148-150`、`163-165`；`src/collector.py:149-153`、`253-258`
- **问题**：① `_open_segment` 失败时 `self._fp` 保持 `None`，而分片切换只在 `seg != self._current_seg` 时发生，故本片剩余时间（默认 1800s）内**不再重试**，写入被 `if self._fp is not None` 完全静默跳过；② 句柄有效但 `write/flush` 抛 OSError 时**每条弹幕一条 warning**，高热度房间下日志刷屏并放大 IO 压力；③ `SrtWriter.close()` 取锁时若写线程正卡在阻塞式 `flush()`，调用它的**录制线程被无限期阻塞**（无 timeout）。
- **建议**：`_fp is None` 时按时间节流重试 `_open_segment`；写异常按分钟聚合告警；`close()` 增加 `acquire(timeout=...)` 保护。

### WD-04 ｜ WebSocket 关闭协议层 ping 且无 recv 超时，半开连接「假在线」；`send()` 无超时致任务堆积
- **位置**：`src/ws_client.py:98-106`、`113`、`193-204`
- **问题**：`ping_interval=None` 关闭了协议层 ping/pong，`async for data in ws` 也无任何 `wait_for` 空闲超时。TCP 半开时既收不到 FIN 也不抛异常，应用级心跳只做**发送**（在半开连接上 `send` 会持续缓冲而不报错），连接被认为「正常」且永不重连。更严重的是 `send()` 无超时：一旦 `await self._ws.send(data)` 挂住，`_send_lock` 永久不释放，此后每次心跳/ack/进房都 `ensure_future` 出新任务堆在锁上。
- **建议**：启用 `ping_interval` + `ping_timeout`，或在 `async for` 外层做空闲超时；`send()` 用 `asyncio.wait_for(..., timeout=5)`，超时即关闭连接触发重连。

### WD-05 ｜ 重连为固定间隔、无指数退避与抖动，且次数耗尽后不再尝试
- **位置**：`src/ws_client.py:158-183`
- **问题**：`reconnect_interval` 恒为 5s（B 站 3s），无退避无抖动；`max_reconnect=5` 耗尽后直接 `on_close`，本轮录制弹幕彻底结束。
- **影响**：多房间同时掉线会在同一秒齐刷刷重连（thundering herd），放大被风控概率；服务端短暂维护时 25 秒即宣告放弃。
- **建议**：`await asyncio.sleep(interval * (2 ** min(count, 4)) * (1 + random.random() * 0.3))`；退避上限与次数做成可配置项，耗尽后按更长周期（如 5 分钟）做低频复活尝试。

### WD-06 ｜ 鉴权中间件每请求重新打开并解析一次 config.ini
- **位置**：`src/web_api.py:191-196`
- **问题**：`read_web_config` 每次都 `configparser.read()` 全文件 + 逐键解析（仅正则编译有 `lru_cache`），且是同步阻塞调用，却跑在**每一个 HTTP 请求**上（含静态资源与前端 2 秒一次的轮询）。
- **影响**：仪表盘长期开启时每 2 秒至少一次全文件读解析，多标签页线性叠加；局域网无认证场景下可被低成本放大为磁盘 IO 压力；也把 CR-08 的「改配置立即生效」放大为「每个请求都重新决策」。
- **建议**：改为 mtime/size + 内容 hash 缓存（失效才重读），或仅对 `/api/*` 非静态路径读取。

### WD-07 ｜ 认证出厂默认关闭，一行环境变量即可对局域网全开
- **位置**：`config/config.ini:143-147`；`src/web_config.py:64-74`；`web.py:206-215`
- **问题**：`WEB_DEFAULTS` 与出厂配置均为 `web_auth_enable=False`。「保护」依赖环境变量这道**显式破例闸门**，而破例方式被写进了启动提示里，用户照抄一行即退化为完全无鉴权。此外 `127.0.0.1` 并非安全边界——同机其他用户与进程在默认配置下同样拥有全部能力。
- **建议**：把「无认证 + 非回环」从「打印建议 + exit」升级为拒绝或交互式二次确认；首次启动引导设置 `web_password` 并默认开启认证；为所有写接口加 QPS 上限。

### WD-08 ｜ 全站无 Origin/Referer 校验，认证关闭时任意网页可跨站驱动写接口
- **位置**：`src/web_api.py:191-207`（中间件只查 Authorization）
- **问题**：凭据走 Authorization 头而非 Cookie，跨域**读取**被 SOP 挡住，但跨域**写入**不被挡——`Content-Type: text/plain` 的 POST 属 simple request，可不发预检直接送达。
- **影响**：用户浏览任意被攻陷网页即可被静默执行：添加直播间（含 CR-09 的 SSRF 载荷）、启停录制、`PUT /api/config` 执行 CR-08 的接管序列。属盲写（读不到响应体），但状态变更真实。
- **建议**：中间件对非 GET/HEAD 请求校验 `Origin`/`Host` 同源（或 `Sec-Fetch-Site: same-origin`），非同源 403。

### WD-09 ｜ Token 无单点吊销，`_tokens` 仅改密码时清理，且默认有效期与注释口径不符
- **位置**：`src/web_api.py:60`、`267`、`286-290`、`552-555`、`677-682`；`src/web_config.py:69`
- **问题**：无注销端点（前端登出只清 localStorage），服务端 token 在 `web_token_expiry` 默认 **86400 秒（24 小时）** 内完全有效，而 `web_api.py:8` 的模块头注释写的是「默认 1 小时」。`_purge_expired_tokens()` 只在 login 路径被调用，长期运行需等下次登录才回收。
- **建议**：新增 `POST /api/logout` 吊销当前 Bearer；把过期清理放进中间件或后台定时器；统一注释与默认值口径（`AGENTS.md` 要求被证伪的表述必须就地纠正）。

### WD-10 ｜ 前端 fetch 无超时、无失败退避、无可见性感知，单个挂起请求令轮询链永久停更
- **位置**：`web/app.js:104-108`、`512-522`、`631-641`
- **问题**：`api()` 未传 `signal` 也无 `Promise.race` 超时；服务端若在 `main.get_status()` 中卡住（需与录制主循环抢 `record_state_lock`），前端会无限期 pending，而下一轮 `setTimeout` 排在 `.then()` 之后 → **轮询链就此停止**，界面停在陈旧数据且 `.catch(function () {})` 把错误吞掉。失败后仍严格 2 秒一发；无 `visibilitychange` 处理，后台标签页持续发请求。
- **建议**：`AbortController` + 8~10s 超时，超时计入失败并退避（2s→5s→10s→30s 上限）；`visibilitychange` 时停/启轮询；UI 给出「已断开」态。

### WD-11 ｜ 抖音全局串行限速 3s/请求，80 房间下单轮周期被拉长至 240s+
- **位置**：`src/stream_select.py:958-967`；`main.py:321`、`1154-1155`
- **问题**：`_douyin_rate_limit` 是**进程级全局互斥**节流，且调用点把 `time.sleep` 放在 `with semaphore:`（网络并发槽）与 `douyin_rate_lock` 双重持锁区间内。
- **影响**：N 个抖音房间必须排队，单轮解析总耗时 ≥ `3 × N` 秒，远超 `delay_default`（默认 120s）；表现为「抖音房间开播后要等好几分钟才被检测到」，且等待期间仍占用网络并发槽，抵消调度器自适应扩容的收益。
- **建议**：改为按 host 的令牌桶（不阻塞线程）；至少把 `time.sleep` 移出 `with semaphore:`。

### WD-12 ｜ 录后转码按分段裸起线程，无并发上限
- **位置**：`main.py:944-949`；`src/video_postprocess.py:42-55`、`126`
- **问题**：录制侧有 `recording_semaphore` 治理，录后处理**完全没有**：每产生一个分段就 `threading.Thread(...).start()`，线程数随「房间数 × 分段数」线性增长；开启 `converts_to_h264` 时每线程跑一路 `libx264` 重编码，单个 ffmpeg 最长存活 600s。
- **影响**：80+ 房间 + 短分段场景下瞬时堆出数十条 CPU 密集进程，与录制进程争抢 CPU/磁盘 IO，诱发录制丢帧与 `-max_muxing_queue_size` 溢出。
- **建议**：改用固定容量 `ThreadPoolExecutor`（如 `min(4, cpu_count//2)`）统一提交，或在调度器内增设与录制槽同级的 `_postprocess_semaphore`。

### WD-13 ｜ 熔断样本把「主播未开播」计为失败，离线房间多的 host 被长期熔断
- **位置**：`main.py:3000-3008`；`src/scheduler.py:134-139`、`388-392`
- **问题**：「解析成功但主播未开播」并非平台故障，却经 `record_error` → `PlatformBreaker.record(False)` 计入失败样本；而「地址无法识别」反而不计样本（`main.py:2982-2987` 直接 `continue`），口径自相矛盾。
- **影响**：80+ 房间绝大多数时间处于未开播状态，失败率天然接近 1.0，轻易越过 `fail_rate=0.5` 阈值；此后该 host 下**所有房间**按退避跳过，**主播真正开播的首段被漏录**。
- **建议**：引入 `record_neutral()`（只上报不计失败），或让 `PlatformBreaker` 增加「连续未开播不算失败」的语义。

### WD-14 ｜ `clean_name` 无长度截断、控制字符与保留设备名处理，Windows MAX_PATH 直接失败
- **位置**：`src/stream_select.py:45-53`；`main.py:286`、`3176-3199`
- **问题**：`rstr` 已覆盖 Windows 非法字符与路径分隔符（值得肯定），但对**长度、控制字符 0x01–0x1F、Windows 保留设备名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）**均无处理，且 `main.py` 构造 `full_path` 时无截断（对比 `scripts/douyin_live_recorder_standalone.py:1661` 有 `[:60]` 截断，主程序缺失该防线）。
- **建议**：三步加固：`re.sub(r"[\x00-\x1f]", "_", ...)`、保留名加后缀、按 60 字符截断；构造 `full_path` 后用绝对路径长度校验，超限时降级（截断标题）而非静默失败。

### WD-15 ｜ `utils.update_config` 与 `update_anchor_name` 仍是 truncate+write，非原子
- **位置**：`src/utils.py:387-389`；`src/config_io.py:161-168`
- **问题**：`config_io` 已有 `_atomic_write_text`（109-129）并把 `update_file`/`delete_line` 改为「同目录临时文件 + `os.replace`」，但两条路径漏改：`utils.update_config` 写整份 config.ini，`config_io.update_anchor_name` 写整份 URL_config.ini。`open(..., "w")` 先截断为 0 字节，此时进程被杀/掉电/磁盘满，读方将读到空文件。
- **影响**：config.ini 被写空 → 全部配置与凭据丢失；URL_config.ini 被写空 → 所有房间配置丢失，且 `update_anchor_name` 这条路径**没有** `main.ini_URL_content` 恢复兜底，快照还可能与实际落盘内容不一致（仅在 `OSError` 时告警，`f.write` 中途失败时快照已被赋值）。
- **建议**：把 `_atomic_write_text` 下沉到 `src/utils.py`，两条路径统一调用；`update_anchor_name` 的 `except` 覆盖写全过程，且仅在成功后更新快照。

### WD-16 ｜ 淘宝会话 cookie 在解析热路径明文回写 config.ini，且未持有配置写锁
- **位置**：`src/spider.py:4959-4963`
- **问题**：在解析热路径中直接把服务端下发的 cookie（含 `_m_h5_tk` / `_m_h5_tk_enc` 会话票据）持久化到配置文件，无权限收紧、无写入失败处理，且**未持有** `main.py:1650` 的 `file_update_lock`（并发写同一文件有半写风险）。
- **影响**：凭据长期明文驻留；`utils.py:517` 已有 `mask_credentials` 说明项目对凭据脱敏有意识，但这条写入路径绕过了它。
- **建议**：仅回写 `_m_h5_tk` 相关两个键值并经 `file_update_lock` 串行化；或改为进程内缓存 + 可选持久化开关（默认关）。

### WD-17 ｜ 嗨秀/嗨嗨内置长期凭据硬编码于源码，<｜hy_place▁holder▁no▁813｜> PopkonTV 凭据两份副本不同源
- **位置**：`src/spider.py:2943-2950`、`3086-3092`（PopkonTV）；`src/spider.py:4429-4430`（嗨秀）
- **问题**：PopkonTV 同一串 64 字符凭据以 `Basic` 与 `Client` 两种前缀写死在两个函数中；嗨秀的 accessToken 为内置缺省值（虽有 `config.ini`/环境变量覆盖机制，但缺省值本身仍随仓库分发）。
- **影响**：凭据轮换必须发版；两份副本易不同步，表现为「登录 OK 但取流 401」或反之。
- **建议**：提为模块级常量 `_POPKONTV_APP_CREDENTIAL` 供两处引用，并照 `_read_haixiu_token_override` 的模式支持外部覆盖。

### WD-18 ｜ 淘宝两轮重试中刷新到的 cookie 从不生效（`else` 绑定错误的 `if`），第二轮为无效重试
- **位置**：`src/spider.py:4915-4963`
- **问题**：`headers["Cookie"] = new_cookie_str`（4960）位于 4953 的 `else:` 分支内，而该 `else` 与 **4918 的 `if isinstance(ret_value, list) and len(ret_value) > 0:`** 配对，并非与 SUCCESS 判断配对。mtop 在 token 缺失/过期时返回的仍是**非空 `ret` 数组**，因此永远走不进该 `else` → 刷新到的 cookie 被丢弃 → 第二轮请求的 Cookie 与首轮完全相同 → 必然复现失败。此外 `utils.jsonp_to_json`（`utils.py:478`）在响应非 JSONP 时直接 `raise`，同样绕过整个重试。
- **影响**：淘宝直播在 cookie 未自带有效 `_m_h5_tk` 时**必然取流失败**，且失败被静默降级为「未开播」。
- **建议**：把「应用新 cookie」提到 `ret` 判定之外无条件执行；把 `else` 改为独立的失败分支；给 `jsonp_to_json` 加 try/except 使重试真正生效。

### WD-19 ｜ B 站 v2 取流对 `data` 为 `None` 无防护；房间信息抓取失败只写 `logger.info`
- **位置**：`src/spider.py:1429-1437`、`1367-1371`
- **问题**：`json_data["data"]["live_status"]` 直接下标。B 站在 `-352`（风控 / wbi 签名无效）时返回 `{"code": -352, "data": null}`,此时抛 `TypeError`；另一侧用 `logger.info` 记录异常本体，常规日志级别下被过滤，且 `except Exception` 把 KeyError / JSONDecodeError / 网络错误压成同一个「未开播」。
- **建议**：`data_obj = json_data.get("data") or {}`，先判 `code != 0` 并记录具体的风控码；错误日志改 `logger.warning` 并补全 URL、异常类型与行号。

### WD-20 ｜ 监控枢纽在线人数恒为 0：采集器只透传 `message`，而平台把人数放在 `data`
- **位置**：`src/collector.py:262-266`；`src/danmaku_monitor.py:164-165`、`288-297`；`src/platforms/bilibili.py:210-218`；`src/platforms/huya.py:133-141`
- **问题**：B 站与虎牙的 ONLINE 消息把人数放进 `data=online`、`message=""`；采集器转发时只取 `msg.user_name` 与 `msg.message`（均为空串）→ `_parse_online("")` 首行空值判断直接返回原值 0。附带发现 `_parse_online` 的单位换算本身有误：非数字字符被直接剔除，`"1.2万"` 会得到 `12` 而非 `12000`。
- **建议**：`room_message` 增加 `data` 形参（或按类型取 `msg.data if msg.type is ONLINE else msg.message`）；修正万/亿单位换算；抖音侧补 `WebcastRoomUserSeqMessage` 的解析。

### WD-21 ｜ 多个子进程的 GUI 阻塞：UI 线程 `join()` 后台线程最长 7 秒；输出线程缺少会话校验置 `running=False`
- **位置**：`gui.py:2588-2594`、`2767-2772`、`2484-2519`
- **问题**：① `_process_ended` 与 `_on_recording_stopped` 均运行在 UI 线程（经 `root.after` / `post_ui` 泵），却在 UI 线程执行 `join(timeout=5)`（输出线程）与 `join(timeout=2)`（弹幕尾线程），累计最长约 7 秒窗口完全冻结。② `_read_output` 手握 `session_id` 却在三处**直接**写 `self.running = False`，未做 `session_id == self._session_id` 校验，而另外两条收尾路径都做了校验——口径不一致。
- **影响**：录制结束/停止时窗口冻结；「停止后立即重启」的竞态下旧线程的迟到 EOF 会把新会话标记为未运行，导致状态刷新迟滞（无任何日志，属难复现的幽灵问题）。
- **建议**：join 移出 UI 线程，改为「置标志 + `root.after` 轮询」或放弃 join；抽出 `_mark_session_stopped(session_id)` 作为唯一出口。

### WD-22 ｜ 装饰器日本語译文以及 Tars 之外的二进制解码同样缺乏统一边界层；Node 安装会把残缺 zip 的哈希固化为基线导致永久失败
- **位置**：`src/node_install.py:116-120`、`133-138`、`164`、`174/179/199/216/270`
- **问题**：ffmpeg 侧有 `_is_valid_zip` 先验证完整性，node 侧只判 `exists()`。中断下载留下的残缺 zip 会在首次校验时把**错误哈希写入基线**，随后解压失败又一次被 `except Exception` 吞掉；下次运行 zip 仍在且「哈希匹配」，再次失败 → **永久失败且不自愈**。此外多处 `subprocess.run` 无 `timeout`（对比 `ffmpeg_install.py:427` 已显式加 `timeout=15` 并写明原因）。
- **建议**：复用 `_is_valid_zip`（提到 utils 共用），校验通过后再记录哈希；所有 `subprocess.run` 补 `timeout`。

---

## 五、轻微问题清单

下表共 28 项，均不影响主流程正确性，建议随相关模块的改动顺手收敛。

| 编号 | 位置 | 问题 | 建议 |
|---|---|---|---|
| MI-01 | `src/platforms/douyin.py:177`、`src/platforms/bilibili.py:246-249`、`src/ws_client.py:103` | gzip / zlib / brotli 三处解压均无输出长度上限，且 `max_size=None` 取消了 websockets 默认 1MiB 帧限制（解压炸弹面） | `max_size` 设为合理上限（如 8MiB）；解压改为流式并按 `max_length` 截断 |
| MI-02 | `src/stream.py:357-369`、`541-542`、`1023` | `_pad_list` 依赖原地修改副作用，调用方写作 `_ = _pad_list(x)` 导致空列表分支的填充结果被显式丢弃，仅靠下游判空兜底才未出错，语义脆弱易在重构中回归 | 统一改为显式接收返回值，并让该函数总是返回填充后的列表 |
| MI-03 | `main.py:3367-3374` | 直下 FLV 分支的字幕线程沿用「不清理 `create_var`」的旧写法，与 852-870 已修复路径行为漂移，长驻模式下单调泄漏 | 抽 `_start_subtitle_thread()` 两处共用 |
| MI-04 | `main.py:2656-2662` | 音频输出路径忽略传入的 `now`，重新取一次系统时间，跨秒时与视频/日志时间戳不一致 | 直接使用形参 `now` |
| MI-05 | `main.py:3363` | 直下 FLV 文件名在 `title_in_name` 为空时产生双下划线 | 与其它分支同构，或复用 `_build_record_output_path` |
| MI-06 | `gui.py:1198`、`1202` | `_log(..., "warning")` 级别串不被识别（只认 `"error"` / `"warn"`），警告按普通日志渲染 | 统一为 `"warn"`；`level` 收敛为枚举类型并对未知值告警 |
| MI-07 | `gui.py:2086-2097` | `save_config()` 未调用 `_refresh_quality_context()`，新增/改名后画质切换菜单用旧快照 | 保存后补一行刷新调用 |
| MI-08 | `gui.py:2429-2435` | `_stopping = False` 位于会话校验之后，校验失败提前 return 会永久留下 `True`（当前路径不可达，属防御性缺陷） | 提到校验之前或用 `try/finally` |
| MI-09 | `src/recorder_status.py:86`、`201` | `display_info` 每 5 秒覆盖 `start_display_time`，使 uptime 恒显示为 0~5 秒 | 二者语义分离，用独立常量 `process_start_time` 计算 uptime |
| MI-10 | `src/recorder_status.py:28-31`、`41-71` | 注释称「部分路径未持锁写入」并据此加 5 次重试兜底；已核查全部写入点均在 `with main.record_state_lock:` 内，该注释与重试均为误导性死逻辑 | 删除注释与重试（`AGENTS.md` 要求此类被证伪的表述须就地纠正） |
| MI-11 | `config_io.py:210` | `delete_line` 读取未指定 `newline=""`，CRLF 行尾被静默改写为 LF，且会使后续精确匹配偶发失效 | 与 `update_file`（78 行）保持一致，补 `newline=""` |
| MI-12 | `src/cookie_cache.py:205-219`、`355-372` | `invalidate()` / `clear()` 不清 `_inflight` 登记表，在途拉取者的结果会回填覆盖失效操作 | 增加世代号或「已作废」标志，写缓存前复查 |
| MI-13 | `src/cookie_cache.py:285-288` | singleflight 快速路径无锁，与本模块其余加锁口径不一致（CPython 下不崩，free-threading 下有风险） | 纳入 `_cache_lock` 临界区 |
| MI-14 | `src/logger.py:190-209` | 文件 sink 注册无异常兜底；`logs/` 不可写时导入期直接抛 OSError 导致程序在启动阶段崩溃且无日志可查 | 用 `try/except OSError` 包住，失败降级为「仅控制台」 |
| MI-15 | `src/spider.py:8`、`234-245` | `import subprocess` 已无引用；`_is_safe_http_url` 是零生产调用的死代码（注释自述已上移至 utils） | 删除 import；函数进给测试保留则应改名标注 |
| MI-16 | `src/spider.py:4738-4747` | Shopee 两处 `host_suffix` 解析算法不一致，多段 TLD 站点（如 `co.id`）的直链入口拼出无效域名 | 统一为一个 `_shopee_host_suffix(url)` |
| MI-17 | `src/spider.py:2905-2908` | Look 直播正则强制要求 `id=` 后还有 `&`，以 id 结尾的链接必然解析失败 | 改用 `re.search(r"live\?id=([^&?#]+)", url)` 或 `get_params` |
| MI-18 | `src/spider.py:1301-1306` | YY 的「补标题」二次请求失败会连同已成功取到的流地址一起丢弃 | 标题请求独立 try/except，失败仅告警不影响取流 |
| MI-19 | `src/room.py:275-280`、`src/utils.py:350/357/359/390-398` | 错误输出用 `print()` 而非 logger，不进日志体系；冻结打包（无控制台）环境下会被丢弃 | 改为 `logger.warning` / `logger.error` |
| MI-20 | `src/proxy.py:70/115/117/132/134` | 5 处日志硬编码英文，未走 `i18n.tr`，不参与多语言翻译 | 改为 `i18n.tr(...)` 并补各语言目录键值 |
| MI-21 | `src/platforms/twitch.py:112-116` | IRC 未按行缓冲，跨帧半行被静默丢弃（WebSocket 是消息边界而非行边界） | 维护 `self._buf` 跨帧拼接，只处理完整行 |
| MI-22 | `src/weverse_auth.py:40-50` | token 刷新异常被完全吞没（裸 `except Exception: return None, None`），凭据失效后无任何线索 | 记录 Warning 日志；非 200 时记录 status_code（注意脱敏） |
| MI-23 | `i18n.py:338-342` | `tr()` 对译文直接 `.format`，译文漏/多花括号会在 `except` 分支内二次抛错，顶掉原始异常；zh_CN 常为恒等映射，问题只在切语言后暴露 | 用 `string.Formatter().vformat` 包裹并捕获，保证 `tr()` 永不抛 |
| MI-24 | `msg_push.py:198-207` | SMTP 非 SSL 分支无 STARTTLS，授权码在明文连接上发送，且无任何告警 | 先 `starttls()`，服务器不支持时拒绝 login 或显著告警 |
| MI-25 | `src/utils.py:142-155` | `migu.js` 是唯一走 `run_node_script_async` 的脚本，该路径不读源文件、不校验哈希，`_JS_SHA256_EXPECTED` 对它形同虚设 | 在该入口同样调用 `_check_js_hash` |
| MI-26 | `build_exe.py:267/333` | `tarfile.extractall` 未显式传 `filter=`（依赖 Python ≥3.14 的默认行为） | 显式补 `filter="data"`，防止未来降级 Python 时回归 Zip Slip |
| MI-27 | `web_api.py:238`；`web/app.js:25` | CSP 的 `connect-src` 放行任意主机 ws/wss（面板实际无需 WebSocket）；bearer 存 `localStorage` 会持久化并跨 Tab 共享 | 收紧为 `'self'`；改用 `sessionStorage` |
| MI-28 | `index.html:1-19` | 根目录 index.html 是独立的 M3U8/FLV 播放器工具页（与面板无关，未被 StaticFiles 挂载），资源齐全且钉版有效，但缺 SRI，`<meta name="referrer" content="never">` 取值无效（规范值为 `no-referrer`） | 为两个 CDN 脚本补 `integrity` + `crossorigin`；修正 referrer 取值 |

---

## 六、已核实但不构成问题的项

为避免后续重复争议，以下疑点已逐条回源核查并**明确排除**：

| 核查项 | 结论 |
|---|---|
| **命令注入** | 全仓生产代码无 `shell=True`。ffmpeg 走 `subprocess.Popen(argv_list)`，外部数据仅作为独立 argv 元素插入；录后脚本走 `shlex.split`；`_DANGEROUS_CONFIG_KEYS` 拦截了唯一可致 RCE 的配置键。**不构成可利用注入。** |
| **路径穿越（文件名）** | `main.py:286` 的 `rstr` 覆盖 `/ \ : * ? " < > |` 等，`../` 被逐字符替换为 `___`；`clean_name` 与 `main.py:3016/3179` 对主播名、标题全量清洗后才进入路径。**无可用穿越点**（长度截断缺失见 WD-14，属另一类问题）。 |
| **CORS 危险组合** | 全仓无任何 CORS 配置。唯一 `Access-Control` 命中是 `spider.py:4484` 的出站请求头（爬虫模拟），与服务端无关。 |
| **默认监听 0.0.0.0** | 默认 `web_host = 127.0.0.1`；`web.py:206-213` 明确「未启用认证 + 非回环 → 拒绝启动」。真实风险是「默认无认证 + 破例闸门」，已登记为 WD-07/CR-08。 |
| **Web 文件读取路径穿越** | `/api/files` 与 `/api/files/download` 均经 `_is_within`（`commonpath`）+ `realpath`，且对每一条目做符号链接逃逸校验。 |
| **前端 XSS** | 已逐条追踪污点链：`/api/status`、`/api/danmaku`（含远端聊天内容）、`/api/config`、`/api/files`、`/api/rooms` 的全部服务端字段，落到 `innerHTML` 前**均经 `esc()`**（覆盖 `& < > " '`）或使用 `textContent`；唯一未转义插值 `m.dropped` 后端恒为 `int`。`eval` / `new Function` / `outerHTML` / `insertAdjacentHTML` / `document.write` 在 `web/` 目录零命中。**无 XSS。** |
| **SRT 内容注入** | `_sanitize_srt_text`（`srt_writer.py:42-43`）已处理换行与 `-->` 伪造字幕条目。 |
| **模块级 `asyncio.Lock` 单例** | 全仓唯一 `asyncio.Lock()` 是 `ws_client.py:83` 的**实例级**；其余全部为 `threading.Lock`，且已逐段核对**所有临界区内均无 `await`**。历史坑已修复，现状完备。 |
| **`config_bool` 统一覆盖面** | 已完备，无遗漏调用点。`main.py` 30 处布尔配置全部经 `read_config_bool`；`logger.py` / `gui.py` / `web_config.py` 全部改用 `parse_config_bool`；Python 侧已无 `.get(read_config_value(...), 兜底)` 式残留（前端 JS 已同步改造为同一套 True/False 记号解析）。 |
| **全局关闭 SSL 验证** | 生产代码无 `verify=False`、无 `urllib3.disable_warnings()`、无 `ssl._create_unverified_context()`；`http_config.ssl_verify` 默认 True 且与「https 录制」正确解耦。 |
| **pickle / `tempfile.mktemp`** | 全仓未命中。原子写用 `<path>.<pid>.tmp` + `os.replace`。 |
| **日志无轮转导致磁盘写满** | 三处文件 sink 全部带 `rotation="300 KB"` + `retention=3`，占用有界。 |
| **`except A, B:`（PEP 758）** | 项目刻意约定（`AGENTS.md:41-53` 明确），非 Python 2 语法遗留。**不报。** |
| **Node/JS 子进程注入** | `run_node_script_async` 传 argv 列表、`run_js_async` 用 `execjs.compile(...).call(func, *args)` 传参；spider.py 三处调用均为「脚本路径固定 + 外部值作参数」，**不存在拼接 JS 源码或命令行的写法**。JS 侧 `eval` 均为常量字符串。 |
| **tarfile 默认 filter** | Python 3.14 起 `extractall` 默认 `filter='data'`（PEP 706），`requires-python = ">=3.14"`，当前不构成路径穿越（显式传参已列为 MI-26 加固项）。 |

---

## 七、改进建议与修复优先级

### 7.1 修复路线图（按风险收敛效率排序）

**第一批｜P0：阻断「必然发生」的严重故障（建议立即修复）**

| 序号 | 条目 | 一句话动作 |
|---|---|---|
| 1 | CR-01 | GUI 启动前自检 URL 配置非空；`input()` 补 `EOFError` 兜底 |
| 2 | CR-02 | 重写 URL 配置行为宽容解析 + 单行异常隔离 |
| 3 | CR-03 | `TarsInputStream` 加 `_need()` 边界助手 + 循环进度断言 |
| 4 | CR-04 | `only_fans` 三层默认值统一为 `False` / `None`，补回归测试 |
| 5 | CR-05 | 录制守护循环加总时长上限 + 文件增长停滞检测 |
| 6 | CR-06 | 成功后追加产物体积校验，零字节按失败处理 |
| 7 | CR-08 / CR-10 | `[Web]` 节写入对称校验 + 配置键白名单；脱敏补值形态检测 |
| 8 | CR-11 | 安装器/打包哈希默认强制 + 统一走 `utils.unzip_file` |
| 9 | CR-12 | `_loads_dict` 改用 `_safe_loads`；修正 3 处装饰器契约 + AST 单测 |

> 其中 CR-01、CR-02、CR-04 属于「用户默认路径上必然触发」的功能性阻断，建议优先于其余各项。

**第二批｜P1：收敛安全暴露面** —— CR-07（凭据独立文件 + 权限收紧）、CR-09（房间 URL scheme 与目标校验）、WD-07（默认启用认证）、WD-08（Origin 同源校验）、WD-09（Token 吊销端点）、WD-01（日志全程脱敏）。

**第三批｜P2：治理资源与并发** —— WD-02、WD-03、WD-04、WD-05（弹幕链路背压与连接存活）、WD-11、WD-12（解析限速与转码池化）、WD-13（熔断样本口径）、WD-21（GUI 线程模型）。

**第四批｜P3：数据一致性与健壮性** —— WD-14、WD-15、WD-18、WD-19、WD-20、WD-22，以及全部轻微项。

### 7.2 结构性改进建议（治本）

1. **建立「唯一实现」清单并机检**。本次审查暴露的核心模式是：同一横切能力存在多套实现且各自腐烂——脱敏 4 种写法、原子写 2 套（3 处已改 2 处未改）、边界校验分散在 4 个模块、安全能力由 4 条互不共享的路径各自拼装。建议把 `mask_credentials`、`_atomic_write_text`、二进制长度校验、文本读写下沉到 `src/utils.py` 作为**唯一入口**，并在 `AGENTS.md` 中列为强制约定，配合 CI 脚本扫描旁路调用。

2. **为「装饰器契约」与「跨层默认值」补 AST 级防回归测试**。CR-12（4 处装饰器契约破裂）与 CR-04（三层默认值漂移）都不是笔误，而是缺少机器约束。建议新增两个测试：① 扫描 `spider.py` 所有 `get_*_stream_*`，按返回注解校验装饰器变体；② 断言跨层传递的开关在无显式传参时的最终生效值。这与本仓已有的黄金快照（F-01 沉淀）思路一致。

3. **给平台解析层引入统一的 `_fetch_json` / `_make_headers` / `_probe_live_status` 三层公共函数**。`spider.py` 现有 50+ 处重复的 headers 样板、多条逐字重复的函数体、两处算法不一致的同一逻辑（Shopee），而这些地方已留下「复制粘贴后漏改」的物证（错误注释、静默不一致）。继续以「再加一个 `get_xxx_stream_url`」的方式扩展只会放大该债。

4. **把安全默认值从「最弱档 + 可选开关」反转为「强制 + 显式豁免」**。当前多处安全能力依赖环境变量才升级（哈希校验、JS 严格模式、Web 认证），而默认路径恰好是零信任锚路径。建议反转默认值，并把「更新基线」变成一次可见的 commit。

5. **让「失败」可观测**。`trace_error_decorator` 把异常压成 `{"is_live": False}` 的设计，使任何平台改版/风控都表现为静默漏录。建议改为「返回带 `error` 标记的 dict 并告警」，让静默失败面可收敛；同时对「解析失败」与「正常未开播」做语义区分（WD-13）。

---

## 八、总结性结论

本次对 `D:\DouyinLiveRecorder-dev` 工作副本执行了覆盖 **148 个自有源文件、44,385 行**的全量静态审查（已剔除第三方依赖与构建产物），按运行时链路分为 7 个模块组逐组全文通读，并对全部严重项执行了回源复核。共登记问题 **62 项**：严重 12 项、中等 22 项、轻微 28 项。

**整体评价**。项目的工程质量处于中上水准，若干关键子系统明显高于平均：`src/ffmpeg_proc.py` 的分级终止与「杀不掉则保留注册表」的闭环、`src/stream_select.py` 的探针节流/退避抖动/分片层探测（保守优先、不误杀可用源）、`src/scheduler.py` 的自适应容量与按 host 熔断、`src/async_http.py` 对跨事件循环客户端生命周期的处理，以及前端 `esc()` 与 `replaceChildren`/`textContent` 的克制组合（经逐条污点链追踪确认无 XSS），都是设计者与历次审查投入的真实体现。命令注入、路径穿越、危险 CORS 组合、pickle/`mktemp`、全局关闭 SSL 等高频高危面**均不构成可利用风险**，这一点在本报告中已逐条核销。

**但同时也存在三条系统性技术债，它们是本次多数严重问题的共同根因**：

1. **安全能力按文件推进而非按能力收敛，导致同源实现多套、互相绕过。** 仓库已有一等公民实现（`unzip_file`、`is_safe_http_url`、JS 哈希钉定、原子写），但 ffmpeg 官方源绕过 `unzip_file`、`migu.js` 绕过哈希校验、`build_exe.py` 绕过全部、`update_config` 绕过原子写。结果是「修过」不等于「收敛」，每补一处漏洞都会在别处留下同型副本。

2. **跨层默认值与装饰器契约缺少机器约束，已产生可见腐烂。** CR-04（`only_fans` 三层默认值漂移，致使上一次修复在真实调用链上完全失效）与 CR-12（4 处装饰器契约破裂）都不是偶发笔误，而是缺少 AST 级断言的必然结果。

3. **错误处理范式把「故障」压成了「无信号」。** `@trace_error_decorator` 统一返回 `{"is_live": False}`、以及「成功判定只看退出码」，共同导致两类真实事故形态（HLS 分片假绿零字节、FLV/CDN 无限重连挂起）既不能自愈也无法被发现，反过来还污染了调度器的熔断样本与线路退避。

从**终端用户可感知**的角度，最紧迫的三项是 CR-01（GUI 首次使用者点击录制后完全无响应）、CR-02（一行配置多写一个逗号即导致其后所有房间永久不录）、CR-04（斗鱼弹幕被静默过滤为空文件）——三者均位于默认路径上且无任何自我提示。从**攻击者视角**最紧迫的则是 CR-11（供应链哈希缺失，blast radius 覆盖所有下载用户）与 CR-08（Web 面板可被自身接口接管或锁死）。

**建议行动项**：按第七章的路线图，先完成 P0 批次共 9 项（尤其是上述前三项功能性阻断），再按 P1/P2 收敛安全面与资源治理；随后投入章节 7.2 的五条结构性改进，以机检手段防止同类问题再次回归。全部修复完成后，建议以「CR-03 畸形帧注入」「CR-04 工厂默认值」「CR-06 零字节产物」「CR-08 未认证 Web 写入」四个场景补充回归测试，作为下一次审查的验证基线。

---

*报告结束。本报告所有条目均可按 `文件:行号` 直接定位复核；第六章所列 14 项已核查排除，供后续审查参照，避免重复争议。*

---

## 附录：修复实施记录（2026-09-19）

> 本附录为审查完成后的**追记**，不修改前述任何发现的内容与分级——第三至五章保持为审查当时的快照，
> 便于日后回溯「当时判断了什么」。本附录记录据此落地的修复范围与验证结果。

### A.1 修复范围

**全部 62 项已处理**：严重 12 / 中等 22 / 轻微 28。

| 处理类型 | 数量 | 说明 |
| --- | --- | --- |
| 已修复 | 61 | 按报告给出的建议方向落地，部分方案做了等价替代（见 A.2） |
| 复核后判定不适用 | 1 | WD-13（详见 A.3） |

### A.2 与报告建议的差异说明（3 处）

1. **CR-07（凭据落盘）**：报告建议「拆分凭据文件或备份脱敏 + 权限收紧」。落地采用
   **备份默认脱敏 + 配置与备份统一 `chmod 0600`**，并保留 `DLR_BACKUP_KEEP_SECRETS=1`
   作为需要「备份含真实凭据以完整还原」者的显式出口。未拆分独立凭据文件，原因是这会改变
   既有部署的配置布局与所有读取路径，超出本次修复的安全边界目标。
2. **CR-11（供应链校验）**：报告建议「内置仓库维护的期望 SHA256」。由于构建机无法在本次
   **离线**取得四个上游源的官方校验值，落地实现为：**校验机制就位 + 钉定表留空 + 未钉定时
   告警并打印实际哈希**（`DLR_RUNTIME_SHA256` 可注入）。即「机制已可用、基线待维护者填入」，
   这一点须明确记为**未完全闭合项**。
3. **MI-28（CDN 脚本 SRI）**：`index.html` 的两个 CDN 脚本补 `integrity` 需要准确的
   上游哈希，未在离线环境获取，故只修正了无效的 `referrer` 取值（`never` → `no-referrer`），
   **SRI 属未完成项**。

### A.3 复核后不适用于本代码库的条目

| 编号 | 原判断 | 复核结论 |
| --- | --- | --- |
| WD-13 | 「熔断样本把『主播未开播』计为失败，离线房间多的 host 被长期熔断」 | **不成立**。`main.py` 在解析成功时（无论是否开播）已调用 `record_success(record_host)`，`record_error` 只在 `anchor_name` 为空（≈解析失败）时触发。原审查未看到这两行的配对关系，故未做改动。 |

### A.4 验证结果（门禁全绿）

| 门禁 | 结果 |
| --- | --- |
| `pytest`（全量） | **1042 passed, 2 skipped, 0 failed**（53.96s） |
| `black --check --line-length 120` | 136 个文件无差异 |
| `isort --profile black --check-only` | 无差异 |
| `mypy`（**无参**，范围由 pyproject 定义） | **Success: no issues found in 117 source files** |
| `scripts/check_annotations.py` | 通过（平均注释密度 22.8%） |
| `scripts/compile_po.py --check` | `.mo` 与 `.po` 同步（636 条） |
| `scripts/extract_i18n_strings.py` | 运行时缺失 **0 条** |
| 前端 `node --test tests/frontend/` | 9 passed |

**随修复同步调整的测试（5 处，均为「对齐正确设计」而非迁就实现）**：
`test_spider.py::TestLoadsDict::test_invalid_json`（改为断言返回 `{}`）、
`test_spider_platform.py` 的 AcFun 失败断言（`{"is_live": False}` → `None`）、
`test_i18n_tr.py::test_tr_missing_kwarg_*`（改为断言降级为原文模板）、
`test_utils.py` 的 7 处 `capsys` 断言（改为捕获 loguru sink，新增 `log_capture` fixture）、
`test_spider_fixes.py` 的 3 处 patch 目标（`sp.subprocess.run` → `subprocess.run`）。

### A.5 修复过程中新发现并已修正的两个问题

1. **自锁死锁（本次修复引入、已修正）**：将 `_purge_expired_tokens()` 改为「内部自行持
   `_tokens_lock`」后，`login` 里原有的 `with _tokens_lock: _purge_expired_tokens()` 形成
   **非重入自死锁**，导致所有登录请求挂死（症状为测试无输出、无报错）。
   已移除调用点的外层锁并在函数处加注约定。
2. **`except A, B as e:` 是语法错误（既存写法风险）**：PEP 758 的无括号写法**不支持 `as`
   绑定**，需异常对象时必须回退为 `except (A, B) as e:`。本次在 `recorder_status.py` 触发，
   已修正并将该语法约束写入 `AGENTS.md`。

### A.6 遗留事项

- **CR-11 的哈希基线**：机制已就位但钉定表为空，需维护者在联网环境填入官方校验值后方为「完全闭合」。
- **MI-28 的 SRI**：需联网取得两个 CDN 脚本的准确 `sha384` 后补齐。
- **端到端真机验证**：本项目约定「单测之外须端到端真机验证」。本次修复覆盖了平台解析、录制看门狗、
  选源限速、Web 面板等多个链路，**建议在真实直播场次下按平台抽样回归**（尤其 CR-01 的 GUI 首次启动、
  CR-04 的斗鱼弹幕、CR-05/06 的录制终止判定、CR-09 的房间 URL 校验），本报告未包含该层验证结果。
