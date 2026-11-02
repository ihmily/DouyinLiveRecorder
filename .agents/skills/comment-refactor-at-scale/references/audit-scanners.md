# The Audit Scanners

Equivalence proves nothing changed in the code. These four checks prove the comments themselves
are still worth reading. Run them after the equivalence pass, then re-run the equivalence pass if
any fix touches a file again.

## Runnable shortcuts

`scripts/audit_comments.py` implements the three checks that are easy to get subtly wrong. It is
stdlib-only and treats its output as candidates, never as verdicts.

```bash
# S1–S5 + K candidate inventory (JSON keeps every finding; stdout is truncated)
python <skill-dir>/scripts/audit_comments.py --repo <root> --paths src web --json <scratch>/candidates.json
# Theme survival over comments only; --strict exits 1 when a baseline theme drops to zero
python <skill-dir>/scripts/audit_comments.py --repo <root> --themes <scratch>/themes.txt --baseline <baseline>
# Ledger coverage/format: malformed JSON, missing keys, duplicate rows, changed file without a record
# Scope with --paths <task dirs> or --allow-unlogged <file> for changes made by another task.
python <skill-dir>/scripts/audit_comments.py --repo <root> --ledger-dir <scratch>/logs --ledger-only --strict
```

Use the inline commands below when you need the full text (the theme script below counts whole
files; the tally below prints a per-agent breakdown). The ledger shortcut is the one that turns
"a diff exists" into "a diff exists and every file has a stated reason"; the 2026-10-26 tree had a
one-line `_tars.py` edit with no row while the report called that domain unchanged.

## 1. Ledger tally — what was actually done

Aggregate the change ledger by category and action, per group and repo-wide:

```bash
python - <<'PY'
import json, collections, pathlib
rows = collections.Counter()
per_file = collections.Counter()
for p in sorted(pathlib.Path("<scratch>/logs").glob("log-*.jsonl")):
    n = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rows[(rec["action"], rec["category"])] += 1
        per_file[rec["file"]] += 1
        n += 1
    print(f"{n:5d}  {p.name}")
print(dict(rows))
print("files touched:", len(per_file), "| records:", sum(per_file.values()))
PY
```

Use it three ways: the totals go into the report; a group with a ledger but no diff (or vice versa)
is an audit break; and `sum` vs `git diff --numstat` comment-line delta is the sanity check that no
change went unlogged.

Cross-check overlap when several agents worked: the same file appearing in two ledgers means the
file domains were not disjoint. Coverage is an audit-trail metric, not a behavior metric: a
changed file with no ledger row can still pass `verify_equivalence` (it did for 173 files on the
2026-10-26 tree, whose first batch predates the ledger). Report it as an audit gap and name the
files; do not translate it into "the code changed".

## 2. Comment-reference integrity

```bash
python <skill-dir>/scripts/check_comment_refs.py --repo <root> --show-ok-count
python <skill-dir>/scripts/check_comment_refs.py --repo <root> --paths src web --strict
```

For every comment it extracts paths, `file::Class::test_name` anchors, `file.py:<line>` anchors and
backticked symbols, then checks them against the identifier universe built **after comments are
stripped** (Python via `ast.dump`, JS/CSS/HTML/VBS via the comment-stripped text). Output buckets:

- `drift-prone` — valid `file:line` anchors; each one is a future false alarm when any line is added
  or removed above it. Convert to symbol anchors as a separate, approved change.
- `HIGH` — provably wrong: cited repo file absent, cited class/test/symbol not in the stripped code,
  or a line number beyond the file's end. `--strict` exits 1 on these.
- `MED` — first path segment is not a repo root, or the name is a placeholder (`foo`, `x`,
  `test_x.py`): usually external packages, remote URLs, generated paths or hypothetical examples.
  Confirm by hand, then ignore for this task.
- `LOW` — bare filename/symbol mentions that only make sense in context.

Extraction is tokenizer/AST based, so text that merely *looks* like a comment inside a string
literal is not scanned, and a string-literal edit is not mistaken for a comment reference.

This scanner sees comments only. A whitelist such as
`ALLOWED_UNRESOLVED_BY_NAME_CALLS = {"src/ui_i18n.py:34"}` lives in a string constant, so it is
invisible here; `refactor_guard.py preflight` scans code and string constants for
`path.py:<line>` and fails when the cited file's line count changed.

Measured on a 276-file Python+frontend repo: 2403 references resolved, 2 drift-prone line anchors,
14 HIGH, 54 MED, 126 LOW, runtime ≈ 9 s. The HIGH bucket included genuine stale paths to a module
that had been inlined away (4 citing files) and a doc directory that no longer existed — both
invisible to the equivalence check. Read it as a candidate list: prose that mentions a hypothetical
`tests/utils.py` will also land there, so the bucket is triaged, never auto-fixed.

## 3. Theme survival — load-bearing topics must not vanish

Pick the phrases that name the contracts worth keeping (from the rules file's must-survive list and
the terminology table), one per line in `<scratch>/themes.txt`, then compare the baseline and the
current tree **over the shared file set** (a baseline mirrors only part of the repo, so comparing
whole trees measures the mirror, not the edit):

```python
# 承重主题存活计数：对基线与当前的**同一文件交集**逐主题给出 前/后/变化，并单列归零主题。
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
base, cur, phrases_file = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
EXTS = {".py", ".js", ".mjs", ".css", ".html", ".vbs"}
EXCS = {".git", ".venv", "node", "ffmpeg", "downloads", "__pycache__", "logs", "build", "dist"}


def rel_code_files(root: Path) -> set[str]:
    out = set()
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        rel = p.relative_to(root)
        if any(part in EXCS for part in rel.parts):
            continue
        out.add(rel.as_posix())
    return out


def corpus(root: Path, names) -> str:
    return "\n".join((root / n).read_bytes().decode("utf-8-sig", errors="replace") for n in sorted(names))


shared = rel_code_files(base) & rel_code_files(cur)
before, after = corpus(base, shared), corpus(cur, shared)
rows, zeroed = [], []
for phrase in (ln.strip() for ln in phrases_file.read_text(encoding="utf-8").splitlines() if ln.strip()):
    b, a = before.count(phrase), after.count(phrase)
    rows.append((phrase, b, a, a - b))
    if b and a == 0:
        zeroed.append(phrase)
print(f"comparing {len(shared)} shared code files")
for phrase, b, a, d in sorted(rows, key=lambda r: r[3]):
    print(f"{b:6d} -> {a:6d} ({d:+d})  {phrase}")
print("ZEROED (主题被整体删除):", ", ".join(zeroed) if zeroed else "none")
```

Run: `python <scratch>/theme_survival.py <baseline_dir> <repo_root> <scratch>/themes.txt`
(the first argument may be the repo itself when no snapshot exists and `git diff` is the baseline).

Reading the output:

- A theme with a **negative delta** is expected (compressing archaeology removes mentions); a theme
  that is **zeroed** is a lost contract and must be restored, not explained away.
- A theme at `0 -> 0` means the phrase never existed on either side — the theme list itself is wrong;
  pick phrases the code comments actually use.

Measured on the 260-file slimming set (baseline vs post-refactor tree), every load-bearing topic
survived: `掩码 63 -> 61`, `熔断 142 -> 141`, `脱敏 234 -> 233`, `守护线程 76 -> 76`,
`探针租约 3 -> 3`, `孪生副本 11 -> 11`, `rebind_console_sink 21 -> 21`, `凭据红线 11 -> 12`,
`ZEROED: none`. The same scanner run against a stale-phrase probe caught a phrase the refactor had
to correct: `2026-09-17 定稿 1 -> 0`, reported as ZEROED.

Note the metric counts occurrences across the whole file text, not only comments; for
Chinese/prose-only phrases the two are equivalent, but a symbol name that also appears in code
inflates both sides equally, which is why only the *direction and the zero case* are meaningful.

## 4. Readings survival — measured numbers must not evaporate

```bash
python <skill-dir>/scripts/refactor_guard.py guard --repo <root> --base <baseline> --strict-readings
```

An equivalence-clean edit can still turn `203KB → 200MB, peak 405MB` into "large payload" and pass
every structural check. The guard extracts numeric tokens from baseline comments (units such as
KB/MB/ms/s/% plus multi-digit values and slash sequences), filters dates and ticket IDs, and
reports any token that no longer appears anywhere in the current file. Triage it as a candidate
list: restore the reading verbatim, or record why it is obsolete. Never replace a reading with an
adjective. Verified instance: `src/async_http.py` lost `203KB → 200MB, peak 405MB`, and
`web/style.css` lost mobile viewport values; both were restored.
