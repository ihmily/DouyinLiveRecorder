---
name: dlr-dev-playbook
description: >-
  Use when 在 DouyinLiveRecorder 仓库中开始新功能/新子系统/新 UI 或产品级行为设计（动手前须
  先出设计并获批）；编写或修改 tests/ 下的测试（monkeypatch、subprocess 替身、双模脚本、只读
  路径、并发锁）；用户粘贴带 file:function:line 的运行时日志要求解读或修复；mypy 或
  basedpyright 报平台专属符号（ctypes.windll、subprocess.STARTUPINFO）或 Windows 本地过而
  Linux CI 红；需要 mock subprocess.Popen 等 stdlib 模块属性；审查代理或 reviewer 断言某段
  代码有语法错误（如「except A, B: 是 Python 2 语法」）。
agent_created: true
---

# DLR 开发手册（DouyinLiveRecorder）

## 定位

本手册是 DouyinLiveRecorder 仓库**开发工作流的唯一入口**：把「动手前怎么想 → 编码时守什么 → 改完怎么验」三件事收在一处，按场景路由到具体配方。它是**路由与提炼**，不是新规则。

- **唯一事实源仍是仓库根目录的 `AGENTS.md`**。本手册与它冲突时以 `AGENTS.md` 为准。
- 被合并的四个旧 skill 内容已全部收编，原目录仅作历史留存，不再单独加载：
  `dlr-test-conventions` → `testing-conventions.md`；`karpathy-guidelines` → `engineering-principles.md`；
  `python-tooling-gotchas` → `log-fault-triage.md` + `platform-type-gating.md` + `static-check-adjudication.md` + 铁律 1/2；
  `brainstorming` → `design-brainstorming.md` + `visual-companion.md`。
- **按需加载**：命中路由表后只读取对应的那一个 `references/*.md`，不要把全部参考文档读进上下文。

## 通用铁律（任何路径都适用）

以下四条与命中哪一节无关，每次执行都要遵守。

### 铁律 1：临时文件零残留

为验证而落盘的文件，验证结束后必须消失。判断标准只有一条：**下次运行还会用到它吗？** 会 → 入库（写进 `tests/`）；不会 → 删。

1. **优先不落盘**：能用 `python -c "..."`、`python - <<'PY'` heredoc、`pytest -q -k <name>` 内联完成的验证，就不写脚本。不产生文件 = 不需要清理。
2. **落盘即登记**：一创建就把绝对路径写进清单（脚本内 `TO_CLEANUP = [...]`，或任务清单一行）。不要凭记忆回收——遗漏几乎都发生在这里。
3. **清理放进 `finally`**：测试失败、断言报错、异常中断时同样要清理，不能只挂在成功路径上。shell 中等价写法 `trap 'rm -f "$TMP"' EXIT`。
4. **先删脚本，再删副产物**：临时脚本 → 它生成的输出目录/日志 → `__pycache__` / `.pytest_cache/` / `*.pyc`。
5. **绝对路径、逐个删**：禁止 `rm -rf *`、`rm -rf .` 这类通配或递归删除，只删本次会话自己创建、路径明确的文件。
6. **清理后复核**：`git status --porcelain` 确认无预期外新增；只看残留，不要顺手 `git clean` 整个工作区。
7. **汇报里写清理结果**：`已清理 N 个临时脚本：<路径列表>`；什么都没创建就写 `未产生临时文件`。

平台注意：pytest 优先用 `tmp_path` fixture，不要手工 `open("/tmp/x.py", "w")`；Windows 临时目录用 `tempfile.mkdtemp()` / `%TEMP%`，别往项目根丢；删除失败多半是文件仍被占用（编辑器句柄、未退出的 Python 进程），先关句柄再删。
完整细则见 `AGENTS.md`「测试收尾清理临时脚本」。

### 铁律 2：结论先实测，再采信

审查代理、静态扫描或真人 reviewer 给出的**语法/类型结论一律先实测裁定**，不直接采信。`except A, B:` 被判成「Python 2 语法」是本仓高复发假阳性。做法见 `references/static-check-adjudication.md`。

### 铁律 3：外科手术式改动

只改必须改的行：不顺手优化相邻代码/注释/格式，不重构没坏的东西，不删既有死代码（发现就提出来）。自己的改动制造出的孤儿（未使用的 import/变量/函数）由自己清理。详见 `references/engineering-principles.md`。

### 铁律 4：门禁只在本地入口跑一次

**不要在任何文档或 skill 里复制 black/isort/mypy 命令清单**——那会制造并行事实源并在 `AGENTS.md` 更新后静默漂移。全量门禁只有一个入口：`python scripts/run_gates.py`（命令清单运行时从 `AGENTS.md`「格式化命令」章节解析）。

## 路由表

| 触发场景 | 加载 | 配套 |
|---|---|---|
| 新功能 / 新子系统 / 新 UI / 产品级行为设计，动手前 | [`references/design-brainstorming.md`](references/design-brainstorming.md) | `assets/spec-reviewer-prompt.md` |
| 设计过程需要给用户看 mockup、架构图、方案对比 | [`references/visual-companion.md`](references/visual-companion.md) | `scripts/start-server.sh` |
| 拿不准需求、想先判断该不该做、要不要停下来问 | [`references/engineering-principles.md`](references/engineering-principles.md) | — |
| 编写或修改 `tests/` 下的测试 | [`references/testing-conventions.md`](references/testing-conventions.md) | — |
| 测试要 mock `subprocess.Popen` 或 stdlib 模块属性 | [`references/testing-conventions.md`](references/testing-conventions.md#4-subprocess-与-stdlib-模块替身) | — |
| 用户粘贴运行时日志要求解读 / 排查 / 修复 | [`references/log-fault-triage.md`](references/log-fault-triage.md) | — |
| mypy / basedpyright 报平台专属符号，或 Windows 过而 CI 红 | [`references/platform-type-gating.md`](references/platform-type-gating.md) | — |
| 有人报告语法错误 / 静态检查结论待裁定 | [`references/static-check-adjudication.md`](references/static-check-adjudication.md) | — |

**不属于本手册范围**：真正的崩溃栈回溯（走 systematic-debugging）、纯日志格式美化、一键式 trivial 改动。

## 验证

### 项目级门禁（统一入口，不复制命令清单）

全量门禁的唯一入口是 `python scripts/run_gates.py`（在仓库根目录执行）：按原顺序跑完全部 `--check` 型门禁，任一失败非 0 退出。**完整命令清单、收窄排障（`--only`/`--keep-going`/`--list`）与平台增跑（`mypy --platform linux`）的口径以 `AGENTS.md`「格式化命令（门禁唯一基准）」为唯一事实源，本手册只引用不复制**——需要逐条命令时用 `run_gates.py --list` 现场解析，或直接查该章节。

退出码语义：`0` 通过 / `1` 门禁红（代码问题）/ `2` 清单缺失或含写型命令（属「没跑」）/ `3` 可执行文件缺失（环境问题）。后两者不是代码不合格，别当成回归。

**单任务验证补充**（随配方执行，非 CI 门禁清单）：改动模块跑 `pytest tests/test_<module>.py -v` → **0 warnings**，涉及子进程输出时再单独跑一次该文件（抓 GBK/UTF-8 代码页问题）；改动文件用 `python -m py_compile` 或 `compileall src` 做语法检查，跑完按铁律 1 清 `__pycache__`；覆盖率跑 `scripts/check_coverage.py`（口径见 `AGENTS.md`「测试」与「完成定义」）。

安全不变量类测试必须做**变异验证**：临时改坏生产代码，确认测试转红；仅被既有测试覆盖的平凡断言可豁免。

## 输入输出约定

**输入**（向用户索取或自行确认，缺失时先问）：

- 目标模块路径：`src/<module>.py` ↔ `tests/test_<module>.py` 一一对应。
- 报错/日志**原文**：mypy 的 `file:line: error: ... [code]`、日志的 `file:func:line` 标记。
- 验证边界：允许跑哪些门禁、是否需要真机/端到端验证。

**输出**（每次任务的固定收尾形态）：

1. 改动文件清单 + 每个文件「改了什么 / 刻意没动什么」。
2. 门禁与测试结果（引用实际输出，不写「应该通过」）。
3. 清理结果一行（见铁律 1 第 7 条）。
4. 在回复里**显式写出本次做的假设与回滚方式**；沉默猜测仍属违规。

**额外收尾约定**：本仓库要求代码改动后同步更新 `CODE_WIKI.md` 与 `CODE_WIKI_EN.md` 的更新日志章节；新增的坑同步进 `AGENTS.md` 防回归条目并补专项测试。

## 常见误用（Red Flags）

- 新功能/子系统还没出设计就动手写代码。
- `patch.dict(os.environ, {...})` 改环境变量（Windows 32767 限制下必炸）。
- `monkeypatch.setattr(main.subprocess, "Popen", fake)` 直接改 stdlib 模块属性。
- 用 `# type: ignore` 压平台专属符号（在任一平台上都是错的）。
- 把无括号 `except A, B:` 「顺手改成」带括号（过不了 `black --check`）。
- 用 `chmod(0o444)` 测 `config_io` 只读路径（对 `os.replace` 无效）。
- 测试里自己实现一遍被测逻辑（假绿）。
- 把门禁命令清单复制到文档或 skill 里。
- 改完代码不同步 `CODE_WIKI.md` / `CODE_WIKI_EN.md` 更新日志。

## 目录结构

```text
dlr-dev-playbook/
├── SKILL.md                                  # 路由 + 通用铁律 + 统一门禁（引用 AGENTS.md）
├── references/
│   ├── engineering-principles.md             # 想清楚再做：假设外显、极简、外科手术、目标驱动
│   ├── design-brainstorming.md               # 设计流程、规格文档、评审门禁
│   ├── visual-companion.md                   # 浏览器可视化伴侣（配 scripts/）
│   ├── testing-conventions.md                # 测试编写强制约定 + stdlib 替身配方
│   ├── log-fault-triage.md                   # 日志分诊 + 三个已验证修复配方
│   ├── platform-type-gating.md               # mypy/basedpyright 平台专属符号门控
│   └── static-check-adjudication.md           # 静态检查结论的实测裁定（PEP 758 等）
├── assets/
│   └── spec-reviewer-prompt.md               # 规格文档评审子代理的派发模板
└── scripts/                                  # 可视化伴侣服务端（frame/helper/server/启停脚本）
```
