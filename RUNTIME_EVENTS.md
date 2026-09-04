# Runtime Events / 运行时事件

> **Language and AI assistance note / 语言及 AI 协助说明**  
> The contributor does not speak, read, or write Chinese. Please excuse any inaccuracies in the Chinese wording. The Chinese translation and wording of this document were prepared with assistance from ChatGPT. The feature design, Python implementation, debugging, and testing were carried out collaboratively by the contributor and ChatGPT.  
> 提交者不会说、读或写中文。如中文表述有不准确之处，敬请谅解。本文档的中文翻译及文字整理由 ChatGPT 协助完成；相关功能的设计、Python 实现、调试和测试由提交者与 ChatGPT 共同完成。

## Purpose / 用途

DouyinLiveRecorder can write semantic runtime state as JSON Lines (JSONL) to `logs/runtime_events.jsonl`. This allows external GUIs, web frontends, monitoring applications, and automation tools to observe accurate recorder state in real time without needing to parse human-oriented console output.

DouyinLiveRecorder 可以将语义化的运行状态以 JSON Lines（JSONL）格式写入 `logs/runtime_events.jsonl`。这样，外部 GUI、Web 前端、监控程序和自动化工具可以实时获取准确的录制程序状态，而无需解析主要面向人工阅读的控制台输出。

**The bridge observes existing recorder behavior; it does not alter the recording workflow.**

**该桥接仅观察现有录制程序的行为，不改变录制工作流程。**

The runtime-event hooks are intentionally passive and read-only. They do not provide a command or control channel. Apart from a small related bugfix that makes a disabled room leave its per-room retry wait promptly, the existing recording logic is not changed by this contribution.

运行时事件钩子被有意设计为被动且只读，不提供命令或控制通道。除了一处相关的小型修复——使被禁用的直播间能够及时退出其自身的重试等待——本次贡献不改变现有录制逻辑。

## Event file / 事件文件

The event file is UTF-8 encoded and contains one independent JSON object per line.

事件文件使用 UTF-8 编码，每行包含一个独立的 JSON 对象。

The path is relative to the application directory:

事件文件路径相对于应用程序目录：

```text
logs/runtime_events.jsonl
```

When running from source, the application directory is the directory containing `runtime_events.py`. In a frozen/PyInstaller build, it is the directory containing the executable.

以源码方式运行时，应用程序目录是包含 `runtime_events.py` 的目录。在冻结/PyInstaller 打包版本中，则是包含可执行文件的目录。

Every event contains:

每个事件都包含：

- `timestamp` — UTC timestamp in ISO 8601 format / UTC ISO 8601 格式时间戳
- `event` — semantic event name / 语义事件名称

Event writing is best-effort. Failure to create the log directory or write an event is ignored and does not alter recorder operation.

事件写入采用尽力而为（best-effort）方式。如果日志目录无法创建或事件无法写入，该错误会被忽略，不会影响录制程序本身的运行。

## Events / 事件

### `runtime_started`

Emitted after runtime initialization has completed sufficiently for the main recorder loop to start.

当运行环境初始化完成到足以进入主录制循环时发出。

Additional fields / 附加字段:

- `version`

---

### `room_monitoring_started`

Emitted once when a worker begins monitoring a configured room.

当工作线程开始监测一个已配置的直播间时发出一次。

Additional fields / 附加字段:

- `url` — configured room URL / 已配置的直播间 URL
- `quality` — configured recording quality / 已配置的录制质量

---

### `room_monitoring_stopped`

Emitted when monitoring of a configured room is stopped and the room is removed from the active monitoring list.

当已配置直播间的监测停止，并从活动监测列表中移除时发出。

Additional fields / 附加字段:

- `url` — configured room URL / 已配置的直播间 URL

---

### `room_live`

Emitted when the resolver reports that a monitored room is live.

当解析器报告被监测的直播间正在直播时发出。

Additional fields / 附加字段:

- `url`
- `platform`
- `anchor`
- `quality`

---

### `room_waiting`

Emitted once before a worker enters a retry/wait period.

在工作线程进入重试/等待周期之前发出一次。

Additional fields / 附加字段:

- `url`
- `platform`
- `anchor`
- `quality`
- `retry_after` — actual wait duration in seconds / 实际等待秒数
- `next_check` — calculated next-check time in UTC ISO 8601 format / 计算出的下一次检查时间（UTC ISO 8601）

This allows an external UI to maintain its own countdown without parsing console output.

这样，外部 UI 可以自行显示倒计时，而无需解析控制台输出。

---

### `recording_started`

Emitted after a recording backend has successfully started.

当录制后端成功启动后发出。

Additional fields / 附加字段:

- `url` — configured room URL / 已配置的直播间 URL
- `backend` — currently `ffmpeg` or `direct_flv` / 当前为 `ffmpeg` 或 `direct_flv`
- `output_path`
- `format`

For the direct FLV backend, this event is emitted only after the HTTP stream request has succeeded.

对于 direct FLV 后端，仅在 HTTP 直播流请求成功后才发出此事件。

---

### `recording_stopped`

Emitted after a previously started recording session stops.

当之前已经启动的录制会话停止后发出。

Additional fields / 附加字段:

- `url`
- `backend`
- `output_path`
- `format`
- `reason`
- `return_code` — present for FFmpeg backend completion/error where applicable / 在适用的 FFmpeg 后端完成或错误情况下提供

Current `reason` values / 当前 `reason` 值:

- `disabled` — the configured room was disabled/commented / 已配置直播间被禁用或注释
- `disk_space_limit` — recording was stopped because the configured free-space limit was reached / 因达到配置的剩余磁盘空间限制而停止录制
- `completed` — backend exited normally / 后端正常结束
- `backend_error` — backend stopped with an error / 后端因错误而停止

## Privacy and security / 隐私与安全

The runtime event bridge intentionally does **not** emit sensitive runtime information such as:

运行时事件桥接有意**不输出**以下敏感运行信息：

- cookies
- passwords / 密码
- authorization data / 授权信息
- proxy credentials / 代理凭据
- signed or direct stream URLs / 签名或直连直播流地址
- raw resolver responses / 原始解析器响应
- FFmpeg command lines / FFmpeg 命令行

The `url` field refers to the configured public room URL, not the resolved/signed media stream URL.

`url` 字段指的是已配置的公开直播间 URL，而不是解析得到的签名媒体流 URL。

## Testing status / 测试状态

The runtime-event hooks on the FFmpeg recording path were exercised with live Douyin rooms. The tests covered monitoring start/stop, live detection, recording start/stop, disabling and re-enabling a room, backend failure, retry waiting, and interruption of that waiting state. Other FFmpeg-based platforms were not separately exercised as part of this contribution.

FFmpeg 录制路径上的运行时事件钩子已使用实际的抖音直播间进行了测试。测试涵盖监测开始/停止、直播检测、录制开始/停止、禁用和重新启用直播间、后端失败、重试等待以及中断该等待状态。本次贡献未单独测试其他基于 FFmpeg 的平台。

The existing direct FLV recording logic was not changed by this contribution; only passive runtime-event emissions were added around its existing control flow. Those new `direct_flv` event hooks were reviewed and syntax-checked. Live verification was also attempted using the Huajiao and Shopee example room URLs supplied by the project, but neither example produced an active live stream during testing. The `direct_flv` hooks therefore could not yet be exercised in a real live recording session. This limitation concerns live verification of the newly added event reporting only, not the existing direct FLV recording functionality.

本次贡献没有修改现有的 direct FLV 录制逻辑；只是在其现有控制流程周围增加了被动式运行时事件输出。新增的 `direct_flv` 事件钩子已经过代码审查和语法检查。我们还尝试使用项目提供的花椒和 Shopee 示例直播间 URL 进行实际验证，但测试时两个示例都没有产生正在进行的直播。因此，`direct_flv` 事件钩子目前尚未能在真实直播录制会话中触发验证。此限制仅涉及新增事件报告功能的实际直播验证，并不表示现有 direct FLV 录制功能存在问题。

The event path was also verified in a PyInstaller onedir build, including creation of `logs/runtime_events.jsonl` beside the frozen executable.

事件路径还在 PyInstaller onedir 打包版本中进行了验证，包括在冻结可执行文件旁创建 `logs/runtime_events.jsonl`。

## Notes / 说明

The event bridge is intended as a generic integration mechanism. It can be used by graphical frontends, web interfaces, monitoring tools, automation, or other external programs.

该事件桥接旨在作为通用集成机制，可供图形界面、Web 接口、监控工具、自动化程序或其他外部程序使用。

No schema version is currently defined. Consumers should ignore unknown fields and unknown event names so that the event stream can be extended in the future.

目前尚未定义事件架构版本。使用方应忽略未知字段和未知事件名称，以便将来可以扩展事件流。
