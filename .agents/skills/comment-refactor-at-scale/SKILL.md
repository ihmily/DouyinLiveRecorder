---
name: comment-refactor-at-scale
description: >-
  End-to-end pipeline for a repo-wide comment/docstring-only refactor done by parallel write agents
  under a capped quota: pre-flight text locks and line-anchor whitelists → baseline snapshot (including
  files the snapshot tool skips) → shared rules file and append-as-you-go JSONL ledger → quota-aware
  wave sizing with exclusive file domains → edit hard constraints → six-dimensional equivalence proof
  (Python ast.dump / comment-stripped code lines / BOM-aware encoding-EOL / measured-reading survival
  / per-file density / formatter+aggregated gates) → four audits → wave-death recovery from artifacts
  → closing gates and structured report.
  Use when the user asks to 精简/优化/重写/统一 comments or docstrings without changing behavior, asks
  to prove 逻辑未改动/行为不变, runs a repo-wide comment or i18n-copy cleanup, dispatches file-writing
  subagents in waves on a rate-limited or interruptible account, or a wave died mid-run and the completed
  scope must be reconstructed from artifacts; also on triggers comment-only refactor、零行为变化、注释精简、
  注释重构、等价性校验、AST 等价、baseline snapshot、CRLF 被改、注释里的锚点失效、密度删穿、实测读数被概括、
  配额、daily usage limit、Queuing failed、write agents、wave、台账覆盖缺口.
  Not for behavior-changing refactors, code deletion, feature work, read-only research fan-out
  (use superpowers:dispatching-parallel-agents), or a single small edit.
agent_created: true
---

# Comment Refactor at Scale

## 本轮合并（2026-10-29）

本 Skill 是 2026-10-29 同类合并的归并结果。以下源能力的完整 playbook 已收编进本目录，按需加载 `references/<name>/SKILL.md`，不要把全部参考文档读进上下文：

- `dispatch-quota-aware-write-agents` → `references/dispatch-quota-aware-write-agents/SKILL.md`
- `safe-batch-text-rewrite` → `references/safe-batch-text-rewrite/SKILL.md`

被吸收源技能的 frontmatter 仅在其原子文档内作历史留存；本目录的 `name` 与路由表为准。跨组的兄弟能力引用见各参考文档内的重定向注。

## Overview

Turn "I only touched comments" into machine-checkable evidence — and make that evidence survive
the fact that the touching was done by several agents that may die mid-run. The pipeline is one
contract with two halves that used to live in two skills:

- **the verification contract** — what every edit must satisfy (equivalence, density, readings);
- **the dispatch contract** — how to size waves, partition files, and recover from artifacts when
  the quota runs out.

Neither half is optional. A wave that lands edits without the contract produces an unauditable tree;
a contract that assumes a single careful editor does not survive 14 parallel agents.

## When To Use / Not Use

- Use: comment or docstring rewrite/cleanup/normalization where behavior must not move; repo-wide
  text hygiene that must survive code review and CI; multi-file text edits dispatched to write agents
  on an account that can queue or hit a daily cap mid-wave.
- Do not use: any change to executable content; a one-line typo fix in a single file (just edit it);
  read-only research fan-out (`superpowers:dispatching-parallel-agents`); a single small edit;
  changes where the user must approve each edit interactively.

## Core Principle

Three structural metrics are independent because each is blind to a different failure:

| Metric | Catches | Blind to |
| --- | --- | --- |
| Structural signature (`ast.dump` for Python; comment-stripped code-line sequence for JS/CSS/HTML/VBS) | changed constant, deleted statement, edit inside a string literal | line-ending churn, files the parser accepts either way |
| Encoding/EOL shape (BOM-aware, compared after decoding) | `write_text` converting CRLF→LF or UTF-16→UTF-8; mixed-EOL introduction | anything inside the code structure |
| Parseability + formatter check | a swallowed newline that merged a code line into a comment | comment text that is now factually wrong |

Three non-structural checks sit around them: snapshot coverage, per-file density and measured-reading
survival. Never claim "logic unchanged" from only one of them.

## Stage 0 — Scope and Pre-flight Gate (before any edit)

1. Confirm the task is comment-only. If any executable change is wanted, do it in a separate commit
   so the equivalence proof stays clean.
2. Exclude assets that a comment edit silently destroys. Determine it by reading the repo, not by
   guessing: search for byte-level hash pins, generated-file headers and non-UTF-8 encodings.
   - *Verified instance (DouyinLiveRecorder)*: `src/javascript/*.js` pinned by
     `src/utils.py::_JS_SHA256_EXPECTED`; `src/proto/douyin_pb2.py` (protoc output);
     `StopRecording.vbs` (UTF-16LE + BOM, so grep reports binary).
3. Text inside string literals is a **constant value**, not a comment. Detect with the AST or
   tokenizer rather than by eye; an edit there reddens the signature check.
4. Enumerate text locks before deleting anything:
   - `python <skill-dir>/scripts/check_comment_refs.py --repo <root> --strict` lists every
     `file:line` anchor and comment reference; treat the `drift-prone` bucket as do-not-touch.
   - `grep -rn "read_text\|read_bytes\|getsource\|doesNotMatch" tests/` lists tests that read source
     text; read their assertions and mark any file whose comment text they lock.
   - Distinguish safe locks from dangerous ones: tests that **strip comments before asserting** are
     safe under comment edits; tests asserting raw line/byte offsets are not. Record which is which.
   - A pre-existing drift (an anchor already broken before this task) is handed back as "not caused
     by this batch"; do not absorb it into the wave.
   - After the snapshot, `refactor_guard.py preflight` checks coverage, density, removed locks and
     anchor drift; run it once before editing and again after the first edit. A changed file with no
     baseline is a FAIL, not a skip. Treat lock hits as candidates: confirm the hit is an assertion,
     not a prose mention — a bare `[历史注` prefix is shared by unrelated notes and is not a unique
     lock; only a date/ticket-bearing prefix is.
5. Compute each file's comment-density budget before choosing delete vs rewrite. The hard floor is
   the repo's gate (DouyinLiveRecorder: 13.0% per Python file); a file already below ~16% is
   rewrite-only, above ~18% has a small net-delete budget. Deleting N comment lines always lowers
   `(C-N)/(T-N)`.
6. Build the candidate list: `python <skill-dir>/scripts/audit_comments.py --repo <root> --json
   <scratch>/candidates.json`. It tags S1 code-like/contradictory, S2 archaeology, S3 duplicate/TODO,
   S4 vague, S5 long/block, plus `K` contract wording that must survive. `K` is a must-survive tag,
   not a ledger category. Treat the output as a ranked reading list, not a verdict: each candidate
   still needs a code/test check.

## Stage 1 — Baseline Snapshot

Prefer a repo-provided snapshot/compare tool; if none exists, copy the in-scope files yourself
preserving relative paths. Verify coverage before trusting it — a tool that only mirrors `**/*.py`
leaves frontend/doc files unprotected.

- The bundled `refactor_guard.py snapshot --all` copies every in-scope extension and writes a manifest
  (hash, encoding, BOM, EOL profile, density). Prefer it when the repo tool covers only `.py`; it
  includes `.mjs`, root `index.html` and other non-Python assets:
  `python <skill-dir>/scripts/refactor_guard.py snapshot --repo <root> --base <baseline> --all`
- Put the snapshot inside the workspace (tooling often refuses absolute or outside paths).
- Record the file count printed at snapshot time; the same number must reappear at compare time.
- *Verified instance*: `python scripts/check_annotations.py --snapshot .workbuddy/<task>-base`
  mirrored 259 files (`.py` + top-level `web/**` only, **not** `tests/frontend/*.mjs`); the retained
  baseline now measures 260 (`find <base> -type f | wc -l`, 2026-10-27) — re-measure, do not trust
  the constant. It skips its own `EXCLUDE_FILES` (`douyin_pb2.py`,
  `scripts/douyin_live_recorder_standalone.py`) while mypy still scans them, so those need a separate
  `ast.dump` comparison.
- Coverage check: `preflight` fails any changed file that was not snapshotted. If using a repo tool
  instead, subtract its file list from `git diff --name-only`.
- A baseline rebuilt from `git show`/`git archive` is **structural only**: with `core.autocrlf` the
  blob may be LF while the checkout is CRLF. Feed it to `verify_equivalence` (AST/code lines), not to
  the EOL preflight, or rewrite it to the current EOL profile. Verified 2026-10-27: a HEAD-archive
  baseline produced 135 false `crlf -> lf` failures on a tree whose working-tree snapshot verified
  260/260.

## Stage 2 — Shared Rules File and Ledger

Write one rules file before dispatching any agent or starting batch 2, and point every worker at
that path rather than paraphrasing it. Use `references/rules-template.md`. It must contain: absolute
prohibitions, the must-survive topic list, the archaeology-compression convention, a terminology
table, per-group self-check commands, and the ledger schema.

**Ledger record** — append one line **immediately after each edit**, never batch-written at the end
(an interrupted agent then leaves zero evidence):

```json
{"file":"path/from/repo/root","line":123,"action":"delete|compress|dedupe|correct","category":"S1|S2|S3|S4|S5|N","before":"<=160 chars","after":"<=160 chars","reason":"why this change is correct"}
```

- `line` = baseline (pre-edit) line number, so records stay reconcilable to the snapshot;
  `before`/`after` truncated to 160 chars to keep ledgers cheap.
- One ledger file per agent domain: `log-<domain>.jsonl`, all under a single logs directory outside
  tracked code (temp dir or git-ignored dir).
- The **diff file set is the coverage source**; the ledger is the audit trail for it. When a domain
  has a diff but no ledger, reconstruct its audit from the diff and record the missing ledger as a
  defect. Ledger absence is an audit defect, not proof that nothing landed.
- Categories may be renamed per task, but keep one stable legend. Verified default (source session
  `fcc124ca`): **S1** contradicts or misleads about current code (highest); **S2** archaeology, dates,
  ticket IDs; **S3** duplicate explanation; **S4** vague "what it does" line; **S5** verbose but valid
  (compress wording, keep every criterion); **N** pending human decision (leave untouched and report
  it). Dedupe: keep the module header or first full occurrence; reduce the rest to one short pointer line.

## Stage 3 — Quota-Aware Dispatch

1. **Wave size ≤ 4 write agents, one wave at a time.** Never dispatch more concurrent write agents
   than the remaining quota verifiably covers for the whole wave. If quota is uncertain, shrink the
   wave — a 14-agent wave that dies at 100% interruption yields less auditable progress than four
   3-agent waves. Wait for every agent of the current wave to notify before starting the next.
2. **On the first queueing / daily-cap failure, stop dispatching and finish in the main session.**
   Those errors mean the quota is gone for the rest of the session; further agents die the same way
   and leave less auditable debris. Record the strategy switch ("parallel → solo after N queue/cap
   failures") in the report.
3. **One agent = one exclusive file domain.** Domains must be pairwise disjoint. A giant single file
   (thousands of lines) gets its own dedicated agent; never bundle it with other files.
4. **The main session only takes files no agent owns.** If the controller edits in parallel, it must
   pick up unassigned files only, stated explicitly in its report.
5. **Agents self-verify locally; the controller runs full gates once.** Agents may run the scoped
   equivalence/format checker (`verify_equivalence.py`, `refactor_guard.py guard`, formatter on their
   own files) and their own domain's test file. Agents must **not** run project-wide gates (full
   pytest / mypy / lint sweep) — concurrent gate runs interfere and each run burns the whole batch's
   time. Aggregated gates run in the main session after the last edit of the batch. *(This resolves
   the apparent conflict between "row 6 = formatter + aggregated gates" and "agents do not run full
   gates": the formatter part is per-group, the aggregated-gate part is controller-only, once.)*

Every agent prompt must contain: the absolute file list it owns ("do not modify any other file");
the path to the shared rules file (single source of truth, not a paraphrase); the prohibitions (no
edits inside string literals, do-not-touch files/spans from Stage 0, keep line-ending style, precise
edits never full-file rewrite); the exact ledger path and schema with "append per change, not at the
end"; the self-verify scope; and the report format (N changes, ledger path, verification command's
pass/fail line, any leftover region judged unsafe).

## Stage 4 — Edit Constraints

- Precise replacements only. A full-file write is forbidden: it converts line endings, drops trailing
  bytes and hides what changed.
- Preserve each file's existing EOL shape; `# type: ignore`, `# noqa`, shebang, coding lines and
  copyright headers stay verbatim.
- No new docstrings where the repo mandates `#` comments (and vice versa); docstrings enter the AST,
  `#` comments do not, and the signature proof relies on that asymmetry.
- Deletion is a judgment call: keep order constraints, invariants, contracts, thread/lock models,
  platform differences and regression-lock anchors; drop archaeology, restated code, id lists and
  stale claims that contradict the code. When unsure, keep it and log `N-待人工确认`.
- Measured readings are content, not prose: numbers, units, thresholds, timings, sizes, peak memory
  and ratios stay verbatim. "实测压缩 203KB → 解压 200MB、峰值 405MB" may not become "超大"; if a
  reading is stale, replace it with a new measured value and the date/command that produced it.

## Stage 5 — Equivalence Verification

Acceptance is six-dimensional. Rows 1–3 are the structural proof; rows 4–6 are the non-structural
checks a pure AST comparison cannot see.

| # | Dimension | Command | Pass condition |
| --- | --- | --- | --- |
| 1 | Structural signature (`ast.dump` for Python) | `verify_equivalence.py` | `ALL OK` |
| 2 | Comment-stripped code lines + parseability (JS/CSS/HTML/VBS) | `verify_equivalence.py` | `ALL OK`; no syntax failure |
| 3 | Encoding / BOM / EOL shape (compared after decoding) | `verify_equivalence.py` | no `encoding` or `EOL shape` reason |
| 4 | Measured-reading survival | `refactor_guard.py guard --strict-readings` | no `readings lost: <file>` entry |
| 5 | Per-file comment density vs floor | repo gate + `refactor_guard.py preflight` | no file crossing the floor |
| 6 | Formatter (per group, by the agent) + aggregated gates (once, by the controller) | black/isort + `run_gates.py` | no reformat; gates green |

Run rows 1–4 per group while working, and once over the whole change set after the **last** edit:

```bash
python <skill-dir>/scripts/verify_equivalence.py --repo <root> --base <baseline_dir> --quiet
python <skill-dir>/scripts/verify_equivalence.py --repo <root> --base <baseline_dir> src/a.py web/app.js
python <skill-dir>/scripts/refactor_guard.py guard --repo <root> --base <baseline_dir> --strict-readings
```

`ALL OK -- checked N, ok N, skipped 0` with exit 0 is the only acceptable verdict;
`FAIL ... EOL shape ('crlf','pure') -> ('lf','pure')` means a whole-file write happened and must be
re-done with precise edits. Then the density/preflight check and the repo's own compare tool:

```bash
python <skill-dir>/scripts/refactor_guard.py preflight --repo <root> --base <baseline_dir>
python scripts/check_annotations.py --baseline <baseline_dir>   # if the repo has one
PYTHONUTF8=1 python -m black --check --diff --line-length 120 --target-version py314 <files>
```

Black may demand `# （` spacing after a shortened comment — fix the comment, never the code.

## Stage 6 — Audit the Claims

Four checks in this order; details and reproduction commands in `references/audit-scanners.md`.

1. **Ledger tally and coverage** — group changes by category/action to see what was actually done.
   Automated: `python <skill-dir>/scripts/audit_comments.py --repo <root> --ledger-dir <logs>
   --ledger-only --strict` fails on malformed JSON, missing keys, duplicate rows, or a changed source
   file with no ledger record. Scope it to the task (`--paths`) or allowlist files changed by another
   task (`--allow-unlogged`) before treating a gap as damage. *(Verified instance: a `_tars.py`
   comment edit had no row while the report listed that domain as unchanged.)*
2. **Comment-reference integrity** — `python scripts/check_comment_refs.py --repo <root>`: every
   path, `file::Test::test_name`, line anchor and backticked symbol found *inside a comment* is
   checked against the code that survives comment stripping. HIGH = provably wrong, MED = outside the
   repo tree or a placeholder, LOW = needs context. Re-scan changed files after fixing.
   `preflight` additionally scans code and string constants for `path.py:<line>`; a whitelist such as
   `ALLOWED = {"src/ui_i18n.py:34"}` is invisible to a comment-only scan.
3. **Theme survival** — count load-bearing phrases in the baseline and current corpora over the
   *shared file set*; any theme that drops to zero is a lost contract. `python <skill-dir>/scripts/
   audit_comments.py --repo <root> --themes <themes.txt> --baseline <baseline>` counts comments only;
   add `--strict` to exit 1 on a zeroed theme. The whole-text variant is in `references/audit-scanners.md`.
4. **Readings survival** — `refactor_guard.py guard --strict-readings`: any measured number/unit in a
   baseline comment but absent from the current file is a candidate lost reading. Ticket IDs and dates
   are filtered out; sizes, timeouts, counts and ports are not. Restore verbatim or record why it is
   obsolete. The regex also catches line references, date fragments and ratios; confirm each candidate
   is a measurement before restoring. A line reference that drifted because comments were deleted is a
   re-anchor task, not a lost reading.

## Stage 7 — Recovery When a Wave Dies

Read `references/dispatch-recovery-playbook.md` and follow it in order. Under time pressure these
three rules still hold:

1. **Full-batch equivalence check before triage** — prove the half-finished tree is unbroken first;
   per-file probes miss an edit in a file nobody expected to change.
2. **Coverage comes from artifacts, in three states** (landed / partial / zero artifact), crossed
   against the task notification's `<usage>` readings (`tool_uses`, `subagent_tokens`), the
   `git status` file set and the ledgers. Dead agents here each burned 32–97 tool uses, so no report
   ≠ no work; and only 3 of 14 domains left a ledger, so no ledger ≠ no work either.
3. **Revert out-of-bounds edits in place** before accepting any file as done. Check every diff line
   is inside the allowed edit class — the incident caught an agent that had edited inside a
   `_SCRIPT = r"""…"""` literal, a constant-value change that black, isort, mypy and the annotation
   checker all pass.

Then hand the user the three-state list with a volume reading per row, and split the conclusion into
done / not-done + reason + the action handed back — never an approximate "about half done".
Ledger audit: `python <skill-dir>/scripts/audit_ledger.py <logs_dir> [--claims claims.json]` checks
malformed/missing fields, duplicate records and cross-agent domain overlap; run it before declaring a
wave auditable.

## Stage 8 — Closing Gates and Report

- Run the repo's aggregated gate runner once, **after the final edit**. Per-file gates run by agents
  during a wave are not the closing evidence.
- Classify every failure before reporting. A missing dev dependency can redden hundreds of tests at
  collection or asyncio-decorator level; count the shared error signature and separate it from real
  regressions, e.g. `pytest -q 2>&1 | tee <log>` then `grep -c "<signature>" <log>` against the
  reported failure total. State the repair as a user action when the repo forbids the agent from
  touching the environment, and report "gates green" and "pytest undecidable due to missing
  dependency" as two separate facts — never claim the suite passed.
- Separate `PRE-EXISTING` (already red at baseline) from damage caused by this task; report both
  counts. Turn every unverified boundary (no baseline, missing dev dependency, unsnapshotted file)
  into a next task instead of calling the task complete.
- Follow `references/report-template.md`: delivery status; proof matrix; classification table
  (S1–S5/N with severity, locations, dedupe note, disposition); implemented minimal fixes; exclusions;
  handbacks and next batch. Report numbers, not adjectives: files checked, files changed, net comment
  lines removed, density before→after, gates green count, and any unverified boundary turned into a
  next task.
- Clean up: delete the snapshot dir, ledgers and one-off tools unless the user asks to keep them;
  confirm with `git status --short` that only intended files remain.

## Regression Handling Decision Tree

When a check reddens, the fix is determined by the surface, not by rewriting the test:

| Red surface | Action |
| --- | --- |
| A test asserts a literal comment phrase (`[历史注 2026-09-30`, a back-reference) | Restore the literal; never edit the test constant. |
| A `path.py:<line>` whitelist or anchor drifts | Roll back the whole anchored target file to baseline; migrate the anchor to a symbol in a separate, approved change. |
| A file falls below the density floor | Restore a load-bearing comment (rationale/invariant/anchor); no filler. |
| A measured reading is missing | Restore it verbatim; if stale, replace with a measured value + date/command. |
| A string literal changed | Revert the constant exactly; re-run the signature check. |
| EOL/encoding changed | Redo with precise replacements; never re-emit the file. |
| A changed file has no baseline | Build one with `git show <rev>:<path>`; do not accept a skip. |

## Failure Modes Learned The Hard Way

See `references/pitfalls.md` (13 verified entries with detection commands). Most consequential:
edits landing inside string literals; CRLF→LF or UTF-16→UTF-8 conversion invisible to the AST and
black; a replacement swallowing a newline and turning a code line into a comment; deleting a comment
phrase a test asserts verbatim; trusting a snapshot that never covered the frontend set; over-deleting
until a per-file density floor trips; compressing a measured reading into a vaguer phrase; a
dependency gap masquerading as a mass regression; a HEAD/archive baseline flipping EOL; trusting an
interrupted worker's "done" without a ledger and artifact check.

## Resources

- `scripts/verify_equivalence.py` — structural equivalence checker: Python `ast.dump`,
  comment-stripped code lines, BOM-aware encoding/EOL; a missing baseline is a failure, not a skip
  (stdlib only).
- `scripts/refactor_guard.py` — snapshot manifest, preflight (coverage/density/locks/anchors),
  guard (equivalence + lost measured readings).
- `scripts/check_comment_refs.py` — comment-reference scanner, HIGH/MED/LOW layered output.
- `scripts/audit_comments.py` — optional S1–S5/K candidate inventory, comment-only theme survival,
  and JSONL ledger coverage/format audit (`--ledger-only`, `--themes`); a triage aid, not an
  equivalence gate.
- `scripts/audit_ledger.py` — stdlib-only JSONL ledger validator and cross-agent domain-overlap
  checker (`--claims`); exit 1 on any violation.
- `references/rules-template.md` — shared rules file skeleton; canonical home of the ledger schema.
- `references/dispatch-recovery-playbook.md` — wave-death recovery: order of operations, three-state
  coverage adjudication, out-of-bounds detection and revert, solo failover, hand-back contract.
- `references/audit-scanners.md` — ledger/reference/theme/readings audit commands.
- `references/report-template.md` — six-section delivery format.
- `references/pitfalls.md` — verified failure modes, detection commands, repo-specific instances.
