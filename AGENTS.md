# AGENTS.md — DouyinLiveRecorder 核心约定

> 本文件是项目长期约定的**唯一事实源**：编码规范、架构决策、并发/线程模型、测试规则、构建与格式化流程、「已知坑」均在此收敛。新增长期约定写回对应章节，不得出现第二份事实源。
>
> **可达性约定**：纯参考长段（目录树、一次性实测读数）外迁到 `docs/agent-reference/` 由此处链接指向；约束、门禁命令、风险控制、「已知坑」约束句一律留根文件。判定：每次会话必守的约束留根，「在哪找清单 / 佐证读数」可外迁。
>
> **阅读顺序**：先读「风险控制（前置）」→ 跑门禁时读「格式化命令」→ 动手前读所在主题的「已知坑」。

## 项目概览

- **名称**: DouyinLiveRecorder
- **版本**: 4.5.0（唯一事实源 `pyproject.toml` 的 `version`，动态读取口径见「关键约定」#1）
- **描述**: 支持抖音、TikTok、YouTube、快手等 60+ 平台的直播录制工具
- **许可证**: MIT

## 风险控制（前置）

> 本节只做路由：把越权边界与凭据红线提到最前，细则仍以其指向的条目为唯一事实源。

### 必须停下来交回用户的情形

- **批量重装 venv 依赖**：必须由用户在普通终端执行，沙箱拦截发生在 pip 已开始卸载之后、会清空包目录。命令与分级流程见「CI / workflow 约定」的「venv 依赖修复分级处置」。
- **清理范围越界**：收尾清理只限本次任务自己产生的一次性脚本与 `tests/` 下用例生成的临时输出；运行期产物目录与 `scripts/` 下正式维护脚本一律不动（范围与命令见「测试收尾清理临时脚本」）。
- **删除被 harness safe-delete 拦截**：记下路径、按同节口径逐文件重试；仍删不净时在回复里明确列出残留路径交回用户，**不得静默跳过**。
- **治理式流程技能（vibe 等）需要 run 范围与 artifact root**：先由用户确认，不得把工具安装目录当产物根目录（见「流程编排技能的使用边界」）。

### 凭据与敏感配置红线

- **不得提交 / 外传运行时凭据**：仓库当前保留一份已跟踪的脱敏 `config/config.ini` 基线模板；`.gitignore` 对已跟踪文件不生效，故本地填入 Cookie / 代理 / Web 密码后绝不能提交。`config/URL_config.ini` 与新增同类运行时文件须保持忽略，二者均经 `.dockerignore` 排除、不得进入镜像。
- **写入配置或日志前必须脱敏**：URL / 代理地址一律经 `utils.mask_credentials()`；Web 面板敏感键判定走「节白名单 + 键名正则」双重口径，`'***'` 掩码跳过是写入侧唯一防线（见「已知坑」「凭据与敏感配置脱敏」）。
- **文档与审查记录里不得出现真实凭据**：新增 `CODE_REVIEW_*.md` / `DIAGNOSIS_*.md` 类根目录文档时只写脱敏后的样例值。

## Python 版本

- **最低要求 / 目标 / mypy 检查版本**: Python >= 3.14（`requires-python = ">=3.14"`）。
- **3.14 破坏性变更基线**: `asyncio.get_event_loop()` 不再隐式创建事件循环（后果与整改口径见「并发、事件循环与锁」，此处只登记破坏面）；`pkg_resources`、PEP 594 亡故电池模块已移除；新代码统一走 `ctypes.WinDLL`（对齐 web.py 惯例，而非 `ctypes.windll`）。
- 语法/编译检查一律使用项目 venv 的 Python 3.14（3.13 做 `compileall`/`py_compile` 会误报 PEP 758 语法，见「已知坑」）。

## 代码风格

> Black / isort / mypy 取值摘录自 `pyproject.toml [tool.*]`，配置本体才是事实源；门禁命令见「格式化命令」。

### Black

- **取值**: `line-length = 120`、`target-version = ['py314']`、`include = '\.pyi?$'`；排除 `.git`/`.venv`/`build`/`dist`/`__pycache__`/`.pyc`/`node`/`ffmpeg`/`downloads`/`logs`。
- **except 多异常写法**: 本仓统一写 `except A, B:`（PEP 758 无括号形式，black 两种写法均接受）。统一无括号是**风格约定，不是门禁强制**：新增/修改代码写无括号，**存量带括号写法不要为对齐而批量改动**（会造成无意义 diff）；需要 `as` 绑定时必须回退加括号（`except (A, B) as e:`）；不要为兼容 <3.14 而加括号。

### isort

- **取值**: `profile = "black"`、`line_length = 120`、`known_first_party = ["src", "i18n"]`；排除 `.git`/`node`/`ffmpeg`/`downloads`/`__pycache__`/`*.pyc`。

### mypy

- **取值**: `python_version = "3.14"`；`warn_return_any`/`warn_unused_configs`/`disallow_untyped_defs`/`ignore_missing_imports` 均为 `true`。
- **不带路径参数**：检查范围由 `pyproject.toml [tool.mypy].files` 定义（src/ + 根入口 + build_exe.py + scripts/ + tests/）。显式传参（如 `mypy src/`）会**覆盖**该配置只查 src/；排障可收窄，但**门禁结果以无参数跑法为准**（早期只查 src/ 时，gui.py 的 `logger`/`session_id` 根入口漏 import 长期逃逸）。
- **平台符号门控双跑同样不带路径**：本机裸跑 `mypy` + 另两个平台目标各增跑一次（`mypy --platform linux` / `mypy --platform win32`），使任一主机上都同时覆盖 linux 与 win32 两侧门控分支；CI typecheck job 已按同一 `[tool.mypy].files` 范围、同样不带路径参数补齐该双跑到合并边界（本机实测 win32 与 linux 判定面逐行一致，不与既有 `# type: ignore` 冲突）。判据见「已知坑」平台专属符号条目。

#### typings/ 存根的「仅 IDE 暴露」告警处理（2026-09-24 定稿）

`[tool.mypy].exclude` 含 `typings`，CLI 门禁不查；但 IDE 的 mypy 语言服务器仍实时检查单独打开的 `.pyi` 且不消费 `ignore_missing_imports = true`——「门禁全绿、IDE 单文件红」属 IDE 噪声，不得按门禁失败处理，也不得放任不管。

- **唯一允许的修复方式**：文件级 `# mypy: disable-error-code="<code>"`，写在头部注释块内（先于任何 `import`），并紧跟「为什么不引入 `types-*` 依赖」的说明。
- **不得**为此新增 `types-*` 开发依赖；**不得**在 `pyproject.toml` 加全局 `disable_error_code`；**不得**用行内 `# type: ignore[<code>]`（本项目配置下变 unused）或 `# mypy: ignore-errors` 整文件豁免。pyright/basedpyright 放宽走同目录既有的 `# pyright: ...` 指令。
- **现存量一处**（新增第二处前先复跑枚举命令确认归因）：`typings/execjs/*` 的 `import six` 报 `[import-untyped]`。[历史注] 原② `typings/customtkinter/__init__.pyi` 的 `_CTkWidget` 混入覆盖报 `[misc]`——该存根已随 customtkinter 依赖摘除（2026-10-03 阶段5）整体删除，条目随之消失。[历史注 2026-10-20] `typings/pystray/__init__.pyi` 亦随 pystray 依赖摘除整体删除（删前全仓 `import pystray` 实测 0 处，且该存根头部自述的消费点 `src/web_tray.py` 已迁 `QSystemTrayIcon`）；`typings/` 现只剩 `execjs/` 一个目录，与本条「现存量一处」重新吻合。
- 改完存根后须确认：`mypy`（无参）exit 0、`black --check` 对被改文件 unchanged、`python scripts/check_annotations.py` 通过。

### 注释约定

- **统一使用 `#` 行注释，不使用三引号 docstring**（docstring 进 AST、`#` 注释不进，AST 等价性校验借此证明「逻辑未改动、未误插 docstring」）。
- **写「为什么」而非「做什么」**：边界条件、平台差异、风控信号、降级路径、异常吞没后果、并发与时序假设。三个层次：模块头总览 / 函数级职责 / 关键分支与边界的「为什么」；`src/stream_select.py`、`src/scheduler.py` 是参照。
- **引用代码位置优先写锚点（符号名 / 唯一语句片段），不写 `file:line`**: 行号随同文件增删必然漂移，本仓 2026-10-17 一轮复核就实测到三处根文件引用失效（弹幕链路唯一调用点、`Dockerfile` 运行阶段的 `COPY`、Linux 直下入口的实参位），已全部改为锚点形态。确需给读数时写「实测日期 + 取数命令」，让读者能复跑，而不是留一个会过期的坐标。
- **修改注释只增不改**：不得删除或重写已有解释性注释；需修正时在其下方补充。**例外**：不适用于已被证伪的事实性陈述——源码注释里的错误结论改正原文并压为一行带日期历史注；本文件自身被证伪的条目直接改正文。
- **「更正考古」段可压缩**：多层叠加的修订段落允许压为「当前实测状态 + 一行 `[历史注]`」，但实测读数、主机名/URL、常量名、环境变量名、平台名、判据、并发与时序假设、错误码、真实存在的回归锁用例名一律逐字保留。

### 注释检查工具（scripts/check_annotations.py）

| 命令 | 用途 |
| --- | --- |
| `python scripts/check_annotations.py` | 规范检查（禁 docstring、密度阈值、模块头） |
| `python scripts/check_annotations.py --snapshot DIR` | 建立基线快照 |
| `python scripts/check_annotations.py --baseline DIR` | 与基线比对，证明「只改了注释、未改逻辑」 |
| `python scripts/check_annotations.py --min-density N` | 自定义密度阈值（默认 13.0） |

- 等价性校验：Python 比对 `ast.dump` 全量序列化；JS/CSS/HTML 剥离注释后比对有效代码行。注释与空行不参与。密度检查只对 Python 生效；前端注释按各自语言惯例。
- 排除项：`douyin_pb2.py`（protoc 生成）、`douyin_live_recorder_standalone.py`（历史遗留），以及 `__pycache__/node/ffmpeg/.venv/build/dist` 等目录。
- **三个盲点（工具发现不了，须另行检查）**：
  1. `except A, B:` 与 `except (A, B):` AST 完全相同——无括号被改写成带括号不会被校验发现，`grep -c 'except [A-Za-z_][A-Za-z0-9_.]*, [A-Za-z_]' <file>` 核对。
  2. 注释缩进错误不影响 AST，只有 `black --check` 能发现——必须与 black 配套。
  3. **换行符形态变化对两者完全隐形**：`ast.parse` 把 `\r\n` 与 `\n` 视为同一行尾，black 按文件首个行尾为准。本仓 CRLF/LF 混存（`main.py`/`src/web_api.py`/`gui.py`/`i18n.py` 等纯 CRLF，部分 `tests/*.py` 纯 LF），整文件 `Path.write_text()` 重写会静默转 LF。判据（改任何文件前后各跑一次，两侧「原本为 0 的那项」必须仍为 0）：`python -c "import pathlib;b=pathlib.Path(f).read_bytes();print(b.count(b'\r\n'), b.count(b'\n')-b.count(b'\r\n'))"`。连带后果：按原文匹配 `\n\n` 的断言遇纯 CRLF 源文件恒不匹配（前端 MIN-2241 曾因此长期红，锚点已改 `\r?\n\r?\n`）。

## 项目结构

完整目录树已外迁为纯参考段：[项目结构目录树][struct-tree]；逐模块覆盖率阈值数值不在本文件维护（事实源 `scripts/check_coverage.py` 的 `MODULE_THRESHOLDS`）。

[struct-tree]: docs/agent-reference/project-structure.md

## 项目级 Skill

> 高频复用的领域约定已提取为独立 Skill（位于 `.agents/skills/`），agent 可按需加载详细流程与验证清单。AGENTS.md 仍保留约束语句（must / must-not）作为唯一事实源；Skill 展开操作步骤、事故背景与验证命令。
>
> **表格与目录同源**: 本表须与 `.agents/skills/` 的一级子目录一一对应，新增、合并或删除 Skill 时同批改本表（不在此维护计数，目录本身才是事实源）；核对口径为 `Get-ChildItem .agents/skills -Directory` 的目录名集合与表格「路径」列逐行相等。「触发词 / 场景」列取各 `SKILL.md` frontmatter `description` 自述的触发词，不得凭印象另写。
>
> **目录必须入库（SR-06）**: `.agents/skills/` 已纳入 git 跟踪，`.gitignore` 以 `.agents/*` + `!.agents/skills/` 反选（**必须**用「排除内容物」形态：写成目录级 `.agents/` 会让 git 停止下钻该目录，随后的反选逐字失效——这正是 2026-10-04 审查 SR-06「干净检出必红」的原状）。原因是 `scripts/check_skill_agents_consistency.py` 属 CI required check `ci-summary` 的 `needs`，缺目录退 2 会让整链变红。`.dockerignore` 侧仍整目录排除（镜像不需要 Skill，与入库与否无关）；两个 `.sh` 由 `.agents/skills/.gitattributes` 钉 `eol=lf`，否则仓库 `core.autocrlf=true` 会把 shebang 翻成 `bash\r`。该目录缺失时脚本退 2 是**有意保留**的硬失败，不得降级为 skip 或 0。

| Skill | 路径 | 触发词 / 场景 | 覆盖领域 |
| --- | --- | --- | --- |
| DLR 开发手册 | `.agents/skills/dlr-dev-playbook/` | 新功能/新子系统/新 UI 或产品级行为设计、编写或修改 `tests/` 用例、用户粘贴带 `file:function:line` 的运行时日志、平台专属符号致 Windows 绿而 Linux CI 红、reviewer 断言某段代码有语法错误 | 开发工作流路由（设计先行、测试约定、日志故障分诊、平台类型门控、静态检查判定、工程原则）；命中路由后只加载对应的单个 `references/*.md` |
| ffmpeg 命令构造 | `.agents/skills/ffmpeg-command-construction/` | `ffmpeg`、`-reconnect`、`-segment_format`、`_build_ffmpeg_input_args`、`_build_ffmpeg_output_args`、`_run_ffmpeg_record`、`record_save_type` | `-reconnect*` 位置、`-segment_format` 查表、F-01 四定义点、黄金命令比对 |
| 平台选源流程 | `.agents/skills/platform-source-selection/` | `select_source_url`、`stream_select`、探针/`probe`、`FLV-first`、`QUALITY_MAPPING`、`_PROBE_BACKOFF_PLATFORMS`、`_FLV_FIRST_PLATFORMS`、`trace_error_decorator` | 探针可达性、FLV-first/HLS 排除、画质映射、装饰器契约 |
| 运行时钉定验证 | `.agents/skills/runtime-pin-verification/` | `_PINNED_RUNTIME_SHA256`、`--require-pinned`、`check_runtime_pins`、`_is_pinned`、`_slot_is_gated`、`DLR_RUNTIME_SHA256`、`releases/tags` | 三层防线、官方签名档、三类钉定边界、来源增删三处同改 |
| BrowserSkill（外部工具技能，非本仓领域约定） | `.agents/skills/browser-skill/` | 操作已登录的 Chromium：读取页面、填表、抓取数据、点击流程、UI 回归、验证已部署页面 | `bsk` CLI + 浏览器扩展前置；会话前检查、任务流程、标签页借用与恢复、截图/Canvas、文件工具。借用用户标签页须显式授权，禁止提取 Cookie/token 等凭据 |

### 项目级 Hooks / Commands（生命周期资产）

> 与 Skill 的分工：Skill 展开**怎么做**（判断与步骤），Hook 只做**确定性拦截与即时反馈**，Command 只是短入口。三者都不得另立判据——约束本体仍在 AGENTS.md，改动顺序是「先改本节 → 再改资产」。

| 资产 | 位置 | 触发条件 | 对应约束条目 |
| --- | --- | --- | --- |
| Hook 执行体 | `scripts/agent_hook_guard.py` | `PreToolUse`（Bash）：批量重装 venv 依赖、删除目标命中运行期产物目录或 `scripts/`、无过滤面的递归/通配删除；`PostToolUse`（Write/Edit/SearchReplace/MultiEdit；Bash 内文件写入不在覆盖内，由收尾门禁兜底）：`MUTATION-` 标记残留、`.py` 行尾形态混存、新增 `tests/frontend/*.mjs` 未登记 ci.yml、`build_exe.py` 或 `scripts/check_runtime_pins.py` 变更未跑 `check_runtime_pins.py` | 「风险控制（前置）」、「CI / workflow 约定」的 venv 分级处置、「测试收尾清理临时脚本」、「变异验证…当轮还原」、「注释检查工具」三个盲点、「测试」的 `.mjs` 登记、「项目级 Skill」运行时钉定验证 |
| Command 入口 | `.qoder/commands/dlr-dod.md` → `/dlr-dod` | 用户显式请求按完成定义逐条验收 | 「完成定义（Definition of Done）」1→6；只引用入口命令，**不得**复制门禁清单 |

- **`.qoder/` 属本地工具目录**（`.gitignore`/`.dockerignore` 已忽略，见「CI / workflow 约定」的 dockerignore / gitignore 同源条目），故这两项资产**不随仓库分发、不得进镜像**；换机器后重建注册：Hook 执行体在 `.qoder/settings.json` 的 `hooks.PreToolUse`（matcher 盖 Bash）与 `hooks.PostToolUse`（matcher 盖 Write/Edit/SearchReplace/MultiEdit）两个入口，均指向上表脚本。接线与判据的一致性由 `tests/test_agent_hook_guard.py` 钉：受保护目录集合与「运行期产物目录」枚举逐项比对，资产缺失时 skip 而非伪绿。
- **Hook 只判不改，出口能力由事件的生命周期点决定**（与 provider 文档 https://docs.qoder.com/extensions/hooks 的 Blockable 列同源）：`PreToolUse` 可阻断——命中时以退出码 2 阻止命令执行并把理由经 stderr 回给 agent，这是写入/执行前真正能拦的一站；`PostToolUse` **非阻断**——写入已发生、不可撤销（官方退出码表注明 exit 2 的 stderr 注入仅对 blockable 事件生效），故命中时以退出码 0 + stdout JSON `hookSpecificOutput.feedback` **即时回传**，职责是提示 agent 当场修，不得把「拦下」的声明套在这一站。「变异验证…当轮还原」等约束的真正切断点因此不在 Post 一站，而落在仍可判红的收尾门禁（`run_gates.py` / `tests/test_test_hygiene.py` 的 R8 全仓扫描 / CI）：feedback 被忽略时由它们在入库前兜住。两站均**不得**代替用户决定「该不该清理」（越界一律停下来交回用户）；事件形态不认识时一律放行（fail-open）——Hook 坏掉不能演变成「agent 什么都做不了」，那会把工具故障伪装成代码不合格，质量判定仍由 `run_gates.py` + CI 承担。[历史注] 旧版本对 Pre/Post 统一声明「命中时以退出码 2 拦下」，2026-10-02 经 provider 文档证伪后改为上述双轨口径。

## 入口点

| 命令                    | 模块          | 说明       |
| --------------------- | ----------- | -------- |
| `douyin-recorder`     | `main:main` | CLI 录制核心 |
| `douyin-recorder-gui` | `gui:main`  | 图形界面     |
| `douyin-recorder-web` | `web:main`  | Web 管理面板 |

## 依赖管理

- **运行时依赖**: `pyproject.toml [project.dependencies]` 与 `requirements.txt` 保持同步（18 条，2026-10-20 复核，两侧包名集合逐项相等；`customtkinter` 已随 UI 现代化阶段5 摘除，`fastapi`/`pydantic` 已随 Web 后端阶段2 移除，`PySide6` 随 GUI 窗口层迁移于 2026-10-17 加入，`pystray`/`Pillow` 随两入口托盘统一迁 `QSystemTrayIcon` + `QPainter` 自绘于 2026-10-20 摘除，`python-multipart` 同日摘除——其声明理由「Web 接口接收配置上传」对应的接口并不存在，全仓无 `.form()`/`UploadFile` 调用点、`web/` 前端亦无 `FormData`/`<input type=file>`/`enctype`）。回归锁：`tests/test_regression_2026_09_22_gates.py`。
- **开发 / 构建 / GUI 依赖**: `pip install .[dev]`（pytest / pytest-asyncio / pytest-cov / black / isort / mypy / pre-commit 七条，配套根目录 `.pre-commit-config.yaml`）/`.[build]`（PyInstaller>=6.10.0）/`.[gui]`（PySide6 一条）；三者均不进运行时清单。[历史注] `.[gui]` 原含 customtkinter，2026-10-03 阶段5 随 UI 现代化摘除（tkinter.ttk 自研控件层替代）；2026-10-17 阶段6 后窗口层迁 PySide6，本 extra 随之增列；2026-10-20 `pystray`/`Pillow` 随两入口托盘统一迁 Qt 摘除（与 `[project.dependencies]` 同批），本 extra 回到单条。
- **i18n 依赖**: PyYAML（zh_TW.yaml 加载；缺失时仅损失 YAML 格式）。
- **GUI 包版本下限（须与 `requirements.txt` 和 `pyproject.toml [project.dependencies]` 三处一致）**: `PySide6>=6.12.0`（2026-10-20 起本项只剩这一条）。[历史注] 原三包含 `customtkinter>=6.0.0`，2026-10-03 阶段5 摘除（运行时清单与 `.[gui]` 同批）；2026-10-17 随窗口层迁 PySide6 增列 `PySide6>=6.12.0`，本项由两包回到三包；2026-10-20 `pystray>=0.19.5` 与 `Pillow>=12.3.0` 随两入口托盘统一迁 `QSystemTrayIcon` + `QPainter` 自绘而摘除（取数命令登记在 `requirements.txt` 的 GUI 段注释里），三包回到一包。
- **安全下限（清单只写下限，抬下限消除「声明区间含已知受影响版本」风险）**: `starlette>=1.3.1`（CVE-2026-48710 受影响 <=1.0.0，叠加 PYSEC-2026-2280/2281/248/249 两轮抬升，2026-09-21 定稿）、`urllib3>=2.8.0`（显式声明，requests 传递依赖且同步出站 HTTP 穿过它，CVE-2026-44431 定下限 2.7.0，2026-10-01 由 `deps-audit`「下限复核」抓出 CVE-2026-97687/97688/97689 均影响 2.7.0、修复于 2.8.0 后抬升）、`h2>=4.4.1`（PYSEC-2026-3628 / GHSA-6hr6-w5qg-qmwg 重复 Host 头致请求走私，2026-09-26 由 `deps-audit`「下限复核」抓出）。`requests>=2.34.2` 已高于修复版本（[历史注] 原与本句并列的 `python-multipart>=0.0.32` 已于 2026-10-20 摘除——无消费点，判据见上「运行时依赖」条）。`pip-audit` 属 CI 审计工具，**不得**进 `requirements.txt`/`[project.dependencies]`；出现新公告优先抬下限而非 `--ignore-vuln` 白名单，新增/上调下限时跑一次 `deps-audit`。
- **前端测试零 Python/npm 依赖**: `tests/frontend/*.mjs` 用 Node 内置 `node:test`，只需系统 Node.js（与 JS 签名脚本共用运行时）。
- **依赖缺失排查**: venv 缺 `brotli`/`protobuf` 等表现为**测试收集期** `ModuleNotFoundError`，先核对 `pip list` 与 `requirements.txt` 差异再怀疑代码；pip 走本地代理被拒时用 `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>` 绕过（装完出现「目录破损」按「CI / workflow 约定」分级处置，不要直接重试 pip）。

## 测试

- **pytest 配置**（`pyproject [tool.pytest.ini_options]`）: `testpaths=["tests"]`、`python_files=["test_*.py"]`、`python_classes=["Test*"]`、`python_functions=["test_*"]`、`asyncio_mode="auto"`。
- **质量门禁（须保持）**: 命令一律取「格式化命令（门禁唯一基准）」一节，**不得在此重述路径参数**——显式传参（如 black/isort/mypy 传 `tests/`）会覆盖 `[tool.mypy].files`，等于缩小覆盖面。判定口径：`pytest` 0 警告 + black/isort/mypy 全绿 + `basedpyright` 0 error/0 warning（本地补充门禁，见其专节）。
- **pytest「0 警告」口径**: warnings summary 为空（0 条）。第三方库告警一律经 `pyproject.toml [tool.pytest.ini_options].filterwarnings` 显式 ignore 并附来源注释；**禁止用 filterwarnings 掩盖项目自身告警**，禁止给用例加宽泛过滤。协程类 RuntimeWarning 由 GC 延迟触发、ignore 拦不住——必须修根因（见「已知坑」跨循环关闭 AsyncClient）。
- 覆盖率源码 `src/`、排除 `tests/`/`__pycache__/`/`node/`/`ffmpeg/` 等（与 `.gitignore`/`.dockerignore`/pyproject 同源）；门禁：`python scripts/check_coverage.py`（阈值事实源 `MODULE_THRESHOLDS`）。
- **前端用例（`tests/frontend/*.mjs`）**: Node 内置 `node:test` + `node:vm` 沙箱驱动 `web/app.js`，零 npm 依赖；由同名 Python 包装用例以子进程 `node --test` 调用，Node 缺失时 skip。新增前端用例沿用「`.mjs` 真用例 + `.py` 包装」双文件结构。
- **新增 `.mjs` 必须同批登记进 `ci.yml`「Gate frontend tests not skipped」的 node-id 清单**: `node --test <文件>` 只跑被点名的文件、不会顺带发现同级其他 `.mjs`，包装写了但不进清单＝该文件的全部锁在正常 CI 中从不执行（M-28 实证：`test_motion.mjs` 的动效降级/清理锁长期空转）。该清单同时是「node 缺失时整体 skip 不被 ci-summary 区分」的第二道防线；新增包装只加 id，**不得**动 `python_build`/`node_version` 常量。完备性由 `tests/test_ci_frontend_registration.py` 机检（枚举 `tests/frontend/*.mjs` 与该清单求双向差集，不另建第二份清单），本机 Hook 只是即时反馈通道，不能替代它。

- **`tests/` 下不得有「收集 0 条」的 `test_*.py`**（2026-10-18 定稿，由 `tests/test_test_hygiene.py` 的 **R9** 机检，起因是 CODE_REVIEW MT-02）：全文没有 `test_` 前缀函数/`Test*` 类方法的文件，pytest 收集 0 条、报告里连一行用例名都不出现，「整轮全绿」在这里的真实含义是「这个文件什么都没跑」，文件内的真机断言可无限腐烂而不报错——与假绿同级且更难发现。判据取 AST 而非真跑 `--collect-only`（后者要 import 每个模块，会经 `tests/conftest.py` 的 autouse fixture 拉起整份运行时依赖，见「跑 pytest 的 job 必须装齐 requirements.txt」条）。例外表 `_R9_ZERO_COLLECTION_SANCTIONED` 按「文件 → 为什么 0 收集是设计使然」登记且**双向相等**：新增 0 收集文件必须先入表给理由，已补用例却赖在表里同样判红。现登记 6 个（4 个双模真机 collector + 2 个斗鱼手动探针），其中两个 douyu 探针**待改造**为离线收集型用例（参照 MT-02 定稿后的 `tests/test_bilibili_danmaku.py` 形态），不得长期赖在表里。新增此类文件时**优先**按 MT-02 的形态写离线用例，而不是进来加一行表。
- **创建/更新测试**: 按「源码分析 → Mock 配置 → 验证执行」编写；新建用例与被测模块同名（`src/x.py` ↔ `tests/test_x.py`），并用变异验证证明用例真能抓回归（删掉生产实现用例应变红）。**变异验证必做**：新增安全不变量类用例（黄金快照、`-reconnect*`/`-segment_format` 回归锁、节流/锁/退避）；**免做**：仅调整既有断言或新增已被完整覆盖的平凡用例。

### 测试编写强制约定

- **环境变量一律用 `monkeypatch.setenv/delenv`，禁用 `patch.dict(os.environ)`**: `patch.dict` 整体快照 `os.environ`，harness 注入的 `CODEBUDDY_MCP_CONFIG` 膨胀超 32767 上限写回即抛 `ValueError`。`monkeypatch` 只动单个 key。已有 `_clear_proxy_env(monkeypatch)` helper。
- **patch `main.py` 的 subprocess 必须替换 main 的全局引用，且 `FakePopen` 必须是类并定义 `__class_getitem__`**: 禁 `monkeypatch.setattr(main.subprocess, "Popen", ...)`（会波及 harness 守护线程）。正确：`shim = types.SimpleNamespace(**vars(subprocess))` → `shim.Popen = FakePopen` → `monkeypatch.setattr(main, "subprocess", shim)`。`__class_getitem__` 不可省：`check_subprocess` 内层 `proc: subprocess.Popen[bytes]` 在 `def` 时求值（`main.py` 未启用 `from __future__ import annotations`）。
- **真机 collector 脚本（`tests/test_*_live_collector.py`，bili/douyin/douyu/huya/twitch 共 5 个）是「独立运行 + pytest 收集」双模式，四条模板约束缺一即污染全量运行与 CI**（由 `tests/test_test_hygiene.py` 的 R7 逐条 AST 机检）: ① 执行体必须包在 `if __name__ == "__main__": main()` 内——`pyproject` 的 `python_files=["test_*.py"]` 会 import 每个 `test_*` 文件，模块级语句在**收集期**就真连平台、`time.sleep(20)`、清空 `tests/_out_live`、失败路径 `sys.exit(1)` 直接终止收集；② 模块级零副作用；③ `int(sys.argv)` 守卫必须两步式——单行式（只判 `not sys.argv[2].startswith("-")`）**已被实测证伪**：`pytest a.py b.py` 一次点多个文件时 `sys.argv[2]` 是下一个测试文件的路径，不带 `-` 前缀会被放行，`int(路径)` 抛 ValueError、该模块收集直接 ERROR（2026-09-30 实测 4 errors during collection）；定稿形态 `_SECONDS_RAW = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else ""` → `SECONDS = int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else N`；④ 清理输出目录必须按平台前缀 + 先判类型。**取证口径**：`python -m pytest tests/<脚本> --collect-only -q` 必须秒级返回。[2026-10-18 证伪改正] 本句原写「必须秒级返回**且 collected ≥ 1**」——同轮实测五个脚本里只有 `test_twitch_live_collector.py` 产出 ≥1 条用例，其余 4 个（bili/douyin/douyu/huya）一律 `no tests collected`，即该判据的后半句从来不成立；本条真正要防的是**收集期副作用**（连真机、sleep、清目录、sys.exit）而不是收集数，故改正为「秒级返回」，4 个 0 收集脚本按 `tests/test_test_hygiene.py` 的 R9 例外表登记理由。五个脚本一律带守卫结构锁。
- **替身禁止裸赋值共享模块属性；进程级 stdlib 替身必须走被测模块命名空间的 shim**: `spider.async_req = fake` 不还原会让同会话后续任何带 `data=` 的调用撞上残缺假签名（M-25）；`monkeypatch` 解析到的是**全进程唯一**的 os 本体，窗口内 loguru 与其它后台线程的删除/重命名一并被替换（M-27，其中一个替身还把删除变成 no-op）。正确形态：`types.SimpleNamespace(**vars(os))` → 只覆盖所需属性 → `monkeypatch.setattr(<被测模块>, "os", shim)`，与本文件 subprocess 的 shim 约定同构。**落进命名空间的 shim 还要按「对象/路径」收窄破坏面**：挂到模块属性只保证「事后还原」，不保证「窗口内只有本用例受影响」——别的用例的后台线程（边车写线程、弹幕 tail 线程、stats 自注销线程）会在窗口内走进同一支替身。2026-10-18 全量 `pytest` 实测：L-18 的 `dm.os.replace` 故障替身被 `tests/test_danmaku_monitor.py` 在途线程喂进别家 `tmp_path`，`attempts` 由 1 变 5（单文件跑恒绿、整包跑红），且反向把别人的轮转一并打坏。形态：`if src != path: real_replace(src, dst); return`（只对本用例的目标对象制造失败，其余透传真实实现），记账同样只记本对象。
- **并发用例的线程 join 之后必须断言该线程已退出**（2026-10-18 定稿，由 `tests/test_test_hygiene.py` 的 **R10** 零容忍机检）：`t.join(timeout=15)` 既不看返回值也不查 `is_alive` 时，被测逻辑真死锁 → join 超时返回、`errors` 为空 → 用例照样全绿，而「死锁」恰恰是这批并发用例唯一要防的东西（同轮 LT-01/02/03/04 与 MT-04 五批实例）。形态：`t.join(timeout=N)` 后 `assert not t.is_alive()`，多线程用 `alive = [t.name for t in threads if t.is_alive()]` + `assert not alive, f"...: {alive}"`（参照 `tests/test_cookie_cache.py:316-353`）。判据粒度是**函数**——join 与 `is_alive` 必须落在同一个函数体内，别处的一句断言不算数。识别口径刻意保守（只认 `X = Thread(...)` 与由 Thread 填充的容器迭代变量），因此 `"\n".join(lines)` 与 `queue.Queue.join()` 不会被误报；代价是跨文件传进来的线程句柄会漏报，那部分由 code review 承担。存量 18 处违例已于 2026-10-18 全部补齐，本条不设例外表。
- **平台分流链路的打桩点必须覆盖全部分支（Windows 本机全绿 ≠ CI 会绿）**: `_send_stop_signal_and_wait` 按平台分流（win32 `_send_ctrl_break_to_child` / POSIX `os.kill`），替身只桩 win32 侧时 Linux CI 上记账恒空、停止链因失去模拟耗时而瞬时完成（`sleep(0.05)` 后在途线程已结束），「恰一次附着」「复用在途线程」判据整体落空——2026-10-01 实测 CI 4 failed、本地全绿。POSIX 侧 stdlib 替身按上一条 shim 口径执行（参照 `tests/test_gui_stop_exit_singleflight.py`）。
- **变异验证的一次性改动必须当轮还原，并给改动行加 `MUTATION-<短id>` 标记**: 2026-09-30 实测事故——变异残留 `pass  # MUTATION-…` 留在生产代码里，`seg_resp` 未赋值 → `UnboundLocalError` 被外层 `except Exception` 当「探测异常」吞掉 → 末位候选 `return True`，**内网地址被交给 `ffmpeg -i`**。这类残留对 black / mypy / 注释检查**三面全隐形**（语法合法、类型不报错、注释反而更多），只有用例真跑到那条分支才现形。硬约束三条：① 优先用「内存备份→改写→跑→按字节还原」的单进程手法，`finally` 里还原并断言 `read_bytes()==原字节`；② 必须留盘标记，收尾由 `tests/test_test_hygiene.py` 的 **R8** 全仓扫描（标记字面量在守卫内刻意拆写以免自指，且自带「遍历面 > 200 个文件」的防空转断言与磁盘级反向见证）；③ 并行工作包被中断时，接手方第一件事是 `grep -rn` 标记 + `compileall` + 门禁，而不是假设实现已完成。
- **安全边界不得再用「正则钉源码字面量」的 `doesNotMatch` 文本锁**: 契约一反转就静默空洞成立（M-26 实证：前端钉旧实参名与旧 403 文案，生产实参已改名、文案已改，断言因字面不一致而永久「通过」，Python 侧锁的恰是**相反**的新契约，全绿给出错误信心）。一律改**行为锁**；确需结构锁时钉不变量（谁被调用、请求带不带凭据），不要钉某个变量名。
- **harness safe-delete 护栏按轮次计删除配额**: 测试内 `os.remove` 可能被拦（`SAFE_DELETE_BULK_CONFIRM_REQUIRED` / `SAFE_DELETE_FAIL_CLOSED`）。**均非代码回归**——预清测试输出目录后重跑即可。清理范围只限 `tests/` 下由用例生成的临时输出，**不要**删 `downloads/`/`logs/`/`backup_config/`（清理命令见「测试收尾清理临时脚本」）。
- **「文件只读」用例不能只靠 `chmod(0o444)`**: `config_io.py`/`utils.py` 写回均走 `_atomic_write_text`（同目录临时文件 + `os.replace`），而 `os.replace` 只校验目标**所在目录**写权限。正确做法：`monkeypatch.setattr(config_io.os, "replace", deny)` 对目标路径抛 `PermissionError`，其余透传真实 `os.replace`，跨平台稳定复现（`test_read_config_value_missing_key_readonly_ok` 即此坑）。
- **改锁类型需同步改测试**: `tests/test_concurrency.py::test_ttwid_module_pattern` 断言凭据锁具体类型。
- **测试产物一律走 `tmp_path`**: 不得写导入期 makedirs 的会话级共享目录（避免多 pytest 会话重叠竞态，全量红、单文件绿）。`tests/_out_live` 由 5 个 live_collector 手跑真机验证时写，但会被任意会话退出清掉，要留存得先复制出去。
- **`pytest.importorskip` 必须探测真正要 import 的**子模块**，并显式传 `exc_type=ImportError`**: pytest 9.1 起它的 `exc_type` 缺省值由 `ImportError` 改为 `ModuleNotFoundError`（见 `_pytest.outcomes.importorskip` docstring 的 `versionchanged:: 9.1`），而带原生扩展的包缺**系统库**时失败点在其子模块的 `dlopen`（ubuntu runner 无 `libEGL.so.1` → `from PySide6.QtGui import ...` 抛 ImportError），顶层 `import PySide6` 仍成功 → 只探测顶层包时这行恒成立，紧随其后的 import 以 collection error 形态**中断整轮 pytest**（2026-10-18 CI 实测：4337 collected / 2 errors → Interrupted，rc=2，其余用例一条没跑、覆盖率 xml 与逐模块门禁全部拿不到数据）。形态：`pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError, reason=...)`。
- **上述降级必须有环境侧对称措施，不许只靠 skip 收场**: 「包装得到、系统库没有」这类依赖要在 CI 把系统库补齐（Qt 运行库清单见 `ci.yml` 的 `Install ffmpeg + xvfb + Qt runtime libs (apt)` 步骤），并配一道**收集侧**闸门关闭「整模块 skip 而 rc 仍为 0」的假绿（形态见 `ci.yml` 的 `Gate Qt GUI tests are collected`，判 `--co -q` 输出里有无 `skipped` / `no tests collected`）——只依赖 importorskip 时 skipped 与 passed 在 ci-summary 里不可区分。闸门判收集而非判运行：运行态「有 skip 即红」会被函数级的合法降级误伤（`tests/test_gui_qt_window.py::test_language_switch_retranslates` 在语言目录未装载时 skip 是对的）。

### 测试收尾清理临时脚本

- **收尾必须删除任务中生成的一次性脚本与产物**：前缀分三类——`_tmp_`/`tmp_`（通用临时）、`mock_`（桩服务/模拟器）。残留会污染 `git status`、被 mypy 收编（`[tool.mypy].files` 含 `scripts/`/`tests/`）、误导协作者。**任务收尾一律删除**，不留「下次可能还用」。
- **优先写在仓库之外**: 落 `%TEMP%`/`/tmp` 或 `tempfile.mkdtemp()`；确需写在仓库内者用完即删，统一前缀命名；需长期复用才进 `scripts/`。
- **清理范围与禁区**: 只删本次任务产生的临时脚本与输出；**不要**删 `downloads/`/`logs/`/`backup_config/` 运行期产物目录、**不要**动 `scripts/` 下正式维护脚本。清理前 `git status --short` 列出未跟踪文件，对 `.workbuddy/` 等 gitignore 目录显式枚举后确认再删；被 safe-delete 拦截时逐文件重试或列出残留交回用户，**不得静默跳过**。

```powershell
# Windows PowerShell（代理沙箱 Git Bash 有 coreutils，POSIX 段亦可执行）
Get-ChildItem -Recurse -File -Include *_tmp_*.py,tmp_*.py,mock_*.py,*_tmp_*.txt,tmp_*.txt |
  Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' } | Remove-Item -Force
```

```bash
# POSIX / Linux CI
find . -type f \( -name '*_tmp_*.py' -o -name 'tmp_*.py' -o -name 'mock_*.py' \
  -o -name '*_tmp_*.txt' -o -name 'tmp_*.txt' \) -not -path '*/.venv/*' -delete
```

## 构建命令

```bash
pip install -r requirements.txt
python build_exe.py              # 标准打包
python build_exe.py --smoke      # 打包 + 冒烟测试
python build_exe.py --no-zip     # 只打包不压缩
python build_exe.py --no-runtime # 跳过 ffmpeg/node（减小体积）
python build_exe.py --dual       # 同时生成 lite + full 两个 zip
docker build --build-arg APP_VERSION="$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")" -t douyin-live-recorder .
docker compose up -d
```

### 打包与冒烟测试语义（build_exe.py）

- 打包入口一次产出 CLI / GUI / Web 三个 exe + 共享 `_internal/`（`.github/workflows/build-release.yml` 的 build job 逐平台跑 `--smoke`；平台数与 runner 标签以同节「CI / workflow 约定」的「**发布矩阵为四平台，runner 标签↔运行时键的映射单点登记**」条目为唯一事实源，此处不重复列举）。
- 冒烟判定：`FATAL_MARKERS = ("Traceback (most recent call last)", "ModuleNotFoundError", "ImportError")`；`_finish()` 仅当进程已退出且输出含 FATAL_MARKERS 才判失败（进程存活时 Traceback 视为良性）；GUI 冒烟用 `ignore_patterns=("Failed to dock icon",)` 忽略 headless 良性堆栈。

### 产物体积门禁（2026-09-24 定稿）

- **度量侧唯一入口**: `python scripts/report_bundle_size.py dist/DouyinLiveRecorder`（`--top N`/`--json F`/`--compare F`/`--strict`）。体积结论**只以本机实跑为准**，不估算。
- **排除侧唯一入口**: `build_exe.py` 的 `BLOAT_EXCLUDES` 由 `SPEC_TEMPLATE` 生成 `excludes_bloat` 挂在**三个** Analysis 上（必须三处都挂，否则合并去重后等于没排）。新增排除项准入：① 指出运行期不可达；② 复测体积；③ 本地 `--smoke --no-runtime` 三入口通过。判据是「不可达」不是「看着没用」。
- **已知体积大头（固定成本，不可删）**: `python314.dll`、`libcrypto`/`libssl`（HTTPS）、Tcl/Tk（GUI）三项一律按固定成本对待。逐文件 MB 读数与 `pydantic_core` 口径失效史见 [体积读数]；新合计须本机复测后填写。
- **已评估未采纳（勿重复提议）**: ① `strip=True`——Windows 无 strip 可执行文件；② `upx=True`——提高杀软误报率，本产物未签名。

[体积读数]: docs/agent-reference/measured-evidence.md#产物体积大头读数

### CI / workflow 约定

- **网络安装重试统一走 `.github/actions/retry` 复合动作**（线性退避），禁止在 job 内重新内联 `for i in 1 2 3` 重试循环；核对 `grep -c 'uses: \./\.github/actions/retry' .github/workflows/<file>`。
- **actions 大版本基线 v7**: `checkout`/`setup-python`/`setup-node`/`upload-artifact` 统一 v7；第三方非认证动作的 ref 口径见「已知坑」MIN-17。
- **版本常量跨 workflow 同值**: `python_build`(3.14) 与 `node_version`(24) 在 ci.yml 与 build-release.yml 各自声明，改一处须同步另一处。
- **触发与并发策略区分**: ci.yml 限 main 的 push/PR + `cancel-in-progress: true`；build-release.yml 由 `v*` tag 触发 + `cancel-in-progress: false`。
- **发布矩阵为四平台，runner 标签↔运行时键的映射单点登记**: `.github/workflows/build-release.yml` 的 `matrix.include` 含 `windows-latest`/`ubuntu-latest`/`ubuntu-24.04-arm`/`macos-latest`（`platform` 依次 `windows`/`linux`/`linux-arm64`/`macos`），一次发布产出 4 ×（lite+full）= **8 个 zip**，`Verify artifact completeness` 的判据随之为 `-lt 8`。**runner 标签↔运行时键映射的唯一登记点是 `scripts/check_runtime_pins.py::RUNNER_TO_RUNTIME_KEY`**，新增 runner 必须同批登记，否则该脚本按「未登记标签」走 `sys.exit(2)`（属「门禁本身失效」档，发布链在 prepare 即断、根本走不到构建）。矩阵条目的**插入位置也是契约**——`_runtime_matrix_keys()` 按 `os:` 行出现顺序返回键列表，`tests/test_check_runtime_pins.py::test_workflow_matrix_and_test_constant_stay_in_sync` 断言与 `_MATRIX_KEYS` **逐序相等**而非集合比较。Linux 两支共用家族判定 `if: startsWith(matrix.platform, 'linux')`（装 ffmpeg+xvfb 与 `xvfb-run` 冒烟两步），取反那步的标量**必须带引号**写成 `if: "!startsWith(matrix.platform, 'linux')"`：YAML 把行首 `!` 当 tag 指令，无引号实测 `ParserError`。
- **多架构镜像只走「原生双 runner 各出一层 + imagetools 按 digest 合成」**: `.github/workflows/docker-publish.yml`（仅 `v*` tag 触发、推 GHCR）由 `docker-build-amd64`(`ubuntu-latest`) 与 `docker-build-arm64`(`ubuntu-24.04-arm`) 各推一个**分架构临时 tag**，merge job 用 `docker buildx imagetools create` 按两个构建 job **提升到 job 级 `outputs:` 的 digest** 合成 `latest` 与版本 tag——漏提升时 `needs.*.outputs.digest` 取到空串、合成步骤报无效引用而构建本身全绿。**禁止单 job QEMU 交叉双平台**：本镜像构建期含 `apt install ffmpeg/nodejs` + `pip install -r requirements.txt`，QEMU 下模拟 aarch64 是整层重活。凭据固定为自动注入的 `GITHUB_TOKEN`，发布链**不得**引用任何其它 `secrets.*`；`latest` 只能由 `v*` tag 推出，**不得**为「方便重跑」加回 `workflow_dispatch`/`schedule` 覆盖它的口子（那等于把不可变发布物变成可反复改写的别名）。结构锁 `tests/test_docker_publish_workflow.py`（12 条，含两处 `provenance: false` 承重与「`:latest` 全清单恰一次」）。GHCR 匿名 `docker pull` 另需把包可见性设为 **public**，那是仓库设置层面的一次性人工动作，`GITHUB_TOKEN` 不会代为放开。
- **dockerignore / gitignore 同源约定**: 本地工具生成目录（`.mimosa/`/`.qoder/`/`.qoder-credits/`/`.agents/`/`.pnpm-store/`/`.npm-cache/`/`.dsh-validation/`/`.ego-browser-test/`/`.plugin-src/`/`.tmp-dps-extract/`/`.v2c/`/`.superpowers/`/`pytest-cache-files-*/`）与运行期产物目录（`downloads/`/`recordings/`/`logs/`/`backup_config/`）须在两份 ignore 文件与 pyproject 各工具排除列表（black/isort/mypy/basedpyright/coverage）同步维护，漏一处即「未跟踪目录 / 误入镜像 / 工具误扫描」。`.superpowers/`（SDD/治理式流程技能的工作区，含 brief/report/review/diff 与运行日志快照）2026-10-03 前四处均未登记，实测后果正是这三种形态的第三与第一种：被 `black`/`check_annotations.py` 扫进仓库面（Python 文件数 216→203），且 `Dockerfile` 运行阶段的 `COPY --chown=recorder:recorder . ./`（按锚点引用，行号随构建段增删漂移）会把它整体打进对外镜像。**第五处同源点**是 `scripts/check_annotations.py::EXCLUDE_DIRS`——它由 `tests/test_run_gates.py::test_check_annotations_exclude_dirs_cover_pyproject_excludes` 与 pyproject 的 black/isort/coverage 三份清单逐名比对（方向为「那边有、这里也得有」），漏登记会让该锁直接变红。
- **配置键审计须先归一化大小写**: 核对「代码读取的键」与 `config/config.ini` 实际键时先转小写再比对（configparser 大小写不敏感，代码常量大写、配置文件小写，精确比对会误报缺失键）。仓库当前把 `config/config.ini` 作为**已跟踪的脱敏基线模板**；`.gitignore` 的同名规则只对未跟踪副本生效。模板默认值须与代码 fallback、README 配置块逐项对账；**禁止**把真实凭据写入提交或以任何形式外传（红线见「风险控制（前置）·凭据与敏感配置红线」）。
- **venv 依赖修复分级处置**: 批量 `pip install --force-reinstall` 会被沙箱拦截且拦截在卸载之后，清空包目录（`ImportError: cannot import name 'x' from 'y' (unknown location)`，`pip check` 查不出）。三级：① **一级（代理自行）**单/少数包破损——wheel 直解绕开卸载：`pip download --no-deps -d <tmpdir> <pkg>` → `zipfile.ZipFile(wheel).extractall(<site-packages>)`；② **二级（代理可试）**常规补装单个小包 `HTTP_PROXY="" HTTPS_PROXY="" pip install --proxy "" <pkg>`，被拦立即转三级；③ **三级（交回用户）**批量重装 `pip install --ignore-installed --no-deps -r requirements.txt`。**破损检测三查法**：① 包目录递归数 `.py`/`.pyd` 为 0；② 目录整体消失逐个 import 实测；③ RECORD 对账只作辅助。
- **覆盖率排除规则两 job 同源**: `pyproject [tool.coverage.report]` 与 `.coveragerc-concurrency` 排除条目必须一致且一律用 `exclude_also`（追加）而非 `exclude_lines`（替换，会丢三条默认排除规则）。
- **镜像额外排除集**（仅 `.dockerignore`）：`uv.lock`/`scripts/`/`AGENTS.md`/`README_EN.md`/`CODE_WIKI_EN.md`/`.coveragerc-concurrency` 及审查记录通配 `CODE_REVIEW_*.md`/`DIAGNOSIS_*.md`/`PERF_REVIEW_*.md`/`PROPOSAL_*.md`（随仓库分发，不得加进 `.gitignore`；换用新前缀必须三处同改）。
- **门禁环境变量 `PYTHONUTF8=1`**: 见「格式化命令」MID-63 条目。
- **`deps-audit` job**: `ci.yml` 中 `pip-audit -r requirements.txt`（按 OSV 审镜像与 CI 实际消费清单），独立成 job 且是 `ci-summary.needs` 的一部分（required check 唯一暴露面）。本地复现须自带 `PYTHONUTF8=1`（中文 Windows 下 pip-audit 读中文注释行会 `UnicodeDecodeError`）。
- **漏洞审查双防线策略（`deps-audit` 阻断 + Trivy advisory）**: 两条覆盖面互不重叠——`deps-audit` 审 Python 依赖清单（blocking，已抓出 starlette / urllib3 / h2 / protobuf 历次 CVE 并抬下限）；`trivy.yml` 扫 Docker 镜像全层（apt / ffmpeg / node / 基础镜像 libssl 等 Python 清单之外的东西，advisory only，结果进 GitHub Security → Code scanning alerts）。**Trivy 维持 advisory-only 不升级为阻断**：镜像层漏洞多来自上游基础镜像与系统包，无法通过改 Python 依赖修复，需维护者人工判定阈值与忽略口径；cron 触发无人值守时变红会造成无意义噪声。替代审查流程：`deps-audit` 在每次 PR / push 阻断 Python 侧；Trivy 在 push / PR / 每周一 cron 把镜像层结论写入 Security 标签页，维护者定期查看 GitHub Security → Code scanning alerts 完成镜像侧审查。升级 Trivy 为阻断门禁属维护者决策（需先定 `exit-code` 阈值与 `trivyignore` 口径），不在代理权限内。
- **`static` job 的派生元数据一致性校验（`sync_metadata.py --check`）**: `uv.lock` 与 `DouyinLiveRecorder.egg-info` 是 `pyproject.toml` 的派生产物（见「关键约定」#1 与下方 egg-info 条目），不得手改版本字段。`ci.yml` 的 `static` job 在 `Check version consistency` 之后跑 `--check`——纯读 `uv.lock`/`egg-info/PKG-INFO`/`pyproject.toml` 比对，**不调 uv/setuptools、不联网、无需装项目依赖**，与元数据回归锁同口径；路径过滤已把 `uv.lock`/`DouyinLiveRecorder.egg-info/**` 纳入 `python` 组，手动改这两个文件也会触发本步。漂移修复：`python scripts/sync_metadata.py` 重新生成。
- **发布链运行时钉定在 prepare 单点收敛（SEV-10）**: 钉定值事实源是 `build_exe.py`，不得把哈希副本写进 workflow（见「已知坑」发布钉定条目）。
- **build 失败会留下空 Release，须由 `release-guard` 回收（2026-09-27）**: `release-create` 为消除 build 矩阵各平台的并发创建竞态（平台数见本节「发布矩阵为四平台」条目，不在此重复），在 build **之前**预建 Release 记录；任一平台 build 失败（典型：`_download_file` 的 SHA256 校验 `SystemExit` → `dist/` 无 zip → 上传步骤报 `Pattern 'dist/*-lite.zip' does not match any files`）时，收尾 `release` job 因 `needs: build` 被跳过，那条记录就以**空 Release** 留在仓库里。`release-guard`（`needs: [prepare, build]`、`if: always() && ... && needs.build.result != 'success'`）按「残缺即不发布」删除它并留 warning；`gh release delete` 默认**不删 tag**，修好后重跑工作流即可重新发布。不得为「让流水线变绿」给上传步骤关掉 `fail_on_unmatched_files`——那条红是产物缺失的唯一可见信号。
- **维护脚本里「按名字起子进程」必须 `shutil.which` 早退或捕 `OSError`**: PATH 无该命令时 `subprocess.run(["uv", ...])` 抛 FileNotFoundError 而非回非零码，「命令不存在→友好降级」的 else 分支根本不可达，且其后**不依赖它**的步骤（egg-info 重建）被一并带走（M-32①）。降级段不得与后续独立步骤共享同一 try 作用域；`--check` 这类只读路径必须零子进程、零联网（由 tripwire 用例钉住）。
- **跑 pytest 的 job 必须装齐 `requirements.txt`（2026-10-18 事故定型）**: `tests/conftest.py` 的三个 **autouse** fixture 会 import `src`（`_clean_credential_caches` → `from src import spider`、`_hermetic_danmaku_hub` → `import src.danmaku_monitor`）与 `i18n`（`_pin_identity_translation`），而 `src/node_install.py` 顶层 `import distro`、`i18n.py` 顶层 `from loguru import logger`——于是「跑仓库里任何一条 pytest」的门槛是**整份运行时依赖**，与被测文件自己的 import 无关（`vbs-behavior-test` job 只装 pytest 时 11 条用例在 setup 阶段全数 `ModuleNotFoundError: No module named 'distro'`，详见 CODE_WIKI 2026-10-18 条目）。新增或改造 job 时不得靠「只装 pytest」省钱，判据由 `tests/test_ci_pytest_env_parity.py` 机检（双向钉：已知 pytest job 必须被认出、`setup` 等只 echo 版本常量的 job 不得被误判）。**不得**改成「fixture 在模块未加载时静默跳过」——那是 MIN-2264 同族的假绿面（fixture 静默不生效，污染类用例退化成「单独跑通过、整包跑失败」）。
- **`scripts/smoke_test.py` 的配置形态畸形一律 rc=2，校验点唯一在 `load_config`（M-32②）**: 消费方 `scripts/_ci_web_smoke.sh` 靠 rc=2 区分「配置问题」与「面板故障（可重试）」，让 `.items()`/`.get()` 抛 AttributeError 变成 rc=1 会触发无谓网络重试。显式 `null` 与「键缺失」等价放行，但取值处必须写成 `x.get("headers") or {}`——`dict.get` 的默认值只在**键缺失**时生效，放行 null 再配 `.get(..., {})` 会重开同族崩口。rc=2 现在能真的立刻停：`.github/actions/retry` 自 2026-09-30 起支持可选入参 `fail_fast_codes`（默认空串＝既有调用点行为逐字不变），仅 web smoke 调用点传 `"2"`，命中即带**原退出码**失败、不进入退避。**不得**为了「让流水线变绿」把 rc=2 退成 0 或降级成 warning——那是假绿。回归锁 `tests/test_ci_retry_action.py`（结构锁 + 真 bash 行为锁 8 格）。

## 格式化命令（门禁唯一基准）

> 本节是全项目门禁命令唯一事实源。`ci.yml` 各 job 与之逐字一致；其它章节一律**引用本节**，不得另定一套。

```bash
# PYTHONUTF8=1 是门禁语义的一部分，不得删（MID-63）：GBK locale 下 isort 会对含中文注释文件
# 抛 'gbk' codec can't encode 并静默跳过、rc 仍 0——本地与 CI 都没查。
PYTHONUTF8=1 python -m black --check --diff --line-length 120 --target-version py314 .
PYTHONUTF8=1 python -m isort --check-only --diff --profile black --line-length 120 .
mypy                      # 不带路径，范围取 pyproject [tool.mypy].files（本机平台目标）
mypy --platform linux     # 平台双跑：本机非 linux 时补测 linux 目标（涉平台专属符号必查）
mypy --platform win32     # 平台双跑：本机非 win32（含 Linux CI）时补测 win32 目标（同范围、不带路径）
python scripts/check_annotations.py
python scripts/compile_po.py --check
python scripts/check_version.py
python scripts/check_runtime_pins.py  # 只查结构；--strict（发布路径）见「CI / workflow 约定」
python scripts/check_skill_agents_consistency.py  # Skill 目录与 AGENTS.md 表格一致性
```

- **`check_annotations.py` 不止查注释**: 常驻符号可达性检查，报告「引用了全仓都没有绑定的名字」（删除模块级函数/常量却留调用点的形态）。该命令在上方清单内，CI 与 `run_gates.py` 两侧都跑。
- **本地一次性触发点**: `python scripts/run_gates.py` 按原顺序跑完全部 `--check` 型门禁（含平台双跑增跑的 `mypy --platform linux` / `mypy --platform win32`），任一失败非 0 退出；`--list`/`--only`/`--keep-going` 用于排障。脚本运行时解析本节 bash 块，**本节仍是唯一事实源**，禁止另建并行清单。给门禁写行尾注释安全，写行首注释会被整行跳过。
- **一律显式传参**（`--line-length 120 --target-version py314`/`--profile black`）：配置会继承，但显式参数避免本地配置漂移造成「本地过、CI 挂」，也与 CI 逐字对齐。排除目录不需传（由 pyproject 生效）。
- **本地门禁可外推的前提：工具版本与 `ci.yml` consts 钉定值逐一同值**: `run_gates.py` 以 `sys.executable -m black/-m isort` 与 venv 内 `mypy` 起子进程，故「本地全绿」只有在 black/isort/mypy/pytest 版本与 CI 的 `black_version`/`isort_version`/`mypy_version`/`pytest_version` 相等时才等于「CI 会绿」；任一项不一致时，报告必须写明「本地口径，未经 CI 同版本验证」并列出差异项。**抬常量只消除版本差，不等于 CI 实跑已验证**；**不得**为凑同值擅自改 workflow 常量或批量重装 venv 依赖（后者见「风险控制（前置）」）。2026-10-17 起四项常量与 `.pre-commit-config.yaml` 的 black / isort 两个 mirror rev 已全部对齐到本机实装——**版本面只有一个值**才是这条门禁可外推的前提，任一处单独抬都会造出「本地提交用 A 版重排、CI 用 B 版判定」的互擦。**抬版本常量前须用新旧两版各跑一次全量 `black --check`，以「两版结论逐字相同」为「抬值不改判定」的判据**；历次对齐读数、rev 存在性核实方式与未验证边界见 `docs/agent-reference/measured-evidence.md`「门禁工具版本与 exclude 锚定的历史读数」。
- **`PYTHONUTF8=1` 必须同时覆盖子进程与转发输出的父进程，且「告警即失败」同回路判定（MID-63）**: ① isort 读文件用平台默认编码，GBK locale 下遇中文注释只发 `UserWarning: Unable to parse file …` 就**跳过该文件**、rc 仍 0。两条配套：`run_gates.py` 把行首 `NAME=value` 转子进程环境变量并对 stderr 中 `Unable to parse file` 判失败；`ci.yml` 用 step 级 `env: PYTHONUTF8: "1"` + 独立 silent-skip 兜底步骤。② `reconfigure(encoding="utf-8")` 必须显式写 `errors="replace"`（只传 `encoding` 不传 `errors` 会把错误处理器重置为 `'strict'`）；`run_gates.ensure_utf8_streams()` 修的是中文 Windows 下本进程 stdout 为 cp936、转发 black emoji 行抛 `UnicodeEncodeError` 炸门禁进程的根因——`errors="replace"` 只是兜底，**不得**改用「只判断退出码」或「过滤 emoji」绕过。③ 本仓「Windows 控制台 UTF-8 补丁」重复实现于 6 处，`build_exe._ensure_utf8_streams()` 曾漏写 `errors`，而 `tests/test_build_exe.py` 在 pytest 进程内调 `build_exe.main()`，pytest 的 fd 捕获包装器被就地翻成 strict，会话收尾读回捕获文件抛 `UnicodeDecodeError`。④ 配套约束三条：任何 `reconfigure` 显式给 `errors`；`tests/conftest.py` 的 `_guard_stdio_encoding_policy` 逐用例校对 `(encoding, errors)`，宿主进程编码策略属框架资产、用例不得改；`gui._install_crash_sink()` 仅 `__name__ == "__main__"` 时装进程级钩子。
- **门禁「告警即失败」推广口径**: 新增门禁若存在「跳过/降级只发 warning、退出码仍 0」形态（isort `Unable to parse file`/coverage「无数据」/pytest warnings summary），必须同回路判失败，否则写明该门禁不自证覆盖。

### basedpyright（本地补充门禁，CI 不跑）

- 命令：`basedpyright`（不传路径，范围取 `pyproject [tool.basedpyright]`）；要求 0 error/0 warning。
- 与 mypy 分工：mypy 是跨平台 CI 门禁（Linux runner）；basedpyright 是本地严格度补充，报错码不同，ignore 注释按各自 code 填写。
- **`pyright` 与 Pylance 的定位**: `pyright` 只是 basedpyright 的引擎基座，本地增跑结论与 basedpyright 同源，**不是第三条门禁**；Pylance 无命令行入口（仅 IDE 语言服务器，且其 server bundle 带 Microsoft 许可证、只授权在 VS Code 系产品内使用，**不得**为绕过这点去 shell 驱动它），任何「Pylance 已查过」的表述都不得直接当作门禁证据。[2026-10-17 改] 本仓原先**没有** `[tool.pyright]` 配置段、裸跑 `pyright` 走自带默认范围（把 `typings/` 存根一并纳入），于是 IDE 与 CLI 的扫描面无法对齐、「IDE 看着没问题」也无出处可复核；现已新增仓库根 `pyrightconfig.json` 作为 **IDE 语言服务器与 `pyright` CLI 的共用配置**（include == `[tool.mypy].files`、exclude == mypy 与 basedpyright 两份清单的并集、typeCheckingMode/pythonVersion/venv 同 `[tool.basedpyright]`）。此后复现 IDE 结论一律**不带路径**跑 `pyright`（读这份配置），并仍在回复里写明它是本地补充证据、不替代 CI 的 mypy；同源关系由 `tests/test_pyright_config_parity.py` 机检（改配置或改 `[tool.mypy].files` 任一侧不同步即红）。
- **裁决规则**: CI 只跑 mypy。只在 Linux 或只在 Windows 出现的基于 basedpyright 结论，以与 CI 一致的 Linux 一侧为准；不要为两侧静默而加 `# type: ignore`（会触发 `reportUnnecessaryTypeIgnoreComment`）。

### isort 收尾清理 `.isorted` 备份残留

清理命令必须匹配 `*.isorted`（`*.py.isorted` 匹配不到 `*.pyi.isorted`）：

```powershell
Get-ChildItem -Recurse -Filter *.isorted |
  Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' } | Remove-Item -Force
```

```bash
find . -name "*.isorted" -delete
```

## 完成定义（Definition of Done）

代码通过门禁 **不等于** 完成。改动落地后按序执行 1→6，任一条不满足即未完成：

1. **门禁全绿**: `python scripts/run_gates.py` + `pytest`（0 警告）+ `scripts/check_coverage.py`；basedpyright 本地核一次。**大批量改动收尾时，被引用为「门禁全绿」证据的那次运行必须发生在整批最后一次编辑之后**——中途跑绿后又改了文件不得沿用旧结果（否则会把「改前的绿」当作「改后的绿」）。收尾须对「本次改动」记录三元组「**最终修订**（最后一次编辑落到的文件/提交点）+ **实际执行的命令** + **通过/失败**」，并确认该运行指向最后一次编辑之后而非之前。此判定与留痕走本入口（第 1 步），**不另建并行清单**；`/dlr-dod` 命令第 1 步与本步同源，冲突时以本节为准。
2. **端到端真机验证**: 涉及录制链路/选源/ffmpeg 参数/平台解析的改动必须用**真实 URL** 增量跑（至少一受影响平台）并写进回复——只有单测绿不算验证过。判定口径：回复含脚本名（`test_{bili,douyin,douyu,huya,twitch}_live_collector.py`）+ 脱敏 URL + 结果状态（PASS/WARN/FAIL）+ 可核对读数（消息数/SRT 字节数）。无法执行（无外网/无活房间）时记「未执行 + 原因 + 交回用户的动作」且**不得宣布完成**。验证结论同时写进 `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志。
3. **回归锁**: 动到带「回归锁」标注的行为时确认对应用例存在且覆盖；缺则补。
4. **文档同源**: `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志追加本次变更（中英双份）；新增长期约定写回本文件。
5. **收尾清理**: 按「测试收尾清理临时脚本」执行（前缀清单、范围与禁区、safe-delete 处置均以该节为唯一事实源），并 `git status --short` 核对无未跟踪残留。
6. **日志**: 当日 `.workbuddy/memory/YYYY-MM-DD.md` 追加一条；值得后来会话取用的经验同时写进 `docs/agent-reference/session-learnings.md`。

**豁免**: 纯文档/注释改动只做 1（门禁可只跑受影响部分）+4+6，第 5 步仅本次确实写过一次性脚本时执行；只改测试且不涉及生产行为时免 2。

## 流程编排技能的使用边界

- 本仓库日常改动（缺陷修复、性能优化、真机验证迭代、重构）**不进入**治理式运行时类技能（如 `vibe`）——其需求/计划冻结与阶段性硬停会打断「改一点→真机跑→看日志→再改」节奏。
- 仅当次会话用户**显式**要求（`$vibe`/`/vibe`/「进 vibe」）才加载；确需治理式执行时先由用户确认 run 范围与 artifact root。
- `brainstorming` 类「先出设计再动手」技能，对「方案已在 AGENTS.md/CODE_WIKI 钉死」或「用户已批准、正在连续推进」的改动不适用（含单文件缺陷修复）。

## 并发与线程模型

> 涉及锁 / 事件循环 / 信号量的改动必须先读本节。

### 基础模型

- **每房间一个独立线程 + 各自独立的 `asyncio.run()` 事件循环**: `main()` 为每个 URL 启常驻 `threading.Thread`（`_room_thread_target` → `start_record`），线程内以 `asyncio.run(...)` 逐轮驱动异步请求。**不存在共享的全局事件循环。**

### 调度中枢 src/scheduler.py

- 取代旧「单个全局 `Semaphore(1)` + 单向压制的 `adjust_max_request`」模型（80 房间共抢 3 槽位、严重延迟）。
- `ConcurrencyScheduler` 为中枢：**并发模式由「最大同时录制数(0为不限制)」是否为 0 决定**——为 0 → 动态调速（默认 min=1/max=128，`max(下限, min(上限, ceil(活跃数/缩放因子)))`，错误率极高时温和降容但永不低于下限，杜绝死螺旋）；非 0 → 固定并发（忽略动态调速与背压，最小 1 槽）。`adjust_loop` 守护循环每 5s 重算容量（固定模式下重算为幂等 no-op）。`main()` 首轮初始化 `scheduler = ConcurrencyScheduler(configured_limit=max_request)`，把全局 `semaphore`/`recording_semaphore` 两 `ResizableSemaphore` 指向其属性。
- `ResizableSemaphore`: 支持运行时 `set_value` 调容（增大唤醒等待者；减小仅降上限、不强行回收已持槽位）；`__init__`/`set_value` **允许容量 0**（暂停态）。
- `PlatformBreaker`（按 host 熔断，`closed→open→half-open`）: open 经冷却后放唯一探针，成功→closed、失败→重新 open；按 host 隔离。探针带租约（`_PROBE_LEASE_SECONDS=60s`）——探针轮可能以 `continue` 结束且不触发 `record`（主播未开播等待/`disable_record`/线程退出），`_probing` 无租约兜底将永不复位→永久熔断；租约超时后 `allow()` 重新授予探针自愈。回归测试 `test_platform_breaker_probe_lease_regrants_after_timeout`。
- **接线点仅限固定几处**: `notify.record_error/record_success` 增 `key` 形参委托 `main.scheduler`；`start_record` 入口 `record_host = host_of(record_url)` 且**必须在 `while True` 外层 try 之前预置 `record_host = ""`**（否则 basedpyright 判 possibly unbound）；平台分派前 `scheduler.allow(record_host)` 预检、False 则退避后 `continue`；`check_subprocess` 录制循环受 `recording_semaphore` 管控。
- 相关配置项「最大同时录制数(0为不限制)」兼作网络并发模式开关；「同一时间访问网络的线程数」在动态模式下为容量下限之一、固定模式下即固定并发值（最小 1）。键名禁止含 `=`/`:`（见「已知坑」configparser 分隔符）。
- **调度模块测试**: `tests/test_scheduler.py`（29 用例，2026-09-30 `pytest --collect-only -q` 实测）；改动后 `pytest tests/test_scheduler.py`。全量 pytest 中 `tests/test_twitch_live_collector.py` 会因 safe-delete 护栏失败，属环境限制非调度问题。

### 录制结果反馈约定（main.py / src/stream_select.py）

- **`check_subprocess` 须按 ffmpeg 退出码上报调度样本**: `rc==0` → `record_success(host_of(record_url))`；`rc!=0` → `record_error(...)`。**禁止轮末无条件 `record_success`**——失败轮记成成功会稀释按 host 熔断统计（虎牙房间秒级 403 死循环根因之一）。
- **快速失败须记入探针退避**: `time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS`(20.0) 判快速失败时，解析 `-i` 后实际拉流地址调 `stream_select.mark_ffmpeg_reject(url, platform)`；下一轮 `select_source_url` 跳过该线路。`platform` 不在退避白名单（`_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)`）时静默无操作，勿扩大到斗鱼。缺 `-i` 以 `except ValueError` 跳过退避标记。慢速失败只记失败样本不记退避。
- **录制成功须撤销该地址探针退避（`clear_ffmpeg_reject`，与 `mark` 对称）**: 成功分支解析 `-i` 后实际拉流地址调 `clear_ffmpeg_reject(url, platform)`（只清实际成功的 FLV，HLS 退避不顺带清）；共用同一白名单与退避键。
- **解析成功轮即上报成功样本**: `port_info["anchor_name"]` 非空须 `record_success(record_host)`，与解析失败分支 `record_error` 对称（此前成功样本仅在 ffmpeg 退出时上报，half-open 探针房间长时间录制期间同 host 其余房间持续熔断饿死）。
- **直下路径（`direct_download_stream`）补成功样本**: 成功路径末尾 `record_success(record_host)`。
- 回归测试：`tests/test_record_failure_feedback.py`（8 用例，2026-09-30 实测）、`tests/test_stream_select.py::test_mark_ffmpeg_reject_marks_backoff`。

### 锁的强制约定

- **禁止模块级 `asyncio.Lock()` 单例**: 惰性绑定首个 `await` 它的事件循环，后续新循环 `await` 即抛 `RuntimeError: … bound to a different event loop`。正确做法见 `src/async_http.py` 的 `_get_client_lock()`：**随当前事件循环缓存/重建**（比对 `asyncio.get_running_loop()`）。仅单房间不报错，**必须并发多房间才能复现**。
- **跨 `await` 持有的跨线程锁一律用 `threading.RLock`，不得用 `threading.Lock`**: 凭据去重锁（`_ttwid_lock`/`_kuaishou_did_lock`/`_twitch_client_id_lock`）跨越 `await` 持有；普通 `Lock` 下同一循环第二个并发协程会自旋死锁。`RLock` 使同线程重入退化为幂等重复拉取，跨线程去重语义不变。

## 关键约定

1. **版本号同步**: 唯一事实源 `pyproject.toml`。`main.py`/`src/web_api.py` 经 `importlib.metadata` 动态读取；`Dockerfile` 经 `APP_VERSION` 注入；`zh_CN.po` 不写版本号；文档当前版本手工同步。`uv.lock` 与已跟踪的 `DouyinLiveRecorder.egg-info` 是**派生**消费方（生成物，不手写版本号）：改 `[project].version` / 依赖 / 包清单后运行 `python scripts/sync_metadata.py` 一键重新生成二者（`uv lock` 整文件重算、`setuptools egg_info` 重建），日常校验用 `--check`（CI `static` job 与 `tests/test_regression_2026_09_22_gates.py` 两条元数据回归锁兜底）。`scripts/check_version.py` 校验动态消费方。
2. **行宽**: 120 字符（black + isort 统一）。
3. **导入排序**: isort `black` profile，`known_first_party = ["src", "i18n"]`。
4. **运行时资源**: `config/`/`ffmpeg/`/`node/` 与 exe 同级，不进入 `_internal/`。
5. **JS 签名脚本**: 位于 `src/javascript/`，通过 `__file__` 定位，打包收入 `_internal/`。
6. **编码与注释风格**: 源文件 UTF-8、注释中文；注释统一 `#`（见「注释约定」），禁止 docstring（多行字符串字面量如 `SPEC_TEMPLATE` 合法保留）。
7. **排除目录**: `node/`/`ffmpeg/`/`downloads/`/`__pycache__/` 在所有工具均排除。
8. **停止录制流程日志归档**: 四个运行日志（`logs/streamget.log`/`PlayURL.log`/`danmaku_monitor.jsonl`/`web_console.log`）在停止录制时经 `src/log_archive.py::archive_runtime_logs` 改名归档（冲突追加 `_N`，缺失/失败仅告警跳过）。触发点两处：Web「停止录制」（`reopen_streams=True`）、进程退出 atexit（须先于两个 cleanup 注册、`reopen_streams=False`）。硬约束：Windows 句柄未关 rename 必抛 PermissionError，改名前须先关句柄（loguru sink 经 `logger.remove()`、弹幕边车经 `DanmakuMonitorHub.close_file()`、`web_console.log` 经 flush+close+`rebind_console_sink()`）。`DLR_GUI_PARENT=1` 与测试（`DOUYIN_DISABLE_LOG_ARCHIVE=1`）一律早返回。回归锁：`tests/test_log_archive.py`+`tests/test_web_api.py::TestRecordingToggle`。
9. **布尔配置项统一解析口径**: 禁止「字典查表+兜底实参」或「字符串相等比较」，一律走：纯解析函数 `src/config_bool.py::parse_config_bool(raw, default)`（零依赖，可被 `src/logger.py` 引用，不得放 `config_io.py`/`utils.py`）；配置层 `src/config_io.py::read_config_bool(parser, section, option, default)`（读取+缺键补写，main.py 全部布尔读取点用它）。识别集合：是/否、true/false、t/f、yes/no、y/n、on/off、1/0（strip+lower）；空值与未识别返回 default 且不覆写用户原文。另三处同源口径（`logger.py`/`web_config.read_web_config`/`gui._get_dynamic_status_info`）已改复用同一解析；`web/app.js` 按内嵌 `parseConfigBool`+`CONFIG_*_TOKENS` 保持同集合（改任一侧须同步）。**禁止**新增 `options.get(read_config_value(...), 兜底)`。回归锁：`tests/test_config_bool.py`+`tests/frontend/test_quality_ui.mjs`。
10. **出站下载源必须登记进可机检白名单**: 任何新的出站二进制/脚本下载点必须同时登记进 `tests/test_ffmpeg_install.py` 的 `DOWNLOAD_SOURCES`（键=主机，值=(完整性方式, 为什么可接受)）与 `DOWNLOAD_MODULES`；两处缺一即锁红。完整性方式为 **TOFU 的源必须默认关闭**（如 `FFMPEG_MASTER_ALLOWED`，取值走 `config_bool`），开启与跳过两侧都落 warning。权威上游必须排在任何镜像之前。该锁自带反向见证（断言确实看到 `gyan.dev` 与镜像常量）。
11. **camelCase 凭据键必须同步脱敏表**: `utils._SECRET_KEYS` 是「黑名单+左边界断言」，天然漏 camelCase（`accessToken`/`wsAuth`/`tk` 曾明文落轮转日志）。新接入平台若凭据参数是 camelCase，**必须**同步该表并在 `TestMaskCredentialsCoverage` 增加「**值确实消失**」断言——不得只断言「调用了 `mask_credentials`」。
12. **修复类注释必须附可复核判据**: 注释写「已修 X」或「回归锁：`tests/…::test_xxx`」时该用例必须真实存在且能因该修复被破坏而变红；否则如实写「待办+为何未做」。判据 `grep -rn "回归锁：tests/" main.py src/ | 逐条 grep 用例名` 复核。
13. **跨模块字符串契约不得靠自然语言子串**: 面板/GUI 解析录制端日志时 `if "没有正在录制" in msg` 在 `language=en_US/en_GB/zh_TW` 下恒假（正文经 `i18n.tr()`）。比较对象一律取 `i18n.tr(...)` 后形态，不得直接拿简中常量；结构化前缀（`#DLRQ|` 键值协议）属待批准长期方案。
14. **i18n 扫描盲区清单**: `scripts/extract_i18n_strings.py` 扫不到 ①`color_obj.print_colored(...)` ②`messagebox.show*` ③**推送正文**（`msg_push.py` 裸字面量+`str.replace` 模板）——三类新增用户可见文案必须手工补进 `zh_CN.po`/`en_US.json`/`en_GB.json`/`zh_TW.yaml` 并重编 `.mo`，否则提取器报「0 缺失」假绿；并行修复中间态落 `_i18n_pending*.json` 由中央合并脚本一次性落四目录。**「按名传入 tr()」的模块常量**（如 `web_api._INSECURE_BIND_ENV_TAIL`）同属此列——首参是名字不是字面量，提取器看不见，须手工登记。`T(...)`（`src/ui_i18n.py` 的静态标签标记）已纳入提取器与 `tests/test_i18n_migration.py` 的 `T_CALLER_IDS`，静态标签词条受不变量③机检（2026-10-04 起）。**同一标签在两套窗口实现里可能是两种 msgid 形态**（2026-10-17 实测：Qt 侧栏 `📊  控制台` 两空格、Tk 遗留 `gui.py` 三空格，二者都是运行时按键）——判定「孤儿条目」一律用 AST 枚举两侧调用点，不得凭 `grep` 下结论：非 ASCII + 连续多空格的模式在 Git Bash grep 下会静默漏配，据此改名会弄坏另一侧译文。**收回孤儿条目前必须把测试夹具也算作调用点**：裸键 `开始录制` 在生产侧已无调用点，但 `tests/test_i18n.py::test_load_translations_priority` 与 `::test_set_language_hot_swaps_translator` 用它当样本 msgid 验证「`.mo` 优先于 JSON/YAML」的三档加载与热切换（`en.get("开始录制") == "Start Recording"`、`tw.get("开始录制") == "開始錄製"`），收回它会把这两条机制用例打红——2026-10-17 收回 6 条裸文本键（`停止录制`/`重新读取`/`保存 URL 配置`/`打开下载目录`/`高级设置`/`清空日志`；收回动作即时读数四目录 1132 → 1126 键、`.mo` 1127 条 / 149 231 字节，同日另一工作包登记其模板后为 1127 键、`.mo` N=1128）时即按此判据把它留下。**盲区④自 2026-10-17 起已有机检**：`tests/test_i18n_catalog_coverage.py` 会解析按名传入 `tr()`/`T()` 的候选 msgid 并断言四目录齐全，同时断言四目录键集合逐项相等；解析不出的调用点用**白名单集合相等**判定（当前仅 `src/ui_i18n.py:34` 的 `tr(self.msgid)`，其候选即全仓 `T()` 字面量、归不变量③管）。新增不可静态解析的按名调用点必须先入该白名单并注明由哪条锁覆盖，不得放任其无人核对。**盲区⑤（raise 位文案，2026-10-17 起已有机检）**: 异常消息被当作 `{reason}` 实参插进一条**已经 `tr()` 过的日志模板**时，模板查了表、**消息本身从没被查过**——把原文登记进四目录只造出死条目，唯一有目录意义的写法是在 **产生点** 包 `i18n.tr()`（`main._hy_fan_path_segment`/`_b23_tv_path_segment`、`src/web_models.py` 的 422 detail、`src/spider.py` 的 TwitCasting/微博/TTingLive 三处即此形态，共 21 站点/16 条 msgid）。锁在 `tests/test_i18n_raise_site_tr.py`：未接 `tr()` 的站点走**白名单集合相等**、已接的 msgid 断言四目录齐全。**确属「消息永不显示」才可入白名单**并注明消费点——现登记 10 条：`XhsUrlError` 九条（`src/spider.py` 两处 `except XhsUrlError` 与 `main._resolve_xhslink_com` 一律只读 `e.code`）与一条整句英文、仅括号里「原」字是汉字的站点（译它等于把英文再写成英文）。
15. **启动期陈旧字节码缓存清理只在白名单根内、判定必须用源码内容哈希**: `src/startup_cleanup.py` 由 `main()` 在 `utils.remove_duplicate_lines` 之后调用，开关键 `是否启动时清理陈旧字节码缓存(是/否)` 走 `read_config_bool`（默认「是」，`config.ini`/中英 README 配置块三处同值）。扫描根**只有**「程序目录顶层 + `src/` 下直接含 `.py` 的目录」，删除对象**只有**其下 `__pycache__/` 里的 `.pyc`/`.pyo`；**禁止**改成 `rglob`/全树递归或去掉「含 .py」判据（会删进 `tests/`/`scripts/`/`.venv/`/`downloads/`；2026-10-02 变异验证实测这两种改法均被 `tests/test_startup_cleanup.py::test_purges_only_whitelisted_roots` 抓红）。判定基线为 `sha256(相对路径 + 文件字节)`，与版本号一起落 `logs/.pyc_stamp`（`版本|哈希` 两字段）——**不得**退化为 `(size, mtime)`：覆盖升级时复制工具常保留 mtime，同字节数改动会让 CPython 的 timestamp 失效判定与 mtime 式指纹同时失明（回归锁 `test_same_size_same_mtime_content_change_is_detected`）。基线缺失或读失败按「无法证明缓存新鲜」处理 = 清一次；写失败仍然清并 warning（退化成用户手工删缓存的语义，不得静默失效）。`_IS_FROZEN` 与开关关闭两条路径一律零 I/O（不遍历、不哈希、不碰哨兵）。新增运行期文件一律优先考虑 `logs/`——该目录已在 `RUNTIME_ARTIFACT_DIR_NAMES`/`.gitignore`/`.dockerignore` 三处排除，不必再改第四处排除口径。
16. **界面语言接线（GUI 静态标签 / 窗口标题 / 错误 detail）**: 构建期定型的静态标签一律经 `src/ui_i18n.T()` 交由 `ui_kit` 工厂「建时查表 + 登记重译」（工厂识别 `Translatable`，普通 `str` 透传不重译）；窗口标题走 `apply_title`；事件时文案（`_log`/`_set_hint`/`_warn_chain`/表格单元格/`HTTPException` detail 的展示类取值）在产生点 `i18n.tr()`。**语言切换必须整窗回填**：`_on_language_change` 依次 `retranslate_all()` → 哨兵值重置为 `tr()` 后形态 → 动态面刷新 → 托盘 `rebuild_menu()`，每步独立 try（重译失败不得吞掉 config 写回）；启动期 `_setup_ui` 末尾同样回填一次（`set_language` 之前构建的标签按导入默认语言定型）。**不得翻译**：配置键名/节名、正则、稳定机器码 detail（`unauthorized`/`rate_limited`/`host_not_allowed`/`insecure_bind_disabled`）、安全黑名单（`自定义脚本执行命令`）——它们是与文件内容/前端契约比对的字面量。新增用户可见文案四目录 + `web/app.js` 内嵌目录同批登记（面板点分键不进后端四目录，其余照旧五处）。

## 已知坑（避免回归）

### 录制链与房间线程主循环

- **录制链不得嵌套于 `if headers:` 内**: 录制主链必须位于条件判断**之外**，仅把「是否附加自定义头」作局部行为；用该条件包裹整条流程会导致无自定义头时静默不录制。
- **`real_url` 为空必须跳过录制链**: `select_source_url` 返回 None 时 `if not real_url: 告警+等待+continue`，否则 None 流入录制执行链崩溃或复用残留命令。守卫之后 `now`/`title_in_name` 为无条件赋值（移除恒真 `if real_url:` 包装）。
- **弹幕监控房间须随录制线程退出而移除**: `main.start_record` 在 outer try 的 `finally` 调 `get_hub().room_stopped(record_name)`（各 return 全覆盖），GUI `_danmaku_dispatch` 收到 `state=="stopped"` 后 pop 房间行；删掉该清理会残留失效直播间。
- **「已被注释」检查必须在解析之前**: 房间线程内层循环顶部（`exit_recording` 检查后）先查 `record_url in url_comments` 再进平台解析——原检查点在解析成功后，平台持续失败（风控空响应）时永远走不到，线程滞留占用监控位。
- **录制并发槽必须在 `Popen` 之前 acquire**（main.py::check_subprocess）: `recording_semaphore` 语义是限制同时进行 ffmpeg 数，先起进程再 acquire 则上限根本不约束 ffmpeg 进程数（资源耗尽）。结构：「`acquire` → `try:`（`Popen`+注册+弹幕启动+主循环）→ `finally: release`」，**启动段也必须落 `try` 内**，抛错同样归还槽位否则泄漏累积饿死所有后续录制。
- **录后自定义脚本（`src/notify.py`）的命令原文进日志前必须脱敏，超时回收必须处理孙进程**: 用户脚本常内嵌 rclone token / curl 的 Authorization / 数据库口令，而 `logs/` 轮转保留多份＝凭据长期落盘，故四条失败分支的 command 与异常文本一律过 `utils.mask_credentials`。超时 `kill()` 只杀直接子进程，孙进程握着管道写端会让**第二次无超时的 `communicate()` 永久挂住**录后钩子线程——第二次读必须带超时；进程树回收 POSIX 走 `start_new_session` + `killpg`、Windows 走 `taskkill /T /F`（一律 argv 列表，禁 `shell=True`），任一步失败退化到原来的 `kill` 且不改写结果。回归锁 `tests/test_notify_script_guard.py`。

### 流地址探针与可达性校验

> 完整流程与操作步骤见 `.agents/skills/platform-source-selection/SKILL.md`。以下为本节硬约束摘要。

- **GET 复核容错不得简化**: 401/403 先原样重试一次再定罪；末位候选仅告警放行交 ffmpeg 定夺。
- **虎牙探针退避仅限 `_PROBE_BACKOFF_PLATFORMS`**: 绝不可把斗鱼等加入名单。
- **虎牙 FLV-first（`_FLV_FIRST_PLATFORMS`），斗鱼绝不加入**: 斗鱼游客态 FLV ~70s 被掐必须 HLS 优先。
- **探针退避窗口 ≥ 一个主循环周期**: 不可改回固定 60s 常量。
- **UA 双端一字不差**: 改字符串须同步四处（`MOBILE_UA`/ffmpeg UA/`room.HEADERS`/B站 H5 UA）。
- **探针节流/抖动不得移除**: 改为固定值或移除会重引风控误伤。
- **探测方法基线**: HEAD 非 2xx → Range GET bytes=0-0（200/206 判可达），不要只覆盖 400/401/403/405。
- **「HLS 采集排除平台」与「FLV-first 调序」两种语义不可互实现**: 回归锁 `tests/test_stream_select.py`。
- **重定向逐跳复检只有两个合法接线点，新增第三处自建客户端即视为漏防**: 异步侧 `async_http._build_client`（response 事件钩子）、同步侧 `stream_select._probe_client` 工厂（2026-09-30 补齐：此前同步探针**连初始 URL 的内网判定都没有**，只有 `_is_recordable_url` 的协议形态白名单，它挡 `file://`/`concat:` 却不挡 `http://127.0.0.1:6379`）。两处判定一律复用 `async_http` 的同一份 helper，禁止在 stream_select 另写 urlparse/内网名单。钩子触发时机在该跳响应头已收到之后，闭合的是「不再跟随 + 响应不外流」，**不是**「不建连」；DNS 重绑定窗口本层不闭合，且**不得**给判定结果加缓存（缓存会把一次解析供给所有跳，主动拉长窗口）。复用形态不得回退：作用域仍是单次选源、不按 `(proxy, verify)` 做模块级全局缓存、不关 keepalive、`utils.handle_proxy_addr` 的归一仍只在构造客户端之前那一处。回归锁 `tests/test_regression_2026_09_29_wp_b_netguard.py` + `tests/test_sync_probe_internal_guard.py`（含 AST 结构锁：构造点唯一 + `event_hooks` 实参必须来自同步钩子工厂）。
- **「响应决定 URL」的落地页一律双闸，且拼出的下游主机须再过一次白名单**: 小红书 SEV-2214 与 Shopee（S-1）同型——① 域族白名单用 `urlparse().hostname` 做「精确等于或 `.` 后缀」判定并拒 userinfo；② `web_config._host_internal_reason` 判内网/回环/云元数据/CGNAT/缩写 IP。任一条不过即**丢弃跳转、保留用户自填的原始 url、并剥离 Cookie**。准入白名单只约束短链宿主，绝不等于约束落地页；由 `host_suffix` 拼出的 `api_host` 是第二处暴露面，发出带凭据请求前必须复验。
- **`sync_http` 的 opener 必须显式按协议白名单构造**: 不得用默认 `build_opener`（自带 FileHandler/FTPHandler/DataHandler，`file://` 即读本地文件），`HTTPSHandler` 是**必填实参**（放默认列表再补会出两支、降级语义被默认那支吃掉）。abroad 分支走进程全局 `urlopen`，只能做事后落地复核——该分支**不得**改 `install_opener`（会波及全进程）。
- **小红书链接形态与判据唯一入口**（2026-10-04）: 四类形态（`/livestream/<数字房间ID>`、`/livestream/<动态段>/<数字房间ID>`、`xhslink.com/o/<短码>`、`/user/profile/<id>`）一律经 `src/spider.py::parse_xhs_live_url`，**不得**在别处重写路径切分或 `re.search` 抠参数。硬约束：① host 精确等于 `www.xiaohongshu.com` / `xhslink.com`（后缀伪装、尾部点、userinfo 伪装、路径里出现域名词全拒），与 `_XHS_ALLOWED_HOST_SUFFIXES`（管落地页能否带凭据，须容纳 CDN 子域）分工不同，**不得**互相替代；② 房间 ID 判 ASCII 数字（`[0-9]+`，**不得**用 `\d+`，会放行全角数字），动态段/短码/主页 ID 只收 `[A-Za-z0-9_-]+`（点段与 `%2e%2e` 不进规范 URL）；③ 动态段原样保留，**不得**折叠成标准路径（删掉后页面未必可访问）；④ query 白名单只留 `host_id` / `xsec_token` / `xsec_source`——`xsec_token` 是页面鉴权参数，**不得**当噪声剥掉（旧 `&host_id=` 正则两个洞：只认 `&` 前缀的首参数形态、连鉴权参数一起剥）；⑤ `XhsUrlError` 带稳定 `code`，消息**不得**回显原始 URL / query / path。回归锁 `tests/test_xhs_live_links.py`（含短链安全边界与 `start_record` 录制启动集成）。
- **小红书未开播轮必须能建起监控作业**: 主播名读 `liveStream.roomData.hostInfo.nickName`（该字段在 `liveStatus="end"` 时依然存在，实测 2026-10-04），**不得**只从 `roomInfo.deeplink` 抠 `host_nickname`（那是开播态字段）——否则标准链接在等待开播的每一轮都拿不到 `anchor_name`，`start_record` 判「网址内容获取失败」并持续重试。仍取不到时用 `小红书_<room_id>` 兜底，**不得**对空 `user_id` 请求 `/user/profile/None`。`port_info["error"]` 必须在 `_resolve_xhslink_com` 转成告警 + `ctx.unrecognized`，不得与「主播没开播」混同空转；短链规范地址经 `new_record_url` 通道回写配置，**不得**在 URL 配置准入阶段解跳转（一次网络抖动就会改写用户配置）。

### 弹幕采集与 SRT 写入

- **弹幕 WS 连接必须显式 `proxy=None`**（src/ws_client.py::connect）: 使 WebSocket 直连不跟随系统代理，否则 B站/斗鱼等报 `connecting through a SOCKS proxy requires python-socks` 连接即断。改动须保留 `proxy=None`。
- **B站弹幕 buvid 必须真实、AUTH_REPLY 必须显式校验**: spi 端点是 `/x/frontend/finger/spi`（少写结尾 `i` 会 200+空 body 永远 JSONDecodeError）；buvid 获取链按真实注册标识优先排序（进程缓存→cookie `buvid3=`→spi→`www.bilibili.com` 首页 Set-Cookie→随机 UUID 兜底标记 is_fallback）。`_decode_packet` 须校验 operation=8 回应的 code：非 0 经 `_reject_auth()` 告警+断开+`spider.invalidate_bili_buvid_cache()`；`_auth_watchdog` 兜底「服务器 8s 不回 AUTH_REPLY 的静默拒绝」。
- **`collector.stop()` 与采集线程握手顺序不可单独调整**（src/collector.py）: `stop()` 必须先 `set(self._stop_event)` 再读 `self._loop`；`_run()` 必须先发布 `self._loop` 再检查 `self._stop_event`（两相反顺序保证信号必被一方接收）。缺一半会丢信号致 `join(timeout=8)` 超时、线程与 SRT 句柄双泄漏。另：`_shutdown` 中 `await danmaku.stop()` 必须 `asyncio.wait_for` 限时（`_SHUTDOWN_TIMEOUT_SECONDS`），否则 SDK 半开连接挂住 `loop.stop()` 永不执行。
- **弹幕文本写入 SRT 前必须转义**（src/srt_writer.py::_sanitize_srt_text）: `user_name`/`message` 为外部可控输入，含 `\n` 截断 SRT 块、含 `-->` 被解析成新时间轴行可伪造字幕。替换（非删除）为可见字符。回归锁：注入 `normal\n2\n00:00:99,000 --> 00:00:99,999\nFAKE\n` 后产物必须仍只有 1 个块 1 条时间轴。片内 `end` 须 `max(start, min(end, _seg_seconds))` 钳制。
- **弹幕链路接线点与分段命名约定**: `start_record` 各平台解析分支只填 `ctx.record_danmaku_args`（现 60 处赋值，2026-10-17 复测口径 `grep -c 'record_danmaku_args = ' main.py`）→ 唯一调用点 `main.py` 内 `comment_end = check_subprocess(...)`（按锚点引用，行号随文件增删漂移）的 `check_subprocess(..., platform=platform, danmaku_args=record_danmaku_args)` → `src/__init__.py::get_danmaku_collector(platform, args, base_filename, segment_seconds)`（实现在 `src/collector.py`）。硬约束：① `danmaku_collector.stop()` 必须在 `while process.poll() is None` 循环之外（`DanmakuCollector.stop()` 有 `_stop_called` 防重入幂等）；② 分段文件名——视频 `_%03d`（FLV 已从 `_%02d` 对齐；音频仍 `_%02d`）、SRT `{seg:03d}` 与之对应，`check_subprocess` 需同时剥离两种占位符；③ 抖音弹幕空 cookie 时在 `DouyinDanmaku.start()` 协程内 `await get_ttwid()` 动态获取（不再硬编码 ttwid）。配置项 `弹幕分片时长(秒)` 走 `_safe_float(..., 1800.0)`。
- **抖音弹幕 `signature` 保持不编码，禁止顺手加 `quote()`**（F-13）: XBogus 字符表含 `+`/`/`，但上游确认直接拼接不 encodeComponent、服务端不按 form-urlencoded 把 `+` 解成空格。改编码会让本端成为唯一异类指纹。回归锁：`tests/test_douyin_signature_encoding.py`。
- **B站弹幕 host 轮换的关闭回调必须走 `BilibiliDanmaku._report_close` 闸门**: 仍有候选 host 未尝试时属轮换中间态（转 `_on_reconnect` 留 debug），候选排空或已进入 `_stopped` 终态才向 hub 上报且**恰好一次**；`start()` 进入每个 host 前登记剩余候选数、循环结束必须归零，否则会话期之后的真实断连会被吞（回归锁 `tests/test_bili_host_rotation.py`）。不得为此新增 i18n msgid——`tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` 是硬门禁，新增裸 `logger.debug` 文案会当场红。

### 平台接口、签名与流地址解析

- **斗鱼必须附带 FLV→m3u8 同 token HLS 候选**: 斗鱼 H5 只返 FLV，游客态 FLV 长连接 ~70s 被掐；wsAuth token 对 FLV/HLS 通用，把路径 `.flv` 改 `.m3u8` 即同 token HLS（hw CDN 200+mpegurl）。该候选由 `select_source_url` 校验 gating、不可达自动回退 FLV，须保留。
- **migu.js 输出契约为完整签名 URL**；`src/javascript/` 的**文件增删必须与 `utils._JS_SHA256_EXPECTED` 同批提交**（2026-09-26 CI 实测坑）：`tests/test_utils.py::TestJsPinTable::test_every_executable_js_is_pinned` 断言「目录里每个 `.js` == 钉定表键集」双向相等，删除脚本却没推送 `.js` 本体（或反之）会让 CI 红，而本地已删的工作区全绿——本地与远端内容不一致时**只信远端**。`src/javascript/migu.js` 适配 migu 播放器 v_20260731+ wasm 接口（12 个导入函数、导出名重排），输出带 `ddCalcu`/`sv` 参数的完整地址（`sv` 失败回退内置默认因子）；`spider.get_migu_stream_url` 直接使用，不再拼接过期 `sv=10010`。
- **抖音接口风控信号是「HTTP 200 + 空响应体」不是 4xx**: 解析失败先看 `len(response.text)`，为 0 基本是 UA/Cookie 被拒。三条配套：① UA 敏感——`src/room.py` 模块级 `HEADERS` 是 2020 三星安卓 UA，`iesdouyin.com/web/api/v2/user/info/` 用它必被静默拒，此类接口一律用 `room.DESKTOP_UA`；② `iesdouyin.com/share/user/<sec_uid>` 已是 JS 反爬壳页，取 `unique_id` 请走 `https://www.iesdouyin.com/web/api/v2/user/info/?sec_uid=<sec_uid>`；③ `webcast.amemv.com/webcast/room/reflow/info/` 用占位 `room_id=2`+`sec_user_id` 解析主页行不通（status_code=10011）。
- **`live.douyin.com` 的 `web_rid` 同时接受数字房间号与抖音号**: `webcast/room/web/enter/` 两者皆可，`live.douyin.com/<抖音号>` 不重定向。**不要写「抖音号需先重定向解析成数字」的逻辑**（已被实测证伪并删除）。`main.py` 以 `port_info["anchor_name"]` 为空作「网址内容获取失败」判据。
- **`hevc_flv_url` 必须带 `codec=h265` 标记**（src/spider.py::extract_douyin_hevc_flv_url）: 正则抠出的 HEVC 地址必须补 `&codec=h265`（已带则原样返回）。下游 `_is_h265()`/`main.py` 的 h265 兜底**只认 URL 上的 codec 查询参数**。注意 `utils.get_query_params` 返回 **list**（`spider.get_params` 返回 str，不可混用）。
- **斗鱼房间号提取只认数字，且新域名必须两处同时登记**（2026-10-03 接入 `m.douyu.com` 时定稿）: 提取走 `spider.extract_douyu_rid_param()`（锚定 `[?&]rid=`，值非数字时**不作数**、回落路径首段）与 `spider.extract_douyu_room_id()`（`urlsplit` 取路径**首个非空段**，天然剥掉尾斜杠 / query / fragment，scheme 无关；无 scheme 时按准入侧同一规则补 `https://`，否则首段取到的是主机名）。取代的两处整串正则各有洞：`rid=(.*?)(?=&|$)` 会被 `?xyzrid=123` 误命中，`douyu.com/(.*?)(?=\?|$)` 会把尾斜杠与后续路径段带进房间号（`/8751648/` → `8751648/`）→ `betard` 拿不到 room、用户只看到「房间不存在」这类误导。字母号仍走移动端 `vike_pageContext` 还原，**还原产物非数字必须在还原出口报错**（`betard` / `getH5PlayV1` 只吃数字 rid）。新增斗鱼域名须**同时**登记 `main.py` 的 `PLATFORM_HOST` 与分发表匹配片段：缺前者链接在读取 URL 配置阶段就被判「未知链接」并注释掉，缺后者落入 `_resolve_unrecognized` 无限空转（SEV-2203 同型）。另：往分发表**插入**表项会挪动其后所有下标，`tests/test_platform_dispatch.py::test_resolver_table_priority_head` 的顺序锁必须同步改。

### 画质档位与选源映射

> 完整流程与操作步骤见 `.agents/skills/platform-source-selection/SKILL.md`「画质档位映射」章。以下为本节硬约束摘要。

- **蓝光子档位折叠到 BD 索引，不得塞进 `QUALITY_MAPPING`**: 中文映射新增须同步四处（`get_quality_code`/`web_config.QUALITY_KEYWORDS`/`main.py` 白名单/`web/index.html`）。
- **虎牙选档不可抛异常或返回空流地址**: 不可用时就近降级或回原画，保持 `is_live=True` 契约。
- **斗鱼本地重试链最多回退 2 档**: 全部失败保持 `is_live=True`，不得替代 HLS 候选与全局退避。
- **选档一律「保留原始请求索引 + FLV/HLS 双列表各自钳制」**: 不得把一侧钳过的下标写回共享变量再供另一侧复用——TikTok 曾因此对 HLS-only 房间恒取首档，且 `actual_quality` 回采 OD 后降级告警永不触发（「选流畅实拉原画」无提示）。参照 `src/stream.py` 抖音分支的 `flv_idx`/`m3u8_idx` 与修复后的 `flv_quality_index`/`m3u8_quality_index`（回归锁 `tests/test_tiktok_hls_quality_index.py`）。回退/探针失败重算分支同样不得复用被钳值。
- **抖音原画 hevc 替换必须把被替换的 h264 FLV 存入 `flv_url_list`**: 原画请求且接口下发 `hevc_flv_url` 时，选源层在保存格式不支持 HEVC 直拷时会把 `codec=h265` 候选在探针前剔除（TS/MKV/MP4 已放行，见下条），不保留 h264 原画备选则「HLS 采集关闭 / m3u8 缺席」+ FLV/音频格式的原画 hevc 房过滤后零可用候选、每轮「本轮无可用源」永不录制（2026-10-01 两间房实测）。与 hevc 地址逐字相同或自带 `codec=h265` 标记的条目不得收进备选（同样会被剔，徒增告警）。回归锁 `tests/test_stream.py::TestGetDouyinStreamUrl` + `tests/test_stream_select.py::test_select_source_url_h265_flv_falls_back_to_h264_from_list`。
- **h265 候选按保存格式放行（`_h265_copy_format_supported`）**: TS/MKV/MP4 三种容器可直拷 HEVC（main.py 选中 h265 地址时强制转 TS 是同一事实），此时 h265 候选进常规序列按序参与探针；FLV（HEVC-in-FLV 属 Enhanced-FLV 扩展、仓库口径不支持）、MP3/M4A 纯音频、域外/缺失取值仍一律剔除（保守默认）。判定读 main 的热更新全局 `video_save_type`（与 `_hls_selection_config` 同模式），改允许集须同步核实 `_EXTENSION_BY_SAVE_TYPE`/`SEGMENT_FORMAT_BY_SUFFIX` 的容器能力；main.py 的 h265→TS 强制块带同一口径守卫（已是 TS/MKV/MP4 不接管、不打「use TS format instead」）。回归锁 `tests/test_stream_select.py` 的 h265×保存格式双矩阵与 `test_h265_copy_format_supported_matrix`。
- **HLS 配置静默丢弃导致无源必须点名**: m3u8 候选被「是否启用HLS采集(是/否)/HLS采集排除平台(逗号分隔)」整组静默剔除且本轮最终无可用源时，选源结论前必须补一条带候选条数与恢复开关指引的告警——这是唯一「零日志」的选源成因（有 FLV/record_url 兜底时早退告警不触发）；选中源的轮次不得打（健康轮零噪音）。回归锁 `tests/test_stream_select.py::test_select_source_url_warns_dropped_hls_when_no_source` + `test_no_dropped_hls_warning_when_source_found`。

### HTTP 客户端复用与连接管理

- **httpx 请求级 headers 是「合并」不是「替换」**: 把 UA/Referer/Cookie 挂 client 级时，只传 `{"Range": "bytes=0-0"}` 的请求仍带全部 client 级头——不要据此判「丢了请求头」。但客户端一旦在多个候选间复用（select_source_url 整轮共用一支），业务头绝不能再挂 client 级（候选间互相污染），必须逐请求显式传入。
- **探针客户端复用作用域 = 单次选源，禁止升级为全局缓存**: `_validate_stream_url` 新增可选 `client` 参数（不传时自建自管）；刻意不做按 `(proxy, verify)` 模块级全局缓存（虎牙 CDN 按连接预算限流，常驻 keepalive 会与 ffmpeg 拉流争抢）。
- **禁止为「保险」关掉探针客户端 keepalive**: 会把复用收益全部退掉；排查虎牙 403 应临时改回「每候选一支 Client」。
- **`requests.Session` 必须线程级复用，禁止每次新建**（src/sync_http.py）: `_session()` 经 `threading.local()` 缓存（Session 非线程安全不可跨线程共享）。改回每次新建会让每次出站多一轮 TCP+TLS 握手（退化幅度本机读数见 `docs/agent-reference/measured-evidence.md`「`sync_http` 线程级 Session 复用的收益读数」）。`tests/test_sync_http.py` 的代理替身 patch 目标须是 `src.sync_http._session` 不是 `src.sync_http.requests`。**注意**：该模块当前无生产 importer（sync_req 调用点现只剩 tests/），保留是因为 requests 仍在运行时清单且 8× 复用结论成立——任何「已经吃到这个收益」的表述不得再写。
- **`sync_req` 的 SSL 降级路径必须保持惰性+单次覆盖**（F-12）: CERT_NONE 上下文与 opener 由 `_get_insecure_context()`/`_get_insecure_opener()` 按需构造，禁止改回模块级常驻。「无调用者」只是当下状态，不作为放宽惰性要求的理由。
- **出站响应体读取一律带上限，异步侧的上限只有 `_build_client` 那一处接线点**（2026-10-18 定稿，CODE_REVIEW M-03/M-04/L-11）：三条读取链各有自己的上限形态——① 异步主路径 `async_http._bounded_response_read`（挂在 `_build_client` 的**唯一** response 钩子内，httpx 钩子触发于「响应头已收到、`aread()` 之前」，读完经 `_content` 回填让后续 `aread()` 短路，故调用面与返回契约逐字不变）；② 同步侧 `sync_http._read_capped`（含 400 错误体分支；该分支从不解压，只设一道 `_MAX_RESPONSE_BYTES`，补解压层反而改透传契约）；③ 探针 `stream_select._bounded_probe_get`（可达性判定只需少量确认，读到首块即限量，判定结论与 HEAD→Range GET 基线一致）。硬约束四条：**不得**为异步侧新建第二支 response 钩子或第二支客户端（`tests/test_regression_2026_09_29_wp_b_netguard.py` 断言钩子恰一支）；8 MB / 32 MB 两个取值与同步侧**同值但各存一份**（同步模块自述零生产 importer，互 import 会制造新的耦合边），漂移由 `tests/test_async_http.py::test_caps_match_the_sync_side_baseline` 钉住；超限时走**既有失败出口**（`async_req` 的 debug 日志 + `_failure_result`、同步侧脱敏后回空串），**不得**让超限变成穿透异常或半截内容；新增任何出站读取点（含 `get_response_status` 一类旁路）必须落进同一上限体系，「看着只读状态码」不是豁免理由——旁路注释须写明它经哪一处受管。回归锁：`tests/test_async_http.py::TestBoundedResponseRead`/`TestAsyncReqCapEndToEnd`、`tests/test_sync_http.py::test_http_error_400_oversized_body_hits_read_cap`、`tests/test_stream_select.py` 的探针限量组。**读取点本身另有台账锁**（2026-10-18，CODE_REVIEW §7.11 第①条）：`tests/test_outbound_read_caps.py` 按 `(文件, 函数)` 双向相等枚举 httpx 独有读取方法（`aread`/`aiter_*`/`iter_*`——文件对象没有这些名字，因此这一档零误报；而 `.read`/`.text`/`.json` 与文件读同形，刻意不收进全仓判据以免白噪声淹掉真信号），新读点必须先登记「上限形态 + 为什么可接受」，同时锁「受管函数体内确实引用上限常量」（防「函数名还在、上限被摘掉」）与「sync_http 内非受管 `.read` 为零」。

### 并发、事件循环与锁

- **`asyncio.get_event_loop()` 3.14 起不再隐式创建事件循环**: 当前线程无循环时抛 RuntimeError。`src/async_http.py::close_all_clients_sync` 已改为捕获 RuntimeError 走引用清理兜底；协程内获取循环一律 `get_running_loop()`。
- **跨事件循环禁止创建/调度旧 AsyncClient 的 aclose 协程**（src/async_http.py::_get_client）: 淘汰他循环创建的旧客户端时一律**不创建** `aclose()` 协程，释放引用交 GC 兜底（三个坑：run_coroutine_threadsafe 只调度不等待、加 is_running 门控 await 仍可能永不执行、当前循环直接 await 旧 client.aclose 会操作旧循环 transport）。回归锁：`tests/test_async_http_lock.py::test_cross_loop_running_old_loop_skips_close`/`test_cross_loop_stopped_old_loop_skips_close`。
- **熔断计数必须增量、不得 `sum(deque)`；`import time` 提顶层**（src/scheduler.py）: `_fail_count`/`_global_error_count` 在样本入队/挤出时增量维护（O(1)），替代 `record()` 内 `sum(self._samples)`（O(40) 持锁遍历）；`_now()`/`_sleep()`（模块级，`_sleep` 在 src/scheduler.py:531）用的 `time` 已在模块顶层 `import time`。[历史注：原写的第二个符号名 `_allow_sleep` 不存在，2026-09-30 grep 实测为 `_sleep`]
- **「调用方持锁」改「内部自持锁」必须同步清调用点外层锁**: `web_api._purge_expired_tokens()` 改为内部 `with _tokens_lock:` 后，`login` 里原有 `with _tokens_lock: _purge_expired_tokens()` 未移除——`threading.Lock` 非重入，每个登录请求自死锁（征兆：接口不报错、永远不返回）。约定：函数要么只内部加锁、要么只由调用方加锁，二选一并在注释写明；改造其一必须 `grep` 全部调用点。
- **可重入性判定一律以源码定义行为为准**: 不要把文档清单当推断依据（main.file_update_lock/`_cache_lock` 实为 `RLock`）。改动前必须 `grep` 定义行确认。历史分类快照（某一时点的实测读数，仅供参照）见 [锁分类快照]。
- **Qt 的 GUI 线程必须是主线程；禁止给 Tk 进程塞第二个工具包**（2026-10-20 遗留托盘退役的定论）: `QApplication` 只能在主线程构造——`src/web_tray.py` 文件头记录在子线程执行 `QApplication(sys.argv)` 实测**段错误**（进程 exit code 139，Python 层无异常可捕获）。遗留 tkinter 路径（`gui.py::_legacy_main`）的 Tk `mainloop` 已占住主线程，而 macOS 上 Tcl/Tk 与 AppKit 同要主线程（这正是旧 pystray 托盘用 `run_detached()` 绕开的原因，也是 `_legacy_main` 原先要按 `sys.platform` 分叉的唯一理由）。结论：该路径**不得**引入 Qt 托盘，需要托盘功能一律走产品入口 `src/gui_qt/`；想「把遗留托盘也迁成 PySide6」之前先读本条。
- **`QDialog` 是顶层窗口，父窗隐藏不影响它显示**: 窗口收在托盘时从托盘菜单开「设置」**不需要**先恢复主窗口——2026-10-20 offscreen 实测父窗 `hide()` 后 `dialog.show()` 仍 `isVisible()==True`、`isWindow()==True`（`src/gui_qt/tray.py::bind_actions` 的注释即据此写）。普通子控件不适用这条。

[锁分类快照]: docs/agent-reference/lock-classification.md

### ffmpeg 命令构造与容器格式

> 完整流程、事故背景与验证命令见 `.agents/skills/ffmpeg-command-construction/SKILL.md`。以下为本节硬约束摘要。

- **`-reconnect*` 必须在 `-i` 之前且紧跟取值**: 写在 `-i` 之后被静默忽略。HLS 输入必须移除 `-reconnect_at_eof`。回归锁：`tests/test_ffmpeg_reconnect_args.py`。
- **`-thread_queue_size` 只能位于 `-i` 之后**: 放错侧致录制 100% 失败。
- **`-segment_format` 一律经 `SEGMENT_FORMAT_BY_SUFFIX` 查表**: 禁止任何分支直接写字面量。回归锁：`tests/test_record_container.py`。
- **命令构造统一到四个单一定义点（F-01）**: ① `_build_ffmpeg_input_args` ② `_build_record_output_path` ③ `_run_ffmpeg_record`+`_convert_after_record` ④ `_PLATFORM_RESOLVERS`+`_PlatformResolveContext`。禁止各平台分支手写 `command=[...]`。回归锁：`tests/test_platform_dispatch.py`+`tests/test_start_record_command_golden.py`。

### 日志、控制台与 GUI / 后台模式

- **Web 后台模式必须重建 loguru 控制台 sink**（web.py::_enter_background_mode）: 在 `import main` 之后才把 stdout/stderr 重定向到 `logs/web_console.log`。loguru sink 在 `add()` 时绑定具体对象，不调 `rebind_console_sink()` 重建则全部日志写往被隐藏控制台，`web_console.log` 只剩 print。**排查 Web 模式问题一律先看 `logs/streamget.log`/`PlayURL.log`，不要只看 `web_console.log`。**
- **GUI 父进程绝不持有录制日志文件句柄（`DLR_GUI_PARENT` 标记）**: `gui.py` 必须在导入任何 `src` 模块**之前**设 `os.environ["DLR_GUI_PARENT"]="1"`，拉起录制核心时 env 经 `src/logger.py::child_process_env()` 构建（剔除标记+固定 `PYTHONIOENCODING=utf-8`）。`src/logger.py` 导入期读该标记决定文件 sink 归属：GUI 进程只写 `logs/gui.log`，绝不创建 streamget.log/PlayURL.log（否则与录制子进程双开同日志文件、轮转 rename 抛 WinError 32、文件日志静默丢失+stderr 刷屏）。回归锁：`tests/test_logger_gui_parent.py`。
- **异常日志必须带异常类型与上下文，禁止裸 `logger.xxx(e)`**: Windows 下 `socket.timeout`/`TimeoutError` 的 `str()` 为空，只写 `{e}` 打出空白行。写法：`i18n.tr()` 模板+关键字实参（禁止 f-string）：`logger.debug(tr("<动作>: {masked_url} - {type_name}: {err}", masked_url=utils.mask_credentials(url), type_name=type(e).__name__, err=e))`。硬要求 `{type_name}`/`{masked_url}` 不可省；流地址校验失败还须额外输出 `status_code` 与 `content-type`，禁止静默吞异常。
- **[历史注 2026-10-20：本条描述的 pystray 托盘已随依赖摘除退役，gui.py 的 tkinter 路径不再持有托盘；此处仅作「macOS 上两个工具包同抢主线程」的成因存档，现行结论见上「Qt 的 GUI 线程必须是主线程；禁止给 Tk 进程塞第二个工具包」条]** **macOS GUI 双重主线程约束**（gui.py）: Tcl/Tk 只能跑主线程，而 pystray darwin 后端 `icon.run()` 接管主线程——两者互斥。唯一正确方案：主线程先 `tray.run_detached()`（darwin 后端仅注册 NSStatusItem 不启事件循环）再 `root.mainloop()`，绝不允许把 mainloop 放子线程。配套：① `run_detached()` 前主线程调 `icon._assert_image()` 预热并置 `_icon_valid=True`（PIL 惰性编码器在冻结环境非主线程首次初始化会原生崩溃）；② `_assert_image` 是 darwin 专有方法，通用路径调用会 AttributeError 被吞导致托盘静默禁用；③ detached 退出先 `icon.visible=False` 再 `icon.stop()`。改动后必须 `py_compile` 并通过 CI（复现需 macOS 冻结构建）。
- **无控制台环境 `sys.stderr is None`，`logger.add` 前必须判空**（src/logger.py）: `pythonw.exe` 与冻结 `console=False` exe 不分配控制台，stderr 全为 None，裸写 `logger.add(sink=sys.stderr,...)` 在导入期抛 TypeError 致 gui.py 静默死亡（pythonw 跑 gui.py 失败真正根因）。必须 `if sys.stderr is not None:` 才加控制台 sink，无控制台时跳过由文件 sink 兜底。排查窗口化静默崩溃：先装 `sys.excepthook`/`threading.excepthook` 落盘+弹窗钩子，再顺调用链 grep `sink=sys.`/`print_exc`/`sys.stdout.write` 判空。
- **多房间交织日志靠 `extra[room]` 列切出，不要靠 `[record_name]` 前缀**（src/logger.py::ROOM_FIELD）: 全局 patcher 写 `record["extra"]["room"]`（ContextVar 承载当前房间），两个录制文件 sink format 含 `{extra[room]}`。`start_record` 入口先绑 `序号{count}` 占位、解析出主播名后升级为完整 `record_name`。三条不要动：① `logger.configure(extra={ROOM_FIELD: ""})` 默认值不可删（缺则每一条日志 KeyError 被丢弃）；② `logs/gui.log` 行格式刻意不带该列；③ 本机制只加关联标识，不得顺手改日志级别/filter 分档/rotation/retention。已知边界：新起线程不继承 ContextVar（弹幕线程/push_message/转码线程池该列为空，仍靠关键字辅助）。回归锁：`tests/test_logger_room_context.py`。
- **GUI 控件层（阶段4 起）一律走 `src/ui_kit` 工厂且颜色不进工厂**（2026-10-03 定稿）: 全部 ttk 配色由 `src/ui_theme.ThemeManager` 注册的变体样式（`Card.TFrame`/`Success.TButton`/`Nav.TButton`…）从 token 派生，调用方以 `variant=` 选样式，**禁止在控件创建处散落配色**（唯一例外 `Colors.TERMINAL_*`——刻意主题无关，经 `terminal_text()` 落 tk 控件）。新增控件类型先在 `_build_ttk_settings` 登记变体，且新配色对先登记 `CONTRAST_REQUIREMENTS` 再取色。三条 ttk 适配坑（Tk 9.0 实测）：① `ttk.Button` **无控件级 `-font`**，带字体须经 `ui_kit.font_style()` 派生样式（显式复制基础变体的 configure/map——多段样式名跨段回退不可靠）；② ttk 的 `wraplength` 是**原始设备像素**（不随 `tk scaling` 缩放），自适应折行公式不再除缩放率；③ CTk 控件的 `configure` 重载**只收命名参数**，位置 cnf 字典被静默忽略（`configure({"wraplength": x})` 不报错但不生效——真窗回归锁抓出）。Treeview 行 tag 是行级的（不支持逐格着色）；`DataTable.sync` 必须保持行级增量（未变化行零触碰），改回整表删除重建会被 `tests/test_ui_kit.py` 抓红。[历史注] 「主窗口/Toplevel 仍是 CTk」为阶段4 过渡态——2026-10-03 阶段5 已整体摘除 customtkinter（root=`tk.Tk`、Toplevel=`tk.Toplevel`、CTkFont→点值 `tkfont.Font`、`_THEME_CTK_MODE`/`_ctk_mode_to_theme` 退役，「跟随系统」走 `ui_theme.detect_system_appearance()`），tk.Toplevel 标题栏跟随系统明暗为可接受观感边界。

- **Web 托盘（src/web_tray.py）走 QSystemTrayIcon，主线程必须交给 Qt 事件循环（2026-10-20 定稿）**: 该模块于 2026-10-20 由 pystray 迁到 PySide6（图标改 QPainter 现画，不再依赖 Pillow；菜单改 QMenu/QAction）。**`QApplication` 只能建在主线程**——本机实测在子线程执行 `QApplication(sys.argv)` 直接段错误退出（进程 exit code 139，Python 层捕获不到），与 Qt 文档「GUI 线程即主线程」一致。接线契约：`start()` 返回 True 表示托盘已占用主线程，web.py 必须把 uvicorn 挪到守护线程（`_serve_forever`；uvicorn 的 `capture_signals()` 对非主线程直接跳过，不抛 ValueError）并随后调用 `run_event_loop()`；返回 False 表示已降级（非 Windows / 缺 PySide6 / `isSystemTrayAvailable()` 为假），web.py 照旧在主线程 `asyncio.run(server.serve())`。三处不可省：① `app.setQuitOnLastWindowClosed(False)`（本进程没有任何 QWidget，否则循环会被提前带下去）；② `run_event_loop` 的看门狗 QTimer 既感知「服务线程已结束」，也是 Ctrl+C 在事件循环阻塞期间唯一的落地点（信号改由 `web.py::_install_sigint_shutdown` 接管，第二次 Ctrl+C 才 `request_quit()`）；③ `aboutToQuit` 里补置 `server.should_exit`，否则 `serve()` 不返回、web.py 的 finally 清理段（后处理线程池 / ffmpeg / 连接池）永远等不到。托盘菜单回调由此全部落在主线程，不再有 pystray 版「托盘线程调 ShowWindow」的跨线程假设。

### i18n 文案、目录与占位符

- **i18n 多格式目录与语言热切换**: `i18n.py` 按语言探测 gettext `.mo`→`<lang>.json`→`<lang>.yaml`（zh_CN 用 .mo、en_US/en_GB 用 .json、zh_TW 用 .yaml）；四目录键集合必须一致。修改 zh_CN.po 后必须 `python scripts/compile_po.py` 重编 .mo（测试强制字节级同步）。新增翻译串提取用 `python scripts/extract_i18n_strings.py`。**前端另行维护内嵌目录**：`web/app.js` 自带四套 UI 字串，**新增/修改翻译串须同步五处**（四份 i18n 目录+`web/app.js`），改完必跑 `node --check web/app.js`+`node --test tests/frontend/`。
- **形参日志必须走 `i18n.tr(模板, **kw)`，禁止再用 f-string**: f-string 在查目录前完成插值，带占位符的 msgid 永远匹配不上、翻译静默退化为原文。三条硬约束：① 模板必须是字面量常量串，占位符只能是纯标识符；② 格式/转换符由调用方预先求值后作实参传入；③ 占位符名由表达式确定性派生（`type(e).__name__`→`type_name` 等），改模板名必须同步改 kwarg 名。回归锁：`tests/test_i18n_migration.py`。`main.py` 的 `import i18n` 必须置于模块级 banner 打印**之前**。
- **测试必须冻结翻译为恒等映射**: `tests/conftest.py::_pin_identity_translation` 把 `i18n._tr` 固定为 `lambda t: t`，断言与语言解耦；不可删除该 fixture（翻译机制本身由 `tests/test_i18n_tr.py`/`test_web_api.py` 覆盖）。
- **`_2` 后缀占位符只在代码真传 `xxx_2=` 时才合法**: 目录里 `{message_2}`/`{msg_2}` 等来自调用方显式传入同名关键字（如 `msg_push.py` 传 `message=`/`msg=`/`errmsg=`）；历史上曾把只出现一次的占位符误写 `*_2` 致繁体 KeyError。新增带重复占位符的模板须确认调用方确实传了 `_2` 实参。
- **四语目录条目数权威口径是 `.mo` 头部 N（含头部空 msgid，故 N == 键数+1），往文档写条数必须同时给「取数命令+读数时刻+两种口径」并实测，不要推算**: 读取 `struct.unpack('<6I', open(mo,'rb').read()[:24])[2]`；与 `scripts/compile_po.py --check` 自报数一致，否则 .po/.mo 不同步。孤儿 msgid 不会变红需人工核对（删源码功能时要手工回查目录侧）。
- **形参日志门禁判据是「首参子树」不是「首参本身」（MID-68）**: `tests/test_i18n_migration.py` 不变量① 判据收紧为「首参子树中存在含 FormattedValue 的 JoinedStr」，唯一收敛处是 `tr()` 调用（只递归模板位）。`extract_i18n_strings.py` 仍只认常量串/单个 f-string 首参，看不见 `BinOp` 拼接——故新增形参日志一律写 `i18n.tr(常量模板, **kw)` 而非拼接式实参。
- **i18n 三件套门禁必须在 UTF-8 环境跑（MID-63 同源）**: `compile_po.py --check`/`extract_i18n_strings.py`/`tests/test_i18n*.py` 一律带 `PYTHONUTF8=1`，细则见「格式化命令」。
- **`tr()` 的两层 except 必须含 `AttributeError, TypeError`**: 译者目录写 `{x.y}` 而调用方传 `x=None` 实测抛 AttributeError、`{x:d}` 抛 TypeError；`tr()` 大量用在 except 分支里，二次异常会顶掉原始异常、把可归因的失败换成一条无关堆栈。承诺「永不抛」就必须接住这两类（回归锁 `tests/test_i18n_tr.py`）。`translated_print` 全程不做 `.format`、无同族缺口——若新增形参日志路径改走 format，须同步扩元组。
- **GUI 静态标签走 `T()` 登记表，语言切换必须整窗回填（2026-10-04）**: 构建期定型的标签经 `ui_i18n.T()` 交 `ui_kit` 工厂建时查表 + 登记（`register(控件弱引用, 模式, 标记)`）；`retranslate_all()` 按 `text`/`title`/`heading:<col>` 三种模式回填并清理死亡引用。硬约束：① 语言切换钩子必须依次做「`retranslate_all()` → 哨兵（`默认画质`/`全部房间`）重置为 `tr()` 后形态 → 动态面刷新 → 托盘 `rebuild_menu()`」，任一步缺失都有对应回归锁转红（`tests/test_gui_language_retranslate.py`）；② 重译与 config 写回必须是**两段独立 try**（重译炸了不得吞掉落盘）；③ 运行态会被周期性改写的标签（状态胶囊/侧栏状态）**不进登记表**——建时 `tr()` 即可，否则回填会把状态打回初始值；④ 启动期顺序：`_build_sidebar` 内 `set_language` 之后的标签天然正确，之前的少数标签靠 `_setup_ui` 末尾的 `retranslate_all()` 兜住（实测宿主探测 en_US 时品牌标签曾中英不一致）；⑤ 子进程探针/脚本若要按源文匹配标签，必须自行钉定语言（`set_language("zh_CN")` + `retranslate_all()`），conftest 的恒等映射只作用于 pytest 进程内。变异验证锚点须取「钩子处唯一」的多行块——单行锚点会命中 `__init__` 里的同名赋值，而桩实例跳过 `__init__`，变异静默不生效。⑥ **Qt 模式（2026-10-17 随 `src/gui_qt/` 新增的 `"qt"` 模式与 `set_text()`）与 Tk 有两处形态差异**：Qt 控件在 C++ 侧被销毁后 **Python 包装对象仍然存活**（弱引用不失效，且 `QApplication` 在存活期间仍持有顶层窗口），任何属性访问抛 `RuntimeError("Internal C++ object already deleted")`；故 `retranslate_all()` 必须接住 `RuntimeError` 并按死条目剔除，否则一条死条目会让整轮回填在半途崩掉（表现为「切完语言一半控件没变」）。同一原因导致**测试文件之间必须还原登记表**（`ui_i18n._ENTRIES`）：建过 Qt 窗口的测试文件会把 20+ 条存活条目留给后面按全局条数断言的 `tests/test_ui_i18n.py`。⑦ **Qt 侧「构造标签」与「`T()` 登记键」必须是同一个 msgid**（2026-10-17 实测 9 处按钮）：`action_button("📥  最小化到托盘")` 之后紧跟 `set_text(btn, T("最小化到托盘"))` 时，`set_text` 建时即回填并登记，构造期带 emoji 的标签会在启动回填与每次 `retranslate_all()` 被打回裸文本——图标永久消失，而单看任一行都「像是对的」。图标形态的键要取目录里**带图标的既有键**（本轮 9 处复用 Tk 遗留的三空格键 `▶   开始录制` 等，零新条目）；锁在 `tests/test_gui_qt_label_parity.py`（AST 判同源 + 带 emoji 配对下限 + 键必须四目录齐全），行为侧证据走 offscreen 真建页面读 `text()`。

### 配置键名、布尔口径与 SSL 验证

- **「禁用SSL证书验证的平台」仅在需要证书校验时生效（FFmpeg 9.0 语义）**: `http_config.get_effective_ssl_verify` 的平台覆盖仅在全局 `ssl_verify=True`（http 录制模式）参与读取；https 录制模式全局已禁用、平台覆盖无意义。`main.py` 启动时经 `_sync_ssl_disable_platforms` 把证书异常平台（虎牙/B站，`SSL_DISABLE_REQUIRED_PLATFORMS`）追加至配置键并写回——只追加绝不移除用户手填项。`update_config_line` 键匹配大小写不敏感，改回精确匹配会导致代码常量（大写）与配置文件行（小写）无法互找。
- **缺键补写必须幂等：同一节内落出两行同名键会让配置基线自坏**: `read_config_value` 的补写形态是「解析器内存 `set` + 全文件原子序列化」，两个持有不同快照的写者并发（跨进程，或同进程内重读后再补写）可在**同一节内**写出两行同名键；而本仓解析器为 `RawConfigParser()`（默认 `strict=True`），下一次读取直接抛 `DuplicateOptionError`——配置文件损坏、入口起不来。2026-10-17 实测到一次（`config/config.ini` 的 `是否启动时清理陈旧字节码缓存(是/否)` 同时出现在第 5 与第 44 行），已还原；运行期写产物**不得**提交进基线模板（红线见「风险控制（前置）·凭据与敏感配置红线」）。改配置写回路径后的最小自证：对同一份文件连续跑两轮「读取 + 缺键补写」，断言该键出现次数仍为 1。
- **读取侧容错层（同一条事故的第二半，2026-10-17 落地）**: `src/config_read.py`（只依赖 stdlib + i18n + logger，GUI 侧可安全 import，**不得**改从 `config_io` 取——那条链 `import main` 会把录制引擎锁体系带进 GUI 进程）提供 `tolerant_config_parser(preserve_case=)`（`strict=False` + `interpolation=None`，`preserve_case=True` 复刻 GUI 原地的恒等 `optionxform` 闭包）、`find_duplicate_options(text)`（按 configparser 口径复刻注释/分节/`=` 与 `:`/大小写判据）、`warn_duplicate_options(path)`（同一「路径+mtime」只点名一次 节/键/行号；记忆集封顶即清空重记，**不得**改成「放不下就不报」）。接线点：`main.py` 模块级 `config` 与 `_hot_reload_config`、`src/gui_qt/main_window.py` 的 `_dynamic_status_info` 与 `_read_config_value`、`src/ui_theme|ui_scale|ui_motion|ui_fonts` 的偏好读取。回归锁：`tests/test_config_read.py`、`tests/test_config_io.py::TestMissingKeyWritebackIdempotency`——后者的判据必须含「写回产物仍能被 **strict** 解析器整份读出」，只数「该键出现几次」挡不住整节被重复追加（变异 M4 加固前漏检、加固后转红）。**尚未纳入**的 strict 解析器：`src/web_config.py`×3、`gui.py`×2、`build_exe.py`×2、`src/web_api.py`、`src/ttwid.py`、`src/logger.py`、`scripts/douyin_live_recorder_standalone.py`——重复键下它们按各自 `except` 静默降级、不构成崩口，任何「全仓读取侧已容错」的表述不得再写。[历史注] 本项原含 `src/utils.py`×2（`read_ini_value` 与 `update_config`），2026-10-18 随 CODE_REVIEW 整改的 M-08 迁入容错层：两处改用 `config_read.tolerant_config_parser`（经新增单点 `_tolerant_ini_parser()`），**只能函数内延迟导入**（顶层 import 会经 `web_config` 成环，由 AST 结构锁钉），`preserve_case=False` 以保持历来「大小写不敏感匹配」口径不变。
- **config.ini 键名禁止含 `=`/`:` 等 configparser 分隔符**: 含 `=` 时读取侧在首个分隔符处截断、写回侧 Python 3.14+ `configparser.write()` 抛 `InvalidWriteError`（3.13 静默写成功，勿把仅 3.13 失败、3.14 通过的用例误判为回归）。括号提示可写 `(0为不限制)` 无分隔符形式。`read_config_value` 的缺键兜底已硬化为内存 StringIO 序列化成功才落盘+捕获 `(OSError, configparser.Error)` 降级，但键名本身须避开分隔符。
- **布尔配置写入 `true/false` 曾被静默判成兜底值**（P0）: 旧实现 `options.get(read_config_value(...), 兜底)` 值不在字典里时静默返回硬编码兜底，导致系列配置生效值漂移。审计须比对「生效值」而非字符串（逐键算 `解析(现值,默认)` 与 `解析(旧值,默认)`）。现已统一到 `src/config_bool.py`（见「关键约定」第 9 条）。回归锁：`tests/test_config_bool.py`/`tests/frontend/test_quality_ui.mjs`。
- **`config.ini` 键集审计三个陷阱**: ① `read_config_value` 的**键是第 3 个参数**——按首参字面量写正则会扫出 0 条；② `config/config.ini` **带 UTF-8 BOM**，审计脚本须用 `encoding="utf-8-sig"`；③ 扫出「缺失键」里有 3 个是有意不写回的旧键迁移读取（`是否强制启用https录制`/`是否禁用SSL证书验证(是/否)`/`虎牙是否禁用SSL证书验证(是/否)`），由 `config.has_option(...)` 守卫，不是缺口不要补。

### 凭据与敏感配置脱敏

- **出站链路的异常文本进日志前必须过 `utils.mask_credentials`，存量以棘轮只降不升**（2026-10-18 定稿，门禁 `tests/test_exception_log_masking.py`，起因是 CODE_REVIEW M-05）：httpx/urllib 的异常 `str(e)` 里常内嵌**带签名/Cookie/token 的完整请求 URL**，而 `logs/` 按大小轮转保留多份 ⇒ 凭据等于长期落盘。判据口径三条，缺一即门禁失效：① 只扫**函数体里确有出站动作**的函数（`async_req`/`sync_req`/httpx 客户端构造/`urlopen`/`build_opener`/`requests.`/`websockets`/`.connect(`），宁可漏报也不把纯本地解析拉进来当噪声；② 关键字实参必须从 **logger 调用的整棵子树**取——本仓日志一律写 `logger.warning(i18n.tr(模板, e=e))`，`e=` 挂在**内层 `tr()`** 上，只查 logger 自己的 keywords 会一条也看不见（M-05 排查期实测的第一版假绿）；③ 反向见证：扫描面必须同时产出「已脱敏」与「未脱敏」两类实参，只见单侧说明判据失明。**不得**把这条做成全仓零容忍：同口径实测在函数级出站上命中 23 个函数 / 34 个实参，零容忍会把门禁写成永久红榜、红榜没人看、保护力归零（M-26 同族教训）。登记表按 `(文件, 函数)` 双向相等——表外新站点即红，表内站点被整改却不删行也红。**待办**：登记表中「凭据型」11 条（`src/spider.py` 的 bilibili/douyin/kuaishou/斗鱼 token/登录接口、`src/room.py::get_unique_id`、`src/ws_client.py::connect`、`src/platforms/douyin.py::start`）应优先烧掉，「下载源型」12 条取数指向公共 CDN、风险面是路径而非凭据，排后。
- **敏感配置判定必须「节白名单 + 键名正则」双重**（src/web_config.py/web/app.js）: 仅按节名会漏掉 `[推送配置]` 内的 `tgapi令牌`/`发件人密码(授权码)`/`pushplus推送token` 及各平台节内 `popkontv_token` 等独立凭据。`expiry|timeout|有效期|过期` 反向例外放行数值型运维参数。前端 `saveConfig` 跳过 `'***'` 掩码的约定是写入侧唯一防线不可移除。写日志 URL/代理一律经 `utils.mask_credentials()`（logs 会轮转保留多份，凭据等于长期落盘）。

### 类型检查、注释与静态门禁

- **PEP 758 `except A, B:` 在 3.14 合法，语法/编译检查一律用项目 venv 的 Python 3.14**: 用 3.13 做 `compileall`/`py_compile` 会把全树误报 `SyntaxError: multiple exception types must be parenthesized`。新增/修改写无括号，但不要把现有无括号写法修回加括号（与约定相反）。**不支持 `as` 绑定**：有异常对象时必须 `except (A, B) as e:`（语法强制），批量替换时务必 grep `as` 用法（与「代码风格」except 条目同口径）。**本条已有常驻门禁 `tests/test_pep758_except_form.py`（2026-10-18，CODE_REVIEW §7.11 第③条）**：① 全仓 .py 必须能被当前解释器整树解析（把「用错 Python 版本做语法检查」这个反复出现的排查坑钉住）；② 无括号多异常处理器计数**不得低于基线**（批量加括号在 AST 里与无括号完全同形、black 两种写法都接受，因此只能力学监测、无法靠 `ast.dump` 或 `black --check` 发现——即「注释检查工具」盲点①的门禁化）；③ **基线必须由本锁自己的分类器实测产出**，不得用行正则代算：首版基线取 60（正则粗扫），变异验证当场发现摘掉一处仍判绿（AST 实数 61，61→60 恒满足旧基线），棘轮与它的基线不同源就等于留一条松缝。
- **protoc 生成模块需手写 `.pyi` 存根**（src/proto/douyin_pb2.py）: 消息类经动态注入，mypy 看不到 `PushFrame`/`Response`/`ChatMessage` 属性而报 `attr-defined`。已建 `src/proto/douyin_pb2.pyi` 声明 3 个消息类及字段（继承 `google.protobuf.message.Message`）。新增字段引用必须同步补存根。
- **平台专属符号必须 `sys.platform` 字面量门控**（mypy 跨平台 CI 检查）: `ctypes.WinDLL`/`windll` 仅 Windows typeshed 有，CI 的 mypy 跑在 linux runner。修复模式：函数体首行早返回 `if sys.platform != "win32": return`；注解需引用平台符号时降级为 `object | None`（禁 `sys.platform` 条件类型别名）。**禁用 `# type: ignore`**（Linux 必要、Windows 多余，basedpyright 报 `reportUnnecessaryTypeIgnoreComment`）。验证双跑且均不带路径：`mypy`+`mypy --platform linux`。门控条件写反静态检查发现不了，须运行时用例锁定（`tests/test_i18n.py::TestWindowsUiLanguagePlatformGate`）。
- **三参 `getattr` 不做字面量名解析，模块级已声明属性一律直接访问**（mypy Any 泄漏）: `getattr(obj, "attr", default)` 返回 `Any | None`，`warn_return_any` 下报 `no-any-return` 且后续属性链类型检查全部失效。凡目标属性有模块级声明（如 `main.scheduler: ConcurrencyScheduler | None`）直接 `main.scheduler` 访问；确需容错用 `cast`。
- **protobuf 升级必须先同代重新生成再放开版本上限**（F-14）: `douyin_pb2.py` 为 protoc 25.x 产物、标注 DO NOT EDIT，本环境无 protoc。**禁止手改生成文件**；声明区间现为 `protobuf>=6.33.5,<8`——**上限 `<8` 不可删**（gencode 4.25.3 与 runtime 跨大版本存在兼容窗口外失效风险），下限 2026-09-26 由 `deps-audit`「下限复核」从 `6.31.1` 抬到 `6.33.5`（PYSEC-2026-1805 影响 6.31.1，修复于 5.29.6 / 6.33.5，旧下限自身就在受影响段内）。事实源是 `pyproject.toml [project.dependencies]` 与 `requirements.txt`，本文件不复述取值以外的规格。回归锁：`tests/test_proto_runtime_compat.py`。
- **`main.py` 内引用模块全局量不得加 `main.` 前缀**: 本文件模块级 `main` 是入口函数而非模块对象，`main.recording_enabled` 运行期必抛 `AttributeError`。
- **删除模块级函数/常量前必须 grep 全部调用点**: `main.py` 曾删 `_ffmpeg_reported_output_failure()` 但留调用点，mypy/basedpyright/tests 三面同时转红，且因调用点在 `and` 右侧短路、在 Linux CI 上恰不炸（典型「本地红、CI 绿」）。执行「删除符号」改动：① grep 收全调用点再删；② 删完立刻跑 mypy+完整 pytest；③ 用例输出路径必须用 `tempfile.gettempdir()`（旧 `"/tmp/out.ts"` 在 Windows 父目录不存在，两端语义相反）。`check_annotations.py` 已常驻符号可达性检查兜底。
- **测试桩转发函数里 `*args`/`**kwargs` 一律注解 `Any`（写成 `object` 只有 basedpyright 报错）**: `monkeypatch.setattr(Path, "unlink", stub)` 类转发桩若 `*a: object, **k: object` 转发，basedpyright 会按声明类型逐个匹配形参报 `reportArgumentType`；mypy 不报故只跑 mypy 会漏。统一 `*args: Any, **kwargs: Any`（必要时 `cast` 收窄返回值）。
- **CI 的 typecheck job 必须装 pytest，否则 `tests/` 的类型检查是半盲的**（2026-09-26 修）: 该 job 若只装 `requirements.txt + mypy`，`tests/` 里的 `pytest.*` 全按 `Any` 检查——fixture / `MonkeyPatch` 免检不说，`pytest.fail()` 的 `NoReturn` 也丢失，于是「声明了非 `None` 返回类型、却以 `pytest.fail()` 收尾」的辅助函数被判成 `[return]`（`tests/test_proto_runtime_compat.py::_declared_protobuf_specifier` 实测只在 CI 红、本机恒绿，无法本地复现）。现随 consts 补装固定版本 `pytest==9.1.1`（与 black / isort / mypy 同口径，防「代码未改动却 CI 变红」）。长期约定：辅助函数走不到终点时统一 `raise AssertionError(...)`（天然 `NoReturn`，不依赖 pytest 是否可见），**不要**依赖 `pytest.fail()` 的返回类型，**也不要**在其后补不可达语句（basedpyright 报 `reportUnreachable`）。复现「pytest 不可见」的老环境：`mypy --no-site-packages`（该模式下 `src/` 多出的 5 条 `no-any-return` 属过度剥离噪声，非真实问题）。
- **`[tool.mypy].exclude` 的运行时二进制目录条目必须写目录段锚定形态 `(^|/)<名>/`，禁止裸名**（2026-10-03 定稿）: mypy 的 `exclude` 是 `re.search` 对「相对路径 + 正斜杠归一、目录补尾 `/`」的**子串**匹配，裸名会把模块名含该词的源码整个排除出门禁；而 black（`/( … )/` 只命中目录段）、isort（`extend_skip` 按名）、basedpyright（目录 glob）的同名排除均无此误伤。两条衍生约束：**新增排除项一律写锚定形态**；**新增源码文件也不得取这些裸名**——2026-10-17 `src/gui_qt/pages/logs.py` 撞上裸名 `logs`、被无参 mypy 静默漏查（正是本条预言的形态），由 `tests/test_run_gates.py::test_mypy_exclude_never_shadows_source_files` 抓出，日志页因此改名 `runlog.py`（改名是它期望的修法，收紧 exclude 会影响别的平台/目录形态）。其余裸名条目（`downloads`/`recordings`/`logs`/`backup_config`/`typings` 等）现无 `.py` 路径碰撞、维持原样。裸名时代的失明文件数、锚定后新暴露的 8 处存量错误形态与修复前后 source-files 读数见 `docs/agent-reference/measured-evidence.md`「门禁工具版本与 exclude 锚定的历史读数」。

### 热路径性能（数据结构 / 正则）

- **`main.py` 主循环去重容器必须为 `set`，禁止退化成 list/O(N²)**: `url_comments` 与循环内的 `_line_list`/`_url_line_list` 均用 `set` 做成员检测，移除用 `.discard()` 而非列表重建，`text_no_repeat_url` 用 `dict.fromkeys` 保序去重。80+ 房间时 list 实现退化 O(N²)。`need_update_line_list` 仍 `list`（要保序 append+pop）。
- **高频正则提模块级常量、按 key 缓存，禁止函数内 `re.compile`**: `_EMOJI_PATTERN`/`_URL_PATTERN`/`_BANDWIDTH_PATTERN`/`_DOUYIN_HEVC_FLV_PATTERN` 提模块级编译；`update_config_line` 按 key 编译的正经 `functools.lru_cache(maxsize=128)` 缓存。

### 构建产物、依赖与运行时基线

- **Node 24 / FFmpeg 9.0 兼容基线**: 9.0 移除的 CLI 参数禁止引入。
- **近期性能优化与修复完整变更记录见 `CODE_WIKI.md`/`CODE_WIKI_EN.md` 更新日志**: 本文件只沉淀可回归硬约定。
- **`StopRecording.vbs` 必须保存为 UTF-16 LE（带 BOM）**: 由 wscript/cscript 消费，按系统 ANSI 解释 `.vbs`，UTF-8 保存会让中文乱码（源文件统一 UTF-8 约定不适用于该文件）。进程匹配现为三层：① 程序专属 exe 按映像名命中；② python 须命令行含入口脚本或 pip 启动器名 `douyin-recorder`（刻意不按项目目录匹配，避免误杀编辑器工具进程）；③ ffmpeg 须「父进程为已识别录制主进程」或「路径/命令行锚定程序目录」。结束顺序先录制主进程（`taskkill /f /t /pid` 连带子进程树）后残留 ffmpeg——原「先杀 ffmpeg→等 10s→再杀主进程」存在主进程重建 ffmpeg 竞态，且强杀不走 atexit 不执行日志归档（本脚本仅作最后手段）。
- **包内 ffmpeg 的 PATH 前置在 Apple Silicon 上必须「让位」（W6）**: full 包内置 macOS ffmpeg 是 x86_64 静态构建，已装原生 arm64 用户会被遮蔽强制走 Rosetta。判据收敛到 `src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir()`（唯一事实源，main.py 只保留「重复插入跳过」守卫）。五条判据：`darwin` ∧ `arm64` ∧ 包内目录存在 ∧ 注入前 PATH 快照另有 ffmpeg ∧ 那份 realpath 不在包内目录。三条不可回退：① 探测必须用调用点传进来的 pre-injection PATH 快照（直接读 `os.environ["PATH"]` 会探到自己刚前置的那份）；② 自我遮蔽形态（用户已把包内目录永久写进 PATH）须按 realpath 归一后排除；③ Windows/Linux/Intel Mac 行为逐字不变。`scripts/douyin_live_recorder_standalone.py` 有同名同语义判据（该文件不 import src），改判据必须两处同改、两边注释互相点名，行为等价性由 `tests/test_ffmpeg_path_preference.py::test_twin_agrees_on_every_criterion_combination`（9 格矩阵）锁住。
- **主线安全/正确性修复必须核对 standalone 孪生副本（2026-09-30 定稿，S-01/S-02 事故沉淀）**: 凡涉及 `sync_http` opener 白名单、`-protocol_whitelist`、ffmpeg 终止链（`ffmpeg_proc`）、`config_bool` 布尔口径、MID-49 类签名/编码修复时，必须同步核对 `scripts/douyin_live_recorder_standalone.py`，并在提交说明写明「已核对 / 已回灌 / 刻意不回灌及原因」——该副本按设计不 import src/，主线修复不会自动生效，单边漂移会在独立发行版上重开已修防线。副本自身的探针/录制链防线（协议白名单 opener、候选内网判定、命令日志脱敏）由 `tests/test_regression_2026_09_22_standalone.py` 独立回归锁护持。
- **`DouyinLiveRecorder.egg-info` 是构建产物、会长期腐化，改 `pyproject.toml` 后须重建**: `importlib.metadata`/`pip install -e .` 会读它；改 `[project].dependencies`/`version`/`packages`/`package-data` 后跑 `python scripts/sync_metadata.py` 重建（与 `uv lock` 一并，口径见「关键约定」#1）。
- **依赖对账必须先剥 `requirements.txt` 行内注释**: 注释紧贴版本号不带空格（如 `brotli>=1.2.0#b站弹幕解压`），整行比对会全量误报不一致；比对前 `line.split("#", 1)[0].strip()` 再归一化。egg-info 里 `protobuf` 规格被 setuptools 规范化成 `<8,>=6.33.5`（与 pyproject `>=6.33.5,<8` 顺序不同不是差异），应按「包名+规格集合」比对。
- **排除目录归一化必须先剥 `**/` 再剥 `*/`**: basedpyright 用 `**/downloads`、coverage 用 `*/downloads/*`，若先剥 `*/` 会把 `**/downloads` 切成 `*downloads` 致「basedpyright 缺 7 个目录」假结论。
- **发布链运行时二进制必须 fail-closed 钉定（SEV-10）**: 三层防线缺一不可：① `_PINNED_RUNTIME_SHA256`（64 位小写十六进制，占位/空串=未钉定，不得回填本地自算哈希）；② `--require-pinned` 缺钉定即 `SystemExit`；③ `check_runtime_pins.py` 表为空/缺平台/缺槽位 rc=2。Linux 取数端点必须是 `releases/tags/<月末标签>`，不得用 `releases/latest`。**macOS 取数端点必须是 evermeet 页面上的版本化直链（`ffmpeg-<ver>.zip` / `ffprobe-<ver>.zip` + 同名 `.zip.sig`），不得用 `getrelease/…` Download API**：该 API 连同其 `/sig` 形态已于 2026-10-18 被上游以「exorbitant abuse」为由整体 **410** 下架（页面原文 `This endpoint has been removed due to exorbitant abuse`），且它本是滚动别名、签名钉不住版本，410 后 macOS 两支归档全取不到、`ffmpeg/` 留空目录，最终由出包前自检判缺件终止（取数与读数以「2026-10-18 复测 · evermeet macOS 取数端点整体下架」表为准，含 429 限速边界）。抬版时要人工同步换两支归档的版本号并重核签名，属与 Linux 月末标签同构的人工闸口。详细验证流程见 `.agents/skills/runtime-pin-verification/SKILL.md`。回归锁 `tests/test_build_exe.py::test_linux_ffmpeg_urls_pin_an_immutable_release_tag` 与 `…::test_macos_ffmpeg_urls_point_at_immutable_artifacts`（后者含「两支归档版本必须一致」「两架构逐槽相等」）。**node 槽的失配形态要认准**：`_download_nodejs` 取 `dist/index.json` 首条 `lts`，上游一发新 LTS 即**多平台同时**报 `node-v<新版本>-*` 哈希不匹配（2026-10-18 实测 win-x64 / linux-x64 / linux-arm64 / macos-arm64 四条一起红，实际值恰为 `v24.22.0` 官方公布值）——这是版本漂移，不是构建机中毒，处置是回官方 `https://nodejs.org/dist/<新版本>/SHASUMS256.txt` 重取并钉定，**不得**把 CI 报出的实测值当基线回填；且要按 `_download_nodejs` 实际请求的扩展名挑行（Windows `.zip`，其余 `.tar.gz`），同版本 `.tar.xz` 是另一行。
- **运行时钉定的「在线来源层」默认 off，且在线值只在清单有独立认证时才可被采用（2026-10-17 定稿）**: `build_exe.py` 的在线来源层（三态 `--pin-source` / `DLR_RUNTIME_PIN_SOURCE` = `off`|`verify`|`adopt`）**不得**被当成「把硬编码哈希换成运行时拉取」——钉定表的强度来自**通道独立**，而 gyan.dev 的 `.sha256`、`api.github.com` 的 digest 与产物同源同服务器，中间人换归档即换清单，「拉清单→当期望值→比对产物」恒等通过。三条硬约束：① 默认 `off`，一次网络请求都不发；② `verify` **永不写入**期望值，只比对并在不一致时按 `require_pinned_hashes()` 决定终止或告警；③ `adopt` 仅对 `trust=signed`（配套分离 GPG 签名 + 已钉 40 位主钥指纹）且**清单本身验签通过**的槽位生效，`advisory` 与「signed 但指纹未登记」一律回退内置表。在线值一律过 `_SHA256_PATTERN` 才可能被采用；失败值不进进程内缓存。node 清单 URL 的 `{version}` 由 `_download_nodejs` 解析结果代入，未解析即显式跳过（**不得**拼残缺 URL）。回归锁：`tests/test_build_exe.py` 的 `test_online_layer_is_off_by_default_and_never_touches_network`、`test_verify_mode_never_writes_the_online_value`、`test_advisory_source_is_never_adopted`、`test_signed_source_without_pinned_fingerprint_is_never_adopted`、`test_signed_manifest_is_adopted_only_when_its_own_signature_verifies`。
- **三类「钉定/校验」互不覆盖**: ① 发布期运行时二进制（含官方签名档）；② 运行期自动安装 TOFU 基线；③ 签名脚本层 `_JS_SHA256_EXPECTED`。新增远程执行代码必须落进三类之一。详细边界判定见 `.agents/skills/runtime-pin-verification/SKILL.md`「三类钉定/校验互不覆盖」章。
- **发布面 ffmpeg 来源增删必须同批改三处**: ① `_FFMPEG_DOWNLOAD_URLS`；② 钉定取值或签名档标记；③ `_ALLOWED_HOSTS` 主机白名单（退役主机须移出）。macOS 另有**两处同批改点**：`_EXTRA_EXECUTABLE_URLS`（ffprobe 独立归档）与 `_RUNTIME_GPG_SIGNATURES`（签名 URL 必须等于产物 URL + `.sig`，2026-10-18 起；旧形态是产物 URL + `/sig`，随 Download API 一起下架），只改产物侧会让验签长期假失败——同构关系由 `tests/test_build_exe.py::test_gpg_config_shape_and_source_consistency` 机检。归档层级经 `_extract_linux_ffmpeg_binaries()` 递归按名取件，不得写死 `bin/` 或平铺。详细流程见 `.agents/skills/runtime-pin-verification/SKILL.md`「发布面 ffmpeg 来源增删」章。
- **运行期 Linux 直下的 URL 与发布链是两份物理副本，换月末标签必须同批改两处并重取钉定值**: `src/ffmpeg_linux_download._LINUX_FFMPEG_URLS`（键 `linux64`/`linuxarm64`）与 `build_exe._FFMPEG_DOWNLOAD_URLS` 的 Linux 两项**逐字相同但各存一份**——冻结 exe 在 import 期拿不到根目录的 build 脚本，「让运行期去读发布链常量」等于给打包产物加一个不存在的依赖。等价性由 `tests/test_ffmpeg_linux_download.py::TestUrlParityWithBuildExe` 机检（测试直接 `from build_exe import _FFMPEG_DOWNLOAD_URLS`——`tests/__init__.py` 使仓库根成为 import 基准目录，故根目录脚本可普通 import，取到的是与 `check_runtime_pins._load_build_exe` 按路径加载**同一份**常量；[历史注] 本句原写「用 importlib 按文件路径加载 build_exe.py」，2026-10-03 经 final-review M-1 对照测试本体证伪：按路径加载的是另一支 `tests/test_check_runtime_pins.py`），漏改一侧即红；改标签的同时必须**重取** `_PINNED_RUNTIME_SHA256` 的两个 Linux 槽。同一模块的期望值通道 `api.github.com` 属**同源一致性校验而非来源认证**——它与产物**同平台、异服务**（API 域 ↔ 对象存储域），强度与 gyan.dev 的 `.sha256` 文档同级（MIN-2258 同一措辞），**注释与日志一律不得写成「已认证来源」**；真正多出来的那半只是「URL 里的月末 autobuild 标签不可变，期望值不随上游重发漂移」。故 `tests/test_ffmpeg_install.py::DOWNLOAD_SOURCES` 保持**两条**：`api.github.com` = `官方哈希`、`github.com` 仍 = `TOFU`（master-latest 那条路还在），**不得合并**成一条。
- **运行期 Linux 直下的两条「不得回退」实现形态**: ① `master_allowed` **由调用方传参**——实参位是 `install_ffmpeg_linux()` **函数体内**调用直下入口的那一处（`src/ffmpeg_install.py` 里的 `install_ffmpeg_linux_native(execute_dir, master_allowed=_master_source_allowed())`，按锚点引用；入口签名为 `install_ffmpeg_linux_native(dest_dir, arch=None, *, master_allowed=False)`），新模块**不得**自己读 `FFMPEG_MASTER_ALLOWED` 环境变量——`ffmpeg_install` 已 import 本模块，反向 import 判据函数即构成循环依赖；[历史注] 本条原把实参位误写成 `install_ffmpeg_linux()` 的形参——该函数自身不收这个关键字，写成它的形参会造出一条不存在的参数；2026-10-03 经 final-review M-2 对照源码改正；② `_install_binaries()` 是**两趟**（先全量递归定位 `ffmpeg`/`ffprobe`、缺件即返回且 dest 侧零改动，两件齐了才 mkdir + copy + 补执行位），不得复原成「边找边拷」——那会留下半截安装，且 `dest/ffmpeg/` 空壳本身成为「装过了」的假证据（回归锁 `tests/test_ffmpeg_linux_download.py::TestBinaryLayoutDiscovery::test_missing_companion_leaves_no_half_install`）。接线处另有「`apt update` 失败不再在 apt 块内早退，改落函数末尾统一出口」的形态改动（非 root 的 Debian/Ubuntu arm64 机器上 `apt update` 失败是常态，而这类机器正是直下的目标人群），回滚 S2 时须连同该 `else:` 嵌套一起还原才等价，见 `docs/worklog/PROPOSAL_2026-10-02_linux-arm64-ffmpeg.md`「九、回滚方案」。
- **`Dockerfile` 的 `ARG` 必须声明在使用它的指令之前，且门禁要断言行序（MIN-14）**: `LABEL version="${APP_VERSION}"` 写在 `ARG APP_VERSION` 之前会固化空串且构建期不报错。现 `check_version.py` 另断言「`ARG APP_VERSION` 声明行 < 使用点所在指令起始行」（多行续写须回溯指令头、跳过注释行）。新增 ARG/ENV 消费点同理。
- **`scripts/check_coverage.py` 无数据即 rc=2 硬失败，不得退回 WARN（MIN-19）**: 「数据文件不存在」「JSON 读不出」「files 为空」三类都必须走 rc=2 并打印 `pytest --cov=src` 下一步命令（与「模块查不到按失败处理」同族防线，不可互替）。CI test job 顺序固定 `pytest --cov=src` → `check_coverage.py`。
- **不可信输入不得跑浮动 ref 的第三方动作（MIN-17）**: `issue-translator.yml` 触发源是任意外部贡献者正文，已降级为仅 `workflow_dispatch`+降权。不得凭记忆填 SHA、不得为恢复便利加回触发器；其余第三方非认证动作（`trivy-action` 已 SHA 钉定等）按同判据区分。
- **镜像的 GUI 依赖由 `INSTALL_GUI` 单开关控制，默认 false**（2026-10-17 定稿）: GUI 窗口层迁 PySide6 后它进了运行时清单，镜像侧的 `pip install -r requirements.txt` 于是会把整只 PySide6 轮子（本机解压尺寸读数见 `docs/agent-reference/measured-evidence.md`「打包与镜像体积读数」）装进只跑 `main.py` / `web.py` 的镜像——实测两者在屏蔽 PySide6 后导入链完整，而 slim-bookworm 运行阶段没有 QtWidgets 的链接依赖（libEGL/libGL/glib/fontconfig/xkbcommon…），默认装入只会翻倍体积却仍起不动窗口。三条硬约束：① **过滤只发生在镜像侧**，`requirements.txt` 与 `pyproject [project.dependencies]` 的集合相等锁不受影响，**不得**为瘦身把 PySide6 从清单里删掉；② 「阶段1 剔除 PySide6」与「阶段2 按需装 Qt 运行库」是同一个开关的两半，`ARG` 不跨阶段、两处必须同条件同改；③ compose 的 `gui` 服务必须显式传 `INSTALL_GUI: "true"` 且**另用一枚 tag**（`:latest-gui`）——build 配置不同的服务共用同一 image 名时，后构建的一方会覆盖另一方正在使用的 tag；发布工作流（`docker-publish.yml`）**不得**传 true，对外镜像必须保持 slim。回归锁 `tests/test_dockerfile_image_gui_arg.py`（四条判据 + 判据自检，六处变异实测各自转红）。
- **`docker-compose.yaml` 不得保留 `:latest` 拉取回退（MIN-18）**: 锚点内已设 `pull_policy: build`，直接 `up` 就地构建而非拉 registry 同名 `:latest`。
- **`make_zip` 的产物名一律整体 f-string 拼接，禁用 `Path.with_suffix(".zip")`（2026-09-27 CI 实红）**: `with_suffix` 按**最后一个点**切分扩展名，而版本号本身带点，实测 `DouyinLiveRecorder-v4.3.0-windows-amd64-lite` 的 `Path.suffix` 是 `.0-windows-amd64-lite` → lite 与 full 同名 `DouyinLiveRecorder-v4.3.zip`（`linux-x86_64` 同形），`--dual` 第二次以 zipfile `"w"` 原地截断第一次且不报错，dist/ 只剩一个 zip、平台/架构段消失，`Build executables + smoke test` 与「lite+full 齐全」同时落空。同族判据：① 产物命名类用例必须断言**名字本身**（正则结构锁），只断言 `is_file()` 或 `SystemExit` 文本的用例对名称漂移全盲；② `version`/`suffix` **两个入参位**含路径分隔符时拼出的都是子路径、成品落到 `DIST_DIR` 之外，故断言「父目录仍是 `DIST_DIR`」且用例两侧都测；③ `--dual` 与 `--no-zip` 互斥并 fail-fast（`--dual` 分支从不读 `no_zip`）；④ 出包后拿 `make_zip` 的**两个返回值**做事后校验（`_assert_dual_zips_are_two_files`：名字互异 + 均是文件），单次调用的守卫只能自证「这一次」；⑤ 出包前清 `DIST_DIR` 里 `{APP_NAME}-v*.zip` 形态的陈旧产物（`_clean_stale_release_zips`，打印被删清单），否则复用工作区的 runner 会把上一轮 zip 一起被 `path: dist/*.zip` 扫进附件，`--no-zip` 路径不清理。产物名示例一律写 `windows-amd64`（`platform.machine().lower()` 的实际取值），`x64` 只是 `_NODE_ARCH_MAP` 归一后的运行时键名。回归锁（均在 `tests/test_build_exe.py`）：`test_make_zip_name_keeps_dotted_version_and_variant_suffix`、`test_dual_suffixes_do_not_collide_on_one_zip`、`test_make_zip_refuses_name_containing_path_separator`、`test_dual_and_no_zip_are_mutually_exclusive`、`test_dual_build_prunes_stale_zips_before_first_zip`、`test_no_zip_build_keeps_existing_dist_zips`、`test_dual_build_aborts_when_both_variants_land_on_one_zip`、`test_dual_build_aborts_when_a_variant_zip_is_missing`、`test_clean_stale_release_zips_only_touches_own_artifacts`。

- **打包图标的 `EXE(icon=)` 与 `datas` 是两条独立通道，缺一条即半途状态（2026-10-22）**: `icon=` 决定**exe 文件自身**的资源（资源管理器 / 任务栏 / Alt+Tab），`datas` 收集的那份供**运行期**读取（Qt 窗口图标、托盘、`/favicon.ico`）——只配前者会出现「任务栏有图标、面板标签没图标」。两条硬约束：① 图标文件缺失时 `build_exe.icon_spec_value()` 必须回 `"None"`，**不得**把路径原样塞进 spec——PyInstaller 对不存在的图标在 Analysis 阶段直接中断整轮打包，而「图标没换」不该让构建红掉；② `.ico` 内的帧编码按尺寸分档（≤64 用 BMP、≥128 用 PNG）：Windows 资源管理器与旧 GDI 取小图时对 ICO 内的 PNG 帧存在兼容瑕疵（16px 列表视图偶发不显示），而 256 档若用 BMP 要 256KB、占整包 98%。Pillow 的 ICO 保存不支持同包混编，故 `assets/app.ico` 由手写 ICONDIR 生成；回归锁 `tests/test_ui_icons.py::test_repo_icon_frame_encoding_is_mixed_by_size` 会让「统一成 PNG」变红。
### 装饰器与平台兜底契约

- **装饰器与 `def` 之间的注释会让装饰器绑到下一个 `def`**: Python 允许 `@decorator` 与 `def` 间夹注释行，会把兜底套在返回 `str` 的同步辅助函数上而目标平台入口裸奔无兜底。约定：`@decorator` 必须紧贴 `def`，说明注释写在装饰器**上方**。排查 `grep -A3 '^@trace_error' src/spider.py`。
- **平台解析函数返回契约必须匹配兜底装饰器**: `trace_error_decorator` 失败时回 `{"is_live": False}` 只适用于返回 dict 的函数；返回 str/tuple/None 的必须用 `trace_error_decorator_or_none`（回 None），否则调用方解包抛 ValueError 被自己装饰器二次吞没。调用点须显式判空再解包，新增平台先看返回注解再选装饰器。
- **`_loads_dict` 与 `_safe_loads` 的分工**: `_loads_dict` 内部复用 `_safe_loads`——平台返回 HTML（WAF/302/Cloudflare/截断 JSON）时回 `{}` 并记 warning，**不再抛 JSONDecodeError**（103 处调用任一抛错都会被兜底装饰器吞成「未开播」；2026-09-30 实测 `grep -c '_loads_dict(' src/spider.py` = 104 行含 1 处定义，旧读数「约 40 处」已证伪）。`tests/test_spider.py::TestLoadsDict::test_invalid_json` 断言返回 `{}` 不要改回 `pytest.raises`。
- **spider.py 平台解析一律走 `_loads_dict`+`_dig/_dig_str/_list`，裸 `json.loads` 由棘轮锁住不得回升（MID-48）**: 剩余唯一 1 处是 `get_twitchtv_room_info`（GQL 返回数组）。判据 `tests/test_spider_hardening.py::BARE_JSON_LOADS_CEILING = 1`（只降不升）+ 零裸 loads AST 扫描。配套：① 取不到字段不得静默变空（数值型字段走保留数值的 `_dig`+cast）；② 凭据不入日志（AID/BNO/visitor_st 等只按原值取用，归因日志只带 code/msg）；③ 未开播/已下播每 120s 一轮正常轮次刻意保持静默。
- **兜底装饰器失败语义影响熔断样本**: 补上装饰器后异常不再穿透到 main.py 通用 except；反之移除装饰器会使该平台瞬时故障计入失败样本、达阈值可能把房间地址自动注释掉。

### Web / GUI 面板与接口层

- **GUI/WEB 画质切换写回 `URL_config.ini` 后必须同步「编辑器快照」与「显示源」**: ① 反查表 `_anchor_url_map` 键是纯主播名，画质菜单传带 `序号N ` 前缀显示名，查表前必须 `re.sub(r"^序号\d+\s+", "", anchor_name)` 剥离；② 写回后必须调 `_load_config()` 同步 `config_text`（否则编辑器持旧快照、用户保存覆盖刚写的画质段）；③ 画质监控表格「设置画质」列必须以配置文件为准（`_anchor_quality_map`），不能取子进程日志值（切换不重启子进程、日志恒为旧值）。WEB 端 `PUT /api/rooms/quality` 与 GUI 共用 `src/web_config.py::update_room_quality`（保留 `#` 注释前缀、os.replace 原子写、换行注入 ValueError），两端改一处即同步。档位白名单只允许 `BUILTIN_QUALITIES`。回归锁：`tests/test_web_config.py::TestUpdateRoomQuality`+`tests/test_web_api.py::TestRoomQualityApi`+`tests/frontend/test_quality_ui.mjs`。
- **Web 面板「直播间列表」表格必须维持 `table-layout: fixed`**（`web/style.css` 末尾段）: 窄视口下默认 auto 布局 6 列 min-content 溢出。修复后按表头定列宽（画质 128/名称 150/启用 72/录制中 72/操作 76，地址列吃剩余宽），地址/名称 `td` 单行省略，≤768px 走 `min-width:640px + .panel overflow-x:auto`。约束：改回 auto 布局或删省略号会让错位回归；新增列必须补对应 `th:nth-child(n)` 定宽；该段作用域保持 `#rooms-view`，勿扩大到其它三张表。
- **Web 后端（src/web_api.py）阶段2 已从 FastAPI 迁移到 Starlette 直接驱动（2026-09-29）**: ① 新增路由必须走 `_route(app, [METHOD], path)` 适配器，禁止手写 `app.add_route` / 裸 `@app.route`——适配器负责 JSON body 解析（`_read_json_body`）、Query 上下界夹取（`_QUERY_DEFAULTS`）、同步 def 端点经 `run_in_threadpool` 派发（避免阻塞事件循环）、非 Response 返回值包 JSONResponse，漏走即丢失这些语义；② 请求模型改走 `src/web_models.py` 的 `.parse(data)` dataclass（替代 pydantic），缺字段/类型错→ValueError（适配器转 422）；③ 测试里的 `TestClient` 必须从 `starlette.testclient` 导入（FastAPI 仅 re-export，移除 fastapi 后不可再 `from fastapi.testclient import TestClient`）；④ `requirements.txt` 与 `pyproject.toml [project.dependencies]` 包名集合须相等（回归锁 `tests/test_regression_2026_09_22_gates.py`），删 fastapi/pydantic 须两侧同步；⑤ 路由契约由 `tests/test_web_api_routes.py` 动态断言（24 条 method/path + /web 挂载），改动路由后该测试必随之更新；⑥ **Starlette 没有 FastAPI 的 `@app.middleware("http")` 装饰器方法**（用了导入即抛 AttributeError，面板整体不可用）——中间件一律 `app.add_middleware(BaseHTTPMiddleware, dispatch=...)` 且必须在 `create_app` 返回前注册（lifespan 启动后再调用抛 RuntimeError）；⑦ **Starlette 内建 HTTPException handler 回 PlainTextResponse(detail)**，丢 `{"detail": ...}` JSON 错误契约（前端 `apiError()` 依赖该键）——`create_app` 必须保留 `_http_exception_to_json` 这份 FastAPI 同款 JSON handler 注册，删掉即全部错误响应漂移。⑥⑦ 均为 2026-09-29 运行期验证（pytest + TestClient）抓出、仅静态验证（py_compile/grep）查不出的接线错误。
- **GUI 度量层（`src/ui_scale.py`，阶段6）的字号与缩放约定**: ① 字号只有**负数点值**一种形态（正数是屏幕像素、不随 `tk scaling` 跨 DPI 缩放，本仓视为 bug 形态），档位定义收敛到 `TYPE_SCALE`，`ScaleProfile.pt()` 是唯一允许产出字号的口令；② **点值不按用户系数线性放大**（点已是 DPI 无关物理量，150% 档线性放大会把正文推到 ~24px 并撑坏行高与卡片），统一走 `factor ** 0.6` 的温和增益，等宽再乘 `MONO_SCALE_FACTOR=0.9`（等宽字符变宽会让一行能装的列数骤减）；③ **换缩放只改尺寸、不改信息密度**——列数/卡片结构/导航项数量恒定，否则「放大界面」退化为「重排信息架构」；④ **缩放必须即时生效且不重建控件树**：`tkfont.Font` 是具名共享资源（控件 `-font` 指向名字而非快照），`Fonts.rescale_all` 改已缓存 Font 对象即可全体重绘；重建会清空日志内容/URL 编辑器未保存内容/两张监控表（与阶段4 之前整表 destroy+重建同类事故）。等宽因此必须返回 `Font` 对象而非元组（元组是快照，不随缩放变）。回归锁 `tests/test_ui_scale.py`。
- **GUI 缩放档位落地必须同步三处，缺一处即半途状态**（2026-10-04 阶段6，真机截图复核发现）: ① **ttk 主题名必须带档位段**（`dlr-light@115`）——`theme_create` 对同名第二次调用抛 TclError 且 Tk 无「更新已注册主题」API，沿用旧名就拿不到新 padding/rowheight；② **`ui_kit.font_style` 的缓存键必须含档位段**——派生样式在创建时**拷贝**了基础变体的 configure，换档后基础变体已变而旧派生样式名会被继续命中；③ **换档后必须调 `ui_kit.restyle_fonts(root)` 把带字体的按钮重新指向新派生样式**——只清缓存不够，已存在的按钮仍指着旧样式名，表现为「字号变大了但按钮内边距还是老样子」（85% 档最明显）。`_on_theme_change` 走的路径不经 `set_scale_percent`，故它也要显式调一次。回归锁 `tests/test_ui_theme.py::TestApplyTtk::test_scale_change_reregisters_under_new_name`。
- **GUI 动效层（`src/ui_motion.py`，阶段6）的四条铁律**: ① **系统「关闭动画」优先于用户选择**（Windows `SPI_GETCLIENTAREAANIMATION` / macOS `reduceMotion`），一律压到 `off`，且必须把菜单显式落到「关闭」并落一条日志——「选了却毫无反应」几乎必然被当成 bug 报上来；② **`off` 档不排 `after`、同步落终态**（`frame_plan` 返回空列表是信号），半途状态 = 控件卡在中间位置；③ **帧数硬上限 `MAX_FRAMES=12`** 与调用方传入值取小，「流畅克制」必须是可机检形态；④ 帧序列**不含终帧**，终帧统一由 `on_done` 落地，使「降级到 off」与「正常跑完」走同一条落地路径。动效只做 Tk 真支持的位移/尺寸/颜色插值——ttk 无控件级 alpha，**不得假装淡入**。回归锁 `tests/test_ui_motion.py`（含 4 处变异验证；注意 `frame_plan` 内有**三道冗余守卫**保护 `off` 路径，单点变异会被掩盖，须同时拆掉才能证明不变量真被测到）。
- **GUI 过渡动效不得用 `place_forget` 收尾**（2026-10-04 阶段6，真机发现）: `place_forget` 把控件从**所有**几何管理器里摘掉——页面原本 grid 排的，forget 之后既不在 grid 也不在任何地方，控件直接从窗口消失（`tkraise` 只提层不给位置）。正确形态见 `ui_kit.slide_in`：过渡前抓 `grid_info`/`pack_info`、终帧 `place_forget` 后按原布局器写回。**任何「借 place 做过渡」的动效都适用**，不限于页面滑入。
- **GUI 表格变化行高亮的末帧必须摘 tag**（2026-10-04 阶段6）: 末帧颜色虽已混回常态底色，但 tag 仍在，下一轮 `DataTable.sync` 比对 tags 时会因「多了一个 tag」判成变化而再次触亮，形成「每轮都闪一下」的自激循环。高亮色取 `primary` 与 `surface_alt` 的混合而非 success/danger——好坏已由 `downgraded`/`disconnected` 两个 tag 表达，复用语义色会让两种含义叠加。
- **GUI 侧栏底部控件高度必须纳入窗口 minsize 下限**（2026-10-04 阶段6）: 侧栏是整窗唯一「高度不随内容伸缩」的列，窗口高小于其需求高时 pack 会把最后一个控件（「彻底退出」）顶到窗口外——用户表现为「退出按钮只剩一条红边」。`_raise_minsize_to_fit_sidebar` 取**实测** `winfo_reqheight`（写死常量必然在某个「档位 × 语言 × 译文行数」组合下失准），但仍以当前窗口高封顶，避免屏幕装不下时窗口拖不动。偏好设置区维持 2×2 网格：竖排四项在 85% 档放不下。
- **GUI 主题层（`src/ui_theme.py`，阶段3）的取色与持久化约定**: ① 任何控件配色必须引用语义 token 槽位，禁止绕过槽位直写十六进制——新增槽位/组合先登记 `CONTRAST_REQUIREMENTS`（正文 4.5 / 非文本与禁用 3.0，机检在 `tests/test_ui_theme.py`）再取色，`on_primary` 是提案清单之外的补充槽位（深色主按钮标签需近黑前景）；② 主题偏好唯一落点是 `config.ini [GUI] gui_theme`（键名无分隔符），读写走 `ui_theme.load/save_theme_preference`（写经 `update_or_append_config_line`），**不得**改用 `config_io.read_config_value`——其写回持 `main.file_update_lock`，GUI 进程不得混入录制引擎锁体系；③ `ThemeManager.select/apply` 必须保持幂等（同 id 短路、重复注册守卫——`theme_create` 对已存在主题名抛 TclError）；④ `ui_theme.py` 不得在 import 期创建任何 Tk 对象（无头 CI 可安全 import，`import gui` 链路依赖此约束）；⑤ 「外观模式」（CTk 明暗，含跟随系统、无持久化）与「界面主题」（token 主题，持久化）两菜单并存是阶段3 过渡形态，阶段4 控件层统一时不得静默删除任一入口。
- **GUI 长文案自适应 wraplength 必须真防抖 + 迟滞，禁止在 `<Configure>` 里同步写**（2026-09-29 卡死事故；2026-10-03 阶段4/5 换 ttk 后结构不变、依据更新）: 同步追写 wraplength 的几何失效会排进 Tk idle 队列——与布局/字体重排互激时队列永不排空，`update()`/mainloop 永不返回 = 整窗卡死，高频重排 = 文字闪烁，绘制饥饿 = 元素渲染不完整（CTk 时代实测：DPI 重缩放的递归互泵下 10 次翻转即卡死、120s 泵不完）。唯一安全形态 = gui.py `_bind_adaptive_wraplength`：真防抖（Configure 只重置 after 计时器，风暴安静 120ms 才结算，节流式「每 N ms 写一次」仍可能经滚动条阈值互振重新点燃递归，不采用）+ 迟滞 `_wrap_should_apply`（`|Δ| ≤ max(12, 2%)` 不写，滚动条翻转 ±11px 被吸收）+ TclError 竞态守护（占位每 2s 重建）。新增自适应布局类回调一律照此结构。回归锁 `tests/test_gui_wrap_hints.py`（DPI 翻转压力 + 防抖/迟滞 AST 锁；压力风暴源 = `tk scaling` 翻转，点值字体随 scaling 重排等价模拟跨 DPI 拖拽）。配套：ttk 的 `wraplength` 是**原始设备像素**、不随 `tk scaling` 缩放（阶段5 实测），`_compute_wraplength` 直接用设备像素宽、**无缩放率换算**（[历史注] CTk 时代为 `(width-margin)/scale`，锚点 1584@1.5→1050，随 `ScalingTracker` 依赖退役）。
- **Web 安全拒绝启动必须早于任何 stdio 重定向**（web.py）: `_enter_background_mode` 会隐藏控制台并把 stdout/stderr 改向 `logs/web_console.log`，「未启用认证不允许监听非回环」的拒绝文案若排在其后就对用户完全不可见（只剩「窗口一闪、面板起不来」）。闸门仍必须晚于 `import main`——`main.config_file` 由 `_app_root()` 解析，提前就得另写一套路径推导。拒绝路径同时落一条 warning，兜住 `pythonw.exe` 与冻结 `console=False` 下 `sys.stderr is None` 的形态。回归锁 `tests/test_web_background_gate_order.py`（含「闸门行早于背景化行」的 AST 结构锁）。
- **GUI 解析录制子进程状态行的匹配串必须由 `i18n.tr()` 后形态派生并按语言惰性重算**（gui.py `_status_patterns`/`_build_status_patterns`）: 生产侧 `src/recorder_status.py`/`main.py` 的状态行一律过 `tr()`，硬编码简中正则在非中文语言下恒不匹配、画质监控页静默停摆（关键约定 #13 同源）。**例外**：`src/recorder_status.py` 里那条**未过 tr 的裸字面量** `"\r没有正在监测和录制的直播"` 在英文界面下仍是中文，GUI 必须继续按原文匹配并在注释写明原因——把它「顺手改成 tr() 形态」会把它弄坏。不得做成模块级一次编译（语言热切换后失效），也**禁止**为省事改走 `#DLRQ` 结构化协议（#13 列为待批准长期方案）。**按语言缓存必须「组装后复验语言码未变」才落键**：`_build_status_patterns()` 要连读 6 次 `tr()`，而它由录制输出线程调用、`set_language` 由 UI 线程调用，语言在中间被切走时组出的是**混语** patterns，无条件写入等于把混语固化（缓存无失效时机 → 长期静默失配）；不稳定时返回结果但不写缓存，把混语存活期压在一轮之内。回归锁 `tests/test_gui_status_pattern_i18n.py`。
- **GUI 右边框裁切的两层根因：`reqwidth` 赤字 + Tk grid 裁切**（2026-10-17 实测，本机各档 px 读数见 `docs/agent-reference/measured-evidence.md`「GUI 右边框裁切的几何读数」）: ① 长提示标签初始 `wraplength=0`（= 不折行，整条文案按单行计入需求宽）与 `ui_kit` 两处 `tk.Text` 默认 80 字符宽，把 `root.winfo_reqwidth()` 顶到大于 geometry 宽；② Tk grid 对「需求宽 > 分配宽」的 slave 是**裁切而不是收缩**，赤字一律从内容列右缘开始切，卡片右边框与 20px 右边距整段消失（左/上/下边框仍在，正是用户截图形态）。修复是三段而不只是一段：源头给标签非零初始 `wraplength` + `tk.Text` 显式 `width=1`；抬**首窗几何**到需求宽消掉首帧赤字；把几何临时压到档位最小宽再读数得到内容**收缩地板**，只把 `minsize` 抬到地板（抬到需求宽等于把窗口最小宽锁死，用户再也拖不窄）。**需求宽必须迭代到稳定再读**：Treeview 列宽在 `<Configure>` 回调里按树宽重算，`update_idletasks()` 不处理 Configure 事件，只读一次会拿到大窗旧值——见 `gui._settled_reqwidth`。回归锁 `tests/test_gui_right_edge_fit.py`。
- **自选字体（gui.py + `src/ui_fonts.py`，2026-10-17）的四条硬约束**: ① **不得用 `tkfont.families()` 判「可用」**——实测 `AddFontResourceExW(FR_PRIVATE)` 返回成功、Tk 也能按该族名排字形，但 `families()` **永远列不到它**（Tk 只枚举注册表已安装字体）；而字体缺失时 Tk 又**静默回退**不报错，于是「在 families() 里」既非必要也非充分。唯一判据是让 Tk 解析一次并对照人造缺失族名的兜底结果（`ui_fonts.family_resolves`，验证方式：把系统字体副本的全部 `nameID=1` 改成一个标记名，`Font(标记名).actual()["family"]` 确实返回它）；② **切字体只改缓存里的 `tkfont.Font` 对象、不重建控件树**（改一次定义全体重绘，日志/编辑器未保存内容/两张表零损失），换族后必须 `restyle_fonts` + 各页 `update_idletasks` + 重跑 `_raise_width_to_fit_content`（换族后需求宽会变，不重算就回到右边框裁切那条老路）；等宽链路 `mono_*` 刻意不动；③ **`woff2`/`woff` 必须在导入入口挡掉并给出「先转 ttf/otf」的可读原因**——GDI 只认 SFNT 容器，静默接受等于「导入成功但没变化」。偏好键 `config.ini [GUI] gui_font` / `gui_font_file`，字体副本落 `config/fonts/`（引用原路径会在用户删源文件后回落默认字体）；④ **`install_font_file` 的失败分支必须留一行 warning，且落盘名要过 Windows 保留设备名清洗**。前者：调用方拿 `None` 只能弹分类级提示（「无法读取或复制该字体文件」），被占用 / 目录只读 / 磁盘满 / 源文件在复制瞬间被移走这几种成因在 UI 上完全同形，异常静默收敛成 `None` 就等于把归因权丢掉——日志写法照「异常日志必须带异常类型与上下文」，`i18n.tr("复制字体文件失败: {name} -> {target} - {type_name}: {err}", …)`（该模板已进四目录）。后者：`_safe_filename` 对 `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9` 加 `_` 前缀（整段基名、大小写不敏感、幂等；`COM10` 刻意不算保留名）。**不得把这条写成「本机写不进去」**——2026-10-17 在 Windows 10.0.26300 实测 `CON.ttf`/`AUX.ttf` 经 Python `open()` 与 cmd 重定向都能落成普通文件，清洗的理由是**跨构建/跨 API 的可移植性**：该名字还会写进 `gui_font_file` 持久化并在下次启动读回。回归锁 `tests/test_ui_fonts.py::TestInstallAndRegister::test_install_font_file_logs_copy_failure_with_reason` 与 `…::test_safe_filename_prefixes_windows_reserved_device_names`（各含「放宽成子串匹配即红」的边界用例；替身按 shim 口径挂到被测模块命名空间）。
- **停止与退出共用「单飞闸门」，在途登记与注销必须落在无条件路径上**: 控制台附着是**进程全局**状态（FreeConsole→AttachConsole→GenerateConsoleCtrlEvent→FreeConsole），两条路径并行操作同一 pid 会错投/丢失 CTRL_BREAK，最坏退化为 taskkill 硬杀并失去子进程 safe_exit 优雅清理 ffmpeg 的机会。登记与注销都不得放在条件分支里——漏注销等于此后每次退出白等。回归锁 `tests/test_gui_stop_exit_singleflight.py`。（本条与下一条同挂在一个标题下是迁移期的复制粘贴痕迹，2026-10-17 按各自内容分标题。）
- **Tkinter `after` 自续期链的续期注册必须在 `try/finally` 内**: 回调抛未捕获异常时尾部的下一次 `after` 不会注册，定时链**永久断裂且无自动恢复**（弹幕刷新 / 状态刷新 / 日志 flush / **UI 事件泵 `_pump_ui_events`** 四条同型；第 4 支的续期还兼管「按需激活日志刷新链」，断了等于 `post_ui` 排队的 `_on_recording_stopped`/`_finalize_quit` 永不执行 = 关不掉窗口）。重排一律经 `gui._after_retry`，它失败返回 None——调用方**不得**把失败记成「已排队」，否则该链再无人唤醒。外部数据字段（`ts` 等）一律走统一数值容错 helper——`danmaku_monitor.jsonl` 里的 `null` 历史脏记录在启动回放末尾 64KB 时可达；tail 线程的 try/except 必须落到**每条事件**（坏条 continue），否则一条脏事件连带丢弃同批后续完好事件且不留痕。结构锁 `_CHAINS` 逐条点名（`tests/test_gui_tail_robustness.py`），新增周期链必须同批登记。

- **GUI 窗口层已迁到 PySide6（Qt6），`src/gui_qt/` 是 2026-10-17 起的唯一窗口实现**(`gui.py` 只做 `main()` → `src.gui_qt.app.main()` 委托；原 tkinter 实现改名 `_legacy_main()` 迁移期保留，因九份 `tests/test_gui_*.py` 以 AST 静态锁 / subprocess 钉在本模块)。选型理由（勿删）：设计稿定的 18/24px 大圆角卡片 + 柔和投影 ttk 无法原生实现，自绘又不参与布局系统的尺寸协商（与「缩放档位要吃下各种语言标签宽度」直接冲突）；QSS + `QGraphicsDropShadowEffect` 可 1:1 还原，且 `QTableView`/`QTextEdit` 自带虚拟化与 `maximumBlockCount`，日志/弹幕高吞吐不需要自建渲染节流。五条硬约束：① **设计令牌单一事实源在 `src/gui_qt/theme.py`**（25 键 × 3 主题，2026-10-17 实测三主题键集合相同；QSS 由 `build_stylesheet()` 现算后整窗 `setStyleSheet` 一次生效），禁止在任何控件上散落配色或逐控件 `setStyleSheet`；② **QSS 只认 objectName 选择器**（`QFrame#card`），写 `QFrame` 会命中 `QTableView` 的内嵌 frame；③ **周期链一律挂 `QTimer` 且回调内仍包 try/except + 30s 限频留痕**（Qt timer 不会因回调抛错而停，但「异常→静默」的老故障形态必须显式消掉），旧版 `_ui_event_queue + post_ui` 事件泵与 `after` id 守卫整套退役；④ **子进程生命周期的竞态逐条搬运而非重写**：session_id 迟到回调、`_stopping` 复位放 finally 且早于会话校验、停止/退出共用单飞闸门 `_stop_child_once()`（控制台附着是进程全局状态）；⑤ **打包不加 `collect_all('PySide6')`**（那会把整只轮子含 `Qt6WebEngineCore` 拖进产物——两项 MB 读数见 `docs/agent-reference/measured-evidence.md`「打包与镜像体积读数」），收集交给 PyInstaller 自带的 `hook-PySide6.py`（按实际导入的 Qt 模块逐个收），`'PySide6'` 只加在 CLI/Web 两个 Analysis 的 excludes 上——GUI 必须收它。**hook 收完还须剪**（⑥）：hook 按「插件类型整目录」收 Qt 插件、插件链接依赖再递带入包，`opengl32sw.dll`（`collect_extra_binaries` 无条件收）与 VirtualKeyboard→Quick→Qml 一整条链会被间接拖进产物；excludes 管不到 hook 收的 DLL，只能 COLLECT 之后按文件名删——清单唯一事实源是 `build_exe.QT_BLOAT_FILES`（11 项，逐项体积见同节），判据与 BLOAT_EXCLUDES 同源（能指出在产物里 + 运行期不可达），改清单前先做链接依赖扫描并实跑冻结 GUI。**⑦ 等宽字体只能经 `src/gui_qt/widgets.py::fixed_font` 取族名**：`QFont` 的族名位只收**单个** family，把 CSS 式 `"Consolas, Menlo, Courier New, monospace"` 整串塞进去等于请求一个不存在的族名——装了 Consolas 的机器侥幸命中，没装的机器上 Qt 按 `styleHint=Monospace`（枚举值 7）落进遗留别名表里的 `Terminal`，打出 `DirectWrite: CreateFontFaceFromHDC() failed` 与 `QFont::setPointSize: Point size <= 0 (-1)` 两条告警；候选全缺时交回 `QFontDatabase.systemFont(FixedFont)`，**不得**再猜名字、也不得在控件上硬写 `setFontFamily("Consolas")`。回归锁为 `tests/test_gui_qt_units.py` 的三条 `fixed_font` 用例（打桩 `QFontDatabase.families` / `systemFont`，不依赖本机字体表）。⑧ **跨线程生产者必须有生产侧消费方——「信号定义了 + 连接了」不等于通路通了**（2026-10-18 S-01 事故，新版 Qt GUI 录制输出完全断路的唯一严重项）：`recorder.py` 的读线程只 `_push()` 入队、`linesReceived` 全仓从未 `emit`、`drain()` 生产调用方为零，于是 `main_window.py` 的 `connect` 是永不触发的死连接，而**测试直调 `drain()` 恰好把这条断路掩盖成全绿**。定稿形态 = 保留队列 + 唤醒信号 `outputReady`（`_push` 按「先入队→置位→发信号」顺序 emit，杜绝「叫醒时数据还没进队列」），主线程 `_pump_recorder_queue` 一次取空后分流：批次交 `_on_lines_received`（画质 `parse_line` 的输入源）、`(session_id,)` 结束哨兵交 `_on_recorder_ended`，并按会话号对「手动停止的 ended 信号」与「自然 EOF 哨兵」双通道去重、保留 `_quitting`/`is_stopping`/迟到会话三重早退；自然结束清 `_process` 一律走 `reclaim_after_natural_end` 且**只由主线程做**（读线程不碰句柄，否则与 `_stopping`/`stop_async` 抢窗口）。三条不可回退：① 新增任何「读线程产出 → UI 消费」的通路必须有生产侧调用方，验证口径是 `grep` 该 Signal 的 `.emit(` 与消费方的调用点**同时存在**，只查定义和 connect 不作数；② 用例直调内部消费函数（`drain()` 之类）时，同文件必须另有一条「经信号/经真实通路驱动」的用例，否则锁自我掩盖；③ `_read_queue` 的排空责任在主线程，不得为「简单」改回读线程直接 emit 带数据的信号（丢批处理节流）也不得加空闲轮询定时器（永久空转）。回归锁：`tests/test_regression_2026_10_18_gui_output_chain.py`（6 条，含「后台线程调 `_queue_log` 不得跨线程 `QTimer.start()`」的 M-11 同根锁）。

- **托盘 / 面板图标必须走 `src/ui_icons.py` 单点解析（2026-10-22）**: ① 生效出口唯一 `ui_icons.current_icon_path(app_root, configured)`（导入副本 > 内置 `assets/app.ico` > `None`），**三个入口（GUI 托盘 / Web 托盘 / `GET /favicon.ico`）必须都调它**——各写一套的表现必然是「托盘换了、标签没换」；② 校验判据唯一 `validate_icon_bytes`（体积 → 结构 → 分辨率；16×16 是硬门槛、缺则系统从大图硬缩成一团糊，256×256 只提示不拦），GUI 弹窗与 Web `detail` 共用同一批 code（`empty`/`too_large`/`not_ico`/`no_tray_size`/`no_app_size`）：`ui_icons` 只回码、GUI 走 `i18n.tr`、Web 前端按码取文案，**不得**在后端拼中文（否则四目录再漂一份）；③ `QIcon(path)` 对损坏文件返回 `isNull()` 而不是抛异常，故**落盘前**必须校验；托盘**不得**设空 `QIcon`——空图标在 Windows 托盘区是看不见也点不到的空白，比「没换图标」糟得多；④ 上传接口走 base64 JSON（`python-multipart` 已摘除，`Request.form()` 零调用点），且必须**先解码、再校验、后落盘**：坏文件不得在 `config/icons/` 留垃圾副本；⑤ `GET /favicon.ico` 无可用图标时回 **404 而非空 200**（空 200 会被浏览器缓存成坏图标，之后导入也刷不掉），响应带 `no-cache` 并由前端在 href 上追加时间戳破缓存。回归锁 `tests/test_ui_icons.py` + `tests/test_web_api.py::TestIconEndpoints` + `tests/test_web_tray.py` + `tests/test_gui_qt_units.py` 的托盘用例。
### 测试质量与审查协作流程

- **测试不得自实现被测逻辑（假绿）**: 曾存在测试里重新实现锁/凭证缓存再断言自实现——删掉 `src/` 对应实现仍全绿等于没覆盖。判据「**删掉生产实现就会失败**」：只允许打桩网络层与时间常量，去重/限流/锁逻辑走真实代码。另：不得 `monkeypatch.setattr(main.time, "sleep", ...)`（`main.time` 是 stdlib 时间模块本体，会替换全进程 sleep，应浅拷贝成 `SimpleNamespace` 覆盖单属性）；覆盖率门禁「模块查不到」按失败处理（非告警）。
- **探测子进程输出一律按字节比较，且这类用例必须能单文件独立运行**: 凡读子进程输出做判定的探测不得用 `text=True`/`encoding=`（Windows `tasklist`/`taskkill` 按控制台码页发本地化消息，UTF-8 模式下 reader 线程解码即抛 `UnicodeDecodeError`→`TypeError`+违背 0 警告）。判据写成字节包含（`str(pid).encode() in probe.stdout`）与码页/语言解耦。`main.py` 导入期 `SetConsoleOutputCP(65001)` 会把整个 pytest 进程控制台码页切 UTF-8，只要同会话有用例先 import main，GBK 分支永不显现→「全量绿、单文件跑红」。故任何驱动子进程并断言其输出/进程状态的测试文件必须保证 `pytest tests/<该文件>` 单独运行全绿且 0 警告。
- **本机全量 pytest 偶发段错误（exit 139）**: 属环境噪声，不要据此认定代码回归。
- **平台专属分支的测试不得靠 `skipif` 让 CI 跳过（CI 实测定稿）**: CI 全部 job 跑在 ubuntu，Windows 专属分支（如 `src/ffmpeg_proc.py` 的「向 stdin 写 `q` 再 close」）若按 `os.name`/`sys.platform` skip，相关回归锁会在 CI 上**静默消失**。做法：把平台判定抽成模块级常量（如 `_QUIT_VIA_STDIN = os.name == "nt"`），测试用 `monkeypatch.setattr(module, "_QUIT_VIA_STDIN", True)` 强制走进该分支，让 Windows 路径在 Linux CI 上真实执行。同理，**门禁工具（black / isort / mypy）必须装进 test job**：`tests/test_run_gates.py` 与 `tests/test_regression_2026_09_22_gates.py` 有两条锁会真起子进程调用它们（复现 isort 的 `Unable to parse file` 走 UserWarning 且 rc 仍 0；验证裸 console-script 不在 PATH 时 `python -m` 兜底不误报 rc=3），缺装即 `No module named isort` → rc=1 → 红；版本取 setup job 的 `black_version` / `isort_version` / `mypy_version` 常量，与 static / typecheck 两 job 同值。
- **并行分组代码审查分工口径**: 子任务 prompt 必须写明本项目刻意约定白名单，避免子代理误报风格为问题。
