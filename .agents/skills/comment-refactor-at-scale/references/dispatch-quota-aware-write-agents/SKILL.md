---
name: dispatch-quota-aware-write-agents
description: Batching and loss-control protocol for dispatching file-writing subagents on quota-limited accounts (model queueing / daily usage caps). Use when parallelizing multi-file edits with write-type agents on a rate-limited or interruptible account, in waves, or when a batch of agents died mid-run and their completed scope must be reconstructed from artifacts instead of re-dispatched. Not for read-only research parallelization (use superpowers:dispatching-parallel-agents) or single-file small edits.
---

# Quota-Aware Dispatch of Write Agents

## Overview

When write-type subagents share a capped quota, a single oversized wave fails all-at-once and leaves half-done changes with no audit trail. This skill fixes both ends: how to size and brief each wave, and how to recover by forensics on artifacts when agents die anyway.

## When to Use / Not Use

- Use: batched, structurally similar edits across many files, dispatched to agents that modify files, on an account that can queue or hit a daily usage cap mid-wave.
- Do not use: read-only research or investigation fan-out (`superpowers:dispatching-parallel-agents`); a single small edit; changes where the user must approve each edit interactively.

## Hard Rules

1. **Wave size ≤ 4 write agents, and one wave at a time.** Never dispatch more concurrent write agents than the remaining quota verifiably covers for the whole wave. If quota is uncertain, shrink the wave — do not gamble; a 14-agent wave that dies at 100% interruption yields less auditable progress than four 3-agent waves. Wait for every agent of the current wave to notify before starting the next.
2. **On the first queueing / daily-cap failure, stop dispatching and finish in the main session.** Those errors mean the quota is gone for the rest of the session; further agents die the same way and leave less auditable debris. Record the strategy switch in the report.
3. **One agent = one exclusive file domain.** Domains must be pairwise disjoint. A giant single file (thousands of lines) gets its own dedicated agent; never bundle it with other files.
4. **The main session only takes files no agent owns.** If the controller edits in parallel with agents, it must pick up unassigned files only, stated explicitly in its report.
5. **Agents self-verify locally; the controller runs full gates once.** Agents may run the repo's scoped equivalence/format checker and their own domain's test file. Agents must NOT run project-wide gates (full pytest / mypy / lint sweep) — concurrent gate runs interfere with each other and each agent's run burns the whole batch's time. Full gates run in the main session after the last edit of the batch.
6. **Append-as-you-go JSONL ledger is mandatory** (see below). Ledger absence is an audit defect, not proof that nothing landed: in the incident wave only 3 of 14 domains wrote a ledger while most of their edits had already reached the tree.

## Pre-flight (before writing agent prompts)

Scan the repo for things a comment/text edit can silently break, and turn findings into per-agent constraints:

- **file:line-anchored test whitelists**: grep tests/config for literal `path.py:<number>` anchors. Any file referenced by such a whitelist becomes a **do-not-touch** file (line numbers drift when lines are added/removed, which reddens the lock).
- **verbatim-asserted text**: grep tests for exact phrases present in target files (assertions on comment/doc/string content that must be preserved character-for-character). Point agents at these spans and forbid touching them.
- **string-literal prohibition**: every agent prompt must explicitly forbid modifying the inside of string literals (UI/i18n copy, log messages, regexes, help text, config keys) — otherwise agents editing "comments" will "fix" copy inside strings.
- Distinguish safe locks from dangerous ones: source-reading tests that **strip comments before asserting** are safe under comment edits; tests asserting raw line/byte offsets are not. Record which is which.
- If a pre-existing drift is found (an anchor already broken before this task), note it as "not caused by this batch" and hand it back to the user instead of fixing it inside the wave.

## JSONL Ledger (interruption-proof audit trail)

Each agent appends **one JSON line per change, immediately after making it** — never batch-write the ledger at the end (an interrupted agent then leaves zero evidence):

```json
{"file":"path/from/repo/root","line":123,"action":"delete|compress|dedupe|correct","category":"<task taxonomy tag>","before":"<=160 chars","after":"<=160 chars","reason":"why this change is correct"}
```

- `line` = baseline (pre-edit) line number, so records stay reconcilable to the snapshot.
- Truncate `before`/`after` to 160 chars to keep ledgers cheap.
- One ledger file per agent domain: `log-<domain>.jsonl`, all under a single logs directory outside tracked code (temp dir or git-ignored dir).
- The ledger is the audit trail for a wave; the diff file set is the coverage source. When a domain has a diff but no ledger, reconstruct its audit from the diff and record the missing ledger as a defect.

## Agent Prompt Skeleton

Include in every write-agent prompt:

1. **Domain**: absolute list of files this agent owns; "do not modify any other file".
2. **Task rules file**: path to the shared rules/spec (single source of truth), not a paraphrase.
3. **Prohibitions**: no edits inside string literals; do-not-touch files/spans from pre-flight; keep line-ending style; use precise edits, never full-file rewrite.
4. **Ledger obligation**: exact logs path, schema above, "append per change, not at the end".
5. **Self-verify scope**: run only the repo's scoped checker + this domain's own test file; explicitly "do not run full pytest/mypy/project gates — the controller does".
6. **Report format**: N changes, ledger path, verification command output (pass/fail line), any leftover region you judged unsafe.

## Recovery When Agents Die (quota interruption, queueing, crash)

Read `references/recovery-playbook.md` and follow it in order. The three rules that must hold even
under time pressure:

1. **Full-batch equivalence check before triage** — prove the half-finished tree is unbroken first;
   per-file probes miss an edit in a file nobody expected to change.
2. **Coverage comes from artifacts, in three states** (landed / partial / zero artifact), cross-checked
   across the task notification's `<usage>` readings (`tool_uses`, `subagent_tokens`), `git status` file
   set, and the ledgers. Dead agents here each burned 32–97 tool uses, so no report ≠ no work; and only
   3 of 14 domains left a ledger, so no ledger ≠ no work either.
3. **Revert out-of-bounds edits in place** before accepting any file as done. Check every diff line is
   inside the allowed edit class — the incident caught an agent that had edited inside a
   `_SCRIPT = r"""…"""` literal, a constant-value change that black, isort, mypy and the annotation
   checker all pass.

Then hand the user the three-state list with a volume reading per row, and split the conclusion into
done / not-done + reason + the action handed back — never an approximate "about half done".

## Ledger Audit

Run `scripts/audit_ledger.py <logs_dir> [--claims claims.json]` to check ledgers for malformed/missing fields and duplicate records, and (optionally) cross-agent file-domain overlap against a claims file `{"agent": ["file", ...], ...}`. Use it before declaring a wave auditable.

## Resources

- `references/recovery-playbook.md` — wave-death recovery: order of operations, three-state coverage adjudication, out-of-bounds detection and revert mechanics, solo failover, hand-back contract. Load when a wave was interrupted.
- `scripts/audit_ledger.py` — stdlib-only JSONL ledger validator and cross-agent overlap checker; outputs a short pass/fail report, exit code 1 on any violation.
