# Verified Failure Modes

Each entry is a failure that actually happened during a comment-only refactor, with the detection
command that found it. Repo-specific instances are labelled; the mechanism generalizes.

## 1. Comment edit landed inside a string literal

- **Symptom**: the compare tool prints `[FAIL] 逻辑签名不一致 -> 疑似改动了可执行代码`. Verified
  instance: `tests/test_gui_tail_robustness.py` holds a `_SCRIPT = r"""..."""` subprocess payload;
  a comment-looking line inside that string was edited, and the AST signature check was the only
  metric that caught it. Treat every `_SCRIPT`/`_PAYLOAD` heredoc-style constant as a high-risk
  zone, not just the files that happened to be caught.
- **Mechanism**: comments never enter the AST, but the **value** of a string constant does. Text
  after `#` inside such a string is data; editing it changes the constant.
- **Prevention**: decide, before editing, whether the target text is part of a constant's value.
  Extract comments with `tokenize`/AST, never with a line-based regex.
- **Second failure in the same round**: the formatter then demanded `# （` spacing for a shortened
  comment. One edit, two independent red surfaces — fix both before declaring the group done.

## 2. CRLF → LF conversion invisible to the AST and to black

- **Symptom**: signature check passes, formatter passes, but the diff shows the whole file rewritten.
- **Mechanism**: `Path.write_text()` (and most "fix the file" fallbacks) normalize EOL. Line
  endings are not part of the AST, and formatter configs are often EOL-agnostic.
- **Detection**: decode with the declared/BOM encoding first, then compare the CRLF / LF / CR
  counts between baseline and current and require the same profile — a file whose LF-only count
  was 0 must still have 0. Byte-level counting is invalid for UTF-16 (`\r\n` is stored as
  `0D 00 0A 00`), which is why `scripts/verify_equivalence.py` decodes before comparing and also
  fails on an encoding/BOM change; it prints
  `FAIL ... EOL shape ('crlf','pure') -> ('lf','pure')` or
  `encoding utf-8 -> utf-16-le+bom`.
- **Prevention**: precise replacements only; never re-emit a whole file.

## 3. A replacement swallowed a newline and turned code into a comment

- **Symptom**: a declaration silently stopped existing. Found twice in `web/app.js`
  (`var SENSITIVE_MASK = '***';` and the `saveQualityOptions` declaration each merged into the
  preceding comment line).
- **Mechanism**: `old_string` ended with `\n` while `new_string` did not (or the reverse), so two
  lines merged.
- **Detection**: comment-stripped code-line sequence comparison (non-Python side of
  `verify_equivalence.py`) — the merged line vanishes from the code sequence; for Python,
  `node --check` / `ast.parse` may still succeed, which is why the code-line metric is mandatory.

## 4. Deleting a comment phrase a test asserts verbatim

- **Symptom**: an unrelated test turns red after a "pure comment" edit.
- **Verified instances (DouyinLiveRecorder)**:
  - `tests/test_sync_probe_internal_guard.py::TestHopGuardWiringLocks::test_async_hop_guard_comment_no_longer_claims_sync_side_is_unwired`
    requires the literal `[历史注 2026-09-30` inside `src/async_http.py` and requires an older
    phrase to be absent.
  - `tests/test_ffmpeg_path_preference.py` requires a back-reference comment pointing at the
    standalone twin copy.
  - `tests/test_agent_hook_guard.py::test_protected_dirs_match_agents_md_enumeration` extracts its
    comparison basis from a parenthesized enumeration in AGENTS.md by regex; converting that
    enumeration to a comma list reddens the lock before any code is touched.
- **Detection, before deleting anything**: `grep -rn "<exact phrase you plan to remove>" tests/`.
- **Decision rule**: restore the locked literal; do **not** adjust the test constant to fit the edit.

## 5. Line-number anchors that drift on any insert or delete

- **Symptom**: whitelists keyed `path.py:<line>` break when a comment above the anchor is removed —
  two assertions fire at once (new unmatched item + stale allowlist entry).
- **Verified instance**: `tests/test_i18n_catalog_coverage.py::ALLOWED_UNRESOLVED_BY_NAME_CALLS =
  {"src/ui_i18n.py:34"}`.
- **Detection**: `python <skill-dir>/scripts/check_comment_refs.py` prints a
  `[drift-prone] … :<line>` bucket, and flags a numeric anchor beyond the cited file's length as HIGH.
- **Handling**: mark every file referenced by such a whitelist do-not-touch for this task. Fixing
  the anchor into a symbol reference is a **separate** approved change, not part of a comment sweep.
- **Verified outcome**: the controller restored `src/ui_i18n.py` to its baseline instead of
  editing the test constant; the anchor stayed valid and the whole fix stayed comment-only.
- **Also observed**: a doc comment may already cite a stale line number before the task starts
  (`async_http.py:518` was wrong at baseline). Report it as "pre-existing, not caused by this
  batch" and hand it back rather than absorbing it into the wave.

## 6. Snapshot scope did not cover what was edited

- **Symptom**: the compare tool reports "equivalent N files" while edited files were never compared.
- **Verified instance**: `check_annotations.py --snapshot` mirrors `.py` plus top-level `web/**`
  only; `tests/frontend/*.mjs` and the root `index.html` are outside it and need their own copies.
  The same tool skips its own `EXCLUDE_FILES`, one of which is still inside the type checker's
  scope, so it needs a separate `ast.dump` comparison.
- **Detection**: subtract the snapshot's file list from `git diff --name-only`; anything in the
  difference was unverified.

## 7. Over-deletion trips the per-file comment-density floor

- **Symptom**: the annotation gate fails with `[密度] <file>: <x>% 低于阈值 <y>%` for a single file
  while the repo average looks fine. Verified instance: DouyinLiveRecorder's
  `scripts/check_annotations.py`, default floor 13.0%, enforced **per Python file**; one wave left
  `tests/test_spider_platform.py` at 12.8%, and restoring the "why this assertion" sentence — not
  filler — brought it back. Files already below ~16% are rewrite-only; deleting lines cannot raise
  their density. Twelve other files sat at 13.12%–13.87%, within one point of the 13.0% floor, so
  every one of them was rewrite-only.
- **Detection**: the compare command prints before→after density per file; run the density check
  with its `--min-density` option to see the margin instead of guessing.
- **Handling**: restore a load-bearing comment (rationale, invariant, anchor) rather than adding
  filler; if the file legitimately deserves a lower density, that is a policy change for the user
  to approve, not part of this task.

## 8. Dependency gap masquerading as a mass regression

- **Symptom**: a comment edit appears to break the suite — 739 failures, of which 736 were
  `async def functions are not natively supported`, caused by a missing dev dependency
  (`pytest-asyncio`) that made `asyncio_mode` an unknown config option.
- **Detection**: group failures by shared error signature and compare against the total; then check
  `pip list` against the declared dependency list before suspecting the diff.
- **Reporting discipline**: state "gates green" and "pytest undecidable due to missing dependency"
  as two separate facts, name the repair command, and leave the environment change to the user when
  project rules forbid the agent touching it. Never claim the suite passed.

## 9. Byte-pinned or non-UTF-8 comment targets

- **Verified instance**: `src/javascript/*.js` (incl. `crypto-js.min.js`) are pinned by raw-byte
  SHA-256 expectations in `src/utils.py::_JS_SHA256_EXPECTED`, with a test that asserts every
  executable JS is pinned — one changed character breaks runtime verification. `StopRecording.vbs`
  is UTF-16LE + BOM, so ordinary text search treats it as binary and byte-level checks mislead.
  `src/proto/douyin_pb2.py` is generated.
- **Detection**: grep the repo for hash pins / `sha256` expectations referencing the file list; check
  declared encodings; look for generated-file headers.
- **Handling**: exclude them from the task and say so in the report.

## 10. Measured readings compressed into vaguer prose

- **Symptom**: the comment still explains the behavior, but the number that makes it actionable is
  gone: `203KB → 200MB, peak 405MB` became "large payload"; mobile viewport values became
  "responsive widths".
- **Detection**: `refactor_guard.py guard --strict-readings` extracts numeric tokens from baseline
  comments and reports any that no longer appear anywhere in the current file. Also scan deleted
  lines for digits; the structural checks are blind here.
- **Handling**: restore the reading verbatim, or record why it is obsolete. Ticket/date numbers
  may disappear; sizes, timeouts, counts and ports may not.

## 11. Interrupted workers leave unlogged edits

- **Symptom**: a quota or round-limit interruption leaves changed files with no ledger rows, or a
  worker claims "no changes" for a domain that was actually edited.
- **Verified instance**: three `tests/frontend/*.mjs` files were edited without ledger entries;
  the controller rebuilt the audit with `git show HEAD:<file>`, comment-stripped line comparison
  and the full `node --test` suite. A separate sweep domain reported zero changes and was confirmed
  by the same artifact check.
- **Verified instance (2026-10-26 tree)**: `src/platforms/_tars.py` had a one-line comment edit
  (`CR-03` removed) but no ledger row, while the closing report listed that file as unchanged.
  `audit_comments.py --ledger-dir <logs> --ledger-only --strict` caught the diff-vs-ledger gap.
- **Handling**: treat a domain as complete only when the artifact check passes. Reconstruct from
  `git show HEAD:`, the baseline, the ledger and the affected tests — never from the worker's
  narrative. Report completed, partial and zero-change domains separately.

## 12. A HEAD/archive baseline flips EOL

- **Symptom**: `preflight` reports `EOL shape changed: <file> crlf -> lf` for most of the tree
  while `verify_equivalence.py` against the working-tree snapshot says `ALL OK`.
- **Mechanism**: `git show`/`git archive` returns the **blob**, not the checkout. With
  `core.autocrlf` the working tree is CRLF and the blob LF, so a HEAD archive is not a valid
  EOL/density baseline.
- **Verified instance (2026-10-27)**: a HEAD-archive baseline produced 135 false EOL failures on
  the 2026-10-26 tree; the original working-tree snapshot verified 260/260.
- **Handling**: use the working-tree snapshot for EOL/density; use `git show` only for structural
  comparison, or rewrite the rebuilt file to the current EOL profile before preflight.

## 13. Preflight lock hits include prose and generic prefixes

- **Symptom**: `locked phrase removed: '[历史注'` or a short ticket ID that a test merely mentions
  in prose, not in an assertion.
- **Mechanism**: token extraction treats any occurrence in `tests/` or `scripts/` as a lock; the
  bare `[历史注` prefix is shared by unrelated notes, so removing one note looks like removing
  text another test cites.
- **Verified instance (2026-10-27)**: 107 removed-lock candidates included one generic
  `[历史注` token that listed 100+ locations; after the prefix fix it disappeared. Short IDs also
  matched longer ones as substrings (`M-2` inside `M-22`); `needle_in_line()` now requires token
  boundaries for bare ticket IDs, which cut the remaining candidates from 106 to 95 on that
  baseline. Triage each: an assertion is a lock; a prose mention is not.
- **Handling**: restore an assertion hit; ignore a prose mention or shared prefix. Confirm the
  exact token before restoring; a short ticket ID may be a prefix of a longer one.
