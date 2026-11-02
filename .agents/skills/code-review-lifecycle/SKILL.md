---
name: code-review-lifecycle
description: "Two-phase code review lifecycle. Phase A: read-only full-repo static review as a dispatched pipeline - sha256 baseline manifest (proves read-only, detects concurrent drift) -> scope table (area x files x lines) -> one shared brief carrying the repo deliberate-design whitelist -> partitioned read-only agents (2k-11k lines each, real-read line numbers) -> main-control re-verification of every high-severity claim plus an overturned-assertions appendix -> timestamp-bound report with rerun criteria. Phase B: remediating those findings - severity triage, one finding per unit of change, per-fix verification recipes, and a report template mapping every finding to a landed change. Includes a DouyinLiveRecorder branch (references/dlr.md) with that repo partition table, whitelist, gate entry points and same-source lock set. Use when the user asks 全仓静态代码审查、只读审查、输出 CODE_REVIEW_YYYY-MM-DD.md、整改审查报告、按审查结论逐条修复. Not for single diff or PR review, and not for comment-only refactors."
agent_created: true
---

# 只读审查生命周期（全仓静态审查 → 逐条整改）

## 本轮合并（2026-10-29）

本 Skill 是 2026-10-29 同类合并的归并结果。以下源能力的完整 playbook 已收编进本目录，按需加载 `references/<name>/SKILL.md`，不要把全部参考文档读进上下文：

- `code-review-remediation` → `references/code-review-remediation/SKILL.md`
- 宿主：本目录 SKILL.md 主体来自 `full-repo-static-review-dispatch`，目录名按合并后语义重命名。

被吸收源技能的 frontmatter 仅在其原子文档内作历史留存；本目录的 `name` 与路由表为准。跨组的兄弟能力引用见各参考文档内的重定向注。

## Overview

单人（单代理）读不完一个 20 万行的仓库，而「让 16 个代理各读一区」如果不设边界，会得到三种废物：把仓库刻意的设计报成缺陷、行号靠猜、以及主控不核对就写进报告的假断言。本 Skill 把一次全仓只读审查固化成 8 个阶段：基线自证 → 范围表 → 白名单简报 → 分区派发 → 主控逐条复跑 → 时间戳绑定成稿 → 复跑判据 → 收尾自证。

核心不是「读得快」，而是**每一条写进报告的结论都能被第三方用一条命令复现**。

## 何时使用 / 不使用

- 使用：用户要求对**全部源代码**做一次性静态审查；要求只读、不得改源文件；要求产出 `CODE_REVIEW_YYYY-MM-DD.md` 类报告；或需要评估「某次大规模合并/冲突解决之后仓库是否还健康」。
- 不使用：按已有报告逐条整改（用本组 `references/code-review-remediation/SKILL.md`）；审单个 diff / PR（用 `requesting-code-review`）；只改注释的批量重构（用 `comment-refactor-at-scale`）；只是问某段代码怎么工作。
- 写型并行派发（会改文件的代理、配额受限）不在本 Skill 范围，见 `comment-refactor-at-scale/references/dispatch-quota-aware-write-agents/SKILL.md`。本 Skill 的代理**一律只读**。

## 硬规则

1. **只读是硬约束，且必须自证。** 审查期间不编辑 / 不创建 / 不删除 / 不格式化仓库内任何文件；不得运行 `black`/`isort` 的写入形态、`pip install`、`pytest --cov`、任何 `git add/commit/checkout/reset/stash/clean`。所有探针落 `%TEMP%`。报告是唯一新增文件，收尾用基线复核证明这一点。若审查中发现需要修代码，**停下来问用户**；改完就不再是「只读审查」，要按整改流程重走。
2. **门禁退出码只取真实值。** 用 `命令 >"$LOG" 2>&1; echo rc=$?`，**禁止** `命令 | tail -5; echo "rc=$?"`——管道后 `$?` 是 `tail` 的退出码，会把红的门禁读成绿的。
3. **行号必须来自实读。** 代理与主控都一样：报告里的 `文件:行号` 必须对应实际 Read 到的内容。禁止用「大概在 300 行附近」推定。
4. **高严重度断言必须由主控独立复跑。** 子代理的任何「严重 / 中等」结论进报告前，主控要么复跑判据、要么标注「待确认 + 缺哪一步」。被推翻的断言不得静默删除，单列成节（见 `references/report-outline.md` §7.2）。
5. **白名单只能来自仓库自身的约定。** 「本项目刻意设计」清单必须逐条能在仓内找到出处（AGENTS.md 章节、CODE_WIKI 条目、历史审查报告、测试里的锚点注释）。主控不得自造，也不许代理自造；找不到出处的取舍不享豁免，按缺陷评。
6. **结论绑定「实测时刻 + 复跑命令」。** 审查期间工作区可能被别的进程持续修改；每条结论写明取数时刻，并给一条能重跑的判据。并发包在期内修掉的项**单列**，不进本轮清单。
7. **不读子代理的 transcript JSONL。** Agent 返回里那个 `output_file` 是完整会话流水，读它会直接撑爆上下文；只要完成通知与代理的回传正文。
8. **未执行项显式声明。** 没联网、没真机、没跑全量 pytest 的，写「未执行 + 原因 + 交回用户的动作」，不得用静态推定的口气写成已验证。

## 流程

### 阶段 0：锁定口径（先问清，别默认）

把用户指令拆成四要素并写进报告 §2：**范围**（哪些语言 / 哪些目录 / 排除什么）、**维度**（质量 / 缺陷 / 安全 / 逻辑）、**输出**（文件名、重名时的 `_2`/`_3` 规则、放哪个目录）、**只读边界**（能否新增报告文件本身）。缺项就按仓库既有惯例补齐，并在报告里注明「本项为我方默认，用户可改」。

输出目录：先查仓库是否已有 `docs/worklog/` 或同类历史报告约定；有则沿用，并在报告首行说明放置理由；用户明确指定了路径则从用户。

### 阶段 1：基线（证明只读 + 抓并发改盘）

```bash
# 用仓库自己的解释器（有 venv 就用 venv，且与 CI 同版本）
python <本 Skill 目录>/scripts/review_scope.py --root .
# 不传 --out 时自动落到系统临时目录并打印路径，跨平台不用自己拼路径
```

同时记录三件事：`git rev-parse --short HEAD`、`git status --porcelain | wc -l`、以及 HEAD 自身的完整性（若 HEAD 含未解决冲突，用 `git grep -c '^<<<<<<< ' HEAD` 一次统计，**不要**逐文件 `git show` 循环——见 `references/pitfalls.md` 流水线层 #5）。

基线的作用有两个：收尾证明「只读」，中途证明「别人动了哪个文件」。

### 阶段 2：范围表

同一脚本的默认输出即范围表：按区域（根入口 / `src/` 各子目录 / `tests/` / `scripts/` / 前端 / CI 配置 …）给出文件数与行数。把它直接贴进报告 §2.1，并单列**排除项**（venv、构建产物、锁文件、第三方压缩库、生成物、基线快照目录、文档正文）。

范围表是后续分区的唯一依据：分区别凭感觉切，按这张表的行数切。

### 阶段 3：写共享作业简报（白名单的载体）

用 `references/brief-template.md` 落一份 `%TEMP%/review-brief-YYYY-MM-DD.md`，填五块：只读硬约束、**已实证的仓库当前状态**（避免代理把已知状态当新发现，例如「HEAD 里本来就有 899 个冲突块」）、刻意设计白名单、审查维度、严重度定义与回传格式。

这一步的收益最大：16 个代理读同一份简报，报告才不会出现「同一个约定在 A 区算缺陷、在 B 区算合规」。DLR 的实测清单在模板里作样例。

### 阶段 4：分区派发

- **粒度**：每区约 2k–11k 行。超长单文件按自然边界切（函数/类边界），并在 prompt 里写清切点（例：`src/spider.py` 全 21317 行 → L1–L11000 与 L11000–末尾两个代理），要求代理声明实际切断点。低于 2k 行的区可以合并，否则代理会把注意力花在「没什么可看」上。
- **每个 prompt 四段**：① 第一步 Read 简报；② 审查范围（文件 + 行区间 + 该区职责）；③ 该区**专属判据**（不要复用别的区的，否则代理互相越界报告）；④ 行号纪律 + 最多 20 条 + 覆盖确认 + 卫生扫描结果。
- **并发**：只读代理可以一波全发（`run_in_background: true`），但若账号有日配额或排队限制，按波次发并在报告里登记因中断造成的覆盖缺口。
- **禁止越界**：明确写「本区之外的发现另起一行标 `[越界]`，不计入你的 20 条」；否则相邻区会重复报同一处。
- 代理必须回传两样东西：**覆盖确认**（实际读了哪些文件/行区间，未覆盖部分是什么）和**范围性卫生扫描结果**（每条 grep 判据 + 命中数，0 也要写「实测 0 处」）。

代理的「无发现」也是结论：没有发现就要求它写「未发现 + 覆盖了哪些维度 + 用什么判据扫的」，不接受一句「未发现问题」。

### 阶段 5：主控复核（本流程的价值所在）

对每一条会被写成「严重」或「中等」的断言，主控自己做一遍：

- **集合差必须用干净基线。** 要证明「文件/用例/资产丢了」，参照点取**已知不含冲突标记的祖先提交**，不是 HEAD；且优先比 **AST 符号集合或用例名集合**，不要用行级 diff。HEAD 本身损坏时，拿它做基线会把冲突副本算成「丢失」。
- **数量断言必须落到具体归属。** 「丢了 N 条用例」要给出文件、用例名、基线计数与工作区计数。「注释被整段删了」要贴出工作区头 N 行实证。
- **「本项目刻意如此」类反驳要找到出处。** 代理说某设计是缺陷、你认为不是——引用 AGENTS.md 的章节或测试里的锚点，找不到出处就按缺陷收。
- **每条结论写两列**：子代理断言 / 主控复核实测 + 处理（采纳 / 降级 / 不采纳 + 理由）。
- **并发修复单列**：复核时发现该项已被另一工作包修掉，移到「期内被修复」节，附修复时刻与复跑判据，不进本轮清单。

### 阶段 6：成稿

按 `references/report-outline.md` 的骨架写。必须有的、且最容易被省略的三节：**§7.1 上轮遗留核对**、**§7.2 被推翻断言**、**§7.3 期内被并发修复**；以及 **§8.3 可复跑判据清单**（每条判据给命令 + 期望值 + 当前实测值）与 **§9 未执行项声明**。

严重度先定口径再定级：**严重** = 进程崩溃 / 数据损坏 / 凭据泄露 / 安全防线失效 / 功能完全不可用 / 提交态产物不可用；**中等** = 特定条件行为错误、资源持续增长、防线可绕过、维护上会误导后人（含悬空引用）；**轻微** = 可读性、命名、日志噪声、备案性观察。

### 阶段 7：复跑自证与收尾

```bash
python <本 Skill 目录>/scripts/review_scope.py --check <阶段 1 打印的基线路径>   # 0 漂移 = 只读成立
git status --porcelain | grep '^??'                                            # 未跟踪应只有报告
```

- 门禁结论各跑一次真实 rc（硬规则 2），并在报告 §2.3 写清工具版本与「本地口径 / 未经 CI 同版本验证」。
- 收尾删掉 `%TEMP%` 下本次产生的探针与简报（`tmp_`/`_tmp_`/`mock_` 前缀），列出删除清单。
- 若中途有并发包改盘，最终报告要写「起始 N 个未提交改动 → 定稿 M 个」，并说明哪些结论可能已过期。
- 按仓库的完成定义（如 AGENTS.md 的 DoD）判定本次豁免项：纯文档产出通常只适用文档同步与日志两条。

## 与相邻 Skill 的边界

| 场景 | 用哪个 |
| --- | --- |
| 生成审查报告（只读） | 本 Skill |
| 按报告逐条整改、修完收口 | 本组 `references/code-review-remediation/SKILL.md` |
| 批量改文件、配额受限的写代理 | `comment-refactor-at-scale/references/dispatch-quota-aware-write-agents/SKILL.md` |
| 纯注释/文档重构的等价性证明 | `comment-refactor-at-scale`（同名一级目录） |
| 已经定位到单个 bug 要修 | `systematic-debugging` |
| 工具层配方（rc 取值、转义被吃、AST 按节点判定、pytest 残留） | `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md` |
| 审查 DouyinLiveRecorder 仓库（该仓分区表、门禁入口、同源锁族、刻意设计白名单） | 本 Skill 的 8 阶段照用 + `references/dlr.md` 分支 |

## 资源

- `references/brief-template.md` — 共享作业简报模板（含 DLR 已实测的白名单样例、回传格式）。派发前必读。
- `references/report-outline.md` — 报告骨架，含 §7.2/§7.3/§8.3/§9 的写法。
- `references/pitfalls.md` — 流水线层 8 个坑（干净基线、并发改盘、不复跑、自造白名单、git 遍历超时、读代理流水、无复跑判据、把「未发现」当覆盖），每条给「症状 → 错误做法 → 正确做法 → 判据」；工具层问题在最上方指路 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md`。
- `scripts/review_scope.py` — 范围表 + sha256 基线；`--check` 复比漂移（0 = 只读成立）。只读，不写仓库。
- `scripts/ast_probe.py` — 只读 AST 判据扫描（解析失败 / 重复定义 / `except: pass` / 未入 with 的 `open()` / 危险原语 / 无超时子进程 / 结构度量 / 疑似未用 import）。阈值可配（`--long-fn/--nest/--params`），默认扫全仓 `.py`（含仓库自带的工具脚本，需要收紧就 `--skip .agents` 之类）。输出紧凑摘要，`--json` 给全量；命中是线索不是结论。
- `references/dlr.md` — DouyinLiveRecorder 专属分支：该仓的事实源交接表、`repo_review_snapshot.py` 用法、P1 分区表与默认排除清单、冲突态基线选择、门禁入口与同源锁族、报告落盘惯例。**审查该仓时在阶段 0 之前加载**；其他仓库不要用它。
- `references/dlr-design-whitelist.md` — 该仓「刻意设计」白名单本体，阶段 3 填进简报；缺它代理会把 `AGENTS.md` 钉死的约定报成缺陷。
- `references/dlr-measurement-recipes.md` — 该仓 10 组判据配方（冲突普查、干净基线、AST 符号差集、门禁 rc、定点 pytest、钉定对账、悬空锁引用、同源锁族）。工具层原理不在此复述，指向 `dlr-dev-playbook/references/windows-readonly-source-probing/SKILL.md`。
- `scripts/repo_review_snapshot.py` — 该仓专属：`snapshot` 产逐文件 sha256 `manifest.json` + `facts.json`（冲突块 / AST 解析失败 / 分区行数），`verify` 复比并证明只读；默认只写 `%TEMP%`，拒绝写入仓库。与 `review_scope.py` 的分工见 `references/dlr.md`。
