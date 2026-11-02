> 本文件是项目**每次会话必守约束**的唯一事实源：核心事实、安全红线、门禁命令。按需查阅的详情在 `.agents/skills/dlr-dev-playbook/references/`，纯参考长段外迁到 `docs/agent-reference/`，更新日志正文归档在 `docs/changelog/`。新增长期约定写回对应章节，不得出现第二份事实源。
>
> **阅读顺序**：先读「风险控制（前置）」→ 跑门禁时读「格式化命令」→ 动手前读所在主题的 Skill 参考文档。

## 项目概览

- **名称 / 版本**: DouyinLiveRecorder 4.7.0（唯一事实源 `pyproject.toml` 的 `version`，动态读取见「关键约定」#1）
- **描述**: 支持抖音、TikTok、YouTube、快手等 60+ 平台的直播录制工具
- **许可证**: MIT

## 风险控制（前置）

### 必须停下来交回用户的情形

- **批量重装 venv 依赖**：必须由用户在普通终端执行：沙箱拦截发生在 pip 开始卸载之后、会清空包目录。分级流程见 dlr-dev-playbook `references/ci-workflow.md`「venv 依赖修复分级处置」。
- **清理范围越界**：收尾清理只限本次任务产生的一次性脚本与 `tests/` 临时输出；运行期产物目录（downloads/recordings/logs/backup_config/）与 `scripts/` 下正式维护脚本一律不动（范围与命令见「测试收尾清理临时脚本」）。**括号枚举是唯一事实源**：`scripts/agent_hook_guard.py::PROTECTED_RUNTIME_DIRS` 与 `.gitignore`/`.dockerignore` 同源，`tests/test_agent_hook_guard.py` 按此括号形态正则比对；改成顿号/斜杠列表会让该锁失去基准而判红，**不得**改动这处括号形态。
- **删除被 harness safe-delete 拦截**：记下路径、按同节口径逐文件重试；仍删不净时在回复里列出残留路径交回用户，**不得静默跳过**。
- **治理式流程技能（vibe 等）**：需先由用户确认 run 范围与 artifact root，不得把工具安装目录当产物根目录（见「流程编排技能的使用边界」）。

### 凭据与敏感配置红线

- **不得提交 / 外传运行时凭据**：仓库保留一份已跟踪的脱敏 `config/config.ini` 基线模板；`.gitignore` 对已跟踪文件不生效，本地填入 Cookie / 代理 / Web 密码后绝不能提交。`config/URL_config.ini` 及新增同类运行时文件须保持忽略，并经 `.dockerignore` 排除、不得进入镜像。
- **写入配置或日志前必须脱敏**：URL / 代理地址一律经 `utils.mask_credentials()`；Web 面板敏感键走「节白名单 + 键名正则」双重判定，`'***'` 掩码跳过是写入侧唯一防线（详见 dlr-dev-playbook `references/known-pitfalls.md`「凭据与敏感配置脱敏」）。
- **文档与审查记录里不得出现真实凭据**：新增 `CODE_REVIEW_*.md` / `DIAGNOSIS_*.md` 类根目录文档时只写脱敏后的样例值。

## Python 版本

- **最低要求 / 目标 / mypy 检查版本**: Python >= 3.14（`requires-python = ">=3.14"`）。
- **3.14 破坏性变更**: `asyncio.get_event_loop()` 不再隐式创建事件循环（口径见 dlr-dev-playbook `references/concurrency-model.md`）；`pkg_resources`、PEP 594 亡故电池模块已移除；新代码统一走 `ctypes.WinDLL`（对齐 web.py，而非 `ctypes.windll`）。
- 语法/编译检查一律用项目 venv 的 Python 3.14（3.13 做 `compileall`/`py_compile` 会误报 PEP 758 语法，见 dlr-dev-playbook `references/known-pitfalls.md`）。

## 代码风格

> 配置摘录自 `pyproject.toml [tool.*]`，配置本体才是事实源；门禁命令见「格式化命令」。

- **Black**: `line-length = 120`、`target-version = ['py314']`；排除 `.git`/`.venv`/`build`/`dist`/`__pycache__`/`.pyc`/`node`/`ffmpeg`、运行期产物目录与本地工具目录（`.agents`/`.workbuddy`/`typings` 等，完整清单见配置本体）。
- **isort**: `profile = "black"`、`line_length = 120`、`known_first_party = ["src", "i18n"]`。
- **mypy**: `python_version = "3.14"`；**不带路径参数**（范围取 `[tool.mypy].files`）；平台双跑 `mypy --platform linux` / `mypy --platform win32`。typings/ 存根告警见 dlr-dev-playbook `references/static-check-adjudication.md`。
- **except 多异常写法**: 本仓统一 `except A, B:`（PEP 758 无括号）。新增写无括号，存量不为对齐而批量改；需 `as` 绑定时回退加括号。

### 注释约定

- **统一使用 `#` 行注释，不使用三引号 docstring**（docstring 进 AST、`#` 注释不进，AST 等价性校验借此证明「逻辑未改动、未误插 docstring」）。
- **写「为什么」而非「做什么」**：边界条件、平台差异、风控信号、降级路径、异常吞没后果、并发与时序假设。三个层次：模块头总览 / 函数级职责 / 关键分支与边界；参照 `src/stream_select.py`、`src/scheduler.py`。
- **引用代码位置优先写锚点（符号名 / 唯一语句片段），不写 `file:line`**: 行号随文件增删漂移。确需给读数时写「实测日期 + 取数命令」，便于复跑。
- **修改注释只增不改**：不得删除或重写已有解释性注释；需修正时在其下方补充。**例外**：不适用于已被证伪的事实性陈述。
- **「更正考古」段可压缩**：多层叠加的修订允许压为「当前实测状态 + 一行 `[历史注]`」，但实测读数、常量名、判据、回归锁用例名逐字保留。

## 项目结构

完整目录树见 [项目结构目录树][struct-tree]；逐模块覆盖率阈值只维护在 `scripts/check_coverage.py` 的 `MODULE_THRESHOLDS`，本文件不复制数值。

[struct-tree]: docs/agent-reference/project-structure.md

## 项目级 Skill

> 高频复用的领域约定已提取为独立 Skill（位于 `.agents/skills/`）。AGENTS.md 保留约束语句作为唯一事实源；Skill 展开操作步骤与验证清单。
> **表格与目录同源**: 本表须与 `.agents/skills/` 一级子目录一一对应。**目录必须入库（SR-06）**: `.gitignore` 以 `.agents/*` + `!.agents/skills/` 反选；`.dockerignore` 侧仍整目录排除。

| Skill | 路径 | 触发词 / 场景 | 覆盖领域 |
| --- | --- | --- | --- |
| DLR 开发手册 | `.agents/skills/dlr-dev-playbook/` | 新功能设计、编写测试、运行时日志分诊、平台符号门控、静态检查裁定、Windows 只读探源 | 开发工作流路由；命中路由后只加载对应的单个 `references/*.md` |
| 领域硬约束（选源/录制/发布） | `.agents/skills/dlr-domain-constraints/` | `select_source_url`、`ffmpeg`、`-reconnect`、`-segment_format`、`_PINNED_RUNTIME_SHA256`、`--require-pinned`、JS 签名脚本钉定 | 选源探针与画质映射、F-01 四定义点与容器格式查表、运行时钉定三层防线、签名脚本字节级对齐 |
| 大规模注释重构（通用，非本仓约定） | `.agents/skills/comment-refactor-at-scale/` | 纯注释重构、等价性校验、配额感知派发写入代理、批量文本改写 | 基线与六维等价证明、波次派发与 JSONL 台账、配额中断后的产物重建、字节级批量改写 |
| 只读审查生命周期（通用，非本仓约定） | `.agents/skills/code-review-lifecycle/` | 全仓静态审查、只读审查、审查报告整改、输出 `CODE_REVIEW_YYYY-MM-DD.md` | 分区派发与主控复核；审查结论的严重度分级与逐条整改验收 |
| 运行时安全应急（通用，非本仓约定） | `.agents/skills/runtime-security-response/` | Node.js Brotli CVE、PHP php2shell、运行时版本核查与升级 | 影响面判定、解压/参数注入入口追踪、缓解与补丁验收 |
| Python 工程规范（外部市场，非本仓约定） | `.agents/skills/python-engineering/` | Python 代码风格与后端分层、ruff/uv、异步与数据库实践 | 函数式风格与文档、后端工程实践清单 |
| 通用开发工具箱（外部市场，非本仓约定） | `.agents/skills/general-dev-toolkit/` | 全栈架构与测试、性能优化、符号级编辑、提示词分析 | Clean Architecture/DDD、优化杠杆、符号导航、任务规格澄清 |

### 项目级 Hooks / Commands

> Skill 展开**怎么做**，Hook 只做**确定性拦截与即时反馈**，Command 只是短入口。

| 资产 | 位置 | 触发条件 |
| --- | --- | --- |
| Hook 执行体 | `scripts/agent_hook_guard.py` | Pre: 批量重装 venv / 删运行期产物 / 无过滤递归删；Post: 变异标记残留 / `.py` 行尾混存 / `.mjs` 未登记 / 钉定变更未跑校验 |
| Command | `.qoder/commands/dlr-dod.md` | 用户请求按完成定义逐条验收 |

- `.qoder/` 属本地工具目录，不随仓库分发。一致性由 `tests/test_agent_hook_guard.py` 钉。
- PreToolUse 可阻断（exit 2）；PostToolUse 非阻断（feedback 即时回传），真正切断点落在收尾门禁。

## 入口点

| 命令                    | 模块          | 说明       |
| --------------------- | ----------- | -------- |
| `douyin-recorder`     | `main:main` | CLI 录制核心 |
| `douyin-recorder-gui` | `gui:main`  | 图形界面     |
| `douyin-recorder-web` | `web:main`  | Web 管理面板 |

## 依赖管理

- **运行时依赖**: `pyproject.toml [project.dependencies]` 与 `requirements.txt` 保持同步。回归锁：`tests/test_regression_gates.py`。
- **开发 / 构建 / GUI 依赖**: `pip install .[dev]`（pytest / pytest-asyncio / pytest-cov / black / isort / mypy / pre-commit）/`.[build]`（PyInstaller>=6.10.0）/`.[gui]`（PySide6 一条）；三者均不进运行时清单。
- **i18n 依赖**: PyYAML（zh_TW.yaml 加载；缺失时仅损失 YAML 格式）。
- **GUI 包版本下限**: `PySide6>=6.12.0`（`requirements.txt`、`pyproject.toml` 运行时依赖与 `[gui]` 三处同值）。
- **安全下限**: `starlette>=1.3.1`、`urllib3>=2.8.0`、`h2>=4.4.1`、`brotli>=1.2.1`。优先抬下限而非 `--ignore-vuln` 白名单。构建侧下限：`[build-system]` `setuptools>=84.1.0`（GHSA-xmj3-9gf7-h52w 修复版；deps-audit 只派生自 requirements.txt，不覆盖该下限）。
- **依赖缺失排查**: venv 缺包表现为测试收集期 `ModuleNotFoundError`，先核对 `pip list` 与 `requirements.txt` 差异再怀疑代码。

## 测试

- **pytest 配置**（`pyproject [tool.pytest.ini_options]`）: `testpaths=["tests"]`、`python_files=["test_*.py"]`、`python_classes=["Test*"]`、`python_functions=["test_*"]`、`asyncio_mode="auto"`。
- **质量门禁（须保持）**: 命令一律取「格式化命令（门禁唯一基准）」一节，**不得在此重述路径参数**。判定口径：`pytest` 0 警告 + black/isort/mypy 全绿 + `basedpyright` 0 error/0 warning。
- **pytest「0 警告」口径**: warnings summary 为空。第三方库告警一律经 `filterwarnings` 显式 ignore 并附来源注释；**禁止用 filterwarnings 掩盖项目自身告警**。
- 覆盖率源码 `src/`、排除 `tests/`/`__pycache__/`/`node/`/`ffmpeg/` 等；门禁：`python scripts/check_coverage.py`。
- **前端用例（`tests/frontend/*.mjs`）**: Node 内置 `node:test`，零 npm 依赖；新增前端用例沿用「`.mjs` 真用例 + `.py` 包装」双文件结构。
- **`tests/` 下不得有「收集 0 条」的 `test_*.py`**（由 R9 机检）：例外表 `_R9_ZERO_COLLECTION_SANCTIONED` 按「文件 → 为什么 0 收集是设计使然」登记。新增此类文件时**优先**按离线用例形态写。
- **创建/更新测试**: 按「源码分析 → Mock 配置 → 验证执行」编写；新建用例与被测模块同名，并用变异验证证明用例真能抓回归。测试编写详细约定见 dlr-dev-playbook `references/testing-conventions.md`。

### 测试收尾清理临时脚本

- **收尾必须删除任务中生成的一次性脚本与产物**：前缀分三类——`_tmp_`/`tmp_`（通用临时）、`mock_`（桩服务/模拟器）。残留会污染 `git status`、被 mypy 收编、误导协作者；**任务收尾一律删除**，不留「下次可能还用」。
- **优先写在仓库之外**: 落 `%TEMP%`/`/tmp` 或 `tempfile.mkdtemp()`；确需写在仓库内者统一前缀命名、用完即删；长期复用才进 `scripts/`。
- **清理范围与禁区**: 只删本次任务产生的临时脚本与输出；**不要**删「风险控制」列出的运行期产物目录、**不要**动 `scripts/` 下正式维护脚本。清理前 `git status --short` 核未跟踪文件，对 `.workbuddy/` 等 gitignore 目录显式枚举后确认再删；safe-delete 拦截按「风险控制」处置，**不得静默跳过**。

```powershell
Get-ChildItem -Recurse -File -Include *_tmp_*.py,tmp_*.py,mock_*.py,*_tmp_*.txt,tmp_*.txt |
  Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' } | Remove-Item -Force
```
POSIX: `find . -type f \( -name '*_tmp_*.py' -o -name 'tmp_*.py' -o -name 'mock_*.py' -o -name '*_tmp_*.txt' -o -name 'tmp_*.txt' \) -not -path '*/.venv/*' -delete`

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

## 格式化命令（门禁唯一基准）

```bash
# PYTHONUTF8=1 属门禁语义、不得删（MID-63）：GBK locale 下 isort 会对含中文注释文件静默跳过、rc 仍 0。
PYTHONUTF8=1 python -m black --check --diff --line-length 120 --target-version py314 .
PYTHONUTF8=1 python -m isort --check-only --diff --profile black --line-length 120 .
mypy                      # 不带路径，范围取 pyproject [tool.mypy].files（本机平台目标）
mypy --platform linux     # 平台双跑：本机非 linux 时补测 linux 目标（涉平台专属符号必查）
mypy --platform win32     # 平台双跑：本机非 win32（含 Linux CI）时补测 win32 目标（同范围、不带路径）
python scripts/check_annotations.py
python scripts/compile_po.py --check
python scripts/check_version.py
python scripts/check_runtime_pins.py  # 只查结构；--strict（发布路径）见 dlr-dev-playbook references/ci-workflow.md
python scripts/check_skill_agents_consistency.py  # Skill 目录与 AGENTS.md 表格一致性
```

- `python scripts/run_gates.py` 按原顺序跑完全部 `--check` 型门禁，任一失败非 0 退出；`--list`/`--only`/`--keep-going` 用于排障。脚本运行时解析上方 bash 块，**本节仍是唯一事实源**。
- **一律显式传参**避免本地配置漂移；**工具版本须与 `ci.yml` consts 同值**，不一致时报告须写明差异。**不得**为凑同值擅自改 workflow 常量或批量重装 venv 依赖。
- **`PYTHONUTF8=1`** 是门禁语义的一部分（MID-63）；「告警即失败」同回路判定——新增门禁若存在「跳过/降级只发 warning、退出码仍 0」形态，必须同回路判失败。

### basedpyright（本地补充门禁，CI 不跑）

- 命令：`basedpyright`（不传路径，范围取 `pyproject [tool.basedpyright]`），要求 0 error/0 warning；mypy 是跨平台 CI 门禁（Linux runner），basedpyright 是本地严格度补充。
- **`pyright` / Pylance 的定位**: `pyright` 只是 basedpyright 的引擎基座，**不是第三条门禁**；Pylance 无命令行入口，不得为绕过许可证去 shell 驱动它。
- **裁决规则**: CI 只跑 mypy。仅单平台出现的 basedpyright 结论，以与 CI 一致的 Linux 一侧为准。

### isort 收尾清理 `.isorted` 备份残留

PowerShell: `Get-ChildItem -Recurse -Filter *.isorted | Where-Object { $_.FullName -notmatch '\\(\.venv|node_modules)\\' } | Remove-Item -Force`
POSIX: `find . -name "*.isorted" -delete`

## 完成定义（Definition of Done）

代码通过门禁 **不等于** 完成。改动落地后按序执行 1→6，任一条不满足即未完成：

1. **门禁全绿**: `python scripts/run_gates.py` + `pytest`（0 警告）+ `scripts/check_coverage.py`；basedpyright 本地核一次。**大批量改动收尾时，被引用为「门禁全绿」证据的那次运行必须发生在整批最后一次编辑之后**。
2. **端到端真机验证**: 涉及录制链路/选源/ffmpeg 参数/平台解析的改动必须用**真实 URL** 增量跑并写进回复。无法执行时记「未执行 + 原因 + 交回用户的动作」且**不得宣布完成**。
3. **回归锁**: 动到带「回归锁」标注的行为时确认对应用例存在且覆盖；缺则补。
4. **文档同源**: 按滚动归档口径追加更新日志（正文入 `docs/changelog/code-wiki-history-*.md`，`CODE_WIKI*.md` 只留索引与概要）；新增长期约定写回本文件。
5. **收尾清理**: 按「测试收尾清理临时脚本」执行，并 `git status --short` 核对无未跟踪残留。
6. **日志**: 当日 `.workbuddy/memory/YYYY-MM-DD.md` 追加一条。

**豁免**: 纯文档/注释改动只做 1+4+6；只改测试且不涉及生产行为时免 2。

## 流程编排技能的使用边界

- 本仓库日常改动（缺陷修复、性能优化、真机验证迭代、重构）**不进入**治理式运行时类技能（如 `vibe`）；仅当次会话用户**显式**要求才加载，且先由用户确认 run 范围与 artifact root。
- `brainstorming` 类「先出设计再动手」技能，对「方案已在 AGENTS.md/CODE_WIKI 钉死」或「用户已批准、正在连续推进」的改动不适用。

## 关键约定

1. **版本号同步**: 唯一事实源 `pyproject.toml`；`main.py`/`src/web_api.py` 经 `importlib.metadata` 读取，`Dockerfile` 经 `APP_VERSION` 注入。改版本后运行 `python scripts/sync_metadata.py` 重生成 `uv.lock` 与 `DouyinLiveRecorder.egg-info`；`scripts/check_version.py` 校验动态消费方。
2. **行宽**: 120 字符（black + isort 统一）。
7. **排除目录**: `node/`/`ffmpeg/`/`downloads/`/`__pycache__/` 在所有工具均排除。

> 关键约定 #3–#16 详情已外迁至 dlr-dev-playbook `references/key-conventions.md`。

---

## 外迁内容路由

> 命中场景时按需加载（目录同上）：
> 已知坑 → `known-pitfalls.md` · 测试编写约定 → `testing-conventions.md` · 并发与线程模型 → `concurrency-model.md` · CI/workflow → `ci-workflow.md` · 打包与冒烟 → `build-details.md` · mypy typings/ 存根 → `static-check-adjudication.md` · 注释检查工具 → `annotation-tools.md` · 关键约定 #3–#16 → `key-conventions.md`
