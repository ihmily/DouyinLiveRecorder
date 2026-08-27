# AGENTS.md — DouyinLiveRecorder 核心约定

> 本文件供编码代理（Copilot / Cursor / Qoder 等）快速消费，汇总项目关键约定。
>
> **本文件是项目长期约定的唯一事实源**：编码规范、架构决策、并发/线程模型、测试编写规则、
> 构建与格式化流程、以及所有「已知坑（避免回归）」均已在此收敛。新增长期性约定请直接写入本文件
> 对应章节，不要只留在临时笔记里。

## 项目概览

- **名称**: DouyinLiveRecorder
- **版本**: 4.0.9.1（唯一事实源：`pyproject.toml` 的 `version` 字段。`main.py` 与 `src/web_api.py` 运行时经 `importlib.metadata` 动态读取；`Dockerfile` 经 `APP_VERSION` 构建参数动态注入；`i18n/zh_CN/LC_MESSAGES/zh_CN.po` 不再携带版本号。`README.md` / `CODE_WIKI.md` 为文档，不再纳入版本同步/校验。）
- **描述**: 支持抖音、TikTok、YouTube、快手等 60+ 平台的直播录制工具
- **许可证**: MIT

## Python 版本

- **最低要求**: Python >= 3.14
- **目标版本**: py314
- **mypy 检查版本**: 3.14
- **3.14 破坏性变更基线**: `asyncio.get_event_loop()` 不再隐式创建事件循环（无当前循环时抛 RuntimeError）；`pkg_resources`、PEP 594 亡故电池模块（telnetlib/cgi/pipes 等）均已移除；`ctypes.windll` 虽仍可用但新代码统一走 `ctypes.WinDLL`（对齐 web.py 惯例）

## 代码风格

### Black

```toml
line-length = 120
target-version = ['py314']
include = '\.pyi?$'
```

排除目录: `.git`, `.venv`, `build`, `dist`, `__pycache__`, `.pyc`, `node`, `ffmpeg`, `downloads`, `logs`

### isort

```toml
profile = "black"
line_length = 120
known_first_party = ["src", "i18n"]
```

排除目录: `.git`, `node`, `ffmpeg`, `downloads`, `__pycache__`, `*.pyc`

### mypy

```toml
python_version = "3.14"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
ignore_missing_imports = true
```

## 项目结构

```
项目根目录/
├── main.py              # CLI 录制入口（douyin-recorder）
├── gui.py               # GUI 入口（douyin-recorder-gui）
├── gui_legacy.py         # 旧版 GUI 入口
├── web.py               # Web 管理面板入口（douyin-recorder-web）
├── i18n.py              # 国际化模块
├── msg_push.py          # 消息推送模块
├── build_exe.py         # PyInstaller 打包脚本
├── pyproject.toml       # 项目元数据 + 工具配置
├── requirements.txt     # 运行时依赖（与 pyproject.toml 同步）
│
├── src/                 # 核心源码包
│   ├── __init__.py      # 包出口（含 get_danmaku_collector 工厂）
│   ├── base.py          # 公共基类/常量
│   ├── room.py          # 直播间管理（HEADERS / DESKTOP_UA）
│   ├── spider.py        # 平台爬虫/流地址解析
│   ├── stream.py        # 流录制逻辑
│   ├── stream_select.py # 选源与流地址可达性校验（探针/节流/退避）
│   ├── scheduler.py     # 并发调度中枢（自适应容量 + 按平台熔断）
│   ├── notify.py        # 错误/成功计数与消息推送接线
│   ├── collector.py     # 弹幕采集器 + DanmakuMonitorHub
│   ├── danmaku_monitor.py # 弹幕监控数据面（Web/GUI 消费）
│   ├── srt_writer.py    # 弹幕 SRT 分片写入
│   ├── ws_client.py     # 弹幕 WebSocket 客户端（proxy=None）
│   ├── async_http.py    # 异步 HTTP 客户端
│   ├── sync_http.py     # 同步 HTTP 请求
│   ├── http_config.py   # HTTP 配置（SSL 验证策略）
│   ├── cookie_cache.py  # Cookie 缓存
│   ├── config_io.py     # 配置读写
│   ├── recorder_status.py # 录制状态
│   ├── ffmpeg_proc.py   # FFmpeg 进程封装
│   ├── video_postprocess.py # 录制后处理
│   ├── logger.py        # 日志（loguru）
│   ├── utils.py         # 工具函数
│   ├── proxy.py         # 代理支持
│   ├── ttwid.py         # 抖音 ttwid 获取
│   ├── ab_sign.py       # AB 签名
│   ├── web_api.py       # FastAPI Web API
│   ├── web_config.py    # Web 配置
│   ├── web_tray.py      # Web 托盘
│   ├── weverse_auth.py  # Weverse 认证
│   ├── ffmpeg_install.py # FFmpeg 自动安装
│   ├── node_install.py  # Node.js 自动安装
│   ├── platforms/       # 平台专属实现（douyin/douyu/huya/bilibili/twitch + _xbogus/_tars）
│   ├── proto/           # protobuf（douyin.proto + douyin_pb2.py + douyin_pb2.pyi 存根）
│   └── javascript/      # JS 签名脚本（各平台）
│
├── config/              # 运行时配置（exe 同级）
│   ├── config.ini       # 主配置
│   └── URL_config.ini   # 直播间 URL 配置
│
├── web/                 # Web 面板前端静态资源
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── i18n/                # 翻译目录（多语言多格式）
│   ├── zh_CN/LC_MESSAGES/  # 简体中文（gettext .po 源 + 编译 .mo）
│   ├── en_US.json          # 英语（美国）目录（JSON 格式）
│   ├── en_GB.json          # 英语（英国）目录（JSON 格式）
│   └── zh_TW.yaml          # 繁体中文目录（YAML 格式）
│
├── ffmpeg/              # FFmpeg 运行时（自动下载）
├── node/                # Node.js 运行时（自动下载）
├── typings/             # 第三方库类型存根
│   ├── customtkinter/   # customtkinter 类型存根（__init__.pyi）
│   ├── execjs/          # PyExecJS 类型存根（多个 .pyi）
│   └── pystray/         # pystray 类型存根（__init__.pyi）
└── .github/workflows/   # CI/CD（GitHub Actions 构建发布）
```

## 入口点

| 命令 | 模块 | 说明 |
|------|------|------|
| `douyin-recorder` | `main:main` | CLI 录制核心 |
| `douyin-recorder-gui` | `gui:main` | 图形界面 |
| `douyin-recorder-web` | `web:main` | Web 管理面板 |

## 依赖管理

- **运行时依赖**: `pyproject.toml` `[project.dependencies]` 与 `requirements.txt` 保持同步
- **开发依赖**: `pip install .[dev]`（pytest, black, isort, mypy）
- **构建依赖**: `pip install .[build]`（PyInstaller >= 6.10.0）
- **GUI 依赖**: `pip install .[gui]`（customtkinter, pystray, Pillow）
- **i18n 依赖**: PyYAML（zh_TW.yaml 目录加载；缺失时仅损失 YAML 格式，JSON/gettext 不受影响）
- **版本下限（须与 `requirements.txt` 和 `pyproject.toml [project.dependencies]` 三处一致）**:
  `pystray>=0.19.5`（macOS 改走 PNG 图标）、`Pillow>=12.3.0`、`customtkinter>=6.0.0`
- **依赖缺失排查顺序**: venv 里缺 `brotli`/`protobuf` 等（requirements.txt 已列但未装）表现为
  **测试收集期 `ModuleNotFoundError`**，极易误判成代码 bug —— 先核对 `pip list` 与 `requirements.txt`
  的差异，再怀疑代码。pip 走本地代理（如 `127.0.0.1:10808`）被拒时用
  `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>` 绕过。

## 测试

```toml
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
```

- 测试目录: `tests/`
- 运行测试: `pytest`
- **tests/ 质量门禁（2026-08 起全绿，须保持）**: `pytest`（0 警告）、`black --check tests/`、`isort --check-only tests/`、`mypy tests/`、`basedpyright tests/`（0 error/0 warning）
- 覆盖率源码: `src/`
- 覆盖率排除: `tests/`, `__pycache__/`, `node/`, `ffmpeg/`
- 逐模块覆盖率门禁: `python scripts/check_coverage.py`（CI 自动执行，阈值定义见脚本 `MODULE_THRESHOLDS`）
- 并发测试专用覆盖率配置: `.coveragerc-concurrency`（随仓库分发，CI 经 `COVERAGE_RCFILE` 引用，`fail_under = 0`）
- 创建/更新测试: 使用 [test-creator Skill](.qoder/skills/test-creator/SKILL.md) 标准化流程（源码分析 → Mock 配置 → 验证执行）

### 测试编写强制约定

- **环境变量一律用 `monkeypatch.setenv/delenv`，禁用 `patch.dict(os.environ)`**：`unittest.mock.patch.dict`
  对 `os.environ` **无论 `clear` 取值**都会 `original = in_dict.copy()` 整体快照，退出时无条件
  `_clear_dict()` + `update(original)` 整体写回。编码代理 harness 注入的 `CODEBUDDY_MCP_CONFIG`
  会动态膨胀，一旦超 Windows 环境变量 32767 上限，写回即抛
  `ValueError: the environment variable is longer than 32767 characters`；且该失败会随修复
  「转移」到下一个 `patch.dict` 用例（根因共通、非单点）。`monkeypatch` 只动单个 key、不整体快照，
  故必须使用。项目已有 `_clear_proxy_env(monkeypatch)` helper 统一清除代理变量。
- **patch `main.py` 的 subprocess 必须替换 main 的全局引用，不能改 stdlib 模块本体**：
  禁止 `monkeypatch.setattr(main.subprocess, "Popen", ...)`——`main.subprocess` 就是 stdlib 模块对象，
  改它会波及同进程 harness 守护线程（safe-delete 守卫线程的 `subprocess.run` 要求 Popen 支持上下文
  管理协议，否则报 `SAFE_DELETE_BULK_GUARD_ERROR`）。正确做法：
  `shim = types.SimpleNamespace(**vars(subprocess))` → `shim.Popen = FakePopen` →
  `monkeypatch.setattr(main, "subprocess", shim)`。
- **FakePopen 必须是类且定义 `__class_getitem__`**：`check_subprocess` 内层函数注解
  `proc: subprocess.Popen[bytes]` 在 `def` 时即求值（`main.py` 未启用
  `from __future__ import annotations`），用 lambda / 未定义 `__class_getitem__` 的普通类分别报
  `'function' object is not subscriptable` / `type 'X' is not subscriptable`。
- **双模式测试脚本须带 `int(sys.argv)` 守卫**：`tests/test_*_live_collector.py`（bili/douyin/douyu/huya/twitch
  共 5 个）既可 `python file.py <URL> [秒数]` 独立运行，也被 pytest 收集。顶层
  `SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else N` 在 pytest 下会拿到 `-q` 等参数导致
  `int('-q')` 崩溃，必须附加 `and not sys.argv[2].startswith("-")` 守卫。新增同类脚本沿用此模式。
  （同理：给 pytest 传 `-p no:cacheprovider` 等参数会被这些脚本的 argv 解析吞掉并报收集错误，属预期行为。）
- **harness safe-delete 护栏按轮次计删除配额**（约 50 次/turn）：测试内 `os.remove` 可能在配额耗尽后被拦
  （`OSError SAFE_DELETE_BULK_CONFIRM_REQUIRED`），沙箱回收站不可用时报
  `SAFE_DELETE_FAIL_CLOSED … windows-sandbox-recycle-bin-unavailable`。**均非代码回归**——
  用 shell `rm` 预清测试输出目录后重跑即可验证。
- **改锁类型需同步改测试**：`tests/test_concurrency.py::test_ttwid_module_pattern` 断言了凭据锁的具体类型。

## 构建命令

```bash
# 安装依赖
pip install -r requirements.txt

# 打包可执行文件
python build_exe.py              # 标准打包
python build_exe.py --smoke      # 打包 + 冒烟测试
python build_exe.py --no-zip     # 只打包不压缩
python build_exe.py --no-runtime # 跳过 ffmpeg/node（减小体积）
python build_exe.py --dual       # 同时生成 lite + full 两个 zip

# Docker 构建（版本号经 --build-arg 从 pyproject.toml 动态注入）
docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" -t douyin-recorder .
docker compose up -d             # 使用 docker-compose.yaml（APP_VERSION 可由 .env 提供）
```

### 打包与冒烟测试语义（`build_exe.py`）

- 打包入口 `build_exe.py` **一次产出 CLI / GUI / Web 三个 exe + 共享 `_internal/` 依赖**；
  `.github/workflows/build-release.yml` 在 macOS / Windows / Linux 三平台跑 `--smoke` 冒烟测试。
- 冒烟判定规则（改动 `build_exe.py` 时须保持）：
  - `FATAL_MARKERS = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError")`
  - `_finish()` **仅当进程已退出且输出含 FATAL_MARKERS 才判失败**；进程仍存活时输出里的 Traceback
    视为良性（长驻程序运行期可能打印可恢复异常）。
  - GUI 冒烟用 `ignore_patterns=("Failed to dock icon",)` 忽略 headless 环境下 pystray 的良性堆栈。

## 格式化命令

```bash
black .
isort .
mypy src/
```

- **isort 收尾必须清理 `.isorted` 备份残留**：isort 在某些配置下会生成 `*.isorted` 备份文件，
  类型存根表现为 `*.pyi.isorted`（如 `typings/pystray/__init__.pyi.isorted`）。清理命令必须匹配
  `*.isorted`：`find . -name "*.isorted" -delete`。
  ⚠️ 用 `*.py.isorted` **匹配不到** `.pyi.isorted`，会静默漏删并误提交。

## 并发与线程模型

> 本节是全项目并发相关改动的前置知识，涉及锁 / 事件循环 / 信号量的改动必须先读。

### 基础模型

- **每房间一个独立线程 + 各自独立的 `asyncio.run()` 事件循环**：`main()` 为每个 URL 启一个
  常驻 `threading.Thread`（`_room_thread_target` → `start_record`），线程内以
  `asyncio.run(...)` 逐轮驱动异步请求（`main.py` 中上百处）。**不存在共享的全局事件循环。**

### 调度中枢 `src/scheduler.py`（2026-08 定稿）

- 取代旧的「单个全局 `threading.Semaphore(1)` + 只会单向压制的 `adjust_max_request`」模型
  （旧模型下 80 房间共抢 3 个网络槽位，77 线程阻塞 → 严重延迟）。
- `ConcurrencyScheduler` 为中枢：
  - **并发模式（2026-08-24 起）由「最大同时录制数(0为不限制)」是否为 0 决定**（`set_dynamic_mode` 接入，
    `main()` 主循环每轮调用、内部幂等）：
    - **为 0 → 动态调速**（默认）：全局网络并发容量 = `max(配置下限, min(上限, ceil(活跃数 / 缩放因子)))`
      （默认 min=8 / max=128）；错误率极高时**温和降容但永不低于下限**，
      杜绝「错误 → 降容 → 更多超时 → 继续降容」的死螺旋；
    - **非 0 → 固定并发**：忽略动态调速器与错误背压，网络容量恒为「同一时间访问网络的线程数」
      （最小 1 个槽位，热更新即时生效）；同时录制上限（ffmpeg 数）语义不变，仍走 `set_recording_limit`。
    - 模式与容量变化经 logger.debug 播报（`并发模式: 动态调速/固定 …`）；per-key 熔断与并发模式正交，
      固定模式下仍生效。
  - `adjust_loop` 守护循环每 5s 重算容量，**取代 `adjust_max_request`**（固定模式下重算为幂等 no-op）。
  - `main()` 首轮初始化 `scheduler = ConcurrencyScheduler(configured_limit=max_request)`，并把全局
    `semaphore` / `recording_semaphore` 两个 `ResizableSemaphore` 指向其属性。
- `ResizableSemaphore`：支持运行时 `set_value` 调容（增大则唤醒相应数量等待者；减小仅降低上限、
  **不强行回收已持有的槽位**）；`__init__` / `set_value` **允许容量 0**（暂停态）。
- `PlatformBreaker`（按 host 熔断，`closed → open → half-open`）：open 经冷却后放**唯一**探针，
  探针成功 → closed、失败 → 重新 open。按 host 隔离，单平台故障不拖垮其他平台。
  **探针带租约（`_PROBE_LEASE_SECONDS = 60s`）**：探针轮可能以 `continue` 结束且不触发 `record`
  （主播未开播等待轮、`disable_record`、房间线程退出等路径），`_probing` 标志若无租约兜底将
  永不复位 → 该 host 永久熔断直到进程重启；租约超时后 `allow()` 重新授予探针实现自愈，
  删除该租约会重新引入永久熔断（回归测试 `test_platform_breaker_probe_lease_regrants_after_timeout`）。
- **接线点仅限固定几处**（未改动 50+ 平台函数，改动时须维持此边界）：
  - `notify.record_error/record_success` 增 `key` 形参，委托给 `main.scheduler`；
  - `start_record` 入口 `record_host = host_of(record_url)`，且**必须在 `while True` 外层 try 之前
    预置 `record_host = ""`**，否则 basedpyright 判 possibly unbound（外层 except 可在赋值前被触达）；
  - 平台分派前做 `scheduler.allow(record_host)` 预检，False 则退避后 `continue`；
  - `check_subprocess` 的录制循环受 `recording_semaphore` 管控。
- 相关配置项：`最大同时录制数(0为不限制)`（默认 0 = 不限制 → 高容量；键名禁止含 `=`/`:`，
  见「已知坑」configparser 分隔符条目）**兼作网络并发模式开关**（0=动态调速 / 非 0=固定并发，见上）；
  `同一时间访问网络的线程数` 在动态模式下为**容量下限之一**（不再是硬上限），
  在固定模式下即**固定并发限制值本身**（最小 1）。
- **调度模块测试与验证要点**：测试文件 `tests/test_scheduler.py`（共 16 用例，覆盖
  `ConcurrencyScheduler` 容量自适应、动态/固定并发模式切换、`ResizableSemaphore` 调容、
  `PlatformBreaker` 熔断状态机等）。
  改动 scheduler 后须 `pytest tests/test_scheduler.py` 确认。
  注意：全量 pytest 中 `tests/test_twitch_live_collector.py` 会因沙箱
  `windows-sandbox-recycle-bin-unavailable` 安全删除护栏失败，**属既有环境限制，与调度改动无关**——
  见「harness safe-delete 护栏」条目。

### 录制结果反馈约定（2026-08-23 定稿，main.py / src/stream_select.py）

- **`check_subprocess` 须按 ffmpeg 退出码上报调度样本**（`src/check_subprocess` 内 return_code 分支）：
  - `rc == 0`（流正常结束/主播下线）→ `record_success(host_of(record_url))`；
  - `rc != 0`（录制出错）→ `record_error(host_of(record_url))`；
  - **禁止轮末无条件 `record_success(record_host)`**——失败轮次会记成成功样本，稀释按 host 的熔断统计，
    多房间同 host 时熔断阈值永远到不了、坏线路被无限重撞（2026-08-23 实测虎牙房间秒级 403 死循环根因之一）。
- **快速失败（输入打开被 CDN 拒绝）须记入探针退避**：`main.check_subprocess` 内
  `time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS`（模块常量 `20.0`）判为快速失败时，
  从 `ffmpeg_command` 中解析 `-i` 后的实际拉流地址，调用 `stream_select.mark_ffmpeg_reject(url, platform)`
  记入 `_probe_backoff` 退避窗口；下一轮 `select_source_url` 跳过该线路的探针、改试下一 CDN 候选。
  - `mark_ffmpeg_reject` 是 `stream_select` 内的公开入口（委托 `_mark_probe_reject`），`platform` 不在退避
    白名单（`_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)`）时静默无操作，勿扩大到斗鱼等其他平台。
  - ffmpeg 命令缺 `-i`（异常入参）时以 `except ValueError` 捕获、跳过退避标记、仅记失败样本。
  - 慢速失败（`-reconnect_delay_max 60` 耗尽，通常 >60s）：只记失败样本、不记探针退避——该线路
    此前可正常拉流，标记退避会误伤下一轮的候选选择。
- **直下路径（`direct_download_stream`）补成功样本**：成功路径末尾须 `record_success(record_host)`，
  与 ffmpeg 路径语义对齐（失败已在 except 分支有 `record_error`）。
- **解析成功轮即上报成功样本（2026-08-27 定稿）**：`main.start_record` 解析成功分支
  （`port_info["anchor_name"]` 非空）须 `record_success(record_host)`，与解析失败分支的
  `record_error` 对称——此前成功样本仅在 ffmpeg 退出时上报，half-open 探针房间进入长时间录制
  期间同 host 其余房间持续熔断饿死；主播未开播等正常轮次则完全无样本，探针标志永不复位。
  这不是「轮末无条件 record_success」（禁令所指的失败轮记成功样本），而是仅解析真正成功才上报。
- **控制台并发容量显示调度器实时值**：`src/recorder_status._live_network_capacity()` 优先取
  `scheduler.network_semaphore.value`，调度器未就绪时回退 `main.max_request`（旧显示固定打印配置值，
  实测容量 12/20 却显示 3，误导用户认为并发优化未生效）。
- 回归测试：`tests/test_record_failure_feedback.py`（5 用例，覆盖成功/快速失败/慢速失败/无 -i 入参/容量回退），
  `tests/test_stream_select.py::test_mark_ffmpeg_reject_marks_backoff`（退避跨轮新 token 命中 + 非白名单无操作）。

### 锁的强制约定

- **禁止模块级 `asyncio.Lock()` 单例**：它会惰性绑定到首个 `await` 它的事件循环，后续房间的新循环里
  `await` 即抛 `RuntimeError: … is bound to a different event loop`。该异常曾被 `async_req` 的
  `except` 整段吞掉并返回 `""`，进而被 `spider.get_douyin_web_stream_data` 误判成「空响应 → 疑似风控」，
  级联导致 HTML 兜底也失败。正确做法见 `src/async_http.py` 的 `_get_client_lock()`：
  **随当前事件循环缓存 / 重建**（内部 `asyncio.get_running_loop()` 比对后重建），与 `_client_cache`
  的 `(client, loop)` 机制一致。仅单房间运行时锁只绑一个循环、不会报错，**必须并发多房间才能复现**。
- **跨 `await` 持有的跨线程锁一律用 `threading.RLock`，不得用 `threading.Lock`**：凭据去重锁
  （`_ttwid_lock` / `_kuaishou_did_lock` / `_twitch_client_id_lock`，位于 `src/spider.py`、`src/ttwid.py`）
  跨越 `await` 持有；普通 `Lock` 下若同一事件循环出现第二个并发协程，会同线程自旋死锁
  （持锁协程永无法恢复）。`RLock` 使同线程重入退化为一次幂等重复拉取，跨线程去重语义不变。

## 关键约定

1. **版本号同步**: 版本唯一事实源是 `pyproject.toml`，各消费方均动态读取、不再写死。`main.py` 与 `src/web_api.py` 运行时经 `importlib.metadata` 读取（无需修改源码）；`Dockerfile` 通过 `APP_VERSION` 构建参数动态注入；`i18n/zh_CN/LC_MESSAGES/zh_CN.po` 不再写版本号。`README.md` / `CODE_WIKI.md` 为文档，不纳入版本同步/校验。`scripts/check_version.py` 校验上述“动态化”状态
2. **行宽**: 120 字符（black + isort 统一）
3. **导入排序**: isort 使用 `black` profile，`known_first_party = ["src", "i18n"]`
4. **运行时资源**: `config/`, `ffmpeg/`, `node/` 与 exe 保持同级，不进入 `_internal/`
5. **JS 签名脚本**: 位于 `src/javascript/`，通过 `__file__` 定位，打包时收入 `_internal/`
6. **编码与注释风格**: 源文件统一 UTF-8，注释统一用中文
   - **注释一律用 `#` 行注释，禁止 `"""..."""` docstring**：模块/类/函数的说明也写成 `#` 注释置于定义上方。全仓已 100% 满足——`src/` 39 个模块（含 `src/platforms/`）、`main.py`/`gui.py`/`gui_legacy.py`/`web.py`/`i18n.py`/`msg_push.py`、`scripts/`、`tests/` 均为 **0 处 docstring**，新增与重构代码须保持
   - **例外**：多行字符串**字面量**不属 docstring，合法保留（如 `build_exe.py` 的 `SPEC_TEMPLATE = """\...` PyInstaller spec 模板）
7. **排除目录**: `node/`, `ffmpeg/`, `downloads/`, `__pycache__/` 在所有工具中均排除

## 已知坑（避免回归）

- **弹幕 WS 连接必须显式 `proxy=None`**：`src/ws_client.py` 的 `connect()` 必须传入 `proxy=None`，使弹幕 WebSocket 直连服务器、不跟随系统代理（macOS `urllib.request.getproxies()` / `ALL_PROXY` 等环境变量）。一旦改为跟随系统代理，B站/斗鱼等平台会报 `connecting through a SOCKS proxy requires python-socks` 并连接即断。该修复对所有复用 `WsClient` 的平台弹幕连接统一生效，改动此处须保留 `proxy=None`。
- **录制链不得嵌套于 `if headers:` 内**：`main.py` 录制主链（约数百行）曾被整体包裹在 `if headers:` 条件中，导致无自定义请求头时抖音/斗鱼等平台静默不录制（状态显示"正在直播中"却无文件、无报错）。编辑录制流程时，录制链必须位于条件判断**之外**，仅把"是否附加自定义头"作为局部行为；绝不可用该条件包裹整个录制流程。
- **流地址校验 GET 复核的容错语义不得简化**：斗鱼 hw/虎牙 al 等 CDN 对毫秒级连击探针（HEAD→GET）会**偶发** 403（实测同 URL 片刻后重试即 200，ffmpeg 单次 GET 正常）。`src/stream_select.py` 的 `_confirm_get_ok` 必须满足两点：401/403 先原样重试一次再定罪；候选已是末位（`select_source_url` 中无 record_url 备选、或 record_url 本身）时稳定拒绝也仅告警放行、交由 ffmpeg 实际拉流定夺（探针与 ffmpeg 客户端指纹不同）。删掉重试或末位放行会重新引入"探针误杀可用源"（校验假红导致整轮放弃录制）。同语义扩展至两处：m3u8 的 Range-GET 探针 401/403 同样先隔 `_GET_RECHECK_INTERVAL` 重试一次再定罪（斗鱼 hw CDN HEAD=405 后连击 Range-GET 偶发 403，重试即 206——救回 HLS 候选，免疫游客态 FLV 约 70 秒被掐断）；HLS 为唯一候选（无 FLV/record_url 备选）或 FLV 为 h265 不可用时，HLS 即末位、校验须传 `last_resort=True`。
- **斗鱼必须附带 FLV→m3u8 同 token HLS 候选**：斗鱼 H5 接口只返回 FLV，游客态 FLV 长连接约 70 秒被 CDN 掐断（反复分段、I/O error）；而 wsAuth token 对 FLV/HLS 通用，`get_douyu_stream_url` 把路径 `.flv` 改 `.m3u8` 即同 token 的 HLS 播放列表（实测 hw CDN 200 + mpegurl），HLS 逐段拉取免疫单连接超时。该候选由 `select_source_url` 校验 gating、不可达自动回退 FLV，须保留。
- **`real_url` 为空必须跳过录制链**：`select_source_url` 返回 None 时若不拦截，会让 None 流入录制执行链（ffmpeg 参数/scheme 转换处崩溃，或复用上一轮残留命令；斗鱼 hw CDN 全候选探针 405/403 时实测）。必须在选源后 `if not real_url: 告警+等待+continue`。该守卫之后 `now`/`title_in_name` 为无条件赋值（原恒真冗余的 `if real_url:` 包装已移除——嵌套条件包裹录制链属反模式，且曾致 basedpyright 判定 possibly unbound）。
- **末位候选的 content-type 拒绝也须放行**：`_validate_stream_url` 的 text/html 启发式分支与尾部非 200 分支，对 `last_resort=True` 候选必须仅告警放行——斗鱼 hw CDN 对探针 HEAD 回 405+text/html（禁 HEAD 方法），ffmpeg 实际 GET 拉流正常；此前放行逻辑只存在于 `_confirm_get_ok`（401/403 GET 复核），content-type 路径漏放行导致斗鱼整轮放弃录制。
- **B站弹幕 buvid 必须真实、AUTH_REPLY 必须显式校验**：spi 官方端点是 `/x/frontend/finger/spi`（少写结尾 `i` 会 200+空 body，永远 JSONDecodeError）；spi 被风控时的兜底随机 UUID 未在 B站注册，弹幕服务器 AUTH 软拒绝（连接保持、不推弹幕、不断连，表现为"连接就绪"但 0 弹幕）。buvid 获取链按真实注册标识优先排序：进程缓存 → 登录 cookie `buvid3=` → spi → **`www.bilibili.com` 首页 Set-Cookie**（经 cookie_cache，与 spi 不同域名、风控独立）→ 随机 UUID 兜底（标记 is_fallback）。`_decode_packet` 必须校验 operation=8 回应的 code：非 0 时经 `_reject_auth()` 告警+断开+调 `spider.invalidate_bili_buvid_cache()` 失效缓存（被拒 UUID 不可复用，下一轮重新获取，否则死循环）；另有 `_auth_watchdog` 兜底「服务器不回 AUTH_REPLY 的静默拒绝」——进房包发出 8 秒无 code=0 回应按被拒处理，host 切换后旧看门狗作废。
- **虎牙探针退避仅限 `_PROBE_BACKOFF_PLATFORMS` 名单**：虎牙 aldirect CDN 对同一路径短时间连续连接做限流，每轮「HLS 3 连探针 + FLV 2~3 连探针 + ffmpeg 拉流」烧光连接预算——实测形态为校验 `GET 复核重试通过(200)` 后 ffmpeg 立即 403（返回码 3436169992），或拉流数百 KB 被 `Stream ends prematurely` 掐断，录制陷入秒级失败循环、弹幕采集器随录制反复起停（"连接就绪"却 0 条消息）。`src/stream_select.py` 的探针退避（`_mark_probe_reject`/`_probe_in_backoff`，键为 scheme://host/路径 去 query，窗口 60 秒）在观测到 401/403（含重试恢复的偶发）后跳过后续探针：非末位候选直接回退下一候选，末位候选零探针直接放行 ffmpeg 独享连接预算。**绝不可把斗鱼等平台加入名单**：斗鱼 hw 的偶发 403 由既有「重试一次再定罪」救回（重试即 206 保住 HLS-first），负缓存跳过会导致斗鱼回退 FLV（游客态约 70 秒被掐）回归。
- **弹幕监控房间须随录制线程退出而移除**：`DanmakuMonitorHub._rooms` 此前永不删除条目，URL 从 URL_config.ini 移除/注释后房间线程退出，但 Web/GUI 监控页会一直残留"已失效直播间"及其旧弹幕数据。`main.py` 的 `start_record` 在 outer try 的 `finally` 中调 `get_hub().room_stopped(record_name)`（录制态/轮询态/解析失败态的 return 全覆盖），枢纽写 `conn/stopped` 事件、GUI `_danmaku_dispatch` 收到 `state=="stopped"` 后 pop 房间行；同房间重新录制时由 collector `room_started` 重新注册。删掉该清理会重新引入旧房间残留。
- **「已被注释」检查必须在解析之前**：`main.py` 房间线程内层循环顶部（`exit_recording` 检查后）须先查 `record_url in url_comments` 再进入平台解析——原检查点位于解析成功之后，平台接口持续失败（如风控返回空）时永远走不到，线程滞留占用监控位，URL_config.ini 的移除/注释变更迟迟不生效。
- **UA 双端一字不差约定与全库统一基准**：录制拉流链的 UA 存在两组"必须一字不差"的配对——`main.py` ffmpeg 命令默认移动 UA ≡ `stream_select.MOBILE_UA`（校验探针与 ffmpeg 客户端指纹一致，否则校验假红/假绿）；`room.HEADERS` 的 UA 参与 X-Bogus 签名（签名以请求头同一 UA 计算、自洽，改字符串安全但四处须同步：`stream_select.MOBILE_UA`、`main.py` ffmpeg 默认 UA、`room.HEADERS`、B站 H5 接口 UA）。全库统一基准（2026-08）：桌面 Chrome/141（对齐 `room.DESKTOP_UA`）、Edg/141、Firefox/148（rv:148.0）、移动端 `Android 14; Pixel 8` Chrome/141——新增 UA 或升级版本时必须对齐该基准，禁止回落 Chrome≤138/Firefox≤127/SamsungBrowser 等过旧指纹（过旧 UA 是风控按指纹识别的特征之一）。
- **探针节流/抖动语义不得移除**：`src/stream_select.py` 的同 host 探针节流（`_throttle_probe`，`_PROBE_MIN_HOST_INTERVAL=0.35s`+抖动，按 host 全局限速）与重试抖动（`_recheck_delay`，`0.8s+uniform(0,0.7s)`）用于消除两类机器人节奏指纹：多房间并发下同 CDN 的毫秒级连击探针、固定 0.8s 恒定重试间隔。把重试间隔改回固定值或移除节流会重新引入"按节奏识别→误触发 403"的风控误伤（实测虎牙/斗鱼 CDN 均有此行为）。测试侧依赖 autouse fixture 把 `_throttle_probe` 置 no-op（部分用例 patch 整个 time 模块，真实节流的时间差比较会炸）；节流专项测试经 from-import 的真实函数引用绕过 no-op。
- **「禁用SSL证书验证的平台」仅在需要证书校验时生效（FFmpeg 9.0 语义）**：FFmpeg 9.0 起 TLS 证书验证默认开启。`http_config.get_effective_ssl_verify` 的平台覆盖仅在全局 `ssl_verify=True`（http 录制模式，即需要证书校验时）参与读取；https 录制模式全局已禁用、平台覆盖无意义。`main.py` 启动时经 `_sync_ssl_disable_platforms` 把证书异常平台（虎牙直播/B站直播，`SSL_DISABLE_REQUIRED_PLATFORMS`）自动追加至配置键并写回——只追加、绝不移除用户手填项。`update_config_line` 的键匹配为大小写不敏感（与 configparser optionxform 语义对齐），改回精确匹配会导致代码常量（大写 SSL/SMTP）与配置文件行（小写）无法互找。
- **i18n 多格式目录与语言热切换**：`i18n.py` 按语言依次探测 gettext `.mo` → `<lang>.json` → `<lang>.yaml`（zh_CN 用 .mo、en_US/en_GB 用 .json、zh_TW 用 .yaml）；四种目录键集合必须一致（test_i18n.py 强制）。`set_language()` 热替换 `_tr` 供 Web（PUT /api/language）/GUI（侧边栏语言菜单）/main 主循环（每轮重同步）即时切换；语言配置键为 `language`，统一经 `i18n.resolve_language` 解析——留空 → 系统语言（`detect_system_language`：环境变量 → Windows UI 语言 → POSIX locale），键值不可识别或语言目录文件缺失 → 回退 `FALLBACK_LANGUAGE`（en_US）。值经 `normalize_language` 归一（别名表键统一为「小写+连字符」形态）。修改 zh_CN.po 后必须 `python scripts/compile_po.py` 重编译 .mo（测试强制字节级同步）。
- **migu.js 输出契约为完整签名 URL**：2026-08 重写后的 `src/javascript/migu.js` 适配 migu 播放器 v_20260731+ 的 wasm 接口（导入函数 a..l 共 12 个、导出名整体重排：memory=m/malloc=p/CI1=t…CI14=F），并改为输出带 `ddCalcu`/`sv` 参数的**完整地址**（sv 由官网因子接口获取，失败回退播放器内置默认因子）；`spider.get_migu_stream_url` 直接使用该 URL，不再拼接固定 `sv=10010`（已过期）。
- **Node 24 / FFmpeg 9.0 兼容基线（2026-08）**：Node 运行时以 24.19.0 实测为准（全部 JS 签名脚本 + migu.js 通过），Dockerfile 随之安装 Node 24 LTS；FFmpeg 以 9.0 为基线——9.0 移除的 CLI 参数（`-vsync`/`-top`/`-qphist`/`-filter_complex_script`/`-adrift_threshold`）禁止引入，录制命令中的冗余 `-v verbose` 已删除（被 `-loglevel error` 覆盖）。
- **`asyncio.get_event_loop()` 3.14 起不再隐式创建事件循环**：当前线程无循环时抛 `RuntimeError`（≤3.13 为隐式创建+DeprecationWarning）。`src/async_http.py` 的 `close_all_clients_sync`（atexit/信号钩子调用）已改为捕获 RuntimeError 后走引用清理兜底；协程内获取循环一律用 `get_running_loop()`，atexit 类同步清理如需复用已存在的循环，保持「try get_event_loop / except RuntimeError → 引用清理」结构，不要改回裸调用。
- **异常日志必须带异常类型与上下文，禁止裸 `logger.xxx(e)`**：Windows 下 `socket.timeout` / `TimeoutError` 的 `str()` **为空字符串**，`f"...: {e}"` 或 `logger.debug(e)` 会打出空白行，排查时完全失去线索。凡 `except Exception as e:` 的日志一律写成 `f"<动作>: {url} - {type(e).__name__}: {e}"`（`src/async_http.py` 的 `async_req` 已按此修正）。流地址校验失败还须额外输出 `status_code` 与 `content-type`，**禁止静默吞异常**。
- **流地址可达性探测的方法基线**：抖音等 CDN 对 m3u8 的 `HEAD` 常回 4xx（**含 404**）而 `GET` 能正常拉流，故校验逻辑一律「HEAD 非 2xx → Range `GET bytes=0-0` 探测（200/206 判可达）」，**不要只覆盖 400/401/403/405**。同步校验器（`main.py` 的 `_validate_stream_url`）与异步校验器（`src/async_http.py` 的 `get_response_status`）的 **proxy / verify / UA 三者必须保持一致**，否则境外平台（TikTok）直连校验会误判不可达而回退或放弃录制。本条与前述「GET 复核容错语义」「末位候选放行」「探针节流/抖动」「虎牙探针退避」四条互补，不可相互简化。
- **macOS GUI 双重主线程约束（`gui.py`）**：Tcl/Tk 只能跑在主线程（否则 `RuntimeError: Calling Tcl from different apartment`），而 pystray darwin 后端的 `icon.run()` 又会以 `NSApplication.run()` 接管主线程——两者互斥。**唯一正确方案**：主线程先 `tray.run_detached()`（darwin 后端仅 `_mark_ready()` 注册 NSStatusItem、不启事件循环，事件交由 Tk 的 Cocoa 循环分发），再 `root.mainloop()`；**绝不允许把 mainloop 放到子线程**。另有三条配套硬约束：① `run_detached()` 前必须在主线程调 `icon._assert_image()` 预热并置 `icon._icon_valid = True`——PIL 惰性编码器在 PyInstaller 冻结环境下从非主线程首次初始化会原生崩溃（Python 无法捕获），漏置 `_icon_valid` 会让 setup 线程 `visible=True` 触发 `_update_icon()` 清空缓存、重回后台线程 PNG 编码崩溃路径；② `_assert_image` 是 **darwin 后端专有方法**（`_win32`/`_xorg` 无），不要在通用路径调用，AttributeError 会被吞掉导致 Windows/Linux 托盘静默禁用；③ detached 模式退出时先 `icon.visible = False` 再 `icon.stop()`（`_run()` 的 finally 不会执行，状态栏项不会自动移除）。复现需 macOS 冻结构建，Windows 无法验证——改动后务必 `py_compile` 并通过 CI 确认。
- **无控制台环境 `sys.stderr is None`，`logger.add` 前必须判空（`src/logger.py`）**：`pythonw.exe` 与冻结的 `console=False` exe 不分配控制台，`sys.stdin/stdout/stderr` **全为 `None`**。控制台 sink 注册处若裸写 `logger.add(sink=sys.stderr, ...)`，会在模块导入期直接抛 `TypeError: Cannot log to objects of type 'NoneType'`，导致 `gui.py`（经 `src.web_config → src.__init__ → node_install → logger` 传导）在 import 期即静默死亡、窗口化运行无任何窗口也无报错。**这是 pythonw 跑 gui.py 失败的真正根因，与解释器是否一致无关。** 必须 `if sys.stderr is not None:` 才加控制台 sink，无控制台时跳过、由文件 sink 兜底。排查窗口化静默崩溃的标准套路：先在文件最顶部装 `sys.excepthook`/`threading.excepthook` 崩溃落盘+弹窗钩子（见 `gui.py` 的 `_install_crash_sink()`），再顺调用链逐层 grep `sink=sys.` / `print_exc` / `sys.stdout.write` 等 None 敏感点逐一判空。
- **抖音接口风控信号是「HTTP 200 + 空响应体」，不是 4xx**：排查解析失败时**先看 `len(response.text)`**，为 0 基本就是 UA/Cookie 被拒。三条配套事实：① **UA 敏感**——`src/room.py` 模块级 `HEADERS` 是 2020 年三星安卓 UA，`iesdouyin.com/web/api/v2/user/info/` 用它必被静默拒，此类接口一律用 `room.DESKTOP_UA`（桌面 Chrome，版本基准见前述 UA 条目）；② `iesdouyin.com/share/user/<sec_uid>` **已是 JS 反爬壳页**，页面内不再有 `unique_id`，基于该页 HTML 的正则全不可靠——主页 → 抖音号请走 `https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid=<sec_uid>`（取 `unique_id`，空则退 `short_id`）；③ `webcast.amemv.com/webcast/room/reflow/info/` 用占位 `room_id=2` + `sec_user_id` 解析主页**行不通**（返回 `status_code=10011`）。
- **`live.douyin.com` 的 `web_rid` 同时接受数字房间号与抖音号**：`webcast/room/web/enter/` 两者皆可，且 `live.douyin.com/<抖音号>` **不发生重定向**。**不要再写「抖音号需先重定向解析成数字」的逻辑**——那是纯静态分析得出的错误结论，已被实测证伪并删除。另：`main.py` 以 `port_info["anchor_name"]` 为空作为「网址内容获取失败」的判据。
- **弹幕链路接线点与分段命名约定**：`start_record` 各平台分支收集 `record_danmaku_args`（局部变量，**每轮重置为 None**）→ 6 处 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` 全部接线 → `src/__init__.py` 的 `get_danmaku_collector(platform, args, base_filename, segment_seconds)` 创建采集器（实现在 `src/collector.py`）。三条硬约束：① `danmaku_collector.stop()` 必须在 `while process.poll() is None` **循环之外**（提前中断分支另有一次），`DanmakuCollector.stop()` 有 `_stop_called` 防重入、幂等；② 分段文件名——ffmpeg 视频分段模板统一 `_%03d`（FLV 已从 `_%02d` 对齐；音频仍 `_%02d` 但无弹幕），SRT 分片用 `{seg:03d}` 与之对应（`_000.srt` ↔ `_000.ts`），`check_subprocess` 需同时剥离 `_%02d` / `_%03d` 两种占位符；③ 抖音弹幕空 cookie 时在 `DouyinDanmaku.start()`（`src/platforms/douyin.py`）协程内 `await get_ttwid()` 动态获取（采集线程有独立事件循环，可直接 await；进程级缓存），**不再硬编码 ttwid**。配置项 `弹幕分片时长(秒)` 走 `_safe_float(..., 1800.0)`。
- **protoc 生成模块需手写 `.pyi` 存根（`src/proto/`）**：`douyin_pb2.py` 由 protoc 生成（DO NOT EDIT），消息类经 `_builder.BuildMessageAndEnumDescriptors` 动态注入，mypy/basedpyright 看不到 `PushFrame`/`Response`/`ChatMessage` 等属性而报 `attr-defined`。已建 `src/proto/douyin_pb2.pyi` 存根声明被引用的 3 个消息类及字段（继承 `google.protobuf.message.Message` 以获得 `SerializeToString`/`ParseFromString`）。**新增字段引用时必须同步补存根。** 这是 `typings/`（第三方库存根）惯例向项目内生成模块的延伸。
- **config.ini 键名禁止含 `=` / `:` 等 configparser 分隔符**：键名含 `=`（历史键「最大同时录制数(0=不限制)」曾致启动即崩溃）时，**读取侧** configparser 在首个分隔符处截断（`最大同时录制数(0=不限制) = 0` 被解析成键 `最大同时录制数(0` + 值 `不限制) = 0`，永远查不到目标键）；**写回侧** Python 3.14+ 的 `configparser.write()` 对含分隔符键抛 `InvalidWriteError`（实测 3.13 对含分隔符键静默写成功、不抛错，3.14 起才抛——本地 3.13 venv 会掩盖该路径，勿把仅 3.13 失败、3.14 通过的 `test_read_config_value_delimiter_key_no_crash` 误判为回归）。`read_config_value`（`src/config_io.py`）的缺键兜底已硬化为「内存 `StringIO` 完整序列化成功后才落盘 + 捕获 `(OSError, configparser.Error)` 降级 warning + 回滚内存 set」，坏键不再截断配置文件或崩溃——但键名本身必须避开分隔符（括号提示可写 `(0为不限制)` 这类无分隔符形式），`update_config_line`（Web 行级更新）的键名匹配同样依赖此约束。
- **平台专属符号必须 `sys.platform` 字面量门控（mypy 跨平台 CI 检查）**：`ctypes.WinDLL` / `ctypes.windll` 等符号仅存在于 Windows typeshed，而 CI 的 `mypy src/`（mypy 2.3.0）跑在 linux runner 上，且会经 import 链把根目录 `main.py` / `i18n.py` 一并拉入检查（**不在 src/ 下的文件同样被查**）——函数体内裸引用平台专属符号必报 `attr-defined`（2026-08-24 `i18n._windows_ui_language` 的 `ctypes.WinDLL` 即此）。修复模式（仅函数体调用、注解不涉及时）：**函数体首行早返回** `if sys.platform != "win32": return`（对齐 `src/web_tray.py._patch_console_window` / `i18n._windows_ui_language` 惯例）；注解需引用平台符号时降级为 `object | None`（禁用 `sys.platform` 条件类型别名——basedpyright strict 报 `reportInvalidTypeForm`）。**禁用 `# type: ignore`**：Linux CI 下必要、Windows 本地下多余，basedpyright 会再报 `reportUnnecessaryTypeIgnoreComment`，两头不讨好。验证必须双跑：`mypy src/` + `mypy --platform linux src/` 两次全绿才算过；门控条件写反（`==` / `!=` 打错）静态检查发现不了，须运行时用例锁定（见 `tests/test_i18n.py::TestWindowsUiLanguagePlatformGate`）。
- **三参 `getattr` 不做字面量名解析，模块级已声明的属性一律直接访问（mypy Any 泄漏）**：`getattr(obj, "attr", default)` 经 mypy（含 2.3.0）reveal_type 实测返回 `Any | None` 而非属性类型——`warn_return_any` 下返回处报 `no-any-return`，更糟的是后续属性链（如 `.network_semaphore.value`）的类型检查**全部静默失效**（2026-08-24 `src/recorder_status.py::_live_network_capacity` 即此）。凡目标属性有模块级声明（如 `main.scheduler: ConcurrencyScheduler | None`，import 完成即必然存在），直接 `main.scheduler` 访问；确需容错「属性可能不存在」时用 `cast` 显式收窄，勿写防御性三参 getattr。运行时等价性判据：测试只 `monkeypatch.setattr`（属性必存在）而非 `delattr` 时，替换为直接访问安全。
