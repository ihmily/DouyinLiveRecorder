# Delivery Report Template

Use the user's language. Keep these six sections in this order. Every number must come from a
command run **after the last edit**; a number from an earlier run is not closing evidence. Mark
every unverified boundary explicitly and turn it into a next task instead of an adjective.

## 1. Delivery status

| Item | Result |
| --- | --- |
| Audit scope | `<N>` tracked files (`<a>` `.py` + `<b>` frontend/script assets) |
| Files changed | `<N>` (`<by area>`); `<unchanged>` confirmed equal |
| Diff volume | `+<A> / -<B>` (net `<C>`); comment lines `before → after` (net `<D>`) |
| Ledger | `<N>` records in `<M>` JSONL files; overlap/coverage audit `<OK/FAIL>` |
| Unfinished | exact domains, count, and why (quota, missing dependency, user decision) |

## 2. Proof matrix

| Dimension | Command | Result | Evidence boundary |
| --- | --- | --- | --- |
| Baseline | `refactor_guard.py snapshot --all` or repo tool | `<N>` files | list what the snapshot excludes |
| Structural equivalence | `verify_equivalence.py` / `refactor_guard.py guard` | `ALL OK` / `FAIL n` | AST for `.py`; stripped code lines for frontend |
| Encoding / EOL | `refactor_guard.py preflight` | shape unchanged / changed | BOM and CRLF/LF/bare-CR profile |
| Density | `refactor_guard.py preflight --floor <f>` | min `<x>%`, floor `<f>%` | per-file, not repo average |
| Theme survival | `audit-scanners.md` theme script | `ZEROED: none` | phrases listed in `<themes.txt>` |
| Readings survival | `refactor_guard.py guard --strict-readings` | `0 lost` / `<N>` candidates | advisory unless `--strict-readings` |
| Aggregated gates | repo gate runner | `<n>/<n>` green | run after the final edit |
| Tests | affected files / full suite | `<passed>/<failed>` | classify every failure below |

Failure classification: `<shared signature>` appears `<k>` times of `<total>` failures; environment
vs regression; pre-existing reds with both inputs proven untouched. If a dependency is missing,
write "suite undecidable", name the repair command, and leave the environment change to the user
when project rules forbid it.

For each interrupted worker domain, add one line: `completed / partial / zero-change`, the artifact
evidence (`git show HEAD:`, baseline, ledger, tests), and what the controller re-ran. Do not accept
the worker's narrative as evidence.

## 3. Classification list

| Severity | Category | Measured scale | Location / sample | Disposition |
| --- | --- | --- | --- | --- |
| S1 | contradicts/misleads vs code | `<n>` | `<symbol>` / `<test>` | fixed / kept with reason |
| S2 | archaeology, dates, ticket IDs | `<n>` | `<file>` | compressed to one history line |
| S3 | duplicate explanation | `<n>` | `<file>` | kept first full occurrence; pointers elsewhere |
| S4 | vague "what it does" | `<n>` | `<file>` | deleted inside body; headings kept |
| S5 | verbose but valid | `<n>` | `<file>` | compressed; every criterion kept |
| N | pending human decision | `<n>` | `<file>` | left untouched; question stated |

Dedupe note: state which occurrence was kept (module header or first full occurrence) and how the
remaining sites point back. List every `N` item with the exact question the user must decide.

## 4. Implemented minimal fixes

- Representative before/after pairs, anchored by symbol or unique statement, not `file:line`.
- For each: what changed, why it is correct now, and what was deliberately left alone.
- Include the locks that were restored verbatim (test-asserted phrases, whitelist anchors).

## 5. Exclusions / non-goals

- Hash-pinned, generated or non-UTF-8 assets (name the pin or encoding).
- Files locked by tests or line-number whitelists; the lock and why it stays.
- Behavior changes, ID-retirement sweeps, or other work deferred to a separate task.

## 6. Handbacks / next batch

- Environment repairs (e.g. missing dev dependency) and who must run them.
- Pre-existing failures, with proof they predate this batch.
- Exact remaining files or domains, with counts and why they were not covered.
- Policy decisions needed (lower a density floor, retire ticket IDs, migrate anchors).

## Optional batch delta

| Batch | Files | Comment lines | Ledger | Gates | Tests |
| --- | --- | --- | --- | --- | --- |
| 1 | `<n>` | `<before → after>` | `<n>` | `<n>/<n>` | `<passed>/<failed>` |
| 2 | `<n>` | `<before → after>` | `<n>` | `<n>/<n>` | `<passed>/<failed>` |
| Total | `<n>` | `<net>` | `<n>` | — | — |
