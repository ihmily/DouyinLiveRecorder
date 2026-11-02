# Wave Recovery Playbook

Load this when a dispatched wave of write agents died mid-run (quota cap, model queueing, crash,
turn cap) and the completed scope must be reconstructed. All readings below are from the
2026-10-26 incident this skill was derived from: 14 concurrent write agents, **all 14 interrupted**
— 4 on `Queuing failed. Try again later or enter /model to switch models.` and 10 on
`You've reached your daily usage limit for Chat.`

## 1. Order of operations

1. **Full-batch equivalence check first, triage second.** Run the repo's own whole-tree
   equivalence/consistency checker over every file the wave could touch, before deciding what is
   done. Per-file probes are not enough: they check the file you expect to have changed, not the
   file that changed by accident.
2. Then build the coverage table (§2).
3. Then detect and revert out-of-bounds edits (§3).
4. Only then decide whether anything is re-dispatched (§4), and write the hand-back (§5).

## 2. Coverage from artifacts, in three states

Never adjudicate from the agent's narration. Cross-check three independent artifact channels per
domain:

- **Task notification `<usage>` block** — `tool_uses`, `subagent_tokens`, `duration_ms`. Dead agents
  in this incident each reported 32–97 `tool_uses`, i.e. substantial work landed with no chat report
  at all. A missing report is not evidence of nothing happening.
- **`git status --short` / `git diff --name-only`** — the actual touched-file set, reconciled against
  the exact file list each agent was assigned.
- **Ledger files** — `wc -l log-<domain>.jsonl` and the records themselves.

Per-domain verdict:

| State | Signals | Action |
| --- | --- | --- |
| Landed | diff + ledger + own test file pass (or scoped checker clean) | Do not re-dispatch; fold records into the batch audit |
| Landed but unauditable | diff non-empty, **no ledger** | Do not re-dispatch; reconstruct the audit from the diff itself and record "ledger missing" as a defect of that wave |
| Partial | ledger stops mid-file, or scoped checker fails, or locks red | Main session finishes the remainder |
| Zero artifact | no diff, no ledger, and the notification shows no meaningful `tool_uses` | Republish that domain only |

The no-ledger case is the norm, not the exception: only **3 of 14** domains wrote a ledger here,
while most of their edits had already landed. So ledger absence must never be read as work absence —
the diff set is the primary coverage source, the ledger is the audit trail for it.

## 3. Out-of-bounds edits: detect, then revert in place

A dead agent's leftover damage is usually an edit outside its allowed class, invisible to
black/isort/mypy. Detect it mechanically before accepting any file as done:

- **Python**: every added/removed diff line must be a comment line after stripping; `ast.dump` must
  equal the pre-wave baseline; per-file CRLF/LF counts must be unchanged (both AST and `black` are
  blind to a whole-file line-ending flip).
- **JS / CSS / HTML / VBS**: strip comments, then compare the remaining code lines to baseline.
- **String literals are values, not comments.** An agent told to slim comments will "fix" copy inside
  a literal if the prompt allows it. In this incident an agent edited inside
  `_SCRIPT = r"""…"""` — a constant-value change that every normal gate passes. The
  diff-lines-are-all-comments check is what caught it.
- **Comment-text locks**: this repo has tests that assert verbatim comment phrases (e.g. a dated
  `[历史注 …]` prefix) and allowlists anchored as `path.py:<line>` that drift when comment lines are
  removed above them. When a suite goes red after comment edits, first separate environment failures
  (a missing plugin produces hundreds of identical collection errors) from real ones, then revert the
  offending file instead of editing the test.

Revert mechanics: restore the single file from the pre-wave baseline snapshot. `git checkout -- <one
path>` also works but is destructive for that file's uncommitted changes — confirm those changes
belong to the current batch first, and never widen it to a directory.

## 4. Stop dispatching: switch the main session to Solo

Queueing and daily-cap errors mean the quota is gone for the rest of the session; further agents
will die the same way and leave less auditable debris.

- Do not launch more write agents once these errors appear — including "one more just for this
  domain".
- Finish the remainder in the main session, taking the unowned files only.
- Re-dispatch only when a fresh quota window is confirmed **and** the domain is in the zero-artifact
  state. Keep waves at 3–4 agents, and wait for each wave's notifications before starting the next.
- Record the strategy switch in the report ("parallel → solo after N queue/cap failures") so the
  next session does not repeat the oversized wave.

## 5. Hand-back contract

- A three-state table (landed / partial / no artifact) with, per row, the file path **plus a volume
  reading** — remaining lines, remaining comment blocks, `wc -l` — so the user can size the next
  batch without re-measuring.
- Conclusion separates 已完成 from 未完成 + reason + the action handed back. Approximate wording
  ("about half done") is a defect.
- State which gates ran **after the last edit** and which did not; a gate run before the final
  revert proves nothing.
- Pre-existing breakage found during triage gets reported as "not caused by this batch" and handed
  back — do not fix it inside the recovery wave.

## Resources

- `../scripts/audit_ledger.py` — run before declaring a wave auditable; reports malformed, missing
  and duplicate ledger records, plus cross-agent file-domain overlap when given a claims file.
