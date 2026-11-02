# Shared Rules File Template

Copy to `<scratch>/<task>-RULES.md` before starting batch 2 or dispatching agents. Every worker
reads this path; do not paraphrase it into prompts. Replace `<...>` placeholders and delete
inapplicable bullets; keep the core sections (prohibitions / must-survive topics / compression
convention / density budget / terminology / self-check commands).

---

# Comment refactor rules (single standard for this task, <date>)

## Goal

Edit comments only: delete stale, duplicated, contradictory, vague or misleading comments;
compress archaeology while keeping the information a maintainer needs; correct statements that
no longer match the code; unify terminology and tone.

## Absolute prohibitions

1. No executable change: no added/removed/edited statements, constants, literals, imports,
   signatures, call order, decorators or type annotations.
2. Nothing inside a string literal: UI/i18n copy, log messages, config keys, regexes, help text.
   That text is a constant value, not a comment.
3. Do not convert `#` comments into docstrings, and do not add docstrings where the repo mandates
   `#` comments (the equivalence proof depends on comments staying out of the AST).
4. Do not change line endings. CRLF stays CRLF, LF stays LF. **Precise replacements only; a
   full-file write is forbidden.**
5. Leave verbatim: `# type: ignore`, `# noqa`, `# pyright:`/`# mypy:` directives, shebangs,
   `# -*- coding:` lines, license/copyright headers.
6. Do not touch generated or byte-pinned assets: `<list the pinned/generated files you found in Stage 0>`.
7. Never invent a fact. If unsure, keep the original comment and log it as `N-待人工确认`.
8. Do not modify files listed as do-not-touch from the pre-flight scan
   (tests asserting verbatim comment text; whitelists keyed by `path.py:<line>`): `<list>`.

## Must survive (wording may shrink, information may not)

- Design rationale — the "why": concurrency/lock order/semaphores, races, idempotency, boundary
  conditions, degradation paths, consequences of swallowed exceptions.
- Platform differences: OS specifics, frozen/bundled execution, headless console, legacy codepage.
- Ordering constraints that cannot be moved, and the reason they cannot be moved.
- Security invariants and where a check must run *before* something is backgrounded.
- I/O, logging, rotation, archival, truncation and masking contracts.
- Measured readings and their units (timeouts, sizes, ports, counts, measured timings); compress
  the prose around them, never the numbers.
- Twin/generated-copy synchronization warnings between duplicated implementations.
- Regression-lock anchors that really exist (`tests/...::test_...`). If an anchor is dead: fix it
  when the real test is findable, delete it when it is not — never leave a fabricated anchor.
- References to the project's own rule documents.

## Archaeology compression convention

- Dates and ticket IDs (`2026-xx-xx`, `M-xx`, `MID-xxxx`, `SEV-xx`, `F-xx`) are normally removed.
  Keep exactly one `[历史注] …` line when the old behavior explains why a guard exists today or when
  the ID anchors a regression lock or rule.
- Rewrite "old code did X → caused Y → now we do Z" into "current criterion + one history line".
- Example (4 lines → 2):

```
# 2026-10-21 M-42: min_samples must also be bounded by the window. The old code only had
# max(1, ...) as a lower bound, so when min_samples > window len(_samples) never reached
# the threshold and the breaker could never open for the whole lifetime of the process.
```

becomes

```
# min_samples is clamped to 1..window: the window is the hard upper bound on collectable
# samples, so a threshold above it means the breaker never opens.
# [历史注] the old implementation only bounded the lower side; a bad host kept full traffic
# and never self-healed.
```

## Deduplication

- When one explanation repeats in a file, keep the module-header or first occurrence and delete
  the rest; if each site has a different local condition, keep the shortest sentence that states
  that difference.
- Keep one structural separator where layout needs it; delete decorative repeats.

## Density budget

- Hard floor: `<repo density gate, e.g. 13.0% per Python file>`. Deleting N comment lines lowers
  density by construction: `(C-N)/(T-N) < C/T`.
- Before editing each file, record its density. Below ~16%: rewrite in place, no net deletion.
  Above ~18%: a small net-delete budget. Never let a file cross the floor.
- If a file would cross, restore a load-bearing comment (rationale/invariant/anchor), not filler,
  and rerun the gate. A per-file floor is not rescued by a healthy repo average.

## Terminology (existing project vocabulary — do not introduce synonyms)

`<list the canonical terms, e.g. breaker / probe lease / cooldown / gate / backlog / rotate /
archive / truncate / redact / mask / daemon thread / main thread / event loop / frozen>`

## Tone

- State the current criterion, not a narrative. No "we"/"you", no exclamations, no "注意!!".
- Keep single-line comments ≤ `<line-length>` for the file type.
- A one-line "what this function does" heading above a function may stay (navigation); repeats of
  that sentence inside the body are deleted.

## Per-group self-check (mandatory, every group)

1. `<skill-dir>/scripts/verify_equivalence.py --repo <root> --base <baseline_dir> <changed files>`
   must print `ALL OK` and exit 0.
2. `<skill-dir>/scripts/refactor_guard.py guard --repo <root> --base <baseline_dir>
   --strict-readings` must report `FAIL 0`; run `refactor_guard.py preflight --repo <root> --base
   <baseline_dir> --floor <floor>` before editing and after the first batch to catch density,
   lock and anchor breaks.
3. `<repo formatter check command>` must report no reformat needed. If the only complaint is blank
   lines left behind by a deleted comment, delete the blank line (that is still comment-only).
4. Append every change to `<scratch>/logs/log-<group>.jsonl`, one line per change, immediately
   after making it:

```json
{"file":"path/from/repo/root","line":123,"action":"delete|compress|dedupe|correct","category":"S1|S2|S3|S4|S5|N","before":"<=160 chars","after":"<=160 chars","reason":"why this is correct"}
```

   `line` is the **pre-edit baseline** line number; `before`/`after` truncated to 160 chars.
   Define the tag legend for this task at the top of this file and keep it stable across groups, so
   the closing tally is comparable. Verified default (source session `fcc124ca`): S1 contradicts or
   misleads about current code; S2 archaeology/date/ticket compression; S3 duplicate explanation;
   S4 vague "what it does" line; S5 verbose but valid; N pending human decision (do not edit).
5. Do **not** run the project-wide suite/type checker/gate sweep — concurrent runs interfere and
   each burns the batch's time. The controller runs them once after the last edit.
6. Report: number of changes, ledger path, the verification command's last line, any region you
   judged unsafe to touch, and the six sections in `references/report-template.md`.
